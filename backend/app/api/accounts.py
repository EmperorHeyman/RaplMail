"""Account management: create IMAP/Gmail/M365 accounts and trigger syncs."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select

from app.api.deps import require_unlocked_store, verify_token
from app.core.db import get_session
from app.core.security import SecretStore
from app.models import Account, Provider
from app.providers import autodiscover as ad
from app.providers import oauth

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(verify_token)])
_log = logging.getLogger("raplmail.accounts")

# Pending Microsoft device-code flows, keyed by an opaque id we hand to the UI.
_pending_ms_flows: dict[str, dict] = {}


class AccountOut(BaseModel):
    id: int
    email: str
    display_name: str
    provider: Provider
    color: str
    enabled: bool
    sort_order: int = 0
    aliases: list[str] = []
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465


def _to_out(a: Account) -> AccountOut:
    return AccountOut(id=a.id, email=a.email, display_name=a.display_name,
                      provider=a.provider, color=a.color, enabled=a.enabled,
                      sort_order=a.sort_order or 0,
                      aliases=list(a.aliases or []),
                      imap_host=a.imap_host, imap_port=a.imap_port,
                      smtp_host=a.smtp_host, smtp_port=a.smtp_port)


@router.get("", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(get_session)) -> list[AccountOut]:
    rows = session.exec(select(Account).order_by(Account.sort_order, Account.id)).all()
    return [_to_out(a) for a in rows]


@router.get("/health")
def accounts_health(request: Request, session: Session = Depends(get_session)) -> list[dict]:
    """Per-account connection/sync/IDLE status for the health dashboard."""
    from app.models import Folder, Message
    from sqlalchemy import func
    snap = request.app.state.sync.health_snapshot()
    out: list[dict] = []
    for a in session.exec(select(Account)):
        h = snap.get(a.id, {})
        folder_count = session.exec(
            select(func.count()).select_from(Folder).where(Folder.account_id == a.id)
        ).one()
        msg_count = session.exec(
            select(func.count()).select_from(Message).where(Message.account_id == a.id)
        ).one()
        out.append({
            "id": a.id, "email": a.email, "display_name": a.display_name,
            "provider": a.provider, "color": a.color, "enabled": a.enabled,
            "status": h.get("status", "idle" if a.enabled else "disabled"),
            "last_sync": h.get("last_sync"),
            "last_attempt": h.get("last_attempt"),
            "last_new": h.get("last_new"),
            "last_error": h.get("last_error"),
            "last_error_at": h.get("last_error_at"),
            "idle_active": h.get("idle_active", False),
            "folders": folder_count,
            "messages": msg_count,
        })
    return out


# --- autodiscovery ---------------------------------------------------------
class AutodiscoverOut(BaseModel):
    email: str
    domain: str
    provider: Provider
    auth: str               # "password" | "oauth"
    imap_host: str
    imap_port: int
    imap_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_starttls: bool
    display_name: str
    source: str
    note: str
    confident: bool


@router.get("/autodiscover", response_model=AutodiscoverOut)
async def autodiscover(email: str) -> AutodiscoverOut:
    """Figure out connection settings + auth method from just an email address."""
    d = await run_in_threadpool(ad.discover, email)
    return AutodiscoverOut(**d.__dict__)


# --- generic IMAP ----------------------------------------------------------
class ImapAccountIn(BaseModel):
    email: str
    display_name: str = ""
    password: str
    imap_host: str
    imap_port: int = 993
    imap_ssl: bool = True
    smtp_host: str
    smtp_port: int = 465


def _verify_imap_login(host: str, port: int, ssl_flag: bool, user: str, password: str) -> None:
    """Attempt an IMAP login (blocking). Raises with a clean message on failure."""
    from imapclient import IMAPClient

    try:
        client = IMAPClient(host, port=port, ssl=ssl_flag, use_uid=True, timeout=15)
    except Exception as exc:
        raise ValueError(f"Could not connect to {host}:{port} — {exc}") from exc
    try:
        client.login(user, password)
        client.list_folders()
    except Exception as exc:
        raise ValueError(f"Sign-in failed: {exc}") from exc
    finally:
        try:
            client.logout()
        except Exception:
            pass


@router.post("/imap", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_imap(body: ImapAccountIn, request: Request,
                      store: SecretStore = Depends(require_unlocked_store),
                      session: Session = Depends(get_session)) -> AccountOut:
    if session.exec(select(Account).where(Account.email == body.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "account already exists")
    # Verify the connection BEFORE persisting anything, so we never add a broken account.
    try:
        await run_in_threadpool(_verify_imap_login, body.imap_host, body.imap_port,
                                body.imap_ssl, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    secret_key = f"account:{body.email}:{uuid.uuid4().hex[:8]}"
    store.set(secret_key, body.password)
    account = Account(
        email=body.email, display_name=body.display_name or body.email,
        provider=Provider.imap, imap_host=body.imap_host, imap_port=body.imap_port,
        smtp_host=body.smtp_host, smtp_port=body.smtp_port, secret_key=secret_key,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    request.app.state.sync.request_sync()
    return _to_out(account)


# --- Microsoft 365 device-code flow ----------------------------------------
class DeviceFlowOut(BaseModel):
    flow_id: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str = ""
    message: str
    expires_in: int


@router.post("/ms/device-flow/start", response_model=DeviceFlowOut)
async def ms_start() -> DeviceFlowOut:
    try:
        flow = await run_in_threadpool(oauth.ms_start_device_flow)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    flow_id = uuid.uuid4().hex
    _pending_ms_flows[flow_id] = flow.flow
    return DeviceFlowOut(flow_id=flow_id, user_code=flow.user_code,
                         verification_uri=flow.verification_uri,
                         verification_uri_complete=flow.verification_uri_complete,
                         message=flow.message, expires_in=flow.expires_in)


class CompleteIn(BaseModel):
    flow_id: str


@router.post("/ms/device-flow/complete", response_model=AccountOut)
async def ms_complete(body: CompleteIn, request: Request,
                      store: SecretStore = Depends(require_unlocked_store),
                      session: Session = Depends(get_session)) -> AccountOut:
    flow = _pending_ms_flows.pop(body.flow_id, None)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or expired flow")
    try:
        email, cache_blob = await run_in_threadpool(oauth.ms_complete_device_flow, flow)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    account = _upsert_oauth_account(session, store, email, Provider.m365, cache_blob)
    request.app.state.sync.request_sync()
    return _to_out(account)


# --- Gmail loopback flow ----------------------------------------------------
@router.post("/google/connect", response_model=AccountOut)
async def google_connect(request: Request,
                         store: SecretStore = Depends(require_unlocked_store),
                         session: Session = Depends(get_session)) -> AccountOut:
    try:
        email, bundle = await run_in_threadpool(oauth.google_run_installed_flow)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    account = _upsert_oauth_account(session, store, email, Provider.gmail,
                                    oauth.serialize_bundle(bundle))
    request.app.state.sync.request_sync()
    return _to_out(account)


def _upsert_oauth_account(session: Session, store: SecretStore, email: str,
                          provider: Provider, secret_blob: str) -> Account:
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "could not determine account email")
    account = session.exec(select(Account).where(Account.email == email)).first()
    if account is None:
        secret_key = f"account:{email}:{uuid.uuid4().hex[:8]}"
        account = Account(email=email, display_name=email, provider=provider,
                          use_oauth=True, secret_key=secret_key)
        session.add(account)
    store.set(account.secret_key, secret_blob)
    session.commit()
    session.refresh(account)
    return account


class AccountUpdate(BaseModel):
    color: str | None = None
    display_name: str | None = None
    sort_order: int | None = None
    aliases: list[str] | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate,
                   session: Session = Depends(get_session)) -> AccountOut:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if body.color is not None:
        account.color = body.color
    if body.display_name is not None:
        account.display_name = body.display_name
    if body.sort_order is not None:
        account.sort_order = body.sort_order
    if body.aliases is not None:
        # Drop blanks and dedupe while preserving order.
        seen, cleaned = set(), []
        for a in (s.strip() for s in body.aliases):
            if a and a.lower() not in seen:
                seen.add(a.lower()); cleaned.append(a)
        account.aliases = cleaned
    if body.imap_host is not None: account.imap_host = body.imap_host.strip()
    if body.imap_port is not None: account.imap_port = body.imap_port
    if body.smtp_host is not None: account.smtp_host = body.smtp_host.strip()
    if body.smtp_port is not None: account.smtp_port = body.smtp_port
    session.add(account)
    session.commit()
    session.refresh(account)
    # New server settings → drop any pooled connection using the old host.
    try:
        from app.providers.pool import pool
        pool.drop(account.id)
    except Exception:
        pass
    return _to_out(account)


class ReconnectIn(BaseModel):
    password: str


@router.post("/{account_id}/reconnect", response_model=AccountOut)
async def reconnect(account_id: int, body: ReconnectIn, request: Request,
                    store: SecretStore = Depends(require_unlocked_store),
                    session: Session = Depends(get_session)) -> AccountOut:
    """Re-enter / fix the password for a password-based IMAP account (verifies it
    against the server before storing), without removing the account."""
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if account.use_oauth or account.provider != Provider.imap:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This account signs in with OAuth — use Sign in with Microsoft/Google instead.")
    if not body.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter your password.")
    try:
        await run_in_threadpool(_verify_imap_login, account.imap_host, account.imap_port,
                                True, account.email, body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    store.set(account.secret_key, body.password)
    request.app.state.sync.request_sync()
    return _to_out(account)


@router.post("/{account_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(account_id: int, request: Request,
                       session: Session = Depends(get_session)) -> dict:
    if session.get(Account, account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    request.app.state.sync.request_sync()
    return {"queued": True}


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, store: SecretStore = Depends(require_unlocked_store),
                   session: Session = Depends(get_session)) -> None:
    from sqlalchemy import delete as sa_delete

    from app.models import (CalendarEvent, Folder, Message, MessageState, Rule,
                            ScheduledSend, Signature)

    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    # Foreign keys are enforced (PRAGMA foreign_keys=ON), so every child row must
    # go before whatever it references. Dependency order matters:
    #   CalendarEvent -> message + account   (delete BEFORE messages)
    #   Message       -> folder + account    (delete BEFORE folders)
    # Do it all in one transaction; on any error, roll back and report cleanly so
    # the request never dies mid-flight ("Failed to fetch").
    try:
        # NB: message_fts is a contentless FTS5 table (content=''), which rejects
        # plain DELETEs, so we intentionally don't touch it here. Its entries are
        # keyed by message rowid; once the messages are gone, a search hit simply
        # doesn't resolve to a row and is dropped — harmless orphans, no crash.
        session.exec(sa_delete(CalendarEvent).where(CalendarEvent.account_id == account_id))
        session.exec(sa_delete(MessageState).where(MessageState.account_id == account_id))
        session.exec(sa_delete(Message).where(Message.account_id == account_id))
        session.exec(sa_delete(Folder).where(Folder.account_id == account_id))
        session.exec(sa_delete(ScheduledSend).where(ScheduledSend.account_id == account_id))
        # Rules/signatures scoped to this account only (account_id IS NULL = global).
        session.exec(sa_delete(Rule).where(Rule.account_id == account_id))
        session.exec(sa_delete(Signature).where(Signature.account_id == account_id))
        # Credential removal is best-effort — an M365 account with an empty token
        # cache still removes cleanly.
        try:
            if account.secret_key:
                store.delete(account.secret_key)
        except Exception:
            pass
        session.delete(account)
        session.commit()
    except Exception as exc:
        session.rollback()
        _log.exception("account delete failed for %s", account_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Couldn't delete the account: {exc}") from exc
