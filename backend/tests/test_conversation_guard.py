"""A reply you were waiting for must stay in the inbox.

The category heuristics are deliberately broad word lists - fine for cold bulk
mail, wrong for a human answer. An answer from info@/support@, or one whose
subject or quoted tail carries "objednávka"/"confirm"/"akce"/"unsubscribe", used
to be filed under newsletters/updates/promotions and vanish from the inbox. The
conversation guard overrides that for mail continuing a conversation you are
part of, via two signals: In-Reply-To resolving to a message you sent, and a
"Re:" from someone you have written to.

Also covers the recipient-line repair: a Bcc'd message (no To/Cc header at all)
now carries its Delivered-To trace instead of showing an empty recipient line.
"""
from sqlmodel import Session

from app.api.messages import _heal_recipients, _mime_recipients
from app.core.db import get_engine
from app.models import Account, Contact, Folder, FolderRole, Message
from app.providers.base import HeaderInfo
from app.sync.categorize import (Conversation, build_conversation, categorize,
                                 is_reply_subject)


def _s():
    return Session(get_engine())


_n = 0


def _seed(email: str = "me@example.com"):
    """An account with an INBOX and a Sent folder."""
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"{_n}-{email}", aliases=["Sales <sales@example.com>"])
        s.add(acct); s.commit(); s.refresh(acct)
        inbox = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        sent = Folder(account_id=acct.id, name="Sent", path="Sent", role=FolderRole.sent)
        s.add(inbox); s.add(sent); s.commit(); s.refresh(inbox); s.refresh(sent)
        return acct.id, inbox.id, sent.id, acct.email


def _mgr():
    from app.sync.engine import SyncManager
    return SyncManager.__new__(SyncManager)   # only the plain _upsert_message is needed


# --- the heuristics the guard has to override -------------------------------

def test_bulk_wording_still_files_cold_mail_away():
    assert categorize("info@brain.cz", "Jan", "Potvrzení objednávky", "") == "updates"
    assert categorize("noreply@shop.cz", "Shop", "Novinky a akce", "") == "promotions"
    assert categorize("support@vendor.com", "V", "Tips", "unsubscribe here") == "newsletters"


def test_guard_pulls_those_same_mails_back_to_primary():
    assert categorize("info@brain.cz", "Jan", "Potvrzení objednávky", "",
                      conversation=True) == "primary"
    assert categorize("noreply@shop.cz", "Shop", "Novinky a akce", "",
                      conversation=True) == "primary"
    assert categorize("support@vendor.com", "V", "Tips", "unsubscribe here",
                      conversation=True) == "primary"


def test_guard_does_not_swallow_invitation_responses():
    # Accept/decline IS a reply to an invite you sent - it keeps its own category.
    assert categorize("jan@brain.cz", "Jan", "Accepted: Sprint review", "",
                      conversation=True) == "invitation_responses"


def test_reply_prefixes():
    assert is_reply_subject("Re: hello")
    assert is_reply_subject("odp: ahoj")
    assert is_reply_subject("AW: Angebot")
    assert is_reply_subject("Re[2]: hello")
    assert is_reply_subject("Re: Odp: hello")
    assert not is_reply_subject("Novinky")
    assert not is_reply_subject("Repairs this week")   # "Re" must be followed by a colon


# --- the two signals --------------------------------------------------------

def test_signal_parent_written_by_me():
    c = Conversation(mine={"me@example.com"}, corresponded=set())
    assert c.is_conversation(from_addr="x@y.cz", subject="anything",
                             parent_from="Me@Example.com")   # case-insensitive
    assert not c.is_conversation(from_addr="x@y.cz", subject="anything",
                                 parent_from="someone@else.cz")


def test_signal_re_from_someone_i_wrote_to():
    c = Conversation(mine={"me@example.com"}, corresponded={"jan@brain.cz"})
    assert c.is_conversation(from_addr="Jan@Brain.cz", subject="Re: ahoj")
    # A stranger's "Re:" (the classic spam trick) is not a conversation.
    assert not c.is_conversation(from_addr="spam@ads.cz", subject="Re: ahoj")
    # Neither is a fresh newsletter from someone you once emailed.
    assert not c.is_conversation(from_addr="jan@brain.cz", subject="Novinky")


# --- what the "Reply" badge is allowed to claim -----------------------------

def test_badge_needs_the_message_to_actually_answer_mine():
    c = Conversation(mine={"me@example.com"}, corresponded={"jan@brain.cz"})
    assert c.answers_my_message(parent_from="Me@Example.com")
    # A "Re:" from a familiar address is enough to keep mail in the inbox, but
    # NOT enough to call it a reply - that is the ticket-system false positive.
    assert c.is_conversation(from_addr="jan@brain.cz", subject="Re: ahoj")
    assert not c.answers_my_message(parent_from="")


def test_a_ticket_system_is_never_a_reply_however_it_threads():
    """You replied to a ticket once; its notifications thread onto your message
    and carry "Re: [#123]" forever. Neither may pass for a personal reply."""
    c = Conversation(mine={"me@example.com"}, corresponded={"support@desk.cz"})
    # Threads directly onto your own message, but announces itself as a machine.
    assert not c.answers_my_message(parent_from="me@example.com", automated=True)
    assert not c.is_conversation(from_addr="support@desk.cz", subject="Re: [#123] update",
                                 parent_from="me@example.com", automated=True)
    # And the weak signal alone certainly doesn't badge it.
    assert not c.answers_my_message(parent_from="")
    # A person at that same address, writing by hand, still counts.
    assert c.answers_my_message(parent_from="me@example.com", automated=False)


def test_a_real_person_at_a_role_address_is_not_written_off_as_a_robot():
    """The other direction: guessing from the address used to call info@ a bot.
    Only the sender's own headers decide."""
    c = Conversation(mine={"me@example.com"}, corresponded={"info@brain.cz"})
    assert c.answers_my_message(parent_from="me@example.com", automated=False)
    assert c.is_conversation(from_addr="info@brain.cz", subject="Re: Objednávka 42",
                             automated=False)


def test_build_conversation_reads_accounts_aliases_contacts_and_sent(client):
    acct_id, _inbox_id, sent_id, email = _seed()
    with _s() as s:
        s.add(Message(account_id=acct_id, folder_id=sent_id, uid=1,
                      message_id="<sent-1@example.com>", from_addr=email,
                      to_addrs=["Fresh@Partner.cz"], subject="Nabídka"))
        s.add(Contact(email="scanned@partner.cz", times_sent=3))
        s.commit()
        convo = build_conversation(s)
    assert email.lower() in convo.mine
    assert "sales@example.com" in convo.mine           # alias, unwrapped from "Name <addr>"
    assert "scanned@partner.cz" in convo.corresponded  # address book
    assert "fresh@partner.cz" in convo.corresponded    # sent mail, before the book is rescanned


# --- end to end through the sync upsert -------------------------------------

def test_reply_to_my_mail_lands_in_primary(client):
    acct_id, inbox_id, sent_id, email = _seed()
    mgr = _mgr()
    with _s() as s:
        acct = s.get(Account, acct_id)
        sent, inbox = s.get(Folder, sent_id), s.get(Folder, inbox_id)
        # I wrote to info@brain.cz about an order.
        mgr._upsert_message(s, acct, sent, HeaderInfo(
            uid=1, message_id="<mine-1@example.com>", subject="Objednávka 42",
            from_addr=email, from_name="Me", to_addrs=["info@brain.cz"]))
        s.commit()
        convo = build_conversation(s)
        # They answer. Without the guard, "objednávka" alone files this under updates.
        reply = mgr._upsert_message(s, acct, inbox, HeaderInfo(
            uid=2, message_id="<theirs-1@brain.cz>", in_reply_to="<mine-1@example.com>",
            subject="Re: Objednávka 42", from_addr="info@brain.cz", from_name="Jan"), {}, convo)
        s.commit()
        assert reply.category == "primary"
        assert reply.is_reply_to_me      # drives the "Reply" badge in the list
        assert reply.thread_id   # threading still works off the same lookup


def test_cold_bulk_mail_is_unaffected_by_the_guard(client):
    acct_id, inbox_id, _sent_id, _email = _seed()
    mgr = _mgr()
    with _s() as s:
        acct, inbox = s.get(Account, acct_id), s.get(Folder, inbox_id)
        convo = build_conversation(s)
        m = mgr._upsert_message(s, acct, inbox, HeaderInfo(
            uid=9, message_id="<promo@shop.cz>", subject="Novinky a akce",
            from_addr="newsletter@shop.cz", from_name="Shop"), {}, convo)
        s.commit()
        assert m.category == "promotions"
        assert not m.is_reply_to_me


def test_sender_override_still_wins_over_the_guard(client):
    acct_id, inbox_id, sent_id, email = _seed()
    mgr = _mgr()
    with _s() as s:
        acct = s.get(Account, acct_id)
        sent, inbox = s.get(Folder, sent_id), s.get(Folder, inbox_id)
        mgr._upsert_message(s, acct, sent, HeaderInfo(
            uid=1, message_id="<mine-2@example.com>", subject="Hi",
            from_addr=email, from_name="Me", to_addrs=["news@vendor.com"]))
        s.commit()
        convo = build_conversation(s)
        m = mgr._upsert_message(s, acct, inbox, HeaderInfo(
            uid=2, message_id="<r2@vendor.com>", in_reply_to="<mine-2@example.com>",
            subject="Re: Hi", from_addr="news@vendor.com", from_name="News"),
            {"news@vendor.com": "newsletters"}, convo)
        s.commit()
        assert m.category == "newsletters"   # the user said so explicitly


# --- recipient line ---------------------------------------------------------

_BCC_MIME = b"""From: Jan Minarik <Jan.Minarik@brain.cz>
Subject: Tesime se na Vas
Delivered-To: me@example.com
Message-ID: <bulk-1@brain.cz>
Content-Type: text/plain; charset=utf-8

Vazeni obchodni pratele,
"""

_CC_MIME = b"""From: Jan <jan@brain.cz>
To: someone@else.cz
Cc: Me <me@example.com>, Other <other@x.cz>
Subject: Hi
Content-Type: text/plain; charset=utf-8

body
"""


def _parse(raw):
    import mailparser
    return _mime_recipients(mailparser.parse_from_bytes(raw))


def test_bcc_only_mail_exposes_its_delivery_trace():
    r = _parse(_BCC_MIME)
    assert r["to"] == [] and r["cc"] == []
    assert r["delivered_to"] == ["me@example.com"]


def test_cc_is_read_from_the_raw_headers():
    r = _parse(_CC_MIME)
    assert r["to"] == ["someone@else.cz"]
    assert r["cc"] == ["me@example.com", "other@x.cz"]


def test_heal_only_fills_gaps():
    # Envelope gave nothing: fill both from the headers.
    m = Message(account_id=1, folder_id=1, uid=1)
    _heal_recipients(m, _parse(_CC_MIME))
    assert m.to_addrs == ["someone@else.cz"]
    assert m.cc_addrs == ["me@example.com", "other@x.cz"]
    assert m.delivered_to == []          # a real To/Cc means the trace is noise

    # Envelope already had a To: it stays authoritative.
    m2 = Message(account_id=1, folder_id=1, uid=2, to_addrs=["envelope@x.cz"])
    _heal_recipients(m2, _parse(_CC_MIME))
    assert m2.to_addrs == ["envelope@x.cz"]

    # A Bcc'd copy: no To/Cc anywhere, so the trace is what the reader shows.
    m3 = Message(account_id=1, folder_id=1, uid=3)
    _heal_recipients(m3, _parse(_BCC_MIME))
    assert m3.to_addrs == [] and m3.delivered_to == ["me@example.com"]
