"""App settings persistence + config export/import.

UI/behavior settings are stored as a single JSON blob in the DB (a file), so
they survive restarts and move with the data. Export bundles the settings plus
the config that isn't re-syncable (rules, signatures, sender categories) so you
can carry a setup from dev to prod. Emails themselves live on the mail server
and re-sync once accounts are connected, so they're not part of the bundle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Account, Rule, SenderCategory, Setting, Signature

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
    # Merge (not replace): preserve backend-owned keys the frontend doesn't send
    # (e.g. raplDesk instances, googleCalendarEmail), so a UI settings save can't
    # wipe them.
    merged = _get_blob(session)
    merged.update(body.data)
    _set_blob(session, merged)
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
    res = _apply_config(session, bundle)
    session.commit()
    return res


def _apply_config(session: Session, bundle: dict) -> ImportResult:
    """Restore the re-syncable config (settings, rules, signatures, sender tags).
    Does NOT commit - the caller commits. Shared by /import and /import-full."""
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

    return res


_FULL_VERSION = 1
_ACCT_FIELDS = ("email", "display_name", "provider", "imap_host", "imap_port",
                "smtp_host", "smtp_port", "use_oauth", "secret_key", "color",
                "enabled", "aliases")


@router.get("/export-full")
def export_full(session: Session = Depends(get_session)) -> dict:
    """Encrypted full backup (.rmail): everything from /export PLUS accounts and
    their credentials, sealed with the master password. Requires an unlocked vault."""
    import json as _json

    from app.core.security import get_secret_store

    store = get_secret_store()
    if not store.is_unlocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock the vault before exporting.")

    accounts, secrets = [], {}
    for a in session.exec(select(Account)):
        prov = a.provider.value if hasattr(a.provider, "value") else a.provider
        accounts.append({**{k: getattr(a, k) for k in _ACCT_FIELDS if k != "provider"}, "provider": prov})
        if a.secret_key:
            cred = store.get(a.secret_key)
            if cred is not None:
                secrets[a.secret_key] = cred

    bundle = export_bundle(session)
    bundle.update(kind="rmail-full", full_version=_FULL_VERSION, accounts=accounts, secrets=secrets)
    sealed = store.seal(_json.dumps(bundle, default=str).encode("utf-8"))
    sealed["kind"] = "rmail-full"
    return sealed


class ImportFullIn(BaseModel):
    blob: dict
    password: str


class ImportFullResult(ImportResult):
    accounts: int = 0


@router.post("/import-full", response_model=ImportFullResult)
def import_full(body: ImportFullIn, request: Request,
                session: Session = Depends(get_session)) -> ImportFullResult:
    """Restore an encrypted .rmail backup: config, accounts, and credentials.
    Requires an unlocked vault (so restored credentials are re-sealed locally)."""
    import json as _json

    from app.core.security import BadPasswordError, get_secret_store

    store = get_secret_store()
    if not store.is_unlocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set/unlock your master password first.")
    try:
        raw = store.open_sealed(body.blob, body.password)
    except BadPasswordError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    try:
        bundle = _json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "corrupt backup file") from exc

    base = _apply_config(session, bundle)
    res = ImportFullResult(**base.model_dump(), accounts=0)

    # Credentials first, so accounts that reference them are immediately usable.
    for key, cred in (bundle.get("secrets") or {}).items():
        try:
            store.set(key, cred)
        except Exception:
            continue
    existing = {a.email.lower() for a in session.exec(select(Account))}
    for a in bundle.get("accounts") or []:
        email = (a.get("email") or "").lower().strip()
        if not email or email in existing:
            continue
        try:
            session.add(Account(**{k: a[k] for k in _ACCT_FIELDS if k in a}))
            existing.add(email)
            res.accounts += 1
        except Exception:
            continue
    session.commit()
    # Connect the freshly-added accounts: discover folders + pull mail.
    try:
        request.app.state.sync.request_sync()
    except Exception:
        pass
    return res
