"""Folder listing per account."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_unlocked_store, verify_token
from app.core.db import get_session
from app.models import Account, Folder, FolderRole, Message

router = APIRouter(prefix="/folders", tags=["folders"], dependencies=[Depends(verify_token)])


class FolderOut(BaseModel):
    id: int
    account_id: int
    name: str
    path: str
    role: FolderRole
    unread_count: int
    total_count: int


@router.get("", response_model=list[FolderOut])
def list_folders(account_id: int | None = None,
                 session: Session = Depends(get_session)) -> list[FolderOut]:
    stmt = select(Folder)
    if account_id is not None:
        stmt = stmt.where(Folder.account_id == account_id)
    out: list[FolderOut] = []
    for f in session.exec(stmt):
        # Live counts excluding done (done is hidden from default views).
        unread = session.exec(
            select(func.count()).select_from(Message).where(
                Message.folder_id == f.id, Message.is_seen == False,  # noqa: E712
                Message.is_done == False)  # noqa: E712
        ).one()
        total = session.exec(
            select(func.count()).select_from(Message).where(Message.folder_id == f.id)
        ).one()
        out.append(FolderOut(id=f.id, account_id=f.account_id, name=f.name, path=f.path,
                             role=f.role, unread_count=unread, total_count=total))
    return out


class FolderCreateIn(BaseModel):
    account_id: int
    name: str


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_unlocked_store)])
async def create_folder(body: FolderCreateIn, request: Request,
                        session: Session = Depends(get_session)) -> dict:
    account = session.get(Account, body.account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "folder name required")

    def _do() -> None:
        from app.sync.engine import build_provider
        provider = build_provider(account)
        try:
            provider.create_folder(name)
        finally:
            provider.close()
    try:
        await run_in_threadpool(_do)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Couldn't create folder: {exc}") from exc
    request.app.state.sync.request_sync()   # pick up the new folder
    return {"created": True}


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_unlocked_store)])
async def delete_folder(folder_id: int, session: Session = Depends(get_session)) -> None:
    folder = session.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "folder not found")
    if folder.role in (FolderRole.inbox, FolderRole.sent):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "can't delete a core folder")
    account = session.get(Account, folder.account_id)
    path = folder.path

    def _do() -> None:
        from app.sync.engine import build_provider
        provider = build_provider(account)
        try:
            provider.delete_folder(path)
        finally:
            provider.close()
    try:
        await run_in_threadpool(_do)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Couldn't delete folder: {exc}") from exc

    # Local cleanup in FK order (foreign keys enforced): events -> messages -> folder.
    from sqlalchemy import delete as sa_delete

    from app.models import CalendarEvent
    msg_ids = select(Message.id).where(Message.folder_id == folder_id)
    session.exec(sa_delete(CalendarEvent).where(CalendarEvent.message_id.in_(msg_ids)))
    session.exec(sa_delete(Message).where(Message.folder_id == folder_id))
    session.delete(folder)
    session.commit()
