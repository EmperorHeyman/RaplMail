"""Minimal CalDAV / CardDAV client (stdlib only).

Pulls VEVENTs and vCards from a CalDAV/CardDAV collection via a REPORT query and
parses them into the same dicts the rest of the app uses. Read-only sync (server
-> local) for now. No third-party deps: urllib for HTTP, xml.etree for the
multistatus response, and the existing iCal parser for events.
"""

from __future__ import annotations

import base64
import ssl
import urllib.request
import xml.etree.ElementTree as ET

from app.sync.ics import parse_events

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
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # self-hosted servers often use self-signed certs
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", "ignore")


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
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        text = resp.read().decode("utf-8", "ignore")
    return parse_events(text)


def fetch_contacts(url: str, user: str = "", password: str = "") -> list[dict]:
    xml_text = _report(url, user, password, _ADDR_QUERY)
    contacts: list[dict] = []
    for card in _extract(xml_text, "address-data"):
        contacts.extend(parse_vcards(card))
    return contacts
