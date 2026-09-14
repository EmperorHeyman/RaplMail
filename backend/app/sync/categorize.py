"""Heuristic email categorization (Gmail-tab style), using only synced metadata.

Categories: primary | newsletters | social | updates | promotions
- social      : notifications from social networks
- promotions  : marketing / sales / deals
- newsletters : bulk/automated senders, anything with unsubscribe wording
- updates     : transactional - receipts, orders, security, code hosting, CI
- primary     : everything else (likely a real person)

One override outranks every heuristic: mail that continues a conversation you
are part of (see `Conversation`) is always primary. The word lists below are
deliberately broad, which is fine for cold bulk mail but wrong for a human reply
- an answer from info@/support@, or one whose subject or quoted tail happens to
carry "objednávka"/"confirm"/"akce"/"unsubscribe", must never be filed out of
the inbox when it is the reply you were waiting for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CATEGORIES = ["primary", "newsletters", "social", "updates", "promotions",
              "invitations", "invitation_responses"]

_INV_RESP_PREFIX = ("accepted:", "declined:", "tentative:", "přijato:", "odmítnuto:",
                    "předběžně přijato:", "accepted -", "declined -")
_INV_WORDS = ("invitation:", "invites you", "meeting invitation", "calendar invite",
              "you're invited", "you are invited", "you have been invited", "invited you",
              "pozvánka", "schůzka", "meeting invite", "updated invitation",
              "canceled event", "cancelled event")
# Subject prefixes that almost always denote a meeting request (Outlook titles
# the invite with the meeting name, often starting with these).
_INV_PREFIXES = ("meeting", "schůzka", "schuzka", "porada", "pozvánka", "pozvanka",
                 "invitation", "call with", "1:1", "sync:", "huddle")


def _domain_matches(domain: str, suffixes) -> bool:
    """True if domain equals or is a subdomain of any entry (no substring traps)."""
    return any(domain == s or domain.endswith("." + s) for s in suffixes)

_SOCIAL_DOMAINS = (
    "facebookmail.com", "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "mail.instagram.com", "reddit.com", "redditmail.com",
    "youtube.com", "discord.com", "tiktok.com", "pinterest.com", "mastodon",
)
_UPDATES_DOMAINS = (
    "github.com", "gitlab.com", "bitbucket.org", "atlassian.net", "paypal.com",
    "stripe.com", "amazon.com", "amazonses.com", "apple.com", "google.com",
    "microsoft.com", "office365.com", "alza.cz", "ppl.cz", "packeta.com",
)
_BULK_LOCALPARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "newsletter", "news",
    "marketing", "mailer", "mailing", "info", "notifications", "notification",
    "updates", "hello", "team", "support", "bounce", "campaign", "neodpovidat",
)
_PROMO_WORDS = (
    "sale", "discount", "% off", "deal", "coupon", "promo", "offer", "save ",
    "black friday", "cyber monday", "limited time", "exclusive", "sleva", "akce",
    "výprodej", "zdarma", "novinky",
)
_UPDATE_WORDS = (
    "receipt", "invoice", "order", "shipped", "shipping", "tracking", "payment",
    "confirm", "verification", "verify", "security alert", "sign-in", "password",
    "reset", "objednávka", "faktura", "potvrzení", "zásilka", "doručení",
)
_NEWSLETTER_WORDS = ("unsubscribe", "view in browser", "odhlásit", "newsletter")

# "Re:" in the locales this app actually sees, plus the numbered form some
# clients use ("Re[2]:") and repeated prefixes ("Re: Odp:").
_REPLY_PREFIX_RE = re.compile(
    r"^\s*(?:(?:re|odp|odpověď|aw|antw|sv|vs|res|rif|ref|回复)\s*(?:\[\d+\])?\s*:\s*)+",
    re.IGNORECASE)


def is_reply_subject(subject: str) -> bool:
    """True when the subject carries a reply prefix ("Re:", "Odp:", "AW:", …)."""
    return bool(_REPLY_PREFIX_RE.match(subject or ""))


@dataclass
class Conversation:
    """Who counts as "someone I'm talking to", for the conversation guard.

    `mine` is every address that is me (each account's email + its aliases);
    `corresponded` is every address I have written to. Both are lowercased.
    Built once per sync pass - see `build_conversation`.
    """

    mine: set[str] = field(default_factory=set)
    corresponded: set[str] = field(default_factory=set)

    def is_reply_to_me(self, from_addr: str = "", subject: str = "",
                       parent_from: str = "") -> bool:
        """Is this message an answer inside a conversation I'm part of?

        Two signals, either is enough:
          - its In-Reply-To resolved to a message *I* sent (`parent_from`), which
            is as certain as it gets, or
          - it carries a reply prefix AND comes from someone I have written to,
            which catches the case where the parent isn't cached locally (Sent
            not synced yet, or a client that dropped In-Reply-To).
        """
        if parent_from and parent_from.strip().lower() in self.mine:
            return True
        sender = (from_addr or "").strip().lower()
        return bool(sender) and sender in self.corresponded and is_reply_subject(subject)


def build_conversation(session, *, sent_limit: int = 5000) -> Conversation:
    """Collect my own addresses + everyone I've written to, in two queries.

    Recipients come from the scanned address book *and* from the newest
    `sent_limit` messages in the Sent folders - the address book is rebuilt on a
    5-minute throttle, so a reply to a mail you sent two minutes ago would
    otherwise miss the guard entirely.
    """
    from email.utils import parseaddr

    from sqlmodel import select

    from app.models import Account, Contact, Folder, FolderRole, Message

    mine: set[str] = set()
    for email, aliases in session.exec(select(Account.email, Account.aliases)):
        if email:
            mine.add(email.strip().lower())
        for alias in (aliases or []):
            addr = (parseaddr(alias)[1] or alias or "").strip().lower()
            if addr:
                mine.add(addr)

    corresponded: set[str] = {
        (e or "").strip().lower()
        for e in session.exec(select(Contact.email).where(Contact.times_sent > 0))
        if e
    }
    sent_folder_ids = list(session.exec(select(Folder.id).where(Folder.role == FolderRole.sent)))
    if sent_folder_ids:
        rows = session.exec(
            select(Message.to_addrs, Message.cc_addrs)
            .where(Message.folder_id.in_(sent_folder_ids))
            .order_by(Message.date.desc())
            .limit(sent_limit)
        )
        for to_addrs, cc_addrs in rows:
            for addr in [*(to_addrs or []), *(cc_addrs or [])]:
                a = (addr or "").strip().lower()
                if a:
                    corresponded.add(a)
    return Conversation(mine=mine, corresponded=corresponded)


def categorize(from_addr: str = "", from_name: str = "", subject: str = "",
               snippet: str = "", conversation: bool = False) -> str:
    addr = (from_addr or "").lower()
    domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    local = addr.split("@", 1)[0] if "@" in addr else ""
    text = f"{subject} {snippet}".lower()
    subj = (subject or "").lower().strip()

    # Calendar invitations + their accept/decline responses (high priority).
    if subj.startswith(_INV_RESP_PREFIX):
        return "invitation_responses"

    # The conversation guard (see module docstring). It sits above every other
    # heuristic except the accept/decline check - those *are* replies to an
    # invite you sent, and the user wants them under invitation_responses. A
    # genuine invite arriving mid-thread is still re-filed as "invitations" when
    # its body is fetched and an ICS REQUEST/CANCEL turns up (api/messages.py).
    if conversation:
        return "primary"

    if any(w in text for w in _INV_WORDS) or subj.startswith(_INV_PREFIXES):
        return "invitations"

    if _domain_matches(domain, _SOCIAL_DOMAINS):
        return "social"
    if _domain_matches(domain, _UPDATES_DOMAINS) or any(w in text for w in _UPDATE_WORDS):
        return "updates"
    if any(w in text for w in _PROMO_WORDS):
        return "promotions"
    bulk = any(local == p or local.startswith(p) for p in _BULK_LOCALPARTS)
    if bulk or any(w in text for w in _NEWSLETTER_WORDS):
        return "newsletters"
    return "primary"
