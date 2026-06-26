"""Encrypted secret store.

Credentials (OAuth refresh tokens, IMAP/SMTP passwords) are kept in a single
file encrypted with a key derived from a master password via Argon2id, then
sealed with Fernet (AES-128-CBC + HMAC). The decrypted secrets live only in
memory once the store is unlocked for the session.

File layout (JSON):
    {"version": 1, "salt": "<b64>", "data": "<fernet-token>"}
The decrypted payload is a JSON object: {"<key>": "<secret>", ...}
"""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken

# Argon2id parameters (interactive-grade; tune up for slower/stronger).
_TIME_COST = 3
_MEMORY_COST = 64 * 1024  # KiB
_PARALLELISM = 4
_KEY_LEN = 32
_SALT_LEN = 16


class SecretStoreError(Exception):
    pass


class LockedError(SecretStoreError):
    """Raised when an operation needs an unlocked store but none is available."""


class BadPasswordError(SecretStoreError):
    """Raised when the master password fails to decrypt the store."""


def _derive_key(password: str, salt: bytes) -> bytes:
    raw = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST,
        parallelism=_PARALLELISM,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )
    return base64.urlsafe_b64encode(raw)


class SecretStore:
    """Thread-safe, lazily-unlocked encrypted key/value store."""

    def __init__(self, path: Path, autounlock_path: Path | None = None):
        self._path = path
        self._autounlock_path = autounlock_path
        self._lock = threading.RLock()
        self._fernet: Fernet | None = None
        self._salt: bytes | None = None
        self._cache: dict[str, str] = {}

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def is_unlocked(self) -> bool:
        return self._fernet is not None

    def initialize(self, master_password: str) -> None:
        """Create a brand-new empty store. Fails if one already exists."""
        with self._lock:
            if self.exists:
                raise SecretStoreError("secret store already exists")
            import os

            self._salt = os.urandom(_SALT_LEN)
            self._fernet = Fernet(_derive_key(master_password, self._salt))
            self._cache = {}
            self._flush()

    def unlock(self, master_password: str) -> None:
        """Unlock an existing store with the master password."""
        with self._lock:
            if not self.exists:
                raise SecretStoreError("secret store does not exist; initialize first")
            blob = json.loads(self._path.read_text("utf-8"))
            self._salt = base64.b64decode(blob["salt"])
            fernet = Fernet(_derive_key(master_password, self._salt))
            try:
                payload = fernet.decrypt(blob["data"].encode("ascii"))
            except InvalidToken as exc:
                raise BadPasswordError("invalid master password") from exc
            self._cache = json.loads(payload.decode("utf-8"))
            self._fernet = fernet

    def change_password(self, new_password: str) -> None:
        with self._lock:
            self._require_unlocked()
            import os

            self._salt = os.urandom(_SALT_LEN)
            self._fernet = Fernet(_derive_key(new_password, self._salt))
            self._flush()

    def lock(self) -> None:
        with self._lock:
            self._fernet = None
            self._cache = {}

    # --- auto-unlock (convenience; trades encryption-at-rest for not retyping) --
    @property
    def auto_unlock_enabled(self) -> bool:
        return bool(self._autounlock_path and self._autounlock_path.exists())

    def verify_password(self, password: str) -> bool:
        if not self.exists:
            return False
        blob = json.loads(self._path.read_text("utf-8"))
        salt = base64.b64decode(blob["salt"])
        try:
            Fernet(_derive_key(password, salt)).decrypt(blob["data"].encode("ascii"))
            return True
        except InvalidToken:
            return False

    def enable_auto_unlock(self, password: str) -> None:
        """Persist the master password locally so the vault unlocks on startup.

        SECURITY: this stores the password reversibly on disk; anyone with file
        access can then decrypt the vault. Convenience-vs-security tradeoff.
        """
        if not self.verify_password(password):
            raise BadPasswordError("invalid master password")
        if self._autounlock_path is None:
            raise SecretStoreError("auto-unlock path not configured")
        self._autounlock_path.parent.mkdir(parents=True, exist_ok=True)
        self._autounlock_path.write_text(
            base64.b64encode(password.encode("utf-8")).decode("ascii"), "utf-8"
        )

    def disable_auto_unlock(self) -> None:
        if self._autounlock_path and self._autounlock_path.exists():
            self._autounlock_path.unlink()

    def try_auto_unlock(self) -> bool:
        if not self.auto_unlock_enabled or self.is_unlocked or not self.exists:
            return False
        try:
            password = base64.b64decode(self._autounlock_path.read_text("utf-8")).decode("utf-8")
            self.unlock(password)
            return True
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        with self._lock:
            self._require_unlocked()
            return self._cache.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._require_unlocked()
            self._cache[key] = value
            self._flush()

    def delete(self, key: str) -> None:
        with self._lock:
            self._require_unlocked()
            self._cache.pop(key, None)
            self._flush()

    def cache_fernet(self) -> Fernet | None:
        """A Fernet for encrypting the local message cache at rest. Uses a random
        data-encryption key kept *inside* the vault (created on first use), so the
        cache is sealed by the same master password. Returns None if locked."""
        with self._lock:
            if self._fernet is None:
                return None
            dek = self._cache.get("__cache_dek__")
            if not dek:
                dek = Fernet.generate_key().decode("ascii")
                self._cache["__cache_dek__"] = dek
                self._flush()
            return Fernet(dek.encode("ascii"))

    def _require_unlocked(self) -> None:
        if self._fernet is None:
            raise LockedError("secret store is locked")

    def _flush(self) -> None:
        assert self._fernet is not None and self._salt is not None
        token = self._fernet.encrypt(json.dumps(self._cache).encode("utf-8"))
        blob = {
            "version": 1,
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "data": token.decode("ascii"),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(blob), "utf-8")
        tmp.replace(self._path)


_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        from app.core.config import get_settings

        s = get_settings()
        _store = SecretStore(s.secret_store_path, s.autounlock_path)
    return _store
