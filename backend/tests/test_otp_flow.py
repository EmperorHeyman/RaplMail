"""Sign-in codes end to end: found on open and kept on the row, read at sync
time for a fresh arrival, and copied through the backend clipboard bridge."""
from sqlmodel import Session

from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message
from app.providers import pool as pool_mod
from app.sync.engine import SyncManager

CODE_MAIL = (b"From: Microsoft account team <account-security-noreply@accountprotection.microsoft.com>\r\n"
             b"To: me@me.example\r\nSubject: Microsoft account security code\r\nMessage-ID: <otp-1@x>\r\n"
             b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
             b"Please use the following security code for the Microsoft account li**@a123.cz.\r\n\r\n"
             b"Security code: 4281937\r\n\r\nThanks,\r\nThe Microsoft account team\r\n")
PLAIN_MAIL = (b"From: Jana <jana@firma.example>\r\nTo: me@me.example\r\nSubject: Lunch tomorrow?\r\n"
              b"Message-ID: <otp-2@x>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
              b"How about 12:00? Table 1234.\r\n")

_n = 0


def _msg(subject):
    global _n
    _n += 1
    with Session(get_engine()) as s:
        a = Account(email=f"otpflow{_n}@me.example")
        s.add(a); s.commit(); s.refresh(a)
        f = Folder(account_id=a.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        m = Message(account_id=a.id, folder_id=f.id, uid=77000 + _n, message_id=f"<otpf-{_n}@x>",
                    from_addr="x@y.example", subject=subject, to_addrs=["me@me.example"])
        s.add(m); s.commit(); s.refresh(m)
        return m.id, a.id


def test_open_finds_the_code_and_the_list_shows_it(client, monkeypatch):
    mid, aid = _msg("Microsoft account security code")
    monkeypatch.setattr(pool_mod.pool, "fetch_raw", lambda account, path, uid, trace=None: CODE_MAIL)
    d = client.get(f"/messages/{mid}").json()
    assert d["otp_code"] == "4281937"
    rows = client.get("/messages", params={"account_id": aid}).json()
    assert [r["otp_code"] for r in rows if r["id"] == mid] == ["4281937"]


def test_ordinary_mail_has_no_code(client, monkeypatch):
    mid, _aid = _msg("Lunch tomorrow?")
    monkeypatch.setattr(pool_mod.pool, "fetch_raw", lambda account, path, uid, trace=None: PLAIN_MAIL)
    assert client.get(f"/messages/{mid}").json()["otp_code"] == ""


class _Prov:
    def __init__(self, raw):
        self.raw = raw

    def fetch_raw(self, path, uid):
        return self.raw


def test_sync_reads_a_fresh_code():
    folder = Folder(id=1, account_id=1, name="INBOX", path="INBOX", role=FolderRole.inbox)
    msg = Message(account_id=1, folder_id=1, uid=5, subject="Microsoft account security code")
    assert SyncManager._read_code(_Prov(CODE_MAIL), folder, msg) == "4281937"
    assert SyncManager._read_code(_Prov(PLAIN_MAIL), folder, msg) is None
    assert SyncManager._read_code(_Prov(b"x" * 2_100_000), folder, msg) is None   # too big to be one


def test_clipboard_bridge(client, monkeypatch):
    got = []
    monkeypatch.setattr("app.core.clipboard.set_text", lambda text: got.append(text) or True)
    assert client.post("/system/clipboard", json={"text": "4281937"}).json() == {"ok": True}
    assert got == ["4281937"]
    assert client.post("/system/clipboard", json={"text": ""}).json() == {"ok": False}
