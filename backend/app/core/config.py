"""Runtime configuration for the RaplMail backend.

The backend is designed to run as a localhost-only sidecar started by the Tauri
shell. Tauri picks a free port and a per-launch shared-secret token and passes
them in via environment variables. When run standalone for development, sensible
defaults are used and the auth token can be disabled.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Per-user data directory for the SQLite DB and the encrypted secret store."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "RaplMail"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAPLMAIL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8765

    # Shared secret required on every request (header X-RaplMail-Token).
    # Empty string disables the check (development only).
    token: str = ""

    # Where the SQLite DB and encrypted secret store live.
    data_dir: Path = Field(default_factory=_default_data_dir)

    # OAuth client IDs (no secrets stored on-device for device-code/PKCE flows).
    ms_client_id: str = ""
    ms_authority: str = "https://login.microsoftonline.com/common"
    google_client_id: str = ""
    google_client_secret: str = ""  # Google "desktop app" clients ship a non-secret secret.

    # Allow the bundled webview / vite dev server origins.
    cors_origins: list[str] = ["http://localhost:1420", "http://localhost:5173", "tauri://localhost"]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "raplmail.db"

    @property
    def secret_store_path(self) -> Path:
        return self.data_dir / "secrets.enc"

    @property
    def autounlock_path(self) -> Path:
        return self.data_dir / "autounlock.bin"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    # If no token was supplied and we're not explicitly in dev mode, mint one so
    # logs can surface it for the launching process.
    if not s.token and os.environ.get("RAPLMAIL_DEV") != "1":
        s.token = secrets.token_urlsafe(32)
    return s
