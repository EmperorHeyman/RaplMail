"""Keep one warm IMAP connection per account for interactive reads.

Opening a message previously created a fresh IMAP connection and logged in every
time (~1-2s on some providers). This pool reuses a connection per account, guarded
by a per-account lock, recreating it if it goes stale.
"""

from __future__ import annotations

import threading

from app.models import Account


class _Entry:
    __slots__ = ("provider", "lock")

    def __init__(self) -> None:
        self.provider = None
        self.lock = threading.Lock()


class ProviderPool:
    def __init__(self) -> None:
        self._entries: dict[int, _Entry] = {}
        self._guard = threading.Lock()

    def _entry(self, account_id: int) -> _Entry:
        with self._guard:
            e = self._entries.get(account_id)
            if e is None:
                e = _Entry()
                self._entries[account_id] = e
            return e

    def fetch_raw(self, account: Account, folder_path: str, uid: int) -> bytes:
        from app.sync.engine import build_provider

        e = self._entry(account.id)
        with e.lock:
            last_exc = None
            for attempt in range(2):
                if e.provider is None:
                    e.provider = build_provider(account)
                try:
                    return e.provider.fetch_raw(folder_path, uid)
                except Exception as exc:  # stale connection -> rebuild once
                    last_exc = exc
                    try:
                        e.provider.close()
                    except Exception:
                        pass
                    e.provider = None
            raise last_exc  # type: ignore[misc]

    def keepalive(self) -> None:
        """NOOP each open connection so the server doesn't drop it (keeps opens fast)."""
        for e in list(self._entries.values()):
            if e.provider and e.lock.acquire(blocking=False):
                try:
                    e.provider._imap().noop()
                except Exception:
                    try:
                        e.provider.close()
                    except Exception:
                        pass
                    e.provider = None
                finally:
                    e.lock.release()

    def drop(self, account_id: int) -> None:
        with self._guard:
            e = self._entries.pop(account_id, None)
        if e and e.provider:
            try:
                e.provider.close()
            except Exception:
                pass


pool = ProviderPool()
