// Typed-ish client for the RaplMail backend.
//
// In browser dev, Vite proxies `/api` -> the Python backend (no token needed in
// dev mode). When running inside Tauri, the shell injects window.__RAPLMAIL__ =
// { base, token } and we talk to the sidecar directly with the shared secret.

// Resolve how to reach the backend. In the Tauri desktop shell, the Rust side
// spawned the backend on a random localhost port with a per-launch token and
// exposes them via the `backend_config` command. In browser dev, Vite proxies
// `/api` -> the backend (no token). We resolve once and wait for readiness.
let cfg = null;
let cfgPromise = null;

function isTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function resolveCfg() {
  // The isolated sandbox window must never reach the backend (it has no token
  // and no capability to). Short-circuit so nothing polls /health from there.
  if (typeof location !== "undefined" && location.hash === "#sandbox") return { base: "", token: "" };
  if (!isTauri()) return { base: "/api", token: "" };
  const { invoke } = await import("@tauri-apps/api/core");
  const c = await invoke("backend_config");
  // Wait for the sidecar to finish booting (PyInstaller unpack can take ~1-2s).
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${c.base}/health`, { headers: { "X-RaplMail-Token": c.token } });
      if (r.ok) break;
    } catch {}
    await new Promise((res) => setTimeout(res, 250));
  }
  return c;
}

function getCfg() {
  if (cfg) return Promise.resolve(cfg);
  if (!cfgPromise) cfgPromise = resolveCfg().then((c) => (cfg = c));
  return cfgPromise;
}

/** @param {string} path @param {RequestInit} [opts] */
async function request(path, opts = {}) {
  const c = await getCfg();
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (c.token) headers["X-RaplMail-Token"] = c.token;
  const res = await fetch(`${c.base}${path}`, { ...opts, headers });
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    throw new ApiError(detail, res.status);
  }
  return data;
}

export class ApiError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  // opts passthrough (e.g. { keepalive: true } for saves during unload).
  put: (p, body, opts) => request(p, { method: "PUT", body: JSON.stringify(body), ...(opts || {}) }),
  patch: (p, body) => request(p, { method: "PATCH", body: JSON.stringify(body) }),
  del: (p) => request(p, { method: "DELETE" }),
};

// Resolved synchronously once cfg is known (after boot). Used for <img src>,
// which can't go through the async request() helper or send auth headers.
export function avatarUrlDomain(domain) {
  const d = (domain || "").toLowerCase().trim();
  if (!d || !d.includes(".")) return "";
  const base = cfg ? cfg.base : "/api";
  return `${base}/avatars/${encodeURIComponent(d)}`;
}
export function avatarUrl(email) {
  return avatarUrlDomain((String(email || "").split("@")[1] || ""));
}

// Fetch an attachment as a Blob (authenticated; can't use <a href> for that).
export async function fetchAttachment(messageId, index) {
  const c = await getCfg();
  const headers = {};
  if (c.token) headers["X-RaplMail-Token"] = c.token;
  const res = await fetch(`${c.base}/messages/${messageId}/attachments/${index}`, { headers });
  if (!res.ok) throw new ApiError("Couldn't download attachment", res.status);
  return res.blob();
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}

// Fetch an attachment and return it in the shape Compose expects, so a forward
// can re-attach the original files instead of dropping them.
export async function fetchAttachmentForCompose(messageId, att) {
  const blob = await fetchAttachment(messageId, att.index);
  return {
    filename: att.filename || "attachment",
    content_type: att.content_type || att.mail_content_type || blob.type || "application/octet-stream",
    data_b64: await blobToBase64(blob),
    size: blob.size,
  };
}

// Open an attachment with the OS default app. In the Tauri shell we must write
// the bytes to disk via Rust and open the path (blob: URLs don't reach the OS).
// In a browser we open a blob URL in a new tab.
export async function openAttachment(messageId, index, filename) {
  const blob = await fetchAttachment(messageId, index);
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("open_attachment", { filename: filename || "attachment", dataB64: await blobToBase64(blob) });
    return;
  }
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// Save an attachment to disk. Returns the saved path in Tauri, else null.
export async function saveAttachment(messageId, index, filename) {
  const blob = await fetchAttachment(messageId, index);
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("save_attachment", { filename: filename || "attachment", dataB64: await blobToBase64(blob) });
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename || "attachment"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return null;
}

// "Save as…": pick a destination via the native dialog, then write the bytes
// there. Returns the saved path, or null if the user cancelled / in the browser.
export async function saveAttachmentBytesAs(filename, contentType, dataB64) {
  if (isTauri()) {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const { invoke } = await import("@tauri-apps/api/core");
    const path = await save({ defaultPath: filename || "attachment" });
    if (!path) return null;  // cancelled
    return invoke("save_attachment_to", { path, dataB64: dataB64 || "" });
  }
  // Browser: a plain download (the OS may still prompt depending on settings).
  const url = URL.createObjectURL(b64ToBlob(dataB64, contentType));
  const a = document.createElement("a");
  a.href = url; a.download = filename || "attachment"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return null;
}

export async function saveAttachmentAs(messageId, index, filename) {
  const blob = await fetchAttachment(messageId, index);
  return saveAttachmentBytesAs(filename, blob.type, await blobToBase64(blob));
}

function b64ToBlob(dataB64, contentType) {
  const bin = atob(dataB64 || "");
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: contentType || "application/octet-stream" });
}

// Open raw bytes (base64) with the OS default app. Used when the caller already
// holds the bytes — an uploaded local file, or a "trust & open" out of the
// sandbox — rather than a message attachment index.
export async function openAttachmentBytes(filename, contentType, dataB64) {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("open_attachment", { filename: filename || "attachment", dataB64: dataB64 || "" });
    return;
  }
  const url = URL.createObjectURL(b64ToBlob(dataB64, contentType));
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// Save raw bytes (base64) to disk. Returns the saved path in Tauri, else null.
export async function saveAttachmentBytes(filename, contentType, dataB64) {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("save_attachment", { filename: filename || "attachment", dataB64: dataB64 || "" });
  }
  const url = URL.createObjectURL(b64ToBlob(dataB64, contentType));
  const a = document.createElement("a");
  a.href = url; a.download = filename || "attachment"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return null;
}

// Fetch an attachment's bytes as base64 (for handing to the sandbox window).
export async function fetchAttachmentB64(messageId, index) {
  const blob = await fetchAttachment(messageId, index);
  return { data_b64: await blobToBase64(blob), size: blob.size, content_type: blob.type };
}

// Export a message as .eml (Safe Export strips internal headers + tracking pixels
// when sanitize=true). Saves to disk in Tauri, blob-downloads in the browser.
export async function saveEml(messageId, sanitize = true, filename = "message.eml") {
  const c = await getCfg();
  const headers = {};
  if (c.token) headers["X-RaplMail-Token"] = c.token;
  const res = await fetch(`${c.base}/messages/${messageId}/export?sanitize=${sanitize ? "true" : "false"}`, { headers });
  if (!res.ok) throw new ApiError("Couldn't export the message", res.status);
  const blob = await res.blob();
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("save_attachment", { filename, dataB64: await blobToBase64(blob) });
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  return null;
}

export async function revealPath(path) {
  if (!path || !isTauri()) return;
  try { const { invoke } = await import("@tauri-apps/api/core"); await invoke("reveal_path", { path }); } catch {}
}

// Open an http(s)/mailto URL in the OS default browser (links inside emails).
export async function openExternal(url) {
  if (!url) return;
  if (isTauri()) {
    try { const { invoke } = await import("@tauri-apps/api/core"); await invoke("open_url", { url }); return; } catch {}
  }
  try { window.open(url, "_blank", "noreferrer"); } catch {}
}

export const unfurl = (url) => api.get(`/unfurl?url=${encodeURIComponent(url)}`);

// Tier-2 deep analysis (macro de-obfuscation, PDF stream decompression) for the
// sandbox. Runs in the backend (extraction only, never executes the file).
export const sandbox = {
  analyze: (filename, dataB64) => api.post("/sandbox/analyze", { filename, data_b64: dataB64 }),
};

// Absolute base URL of the backend (e.g. http://127.0.0.1:8765), once resolved.
// Used to show the user the local /metrics URL for LAN devices.
export function backendBase() {
  const base = cfg ? cfg.base : "/api";
  if (base.startsWith("http")) return base;
  try { return `${location.origin}${base}`; } catch { return base; }
}

export const appSettings = {
  get: () => api.get("/settings"),
  put: (data, opts) => api.put("/settings", { data }, opts),
  export: () => api.get("/settings/export"),
  import: (bundle) => api.post("/settings/import", bundle),
  exportFull: () => api.get("/settings/export-full"),
  importFull: (blob, password) => api.post("/settings/import-full", { blob, password }),
};

// Security Lab: full forensic report for one message.
export const security = {
  analyze: (id) => api.get(`/security/analyze/${id}`),
};

export const ai = {
  status: () => api.get("/ai/status"),
  summarize: (body) => api.post("/ai/summarize", body),
  draft: (body) => api.post("/ai/draft", body),
  // Anti-phishing: judge a message as safe/suspicious/dangerous (cached on the
  // message; force re-runs). See Settings → Security.
  screen: (message_id, force = false) => api.post("/ai/screen", { message_id, force }),
  digest: () => api.post("/ai/digest", {}),
  triage: (limit = 20) => api.post("/ai/triage", { limit }),
  // Ollama (local, keyless) — detect / pull models / one-click install.
  ollamaStatus: (base = "") => api.get(`/ai/ollama/status${base ? `?base=${encodeURIComponent(base)}` : ""}`),
  ollamaPull: (model, base = "") => api.post("/ai/ollama/pull", { model, base }),
  ollamaPullStatus: () => api.get("/ai/ollama/pull-status"),
  ollamaInstall: () => api.post("/ai/ollama/install", {}),
  ollamaUpdate: () => api.post("/ai/ollama/update", {}),
  ollamaInstallStatus: () => api.get("/ai/ollama/install-status"),
  ollamaUnload: () => api.post("/ai/ollama/unload", {}),
  ollamaWarm: () => api.post("/ai/ollama/warm", {}),
  ollamaManaged: (enabled) => api.post(`/ai/ollama/managed?enabled=${enabled ? "true" : "false"}`, {}),
  ollamaStart: (base = "") => api.post(`/ai/ollama/start${base ? `?base=${encodeURIComponent(base)}` : ""}`, {}),
  ollamaRestart: (base = "") => api.post(`/ai/ollama/restart${base ? `?base=${encodeURIComponent(base)}` : ""}`, {}),
  ollamaSearch: (q) => api.get(`/ai/ollama/search?q=${encodeURIComponent(q)}`),   // live library search
  // Semantic search index (local embeddings).
  embedStatus: () => api.get("/ai/embed/status"),
  embedReindex: () => api.post("/ai/embed/reindex", {}),
  semantic: (q, limit = 60) =>
    api.get(`/messages/semantic?q=${encodeURIComponent(q)}&limit=${limit}`),
  // Composer rewrite + freeform ask-over-context (reader + AI assistant).
  rewrite: (body) => api.post("/ai/rewrite", body),
  ask: (body) => api.post("/ai/ask", body),
  search: (q) => api.post("/ai/search", { q }),   // natural language → keyword query
  // Assistant "with hands": answers questions about the app/mail AND proposes a
  // resolved mailbox action ({kind:"action", ids, count, …}) for the UI to confirm.
  agent: (body) => api.post("/ai/agent", body),
};

export const calendar = {
  list: (startIso, endIso) => api.get(`/calendar?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`),
  scan: (limit = 100) => api.post(`/calendar/scan?limit=${limit}`),
  rsvp: (id, status) => api.post(`/calendar/${id}/rsvp`, { status }),
  caldavSync: () => api.post("/calendar/caldav/sync", {}),
  create: (ev) => api.post("/calendar/create", ev),
  googleStatus: () => api.get("/calendar/google/status"),
  googleConnect: () => api.post("/calendar/google/connect", {}),
  googleDisconnect: () => api.post("/calendar/google/disconnect", {}),
  remove: (id) => api.del(`/calendar/${id}`),
};

export const rapldesk = {
  instances: () => api.get("/rapldesk/instances"),
  add: (i) => api.post("/rapldesk/instances", i),
  remove: (id) => api.del(`/rapldesk/instances/${id}`),
  call: (id, payload) => api.post(`/rapldesk/${id}/call`, payload),
};

// --- domain helpers --------------------------------------------------------
export const vault = {
  status: () => api.get("/vault/status"),
  initialize: (password) => api.post("/vault/initialize", { password }),
  unlock: (password) => api.post("/vault/unlock", { password }),
  lock: () => api.post("/vault/lock"),
  setAutoUnlock: (enabled, password = "") => api.post("/vault/auto-unlock", { enabled, password }),
};

export const accounts = {
  list: () => api.get("/accounts"),
  health: () => api.get("/accounts/health"),
  update: (id, body) => api.patch(`/accounts/${id}`, body),
  autodiscover: (email) => api.get(`/accounts/autodiscover?email=${encodeURIComponent(email)}`),
  createImap: (body) => api.post("/accounts/imap", body),
  msStart: () => api.post("/accounts/ms/device-flow/start"),
  msComplete: (flow_id) => api.post("/accounts/ms/device-flow/complete", { flow_id }),
  googleConnect: () => api.post("/accounts/google/connect"),
  sync: (id) => api.post(`/accounts/${id}/sync`),
  reconnect: (id, password) => api.post(`/accounts/${id}/reconnect`, { password }),
  remove: (id) => api.del(`/accounts/${id}`),
  backfillStatus: () => api.get("/accounts/backfill-history"),
  setBackfill: (enabled) => api.post("/accounts/backfill-history", { enabled }),
};

export const folders = {
  list: (accountId) => api.get(`/folders${accountId ? `?account_id=${accountId}` : ""}`),
  create: (account_id, name) => api.post("/folders", { account_id, name }),
  remove: (id) => api.del(`/folders/${id}`),
};

export const messages = {
  list: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    return api.get(`/messages${q ? `?${q}` : ""}`);
  },
  get: (id) => api.get(`/messages/${id}`),
  setDone: (id, value) => api.post(`/messages/${id}/done`, { value }),
  setFlag: (id, value) => api.post(`/messages/${id}/flag`, { value }),
  setSeen: (id, value) => api.post(`/messages/${id}/seen`, { value }),
  snooze: (id, until, presence = false) => api.post(`/messages/${id}/snooze`, { until, presence }),
  bulk: (ids, action, until = null) => api.post("/messages/bulk", { ids, action, until }),
  move: (ids, folderId) => api.post("/messages/move", { ids, folder_id: folderId }),   // drag → folder
  mute: (id) => api.post(`/messages/${id}/mute`),
  muteThread: (id) => api.post(`/messages/${id}/mute-thread`),
  pin: (id, value) => api.post(`/messages/${id}/pin`, { value }),
  followups: (days = 3) => api.get(`/messages/followups?days=${days}`),
  plusAliases: () => api.get("/messages/plus-aliases"),
  thread: (threadId) => api.get(`/messages/thread?thread_id=${encodeURIComponent(threadId)}`),
  categoryCounts: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null)).toString();
    return api.get(`/messages/category-counts${qs ? `?${qs}` : ""}`);
  },
  smartGroups: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null)).toString();
    return api.get(`/messages/smart-groups${qs ? `?${qs}` : ""}`);
  },
  recategorize: () => api.post("/messages/recategorize"),
  rethread: () => api.post("/messages/rethread"),
  setSenderCategory: (email, category) => api.post("/messages/sender-category", { email, category }),
  queueStatus: () => api.get("/messages/queue"),
  queueRetry: () => api.post("/messages/queue/retry"),
  queueItems: () => api.get("/messages/queue/items"),
  queueDiscard: (id) => api.del(`/messages/queue/${id}`),
};

export const subscriptions = {
  audit: (sort = "dormant") => api.get(`/subscriptions/audit?sort=${encodeURIComponent(sort)}`),
  // RFC 8058 one-click unsubscribe (server-side POST); resolves { ok, ... }.
  unsubscribe: (url) => api.post("/subscriptions/unsubscribe", { url }),
};

export const smime = {
  importP12: (data_b64, password) => api.post("/smime/import-p12", { data_b64, password }),
  certInfo: (cert_pem) => api.post("/smime/cert-info", { cert_pem }),
};

export const rules = {
  list: (accountId) => api.get(`/rules${accountId ? `?account_id=${accountId}` : ""}`),
  create: (body) => api.post("/rules", body),
  update: (id, body) => api.put(`/rules/${id}`, body),
  remove: (id) => api.del(`/rules/${id}`),
  preview: (body) => api.post("/rules/preview", body),
  apply: (body) => api.post("/rules/apply", body),   // run a rule against existing mail
};

export const signatures = {
  list: (accountId) => api.get(`/signatures${accountId ? `?account_id=${accountId}` : ""}`),
  create: (body) => api.post("/signatures", body),
  update: (id, body) => api.put(`/signatures/${id}`, body),
  remove: (id) => api.del(`/signatures/${id}`),
};

export const compose = {
  send: (body) => api.post("/compose/send", body),
  saveDraft: (body) => api.post("/compose/draft", body),
  scheduled: () => api.get("/compose/scheduled"),
  cancelScheduled: (id) => api.del(`/compose/scheduled/${id}`),
};

export const contacts = {
  list: (q) => api.get(`/contacts${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  create: (body) => api.post("/contacts", body),
  update: (id, body) => api.patch(`/contacts/${id}`, body),
  remove: (id) => api.del(`/contacts/${id}`),
  rescan: () => api.post("/contacts/rescan"),
};

export const debug = {
  logs: (since = 0, level) =>
    api.get(`/debug/logs?since=${since}${level ? `&level=${encodeURIComponent(level)}` : ""}`),
  clearLogs: () => api.del("/debug/logs"),
  health: () => api.get("/debug/health"),
};

/**
 * Connect to the live event stream.
 * @param {(ev:{event:string,payload:any})=>void} onEvent
 * @param {() => void} [onReconnect] called when the socket REopens after a drop
 *   (not the first connect) — events sent while it was down are lost, so the
 *   caller should refresh its state.
 */
export function connectEvents(onEvent, onReconnect) {
  let ws;
  let closed = false;
  let wasConnected = false;
  getCfg().then((c) => {
    if (closed) return;
    const url = c.base.startsWith("http")
      ? `${c.base.replace(/^http/, "ws")}/ws${c.token ? `?token=${c.token}` : ""}`
      : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
    function open() {
      if (closed) return;
      ws = new WebSocket(url);
      ws.onopen = () => {
        if (wasConnected && onReconnect) { try { onReconnect(); } catch {} }
        wasConnected = true;
      };
      ws.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); } catch {}
      };
      ws.onclose = () => { if (!closed) setTimeout(open, 2000); };
    }
    open();
  });
  return () => { closed = true; ws && ws.close(); };
}
