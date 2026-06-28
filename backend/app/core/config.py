"""Runtime configuration for the RaplMail backend.

The backend is designed to run as a localhost-only sidecar started by the Tauri
shell. Tauri picks a free port and a per-launch shared-secret token and passes
them in via environment variables. When run standalone for development, sensible
defaults are used and the auth token can be disabled.
"""

from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Per-user data directory for the SQLite DB and the encrypted secret store."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "RaplMail"


def _env_files() -> tuple[str, ...]:
    """Where to look for .env, lowest -> highest priority (later wins).

    Works both in dev (./.env) and in the packaged app, where the exe has no
    working-dir .env: we read the copy baked into the bundle, and let the user
    override it with a .env next to the exe or in the data dir without rebuilding.
    """
    files: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            files.append(os.path.join(meipass, ".env"))          # baked into the bundle
        files.append(os.path.join(os.path.dirname(sys.executable), ".env"))  # next to the exe
    files.append(str(_default_data_dir() / ".env"))              # user-editable, post-install
    files.append(".env")                                         # dev / current dir (wins)
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAPLMAIL_", env_file=_env_files(), env_file_encoding="utf-8", extra="ignore"
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
