"""Rules travelling device-to-device: the config bundle must survive the JSON
round-trip (enum members whose NAME differs from their VALUE - RuleField
'from'/'to' - are the trap), import must dedup, imported rules must actually
match mail, and the automatic LWW rules channel must adopt/ignore correctly."""
import json

from sqlmodel import Session, select

from app.api.settings import _apply_config, export_bundle, export_rules
from app.core.db import get_engine
from app.models import Rule, RuleAction, RuleField, RuleOp
from app.sync import devicesync
from app.sync.rules import MessageFields, rule_matches


def _s():
    return Session(get_engine())


def _wipe_rules():
    with _s() as s:
        for r in s.exec(select(Rule)).all():
            s.delete(r)
        s.commit()


def test_rule_bundle_json_roundtrip_applies_and_matches(client):
    _wipe_rules()
    try:
        # Device A: a rule created through the API (the normal path).
        r = client.post("/rules", json={
            "name": "spam-away", "match_field": "from", "match_op": "contains",
            "match_value": "newsletter@", "action": "move", "action_arg": "Archive",
        })
        assert r.status_code == 201, r.text

        # Device A publishes: export bundle -> JSON (same as the sync payload).
        with _s() as s:
            bundle = json.loads(json.dumps(export_bundle(s), default=str))
        assert bundle["rules"], "rule missing from the export bundle"

        # Device B: no rules yet; pull applies the bundle.
        _wipe_rules()
        with _s() as s:
            res = _apply_config(s, {"rules": bundle["rules"]})
            s.commit()
        assert res.rules == 1

        with _s() as s:
            rows = s.exec(select(Rule)).all()
            assert len(rows) == 1
            got = rows[0]
            assert got.match_field == RuleField.from_addr
            assert got.match_op == RuleOp.contains
            assert got.action == RuleAction.move
            # And it must actually match mail on device B.
            assert rule_matches(got, MessageFields(
                from_addr="newsletter@shop.com", to_addrs=[], subject="Sale")) is True

        # Applying the same bundle again must NOT duplicate the rule.
        with _s() as s:
            res2 = _apply_config(s, {"rules": bundle["rules"]})
            s.commit()
        assert res2.rules == 0
        with _s() as s:
            assert len(s.exec(select(Rule)).all()) == 1
    finally:
        _wipe_rules()


def _blob_backup():
    from app.api.settings import _get_blob
    with _s() as s:
        return _get_blob(s)


def _blob_restore(before):
    from app.api.settings import _set_blob
    with _s() as s:
        _set_blob(s, before)


def test_rule_crud_stamps_sync_ts(client):
    before = _blob_backup()
    _wipe_rules()
    try:
        from app.api.settings import _get_blob
        r = client.post("/rules", json={
            "name": "t", "match_field": "subject", "match_op": "contains",
            "match_value": "xyz", "action": "mark_read",
        })
        assert r.status_code == 201
        with _s() as s:
            ts1 = _get_blob(s).get("syncRulesTs")
        assert ts1, "create didn't stamp syncRulesTs"
        rid = r.json()["id"]
        assert client.delete(f"/rules/{rid}").status_code == 204
        with _s() as s:
            ts2 = _get_blob(s).get("syncRulesTs")
        assert ts2 and ts2 > ts1, "delete didn't bump syncRulesTs"
    finally:
        _wipe_rules()
        _blob_restore(before)


def test_rules_lww_adopt_edit_and_delete(client):
    """A fresher peer payload replaces the whole local set (so edits AND deletes
    propagate); a stale or echoed payload never does."""
    before = _blob_backup()
    _wipe_rules()
    try:
        from app.api.settings import _get_blob, _set_blob
        with _s() as s:   # local set: two rules, last touched at T1
            s.add(Rule(name="keep-edited", match_value="old", match_field=RuleField.subject,
                       match_op=RuleOp.contains, action=RuleAction.mark_read))
            s.add(Rule(name="to-be-deleted", match_value="bye", match_field=RuleField.subject,
                       match_op=RuleOp.contains, action=RuleAction.mark_read))
            s.commit()
            blob = _get_blob(s); blob["syncRulesTs"] = "2026-07-01T10:00:00+00:00"
            _set_blob(s, blob)

        peer = {   # the peer edited one rule and deleted the other at T2 > T1
            "rules_ts": "2026-07-02T10:00:00+00:00",
            "rules": [{"name": "keep-edited", "enabled": True, "order": 0,
                       "match_field": "subject", "match_op": "contains",
                       "match_value": "new", "action": "mark_read", "action_arg": ""}],
        }
        with _s() as s:
            assert devicesync._apply_rules_payload(s, peer) is True
            s.commit()
        with _s() as s:
            rows = s.exec(select(Rule)).all()
            assert len(rows) == 1 and rows[0].match_value == "new"   # edit + delete adopted
            blob = _get_blob(s)
            assert blob["syncRulesTs"] == peer["rules_ts"]
            assert blob["syncRulesPushedTs"] == peer["rules_ts"]      # echo guard

        # The same (or an older) payload must be a no-op now.
        with _s() as s:
            assert devicesync._apply_rules_payload(s, peer) is False
            assert devicesync._apply_rules_payload(s, {
                "rules_ts": "2026-06-30T10:00:00+00:00", "rules": []}) is False
        # A payload without a rules list never wipes anything.
        with _s() as s:
            assert devicesync._apply_rules_payload(s, {"rules_ts": "2027-01-01T00:00:00+00:00"}) is False
            assert len(s.exec(select(Rule)).all()) == 1
    finally:
        _wipe_rules()
        _blob_restore(before)


def test_export_rules_shape(client):
    _wipe_rules()
    try:
        with _s() as s:
            s.add(Rule(name="x", match_value="v", match_field=RuleField.from_addr,
                       match_op=RuleOp.equals, action=RuleAction.archive))
            s.commit()
        with _s() as s:
            out = json.loads(json.dumps(export_rules(s), default=str))
        assert out == [{"name": "x", "enabled": True, "order": 0, "match_field": "from",
                        "match_op": "equals", "match_value": "v", "action": "archive",
                        "action_arg": ""}]
    finally:
        _wipe_rules()
