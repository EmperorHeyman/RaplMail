"""Signature CRUD. Inline images are stored base64-encoded and referenced from
the signature HTML via ``cid:<id>`` so they embed correctly when sending."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Signature

router = APIRouter(prefix="/signatures", tags=["signatures"], dependencies=[Depends(verify_token)])


class InlineImage(BaseModel):
    cid: str
    filename: str = "image.png"
    content_type: str = "image/png"
    data_b64: str


class SignatureIn(BaseModel):
    account_id: int | None = None
    name: str = "Default"
    html: str = ""
    inline_images: list[InlineImage] = []
    is_default: bool = True


class SignatureOut(SignatureIn):
    id: int


def _to_out(s: Signature) -> SignatureOut:
    return SignatureOut(id=s.id, account_id=s.account_id, name=s.name, html=s.html,
                        inline_images=[InlineImage(**i) for i in (s.inline_images or [])],
                        is_default=s.is_default)


@router.get("", response_model=list[SignatureOut])
def list_signatures(account_id: int | None = None, session: Session = Depends(get_session)) -> list[SignatureOut]:
    stmt = select(Signature)
    if account_id is not None:
        stmt = stmt.where((Signature.account_id == account_id) | (Signature.account_id == None))  # noqa: E711
    return [_to_out(s) for s in session.exec(stmt)]


@router.post("", response_model=SignatureOut, status_code=status.HTTP_201_CREATED)
def create_signature(body: SignatureIn, session: Session = Depends(get_session)) -> SignatureOut:
    sig = Signature(account_id=body.account_id, name=body.name, html=body.html,
                    inline_images=[i.model_dump() for i in body.inline_images],
                    is_default=body.is_default)
    session.add(sig)
    session.commit()
    session.refresh(sig)
    return _to_out(sig)


@router.put("/{sig_id}", response_model=SignatureOut)
def update_signature(sig_id: int, body: SignatureIn, session: Session = Depends(get_session)) -> SignatureOut:
    sig = session.get(Signature, sig_id)
    if sig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signature not found")
    sig.account_id = body.account_id
    sig.name = body.name
    sig.html = body.html
    sig.inline_images = [i.model_dump() for i in body.inline_images]
    sig.is_default = body.is_default
    session.add(sig)
    session.commit()
    session.refresh(sig)
    return _to_out(sig)


@router.delete("/{sig_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_signature(sig_id: int, session: Session = Depends(get_session)) -> None:
    sig = session.get(Signature, sig_id)
    if sig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signature not found")
    session.delete(sig)
    session.commit()
