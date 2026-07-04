"""Device-to-device sync over the user's own mailbox (0.4.0).

Local-first, no cloud account, no third-party server: one account you already
have carries the sync data. Each change is encrypted (a passphrase-derived key
that never leaves your devices) and APPENDed as a message into a hidden
`RaplMail Sync` folder. The other PC reads that folder, decrypts, and applies.

What travels:
  * Per-message triage state (done / snooze / pin) — the stuff that does NOT
    ride standard IMAP flags, so it never synced before. Keyed by
    (account email, RFC Message-ID) so it resolves to the right mail on the
    other machine regardless of local row ids. Applied straight into
    MessageState, which is also the durable parking lot: if the mail hasn't
    synced yet on the other PC, _restore_state applies it when it does.
  * Config (settings / rules / signatures / sender tags) via the existing
    export bundle, newest-publish-wins. Sync-control keys are stripped both ways
    so a peer's settings can never clobber this device's own sync configuration.

Last-writer-wins by MessageState.updated_at. The publish cursor (syncLastPushTs)
is advanced past applied remote state so we don't echo it back.
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Account, Message, MessageState

log = logging.getLogger("raplmail.devicesync")

SYNC_FOLDER_DEFAULT = "RaplMail Sync"
SYNC_HEADER = "X-RaplMail-Sync"
DEVICE_HEADER = "X-RaplMail-Device"
PASSPHRASE_KEY = "__sync_passphrase__"   # vault key
_BEGIN = "-----BEGIN RAPLMAIL SYNC-----"
_END = "-----END RAPLMAIL SYNC-----"
# Fixed salt: a shared passphrase must derive the SAME key on every device, so
# the salt can't be random. Argon2's cost still makes the passphrase expensive
# to brute-force; enforce a decent length in the UI.
_SYNC_SALT = b"RaplMail-DeviceSync-v1-salt\x00\x00"

_EPOCH = datetime(1970, 1, 1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _naive(dt: datetime | None) -> datetime | None:
    """Normalize to naive-UTC. MessageState.updated_at is stored naive by SQLite
    but is tz-aware in memory before a reload (utcnow() is aware), so every
    comparison must go through here or naive-vs-aware raises TypeError."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return _naive(datetime.fromisoformat(s))
    except (ValueError, TypeError):
        return None


def derive_fernet(passphrase: str):
    """Fernet from the sync passphrase (Argon2 + fixed salt), matching on every device."""
    from cryptography.fernet import Fernet

    from app.core.security import _derive_key
    return Fernet(_derive_key(passphrase, _SYNC_SALT))


# --- device-local sync config (lives in the settings blob, never synced) -----

def _blob(session: Session) -> dict:
    from app.api.settings import _get_blob
    return _get_blob(session)


def _save(session: Session, updates: dict) -> None:
    from app.api.settings import _get_blob, _set_blob
    blob = _get_blob(session)
    blob.update(updates)
    _set_blob(session, blob)


def device_id(session: Session) -> str:
    blob = _blob(session)
    did = blob.get("syncDeviceId")
    if not did:
        did = uuid.uuid4().hex
        _save(session, {"syncDeviceId": did})
    return did


def _strip_sync_keys(settings: dict) -> dict:
    """Drop device-local sync-control keys so they're never propagated to (or
    overwritten on) another machine."""
    return {k: v for k, v in (settings or {}).items() if not k.startswith("sync")}


def get_passphrase() -> str | None:
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.is_unlocked:
        return None
    return store.get(PASSPHRASE_KEY)


def set_config(session: Session, *, enabled: bool, account_id: int | None, passphrase: str | None) -> None:
    from app.core.security import get_secret_store
    store = get_secret_store()
    if passphrase:
        store.set(PASSPHRASE_KEY, passphrase)
    _save(session, {
        "syncEnabled": bool(enabled),
        "syncAccountId": account_id,
        "syncFolder": _blob(session).get("syncFolder") or SYNC_FOLDER_DEFAULT,
    })
    device_id(session)  # ensure one exists


def status(session: Session) -> dict:
    blob = _blob(session)
    return {
        "enabled": bool(blob.get("syncEnabled")),
        "account_id": blob.get("syncAccountId"),
        "folder": blob.get("syncFolder") or SYNC_FOLDER_DEFAULT,
        "has_passphrase": bool(get_passphrase()),
        "device_id": blob.get("syncDeviceId") or "",
        "last_at": blob.get("syncLastAt") or "",
        "last_error": blob.get("syncLastError") or "",
    }


def is_sync_account(session: Session, account_id: int) -> bool:
    blob = _blob(session)
    return bool(blob.get("syncEnabled")) and blob.get("syncAccountId") == account_id


# --- payload build / parse ----------------------------------------------------

def _collect_states(session: Session, since: datetime | None, full: bool) -> list[dict]:
    """MessageState rows changed since `since` (or all, on first publish), tagged
    with their account's email for cross-device matching."""
    email_by_acct = {a.id: a.email for a in session.exec(select(Account))}
    stmt = select(MessageState)
    if not full and since is not None:
        stmt = stmt.where(MessageState.updated_at != None, MessageState.updated_at > since)  # noqa: E711
    out = []
    for st in session.exec(stmt):
        email = email_by_acct.get(st.account_id)
        if not email or not st.message_id:
            continue
        out.append({
            "email": email.lower(),
            "mid": st.message_id,
            "done": bool(st.is_done),
            "snooze": st.snooze_until.isoformat() if st.snooze_until else None,
            "presence": bool(st.snooze_presence),
            "pinned": bool(st.is_pinned),
            "ts": (st.updated_at or _EPOCH).isoformat(),
        })
    return out


def _build_payload(session: Session, device: str, since: datetime | None, full: bool) -> dict:
    from app.api.settings import export_bundle
    bundle = export_bundle(session)
    bundle["settings"] = _strip_sync_keys(bundle.get("settings"))
    return {
        "v": 1,
        "device": device,
        "ts": _now_iso(),
        "config": bundle,
        "states": _collect_states(session, since, full),
    }


def _wrap_message(token: str, account_email: str, device: str) -> bytes:
    """A self-describing RFC822 message carrying the encrypted token. Marked seen
    so it never counts as unread; a plain-language body explains it if the user
    ever sees it in another mail client."""
    msg = EmailMessage()
    msg["From"] = account_email
    msg["To"] = account_email
    msg["Subject"] = "RaplMail settings sync — safe to ignore"
    msg["Date"] = formatdate(localtime=True)
    msg[SYNC_HEADER] = "1"
    msg[DEVICE_HEADER] = device
    # Wrap the token to short lines and force 7-bit so the mail layer doesn't
    # quoted-printable-mangle the base64 '=' padding or fold it unpredictably;
    # _extract_token strips all whitespace to rejoin it verbatim.
    chunked = "\n".join(token[i:i + 76] for i in range(0, len(token), 76))
    msg.set_content(
        "This is an automated RaplMail sync message. It carries your encrypted "
        "settings and read/done state so your RaplMail installs stay in step.\n\n"
        "It's safe to ignore or delete -- RaplMail re-sends the latest state on the "
        "next change. The contents below are encrypted and unreadable without your "
        "sync passphrase.\n\n"
        f"{_BEGIN}\n{chunked}\n{_END}\n",
        cte="7bit",
    )
    return msg.as_bytes()


def _extract_token(raw: bytes) -> str | None:
    text = raw.decode("utf-8", "replace")
    i = text.find(_BEGIN)
    j = text.find(_END)
    if i < 0 or j < 0 or j <= i:
        return None
    return "".join(text[i + len(_BEGIN):j].split()) or None


# --- apply --------------------------------------------------------------------

def apply_states(session: Session, states: list[dict]) -> datetime | None:
    """Apply incoming per-message state, last-writer-wins by timestamp. Returns
    the newest applied timestamp (to advance the publish cursor past it)."""
    acct_by_email = {a.email.lower(): a.id for a in session.exec(select(Account))}
    newest: datetime | None = None
    for st in states:
        acct_id = acct_by_email.get((st.get("email") or "").lower())
        mid = st.get("mid")
        ts = _parse_iso(st.get("ts")) or _EPOCH
        if not acct_id or not mid:
            continue
        row = session.exec(
            select(MessageState).where(MessageState.account_id == acct_id,
                                       MessageState.message_id == mid)
        ).first()
        local_ts = _naive(row.updated_at) if (row and row.updated_at) else _EPOCH
        if row is not None and ts <= local_ts:
            continue   # our copy is newer or equal — keep it
        if row is None:
            row = MessageState(account_id=acct_id, message_id=mid)
            session.add(row)
        row.is_done = bool(st.get("done"))
        row.snooze_until = _parse_iso(st.get("snooze"))
        row.snooze_presence = bool(st.get("presence"))
        row.is_pinned = bool(st.get("pinned"))
        row.updated_at = ts   # adopt source time so LWW converges (beats onupdate)
        # Reflect onto any live message rows for this Message-ID right now.
        for m in session.exec(select(Message).where(Message.account_id == acct_id,
                                                     Message.message_id == mid)):
            m.is_done = row.is_done
            m.snooze_until = row.snooze_until
            m.snooze_presence = row.snooze_presence
            m.pinned = row.is_pinned
            session.add(m)
        newest = ts if newest is None or ts > newest else newest
    return newest


def _maybe_apply_config(session: Session, payload: dict) -> None:
    """Apply a peer's config if its publish time is newer than the last we applied.
    Sync-control keys are stripped so this device keeps its own sync settings."""
    cfg = payload.get("config")
    if not isinstance(cfg, dict):
        return
    cfg_ts = _parse_iso(payload.get("ts")) or _EPOCH
    last = _parse_iso(_blob(session).get("syncLastCfgTs"))
    if last is not None and cfg_ts <= last:
        return
    from app.api.settings import _apply_config, _get_blob, _set_blob
    incoming = dict(cfg)
    # Merge settings: keep this device's sync-control keys, take the rest.
    if isinstance(incoming.get("settings"), dict):
        merged = _get_blob(session)
        for k, v in _strip_sync_keys(incoming["settings"]).items():
            merged[k] = v
        _set_blob(session, merged)
        incoming = {k: v for k, v in incoming.items() if k != "settings"}
    _apply_config(session, incoming)   # rules / signatures / sender categories
    _save(session, {"syncLastCfgTs": payload.get("ts")})


# --- publish / scan -----------------------------------------------------------

def publish(session: Session, account: Account, provider) -> None:
    passphrase = get_passphrase()
    if not passphrase:
        return
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    since = _parse_iso(blob.get("syncLastPushTs"))
    full = since is None   # first publish → full snapshot so the peer catches up
    payload = _build_payload(session, device_id(session), since, full)
    # Nothing changed and not the first run → skip the round-trip.
    if not full and not payload["states"]:
        # Still refresh config occasionally? Keep it simple: skip when no state
        # changed. Config changes bump state rarely, so publish on demand instead.
        return
    fernet = derive_fernet(passphrase)
    token = fernet.encrypt(json.dumps(payload, default=str).encode("utf-8")).decode("ascii")
    provider.ensure_folder(folder)
    provider.append_to_folder(folder, _wrap_message(token, account.email, payload["device"]), seen=True)
    _save(session, {"syncLastPushTs": payload["ts"]})


def scan(session: Session, provider) -> int:
    passphrase = get_passphrase()
    if not passphrase:
        return 0
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    my_device = device_id(session)
    cursor = int(blob.get("syncCursorUid") or 0)
    fernet = derive_fernet(passphrase)
    try:
        provider.ensure_folder(folder)
        uids = provider.list_uids(folder)
    except Exception:
        return 0
    new_uids = [u for u in uids if u > cursor]
    if not new_uids:
        return 0
    applied = 0
    newest_applied: datetime | None = None
    max_uid = cursor
    for uid in new_uids:
        max_uid = max(max_uid, uid)
        try:
            raw = provider.fetch_raw(folder, uid)
            token = _extract_token(raw)
            if not token:
                continue
            payload = json.loads(fernet.decrypt(token.encode("ascii")).decode("utf-8"))
        except Exception:
            continue   # not ours / wrong passphrase / corrupt — skip
        if payload.get("device") == my_device:
            continue   # our own message
        ts = apply_states(session, payload.get("states") or [])
        _maybe_apply_config(session, payload)
        if ts is not None and (newest_applied is None or ts > newest_applied):
            newest_applied = ts
        applied += 1
    updates = {"syncCursorUid": max_uid}
    # Advance the publish cursor past applied remote state so we don't echo it.
    if newest_applied is not None:
        cur_push = _parse_iso(blob.get("syncLastPushTs")) or _EPOCH
        if newest_applied > cur_push:
            updates["syncLastPushTs"] = newest_applied.isoformat()
    _save(session, updates)
    return applied


def tick(session: Session, account: Account, provider) -> None:
    """One publish+scan cycle for the sync account. Best-effort — never let a
    sync-channel hiccup break the normal mail sync."""
    if not is_sync_account(session, account.id):
        return
    try:
        publish(session, account, provider)
        scan(session, provider)
        _save(session, {"syncLastAt": _now_iso(), "syncLastError": ""})
    except Exception as exc:  # noqa: BLE001
        log.exception("device sync tick failed")
        _save(session, {"syncLastError": str(exc)})
