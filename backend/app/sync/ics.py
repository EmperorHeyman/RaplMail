"""Minimal iCalendar (RFC 5545) extraction — enough to surface meeting invites.

We don't implement the full spec (no RRULE expansion, no VTIMEZONE math); we pull
the fields a calendar view needs from VEVENTs in text/calendar parts or .ics
attachments. Times are normalised to UTC on a best-effort basis.
"""

from __future__ import annotations

import email
import re
from datetime import datetime, timezone


def _unfold(text: str) -> list[str]:
    """Undo RFC 5545 line folding (continuation lines start with space/tab)."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_dt(val: str, params: dict) -> tuple[datetime | None, bool]:
    val = val.strip()
    if not val:
        return None, False
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", val):
        try:
            return datetime.strptime(val[:8], "%Y%m%d").replace(tzinfo=timezone.utc), True
        except ValueError:
            return None, False
    try:
        if val.endswith("Z"):
            return datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
        # Floating / TZID-qualified: best-effort, treat as UTC.
        return datetime.strptime(val[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc), False
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


def parse_events(text: str) -> list[dict]:
    method = ""
    events: list[dict] = []
    cur: dict | None = None
    for line in _unfold(text):
        u = line.strip().upper()
        if u.startswith("METHOD:"):
            method = line.split(":", 1)[1].strip().upper()
        elif u == "BEGIN:VEVENT":
            cur = {}
        elif u == "END:VEVENT":
            if cur is not None:
                events.append(cur)
                cur = None
        elif cur is not None:
            parsed = _split_prop(line)
            if not parsed:
                continue
            name, params, value = parsed
            if name == "DTSTART":
                cur["start"], cur["all_day"] = _parse_dt(value, params)
            elif name == "DTEND":
                cur["end"], _ = _parse_dt(value, params)
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
    for e in events:
        e["method"] = method
        e["cancelled"] = (method == "CANCEL") or (e.get("status_raw") == "CANCELLED")
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
