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
