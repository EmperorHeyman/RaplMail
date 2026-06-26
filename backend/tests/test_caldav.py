"""CalDAV / CardDAV response parsing tests (no network)."""

from app.sync import caldav

_CAL_MULTISTATUS = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/1.ics</d:href>
    <d:propstat><d:prop>
      <c:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-1@example.com
SUMMARY:Sprint planning
DTSTART:20260701T090000Z
DTEND:20260701T100000Z
END:VEVENT
END:VCALENDAR</c:calendar-data>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""

_ADDR_MULTISTATUS = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:response>
    <d:href>/card/1.vcf</d:href>
    <d:propstat><d:prop>
      <c:address-data>BEGIN:VCARD
VERSION:3.0
FN:Jane Doe
EMAIL;TYPE=INTERNET:jane@example.com
END:VCARD</c:address-data>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""


def test_fetch_events(monkeypatch):
    monkeypatch.setattr(caldav, "_report", lambda *a, **k: _CAL_MULTISTATUS)
    events = caldav.fetch_events("https://dav.example.com/cal/")
    assert len(events) == 1
    assert events[0]["summary"] == "Sprint planning"


def test_fetch_contacts(monkeypatch):
    monkeypatch.setattr(caldav, "_report", lambda *a, **k: _ADDR_MULTISTATUS)
    contacts = caldav.fetch_contacts("https://dav.example.com/card/")
    assert contacts == [{"name": "Jane Doe", "email": "jane@example.com"}]


def test_parse_vcards_multiple():
    text = ("BEGIN:VCARD\nFN:A\nEMAIL:a@x.com\nEND:VCARD\n"
            "BEGIN:VCARD\nFN:B\nEMAIL:B@X.com\nEND:VCARD\n")
    out = caldav.parse_vcards(text)
    assert {c["email"] for c in out} == {"a@x.com", "b@x.com"}
