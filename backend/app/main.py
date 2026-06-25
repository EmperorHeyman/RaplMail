"""RaplMail backend entrypoint.

Run standalone for development:
    RAPLMAIL_DEV=1 python -m uvicorn app.main:app --reload --port 8765

When launched by the Tauri shell, RAPLMAIL_PORT / RAPLMAIL_TOKEN are injected.
"""

from __future__ import annotations

import contextlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, avatars, calendar, compose, contacts, folders, messages, rules, settings as settings_api, signatures, vault
from app.core.config import get_settings
from app.core.db import init_db
from app.core.ws import hub
from app.sync.engine import SyncManager


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # If the user enabled "don't require password", unlock the vault now.
    from app.core.security import get_secret_store
    get_secret_store().try_auto_unlock()
    manager = SyncManager(hub)
    app.state.sync = manager
    await manager.start()
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(title="RaplMail", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    # The backend is localhost-only and authenticated by the X-RaplMail-Token
    # header (no cookies), so any origin is safe to allow. This is required
    # because the packaged Tauri webview's origin varies by platform
    # (http://tauri.localhost on Windows, tauri://localhost elsewhere).
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vault.router)
app.include_router(accounts.router)
app.include_router(folders.router)
app.include_router(messages.router)
app.include_router(rules.router)
app.include_router(signatures.router)
app.include_router(compose.router)
app.include_router(contacts.router)
app.include_router(avatars.router)
app.include_router(calendar.router)
app.include_router(settings_api.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # Token passed as a query param since browsers can't set WS headers easily.
    token = ws.query_params.get("token", "")
    if _settings.token and token != _settings.token:
        await ws.close(code=1008)
        return
    await hub.connect(ws)
    try:
        while True:
            # We don't expect client->server messages yet; keep the socket open.
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)
