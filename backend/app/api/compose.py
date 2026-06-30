"""Compose and send mail, with signature embedding and Send Later scheduling."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_unlocked_store, verify_token
from app.core.db import get_session
from app.models import Account, ActionQueue, Folder, FolderRole, Provider, ScheduledSend, Signature
from app.providers.base import OutgoingMessage
from app.sync.compose import inject_signature

router = APIRouter(prefix="/compose", tags=["compose"], dependencies=[Depends(verify_token)])


def _alias_addr(s: str) -> str:
    """Bare email from a 'Name <email>' or plain 'email' identity string."""
    from email.utils import parseaddr
    return parseaddr(s)[1] or s


class Attachment(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    data_b64: str


class SendIn(BaseModel):
    account_id: int
    from_addr: str = ""        # send-as identity (account email or one of its aliases)
    to: list[str]
    cc: list[str] = []
    bcc: list[str] = []
    subject: str = ""
    html: str = ""
    in_reply_to: str = ""
    references: list[str] = []
    signature_id: int | None = None
    use_default_signature: bool = True
    attachments: list[Attachment] = []
    send_at: datetime | None = None   # schedule for later (Send Later)
    pgp_sign: bool = False
    pgp_encrypt: bool = False
    request_receipt: bool = False   # embed a read-receipt tracking pixel
    calendar_ics: str = ""          # iMIP: text/calendar payload (METHOD below)
    calendar_method: str = "REQUEST"


@router.post("/send", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_unlocked_store)])
async def send(body: SendIn, request: Request, session: Session = Depends(get_session)) -> dict:
    if session.get(Account, body.account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    if body.send_at is not None:
        when = body.send_at
        if when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        session.add(ScheduledSend(
            account_id=body.account_id, payload=body.model_dump(mode="json"),
            to_summary=", ".join(body.to), subject=body.subject, send_at=when,
        ))
        session.commit()
        return {"scheduled": True, "send_at": when.isoformat()}

    payload = body.model_dump(mode="json")
    try:
        await run_in_threadpool(_deliver_blocking, payload)
    except Exception:
        # Offline / transient failure — queue it and let the worker retry.
        session.add(ActionQueue(kind="send", payload=payload))
        session.commit()
        request.app.state.sync.request_sync()
        return {"queued": True}
    request.app.state.sync.request_sync()
    return {"sent": True}


class DraftIn(SendIn):
    replace_uid: int | None = None   # delete this previously-saved draft first


@router.post("/draft", dependencies=[Depends(require_unlocked_store)])
async def save_draft(body: DraftIn, session: Session = Depends(get_session)) -> dict:
    """Save the message to the account's IMAP Drafts folder (cross-device drafts)."""
    if session.get(Account, body.account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    payload = body.model_dump(mode="json")
    payload.pop("replace_uid", None)
    payload.pop("send_at", None)
    try:
        result = await run_in_threadpool(_save_draft_blocking, payload, body.replace_uid)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return {"saved": True, **result}


# --- scheduled sends --------------------------------------------------------
class ScheduledOut(BaseModel):
    id: int
    subject: str
    to_summary: str
    send_at: datetime
    status: str


@router.get("/scheduled", response_model=list[ScheduledOut])
def list_scheduled(session: Session = Depends(get_session)) -> list[ScheduledOut]:
    rows = session.exec(
        select(ScheduledSend).where(ScheduledSend.status == "pending").order_by(ScheduledSend.send_at)
    )
    return [ScheduledOut(id=s.id, subject=s.subject, to_summary=s.to_summary,
                         send_at=s.send_at, status=s.status) for s in rows]


@router.delete("/scheduled/{sched_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_scheduled(sched_id: int, session: Session = Depends(get_session)) -> None:
    s = session.get(ScheduledSend, sched_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    session.delete(s)
    session.commit()


# --- delivery (shared by immediate send + the scheduled worker) -------------
def _resolve_signature(session: Session, body: SendIn) -> Signature | None:
    if body.signature_id is not None:
        return session.get(Signature, body.signature_id)
    if not body.use_default_signature:
        return None
    return session.exec(
        select(Signature).where(
            ((Signature.account_id == body.account_id) | (Signature.account_id == None)),  # noqa: E711
            Signature.is_default == True,  # noqa: E712
        ).order_by(Signature.account_id.desc())
    ).first()


def _build_message(session: Session, account: Account, body: SendIn) -> OutgoingMessage:
    """Assemble the outgoing MIME message (signature + inline images + send-as)."""
    signature = _resolve_signature(session, body)
    html = body.html
    inline_images: list[dict] = []
    if signature:
        html, inline_images = inject_signature(html, signature.html, signature.inline_images)
    # Convert any data:base64 images in the body (e.g. an in-body signature or
    # pasted image) into proper inline CID attachments so recipients see them.
    from app.sync.compose import extract_data_images
    html, body_imgs = extract_data_images(html)
    inline_images = inline_images + body_imgs
    # Use the chosen send-as identity, but only if it's a recognized alias of
    # this account (or the account's own address) — never an arbitrary From.
    from_addr = account.email
    if body.from_addr:
        valid = {account.email.lower(), *( _alias_addr(a).lower() for a in (account.aliases or []) )}
        if _alias_addr(body.from_addr).lower() in valid or body.from_addr.lower() in valid:
            from_addr = body.from_addr
    message = OutgoingMessage(
        from_addr=from_addr, to=body.to, cc=body.cc, bcc=body.bcc,
        subject=body.subject, html=html, in_reply_to=body.in_reply_to,
        references=body.references, inline_images=inline_images,
        attachments=[{"filename": a.filename, "content_type": a.content_type,
                      "data": base64.b64decode(a.data_b64)} for a in body.attachments],
        calendar_ics=getattr(body, "calendar_ics", "") or "",
        calendar_method=getattr(body, "calendar_method", "REQUEST") or "REQUEST",
    )
    # OpenPGP: sign and/or encrypt the body inline (ASCII-armored). Encryption
    # needs a stored public key for every recipient.
    if getattr(body, "pgp_sign", False) or getattr(body, "pgp_encrypt", False):
        from app.sync import pgp as pgpmod
        from app.sync.compose import _html_to_text
        from app.models import Setting
        row = session.get(Setting, 1)
        blob = dict(row.data) if row and row.data else {}
        recipients = [*body.to, *body.cc, *body.bcc]
        recip_keys = pgpmod.pubkeys_for(recipients, blob) if body.pgp_encrypt else []
        if body.pgp_encrypt and len(recip_keys) < len({r.lower() for r in recipients if r}):
            raise RuntimeError("Missing a PGP public key for one or more recipients — import it first.")
        armored = pgpmod.sign_and_encrypt(
            _html_to_text(html), blob, recip_keys,
            do_sign=body.pgp_sign, do_encrypt=body.pgp_encrypt)
        if armored:
            message.text = armored
            message.html = ""
            message.inline_images = []
    return message


def _embed_receipt(session: Session, message: OutgoingMessage, body: SendIn) -> None:
    """Append a read-receipt pixel to the HTML body and record the tracker."""
    import secrets

    from app.core.config import get_settings
    from app.models import OpenTrack, Setting
    row = session.get(Setting, 1)
    blob = dict(row.data) if row and row.data else {}
    cfg = get_settings()
    base = (blob.get("trackBaseUrl") or f"http://{cfg.host}:{cfg.port}").rstrip("/")
    token = secrets.token_urlsafe(16)
    message.html += f'<img src="{base}/track/o/{token}.png" width="1" height="1" alt="" style="display:none">'
    session.add(OpenTrack(token=token, subject=body.subject,
                          recipient=", ".join(body.to) or ""))
    session.commit()


def _deliver_blocking(body_dict: dict) -> None:
    """Build, send via SMTP, and append to Sent. Blocking; used everywhere."""
    from app.core.db import get_engine
    from app.sync.engine import build_provider

    body = SendIn(**body_dict)
    with Session(get_engine()) as session:
        account = session.get(Account, body.account_id)
        if account is None:
            raise RuntimeError("account not found")
        message = _build_message(session, account, body)
        # Read-receipt: embed a tracking pixel (only into an HTML body — skip if
        # the message was PGP-encrypted/signed into a plaintext armored block).
        if body.request_receipt and message.html:
            _embed_receipt(session, message, body)
        sent_path = session.exec(
            select(Folder.path).where(Folder.account_id == body.account_id,
                                      Folder.role == FolderRole.sent)
        ).first()
        provider = build_provider(account)
    try:
        try:
            raw = provider.send(message)
        except OSError as exc:   # incl. socket.gaierror "getaddrinfo failed"
            # unreachable SMTP host — the stored server is
            # stale or wrong (common for vanity domains, e.g. a Seznam-hosted
            # rapl-group.eu). Re-detect from MX, persist, and retry once.
            raw = _resend_with_detected_host(body.account_id, message, exc)
        if sent_path:
            try:
                provider.append_to_folder(sent_path, raw, seen=True)
            except Exception:
                pass
    finally:
        provider.close()


def _resend_with_detected_host(account_id: int, message, original_exc):
    """Auto-correct a wrong/unreachable SMTP host via autodiscover, save it, retry."""
    from app.core.db import get_engine
    from app.providers.autodiscover import discover
    from app.sync.engine import build_provider

    with Session(get_engine()) as session:
        account = session.get(Account, account_id)
        if account is None or account.provider != Provider.imap:
            raise original_exc
        d = discover(account.email)
        if not d.smtp_host or (d.smtp_host == account.smtp_host and d.imap_host == account.imap_host):
            raise original_exc   # nothing better to try
        account.imap_host = d.imap_host or account.imap_host
        account.imap_port = d.imap_port or account.imap_port
        account.smtp_host = d.smtp_host
        account.smtp_port = d.smtp_port or account.smtp_port
        session.add(account)
        session.commit()
        session.refresh(account)
        fixed = build_provider(account)
    try:
        return fixed.send(message)
    finally:
        fixed.close()


def _save_draft_blocking(body_dict: dict, replace_uid: int | None) -> dict:
    """Build the MIME and APPEND it to the account's IMAP Drafts folder.
    Optionally expunges a previously-saved draft (replace_uid) so updating a
    draft doesn't pile up copies. Returns {folder, uid}."""
    from app.core.db import get_engine
    from app.sync.compose import build_mime
    from app.sync.engine import build_provider

    body = SendIn(**body_dict)
    with Session(get_engine()) as session:
        account = session.get(Account, body.account_id)
        if account is None:
            raise RuntimeError("account not found")
        message = _build_message(session, account, body)
        drafts_path = session.exec(
            select(Folder.path).where(Folder.account_id == body.account_id,
                                      Folder.role == FolderRole.drafts)
        ).first()
        provider = build_provider(account)
    if not drafts_path:
        provider.close()
        raise RuntimeError("no Drafts folder for this account")
    raw = build_mime(message).as_bytes()
    try:
        client = provider._imap()
        if replace_uid:
            try:
                client.select_folder(drafts_path)
                client.delete_messages([replace_uid])
                client.expunge()
            except Exception:
                pass
        uid = None
        try:
            resp = client.append(drafts_path, raw, flags=[b"\\Draft", b"\\Seen"])
            # imapclient returns the server's APPENDUID line when supported.
            import re
            m = re.search(rb"APPENDUID\s+\d+\s+(\d+)", resp or b"")
            if m:
                uid = int(m.group(1))
        except Exception as exc:
            raise RuntimeError(f"couldn't save draft: {exc}")
    finally:
        provider.close()
    return {"folder": drafts_path, "uid": uid}


def process_due_scheduled() -> int:
    """Deliver any scheduled sends whose time has arrived. Called by the sync loop."""
    from app.core.db import get_engine

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(get_engine()) as session:
        due = session.exec(
            select(ScheduledSend).where(ScheduledSend.status == "pending",
                                        ScheduledSend.send_at <= now)
        ).all()
        items = [(s.id, dict(s.payload)) for s in due]

    sent = 0
    for sid, payload in items:
        ok = True
        try:
            _deliver_blocking(payload)
        except Exception:
            ok = False
        with Session(get_engine()) as session:
            s = session.get(ScheduledSend, sid)
            if s:
                if ok:
                    s.status = "sent"
                else:
                    # Don't silently drop it: hand off to the resilient send
                    # queue (8 retries with backoff) just like an immediate send
                    # that couldn't reach the server. The message is no longer
                    # lost on a momentary blip at the scheduled minute.
                    s.status = "failed"
                    session.add(ActionQueue(kind="send", payload=payload))
                session.commit()
        sent += 1 if ok else 0
    return sent
