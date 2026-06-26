"""Optional encryption-at-rest for the local message-body cache.

When the user enables it (setting `encryptCache`), cached `body_html` / `body_text`
are sealed with a vault-held data-encryption key before being written to SQLite,
and transparently decrypted on read. Field-level (not whole-DB) so it can never
corrupt the database structure, and it degrades gracefully: if the vault is
locked or the feature is off, values pass through unchanged.
"""

from __future__ import annotations

_PREFIX = "enc:v1:"


def _enabled() -> bool:
    try:
        from app.core.db import get_engine
        from app.models import Setting
        from sqlmodel import Session
        with Session(get_engine()) as session:
            row = session.get(Setting, 1)
            data = dict(row.data) if row and row.data else {}
        return bool(data.get("encryptCache"))
    except Exception:
        return False


def _cipher():
    try:
        from app.core.security import get_secret_store
        return get_secret_store().cache_fernet()
    except Exception:
        return None


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_field(value: str | None) -> str:
    """Encrypt a cache field if the feature is on and the vault is unlocked."""
    if not value or is_encrypted(value) or not _enabled():
        return value or ""
    cipher = _cipher()
    if cipher is None:
        return value
    try:
        token = cipher.encrypt(value.encode("utf-8")).decode("ascii")
        return _PREFIX + token
    except Exception:
        return value


def decrypt_field(value: str | None) -> str:
    """Decrypt a previously-encrypted cache field; pass through plaintext."""
    if not is_encrypted(value):
        return value or ""
    cipher = _cipher()
    if cipher is None:
        return ""  # locked — can't read the encrypted body right now
    try:
        return cipher.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return ""
