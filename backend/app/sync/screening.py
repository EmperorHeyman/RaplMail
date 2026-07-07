"""Anti-phishing screening applied during sync.

Two independent, user-controlled layers:

* A **domain/TLD blocklist** the user configures (Settings → Security). Mail whose
  sender domain matches is quarantined on arrival (moved to Junk, or deleted) —
  the same hard action a "block" rule takes.
* **Header spoof heuristics** — a subset of `authcheck.spoof_warnings` that needs
  no message body (lookalike/IDN domain, display-name/domain mismatch, brand
  impersonation). When enabled, a matching inbox mail is *flagged* suspicious
  (a warning badge); it is never auto-deleted, so a false positive costs nothing.

Kept as pure functions so they're trivially unit-testable without a live mailbox.
"""

from __future__ import annotations

import re

from app.sync.authcheck import spoof_warnings

_SPLIT = re.compile(r"[\s,;]+")


def _norm_domain(d: str) -> str:
    """Normalize a domain/TLD entry: lowercase, drop a leading '@' or '.', and any
    trailing dot. "@Bad.RU" / ".ru" / "ru" all normalize to a bare host/suffix."""
    d = (d or "").strip().lower().lstrip("@").strip()
    return d.lstrip(".").rstrip(".")


def normalize_blocklist(raw) -> list[str]:
    """Accept a list, or a comma/space/newline-separated string, of domains or
    TLDs → a clean, de-duplicated lowercase list. Order preserved."""
    parts = _SPLIT.split(raw) if isinstance(raw, str) else list(raw or [])
    out: list[str] = []
    for p in parts:
        d = _norm_domain(str(p))
        if d and d not in out:
            out.append(d)
    return out


def matches_blocked_domain(from_addr: str, blocked: list[str]) -> bool:
    """True if the sender's domain equals a blocked entry, is a subdomain of one,
    or ends in a blocked TLD. So "ru" blocks x.ru; "spammer.com" blocks
    spammer.com and mail.spammer.com; "bad.co.uk" blocks exactly that + subs."""
    dom = _norm_domain((from_addr or "").split("@")[-1])
    if not dom:
        return False
    return any(b and (dom == b or dom.endswith("." + b)) for b in blocked)


def header_spoof_flags(from_addr: str, from_name: str) -> list[str]:
    """Header-only spoof signals (no message body available at sync time). Reuses
    the shared heuristics with an empty html body so the link-mismatch check is
    simply skipped."""
    return spoof_warnings(from_addr or "", from_name or "", "")
