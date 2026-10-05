"""Small bridges to the desktop the webview can't do on its own."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import verify_token
from app.core import clipboard

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(verify_token)])


class ClipboardIn(BaseModel):
    text: str


@router.post("/clipboard")
def set_clipboard(body: ClipboardIn) -> dict:
    """Copy text to the system clipboard - works while RaplMail isn't the
    focused window (a sign-in code copied as it arrives)."""
    text = (body.text or "")[:2000]
    return {"ok": bool(text) and clipboard.set_text(text)}
