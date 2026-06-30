"""Minimal Google Calendar API v3 client — enough to create/delete events.

Reading still happens via the subscribed iCal feed; this is purely for *writing*
events to the user's Google Calendar with a properly OAuth-scoped token, which
(unlike the iMIP self-invite trick) reliably lands on the calendar.
"""

from __future__ import annotations

from datetime import timedelta

import httpx

from app.providers import oauth

_API = "https://www.googleapis.com/calendar/v3"


def _event_body(summary, start, end, all_day, location, description) -> dict:
    body: dict = {"summary": summary or "(no title)"}
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    if all_day:
        # All-day uses date-only; Google's end date is EXCLUSIVE.
        end_d = (end or start).date()
        start_d = start.date()
        if end_d <= start_d:
            end_d = start_d + timedelta(days=1)
        else:
            end_d = end_d + timedelta(days=1)
        body["start"] = {"date": start_d.isoformat()}
        body["end"] = {"date": end_d.isoformat()}
    else:
        end_dt = end or (start + timedelta(hours=1))
        # dateTime carries an offset/Z, so Google places it in the user's zone.
        body["start"] = {"dateTime": start.isoformat()}
        body["end"] = {"dateTime": end_dt.isoformat()}
    return body


def insert_event(bundle: dict, *, summary, start, end, all_day, location, description) -> tuple[dict, dict]:
    """Create an event on the user's primary calendar. Returns (event, refreshed_bundle)."""
    token, bundle = oauth.google_access_token(bundle)
    body = _event_body(summary, start, end, all_day, location, description)
    r = httpx.post(f"{_API}/calendars/primary/events",
                   headers={"Authorization": f"Bearer {token}"}, json=body, timeout=30)
    r.raise_for_status()
    return r.json(), bundle


def delete_event(bundle: dict, event_id: str) -> dict:
    token, bundle = oauth.google_access_token(bundle)
    httpx.delete(f"{_API}/calendars/primary/events/{event_id}",
                 headers={"Authorization": f"Bearer {token}"}, timeout=30)
    return bundle
