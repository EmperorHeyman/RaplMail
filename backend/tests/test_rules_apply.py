"""POST /rules/apply - apply a rule to EXISTING mail (rules otherwise only run
on new arrivals). Focused on the subject-rule case the user hit: a daily report
whose subject has a fixed part plus a changing date should be markable done.
"""
from sqlmodel import Session

from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message


def _s():
    return Session(get_engine())


_n = 0


def _seed_subject(subject, n=1):
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"rule{_n}@ex.com"); s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        ids = []
        for i in range(n):
            m = Message(account_id=acct.id, folder_id=f.id, uid=7000 + _n * 10 + i,
                        message_id=f"<rule-{_n}-{i}>", from_addr="z@ex.com", subject=subject)
            s.add(m); s.commit(); s.refresh(m); ids.append(m.id)
        return acct.id, ids


def test_apply_subject_contains_mark_done(client):
    aid, ids = _seed_subject("[ZERV] Daily Report - 2026-07-04 (FPY 0.0%)", n=2)
    r = client.post("/rules/apply", json={"account_id": aid, "match_field": "subject",
                                          "match_op": "contains", "match_value": "[ZERV] Daily Report",
                                          "action": "mark_done"})
    assert r.status_code == 200 and r.json()["applied"] == 2
    with _s() as s:
        for mid in ids:
            assert s.get(Message, mid).is_done is True


def test_apply_subject_regex_mark_done(client):
    aid, ids = _seed_subject("[ZERV] Daily Report - 2026-07-05 (FPY 12.3%)")
    r = client.post("/rules/apply", json={"account_id": aid, "match_field": "subject",
                                          "match_op": "regex",
                                          "match_value": r"\[ZERV\] Daily Report .* \(FPY",
                                          "action": "mark_done"})
    assert r.status_code == 200 and r.json()["applied"] == 1
    with _s() as s:
        assert s.get(Message, ids[0]).is_done is True


def test_apply_no_match_is_zero(client):
    aid, _ = _seed_subject("Totally unrelated subject line")
    r = client.post("/rules/apply", json={"account_id": aid, "match_field": "subject",
                                          "match_op": "contains", "match_value": "ZERV",
                                          "action": "mark_done"})
    assert r.status_code == 200 and r.json()["applied"] == 0


def test_preview_finds_match_among_many(client):
    # Regression: preview used to scan the first 2000 rows UNORDERED, so a recent
    # matching mail among a big pile was never looked at → 0. Now it matches in SQL
    # over the whole mailbox.
    aid, _ = _seed_subject("Noise subject A", n=30)
    _seed_subject("[ZERV] Daily Report - 2026-07-06 (FPY 90.0%)")  # different account, recent
    # Preview a global (all-account) subject rule.
    r = client.post("/rules/preview", json={"match_field": "subject", "match_op": "contains",
                                            "match_value": "[ZERV] Daily Report", "action": "mark_done"})
    assert r.status_code == 200 and r.json()["match_count"] >= 1


def test_apply_from_display_name(client):
    # "from contains ZERV Reporter" must match the DISPLAY NAME, not only the address.
    global _n
    _n += 1
    with _s() as s:
        acct = Account(email=f"fromname{_n}@ex.com"); s.add(acct); s.commit(); s.refresh(acct)
        f = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(f); s.commit(); s.refresh(f)
        m = Message(account_id=acct.id, folder_id=f.id, uid=9000 + _n, message_id=f"<fn-{_n}>",
                    from_name="ZERV Reporter", from_addr="tickety@a123systems.cz", subject="Daily")
        s.add(m); s.commit(); s.refresh(m); mid = m.id
        aid = acct.id
    r = client.post("/rules/apply", json={"account_id": aid, "match_field": "from",
                                          "match_op": "contains", "match_value": "ZERV Reporter",
                                          "action": "mark_done"})
    assert r.status_code == 200 and r.json()["applied"] == 1
    with _s() as s:
        assert s.get(Message, mid).is_done is True


def test_apply_mark_read(client):
    aid, ids = _seed_subject("Newsletter: weekly digest", n=3)
    r = client.post("/rules/apply", json={"account_id": aid, "match_field": "subject",
                                          "match_op": "contains", "match_value": "Newsletter",
                                          "action": "mark_read"})
    assert r.json()["applied"] == 3
    with _s() as s:
        for mid in ids:
            assert s.get(Message, mid).is_seen is True
