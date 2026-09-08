"""Regressions for the "sync says it's done but no mail arrives" class of bug.

Several separate causes, all covered here:

* a message whose Date header is missing or unparseable was stored with
  ``date=NULL``, which sorts below everything in the date-ordered list - the mail
  was fetched, but invisible (this is what hid sent copies);
* the flag resync now heals such rows from INTERNALDATE;
* a manual sync must run the requested account immediately instead of only
  nudging the poll loop, and must never double-sync a mailbox already in flight;
* the flag reconcile - the most expensive part of a cycle - stays authoritative
  for the inbox and Sent but is throttled everywhere else, so a cycle finishes
  fast enough that the fallback poll still catches mail promptly.

All against fakes - no live IMAP.
"""
from datetime import datetime

import pytest
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, Folder, Message
from app.providers.imap_smtp import Auth, ImapSmtpProvider
from app.sync.engine import HEADERS_PER_FOLDER_LIMIT, SyncManager


def _s():
    return Session(get_engine())


@pytest.fixture(autouse=True)
def _clean(client):
    yield
    from sqlalchemy import delete as sa_delete

    from app.models import MessageState
    with _s() as s:
        ids = [a.id for a in s.exec(select(Account).where(Account.email.like("lat%@example.com")))]
        for aid in ids:
            s.exec(sa_delete(Message).where(Message.account_id == aid))
            s.exec(sa_delete(MessageState).where(MessageState.account_id == aid))
            s.exec(sa_delete(Folder).where(Folder.account_id == aid))
            s.exec(sa_delete(Account).where(Account.id == aid))
        s.commit()


# --- date fallback ---------------------------------------------------------
class _FakeEnvelope:
    def __init__(self, date):
        self.date = date
        self.from_ = None
        self.to = None
        self.cc = None
        self.subject = b"no date header"
        self.message_id = b"<nodate@x>"
        self.in_reply_to = None


class _FakeClient:
    """Just enough IMAPClient surface for fetch_headers/fetch_flags_dates."""
    def __init__(self, envelope_date, internaldate):
        self._env_date = envelope_date
        self._internaldate = internaldate

    def select_folder(self, path, readonly=False):
        return {b"UIDVALIDITY": 1}

    def search(self, criteria):
        return [7]

    def fetch(self, uids, what):
        info = {
            b"FLAGS": (b"\\Seen",),
            b"RFC822.SIZE": 123,
            b"BODYSTRUCTURE": None,
            b"INTERNALDATE": self._internaldate,
        }
        if "ENVELOPE" in what:
            info[b"ENVELOPE"] = _FakeEnvelope(self._env_date)
        return {7: info}


def _provider(envelope_date, internaldate):
    p = ImapSmtpProvider(Auth("plain", "u", "p"), "h", 993, "h", 587)
    p._client = _FakeClient(envelope_date, internaldate)
    return p


def test_missing_date_header_falls_back_to_internaldate():
    # No parsable Date header: imapclient hands back envelope.date=None. Storing
    # that as NULL buries the row at the bottom of every date-sorted list.
    arrival = datetime(2026, 8, 24, 11, 5, 0)
    headers = _provider(None, arrival).fetch_headers("INBOX")
    assert len(headers) == 1
    assert headers[0].date == arrival


def test_envelope_date_still_wins_when_present():
    sent_at = datetime(2026, 8, 20, 9, 0, 0)
    arrival = datetime(2026, 8, 24, 11, 5, 0)
    headers = _provider(sent_at, arrival).fetch_headers("INBOX")
    assert headers[0].date == sent_at   # the author's Date, not the server's


def test_flag_resync_heals_a_dateless_row():
    arrival = datetime(2026, 8, 24, 11, 5, 0)
    with _s() as s:
        acct = Account(email="lat1@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="sent", path="sent", role="sent")
        s.add(folder); s.commit(); s.refresh(folder)
        s.add(Message(account_id=acct.id, folder_id=folder.id, uid=7,
                      message_id="<nodate@x>", from_addr="a@b.com", subject="s", date=None))
        s.commit()
        acct_id, folder_id = acct.id, folder.id

    mgr = SyncManager(hub=object())
    with _s() as s:
        mgr._resync_flags(s, s.get(Account, acct_id), s.get(Folder, folder_id),
                          _provider(None, arrival))
        s.commit()

    with _s() as s:
        healed = s.exec(select(Message).where(Message.folder_id == folder_id)).one()
        assert healed.date == arrival, "a dateless row must be given its arrival time"


# --- manual sync actually syncs -------------------------------------------
# pytest-asyncio isn't installed here, so these drive their own loop.
def test_manual_sync_runs_the_account_now():
    """request_account_sync must start that account's sync straight away, not
    just set the wake flag (which is only read at the end of the current cycle)."""
    import asyncio

    started: list[int] = []

    async def scenario():
        mgr = SyncManager(hub=object())
        mgr._loop_ref = asyncio.get_running_loop()

        async def _record(account_id):
            started.append(account_id)

        mgr.sync_account = _record
        mgr.request_account_sync(42)
        await asyncio.sleep(0)          # let the spawned task run
        assert not mgr._wake.is_set(), "no need to wake the loop; the sync already ran"

    asyncio.run(scenario())
    assert started == [42]


def test_inflight_account_is_not_synced_twice():
    """A second trigger for a mailbox already syncing must be folded into a
    follow-up pass instead of opening a second connection to the same mailbox."""
    import asyncio

    async def scenario():
        mgr = SyncManager(hub=object())
        mgr._loop_ref = asyncio.get_running_loop()
        mgr._inflight.add(9)
        mgr.request_account_sync(9)
        await asyncio.sleep(0)
        assert not mgr._tasks, "must not spawn a duplicate sync"
        assert mgr._wake.is_set(), "a follow-up pass must still be scheduled"

    asyncio.run(scenario())


# --- flag reconcile throttle ----------------------------------------------
class _CountingProvider:
    """Counts flag reconciles; returns nothing so no rows are touched."""
    def __init__(self):
        self.calls = 0

    def fetch_flags_dates(self, path, uids):
        self.calls += 1
        return {}


def _one_folder(email, role):
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name=role, path=role, role=role)
        s.add(folder); s.commit(); s.refresh(folder)
        s.add(Message(account_id=acct.id, folder_id=folder.id, uid=1,
                      message_id="<a@x>", from_addr="a@b.com", subject="s",
                      date=datetime(2026, 8, 24, 10, 0, 0)))
        s.commit()
        return acct.id, folder.id


def test_inbox_flags_reconcile_every_sync():
    acct_id, folder_id = _one_folder("lat2@example.com", "inbox")
    mgr, prov = SyncManager(hub=object()), _CountingProvider()
    with _s() as s:
        for _ in range(3):
            mgr._resync_flags(s, s.get(Account, acct_id), s.get(Folder, folder_id), prov)
    assert prov.calls == 3, "the inbox must stay authoritative on every cycle"


def test_other_folders_flags_are_throttled():
    # A mailbox can have dozens of these; reconciling every one every 60s is what
    # made a cycle take minutes and delayed new mail.
    acct_id, folder_id = _one_folder("lat3@example.com", "other")
    mgr, prov = SyncManager(hub=object()), _CountingProvider()
    with _s() as s:
        for _ in range(3):
            mgr._resync_flags(s, s.get(Account, acct_id), s.get(Folder, folder_id), prov)
    assert prov.calls == 1, "should reconcile once, then wait out the interval"

    # Once the interval has passed it reconciles again.
    mgr._last_flag_sync[folder_id] -= mgr.FLAG_RESYNC_OTHER_SECONDS + 1
    with _s() as s:
        mgr._resync_flags(s, s.get(Account, acct_id), s.get(Folder, folder_id), prov)
    assert prov.calls == 2


# --- catching up must never skip UIDs ------------------------------------
class _RangeProvider:
    """A mailbox holding a fixed UID set, with the same range semantics as the
    real provider. Records how many FETCH round trips the sync made."""
    def __init__(self, uids):
        self._uids = sorted(uids)
        self.fetches = 0

    def folder_uidvalidity(self, path):
        return 1

    def search_uids(self, path, min_uid=1, max_uid=None):
        return [u for u in self._uids
                if u >= min_uid and (max_uid is None or u <= max_uid)]

    def fetch_headers_for(self, path, uids):
        self.fetches += 1
        from app.providers.base import HeaderInfo
        return [HeaderInfo(uid=u, message_id=f"<m{u}@x>", subject=f"s{u}",
                           from_addr="a@b.com", from_name="A",
                           date=datetime(2026, 8, 24, 10, 0, 0)) for u in uids]

    def fetch_flags_dates(self, path, uids):
        return {}


def _archive_folder(email):
    # role=archive keeps the test on the UID logic: no rules, screening, or
    # notification previews run for it.
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="archive", path="archive",
                   role="archive", uidvalidity=1)
        s.add(f); s.commit(); s.refresh(f)
        return acct.id, f.id


def _cached_uids(folder_id):
    with _s() as s:
        return sorted(m.uid for m in
                      s.exec(select(Message).where(Message.folder_id == folder_id)).all())


def _run_sync(mgr, acct_id, folder_id, provider):
    with _s() as s:
        mgr._sync_folder(s, s.get(Account, acct_id), s.get(Folder, folder_id), provider, [])
        s.commit()


def test_catchup_leaves_no_uid_gap():
    """>1 window of new mail since the last sync must ALL be fetched. Taking the
    newest window only advanced the cursor past the rest, and nothing ever went
    back for it: the forward sync only looks above the cursor and the history
    backfill only pages below the oldest cached UID."""
    acct_id, folder_id = _archive_folder("lat4@example.com")
    with _s() as s:
        s.add(Message(account_id=acct_id, folder_id=folder_id, uid=1000,
                      message_id="<m1000@x>", from_addr="a@b.com", subject="s",
                      date=datetime(2026, 8, 1, 10, 0, 0)))
        s.commit()

    provider = _RangeProvider(range(1, 2001))    # server went 1000 -> 2000
    _run_sync(SyncManager(hub=object()), acct_id, folder_id, provider)

    cached = set(_cached_uids(folder_id))
    missing = [u for u in range(1001, 2001) if u not in cached]
    assert not missing, f"{len(missing)} UIDs were skipped, starting at {missing[:1]}"
    assert provider.fetches == 2, "1000 messages should be two FETCH round trips"


def test_first_sync_takes_the_newest_window_only():
    """With nothing cached, only the newest window is pulled - the history
    backfill pages downward from there, which is what it's for."""
    acct_id, folder_id = _archive_folder("lat5@example.com")
    provider = _RangeProvider(range(1, 2001))
    _run_sync(SyncManager(hub=object()), acct_id, folder_id, provider)

    cached = _cached_uids(folder_id)
    assert len(cached) == HEADERS_PER_FOLDER_LIMIT
    assert cached[-1] == 2000 and cached[0] == 2000 - HEADERS_PER_FOLDER_LIMIT + 1


def test_bounded_catchup_advances_contiguously():
    """When even the catch-up ceiling is exceeded, the OLDEST are taken so the
    cursor stays contiguous and the next cycle resumes exactly where this one
    stopped. Taking the newest would strand everything below them forever."""
    acct_id, folder_id = _archive_folder("lat6@example.com")
    with _s() as s:
        s.add(Message(account_id=acct_id, folder_id=folder_id, uid=1,
                      message_id="<m1@x>", from_addr="a@b.com", subject="s",
                      date=datetime(2026, 8, 1, 10, 0, 0)))
        s.commit()

    mgr = SyncManager(hub=object())
    mgr.CATCHUP_LIMIT = 40                      # stand-in for the real 5000
    provider = _RangeProvider(range(1, 302))    # 300 behind, ceiling 40

    _run_sync(mgr, acct_id, folder_id, provider)
    assert _cached_uids(folder_id) == list(range(1, 42)), "should take the oldest 40"

    # Next cycle resumes at the cursor - no hole left behind it.
    _run_sync(mgr, acct_id, folder_id, provider)
    assert _cached_uids(folder_id) == list(range(1, 82))
