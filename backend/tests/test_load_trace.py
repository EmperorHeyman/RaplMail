"""Opening a message: every server fetch records its phases (so a slow or
stuck open can say what it's waiting for), and a stuck connection can be cut."""
import threading
import time

import pytest
from sqlmodel import Session

from app.core.db import get_engine
from app.core.loadtrace import LoadTracker, tracker
from app.models import Account, Folder, FolderRole, Message
from app.providers import pool as pool_mod
from app.providers.pool import ConnectionReset, ProviderPool

RAW = (b"From: Sender <s@x.example>\r\nTo: me@me.example\r\nSubject: Hello\r\n"
       b"Message-ID: <lt-1@x>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nBody text here\r\n")


class FakeProvider:
    """Stands in for ImapSmtpProvider: fetch_raw can be made to hang until abort()."""

    def __init__(self, raw=RAW, hang: threading.Event | None = None, fail: Exception | None = None):
        self.raw, self.hang, self.fail = raw, hang, fail
        self.aborted = threading.Event()
        self.connected = False

    def _imap(self):
        self.connected = True
        return self

    def fetch_raw(self, folder_path, uid):
        if self.fail:
            raise self.fail
        if self.hang is not None:
            # A dead socket: block until the connection is cut.
            if not self.aborted.wait(10):
                raise TimeoutError("read timed out")
            raise OSError("socket closed")
        return self.raw

    def abort(self):
        self.aborted.set()

    def close(self):
        pass


def _account():
    return Account(id=4242, email="trace@me.example")


def test_phases_are_recorded(monkeypatch):
    p = ProviderPool()
    monkeypatch.setattr("app.sync.engine.build_provider", lambda a: FakeProvider())
    t = LoadTracker().start(1, "open", 4242, "Hello")
    raw = p.fetch_raw(_account(), "INBOX", 7, trace=t)
    assert raw == RAW
    t.finish()
    names = [n for n, _ in t.phases]
    assert names == ["waiting", "connecting", "downloading"]
    assert t.info["bytes"] == len(RAW)


def test_busy_says_what_holds_the_connection(monkeypatch):
    p = ProviderPool()
    hang = threading.Event()
    fake = FakeProvider(hang=hang)
    monkeypatch.setattr("app.sync.engine.build_provider", lambda a: fake)
    pre = LoadTracker().start(1, "prefetch", 4242)
    th = threading.Thread(target=lambda: _swallow(p.fetch_raw, _account(), "INBOX", 1, pre))
    th.start()
    for _ in range(100):
        if p.busy(4242):
            break
        time.sleep(0.01)
    busy = p.busy(4242)
    assert busy and busy["what"] == "prefetch"
    p.reset(4242)
    th.join(5)
    assert not th.is_alive()


def _swallow(fn, *a):
    try:
        fn(*a)
    except Exception:
        pass


def test_reset_unblocks_a_stuck_read_at_once(monkeypatch):
    p = ProviderPool()
    fake = FakeProvider(hang=threading.Event())
    monkeypatch.setattr("app.sync.engine.build_provider", lambda a: fake)
    errors = []

    def stuck():
        try:
            p.fetch_raw(_account(), "INBOX", 1)
        except Exception as exc:
            errors.append(exc)

    th = threading.Thread(target=stuck)
    th.start()
    for _ in range(100):
        if p.busy(4242):
            break
        time.sleep(0.01)
    t0 = time.monotonic()
    assert p.reset(4242) is True
    th.join(5)
    assert time.monotonic() - t0 < 2          # not the 10 s "read timeout"
    assert errors and isinstance(errors[0], ConnectionReset)
    # The next open gets a fresh connection instead of queueing behind the dead one.
    monkeypatch.setattr("app.sync.engine.build_provider", lambda a: FakeProvider())
    assert p.fetch_raw(_account(), "INBOX", 2) == RAW


_n = 0


def _message():
    global _n
    _n += 1
    with Session(get_engine()) as s:
        a = Account(email=f"opentrace{_n}@me.example")
        s.add(a); s.commit(); s.refresh(a)
        f = Folder(account_id=a.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        m = Message(account_id=a.id, folder_id=f.id, uid=88000 + _n, message_id=f"<lt-{_n}@x>",
                    from_addr="s@x.example", subject="Trace me", to_addrs=["me@me.example"])
        s.add(m); s.commit(); s.refresh(m)
        return m.id


def test_open_records_a_trace_and_status(client, monkeypatch):
    mid = _message()
    monkeypatch.setattr(pool_mod.pool, "fetch_raw",
                        lambda account, path, uid, trace=None: (trace.mark("downloading"), RAW)[1])
    r = client.get(f"/messages/{mid}", params={"why": "open"})
    assert r.status_code == 200 and "Body text here" in r.json()["text"]
    st = client.get(f"/messages/{mid}/load-status").json()
    assert st["done"] and st["why"] == "open" and not st["error"]
    assert [p["name"] for p in st["phases"]][:2] == ["downloading", "parsing"]
    assert any(l["message_id"] == mid for l in client.get("/debug/loads").json()["loads"])


def test_failed_open_says_where_it_failed(client, monkeypatch):
    mid = _message()

    def boom(account, path, uid, trace=None):
        trace.mark("downloading")
        raise TimeoutError("read timed out")
    monkeypatch.setattr(pool_mod.pool, "fetch_raw", boom)
    d = client.get(f"/messages/{mid}").json()
    assert d["load_error"].startswith("TimeoutError")
    assert d["load_phase"] == "downloading"
    st = client.get(f"/messages/{mid}/load-status").json()
    assert st["error"].startswith("TimeoutError")


def test_connection_reset_endpoint(client):
    mid = _message()
    r = client.post("/messages/connection-reset", json={"message_id": mid})
    assert r.status_code == 200 and r.json() == {"reset": False}   # nothing open to cut


@pytest.fixture(autouse=True)
def _clean_tracker():
    yield
    with tracker._lock:
        tracker._active.clear()


def test_open_during_a_preload_shares_its_download(monkeypatch):
    """The hover preload and the click arrive together: one download, not two."""
    import asyncio

    import httpx

    from app.main import app as fastapi_app
    mid = _message()
    calls = []

    def slow(account, path, uid, trace=None):
        calls.append(uid)
        time.sleep(0.6)
        return RAW
    monkeypatch.setattr(pool_mod.pool, "fetch_raw", slow)

    async def both():
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            pre = asyncio.create_task(c.get(f"/messages/{mid}", params={"why": "prefetch"}))
            await asyncio.sleep(0.15)
            opened = await c.get(f"/messages/{mid}", params={"why": "open"})
            return (await pre), opened
    pre, opened = asyncio.run(both())
    assert pre.status_code == opened.status_code == 200
    assert "Body text here" in opened.json()["text"]
    assert len(calls) == 1
