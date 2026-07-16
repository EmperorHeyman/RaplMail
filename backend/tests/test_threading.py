"""Reply-chain threading (D4): a message carrying In-Reply-To inherits its
parent's thread_id, so a reply whose subject was rewritten still joins the
original conversation. Messages with no references keep the subject+participant
key (no regression). Both the live-sync upsert path and the /rethread backfill
use the same rule.
"""
from datetime import datetime

from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message
from app.providers.base import HeaderInfo
from app.sync.threading import thread_key


def _s():
    return Session(get_engine())


_n = 0


def _seed_account():
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"thread{_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        inbox = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(inbox); s.commit(); s.refresh(inbox)
        return acct.id, inbox.id


def _mgr():
    from app.sync.engine import SyncManager
    return SyncManager.__new__(SyncManager)   # only need the plain _upsert_message method


def test_reply_inherits_parent_thread_on_sync(client):
    acct_id, folder_id = _seed_account()
    mgr = _mgr()
    parent_mid = "<orig-123@example.com>"
    with _s() as s:
        acct = s.get(Account, acct_id); folder = s.get(Folder, folder_id)
        # Original message.
        h1 = HeaderInfo(uid=101, message_id=parent_mid, subject="Project kickoff",
                        from_addr="a@example.com", from_name="A", to_addrs=["b@example.com"])
        p = mgr._upsert_message(s, acct, folder, h1)
        s.commit()
        parent_tid = p.thread_id
        # A reply with a REWRITTEN subject but In-Reply-To the original.
        h2 = HeaderInfo(uid=102, message_id="<reply-456@example.com>",
                        subject="Re: [EXTERNAL] Project kickoff", from_addr="b@example.com",
                        from_name="B", to_addrs=["a@example.com"], in_reply_to=parent_mid)
        child = mgr._upsert_message(s, acct, folder, h2)
        s.commit()
        assert child.thread_id == parent_tid          # joined via In-Reply-To
        assert child.in_reply_to == parent_mid         # header persisted


def test_no_references_uses_subject_key(client):
    acct_id, folder_id = _seed_account()
    mgr = _mgr()
    with _s() as s:
        acct = s.get(Account, acct_id); folder = s.get(Folder, folder_id)
        h = HeaderInfo(uid=201, message_id="<solo-1@example.com>", subject="Standalone note",
                       from_addr="c@example.com", from_name="C", to_addrs=["d@example.com"])
        m = mgr._upsert_message(s, acct, folder, h)
        s.commit()
        expected = thread_key(acct_id, "Standalone note", uid=201, folder_id=folder_id,
                              participants=["c@example.com", "d@example.com"])
        assert m.thread_id == expected                 # unchanged subject+participant key


def test_rethread_backfills_reply_chain(client):
    acct_id, folder_id = _seed_account()
    parent_mid = "<bf-orig@example.com>"
    # Seed rows DIRECTLY with mismatched thread ids (as if synced before the
    # reply-chain rule existed): the child has a different subject key.
    with _s() as s:
        s.add(Message(account_id=acct_id, folder_id=folder_id, uid=301, message_id=parent_mid,
                      subject="Invoice", from_addr="x@example.com", to_addrs=["y@example.com"],
                      thread_id="stale-parent", date=datetime(2026, 1, 1)))
        s.add(Message(account_id=acct_id, folder_id=folder_id, uid=302,
                      message_id="<bf-reply@example.com>", in_reply_to=parent_mid,
                      subject="Re: Invoice (paid)", from_addr="y@example.com",
                      to_addrs=["x@example.com"], thread_id="stale-child",
                      date=datetime(2026, 1, 2)))
        s.commit()
    r = client.post("/messages/rethread")
    assert r.status_code == 200
    with _s() as s:
        rows = {m.uid: m.thread_id for m in s.exec(
            select(Message).where(Message.account_id == acct_id, Message.uid.in_([301, 302])))}
        # The reply now shares the parent's (recomputed) thread id.
        assert rows[301] == rows[302]
