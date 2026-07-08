"""Lightweight, execution-free threat assessment for mail attachments.

This is the *first* line of the sandbox feature: a cheap heuristic run while the
attachment list is built, so the UI can flag a file BEFORE the user clicks it and
offer to open it in the isolated WebAssembly sandbox instead of the OS. It never
executes anything - it only inspects the filename and the first bytes.

The deeper structural analysis (embedded scripts, launch actions, extracted
URLs, live "what is it trying to do" feed) happens later, inside the sealed wasm
sandbox in the frontend. Keep the two layers distinct: this one is fast and
conservative; the wasm one is thorough.
"""
from __future__ import annotations

# Extensions that can execute code / actions directly when opened.
DANGEROUS_EXTS = {
    "exe", "scr", "com", "pif", "bat", "cmd", "ps1", "psm1", "vbs", "vbe",
    "js", "jse", "wsf", "wsh", "hta", "jar", "msi", "msp", "cpl", "dll",
    "lnk", "reg", "gadget", "apk", "app", "deb", "dmg", "run", "bin", "sh",
    "scf", "inf", "ins", "isp", "job", "vb", "vbscript", "ws", "chm",
}
# Macro-enabled Office documents.
MACRO_EXTS = {"docm", "xlsm", "pptm", "dotm", "xltm", "potm", "xlam", "ppam", "sldm"}
# Extensions commonly used as the *decoy* first half of a double extension.
DECOY_EXTS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "rtf",
    "jpg", "jpeg", "png", "gif", "zip", "html", "htm", "mp3", "mp4", "invoice",
}
ARCHIVE_EXTS = {"zip", "rar", "7z", "gz", "tar", "tgz", "cab", "arj", "lzh", "iso", "img"}

# Magic-byte signatures -> a short human type + the extensions that legitimately
# carry that magic. If a file claims a different extension, it's a mismatch.
_MAGIC = [
    (b"MZ", "Windows executable", {"exe", "dll", "scr", "com", "cpl", "sys", "msi", "ocx"}),
    (b"\x7fELF", "Linux executable", {"so", "o", "bin", "elf", "run"}),
    (b"\xca\xfe\xba\xbe", "Java/Mach-O binary", {"class", "jar"}),
    (b"%PDF", "PDF document", {"pdf"}),
    (b"PK\x03\x04", "ZIP/OpenXML archive",
     {"zip", "docx", "xlsx", "pptx", "docm", "xlsm", "pptm", "jar", "apk", "odt",
      "ods", "odp", "epub", "kmz", "vsdx", "xpi"}),
    (b"\xd0\xcf\x11\xe0", "Legacy Office/OLE",
     {"doc", "xls", "ppt", "msi", "msg", "dot", "xlm"}),
    (b"Rar!", "RAR archive", {"rar"}),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive", {"7z"}),
    (b"\x1f\x8b", "GZIP archive", {"gz", "tgz", "gzip"}),
    (b"\x89PNG", "PNG image", {"png"}),
    (b"\xff\xd8\xff", "JPEG image", {"jpg", "jpeg", "jfif"}),
    (b"GIF8", "GIF image", {"gif"}),
    (b"{\\rtf", "Rich Text document", {"rtf", "doc"}),
]

# The right-to-left override and other bidi chars used to disguise extensions
# (e.g. "photo_gpj.exe" that renders as "photo_exe.jpg").
_BIDI_SPOOF = ("‮", "‭", "‫", "‪", "⁦", "⁧", "⁨")


def _exts(filename: str) -> list[str]:
    parts = [p for p in (filename or "").lower().split(".") if p != ""]
    return parts[1:] if len(parts) > 1 else []


def assess(filename: str, content_type: str, head: bytes | None) -> dict:
    """Return {risk, score, reasons, type_guess, mismatch}.

    ``head`` is the first bytes of the file (a few KB is plenty). ``risk`` is one
    of "high" / "medium" / "low" / "none".
    """
    reasons: list[str] = []
    score = 0
    name = filename or ""
    exts = _exts(name)
    last = exts[-1] if exts else ""

    # --- filename-disguise spoofing ---
    if any(ch in name for ch in _BIDI_SPOOF):
        reasons.append("Filename uses right-to-left override characters to disguise its real extension")
        score += 70

    # --- dangerous / macro extension ---
    if last in DANGEROUS_EXTS:
        reasons.append(f"Executable file type (.{last}) that can run code when opened")
        score += 60
    elif last in MACRO_EXTS:
        reasons.append(f"Macro-enabled Office document (.{last}) can run embedded VBA macros")
        score += 35
    elif last == "rtf":
        reasons.append("RTF documents can embed and auto-launch OLE objects")
        score += 12
    elif last in ARCHIVE_EXTS:
        reasons.append("Archive - its contents are not scanned until extracted")
        score += 8

    # --- double / decoy extension ---
    if len(exts) >= 2 and exts[-2] in DECOY_EXTS and last in (DANGEROUS_EXTS | MACRO_EXTS):
        reasons.append(
            f"Double extension (.{exts[-2]}.{last}) - disguised as a "
            f"{exts[-2].upper()} file but is actually a .{last}"
        )
        score += 30

    # --- magic-byte type detection + extension mismatch ---
    type_guess = ""
    mismatch = False
    h = bytes(head or b"")
    for sig, label, ok_exts in _MAGIC:
        if h.startswith(sig):
            type_guess = label
            if last and last not in ok_exts:
                mismatch = True
                reasons.append(
                    f"Content is a {label} but the name claims a .{last} file"
                )
                # An executable wearing a document name is the classic malware trick.
                score += 55 if sig in (b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe") else 20
            break

    # Executable magic regardless of a claimed extension we couldn't classify.
    if not type_guess and h[:2] == b"MZ":
        type_guess = "Windows executable"
        reasons.append("File begins with an executable (MZ) header")
        score += 55

    # Light content scan so a *content*-malicious document (a clean-looking name
    # + magic, but active code inside) still gets flagged before it's opened.
    # The deep structural analysis is the wasm sandbox; this is just enough to
    # decide whether to warn.
    if h.startswith(b"%PDF"):
        if b"/Launch" in h:
            reasons.append("PDF contains a /Launch action that can run an external program")
            score += 55
        if b"/JavaScript" in h or b"/JS" in h:
            reasons.append("PDF contains embedded JavaScript")
            score += 30
        if b"/OpenAction" in h or b"/AA" in h:
            reasons.append("PDF auto-runs an action when opened (/OpenAction)")
            score += 20
        if b"/EmbeddedFile" in h:
            reasons.append("PDF has an embedded file payload")
            score += 15
    elif h.startswith(b"PK\x03\x04") and (b"vbaProject.bin" in h or b"macroEnabled" in h):
        reasons.append("Office document carries executable VBA macros")
        score += 40
    elif h.startswith(b"\xd0\xcf\x11\xe0") and (b"VBA" in h or b"Macros" in h or b"_VBA_PROJECT" in h):
        reasons.append("Legacy Office document carries VBA macro streams")
        score += 40

    score = min(100, score)
    if score >= 55:
        risk = "high"
    elif score >= 22:
        risk = "medium"
    elif score > 0:
        risk = "low"
    else:
        risk = "none"

    return {
        "risk": risk,
        "score": score,
        "reasons": reasons,
        "type_guess": type_guess,
        "mismatch": mismatch,
    }
