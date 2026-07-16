"""Device-to-device sync over the user's own mailbox (0.4.0).

Local-first, no cloud account, no third-party server: one account you already
have carries the sync data. Each change is encrypted (a passphrase-derived key
that never leaves your devices) and APPENDed as a message into a hidden
`RaplMail Sync` folder. The other PC reads that folder, decrypts, and applies.

What travels:
  * Per-message triage state (done / snooze / pin) - the stuff that does NOT
    ride standard IMAP flags, so it never synced before. Keyed by
    (account email, RFC Message-ID) so it resolves to the right mail on the
    other machine regardless of local row ids. Applied straight into
    MessageState, which is also the durable parking lot: if the mail hasn't
    synced yet on the other PC, _restore_state applies it when it does.
  * Rules - automatically, whole-set last-writer-wins by a "rules changed at"
    timestamp (syncRulesTs, bumped by every rule create/edit/delete). The device
    that touched its rules most recently propagates its complete list; a device
    that never touched rules never publishes them, so a fresh install can't wipe
    anyone. Edits and deletes propagate (an add-only merge couldn't carry them).
  * Config (settings / signatures / sender tags, plus rules for back-compat)
    via the existing export bundle, on explicit push/pull only,
    newest-publish-wins. Sync-control keys are stripped both ways so a peer's
    settings can never clobber this device's own sync configuration.

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


def touch_rules_changed(session: Session) -> None:
    """Mark this device's rule set as locally changed. The next sync tick
    publishes the full list; peers adopt it if this timestamp beats theirs."""
    _save(session, {"syncRulesTs": _now_iso()})


def _replace_rules(session: Session, incoming: list[dict]) -> None:
    """LWW adopt: the peer changed its rules more recently, so its complete rule
    set replaces ours. Rules have no per-row identity across devices, so a
    whole-set swap is the only way edits and deletes can propagate."""
    from app.models import Rule
    for r in session.exec(select(Rule)):
        session.delete(r)
    session.flush()
    for r in incoming:
        try:
            session.add(Rule(account_id=None, **{k: r[k] for k in (
                "name", "enabled", "order", "match_field", "match_op",
                "match_value", "action", "action_arg") if k in r}))
        except Exception:
            continue
    session.flush()


def _apply_rules_payload(session: Session, payload: dict) -> bool:
    """Adopt the peer's rule set from a state payload if it's fresher than ours
    (LWW by rules_ts). Returns True when applied. The pushed-cursor is advanced
    to the same ts so we don't echo the adopted set back."""
    rules_ts = payload.get("rules_ts") or ""
    incoming = payload.get("rules")
    if not rules_ts or not isinstance(incoming, list):
        return False
    if rules_ts <= (_blob(session).get("syncRulesTs") or ""):
        return False   # ours is newer or the same - keep it
    _replace_rules(session, incoming)
    _save(session, {"syncRulesTs": rules_ts, "syncRulesPushedTs": rules_ts})
    return True


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


def set_config(session: Session, *, enabled: bool, account_id: int | None, passphrase: str | None,
               device_label: str | None = None) -> None:
    from app.core.security import get_secret_store
    store = get_secret_store()
    if passphrase:
        store.set(PASSPHRASE_KEY, passphrase)
    updates = {
        "syncEnabled": bool(enabled),
        "syncAccountId": account_id,
        "syncFolder": _blob(session).get("syncFolder") or SYNC_FOLDER_DEFAULT,
    }
    if device_label is not None:
        # Empty string clears the custom name; _default_label falls back to hostname.
        updates["syncDeviceLabel"] = device_label.strip()[:40]
    _save(session, updates)
    device_id(session)  # ensure one exists


def status(session: Session) -> dict:
    blob = _blob(session)
    return {
        "enabled": bool(blob.get("syncEnabled")),
        "account_id": blob.get("syncAccountId"),
        "folder": blob.get("syncFolder") or SYNC_FOLDER_DEFAULT,
        "has_passphrase": bool(get_passphrase()),
        "device_id": blob.get("syncDeviceId") or "",
        "device_label": _default_label(session),
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


def _build_state_payload(session: Session, device: str, since: datetime | None, full: bool) -> dict:
    """Automatic payload: per-message triage state only. Config never rides the
    automatic channel - it moves only on an explicit push/pull, so a device that
    hasn't touched its settings can't clobber one that has."""
    return {
        "v": 1,
        "kind": "state",
        "device": device,
        "ts": _now_iso(),
        "states": _collect_states(session, since, full),
    }


def _config_changed_at(session: Session) -> str:
    """Best-effort 'settings last changed' time, shown in the pull picker so you
    can tell which device's config is actually the freshest."""
    from app.models import Setting
    row = session.get(Setting, 1)
    dt = _naive(row.updated_at) if (row and getattr(row, "updated_at", None)) else None
    return (dt or _EPOCH).isoformat()


def _build_config_payload(session: Session, device: str, label: str, version: int) -> dict:
    """Explicit config snapshot: the full export bundle plus a version + real
    change-time, so the receiving device can order snapshots honestly and a
    stale one never wins by mere publish time."""
    from app.api.settings import export_bundle
    bundle = export_bundle(session)
    bundle["settings"] = _strip_sync_keys(bundle.get("settings"))
    return {
        "v": 1,
        "kind": "config",
        "device": device,
        "device_label": label,
        "ts": _now_iso(),
        "config_version": version,
        "config_changed_at": _config_changed_at(session),
        "config": bundle,
    }


def _wrap_message(token: str, account_email: str, device: str, subject: str | None = None) -> bytes:
    """A self-describing RFC822 message carrying the encrypted token. Marked seen
    so it never counts as unread; a plain-language body explains it if the user
    ever sees it in another mail client."""
    msg = EmailMessage()
    msg["From"] = account_email
    msg["To"] = account_email
    msg["Subject"] = subject or "RaplMail settings sync - safe to ignore"
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
            continue   # our copy is newer or equal - keep it
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


def _apply_config_bundle(session: Session, cfg: dict) -> None:
    """Apply a config snapshot onto this device (explicit pull only). Sync-control
    keys are stripped so a peer's bundle can never change this device's own sync
    setup (carrier account / passphrase / cursors). Does NOT commit rules/sigs -
    the caller commits."""
    if not isinstance(cfg, dict):
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


# --- publish / scan -----------------------------------------------------------

def publish(session: Session, account: Account, provider, force_full: bool = False) -> None:
    """Automatic publish: encrypt and append changed triage state, plus the rule
    set when it changed locally (LWW by syncRulesTs). Settings/signatures are
    never published automatically - use push_config for that. force_full appends
    a complete baseline (all local state) - used by compaction so the folder
    always holds a snapshot any peer can rebuild from."""
    passphrase = get_passphrase()
    if not passphrase:
        return
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    since = _parse_iso(blob.get("syncLastPushTs"))
    full = force_full or since is None   # first publish → all local state so a new peer catches up
    payload = _build_state_payload(session, device_id(session), since, full)
    # Rules ride along whenever they changed since the last publish. A device
    # whose rules were never touched (no syncRulesTs) publishes none - so a
    # fresh install can never blank a configured device's rules.
    rules_ts = blob.get("syncRulesTs") or ""
    push_rules = bool(rules_ts) and (full or rules_ts > (blob.get("syncRulesPushedTs") or ""))
    if push_rules:
        from app.api.settings import export_rules
        payload["rules"] = export_rules(session)
        payload["rules_ts"] = rules_ts
    if not payload["states"] and not push_rules:
        return   # nothing changed - skip the round-trip
    fernet = derive_fernet(passphrase)
    token = fernet.encrypt(json.dumps(payload, default=str).encode("utf-8")).decode("ascii")
    provider.ensure_folder(folder)
    provider.append_to_folder(folder, _wrap_message(token, account.email, payload["device"]), seen=True)
    updates = {"syncLastPushTs": payload["ts"]}
    if push_rules:
        updates["syncRulesPushedTs"] = rules_ts
    _save(session, updates)


def scan(session: Session, provider) -> int:
    """Automatic scan: apply incoming triage state. Config snapshots sitting in
    the folder are ignored here - they only apply on an explicit pull_config."""
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
            continue   # not ours / wrong passphrase / corrupt - skip
        if payload.get("device") == my_device:
            continue   # our own message
        handled = False
        states = payload.get("states") or []
        if states:
            ts = apply_states(session, states)
            if ts is not None and (newest_applied is None or ts > newest_applied):
                newest_applied = ts
            handled = True
        if _apply_rules_payload(session, payload):
            handled = True
        if handled:
            applied += 1
        # else: config snapshot or empty - not applied automatically
    updates = {"syncCursorUid": max_uid}
    # Advance the publish cursor past applied remote state so we don't echo it.
    if newest_applied is not None:
        cur_push = _parse_iso(blob.get("syncLastPushTs")) or _EPOCH
        if newest_applied > cur_push:
            updates["syncLastPushTs"] = newest_applied.isoformat()
    _save(session, updates)
    return applied


# --- explicit settings push / pull (manual, user-driven) ----------------------

def _default_label(session: Session) -> str:
    """A human name for this device in the pull picker - the machine hostname if
    we can read it, else the short device id."""
    blob = _blob(session)
    lbl = blob.get("syncDeviceLabel")
    if lbl:
        return lbl
    try:
        import socket
        return socket.gethostname() or device_id(session)[:8]
    except Exception:
        return device_id(session)[:8]


def push_config(session: Session, account: Account, provider) -> dict:
    """Publish this device's settings/rules/signatures/sender-tags as a config
    snapshot the other devices can choose to pull. Bumps a monotonic version."""
    passphrase = get_passphrase()
    if not passphrase:
        raise RuntimeError("Set a sync passphrase first.")
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    version = int(blob.get("syncConfigVersion") or 0) + 1
    payload = _build_config_payload(session, device_id(session), _default_label(session), version)
    fernet = derive_fernet(passphrase)
    token = fernet.encrypt(json.dumps(payload, default=str).encode("utf-8")).decode("ascii")
    provider.ensure_folder(folder)
    provider.append_to_folder(
        folder,
        _wrap_message(token, account.email, payload["device"],
                      subject="RaplMail settings snapshot - safe to ignore"),
        seen=True,
    )
    _save(session, {"syncConfigVersion": version, "syncLastConfigPushAt": payload["ts"]})
    return {"version": version, "at": payload["ts"], "label": payload["device_label"]}


# The sync folder is dominated by frequent state payloads; config pushes are
# rare. Scan newest-first with a budget rather than the whole (possibly large)
# folder so opening the picker stays snappy.
_SNAPSHOT_SCAN_BUDGET = 400


def list_config_snapshots(session: Session, provider) -> list[dict]:
    """Every config snapshot in the folder (newest first, within a scan budget),
    with device + timestamps + a content summary so the user can pick one."""
    passphrase = get_passphrase()
    if not passphrase:
        return []
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    my_device = device_id(session)
    fernet = derive_fernet(passphrase)
    try:
        provider.ensure_folder(folder)
        uids = provider.list_uids(folder)
    except Exception:
        return []
    out: list[dict] = []
    for scanned, uid in enumerate(sorted(uids, reverse=True)):   # newest first
        if scanned >= _SNAPSHOT_SCAN_BUDGET:
            break
        try:
            raw = provider.fetch_raw(folder, uid)
            token = _extract_token(raw)
            if not token:
                continue
            payload = json.loads(fernet.decrypt(token.encode("ascii")).decode("utf-8"))
        except Exception:
            continue
        cfg = payload.get("config")
        if not isinstance(cfg, dict):
            continue   # state-only payload - not a settings snapshot
        settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
        out.append({
            "uid": uid,
            "device": payload.get("device", ""),
            "device_label": payload.get("device_label") or (payload.get("device", "")[:8] or "unknown"),
            "is_me": payload.get("device") == my_device,
            "published_at": payload.get("ts", ""),
            "config_changed_at": payload.get("config_changed_at", ""),
            "version": payload.get("config_version", 0),
            "summary": {
                "settings": len(settings),
                "rules": len(cfg.get("rules") or []),
                "signatures": len(cfg.get("signatures") or []),
                "sender_categories": len(cfg.get("sender_categories") or []),
            },
        })
    out.sort(key=lambda x: (x.get("published_at") or ""), reverse=True)
    return out


def pull_config(session: Session, provider, uid: int) -> dict:
    """Apply the config snapshot at `uid` onto this device (explicit user action)."""
    passphrase = get_passphrase()
    if not passphrase:
        raise RuntimeError("Set a sync passphrase first.")
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    fernet = derive_fernet(passphrase)
    provider.ensure_folder(folder)
    raw = provider.fetch_raw(folder, uid)
    token = _extract_token(raw)
    if not token:
        raise RuntimeError("That snapshot could not be read.")
    payload = json.loads(fernet.decrypt(token.encode("ascii")).decode("utf-8"))
    cfg = payload.get("config")
    if not isinstance(cfg, dict):
        raise RuntimeError("That message isn't a settings snapshot.")
    _apply_config_bundle(session, cfg)
    session.commit()
    _save(session, {
        "syncLastCfgTs": payload.get("ts"),
        "syncConfigVersion": max(int(blob.get("syncConfigVersion") or 0),
                                 int(payload.get("config_version") or 0)),
    })
    return {"applied": True, "version": payload.get("config_version", 0),
            "label": payload.get("device_label") or payload.get("device", "")[:8]}


# --- encrypted credential sync (opt-in, second independent key) ------------
# Account passwords / OAuth tokens are the crown jewels, so they get their OWN
# lock on top of the sync channel, keyed by a secret that NEVER travels over the
# mailbox (a dedicated credential passphrase, or the reused master password).
#
# Two independent envelopes:
#   inner: ChaCha20-Poly1305 AEAD over the credential bundle, key = Argon2id of
#          the credential secret with a RANDOM per-publish salt (not the sync
#          channel's fixed salt) + random 96-bit nonce. AAD binds it to this
#          message kind + the origin device so it can't be replayed/mistyped.
#   outer: the normal sync Fernet (sync passphrase), so the blob is even
#          invisible without the sync passphrase.
# Result: an attacker with the whole mailbox AND the sync passphrase still can't
# read credentials - they'd need the credential secret, and Argon2id makes an
# offline guess against the AEAD blob expensive.
_CRED_AAD = b"raplmail-creds-v1"
_CRED_SUBJECT = "RaplMail credential vault - safe to ignore"
_ACCT_SYNC_FIELDS = ("email", "display_name", "imap_host", "imap_port", "smtp_host",
                     "smtp_port", "use_oauth", "secret_key", "color", "enabled", "aliases")


def _cred_key(secret: str, salt: bytes) -> bytes:
    """32 raw bytes for ChaCha20-Poly1305, via the same Argon2id KDF the vault
    uses (its output is urlsafe-b64 of the 32-byte hash - decode back to raw)."""
    from app.core.security import _derive_key
    return base64.urlsafe_b64decode(_derive_key(secret, salt))


def _gather_credentials(session: Session) -> list[dict]:
    """Every account plus its vault-held secret (password / OAuth bundle).
    Requires an unlocked vault - the secrets are sealed at rest."""
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.is_unlocked:
        raise RuntimeError("Unlock the vault first.")
    out = []
    for a in session.exec(select(Account)):
        prov = a.provider.value if hasattr(a.provider, "value") else a.provider
        entry = {k: getattr(a, k) for k in _ACCT_SYNC_FIELDS}
        entry["provider"] = prov
        entry["secret"] = store.get(a.secret_key) if a.secret_key else None
        out.append(entry)
    return out


def _encrypt_credentials(accounts: list[dict], device: str, secret: str) -> dict:
    import os

    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _cred_key(secret, salt)
    aad = _CRED_AAD + b":" + device.encode("utf-8")
    plaintext = json.dumps({"v": 1, "accounts": accounts}, default=str).encode("utf-8")
    ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    return {
        "v": 1, "kind": "credentials", "device": device,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
        "count": len(accounts),
    }


def _decrypt_credentials(env: dict, secret: str) -> list[dict]:
    """Decrypt the inner AEAD bundle. A wrong secret or any tampering fails the
    Poly1305 tag - surfaced as a clean error, never a partial/garbage result."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    try:
        salt = base64.b64decode(env["salt"])
        nonce = base64.b64decode(env["nonce"])
        ct = base64.b64decode(env["ct"])
        key = _cred_key(secret, salt)
        aad = _CRED_AAD + b":" + (env.get("device") or "").encode("utf-8")
        pt = ChaCha20Poly1305(key).decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise RuntimeError("Incorrect credential passphrase (or the data was tampered with).") from exc
    except Exception as exc:
        raise RuntimeError("That credential snapshot could not be read.") from exc
    data = json.loads(pt.decode("utf-8"))
    return data.get("accounts") or []


def push_credentials(session: Session, account: Account, provider, secret: str) -> dict:
    """Publish this device's account credentials as an encrypted vault snapshot.
    Requires the vault unlocked (to read secrets) and the sync passphrase set."""
    if not get_passphrase():
        raise RuntimeError("Set a sync passphrase first.")
    if not secret or len(secret) < 8:
        raise RuntimeError("The credential passphrase must be at least 8 characters.")
    accounts = _gather_credentials(session)
    if not accounts:
        raise RuntimeError("No accounts to sync.")
    device = device_id(session)
    env = _encrypt_credentials(accounts, device, secret)
    env["device_label"] = _default_label(session)
    env["ts"] = _now_iso()
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    token = derive_fernet(get_passphrase()).encrypt(
        json.dumps(env, default=str).encode("utf-8")).decode("ascii")
    provider.ensure_folder(folder)
    provider.append_to_folder(folder, _wrap_message(token, account.email, device,
                                                    subject=_CRED_SUBJECT), seen=True)
    _save(session, {"syncCredPushAt": env["ts"]})
    return {"count": env["count"], "at": env["ts"], "label": env["device_label"]}


def _fetch_cred_env(session: Session, provider, uid: int) -> dict:
    """Outer-decrypt (sync passphrase) the message at uid and confirm it's a
    credential snapshot. Does NOT touch the inner AEAD - no credential secret
    needed here (that's the picker path)."""
    passphrase = get_passphrase()
    if not passphrase:
        raise RuntimeError("Set a sync passphrase first.")
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    provider.ensure_folder(folder)
    raw = provider.fetch_raw(folder, uid)
    token = _extract_token(raw)
    if not token:
        raise RuntimeError("That snapshot could not be read.")
    env = json.loads(derive_fernet(passphrase).decrypt(token.encode("ascii")).decode("utf-8"))
    if env.get("kind") != "credentials":
        raise RuntimeError("That message isn't a credential snapshot.")
    return env


def list_credential_snapshots(session: Session, provider) -> list[dict]:
    """Credential snapshots in the folder (newest first) - metadata only. Emails
    and secrets stay sealed inside the AEAD; the picker shows device + count +
    time, and the real account list only appears after the secret is entered."""
    passphrase = get_passphrase()
    if not passphrase:
        return []
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    my_device = device_id(session)
    fernet = derive_fernet(passphrase)
    try:
        provider.ensure_folder(folder)
        uids = provider.list_uids(folder)
    except Exception:
        return []
    out: list[dict] = []
    for scanned, uid in enumerate(sorted(uids, reverse=True)):
        if scanned >= _SNAPSHOT_SCAN_BUDGET:
            break
        try:
            raw = provider.fetch_raw(folder, uid)
            token = _extract_token(raw)
            if not token:
                continue
            env = json.loads(fernet.decrypt(token.encode("ascii")).decode("utf-8"))
        except Exception:
            continue
        if env.get("kind") != "credentials":
            continue
        out.append({
            "uid": uid,
            "device": env.get("device", ""),
            "device_label": env.get("device_label") or (env.get("device", "")[:8] or "unknown"),
            "is_me": env.get("device") == my_device,
            "published_at": env.get("ts", ""),
            "count": int(env.get("count") or 0),
        })
    out.sort(key=lambda x: (x.get("published_at") or ""), reverse=True)
    return out


def preview_credentials(session: Session, provider, uid: int, secret: str) -> list[dict]:
    """Decrypt a credential snapshot and list its accounts (email + provider +
    whether this device already has that account) so the user can choose which
    to import. No account is created here."""
    env = _fetch_cred_env(session, provider, uid)
    accounts = _decrypt_credentials(env, secret)
    existing = {a.email.lower() for a in session.exec(select(Account))}
    return [{"email": e.get("email", ""), "provider": e.get("provider", ""),
             "exists": (e.get("email") or "").lower() in existing}
            for e in accounts if e.get("email")]


def apply_credentials(session: Session, provider, uid: int, secret: str,
                      emails: list[str] | None) -> dict:
    """Import the chosen accounts (+ their secrets) from a credential snapshot.
    Skips accounts already present locally; never overwrites an existing one."""
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.is_unlocked:
        raise RuntimeError("Unlock the vault first.")
    env = _fetch_cred_env(session, provider, uid)
    accounts = _decrypt_credentials(env, secret)
    want = {(e or "").lower() for e in (emails or [])}
    existing = {a.email.lower() for a in session.exec(select(Account))}
    imported = 0
    for e in accounts:
        email = (e.get("email") or "").lower().strip()
        if not email or email in existing:
            continue
        if want and email not in want:
            continue
        try:
            fields = {k: e[k] for k in _ACCT_SYNC_FIELDS if k in e}
            fields["provider"] = e.get("provider", "imap")
            acct = Account(**fields)
            session.add(acct)
            session.flush()   # assign secret_key-referenced row / id
            sec_val = e.get("secret")
            if e.get("secret_key") and sec_val is not None:
                store.set(e["secret_key"], sec_val)
            existing.add(email)
            imported += 1
        except Exception:
            log.exception("credential import failed for one account")
            continue
    session.commit()
    return {"imported": imported}


# --- op-log compaction ----------------------------------------------------
# The sync folder grows one message per publish, forever. Past this size, old
# increments are deleted - AFTER appending one full state baseline, so any peer
# (even one offline for months) can still rebuild from the newest snapshot.
_COMPACT_THRESHOLD = 400      # start compacting past this many messages
_COMPACT_KEEP_NEWEST = 150    # recent increments always kept (any kind)
_COMPACT_KEEP_CONFIG = 20     # settings snapshots kept for the pull picker
_COMPACT_MAX_DELETE = 150     # per tick, so one compaction can't stall a sync


def compact(session: Session, account: Account, provider) -> int:
    """Compact the sync folder once it outgrows _COMPACT_THRESHOLD. Publishes a
    full baseline first, then deletes old messages - keeping the newest
    _COMPACT_KEEP_NEWEST of any kind plus the newest _COMPACT_KEEP_CONFIG
    settings snapshots (identified by their subject, which we wrote ourselves;
    no decryption needed). Returns the number of deleted messages."""
    if not get_passphrase():
        return 0
    blob = _blob(session)
    folder = blob.get("syncFolder") or SYNC_FOLDER_DEFAULT
    try:
        uids = sorted(provider.list_uids(folder))
    except Exception:
        return 0
    if len(uids) <= _COMPACT_THRESHOLD:
        return 0
    publish(session, account, provider, force_full=True)   # baseline before any delete
    candidates = uids[:-_COMPACT_KEEP_NEWEST]
    deleted = kept_config = 0
    from email import message_from_bytes
    for uid in reversed(candidates):   # newest-first so the newest old configs survive
        if deleted >= _COMPACT_MAX_DELETE:
            break
        try:
            raw = provider.fetch_raw(folder, uid)
            subject = str(message_from_bytes(raw).get("Subject") or "")
        except Exception:
            continue
        if "settings snapshot" in subject.lower() and kept_config < _COMPACT_KEEP_CONFIG:
            kept_config += 1
            continue
        if "credential vault" in subject.lower():
            continue   # never prune credential snapshots - the only copy of a
                       # password may live here for a device that later dies
        try:
            provider.delete(folder, uid)
            deleted += 1
        except Exception:
            continue
    if deleted:
        log.info("device sync compacted %d old message(s) from %r", deleted, folder)
    return deleted


def tick(session: Session, account: Account, provider) -> None:
    """One publish+scan+compact cycle for the sync account. Best-effort - never
    let a sync-channel hiccup break the normal mail sync."""
    if not is_sync_account(session, account.id):
        return
    try:
        publish(session, account, provider)
        scan(session, provider)
        compact(session, account, provider)
        _save(session, {"syncLastAt": _now_iso(), "syncLastError": ""})
    except Exception as exc:  # noqa: BLE001
        log.exception("device sync tick failed")
        _save(session, {"syncLastError": str(exc)})
