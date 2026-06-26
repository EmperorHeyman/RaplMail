"""Read-only mailbox metrics for LAN consumers (Home Assistant, ESP32, dashboards).

Unlike the rest of the API (locked behind the per-launch token that only the Tauri
shell knows), this endpoint is meant to be polled by other devices on your network.
It is therefore:
  * read-only — exposes counts only, never message content;
  * opt-in — returns 404 unless you enable it in Settings;
  * authenticated by a *stable* API key you set (header `X-API-Key` or `?key=`),
    not the per-launch token, so a device can be configured once.

To reach it from another machine the backend must also listen on the LAN
interface — set RAPLMAIL_HOST=0.0.0.0 for the backend process.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import get_engine
from app.models import Account, ActionQueue, Folder, FolderRole, Message, ScheduledSend

router = APIRouter(tags=["metrics"])


def _local_api_config() -> tuple[bool, str]:
    """(enabled, key) from the persisted settings blob."""
    from app.models import Setting
    with Session(get_engine()) as session:
        row = session.get(Setting, 1)
        data = dict(row.data) if row and row.data else {}
    return bool(data.get("localApiEnabled")), str(data.get("localApiKey") or "")


def _authorize(request: Request) -> None:
    enabled, key = _local_api_config()
    if not enabled:
        # Indistinguishable from "no such endpoint" when disabled.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    supplied = request.headers.get("X-API-Key") or request.query_params.get("key") or ""
    launch_token = get_settings().token
    token_hdr = request.headers.get("X-RaplMail-Token") or ""
    # Accept the stable API key, or the app's own launch token (so the UI can preview it).
    if key and supplied == key:
        return
    if launch_token and token_hdr == launch_token:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


def _gather() -> dict:
    with Session(get_engine()) as session:
        inbox_folder_ids = list(session.exec(
            select(Folder.id).where(Folder.role == FolderRole.inbox)
        ))

        def _count(*conds):
            stmt = select(func.count()).select_from(Message)
            for c in conds:
                stmt = stmt.where(c)
            return int(session.exec(stmt).one())

        in_inbox = Message.folder_id.in_(inbox_folder_ids or [-1])
        active = (Message.is_done == False) & (Message.pending_action == "")  # noqa: E712
        unread = _count(in_inbox, active, Message.is_seen == False)  # noqa: E712
        inbox_total = _count(in_inbox, active)
        flagged = _count(Message.is_flagged == True, active)  # noqa: E712
        snoozed = _count(Message.snooze_until != None)  # noqa: E711
        total = _count()

        accounts = []
        for a in session.exec(select(Account)):
            a_inbox = Message.account_id == a.id
            accounts.append({
                "email": a.email,
                "unread": _count(in_inbox, active, a_inbox, Message.is_seen == False),  # noqa: E712
                "inbox": _count(in_inbox, active, a_inbox),
                "total": _count(a_inbox),
            })

        queue_pending = _count_queue(session, "pending")
        queue_failed = _count_queue(session, "failed")
        scheduled = int(session.exec(
            select(func.count()).select_from(ScheduledSend).where(ScheduledSend.status == "pending")
        ).one())

    return {
        "unread": unread,
        "inbox": inbox_total,
        "flagged": flagged,
        "snoozed": snoozed,
        "total_messages": total,
        "accounts": accounts,
        "queue_pending": queue_pending,
        "queue_failed": queue_failed,
        "scheduled_pending": scheduled,
    }


def _count_queue(session: Session, qstatus: str) -> int:
    stmt = select(func.count()).select_from(ActionQueue).where(ActionQueue.status == qstatus)
    return int(session.exec(stmt).one())


@router.get("/metrics")
def metrics(request: Request) -> dict:
    """Mailbox stats as JSON (Home Assistant REST sensor friendly)."""
    _authorize(request)
    return _gather()


@router.get("/metrics/prometheus")
def metrics_prometheus(request: Request) -> Response:
    """Same stats in Prometheus text exposition format."""
    _authorize(request)
    m = _gather()
    lines = [
        "# HELP raplmail_unread Unread messages in the inbox",
        "# TYPE raplmail_unread gauge",
        f"raplmail_unread {m['unread']}",
        "# HELP raplmail_inbox Active (not done) messages in the inbox",
        "# TYPE raplmail_inbox gauge",
        f"raplmail_inbox {m['inbox']}",
        "# HELP raplmail_flagged Flagged messages",
        "# TYPE raplmail_flagged gauge",
        f"raplmail_flagged {m['flagged']}",
        "# HELP raplmail_queue_pending Outgoing actions awaiting send",
        "# TYPE raplmail_queue_pending gauge",
        f"raplmail_queue_pending {m['queue_pending']}",
        "# HELP raplmail_scheduled_pending Scheduled sends awaiting delivery",
        "# TYPE raplmail_scheduled_pending gauge",
        f"raplmail_scheduled_pending {m['scheduled_pending']}",
        "# HELP raplmail_account_unread Unread messages per account",
        "# TYPE raplmail_account_unread gauge",
    ]
    for a in m["accounts"]:
        safe = a["email"].replace("\\", "").replace('"', "")
        lines.append(f'raplmail_account_unread{{account="{safe}"}} {a["unread"]}')
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
