"""POST /messages/move - move messages to an arbitrary folder (drag-to-folder).

The endpoint only queues the move + hides the rows optimistically; the real IMAP
move runs in the background (and is skipped here since the test secret store is
locked), so we assert the queued/hidden DB state rather than a server round-trip.
"""
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, ActionQueue, Folder, FolderRole, Message


def _s():
    return Session(get_engine())


_n = 0


def _seed(same_account=True):
    """Seed an account with an inbox + a destination folder + one inbox message.
    When same_account is False the destination lives on a DIFFERENT account (an
    IMAP move can't cross accounts). Returns (message_id, dest_folder_id)."""
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"move{_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        inbox = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(inbox); s.commit(); s.refresh(inbox)
        dest_acct_id = acct.id
        if not same_account:
            other = Account(email=f"move{_n}b@example.com"); s.add(other); s.commit(); s.refresh(other)
            dest_acct_id = other.id
        dest = Folder(account_id=dest_acct_id, name="Projects", path="Projects", role=FolderRole.other)
        s.add(dest); s.commit(); s.refresh(dest)
        m = Message(account_id=acct.id, folder_id=inbox.id, uid=1000 + _n,
                    message_id=f"<move-{_n}>", from_addr="x@ex.com", subject="hi")
        s.add(m); s.commit(); s.refresh(m)
        return m.id, dest.id


def test_move_queues_and_hides(client):
    mid, did = _seed()
    r = client.post("/messages/move", json={"ids": [mid], "folder_id": did})
    assert r.status_code == 200
    assert r.json()["queued"] == 1
    with _s() as s:
        assert s.get(Message, mid).pending_action == "move"     # hidden optimistically
        q = s.exec(select(ActionQueue).where(ActionQueue.kind == "move")).all()
        assert any(a.payload.get("folder_id") == did and mid in a.payload.get("ids", []) for a in q)
    # Hidden from the normal listing.
    assert all(row["id"] != mid for row in client.get("/messages?limit=500").json())


def test_move_missing_folder_404(client):
    mid, _ = _seed()
    r = client.post("/messages/move", json={"ids": [mid], "folder_id": 999999})
    assert r.status_code == 404
    with _s() as s:
        assert s.get(Message, mid).pending_action == ""         # untouched


def test_move_skips_cross_account(client):
    mid, did = _seed(same_account=False)
    r = client.post("/messages/move", json={"ids": [mid], "folder_id": did})
    assert r.status_code == 200
    assert r.json()["queued"] == 0
    with _s() as s:
        assert s.get(Message, mid).pending_action == ""         # not hidden


def test_move_skips_already_in_folder(client):
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"movesame{_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        inbox = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(inbox); s.commit(); s.refresh(inbox)
        m = Message(account_id=acct.id, folder_id=inbox.id, uid=5000 + _n,
                    message_id=f"<movesame-{_n}>", from_addr="x@ex.com", subject="hi")
        s.add(m); s.commit(); s.refresh(m)
        mid, did = m.id, inbox.id
    r = client.post("/messages/move", json={"ids": [mid], "folder_id": did})
    assert r.status_code == 200 and r.json()["queued"] == 0
    with _s() as s:
        assert s.get(Message, mid).pending_action == ""


def test_flush_move_to_deletes_row_after_move(client, monkeypatch):
    """The background flush should move via the provider then drop the local row
    (sync re-materializes it under the destination). Provider is faked so no IMAP."""
    from app.api import messages as mod
    mid, did = _seed()

    calls = {}

    class FakeProvider:
        def move(self, src, uid, dest): calls["move"] = (src, uid, dest)
        def close(self): calls["closed"] = True

    monkeypatch.setattr(mod, "build_provider", lambda acct: FakeProvider(), raising=False)
    # build_provider is imported inside the function from app.sync.engine - patch there too.
    import app.sync.engine as eng
    monkeypatch.setattr(eng, "build_provider", lambda acct: FakeProvider(), raising=False)

    mod._flush_move_to([mid], did)
    assert calls.get("move") and calls["move"][2] == "Projects"   # moved to dest path
    assert calls.get("closed") is True
    with _s() as s:
        assert s.get(Message, mid) is None                        # local row dropped
