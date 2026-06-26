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
  if (!html) return { main: "", quoted: "" };
  let idx = -1;
  for (const re of _QUOTE_MARKERS) {
    const m = re.exec(html);
    if (m && (idx === -1 || m.index < idx)) idx = m.index;
  }
  // Need a meaningful amount of "new" text above the quote to bother collapsing.
  if (idx < 40) return { main: html, quoted: "" };
  return { main: html.slice(0, idx), quoted: html.slice(idx) };
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

/** Re-render every <pre> code block in an email with syntax highlighting. */
export function highlightCodeBlocks(html) {
  if (!html || !/<pre[\s>]/i.test(html)) return html;
  return html.replace(/<pre\b[^>]*>([\s\S]*?)<\/pre>/gi, (_full, inner) => {
    const codeMatch = inner.match(/<code\b[^>]*>([\s\S]*?)<\/code>/i);
    const body = codeMatch ? codeMatch[1] : inner;
    const text = decodeEntities(body.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, ""));
    const hl = highlightSource(text);
    return `<pre class="rapl-code">${codeMatch ? `<code>${hl}</code>` : hl}</pre>`;
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

function currentBg() {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#0e1014";
  } catch { return "#0e1014"; }
}

/**
 * Wrap a message body in a sandboxed HTML document for the iframe.
 * Emails are authored for a white background, so we always render on a light
 * pane (guaranteeing readable text). When the app theme is dark AND the user's
 * "Adapt email colors" setting is on, we invert the whole document to match the
 * dark UI, re-inverting media so photos/logos keep their real colors.
 */
export function emailDoc(bodyHtml, { raw = false } = {}) {
  // raw = show the email exactly as the sender designed it: no theme adaptation,
  // no injected custom CSS (just the white pane it was authored for).
  const adapt = !raw && app?.settings?.emailAdaptColors !== false; // default ON
  const invert = adapt && isDarkColor(currentBg());
  const filter = invert
    ? `html{filter:invert(1) hue-rotate(180deg);}
       img,picture,video,svg,canvas,iframe,embed,object,[style*="background-image"],[background]{filter:invert(1) hue-rotate(180deg);}`
    : "";
  // Opt-in: let the user's custom CSS also style email bodies (default off — emails untouched).
  const userCss = !raw && app?.settings?.customCssInEmails ? (app?.settings?.customCss || "") : "";
  // Syntax-highlight code blocks (default ON) — developer-friendly reading of pasted code.
  const highlight = !raw && app?.settings?.highlightCode !== false;
  const body = highlight ? highlightCodeBlocks(bodyHtml) : bodyHtml;
  const codeCss = highlight
    ? `pre.rapl-code{background:#f6f8fa;border:1px solid #e1e4e8;border-radius:8px;padding:12px 14px;overflow:auto;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
       pre.rapl-code .hl-k{color:#cf222e;font-weight:600;} pre.rapl-code .hl-s{color:#0a3069;}
       pre.rapl-code .hl-c{color:#6e7781;font-style:italic;} pre.rapl-code .hl-n{color:#0550ae;}
       pre.rapl-code .hl-l{color:#8250df;}`
    : "";
  return `<!doctype html><html><head><meta charset="utf-8">
    <style>html{background:#fff;}
    body{font:14px/1.6 system-ui,sans-serif;color:#1a1a1a;background:#fff;margin:16px;}
    a{color:#1a56db;} img{max-width:100%;height:auto;} blockquote{border-left:3px solid #d0d5dd;margin:0;padding-left:12px;color:#667085;}
    ${codeCss}
    ${filter}
    ${userCss}</style>
    </head><body>${body}</body></html>`;
}
