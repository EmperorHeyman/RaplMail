"""The stdio MCP server an AI app launches: ``raplmail-backend.exe --mcp``.

It reads JSON-RPC messages line by line from stdin, forwards each to the
running RaplMail (POST /mcp, found through the endpoint file) and writes the
reply to stdout. While RaplMail isn't running it still answers - the AI app
connects, lists the tools, and is told to start RaplMail when it calls one.

stdout carries protocol messages only; anything else goes to stderr.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from app.mcp import endpoint, protocol

# A tool can take a while (downloading a big message, extracting a PDF).
TIMEOUT = 300
# After a refused connection, answer "not running" straight away for this long
# instead of waiting on the same dead endpoint again (Windows takes ~2 s to
# refuse a loopback connect). Short, because RaplMail writes the file just
# before it starts listening.
DEAD_FOR = 5.0
# No proxy for the loopback call (a system proxy must not see it).
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_dead: tuple[str, float] | None = None     # (endpoint key, until) - left behind by a closed RaplMail


def _forward(msg):
    global _dead
    ep = endpoint.read()
    if ep is None:
        return protocol.offline(msg)
    if _dead and _dead[0] == ep["key"] and time.monotonic() < _dead[1]:
        return protocol.offline(msg)
    req = urllib.request.Request(
        ep["url"], data=json.dumps(msg).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "Authorization": f"Bearer {ep['key']}"})
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            return json.loads(body) if body.strip() else None
    except urllib.error.HTTPError as exc:
        if exc.code == 202:
            return None
        print(f"raplmail mcp: backend answered HTTP {exc.code}", file=sys.stderr)
        return protocol.offline(msg)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if isinstance(getattr(exc, "reason", exc), ConnectionRefusedError):
            _dead = (ep["key"], time.monotonic() + DEAD_FOR)
        print(f"raplmail mcp: RaplMail not reachable ({exc})", file=sys.stderr)
        return protocol.offline(msg)


def _write(out, obj) -> None:
    out.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    out.flush()


def main() -> None:
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    for raw in inp:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        reply = _forward(msg)
        if reply is not None:
            _write(out, reply)


if __name__ == "__main__":
    main()
