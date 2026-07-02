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


def thread_key(account_id: int, subject: str, uid: int = 0, folder_id: int = 0,
               participants: list[str] | None = None) -> str:
    """Stable thread id for a message.

    Subject threads carry the lowest participant address as a discriminator, so
    a common subject ("Invoice") from unrelated senders doesn't merge — while a
    reply (which swaps From/To but keeps the same pair) still matches. Empty
    subjects fall back to a per-folder key (UIDs are only unique per folder).
    """
    norm = normalize_subject(subject)
    if norm:
        low = min((p.strip().lower() for p in (participants or []) if p and p.strip()),
                  default="")
        return f"{account_id}|{low}|{norm}" if low else f"{account_id}|{norm}"
    return f"{account_id}|u:{folder_id}:{uid}"
