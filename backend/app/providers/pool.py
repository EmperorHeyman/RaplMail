"""Keep one warm IMAP connection per account for interactive reads.

Opening a message previously created a fresh IMAP connection and logged in every
time (~1-2s on some providers). This pool reuses a connection per account, guarded
by a per-account lock, recreating it if it goes stale.
"""

from __future__ import annotations

import threading
import time

from app.models import Account

# Close a pooled connection that hasn't served a real read/flag in this many
# seconds, instead of NOOPing it warm forever. Frees the socket + its pinned
# read buffers for accounts you're not actively touching; the next fetch just
# rebuilds it (~1-2s, one-time).
IDLE_TIMEOUT = 600.0


class _Entry:
    __slots__ = ("provider", "lock", "last_used")

    def __init__(self) -> None:
        self.provider = None
        self.lock = threading.Lock()
        self.last_used = 0.0


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
            e.last_used = time.monotonic()
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

    def set_keyword(self, account: Account, folder_path: str, uid: int, keyword: str, on: bool) -> None:
        """Add/remove a custom IMAP keyword on a message (used to mirror the local
        'done' state to the server so it syncs across devices)."""
        from app.sync.engine import build_provider

        e = self._entry(account.id)
        with e.lock:
            e.last_used = time.monotonic()
            for _ in range(2):
                if e.provider is None:
                    e.provider = build_provider(account)
                try:
                    e.provider.set_flags(folder_path, uid, [keyword.encode("ascii")], add=on)
                    return
                except Exception:
                    try:
                        e.provider.close()
                    except Exception:
                        pass
                    e.provider = None

    @staticmethod
    def _discard(e: _Entry) -> None:
        """Close and forget an entry's connection (frees its socket + buffers)."""
        try:
            if e.provider:
                e.provider.close()
        except Exception:
            pass
        e.provider = None

    def keepalive(self) -> None:
        """Keep recently-used connections warm (NOOP so the server doesn't drop
        them and opens stay fast); close connections idle past IDLE_TIMEOUT so
        their socket + read buffers are released instead of pinned forever."""
        now = time.monotonic()
        for e in list(self._entries.values()):
            if not (e.provider and e.lock.acquire(blocking=False)):
                continue
            try:
                if now - e.last_used > IDLE_TIMEOUT:
                    self._discard(e)  # idle too long — next fetch rebuilds on demand
                else:
                    e.provider._imap().noop()
            except Exception:
                self._discard(e)
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
