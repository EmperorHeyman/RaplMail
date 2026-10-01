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

import logging
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

    def answers_my_message(self, parent_from: str = "", automated: bool = False) -> bool:
        """Is this a person answering a message I actually sent?

        Deliberately the narrow question, because it is the one the "Reply" badge
        claims. It needs the message's own In-Reply-To to resolve to something I
        sent - a "Re:" subject from a familiar address is not evidence, or every
        notification from a ticket system you once replied to would call itself a
        reply. Machine-generated mail never qualifies, however it threads.
        """
        if automated:
            return False
        return bool(parent_from) and parent_from.strip().lower() in self.mine

    def is_conversation(self, from_addr: str = "", subject: str = "",
                        parent_from: str = "", automated: bool = False) -> bool:
        """Is this message part of a conversation I'm in - i.e. must it stay in
        the inbox rather than be filed under newsletters/updates/promotions?

        Wider than `answers_my_message`, because the cost of being wrong differs:
        a missed reply is the bug we are fixing, an extra mail left in Primary is
        not. So a reply prefix from someone I have written to also counts, which
        catches a reply whose parent isn't cached (Sent not synced yet, or a
        client that dropped In-Reply-To). Machine mail is excluded either way:
        a list, an autoresponder or a ticket system is not a conversation, and
        the ordinary heuristics file it where the user expects it.
        """
        if automated:
            return False
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


def refile(session, where=None) -> int:
    """Recompute the category (and the reply marker) of stored mail, exactly as
    the sync would file it today: sender override or heuristic, then "put in
    group" rules on top. `where` narrows it to a subset (one sender, one group);
    None re-files everything. Column-only, and the caller commits.

    Every path that re-files existing mail goes through here, so a message can't
    land in one group after a rule edit and another after the next startup.
    """
    from sqlalchemy import text
    from sqlmodel import select

    from app.models import Message, Rule, RuleAction, SenderCategory
    from app.sync.rules import MessageFields, group_for

    log = logging.getLogger("raplmail.categorize")
    overrides = {sc.email.lower(): sc.category for sc in session.exec(select(SenderCategory))}
    group_rules = [r for r in session.exec(select(Rule))
                   if r.enabled and r.action == RuleAction.set_group and r.action_arg]
    # Same conversation guard the sync applies to fresh mail, so re-filing pulls
    # already-misfiled replies back into the inbox.
    try:
        convo = build_conversation(session)
    except Exception:
        log.exception("conversation context failed; re-filing without it")
        convo = None
    cols = [Message.id, Message.account_id, Message.from_addr, Message.from_name,
            Message.subject, Message.snippet, Message.category, Message.in_reply_to,
            Message.is_reply_to_me, Message.is_automated, Message.unsubscribe]
    if group_rules:
        cols.append(Message.to_addrs)   # a rule can match on the recipient
    stmt = select(*cols)
    if where is not None:
        stmt = stmt.where(where)
    rows = session.exec(stmt).all()
    # Who wrote the parent of each reply, keyed by the parent's Message-ID.
    # Everything: one pass over the (indexed) message_id/from_addr columns
    # instead of a lookup per row. A subset: just the parents it points at.
    parent_from: dict[str, str] = {}
    if convo:
        if where is None:
            pairs = session.exec(select(Message.message_id, Message.from_addr)).all()
        else:
            irts = list({r[7] for r in rows if r[7]})
            pairs = []
            for i in range(0, len(irts), 500):
                pairs += session.exec(select(Message.message_id, Message.from_addr)
                                      .where(Message.message_id.in_(irts[i:i + 500]))).all()
        for mid_hdr, fa in pairs:
            if mid_hdr and (fa or "").strip().lower() in convo.mine:
                parent_from[mid_hdr] = fa
    n = 0
    for row in rows:
        mid, aid, fa, fn, subj, snip, cat, irt, was_reply, automated, unsub = row[:11]
        # Mail synced before the sender's list/auto headers were read has
        # is_automated=False by default, which would let an old ticket blast pass
        # for a personal reply. A stored List-Unsubscribe (kept whenever a body
        # was fetched) says the same thing, so use it as the stand-in until the
        # row is re-synced.
        is_auto = bool(automated) or bool((unsub or "").strip())
        parent = parent_from.get(irt or "", "")
        conversation = bool(convo) and convo.is_conversation(
            from_addr=fa or "", subject=subj or "", parent_from=parent, automated=is_auto)
        replied = bool(convo) and convo.answers_my_message(parent_from=parent, automated=is_auto)
        new = overrides.get((fa or "").lower()) or categorize(
            fa or "", fn or "", subj or "", snip or "", conversation=conversation)
        if group_rules:
            mine = [r for r in group_rules if r.account_id is None or r.account_id == aid]
            new = group_for(mine, MessageFields(
                from_addr=fa or "", to_addrs=list(row[11] or []), subject=subj or "",
                body=snip or "", category=new, from_name=fn or "")) or new
        # The same pass backfills the reply marker, so the badge appears on mail
        # that was already synced before it existed - and clears from mail that
        # never earned it.
        if new != cat or replied != bool(was_reply):
            session.exec(
                text("UPDATE message SET category = :c, is_reply_to_me = :r WHERE id = :i")
                .bindparams(c=new, r=1 if replied else 0, i=mid))
            n += 1
    return n
