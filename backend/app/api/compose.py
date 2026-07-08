"""Compose and send mail, with signature embedding and Send Later scheduling."""

from __future__ import annotations

import base64
import logging
import smtplib
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_serializer
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_unlocked_store, verify_token
from app.core.db import get_session
from app.models import Account, ActionQueue, Folder, FolderRole, Provider, ScheduledSend, Signature
from app.providers.base import OutgoingMessage
from app.sync.compose import inject_signature

router = APIRouter(prefix="/compose", tags=["compose"], dependencies=[Depends(verify_token)])
log = logging.getLogger("raplmail.send")


class PermanentSendError(RuntimeError):
    """A send that won't succeed on retry (e.g. missing Graph Mail.Send consent),
    so we surface it to the user instead of silently queuing it forever."""


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
    smime_sign: bool = False        # S/MIME detached signature (needs your cert)
    smime_encrypt: bool = False     # S/MIME encrypt to recipients' certs
    request_receipt: bool = False   # embed a read-receipt tracking pixel
    calendar_ics: str = ""          # iMIP: text/calendar payload (METHOD below)
    calendar_method: str = "REQUEST"


@router.post("/send", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_unlocked_store)])
async def send(body: SendIn, request: Request, session: Session = Depends(get_session)) -> dict:
    if session.get(Account, body.account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    # Read-receipt: embed the pixel ONCE, here - retries/scheduled sends rebuild
    # the message from this payload, so embedding at delivery time minted a new
    # tracker row per attempt. (PGP turns the body into armored text; skip.)
    if body.request_receipt and not body.pgp_sign and not body.pgp_encrypt:
        body.html = _embed_receipt(session, body)

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
    log.info("send: account=%s to=%s subject=%r", body.account_id, ", ".join(body.to), body.subject)
    t0 = time.monotonic()
    try:
        await run_in_threadpool(_deliver_blocking, payload)
    except PermanentSendError as exc:
        # Won't succeed on retry (e.g. missing Graph Mail.Send consent) - tell the
        # user now instead of silently queuing a doomed send.
        log.error("send rejected (permanent): %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except Exception as exc:
        # Offline / transient failure - queue it and let the worker retry.
        log.warning("send failed after %.1fs (queued for retry): %s", time.monotonic() - t0, exc)
        session.add(ActionQueue(kind="send", payload=payload))
        session.commit()
        request.app.state.sync.request_sync()
        return {"queued": True}
    log.info("send: delivered in %.1fs", time.monotonic() - t0)
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

    # send_at is stored UTC but SQLite drops the tzinfo, so stamp the offset -
    # otherwise the frontend's `new Date(...)` reads the UTC wall-clock as local.
    @field_serializer("send_at")
    def _as_utc(self, v: datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


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
    # this account (or the account's own address) - never an arbitrary From.
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
            raise RuntimeError("Missing a PGP public key for one or more recipients - import it first.")
        armored = pgpmod.sign_and_encrypt(
            _html_to_text(html), blob, recip_keys,
            do_sign=body.pgp_sign, do_encrypt=body.pgp_encrypt)
        if armored:
            message.text = armored
            message.html = ""
            message.inline_images = []
    # S/MIME: attach the identity + recipient certs; the actual sign/encrypt of the
    # fully-assembled MIME happens in build_mime (which has the final body).
    if getattr(body, "smime_sign", False) or getattr(body, "smime_encrypt", False):
        from email.utils import parseaddr

        from app.models import Setting
        from app.sync import smime as smod
        row = session.get(Setting, 1)
        blob = dict(row.data) if row and row.data else {}
        if body.smime_sign and not (blob.get("smimeCert") and blob.get("smimeKey")):
            raise RuntimeError("No S/MIME certificate imported - add one in Settings → S/MIME.")
        recip_certs: list[str] = []
        if body.smime_encrypt:
            recipients = {parseaddr(r)[1].lower() for r in [*body.to, *body.cc, *body.bcc] if r}
            recipients.discard("")
            by_email: dict[str, str] = {}
            for pem in (blob.get("smimeCerts") or []):
                try:
                    info = smod.cert_info(pem)
                    if info.get("email"):
                        by_email[info["email"].lower()] = pem
                except Exception:
                    continue
            recip_certs = [by_email[r] for r in recipients if r in by_email]
            if len(recip_certs) < len(recipients):
                raise RuntimeError("Missing an S/MIME certificate for one or more recipients - "
                                   "import it in Settings → S/MIME.")
        message.smime_sign = bool(body.smime_sign)
        message.smime_encrypt = bool(body.smime_encrypt)
        message.smime_cert = blob.get("smimeCert", "")
        message.smime_key = blob.get("smimeKey", "")
        message.smime_recip_certs = recip_certs
    return message


def _embed_receipt(session: Session, body: SendIn) -> str:
    """Record a tracker and return the compose HTML with the read-receipt pixel
    appended. Called once per message (in /send), NOT per delivery attempt."""
    import secrets

    from app.core.config import get_settings
    from app.models import OpenTrack, Setting
    row = session.get(Setting, 1)
    blob = dict(row.data) if row and row.data else {}
    cfg = get_settings()
    base = (blob.get("trackBaseUrl") or f"http://{cfg.host}:{cfg.port}").rstrip("/")
    token = secrets.token_urlsafe(16)
    session.add(OpenTrack(token=token, subject=body.subject,
                          recipient=", ".join(body.to) or ""))
    session.commit()
    return body.html + f'<img src="{base}/track/o/{token}.png" width="1" height="1" alt="" style="display:none">'


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
        sent_path = session.exec(
            select(Folder.path).where(Folder.account_id == body.account_id,
                                      Folder.role == FolderRole.sent)
        ).first()
        is_m365 = account.provider == Provider.m365
        secret_key = account.secret_key
        provider = build_provider(account)
    try:
        raw, saved_to_sent = _transport_send(provider, message, is_m365, secret_key, body.account_id)
        if sent_path and not saved_to_sent:
            try:
                provider.append_to_folder(sent_path, raw, seen=True)
            except Exception:
                pass
    finally:
        provider.close()


def _transport_send(provider, message, is_m365: bool, secret_key: str, account_id: int):
    """Send the message via the best transport. Returns (raw_mime, saved_to_sent),
    where saved_to_sent is True when the transport (Graph) already filed a copy in
    Sent so the caller shouldn't append it again."""
    if is_m365:
        # Graph-first for Microsoft 365: works even when the tenant has SMTP AUTH
        # disabled (the common default) and avoids a guaranteed ~13s SMTP failure.
        # Fall back to SMTP only if Graph is unavailable - some tenants allow SMTP
        # but haven't granted Graph Mail.Send.
        try:
            return _send_via_graph(secret_key, message), True
        except PermanentSendError as graph_err:
            try:
                return provider.send(message), False
            except smtplib.SMTPResponseException as smtp_err:
                if _is_smtp_auth_disabled(smtp_err):
                    raise graph_err from smtp_err   # both blocked → Graph guidance
                raise
    # NB: smtplib.SMTPException subclasses OSError, so the SMTP-protocol handler
    # MUST come before the OSError (socket-level) handler or it never runs.
    try:
        return provider.send(message), False
    except smtplib.SMTPResponseException as exc:
        # A Microsoft mailbox connected as a plain IMAP/password account hits the
        # tenant SMTP-disabled 535 but can't use Graph (no OAuth token).
        if _is_smtp_auth_disabled(exc):
            raise PermanentSendError(
                "This Microsoft 365 mailbox has SMTP sending disabled by the tenant, "
                "and it's connected here with a password. Re-add it with 'Sign in "
                "with Microsoft' so RaplMail can send via Graph - or ask your admin "
                "to re-enable SMTP AUTH."
            ) from exc
        raise
    except smtplib.SMTPException:
        # Other SMTP-protocol failures (recipient refused, disconnect, …) also
        # subclass OSError - they must not trigger the host re-detection below.
        raise
    except OSError as exc:   # socket.gaierror "getaddrinfo failed", timeouts, etc.
        # Unreachable SMTP host - the stored server is stale/wrong (common for
        # vanity domains, e.g. a Seznam-hosted rapl-group.eu). Re-detect + retry.
        return _resend_with_detected_host(account_id, message, exc), False


def _is_smtp_auth_disabled(exc: smtplib.SMTPResponseException) -> bool:
    """True for the M365 'SmtpClientAuthentication is disabled' 535 response."""
    if getattr(exc, "smtp_code", None) != 535:
        return False
    msg = getattr(exc, "smtp_error", b"")
    if isinstance(msg, bytes):
        msg = msg.decode("utf-8", "replace")
    return "smtpclientauthentication" in msg.lower() or "5.7.139" in msg


def _send_via_graph(secret_key: str, message) -> bytes:
    """Send an OutgoingMessage through Microsoft Graph (Mail.Send). Returns the
    raw MIME so callers keep the same contract as provider.send()."""
    from app.core.security import get_secret_store
    from app.providers import graph, oauth
    from app.sync.compose import build_mime

    store = get_secret_store()
    cache_blob = store.get(secret_key) or ""
    try:
        token, updated = oauth.ms_graph_token(cache_blob)
    except Exception as exc:
        raise PermanentSendError(
            "This Microsoft 365 tenant has SMTP sending disabled, and RaplMail "
            "couldn't get a Microsoft Graph send token. Ask your admin to add the "
            "Graph 'Mail.Send' permission to the app registration (with admin "
            "consent), then reconnect the account - or to re-enable SMTP AUTH for "
            f"your mailbox. ({exc})"
        ) from exc
    if updated and updated != cache_blob:
        store.set(secret_key, updated)
    raw = build_mime(message).as_bytes()
    try:
        graph.send_mime(token, raw)
    except graph.GraphSendError as exc:
        # Only 401/403 (token lacks Mail.Send) is a config problem that won't fix
        # itself on retry. 5xx/throttling - and network errors, which aren't
        # GraphSendError at all - stay ordinary exceptions so the send is queued.
        if exc.status_code not in (401, 403):
            raise
        raise PermanentSendError(
            "Microsoft Graph refused the send (the account's token is missing the "
            "'Mail.Send' permission). Ask your admin to grant Graph 'Mail.Send' to the "
            f"app registration, then reconnect the account. ({exc})"
        ) from exc
    return raw


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
