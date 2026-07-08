"""RaplMail backend entrypoint.

Run standalone for development:
    RAPLMAIL_DEV=1 python -m uvicorn app.main:app --reload --port 8765

When launched by the Tauri shell, RAPLMAIL_PORT / RAPLMAIL_TOKEN are injected.
"""

from __future__ import annotations

import contextlib
import gc
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api import accounts, ai, avatars, calendar, compose, contacts, debug, devicesync, folders, messages, metrics, rapldesk, rules, sandbox, security, settings as settings_api, signatures, smime, subscriptions, track, unfurl, vault
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logbuffer import install as install_log_buffer
from app.core.ws import hub
from app.sync.engine import SyncManager


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_buffer()   # capture backend logs for the in-app Debug window
    init_db()
    # If the user enabled "don't require password", unlock the vault now.
    from app.core.security import get_secret_store
    get_secret_store().try_auto_unlock()
    manager = SyncManager(hub)
    app.state.sync = manager
    await manager.start()
    # Bring up the local Ollama server on launch if the user opted in (and it
    # isn't already running). Background thread so it never delays startup.
    import threading as _threading

    from app.api.ai import autostart_ollama_if_configured
    _threading.Thread(target=autostart_ollama_if_configured, daemon=True,
                      name="ollama-autostart").start()
    # Everything created during startup (modules, routes, engine) lives for the
    # whole process - freeze it out of the cyclic GC so collections only scan
    # request-lifetime objects (fewer + faster GC pauses).
    gc.collect()
    gc.freeze()
    try:
        yield
    finally:
        await manager.stop()
        # Stop the hidden Ollama serve we started (and its runner child) so it
        # doesn't outlive the app. Best-effort; a hard kill by the shell may skip
        # this, in which case the next launch reuses/cleans it up.
        try:
            from app.api.ai import shutdown_managed_ollama
            shutdown_managed_ollama()
        except Exception:  # noqa: BLE001
            pass


# Version is injected by the Tauri shell (RAPLMAIL_VERSION) so /health and the
# Debug window report the real installed version, not a hardcoded stub.
# orjson serializes the big list/thread payloads several times faster than the
# stdlib encoder (and without building an intermediate string).
app = FastAPI(title="RaplMail", version=os.environ.get("RAPLMAIL_VERSION", "0.0.0-dev"),
              lifespan=lifespan, default_response_class=ORJSONResponse)

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
app.include_router(security.router)
app.include_router(signatures.router)
app.include_router(compose.router)
app.include_router(contacts.router)
app.include_router(avatars.router)
app.include_router(calendar.router)
app.include_router(settings_api.router)
app.include_router(devicesync.router)
app.include_router(unfurl.router)
app.include_router(metrics.router)
app.include_router(ai.router)
app.include_router(smime.router)
app.include_router(subscriptions.router)
app.include_router(rapldesk.router)
app.include_router(sandbox.router)
app.include_router(debug.router)
app.include_router(track.router)
app.include_router(track.pixel_router)


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
