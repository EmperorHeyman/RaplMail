"""The tools an AI app gets over MCP, and what each one does.

Three access levels (Settings -> AI assistant -> Connect AI apps), each including
the ones before it:

* ``read`` - list accounts and folders, search, read messages, conversations and
  attachments. Reading never marks anything as read.
* ``act``  - also mark read / done, flag, archive, move, snooze, and save drafts.
* ``send`` - also send mail.

Specs are plain data (the relay lists them even while RaplMail is closed);
implementations import the app lazily.
"""

from __future__ import annotations

import html as _html
import json
from datetime import datetime, timezone

LEVELS = {"read": 0, "act": 1, "send": 2}

_IDS = {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 200,
        "description": "Message ids (from search_messages / get_message)"}
_MAIL_FIELDS = {
    "to": {"type": "array", "items": {"type": "string"}, "description": "Recipient addresses"},
    "cc": {"type": "array", "items": {"type": "string"}},
    "bcc": {"type": "array", "items": {"type": "string"}},
    "subject": {"type": "string", "description": "Subject (for a reply, defaults to \"Re: \" + the original)"},
    "body": {"type": "string", "description": "Plain-text body; blank lines separate paragraphs"},
    "reply_to_message_id": {"type": "integer",
                            "description": "Make it a reply to this message (threading, subject, the account it came to)"},
    "account_id": {"type": "integer", "description": "Account to send from (default: the replied message's, else the first)"},
}

TOOLS: list[dict] = [
    {"name": "list_accounts", "level": "read", "title": "List mail accounts",
     "description": "The mail accounts set up in RaplMail: id and address. Use an id to narrow a search or to choose the account to write from.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_folders", "level": "read", "title": "List folders",
     "description": "Folders (id, name, role such as inbox/sent/archive/trash, unread and total counts), optionally for one account.",
     "inputSchema": {"type": "object", "properties": {
         "account_id": {"type": "integer", "description": "Only this account's folders"}}}},
    {"name": "search_messages", "level": "read", "title": "Search mail",
     "description": ("Find messages, newest first. `query` takes free text plus operators: from:, to:, cc:, subject:, "
                     "has:attachment, is:unread, is:read, is:flagged, is:done - e.g. 'from:boss is:unread invoice' "
                     "or 'subject:\"budget 2027\"'. Without a query it returns the most recent mail. Mail marked "
                     "done is left out unless include_done is true or the query has is:done. Returns ids for get_message."),
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"},
         "account_id": {"type": "integer"},
         "folder_id": {"type": "integer"},
         "inbox_only": {"type": "boolean", "description": "Only inbox folders (all accounts)"},
         "unread_only": {"type": "boolean"},
         "include_done": {"type": "boolean"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}}}},
    {"name": "get_message", "level": "read", "title": "Read a message",
     "description": "One message in full: sender, recipients, date, plain-text body and its attachments (index, name, size). The body is downloaded from the mail server the first time. Doesn't mark it as read.",
     "inputSchema": {"type": "object", "properties": {"message_id": {"type": "integer"}}, "required": ["message_id"]}},
    {"name": "get_thread", "level": "read", "title": "Read a conversation",
     "description": "Every message in the conversation a message belongs to, oldest first (headers and snippets - use get_message for a full body).",
     "inputSchema": {"type": "object", "properties": {"message_id": {"type": "integer"}}, "required": ["message_id"]}},
    {"name": "get_attachment_text", "level": "read", "title": "Read an attachment",
     "description": "Text extracted from one attachment (PDF, Word, Excel, plain text, ...) by the index get_message lists.",
     "inputSchema": {"type": "object", "properties": {"message_id": {"type": "integer"}, "index": {"type": "integer"}},
                     "required": ["message_id", "index"]}},
    {"name": "mark_read", "level": "act", "title": "Mark read or unread",
     "description": "Mark messages read (default) or unread - also on the mail server.",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS, "read": {"type": "boolean", "default": True}},
                     "required": ["message_ids"]}},
    {"name": "mark_done", "level": "act", "title": "Mark done",
     "description": "Mark messages done (RaplMail's triage: they leave the inbox view but stay in their folder) or, with done=false, back to not done.",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS, "done": {"type": "boolean", "default": True}},
                     "required": ["message_ids"]}},
    {"name": "flag", "level": "act", "title": "Flag or unflag",
     "description": "Flag (star) messages, or unflag them with flagged=false.",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS, "flagged": {"type": "boolean", "default": True}},
                     "required": ["message_ids"]}},
    {"name": "archive", "level": "act", "title": "Archive",
     "description": "Move messages to their account's Archive folder.",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS}, "required": ["message_ids"]}},
    {"name": "move_messages", "level": "act", "title": "Move to a folder",
     "description": "Move messages to a folder of the same account (folder ids from list_folders).",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS, "folder_id": {"type": "integer"}},
                     "required": ["message_ids", "folder_id"]}},
    {"name": "snooze", "level": "act", "title": "Snooze",
     "description": "Hide messages until a time (ISO 8601, e.g. 2026-10-29T09:00:00+01:00); they come back to the inbox then.",
     "inputSchema": {"type": "object", "properties": {"message_ids": _IDS, "until": {"type": "string"}},
                     "required": ["message_ids", "until"]}},
    {"name": "create_draft", "level": "act", "title": "Write a draft",
     "description": "Save a draft in the account's Drafts folder for the user to review and send. Plain-text body; the default signature is added.",
     "inputSchema": {"type": "object", "properties": dict(_MAIL_FIELDS), "required": ["to", "body"]}},
    {"name": "send_email", "level": "send", "title": "Send an email",
     "description": "Send an email right away (with the default signature). Same fields as create_draft. Prefer create_draft unless the user clearly asked to send.",
     "inputSchema": {"type": "object", "properties": dict(_MAIL_FIELDS), "required": ["to", "body"]}},
]
TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def _annotations(t: dict) -> dict:
    read = t["level"] == "read"
    return {"title": t["title"], "readOnlyHint": read, "destructiveHint": False,
            "idempotentHint": read, "openWorldHint": t["name"] == "send_email"}


def tools_for(access: str) -> list[dict]:
    """The MCP tool list for an access level (only the tools it allows)."""
    lvl = LEVELS.get(access, 0)
    return [{"name": t["name"], "title": t["title"], "description": t["description"],
             "inputSchema": t["inputSchema"], "annotations": _annotations(t)}
            for t in TOOLS if LEVELS[t["level"]] <= lvl]


class ToolError(Exception):
    """A tool failed in a way the AI should hear about (bad input, locked, ...)."""


# --- helpers -----------------------------------------------------------------

def _session():
    from sqlmodel import Session

    from app.core.db import get_engine
    return Session(get_engine())


def _iso(d) -> str:
    if not d:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _sender(name: str, addr: str) -> str:
    return f"{name} <{addr}>" if name and addr and name != addr else (addr or name or "")


def _brief(m) -> dict:
    """A message row for the AI: enough to pick one, no body."""
    return {"id": m.id, "account_id": m.account_id, "folder_id": m.folder_id,
            "from": _sender(m.from_name or "", m.from_addr or ""), "to": list(m.to_addrs or []),
            "subject": m.subject or "", "date": _iso(m.date), "snippet": (m.snippet or "")[:240],
            "unread": not m.is_seen, "flagged": bool(m.is_flagged), "done": bool(m.is_done),
            "has_attachments": bool(m.has_attachments), "thread_id": m.thread_id or ""}


def _int(args: dict, key: str, required: bool = True) -> int | None:
    v = args.get(key)
    if v is None:
        if required:
            raise ToolError(f"`{key}` is required")
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ToolError(f"`{key}` must be an integer") from None


def _ids(args: dict) -> list[int]:
    v = args.get("message_ids")
    if isinstance(v, (int, str)):
        v = [v]
    if not isinstance(v, list) or not v:
        raise ToolError("`message_ids` must be a non-empty list of message ids")
    try:
        ids = [int(x) for x in v]
    except (TypeError, ValueError):
        raise ToolError("`message_ids` must be integers") from None
    if len(ids) > 200:
        raise ToolError("at most 200 messages at a time")
    return ids


def _addrs(v) -> list[str]:
    if isinstance(v, str):
        v = [p for p in v.replace(";", ",").split(",")]
    return [str(a).strip() for a in (v or []) if str(a).strip()]


def _text_to_html(text: str) -> str:
    paras = [p for p in (text or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(f"<p>{_html.escape(p).replace(chr(10), '<br>')}</p>" for p in paras if p.strip()) or "<p></p>"


def _existing(session, ids: list[int]) -> list[int]:
    from sqlmodel import select

    from app.models import Message
    found = set(session.exec(select(Message.id).where(Message.id.in_(ids))).all())
    missing = [i for i in ids if i not in found]
    if missing:
        raise ToolError(f"no such message: {', '.join(map(str, missing[:10]))}")
    return ids


def _changed(request) -> None:
    """Tell the open RaplMail window to refresh its list."""
    import asyncio

    from app.core.ws import hub
    try:
        asyncio.get_running_loop().create_task(hub.broadcast("mail:changed", {"source": "mcp"}))
    except Exception:
        pass


def _unlocked() -> None:
    from app.core.security import get_secret_store
    if not get_secret_store().is_unlocked:
        raise ToolError("RaplMail is locked - unlock it with the master password first.")


# --- the tools ---------------------------------------------------------------

async def _list_accounts(args, request):
    from sqlmodel import select

    from app.models import Account
    with _session() as s:
        return [{"id": a.id, "email": a.email, "name": a.display_name or ""}
                for a in s.exec(select(Account).order_by(Account.sort_order, Account.id))]


async def _list_folders(args, request):
    from app.api.folders import list_folders
    with _session() as s:
        rows = list_folders(account_id=_int(args, "account_id", False), session=s)
        return [{"id": f.id, "account_id": f.account_id, "name": f.name, "role": getattr(f.role, "value", f.role),
                 "unread": f.unread_count, "total": f.total_count} for f in rows]


async def _search(args, request):
    from app.api.messages import list_messages
    from app.models import FolderRole
    limit = max(1, min(_int(args, "limit", False) or 20, 50))
    q = (args.get("query") or "").strip() or None
    with _session() as s:
        rows = list_messages(folder_id=_int(args, "folder_id", False), account_id=_int(args, "account_id", False),
                             role=FolderRole.inbox if args.get("inbox_only") else None,
                             include_done=bool(args.get("include_done")) or bool(q and "is:done" in q.lower()),
                             unread_only=bool(args.get("unread_only")), q=q, limit=limit, offset=0, session=s)
        return {"count": len(rows), "messages": [_brief(m) for m in rows]}


async def _get_message(args, request):
    from app.api.messages import get_message
    from app.sync.otp import html_to_text
    mid = _int(args, "message_id")
    with _session() as s:
        try:
            d = await get_message(mid, why="mcp", session=s)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                raise ToolError(f"no such message: {mid}") from None
            raise
    text = d.text or html_to_text(d.html or "")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    cut = len(text) > 40000
    out = {**_brief(d), "cc": list(d.cc_addrs or []), "body": text[:40000] + ("\n[... truncated]" if cut else ""),
           "attachments": [{"index": a.get("index", i), "filename": a.get("filename") or "", "size": a.get("size") or 0,
                            "content_type": a.get("content_type") or ""} for i, a in enumerate(d.attachments or [])]}
    if d.load_error:
        out["load_error"] = d.load_error
    return out


async def _get_thread(args, request):
    from app.api.messages import thread
    from app.models import Message
    mid = _int(args, "message_id")
    with _session() as s:
        m = s.get(Message, mid)
        if m is None:
            raise ToolError(f"no such message: {mid}")
        rows = thread(m.thread_id, session=s) if m.thread_id else []
        return {"messages": [_brief(r) for r in rows] or [_brief(m)]}


async def _attachment_text(args, request):
    from starlette.concurrency import run_in_threadpool

    from app.api.messages import _attachment_bytes
    from app.models import Account, Folder, Message
    from app.sync.extract import extract_attachment_text
    mid, idx = _int(args, "message_id"), _int(args, "index")
    with _session() as s:
        m = s.get(Message, mid)
        if m is None:
            raise ToolError(f"no such message: {mid}")
        account, folder = s.get(Account, m.account_id), s.get(Folder, m.folder_id)
    data, filename, ctype = await run_in_threadpool(_attachment_bytes, account, folder, m.uid, idx)
    if data is None:
        raise ToolError(f"message {mid} has no attachment {idx}")
    text = (extract_attachment_text(filename or "", ctype or "", data) or "").strip()
    if not text:
        return {"filename": filename, "content_type": ctype, "size": len(data),
                "text": "", "note": "No text could be extracted from this file type."}
    return {"filename": filename, "content_type": ctype, "size": len(data), "text": text[:40000]}


async def _bulk(ids, action, request, until=None):
    from app.api.messages import BulkIn, bulk
    with _session() as s:
        _existing(s, ids)
        r = await bulk(BulkIn(ids=ids, action=action, until=until), request, session=s)
    _changed(request)
    return r


async def _mark_read(args, request):
    return await _bulk(_ids(args), "seen" if args.get("read", True) else "unseen", request)


async def _mark_done(args, request):
    return await _bulk(_ids(args), "done" if args.get("done", True) else "undone", request)


async def _flag(args, request):
    return await _bulk(_ids(args), "flag" if args.get("flagged", True) else "unflag", request)


async def _archive(args, request):
    return await _bulk(_ids(args), "archive", request)


async def _snooze(args, request):
    raw = str(args.get("until") or "").strip()
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ToolError("`until` must be an ISO 8601 date-time, e.g. 2026-10-29T09:00:00+01:00") from None
    if until.tzinfo is None:
        until = until.astimezone()   # a bare time means the user's local time
    return await _bulk(_ids(args), "snooze", request, until=until)


async def _move(args, request):
    from app.api.messages import MoveIn, move_messages
    ids, fid = _ids(args), _int(args, "folder_id")
    with _session() as s:
        _existing(s, ids)
        r = await move_messages(MoveIn(ids=ids, folder_id=fid), request, session=s)
    _changed(request)
    return r


def _mail_payload(session, args) -> dict:
    """SendIn fields from the tool arguments (reply threading included)."""
    from sqlmodel import select

    from app.models import Account, Message
    to = _addrs(args.get("to"))
    if not to:
        raise ToolError("`to` needs at least one address")
    subject = str(args.get("subject") or "").strip()
    in_reply_to, refs = "", []
    account_id = _int(args, "account_id", False)
    rid = _int(args, "reply_to_message_id", False)
    if rid is not None:
        orig = session.get(Message, rid)
        if orig is None:
            raise ToolError(f"no such message to reply to: {rid}")
        in_reply_to = orig.message_id or ""
        refs = [orig.message_id] if orig.message_id else []
        account_id = account_id or orig.account_id
        if not subject:
            base = orig.subject or ""
            subject = base if base.lower().startswith(("re:", "odp:")) else f"Re: {base}"
    if account_id is None:
        first = session.exec(select(Account).order_by(Account.sort_order, Account.id)).first()
        if first is None:
            raise ToolError("no mail account is set up")
        account_id = first.id
    elif session.get(Account, account_id) is None:
        raise ToolError(f"no such account: {account_id}")
    return {"account_id": account_id, "to": to, "cc": _addrs(args.get("cc")), "bcc": _addrs(args.get("bcc")),
            "subject": subject, "html": _text_to_html(str(args.get("body") or "")),
            "in_reply_to": in_reply_to, "references": refs}


async def _create_draft(args, request):
    from app.api.compose import DraftIn, save_draft
    _unlocked()
    with _session() as s:
        payload = _mail_payload(s, args)
        r = await save_draft(DraftIn(**payload), session=s)
    _changed(request)
    return {"saved": True, "subject": payload["subject"], "to": payload["to"], **(r if isinstance(r, dict) else {})}


async def _send_email(args, request):
    from app.api.compose import SendIn, send
    _unlocked()
    with _session() as s:
        payload = _mail_payload(s, args)
        r = await send(SendIn(**payload), request, session=s)
    return {"sent": True, "subject": payload["subject"], "to": payload["to"], **(r if isinstance(r, dict) else {})}


RUN = {
    "list_accounts": _list_accounts, "list_folders": _list_folders, "search_messages": _search,
    "get_message": _get_message, "get_thread": _get_thread, "get_attachment_text": _attachment_text,
    "mark_read": _mark_read, "mark_done": _mark_done, "flag": _flag, "archive": _archive,
    "move_messages": _move, "snooze": _snooze, "create_draft": _create_draft, "send_email": _send_email,
}


async def run(name: str, args: dict, request) -> str:
    """Run a tool; the result as JSON text for the AI."""
    result = await RUN[name](args or {}, request)
    return json.dumps(result, ensure_ascii=False, default=str, indent=1)


def describe_args(name: str, args: dict) -> dict:
    """What a call was about, body-free, for the activity log ("what did the AI
    do"). Fields, not a sentence: the Settings card words it in the UI language."""
    args = args or {}
    if name == "search_messages":
        return {"query": str(args.get("query") or "")[:120]}
    if name in ("create_draft", "send_email"):
        return {"to": ", ".join(_addrs(args.get("to")))[:120], "subject": str(args.get("subject") or "")[:80]}
    if "message_ids" in args:
        ids = args.get("message_ids") or []
        return {"count": len(ids) if isinstance(ids, list) else 1}
    if "message_id" in args:
        return {"message": args.get("message_id")}
    return {}
