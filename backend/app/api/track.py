"""Local open-tracking: a 1x1 read-receipt pixel served by the backend.

When you enable a read receipt on a message, the body gets an <img> pointing at
`/track/o/{token}.png`. The recipient's mail client fetching that image records
the open here and pushes a live "mail:opened" event. Privacy note: this only
works if the recipient can actually reach this backend (i.e. it's exposed on the
LAN/internet, RAPLMAIL_HOST=0.0.0.0). The pixel endpoint is intentionally
unauthenticated — anyone with the opaque token can register an open.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import OpenTrack

# A 1x1 transparent GIF (smaller than PNG, universally rendered).
_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

# Unauthenticated pixel endpoint (the recipient must be able to load it).
pixel_router = APIRouter(prefix="/track", tags=["track"])
# Authenticated management endpoints.
router = APIRouter(prefix="/track", tags=["track"], dependencies=[Depends(verify_token)])


@pixel_router.get("/o/{token}.png")
async def open_pixel(token: str, request: Request, session: Session = Depends(get_session)) -> Response:
    row = session.exec(select(OpenTrack).where(OpenTrack.token == token)).first()
    if row is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row.open_count += 1
        row.last_open = now
        if row.first_open is None:
            row.first_open = now
        session.add(row)
        session.commit()
        try:
            await request.app.state.sync._hub.broadcast(
                "mail:opened", {"subject": row.subject, "recipient": row.recipient,
                                "count": row.open_count})
        except Exception:
            pass
    return Response(content=_PIXEL, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("")
def list_tracked(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(OpenTrack).order_by(OpenTrack.created_at.desc()).limit(200))
    return [{
        "token": r.token, "subject": r.subject, "recipient": r.recipient,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "open_count": r.open_count,
        "first_open": r.first_open.isoformat() if r.first_open else None,
        "last_open": r.last_open.isoformat() if r.last_open else None,
    } for r in rows]
