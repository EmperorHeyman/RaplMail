"""Encryption-at-rest field helper: round-trip, prefix, and graceful passthrough."""

from cryptography.fernet import Fernet

from app.core import atrest


def test_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr(atrest, "_enabled", lambda: False)
    assert atrest.encrypt_field("hello") == "hello"
    assert atrest.decrypt_field("hello") == "hello"


def test_roundtrip_when_enabled(monkeypatch):
    cipher = Fernet(Fernet.generate_key())
    monkeypatch.setattr(atrest, "_enabled", lambda: True)
    monkeypatch.setattr(atrest, "_cipher", lambda: cipher)

    sealed = atrest.encrypt_field("the body of a private message")
    assert atrest.is_encrypted(sealed)
    assert sealed.startswith("enc:v1:")
    assert "private message" not in sealed  # ciphertext, not plaintext
    assert atrest.decrypt_field(sealed) == "the body of a private message"


def test_encrypt_noop_when_locked(monkeypatch):
    monkeypatch.setattr(atrest, "_enabled", lambda: True)
    monkeypatch.setattr(atrest, "_cipher", lambda: None)  # vault locked
    assert atrest.encrypt_field("x") == "x"  # left plaintext rather than lost


def test_decrypt_empty_for_blank():
    assert atrest.decrypt_field("") == ""
    assert atrest.decrypt_field(None) == ""
