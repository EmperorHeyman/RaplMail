"""Calendar: events extracted from meeting invites in your mail.

Events are pulled from text/calendar parts when a message body is fetched, and
can be back-filled in bulk via /calendar/scan (which fetches the raw invite
messages and parses their .ics). This is an email-derived calendar — no CalDAV.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import verify_token
from app.core.db import get_engine, get_session
from app.models import Account, CalendarEvent, Folder, Message

router = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=[Depends(verify_token)])


class EventOut(BaseModel):
    id: int
    account_id: int
    message_id: int | None
    summary: str
    location: str
    organizer: str
    start: datetime | None
    end: datetime | None
    all_day: bool
    status: str
    cancelled: bool


def _synth_uid(account_id: int, ev: dict) -> str:
    if ev.get("uid"):
        return ev["uid"]
    base = f"{ev.get('summary', '')}|{ev.get('start')}"
    return f"nouid:{abs(hash(base))}"


def upsert_events(session: Session, account_id: int, message_id: int | None, events: list[dict]) -> int:
    """Insert/update extracted events. Dedup by (account_id, uid). Does not commit."""
    n = 0
    for ev in events:
        if not ev.get("start"):
            continue  # skip undated entries (e.g. todos)
        uid = _synth_uid(account_id, ev)
        row = session.exec(
            select(CalendarEvent).where(CalendarEvent.account_id == account_id, CalendarEvent.uid == uid)
        ).first()
        if row is None:
            row = CalendarEvent(account_id=account_id, uid=uid)
            session.add(row)
        row.message_id = message_id or row.message_id
        row.summary = ev.get("summary", "") or row.summary
        row.location = ev.get("location", "") or row.location
        row.description = ev.get("description", "") or row.description
        row.organizer = ev.get("organizer", "") or row.organizer
        row.start = ev.get("start")
        row.end = ev.get("end")
        row.all_day = bool(ev.get("all_day"))
        row.method = ev.get("method", "") or row.method
        if ev.get("cancelled"):
            row.cancelled = True
        n += 1
    session.flush()
    return n


@router.get("", response_model=list[EventOut])
def list_events(start: datetime | None = None, end: datetime | None = None,
                session: Session = Depends(get_session)) -> list[CalendarEvent]:
    q = select(CalendarEvent)
    if start is not None:
        q = q.where((CalendarEvent.end >= start) | (CalendarEvent.start >= start))
    if end is not None:
        q = q.where(CalendarEvent.start <= end)
    return list(session.exec(q.order_by(CalendarEvent.start)))


class ScanResult(BaseModel):
    scanned: int
    found: int


@router.post("/scan", response_model=ScanResult)
async def scan(limit: int = 80, session: Session = Depends(get_session)) -> ScanResult:
    limit = max(1, min(limit, 300))
    return await run_in_threadpool(_scan_blocking, limit)


def _scan_blocking(limit: int) -> ScanResult:
    from app.providers.pool import pool
    from app.sync.ics import extract_ics

    scanned = found = 0
    with Session(get_engine()) as session:
        msgs = list(session.exec(
            select(Message)
            .where(Message.category.in_(["invitations", "invitation_responses"]))
            .order_by(Message.date.desc()).limit(limit)
        ))
        for msg in msgs:
            already = session.exec(
                select(CalendarEvent.id).where(CalendarEvent.message_id == msg.id)
            ).first()
            if already:
                continue
            account = session.get(Account, msg.account_id)
            folder = session.get(Folder, msg.folder_id)
            if not account or not folder:
                continue
            scanned += 1
            try:
                raw = pool.fetch_raw(account, folder.path, msg.uid)
            except Exception:
                continue
            events = extract_ics(raw) if raw else []
            if events:
                found += upsert_events(session, msg.account_id, msg.id, events)
        session.commit()
    return ScanResult(scanned=scanned, found=found)


class RsvpIn(BaseModel):
    status: str  # accepted | declined | tentative | needsAction


class CalDavResult(BaseModel):
    events: int = 0
    contacts: int = 0
    error: str = ""


@router.post("/caldav/sync", response_model=CalDavResult)
async def caldav_sync(session: Session = Depends(get_session)) -> CalDavResult:
    """Pull events (CalDAV) and contacts (CardDAV) from the configured servers."""
    from app.models import Contact, Setting
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    cal_url = (cfg.get("caldavUrl") or "").strip()
    card_url = (cfg.get("carddavUrl") or "").strip()
    user = cfg.get("caldavUser") or ""
    pw = cfg.get("caldavPassword") or ""
    if not cal_url and not card_url:
        return CalDavResult(error="No CalDAV/CardDAV URL configured.")

    from app.sync import caldav as dav
    acct_id = session.exec(select(Account.id)).first() or 0
    res = CalDavResult()
    try:
        if cal_url:
            events = await run_in_threadpool(dav.fetch_events, cal_url, user, pw)
            res.events = upsert_events(session, acct_id, None, events)
        if card_url:
            cards = await run_in_threadpool(dav.fetch_contacts, card_url, user, pw)
            for c in cards:
                email = c.get("email", "")
                if not email:
                    continue
                existing = session.exec(select(Contact).where(Contact.email == email)).first()
                if existing is None:
                    session.add(Contact(email=email, name=c.get("name", ""), source="carddav"))
                    res.contacts += 1
                elif c.get("name") and not existing.name:
                    existing.name = c["name"]
        session.commit()
    except Exception as exc:
        res.error = str(exc)
    return res


@router.post("/{event_id}/rsvp", response_model=EventOut)
def rsvp(event_id: int, body: RsvpIn, session: Session = Depends(get_session)) -> CalendarEvent:
    ev = session.get(CalendarEvent, event_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    if body.status not in ("accepted", "declined", "tentative", "needsAction"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid status")
    ev.status = body.status
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev
