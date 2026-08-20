"""Meeting mail resolution: recovering WHEN a meeting is from mail that never
says. Covers subject classification, the Exchange link-only footprint, matching
the local calendar (cross-account, prefix-insensitive), and which occurrence of a
recurring series a mail is taken to mean."""
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, CalendarEvent, Folder, Message
from app.sync.meeting import _as_utc_naive, classify, normalize_title, owa_url, resolve

# A real Exchange link-only cancellation body: an OWA deep link to the calendar
# item plus the "turn on iCalendar format" tip, and no date anywhere.
OWA_BODY = (
    '<body>Microsoft Outlook Web Access: '
    '<a href="https://outlook.office365.com/owa/example.eu/?itemid=AAMkAGEy%3D'
    '&amp;exvsurl=1&amp;path=/calendar/item">link</a><br>'
    'To receive meeting invitations as .iCalendar attachments instead of Outlook Web App links, go to '
    '<a href="https://outlook.office365.com/owa/example.eu/?path=/options/popandimap">options</a>'
    ' and select Send meeting invitations in iCalendar format.<br>See you there.</body>'
)


def _s():
    return Session(get_engine())


def _wipe_events():
    with _s() as s:
        for r in s.exec(select(CalendarEvent)).all():
            s.delete(r)
        s.commit()


_seq = [9000]   # unique account emails / message uids across tests in this module


def _mk_mail(s, subject, when, *, html="", account_id=None):
    """`when` is an aware UTC instant. The column is naive, so the naive form is
    what gets stored and the aware value is put back on the instance afterwards -
    keeping these tests independent of the runner's local timezone."""
    _seq[0] += 1
    if account_id is None:
        acct = Account(email=f"meet-{_seq[0]}@example.com")
        s.add(acct); s.commit(); s.refresh(acct)
        account_id = acct.id
    folder = Folder(account_id=account_id, path="INBOX", name="INBOX")
    s.add(folder); s.commit(); s.refresh(folder)
    msg = Message(account_id=account_id, folder_id=folder.id, uid=_seq[0],
                  subject=subject, date=when.replace(tzinfo=None), body_html=html)
    s.add(msg); s.commit(); s.refresh(msg)
    msg.date = when
    return msg


def test_classify_reads_outlook_subject_prefixes():
    assert classify("Canceled: IT Ticketing") == "cancel"
    assert classify("Zrušeno: Ranní porada") == "cancel"
    assert classify("FW: Canceled: IT meeting") == "cancel"
    assert classify("Updated: Standup") == "update"
    assert classify("Accepted: MSIC") == "reply"
    assert classify("Odmítnuto: MSIC") == "reply"
    assert classify("Invitation: test") == "invite"
    # Ordinary mail must not be mistaken for calendar mail.
    assert classify("Re: invoice") == ""
    assert classify("Cancellation policy update") == ""


def test_normalize_title_strips_prefixes_on_both_sides():
    # Outlook's published-calendar feeds carry "Canceled: " in the SUMMARY itself,
    # so mail subject and event title only line up once both are normalised.
    assert normalize_title("Canceled: IT Ticketing") == normalize_title("IT Ticketing")
    assert normalize_title("FW: Zrušeno: Ranní  porada") == "ranní porada"


def test_owa_url_extracted_and_unescaped():
    url = owa_url(OWA_BODY)
    assert url.startswith("https://outlook.office365.com/owa/example.eu/?itemid=")
    assert "&amp;" not in url
    assert "path=/calendar/item" in url


def test_link_only_cancellation_resolves_from_the_local_calendar(client):
    _wipe_events()
    with _s() as s:
        # The meeting lives in the calendar under a DIFFERENT account (an ICS
        # subscription set up on another account) - the match must still be found.
        other = Account(email="meet-feed@example.com")
        s.add(other); s.commit(); s.refresh(other)
        s.add(CalendarEvent(account_id=other.id, uid="ics:feed:MTG-TICK", source="ics",
                            summary="Canceled: IT Ticketing",
                            start=datetime(2026, 8, 21, 9), end=datetime(2026, 8, 21, 10)))
        s.commit()

        msg = _mk_mail(s, "Canceled: IT Ticketing", datetime(2026, 8, 19, 9, 28, tzinfo=timezone.utc), html=OWA_BODY)
        card = resolve(s, msg, msg.body_html)

    assert card is not None
    assert card["kind"] == "cancel"
    assert card["source"] == "calendar"        # inferred, and labelled as such
    assert card["start"] == "2026-08-21T09:00:00+00:00"
    assert card["end"] == "2026-08-21T10:00:00+00:00"
    assert card["link_only"] is True
    assert card["owa_url"]


def test_recurring_series_reports_the_next_occurrence_not_the_first(client):
    _wipe_events()
    with _s() as s:
        acct = Account(email="meet-rec@example.com")
        s.add(acct); s.commit(); s.refresh(acct)
        for day in range(17, 22):             # daily 06:30-07:00 standup
            s.add(CalendarEvent(account_id=acct.id, uid=f"ics:feed:STANDUP_{day}", source="ics",
                                summary="Canceled: Ranní porada",
                                start=datetime(2026, 8, day, 6, 30), end=datetime(2026, 8, day, 7)))
        s.commit()

        # Sent at 16:23 on the 19th: the 19th's occurrence is already over, so the
        # cancellation is about the 20th.
        msg = _mk_mail(s, "Zrušeno: Ranní porada", datetime(2026, 8, 19, 16, 23, tzinfo=timezone.utc),
                       html=OWA_BODY, account_id=acct.id)
        card = resolve(s, msg, msg.body_html)

    assert card["start"] == "2026-08-20T06:30:00+00:00"
    assert card["occurrences"] == 5            # drives the "repeating" hint


def test_own_ics_part_wins_over_a_calendar_match(client):
    _wipe_events()
    with _s() as s:
        acct = Account(email="meet-own@example.com")
        s.add(acct); s.commit(); s.refresh(acct)
        msg = _mk_mail(s, "Accepted: MSIC", datetime(2026, 5, 25, 14, tzinfo=timezone.utc), account_id=acct.id)
        # Parsed straight out of this mail's text/calendar part.
        s.add(CalendarEvent(account_id=acct.id, uid="MSIC@outlook.com", message_id=msg.id,
                            summary="MSIC", method="REPLY", organizer="boss@example.com",
                            start=datetime(2026, 5, 25, 12), end=datetime(2026, 5, 25, 13)))
        # A same-titled decoy in the calendar that must not be preferred.
        s.add(CalendarEvent(account_id=acct.id, uid="ics:feed:MSIC-decoy", source="ics",
                            summary="MSIC", start=datetime(2026, 6, 1, 8)))
        s.commit()
        card = resolve(s, msg, "")

    assert card["source"] == "mail"
    assert card["kind"] == "reply"
    assert card["start"] == "2026-05-25T12:00:00+00:00"
    assert card["organizer"] == "boss@example.com"


def test_link_only_mail_with_nothing_to_match_still_says_so(client):
    _wipe_events()
    with _s() as s:
        msg = _mk_mail(s, "Canceled: A meeting nobody has", datetime(2026, 8, 19, 9, tzinfo=timezone.utc), html=OWA_BODY)
        card = resolve(s, msg, msg.body_html)

    assert card["source"] == "none"
    assert card["start"] is None
    assert card["link_only"] is True
    assert card["owa_url"]                     # the reader can still offer the link


def test_ordinary_mail_produces_no_card(client):
    _wipe_events()
    with _s() as s:
        msg = _mk_mail(s, "Invoice 2026-08 attached", datetime(2026, 8, 19, 9, tzinfo=timezone.utc),
                       html="<p>Hello, please find the invoice attached.</p>")
        assert resolve(s, msg, msg.body_html) is None

        # A meeting-ish prefix alone isn't enough - the calendar has to know it.
        msg2 = _mk_mail(s, "Accepted: something we never scheduled", datetime(2026, 8, 19, 9, tzinfo=timezone.utc),
                        html="<p>Thanks!</p>")
        assert resolve(s, msg2, msg2.body_html) is None


def test_message_dates_are_read_as_local_not_utc():
    # imapclient hands us naive LOCAL times; event times are stored naive UTC. The
    # conversion has to bridge that, or a recurring series resolves to the wrong
    # occurrence by the local offset.
    naive = datetime(2026, 8, 19, 16, 23)
    assert _as_utc_naive(naive) == naive - naive.astimezone().utcoffset()
    # An already-aware instant converts exactly, whatever the machine's zone.
    assert _as_utc_naive(datetime(2026, 8, 19, 16, 23, tzinfo=timezone.utc)) == naive
