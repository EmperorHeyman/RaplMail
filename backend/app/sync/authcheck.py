"""Local sender-authentication check (anti-spoof shield).

Rather than re-run DKIM crypto + DNS ourselves, we read the Authentication-Results
header that the receiving server (M365 / Seznam / Gmail) already stamped after
doing full SPF + DKIM + DMARC with proper DNS. That header is added at the trust
boundary (your mailbox provider), so a spoofed `a123systems.eu` arrives with
`dmarc=fail` — which is exactly the signal we surface as a red shield.

Verdict:
  pass        — authentication checks passed (green shield)
  fail        — DMARC failed or DKIM/SPF explicitly failed (red shield — likely spoof)
  none        — no/neutral auth info (no shield)
"""

from __future__ import annotations

import email
import re


def _find(blob: str, name: str) -> str:
    m = re.search(rf"(?:^|[\s;])\b{name}=([a-zA-Z]+)", blob)
    return m.group(1).lower() if m else ""


_DOMAIN_IN_TEXT = re.compile(r"\b([a-z0-9][a-z0-9.-]*\.[a-z]{2,})\b", re.IGNORECASE)
_HREF_A = re.compile(r'<a\b[^>]*\bhref=["\']https?://([^/"\'?#\s]+)[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

# Commonly-impersonated brands → the registered domains they actually send from.
# A display name that names one of these while the address is on some other domain
# is the classic phishing tell ("LinkedIn <x@whatever.ru>"). Kept deliberately to
# distinctive brand words (no ambiguous short tokens like "ups") and generous on
# the legit-domain side so real transactional mail is never flagged.
_BRAND_DOMAINS: dict[str, set[str]] = {
    "paypal": {"paypal.com", "paypal.co.uk"},
    "microsoft": {"microsoft.com", "outlook.com", "office.com", "office365.com",
                  "live.com", "hotmail.com", "microsoftonline.com", "microsoftstore.com"},
    "onedrive": {"microsoft.com", "onedrive.com"},
    "apple": {"apple.com", "icloud.com", "me.com"},
    "icloud": {"apple.com", "icloud.com"},
    "google": {"google.com", "gmail.com", "googlemail.com", "youtube.com"},
    "amazon": {"amazon.com", "amazon.co.uk", "amazon.de", "amazon.cz", "amazonses.com"},
    "linkedin": {"linkedin.com"},
    "netflix": {"netflix.com"},
    "facebook": {"facebook.com", "facebookmail.com", "fb.com", "meta.com"},
    "instagram": {"instagram.com", "mail.instagram.com"},
    "whatsapp": {"whatsapp.com"},
    "spotify": {"spotify.com", "spotifymail.com"},
    "dropbox": {"dropbox.com", "dropboxmail.com"},
    "docusign": {"docusign.com", "docusign.net"},
    "coinbase": {"coinbase.com"},
    "binance": {"binance.com"},
    "dhl": {"dhl.com", "dhl.de"},
    "fedex": {"fedex.com"},
    "wetransfer": {"wetransfer.com", "wetransfer.zendesk.com"},
    "seznam": {"seznam.cz", "email.cz"},
    "alza": {"alza.cz", "alza.sk"},
    "csob": {"csob.cz"},
    "airbank": {"airbank.cz"},
}

# TLDs disproportionately used for throwaway/abusive senders. A brand-mismatch or
# lookalike domain on one of these is a stronger tell; not flagged on its own to
# avoid nagging on legitimate regional mail.
_RISKY_TLDS = {"ru", "su", "cn", "tk", "top", "xyz", "gq", "ml", "cf", "ga", "click",
               "work", "zip", "mov", "loan", "kim", "country", "download", "review"}


def _reg_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0].strip().rstrip(".")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _brand_impersonation(from_name: str, from_dom: str) -> str:
    """The display name names a well-known brand, but the sender's registered
    domain isn't one that brand sends from (e.g. "LinkedIn <x@whatever.ru>").
    Returns a warning string, or "" when nothing looks off. Word-boundary matched
    so a brand word inside another word ("Applebee's") doesn't trip it."""
    if not from_name or not from_dom:
        return ""
    reg = _reg_domain(from_dom)
    name_l = from_name.lower()
    for brand, domains in _BRAND_DOMAINS.items():
        if reg in domains:
            return ""   # legit brand domain — never flag, whatever the name says
        if re.search(rf"\b{re.escape(brand)}\b", name_l):
            tld = reg.rsplit(".", 1)[-1]
            extra = " (and a high-risk domain)" if tld in _RISKY_TLDS else ""
            return (f"Display name looks like “{brand.title()}”, but the address is "
                    f"@{from_dom}{extra} — possible impersonation.")
    return ""


def spoof_warnings(from_addr: str = "", from_name: str = "", html: str = "") -> list[str]:
    """Social-engineering checks DMARC can't catch: lookalike/IDN domains,
    display-name domain mismatch, brand impersonation, and link-text-vs-href
    mismatch."""
    out: list[str] = []
    from_dom = (from_addr or "").split("@")[-1].lower()

    # 1) Confusable / punycode sender domain (Cyrillic 'е', etc.).
    if from_dom and (from_dom.startswith("xn--") or any(ord(c) > 127 for c in from_dom)):
        out.append(f"Sender domain “{from_dom}” uses non-standard characters — possible lookalike.")

    # 1b) Display name impersonates a known brand from the wrong domain.
    brand_warn = _brand_impersonation(from_name or "", from_dom)
    if brand_warn:
        out.append(brand_warn)

    # 2) Display name claims a different domain/email than the actual address.
    #    Skip false positives where the "domain" in the name is really just the
    #    local part of the address — e.g. name "pet.regina" for pet.regina@seznam.cz
    #    (a dotted handle that merely looks like a domain). Only flag when the name
    #    cites a domain that is genuinely absent from the real address.
    full_addr = (from_addr or "").lower()
    if from_name and from_dom:
        for m in _DOMAIN_IN_TEXT.finditer(from_name):
            cand = m.group(1).lower()
            if cand in full_addr:           # name echoes the real address — fine
                continue
            d = _reg_domain(cand)
            if "." in d and d != _reg_domain(from_dom):
                out.append(f"Display name mentions “{d}” but the address is @{from_dom}.")
                break

    # 3) A link's visible text names one domain but it points to another.
    if html:
        for m in _HREF_A.finditer(html):
            href_dom = _reg_domain(m.group(1))
            shown_text = re.sub(r"<[^>]+>", "", m.group(2))
            tm = _DOMAIN_IN_TEXT.search(shown_text)
            if tm:
                shown = _reg_domain(tm.group(1))
                if "." in shown and href_dom and shown != href_dom:
                    out.append(f"A link labeled “{shown}” actually goes to “{href_dom}”.")
                    break
    return out


def check_auth(raw: bytes, from_addr: str = "") -> dict:
    out = {"status": "none", "dkim": "", "spf": "", "dmarc": "", "detail": "", "from_domain": ""}
    try:
        msg = email.message_from_bytes(raw)
    except Exception:
        return out

    headers = (msg.get_all("Authentication-Results") or [])
    if not headers:
        headers = (msg.get_all("ARC-Authentication-Results") or [])
    blob = " ; ".join(str(h) for h in headers)
    out["from_domain"] = (from_addr or "").split("@")[-1].lower()
    if not blob:
        return out

    dkim, spf, dmarc = _find(blob, "dkim"), _find(blob, "spf"), _find(blob, "dmarc")
    out.update(dkim=dkim, spf=spf, dmarc=dmarc)

    if dmarc:
        status = "pass" if dmarc == "pass" else ("fail" if dmarc == "fail" else "none")
    elif dkim == "pass" or spf == "pass":
        status = "pass"
    elif dkim == "fail" or spf == "fail":
        status = "fail"
    else:
        status = "none"
    out["status"] = status
    out["detail"] = f"DKIM {dkim or '—'} · SPF {spf or '—'} · DMARC {dmarc or '—'}"
    return out
