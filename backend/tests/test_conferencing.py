"""Join-link extraction from meeting invites (app/sync/conferencing.py).

The point of these is the negative cases as much as the positive ones: a
detector that surfaces an unsubscribe link as "Join Teams" is worse than no
button at all, because you only find out at the moment the meeting starts.
"""

import pytest

from app.sync.conferencing import detect

TEAMS_BODY = (
    '<div>Microsoft Teams meeting</div>'
    '<div><a href="https://teams.microsoft.com/l/meetup-join/'
    '19%3ameeting_ZmEx%40thread.v2/0?context=%7b%22Tid%22%3a%22abc%22%2c'
    '%22Oid%22%3a%22def%22%7d">Click here to join the meeting</a></div>'
    '<div>Meeting ID: 123 456 789 012 | Passcode: aB1cD2</div>'
    '<div>Dial in by phone +420 2 3456 7890,,123456789# Czechia</div>'
    '<div><a href="https://aka.ms/JoinTeamsMeeting">Learn More</a> | '
    '<a href="https://teams.microsoft.com/meetingOptions/?organizerId=x">Meeting options</a></div>'
)


def test_teams_picks_the_join_url_not_the_help_links():
    got = detect("Microsoft Teams Meeting", TEAMS_BODY)
    assert got["kind"] == "teams"
    assert got["label"] == "Teams"
    assert got["url"].startswith("https://teams.microsoft.com/l/meetup-join/")
    # The boilerplate around it is full of other teams.microsoft.com URLs.
    assert "aka.ms" not in got["url"]
    assert "meetingOptions" not in got["url"]


@pytest.mark.parametrize("url", [
    "https://teams.microsoft.com/l/meetup-join/19%3ax%40thread.v2/0",
    "https://teams.microsoft.us/l/meetup-join/19%3ax%40thread.v2/0",   # GCC High
    "https://teams.live.com/meet/9354827364512?p=aBcD",               # consumer
    "https://teams.cloud.microsoft/l/meetup-join/19%3ax%40thread.v2/0",  # newer domain
])
def test_every_teams_domain(url):
    assert detect("", f"Join here: {url}")["kind"] == "teams"


@pytest.mark.parametrize("body,kind,label", [
    ("Join Zoom Meeting\nhttps://acme.zoom.us/j/98765432101?pwd=aBcDeF", "zoom", "Zoom"),
    ("https://zoom.us/w/12345678", "zoom", "Zoom"),
    ("Video call link: https://meet.google.com/abc-defg-hij", "meet", "Google Meet"),
    ("https://acme.webex.com/acme/j.php?MTID=m0123456789", "webex", "Webex"),
    ("https://global.gotomeeting.com/join/123456789", "goto", "GoTo Meeting"),
    ("https://join.skype.com/aBcDeFgHiJkL", "skype", "Skype"),
    ("https://meet.jit.si/RaplMailStandup", "jitsi", "Jitsi"),
    ("https://acme.whereby.com/standup-abc123", "whereby", "Whereby"),
])
def test_other_providers(body, kind, label):
    got = detect("", body)
    assert (got["kind"], got["label"]) == (kind, label)


def test_html_entities_are_decoded():
    """`&amp;` left in place makes a Webex/Teams URL a different, broken URL."""
    got = detect("", 'href="https://acme.webex.com/acme/j.php?MTID=m01&amp;t=99"')
    assert got["url"] == "https://acme.webex.com/acme/j.php?MTID=m01&t=99"


@pytest.mark.parametrize("body,expected", [
    ("Join the meeting: https://acme.zoom.us/j/98765432101.", "https://acme.zoom.us/j/98765432101"),
    ("(https://meet.jit.si/Standup)", "https://meet.jit.si/Standup"),
    ("see https://acme.zoom.us/j/123456789, thanks", "https://acme.zoom.us/j/123456789"),
])
def test_trailing_prose_punctuation_is_stripped(body, expected):
    assert detect("", body)["url"] == expected


@pytest.mark.parametrize("body", [
    "",
    "Conference room 4B, second floor",
    "Unsubscribe: https://example.com/join/newsletter",          # 'join' but not a meeting
    "Manage preferences at https://mailchimp.com/join/abc",
    "Docs: https://support.microsoft.com/teams",                 # teams, but not a join link
    "https://meet.google.com/",                                  # no meeting code
])
def test_nothing_to_join(body):
    assert detect("", body) is None


def test_location_outranks_description():
    """Passed in order of authority - an explicit LOCATION wins."""
    got = detect("https://meet.jit.si/TheRealOne",
                 "old link: https://acme.zoom.us/j/11111111")
    assert got["url"] == "https://meet.jit.si/TheRealOne"


def test_none_and_missing_texts_are_tolerated():
    """Event fields come back as None from the DB often enough to matter."""
    assert detect(None, None) is None
    assert detect(None, "https://meet.jit.si/x1234")["kind"] == "jitsi"
