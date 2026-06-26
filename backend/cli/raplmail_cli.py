#!/usr/bin/env python3
"""raplmail-cli — drive your local RaplMail backend from the terminal.

The backend is a localhost HTTP service. In dev it needs no token; the packaged
app uses a per-launch token + random port. Point the CLI at it with env vars:

    RAPLMAIL_URL    base URL of the backend     (default http://127.0.0.1:8765)
    RAPLMAIL_TOKEN  X-RaplMail-Token, if the backend requires one

Examples:
    raplmail-cli unread                       # count + list recent unread
    raplmail-cli search "invoice from:acme"   # full-text search (incl. attachments)
    raplmail-cli accounts                      # connected accounts + health
    raplmail-cli send -t you@x.com -s "Build done" --account 1
    make 2>&1 | raplmail-cli send -t me@x.com -s "Build log"   # pipe stdin into the body

Pure stdlib — no dependencies. Designed to pipe terminal output straight into a draft.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("RAPLMAIL_URL", "http://127.0.0.1:8765").rstrip("/")
TOKEN = os.environ.get("RAPLMAIL_TOKEN", "")

# Subjects/names contain emoji & non-Latin text; force UTF-8 so a Windows
# cp1252 console doesn't crash on them.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _request(method: str, path: str, body: dict | None = None) -> object:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["X-RaplMail-Token"] = TOKEN
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        sys.exit(f"error {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach backend at {BASE} ({e.reason}). Is RaplMail running?")


def cmd_unread(args: argparse.Namespace) -> None:
    rows = _request("GET", "/messages?" + urllib.parse.urlencode({"unread_only": "true", "limit": args.limit}))
    rows = rows if isinstance(rows, list) else rows.get("items", rows)
    print(f"{len(rows)} unread")
    for m in rows:
        who = m.get("from_name") or m.get("from_addr") or "?"
        print(f"  [{m.get('id')}] {who:<28.28}  {m.get('subject', '')[:60]}")


def cmd_search(args: argparse.Namespace) -> None:
    rows = _request("GET", "/messages?" + urllib.parse.urlencode({"q": args.query, "limit": args.limit}))
    rows = rows if isinstance(rows, list) else rows.get("items", rows)
    print(f"{len(rows)} match \"{args.query}\"")
    for m in rows:
        who = m.get("from_name") or m.get("from_addr") or "?"
        print(f"  [{m.get('id')}] {who:<28.28}  {m.get('subject', '')[:60]}")


def cmd_accounts(_args: argparse.Namespace) -> None:
    rows = _request("GET", "/accounts/health")
    for a in rows:
        idle = " ⚡live" if a.get("idle_active") else ""
        print(f"  [{a['id']}] {a['email']:<32} {a.get('status', '?'):<9} "
              f"{a.get('unread', a.get('messages', '?'))} unread  {a.get('messages', '?')} msgs{idle}")


def cmd_metrics(_args: argparse.Namespace) -> None:
    print(json.dumps(_request("GET", "/metrics"), indent=2))


def cmd_send(args: argparse.Namespace) -> None:
    body_text = args.body
    if body_text is None and not sys.stdin.isatty():
        body_text = sys.stdin.read()
    body_text = body_text or ""
    # Wrap piped/plain text so it renders with line breaks preserved.
    html = "<pre style=\"white-space:pre-wrap;font-family:ui-monospace,monospace\">" + \
           body_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"
    payload = {
        "account_id": args.account,
        "to": [t.strip() for t in args.to.split(",") if t.strip()],
        "subject": args.subject,
        "html": html,
        "use_default_signature": not args.no_signature,
    }
    res = _request("POST", "/compose/send", payload)
    print(json.dumps(res))


def main() -> None:
    p = argparse.ArgumentParser(prog="raplmail-cli", description="Drive your local RaplMail backend.")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("unread", help="list unread messages")
    u.add_argument("--limit", type=int, default=20)
    u.set_defaults(func=cmd_unread)

    s = sub.add_parser("search", help="full-text search (subject/from/body/attachments)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_search)

    a = sub.add_parser("accounts", help="list accounts and their health")
    a.set_defaults(func=cmd_accounts)

    m = sub.add_parser("metrics", help="dump mailbox metrics JSON")
    m.set_defaults(func=cmd_metrics)

    sd = sub.add_parser("send", help="send a message (body from --body or stdin)")
    sd.add_argument("-t", "--to", required=True, help="comma-separated recipients")
    sd.add_argument("-s", "--subject", default="")
    sd.add_argument("-b", "--body", default=None, help="body text (omit to read stdin)")
    sd.add_argument("--account", type=int, required=True, help="account id (see `accounts`)")
    sd.add_argument("--no-signature", action="store_true")
    sd.set_defaults(func=cmd_send)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
