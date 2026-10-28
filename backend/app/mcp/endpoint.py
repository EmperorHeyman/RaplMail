"""Where an AI app's relay finds the running RaplMail.

The backend listens on a random port with a per-launch token, so the relay
can't be configured with an address. Instead the running backend writes
``mcp-endpoint.json`` into the data dir (URL + a fresh per-launch key), and the
relay reads it on every message - so it follows RaplMail across restarts. The
key only opens /mcp; what the AI may do there is up to the settings.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

FILE_NAME = "mcp-endpoint.json"
_key = secrets.token_urlsafe(32)


def key() -> str:
    return _key


def data_dir() -> Path:
    """Same rule as app.core.config (RAPLMAIL_DATA_DIR, else %APPDATA%/RaplMail),
    without importing the app (the relay stays light)."""
    explicit = os.environ.get("RAPLMAIL_DATA_DIR")
    if explicit:
        return Path(explicit)
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "RaplMail"


def publish(port: int) -> None:
    """Write the endpoint file (atomically). Called at backend startup."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    info = {"url": f"http://127.0.0.1:{port}/mcp", "key": _key, "pid": os.getpid(),
            "version": os.environ.get("RAPLMAIL_VERSION") or ""}
    tmp = d / (FILE_NAME + ".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, d / FILE_NAME)


def unpublish() -> None:
    """Remove the endpoint file if it's ours (a newer instance may own it)."""
    p = data_dir() / FILE_NAME
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        if info.get("pid") == os.getpid():
            p.unlink()
    except Exception:
        pass


def read() -> dict | None:
    try:
        info = json.loads((data_dir() / FILE_NAME).read_text(encoding="utf-8"))
        return info if info.get("url") and info.get("key") else None
    except Exception:
        return None
