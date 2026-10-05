"""Keep one warm IMAP connection per account for interactive reads.

Opening a message previously created a fresh IMAP connection and logged in every
time (~1-2s on some providers). This pool reuses a connection per account, guarded
by a per-account lock, recreating it if it goes stale.

One connection per account means one thing at a time: a background preload, a
flag update or the keepalive NOOP holds it while your open waits. The entry
records what it's busy with (`holder`), so a slow open can say what it's
waiting behind, and `reset()` can cut a connection that's stuck on a dead
socket instead of letting every open queue behind it until the read times out.
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


class ConnectionReset(Exception):
    """The connection was cut on purpose (reset()) while this read waited on it."""


class _Entry:
    __slots__ = ("provider", "lock", "last_used", "holder", "held_since", "dead")

    def __init__(self) -> None:
        self.provider = None
        self.lock = threading.Lock()
        self.last_used = 0.0
        self.holder = ""        # what holds the connection now: "open" / "prefetch" / "flag" / "keepalive" / "read"
        self.held_since = 0.0
        self.dead = False       # reset() threw this entry away; finish without reusing it


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

    @staticmethod
    def _hold(e: _Entry, what: str) -> None:
        e.holder, e.held_since = what, time.monotonic()

    def busy(self, account_id: int | None) -> dict | None:
        """What the account's connection is doing right now, and for how long."""
        with self._guard:
            e = self._entries.get(account_id) if account_id is not None else None
        if e is None or not e.holder:
            return None
        return {"what": e.holder, "ms": round((time.monotonic() - e.held_since) * 1000)}

    def fetch_raw(self, account: Account, folder_path: str, uid: int, trace=None) -> bytes:
        """The raw message. `trace` (app.core.loadtrace.LoadTrace) records the
        phases - waiting for the connection, connecting, downloading."""
        from app.sync.engine import build_provider

        e = self._entry(account.id)
        if trace is not None:
            trace.mark("waiting")
        with e.lock:
            self._hold(e, trace.why if trace is not None else "read")
            try:
                if e.dead:
                    raise ConnectionReset("the connection was reset")
                e.last_used = time.monotonic()
                last_exc = None
                for attempt in range(2):
                    if trace is not None:
                        trace.mark("connecting" if attempt == 0 else "retrying")
                    if e.provider is None:
                        e.provider = build_provider(account)
                    try:
                        e.provider._imap()   # connect + sign in when cold; instant when warm
                        if trace is not None:
                            trace.mark("downloading")
                        raw = e.provider.fetch_raw(folder_path, uid)
                        if trace is not None:
                            trace.note(bytes=len(raw or b""))
                        return raw
                    except Exception as exc:  # stale connection -> rebuild once
                        last_exc = exc
                        if trace is not None:
                            trace.note(first_error=f"{type(exc).__name__}: {exc}"[:240])
                        try:
                            e.provider.close()
                        except Exception:
                            pass
                        e.provider = None
                        if e.dead:
                            raise ConnectionReset("the connection was reset") from exc
                raise last_exc  # type: ignore[misc]
            finally:
                e.holder = ""
                if e.dead and e.provider is not None:
                    # reset() orphaned this entry while we were reading; don't leave
                    # the connection we may have rebuilt open with nobody to use it.
                    self._discard(e)

    def set_keyword(self, account: Account, folder_path: str, uid: int, keyword: str, on: bool) -> None:
        """Add/remove a custom IMAP keyword on a message (used to mirror the local
        'done' state to the server so it syncs across devices)."""
        from app.sync.engine import build_provider

        e = self._entry(account.id)
        with e.lock:
            self._hold(e, "flag")
            try:
                e.last_used = time.monotonic()
                for _ in range(2):
                    if e.dead:
                        return
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
            finally:
                e.holder = ""

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
            self._hold(e, "keepalive")
            try:
                if now - e.last_used > IDLE_TIMEOUT:
                    self._discard(e)  # idle too long - next fetch rebuilds on demand
                else:
                    e.provider._imap().noop()
            except Exception:
                self._discard(e)
            finally:
                e.holder = ""
                e.lock.release()

    def drop(self, account_id: int) -> None:
        with self._guard:
            e = self._entries.pop(account_id, None)
        if e and e.provider:
            try:
                e.provider.close()
            except Exception:
                pass

    def reset(self, account_id: int) -> bool:
        """Throw the account's connection away NOW, even mid-read. A read stuck
        on a dead socket holds the lock until its read timeout (minutes); cutting
        the socket fails it at once, and the next open gets a fresh connection
        (new entry, new lock) instead of queueing behind it. True if there was
        a connection to cut."""
        with self._guard:
            e = self._entries.pop(account_id, None)
        if e is None:
            return False
        e.dead = True
        prov = e.provider
        if prov is not None:
            try:
                prov.abort()
            except Exception:
                pass
        return prov is not None


pool = ProviderPool()
