"""Address book API: autocomplete search, manual add, delete, and rescan."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import verify_token
from app.core.db import get_engine, get_session
from app.models import Contact
from app.providers.imap_smtp import decode_mime_words
from app.sync.contacts import scan_contacts

router = APIRouter(prefix="/contacts", tags=["contacts"], dependencies=[Depends(verify_token)])


class ContactOut(BaseModel):
    id: int
    email: str
    name: str
    times_sent: int
    times_received: int
    last_contacted: datetime | None
    is_known_domain: bool
    favorite: bool
    source: str


def _to_out(c: Contact) -> ContactOut:
    return ContactOut(id=c.id, email=c.email, name=decode_mime_words(c.name), times_sent=c.times_sent,
                      times_received=c.times_received, last_contacted=c.last_contacted,
                      is_known_domain=c.is_known_domain, favorite=c.favorite, source=c.source)


@router.get("", response_model=list[ContactOut])
def list_contacts(q: str | None = None, limit: int = 50,
                  session: Session = Depends(get_session)) -> list[ContactOut]:
    stmt = select(Contact)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(Contact.email.ilike(like), Contact.name.ilike(like)))
    # Most-contacted and favorites first — best autocomplete ordering.
    stmt = stmt.order_by(Contact.favorite.desc(), Contact.times_sent.desc(),
                         Contact.last_contacted.desc()).limit(limit)
    return [_to_out(c) for c in session.exec(stmt)]


class ContactIn(BaseModel):
    email: str
    name: str = ""
    favorite: bool = False


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(body: ContactIn, session: Session = Depends(get_session)) -> ContactOut:
    email = body.email.strip().lower()
    contact = session.exec(select(Contact).where(Contact.email == email)).first()
    if contact is None:
        contact = Contact(email=email, source="manual")
        session.add(contact)
    contact.name = body.name or contact.name
    contact.favorite = body.favorite
    session.commit()
    session.refresh(contact)
    return _to_out(contact)


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, body: ContactIn, session: Session = Depends(get_session)) -> ContactOut:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    contact.name = body.name
    contact.favorite = body.favorite
    session.commit()
    session.refresh(contact)
    return _to_out(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: int, session: Session = Depends(get_session)) -> None:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    session.delete(contact)
    session.commit()


class RescanOut(BaseModel):
    scanned: int


@router.post("/rescan", response_model=RescanOut)
async def rescan() -> RescanOut:
    def _do() -> int:
        with Session(get_engine()) as session:
            return scan_contacts(session)
    count = await run_in_threadpool(_do)
    return RescanOut(scanned=count)
