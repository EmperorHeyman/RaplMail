// All RaplMail UI icons in one place.
//
// Material Symbols Rounded (Google's icon set, Apache-2.0) - the shapes are in
// msym.js. Each value is an inline SVG string filled with `currentColor`, so an
// icon takes the text colour of wherever it's placed, and sized `1em`, so it
// scales with font-size.
//
// Because these are markup (not plain glyphs), components render them with
// Svelte's `{@html icons.x}` rather than `{icons.x}`.
//
// `icons.x` is the outlined style; `iconsFilled.x` the filled one, which marks
// the active item in navigation (as Android does).
import { MS } from "./msym.js";

/** @param {string} d */
const svg = (d) =>
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" width="1em" height="1em" ' +
  `fill="currentColor" aria-hidden="true" style="vertical-align:-0.15em"><path d="${d}"/></svg>`;

// Our icon names -> Material Symbols names. Keys are what components use.
const NAMES = {
  // Brand
  brand: "mail",
  // Home / dashboard
  home: "home",
  // Folder roles
  inbox: "inbox", archive: "archive", sent: "send", drafts: "draft", trash: "delete",
  junk: "report", folder: "folder", unified: "all_inbox",
  // Message actions
  compose: "edit", reply: "reply", replyAll: "reply_all", forward: "forward", done: "check",
  restore: "undo", flag: "star", attachment: "attach_file",
  // App chrome
  sync: "sync", settings: "settings", search: "search", sliders: "tune", close: "close",
  copy: "content_copy", pin: "push_pin", hide: "visibility_off", show: "visibility",
  // Settings tabs
  accounts: "account_circle", contacts: "contacts", rules: "filter_alt", signature: "signature",
  general: "tune", mail: "mail",
  // Empty states
  inboxZero: "celebration", allDone: "check_circle", placeholderMail: "drafts", warning: "warning",
  // Smart views / sidebar nav
  smart: "auto_awesome", screener: "verified_user", snooze: "snooze", clock: "schedule",
  newspaper: "newspaper", receipt: "receipt_long", alarm: "alarm",
  // Customize / layout / security
  customize: "dashboard_customize", lock: "lock", unlock: "lock_open", shield: "shield",
  shieldCheck: "verified_user", shieldAlert: "gpp_maybe",
  // Compose / editor tools
  link: "link", image: "image", clearFormat: "format_clear", bulb: "lightbulb",
  // Categories
  bell: "notifications", chat: "forum", video: "videocam", tag: "sell", calendar: "calendar_today",
  // Settings tabs / actions
  groups: "view_agenda", workspaces: "workspaces", bolt: "bolt", palette: "palette",
  keyboard: "keyboard", mute: "notifications_off", reset: "restart_alt", inboxMove: "move_to_inbox",
  star: "star",
  // Files / misc
  download: "download", save: "save", upload: "upload", edit: "edit", window: "open_in_new",
  external: "open_in_new", sparkles: "auto_awesome", paperclip: "attach_file", info: "info",
  globe: "language", eye: "visibility", doneAll: "done_all", x: "close",
  // Navigation chrome
  chevronRight: "chevron_right", chevronLeft: "chevron_left", expandMore: "expand_more",
  expandLess: "expand_less", menu: "menu", menuOpen: "menu_open", add: "add", more: "more_vert",
  moreHoriz: "more_horiz", back: "arrow_back", markUnread: "mark_email_unread",
  markRead: "mark_email_read", moveTo: "drive_file_move", label: "label",
  tickets: "confirmation_number", subscriptions: "unsubscribe", person: "person", filter: "filter_list",
  hub: "hub", event: "event", taskAlt: "task_alt", block: "block", refresh: "refresh",
  history: "history", bug: "bug_report", print: "print", code: "code",
  // Appearance
  lightMode: "light_mode", darkMode: "dark_mode", contrast: "contrast", autoMode: "brightness_auto",
  densitySmall: "density_small", densityMedium: "density_medium", densityLarge: "density_large",
  textSize: "format_size", textSmaller: "text_decrease", textBigger: "text_increase", colors: "colors",
};

/** @type {Record<string, string>} */
export const icons = {};
/** @type {Record<string, string>} */
export const iconsFilled = {};
for (const [key, name] of Object.entries(NAMES)) {
  const [outline, filled] = MS[name];
  icons[key] = svg(outline);
  iconsFilled[key] = svg(filled || outline);
}
// A flagged message wears the filled star.
icons.flagged = iconsFilled.flag;

// Providers - true brand marks, in their own colours (not Material shapes).
icons.microsoft =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" style="vertical-align:-0.14em">' +
  '<rect x="3" y="3" width="8" height="8" fill="#F25022"/><rect x="13" y="3" width="8" height="8" fill="#7FBA00"/>' +
  '<rect x="3" y="13" width="8" height="8" fill="#00A4EF"/><rect x="13" y="13" width="8" height="8" fill="#FFB900"/></svg>';
icons.google =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" fill="none" ' +
  'stroke-width="3" stroke-linecap="round" style="vertical-align:-0.14em">' +
  '<path d="M18.13 6.86A8 8 0 0 0 19.25 15.38" stroke="#EA4335"/>' +
  '<path d="M19.25 15.38A8 8 0 0 1 8.62 19.25" stroke="#FBBC05"/>' +
  '<path d="M8.62 19.25A8 8 0 0 1 4.75 8.62" stroke="#34A853"/>' +
  '<path d="M4.75 8.62A8 8 0 0 1 17.14 5.87" stroke="#4285F4"/>' +
  '<path d="M12 12h8" stroke="#4285F4"/></svg>';

/** Filled variant of an icon key (falls back to the outlined one). */
export function filledIcon(key) {
  return iconsFilled[key] || icons[key] || "";
}

/** Icon for a folder by its role, with a sensible fallback. */
export function folderIcon(role, filled = false) {
  const key = icons[role] ? role : "folder";
  return filled ? filledIcon(key) : icons[key];
}

// Map a sender's email domain to a brand mark (Spark-style avatars). Returns an
// SVG string for known providers, or null to fall back to the initial avatar.
const BRAND_DOMAINS = [
  { re: /(^|\.)(gmail|googlemail)\.com$/, icon: icons.google },
  { re: /(^|\.)google\.com$/, icon: icons.google },
  { re: /(^|\.)(outlook|hotmail|live|msn)\.[a-z.]+$/, icon: icons.microsoft },
  { re: /(^|\.)(microsoft|office365|sharepointonline|microsoftonline)\.com$/, icon: icons.microsoft },
];
/** @param {string} email */
export function brandFor(email) {
  const d = (String(email || "").split("@")[1] || "").toLowerCase().trim();
  if (!d) return null;
  for (const b of BRAND_DOMAINS) if (b.re.test(d)) return b.icon;
  return null;
}
