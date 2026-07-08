// All RaplMail UI icons in one place.
//
// Each value is an inline SVG string - original, hand-drawn line art on a
// 24×24 grid. They use `currentColor`, so an icon takes the text color of
// wherever it's placed, and `width/height: 1em`, so it scales with font-size.
//
// Because these are markup (not plain glyphs), components render them with
// Svelte's `{@html icons.x}` rather than `{icons.x}`.

// Shared attributes for the line-icon style: rounded strokes, no fill, sized
// to the surrounding text. `vertical-align` nudges them onto the text baseline.
const A =
  'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" ' +
  'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
  'stroke-linejoin="round" style="vertical-align:-0.14em"';

// Line icon: stroked paths on the shared grid.
/** @param {string} body */
const line = (body) => `<svg ${A}>${body}</svg>`;

// Solid icon: filled with currentColor, no stroke (e.g. a flagged star).
/** @param {string} body */
const solid = (body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" ` +
  `fill="currentColor" style="vertical-align:-0.14em">${body}</svg>`;

// A 5-pointed star, shared by the flag (outline) and flagged (filled) icons.
const STAR =
  "M12 2.8 14.17 9.01 20.75 9.16 15.52 13.14 17.41 19.44 12 15.7 6.59 19.44 8.48 13.14 3.25 9.16 9.83 9.01Z";

export const icons = {
  // Brand
  brand: line('<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="m3 7.5 9 6 9-6"/>'),

  // Home / dashboard
  home: line('<path d="M3.5 11 12 4l8.5 7"/><path d="M5.5 9.5V19a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1V9.5"/>'),

  // Folder roles
  inbox: line(
    '<path d="M12 3v9m0 0 3.5-3.5M12 12 8.5 8.5"/>' +
    '<path d="M3 13h4l2 3h6l2-3h4v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
  ),
  archive: line(
    '<rect x="3" y="4" width="18" height="4" rx="1"/>' +
    '<path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/><path d="M10 12h4"/>'
  ),
  sent: line('<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>'),
  drafts: line(
    '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>' +
    '<path d="M14 3v5h5"/><path d="M18.5 2.5a1.4 1.4 0 0 1 2 2L15 10l-3 1 1-3z"/>'
  ),
  trash: line(
    '<path d="M4 7h16"/><path d="M10 4h4a1 1 0 0 1 1 1v2H9V5a1 1 0 0 1 1-1z"/>' +
    '<path d="M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7"/><path d="M10 11v6M14 11v6"/>'
  ),
  junk: line('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6 18.4 18.4"/>'),
  folder: line('<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  unified: line('<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/>'),

  // Message actions
  compose: line('<path d="M4 20h4L19 9a2 2 0 0 0-3-3L5 17z"/><path d="m14 7 3 3"/>'),
  reply: line('<path d="M9 7 4 12l5 5"/><path d="M4 12h11a5 5 0 0 1 5 5v1"/>'),
  replyAll: line('<path d="m7 7-5 5 5 5"/><path d="m12 7-5 5 5 5"/><path d="M12 12h6a4 4 0 0 1 4 4v1"/>'),
  forward: line('<path d="m15 7 5 5-5 5"/><path d="M20 12H9a5 5 0 0 0-5 5v1"/>'),
  done: line('<path d="m5 12.5 4.5 4.5L19 7"/>'),
  restore: line('<path d="M3 4v4h4"/><path d="M3 8a9 9 0 1 0 3-2.4"/>'),
  flag: line(STAR),
  flagged: solid(`<path d="${STAR}"/>`),
  attachment: line(
    '<path d="M20 11.5 11 20.5a5 5 0 0 1-7-7l9-9a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.6 1.6 0 0 1-2.3-2.3l7.8-7.8"/>'
  ),

  // App chrome
  sync: line(
    '<path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>' +
    '<path d="M21 3v5h-5"/><path d="M3 21v-5h5"/>'
  ),
  settings: line(
    '<path d="M10.05 1.99 13.95 1.99 13.67 3.77 16.64 5 17.7 3.54 20.46 6.3 19 7.36 ' +
    '20.23 10.33 22.01 10.05 22.01 13.95 20.23 13.67 19 16.64 20.46 17.7 17.7 20.46 ' +
    '16.64 19 13.67 20.23 13.95 22.01 10.05 22.01 10.33 20.23 7.36 19 6.3 20.46 ' +
    '3.54 17.7 5 16.64 3.77 13.67 1.99 13.95 1.99 10.05 3.77 10.33 5 7.36 3.54 6.3 ' +
    '6.3 3.54 7.36 5 10.33 3.77Z"/><circle cx="12" cy="12" r="3.1"/>'
  ),
  search: line('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>'),
  sliders: line('<path d="M4 6h11"/><circle cx="18" cy="6" r="2.2"/><path d="M20 12H9"/><circle cx="6" cy="12" r="2.2"/><path d="M4 18h11"/><circle cx="18" cy="18" r="2.2"/>'),
  close: line('<path d="M6 6 18 18M18 6 6 18"/>'),
  copy: line('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>'),
  pin: line('<path d="M12 17v5"/><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/>'),
  hide: line(
    '<path d="m3 3 18 18"/>' +
    '<path d="M10.5 6.2A9.8 9.8 0 0 1 12 6c5.5 0 9.5 4.5 10.5 6a13.7 13.7 0 0 1-3.1 3.8"/>' +
    '<path d="M6.6 6.6C3.8 8.1 1.8 10.5 1.5 12c1 1.6 5 6 10.5 6a10 10 0 0 0 3.9-.8"/>' +
    '<path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'
  ),
  show: line('<path d="M1.5 12S5.5 5 12 5s10.5 7 10.5 7-4 7-10.5 7S1.5 12 1.5 12z"/><circle cx="12" cy="12" r="3"/>'),

  // Settings tabs
  accounts: line('<circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0 1 16 0"/>'),
  contacts: line(
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 8H2m2 4H2m2 4H2"/>' +
    '<circle cx="11" cy="10" r="2.5"/><path d="M7.5 16a3.5 3.5 0 0 1 7 0"/>'
  ),
  rules: line('<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'),
  signature: line('<path d="M3 16c3 0 3-9 6-9s2 7 5 7 3-3.5 7-3.5"/><path d="M3 21h18"/>'),
  general: line(
    '<path d="M4 6h9M19 6h1M4 12h1M11 12h9M4 18h7M17 18h3"/>' +
    '<circle cx="16" cy="6" r="2.2"/><circle cx="8" cy="12" r="2.2"/><circle cx="14" cy="18" r="2.2"/>'
  ),

  // Providers - true brand marks, in their own colors.
  microsoft:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" style="vertical-align:-0.14em">' +
    '<rect x="3" y="3" width="8" height="8" fill="#F25022"/><rect x="13" y="3" width="8" height="8" fill="#7FBA00"/>' +
    '<rect x="3" y="13" width="8" height="8" fill="#00A4EF"/><rect x="13" y="13" width="8" height="8" fill="#FFB900"/></svg>',
  google:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em" fill="none" ' +
    'stroke-width="3" stroke-linecap="round" style="vertical-align:-0.14em">' +
    '<path d="M18.13 6.86A8 8 0 0 0 19.25 15.38" stroke="#EA4335"/>' +
    '<path d="M19.25 15.38A8 8 0 0 1 8.62 19.25" stroke="#FBBC05"/>' +
    '<path d="M8.62 19.25A8 8 0 0 1 4.75 8.62" stroke="#34A853"/>' +
    '<path d="M4.75 8.62A8 8 0 0 1 17.14 5.87" stroke="#4285F4"/>' +
    '<path d="M12 12h8" stroke="#4285F4"/></svg>',
  mail: line('<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="m3 7.5 9 6 9-6"/>'),

  // Empty states
  inboxZero: line(
    '<path d="M3.5 20.5 8 8.5l7.5 7.5z"/><path d="M8 8.5c2.2 0 3.5 1.3 3.5 3.5"/>' +
    '<path d="M15 3v2.5M19.5 4.5 18 6.5M21 10h-2.5M17.5 8.5l1.8 1.4"/>'
  ),
  allDone: line('<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'),
  placeholderMail: line(
    '<path d="M3 9 12 3.5 21 9"/><path d="M3 9v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9"/><path d="m3 9 9 6 9-6"/>'
  ),
  warning: line('<path d="M12 3.2 22 19.5H2z"/><path d="M12 9.5v4.2"/><path d="M12 17h.01"/>'),

  // Smart views / sidebar nav
  smart: line('<path d="M12 3.5c.5 4 1.5 5 5.5 5.5-4 .5-5 1.5-5.5 5.5-.5-4-1.5-5-5.5-5.5 4-.5 5-1.5 5.5-5.5z"/><path d="M18 14.5c.2 1.6.6 2 2.2 2.2-1.6.2-2 .6-2.2 2.2-.2-1.6-.6-2-2.2-2.2 1.6-.2 2-.6 2.2-2.2z"/>'),
  screener: line('<path d="M12 3 5 6v5c0 4 3 6.6 7 8 4-1.4 7-4 7-8V6z"/><path d="m9 11.5 2 2 4-4"/>'),
  snooze: line('<path d="M20 14.2A8 8 0 1 1 9.8 4 6.4 6.4 0 0 0 20 14.2z"/>'),
  clock: line('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3.2 2"/>'),
  newspaper: line('<path d="M4 5h13v15H6a2 2 0 0 1-2-2z"/><path d="M17 8h3v10a2 2 0 0 1-2 2"/><path d="M7 8.5h6M7 12h6M7 15.5h4"/>'),
  receipt: line('<path d="M6 3h12v18l-2.2-1.4L13.6 21 12 19.6 10.4 21 8.2 19.6 6 21z"/><path d="M9 8h6M9 12h4"/>'),
  alarm: line('<circle cx="12" cy="13" r="7"/><path d="M12 9.5V13l2.5 1.8"/><path d="M5 4.2 2.7 6.6M19 4.2l2.3 2.4"/>'),

  // Customize / layout
  customize: line('<path d="M4 8h9M17 8h3"/><path d="M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2.3"/><circle cx="9" cy="16" r="2.3"/>'),
  lock: line('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
  unlock: line('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>'),
  shield: line('<path d="M12 3 5 6v5c0 4 3 6.6 7 8 4-1.4 7-4 7-8V6z"/>'),
  shieldCheck: line('<path d="M12 3 5 6v5c0 4 3 6.6 7 8 4-1.4 7-4 7-8V6z"/><path d="m9 11.5 2 2 4-4"/>'),
  shieldAlert: line('<path d="M12 3 5 6v5c0 4 3 6.6 7 8 4-1.4 7-4 7-8V6z"/><path d="M12 8.5v3.2"/><path d="M12 15h.01"/>'),

  // Compose / editor tools
  link: line('<path d="M9.5 14.5 14.5 9.5"/><path d="M11 6.5 12.5 5a4 4 0 0 1 5.7 5.7L16.5 12"/><path d="M13 17.5 11.5 19a4 4 0 0 1-5.7-5.7L7.5 12"/>'),
  image: line('<rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="10" r="1.8"/><path d="m4 17 5-5 3.5 3.5L16 12l4 4"/>'),
  clearFormat: line('<path d="M8 6h12M11 6l-3 13M6 19h6"/><path d="m16 14 5 5M21 14l-5 5"/>'),
  bulb: line('<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.8 10.6c.7.6 1.1 1.3 1.2 2.4h5.2c.1-1.1.5-1.8 1.2-2.4A6 6 0 0 0 12 3z"/>'),

  // Categories
  bell: line('<path d="M6 9a6 6 0 0 1 12 0c0 4.5 1.8 5.5 1.8 5.5H4.2S6 13.5 6 9z"/><path d="M10 18.5a2 2 0 0 0 4 0"/>'),
  chat: line('<path d="M5 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H9l-4 3.5V6a1 1 0 0 1 1-1z"/>'),
  tag: line('<path d="M3.5 11.5V5a1.5 1.5 0 0 1 1.5-1.5h6.5L20 12l-8 8z"/><circle cx="7.7" cy="7.7" r="1.3"/>'),
  calendar: line('<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/>'),

  // Settings tabs / actions
  workspaces: line('<path d="M3 7a2 2 0 0 1 2-2h3.5l2 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 11h18"/>'),
  bolt: line('<path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11.5H12z"/>'),
  palette: line('<path d="M12 3.2a8.8 8.8 0 1 0 0 17.6c1.4 0 1.9-1 1.9-1.9s-.7-1.1-.7-1.9.7-1.4 1.8-1.4h1.6a3 3 0 0 0 3-3c0-4.3-3.8-7.5-7.6-7.5z"/><circle cx="7.5" cy="11.5" r="1"/><circle cx="12" cy="8" r="1"/><circle cx="16" cy="11.5" r="1"/>'),
  keyboard: line('<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>'),
  mute: line('<path d="M4 9v6h4l5 4V5L8 9z"/><path d="m16.5 9.5 4 5M20.5 9.5l-4 5"/>'),
  reset: line('<path d="M3 5v5h5"/><path d="M3.5 10A8.5 8.5 0 1 1 4 14.5"/>'),
  inboxMove: line('<path d="M12 3v8m0 0 3-3m-3 3-3-3"/><path d="M3 13h4l2 3h6l2-3h4v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  star: line('<path d="M12 4.5 14 9.7l5.5.1-4.4 3.4 1.6 5.3L12 15.4 7.3 18.5l1.6-5.3-4.4-3.4 5.5-.1z"/>'),
};

/** Icon for a folder by its role, with a sensible fallback. */
export function folderIcon(role) {
  return icons[role] || icons.folder;
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
