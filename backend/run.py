"""Frozen-friendly entrypoint for the bundled backend (PyInstaller sidecar).

Tauri injects RAPLMAIL_PORT and RAPLMAIL_TOKEN; we bind localhost only.
"""

import os

import uvicorn

from app.main import app


def main() -> None:
    port = int(os.environ.get("RAPLMAIL_PORT", "8765"))
    # Bind localhost by default; RAPLMAIL_HOST=0.0.0.0 exposes the read-only
    # /metrics endpoint to LAN devices (Home Assistant, ESP32).
    host = os.environ.get("RAPLMAIL_HOST", "127.0.0.1")
    # Use the plain asyncio loop / h11 + websockets implementation so we don't
    # depend on uvloop/httptools (not needed on Windows and simpler to freeze).
    uvicorn.run(app, host=host, port=port, loop="asyncio",
                http="h11", ws="websockets", log_level="info")


if __name__ == "__main__":
    main()
