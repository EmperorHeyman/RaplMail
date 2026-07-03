"""Message listing, reading, and the Spark-style triage state toggles."""

from __future__ import annotations

import logging
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
    Rule, RuleAction, RuleField, RuleOp, SenderCategory, Setting,
)
from app.providers.imap_smtp import decode_mime_words

router = APIRouter(prefix="/messages", tags=["messages"], dependencies=[Depends(verify_token)])
log = logging.getLogger("raplmail.messages")


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
    pinned: bool = False


class MessageDetail(MessageOut):
    html: str
    text: str
    cc_addrs: list[str]
    unsubscribe: str = ""
    attachments: list[dict] = []
    auth: dict = {}
    warnings: list[str] = []
    pgp: dict | None = None       # {type, verified, signer} for PGP-signed/encrypted mail
    smime: dict | None = None     # {type, verified, signer, decrypted} for S/MIME mail
    first_time_sender: bool = False  # inbox mail from an unknown sender (inline screener prompt)


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
        pinned=bool(m.pinned),
    )


# Typed search operators: from:  to:  subject:  has:attachment  is:unread|read|done|flagged
_TOKEN_RE = re.compile(r'(\w+):\s*(?:"([^"]*)"|(\S+))')


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
    new_days: int | None = None,   # only mail received within the last N days ("new")
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
        # Scan the whole mailbox in date-desc batches until we have `limit`
        # matches or run out — instead of silently only looking at the newest
        # 4000 messages (which made /regex/ unable to find anything older).
        ids = []
        batch, off = 2000, 0
        while len(ids) < limit:
            rows = session.exec(
                select(Message.id, Message.subject, Message.from_addr, Message.from_name,
                       Message.snippet, Message.body_text).where(Message.pending_action == "")
                .order_by(Message.date.desc()).offset(off).limit(batch)
            ).all()
            if not rows:
                break
            for row in rows:
                hay = " ".join(str(x) for x in row[1:] if x)
                if rx.search(hay):
                    ids.append(row[0])
                    if len(ids) >= limit:
                        break
            off += batch
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
    if new_days and new_days > 0:
        from datetime import timedelta
        cutoff = now - timedelta(days=new_days)
        stmt = stmt.where(Message.date != None, Message.date >= cutoff)  # noqa: E711
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

    # Free text -> substring match across every visible field. Each whitespace-
    # separated term must appear somewhere (sender, recipients, subject, snippet,
    # or cached body) — so partial words like "ertel" match "erteltrading@…".
    if free_text:
        from sqlalchemy import or_
        from sqlalchemy import text as sa_text
        for i, term in enumerate(free_text.split()):
            like = f"%{term.lower()}%"
            conds = [
                func.lower(Message.from_addr).like(like),
                func.lower(Message.from_name).like(like),
                func.lower(Message.subject).like(like),
                func.lower(Message.snippet).like(like),
                func.lower(cast(Message.to_addrs, String)).like(like),
                func.lower(cast(Message.cc_addrs, String)).like(like),
                func.lower(Message.body_text).like(like),
            ]
            # Also match via FTS — indexed from plaintext, so bodies stay
            # searchable even when the cached body column is sealed at rest.
            # The term is double-quoted (a literal FTS5 string); the probe query
            # catches any FTS error so we fall back to the LIKE clauses only.
            fts_q = '"' + term.replace('"', '""') + '"'
            pname = f"ftsq{i}"
            try:
                session.exec(sa_text(
                    f"SELECT rowid FROM message_fts WHERE message_fts MATCH :{pname} LIMIT 1"
                ).bindparams(**{pname: fts_q}))
                conds.append(Message.id.in_(sa_text(
                    f"SELECT rowid FROM message_fts WHERE message_fts MATCH :{pname}"
                ).bindparams(**{pname: fts_q}).columns(Message.id)))
            except Exception:
                session.rollback()
            stmt = stmt.where(or_(*conds))

    # Screener filter pushed into SQL so pagination is correct. Doing it in
    # Python over a capped fetch dropped results and broke page 2 (it re-sliced
    # the same capped window instead of paging through the whole mailbox).
    use_screener = screener in ("only", "exclude") and not searching
    if use_screener:
        from sqlalchemy import false, or_

        from app.sync.contacts import KNOWN_DOMAINS
        known = [e.lower() for e in session.exec(select(Contact.email)) if e]
        conds = []
        if known:
            conds.append(func.lower(Message.from_addr).in_(known))
        for dom in KNOWN_DOMAINS:
            conds.append(func.lower(Message.from_addr).like(f"%@{dom.lower()}"))
        known_expr = or_(*conds) if conds else false()
        # "exclude" hides first-time senders (show known); "only" is the Screener
        # view (show unknown / first-time senders).
        stmt = stmt.where(known_expr if screener == "exclude" else ~known_expr)

    # Newest first at the SQL level, then page in SQL.
    stmt = stmt.order_by(Message.date.desc())
    msgs = list(session.exec(stmt.offset(offset).limit(limit)))
    return [_to_out(m) for m in msgs]


@router.get("/followups", response_model=list[MessageOut])
def followups(days: int = 3, session: Session = Depends(get_session)) -> list[MessageOut]:
    """Sent messages >= `days` old with no reply yet — nudge to follow up.
    Declared before /{message_id} so the path isn't captured by the int route."""
    # Message.date is naive LOCAL time (imapclient normalises envelope dates to
    # local), so these cutoffs must be local-naive too — not UTC.
    now = datetime.now()
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


class QueueItem(BaseModel):
    id: int
    kind: str
    status: str
    attempts: int
    last_error: str
    summary: str


@router.get("/queue/items", response_model=list[QueueItem])
def queue_items(session: Session = Depends(get_session)) -> list[QueueItem]:
    """The actual queued/failed actions, with their error and a human summary —
    so the UI can show *what* failed and *why* (e.g. a send that SMTP rejected)."""
    out: list[QueueItem] = []
    for a in session.exec(select(ActionQueue).order_by(ActionQueue.created_at.desc())):
        p = a.payload or {}
        if a.kind == "send":
            to = ", ".join(p.get("to", []) or [])
            summary = f"Send “{p.get('subject') or '(no subject)'}” → {to or '?'}"
        elif a.kind in ("archive", "delete"):
            summary = f"{a.kind.title()} {len(p.get('ids', []) or [])} message(s)"
        else:
            summary = a.kind
        out.append(QueueItem(id=a.id, kind=a.kind, status=a.status, attempts=a.attempts,
                             last_error=a.last_error or "", summary=summary))
    return out


@router.delete("/queue/{item_id}")
def queue_discard(item_id: int, session: Session = Depends(get_session)) -> dict:
    a = session.get(ActionQueue, item_id)
    if a:
        session.delete(a)
        session.commit()
    return {"discarded": bool(a)}


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
                 new_days: int = 3,
                 session: Session = Depends(get_session)) -> dict:
    """Per-category preview for the Smart Inbox: count, latest activity, and top senders."""
    from datetime import timedelta
    from sqlalchemy import distinct
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    new_cutoff = now - timedelta(days=max(1, new_days))

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
    # Unread count per category (so the UI can float groups with new mail to the top).
    unread_map = dict(session.exec(
        scoped(select(Message.category, func.count()))
        .where(Message.is_seen == False)  # noqa: E712
        .group_by(Message.category)
    ).all())
    # "New" = unread AND received within the last new_days days — what the badge
    # shows and what the "N new" quick-filter opens.
    new_map = dict(session.exec(
        scoped(select(Message.category, func.count()))
        .where(Message.is_seen == False, Message.date != None, Message.date >= new_cutoff)  # noqa: E711,E712
        .group_by(Message.category)
    ).all())
    for cat, cnt, latest in cats:
        # Order senders by their MOST RECENT message (not total count) so the
        # collapsed chips match the newest-first messages shown when expanded.
        sender_rows = session.exec(
            scoped(select(Message.from_addr, func.max(Message.from_name), func.count()))
            .where(Message.category == cat).group_by(Message.from_addr)
            .order_by(func.max(Message.date).desc()).limit(8)
        ).all()
        distinct_total = session.exec(
            scoped(select(func.count(distinct(Message.from_addr)))).where(Message.category == cat)
        ).one()
        senders = [{"email": addr, "name": decode_mime_words(nm) or addr, "count": sc}
                   for addr, nm, sc in sender_rows]
        # Newest messages first — what the card shows "at a glance" so it reflects
        # what just arrived, not the most prolific (and often oldest) senders.
        recent_rows = session.exec(
            scoped(select(Message.from_addr, Message.from_name, Message.subject, Message.date))
            .where(Message.category == cat).order_by(Message.date.desc()).limit(4)
        ).all()
        recent = [{"email": addr, "name": decode_mime_words(nm) or addr,
                   "subject": decode_mime_words(subj) or "(no subject)",
                   "date": dt.isoformat() if dt else None}
                  for addr, nm, subj, dt in recent_rows]
        out[cat] = {
            "count": cnt,
            "unread": int(unread_map.get(cat, 0)),
            "new": int(new_map.get(cat, 0)),
            "latest": latest.isoformat() if latest else None,
            "senders": senders,
            "recent": recent,
            "distinct": distinct_total,   # total unique senders (frontend computes "+N")
        }
    return out


@router.get("/plus-aliases")
def plus_aliases(session: Session = Depends(get_session)) -> list[dict]:
    """Detect sub-addresses (you+tag@domain) you've received mail on, and who's
    been emailing each — so you can see which service leaked/shared your address."""
    # Map each account's (localpart, domain) so we only match your own addresses.
    acct_parts: dict[tuple[str, str], int] = {}
    for a in session.exec(select(Account)):
        email = (a.email or "").lower()
        if "@" in email:
            lp, dom = email.split("@", 1)
            acct_parts[(lp, dom)] = a.id

    groups: dict[str, dict] = {}
    rows = session.exec(select(Message.to_addrs, Message.cc_addrs, Message.from_addr,
                               Message.from_name, Message.date))
    for to_addrs, cc_addrs, from_addr, from_name, date in rows:
        for raw in [*(to_addrs or []), *(cc_addrs or [])]:
            addr = (raw or "").strip().lower()
            if "@" not in addr or "+" not in addr.split("@", 1)[0]:
                continue
            localpart, domain = addr.split("@", 1)
            base, tag = localpart.split("+", 1)
            if not tag or (base, domain) not in acct_parts:
                continue
            alias = f"{base}+{tag}@{domain}"
            g = groups.setdefault(alias, {
                "alias": alias, "tag": tag, "account_id": acct_parts[(base, domain)],
                "count": 0, "senders": {}, "last_seen": None,
            })
            g["count"] += 1
            sender = (from_addr or "").lower()
            if sender:
                s = g["senders"].setdefault(sender, {"email": sender,
                                                     "name": decode_mime_words(from_name) or sender, "count": 0})
                s["count"] += 1
            iso = date.isoformat() if date else None
            if iso and (g["last_seen"] is None or iso > g["last_seen"]):
                g["last_seen"] = iso

    out = []
    for g in groups.values():
        senders = sorted(g["senders"].values(), key=lambda s: s["count"], reverse=True)
        out.append({**g, "senders": senders[:6], "distinct_senders": len(g["senders"])})
    out.sort(key=lambda g: (g["last_seen"] or ""), reverse=True)
    return out


@router.get("/thread", response_model=list[MessageOut])
def thread(thread_id: str, session: Session = Depends(get_session)) -> list[MessageOut]:
    """All messages in a conversation (across folders), oldest first."""
    if not thread_id:
        return []
    msgs = list(session.exec(select(Message).where(Message.thread_id == thread_id)))
    msgs.sort(key=lambda m: m.date.timestamp() if m.date else 0.0)
    return [_to_out(m) for m in msgs]


# Our own read-receipt pixel (see compose._embed_receipt) — stripped when
# rendering so viewing your own Sent copy doesn't register an "open".
_RECEIPT_IMG_RE = re.compile(
    r'<img\b[^>]*\bsrc=["\']https?://[^"\']*/track/o/[^"\']+["\'][^>]*>', re.IGNORECASE)


@router.get("/{message_id}", response_model=MessageDetail)
async def get_message(message_id: int, session: Session = Depends(get_session)) -> MessageDetail:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")

    auth = {"status": msg.auth_status or "none"}
    if msg.body_fetched:
        from app.core.atrest import decrypt_field
        html, text_body = decrypt_field(msg.body_html), decrypt_field(msg.body_text)
        # Backfill (one raw fetch) for mail cached before attachments/auth existed.
        if (msg.has_attachments and not msg.attachments) or not msg.auth_status:
            account = session.get(Account, msg.account_id)
            folder = session.get(Folder, msg.folder_id)
            try:
                _h, _t, _u, _e, atts, a, att_text = await run_in_threadpool(_fetch_body, account, folder, msg.uid)
                if atts and not msg.attachments:
                    msg.attachments = atts
                msg.auth_status = a.get("status", "none")
                auth = a
                session.add(msg)
                # Re-index now that we've read attachment text (backfill for old mail).
                if att_text:
                    try:
                        index_message_fts(session, msg.id, subject=msg.subject, from_addr=msg.from_addr,
                                          from_name=msg.from_name, snippet=msg.snippet,
                                          body=(text_body[:20000] + " " + att_text))
                    except Exception:
                        pass
                session.commit()
                session.refresh(msg)
            except Exception:
                pass
    else:
        account = session.get(Account, msg.account_id)
        folder = session.get(Folder, msg.folder_id)
        try:
            html, text_body, unsub, events, atts, auth, att_text = await run_in_threadpool(_fetch_body, account, folder, msg.uid)
        except Exception as exc:
            # Don't let one malformed/huge message break the whole open — return a
            # readable placeholder instead of failing the fetch.
            log.warning("body fetch failed for message %s: %s", msg.id, exc)
            base = _to_out(msg)
            return MessageDetail(**base.model_dump(),
                                 html=f'<p style="color:#888">Couldn\'t load this message body ({type(exc).__name__}). It\'s still on the server — try again or open it in webmail.</p>',
                                 text="", cc_addrs=list(msg.cc_addrs or []), unsubscribe=msg.unsubscribe or "",
                                 attachments=[], auth={"status": msg.auth_status or "none"}, warnings=[])
        # Cache so re-opening is instant. Optionally seal the bodies at rest
        # (FTS is indexed below from the in-memory plaintext, so search still works).
        from app.core.atrest import encrypt_field
        msg.body_html, msg.body_text = encrypt_field(html), encrypt_field(text_body)
        msg.body_fetched, msg.unsubscribe = True, unsub
        msg.attachments = atts
        msg.auth_status = auth.get("status", "none")
        if events:
            from app.api.calendar import upsert_events
            try: upsert_events(session, msg.account_id, msg.id, events)
            except Exception: pass
            # A real calendar event in the body proves this is an invite/response,
            # even if the subject didn't look like one.
            methods = {(e.get("method") or "").upper() for e in events}
            if "REPLY" in methods:
                msg.category = "invitation_responses"
            elif methods & {"REQUEST", "CANCEL"}:
                msg.category = "invitations"
        session.add(msg)
        # Index the body + any extracted attachment text for full-text search.
        try:
            fts_body = (text_body[:20000] + " " + att_text) if att_text else text_body[:20000]
            index_message_fts(session, msg.id, subject=msg.subject, from_addr=msg.from_addr,
                              from_name=msg.from_name, snippet=msg.snippet, body=fts_body)
        except Exception:
            pass
        session.commit()
        session.refresh(msg)

    # Never fire our own read-receipt pixel: the Sent copy carries it, and the
    # reader loading it from this very backend would count as a recipient open.
    if html and "/track/o/" in html:
        html = _RECEIPT_IMG_RE.sub("", html)

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

    try:
        from app.sync.authcheck import spoof_warnings
        warnings = spoof_warnings(msg.from_addr, msg.from_name, html)
    except Exception:
        warnings = []

    # OpenPGP: detect signed/encrypted bodies; verify or decrypt with the user's
    # keys. A decrypted body replaces the (ciphertext) view.
    pgp_info = None
    try:
        from app.sync.pgp import analyze as _pgp_analyze
        row = session.get(Setting, 1)
        blob = dict(row.data) if row and row.data else {}
        probe = text_body or (html or "")
        if "BEGIN PGP" in probe:
            pgp_info = _pgp_analyze("", probe, blob)
            if pgp_info.get("decrypted"):
                text_body = pgp_info["decrypted"]
                html = ""  # show the decrypted plaintext, not the armored ciphertext
    except Exception:
        pgp_info = None

    # S/MIME: detect a PKCS#7 part (signed / encrypted), verify the signer or
    # decrypt with the user's imported identity. Purely additive + fully guarded:
    # analyze() returns None for anything that isn't S/MIME, so normal mail is
    # untouched; a decrypted body is shown for this response only (not persisted).
    smime_info = None
    try:
        _atts = msg.attachments or []
        _looks_smime = any(
            "pkcs7" in (a.get("content_type") or a.get("mail_content_type") or "").lower()
            or (a.get("filename") or "").lower().endswith((".p7m", ".p7s"))
            for a in _atts
        )
        if _looks_smime:
            from app.sync import smime as _sm
            _row = session.get(Setting, 1)
            _blob = dict(_row.data) if _row and _row.data else {}
            _identity = {"cert": _blob.get("smimeCert", ""), "key": _blob.get("smimeKey", "")}
            _acct = session.get(Account, msg.account_id)
            _fld = session.get(Folder, msg.folder_id)
            if _acct is not None and _fld is not None:
                from app.providers.pool import pool
                _raw = await run_in_threadpool(pool.fetch_raw, _acct, _fld.path, msg.uid)
                smime_info = _sm.analyze(_raw, _identity)
                if smime_info and smime_info.get("decrypted"):
                    html, text_body = smime_info["decrypted"], ""
    except Exception:
        smime_info = None

    # First-time sender: inbox mail from someone not in Contacts and not on a
    # known domain — drives the inline "accept the sender?" prompt in the reader
    # (same definition as the Screener list filter, so they stay in sync).
    first_time = False
    try:
        from app.sync.contacts import KNOWN_DOMAINS, domain_of
        fld = session.get(Folder, msg.folder_id)
        addr = (msg.from_addr or "").lower()
        if fld is not None and fld.role == FolderRole.inbox and addr:
            known = session.exec(
                select(Contact.id).where(func.lower(Contact.email) == addr)
            ).first() is not None
            first_time = not known and domain_of(addr) not in KNOWN_DOMAINS
    except Exception:
        first_time = False

    base = _to_out(msg)
    return MessageDetail(**base.model_dump(), html=html, text=text_body,
                         cc_addrs=list(msg.cc_addrs or []), unsubscribe=msg.unsubscribe,
                         attachments=list(msg.attachments or []), auth=auth, warnings=warnings,
                         pgp=pgp_info, smime=smime_info, first_time_sender=first_time)


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


def _fetch_body(account: Account, folder: Folder, uid: int) -> tuple[str, str, str, list, list, dict, str]:
    """Fetch + parse raw into (html, text, list_unsubscribe, ics_events, attachments, auth, attachment_text)."""
    import mailparser

    from app.providers.pool import pool
    from app.sync.authcheck import check_auth
    from app.sync.ics import extract_ics

    raw = pool.fetch_raw(account, folder.path, uid)
    if not raw:
        return "", "", "", [], [], {"status": "none"}, ""
    parsed = mailparser.parse_from_bytes(raw)
    html = "\n".join(parsed.text_html) if parsed.text_html else ""
    text_body = "\n".join(parsed.text_plain) if parsed.text_plain else ""
    # Inline images are referenced as `cid:...`, which a webview can't resolve —
    # rewrite them to data: URIs so logos/snapshots render inline.
    try:
        html = _embed_inline_images(html, parsed)
    except Exception:
        pass
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
    # Pull searchable text out of supported attachments (docs, code, text) so a
    # full-text search can match words that only appear inside a file.
    att_text = _extract_attachment_text(parsed)
    try:
        from_addr = parsed.from_[0][1] if parsed.from_ else ""
        auth = check_auth(raw, from_addr)
    except Exception:
        auth = {"status": "none"}
    return html, text_body, unsub, events, atts, auth, att_text


def _embed_inline_images(html: str, parsed) -> str:
    """Rewrite `src="cid:..."` references to data: URIs using the message's inline
    image parts, so they render in the sandboxed reader iframe (which can't resolve
    cid:). Large images (>6 MB) are left as-is to avoid bloating the cached body."""
    import base64
    import re

    if not html or "cid:" not in html.lower():
        return html
    cid_map: dict[str, str] = {}
    for a in (parsed.attachments or []):
        cid = (a.get("content-id") or a.get("content_id") or "").strip().strip("<>").strip()
        ctype = (a.get("mail_content_type") or "").lower()
        if not cid or not ctype.startswith("image/"):
            continue
        try:
            payload = a.get("payload") or ""
            cte = (a.get("content_transfer_encoding") or "").lower()
            data = base64.b64decode(payload) if cte == "base64" else (
                payload.encode("utf-8", "ignore") if isinstance(payload, str) else bytes(payload))
        except Exception:
            continue
        if not data or len(data) > 6_000_000:
            continue
        cid_map[cid.lower()] = f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"
    if not cid_map:
        return html

    def repl(m: "re.Match") -> str:
        q, ref = m.group(1), m.group(2).strip().lower()
        uri = cid_map.get(ref) or cid_map.get(ref.split("@")[0])
        return f"src={q}{uri}{q}" if uri else m.group(0)

    return re.sub(r"""src=(["'])\s*cid:([^"']+)\1""", repl, html, flags=re.IGNORECASE)


def _extract_attachment_text(parsed) -> str:
    import base64

    from app.sync.extract import extract_attachment_text
    chunks: list[str] = []
    for a in (parsed.attachments or []):
        try:
            payload = a.get("payload") or ""
            cte = (a.get("content_transfer_encoding") or "").lower()
            data = base64.b64decode(payload) if cte == "base64" else (
                payload.encode("utf-8", "ignore") if isinstance(payload, str) else bytes(payload))
            txt = extract_attachment_text(a.get("filename") or "",
                                          a.get("mail_content_type") or "", data)
            if txt:
                chunks.append(txt)
        except Exception:
            continue
        if sum(len(c) for c in chunks) > 60_000:
            break
    return " ".join(chunks)[:60_000]


@router.get("/{message_id}/attachments/{index}")
async def download_attachment(message_id: int, index: int,
                              session: Session = Depends(get_session)):
    from fastapi import Response
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    account = session.get(Account, msg.account_id)
    folder = session.get(Folder, msg.folder_id)
    try:
        data, filename, ctype = await run_in_threadpool(_attachment_bytes, account, folder, msg.uid, index)
    except Exception as exc:
        detail = str(exc)
        log.warning("attachment fetch failed for message %s/%s: %s", message_id, index, detail)
        if "password" in detail.lower() or "authenticationfailed" in detail.lower() or "login" in detail.lower():
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                f"Can't reach {account.email if account else 'this account'} — it has no saved/valid "
                                "password. Re-add the account in Settings → Accounts.") from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Couldn't download the attachment from the server ({type(exc).__name__}).") from exc
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
    from urllib.parse import quote
    return Response(content=data, media_type=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


# Internal / infrastructure headers stripped by the "Safe Export" sanitizer so an
# exported/forwarded .eml doesn't leak routing, IPs, or provider internals.
_EXPORT_DROP_HEADERS = {
    "received", "x-originating-ip", "x-received", "return-path", "delivered-to",
    "authentication-results", "arc-authentication-results", "arc-message-signature",
    "arc-seal", "x-google-smtp-source", "x-gm-message-state", "x-spam-status",
    "x-spam-score", "x-spam-level", "x-mailer", "user-agent",
}
_EXPORT_DROP_PREFIXES = ("x-ms-exchange", "x-microsoft-", "x-forefront", "x-google-", "x-gm-")
_PIXEL_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_PIXEL_HINT_RE = re.compile(r"(pixel|beacon|/open\b|/wf/|/e/o/|/track|1x1|spacer)", re.IGNORECASE)
_PIXEL_TINY_RE = re.compile(r"(?:width|height)\s*[:=]\s*[\"']?\s*[0-2](?:px)?\b", re.IGNORECASE)


def _strip_pixels_html(html: str) -> str:
    def repl(m: re.Match) -> str:
        tag = m.group(0)
        return "" if (_PIXEL_TINY_RE.search(tag) or _PIXEL_HINT_RE.search(tag)) else tag
    return _PIXEL_IMG_RE.sub(repl, html or "")


def _sanitize_eml(raw: bytes) -> bytes:
    """Strip internal routing headers + hidden tracking pixels from a raw message."""
    import email
    from email import policy
    msg = email.message_from_bytes(raw, policy=policy.default)
    for name in list(msg.keys()):
        low = name.lower()
        if low in _EXPORT_DROP_HEADERS or low.startswith(_EXPORT_DROP_PREFIXES):
            del msg[name]
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            try:
                html = part.get_content()
                cleaned = _strip_pixels_html(html)
                if cleaned != html:
                    part.set_content(cleaned, subtype="html")
            except Exception:
                pass
    return msg.as_bytes(policy=policy.SMTP)


def _export_eml(account: Account, folder: Folder, uid: int, sanitize: bool) -> bytes:
    from app.providers.pool import pool
    raw = pool.fetch_raw(account, folder.path, uid)
    if not raw:
        return b""
    if sanitize:
        try:
            raw = _sanitize_eml(raw)
        except Exception:
            pass
    return raw


@router.get("/{message_id}/export")
async def export_message(message_id: int, sanitize: bool = True,
                         session: Session = Depends(get_session)):
    """Download a message as a .eml. With sanitize=true (Safe Export), internal
    routing headers (Received / X-Originating-IP / …) and hidden tracking pixels
    are stripped first."""
    from fastapi import Response
    from urllib.parse import quote
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    account = session.get(Account, msg.account_id)
    folder = session.get(Folder, msg.folder_id)
    if account is None or folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    try:
        raw = await run_in_threadpool(_export_eml, account, folder, msg.uid, sanitize)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Couldn't fetch the message from the server ({type(exc).__name__}).") from exc
    if not raw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not available")
    name = (re.sub(r"[^\w.-]+", "_", msg.subject or "message")[:60] or "message") + ".eml"
    return Response(content=raw, media_type="message/rfc822",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


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


_bg_tasks: set = set()


def _push_done_keyword(account: Account, folder_path: str, uid: int, done: bool) -> None:
    """Mirror the local 'done' to the server as a custom IMAP keyword (best-effort)
    so it syncs to other devices. Failures are swallowed — local state still holds."""
    from app.providers.base import DONE_KEYWORD
    from app.providers.pool import pool
    try:
        pool.set_keyword(account, folder_path, uid, DONE_KEYWORD, done)
    except Exception:
        pass


def _push_done_keywords_bulk(targets: list[tuple], done: bool) -> None:
    """Mirror many 'done' toggles to their servers (grouped by account+folder)."""
    from collections import defaultdict

    from app.core.db import get_engine
    from app.providers.base import DONE_KEYWORD
    from app.providers.pool import pool

    by_folder: dict = defaultdict(list)
    for acct_id, folder_id, uid in targets:
        by_folder[(acct_id, folder_id)].append(uid)
    with Session(get_engine()) as s:
        for (acct_id, folder_id), uids in by_folder.items():
            account = s.get(Account, acct_id)
            folder = s.get(Folder, folder_id)
            if not account or not folder:
                continue
            for uid in uids:
                try:
                    pool.set_keyword(account, folder.path, uid, DONE_KEYWORD, done)
                except Exception:
                    continue


def _push_seen_flags_bulk(targets: list[tuple], seen: bool) -> None:
    """Mirror read/unread to the servers' \\Seen flag (grouped by account+folder),
    so read state syncs to other devices. Best-effort, like the done keyword."""
    from collections import defaultdict

    from app.core.db import get_engine
    from app.providers.pool import pool

    by_folder: dict = defaultdict(list)
    for acct_id, folder_id, uid in targets:
        by_folder[(acct_id, folder_id)].append(uid)
    with Session(get_engine()) as s:
        for (acct_id, folder_id), uids in by_folder.items():
            account = s.get(Account, acct_id)
            folder = s.get(Folder, folder_id)
            if not account or not folder:
                continue
            for uid in uids:
                try:
                    pool.set_keyword(account, folder.path, uid, "\\Seen", seen)
                except Exception:
                    continue


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
async def set_done(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    """The hero action: mark a message done so it leaves the inbox view. Also
    mirrored to the server as an IMAP keyword so 'done' syncs across devices."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.is_done = body.value
    _persist_state(session, msg, done=body.value)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    # Mirror the done state to the server keyword in the BACKGROUND — don't make
    # the user wait on an IMAP STORE round-trip (that was the perceptible lag on
    # every "e"). Fire-and-forget; a failed push just isn't mirrored cross-device.
    if msg.account_id and msg.folder_id and msg.uid:
        import asyncio
        task = asyncio.create_task(run_in_threadpool(
            _push_done_keywords_bulk, [(msg.account_id, msg.folder_id, msg.uid)], body.value))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
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


@router.post("/{message_id}/pin", response_model=MessageOut)
def set_pin(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.pinned = body.value
    # Persist durably (survives re-sync) keyed by Message-ID.
    if msg.message_id:
        state = session.exec(
            select(MessageState).where(MessageState.account_id == msg.account_id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state is None:
            state = MessageState(account_id=msg.account_id, message_id=msg.message_id)
            session.add(state)
        state.is_pinned = body.value
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
            elif a == "snooze": m.snooze_until = until; m.snooze_presence = False; _persist_snooze(session, m, until)
            session.add(m)
        # Collect (account, folder, uid) for done/undone to mirror as IMAP keywords.
        done_targets = None
        if a in ("done", "undone"):
            done_targets = [(m.account_id, m.folder_id, m.uid) for m in msgs if m.uid and m.message_id]
        seen_targets = None
        if a in ("seen", "unseen"):
            seen_targets = [(m.account_id, m.folder_id, m.uid) for m in msgs if m.uid]
        session.commit()
        if done_targets:
            import asyncio
            task = asyncio.create_task(run_in_threadpool(_push_done_keywords_bulk, done_targets, a == "done"))
            _bg_tasks.add(task)
            task.add_done_callback(_bg_tasks.discard)
        if seen_targets:
            import asyncio
            task = asyncio.create_task(run_in_threadpool(_push_seen_flags_bulk, seen_targets, a == "seen"))
            _bg_tasks.add(task)
            task.add_done_callback(_bg_tasks.discard)
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
    # A dated snooze replaces any "until I'm back" snooze — otherwise the
    # presence watcher would clear it the moment the user returns.
    state.snooze_presence = False


def _flush_move(ids: list[int], action: str) -> None:
    """Move messages to Archive/Trash on the server. Raises on connection failure
    (so the queue retries); commits per-message so partial progress is kept."""
    from collections import defaultdict

    from sqlalchemy import delete as sa_delete

    from app.core.db import get_engine
    from app.models import CalendarEvent
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
                    # Extracted events reference the message (FK enforced) — they
                    # must go first or the local delete fails forever.
                    session.exec(sa_delete(CalendarEvent).where(CalendarEvent.message_id == m.id))
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
                        # Give up: un-hide the affected messages so they don't
                        # vanish forever (they were never actually moved/deleted
                        # on the server). They reappear in the normal views.
                        if kind in ("archive", "delete"):
                            ids = payload.get("ids", [])
                            if ids:
                                for m in session.exec(select(Message).where(Message.id.in_(ids))):
                                    m.pending_action = ""
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
    n = 0
    parts: set[str] = set()
    for m in session.exec(select(Message).where(Message.thread_id == key)):
        m.is_done = True
        _persist_state(session, m, done=True)
        if m.from_addr:
            parts.add(m.from_addr.strip().lower())
        n += 1
    # Scope the mute to the senders in this conversation so a shared subject line
    # doesn't silently auto-archive unrelated mail from strangers (see threading).
    participants = ",".join(sorted(parts))
    existing = session.exec(select(MutedThread).where(MutedThread.thread_key == key)).first()
    if existing:
        existing.participants = participants
    else:
        session.add(MutedThread(thread_key=key, participants=participants))
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
    rows = session.exec(select(Message.id, Message.account_id, Message.folder_id,
                               Message.subject, Message.uid, Message.from_addr,
                               Message.to_addrs, Message.thread_id)).all()
    n = 0
    for mid, acct, fid, subj, uid, from_addr, to_addrs, tid in rows:
        new = thread_key(acct, subj or "", uid=uid or 0, folder_id=fid or 0,
                         participants=[from_addr or "", *(to_addrs or [])])
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
async def set_seen(message_id: int, body: BoolValue, session: Session = Depends(get_session)) -> MessageOut:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    msg.is_seen = body.value
    session.add(msg)
    session.commit()
    session.refresh(msg)
    # Mirror to the server's \Seen flag in the background — same fire-and-forget
    # pattern as the done keyword, so other devices see the read state too.
    if msg.account_id and msg.folder_id and msg.uid:
        import asyncio
        task = asyncio.create_task(run_in_threadpool(
            _push_seen_flags_bulk, [(msg.account_id, msg.folder_id, msg.uid)], body.value))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    return _to_out(msg)
