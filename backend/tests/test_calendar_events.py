"""Calendar event store: cancellation propagation across UID namespaces, the
no-ghost rule for CANCEL notices, and delete tombstones (cleared events must
not resurrect on the next mail scan / feed sync)."""
from datetime import datetime

from sqlmodel import Session, select

from app.api import calendar as cal
from app.core.db import get_engine
from app.models import Account, CalendarEvent


def _s():
    return Session(get_engine())


def _blob_backup():
    from app.api.settings import _get_blob
    with _s() as s:
        return _get_blob(s)


def _blob_restore(before):
    from app.api.settings import _set_blob
    with _s() as s:
        _set_blob(s, before)


def _mk_account(s, email):
    acct = Account(email=email)
    s.add(acct); s.commit(); s.refresh(acct)
    return acct.id


def _wipe_events():
    with _s() as s:
        for r in s.exec(select(CalendarEvent)).all():
            s.delete(r)
        s.commit()


def test_cancel_strikes_copies_across_namespaces_and_accounts(client):
    before = _blob_backup()
    _wipe_events()
    try:
        with _s() as s:
            a1 = _mk_account(s, "cal-a1@example.com")
            a2 = _mk_account(s, "cal-a2@example.com")
            start = datetime(2026, 8, 1, 10)
            # The same meeting stored three ways: mail invite in account 1,
            # a per-feed namespaced copy, and per-occurrence rows of the series.
            s.add(CalendarEvent(account_id=a1, uid="MTG1@outlook.com", summary="Standup", start=start))
            s.add(CalendarEvent(account_id=a2, uid="ics:abcdef1234:MTG1@outlook.com", summary="Standup",
                                start=start, source="ics"))
            s.add(CalendarEvent(account_id=a1, uid="MTG1@outlook.com_20260801T100000Z", summary="Standup",
                                start=start))
            # An unrelated event must stay untouched.
            s.add(CalendarEvent(account_id=a1, uid="OTHER@outlook.com", summary="Lunch", start=start))
            s.commit()

        # The CANCEL arrives in account 2, where no row has that exact uid.
        with _s() as s:
            n_before = len(s.exec(select(CalendarEvent)).all())
            cal.upsert_events(s, a2, None, [{
                "uid": "MTG1@outlook.com", "summary": "Canceled: Standup",
                "start": start, "method": "CANCEL", "cancelled": True,
            }])
            s.commit()
        with _s() as s:
            rows = s.exec(select(CalendarEvent)).all()
            assert len(rows) == n_before   # no ghost "Canceled: ..." row inserted
            by_uid = {r.uid: r for r in rows}
            assert by_uid["MTG1@outlook.com"].cancelled is True
            assert by_uid["ics:abcdef1234:MTG1@outlook.com"].cancelled is True
            assert by_uid["MTG1@outlook.com_20260801T100000Z"].cancelled is True
            assert by_uid["OTHER@outlook.com"].cancelled is False
    finally:
        _wipe_events()
        _blob_restore(before)


def test_cleared_uid_tombstone_blocks_reinsert(client):
    before = _blob_backup()
    _wipe_events()
    try:
        with _s() as s:
            a1 = _mk_account(s, "cal-tomb@example.com")
            start = datetime(2026, 8, 2, 9)
            # Live event first, then its CANCEL notice flags it (a brand-new
            # cancelled event is never inserted - the no-ghost rule).
            cal.upsert_events(s, a1, None, [
                {"uid": "GONE@outlook.com", "summary": "Old mtg", "start": start},
                {"uid": "KEEP@outlook.com", "summary": "Keep me", "start": start},
            ])
            cal.upsert_events(s, a1, None, [
                {"uid": "GONE@outlook.com", "summary": "Canceled: Old mtg", "start": start,
                 "method": "CANCEL", "cancelled": True},
            ])
            s.commit()

        # Bulk-clear removes the cancelled row and tombstones its uid.
        with _s() as s:
            res = cal.clear_cancelled(session=s)
        assert res.deleted == 1
        with _s() as s:
            uids = {r.uid for r in s.exec(select(CalendarEvent)).all()}
            assert uids == {"KEEP@outlook.com"}

        # A rescan of the original invite must NOT resurrect the event -
        # neither via the mail path nor via a namespaced feed copy.
        with _s() as s:
            cal.upsert_events(s, a1, None, [
                {"uid": "GONE@outlook.com", "summary": "Old mtg", "start": start},
            ])
            s.commit()
        with _s() as s:
            assert {r.uid for r in s.exec(select(CalendarEvent)).all()} == {"KEEP@outlook.com"}
            assert "GONE@outlook.com" in cal._cleared_uids(s)
    finally:
        _wipe_events()
        _blob_restore(before)


def test_single_delete_tombstones_uid(client):
    before = _blob_backup()
    _wipe_events()
    try:
        with _s() as s:
            a1 = _mk_account(s, "cal-del@example.com")
            cal.upsert_events(s, a1, None, [
                {"uid": "DEL@outlook.com", "summary": "Delete me", "start": datetime(2026, 8, 3, 9)},
            ])
            s.commit()
            row_id = s.exec(select(CalendarEvent.id).where(CalendarEvent.uid == "DEL@outlook.com")).first()
        r = client.delete(f"/calendar/{row_id}")
        assert r.status_code == 200 and r.json()["deleted"] is True
        with _s() as s:
            assert "DEL@outlook.com" in cal._cleared_uids(s)
            # Rescan of the invite mail can't bring it back.
            cal.upsert_events(s, a1, None, [
                {"uid": "DEL@outlook.com", "summary": "Delete me", "start": datetime(2026, 8, 3, 9)},
            ])
            s.commit()
            assert s.exec(select(CalendarEvent).where(CalendarEvent.uid == "DEL@outlook.com")).first() is None
    finally:
        _wipe_events()
        _blob_restore(before)
