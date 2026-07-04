"""RAPL Desk (ticketing) integration.

Connect one or more RaplDesk instances (name + base URL + API key). Keys live in
the encrypted secret store; instance metadata in the settings blob. A generic
proxy forwards calls to the instance's api.php with the Bearer key, so the
frontend never holds the key and we avoid CORS.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Setting

router = APIRouter(prefix="/rapldesk", tags=["rapldesk"], dependencies=[Depends(verify_token)])
_KEY = "rapldesk:"   # secret-store key prefix per instance


def _instances(session: Session) -> list[dict]:
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    return list(cfg.get("raplDesk") or [])


def _save_instances(session: Session, items: list[dict]) -> None:
    row = session.get(Setting, 1)
    cfg = dict(row.data) if row and row.data else {}
    cfg["raplDesk"] = items
    if row is None:
        session.add(Setting(id=1, data=cfg))
    else:
        row.data = cfg
    session.commit()


class InstanceIn(BaseModel):
    name: str
    url: str
    key: str


@router.get("/instances")
def list_instances(session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    store = get_secret_store()
    out = []
    for i in _instances(session):
        out.append({"id": i["id"], "name": i.get("name", ""), "url": i.get("url", ""),
                    "connected": store.is_unlocked and bool(store.get(_KEY + i["id"]))})
    return {"instances": out}


@router.post("/instances")
def add_instance(body: InstanceIn, session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.is_unlocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock the vault first.")
    url = body.url.strip().rstrip("/")
    if not url.startswith("http"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "URL must start with http(s)://")
    iid = uuid.uuid4().hex[:8]
    items = _instances(session)
    items.append({"id": iid, "name": body.name.strip() or url, "url": url})
    _save_instances(session, items)
    store.set(_KEY + iid, body.key.strip())
    return {"id": iid, "name": body.name.strip() or url, "url": url, "connected": True}


@router.delete("/instances/{iid}")
def delete_instance(iid: str, session: Session = Depends(get_session)) -> dict:
    from app.core.security import get_secret_store
    store = get_secret_store()
    _save_instances(session, [i for i in _instances(session) if i["id"] != iid])
    if store.is_unlocked:
        try:
            store.delete(_KEY + iid)
        except Exception:
            pass
    return {"deleted": True}


class CallIn(BaseModel):
    method: str = "GET"
    endpoint: str                  # e.g. "tickets" or "tickets/123/replies"
    query: dict = {}
    body: dict | None = None


@router.post("/{iid}/call")
async def call(iid: str, body: CallIn, session: Session = Depends(get_session)) -> dict:
    """Generic authenticated proxy to a RaplDesk instance's api.php."""
    from app.core.security import get_secret_store
    store = get_secret_store()
    inst = next((i for i in _instances(session) if i["id"] == iid), None)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "instance not found")
    key = store.get(_KEY + iid) if store.is_unlocked else None
    if not key:
        raise HTTPException(status.HTTP_409_CONFLICT, "No API key for this instance — re-add it.")
    method = (body.method or "GET").upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported method")
    base = _api_base(inst["url"])
    params = {"endpoint": body.endpoint, **(body.query or {})}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _do():
        import httpx  # deferred — only loaded when a RaplDesk instance is actually used
        return httpx.request(method, base, params=params, headers=headers,
                             json=body.body if method in ("POST", "PUT") else None,
                             timeout=30, follow_redirects=True)
    try:
        r = await run_in_threadpool(_do)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"RaplDesk unreachable: {exc}") from exc
    try:
        data = r.json()
    except Exception:
        # Non-JSON (e.g. an nginx 404 HTML page) — surface the URL we hit so a
        # wrong base URL is obvious.
        data = {"status": "error", "message": f"Non-JSON response (HTTP {r.status_code}) from {r.request.url}"}
    return {"http": r.status_code, "url": str(r.request.url), "data": data}


def _api_base(url: str) -> str:
    """Resolve the v2 api.php endpoint from whatever the user entered — bare domain
    or any /admin/addons/api[/vN]/api.php path (always normalized to v2)."""
    u = (url or "").strip().rstrip("/")
    if "/admin/addons/api" in u:
        root = u.split("/admin/addons/api")[0]
        return f"{root}/admin/addons/api/v2/api.php"
    return f"{u}/admin/addons/api/v2/api.php"
