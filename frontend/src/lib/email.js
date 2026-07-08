// Shared helpers for rendering email HTML safely (used by Reader + Newsletter feed).
import { app } from "./store.svelte.js";

const TRACKER_RE = /(pixel|beacon|\/open\b|\/wf\/open|webpixel|spacer|1x1|\/email\/open|\/track|\/e\/o\/|sentdate=|corid=|openrate|\/imp\b)/i;

export function escapeHtml(s) {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

/** Strip tracking pixels / suspicious images; keep legitimate ones. */
export function sanitizeTrackers(html, block = true) {
  if (!block || !html) return { html: html || "", blocked: 0, urls: [] };
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const urls = [];
    for (const img of doc.querySelectorAll("img")) {
      const src = img.getAttribute("src") || "";
      if (!src || src.startsWith("data:") || src.startsWith("cid:")) continue;
      const w = parseInt(img.getAttribute("width") || "0", 10);
      const h = parseInt(img.getAttribute("height") || "0", 10);
      const style = (img.getAttribute("style") || "").toLowerCase();
      const tiny = (w > 0 && w <= 2) || (h > 0 && h <= 2) || /(?:width|height)\s*:\s*[0-2]px/.test(style);
      if (tiny || TRACKER_RE.test(src)) {
        img.removeAttribute("src");
        img.setAttribute("style", style + ";display:none");
        urls.push(src);
      }
    }
    return { html: doc.body.innerHTML, blocked: urls.length, urls };
  } catch {
    return { html, blocked: 0, urls: [] };
  }
}

// Split a reply into the new text vs. the quoted history below it, so the reader
// can hide the nested "On … wrote: >>>" garbage behind a toggle.
const _QUOTE_MARKERS = [
  /<blockquote/i,
  /<div[^>]+class=["'][^"']*gmail_quote/i,
  /<div[^>]+(?:id|class)=["'][^"']*(?:divRplyFwdMsg|appendonsend|moz-cite|yahoo_quoted)/i,
  /-----+\s*(?:Original Message|Původní zpráva|Forwarded message)\s*-----+/i,
  /________________________________+/,
  /(?:^|>)\s*On\b.{3,120}?\bwrote:\s*(?:<|$)/i,
  /(?:^|>)\s*[Dd]ne\b.{3,120}?\bnapsal(?:\(a\))?:\s*(?:<|$)/i,
];
export function splitQuoted(html) {
  if (!html) return { main: "", recent: "", earlier: "" };
  let idx = -1;
  for (const re of _QUOTE_MARKERS) {
    const m = re.exec(html);
    if (m && (idx === -1 || m.index < idx)) idx = m.index;
  }
  if (idx < 0) return { main: html, recent: "", earlier: "" };
  // Only collapse if there's meaningful NEW (visible) text above the quote. A
  // forward has ~no new text above the original, so collapsing would hide the
  // whole message - measure stripped text, not the raw HTML offset (tags inflate it).
  const visibleAbove = html.slice(0, idx).replace(/<[^>]+>/g, "").replace(/&[a-z#0-9]+;/gi, " ").trim();
  if (visibleAbove.length < 25) return { main: html, recent: "", earlier: "" };
  // main      = the new text the sender just wrote
  // recent    = the single most-recent quoted reply (shown by default)
  // earlier   = the deeper/older history below it (revealed on demand)
  const main = html.slice(0, idx);
  const { recent, earlier } = _splitQuoteLevels(html.slice(idx));
  return { main, recent, earlier };
}

// Within the quoted region, peel off the OLDER history so the reader shows only
// the most-recent reply by default. Reply clients nest each older message in
// another <blockquote>, so a blockquote that sits inside another blockquote is
// older history - we lift those out into `earlier`. Clients that don't nest
// (Outlook divs, plain "-----Original Message-----") degrade gracefully: the
// whole quote is treated as `recent` and no "show earlier" button appears.
function _splitQuoteLevels(quotedHtml) {
  try {
    const doc = new DOMParser().parseFromString(quotedHtml, "text/html");
    const nested = [...doc.querySelectorAll("blockquote")].filter((bq) => {
      const anc = bq.parentElement?.closest("blockquote");
      return anc && !anc.parentElement?.closest("blockquote"); // exactly nesting depth 2
    });
    if (!nested.length) return { recent: quotedHtml, earlier: "" };
    let earlier = "";
    for (const bq of nested) { earlier += bq.outerHTML; bq.remove(); }
    return { recent: doc.body.innerHTML, earlier };
  } catch {
    return { recent: quotedHtml, earlier: "" };
  }
}

// --- code-block syntax highlighting ---------------------------------------
// Language-agnostic: highlights comments, strings, numbers, and a broad set of
// keywords common across C-family/Python/JS/SQL/shell. Good enough to make
// pasted code in an email readable without bundling a multi-MB highlighter.
const HL_KEYWORDS = new Set((
  "abstract and arguments as assert async await base bool boolean break byte case catch " +
  "char class const continue debugger def default del delete do double elif else end enum " +
  "except export extends false final finally float fn for foreach from func function global " +
  "go goto if impl implements import in instanceof int interface is lambda let long match mod " +
  "module mut namespace native new nil none not null object operator or override package params " +
  "pass private protected pub public raise readonly rec ref return select self short signed " +
  "sizeof static str string struct super switch synchronized template this throw throws trait " +
  "true try type typedef typeof union unsigned use using val var virtual void volatile when " +
  "where while with yield"
).split(" "));
const HL_LITERALS = new Set(["true", "false", "null", "nil", "none", "undefined", "nan", "self", "this"]);

function decodeEntities(s) {
  return (s || "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
    .replace(/&#0?39;|&apos;/g, "'").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
}

function highlightSource(raw) {
  const TOKEN = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|--[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d[\d._]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([A-Za-z_$][\w$]*)/g;
  let out = "", last = 0, m;
  while ((m = TOKEN.exec(raw)) !== null) {
    out += escapeHtml(raw.slice(last, m.index));
    if (m[1]) out += `<span class="hl-c">${escapeHtml(m[1])}</span>`;
    else if (m[2]) out += `<span class="hl-s">${escapeHtml(m[2])}</span>`;
    else if (m[3]) out += `<span class="hl-n">${escapeHtml(m[3])}</span>`;
    else {
      const w = m[4];
      const lw = w.toLowerCase();
      if (HL_LITERALS.has(lw)) out += `<span class="hl-l">${escapeHtml(w)}</span>`;
      else if (HL_KEYWORDS.has(w)) out += `<span class="hl-k">${escapeHtml(w)}</span>`;
      else out += escapeHtml(w);
    }
    last = m.index + m[0].length;
  }
  out += escapeHtml(raw.slice(last));
  return out;
}

// --- git patch / unified-diff detection + rendering ------------------------
/** Heuristic: does this text look like a unified diff / git patch? */
function looksLikeDiff(text) {
  if (/^diff --git /m.test(text)) return true;
  if (!/^@@ -\d+(?:,\d+)? \+\d+/m.test(text)) return false;  // needs a real hunk header
  return /^\+/m.test(text) && /^-/m.test(text);
}
/** Color-code each line of a unified diff (added/removed/hunk/meta). */
function renderDiff(text) {
  return text.split("\n").map((ln) => {
    let cls = "d-ctx";
    if (/^(diff --git |index |new file|deleted file|similarity |rename |old mode|new mode)/.test(ln)) cls = "d-meta";
    else if (ln.startsWith("@@")) cls = "d-hunk";
    else if (/^(\+\+\+|---) /.test(ln)) cls = "d-file";
    else if (ln.startsWith("+")) cls = "d-add";
    else if (ln.startsWith("-")) cls = "d-del";
    return `<span class="d-line ${cls}">${escapeHtml(ln) || "&nbsp;"}</span>`;
  }).join("\n");
}

/** Re-render every <pre> code block in an email with syntax highlighting, or as
 *  a color-coded diff when the block is a git patch / unified diff. */
export function highlightCodeBlocks(html) {
  if (!html || !/<pre[\s>]/i.test(html)) return html;
  return html.replace(/<pre\b[^>]*>([\s\S]*?)<\/pre>/gi, (_full, inner) => {
    const codeMatch = inner.match(/<code\b[^>]*>([\s\S]*?)<\/code>/i);
    const body = codeMatch ? codeMatch[1] : inner;
    const text = decodeEntities(body.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, ""));
    if (looksLikeDiff(text)) return `<pre class="rapl-code rapl-diff">${renderDiff(text)}</pre>`;
    const hl = highlightSource(text);
    const inner2 = codeMatch ? `<code>${hl}</code>` : hl;
    return `<pre class="rapl-code">${inner2}</pre>`;
  });
}

/** Is a CSS color string (hex or rgb()) dark enough to need light text? */
export function isDarkColor(c) {
  c = (c || "").trim();
  let r, g, b;
  if (c[0] === "#") {
    let h = c.slice(1);
    if (h.length === 3) h = h.split("").map((x) => x + x).join("");
    r = parseInt(h.slice(0, 2), 16); g = parseInt(h.slice(2, 4), 16); b = parseInt(h.slice(4, 6), 16);
  } else {
    const m = c.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    if (!m) return true;
    r = +m[1]; g = +m[2]; b = +m[3];
  }
  if ([r, g, b].some((v) => Number.isNaN(v))) return true;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.5;
}

/** Relative luminance 0..1 of a CSS color (NaN if unparseable). */
function _lum(c) {
  c = (c || "").trim().toLowerCase();
  if (c === "white" || c === "#fff" || c === "#ffffff") return 1;
  let r, g, b;
  if (c[0] === "#") {
    let h = c.slice(1);
    if (h.length === 3) h = h.split("").map((x) => x + x).join("");
    r = parseInt(h.slice(0, 2), 16); g = parseInt(h.slice(2, 4), 16); b = parseInt(h.slice(4, 6), 16);
  } else {
    const m = c.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    if (!m) return NaN;
    r = +m[1]; g = +m[2]; b = +m[3];
  }
  if ([r, g, b].some((v) => Number.isNaN(v))) return NaN;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

/**
 * Force a dark reading surface for ANY email: rewrite near-white backgrounds to
 * the theme's dark background and dark text to light, while leaving saturated
 * brand colors alone. This is the "Dark" email mode - guarantees no white pane.
 */
function recolorForDark(html, bg, text) {
  const LIGHT = 0.82;   // luminance above this = "basically white/very light"
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const el of doc.querySelectorAll("[bgcolor]")) {
      const l = _lum(el.getAttribute("bgcolor"));
      if (!Number.isNaN(l) && l >= LIGHT) el.setAttribute("bgcolor", bg);
    }
    for (const el of doc.querySelectorAll("font[color]")) {
      if (isDarkColor(el.getAttribute("color"))) el.removeAttribute("color");
    }
    for (const el of doc.querySelectorAll("[style]")) {
      let style = el.getAttribute("style");
      // Darken near-white backgrounds.
      style = style.replace(/background(-color)?\s*:\s*([^;]+)/gi, (full, _suf, val) => {
        const l = _lum(val.trim());
        return (!Number.isNaN(l) && l >= LIGHT) ? `background${_suf || ""}:${bg}` : full;
      });
      // Recolor dark text to light (won't touch background-color / border-color).
      style = style.replace(/(^|;)(\s*)color\s*:\s*([^;]+)/gi,
        (full, sep, ws, val) => (isDarkColor(val) ? `${sep}${ws}color:${text}` : full));
      el.setAttribute("style", style);
    }
    return doc.body.innerHTML;
  } catch { return html; }
}

// The background color declared directly on an element (bgcolor attr or inline
// style), "" if none.
function _bgOf(el) {
  const bgc = el.getAttribute ? el.getAttribute("bgcolor") : "";
  if (bgc) return bgc.trim();
  const style = (el.getAttribute && el.getAttribute("style")) || "";
  const m = style.match(/background(?:-color)?\s*:\s*([^;]+)/i);
  return m ? m[1].trim() : "";
}
// Does this element (or any ancestor) paint itself a dark background? If so, its
// light text is intentional (light-on-dark) and must be left alone.
function _onDarkBg(el) {
  let n = el;
  while (n && n.getAttribute) {
    const l = _lum(_bgOf(n));
    if (!Number.isNaN(l) && l < 0.5) return true;
    n = n.parentElement;
  }
  return false;
}

/**
 * White-on-white guard for the LIGHT reading pane: emails authored for a dark
 * background (light/near-white text) render invisibly on our white pane. Recolor
 * only near-white text to the pane's dark text color, and only when the element
 * isn't sitting on its own dark background (so light-on-dark brand blocks stay
 * exactly as designed). Never runs in "show original" mode.
 */
function fixInvisibleText(html, paneText) {
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const el of doc.querySelectorAll("font[color]")) {
      const l = _lum(el.getAttribute("color"));
      if (!Number.isNaN(l) && l >= 0.75 && !_onDarkBg(el)) el.removeAttribute("color");
    }
    for (const el of doc.querySelectorAll("[style]")) {
      const style = el.getAttribute("style");
      const next = style.replace(/(^|;)(\s*)color\s*:\s*([^;]+)/gi, (full, sep, ws, val) => {
        const l = _lum(val.trim());
        return (!Number.isNaN(l) && l >= 0.75 && !_onDarkBg(el)) ? `${sep}${ws}color:${paneText}` : full;
      });
      if (next !== style) el.setAttribute("style", next);
    }
    return doc.body.innerHTML;
  } catch { return html; }
}

const _URL_RE = /\b(https?:\/\/[^\s<>"')]+)/gi;
/** Turn a plain-text body into safe HTML with clickable links. */
export function autoLink(text) {
  return escapeHtml(text || "").replace(_URL_RE, (u) => `<a href="${u}" target="_blank" rel="noreferrer">${u}</a>`);
}

// --- link hygiene: strip tracking params + unwrap redirect wrappers ----------
// Query-param families that only exist to track you (Google/Meta/ESP analytics).
const _TRACK_PREFIX = /^(utm_|__?hs|hsenc|hsmi|mc_|pk_|mtm_|matomo_|piwik_|vero_|oly_|ns_|s_|ga_|_ga|elq|trk_|sc_)/i;
const _TRACK_EXACT = new Set([
  "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "twclid",
  "igshid", "mc_eid", "mc_cid", "spm", "cmpid", "icid", "mkt_tok", "_openstat",
  "oly_anon_id", "oly_enc_id", "vero_id", "wickedid", "ref_src", "ref_url",
  "action_object_map", "action_type_map", "action_ref_map",
]);
// Hosts that wrap the real destination in a decodable query param.
const _REDIR_HOSTS = /(^|\.)(google\.[a-z.]+|l\.facebook\.com|lm\.facebook\.com|out\.reddit\.com|href\.li|safelinks\.protection\.outlook\.com)$/i;
const _REDIR_PARAMS = ["url", "q", "u", "target", "dest", "destination", "redirect", "redirect_uri", "to"];

/** Clean a single URL: unwrap a known redirect wrapper, then drop tracking params. */
export function cleanUrl(raw) {
  try {
    let u = new URL(raw);
    if (_REDIR_HOSTS.test(u.hostname)) {
      for (const p of _REDIR_PARAMS) {
        const v = u.searchParams.get(p);
        if (v && /^https?:\/\//i.test(v)) { try { u = new URL(v); } catch {} break; }
      }
    }
    for (const key of [...u.searchParams.keys()]) {
      if (_TRACK_EXACT.has(key.toLowerCase()) || _TRACK_PREFIX.test(key)) u.searchParams.delete(key);
    }
    return u.toString().replace(/\?(#|$)/, "$1");   // tidy a now-empty query string
  } catch { return raw; }
}

/**
 * Rewrite every <a href> in an email to its cleaned/unwrapped destination and
 * expose that clean URL as a tooltip, so a click never leaks utm_/fbclid/gclid
 * and the real destination is visible on hover (RaplMail's privacy-first brand).
 */
export function cleanLinks(html) {
  if (!html?.includes("href")) return html;
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const a of doc.querySelectorAll("a[href]")) {
      const href = a.getAttribute("href") || "";
      if (!/^https?:\/\//i.test(href)) continue;
      const clean = cleanUrl(href);
      if (clean !== href) a.setAttribute("href", clean);
      a.setAttribute("title", clean);
    }
    return doc.body.innerHTML;
  } catch { return html; }
}

function themeVar(name, fallback) {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch { return fallback; }
}
function currentBg() { return themeVar("--bg", "#0e1014"); }

const _PLAIN_BG = /^(?:#fff(?:fff)?|#ffffffff|white|transparent|none|inherit|initial|unset)$/i;

/**
 * Does this email bring its own visual theme (background colors / background
 * images on a wrapper)? Branded newsletters and HTML-designed mail do; a plain
 * typed reply does not. We use this to decide whether dark-mode adaptation is
 * safe - we only re-theme PLAIN mail and never touch a sender's own design.
 */
function emailHasOwnTheme(html) {
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const el of doc.querySelectorAll("[bgcolor],[background],[style]")) {
      if (el.getAttribute("background")) return true; // background-image attribute
      const bg = (el.getAttribute("bgcolor") || "").trim();
      if (bg && !_PLAIN_BG.test(bg)) return true;
      const style = (el.getAttribute("style") || "").toLowerCase();
      const m = style.match(/background(?:-color)?\s*:\s*([^;]+)/);
      if (m) {
        const v = m[1].trim();
        if (v && !_PLAIN_BG.test(v)) return true; // a real color, gradient, or url()
      }
    }
    return false;
  } catch { return false; }
}

/**
 * Recolor only the DARK inline text colors in a plain email to a light theme
 * color, so dark-on-dark text stays readable. Light/colored text and everything
 * else (links, borders, images) is left untouched.
 */
function darkenPlainBody(html, lightText) {
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const el of doc.querySelectorAll("font[color]")) {
      if (isDarkColor(el.getAttribute("color"))) el.removeAttribute("color");
    }
    for (const el of doc.querySelectorAll("[style]")) {
      const style = el.getAttribute("style");
      // `(^|;)\s*color` deliberately won't match `background-color` / `border-color`.
      const next = style.replace(/(^|;)(\s*)color\s*:\s*([^;]+)/gi,
        (full, sep, ws, val) => (isDarkColor(val) ? `${sep}${ws}color:${lightText}` : full));
      if (next !== style) el.setAttribute("style", next);
    }
    return doc.body.innerHTML;
  } catch { return html; }
}

/**
 * Wrap a message body in a sandboxed HTML document for the iframe.
 *
 * Emails are authored for a white background. In a dark theme, with "Adapt email
 * colors" on, we *smart-adapt*: PLAIN mail (no styling of its own) is rendered on
 * a true dark pane with light text - easy on the eyes - while branded / custom-
 * styled mail is left exactly as the sender designed it on a white reading pane,
 * so its colors are never mangled. No whole-document inversion.
 */
export function emailDoc(bodyHtml, { raw = false } = {}) {
  // raw = per-message "show original" toggle: exact sender design, white pane.
  // Otherwise the email appearance mode decides:
  //   "original" - as the sender designed it (white pane)
  //   "adaptive" - dark pane for plain mail, leave branded mail on white (default)
  //   "dark"     - force a dark pane for ALL mail (no white, ever)
  const s = app?.settings || {};
  let mode = s.emailTheme;
  if (!mode) mode = s.alwaysOriginalHtml ? "original" : (s.emailAdaptColors === false ? "original" : "adaptive");
  if (raw) mode = "original";
  const themeIsDark = isDarkColor(currentBg());
  const force = mode === "dark" && themeIsDark;                       // recolor everything
  const dark = force || (mode === "adaptive" && themeIsDark && !emailHasOwnTheme(bodyHtml));
  const original = mode === "original";
  // Opt-in: let the user's custom CSS also style email bodies (default off - emails untouched).
  const userCss = !original && app?.settings?.customCssInEmails ? (app?.settings?.customCss || "") : "";
  // Syntax-highlight code blocks (default ON) - developer-friendly reading of pasted code.
  const highlight = !original && app?.settings?.highlightCode !== false;
  let body = highlight ? highlightCodeBlocks(bodyHtml) : bodyHtml;
  // Link hygiene (privacy, default on): strip utm_/fbclid/gclid & unwrap redirect
  // wrappers so a click can't leak tracking params. "Show original" keeps links.
  if (!original && s.stripTrackingParams !== false) body = cleanLinks(body);

  // Reading-width cap (Appearance → Reading width): center the body at a
  // comfortable column on wide screens so long lines don't stretch edge-to-edge.
  // 0 = full width. `margin: 16px auto` centers; the max-width is a soft cap so
  // fixed-width branded tables (usually <=600px) still sit centered.
  const maxW = Number(app?.settings?.emailMaxWidth ?? 0);
  const bodyBox = maxW > 0 ? `margin:16px auto;max-width:${maxW}px;` : "margin:16px;";

  let pageCss;
  if (dark) {
    const bg = currentBg();
    const text = themeVar("--text", "#e6e6e6");
    const muted = themeVar("--muted", "#9aa0a6");
    const border = themeVar("--border", "#33363d");
    const link = themeVar("--accent", "#5b8def");
    // "Dark" mode forcibly recolors near-white backgrounds too; "adaptive" only
    // recolors dark text on the (already plain) body.
    body = force ? recolorForDark(body, bg, text) : darkenPlainBody(body, text);
    pageCss =
      `html{background:${bg};}` +
      `body{font:14px/1.6 system-ui,sans-serif;color:${text};background:${bg};${bodyBox}}` +
      `a{color:${link};} img{max-width:100%;height:auto;}` +
      `blockquote{border-left:3px solid ${border};margin:0;padding-left:12px;color:${muted};}`;
  } else {
    // Default (non-"original") light pane: guard against white-on-white - recolor
    // near-white text that isn't on its own dark background so it stays readable.
    if (!original) body = fixInvisibleText(body, "#1a1a1a");
    pageCss =
      `html{background:#fff;}` +
      `body{font:14px/1.6 system-ui,sans-serif;color:#1a1a1a;background:#fff;${bodyBox}}` +
      `a{color:#1a56db;} img{max-width:100%;height:auto;}` +
      `blockquote{border-left:3px solid #d0d5dd;margin:0;padding-left:12px;color:#667085;}`;
  }
  const codeCss = highlight
    ? `pre.rapl-code{background:#f6f8fa;border:1px solid #e1e4e8;border-radius:8px;padding:12px 14px;overflow:auto;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
       pre.rapl-code .hl-k{color:#cf222e;font-weight:600;} pre.rapl-code .hl-s{color:#0a3069;}
       pre.rapl-code .hl-c{color:#6e7781;font-style:italic;} pre.rapl-code .hl-n{color:#0550ae;}
       pre.rapl-code .hl-l{color:#8250df;}
       pre.rapl-diff .d-line{display:block;white-space:pre-wrap;word-break:break-word;}
       pre.rapl-diff .d-add{background:#e6ffec;color:#116329;} pre.rapl-diff .d-del{background:#ffebe9;color:#a40e26;}
       pre.rapl-diff .d-hunk{color:#0550ae;background:#f1f8ff;} pre.rapl-diff .d-file{color:#6e7781;font-weight:600;} pre.rapl-diff .d-meta{color:#6e7781;}`
    : "";
  return `<!doctype html><html><head><meta charset="utf-8">
    <style>${pageCss}
    ${codeCss}
    ${userCss}</style>
    </head><body>${body}</body></html>`;
}
