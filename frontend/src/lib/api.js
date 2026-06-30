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
  put: (p, body) => request(p, { method: "PUT", body: JSON.stringify(body) }),
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

// Absolute base URL of the backend (e.g. http://127.0.0.1:8765), once resolved.
// Used to show the user the local /metrics URL for LAN devices.
export function backendBase() {
  const base = cfg ? cfg.base : "/api";
  if (base.startsWith("http")) return base;
  try { return `${location.origin}${base}`; } catch { return base; }
}

export const appSettings = {
  get: () => api.get("/settings"),
  put: (data) => api.put("/settings", { data }),
  export: () => api.get("/settings/export"),
  import: (bundle) => api.post("/settings/import", bundle),
  exportFull: () => api.get("/settings/export-full"),
  importFull: (blob, password) => api.post("/settings/import-full", { blob, password }),
};

export const ai = {
  status: () => api.get("/ai/status"),
  summarize: (body) => api.post("/ai/summarize", body),
  draft: (body) => api.post("/ai/draft", body),
  digest: () => api.post("/ai/digest", {}),
  triage: (limit = 20) => api.post("/ai/triage", { limit }),
};

export const calendar = {
  list: (startIso, endIso) => api.get(`/calendar?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`),
  scan: (limit = 100) => api.post(`/calendar/scan?limit=${limit}`),
  rsvp: (id, status) => api.post(`/calendar/${id}/rsvp`, { status }),
  caldavSync: () => api.post("/calendar/caldav/sync", {}),
  create: (ev) => api.post("/calendar/create", ev),
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

export const rules = {
  list: (accountId) => api.get(`/rules${accountId ? `?account_id=${accountId}` : ""}`),
  create: (body) => api.post("/rules", body),
  update: (id, body) => api.put(`/rules/${id}`, body),
  remove: (id) => api.del(`/rules/${id}`),
  preview: (body) => api.post("/rules/preview", body),
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

/** Connect to the live event stream. @param {(ev:{event:string,payload:any})=>void} onEvent */
export function connectEvents(onEvent) {
  let ws;
  let closed = false;
  getCfg().then((c) => {
    if (closed) return;
    const url = c.base.startsWith("http")
      ? `${c.base.replace(/^http/, "ws")}/ws${c.token ? `?token=${c.token}` : ""}`
      : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
    function open() {
      if (closed) return;
      ws = new WebSocket(url);
      ws.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); } catch {}
      };
      ws.onclose = () => { if (!closed) setTimeout(open, 2000); };
    }
    open();
  });
  return () => { closed = true; ws && ws.close(); };
}
