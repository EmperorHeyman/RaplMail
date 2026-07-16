"""Encrypted credential sync (opt-in). The crown-jewels path, so it gets the
most adversarial tests: the inner AEAD must round-trip, reject a wrong secret,
reject any tampering, and the full push->list->preview->apply flow over an
in-memory carrier folder must need BOTH the sync passphrase (outer) and the
credential secret (inner). A device holding only the sync passphrase learns the
account COUNT but never an email or a password.
"""
import base64
import json

import pytest
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account
from app.sync import devicesync as ds


def _s():
    return Session(get_engine())


def _unlock():
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.exists:
        store.initialize("test-master")
    elif not store.is_unlocked:
        store.unlock("test-master")
    return store


# --- in-memory carrier provider -------------------------------------------

class FakeProvider:
    def __init__(self):
        self.folders = {}
        self._uid = 0

    def ensure_folder(self, folder):
        self.folders.setdefault(folder, {})

    def append_to_folder(self, folder, raw, seen=True):
        self._uid += 1
        self.folders.setdefault(folder, {})[self._uid] = raw
        return self._uid

    def list_uids(self, folder):
        return list(self.folders.get(folder, {}).keys())

    def fetch_raw(self, folder, uid):
        return self.folders.get(folder, {}).get(uid)

    def delete(self, folder, uid):
        self.folders.get(folder, {}).pop(uid, None)

    def close(self):
        pass


# --- pure crypto (no vault, no provider) -----------------------------------

_ACCOUNTS = [{"email": "me@example.com", "provider": "imap", "secret_key": "acct:1",
              "secret": "hunter2-imap-pw"}]


def test_aead_roundtrip():
    env = ds._encrypt_credentials(_ACCOUNTS, "devA", "a strong shared secret")
    assert env["kind"] == "credentials" and env["count"] == 1
    # Ciphertext carries no plaintext email/password.
    assert "me@example.com" not in env["ct"] and "hunter2" not in env["ct"]
    out = ds._decrypt_credentials(env, "a strong shared secret")
    assert out[0]["email"] == "me@example.com" and out[0]["secret"] == "hunter2-imap-pw"


def test_aead_wrong_secret_fails_cleanly():
    env = ds._encrypt_credentials(_ACCOUNTS, "devA", "the right secret 123")
    with pytest.raises(RuntimeError, match="Incorrect credential passphrase"):
        ds._decrypt_credentials(env, "the WRONG secret 123")


def test_aead_tamper_is_detected():
    env = ds._encrypt_credentials(_ACCOUNTS, "devA", "the right secret 123")
    ct = bytearray(base64.b64decode(env["ct"]))
    ct[0] ^= 0x01                                  # flip one bit of the ciphertext
    env["ct"] = base64.b64encode(bytes(ct)).decode()
    with pytest.raises(RuntimeError):
        ds._decrypt_credentials(env, "the right secret 123")


def test_aead_device_binding_in_aad():
    # The origin device id is authenticated (AAD); spoofing it fails the tag.
    env = ds._encrypt_credentials(_ACCOUNTS, "devA", "the right secret 123")
    env["device"] = "devB"
    with pytest.raises(RuntimeError):
        ds._decrypt_credentials(env, "the right secret 123")


# --- full flow over the fake carrier ---------------------------------------

def _setup_sync(session, provider_email="carrier@example.com"):
    """An unlocked vault + a configured sync passphrase + a carrier account."""
    _unlock()
    acct = session.exec(select(Account).where(Account.email == provider_email)).first()
    if acct is None:
        acct = Account(email=provider_email, secret_key="acct:carrier")
        session.add(acct); session.commit(); session.refresh(acct)
    ds.set_config(session, enabled=True, account_id=acct.id, passphrase="sync-pass-1234")
    session.commit()
    return acct


def test_push_then_list_preview_apply(client):
    prov = FakeProvider()
    with _s() as s:
        carrier = _setup_sync(s)
        # A second account whose credential we will sync.
        if s.exec(select(Account).where(Account.email == "synced@example.com")).first() is None:
            a = Account(email="synced@example.com", secret_key="cred:synced")
            s.add(a); s.commit()
        from app.core.security import get_secret_store
        get_secret_store().set("cred:synced", "the-synced-password")
        ds.push_credentials(s, carrier, prov, "cred-secret-abcdef")

    # Metadata listing needs only the sync passphrase; it exposes count, never emails.
    with _s() as s:
        snaps = ds.list_credential_snapshots(s, prov)
    assert len(snaps) == 1 and snaps[0]["count"] >= 2
    blob_text = json.dumps(list(prov.folders.values())[0], default=str)
    assert "synced@example.com" not in blob_text        # sealed inside the AEAD
    assert "the-synced-password" not in blob_text

    uid = snaps[0]["uid"]
    # Wrong credential secret is rejected even with the right sync passphrase.
    with _s() as s, pytest.raises(Exception):
        ds.preview_credentials(s, prov, uid, "wrong-secret-xxxxx")

    # Correct secret -> the account list appears for confirmation.
    with _s() as s:
        preview = ds.preview_credentials(s, prov, uid, "cred-secret-abcdef")
    emails = {p["email"] for p in preview}
    assert "synced@example.com" in emails

    # Simulate device B: drop the synced account, then import just that one.
    with _s() as s:
        gone = s.exec(select(Account).where(Account.email == "synced@example.com")).first()
        if gone:
            s.delete(gone); s.commit()
    with _s() as s:
        res = ds.apply_credentials(s, prov, uid, "cred-secret-abcdef", ["synced@example.com"])
    assert res["imported"] == 1
    with _s() as s:
        acct = s.exec(select(Account).where(Account.email == "synced@example.com")).first()
        assert acct is not None
        from app.core.security import get_secret_store
        assert get_secret_store().get(acct.secret_key) == "the-synced-password"
