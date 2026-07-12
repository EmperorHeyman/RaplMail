"""Device sync core: crypto determinism, last-writer-wins merge, config-key
isolation, and a full serialize → encrypt → extract → decrypt → apply round-trip.

The IMAP APPEND/scan plumbing needs a live server, but everything correctness-
critical (the merge + the crypto + the payload) is exercised here against the
throwaway test DB."""
import json
from datetime import datetime

import pytest
from cryptography.fernet import InvalidToken
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, Folder, Message, MessageState
from app.sync import devicesync


def _s():
    return Session(get_engine())


def test_derive_fernet_deterministic_and_isolated(client):
    a = devicesync.derive_fernet("correct horse battery staple")
    b = devicesync.derive_fernet("correct horse battery staple")
    token = a.encrypt(b"hello")
    assert b.decrypt(token) == b"hello"                 # same passphrase → interoperable key
    with pytest.raises(InvalidToken):
        devicesync.derive_fernet("a different passphrase").decrypt(token)


def test_strip_sync_keys():
    out = devicesync._strip_sync_keys(
        {"syncEnabled": True, "syncAccountId": 3, "syncDeviceId": "x", "theme": "dark", "smartInbox": True})
    assert out == {"theme": "dark", "smartInbox": True}


def test_wrap_extract_roundtrip():
    raw = devicesync._wrap_message("TOKENDATA.123_-", "me@example.com", "devA")
    assert b"X-RaplMail-Sync" in raw and b"safe to ignore" in raw
    assert devicesync._extract_token(raw) == "TOKENDATA.123_-"


def test_extract_token_none_for_plain_mail():
    assert devicesync._extract_token(b"Subject: hi\r\n\r\njust a normal message") is None


def test_apply_states_last_writer_wins(client):
    email, mid = "lww@example.com", "<lww-1@example.com>"
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="INBOX", path="INBOX")
        s.add(folder); s.commit(); s.refresh(folder)
        s.add(Message(account_id=acct.id, folder_id=folder.id, uid=1, message_id=mid,
                      from_addr="x@y.com", subject="hi", is_done=False))
        s.add(MessageState(account_id=acct.id, message_id=mid, is_done=False,
                           updated_at=datetime(2026, 1, 1)))
        s.commit()

    # A newer remote op flips it, and adopts the SOURCE timestamp (not now()).
    with _s() as s:
        devicesync.apply_states(s, [{"email": email, "mid": mid, "done": True, "snooze": None,
                                     "presence": False, "pinned": False, "ts": datetime(2026, 6, 1).isoformat()}])
        s.commit()
    with _s() as s:
        st = s.exec(select(MessageState).where(MessageState.message_id == mid)).first()
        assert st.is_done is True
        assert st.updated_at == datetime(2026, 6, 1)      # source ts kept (onupdate didn't clobber it)
        m = s.exec(select(Message).where(Message.message_id == mid)).first()
        assert m.is_done is True                          # live row reflected too

    # An OLDER op must be ignored - our copy is newer.
    with _s() as s:
        devicesync.apply_states(s, [{"email": email, "mid": mid, "done": False, "snooze": None,
                                     "presence": False, "pinned": False, "ts": datetime(2025, 6, 1).isoformat()}])
        s.commit()
    with _s() as s:
        assert s.exec(select(MessageState).where(MessageState.message_id == mid)).first().is_done is True


def test_apply_states_skips_unknown_account(client):
    # An op for an email we don't have must be a no-op, not an error.
    n_before = 0
    with _s() as s:
        n_before = len(s.exec(select(MessageState)).all())
        devicesync.apply_states(s, [{"email": "nobody@nowhere.tld", "mid": "<x@y>", "done": True,
                                     "snooze": None, "presence": False, "pinned": False,
                                     "ts": datetime(2026, 6, 1).isoformat()}])
        s.commit()
    with _s() as s:
        assert len(s.exec(select(MessageState)).all()) == n_before


def test_apply_states_handles_aware_local_timestamp(client):
    # A MessageState freshly created in-session is tz-AWARE in memory (utcnow()),
    # only naive after a DB reload. Applying a naive incoming ts must not raise a
    # naive-vs-aware TypeError.
    from datetime import timezone
    email, mid = "aware@example.com", "<aware-1@example.com>"
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        s.add(MessageState(account_id=acct.id, message_id=mid, is_done=False,
                           updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        s.flush()   # in identity map, still aware (not reloaded)
        devicesync.apply_states(s, [{"email": email, "mid": mid, "done": True, "snooze": None,
                                     "presence": False, "pinned": False, "ts": datetime(2026, 6, 1).isoformat()}])
        s.commit()
    with _s() as s:
        assert s.exec(select(MessageState).where(MessageState.message_id == mid)).first().is_done is True


def test_full_roundtrip_serialize_encrypt_apply(client):
    email, mid = "rt@example.com", "<rt-1@example.com>"
    with _s() as s:
        acct = Account(email=email); s.add(acct); s.commit(); s.refresh(acct)
        s.add(MessageState(account_id=acct.id, message_id=mid, is_done=True,
                           updated_at=datetime(2026, 5, 5)))
        s.commit()

    passphrase = "the shared sync secret"
    # Device A builds + encrypts + wraps (automatic channel = state only).
    with _s() as s:
        payload = devicesync._build_state_payload(s, "devA", since=None, full=True)
    assert payload["kind"] == "state" and "config" not in payload
    assert any(x["mid"] == mid and x["done"] for x in payload["states"])
    token = devicesync.derive_fernet(passphrase).encrypt(
        json.dumps(payload, default=str).encode("utf-8")).decode("ascii")
    raw = devicesync._wrap_message(token, email, "devA")

    # Simulate device B: local copy is stale (not done).
    with _s() as s:
        st = s.exec(select(MessageState).where(MessageState.message_id == mid)).first()
        st.is_done = False; st.updated_at = datetime(2020, 1, 1); s.add(st); s.commit()

    # Device B extracts, decrypts, applies → A's "done" propagates.
    tok = devicesync._extract_token(raw)
    payload2 = json.loads(devicesync.derive_fernet(passphrase).decrypt(tok.encode("ascii")).decode("utf-8"))
    with _s() as s:
        devicesync.apply_states(s, payload2["states"]); s.commit()
    with _s() as s:
        assert s.exec(select(MessageState).where(MessageState.message_id == mid)).first().is_done is True


def test_apply_config_bundle_preserves_local_sync_keys(client):
    # An explicit pull applies a peer's config but must never change THIS device's
    # own sync-control keys (carrier account / device id / cursors).
    from app.api.settings import _get_blob, _set_blob
    with _s() as s:
        before = _get_blob(s)
    try:
        with _s() as s:
            _set_blob(s, {"syncEnabled": True, "syncAccountId": 7, "syncDeviceId": "local-dev", "theme": "nord"})
        cfg = {"settings": {"syncEnabled": False, "syncAccountId": 99, "theme": "dracula"}}
        with _s() as s:
            devicesync._apply_config_bundle(s, cfg)
            s.commit()
        with _s() as s:
            blob = _get_blob(s)
        assert blob["syncEnabled"] is True and blob["syncAccountId"] == 7   # local sync control preserved
        assert blob["syncDeviceId"] == "local-dev"
        assert blob["theme"] == "dracula"                                    # peer's real setting applied
    finally:
        with _s() as s:
            _set_blob(s, before)   # restore so the shared test DB stays clean


def test_device_label_set_clear_and_fallback(client):
    # The friendly name is trimmed + capped, survives a config save that omits it
    # (None = leave unchanged), and clearing it falls back to the hostname/id.
    from app.api.settings import _get_blob, _set_blob
    with _s() as s:
        before = _get_blob(s)
    try:
        with _s() as s:
            devicesync.set_config(s, enabled=False, account_id=None, passphrase=None,
                                  device_label="  Main  ")
        with _s() as s:
            assert devicesync.status(s)["device_label"] == "Main"
        with _s() as s:   # a save without the field must not touch the name
            devicesync.set_config(s, enabled=False, account_id=None, passphrase=None)
        with _s() as s:
            assert devicesync.status(s)["device_label"] == "Main"
        with _s() as s:   # explicit empty clears it → hostname/short-id fallback
            devicesync.set_config(s, enabled=False, account_id=None, passphrase=None,
                                  device_label="")
        with _s() as s:
            lbl = devicesync.status(s)["device_label"]
            assert lbl and lbl != "Main"
        with _s() as s:   # overly long names are capped at 40 chars
            devicesync.set_config(s, enabled=False, account_id=None, passphrase=None,
                                  device_label="x" * 100)
        with _s() as s:
            assert devicesync.status(s)["device_label"] == "x" * 40
    finally:
        with _s() as s:
            _set_blob(s, before)


def test_build_config_payload_shape(client):
    # The explicit config snapshot carries a version + real change-time + bundle,
    # and strips sync-control keys from the settings it publishes.
    from app.api.settings import _get_blob, _set_blob
    with _s() as s:
        before = _get_blob(s)
    try:
        with _s() as s:
            _set_blob(s, {"syncEnabled": True, "syncAccountId": 3, "theme": "nord", "smartInbox": True})
        with _s() as s:
            payload = devicesync._build_config_payload(s, "devA", "Main-PC", 5)
        assert payload["kind"] == "config" and payload["config_version"] == 5
        assert payload["device_label"] == "Main-PC"
        assert payload["config_changed_at"]
        settings = payload["config"]["settings"]
        assert settings.get("theme") == "nord" and settings.get("smartInbox") is True
        assert "syncEnabled" not in settings and "syncAccountId" not in settings  # sync keys stripped
    finally:
        with _s() as s:
            _set_blob(s, before)
