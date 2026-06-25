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
  return `<!doctype html><html><head><meta charset="utf-8">
    <style>html{background:#fff;}
    body{font:14px/1.6 system-ui,sans-serif;color:#1a1a1a;background:#fff;margin:16px;}
    a{color:#1a56db;} img{max-width:100%;height:auto;} blockquote{border-left:3px solid #d0d5dd;margin:0;padding-left:12px;color:#667085;}
    ${filter}
    ${userCss}</style>
    </head><body>${bodyHtml}</body></html>`;
}
