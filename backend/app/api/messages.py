"""Message listing, reading, and the Spark-style triage state toggles."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import String, cast, func, text
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import verify_token
from app.core.db import get_engine, get_session, index_message_fts
from app.models import (
    Account, ActionQueue, Contact, Folder, FolderRole, Message, MessageState,
    Rule, RuleAction, RuleField, RuleOp, SenderCategory,
)
from app.providers.imap_smtp import decode_mime_words

router = APIRouter(prefix="/messages", tags=["messages"], dependencies=[Depends(verify_token)])


class MessageOut(BaseModel):
    id: int
    account_id: int
    folder_id: int
    from_addr: str
    from_name: str
    to_addrs: list[str]
    subject: str
    snippet: str
    date: datetime | None
    is_seen: bool
    is_flagged: bool
    is_done: bool
    has_attachments: bool
    category: str
    thread_id: str
    brand_domain: str = ""
    auth_status: str = ""


class MessageDetail(MessageOut):
    html: str
    text: str
    cc_addrs: list[str]
    unsubscribe: str = ""
    attachments: list[dict] = []
    auth: dict = {}


def _to_out(m: Message) -> MessageOut:
    # decode_mime_words is idempotent, so this also fixes rows synced before the
    # decoding fix without a migration.
    return MessageOut(
        id=m.id, account_id=m.account_id, folder_id=m.folder_id, from_addr=m.from_addr,
        from_name=decode_mime_words(m.from_name), to_addrs=list(m.to_addrs or []),
        subject=decode_mime_words(m.subject),
        snippet=m.snippet, date=m.date, is_seen=m.is_seen, is_flagged=m.is_flagged,
        is_done=m.is_done, has_attachments=m.has_attachments, category=m.category,
        thread_id=m.thread_id, brand_domain=m.brand_domain or "", auth_status=m.auth_status or "",
    )


# Typed search operators: from:  to:  subject:  has:attachment  is:unread|read|done|flagged
_TOKEN_RE = re.compile(r'(\w+):(?:"([^"]*)"|(\S+))')


def _parse_query(q: str):
    """Split a query into structured operator filters + leftover free text."""
    filters: dict = {}
    def grab(m):
        key = m.group(1).lower()
        val = (m.group(2) if m.group(2) is not None else m.group(3) or "").strip()
        v = val.lower()
        if key == "from": filters["from"] = val
        elif key == "to": filters["to"] = val
        elif key == "subject": filters["subject"] = val
        elif key == "has" and v in ("attachment", "attachments", "file"): filters["has_attachment"] = True
        elif key == "is":
            if v in ("unread",): filters["unread"] = True
            elif v in ("read", "seen"): filters["read"] = True
            elif v in ("done",): filters["done"] = True
            elif v in ("flagged", "starred"): filters["flagged"] = True
        else:
            return m.group(0)  # unknown operator -> keep as free text
        return ""
    free = _TOKEN_RE.sub(grab, q).strip()
    return filters, free


@router.get("", response_model=list[MessageOut])
def list_messages(
    folder_id: int | None = None,
    account_id: int | None = None,
    role: FolderRole | None = None,   # e.g. "inbox" -> unified inbox across accounts
    category: str | None = None,
    exclude_categories: str | None = None,   # comma list hidden from the main list (smart inbox)
    include_done: bool = False,
    only_done: bool = False,
    unread_only: bool = False,
    flagged_only: bool = False,
    snoozed_only: bool = False,
    screener: str | None = None,   # "only" (unknown senders) | "exclude" (known only)
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[MessageOut]:
    # Regex search: /pattern/ scans the local DB (subject/from/snippet/body).
    if q and len(q.strip()) >= 3 and q.strip().startswith("/") and q.strip().endswith("/"):
        try:
            rx = re.compile(q.strip()[1:-1], re.IGNORECASE)
        except re.error:
            return []
        cand = session.exec(
            select(Message.id, Message.subject, Message.from_addr, Message.from_name,
                   Message.snippet, Message.body_text).where(Message.pending_action == "")
            .order_by(Message.date.desc()).limit(4000)
        ).all()
        ids = []
        for row in cand:
            hay = " ".join(str(x) for x in row[1:] if x)
            if rx.search(hay):
                ids.append(row[0])
            if len(ids) >= limit:
                break
        if not ids:
            return []
        msgs = session.exec(select(Message).where(Message.id.in_(ids))).all()
        order = {mid: i for i, mid in enumerate(ids)}
        msgs.sort(key=lambda m: order.get(m.id, 1_000_000))
        return [_to_out(m) for m in msgs]

    op_filters: dict = {}
    free_text = ""
    if q:
        op_filters, free_text = _parse_query(q)

    stmt = select(Message).where(Message.pending_action == "")
    # Scope (skip folder/role scope when doing a free-text/operator search so it
    # searches everywhere).
    searching = bool(q)
    if not searching:
        if folder_id is not None:
            stmt = stmt.where(Message.folder_id == folder_id)
        if role is not None:
            folder_ids = list(session.exec(select(Folder.id).where(Folder.role == role)))
            stmt = stmt.where(Message.folder_id.in_(folder_ids or [-1]))
        if account_id is not None:
            stmt = stmt.where(Message.account_id == account_id)

    if category:
        stmt = stmt.where(Message.category == category)
    if exclude_categories:
        excl = [c.strip() for c in exclude_categories.split(",") if c.strip()]
        if excl:
            stmt = stmt.where(Message.category.not_in(excl))

    # Snooze: hide messages snoozed into the future from normal views; the
    # Snoozed view shows only those. (Search ignores snooze.)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if snoozed_only:
        stmt = stmt.where(Message.snooze_until != None, Message.snooze_until > now)  # noqa: E711
    elif not searching:
        stmt = stmt.where((Message.snooze_until == None) | (Message.snooze_until <= now))  # noqa: E711

    # Done/unread/flagged from params or operators.
    if only_done or op_filters.get("done"):
        stmt = stmt.where(Message.is_done == True)  # noqa: E712
    elif not include_done and not searching:
        stmt = stmt.where(Message.is_done == False)  # noqa: E712
    if unread_only or op_filters.get("unread"):
        stmt = stmt.where(Message.is_seen == False)  # noqa: E712
    if op_filters.get("read"):
        stmt = stmt.where(Message.is_seen == True)  # noqa: E712
    if flagged_only or op_filters.get("flagged"):
        stmt = stmt.where(Message.is_flagged == True)  # noqa: E712
    if op_filters.get("has_attachment"):
        stmt = stmt.where(Message.has_attachments == True)  # noqa: E712
    if op_filters.get("from"):
        like = f"%{op_filters['from'].lower()}%"
        stmt = stmt.where(func.lower(Message.from_addr).like(like) | func.lower(Message.from_name).like(like))
    if op_filters.get("to"):
        stmt = stmt.where(func.lower(cast(Message.to_addrs, String)).like(f"%{op_filters['to'].lower()}%"))
    if op_filters.get("subject"):
        stmt = stmt.where(func.lower(Message.subject).like(f"%{op_filters['subject'].lower()}%"))

    # Free text -> FTS5, restrict + rank.
    fts_rank = None
    if free_text:
        # Quote each token so emails/punctuation don't trigger FTS5 syntax errors.
        safe = " ".join('"' + t.replace('"', '""') + '"' for t in free_text.split())
        rows = session.exec(
            text("SELECT rowid FROM message_fts WHERE message_fts MATCH :q ORDER BY rank LIMIT 2000")
            .bindparams(q=safe)
        ).all()
        ids = [r[0] for r in rows]
        if not ids:
            return []
        stmt = stmt.where(Message.id.in_(ids))
        fts_rank = {mid: i for i, mid in enumerate(ids)}

    # Newest first at the SQL level, so the limit keeps the most recent mail
    # (not the first rows by insertion order).
    stmt = stmt.order_by(Message.date.desc())

    use_screener = screener in ("only", "exclude") and not searching
    fetch_limit = 2000 if fts_rank else (max(limit * 5, 200) if use_screener else limit)
    msgs = list(session.exec(stmt.limit(fetch_limit)))

    if use_screener:
        from app.sync.contacts import KNOWN_DOMAINS
        known = {e.lower() for e in session.exec(select(Contact.email))}

        def known_sender(m: Message) -> bool:
            a = (m.from_addr or "").lower()
            return a in known or a.rsplit("@", 1)[-1] in KNOWN_DOMAINS

        msgs = [m for m in msgs if (not known_sender(m)) == (screener == "only")]

    if fts_rank is not None:
        msgs.sort(key=lambda m: fts_rank.get(m.id, 1_000_000))
        msgs = msgs[:limit]
    else:
        msgs.sort(key=lambda m: m.date.timestamp() if m.date else 0.0, reverse=True)
        msgs = msgs[offset:offset + limit]
    return [_to_out(m) for m in msgs]


@router.get("/followups", response_model=list[MessageOut])
def followups(days: int = 3, session: Session = Depends(get_session)) -> list[MessageOut]:
    """Sent messages >= `days` old with no reply yet — nudge to follow up.
    Declared before /{message_id} so the path isn't captured by the int route."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    older_than = now - timedelta(days=days)
    recent = now - timedelta(days=30)
    sent_ids = list(session.exec(select(Folder.id).where(Folder.role == FolderRole.sent)))
    if not sent_ids:
        return []

    inbound: dict[str, datetime] = {}
    for from_addr, date in session.exec(
        select(Message.from_addr, Message.date).where(Message.folder_id.not_in(sent_ids))
    ):
        a = (from_addr or "").lower()
        if a and date and (a not in inbound or date > inbound[a]):
            inbound[a] = date

    sent = session.exec(
        select(Message).where(Message.folder_id.in_(sent_ids),
                              Message.date <= older_than, Message.date >= recent)
        .order_by(Message.date.desc())
    ).all()

    out: list[MessageOut] = []
    for m in sent:
        recipients = [(r or "").lower() for r in (m.to_addrs or [])]
        replied = any(inbound.get(r) and inbound[r] > m.date for r in recipients)
        if not replied:
            out.append(_to_out(m))
        if len(out) >= 100:
            break
    return out


class QueueStatus(BaseModel):
    pending: int
    failed: int


def queue_counts() -> dict:
    from app.core.db import get_engine
    with Session(get_engine()) as s:
        pending = len(s.exec(select(ActionQueue.id).where(ActionQueue.status == "pending")).all())
        failed = len(s.exec(select(ActionQueue.id).where(ActionQueue.status == "failed")).all())
    return {"pending": pending, "failed": failed}


@router.get("/queue", response_model=QueueStatus)
def queue_status(session: Session = Depends(get_session)) -> QueueStatus:
    return QueueStatus(**queue_counts())


@router.post("/queue/retry")
def queue_retry(session: Session = Depends(get_session)) -> dict:
    n = 0
    for a in session.exec(select(ActionQueue).where(ActionQueue.status == "failed")):
        a.status = "pending"
        a.attempts = 0
        n += 1
    session.commit()
    return {"retrying": n}


@router.get("/category-counts")
def category_counts(role: FolderRole | None = None, folder_id: int | None = None,
                    session: Session = Depends(get_session)) -> dict[str, int]:
    """Live count of active (not done/snoozed/queued) messages per category."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = select(Message.category, func.count()).where(
        Message.pending_action == "", Message.is_done == False,  # noqa: E712
        ((Message.snooze_until == None) | (Message.snooze_until <= now)),  # noqa: E711
    )
    if folder_id is not None:
        stmt = stmt.where(Message.folder_id == folder_id)
    elif role is not None:
        fids = list(session.exec(select(Folder.id).where(Folder.role == role)))
        stmt = stmt.where(Message.folder_id.in_(fids or [-1]))
    stmt = stmt.group_by(Message.category)
    return {cat: cnt for cat, cnt in session.exec(stmt)}


@router.get("/smart-groups")
def smart_groups(role: FolderRole | None = None, folder_id: int | None = None,
                 session: Session = Depends(get_session)) -> dict:
    """Per-category preview for the Smart Inbox: count, latest activity, and top senders."""
    from sqlalchemy import distinct
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def scoped(stmt):
        stmt = stmt.where(Message.pending_action == "", Message.is_done == False,  # noqa: E712
                          ((Message.snooze_until == None) | (Message.snooze_until <= now)))  # noqa: E711
        if folder_id is not None:
            return stmt.where(Message.folder_id == folder_id)
        if role is not None:
            fids = list(session.exec(select(Folder.id).where(Folder.role == role)))
            return stmt.where(Message.folder_id.in_(fids or [-1]))
        return stmt

    out: dict = {}
    cats = session.exec(scoped(select(Message.category, func.count(), func.max(Message.date)))
                        .group_by(Message.category)).all()
    for cat, cnt, latest in cats:
        sender_rows = session.exec(
            scoped(select(Message.from_addr, func.max(Message.from_name), func.count()))
            .where(Message.category == cat).group_by(Message.from_addr)
            .order_by(func.count().desc()).limit(8)
        ).all()
        distinct_total = session.exec(
            scoped(select(func.count(distinct(Message.from_addr)))).where(Message.category == cat)
        ).one()
        senders = [{"email": addr, "name": decode_mime_words(nm) or addr, "count": sc}
                   for addr, nm, sc in sender_rows]
        out[cat] = {
            "count": cnt,
            "latest": latest.isoformat() if latest else None,
            "senders": senders,
            "distinct": distinct_total,   # total unique senders (frontend computes "+N")
        }
    return out


@router.get("/thread", response_model=list[MessageOut])
def thread(thread_id: str, session: Session = Depends(get_session)) -> list[MessageOut]:
    """All messages in a conversation (across folders), oldest first."""
    if not thread_id:
        return []
    msgs = list(session.exec(select(Message).where(Message.thread_id == thread_id)))
    msgs.sort(key=lambda m: m.date.timestamp() if m.date else 0.0)
    return [_to_out(m) for m in msgs]


@router.get("/{message_id}", response_model=MessageDetail)
async def get_message(message_id: int, session: Session = Depends(get_session)) -> MessageDetail:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")

    auth = {"status": msg.auth_status or "none"}
    if msg.body_fetched:
        html, text_body = msg.body_html, msg.body_text
        # Backfill (one raw fetch) for mail cached before attachments/auth existed.
        if (msg.has_attachments and not msg.attachments) or not msg.auth_status:
            account = session.get(Account, msg.account_id)
            folder = session.get(Folder, msg.folder_id)
            try:
                _h, _t, _u, _e, atts, a = await run_in_threadpool(_fetch_body, account, folder, msg.uid)
                if atts and not msg.attachments:
                    msg.attachments = atts
                msg.auth_status = a.get("status", "none")
                auth = a
                session.add(msg)
                session.commit()
                session.refresh(msg)
            except Exception:
                pass
    else:
        account = session.get(Account, msg.account_id)
        folder = session.get(Folder, msg.folder_id)
        html, text_body, unsub, events, atts, auth = await run_in_threadpool(_fetch_body, account, folder, msg.uid)
        # Cache so re-opening is instant.
        msg.body_html, msg.body_text, msg.body_fetched, msg.unsubscribe = html, text_body, True, unsub
        msg.attachments = atts
        msg.auth_status = auth.get("status", "none")
        if events:
            from app.api.calendar import upsert_events
            try: upsert_events(session, msg.account_id, msg.id, events)
            except Exception: pass
        session.add(msg)
        # Index the body for full-text search now that we have it.
        try:
            index_message_fts(session, msg.id, subject=msg.subject, from_addr=msg.from_addr,
                              from_name=msg.from_name, snippet=msg.snippet, body=text_body[:20000])
        except Exception:
            pass
        session.commit()
        session.refresh(msg)

    # Derive a "brand" domain from the body's links so the avatar can fall back
    # to it when the sender's own domain has no favicon (computed from cached
    # html — no extra IMAP round-trip).
    if html:
        bd = _brand_domain(html, msg.from_addr)
        if bd and bd != msg.brand_domain:
            msg.brand_domain = bd
            session.add(msg)
            session.commit()
            session.refresh(msg)

    base = _to_out(msg)
    return MessageDetail(**base.model_dump(), html=html, text=text_body,
                         cc_addrs=list(msg.cc_addrs or []), unsubscribe=msg.unsubscribe,
                         attachments=list(msg.attachments or []), auth=auth)


def _attachment_size(att: dict) -> int:
    payload = att.get("payload") or ""
    cte = (att.get("content_transfer_encoding") or "").lower()
    try:
        if cte == "base64":
            import base64
            return len(base64.b64decode(payload))
        return len(payload)
    except Exception:
        return 0


def _attachment_meta(parsed) -> list[dict]:
    """User-facing attachment list. Skips inline body images (embedded logos)."""
    out: list[dict] = []
    for i, a in enumerate(parsed.attachments or []):
        fname = (a.get("filename") or "").strip()
        ctype = a.get("mail_content_type") or "application/octet-stream"
        cid = (a.get("content-id") or "").strip("<>")
        inline = bool(cid) and ctype.startswith("image/")
        if inline and not fname:
            continue  # embedded body image — not a real attachment
        out.append({
            "index": i,
            "filename": fname or f"attachment-{i + 1}",
            "content_type": ctype,
            "size": _attachment_size(a),
            "inline": inline,
        })
    return out


# Link domains that are never a sender's "brand" — trackers, CDNs, ESPs, social.
_BRAND_BLOCK = (
    "google", "gstatic", "googleapis", "doubleclick", "ggpht", "youtube", "ytimg",
    "microsoft", "office", "office365", "outlook", "live.com", "msn", "bing",
    "apple", "icloud", "facebook", "fbcdn", "fb.com", "instagram", "twitter", "x.com",
    "linkedin", "licdn", "pinterest", "tiktok", "snapchat", "whatsapp",
    "mailchimp", "list-manage", "mcusercontent", "sendgrid", "sparkpostmail", "mailgun",
    "sendinblue", "klaviyo", "hubspot", "mandrillapp", "exct", "rs6", "constantcontact",
    "cmail", "createsend", "salesforce", "marketo", "mktoresp", "amazonaws", "cloudfront",
    "akamai", "fastly", "cdn", "gravatar", "w3.org", "schema.org", "bit.ly", "goo.gl",
    "sentry", "fonts", "gmail", "googlemail",
)
_HREF_RE = re.compile(r'href=["\']https?://([^/"\'?#\s]+)', re.IGNORECASE)


def _brand_domain(html: str, sender_addr: str) -> str:
    """Pick the most-linked external company domain in the body (Spark-style).

    Skips trackers/CDNs/ESPs and the sender's own domain. Returns "" if none.
    """
    if not html:
        return ""
    from collections import Counter
    sender_dom = (sender_addr or "").split("@")[-1].lower()
    counts: Counter = Counter()
    for host in _HREF_RE.findall(html):
        host = host.lower().split(":")[0].rstrip(".")
        # Keep the FULL host (incl. subdomain) — e.g. hr.a123systems.cz has its own
        # favicon even when the bare a123systems.cz doesn't. Only skip the sender's
        # exact bare domain (whose icon we already try as the primary avatar).
        if not re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", host):
            continue
        if host == sender_dom or host == f"www.{sender_dom}":
            continue
        if any(b in host for b in _BRAND_BLOCK):
            continue
        counts[host] += 1
    return counts.most_common(1)[0][0] if counts else ""


def _fetch_body(account: Account, folder: Folder, uid: int) -> tuple[str, str, str, list, list, dict]:
    """Fetch + parse raw into (html, text, list_unsubscribe, ics_events, attachments, auth)."""
    import mailparser

    from app.providers.pool import pool
    from app.sync.authcheck import check_auth
    from app.sync.ics import extract_ics

    raw = pool.fetch_raw(account, folder.path, uid)
    if not raw:
        return "", "", "", [], [], {"status": "none"}
    parsed = mailparser.parse_from_bytes(raw)
    html = "\n".join(parsed.text_html) if parsed.text_html else ""
    text_body = "\n".join(parsed.text_plain) if parsed.text_plain else ""
    unsub = ""
    for k, v in (parsed.headers or {}).items():
        if k.lower() == "list-unsubscribe":
            unsub = v if isinstance(v, str) else str(v)
            break
    try:
        events = extract_ics(raw)
    except Exception:
        events = []
    try:
        atts = _attachment_meta(parsed)
    except Exception:
        atts = []
    try:
        from_addr = parsed.from_[0][1] if parsed.from_ else ""
        auth = check_auth(raw, from_addr)
    except Exception:
        auth = {"status": "none"}
    return html, text_body, unsub, events, atts, auth


@router.get("/{message_id}/attachments/{index}")
async def download_attachment(message_id: int, index: int,
                              session: Session = Depends(get_session)):
    from fastapi import Response
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    account = session.get(Account, msg.account_id)
    folder = session.get(Folder, msg.folder_id)
    data, filename, ctype = await run_in_threadpool(_attachment_bytes, account, folder, msg.uid, index)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
    from urllib.parse import quote
    return Response(content=data, media_type=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


def _attachment_bytes(account: Account, folder: Folder, uid: int, index: int):
    import base64
    import mailparser

    from app.providers.pool import pool

    raw = pool.fetch_raw(account, folder.path, uid)
    if not raw:
        return None, "", ""
    parsed = mailparser.parse_from_bytes(raw)
    atts = parsed.attachments or []
    if index < 0 or index >= len(atts):
        return None, "", ""
    a = atts[index]
    payload = a.get("payload") or ""
    cte = (a.get("content_transfer_encoding") or "").lower()
    try:
        data = base64.b64decode(payload) if cte == "base64" else (
            payload.encode("utf-8", "replace") if isinstance(payload, str) else payload)
    except Exception:
        data = payload.encode("utf-8", "replace") if isinstance(payload, str) else (payload or b"")
    fname = (a.get("filename") or f"attachment-{index + 1}").strip() or f"attachment-{index + 1}"
    return data, fname, a.get("mail_content_type") or "application/octet-stream"


# --- triage state toggles ---------------------------------------------------
class BoolValue(BaseModel):
    value: bool


def _persist_state(session: Session, msg: Message, *, done: bool | None = None) -> None:
    if not msg.message_id:
        return
    state = session.exec(
        select(MessageState).where(MessageState.account_id == msg.account_id,
                                   MessageState.message_id == msg.message_id)
    ).first()
    if state is None:
        state = MessageState(account_id=msg.account_id, message_id=msg.message_id)
        session.add(state)
    if done is not None:
        state.is_done = done


@router.post("/{message_id}/done", response_model=MessageOut)
def set_done(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    """The hero action: mark a message done so it leaves the inbox view."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.is_done = body.value
    _persist_state(session, msg, done=body.value)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return _to_out(msg)


# Sentinel "far future" used for presence snooze (kept hidden until you return).
PRESENCE_UNTIL = datetime(2999, 1, 1)


class SnoozeIn(BaseModel):
    until: datetime | None = None  # ISO datetime; null = unsnooze
    presence: bool = False         # snooze "until I'm back at my desk"


@router.post("/{message_id}/snooze", response_model=MessageOut)
def snooze(message_id: int, body: SnoozeIn, session: Session = Depends(get_session)) -> MessageOut:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    if body.presence:
        until = PRESENCE_UNTIL
    else:
        until = body.until
        if until is not None and until.tzinfo is not None:
            until = until.astimezone(timezone.utc).replace(tzinfo=None)
    msg.snooze_until = until
    msg.snooze_presence = bool(body.presence)
    # Persist durably (survives re-sync) keyed by Message-ID.
    if msg.message_id:
        state = session.exec(
            select(MessageState).where(MessageState.account_id == msg.account_id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state is None:
            state = MessageState(account_id=msg.account_id, message_id=msg.message_id)
            session.add(state)
        state.snooze_until = until
        state.snooze_presence = bool(body.presence)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return _to_out(msg)


@router.post("/{message_id}/flag", response_model=MessageOut)
def set_flag(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.is_flagged = body.value
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return _to_out(msg)


class BulkIn(BaseModel):
    ids: list[int]
    action: str                    # done|undone|seen|unseen|flag|unflag|snooze|archive|delete
    until: datetime | None = None  # for snooze


@router.post("/bulk")
async def bulk(body: BulkIn, request: Request, session: Session = Depends(get_session)) -> dict:
    a = body.action
    db_actions = {"done", "undone", "seen", "unseen", "flag", "unflag", "snooze"}
    if a in db_actions:
        until = body.until
        if until is not None and until.tzinfo is not None:
            until = until.astimezone(timezone.utc).replace(tzinfo=None)
        msgs = session.exec(select(Message).where(Message.id.in_(body.ids))).all()
        for m in msgs:
            if a == "done": m.is_done = True; _persist_state(session, m, done=True)
            elif a == "undone": m.is_done = False; _persist_state(session, m, done=False)
            elif a == "seen": m.is_seen = True
            elif a == "unseen": m.is_seen = False
            elif a == "flag": m.is_flagged = True
            elif a == "unflag": m.is_flagged = False
            elif a == "snooze": m.snooze_until = until; _persist_snooze(session, m, until)
            session.add(m)
        session.commit()
        return {"updated": len(msgs)}

    if a in ("archive", "delete"):
        # Queue it: hide the messages immediately, flush to IMAP in the background
        # (offline-resilient — retried until the connection is back).
        msgs = session.exec(select(Message).where(Message.id.in_(body.ids))).all()
        for m in msgs:
            m.pending_action = a
            session.add(m)
        session.add(ActionQueue(kind=a, payload={"ids": list(body.ids)}))
        session.commit()
        request.app.state.sync.request_sync()  # flush soon
        return {"queued": len(msgs)}

    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown action {a}")


def _persist_snooze(session: Session, msg: Message, until) -> None:
    if not msg.message_id:
        return
    state = session.exec(
        select(MessageState).where(MessageState.account_id == msg.account_id,
                                   MessageState.message_id == msg.message_id)
    ).first()
    if state is None:
        state = MessageState(account_id=msg.account_id, message_id=msg.message_id)
        session.add(state)
    state.snooze_until = until


def _flush_move(ids: list[int], action: str) -> None:
    """Move messages to Archive/Trash on the server. Raises on connection failure
    (so the queue retries); commits per-message so partial progress is kept."""
    from collections import defaultdict

    from app.core.db import get_engine
    from app.sync.engine import build_provider

    with Session(get_engine()) as session:
        msgs = session.exec(select(Message).where(Message.id.in_(ids))).all()
        by_acct: dict[int, list[Message]] = defaultdict(list)
        for m in msgs:
            by_acct[m.account_id].append(m)
        role = FolderRole.archive if action == "archive" else FolderRole.trash
        for acct_id, group in by_acct.items():
            account = session.get(Account, acct_id)
            dest = session.exec(
                select(Folder.path).where(Folder.account_id == acct_id, Folder.role == role)
            ).first()
            provider = build_provider(account)  # connection errors propagate -> retry
            try:
                for m in group:
                    folder = session.get(Folder, m.folder_id)
                    if dest:
                        provider.move(folder.path, m.uid, dest)
                    else:
                        provider.delete(folder.path, m.uid)
                    session.delete(m)
                    session.commit()
            finally:
                provider.close()


def process_action_queue() -> int:
    """Flush queued archive/delete/send actions to IMAP/SMTP, retrying on failure."""
    from app.core.db import get_engine

    with Session(get_engine()) as session:
        items = session.exec(select(ActionQueue).where(ActionQueue.status == "pending")).all()
        snapshot = [(a.id, a.kind, dict(a.payload)) for a in items]

    flushed = 0
    for aid, kind, payload in snapshot:
        ok, err = True, ""
        try:
            if kind in ("archive", "delete"):
                _flush_move(payload.get("ids", []), kind)
            elif kind == "send":
                from app.api.compose import _deliver_blocking
                _deliver_blocking(payload)
        except Exception as exc:
            ok, err = False, str(exc)
        with Session(get_engine()) as session:
            a = session.get(ActionQueue, aid)
            if a:
                if ok:
                    session.delete(a)
                    flushed += 1
                else:
                    a.attempts += 1
                    a.last_error = err[:300]
                    if a.attempts >= 8:
                        a.status = "failed"
                session.commit()
    return flushed


@router.post("/{message_id}/mute")
def mute(message_id: int, session: Session = Depends(get_session)) -> dict:
    """Mute a sender: auto-mark future mail from them done, and clear existing."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    addr = (msg.from_addr or "").strip()
    if not addr:
        return {"muted": ""}
    exists = session.exec(
        select(Rule).where(Rule.match_field == RuleField.from_addr,
                           Rule.match_value == addr, Rule.action == RuleAction.mark_done)
    ).first()
    if not exists:
        session.add(Rule(account_id=None, name=f"Muted {addr}", enabled=True,
                         match_field=RuleField.from_addr, match_op=RuleOp.equals,
                         match_value=addr, action=RuleAction.mark_done))
    # Clear out anything already in the inbox from this sender.
    for m in session.exec(select(Message).where(func.lower(Message.from_addr) == addr.lower())):
        m.is_done = True
        _persist_state(session, m, done=True)
    session.commit()
    return {"muted": addr}


@router.post("/{message_id}/mute-thread")
def mute_thread(message_id: int, session: Session = Depends(get_session)) -> dict:
    """Mute a whole conversation: remember its thread key (new replies auto-archive
    on arrival) and clear everything already in it."""
    from app.models import MutedThread
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    key = msg.thread_id
    if not key:
        return {"muted": "", "count": 0}
    if not session.exec(select(MutedThread).where(MutedThread.thread_key == key)).first():
        session.add(MutedThread(thread_key=key))
    n = 0
    for m in session.exec(select(Message).where(Message.thread_id == key)):
        m.is_done = True
        _persist_state(session, m, done=True)
        n += 1
    session.commit()
    return {"muted": key, "count": n}


@router.post("/{message_id}/unmute-thread")
def unmute_thread(message_id: int, session: Session = Depends(get_session)) -> dict:
    from app.models import MutedThread
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    row = session.exec(select(MutedThread).where(MutedThread.thread_key == msg.thread_id)).first()
    if row:
        session.delete(row)
        session.commit()
    return {"unmuted": msg.thread_id}


@router.post("/rethread")
def rethread(session: Session = Depends(get_session)) -> dict:
    """Backfill thread ids for mail synced before threading existed (column-only)."""
    from app.sync.threading import thread_key
    rows = session.exec(select(Message.id, Message.account_id, Message.subject,
                               Message.uid, Message.thread_id)).all()
    n = 0
    for mid, acct, subj, uid, tid in rows:
        new = thread_key(acct, subj or "", uid or 0)
        if new != tid:
            session.exec(text("UPDATE message SET thread_id = :t WHERE id = :i").bindparams(t=new, i=mid))
            n += 1
    session.commit()
    return {"updated": n}


class SenderCategoryIn(BaseModel):
    email: str
    category: str   # a category, or "auto" to clear the override


@router.post("/sender-category")
def set_sender_category(body: SenderCategoryIn, session: Session = Depends(get_session)) -> dict:
    """Reclassify a sender ('this is a newsletter'): remember it and re-file existing mail."""
    from app.sync.categorize import categorize
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email required")
    existing = session.exec(select(SenderCategory).where(SenderCategory.email == email)).first()
    n = 0
    if body.category == "auto" or not body.category:
        if existing:
            session.delete(existing)
        # Re-file existing mail from this sender back to the heuristic category.
        for m in session.exec(select(Message).where(func.lower(Message.from_addr) == email)):
            m.category = categorize(m.from_addr, m.from_name, m.subject, m.snippet); n += 1
    else:
        if existing:
            existing.category = body.category
        else:
            session.add(SenderCategory(email=email, category=body.category))
        for m in session.exec(select(Message).where(func.lower(Message.from_addr) == email)):
            m.category = body.category; n += 1
    session.commit()
    return {"updated": n}


@router.post("/recategorize")
def recategorize(session: Session = Depends(get_session)) -> dict:
    """Recompute categories for all messages, honoring sender overrides. Column-only."""
    from app.sync.categorize import categorize
    overrides = {sc.email.lower(): sc.category for sc in session.exec(select(SenderCategory))}
    rows = session.exec(
        select(Message.id, Message.from_addr, Message.from_name, Message.subject,
               Message.snippet, Message.category)
    ).all()
    n = 0
    for mid, fa, fn, subj, snip, cat in rows:
        new = overrides.get((fa or "").lower()) or categorize(fa or "", fn or "", subj or "", snip or "")
        if new != cat:
            session.exec(text("UPDATE message SET category = :c WHERE id = :i").bindparams(c=new, i=mid))
            n += 1
    session.commit()
    return {"updated": n}


@router.post("/{message_id}/seen", response_model=MessageOut)
def set_seen(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.is_seen = body.value
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return _to_out(msg)
