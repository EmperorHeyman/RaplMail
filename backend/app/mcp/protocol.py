"""The JSON-RPC side of MCP: initialize, ping, tools/list, tools/call.

``handle`` runs inside the backend (POST /mcp). ``offline`` answers in the relay
when RaplMail isn't running, so an AI app still connects and can tell the user
to start it instead of just failing.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone

from app.mcp.tools import LEVELS, TOOLS_BY_NAME, ToolError, describe_args, tools_for

SERVER_NAME = "raplmail"
# Newest first; we answer with the client's version when we speak it.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LEVEL_LABELS = {"read": "Read only", "act": "Read & organize", "send": "Full (can send)"}

INSTRUCTIONS = (
    "RaplMail is the user's desktop mail client; these tools work on their real mailbox. "
    "Find mail with search_messages (operators like from:, subject:, is:unread), then read it "
    "with get_message. Reading never marks mail as read. Prefer create_draft over send_email "
    "unless the user clearly asked you to send, and confirm recipients before sending."
)

# What AI apps did recently (shown in Settings): no bodies, just tool + target.
_activity: deque = deque(maxlen=60)
_activity_lock = threading.Lock()


def recent_activity() -> list[dict]:
    with _activity_lock:
        return list(_activity)


def _record(tool: str, args: dict, ok: bool, ms: int, error: str = "", refused: bool = False) -> None:
    with _activity_lock:
        _activity.appendleft({"at": datetime.now(timezone.utc).isoformat(), "tool": tool,
                              "detail": describe_args(tool, args), "ok": ok, "refused": refused,
                              "ms": ms, "error": error[:200]})


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _version(params: dict) -> str:
    asked = str((params or {}).get("protocolVersion") or "")
    return asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]


def _initialize(params: dict, note: str = "") -> dict:
    import os

    # The desktop shell passes the real version in (as for /health).
    version = os.environ.get("RAPLMAIL_VERSION") or "0.0.0-dev"
    return {"protocolVersion": _version(params),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "RaplMail", "version": version},
            "instructions": (note + " " + INSTRUCTIONS).strip()}


def _text_result(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}


async def _call(params: dict, ctx: dict) -> dict:
    name = str(params.get("name") or "")
    args = params.get("arguments") or {}
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        raise RpcError(-32602, f"Unknown tool: {name}")
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    if not ctx.get("enabled"):
        return _text_result("Access from AI apps is turned off in RaplMail (Settings -> AI assistant -> "
                            "Connect AI apps). Ask the user to turn it on.", error=True)
    access = ctx.get("access") or "read"
    if LEVELS[spec["level"]] > LEVELS.get(access, 0):
        need = LEVEL_LABELS["send" if spec["level"] == "send" else "act"]
        _record(name, args, False, 0, f"Refused: needs \"{need}\"", refused=True)
        return _text_result(f"{name} needs the \"{need}\" access level; RaplMail is set to "
                            f"\"{LEVEL_LABELS.get(access, access)}\" (Settings -> AI assistant -> Connect AI apps).",
                            error=True)
    from app.mcp.tools import run
    t0 = time.monotonic()
    try:
        text = await run(name, args, ctx.get("request"))
    except ToolError as exc:
        _record(name, args, False, round((time.monotonic() - t0) * 1000), str(exc))
        return _text_result(str(exc), error=True)
    except Exception as exc:  # noqa: BLE001 - the AI gets the reason, the app keeps running
        detail = getattr(exc, "detail", None) or str(exc) or type(exc).__name__
        _record(name, args, False, round((time.monotonic() - t0) * 1000), str(detail))
        return _text_result(f"{name} failed: {detail}", error=True)
    _record(name, args, True, round((time.monotonic() - t0) * 1000))
    return _text_result(text)


async def _one(msg, ctx: dict):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = msg.get("method")
    if method is None:
        return None                      # a client's reply to a server request - we send none
    is_note = "id" not in msg
    mid = msg.get("id")
    params = msg.get("params") or {}
    try:
        if method == "initialize":
            note = "" if ctx.get("enabled") else (
                "Note: access from AI apps is currently turned off in RaplMail Settings.")
            result = _initialize(params, note)
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tools_for(ctx.get("access") or "read") if ctx.get("enabled") else []}
        elif method == "tools/call":
            result = await _call(params, ctx)
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "prompts/list":
            result = {"prompts": []}
        elif method.startswith("notifications/"):
            return None
        else:
            raise RpcError(-32601, f"Method not found: {method}")
    except RpcError as exc:
        return None if is_note else {"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": exc.message}}
    return None if is_note else {"jsonrpc": "2.0", "id": mid, "result": result}


async def handle(payload, ctx: dict):
    """One JSON-RPC message (or a batch). Returns the reply, or None for a notification."""
    if isinstance(payload, list):
        replies = [r for r in [await _one(m, ctx) for m in payload] if r is not None]
        return replies or None
    return await _one(payload, ctx)


OFFLINE_NOTE = "RaplMail isn't running right now - start RaplMail (and unlock it) to use these tools."


def offline(msg):
    """The relay's answer while RaplMail is closed (or unreachable)."""
    if not isinstance(msg, dict):
        return None
    method, mid = msg.get("method"), msg.get("id")
    if method is None or "id" not in msg:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": _initialize(msg.get("params") or {}, OFFLINE_NOTE)}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tools_for("read")}}
    if method == "tools/call":
        return {"jsonrpc": "2.0", "id": mid, "result": _text_result(OFFLINE_NOTE, error=True)}
    if method in ("resources/list", "prompts/list"):
        return {"jsonrpc": "2.0", "id": mid, "result": {method.split("/")[0]: []}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
