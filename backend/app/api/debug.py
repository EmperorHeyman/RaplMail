"""Debug window API: recent backend logs + per-account sync health.

Read-only diagnostics for the in-app Debug settings tab, so the user can see what
the backend is doing (and hand over a log if something stalls) without a console.
"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, Request

from app.api.deps import verify_token
from app.core.logbuffer import get_log_buffer

router = APIRouter(prefix="/debug", tags=["debug"], dependencies=[Depends(verify_token)])


@router.get("/logs")
def get_logs(since: int = 0, level: str | None = None) -> dict:
    """Recent log lines. Pass ?since=<last seq> to fetch only newer lines (cheap
    polling for the live view)."""
    buf = get_log_buffer()
    records = buf.records(since=since, level=level)
    last_seq = records[-1]["seq"] if records else since
    return {"records": records, "last_seq": last_seq}


@router.delete("/logs")
def clear_logs() -> dict:
    get_log_buffer().clear()
    return {"cleared": True}


@router.get("/health")
def get_health(request: Request) -> dict:
    """Per-account sync status (last sync/attempt, errors, IDLE state) merged with
    account email/provider so the UI can label each row."""
    from sqlmodel import Session, select

    from app.core.db import get_engine
    from app.models import Account

    snap = {}
    try:
        snap = request.app.state.sync.health_snapshot()
    except Exception:
        snap = {}

    accounts = []
    with Session(get_engine()) as session:
        for a in session.exec(select(Account)):
            prov = a.provider.value if hasattr(a.provider, "value") else a.provider
            h = snap.get(a.id, {})
            accounts.append({
                "id": a.id, "email": a.email, "provider": prov, "enabled": a.enabled,
                "imap_host": a.imap_host, "smtp_host": a.smtp_host, **h,
            })

    return {
        "accounts": accounts,
        "system": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "version": request.app.version,
        },
    }
