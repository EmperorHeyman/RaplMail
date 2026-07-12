"""Device-to-device sync API (0.4.0).

Thin control surface over app/sync/devicesync: read status, configure (enable +
choose the carrier account + set the passphrase), and trigger an immediate
publish/scan. The heavy lifting (crypto, IMAP APPEND/scan, merge) lives in the
sync module; a normal mail sync of the carrier account also runs a tick.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import verify_token
from app.core.db import get_engine, get_session
from app.models import Account
from app.sync import devicesync

router = APIRouter(prefix="/sync", tags=["sync"], dependencies=[Depends(verify_token)])


@router.get("/status")
def sync_status(session: Session = Depends(get_session)) -> dict:
    return devicesync.status(session)


class SyncConfigIn(BaseModel):
    enabled: bool
    account_id: int | None = None
    passphrase: str | None = None
    device_label: str | None = None   # None = leave unchanged, "" = reset to hostname


@router.put("/config")
def sync_config(body: SyncConfigIn, session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    if body.enabled:
        if body.account_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an account to carry the sync.")
        if session.get(Account, body.account_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
        store = get_secret_store()
        have_pass = store.is_unlocked and store.get(devicesync.PASSPHRASE_KEY)
        if not body.passphrase and not have_pass:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set a sync passphrase.")
        if body.passphrase is not None and len(body.passphrase) < 8:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The sync passphrase must be at least 8 characters.")
    devicesync.set_config(session, enabled=body.enabled, account_id=body.account_id,
                          passphrase=body.passphrase, device_label=body.device_label)
    return devicesync.status(session)


def _guard_ready(st: dict) -> None:
    if not st["enabled"] or not st["account_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Device sync isn't set up yet.")
    if not st["has_passphrase"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock the vault and set a passphrase first.")


def _with_provider(account_id: int, action: str, uid: int | None = None) -> dict:
    """Build a provider for the carrier account and run one sync action against
    it, always closing the provider afterwards."""
    from app.sync.engine import build_provider
    with Session(get_engine()) as s:
        account = s.get(Account, account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
        provider = build_provider(account)
        try:
            if action == "tick":
                devicesync.tick(s, account, provider)
                return devicesync.status(s)
            if action == "push":
                return devicesync.push_config(s, account, provider)
            if action == "snapshots":
                return {"snapshots": devicesync.list_config_snapshots(s, provider)}
            if action == "pull":
                return devicesync.pull_config(s, provider, uid)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown sync action.")
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        finally:
            try:
                provider.close()
            except Exception:
                pass


@router.post("/now")
async def sync_now(session: Session = Depends(get_session)) -> dict:
    st = devicesync.status(session)
    _guard_ready(st)
    return await run_in_threadpool(_with_provider, st["account_id"], "tick")


@router.post("/push-config")
async def push_config(session: Session = Depends(get_session)) -> dict:
    """Publish this device's settings/rules/signatures as a config snapshot."""
    st = devicesync.status(session)
    _guard_ready(st)
    return await run_in_threadpool(_with_provider, st["account_id"], "push")


@router.get("/config-snapshots")
async def config_snapshots(session: Session = Depends(get_session)) -> dict:
    """List the config snapshots available to pull, newest first."""
    st = devicesync.status(session)
    _guard_ready(st)
    return await run_in_threadpool(_with_provider, st["account_id"], "snapshots")


class PullConfigIn(BaseModel):
    uid: int


@router.post("/pull-config")
async def pull_config(body: PullConfigIn, session: Session = Depends(get_session)) -> dict:
    """Apply a chosen config snapshot onto this device."""
    st = devicesync.status(session)
    _guard_ready(st)
    return await run_in_threadpool(_with_provider, st["account_id"], "pull", body.uid)
