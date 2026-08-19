"""Meeting mail: recover WHEN the meeting is when the mail itself never says.

Exchange / Microsoft 365 mailboxes with "Send meeting invitations in iCalendar
format" turned OFF (the POP/IMAP default) strip the text/calendar part out of
every invitation, update and cancellation and replace the body with an Outlook
Web Access link. What lands in the mailbox then carries no date and no time at
all - just "Canceled: IT Ticketing" in the subject and a wall of link text - so
the reader has nothing to show and the only way to learn when the meeting was is
to click through to webmail.

This recovers the time from two sources, best first:

  1. the mail's own iCalendar part, when it has one - those events are already
     parsed on body fetch and stored as CalendarEvent rows linked by message_id;

  2. the local calendar - the same meeting is nearly always already there via an
     ICS subscription or CalDAV, so we match it by normalised title around the
     mail's own date. That is an inference rather than a fact from the mail, so
     the result is tagged source="calendar" and the reader labels it that way.

The calendar lookup is deliberately NOT account-scoped: people subscribe to their
work calendar under whichever account they happened to set the feed up on, which
is often not the account the invitation was delivered to.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import CalendarEvent, Message

# Reply/forward noise, stripped before (and while) looking for a meeting prefix
# so "FW: Canceled: Standup" still reads as a cancellation of "Standup".
_NOISE = r"re|res|rv|sv|fw|fwd|odp|p[rř]edat"

# Subject prefixes Outlook/Google put on calendar mail, EN + CS. The groups don't
# overlap, so the first match wins.
_KINDS: tuple[tuple[str, str], ...] = (
    ("cancel", r"canceled|cancelled|zru[sš]eno|odvol[aá]no"),
    ("update", r"updated|aktualizov[aá]no|zm[eě]n[eě]no"),
    ("reply", r"accepted|p[rř]ijato|declined|odm[ií]tnuto|tentative|p[rř]edb[eě][zž]n[eě]"),
    ("invite", r"invitation|invite|pozv[aá]nka"),
)
_KIND_RES = tuple((kind, re.compile(rf"^\s*(?:{pat})\s*:\s*", re.IGNORECASE)) for kind, pat in _KINDS)
_NOISE_RE = re.compile(rf"^\s*(?:{_NOISE})\s*:\s*", re.IGNORECASE)
_ANY_PREFIX_RE = re.compile(
    rf"^\s*(?:{_NOISE}|" + "|".join(pat for _, pat in _KINDS) + r")\s*:\s*", re.IGNORECASE)

# Exchange's own footprint on a link-only calendar message: the OWA deep link to
# the calendar item, and the "turn on iCalendar format" tip it appends. Either one
# identifies the mail as calendar mail even with no ics part and no subject prefix.
_OWA_ITEM_RE = re.compile(
    r"""https?://[^\s"'<>]*?itemid=[^\s"'<>]*?path=/calendar/item[^\s"'<>]*""",
    re.IGNORECASE)
_OWA_MARK_RE = re.compile(r"path=/(?:calendar/item|options/popandimap)", re.IGNORECASE)

# How far around the mail's own date a calendar match is allowed to sit. Wide
# enough for an invitation sent months ahead, tight enough that an unrelated
# same-titled event years away can't be mistaken for this one.
_BACK = timedelta(days=30)
_FWD = timedelta(days=400)


def normalize_title(s: str) -> str:
    """A title stripped of every reply/meeting prefix, for matching mail against
    calendar. Outlook's published-calendar feeds carry the "Canceled: " prefix in
    the event SUMMARY itself, so both sides need the same treatment."""
    s = (s or "").replace(" ", " ")
    while True:
        stripped = _ANY_PREFIX_RE.sub("", s, count=1)
        if stripped == s:
            break
        s = stripped
    return re.sub(r"\s+", " ", s).strip(" .-:–—").casefold()


def classify(subject: str) -> str:
    """"cancel" | "update" | "reply" | "invite" from the subject prefix, else ""."""
    s = subject or ""
    for _ in range(4):  # "FW: RE: Canceled: ..." - peel the reply noise first
        stripped = _NOISE_RE.sub("", s, count=1)
        if stripped == s:
            break
        s = stripped
    for kind, rx in _KIND_RES:
        if rx.match(s):
            return kind
    return ""


def owa_url(html: str) -> str:
    """The Outlook Web Access link to the calendar item, if the body carries one."""
    m = _OWA_ITEM_RE.search(html or "")
    return m.group(0).replace("&amp;", "&") if m else ""


def is_link_only(html: str) -> bool:
    """True when this is Exchange's link-instead-of-invitation calendar mail."""
    return bool(_OWA_MARK_RE.search(html or ""))


def _utc_iso(v: datetime | None) -> str | None:
    """Stored times are UTC but SQLite hands them back naive - re-stamp the zone so
    the frontend's `new Date(...)` renders them in the viewer's local time."""
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _pick(cands: list[CalendarEvent], when: datetime) -> CalendarEvent | None:
    """The occurrence a mail sent at `when` is talking about: the first one that
    hasn't finished yet, else the most recent past one.

    Recurring series are why this needs a rule at all - a "Canceled: Standup" mail
    matches every daily occurrence, and the one that matters is the next one still
    to come, not the first in the series.
    """
    if not cands:
        return None
    live = sorted((e for e in cands if (e.end or e.start) >= when), key=lambda e: e.start)
    return live[0] if live else sorted(cands, key=lambda e: e.start)[-1]


def _match_calendar(session: Session, subject: str, when: datetime) -> tuple[CalendarEvent | None, int]:
    """Find this meeting in the local calendar by title, near the mail's own date."""
    key = normalize_title(subject)
    if len(key) < 3:
        return None, 0  # too generic to match on safely
    rows = session.exec(
        select(CalendarEvent).where(
            CalendarEvent.start != None,  # noqa: E711 - SQL NULL test, not identity
            CalendarEvent.start >= when - _BACK,
            CalendarEvent.start <= when + _FWD,
        )
    ).all()
    cands = [r for r in rows if normalize_title(r.summary) == key]
    return _pick(cands, when), len(cands)


def _card(kind: str, source: str, ev: CalendarEvent | None, occurrences: int,
          link: str, link_only: bool) -> dict:
    return {
        "kind": kind,
        "source": source,
        "summary": (ev.summary if ev else "") or "",
        "location": (ev.location if ev else "") or "",
        "organizer": (ev.organizer if ev else "") or "",
        "start": _utc_iso(ev.start if ev else None),
        "end": _utc_iso(ev.end if ev else None),
        "all_day": bool(ev.all_day) if ev else False,
        "event_id": ev.id if ev else None,
        "occurrences": occurrences,
        "owa_url": link,
        "link_only": link_only,
    }


def resolve(session: Session, msg: Message, html: str = "") -> dict | None:
    """Describe the meeting a mail is about, or None if it isn't meeting mail.

    Detection is deliberately conservative: an ics part or Exchange's OWA
    footprint is proof on its own, but a bare subject prefix ("Accepted: ...")
    only counts when the local calendar actually holds a matching meeting.
    """
    kind = classify(msg.subject or "")
    link = owa_url(html)
    link_only = bool(link) or is_link_only(html)
    when = msg.date or datetime.now(timezone.utc)
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)

    # 1. The mail brought its own iCalendar part.
    own = list(session.exec(
        select(CalendarEvent).where(CalendarEvent.message_id == msg.id,
                                    CalendarEvent.start != None)  # noqa: E711
    ))
    ev = _pick(own, when)
    if ev is not None:
        if not kind:
            kind = "cancel" if ev.cancelled else ("reply" if ev.method == "REPLY" else "invite")
        return _card(kind, "mail", ev, len(own), link, link_only)

    if not (link_only or kind):
        return None

    # 2. The same meeting, matched in the local calendar.
    ev, n = _match_calendar(session, msg.subject or "", when)
    if ev is not None:
        return _card(kind or "invite", "calendar", ev, n, link, link_only)

    # 3. Known to be meeting mail, but nothing anywhere says when. Saying so - and
    #    offering the link - still beats a wall of unexplained URL text.
    if link_only:
        return _card(kind or "invite", "none", None, 0, link, True)
    return None
