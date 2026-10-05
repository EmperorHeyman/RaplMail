"""Find the sign-in / verification code in a mail ("Security code: 482931").

Used to put a one-click copy button on such mail and, when one arrives, to
copy the code straight to the clipboard. A wrong guess is worse than none -
copying an order number over whatever you had on the clipboard - so this is
deliberately strict:

* the mail must be about signing in / verifying (an auth word in the subject
  or the opening text); "use code SAVE20 for 20% off" is not,
* the candidate must sit next to a code word ("code", "kód", "OTP", ...) or
  alone on its own line, the way these mails present it,
* dates, times, years, amounts, phone numbers, order numbers and anything
  inside a link or an address are never candidates,
* two equally good, different candidates means no answer.
"""

from __future__ import annotations

import html as _html
import re

# What the mail has to be about. Kept to sign-in / verification wording - a
# bare "code" is in every promo mail.
_AUTH_RE = re.compile(
    r"verif|ověř|over(?:ení|ovací)|sign[\s-]?in|signin|log[\s-]?in\b|login|přihl|prihl|"
    r"one[\s-]?time|jednoráz|jednoraz|\botp\b|\b2fa\b|two[\s-]?(?:factor|step)|dvoufáz|dvoufaz|"
    r"authenticat|autentiz|autentiz|security code|bezpečnostní kód|bezpecnostni kod|passcode|"
    r"access code|confirmation code|confirm your|potvrzovací|potvrzovaci|potvrzení|"
    r"steam guard|bestätigung|sicherheitscode|anmelde|vérification|verificación|"
    r"single[\s-]use code|login code|sign-in code|přístupový kód|pristupovy kod",
    re.IGNORECASE)

# Words a code sits next to.
_CODE_WORD_RE = re.compile(
    r"\bcode\b|\bcodes\b|kód|\bkod\b|passcode|\botp\b|\bpin\b|heslo|token|\bcódigo\b|\bcode:",
    re.IGNORECASE)

# Context that makes a number something else.
_NOT_CODE_BEFORE_RE = re.compile(
    r"(?:order|objednávk|objednavk|invoice|faktur|účtenk|uctenk|tracking|zásilk|zasilk|ticket|"
    r"č\.|no\.|nr\.|#|tel|phone|telefon|iban|account number|číslo účtu|cislo uctu|ič|dič|psč)\W{0,3}$",
    re.IGNORECASE)
_UNIT_AFTER_RE = re.compile(
    r"^\s?(?:%|kč|kc\b|czk|eur|€|\$|usd|gbp|£|min\b|minut|hod|ks\b|x\b|px|mb|gb|kb)", re.IGNORECASE)

# Candidate shapes. Digits (4-8, or 3+3 split by a space / dash), uppercase
# letters+digits (Steam "F7K2X"), Slack-style "ABC-123".
_CANDIDATE_RE = re.compile(
    r"(?<![\w+#/@.,:-])(?<!\d[ -])"
    r"(\d{3}[ -]\d{3}(?![ -]?\d)|\d{4,8}|(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{5,8}|[A-Z]{3}-\d{3})"
    r"(?![\w/@-]|[.,:]\d)")
# After "code is" / "kód:" a lower-case code is allowed too (X / Twitter style).
_LOWER_AFTER_RE = re.compile(
    r"(?:code|kód|kod|passcode)\s*(?:is|je|:)\s*:?\s*([a-z0-9]{6,10})\b", re.IGNORECASE)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\S+@\S+")
_DATE_RE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b")
_PHONE_RE = re.compile(r"\+\d[\d ()-]{7,}\d|\b\d{3} \d{3} \d{3}\b")
# Google writes "G-482931"; the code you type is the digits.
_GOOGLE_PREFIX_RE = re.compile(r"\bG-(?=\d{6}\b)")


def html_to_text(html: str) -> str:
    """Rough visible text of an HTML body (codes are usually in their own block)."""
    if not html:
        return ""
    s = re.sub(r"(?is)<(head|style|script|title)\b.*?</\1>", " ", html)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table|td|th)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = s.replace("\u00a0", " ").replace("\u200b", "").replace("\u200c", "").replace("\u2060", "")
    return re.sub(r"[ \t]+", " ", s)


def looks_like_code_mail(subject: str, text: str = "") -> bool:
    """Is this mail about signing in / verifying? (Cheap: subject + opening text.)"""
    return bool(_AUTH_RE.search(subject or "") or (text and _AUTH_RE.search(text[:800])))


def _scrub(text: str) -> str:
    """Blank out what can never hold the code, keeping positions intact."""
    for rx in (_URL_RE, _EMAIL_RE, _PHONE_RE, _DATE_RE, _GOOGLE_PREFIX_RE):
        text = rx.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _score(text: str, start: int, end: int, raw: str) -> float:
    code = re.sub(r"[ -]", "", raw) if re.fullmatch(r"\d{3}[ -]\d{3}", raw) else raw
    digits = code.isdigit()
    if digits:
        n = len(code)
        score = {6: 3.0, 7: 2.5, 8: 2.5, 5: 1.5, 4: 1.2}.get(n, 0.0)
        if n == 4 and re.fullmatch(r"(19|20)\d\d", code):
            score -= 3            # a year
    elif re.fullmatch(r"[A-Z]{3}-\d{3}", code):
        score = 2.5
    else:
        score = 2.0
    before = text[max(0, start - 60):start]
    after = text[end:end + 50]
    near_before = before[-40:]
    if _CODE_WORD_RE.search(near_before):
        score += 3.0
    elif _CODE_WORD_RE.search(before):
        score += 1.5
    if _CODE_WORD_RE.search(after.split("\n")[0][:40]):
        score += 2.5            # "482931 is your verification code" (same line only)
    if re.search(r"(?:\bis|\bje|:)\s*$", before, re.IGNORECASE):
        score += 1.5            # "code is 482931" / "kód: 482931"
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start:line_end if line_end >= 0 else len(text)].strip(" \t*:\r")
    if line == raw.strip():
        score += 2.0            # the code alone on its own line
    if _NOT_CODE_BEFORE_RE.search(before[-25:]):
        score -= 4.0
    if _UNIT_AFTER_RE.match(after):
        score -= 4.0
    return score


def find_code(subject: str, text: str = "", html: str = "") -> str | None:
    """The sign-in code in a mail, or None. `text` is the plain body; `html` is
    used when there's no plain part."""
    body = text or ""
    if len(body.strip()) < 8 and html:
        body = html_to_text(html)
    if not looks_like_code_mail(subject, body):
        return None
    full = (subject or "") + "\n\n" + body[:6000]
    scan = _scrub(full)
    best: dict[str, float] = {}
    for m in _CANDIDATE_RE.finditer(scan):
        raw = m.group(1)
        code = re.sub(r"[ -]", "", raw) if re.fullmatch(r"\d{3}[ -]\d{3}", raw) else raw
        s = _score(scan, m.start(1), m.end(1), raw)
        if m.start(1) < len(subject or ""):
            s += 0.5
        best[code] = max(best.get(code, -99.0), s)
    for m in _LOWER_AFTER_RE.finditer(scan):
        code = m.group(1)
        if code.isdigit() or code.isupper():
            continue            # the main pattern already covers these
        if not re.search(r"\d", code) or not re.search(r"[a-z]", code):
            continue            # a word ("code is expired"), not a code
        best[code] = max(best.get(code, -99.0), 5.0)
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top_code, top = ranked[0]
    if top < 4.5:
        return None
    if len(ranked) > 1 and ranked[1][1] > top - 0.5:
        return None             # two equally likely codes: don't guess
    return top_code
