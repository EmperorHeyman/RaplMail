"""D1: OS-credential-store (keyring) backing for auto-unlock. With a usable
keyring the secret lands in the OS store and the file holds only a marker;
disabling clears the store; unlock reads it back; and a keyring that raises
falls back to the legacy base64 file without error.
"""
import base64

import pytest

from app.core import security as sec
from app.core.security import SecretStore


@pytest.fixture
def store(tmp_path):
    s = SecretStore(tmp_path / "vault.bin", autounlock_path=tmp_path / "autounlock")
    s.initialize("master-pw-123")
    return s


class _FakeKeyring:
    """In-memory stand-in for the keyring module."""
    def __init__(self):
        self.data = {}
        self.raise_on = set()

    def set_password(self, service, user, secret):
        if "set" in self.raise_on:
            raise RuntimeError("backend locked")
        self.data[(service, user)] = secret

    def get_password(self, service, user):
        if "get" in self.raise_on:
            raise RuntimeError("backend locked")
        return self.data.get((service, user))

    def delete_password(self, service, user):
        self.data.pop((service, user), None)


def _use_keyring(monkeypatch, fake):
    # Mirror the real helpers, including their swallow-and-return-False on error.
    def _set(s):
        try:
            fake.set_password(sec._KEYRING_SERVICE, sec._KEYRING_USERNAME, s)
            return fake.get_password(sec._KEYRING_SERVICE, sec._KEYRING_USERNAME) == s
        except Exception:
            return False

    def _get():
        try:
            return fake.get_password(sec._KEYRING_SERVICE, sec._KEYRING_USERNAME)
        except Exception:
            return None

    monkeypatch.setattr(sec, "_keyring_set", _set)
    monkeypatch.setattr(sec, "_keyring_get", _get)
    monkeypatch.setattr(sec, "_keyring_delete",
                        lambda: fake.delete_password(sec._KEYRING_SERVICE, sec._KEYRING_USERNAME))


def test_enable_stores_in_keyring_not_file(store, monkeypatch):
    fake = _FakeKeyring()
    _use_keyring(monkeypatch, fake)
    store.enable_auto_unlock("master-pw-123")
    # Secret is in the OS store; the file holds only the marker (no password).
    assert fake.data[(sec._KEYRING_SERVICE, sec._KEYRING_USERNAME)] == "master-pw-123"
    assert store._autounlock_path.read_text("utf-8") == sec._KEYRING_MARKER


def test_disable_clears_keyring_and_file(store, monkeypatch):
    fake = _FakeKeyring()
    _use_keyring(monkeypatch, fake)
    store.enable_auto_unlock("master-pw-123")
    store.disable_auto_unlock()
    assert (sec._KEYRING_SERVICE, sec._KEYRING_USERNAME) not in fake.data
    assert not store._autounlock_path.exists()


def test_try_auto_unlock_reads_keyring(store, monkeypatch, tmp_path):
    fake = _FakeKeyring()
    _use_keyring(monkeypatch, fake)
    store.enable_auto_unlock("master-pw-123")
    # Fresh, locked store over the same files - unlock must come from keyring.
    fresh = SecretStore(store._path, autounlock_path=store._autounlock_path)
    assert fresh.is_unlocked is False
    assert fresh.try_auto_unlock() is True
    assert fresh.is_unlocked is True


def test_keyring_failure_falls_back_to_file(store, monkeypatch):
    fake = _FakeKeyring()
    fake.raise_on.add("set")   # keyring write fails -> legacy base64 file path
    _use_keyring(monkeypatch, fake)
    store.enable_auto_unlock("master-pw-123")
    # Nothing in the store; the file holds the (reversible) legacy secret.
    assert (sec._KEYRING_SERVICE, sec._KEYRING_USERNAME) not in fake.data
    raw = store._autounlock_path.read_text("utf-8")
    assert raw != sec._KEYRING_MARKER
    assert base64.b64decode(raw).decode("utf-8") == "master-pw-123"
    # And a fresh store still auto-unlocks from that file.
    fresh = SecretStore(store._path, autounlock_path=store._autounlock_path)
    assert fresh.try_auto_unlock() is True
