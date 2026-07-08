"""Smart address book: scan outgoing mail and build a contact list, skipping
obviously-junk addresses (random local parts / gibberish domains) unless there's
real two-way correspondence.

Rules for adding a recipient seen in *sent* mail (first matching wins):
  1. Junk/automated address (no-reply@, random blob)      -> skip
  2. Known domain (gmail, seznam, a123systems, …)         -> add
  3. They replied / we received mail from them (two-way)  -> add
  4. We emailed them more than once (deliberate)          -> add
  5. Otherwise - a single cold send to an unknown domain  -> skip

So a one-off to e.g. sales@xyzasd.it that never wrote back is skipped, but it
gets added the moment they reply or you email them again. Known-domain and
repeat contacts are always kept.
"""

from __future__ import annotations

import re
from collections import defaultdict

from sqlmodel import Session, select

from app.models import Contact, Folder, FolderRole, Message, utcnow

# Common consumer + the user's own domains. Lowercase. Extend freely.
KNOWN_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "proton.me", "protonmail.com",
    "seznam.cz", "email.cz", "centrum.cz", "post.cz", "volny.cz", "atlas.cz",
    "a123systems.eu",
}

_VOWELS = set("aeiouy")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _vowel_ratio(s: str) -> float:
    letters = [c for c in s.lower() if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c in _VOWELS for c in letters) / len(letters)


def _max_consonant_run(s: str) -> int:
    best = run = 0
    for c in s.lower():
        if c.isalpha() and c not in _VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def looks_fake(email: str) -> bool:
    """Heuristic: does this look auto-generated / random rather than a real person?"""
    if not _EMAIL_RE.match(email):
        return True
    local, domain = email.rsplit("@", 1)
    local = local.lower()
    sld = domain.split(".")[0]  # second-level label, e.g. "xyzasd" in xyzasd.it

    # No-reply / automated senders.
    if re.search(r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer|postmaster|bounce|notification[s]?)", local):
        return True

    # Random-looking local part: long, vowel-poor, or long consonant runs, or hex/uuid-ish.
    if len(local) >= 18 and "." not in local and _vowel_ratio(local) < 0.25:
        return True
    if re.fullmatch(r"[0-9a-f]{16,}", local):  # hex blob
        return True
    if _max_consonant_run(local) >= 6:
        return True

    # Gibberish second-level domain: short, no vowels (e.g. "xyzasd", "qwlkj").
    if len(sld) <= 8 and _vowel_ratio(sld) == 0.0 and sld not in ("ms", "fb"):
        return True
    if _max_consonant_run(sld) >= 6:
        return True

    return False


def should_add(email: str, *, sent: int, received: int) -> bool:
    if not _EMAIL_RE.match(email):
        return False
    if looks_fake(email):       # no-reply@, mailer-daemon, random blobs -> never
        return False
    if domain_of(email) in KNOWN_DOMAINS:
        return True
    if received > 0:            # they wrote back -> real relationship
        return True
    if sent >= 2:               # we deliberately emailed them more than once
        return True
    return False                # single cold send to an unknown domain -> skip


def scan_contacts(session: Session) -> int:
    """Rebuild/augment the address book from synced mail. Returns contacts upserted."""
    # Recipients of our outgoing mail (sent folders).
    sent_folder_ids = [
        f.id for f in session.exec(select(Folder).where(Folder.role == FolderRole.sent))
    ]
    sent_counts: dict[str, int] = defaultdict(int)
    last_sent: dict[str, object] = {}
    if sent_folder_ids:
        # Select only the needed columns - never load cached body blobs here.
        rows = session.exec(
            select(Message.to_addrs, Message.cc_addrs, Message.date)
            .where(Message.folder_id.in_(sent_folder_ids))
        )
        for to_addrs, cc_addrs, date in rows:
            for addr in [*(to_addrs or []), *(cc_addrs or [])]:
                a = (addr or "").strip().lower()
                if not a:
                    continue
                sent_counts[a] += 1
                if date and (a not in last_sent or (last_sent[a] and date > last_sent[a])):
                    last_sent[a] = date

    # Inbound signal + display names, keyed by sender address.
    from app.providers.imap_smtp import decode_mime_words

    received_counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for from_addr, from_name in session.exec(select(Message.from_addr, Message.from_name)):
        a = (from_addr or "").strip().lower()
        if a:
            received_counts[a] += 1
            if from_name and a not in names:
                names[a] = decode_mime_words(from_name)

    upserted = 0
    for email, sent in sent_counts.items():
        recv = received_counts.get(email, 0)
        if not should_add(email, sent=sent, received=recv):
            continue
        contact = session.exec(select(Contact).where(Contact.email == email)).first()
        if contact is None:
            contact = Contact(email=email, source="scanned")
            session.add(contact)
        # Fill/repair the name (overwrite if missing or still MIME-encoded).
        if not contact.name or contact.name.startswith("=?"):
            contact.name = names.get(email, contact.name)
        contact.times_sent = sent
        contact.times_received = recv
        contact.is_known_domain = domain_of(email) in KNOWN_DOMAINS
        if email in last_sent:
            contact.last_contacted = last_sent[email]
        upserted += 1

    session.commit()
    return upserted
