"""Typed search operators: from: / to: / cc: / subject: ..., with or without a
space after the colon (people type "from: lpeterek" out of habit)."""
from sqlmodel import Session

from app.api.messages import _parse_query
from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message


def test_space_after_colon_is_fine():
    assert _parse_query("from: lpeterek") == ({"from": "lpeterek"}, "")
    assert _parse_query("from:lpeterek") == ({"from": "lpeterek"}, "")
    assert _parse_query('subject: "budget 2027"') == ({"subject": "budget 2027"}, "")


def test_free_text_around_operators_survives():
    f, free = _parse_query("invoice from: lpeterek is:unread")
    assert f == {"from": "lpeterek", "unread": True}
    assert free == "invoice"


def test_cc_is_an_operator():
    assert _parse_query("cc: boss@corp.example") == ({"cc": "boss@corp.example"}, "")


def test_cc_filters_on_cc_recipients(client):
    with Session(get_engine()) as s:
        a = Account(email="ccsearch@me.example")
        s.add(a); s.commit(); s.refresh(a)
        f = Folder(account_id=a.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        hit = Message(account_id=a.id, folder_id=f.id, uid=71001, message_id="<cc-hit@x>",
                      from_addr="x@y.example", subject="cc search hit",
                      to_addrs=["me@me.example"], cc_addrs=["boss-cc-search@corp.example"])
        miss = Message(account_id=a.id, folder_id=f.id, uid=71002, message_id="<cc-miss@x>",
                       from_addr="x@y.example", subject="cc search miss",
                       to_addrs=["boss-cc-search@corp.example"], cc_addrs=[])
        s.add(hit); s.add(miss); s.commit()
    rows = client.get("/messages", params={"q": "cc: boss-cc-search", "limit": 50}).json()
    subjects = {r["subject"] for r in rows}
    assert "cc search hit" in subjects
    assert "cc search miss" not in subjects   # only in To, not Cc
