"""Find the "join the meeting" link inside an invitation.

A Teams/Zoom/Meet invite buries its join URL in the DESCRIPTION blob, wrapped in
boilerplate: "Click here to join the meeting", dial-in numbers, conference IDs,
tenant legal footers. Hunting for it by eye at the moment a reminder pops is
exactly when there's no time to - so we pull it out up front and hand the card
and the reminder popup a single Join button.

Detection is by known provider only. A generic "any URL with 'join' in it"
fallback would happily surface an unsubscribe link as the way into your meeting.
"""

from __future__ import annotations

import re
from html import unescape

# Trailing punctuation that belongs to the surrounding prose, not the URL
# ("...join the meeting: https://x/y." / "(https://x/y)").
_URL_TAIL = ".,;:!?)]}>\"'*|"

# Everything a URL may contain when embedded in HTML or plain text. Excluding
# quotes and angle brackets is what makes href="..." extraction work.
_U = r"""[^\s"'<>]+"""

# (kind, display label, pattern). Order matters only when one text carries links
# for two providers; first match wins.
_PROVIDERS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    # Teams, across every domain Microsoft has shipped it on (teams.microsoft.com,
    # the GCC teams.microsoft.us, consumer teams.live.com, and the newer
    # teams.cloud.microsoft), plus both the /l/meetup-join and short /meet forms.
    ("teams", "Teams", re.compile(
        r"https://teams\.(?:microsoft\.com|microsoft\.us|live\.com|cloud\.microsoft)"
        r"/(?:l/meetup-join|meet)/" + _U, re.I)),
    ("zoom", "Zoom", re.compile(
        r"https://[\w.-]*zoom\.(?:us|com|com\.cn)/(?:j|w|s|my)/" + _U, re.I)),
    ("meet", "Google Meet", re.compile(
        r"https://meet\.google\.com/(?:lookup/)?" + _U, re.I)),
    ("webex", "Webex", re.compile(
        r"https://[\w.-]*webex\.com(?:/[\w.-]+)?/(?:j\.php\?|meet/|join/|m/)" + _U, re.I)),
    ("goto", "GoTo Meeting", re.compile(
        r"https://[\w.-]*goto(?:meeting|webinar)?\.com/join/" + _U, re.I)),
    ("skype", "Skype", re.compile(r"https://join\.skype\.com/" + _U, re.I)),
    ("whereby", "Whereby", re.compile(r"https://[\w.-]*whereby\.com/" + _U, re.I)),
    ("jitsi", "Jitsi", re.compile(r"https://meet\.jit\.si/" + _U, re.I)),
    ("bluejeans", "BlueJeans", re.compile(
        r"https://[\w.-]*bluejeans\.com/" + _U, re.I)),
    ("slack", "Slack", re.compile(r"https://app\.slack\.com/huddle/" + _U, re.I)),
)


def _clean(url: str) -> str:
    """Undo HTML entity escaping and shed trailing prose punctuation.

    The entity pass matters: a Webex/Teams URL written as
    `...?MTID=x&amp;t=y` in the HTML body is a different, broken URL if handed
    to the browser verbatim.
    """
    url = unescape(url).strip()
    while url and url[-1] in _URL_TAIL:
        url = url[:-1]
    return url


def detect(*texts: str | None) -> dict | None:
    """The first recognised join link across `texts`, or None.

    Args are searched in the order given, so pass the most authoritative field
    first (LOCATION before DESCRIPTION before the raw mail body).
    Returns {"url", "kind", "label"}.
    """
    for text in texts:
        if not text:
            continue
        for kind, label, pat in _PROVIDERS:
            m = pat.search(text)
            if not m:
                continue
            url = _clean(m.group(0))
            if len(url) > 12:   # a bare "https://meet.google.com/" isn't joinable
                return {"url": url, "kind": kind, "label": label}
    return None
