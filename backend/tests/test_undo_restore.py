"""Archive/delete undo: the bulk endpoint defers the IMAP flush past the undo
toast window (payload not_before), and /messages/restore cancels the queued
action + un-hides the rows before the server is ever touched."""
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, ActionQueue, Folder, FolderRole, Message


def _s():
    return Session(get_engine())


_n = 0


def _seed():
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"undo{_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        inbox = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(inbox); s.commit(); s.refresh(inbox)
        m = Message(account_id=acct.id, folder_id=inbox.id, uid=7000 + _n,
                    message_id=f"<undo-{_n}>", from_addr="x@ex.com", subject="hi")
        s.add(m); s.commit(); s.refresh(m)
        return m.id


def test_archive_defers_flush_and_restore_cancels(client):
    mid = _seed()
    r = client.post("/messages/bulk", json={"ids": [mid], "action": "archive"})
    assert r.status_code == 200 and r.json()["queued"] == 1
    with _s() as s:
        assert s.get(Message, mid).pending_action == "archive"    # hidden optimistically
        q = [a for a in s.exec(select(ActionQueue).where(ActionQueue.kind == "archive"))
             if mid in a.payload.get("ids", [])]
        assert q, "archive not queued"
        # The flush hold is stamped and still in the future.
        nb = q[0].payload.get("not_before") or ""
        assert nb > datetime.now(timezone.utc).isoformat()

    # A flush run during the hold must NOT touch the item.
    from app.api.messages import process_action_queue
    process_action_queue()
    with _s() as s:
        assert s.get(Message, mid) is not None                    # row still here
        assert any(mid in a.payload.get("ids", [])
                   for a in s.exec(select(ActionQueue).where(ActionQueue.kind == "archive")))

    # Undo: the queue entry disappears and the row is un-hidden.
    r = client.post("/messages/restore", json={"ids": [mid]})
    assert r.status_code == 200 and r.json()["restored"] == 1
    with _s() as s:
        assert s.get(Message, mid).pending_action == ""
        assert not any(mid in a.payload.get("ids", [])
                       for a in s.exec(select(ActionQueue).where(ActionQueue.kind == "archive")))


def test_restore_keeps_other_ids_in_shared_queue_item(client):
    a, b = _seed(), _seed()
    r = client.post("/messages/bulk", json={"ids": [a, b], "action": "delete"})
    assert r.status_code == 200 and r.json()["queued"] == 2
    r = client.post("/messages/restore", json={"ids": [a]})
    assert r.json()["restored"] == 1
    with _s() as s:
        assert s.get(Message, a).pending_action == ""
        assert s.get(Message, b).pending_action == "delete"       # untouched
        q = [x for x in s.exec(select(ActionQueue).where(ActionQueue.kind == "delete"))
             if b in x.payload.get("ids", [])]
        assert q and a not in q[0].payload["ids"]


def test_flush_processes_after_hold_expires(client, monkeypatch):
    mid = _seed()
    client.post("/messages/bulk", json={"ids": [mid], "action": "archive"})
    # Rewind the hold so the item is due now, then flush with a fake provider.
    with _s() as s:
        for q in s.exec(select(ActionQueue).where(ActionQueue.kind == "archive")):
            if mid in q.payload.get("ids", []):
                q.payload = {**q.payload, "not_before": "2000-01-01T00:00:00+00:00"}
                s.add(q)
        s.commit()

    class FakeProvider:
        def move(self, src, uid, dest): pass
        def delete(self, folder, uid): pass
        def close(self): pass

    import app.sync.engine as eng
    monkeypatch.setattr(eng, "build_provider", lambda acct: FakeProvider(), raising=False)
    from app.api.messages import process_action_queue
    process_action_queue()
    with _s() as s:
        assert s.get(Message, mid) is None                        # flushed for real
