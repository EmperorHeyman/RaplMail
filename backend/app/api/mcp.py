"""MCP over HTTP for the stdio relay (app.mcp.relay), and its settings info.

POST /mcp is authenticated with the per-launch key from the endpoint file, not
the app token: the relay is launched by another app (Claude Desktop, ...) and
never sees the app token. What a call may do is decided per request from the
settings (mcpEnabled, mcpAccess).
"""

from __future__ import annotations

import hmac
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import verify_token
from app.mcp import endpoint, protocol
from app.mcp.tools import LEVELS

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _mcp_settings() -> tuple[bool, str]:
    from sqlmodel import Session

    from app.core.db import get_engine
    from app.models import Setting
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        data = dict(row.data) if row and row.data else {}
    access = str(data.get("mcpAccess") or "read")
    return data.get("mcpEnabled") is True, access if access in LEVELS else "read"


@router.post("")
async def mcp_rpc(request: Request):
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {endpoint.key()}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad or missing MCP key")
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                            status_code=400)
    enabled, access = _mcp_settings()
    reply = await protocol.handle(payload, {"enabled": enabled, "access": access, "request": request})
    if reply is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(reply)


@router.get("/info", dependencies=[Depends(verify_token)])
def mcp_info() -> dict:
    """For Settings: the command an AI app should launch, and what AI apps did."""
    if getattr(sys, "frozen", False):
        command, args = sys.executable, ["--mcp"]          # the installed raplmail-backend.exe
    else:
        command, args = sys.executable, [str(Path(__file__).resolve().parents[2] / "mcp_relay.py")]
    return {"command": command, "args": args, "activity": protocol.recent_activity(),
            "reachable": endpoint.read() is not None}
