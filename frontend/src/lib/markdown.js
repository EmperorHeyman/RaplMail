// Tiny, dependency-free Markdown → inline-styled HTML for the composer.
// Not full CommonMark — covers the constructs people actually write in email
// (headings, bold/italic, inline + fenced code, links, lists, blockquotes,
// horizontal rules) and emits inline styles so it renders consistently in
// recipients' mail clients (which strip <style> blocks).

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Apply inline markdown to a line. Text is HTML-escaped first, then spans are
// wrapped — so a literal "<" in the source can't inject markup.
function inline(s) {
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g,
    (_m, c) => `<code style="background:#f0f0f0;padding:1px 4px;border-radius:4px;font-family:ui-monospace,Consolas,monospace">${c}</code>`);
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    (_m, txt, url) => `<a href="${url}">${txt}</a>`);
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>");
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  t = t.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
  return t;
}

const _BLOCK_START = /^(#{1,6}\s|>|\s*[-*+]\s|\s*\d+[.)]\s|```)/;

export function mdToHtml(src) {
  const lines = String(src || "").replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  let listType = null; // "ul" | "ol"
  const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };

  while (i < lines.length) {
    const ln = lines[i];

    if (/^```(\w*)\s*$/.test(ln)) {                       // fenced code block
      closeList();
      const buf = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;                                                // skip closing fence
      out.push(`<pre style="background:#f6f8fa;border:1px solid #e1e4e8;border-radius:8px;padding:12px 14px;overflow:auto;font-family:ui-monospace,Consolas,monospace"><code>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }
    const h = ln.match(/^(#{1,6})\s+(.*)$/);              // heading
    if (h) {
      closeList();
      const size = [22, 19, 17, 15, 14, 13][h[1].length - 1];
      out.push(`<div style="font-weight:700;font-size:${size}px;margin:14px 0 6px">${inline(h[2])}</div>`);
      i++; continue;
    }
    if (/^\s*([-*_])\1{2,}\s*$/.test(ln)) {               // horizontal rule
      closeList();
      out.push('<hr style="border:none;border-top:1px solid #ddd;margin:14px 0">');
      i++; continue;
    }
    if (/^>\s?/.test(ln)) {                               // blockquote
      closeList();
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, "")); i++; }
      out.push(`<blockquote style="margin:0 0 0 4px;padding-left:12px;border-left:3px solid #ccc;color:#666">${inline(buf.join("\n")).replace(/\n/g, "<br>")}</blockquote>`);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(ln)) {                        // unordered list
      if (listType !== "ul") { closeList(); out.push('<ul style="margin:6px 0;padding-left:22px">'); listType = "ul"; }
      out.push(`<li>${inline(ln.replace(/^\s*[-*+]\s+/, ""))}</li>`);
      i++; continue;
    }
    if (/^\s*\d+[.)]\s+/.test(ln)) {                      // ordered list
      if (listType !== "ol") { closeList(); out.push('<ol style="margin:6px 0;padding-left:22px">'); listType = "ol"; }
      out.push(`<li>${inline(ln.replace(/^\s*\d+[.)]\s+/, ""))}</li>`);
      i++; continue;
    }
    if (/^\s*$/.test(ln)) { closeList(); i++; continue; } // blank line

    closeList();                                          // paragraph
    const para = [ln];
    i++;
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !_BLOCK_START.test(lines[i])) { para.push(lines[i]); i++; }
    out.push(`<p style="margin:0 0 10px">${inline(para.join("\n")).replace(/\n/g, "<br>")}</p>`);
  }
  closeList();
  return out.join("\n");
}
