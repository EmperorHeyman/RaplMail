"""Minimal CalDAV / CardDAV client (stdlib only).

Pulls VEVENTs and vCards from a CalDAV/CardDAV collection via a REPORT query and
parses them into the same dicts the rest of the app uses. Events can also be
written back (PUT/DELETE of individual .ics objects - see put_event/delete_event);
contacts remain read-only. No third-party deps: urllib for HTTP, xml.etree for
the multistatus response, and the existing iCal parser for events.
"""

from __future__ import annotations

import base64
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from app.sync.ics import parse_events


def _ssl_context() -> ssl.SSLContext:
    """Verify TLS certs + hostname by DEFAULT - credentials travel over HTTP Basic,
    so disabling verification globally exposed them to MITM on hostile networks.
    Self-hosted boxes with self-signed certs can opt out via an env var."""
    ctx = ssl.create_default_context()
    if os.environ.get("RAPLMAIL_CALDAV_INSECURE_TLS", "").lower() in ("1", "true", "yes"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx

_CAL_QUERY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    '<d:prop><d:getetag/><c:calendar-data/></d:prop>'
    '<c:filter><c:comp-filter name="VCALENDAR">'
    '<c:comp-filter name="VEVENT"/></c:comp-filter></c:filter>'
    '</c:calendar-query>'
)
_ADDR_QUERY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    '<d:prop><d:getetag/><c:address-data/></d:prop>'
    '</c:addressbook-query>'
)


def _report(url: str, user: str, password: str, body: str) -> str:
    headers = {
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }
    if user:
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="REPORT", headers=headers)
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", "ignore")


def _object_request(base_url: str, user: str, password: str, uid: str,
                    method: str, data: bytes | None = None,
                    content_type: str = "") -> None:
    """Issue a PUT/DELETE against the <collection>/<uid>.ics object URL."""
    url = base_url.rstrip("/") + "/" + urllib.parse.quote(uid, safe="") + ".ics"
    headers: dict[str, str] = {}
    if content_type:
        headers["Content-Type"] = content_type
    if user:
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx):
        pass  # urlopen raises HTTPError on any non-2xx status


def put_event(base_url: str, user: str, password: str, uid: str, ics_text: str) -> str:
    """PUT a full VCALENDAR to <collection>/<uid>.ics. Returns the object URL;
    raises on any non-2xx response."""
    _object_request(base_url, user, password, uid, "PUT",
                    data=ics_text.encode("utf-8"),
                    content_type="text/calendar; charset=utf-8")
    return base_url.rstrip("/") + "/" + urllib.parse.quote(uid, safe="") + ".ics"


def delete_event(base_url: str, user: str, password: str, uid: str) -> bool:
    """DELETE <collection>/<uid>.ics. A 404 counts as success (already gone)."""
    try:
        _object_request(base_url, user, password, uid, "DELETE")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True
        raise
    return True


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract(xml_text: str, wanted: str) -> list[str]:
    """All text payloads of elements whose local name == wanted (e.g. calendar-data)."""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for el in root.iter():
        if _localname(el.tag) == wanted and el.text:
            out.append(el.text)
    return out


def parse_vcards(text: str) -> list[dict]:
    """Pull {name, email} out of one or more vCard blocks."""
    contacts, cur = [], {}
    in_card = False
    for raw in text.splitlines():
        line = raw.strip()
        u = line.upper()
        if u == "BEGIN:VCARD":
            in_card, cur = True, {}
        elif u == "END:VCARD":
            if cur.get("email"):
                contacts.append(cur)
            in_card = False
        elif in_card:
            if u.startswith("FN"):
                cur["name"] = line.split(":", 1)[-1].strip()
            elif u.startswith("EMAIL") and ":" in line and not cur.get("email"):
                cur["email"] = line.split(":", 1)[-1].strip().lower()
    return contacts


def fetch_events(url: str, user: str = "", password: str = "") -> list[dict]:
    xml_text = _report(url, user, password, _CAL_QUERY)
    events: list[dict] = []
    for cal in _extract(xml_text, "calendar-data"):
        events.extend(parse_events(cal))
    return events


def fetch_ics(url: str) -> list[dict]:
    """Fetch a plain iCal/ICS subscription feed (e.g. a Google 'Secret address in
    iCal format' URL) and parse its VEVENTs. webcal:// is treated as https://."""
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "RaplMail/1.0"})
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        text = resp.read().decode("utf-8", "ignore")
    return parse_events(text)


def fetch_contacts(url: str, user: str = "", password: str = "") -> list[dict]:
    xml_text = _report(url, user, password, _ADDR_QUERY)
    contacts: list[dict] = []
    for card in _extract(xml_text, "address-data"):
        contacts.extend(parse_vcards(card))
    return contacts
