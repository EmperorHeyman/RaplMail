"""Heuristic email categorization (Gmail-tab style), using only synced metadata.

Categories: primary | newsletters | social | updates | promotions
- social      : notifications from social networks
- promotions  : marketing / sales / deals
- newsletters : bulk/automated senders, anything with unsubscribe wording
- updates     : transactional — receipts, orders, security, code hosting, CI
- primary     : everything else (likely a real person)
"""

from __future__ import annotations

CATEGORIES = ["primary", "newsletters", "social", "updates", "promotions",
              "invitations", "invitation_responses"]

_INV_RESP_PREFIX = ("accepted:", "declined:", "tentative:", "přijato:", "odmítnuto:",
                    "předběžně přijato:", "accepted —", "declined —")
_INV_WORDS = ("invitation:", "invites you", "meeting invitation", "calendar invite",
              "you're invited", "you are invited", "you have been invited", "invited you",
              "pozvánka", "schůzka", "meeting invite", "updated invitation",
              "canceled event", "cancelled event")


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


def categorize(from_addr: str = "", from_name: str = "", subject: str = "",
               snippet: str = "") -> str:
    addr = (from_addr or "").lower()
    domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    local = addr.split("@", 1)[0] if "@" in addr else ""
    text = f"{subject} {snippet}".lower()
    subj = (subject or "").lower().strip()

    # Calendar invitations + their accept/decline responses (high priority).
    if subj.startswith(_INV_RESP_PREFIX):
        return "invitation_responses"
    if any(w in text for w in _INV_WORDS):
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
