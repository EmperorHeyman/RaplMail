"""Tier-2 deep attachment analysis (extraction + de-obfuscation, never execution).

Static analysis only tells you a macro *exists*; a real dropper hides its
`Shell("powershell ...")` behind `Chr()`/Base64 concatenation so a plain keyword
scan sees nothing. This module goes a level deeper WITHOUT ever running the file:

- **Office macros** are extracted and de-obfuscated with `oletools` (olevba) - the
  same engine most mail-security tools use. It decodes obfuscated strings, so the
  hidden download-and-run intent, auto-exec triggers (AutoOpen/Document_Open) and
  IOCs (URLs, dropped filenames) are revealed as readable text.
- **PDF object streams are decompressed** (FlateDecode/zlib) and re-scanned, so a
  malicious PDF that hides `/JS` / `/Launch` inside a compressed stream can't slip
  past the raw-byte scan.

Everything here is pure parsing. No macro is executed, no code is run; we only
read and decode bytes, then report what the file *would* do.
"""
from __future__ import annotations

import re
import zlib

_PDF_TOKENS = [
    (b"/Launch", "launch", "Runs an external program (/Launch)"),
    (b"/JavaScript", "script", "Embedded JavaScript"),
    (b"/JS", "script", "Embedded JavaScript"),
    (b"/OpenAction", "script", "Auto-runs an action when opened (/OpenAction)"),
    (b"/AA", "script", "Event-triggered actions (/AA)"),
    (b"/EmbeddedFile", "embed", "Embedded file payload"),
    (b"/SubmitForm", "network", "Submits form data to a remote server"),
    (b"/URI", "network", "Opens a remote URL"),
]
_URL_RE = re.compile(rb"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{4,300}")


def deep_analyze(filename: str, data: bytes) -> dict:
    """Return a structured deep report. Safe on any bytes; never raises."""
    report: dict = {
        "ran": True,
        "office": None,
        "pdf": None,
        "summary": [],   # human-readable headline findings
        "score": 0,
    }
    data = bytes(data or b"")
    try:
        office = _analyze_office(filename or "file", data)
        if office:
            report["office"] = office
            report["score"] += office.get("score", 0)
            report["summary"] += office.get("summary", [])
    except Exception as e:  # never let analysis break the request
        report["office"] = {"error": str(e)[:200]}

    if data[:5].startswith(b"%PDF"):
        try:
            pdf = _analyze_pdf(data)
            report["pdf"] = pdf
            report["score"] += pdf.get("score", 0)
            report["summary"] += pdf.get("summary", [])
        except Exception as e:
            report["pdf"] = {"error": str(e)[:200]}

    report["score"] = min(100, report["score"])
    return report


# ---------------------------------------------------------------- Office ----

def _analyze_office(filename: str, data: bytes) -> "dict | None":
    """Extract + de-obfuscate VBA macros with olevba. Returns None if the file
    isn't an Office document / carries no macros."""
    # Cheap gate so we don't spin olevba up on every file type: OLE (legacy
    # .doc/.xls), OOXML/zip (.docm/.xlsm), or an attached VBA source module.
    head = data[:8]
    is_ole = head.startswith(b"\xd0\xcf\x11\xe0")
    is_zip = head.startswith(b"PK\x03\x04")
    name = (filename or "").lower()
    is_vba_src = name.endswith((".vba", ".bas", ".cls", ".frm"))
    if not (is_ole or is_zip or is_vba_src):
        return None

    from oletools.olevba import VBA_Parser

    vp = VBA_Parser(filename, data=data)
    try:
        if not vp.detect_vba_macros():
            return {"has_macros": False, "summary": [], "score": 0}

        autoexec: list[str] = []
        suspicious: list[dict] = []
        iocs: list[dict] = []
        decoded: list[str] = []
        seen = set()
        for kw_type, keyword, description in vp.analyze_macros(show_decoded_strings=True, deobfuscate=True):
            key = (kw_type, str(keyword))
            if key in seen:
                continue
            seen.add(key)
            k = (kw_type or "").lower()
            kw = str(keyword)
            if "autoexec" in k:
                autoexec.append(kw)
            elif "ioc" in k:
                iocs.append({"value": kw[:300], "kind": description})
            elif "suspicious" in k:
                suspicious.append({"keyword": kw, "description": description})
            elif "base64" in k or "hex" in k or "dridex" in k or "obfusc" in k or "decoded" in k:
                if kw.strip():
                    decoded.append(kw[:300])

        # Grab a readable, de-obfuscated snippet of the macro source.
        try:
            revealed = vp.reveal()
        except Exception:
            revealed = ""
        revealed = (revealed or "")[:4000]

        # Score: macros that auto-run AND do something suspicious are the danger.
        score = 25
        if autoexec:
            score += 20
        if suspicious:
            score += 35
        if any(s["keyword"].lower() in ("shell", "wscript.shell", "createobject", "run")
               for s in suspicious):
            score += 20

        summary = [f"Document contains {'auto-running ' if autoexec else ''}VBA macros"]
        if autoexec:
            summary.append("Auto-executes on open: " + ", ".join(sorted(set(autoexec))[:4]))
        if any(i["kind"] == "URL" for i in iocs):
            summary.append("Macro references remote URLs")

        return {
            "has_macros": True,
            "autoexec": sorted(set(autoexec)),
            "suspicious": suspicious[:30],
            "iocs": iocs[:30],
            "decoded": decoded[:30],
            "source": revealed,
            "score": min(100, score),
            "summary": summary,
        }
    finally:
        try:
            vp.close()
        except Exception:
            pass


# ------------------------------------------------------------------- PDF ----

def _analyze_pdf(data: bytes) -> dict:
    """Decompress FlateDecode streams and re-scan for active content that the
    raw-byte scan can't see through compression."""
    hits: list[str] = []
    urls: set[str] = set()
    streams = 0
    decompressed_bytes = 0
    TOTAL_CAP = 48 * 1024 * 1024  # anti decompression-bomb: stop inflating past this

    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        streams += 1
        raw = m.group(1)
        out = _inflate(raw)
        if out is None:
            continue
        decompressed_bytes += len(out)
        if decompressed_bytes > TOTAL_CAP:
            break
        for token, cat, desc in _PDF_TOKENS:
            if token in out and desc not in hits:
                hits.append(desc)
        for u in _URL_RE.findall(out)[:20]:
            urls.add(u.decode("latin-1", "ignore")[:300])
        if streams > 400:  # bound the work
            break

    score = 0
    summary: list[str] = []
    if hits:
        # Active content hidden inside a compressed stream is a strong signal.
        score = 60
        summary.append("Active content hidden inside compressed PDF streams: " + ", ".join(hits[:4]))
    if urls:
        score = max(score, 20)
        summary.append(f"{len(urls)} URL(s) embedded in PDF streams")

    return {
        "streams": streams,
        "decompressed_bytes": decompressed_bytes,
        "hits": hits,
        "urls": sorted(urls)[:30],
        "score": score,
        "summary": summary,
    }


def _inflate(raw: bytes, max_out: int = 8 * 1024 * 1024) -> "bytes | None":
    # Cap output per stream so a tiny stream can't inflate to gigabytes (a
    # decompression bomb). We only need enough to scan for tokens/URLs anyway.
    for wbits in (15, -15):  # zlib-wrapped, then raw deflate
        try:
            return zlib.decompressobj(wbits).decompress(raw, max_out)
        except Exception:
            continue
    return None
