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
from app.models import Account, ActionQueue, Folder, FolderRole, ScheduledSend, Signature
from app.providers.base import OutgoingMessage
from app.sync.compose import inject_signature

router = APIRouter(prefix="/compose", tags=["compose"], dependencies=[Depends(verify_token)])


class Attachment(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    data_b64: str


class SendIn(BaseModel):
    account_id: int
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


def _deliver_blocking(body_dict: dict) -> None:
    """Build, send via SMTP, and append to Sent. Blocking; used everywhere."""
    from app.core.db import get_engine
    from app.sync.engine import build_provider

    body = SendIn(**body_dict)
    with Session(get_engine()) as session:
        account = session.get(Account, body.account_id)
        if account is None:
            raise RuntimeError("account not found")
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
        message = OutgoingMessage(
            from_addr=account.email, to=body.to, cc=body.cc, bcc=body.bcc,
            subject=body.subject, html=html, in_reply_to=body.in_reply_to,
            references=body.references, inline_images=inline_images,
            attachments=[{"filename": a.filename, "content_type": a.content_type,
                          "data": base64.b64decode(a.data_b64)} for a in body.attachments],
        )
        sent_path = session.exec(
            select(Folder.path).where(Folder.account_id == body.account_id,
                                      Folder.role == FolderRole.sent)
        ).first()
        provider = build_provider(account)
    try:
        raw = provider.send(message)
        if sent_path:
            try:
                provider.append_to_folder(sent_path, raw, seen=True)
            except Exception:
                pass
    finally:
        provider.close()


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
                s.status = "sent" if ok else "failed"
                session.commit()
        sent += 1 if ok else 0
    return sent
