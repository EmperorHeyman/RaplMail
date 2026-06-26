"""Extract searchable text from attachment bytes — no third-party deps.

Handles plain text, source code, CSV/JSON/XML, and the OOXML Office formats
(.docx / .xlsx / .pptx), which are just ZIP archives of XML. PDF and legacy
binary Office formats need a parser library and are skipped for now (returns "").
The extracted text is folded into the message's full-text-search index so a
search matches words that only appear inside an attachment.
"""

from __future__ import annotations

import io
import re
import zipfile

# Cap per attachment so a giant file can't bloat the FTS index or stall a fetch.
_MAX_CHARS = 40_000

_TEXT_EXTS = {
    "txt", "md", "markdown", "rst", "log", "csv", "tsv", "json", "yaml", "yml",
    "xml", "html", "htm", "ini", "cfg", "conf", "toml", "env",
    # source code
    "py", "js", "ts", "jsx", "tsx", "java", "c", "h", "cpp", "hpp", "cc", "cs",
    "go", "rs", "rb", "php", "swift", "kt", "scala", "sh", "bash", "zsh", "ps1",
    "sql", "r", "lua", "pl", "dart", "vue", "svelte", "css", "scss",
}
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="ignore")


def _ooxml_text(data: bytes) -> str:
    """Pull visible text out of a .docx/.xlsx/.pptx (ZIP of XML) archive."""
    parts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            # Word: the document body; Excel: shared strings; PowerPoint: each slide.
            wanted = [n for n in names if (
                n == "word/document.xml"
                or n == "xl/sharedStrings.xml"
                or (n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            )]
            for n in wanted:
                try:
                    xml = zf.read(n).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                # Insert spaces at tag boundaries so adjacent runs don't fuse.
                text = _TAG_RE.sub(" ", xml)
                parts.append(text)
                if sum(len(p) for p in parts) > _MAX_CHARS:
                    break
    except (zipfile.BadZipFile, OSError):
        return ""
    return " ".join(parts)


def extract_attachment_text(filename: str, content_type: str, data: bytes) -> str:
    """Best-effort searchable text from one attachment. Empty if unsupported."""
    if not data:
        return ""
    ext = _ext(filename)
    ctype = (content_type or "").lower()
    try:
        if ext in {"docx", "xlsx", "pptx"} or "openxmlformats" in ctype:
            text = _ooxml_text(data)
        elif ext in _TEXT_EXTS or ctype.startswith("text/") or ctype in (
            "application/json", "application/xml", "application/javascript",
        ):
            text = _decode(data)
            if ext in ("html", "htm") or ctype == "text/html":
                text = _TAG_RE.sub(" ", text)
        else:
            return ""  # pdf, images, binaries — not indexed (no parser dep)
    except Exception:
        return ""
    text = _WS_RE.sub(" ", text).strip()
    return text[:_MAX_CHARS]
