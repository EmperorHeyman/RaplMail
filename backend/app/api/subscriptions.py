"""Subscription Audit.

Aggregates mailing-list senders (those that stamp a List-Unsubscribe header, or
land in the Newsletters category) with a 30-day read rate computed from local
read state, so the user can spot dormant / never-opened subscriptions and clear
them in one sweep. Read-only; the actual unsubscribe / archive is driven from the
frontend via the existing unsubscribe links and the rules engine.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Message

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"],
                   dependencies=[Depends(verify_token)])


def _unsub_target(raw: str) -> str:
    """Pick a usable unsubscribe target from a raw List-Unsubscribe header
    (prefer an http(s) one-click URL, else a mailto:)."""
    parts = [p.strip() for p in re.findall(r"<([^>]+)>", raw or "")]
    http = next((p for p in parts if p.lower().startswith("http")), "")
    mailto = next((p for p in parts if p.lower().startswith("mailto:")), "")
    return http or mailto or ""


@router.get("/audit")
def audit(sort: str = "dormant", session: Session = Depends(get_session)) -> dict:
    """One row per mailing-list sender: totals, 30-day activity + read rate,
    last-seen, and an unsubscribe target.

    `sort` orders the rows: "dormant" (lowest read-rate + oldest, the best cleanup
    targets - the default), "most" (most received overall), "recent" (most active
    in the last 30 days), "unread" (lowest read-rate), or "name" (A-Z)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=30)
    # A "subscription" = mail that carries a List-Unsubscribe header (only set once
    # a message body has been fetched) OR is classified as a newsletter.
    is_list = or_(Message.unsubscribe != "", Message.category == "newsletters")

    totals = session.exec(
        select(Message.from_addr, func.max(Message.from_name), func.count(),
               func.max(Message.date), func.max(Message.unsubscribe))
        .where(is_list)
        .group_by(Message.from_addr)
    ).all()
    recent30 = dict(session.exec(
        select(Message.from_addr, func.count())
        .where(is_list, Message.date != None, Message.date >= cutoff)  # noqa: E711
        .group_by(Message.from_addr)
    ).all())
    read30 = dict(session.exec(
        select(Message.from_addr, func.count())
        .where(is_list, Message.is_seen == True,  # noqa: E712
               Message.date != None, Message.date >= cutoff)  # noqa: E711
        .group_by(Message.from_addr)
    ).all())

    lists = []
    for from_addr, from_name, total, last_date, unsub in totals:
        if not from_addr:
            continue
        recent = int(recent30.get(from_addr, 0))
        read = int(read30.get(from_addr, 0))
        lists.append({
            "from_addr": from_addr,
            "from_name": from_name or "",
            "total": int(total or 0),
            "recent30": recent,
            "read30": read,
            "read_rate": round(read / recent, 2) if recent else 0.0,
            "last_seen": last_date.isoformat() if last_date else "",
            "unsubscribe": _unsub_target(unsub or ""),
        })
    sorters = {
        # Dormant first: lowest read-rate, then oldest last-seen - best cleanup targets.
        "dormant": (lambda r: (r["read_rate"], r["last_seen"]), False),
        "most": (lambda r: r["total"], True),                 # most received overall
        "recent": (lambda r: r["recent30"], True),            # most active last 30 days
        "unread": (lambda r: r["read_rate"], False),          # lowest read rate
        "name": (lambda r: (r["from_name"] or r["from_addr"]).lower(), False),
    }
    key, reverse = sorters.get(sort, sorters["dormant"])
    lists.sort(key=key, reverse=reverse)
    return {"lists": lists, "count": len(lists)}


class UnsubIn(BaseModel):
    url: str


@router.post("/unsubscribe")
def unsubscribe_oneclick(body: UnsubIn) -> dict:
    """RFC 8058 one-click unsubscribe: POST `List-Unsubscribe=One-Click` to the
    http(s) unsubscribe URL. Many bulk senders (e.g. Humble Bundle) expose a
    one-click endpoint that returns an error page on a plain browser GET but
    unsubscribes correctly on a POST. Returns ok=False so the caller can fall back
    to opening the page in the browser (confirmation-style unsubscribes)."""
    import httpx  # deferred - only when the user actually unsubscribes

    url = (body.url or "").strip()
    if not url.lower().startswith("http"):
        return {"ok": False, "method": "none"}
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            r = client.post(
                url,
                data={"List-Unsubscribe": "One-Click"},
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "User-Agent": "RaplMail-Unsubscribe/1.0"},
            )
        return {"ok": 200 <= r.status_code < 300, "method": "post", "status": r.status_code}
    except Exception as exc:  # noqa: BLE001 - network/DNS/TLS: fall back to the browser
        return {"ok": False, "method": "post", "error": str(exc)}
