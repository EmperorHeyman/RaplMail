"""Full-history backfill: paging OLDER mail downward, and the UIDVALIDITY-reset
purge. The forward sync only grabs the newest window; backfill must walk the rest
of the mailbox into the cache without gaps and stop cleanly at the bottom.

These exercise the correctness-critical logic against a fake in-memory provider
(no live IMAP), matching how test_devicesync avoids a real server."""
from datetime import datetime

import pytest
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, Folder, Message
from app.providers.base import HeaderInfo
from app.sync.engine import HEADERS_PER_FOLDER_LIMIT, SyncManager


def _s():
    return Session(get_engine())


@pytest.fixture(autouse=True)
def _clean_bf_accounts(client):
    """The test DB is shared across the session; these tests insert up to ~1k
    messages, which would pollute other files' scans (e.g. embeddings). Tear down
    every bf* account and its mail after each test regardless of pass/fail."""
    yield
    from sqlalchemy import delete as sa_delete

    from app.models import MessageState
    with _s() as s:
        ids = [a.id for a in s.exec(select(Account).where(Account.email.like("bf%@example.com")))]
        for aid in ids:
            s.exec(sa_delete(Message).where(Message.account_id == aid))
            s.exec(sa_delete(MessageState).where(MessageState.account_id == aid))
            s.exec(sa_delete(Folder).where(Folder.account_id == aid))
            s.exec(sa_delete(Account).where(Account.id == aid))
        s.commit()


class _FakeProvider:
    """Serves headers for a fixed set of UIDs with the same range+newest-limit
    semantics as the real IMAP provider."""
    def __init__(self, uids, uidvalidity=1):
        self._uids = sorted(uids)
        self._uidvalidity = uidvalidity

    def folder_uidvalidity(self, path):
        return self._uidvalidity

    def fetch_headers(self, path, min_uid=1, max_uid=None, limit=None):
        sel = [u for u in self._uids if u >= min_uid and (max_uid is None or u <= max_uid)]
        if limit:
            sel = sorted(sel)[-limit:]
        return [HeaderInfo(uid=u, message_id=f"<m{u}@x>", subject=f"s{u}",
                           from_addr="a@b.com", from_name="A", date=datetime(2024, 1, 1))
                for u in sel]


def _mgr():
    # The hub is unused by the backfill methods; a bare object is enough.
    return SyncManager(hub=object())


def _mk_account_folder(email, uidvalidity=None):
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="INBOX", path="INBOX", uidvalidity=uidvalidity)
        s.add(folder); s.commit(); s.refresh(folder)
        return acct.id, folder.id


def test_backfill_pages_all_older_mail(client):
    acct_id, folder_id = _mk_account_folder("bf1@example.com")
    # Simulate the forward sync already holding the newest window: store the top
    # `limit` UIDs, leaving 1..(N-limit) to be backfilled.
    total = HEADERS_PER_FOLDER_LIMIT * 2 + 37   # 1037 with limit 500
    provider = _FakeProvider(range(1, total + 1))
    top = list(range(total - HEADERS_PER_FOLDER_LIMIT + 1, total + 1))
    with _s() as s:
        acct = s.get(Account, acct_id); folder = s.get(Folder, folder_id)
        for u in top:
            s.add(Message(account_id=acct.id, folder_id=folder.id, uid=u,
                          message_id=f"<m{u}@x>", from_addr="a@b.com", subject=f"s{u}"))
        s.commit()

    mgr = _mgr()
    # Page window by window until the folder reports done.
    with _s() as s:
        acct = s.get(Account, acct_id)
        for _ in range(20):   # generous cap; should finish in ~2 windows
            folder = s.get(Folder, folder_id)
            if folder.backfill_done:
                break
            mgr._backfill_folder(s, acct, folder, provider)
            s.commit()

    with _s() as s:
        folder = s.get(Folder, folder_id)
        assert folder.backfill_done is True
        count = len(s.exec(select(Message).where(Message.folder_id == folder_id)).all())
        assert count == total, f"expected every message cached, got {count}/{total}"


def test_backfill_marks_empty_folder_done(client):
    # An empty folder (no mail at all) must be marked done, not left pending -
    # otherwise it holds overall progress below 100% forever (the "stuck at 44/69"
    # bug: empty Trash/Junk/Drafts folders never completing).
    acct_id, folder_id = _mk_account_folder("bf2@example.com")
    provider = _FakeProvider(range(1, 50))
    mgr = _mgr()
    with _s() as s:
        acct = s.get(Account, acct_id); folder = s.get(Folder, folder_id)
        n = mgr._backfill_folder(s, acct, folder, provider)
        s.commit()
    assert n == 0
    with _s() as s:
        assert s.get(Folder, folder_id).backfill_done is True   # empty → done, unblocks progress


def test_uidvalidity_change_purges_and_resyncs(client):
    # A folder whose server UIDVALIDITY changed must have its stale rows purged.
    acct_id, folder_id = _mk_account_folder("bf3@example.com", uidvalidity=100)
    with _s() as s:
        acct = s.get(Account, acct_id); folder = s.get(Folder, folder_id)
        folder.backfill_done = True; folder.backfill_min_uid = 1; s.add(folder)
        for u in (1, 2, 3):
            s.add(Message(account_id=acct.id, folder_id=folder.id, uid=u,
                          message_id=f"<old{u}@x>", from_addr="a@b.com", subject="old"))
        s.commit()

    provider = _FakeProvider(range(1, 10), uidvalidity=999)   # reset!
    mgr = _mgr()
    with _s() as s:
        folder = s.get(Folder, folder_id)
        mgr._check_uidvalidity(s, folder, provider)
        s.commit()

    with _s() as s:
        folder = s.get(Folder, folder_id)
        assert folder.uidvalidity == 999
        assert folder.backfill_done is False and folder.backfill_min_uid is None
        assert s.exec(select(Message).where(Message.folder_id == folder_id)).all() == []
