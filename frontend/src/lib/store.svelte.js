// Central reactive app state using Svelte 5 runes.
import { vault, accounts, folders, messages, compose, contacts, rules, connectEvents, appSettings, avatarUrlDomain, calendar as calendarApi, ai } from "./api.js";
import { playSound } from "./sound.js";
import { setLocale, t } from "./i18n.svelte.js";

// Distinct, legible colors auto-assigned to calendar feeds by order.
export const CAL_PALETTE = ["#7c6cf0", "#e0556e", "#37a169", "#dd8a17", "#2f86d6", "#b052c9", "#0fa3a3", "#c2603a"];
// Normalize icsFeeds (legacy plain-URL strings or {url,color} objects) into a
// stable [{ url, color }] list, filling missing colors from the palette.
export function normalizeFeeds(feeds) {
  return (feeds || [])
    .map((f) => (typeof f === "string" ? { url: f } : { ...f }))
    .map((f, i) => ({ url: (f.url || "").trim(), color: f.color || CAL_PALETTE[i % CAL_PALETTE.length] }))
    .filter((f) => f.url);
}

// --- persisted UI settings -------------------------------------------------
const SETTINGS_KEY = "raplmail.settings";
function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}
const DEFAULT_SETTINGS = {
  composeMode: "panel",          // "panel" | "window"
  composePosition: "bottom-right", // "bottom-right" | "bottom-left"
  unifiedInbox: true,            // show a combined inbox across accounts
  hiddenFolders: [],             // folder ids hidden from the sidebar
  folderOrder: {},               // { folderId: index } custom ordering
  collapsedAccounts: [],         // account ids whose folder list is folded
  specialOrder: [],              // custom order of the special nav items (ids)
  sidebarCollapsed: false,       // collapse the whole sidebar to an icon rail
  undoSend: true,                // delay sends so they can be cancelled
  undoSendDelay: 5,              // seconds
  blockTrackers: true,           // block tracking pixels / suspicious images (keep legit ones)
  snippets: [                    // text expander: type the shortcut + space in compose
    { shortcut: ";intro", body: "Hi {{first}},<br><br>" },
    { shortcut: ";thanks", body: "Thanks so much,<br>" },
  ],
  theme: {},                     // CSS custom-property overrides: { "--accent": "#..." }
  radius: 11,                    // corner roundness (px)
  uiScale: 1,                    // overall UI/font scale (0.85–1.3) via CSS zoom
  customCss: "",                 // user CSS injected app-wide
  sidebarWidth: 248,             // resizable layout (Customize mode)
  listWidth: 400,
  themeMode: "manual",           // "manual" | "auto" (day/night)
  emailAdaptColors: true,        // invert light-authored email HTML to match a dark theme
  alwaysOriginalHtml: false,     // always render emails in their original HTML (no theming)
  customCssInEmails: false,      // also apply custom CSS inside email bodies (off = emails untouched)
  smartGroupPlacement: "dateSections", // "dateSections" (Spark-style) | "top" | "afterN" | "timeline" | "bottom"
  smartGroupsAfter: 3,           // for "afterN": how many classic messages show before the groups
  senderAvatars: true,           // fetch + cache the sender domain's favicon as the avatar
  relativeTime: false,           // list rows show "3 hours ago" instead of a date
  collapseQuotes: true,          // hide quoted reply history behind a toggle in the reader
  templates: [],                 // canned messages: [{ id, name, subject, body }]
  vipSenders: [],                // emails/domains whose mail floats to the top + always notifies
  linkUnfurls: false,            // fetch an OpenGraph preview card for the main link (privacy: off)
  highlightCode: true,           // syntax-highlight <pre> code blocks in the reader
  localApiEnabled: false,        // expose read-only /metrics for LAN devices
  localApiKey: "",               // stable API key for the local metrics endpoint
  aiProvider: "anthropic",       // AI provider: anthropic | openai | openai-compatible
  aiApiKey: "",                  // BYOK: your own provider API key (stays local)
  aiBaseUrl: "",                 // base URL for an OpenAI-compatible endpoint (Groq/OpenRouter/Ollama/…)
  aiModel: "",                   // optional model override (blank = per-provider default)
  aiButtons: true,               // show AI buttons (only relevant once a key is set)
  digestEnabled: false,          // deliver a daily AI "morning briefing" of unread mail
  digestHour: 8,                 // local hour (0-23) to deliver the briefing
  spellCheck: true,              // native (WebView2/OS) spell-check in the composer
  spellCheckLang: "auto",        // spell-check dictionary: "auto" (UI lang) | en | cs | sk | de | …
  ollamaKeepAlive: "5m",         // how long Ollama keeps the model in VRAM after a request ("30s".."-1")
  ollamaAutostart: false,        // start the local Ollama server when RaplMail launches
  ollamaManaged: true,           // Windows: run our OWN hidden `ollama serve` so the model-runner console windows never flash (routes traffic to it; leaves the tray Ollama idle)
  semanticEnabled: false,        // local meaning-based search (embeddings) — opt-in
  embedProvider: "ollama",       // embeddings source: "ollama" | "openai-compatible"
  embedBaseUrl: "",              // embeddings endpoint (blank → Ollama localhost:11434)
  embedModel: "",                // embedding model (blank → nomic-embed-text / text-embedding-3-small)
  embedApiKey: "",               // key for a cloud OpenAI-compatible embeddings endpoint (local Ollama needs none)
  launchOnStartup: false,        // start RaplMail at login (tray/background mode)
  minimizeToTray: true,          // closing the window hides to the tray instead of quitting
  dashboard: true,               // show the Home dashboard entry in the sidebar
  showPaperTrail: true,          // show the "Paper Trail" nav item (receipts/orders)
  showNewsletterFeed: true,      // show the "Newsletter Feed" nav item
  pgpPrivateKey: "",             // your armored OpenPGP private key (for decrypt/sign)
  pgpPassphrase: "",             // passphrase for the private key (if protected)
  pgpPublicKeys: [],             // armored public keys of correspondents (verify/encrypt)
  smimeCert: "",                 // your S/MIME certificate (PEM, from an imported .p12)
  smimeKey: "",                  // your S/MIME private key (PEM, from the .p12)
  smimeEmail: "",                // the address on your S/MIME cert (for display)
  smimeCerts: [],                // recipients' S/MIME certs (PEM) to encrypt to them
  encryptCache: false,           // seal cached message bodies at rest with the vault key
  trackBaseUrl: "",              // public base URL for read-receipt pixels (else localhost)
  caldavUrl: "",                 // CalDAV collection URL (events)
  carddavUrl: "",                // CardDAV collection URL (contacts)
  caldavUser: "",                // CalDAV/CardDAV username
  caldavPassword: "",            // CalDAV/CardDAV password
  readerActionsPos: "top",       // Reply/Forward/Done bar: "top" | "bottom"
  emailTheme: "",                // email body rendering: "" (auto) | "adaptive" | "dark" | "original"
  trustedSenders: [],            // addresses the user marked OK (suppresses spoof warnings)
  icsFeeds: [],                  // subscribed iCal feeds: [{ url, color }] (read-only)
  raplDesk: [],                  // connected RaplDesk instances [{id,name,url}] (keys in vault)
  raplDeskUserId: null,          // your RaplDesk agent user id (for replies/new tickets)
  calendarDefaultView: "month",  // calendar opens in "month" or "week"
  calendarReminders: [10],       // lead times (minutes) for event reminders; combinable
  icsSyncMinutes: 30,            // auto-refresh subscribed calendars this often
  scheduleLaterHours: 3,         // "Later today" = now + this many hours
  scheduleMorningHour: 9,        // hour used for Tomorrow / weekend / next week
  scheduleEveningHour: 18,       // hour used for "This evening"
  notifyNewMail: true,           // desktop notification when new mail arrives
  notifySound: "ding",           // sound on new mail: "none"|"ding"|"chime"|"pop"|"marimba"|"glass"
  notifyVolume: 80,              // notification sound volume, 0–100
  notifyOnlyUnfocused: true,     // only notify when the RaplMail window isn't focused
  quietHoursEnabled: false,      // suppress notifications during a nightly window
  quietStart: 22,                // quiet hours start hour (local)
  quietEnd: 7,                   // quiet hours end hour (local)
  rowActions: ["snooze", "done"],// the two hover buttons on each message row (left, right)
  readerActions: ["reply", "replyAll", "forward", "archive", "snooze", "done", "flag", "delete"], // buttons under the recipient
  followupDays: 3,               // nudge to follow up after this many days with no reply
  workspaces: [],                // [{ id, name, accountIds: [] }]
  activeWorkspace: null,         // workspace id, or null = all accounts
  screener: false,              // route first-time senders to a Screener (Hey-style)
  savedSearches: [],            // [{ id, name, query }] pinned smart folders
  autoBcc: [],                  // [{ domain, bcc }] auto-BCC outgoing mail by recipient domain
  threading: false,             // group the list into conversations
  bundles: false,               // collapse notification senders into one card
  keybinds: { next: "ArrowDown", prev: "ArrowUp", open: "Enter", done: "e",
              reply: "r", forward: "f", archive: "a", delete: "Delete", read: "u",
              compose: "Ctrl+n", search: "/", palette: "Ctrl+k", help: "?" },
  openNextOnDone: true,          // after marking the open message done, open the next one
  language: "auto",             // UI language: "auto" (system) | "en" | "cs"
  onboarded: false,             // has the first-run onboarding wizard been completed?
  smartInbox: true,             // Spark-style smart inbox: group chosen categories (default view)
  smartGroups: { newsletters: true, social: true, updates: true, promotions: true, invitations: false, invitation_responses: true },
  smartPreviewCount: 4,         // sender chips shown per group card
  smartNewDays: 3,              // "new" = unread AND received within this many days
  smartOrderMode: "recency",    // "recency" | "custom"
  smartOrder: [],               // category ids, top→bottom, when custom
  density: "comfortable",       // message-list row density: comfortable | compact | cozy
  emailMaxWidth: 820,           // reading-width cap for email bodies (px; 0 = full width)
};

// Stored keybinds replace the defaults wholesale (the settings merge is
// shallow), so bindings added in later versions are missing from older saves —
// always read keybinds through this merge.
export const KB_DEFAULTS = DEFAULT_SETTINGS.keybinds;
export function kbAll() {
  return { ...KB_DEFAULTS, ...app.settings.keybinds };
}

export const app = $state({
  vault: { exists: false, unlocked: false, auto_unlock: false, ready: false },
  accounts: [],
  folders: [],
  selectedKind: "folder",        // "folder" | "unified"
  selectedAccountId: null,
  selectedFolderId: null,
  selectedFolderRole: "inbox",
  category: null,                // null = all categories; else "primary"/"newsletters"/...
  messages: [],
  smartGroupData: {},            // category -> { count, latest, senders, more } for Smart Inbox
  selectedMessageId: null,
  threadKey: null,               // when viewing a conversation in the reader
  readerCmd: null,               // { cmd, n } — keyboard-triggered reader action (reply/forward)
  showDone: false,
  search: "",
  semantic: false,               // current search is meaning-based (local embeddings) vs keyword
  view: "mail",                  // "mail" | "settings" | "scheduled" | "newsfeed"
  settingsTab: null,             // when set, Settings opens to this tab
  ruleDraft: null,               // prefill for the Rules editor (from "Create rule")
  ruleModal: null,               // { message } — open the quick "New rule" modal
  lab: null,                     // { id, subject, from } — message sent to the Security Lab
  composing: null,
  mailMergeOpen: false,          // mail-merge / personalized bulk send dialog
  aiInboxOpen: false,            // AI inbox digest + priority triage dialog
  aiAssistantOpen: false,        // AI assistant: chat over emails added as context
  aiAssistantSeed: null,         // { messageId, threadId, threadKey } to preload context
  aiChatContext: [],             // [{ id, from, subject, date }] — emails the assistant reasons over
  aiBusy: false,                 // an AI request is in flight (adaptive mode keeps the GPU warm while true)
  aiDigest: "",                  // last scheduled morning-brief text (shown in the assistant)
  pendingSend: null,             // { payload, seed, delay, label, timer } while undo-send counts down
  paletteOpen: false,            // command palette (Ctrl+K)
  loading: false,
  syncing: false,
  queuePending: 0,
  queueFailed: 0,
  customizing: false,            // layout-edit mode (resize columns)
  toast: null,
  confirm: null,                 // { title, message, confirmLabel, danger, resolve } — in-app confirm dialog
  syncTick: 0,                   // bumped on each sync:done so views can refresh live
  dragMessageIds: [],            // message ids being dragged (drag-onto-folder to move)
  dragAccountId: null,           // account of the dragged messages (moves stay in-account)
  settings: loadSettings(),
});

// Move messages to a folder (drag-a-message-onto-a-folder). Optimistic: drop the
// rows from the current view now; the backend queues the IMAP move + retries.
export async function moveMessages(ids, folder) {
  const list = [...(ids || [])];
  if (!list.length || !folder) return;
  const idset = new Set(list);
  app.messages = app.messages.filter((m) => !idset.has(m.id));   // optimistic hide
  if (idset.has(app.selectedMessageId)) { app.selectedMessageId = null; app.threadKey = null; }
  try {
    const r = await messages.move(list, folder.id);
    const n = r?.queued ?? 0;
    notify(n ? t("list.movedN", { n, folder: folder.name }) : t("list.moveNothing"));
    refreshMessages({ background: true });
    refreshQueue();
  } catch (e) {
    notify(t("list.couldntUpdate"), "error");
    refreshMessages({ background: true });
  }
}

// Mark every unread message in the current view read (loaded rows + any hidden
// inside Smart Inbox group cards). Shared by the list button and the command
// palette. Optimistic + undo.
export async function markAllRead() {
  const ids = new Set(app.messages.filter((m) => !m.is_seen).map((m) => m.id));
  const scope = (smartActive() || app.selectedKind === "unified") ? { role: "inbox" }
    : (app.selectedKind === "folder" ? { folder_id: app.selectedFolderId } : null);
  if (scope) {
    try {
      const unread = await messages.list({ ...scope, unread_only: true, include_done: app.showDone, limit: 2000 });
      (unread || []).forEach((m) => ids.add(m.id));
    } catch {}
  }
  const list = [...ids];
  if (!list.length) { notify(t("list.allReadAlready")); return; }
  for (const m of app.messages) if (ids.has(m.id)) m.is_seen = true;   // optimistic -N on badges
  try {
    await messages.bulk(list, "seen");
    notify(t("list.bulkRead", { n: list.length }), "info", () => {
      messages.bulk(list, "unseen")
        .then(() => refreshMessages({ background: true }))
        .catch(() => notify(t("list.couldntUndo"), "error"));
    });
    refreshMessages({ background: true });
  } catch (e) { notify(t("list.couldntUpdate"), "error"); refreshMessages({ background: true }); }
}

export async function refreshQueue() {
  try { const q = await messages.queueStatus(); app.queuePending = q.pending; app.queueFailed = q.failed; } catch {}
}
export async function retryQueue() {
  try { await messages.queueRetry(); refreshQueue(); } catch {}
}

// Customizable color tokens (mirror app.css :root) with their built-in defaults.
export const THEME_TOKENS = [
  ["--bg", "#0b0d12"], ["--surface", "#12151d"], ["--surface-2", "#1a1e29"],
  ["--surface-3", "#232937"], ["--border", "#262c3b"], ["--text", "#e8ebf2"],
  ["--muted", "#8f97ab"], ["--accent", "#5e8bff"], ["--done", "#34d399"],
  ["--danger", "#f26d79"], ["--warning", "#f5b83d"],
];

// A built-in light palette (used by the "Light" preset and auto day mode).
export const LIGHT_THEME = {
  "--bg": "#f5f6fa", "--surface": "#ffffff", "--surface-2": "#eef0f5",
  "--surface-3": "#e3e7ef", "--border": "#d8dde8", "--text": "#171d2b",
  "--muted": "#5f6a80", "--accent": "#3e6fe6", "--done": "#149d6d",
  "--danger": "#d84557", "--warning": "#b57d05",
};

function effectiveTheme() {
  const s = app.settings;
  if (s.themeMode === "auto") {
    const h = new Date().getHours();
    return h >= 7 && h < 19 ? LIGHT_THEME : {}; // day = light, night = default dark
  }
  return s.theme || {};
}

/** Apply the active UI language from settings (reactive; live-switches). */
export function setLanguage(lang) {
  saveSettings({ language: lang });
  setLocale(lang);
}

/** Apply the active theme to CSS custom properties (clears unset ones). */
export function applyTheme() {
  if (typeof document === "undefined") return;
  // Keep the UI language in sync whenever we re-apply appearance (boot, import…).
  setLocale(app.settings.language);
  const root = document.documentElement;
  const t = effectiveTheme();
  for (const [k] of THEME_TOKENS) {
    if (t[k]) root.style.setProperty(k, t[k]);
    else root.style.removeProperty(k);
  }
  // Corner roundness.
  const r = app.settings.radius ?? 11;
  root.style.setProperty("--radius", `${r}px`);
  root.style.setProperty("--radius-sm", `${Math.max(3, r - 4)}px`);
  // UI scale (font/zoom). WebView2/Chromium honors `zoom`, which scales the whole
  // px-based UI cleanly.
  const scale = app.settings.uiScale ?? 1;
  // Only apply `zoom` when actually scaling — an explicit `zoom: 1` still forces
  // Chromium/WebView2 off its fast-scroll path, which made long panes (Settings)
  // scroll sluggishly for no reason.
  if (scale && scale !== 1) root.style.setProperty("zoom", String(scale));
  else root.style.removeProperty("zoom");
  // List density → row vertical padding / gap / avatar size, consumed by the
  // message rows (var fallbacks keep the "comfortable" look if unset).
  const D = ({ comfortable: [11, 11, 34], compact: [6, 9, 28], cozy: [15, 13, 36] }[app.settings.density] || [11, 11, 34]);
  root.style.setProperty("--row-pad-y", `${D[0]}px`);
  root.style.setProperty("--row-gap", `${D[1]}px`);
  root.style.setProperty("--row-av", `${D[2]}px`);
  // User custom CSS (escape hatch for buttons, spacing, anything).
  let el = document.getElementById("rapl-custom-css");
  if (!el) { el = document.createElement("style"); el.id = "rapl-custom-css"; document.head.appendChild(el); }
  el.textContent = app.settings.customCss || "";
}

async function doSend(payload) {
  try {
    const r = await compose.send(payload);
    if (r && r.queued) notify("Couldn't reach the server — queued, will retry. See Settings/sidebar for details.", "error");
    else notify("Sent ✓");
    refreshQueue();
  } catch (e) {
    notify("Send failed: " + e.message, "error");
  }
}

// During the undo-send delay the payload is also written to localStorage, so a
// hard quit/kill within the (default 5s) window doesn't silently lose the mail —
// it's redelivered on the next boot (see recoverPendingSend).
const PENDING_SEND_KEY = "raplmail.pendingSend";
function persistPendingSend(payload) { try { localStorage.setItem(PENDING_SEND_KEY, JSON.stringify(payload)); } catch {} }
function clearPersistedPendingSend() { try { localStorage.removeItem(PENDING_SEND_KEY); } catch {} }

/** Queue a send; with undo-send on, it can be cancelled during the delay. */
export function queueSend(payload, seed) {
  app.composing = null; // hide the compose window immediately
  // A second send while one is still counting down would overwrite the first
  // timer's state and silently lose that mail — flush it out the door now
  // (its undo window just ends early).
  const prev = app.pendingSend;
  if (prev) {
    clearTimeout(prev.timer);
    app.pendingSend = null;
    clearPersistedPendingSend();
    doSend(prev.payload);
  }
  const delay = app.settings.undoSend ? (app.settings.undoSendDelay || 5) : 0;
  if (delay <= 0) { doSend(payload); return; }
  persistPendingSend(payload);
  const timer = setTimeout(() => {
    const ps = app.pendingSend;
    app.pendingSend = null;
    clearPersistedPendingSend(); // clear right before delivery so we never double-send
    if (ps) doSend(ps.payload);
  }, delay * 1000);
  app.pendingSend = { payload, seed, delay, timer, label: payload.subject || "(no subject)" };
}

export function cancelSend() {
  const ps = app.pendingSend;
  if (!ps) return;
  clearTimeout(ps.timer);
  app.pendingSend = null;
  clearPersistedPendingSend();
  notify("Send cancelled");
  openCompose(ps.seed); // bring the message back to keep editing
}

// On boot, redeliver any send that was still counting down when the app was
// quit/killed (the renderer setTimeout died with the process). The key is
// cleared the instant before a normal delivery, so this only fires for sends
// that genuinely never went out.
export function recoverPendingSend() {
  let payload = null;
  try { payload = JSON.parse(localStorage.getItem(PENDING_SEND_KEY) || "null"); } catch {}
  if (!payload) return;
  clearPersistedPendingSend();
  doSend(payload);
  notify("Delivered a message that was still sending when the app closed");
}

let _settingsTimer = null;
// Keys the BACKEND owns inside the shared settings blob — never sent from the
// UI save (the backend merges its own), so a settings save can't wipe them.
const _BACKEND_OWNED = ["raplDesk", "googleCalendarEmail"];
function _pushSettings(opts) {
  const out = { ...app.settings };
  for (const k of _BACKEND_OWNED) delete out[k];
  appSettings.put(out, opts).catch(() => {});
}
export function saveSettings(patch) {
  // Mutate in place — replacing the whole settings object invalidated EVERY
  // settings-reading derived in the app (each mail row reads several), so any
  // toggle (e.g. collapsing the sidebar) recomputed hundreds of them and lagged
  // the UI. In-place assignment keeps Svelte's per-key tracking granular.
  Object.assign(app.settings, patch);
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(app.settings)); } catch {}
  // Persist to the backend (a file) too, debounced, so settings survive across
  // installs and can be exported.
  clearTimeout(_settingsTimer);
  _settingsTimer = setTimeout(() => { _settingsTimer = null; _pushSettings(); }, 400);
}
// Quitting inside the 400ms debounce window would lose the last change (the
// server copy wins on next boot) — flush it with a keepalive request.
function _flushSettingsSave() {
  if (!_settingsTimer) return;
  clearTimeout(_settingsTimer);
  _settingsTimer = null;
  _pushSettings({ keepalive: true });
}
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", _flushSettingsSave);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") _flushSettingsSave();
  });
}

// Load settings from the server on boot. The server copy is authoritative; if
// it's empty (fresh install), seed it from whatever localStorage had.
export async function initSettings() {
  // Read whatever the local copy has so we can backfill keys the server might be
  // missing (e.g. an older/partial blob) — server stays authoritative per-key.
  let local = {};
  try { local = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}; } catch {}
  try {
    const server = await appSettings.get();
    if (server && Object.keys(server).length) {
      const merged = { ...DEFAULT_SETTINGS, ...local, ...server };
      app.settings = merged;
      try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged)); } catch {}
      applyTheme();
      // If local had keys the server lost, heal the server copy.
      if (Object.keys(local).some((k) => !(k in server))) {
        appSettings.put(merged).catch(() => {});
      }
    } else {
      appSettings.put(app.settings).catch(() => {});
    }
  } catch { /* offline / not ready — localStorage value stands */ }
  // One-time migration: move the old default "afterN" to the new Spark-style
  // date sections. Guarded so it runs once and never overrides a later choice.
  if (!app.settings._placementMigrated) {
    const patch = { _placementMigrated: true };
    if ((app.settings.smartGroupPlacement || "afterN") === "afterN") patch.smartGroupPlacement = "dateSections";
    saveSettings(patch);
  }
}

export async function exportConfig() {
  return appSettings.export();
}
export async function importConfig(bundle) {
  const res = await appSettings.import(bundle);
  await initSettings();   // pull the freshly-imported settings back in
  return res;
}

// Full encrypted backup (.rmail) — includes accounts + credentials.
export async function exportFullBackup() {
  return appSettings.exportFull();
}
export async function importFullBackup(blob, password) {
  const res = await appSettings.importFull(blob, password);
  await initSettings();
  try { await loadAccountsAndFolders(); } catch {}
  return res;
}

export function isTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Pull the bare, lowercased email out of "Name <addr>" or a raw address. */
function extractEmail(s) {
  if (!s) return "";
  const m = /<([^>]+)>/.exec(String(s));
  return (m ? m[1] : String(s)).trim().toLowerCase();
}

/**
 * Given a message row (its account_id + to/cc recipients), work out which account
 * it belongs to and which of that account's identities (primary address or an
 * alias) it was addressed to. Lets compose default the From — and therefore the
 * signature — to the address the mail actually arrived on, instead of account #1.
 */
export function identityForMessage(msg) {
  if (!msg) return {};
  const acct = app.accounts.find((a) => a.id === msg.account_id);
  if (!acct) return { account_id: msg?.account_id ?? null };
  const rcpts = [...(msg.to_addrs || []), ...(msg.cc_addrs || [])].map(extractEmail);
  if (rcpts.includes(extractEmail(acct.email))) return { account_id: acct.id, from_addr: "" };
  for (const alias of acct.aliases || []) {
    if (rcpts.includes(extractEmail(alias))) return { account_id: acct.id, from_addr: alias };
  }
  return { account_id: acct.id, from_addr: "" };
}

/** Open a compose surface honoring the user's setting (docked panel vs separate window). */
export async function openCompose(seed = {}) {
  const merged = { ...seed };
  // Default the From (and therefore the signature) to the identity of the message
  // you're currently reading: a reply — or a blank compose opened while a mail is
  // open — should go out from the address it was addressed to, not always the
  // first account. Explicit seed fields (set by reply/forward) always win.
  const om = app.selectedMessageId ? app.messages.find((m) => m.id === app.selectedMessageId) : null;
  if (om) {
    const idn = identityForMessage(om);
    if (merged.account_id == null && idn.account_id != null) merged.account_id = idn.account_id;
    if (merged.from_addr == null && idn.from_addr && merged.account_id === idn.account_id) {
      merged.from_addr = idn.from_addr;
    }
  }
  seed = merged;
  if (app.settings.composeMode === "window") {
    // localStorage (not sessionStorage) so the seed is readable in the new window.
    try { localStorage.setItem("raplmail.compose.seed", JSON.stringify(seed)); } catch {}
    const url = `${location.pathname}${location.search}#compose`;
    if (isTauri()) {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      new WebviewWindow(`compose-${Date.now()}`, { url, title: "New message", width: 720, height: 660 });
    } else {
      window.open(url, "_blank", "width=720,height=680");
    }
  } else {
    app.composing = seed;
  }
}

// Self-update via the Tauri updater plugin. No-op in the browser dev build.
export async function checkForUpdates({ silent = false } = {}) {
  if (!isTauri()) {
    if (!silent) notify("Updates are only available in the installed app", "info");
    return;
  }
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const update = await check();
    if (!update) { if (!silent) notify("You're on the latest version ✓"); return; }
    if (!confirm(`Update available: ${update.version}\n\n${update.body || ""}\n\nDownload and install now? The app will restart.`)) return;
    notify(`Downloading update ${update.version}…`);
    await update.downloadAndInstall();
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch (e) {
    if (!silent) notify(`Update check failed: ${e.message || e}`, "error");
  }
}

// LIFO stack of recent undoable actions. The toast only shows the latest, but
// fast triage produces several — keeping a stack means each one stays reversible
// (via Ctrl+Z) instead of only the most recent surviving.
const _undoStack = [];
export function notify(message, kind = "info", undo = null) {
  const id = Math.random();
  if (undo) {
    _undoStack.push(undo);
    if (_undoStack.length > 20) _undoStack.shift();
  }
  app.toast = { message, kind, id, undo };
  setTimeout(() => { if (app.toast && app.toast.id === id) app.toast = null; }, undo ? 6000 : 3200);
}
// In-app confirmation dialog (replaces the browser's ugly "tauri.localhost says"
// window.confirm). Returns a Promise<boolean>. Render <ConfirmDialog /> once at
// the app root; it reads app.confirm.
const _confirmQueue = [];
export function confirmDialog({ title = "Are you sure?", message = "", confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false } = {}) {
  return new Promise((resolve) => {
    const item = { title, message, confirmLabel, cancelLabel, danger, resolve };
    // A dialog is already up: queue this one so neither promise is orphaned.
    if (app.confirm) _confirmQueue.push(item);
    else app.confirm = item;
  });
}
export function resolveConfirm(result) {
  const c = app.confirm;
  app.confirm = _confirmQueue.shift() || null;
  if (c) c.resolve(result);
}

export function runUndo() {
  app.toast = null;
  const u = _undoStack.pop();
  if (u) { u(); notify("Undone"); }
}
export function hasUndo() { return _undoStack.length > 0; }

export async function refreshVault() {
  app.vault = { ...(await vault.status()), ready: true };
}

// Reflect total inbox-unread on the taskbar/dock icon + tray tooltip (Tauri only).
export async function updateBadge() {
  if (!isTauri()) return;
  try {
    const count = (app.folders || [])
      .filter((f) => f.role === "inbox")
      .reduce((n, f) => n + (f.unread_count || 0), 0);
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("set_unread_badge", { count });
  } catch {}
}

// Mark a message seen/unseen and reflect it EVERYWHERE instantly — the row,
// the folder unread badge, and the Smart Inbox group counts — instead of
// waiting for the next sync to correct the numbers. The server call is
// fire-and-forget; a sync later reconciles the exact counts.
export function setMessageSeen(message, seen) {
  if (!message || message.is_seen === seen) return;
  message.is_seen = seen;
  const inList = app.messages.find((m) => m.id === message.id);
  if (inList) inList.is_seen = seen;
  const delta = seen ? -1 : 1;
  // Folder badge (sidebar + Home hero read from app.folders).
  const folder = app.folders.find((f) => f.id === message.folder_id);
  if (folder) folder.unread_count = Math.max(0, (folder.unread_count || 0) + delta);
  // Smart Inbox group counts (the "N new" / unread badges).
  const g = app.smartGroupData?.[message.category];
  if (g) {
    if (typeof g.unread === "number") g.unread = Math.max(0, g.unread + delta);
    if (typeof g.new === "number") g.new = Math.max(0, g.new + delta);
  }
  updateBadge();
  messages.setSeen(message.id, seen).catch(() => {});
}

// Close-to-tray toggle: tell the Rust shell whether the window-close button
// hides to the tray (true) or fully quits (false).
export async function setCloseToTray(on) {
  saveSettings({ minimizeToTray: on });
  if (!isTauri()) return;
  try { const { invoke } = await import("@tauri-apps/api/core"); await invoke("set_close_to_tray", { on }); } catch {}
}
// Push the saved tray preference to the shell on boot (default: hide to tray).
export async function syncTrayPref() {
  if (!isTauri()) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("set_close_to_tray", { on: app.settings.minimizeToTray !== false });
  } catch {}
}

// Launch RaplMail at login (Tauri autostart plugin).
export async function setAutostart(on) {
  saveSettings({ launchOnStartup: on });
  if (!isTauri()) return;
  try {
    const { enable, disable } = await import("@tauri-apps/plugin-autostart");
    if (on) await enable(); else await disable();
  } catch (e) { notify(`Couldn't change startup setting: ${e.message || e}`, "error"); }
}
// On boot, reconcile the saved preference with the OS autostart registration —
// they're two sources of truth and can drift (e.g. the entry was removed
// externally, or a prior enable() silently failed). The plugin's live state wins.
export async function syncAutostart() {
  if (!isTauri()) return;
  try {
    const { isEnabled, enable, disable } = await import("@tauri-apps/plugin-autostart");
    const want = !!app.settings.launchOnStartup;
    const have = await isEnabled();
    if (want === have) return;
    // The user's saved intent is authoritative; make the OS match it.
    if (want) await enable(); else await disable();
  } catch { /* plugin unavailable (dev/browser) — ignore */ }
}

export async function loadAccountsAndFolders() {
  app.accounts = await accounts.list();
  app.folders = await folders.list();
  updateBadge();
  // Default selection on first load.
  if (app.selectedFolderId === null && app.selectedKind === "folder") {
    const hasInbox = app.folders.some((f) => f.role === "inbox");
    if (app.settings.smartInbox && hasInbox) {
      selectSmartInbox();
    } else if (app.settings.unifiedInbox && hasInbox) {
      selectUnifiedInbox();
    } else {
      const inbox = app.folders.find((f) => f.role === "inbox") || app.folders[0];
      if (inbox) selectFolder(inbox);
    }
  }
}

export function selectFolder(folder) {
  app.selectedKind = "folder";
  app.selectedFolderId = folder.id;
  app.selectedAccountId = folder.account_id;
  app.selectedFolderRole = folder.role;
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectUnifiedInbox() {
  app.selectedKind = "unified";
  app.selectedFolderId = null;
  app.selectedAccountId = null;
  app.selectedFolderRole = "inbox";
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectUnifiedSent() {
  app.selectedKind = "sent";
  app.selectedFolderId = null;
  app.selectedAccountId = null;
  app.selectedFolderRole = "sent";
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectUnifiedDrafts() {
  app.selectedKind = "drafts";
  app.selectedFolderId = null;
  app.selectedAccountId = null;
  app.selectedFolderRole = "drafts";
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectSmartInbox() {
  app.selectedKind = "smart";
  app.selectedFolderId = null;
  app.selectedAccountId = null;
  app.selectedFolderRole = "inbox";
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

/** Smart Inbox active? (the unified smart view, or an inbox folder with the setting on). */
export function smartActive() {
  return app.selectedKind === "smart" ||
    (app.selectedKind === "folder" && app.selectedFolderRole === "inbox" && app.settings.smartInbox);
}
export function groupedCategories() {
  return Object.entries(app.settings.smartGroups || {}).filter(([, v]) => v).map(([k]) => k);
}

export function setCategory(cat) {
  app.category = cat;
  app.selectedMessageId = null;
  refreshMessages();
}

/** Account ids visible in the active workspace, or null for all accounts. */
export function workspaceAccountIds() {
  const ws = (app.settings.workspaces || []).find((w) => w.id === app.settings.activeWorkspace);
  return ws ? ws.accountIds : null;
}

export function setWorkspace(id) {
  saveSettings({ activeWorkspace: id });
  // If the selected folder belongs to a now-hidden account, fall back to unified.
  const ids = workspaceAccountIds();
  if (ids && app.selectedKind === "folder" && app.selectedAccountId != null && !ids.includes(app.selectedAccountId)) {
    selectUnifiedInbox();
  } else {
    app.selectedMessageId = null;
    refreshMessages();
  }
}

export function selectSnoozed() {
  app.selectedKind = "snoozed";
  app.selectedFolderId = null;
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectScreener() {
  app.selectedKind = "screener";
  app.selectedFolderId = null;
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectPaperTrail() {
  app.selectedKind = "papertrail";
  app.selectedFolderId = null;
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export function selectFollowups() {
  app.selectedKind = "followups";
  app.selectedFolderId = null;
  app.selectedMessageId = null;
  app.search = "";
  app.category = null;
  refreshMessages();
}

export async function approveSender(message) {
  app.messages = app.messages.filter((m) => m.id !== message.id);
  if (app.selectedMessageId === message.id) app.selectedMessageId = null;
  try {
    await contacts.create({ email: message.from_addr, name: message.from_name || "" });
    notify(`Approved ${message.from_addr} — future mail lands in your inbox`);
  } catch (e) { notify("Couldn't approve", "error"); refreshMessages({ background: true }); }
}

export async function blockSender(message) {
  app.messages = app.messages.filter((m) => m.id !== message.id);
  if (app.selectedMessageId === message.id) app.selectedMessageId = null;
  try {
    await rules.create({ name: `Blocked ${message.from_addr}`, match_field: "from",
                         match_op: "equals", match_value: message.from_addr, action: "block" });
    await messages.mute(message.id);  // also clear current mail from this sender
    notify(`Blocked ${message.from_addr}`);
  } catch (e) { notify("Couldn't block", "error"); refreshMessages({ background: true }); }
}

// Silence future desktop notifications from a sender WITHOUT touching the mail
// itself — unlike "Mute sender" (which auto-marks it done), the message still
// arrives in the inbox, unread; it just doesn't ding. A "mute_notifications"
// rule the sync engine honors when deciding whether new mail is notify-worthy.
export async function muteNotificationsFromSender(message) {
  const addr = message?.from_addr || "";
  if (!addr) return;
  try {
    await rules.create({ name: `Muted notifications: ${addr}`, match_field: "from",
                         match_op: "equals", match_value: addr, action: "mute_notifications" });
    notify(`Muted notifications from ${message.from_name || addr}`);
  } catch (e) { notify("Couldn't mute notifications", "error"); }
}

// The value a rule should match for a given field, pulled from the clicked
// message — so picking "Subject" auto-fills the subject, "Sender domain" the
// domain, etc. Body has no sensible single value, so it stays blank.
export function ruleValueForField(field, message) {
  if (!message) return "";
  const addr = message.from_addr || "";
  switch (field) {
    case "from_domain": return addr.includes("@") ? addr.split("@")[1] : "";
    case "from": return addr;
    case "to": return message.to_addrs?.[0] || "";
    case "subject": return message.subject || "";
    default: return "";   // body
  }
}

// The operator that fits a field by default (substring for text, exact/suffix
// for addresses).
export function ruleOpForField(field) {
  if (field === "from_domain") return "ends_with";
  if (field === "from" || field === "to") return "equals";
  return "contains";   // subject / body
}

// Open the quick "New rule" modal, prefilled from the clicked message.
export function openRuleModal(message, field) {
  const addr = message?.from_addr || "";
  const domain = addr.includes("@") ? addr.split("@")[1] : "";
  const startField = field || (domain ? "from_domain" : "from");
  app.ruleModal = {
    message,
    draft: {
      name: `From ${domain || addr}`.trim(),
      match_field: startField,
      match_op: ruleOpForField(startField),
      match_value: ruleValueForField(startField, message),
      action: "move", action_arg: "Archive", enabled: true, order: 0,
    },
  };
}

// Context-menu "Create rule…": open the modal instead of jumping to Settings.
export function createRuleFromSender(message) {
  openRuleModal(message);
}

// Open the Security Lab (Settings → Security) with a full forensic report for
// this message — reachable from the list/reader right-click menu. IT-admin /
// power-user triage: headers, hop chain, DNS, links, attachment hashes + one-tap
// deep links to VirusTotal / urlscan / MXToolbox / AbuseIPDB / whois.
export function sendToLab(message) {
  if (!message) return;
  app.lab = { id: message.id, subject: message.subject || "", from: message.from_addr || "" };
  app.settingsTab = "security";
  app.view = "settings";
}

export async function setSenderCategory(message, category) {
  const addr = (message.from_addr || "").toLowerCase();
  // Optimistic: if it's moving into a grouped category, drop the sender's mail
  // from the main flow now (it reappears under the group card after refresh).
  if (category !== "auto" && smartActive() && groupedCategories().includes(category)) {
    app.messages = app.messages.filter((m) => (m.from_addr || "").toLowerCase() !== addr);
  }
  try {
    await messages.setSenderCategory(message.from_addr, category);
    notify(category === "auto" ? "Reset sender category" : `Sender → ${category}`);
    refreshMessages({ background: true });
  } catch (e) { notify("Couldn't reclassify", "error"); refreshMessages({ background: true }); }
}

export async function muteSender(message) {
  app.messages = app.messages.filter((m) => m.id !== message.id);
  try { await messages.mute(message.id); notify(`Muted ${message.from_addr}`); }
  catch (e) { notify("Couldn't mute", "error"); refreshMessages({ background: true }); }
}

export async function syncAllAccounts() {
  // No accounts → no sync:done event will ever clear the flag; don't set it.
  if (!app.accounts.length) return;
  app.syncing = true;
  for (const a of app.accounts) { try { await accounts.sync(a.id); } catch {} }
  notify("Syncing…");
}

/** Snooze preset times relative to now. */
export function snoozePresets() {
  const s = app.settings;
  const morning = s.scheduleMorningHour ?? 9;
  const eveningH = s.scheduleEveningHour ?? 18;
  const laterH = s.scheduleLaterHours ?? 3;
  const at = (d, h) => { const x = new Date(d); x.setHours(h, 0, 0, 0); return x; };
  const now = new Date();
  const laterToday = new Date(now.getTime() + laterH * 3600 * 1000);
  const tomorrow = at(new Date(now.getTime() + 86400000), morning);
  const evening = at(now, eveningH);
  const eveningOut = evening > now ? evening : at(new Date(now.getTime() + 86400000), eveningH);
  const sat = new Date(now); sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7 || 7)); sat.setHours(morning, 0, 0, 0);
  const mon = new Date(now); mon.setDate(now.getDate() + ((1 - now.getDay() + 7) % 7 || 7)); mon.setHours(morning, 0, 0, 0);
  return [
    { label: "Later today", at: laterToday, iso: laterToday.toISOString() },
    { label: "This evening", at: eveningOut, iso: eveningOut.toISOString() },
    { label: "Tomorrow", at: tomorrow, iso: tomorrow.toISOString() },
    { label: "This weekend", at: sat, iso: sat.toISOString() },
    { label: "Next week", at: mon, iso: mon.toISOString() },
    { label: "Until I'm back", presence: true },
  ];
}

// Human "when" for a preset target, e.g. "5:30 PM", "tomorrow 9:00 AM", "Mon 9:00 AM".
export function presetWhen(at) {
  if (!at) return "";
  const now = new Date();
  const time = at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (at.toDateString() === now.toDateString()) return time;
  const tom = new Date(now.getTime() + 86400000);
  if (at.toDateString() === tom.toDateString()) return `tomorrow ${time}`;
  if (at - now < 7 * 86400000) return `${at.toLocaleDateString([], { weekday: "short" })} ${time}`;
  return `${at.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

// True if the view the user is looking at is still the one an undo closure was
// created in — otherwise the optimistic re-insert would splice a foreign row
// into whatever list is currently displayed.
function _viewKey() {
  return `${app.selectedKind}|${app.selectedFolderId}|${app.category}|${app.search}`;
}

export async function snoozeMessage(message, untilISO, presence = false) {
  // Optimistically drop it from the current view.
  const idx = app.messages.findIndex((m) => m.id === message.id);
  const originView = _viewKey();
  app.messages = app.messages.filter((m) => m.id !== message.id);
  if (app.selectedMessageId === message.id) app.selectedMessageId = null;
  try {
    await messages.snooze(message.id, presence ? null : untilISO, presence);
    if (untilISO || presence) {
      notify(presence ? "Snoozed until you're back" : "Snoozed", "info", () => {
        message.snooze_until = null;
        if (_viewKey() === originView && !app.messages.some((m) => m.id === message.id)) {
          const at = idx >= 0 ? idx : app.messages.length;
          app.messages = [...app.messages.slice(0, at), message, ...app.messages.slice(at)];
        }
        // Re-sync to land the row in its correct sorted position (the captured
        // idx may be stale if the list changed during the undo window).
        messages.snooze(message.id, null, false)
          .then(() => refreshMessages({ background: true }))
          .catch(() => notify("Couldn't undo the snooze — check your connection", "error"));
      });
    } else {
      notify("Unsnoozed");
    }
  } catch (e) {
    notify("Couldn't snooze", "error");
    refreshMessages({ background: true });
  }
}

export function isVip(addr) {
  const a = (addr || "").toLowerCase().trim();
  if (!a) return false;
  const dom = a.split("@")[1] || "";
  return (app.settings.vipSenders || []).some((raw) => {
    const v = (raw || "").toLowerCase().trim().replace(/^@/, "");
    return v && (v === a || v === dom || dom.endsWith("." + v));
  });
}
export function toggleVip(addrOrMsg) {
  const a = (typeof addrOrMsg === "string" ? addrOrMsg : addrOrMsg?.from_addr || "").toLowerCase().trim();
  if (!a) return;
  const list = app.settings.vipSenders || [];
  const has = list.some((x) => (x || "").toLowerCase().trim() === a);
  saveSettings({ vipSenders: has ? list.filter((x) => (x || "").toLowerCase().trim() !== a) : [...list, a] });
  notify(has ? "Removed from VIP" : "Marked as VIP ⭐");
}

// Senders the user has marked trusted — suppresses the spoof/lookalike warning.
export function isTrustedSender(addr) {
  return (app.settings.trustedSenders || []).includes((addr || "").toLowerCase().trim());
}
export function trustSender(addr) {
  const a = (addr || "").toLowerCase().trim();
  if (!a || isTrustedSender(a)) return;
  saveSettings({ trustedSenders: [...(app.settings.trustedSenders || []), a] });
  notify("Marked safe — this sender now shows a green check ✓");
}
export function untrustSender(addr) {
  const a = (addr || "").toLowerCase().trim();
  if (!a) return;
  saveSettings({ trustedSenders: (app.settings.trustedSenders || []).filter((x) => x !== a) });
  notify("Removed “safe” mark");
}
export function toggleTrusted(addr) {
  isTrustedSender(addr) ? untrustSender(addr) : trustSender(addr);
}

// --- calendar background services: reminders + auto-sync of subscriptions ---
let _calEvents = [];
const _firedReminders = new Set();
let _calTimers = null;

export async function syncCalendarFeeds() {
  const s = app.settings;
  const has = (s.icsFeeds?.length > 0) || !!s.caldavUrl || !!s.carddavUrl;
  if (has) { try { await calendarApi.caldavSync(); } catch {} }
}
async function _loadUpcomingEvents() {
  const start = new Date();
  const end = new Date(start.getTime() + 9 * 86400000);  // next ~9 days
  try { _calEvents = (await calendarApi.list(start.toISOString(), end.toISOString())) || []; } catch {}
}
function _remindLabel(min) {
  if (min <= 0) return "now";
  if (min < 60) return `in ${min} min`;
  if (min < 1440) return `in ${Math.round(min / 60)} h`;
  if (min < 10080) return `in ${Math.round(min / 1440)} day(s)`;
  return `in ${Math.round(min / 10080)} week(s)`;
}
function _checkReminders() {
  const offsets = app.settings.calendarReminders || [];
  // NB: calendar reminders are NOT gated by email quiet hours — a meeting
  // reminder you explicitly set must still fire overnight/early. Quiet hours
  // only governs new-mail notifications.
  if (!offsets.length) return;
  const now = Date.now();
  for (const e of _calEvents) {
    if (!e.start || e.cancelled) continue;
    const t = new Date(e.start).getTime();
    for (const min of offsets) {
      const due = t - min * 60000;
      const key = `${e.id}:${min}`;
      // Fire once past the lead time, up to the event start — a fixed 90s
      // window silently skipped reminders when the machine slept across it.
      if (now >= due && now < t + 60000 && !_firedReminders.has(key)) {
        // Keys older than the reminder window can never fire again — don't let
        // a long-running session accumulate them forever.
        if (_firedReminders.size > 500) _firedReminders.clear();
        _firedReminders.add(key);
        sendNative(e.summary || "Event", `Starts ${_remindLabel(min)}${e.location ? " · " + e.location : ""}`);
      }
    }
  }
}
let _feedTimer = null;
// Self-rescheduling so a changed icsSyncMinutes takes effect without a restart.
function _scheduleFeedSync() {
  clearTimeout(_feedTimer);
  const ms = Math.max(5, app.settings.icsSyncMinutes || 30) * 60000;
  _feedTimer = setTimeout(() => {
    syncCalendarFeeds().then(_loadUpcomingEvents).finally(_scheduleFeedSync);
  }, ms);
}
export function startCalendarServices() {
  if (_calTimers) return;
  _loadUpcomingEvents();
  _calTimers = [
    setInterval(_checkReminders, 60000),                                   // reminders: every minute
    setInterval(_loadUpcomingEvents, 5 * 60000),                           // refresh window: every 5 min
  ];
  _scheduleFeedSync();                                                     // auto-sync feeds
}

export async function pinMessage(message, value) {
  const v = value ?? !message.pinned;
  const item = app.messages.find((m) => m.id === message.id);
  if (item) item.pinned = v;       // optimistic — list re-sorts immediately
  message.pinned = v;
  try { await messages.pin(message.id, v); }
  catch (e) { notify("Couldn't pin", "error"); if (item) item.pinned = !v; message.pinned = !v; }
}

export async function muteThread(message) {
  // Optimistically drop the whole conversation from the current view.
  const key = message.thread_id;
  if (key) app.messages = app.messages.filter((m) => m.thread_id !== key);
  else app.messages = app.messages.filter((m) => m.id !== message.id);
  if (app.selectedMessageId === message.id) { app.selectedMessageId = null; app.threadKey = null; }
  try {
    const r = await messages.muteThread(message.id);
    notify(`Conversation muted${r?.count ? ` (${r.count})` : ""}`);
  } catch (e) {
    notify("Couldn't mute conversation", "error");
    refreshMessages({ background: true });
  }
}

let _recategorized = false;
export async function recategorizeOnce() {
  if (_recategorized) return;
  _recategorized = true;
  try { await messages.recategorize(); } catch {}
  try { await messages.rethread(); } catch {}
}

/** Open a conversation in the reader. */
export function openThread(latest) {
  app.view = "mail";
  app.threadKey = latest.thread_id;
  app.selectedMessageId = latest.id;
  if (!latest.is_seen) setMessageSeen(latest, true);
}

// Hand a just-fetched thread to ThreadView so auto-opening a conversation
// doesn't fetch the same list twice (Reader detects the thread, ThreadView
// renders it).
export const threadPrefetch = { key: null, msgs: null };

// Route a keyboard shortcut to whichever reader surface is showing (single
// message or conversation) — they own the bodies needed to build the quote.
export function readerCommand(cmd) {
  app.readerCmd = { cmd, n: (app.readerCmd?.n || 0) + 1 };
}

// Archive/delete a single message: optimistic removal, Spark-style advance to
// the next message when the removed one was open, toast. Used by the list row,
// the reader toolbar, and the keyboard shortcuts.
async function _removeMessage(message, action, label) {
  const wasSelected = app.selectedMessageId === message.id;
  const idx = app.messages.findIndex((m) => m.id === message.id);
  app.messages = app.messages.filter((m) => m.id !== message.id);
  if (wasSelected) {
    const next = (app.settings.openNextOnDone && idx >= 0)
      ? (app.messages[idx] || app.messages[idx - 1]) : null;
    app.threadKey = null;
    app.selectedMessageId = next ? next.id : null;
    if (next && !next.is_seen) setMessageSeen(next, true);
  }
  try {
    await messages.bulk([message.id], action);
    notify(label);
    refreshQueue();
    refreshFoldersSoon();
  } catch (e) {
    notify(`Couldn't ${action} — restoring`, "error");
    refreshMessages({ background: true });
  }
}
export function archiveMessage(message) { return _removeMessage(message, "archive", "Archived"); }
export function deleteMessage(message) { return _removeMessage(message, "delete", "Deleted"); }

// Open a message in the reader by id (used by the AI inbox assistant). The
// Reader fetches the full message from the id, so it needn't be in the list.
export function openMessageById(id) {
  if (id == null) return;
  app.view = "mail";
  app.threadKey = null;
  app.selectedMessageId = id;
  // Opening a message marks it read (matches clicking it in the list).
  const m = app.messages.find((x) => x.id === id);
  if (m) setMessageSeen(m, true);
  else messages.setSeen(id, true).catch(() => {});
}

// Merge a freshly-fetched list into an existing one WITHOUT swapping every row
// object. Reuse the existing object (by id) for messages still present and copy
// changed fields onto it in place — Svelte's $state proxy only notifies for
// fields that actually changed, so an unchanged row doesn't re-render. That's
// what stops the list from flickering on every background sync. New messages
// pass through as-is; removed ones fall out (the keyed {#each} plays their
// out-transition).
export function mergeById(prev, next) {
  if (!prev?.length) return next;
  const byId = new Map(prev.map((m) => [m.id, m]));
  return next.map((m) => {
    const old = byId.get(m.id);
    if (!old) return m;
    Object.assign(old, m);   // unchanged primitives are no-ops through the proxy
    return old;              // keep identity so the row (avatar, shield, focus) stays put
  });
}
const mergeMessages = (next) => mergeById(app.messages, next);

// Latest-request-wins: overlapping loads (fast navigation, background refresh
// racing a user click) must not let an OLDER response clobber a newer view.
let _msgGen = 0;
export async function refreshMessages({ background = false } = {}) {
  const gen = ++_msgGen;
  const fresh = () => gen === _msgGen;   // still the most recent request?
  const done = () => { if (fresh()) app.loading = false; };
  if (!background) app.loading = true;
  try {
    if (app.selectedKind === "followups") {
      try {
        const list = await messages.followups(app.settings.followupDays || 3);
        if (!fresh()) return;
        app.messages = mergeMessages(list);
      } finally { done(); }
      prefetchVisible(app.messages.map((m) => m.id));
      return;
    }
    // Smart Inbox: main flow excludes grouped categories; cards show their counts.
    if (smartActive() && !app.search) {
      const scope = app.selectedKind === "smart" ? { role: "inbox" } : { folder_id: app.selectedFolderId };
      const grouped = groupedCategories();
      try {
        let list = await messages.list({ ...scope, exclude_categories: grouped.join(","), include_done: app.showDone });
        if (!fresh()) return;
        if (app.selectedKind === "smart") {
          const ws = workspaceAccountIds();
          if (ws) list = list.filter((m) => ws.includes(m.account_id));
        }
        app.messages = mergeMessages(list);
        messages.smartGroups({ ...scope, new_days: app.settings.smartNewDays ?? 3 })
          .then((d) => { if (fresh()) app.smartGroupData = d; }).catch(() => {});
      } finally { done(); }
      prefetchVisible(app.messages.map((m) => m.id));
      return;
    }
    // Smart search: try meaning-based, then AI keyword extraction, then fall
    // through to plain keyword search so the user always gets *some* results.
    if (app.search && app.semantic) {
      const showList = (list) => {
        if (!list || !list.length) return false;
        app.messages = mergeMessages(list);
        done();
        prefetchVisible(app.messages.map((m) => m.id));
        return true;
      };
      app.aiBusy = true;
      try {
        // 1. Local embedding index (best) — only if the user built one.
        if (app.settings.semanticEnabled) {
          const list = await ai.semantic(app.search, 80);
          if (!fresh()) return;
          if (showList(list)) return;
        }
        // 2. AI turns the plain-language request into keywords, then keyword-search.
        if (aiEnabled()) {
          const { query } = await ai.search(app.search);
          if (!fresh()) return;
          if (query) {
            const list = await messages.list({ q: query });
            if (!fresh()) return;
            if (showList(list)) return;
          }
        }
      } catch { /* fall back to keyword below */ }
      finally { app.aiBusy = false; }
    }
    let params;
    if (app.search) {
      params = { q: app.search };
    } else if (app.selectedKind === "snoozed") {
      params = { snoozed_only: true };
    } else if (app.selectedKind === "screener") {
      params = { role: "inbox", screener: "only" };
    } else if (app.selectedKind === "papertrail") {
      params = { role: "inbox", category: "updates", include_done: app.showDone };
    } else if (app.selectedKind === "unified") {
      params = { role: "inbox", include_done: app.showDone };
      if (app.settings.screener) params.screener = "exclude";  // hide first-time senders
    } else if (app.selectedKind === "sent") {
      params = { role: "sent", include_done: true };
    } else if (app.selectedKind === "drafts") {
      params = { role: "drafts", include_done: true };
    } else {
      params = { folder_id: app.selectedFolderId ?? undefined, include_done: app.showDone };
      if (app.settings.screener && app.selectedFolderRole === "inbox") params.screener = "exclude";
    }
    if (app.category && !app.search) params.category = app.category;
    let list = await messages.list(params);
    if (!fresh()) return;
    // Workspace isolation: limit the unified inbox to the active workspace's accounts.
    const wsIds = workspaceAccountIds();
    if (wsIds && app.selectedKind === "unified") list = list.filter((m) => wsIds.includes(m.account_id));
    app.messages = mergeMessages(list);
  } finally {
    done();
  }
  prefetchVisible(app.messages.map((m) => m.id));
}

// --- body prefetch: open instantly by caching bodies ahead of the click ----
//
// Bodies are fetched over IMAP behind a per-account lock on the backend, so
// fetches serialise. Firing many in parallel floods that lock and makes an
// actual click wait behind the whole queue. Instead we run ONE background
// prefetch at a time (a low-priority queue), leaving the connection free for
// the message the user actually opens. An explicit prefetchBody(id, true)
// jumps the queue (e.g. the row under the cursor / keyboard focus).
const prefetched = new Set();
let prefetchQueue = [];
let prefetchRunning = false;

async function drainPrefetch() {
  if (prefetchRunning) return;
  prefetchRunning = true;
  try {
    while (prefetchQueue.length) {
      const id = prefetchQueue.shift();
      if (!id || prefetched.has(id)) continue;
      // Ids are tiny but a long session shouldn't grow this without bound; a
      // reset just means an already-cached body gets re-fetched once.
      if (prefetched.size > 5000) prefetched.clear();
      prefetched.add(id);
      try {
        const detail = await messages.get(id);
        // Upgrade the list row with body-derived info (brand avatar, auth shield).
        if (detail) {
          const m = app.messages.find((x) => x.id === id);
          if (m) {
            if (detail.brand_domain && m.brand_domain !== detail.brand_domain) m.brand_domain = detail.brand_domain;
            if (detail.auth_status && m.auth_status !== detail.auth_status) m.auth_status = detail.auth_status;
          }
        }
      } catch { prefetched.delete(id); }
    }
  } finally {
    prefetchRunning = false;
  }
}

export function prefetchBody(id, urgent = false) {
  if (!id || prefetched.has(id) || prefetchQueue.includes(id)) return;
  if (urgent) prefetchQueue.unshift(id); else prefetchQueue.push(id);
  drainPrefetch();
}
export function prefetchVisible(ids) {
  // Queue a small leading window; the rest fill in as the user hovers/navigates.
  ids.slice(0, 4).forEach((id) => prefetchBody(id));
  preloadAvatars();
}

// Warm the browser cache for sender/brand favicons so avatars don't pop in when
// the list re-renders (e.g. returning from Settings).
const _avatarWarmed = new Set();
function preloadAvatars() {
  if (app.settings.senderAvatars === false || typeof Image === "undefined") return;
  // Bound the memo set over a marathon session (domains are HTTP-cached anyway,
  // so re-warming a handful after a reset is cheap).
  if (_avatarWarmed.size > 4000) _avatarWarmed.clear();
  for (const m of app.messages.slice(0, 80)) {
    for (const d of [(m.from_addr || "").split("@")[1], m.brand_domain]) {
      const dom = (d || "").toLowerCase().trim();
      if (!dom || !dom.includes(".") || _avatarWarmed.has(dom)) continue;
      _avatarWarmed.add(dom);
      const img = new Image();
      img.src = avatarUrlDomain(dom);
    }
  }
}

// Folder counts (sidebar unread/badges) refresh after triage actions. Debounced
// so rapid keyboard triage (holding/repeating `e`) coalesces into one request
// instead of one round-trip per keystroke.
let _folderRefreshTimer = null;
export function refreshFoldersSoon() {
  clearTimeout(_folderRefreshTimer);
  _folderRefreshTimer = setTimeout(() => {
    folders.list().then((f) => { app.folders = f; updateBadge(); }).catch(() => {});
  }, 350);
}

export async function markDone(message, done) {
  const wasSelected = app.selectedMessageId === message.id;
  const idx = app.messages.findIndex((m) => m.id === message.id);
  // Optimistic, in-place so the "done" indicator updates immediately.
  const item = app.messages.find((m) => m.id === message.id);
  if (item) item.is_done = done;
  if (message) message.is_done = done;
  // When the list hides done (slider off), marking done removes it from view.
  if (!app.showDone && done) {
    app.messages = app.messages.filter((m) => m.id !== message.id);
    if (wasSelected) {
      // Spark-style: open the next message so you can keep reading.
      const next = (app.settings.openNextOnDone && idx >= 0)
        ? (app.messages[idx] || app.messages[idx - 1]) : null;
      if (next) {
        app.threadKey = null;
        app.selectedMessageId = next.id;
        if (!next.is_seen) { next.is_seen = true; messages.setSeen(next.id, true).catch(() => {}); }
      } else {
        app.selectedMessageId = null;
      }
    }
  }
  try {
    await messages.setDone(message.id, done);
    refreshFoldersSoon();
    // Offer a quick undo when a message was archived out of the view.
    if (!app.showDone && done) {
      const originView = _viewKey();
      notify("Marked done", "info", () => {
        message.is_done = false;
        // idx < 0 = the message lives inside an expanded smart-group card, not
        // the main list — flipping is_done un-hides it there; don't splice a
        // duplicate row into the main list.
        if (_viewKey() === originView && idx >= 0 && !app.messages.some((m) => m.id === message.id)) {
          app.messages = [...app.messages.slice(0, idx), message, ...app.messages.slice(idx)];
        }
        messages.setDone(message.id, false)
          .then(() => { refreshFoldersSoon(); refreshMessages({ background: true }); })
          .catch(() => notify("Couldn't undo — check your connection", "error"));
      });
    }
  } catch (e) {
    notify("Couldn't update — restoring", "error");
    refreshMessages({ background: true });
  }
}

export function toggleShowDone() {
  app.showDone = !app.showDone;
  app.selectedMessageId = null;
  refreshMessages();
}

// Quick "show mail from this address" — uses the reliable from: operator.
export function searchAddress(addr) {
  app.view = "mail";
  app.search = `from:${addr}`;
  app.semantic = false;
  app.selectedMessageId = null;
  refreshMessages();
}

export function runSearch(query) {
  app.view = "mail";
  app.search = query;
  app.semantic = false;
  app.selectedMessageId = null;
  refreshMessages();
}

// Whether AI actions/buttons should be shown. True when the user hasn't hidden
// them AND a provider is usable — a cloud key is set, OR the provider is Ollama
// (local, keyless). This is the single source of truth so keyless Ollama no
// longer hides every AI button for lack of an API key.
export function aiEnabled() {
  if (app.settings.aiButtons === false) return false;
  return !!(app.settings.aiApiKey || "").trim() || app.settings.aiProvider === "ollama";
}

// Open the AI assistant (multi-mail context chat). `seed` optionally pre-loads
// context: { messageId, threadId, threadKey }.
export function openAiAssistant(seed = null) {
  app.aiAssistantSeed = seed;
  app.aiAssistantOpen = true;
}

// Add a message to the AI assistant's context tray (right-click → Add to AI chat).
// Opens the assistant if it's closed; works while it's already open too.
export function addToAiChat(m) {
  if (!m) return;
  const item = { id: m.id, from: m.from_name || m.from_addr || "?",
                 subject: m.subject || "(no subject)", date: m.date };
  if (!app.aiChatContext.some((c) => c.id === item.id)) {
    app.aiChatContext = [...app.aiChatContext, item];
  }
  app.aiAssistantSeed = null;   // we're adding directly; don't double-seed on mount
  app.aiAssistantOpen = true;
  notify(`Added to AI chat: ${item.subject}`);
}

// --- Adaptive Ollama: warm the model into VRAM while the app is focused, unload
// it shortly after the app loses focus — unless the user is mid-AI-task. This is
// the "adaptive" option in Settings → AI assistant → Free GPU after.
function _adaptiveOn() {
  return app.settings.aiProvider === "ollama"
      && app.settings.ollamaKeepAlive === "adaptive" && aiEnabled();
}
let _adaptiveUnloadTimer;
function _onAppFocus() {
  if (!_adaptiveOn()) return;
  clearTimeout(_adaptiveUnloadTimer);
  ai.ollamaWarm().catch(() => {});
}
function _onAppBlur() {
  if (!_adaptiveOn()) return;
  clearTimeout(_adaptiveUnloadTimer);
  // Small delay so a quick alt-tab doesn't thrash the model in/out of VRAM.
  _adaptiveUnloadTimer = setTimeout(() => {
    if (app.aiBusy || app.aiAssistantOpen) return;   // don't yank it mid-use
    ai.ollamaUnload().catch(() => {});
  }, 5000);
}
if (typeof window !== "undefined") {
  window.addEventListener("focus", _onAppFocus);
  window.addEventListener("blur", _onAppBlur);
  // Warm on startup if we launch focused (no focus event fires for that).
  queueMicrotask(() => { try { if (document.hasFocus?.()) _onAppFocus(); } catch {} });
}

// Meaning-based search over the local embedding index (Settings → Semantic
// search). Falls back to keyword search in refreshMessages if the index is off,
// the endpoint is unreachable, or nothing matched.
export function runSemanticSearch(query) {
  app.view = "mail";
  app.search = query;
  app.semantic = true;
  app.selectedMessageId = null;
  refreshMessages();
}

export function saveCurrentSearch(name) {
  const query = app.search.trim();
  if (!query || !name) return;
  const id = (crypto.randomUUID && crypto.randomUUID()) || `ss${Date.now()}`;
  saveSettings({ savedSearches: [...app.settings.savedSearches, { id, name, query }] });
  notify(`Saved search “${name}”`);
}

export function removeSavedSearch(id) {
  saveSettings({ savedSearches: app.settings.savedSearches.filter((s) => s.id !== id) });
}

// --- desktop notifications -------------------------------------------------
// In the Tauri shell we use the native notification plugin (the webview's web
// Notification API is usually blocked and can't be re-enabled by the user —
// that's the "blocked by the system" you saw). In a browser we fall back to the
// web Notification API.
async function _notifPlugin() {
  if (!isTauri()) return null;
  try { return await import("@tauri-apps/plugin-notification"); } catch { return null; }
}
export function notificationsAvailable() {
  return isTauri() || typeof Notification !== "undefined";
}
export async function enableNotifications() {
  const mod = await _notifPlugin();
  if (mod) {
    let granted = await mod.isPermissionGranted();
    if (!granted) granted = (await mod.requestPermission()) === "granted";
    return granted ? "granted" : "denied";
  }
  if (typeof Notification === "undefined") return "unsupported";
  if (Notification.permission === "granted") return "granted";
  try { return await Notification.requestPermission(); } catch { return "denied"; }
}
// Low-level send used by every notification path.
async function sendNative(title, body) {
  const mod = await _notifPlugin();
  if (mod) {
    try {
      if (!(await mod.isPermissionGranted()) && (await mod.requestPermission()) !== "granted") return false;
      mod.sendNotification({ title, body });
      return true;
    } catch { return false; }
  }
  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    try { const n = new Notification(title, { body }); n.onclick = () => { try { window.focus(); } catch {} n.close(); }; return true; }
    catch { return false; }
  }
  return false;
}
// Quiet hours: true if the current local hour is within the configured window
// (handles windows that wrap past midnight, e.g. 22 → 7).
export function inQuietHours() {
  if (!app.settings.quietHoursEnabled) return false;
  const h = new Date().getHours();
  const s = app.settings.quietStart ?? 22;
  const e = app.settings.quietEnd ?? 7;
  return s <= e ? (h >= s && h < e) : (h >= s || h < e);
}
function desktopNotify(payload, count) {
  if (app.settings.notifyNewMail === false) return;
  // Never fire without a real message preview — a notification with no sender/
  // subject is the "empty notification" bug. Genuine new inbox mail always has
  // one now (the backend only counts notify-worthy inbox arrivals).
  if (!payload) return;
  // VIP mail always breaks through quiet hours and the focused-window rule.
  const vip = isVip(payload?.from_addr);
  if (!vip && inQuietHours()) return;
  // The ding plays even when the window is focused (audible feedback that mail
  // landed) — only the OS notification honors the "only when unfocused" rule.
  playSound(app.settings.notifySound || "ding", (app.settings.notifyVolume ?? 80) / 100);
  if (!vip) {
    if (app.settings.notifyOnlyUnfocused !== false && typeof document !== "undefined"
        && document.hasFocus && document.hasFocus()) return;
  }
  const p = payload || {};
  let title, body;
  if (count > 1) {
    title = `${count} new messages`;
    body = p.from ? `Latest: ${p.from} — ${p.subject || ""}` : "";
  } else {
    title = p.from || "New message";
    body = p.subject || "";
  }
  sendNative(title, body);
}

// Fire a notification immediately to verify the OS path works (ignores the
// "only when unfocused" rule so the user always sees the test).
export async function testNotification() {
  const perm = await enableNotifications();
  if (perm === "unsupported") return { ok: false, reason: "unsupported" };
  if (perm !== "granted") return { ok: false, reason: "denied" };
  const ok = await sendNative("RaplMail", "Test notification — you're all set ✓");
  return ok ? { ok: true } : { ok: false, reason: "error" };
}

let disconnect = null;
export function startEvents() {
  if (disconnect) return;
  // Events emitted while the socket was down (backend restart, network blip)
  // are gone — treat every reconnect as a missed sync:done and catch up.
  const onReconnect = () => {
    loadAccountsAndFolders();
    refreshMessages({ background: true });
    refreshQueue();
    app.syncTick = (app.syncTick || 0) + 1;
  };
  disconnect = connectEvents((ev) => {
    if (ev.event === "sync:done") {
      app.syncing = false;
      loadAccountsAndFolders();
      // Background refresh: don't blank the list the user is looking at.
      refreshMessages({ background: true });
      // Bump a tick so other views (Home/Dashboard, Calendar) can refresh live
      // when new mail lands, instead of only updating on navigation.
      app.syncTick = (app.syncTick || 0) + 1;
      // `notify` = genuinely notify-worthy new inbox mail (unread, survived
      // rules, not notification-muted). Older payloads without it fall back to
      // `new` only when a preview exists, so we never fire an empty popup.
      const n = ev.payload?.notify ?? (ev.payload?.preview ? ev.payload?.new : 0);
      if (n > 0) {
        notify(`${n} new message(s)`);
        desktopNotify(ev.payload.preview, n);
      }
    } else if (ev.event === "sync:error") {
      app.syncing = false;
    } else if (ev.event === "queue") {
      app.queuePending = ev.payload?.pending ?? 0;
      app.queueFailed = ev.payload?.failed ?? 0;
    } else if (ev.event === "presence:back") {
      // Returned to the desk — "until I'm back" mail was resurfaced server-side.
      if (ev.payload?.count) notify(`Welcome back — ${ev.payload.count} message(s) resurfaced`);
      refreshMessages({ background: true });
    } else if (ev.event === "mail:opened") {
      // A read-receipt tracking pixel fired — someone opened your message.
      const subj = ev.payload?.subject ? `“${ev.payload.subject}”` : "your message";
      notify(`📬 ${ev.payload?.recipient || "Someone"} opened ${subj}`);
    } else if (ev.event === "inbox:digest") {
      // Scheduled morning briefing arrived — cache it and nudge the user.
      app.aiDigest = ev.payload?.digest || "";
      const first = (app.aiDigest.split("\n").find((l) => l.trim()) || "Your morning briefing is ready");
      notify("☀️ Morning briefing ready — open the inbox assistant");
      sendNative("RaplMail — morning briefing", first.slice(0, 180));
    }
  }, onReconnect);
  refreshQueue();
}
