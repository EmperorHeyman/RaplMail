"""Conversation threading by normalized subject (per account).

We don't have full References headers, so we thread by a normalized subject
(stripping Re:/Fwd:/… prefixes) scoped to the account. Pragmatic and matches
how most clients group day-to-day mail.
"""

from __future__ import annotations

import re

# Strips repeated reply/forward prefixes in several languages (en/cz/de/…).
_PREFIX = re.compile(r"^\s*((re|fwd|fw|aw|wg|sv|vs|odp|fwd?)\s*(\[\d+\])?\s*:\s*)+", re.I)


def normalize_subject(subject: str) -> str:
    s = subject or ""
    prev = None
    while prev != s:
        prev = s
        s = _PREFIX.sub("", s).strip()
    return s.strip().lower()


def thread_key(account_id: int, subject: str, uid: int = 0) -> str:
    """Stable thread id for a message. Empty subjects fall back to a unique key."""
    norm = normalize_subject(subject)
    if norm:
        return f"{account_id}|{norm}"
    return f"{account_id}|u:{uid}"
