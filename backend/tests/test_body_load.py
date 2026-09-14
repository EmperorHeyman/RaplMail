"""Opening a message must either show it or say it couldn't - never blank it.

Three defects made mail "sometimes not load", and they compounded:

1. `fetch_raw` read only the `b"RFC822"` key out of the FETCH result. RFC 3501
   makes `RFC822` equivalent to `BODY[]` and lets a server answer with either
   name; imapclient keys the result by whatever the server echoed. On a server
   that answers `BODY[]`, every message came back as zero bytes.
2. Those zero bytes were cached as the message body with `body_fetched=1`, and
   nothing ever retried - so the mail was blank forever, not just that once.
3. The post-fetch repair pass ran unguarded, and two of its triggers are
   conditions a re-fetch cannot clear (a multipart/mixed whose only non-text
   part is an inline logo; an unresolvable `cid:` reference). Those messages
   re-downloaded in full on every single open.
"""
import pytest
from sqlmodel import Session

from app.api.messages import BodyUnavailable, _fetch_body
from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message
from app.providers.imap_smtp import _bodystructure_has_attachment, _raw_from_fetch

_RAW = b"From: a@x.cz\r\nSubject: hi\r\n\r\nbody\r\n"


def _s():
    return Session(get_engine())


# --- 1. the FETCH response key ----------------------------------------------

def test_raw_is_found_under_every_spelling_a_server_may_use():
    assert _raw_from_fetch({b"SEQ": 1, b"RFC822": _RAW}) == _RAW
    # Exchange/Zimbra answer an RFC822 fetch by naming the item BODY[].
    assert _raw_from_fetch({b"SEQ": 1, b"BODY[]": _RAW}) == _RAW
    # Anything else large and unrecognised is the message, by elimination.
    assert _raw_from_fetch({b"SEQ": 1, b"UID": 7, b"BODY[TEXT]": _RAW}) == _RAW


def test_metadata_is_never_mistaken_for_the_message():
    info = {b"SEQ": 1, b"UID": 7, b"FLAGS": (b"\\Seen",), b"RFC822.SIZE": 4321}
    assert _raw_from_fetch(info) == b""


def test_nothing_at_all_reads_as_nothing():
    assert _raw_from_fetch({}) == b""
    assert _raw_from_fetch({b"SEQ": 1}) == b""


# --- 2. an unfetched body is never cached -----------------------------------

class _EmptyPool:
    """Stands in for a server that has no such UID any more."""

    @staticmethod
    def fetch_raw(account, folder_path, uid):
        return b""


def test_fetch_body_raises_rather_than_returning_an_empty_message(monkeypatch, client):
    from app.providers import pool as pool_mod
    monkeypatch.setattr(pool_mod, "pool", _EmptyPool)
    with _s() as s:
        acct = Account(email="blank@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        fld = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(fld); s.commit(); s.refresh(fld)
        with pytest.raises(BodyUnavailable):
            _fetch_body(acct, fld, 999)


def test_open_leaves_no_cache_behind_when_the_body_could_not_be_fetched(monkeypatch, client):
    """The endpoint answers with the placeholder and the row stays unfetched, so
    the next open tries again instead of serving a permanent blank."""
    from app.providers import pool as pool_mod
    monkeypatch.setattr(pool_mod, "pool", _EmptyPool)
    with _s() as s:
        acct = Account(email="blank2@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        fld = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(fld); s.commit(); s.refresh(fld)
        m = Message(account_id=acct.id, folder_id=fld.id, uid=42, subject="gone",
                    from_addr="a@x.cz", message_id="<gone@x>")
        s.add(m); s.commit(); s.refresh(m)
        mid = m.id

    r = client.get(f"/messages/{mid}")
    assert r.status_code == 200
    assert "load this message body" in r.json()["html"]
    with _s() as s:
        assert not s.get(Message, mid).body_fetched


def test_blanked_rows_are_repaired_on_startup(client):
    """The scar left by the old build: body_fetched with nothing in it."""
    from app.core.db import _REPAIRS
    from sqlalchemy import text as sa_text
    with _s() as s:
        acct = Account(email="scar@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        fld = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(fld); s.commit(); s.refresh(fld)
        blank = Message(account_id=acct.id, folder_id=fld.id, uid=1, body_fetched=True,
                        body_html="", body_text="", from_addr="a@x.cz")
        # A mail that is genuinely body-less but did carry a file must be left alone.
        fileonly = Message(account_id=acct.id, folder_id=fld.id, uid=2, body_fetched=True,
                           body_html="", body_text="", from_addr="scanner@x.cz",
                           attachments=[{"index": 0, "filename": "scan.pdf"}])
        ok = Message(account_id=acct.id, folder_id=fld.id, uid=3, body_fetched=True,
                     body_html="<p>hi</p>", from_addr="a@x.cz")
        s.add(blank); s.add(fileonly); s.add(ok); s.commit()
        ids = (blank.id, fileonly.id, ok.id)
        for stmt in _REPAIRS:
            s.exec(sa_text(stmt))
        s.commit()
    with _s() as s:
        assert not s.get(Message, ids[0]).body_fetched   # cleared -> refetched on open
        assert s.get(Message, ids[1]).body_fetched       # attachment-only, left alone
        assert s.get(Message, ids[2]).body_fetched       # has a body, left alone


# --- 3. the repair pass is one-shot -----------------------------------------

def test_bodystructure_guess_overreports_attachments():
    """Why the repair pass needs a flag: this guess says "has an attachment" for
    any multipart/mixed, including one whose only extra part is an inline logo.
    The parsed attachment list then comes back empty, and the two disagree
    forever - which is exactly the condition that used to retrigger the fetch."""
    alternative = ([(b"TEXT", b"PLAIN"), (b"TEXT", b"HTML")], b"ALTERNATIVE")
    assert not _bodystructure_has_attachment(alternative)
    mixed_with_logo = ([alternative, (b"IMAGE", b"PNG")], b"MIXED")
    assert _bodystructure_has_attachment(mixed_with_logo)


def test_repair_pass_runs_once_even_when_it_cannot_clear_its_trigger(monkeypatch, client):
    calls = []

    def _counting_fetch(account, folder, uid):
        calls.append(uid)
        # A mail with an inline logo only: has_attachments was guessed true at
        # sync, the parse finds no real attachment, and no re-fetch can change
        # that. The old code re-downloaded the whole message on every open.
        return ("<p>hi <img src='cid:logo'></p>", "hi", "", [], [],
                {"status": "pass"}, "", {"to": ["me@x.cz"], "cc": [], "delivered_to": []})

    monkeypatch.setattr("app.api.messages._fetch_body", _counting_fetch)
    with _s() as s:
        acct = Account(email="loop@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        fld = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(fld); s.commit(); s.refresh(fld)
        m = Message(account_id=acct.id, folder_id=fld.id, uid=7, from_addr="a@x.cz",
                    message_id="<logo@x>", subject="newsletter",
                    body_fetched=True, body_html="<p>hi <img src='cid:logo'></p>",
                    has_attachments=True, attachments=[], auth_status="pass")
        s.add(m); s.commit(); s.refresh(m)
        mid = m.id

    for _ in range(3):
        assert client.get(f"/messages/{mid}").status_code == 200
    assert len(calls) == 1, f"re-fetched {len(calls)} times; the repair pass must be one-shot"
    with _s() as s:
        row = s.get(Message, mid)
        assert row.repaired
        assert not row.has_attachments   # corrected from the parse: the logo is inline
