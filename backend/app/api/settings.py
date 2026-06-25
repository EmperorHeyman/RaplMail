"""App settings persistence + config export/import.

UI/behavior settings are stored as a single JSON blob in the DB (a file), so
they survive restarts and move with the data. Export bundles the settings plus
the config that isn't re-syncable (rules, signatures, sender categories) so you
can carry a setup from dev to prod. Emails themselves live on the mail server
and re-sync once accounts are connected, so they're not part of the bundle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Rule, SenderCategory, Setting, Signature

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(verify_token)])

EXPORT_VERSION = 1


def _get_blob(session: Session) -> dict:
    row = session.get(Setting, 1)
    return dict(row.data) if row and row.data else {}


def _set_blob(session: Session, data: dict) -> None:
    row = session.get(Setting, 1)
    if row is None:
        row = Setting(id=1, data=data)
        session.add(row)
    else:
        row.data = data
        row.updated_at = datetime.now(timezone.utc)
    session.commit()


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> dict:
    return _get_blob(session)


class SettingsIn(BaseModel):
    data: dict


@router.put("")
def put_settings(body: SettingsIn, session: Session = Depends(get_session)) -> dict:
    _set_blob(session, body.data)
    return {"ok": True}


@router.get("/export")
def export_bundle(session: Session = Depends(get_session)) -> dict:
    rules = [
        {k: v for k, v in r.model_dump().items() if k not in ("id", "account_id", "created_at")}
        for r in session.exec(select(Rule))
    ]
    sigs = [
        {k: v for k, v in s.model_dump().items() if k not in ("id", "account_id", "created_at")}
        for s in session.exec(select(Signature))
    ]
    cats = [{"email": c.email, "category": c.category} for c in session.exec(select(SenderCategory))]
    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "settings": _get_blob(session),
        "rules": rules,
        "signatures": sigs,
        "sender_categories": cats,
    }


class ImportResult(BaseModel):
    settings: bool
    rules: int
    signatures: int
    sender_categories: int


@router.post("/import", response_model=ImportResult)
def import_bundle(bundle: dict, session: Session = Depends(get_session)) -> ImportResult:
    res = ImportResult(settings=False, rules=0, signatures=0, sender_categories=0)

    if isinstance(bundle.get("settings"), dict):
        _set_blob(session, bundle["settings"])
        res.settings = True

    # Rules: add ones we don't already have (matched by field/op/value/action), global.
    existing_rules = {
        (r.match_field, r.match_op, r.match_value, r.action, r.action_arg)
        for r in session.exec(select(Rule))
    }
    for r in bundle.get("rules", []) or []:
        try:
            key = (r.get("match_field"), r.get("match_op"), r.get("match_value"),
                   r.get("action"), r.get("action_arg", ""))
            if key in existing_rules:
                continue
            session.add(Rule(account_id=None, **{k: r[k] for k in (
                "name", "enabled", "order", "match_field", "match_op", "match_value",
                "action", "action_arg") if k in r}))
            res.rules += 1
        except Exception:
            continue

    # Signatures: add by name if missing, as global signatures.
    existing_sig_names = {s.name for s in session.exec(select(Signature))}
    for s in bundle.get("signatures", []) or []:
        try:
            if s.get("name") in existing_sig_names:
                continue
            session.add(Signature(account_id=None, name=s.get("name", "Imported"),
                                   html=s.get("html", ""), inline_images=s.get("inline_images", []),
                                   is_default=False))
            res.signatures += 1
        except Exception:
            continue

    # Sender categories: upsert by email.
    for c in bundle.get("sender_categories", []) or []:
        email = (c.get("email") or "").lower().strip()
        if not email:
            continue
        row = session.exec(select(SenderCategory).where(SenderCategory.email == email)).first()
        if row is None:
            session.add(SenderCategory(email=email, category=c.get("category", "primary")))
        else:
            row.category = c.get("category", row.category)
        res.sender_categories += 1

    session.commit()
    return res
