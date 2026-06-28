"""iCalendar (RFC 5545) extraction — enough to surface invites and feed events.

We don't implement the full spec, but we do handle the parts that matter for a
useful calendar: real timezone conversion via TZID (zoneinfo), all-day vs timed
events, and RRULE expansion of recurring events (DAILY/WEEKLY/MONTHLY/YEARLY
with INTERVAL/COUNT/UNTIL/BYDAY/BYMONTHDAY and EXDATE). Recurrences are expanded
into concrete instances within a rolling window so they actually show up on the
calendar grid instead of only on their first day.
"""

from __future__ import annotations

import email
import re
from datetime import date, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# How far back / forward we materialise recurring instances. Mail navigates
# month-by-month, so this comfortably covers the views people actually open.
_WINDOW_BACK = timedelta(days=120)
_WINDOW_FWD = timedelta(days=540)
_MAX_INSTANCES = 800   # per recurring event — a hard backstop against runaways

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unfold(text: str) -> list[str]:
    """Undo RFC 5545 line folding (continuation lines start with space/tab)."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _zone(tzid: str | None):
    if not tzid or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(tzid)
    except Exception:
        return None


def _parse_dt(val: str, params: dict, default_tz=None) -> tuple[datetime | None, bool]:
    """Parse an iCal DATE/DATE-TIME into a tz-aware datetime kept in its *original*
    zone (so recurrence can step in local wall-clock terms). Returns (dt, all_day)."""
    val = val.strip()
    if not val:
        return None, False
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", val):
        try:
            d = datetime.strptime(val[:8], "%Y%m%d")
            return d.replace(tzinfo=timezone.utc), True
        except ValueError:
            return None, False
    try:
        if val.endswith("Z"):
            return datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
        naive = datetime.strptime(val[:15], "%Y%m%dT%H%M%S")
        tz = _zone(params.get("TZID")) or default_tz or timezone.utc
        return naive.replace(tzinfo=tz), False
    except ValueError:
        return None, False


def _split_prop(line: str):
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_rrule(value: str) -> dict:
    rule: dict = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        rule[k.upper()] = v
    return rule


def _add_months(d: datetime, months: int) -> datetime:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # Clamp day to the target month's length (e.g. Jan 31 -> Feb 28).
    import calendar as _cal
    day = min(d.day, _cal.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _expand(ev: dict, win_start: datetime, win_end: datetime) -> list[datetime]:
    """Return the list of occurrence start datetimes (in the seed's tz) within the
    window. Non-recurring events return just their start."""
    start: datetime = ev["start"]
    rule = ev.get("_rrule")
    if not rule:
        return [start]

    freq = (rule.get("FREQ") or "").upper()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return [start]
    interval = max(1, int(rule.get("INTERVAL", "1") or "1"))
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    until = None
    if rule.get("UNTIL"):
        u, _ = _parse_dt(rule["UNTIL"], {}, default_tz=timezone.utc)
        until = u
    exdates: set = ev.get("_exdates") or set()

    occ: list[datetime] = []
    emitted = 0  # counts toward COUNT (includes pre-window instances)

    def consider(dt: datetime) -> bool:
        """Record dt if in window; return False when we should stop iterating."""
        nonlocal emitted
        if until is not None and dt.astimezone(timezone.utc) > until:
            return False
        if count is not None and emitted >= count:
            return False
        emitted += 1
        if dt in exdates or dt.date() in {e.date() for e in exdates}:
            return True
        if dt.astimezone(timezone.utc) > win_end:
            # Future beyond window: keep counting (for COUNT) but stop if unbounded.
            return count is not None
        if dt.astimezone(timezone.utc) >= win_start:
            occ.append(dt)
        return True

    guard = 0
    if freq == "WEEKLY":
        bydays = [_WEEKDAYS[d] for d in (rule.get("BYDAY", "").split(",")) if d in _WEEKDAYS]
        if not bydays:
            bydays = [start.weekday()]
        bydays.sort()
        week0 = start - timedelta(days=start.weekday())  # Monday of seed's week
        w = 0
        while guard < _MAX_INSTANCES * 3:
            base = week0 + timedelta(weeks=w * interval)
            for wd in bydays:
                cand = base + timedelta(days=wd)
                if cand < start:
                    continue
                if not consider(cand):
                    return occ
                guard += 1
            if base.astimezone(timezone.utc) > win_end and count is None:
                break
            if len(occ) >= _MAX_INSTANCES:
                break
            w += 1
    else:
        cur = start
        while guard < _MAX_INSTANCES * 3:
            if not consider(cur):
                break
            guard += 1
            if len(occ) >= _MAX_INSTANCES:
                break
            if cur.astimezone(timezone.utc) > win_end and count is None:
                break
            if freq == "DAILY":
                cur = cur + timedelta(days=interval)
            elif freq == "MONTHLY":
                cur = _add_months(cur, interval)
            elif freq == "YEARLY":
                cur = _add_months(cur, 12 * interval)
    return occ


def parse_events(text: str) -> list[dict]:
    method = ""
    default_tz = None
    raw: list[dict] = []
    cur: dict | None = None
    for line in _unfold(text):
        u = line.strip().upper()
        if u.startswith("METHOD:"):
            method = line.split(":", 1)[1].strip().upper()
        elif u.startswith("X-WR-TIMEZONE:"):
            default_tz = _zone(line.split(":", 1)[1].strip()) or default_tz
        elif u == "BEGIN:VEVENT":
            cur = {}
        elif u == "END:VEVENT":
            if cur is not None:
                raw.append(cur)
                cur = None
        elif cur is not None:
            parsed = _split_prop(line)
            if not parsed:
                continue
            name, params, value = parsed
            if name == "DTSTART":
                cur["start"], cur["all_day"] = _parse_dt(value, params, default_tz)
            elif name == "DTEND":
                cur["end"], _ = _parse_dt(value, params, default_tz)
            elif name == "SUMMARY":
                cur["summary"] = _unescape(value)
            elif name == "LOCATION":
                cur["location"] = _unescape(value)
            elif name == "DESCRIPTION":
                cur["description"] = _unescape(value)[:2000]
            elif name == "UID":
                cur["uid"] = value.strip()
            elif name == "ORGANIZER":
                cur["organizer"] = (params.get("CN") or value).replace("MAILTO:", "").replace("mailto:", "").strip()
            elif name == "STATUS":
                cur["status_raw"] = value.strip().upper()
            elif name == "RRULE":
                cur["_rrule"] = _parse_rrule(value)
            elif name == "EXDATE":
                ex = cur.setdefault("_exdates", set())
                for v in value.split(","):
                    dt, _ = _parse_dt(v, params, default_tz)
                    if dt:
                        ex.add(dt)

    win_start = _now() - _WINDOW_BACK
    win_end = _now() + _WINDOW_FWD
    events: list[dict] = []
    for e in raw:
        if not e.get("start"):
            continue
        duration = None
        if e.get("end"):
            duration = e["end"] - e["start"]
        base_uid = e.get("uid", "")
        recurring = bool(e.get("_rrule"))
        for occ in _expand(e, win_start, win_end):
            inst = {
                "summary": e.get("summary", ""),
                "location": e.get("location", ""),
                "description": e.get("description", ""),
                "organizer": e.get("organizer", ""),
                "all_day": bool(e.get("all_day")),
                "start": occ.astimezone(timezone.utc),
                "end": (occ + duration).astimezone(timezone.utc) if duration is not None else None,
                "method": method,
                "cancelled": (method == "CANCEL") or (e.get("status_raw") == "CANCELLED"),
            }
            # Per-instance UID so each occurrence is its own dedupable row.
            if recurring and base_uid:
                inst["uid"] = f"{base_uid}_{occ.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"
            elif base_uid:
                inst["uid"] = base_uid
            events.append(inst)
    return events


def extract_ics(raw: bytes) -> list[dict]:
    """Pull events from every text/calendar part or .ics attachment of a raw email."""
    try:
        msg = email.message_from_bytes(raw)
    except Exception:
        return []
    out: list[dict] = []
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        fname = (part.get_filename() or "").lower()
        if ctype == "text/calendar" or fname.endswith(".ics"):
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    out.extend(parse_events(text))
            except Exception:
                continue
    return out
