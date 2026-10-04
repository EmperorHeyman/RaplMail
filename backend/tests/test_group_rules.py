"""The "put in group" rules: file mail into a Smart Inbox group (built-in or a
custom one like "HR system") instead of a folder.

They classify rather than act, so they must: never stop other rules from
running, survive every re-file pass (the startup recategorize, a sender reset),
and let go of their mail again when the rule is turned off or deleted.
"""
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import (Account, Folder, FolderRole, Message, Rule, RuleAction,
                        RuleField, RuleOp)
from app.providers.base import HeaderInfo
from app.sync.rules import MessageFields, first_matching_action, group_for

GROUP = "grp_hrsystem"


def _s():
    return Session(get_engine())


_n = 0


def _seed(sender: str, subjects: list[str]):
    """An account + INBOX holding one message per subject from `sender`."""
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"grp{_n}@me.example")
        s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        ids = []
        for i, subj in enumerate(subjects):
            m = Message(account_id=acct.id, folder_id=f.id, uid=9000 + _n * 10 + i,
                        message_id=f"<grp-{_n}-{i}@x>", from_addr=sender,
                        from_name="HR", subject=subj, category="updates")
            s.add(m); s.commit(); s.refresh(m); ids.append(m.id)
        return acct.id, f.id, ids


def _cats(ids):
    with _s() as s:
        return [s.get(Message, i).category for i in ids]


def _rule(**kw):
    body = {"name": "HR", "match_field": "from", "match_op": "contains",
            "match_value": "", "action": "set_group", "action_arg": GROUP}
    body.update(kw)
    return body


def _wipe_rules():
    with _s() as s:
        for r in s.exec(select(Rule)).all():
            s.delete(r)
        s.commit()


# --- matching ------------------------------------------------------------------

def test_group_rules_never_stop_other_rules():
    grp = Rule(order=0, match_field=RuleField.from_addr, match_op=RuleOp.contains,
               match_value="hr@", action=RuleAction.set_group, action_arg=GROUP)
    read = Rule(order=1, match_field=RuleField.from_addr, match_op=RuleOp.contains,
                match_value="hr@", action=RuleAction.mark_read)
    f = MessageFields(from_addr="hr@corp.example", to_addrs=[], subject="Payslip")
    assert group_for([grp, read], f) == GROUP
    # The group rule is first by order, but it already ran at categorize time -
    # the mark-read rule still gets its turn.
    assert first_matching_action([grp, read], f) is read


def test_group_rule_can_regroup_a_category():
    grp = Rule(match_field=RuleField.category, match_op=RuleOp.equals,
               match_value="newsletters", action=RuleAction.set_group, action_arg=GROUP)
    assert group_for([grp], MessageFields(from_addr="a@b.c", to_addrs=[], subject="x",
                                          category="newsletters")) == GROUP
    assert group_for([grp], MessageFields(from_addr="a@b.c", to_addrs=[], subject="x",
                                          category="social")) is None


def test_disabled_or_targetless_group_rule_does_nothing():
    f = MessageFields(from_addr="hr@corp.example", to_addrs=[], subject="x")
    off = Rule(enabled=False, match_field=RuleField.from_addr, match_value="hr@",
               action=RuleAction.set_group, action_arg=GROUP)
    blank = Rule(match_field=RuleField.from_addr, match_value="hr@",
                 action=RuleAction.set_group, action_arg="")
    assert group_for([off, blank], f) is None


# --- existing mail ---------------------------------------------------------------

def test_apply_files_existing_mail_and_it_survives_recategorize(client):
    _wipe_rules()
    sender = "noreply@hr-apply.example"
    _aid, _fid, ids = _seed(sender, ["Payslip July", "Vacation approved"])
    try:
        body = _rule(match_value="hr-apply.example")
        assert client.post("/rules", json=body).status_code == 201
        r = client.post("/rules/apply", json=body)
        assert r.status_code == 200 and r.json()["applied"] == 2
        assert _cats(ids) == [GROUP, GROUP]
        # The startup pass used to recompute from heuristics alone - which would
        # throw everything back out of the group on every launch.
        assert client.post("/messages/recategorize").status_code == 200
        assert _cats(ids) == [GROUP, GROUP]
        # And the Smart Inbox sees it as a group of its own.
        groups = client.get("/messages/smart-groups", params={"role": "inbox"}).json()
        assert groups[GROUP]["count"] >= 2
    finally:
        _wipe_rules()


def test_disabling_then_deleting_the_rule_releases_its_mail(client):
    _wipe_rules()
    sender = "noreply@hr-release.example"
    _aid, _fid, ids = _seed(sender, ["Payslip", "Payslip"])
    try:
        body = _rule(match_value="hr-release.example")
        rid = client.post("/rules", json=body).json()["id"]
        client.post("/rules/apply", json=body)
        assert _cats(ids) == [GROUP, GROUP]

        off = client.put(f"/rules/{rid}", json={**body, "enabled": False})
        assert off.status_code == 200
        # Back to what the heuristic says (noreply@ + no keywords = newsletters),
        # not left stranded in a group no rule fills any more.
        assert GROUP not in _cats(ids)

        assert client.put(f"/rules/{rid}", json={**body, "enabled": True}).status_code == 200
        assert _cats(ids) == [GROUP, GROUP]

        assert client.delete(f"/rules/{rid}").status_code == 204
        assert GROUP not in _cats(ids)
    finally:
        _wipe_rules()


def test_rule_outranks_a_sender_override_and_says_so(client):
    _wipe_rules()
    sender = "noreply@hr-held.example"
    _aid, _fid, ids = _seed(sender, ["Payslip"])
    try:
        body = _rule(match_value="hr-held.example")
        client.post("/rules", json=body)
        client.post("/rules/apply", json=body)
        r = client.post("/messages/sender-category", json={"email": sender, "category": "social"})
        assert r.status_code == 200
        assert r.json()["held"] == 1          # the UI explains why it didn't move
        assert _cats(ids) == [GROUP]
        # Resetting the sender goes through the same pass - still grouped.
        client.post("/messages/sender-category", json={"email": sender, "category": "auto"})
        assert _cats(ids) == [GROUP]
    finally:
        client.post("/messages/sender-category", json={"email": sender, "category": "auto"})
        _wipe_rules()


def test_sender_override_without_a_rule_still_moves_everything(client):
    _wipe_rules()
    sender = "noreply@plain-override.example"
    _aid, _fid, ids = _seed(sender, ["a", "b"])
    try:
        r = client.post("/messages/sender-category", json={"email": sender, "category": GROUP})
        assert r.status_code == 200 and r.json()["held"] == 0
        assert _cats(ids) == [GROUP, GROUP]
    finally:
        client.post("/messages/sender-category", json={"email": sender, "category": "auto"})


# --- new mail through the sync ---------------------------------------------------

def test_sync_files_new_mail_into_the_group(client):
    from app.sync.engine import SyncManager
    _aid, fid, _ids = _seed("someone@else.example", [])
    rule = Rule(match_field=RuleField.from_domain, match_op=RuleOp.ends_with,
                match_value="hr-sync.example", action=RuleAction.set_group, action_arg=GROUP)
    mgr = SyncManager.__new__(SyncManager)
    with _s() as s:
        folder = s.get(Folder, fid)
        acct = s.get(Account, folder.account_id)
        hit = mgr._upsert_message(s, acct, folder, HeaderInfo(
            uid=1, message_id="<hr-sync-1@x>", subject="Payslip",
            from_addr="noreply@hr-sync.example", from_name="HR"), {}, None, [rule])
        miss = mgr._upsert_message(s, acct, folder, HeaderInfo(
            uid=2, message_id="<hr-sync-2@x>", subject="Hello",
            from_addr="friend@elsewhere.example", from_name="Friend"), {}, None, [rule])
        s.commit()
        assert hit.category == GROUP
        assert miss.category == "primary"


def test_deleting_a_group_releases_rules_overrides_and_mail(client):
    _wipe_rules()
    ruled = "noreply@hr-gone.example"
    tagged = "boss@hr-gone-override.example"
    _aid, _fid, ids = _seed(ruled, ["Payslip"])
    _aid2, _fid2, ids2 = _seed(tagged, ["Hi"])
    try:
        body = _rule(match_value="hr-gone.example")
        client.post("/rules", json=body)
        client.post("/rules/apply", json=body)
        client.post("/messages/sender-category", json={"email": tagged, "category": GROUP})
        assert _cats(ids + ids2) == [GROUP, GROUP]

        r = client.post("/messages/release-group", json={"group": GROUP})
        assert r.status_code == 200 and r.json()["rules"] == 1
        assert GROUP not in _cats(ids + ids2)
        with _s() as s:
            assert not s.exec(select(Rule).where(Rule.action_arg == GROUP)).all()
        # And it stays released through the next startup pass.
        client.post("/messages/recategorize")
        assert GROUP not in _cats(ids + ids2)
    finally:
        _wipe_rules()


# --- "Sender address equals" on a sender with a display name ---------------------

def test_sender_equals_matches_a_named_sender():
    """The real-world miss: "from equals hrms@a123systems.cz" was compared to
    the joined "Robee - A123 Systems hrms@a123systems.cz" and never matched -
    which also broke every mute/block-sender rule for named senders."""
    from app.sync.rules import rule_matches
    f = MessageFields(from_addr="hrms@a123systems.cz", to_addrs=[], subject="Payslip",
                      from_name="Robee - A123 Systems")
    by_addr = Rule(match_field=RuleField.from_addr, match_op=RuleOp.equals,
                   match_value="HRMS@a123systems.cz", action=RuleAction.mark_done)
    by_name = Rule(match_field=RuleField.from_addr, match_op=RuleOp.equals,
                   match_value="Robee - A123 Systems", action=RuleAction.mark_done)
    partial = Rule(match_field=RuleField.from_addr, match_op=RuleOp.equals,
                   match_value="a123systems.cz", action=RuleAction.mark_done)
    contains_name = Rule(match_field=RuleField.from_addr, match_op=RuleOp.contains,
                         match_value="robee", action=RuleAction.mark_done)
    assert rule_matches(by_addr, f)
    assert rule_matches(by_name, f)
    assert not rule_matches(partial, f)          # equals is still exact
    assert rule_matches(contains_name, f)


def test_named_sender_rule_fills_the_group_on_apply(client):
    _wipe_rules()
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"grp{_n}@me.example"); s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        m = Message(account_id=acct.id, folder_id=f.id, uid=99000 + _n, message_id=f"<named-{_n}@x>",
                    from_addr="hrms@named-sender.example", from_name="Robee - A123 Systems",
                    subject="Schvaleni dovolene", category="primary")
        s.add(m); s.commit(); s.refresh(m); mid = m.id
    try:
        body = _rule(match_field="from", match_op="equals", match_value="hrms@named-sender.example")
        client.post("/rules", json=body)
        r = client.post("/rules/apply", json=body)
        assert r.json()["applied"] == 1
        assert _cats([mid]) == [GROUP]
    finally:
        _wipe_rules()


# --- new grouped mail stays visible in the main list ------------------------------

def test_new_grouped_mail_stays_in_the_main_list_until_read(client):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"grp{_n}@me.example"); s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        uids = iter(range(98000 + _n * 10, 98000 + _n * 10 + 10))
        def mk(subj, seen, hours):
            m = Message(account_id=acct.id, folder_id=f.id, uid=next(uids),
                        message_id=f"<keep-{_n}-{subj}@x>", from_addr="news@keep.example",
                        subject=subj, category="newsletters", is_seen=seen,
                        date=now - timedelta(hours=hours))
            s.add(m); s.commit(); s.refresh(m); return m.id
        fresh_unread = mk("fresh", False, 2)
        fresh_read = mk("freshread", True, 2)
        old_unread = mk("oldunread", False, 24 * 10)
        fid = f.id
    base = {"folder_id": fid, "exclude_categories": "newsletters,social"}
    ids = {m["id"] for m in client.get("/messages", params=base).json()}
    assert not ids & {fresh_unread, fresh_read, old_unread}          # grouped = hidden
    ids = {m["id"] for m in client.get("/messages", params={**base, "keep_new_days": 3}).json()}
    assert fresh_unread in ids                                       # new -> stays in the list
    assert fresh_read not in ids and old_unread not in ids           # read / old -> folded into the card
