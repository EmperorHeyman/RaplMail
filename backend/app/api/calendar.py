"""Calendar: events extracted from meeting invites in your mail.

Events are pulled from text/calendar parts when a message body is fetched, and
can be back-filled in bulk via /calendar/scan (which fetches the raw invite
messages and parses their .ics). This is an email-derived calendar - no CalDAV.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_serializer
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
    color: str = ""

    # Event times are stored normalized to UTC, but SQLite drops the tzinfo so
    # they come back naive. Emit them with an explicit UTC offset so the frontend's
    # `new Date(...)` converts to the viewer's local zone (else it reads the UTC
    # wall-clock as local - the "2 hours behind" bug).
    @field_serializer("start", "end")
    def _as_utc(self, v: datetime | None):
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


def _synth_uid(account_id: int, ev: dict) -> str:
    if ev.get("uid"):
        return ev["uid"]
    # hashlib, NOT hash(): str hashing is salted per process, which would mint a
    # new uid every restart and duplicate the event on each rescan.
    import hashlib
    base = f"{ev.get('summary', '')}|{ev.get('start')}"
    return f"nouid:{hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]}"


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


def _to_utc_naive(v: datetime | None) -> datetime | None:
    """Match storage: SQLite drops tzinfo WITHOUT converting, so any tz-aware
    input must be normalized to UTC-naive first (same as SnoozeIn/send_at)."""
    if v is not None and v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


@router.get("", response_model=list[EventOut])
def list_events(start: datetime | None = None, end: datetime | None = None,
                session: Session = Depends(get_session)) -> list[CalendarEvent]:
    start, end = _to_utc_naive(start), _to_utc_naive(end)
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
    ics_events: int = 0
    ics_removed: int = 0
    error: str = ""


def _ics_uid(url: str, ev_uid: str) -> str:
    """Namespace an event UID per-feed so feeds never collide with each other or
    with mail-derived events."""
    import hashlib
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"ics:{h}:{ev_uid or hashlib.sha1(repr(ev_uid).encode()).hexdigest()[:8]}"


def _sync_ics_feeds(session: Session, acct_id: int, feeds: list[dict]) -> tuple[int, int]:
    """Fetch each ICS feed, upsert its events, and delete events that are no
    longer present in any feed (handles deletions). Each feed is {url, color}.
    Returns (upserted, removed)."""
    import hashlib

    from app.sync import caldav as dav
    from app.models import CalendarEvent
    seen: set[str] = set()
    ok_prefixes: list[str] = []   # "ics:<feedhash>:" for feeds that fetched OK
    google_ids_seen: set[str] = set()   # raw Google event ids present in any feed
    upserted = 0
    for feed in feeds:
        url = (feed.get("url") or "").strip()
        color = (feed.get("color") or "").strip()
        if not url:
            continue
        try:
            events = dav.fetch_ics(url)
        except Exception:
            continue  # one bad feed shouldn't break the rest (and don't prune its events)
        # This feed responded - its events are now authoritative for pruning.
        ok_prefixes.append(f"ics:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}:")
        for ev in events:
            if not ev.get("start"):
                continue
            raw_uid = ev.get("uid") or f"{ev.get('summary','')}|{ev.get('start')}"
            if "@google.com" in raw_uid:
                google_ids_seen.add(raw_uid.split("@")[0])
            uid = _ics_uid(url, raw_uid)
            seen.add(uid)
            row = session.exec(select(CalendarEvent).where(
                CalendarEvent.account_id == acct_id, CalendarEvent.uid == uid)).first()
            if row is None:
                row = CalendarEvent(account_id=acct_id, uid=uid, source="ics")
                session.add(row)
            row.source = "ics"
            row.color = color
            row.summary = ev.get("summary", "") or row.summary
            row.location = ev.get("location", "") or row.location
            row.description = ev.get("description", "") or row.description
            row.organizer = ev.get("organizer", "") or row.organizer
            row.start = ev.get("start")
            row.end = ev.get("end")
            row.all_day = bool(ev.get("all_day"))
            row.cancelled = bool(ev.get("cancelled"))
            upserted += 1
    # Delete ICS events that vanished - but ONLY for feeds that actually responded
    # this run. A feed that failed (network blip / temporary 5xx) must not have its
    # whole calendar wiped; its events are left untouched until it fetches again.
    removed = 0
    for row in session.exec(select(CalendarEvent).where(CalendarEvent.source == "ics")).all():
        from_ok_feed = any(row.uid.startswith(p) for p in ok_prefixes)
        if from_ok_feed and row.uid not in seen:
            session.delete(row)
            removed += 1
    # Drop our local "gcal:" placeholder once the same event arrives via the feed,
    # so an event created in RaplMail doesn't show twice after the feed catches up.
    for row in session.exec(select(CalendarEvent).where(CalendarEvent.source == "gcal")).all():
        gid = (row.uid or "")[5:]
        if gid and gid in google_ids_seen:
            session.delete(row)
            removed += 1
    session.flush()
    return upserted, removed


@router.post("/caldav/sync", response_model=CalDavResult)
async def caldav_sync(session: Session = Depends(get_session)) -> CalDavResult:
    """Pull events (CalDAV), contacts (CardDAV), and ICS feed subscriptions."""
    from app.models import Contact, Setting
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    cal_url = (cfg.get("caldavUrl") or "").strip()
    card_url = (cfg.get("carddavUrl") or "").strip()
    user = cfg.get("caldavUser") or ""
    pw = cfg.get("caldavPassword") or ""
    # Feeds may be legacy plain URL strings or {url, color} objects.
    ics_feeds: list[dict] = []
    for f in (cfg.get("icsFeeds") or []):
        if isinstance(f, str):
            f = {"url": f}
        if (f.get("url") or "").strip():
            ics_feeds.append({"url": f["url"].strip(), "color": (f.get("color") or "").strip()})
    if not cal_url and not card_url and not ics_feeds:
        return CalDavResult(error="No CalDAV/CardDAV URL or ICS feed configured.")

    from app.sync import caldav as dav
    acct_id = session.exec(select(Account.id)).first()
    if not acct_id:
        # Events are stored per account (FK enforced) - account_id 0 would just
        # fail every insert.
        return CalDavResult(error="Add a mail account first - calendar entries are stored per account.")
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
        if ics_feeds:
            res.ics_events, res.ics_removed = await run_in_threadpool(
                _sync_ics_feeds, session, acct_id, ics_feeds)
        session.commit()
    except Exception as exc:
        res.error = str(exc)
    return res


def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _ics_dt(dt: datetime, all_day: bool) -> str:
    if all_day:
        return dt.strftime("%Y%m%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_event_ics(uid, summary, start, end, all_day, location, description,
                     organizer, attendee, method="REQUEST", partstat="NEEDS-ACTION") -> str:
    """A minimal iMIP VEVENT. With METHOD:REQUEST + an ATTENDEE, Gmail/Outlook add
    it to the calendar and show an RSVP box - no API needed (RFC 6047). With
    METHOD:REPLY + a PARTSTAT it tells the organizer your accept/decline."""
    end = end or (start + (timedelta(days=1) if all_day else timedelta(hours=1)))
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = f"DTSTART;VALUE=DATE:{_ics_dt(start, True)}" if all_day else f"DTSTART:{_ics_dt(start, False)}"
    dtend = f"DTEND;VALUE=DATE:{_ics_dt(end, True)}" if all_day else f"DTEND:{_ics_dt(end, False)}"
    lines = [
        "BEGIN:VCALENDAR", "PRODID:-//RaplMail//Calendar//EN", "VERSION:2.0",
        f"METHOD:{method}", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:{uid}", f"DTSTAMP:{now}", dtstart, dtend,
        f"SUMMARY:{_ics_escape(summary)}",
    ]
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    rsvp_attr = ";RSVP=TRUE" if method == "REQUEST" else ""
    lines += [
        f"ORGANIZER:mailto:{organizer}",
        f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT={partstat}{rsvp_attr}:mailto:{attendee}",
        "SEQUENCE:0", "STATUS:CONFIRMED", "TRANSP:OPAQUE", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


# RSVP status -> iCalendar PARTSTAT
_PARTSTAT = {"accepted": "ACCEPTED", "declined": "DECLINED",
             "tentative": "TENTATIVE", "needsAction": "NEEDS-ACTION"}


def _bare_email(s: str) -> str:
    """Extract a bare address from 'Name <a@b>' / 'mailto:a@b' / 'a@b'."""
    s = (s or "").strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        s = m.group(1)
    return s.replace("mailto:", "").strip()


class CreateEventIn(BaseModel):
    account_id: int
    summary: str
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    location: str = ""
    description: str = ""


# --- Google Calendar (OAuth write) ------------------------------------------
_GCAL_KEY = "google_calendar"


def _gcal_bundle(store) -> dict | None:
    import json
    if not store.is_unlocked:
        return None
    raw = store.get(_GCAL_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@router.post("/google/connect")
async def google_calendar_connect(session: Session = Depends(get_session)) -> dict:
    """Run the Google OAuth flow (calendar scope) so events can be written
    directly to the user's Google Calendar - reliable, unlike the iMIP trick."""
    import json

    from app.core.security import get_secret_store
    from app.models import Setting
    from app.providers import oauth

    store = get_secret_store()
    if not store.is_unlocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock the vault first.")
    try:
        email, bundle = await run_in_threadpool(oauth.google_run_installed_flow, oauth.GCAL_SCOPES)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Google sign-in failed: {exc}") from exc
    store.set(_GCAL_KEY, json.dumps(bundle))
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    cfg["googleCalendarEmail"] = email
    if row is None:
        session.add(Setting(id=1, data=cfg))
    else:
        row.data = cfg
    session.commit()
    return {"connected": True, "email": email}


@router.get("/google/status")
def google_calendar_status(session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    from app.models import Setting
    store = get_secret_store()
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    connected = bool(_gcal_bundle(store))
    return {"connected": connected, "email": cfg.get("googleCalendarEmail", "")}


@router.post("/google/disconnect")
def google_calendar_disconnect(session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    from app.models import Setting
    store = get_secret_store()
    if store.is_unlocked:
        try:
            store.delete(_GCAL_KEY)
        except Exception:
            pass
    row = session.get(Setting, 1)
    if row and row.data and "googleCalendarEmail" in row.data:
        cfg = dict(row.data); cfg.pop("googleCalendarEmail", None); row.data = cfg
        session.commit()
    return {"connected": False}


@router.post("/create")
async def create_event(body: CreateEventIn, request: Request,
                       session: Session = Depends(get_session)) -> dict:
    """Create an event. If Google Calendar is connected (OAuth), write it there
    via the API (reliable). Otherwise fall back to the iMIP email trick. Always
    stored locally so it shows in RaplMail immediately."""
    acct = session.get(Account, body.account_id)
    if acct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    # Normalize tz-aware input to UTC: SQLite drops the offset UNTRANSLATED, and
    # EventOut re-labels stored times as UTC - an un-normalized "+02:00" would
    # display shifted. Kept tz-aware for the Google/iMIP writers below.
    if body.start.tzinfo is not None:
        body.start = body.start.astimezone(timezone.utc)
    if body.end is not None and body.end.tzinfo is not None:
        body.end = body.end.astimezone(timezone.utc)
    uid = f"raplmail-{uuid.uuid4().hex}@raplmail"
    # Store locally first so it appears immediately regardless of the write path.
    upsert_events(session, acct.id, None, [{
        "uid": uid, "summary": body.summary, "location": body.location,
        "description": body.description, "start": body.start, "end": body.end,
        "all_day": body.all_day, "status_raw": "CONFIRMED",
    }])
    row = session.exec(select(CalendarEvent).where(
        CalendarEvent.account_id == acct.id, CalendarEvent.uid == uid)).first()
    if row:
        row.source = "local"
        row.status = "accepted"
    session.commit()

    # Preferred path: write straight to Google Calendar via the API.
    from app.core.security import get_secret_store
    store = get_secret_store()
    bundle = _gcal_bundle(store)
    if bundle is not None:
        import json

        from app.sync import gcal
        try:
            _ev, bundle = await run_in_threadpool(
                gcal.insert_event, bundle, summary=body.summary, start=body.start,
                end=body.end, all_day=body.all_day, location=body.location,
                description=body.description)
            store.set(_GCAL_KEY, json.dumps(bundle))
            # Encode the Google event id in the local row's uid so we can delete it
            # later and dedupe it against the ICS feed when that catches up.
            gid = (_ev or {}).get("id") or ""
            if row and gid:
                row.uid = f"gcal:{gid}"
                row.source = "gcal"
                session.add(row)
                session.commit()
            return {"uid": row.uid if row else uid, "google": True, "sent": True}
        except Exception as exc:
            return {"uid": uid, "google": False, "sent": False,
                    "error": f"Google Calendar write failed: {exc}"}

    # Fallback: iMIP email trick (best-effort; unreliable for self-events).
    ics = _build_event_ics(uid, body.summary, body.start, body.end, body.all_day,
                           body.location, body.description, acct.email, acct.email)
    from html import escape as _esc
    payload = {
        "account_id": body.account_id, "from_addr": acct.email, "to": [acct.email],
        "subject": f"Invitation: {body.summary}",
        "html": f"<p>RaplMail event: <b>{_esc(body.summary)}</b></p>",
        "calendar_ics": ics, "calendar_method": "REQUEST",
    }
    sent = False
    try:
        from app.api.compose import _deliver_blocking
        await run_in_threadpool(_deliver_blocking, payload)
        sent = True
    except Exception:
        pass
    return {"uid": uid, "sent": sent, "google": False}


def _google_event_id(ev: CalendarEvent) -> str | None:
    """The Google Calendar event id for a row, if it maps to one - either an event
    we created (uid 'gcal:<id>') or a Google-feed event synced via ICS."""
    if (ev.uid or "").startswith("gcal:"):
        return ev.uid[5:]
    if ev.source == "ics" and "@google.com" in (ev.uid or ""):
        raw = ev.uid.split(":", 2)[-1]   # ics:<feedhash>:<rawuid>
        return raw.split("@")[0]
    return None


@router.delete("/{event_id}")
async def delete_event(event_id: int, session: Session = Depends(get_session)) -> dict:
    """Delete an event. If it lives on a connected Google Calendar (created here
    or synced from the feed), delete it there too; always remove the local row."""
    ev = session.get(CalendarEvent, event_id)
    if ev is None:
        return {"deleted": False}
    gid = _google_event_id(ev)
    if gid:
        from app.core.security import get_secret_store
        store = get_secret_store()
        bundle = _gcal_bundle(store)
        if bundle is not None:
            import json

            from app.sync import gcal
            try:
                bundle = await run_in_threadpool(gcal.delete_event, bundle, gid)
                store.set(_GCAL_KEY, json.dumps(bundle))
            except Exception:
                pass   # local delete still proceeds
    session.delete(ev)
    session.commit()
    return {"deleted": True, "google": bool(gid)}


@router.post("/{event_id}/rsvp", response_model=EventOut)
async def rsvp(event_id: int, body: RsvpIn, session: Session = Depends(get_session)) -> CalendarEvent:
    ev = session.get(CalendarEvent, event_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    if body.status not in ("accepted", "declined", "tentative", "needsAction"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid status")
    ev.status = body.status
    session.add(ev)
    session.commit()
    session.refresh(ev)

    # Tell the organizer (iMIP METHOD:REPLY) - otherwise "Accept/Decline" only
    # turned a local badge green and the organizer saw no response. Best-effort:
    # the local status is already saved if the email can't go out.
    acct = session.get(Account, ev.account_id)
    organizer = _bare_email(ev.organizer)
    me = (acct.email if acct else "").strip()
    if acct and organizer and me and organizer.lower() != me.lower() and body.status != "needsAction" and ev.start:
        ics = _build_event_ics(
            ev.uid or f"raplmail-{uuid.uuid4().hex}@raplmail", ev.summary, ev.start, ev.end,
            bool(ev.all_day), ev.location or "", ev.description or "",
            organizer=organizer, attendee=me, method="REPLY", partstat=_PARTSTAT[body.status],
        )
        verb = {"accepted": "Accepted", "declined": "Declined", "tentative": "Tentative"}[body.status]
        payload = {
            "account_id": ev.account_id, "from_addr": me, "to": [organizer],
            "subject": f"{verb}: {ev.summary or '(no title)'}",
            "html": f"<p>{verb} - {ev.summary or ''}</p>",
            "calendar_ics": ics, "calendar_method": "REPLY",
        }
        try:
            from app.api.compose import _deliver_blocking
            await run_in_threadpool(_deliver_blocking, payload)
        except Exception:
            pass
    return ev
