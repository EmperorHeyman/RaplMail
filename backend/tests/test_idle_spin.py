"""IMAP IDLE watcher must not busy-spin on a half-closed connection.

A peer that closed its end stays readable forever, so imapclient's idle_check()
returns [] instantly and for ever without raising. The watcher loop used to call
it again immediately, burning a full CPU core per dead connection - silently,
with idle_active still reported as "true". These tests pin the three behaviours
that stop that: dead-peer detection, keepalive filtering, and IDLE refresh.
"""

import time

import pytest

from app.sync import engine as eng


class _DeadClient:
    """A half-closed peer: idle_check returns nothing, instantly, forever."""

    def __init__(self):
        self.calls = 0
        self.idle_calls = 0

    def has_capability(self, name):
        return True

    def select_folder(self, path):
        pass

    def idle(self):
        self.idle_calls += 1

    def idle_done(self):
        pass

    def idle_check(self, timeout=None):
        self.calls += 1
        return []


class _HealthyClient(_DeadClient):
    """A live peer: idle_check blocks for the full timeout, then returns []."""

    def __init__(self, sleep=0.02):
        super().__init__()
        self._sleep = sleep

    def idle_check(self, timeout=None):
        self.calls += 1
        time.sleep(self._sleep)
        return []


def _run_watcher(monkeypatch, client, stop_after_reconnects=1):
    """Drive SyncEngine._idle_watch against a fake client, stopping once it has
    torn the connection down `stop_after_reconnects` times."""
    e = eng.SyncManager.__new__(eng.SyncManager)   # no __init__: no DB, no hub
    e._idle = {1: {}}
    e._idle_stop = eng.threading.Event()
    e._synced = []
    e.request_account_sync_threadsafe = lambda aid: e._synced.append(aid)

    class _Provider:
        def _imap(self):
            return client

        def close(self):
            pass

    reconnects = {"n": 0}
    real_wait = e._idle_stop.wait

    def _wait(timeout=None):
        # The back-off is the only place the watcher lands after giving up on a
        # connection - count it, and stop the loop instead of actually sleeping.
        reconnects["n"] += 1
        if reconnects["n"] >= stop_after_reconnects:
            e._idle_stop.set()
        return real_wait(0)

    monkeypatch.setattr(e._idle_stop, "wait", _wait)
    monkeypatch.setattr(eng, "build_provider", lambda account: _Provider())
    monkeypatch.setattr(eng, "Session", lambda engine: _FakeSession())
    monkeypatch.setattr(eng, "get_engine", lambda: None)
    monkeypatch.setattr(eng, "IDLE_RECONNECT_BACKOFF", 0)

    e._idle_watch(1)
    return reconnects["n"], e._idle


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, model, ident):
        class _A:
            id = 1
            enabled = True
            email = "a@b.c"
        return _A()


def test_dead_peer_does_not_spin(monkeypatch):
    """A half-closed connection is detected and rebuilt, not spun on."""
    client = _DeadClient()
    _run_watcher(monkeypatch, client)
    # Bounded by IDLE_DEAD_EMPTY_LIMIT - the pre-fix loop ran until the heat death
    # of the CPU. Allow one extra call for loop-entry slack.
    assert client.calls <= eng.IDLE_DEAD_EMPTY_LIMIT + 1, (
        f"idle_check called {client.calls}x on a dead connection - still spinning"
    )


def test_dead_peer_marks_disconnected(monkeypatch):
    """idle_active must not keep claiming a dead connection is live.

    This is what made the bug invisible: the health dashboard read `connected`,
    which stayed True for the entire time the thread was spinning.
    """
    _, idle_state = _run_watcher(monkeypatch, _DeadClient())
    assert idle_state[1].get("connected") is False


def test_healthy_peer_keeps_idling(monkeypatch):
    """A live connection that simply has no news must NOT be torn down."""
    client = _HealthyClient(sleep=eng.IDLE_DEAD_WAIT_SECONDS + 0.05)

    e = eng.SyncManager.__new__(eng.SyncManager)
    e._idle = {1: {}}
    e._idle_stop = eng.threading.Event()
    e.request_account_sync_threadsafe = lambda aid: None

    class _Provider:
        def _imap(self):
            return client

        def close(self):
            pass

    monkeypatch.setattr(eng, "build_provider", lambda account: _Provider())
    monkeypatch.setattr(eng, "Session", lambda engine: _FakeSession())
    monkeypatch.setattr(eng, "get_engine", lambda: None)

    # Let it go round a few times, then stop it the way shutdown() would.
    stopper = eng.threading.Timer(
        (eng.IDLE_DEAD_WAIT_SECONDS + 0.05) * 3, e._idle_stop.set)
    stopper.start()
    e._idle_watch(1)
    stopper.cancel()

    # One idle() at connect and no reconnects: the slow-but-alive peer was kept.
    assert client.idle_calls == 1, "healthy connection was needlessly rebuilt"


@pytest.mark.parametrize("responses,expected", [
    ([(b"OK", b"Still here")], False),                  # pure keepalive
    ([(b"OK", b"Still here"), (1, b"EXISTS")], True),   # keepalive + new mail
    ([(1, b"EXISTS")], True),
    ([(3, b"EXPUNGE")], True),
    ([(1, b"FETCH", (b"FLAGS", (b"\\Seen",)))], True),
    ([(b"BYE", b"Logging out")], True),                 # not a keepalive
    ([(b"something-unknown",)], True),                  # unknown = sync anyway
])
def test_keepalive_filtering(responses, expected):
    """A bare 'OK Still here' ping must not cost a full account sync."""
    assert eng._idle_is_interesting(responses) is expected


def test_idle_refresh_stays_inside_rfc2177():
    """RFC 2177: re-issue IDLE at least every 29 minutes."""
    assert eng.IDLE_REFRESH_SECONDS < 29 * 60
