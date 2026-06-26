"""Background sync engine.

Periodically syncs every enabled account: discovers folders, pulls new message
headers incrementally (UID-based), applies rules to fresh inbox mail, restores
local "done"/"blocked" state, and pushes live events to the UI over the hub.

Blocking IMAP/OAuth work runs in a thread pool; the orchestration is async.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.db import get_engine, index_message_fts
from app.core.security import get_secret_store
from app.core.ws import WebSocketHub
from app.models import (
    Account, Folder, FolderRole, Message, MessageState, Provider, Rule, RuleAction,
)
from app.providers import oauth
from app.providers.base import HeaderInfo
from app.providers.imap_smtp import Auth, ImapSmtpProvider
from app.sync.rules import MessageFields, first_matching_action

log = logging.getLogger("raplmail.sync")

SYNC_INTERVAL_SECONDS = 120
HEADERS_PER_FOLDER_LIMIT = 500  # cap on a single incremental pull


def _make_idle_probe():
    """Return a callable -> seconds since last local input, or None if unsupported.

    Windows: GetLastInputInfo via ctypes. Other platforms aren't supported yet
    (the presence feature simply stays inert there).
    """
    import sys
    if not sys.platform.startswith("win"):
        return None
    import ctypes

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    def idle_seconds() -> float:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        millis = (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return millis / 1000.0

    return idle_seconds


# ---------------------------------------------------------------------------
# Provider construction (resolves credentials + refreshes OAuth tokens)
# ---------------------------------------------------------------------------
def build_provider(account: Account) -> ImapSmtpProvider:
    store = get_secret_store()
    secret = store.get(account.secret_key) or ""

    if account.provider == Provider.imap:
        auth = Auth(mechanism="plain", user=account.email, secret=secret)
        return ImapSmtpProvider(auth, account.imap_host, account.imap_port,
                                account.smtp_host, account.smtp_port)

    if account.provider == Provider.gmail:
        bundle = oauth.deserialize_bundle(secret)
        token, bundle = oauth.google_access_token(bundle)
        store.set(account.secret_key, oauth.serialize_bundle(bundle))
        auth = Auth(mechanism="xoauth2", user=account.email, secret=token)
        return ImapSmtpProvider(auth, oauth.GMAIL_IMAP_HOST, 993, oauth.GMAIL_SMTP_HOST, 587)

    if account.provider == Provider.m365:
        token, cache_blob = oauth.ms_access_token(secret)
        store.set(account.secret_key, cache_blob)
        auth = Auth(mechanism="xoauth2", user=account.email, secret=token)
        return ImapSmtpProvider(auth, oauth.MS_IMAP_HOST, 993, oauth.MS_SMTP_HOST, 587)

    raise ValueError(f"unknown provider {account.provider}")


class SyncManager:
    def __init__(self, hub: WebSocketHub):
        self._hub = hub
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sync")
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._wake = asyncio.Event()
        self._last_contact_scan = 0.0
        self._loop_ref: asyncio.AbstractEventLoop | None = None
        # IMAP IDLE watchers (near-instant new-mail push), one per account.
        self._idle: dict[int, dict] = {}
        self._idle_stop = threading.Event()
        self._presence_thread: threading.Thread | None = None
        # Per-account live health for the dashboard (in-memory; reset on restart).
        self._health: dict[int, dict] = {}
        # Morning-digest scheduler: the local date we last delivered a brief.
        self._last_digest_day: str | None = None

    def _set_health(self, account_id: int, **fields) -> None:
        self._health.setdefault(account_id, {}).update(fields)

    def health_snapshot(self) -> dict[int, dict]:
        """Per-account status: last sync time/result, error, IDLE state."""
        snap: dict[int, dict] = {}
        for aid, h in self._health.items():
            idle = self._idle.get(aid)
            snap[aid] = {**h, "idle_active": bool(idle and idle.get("connected"))}
        return snap

    async def start(self) -> None:
        self._loop_ref = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._loop())
        # Presence monitor: resurface "until I'm back" mail when the user returns.
        self._presence_thread = threading.Thread(target=self._presence_watch, daemon=True,
                                                  name="presence")
        self._presence_thread.start()

    async def stop(self) -> None:
        self._stopping.set()
        self._idle_stop.set()
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)

    def request_sync(self) -> None:
        """Wake the loop to sync immediately (e.g. after adding an account)."""
        self._wake.set()

    def request_sync_threadsafe(self) -> None:
        """Wake the loop from a worker thread (e.g. an IDLE watcher)."""
        if self._loop_ref:
            self._loop_ref.call_soon_threadsafe(self._wake.set)

    def _ensure_idle(self, account_ids: list[int]) -> None:
        """Start an IDLE watcher thread per account; reap watchers for gone accounts."""
        for aid in account_ids:
            if aid not in self._idle:
                t = threading.Thread(target=self._idle_watch, args=(aid,), daemon=True,
                                     name=f"idle-{aid}")
                self._idle[aid] = {"thread": t}
                t.start()
        for aid in list(self._idle):
            if aid not in account_ids:
                self._idle.pop(aid, None)  # thread exits on next account check

    def _idle_watch(self, account_id: int) -> None:
        """Hold an IMAP IDLE connection on INBOX; on activity, trigger a sync.
        Best-effort: any error backs off and reconnects; polling still covers us."""
        while not self._idle_stop.is_set() and account_id in self._idle:
            provider = None
            try:
                with Session(get_engine()) as session:
                    account = session.get(Account, account_id)
                    if account is None or not account.enabled:
                        return
                provider = build_provider(account)
                client = provider._imap()
                if not client.has_capability("IDLE"):
                    return  # server doesn't support IDLE; rely on polling
                client.select_folder("INBOX")
                client.idle()
                if account_id in self._idle:
                    self._idle[account_id]["connected"] = True
                while not self._idle_stop.is_set() and account_id in self._idle:
                    responses = client.idle_check(timeout=60)
                    if responses:
                        client.idle_done()
                        self.request_sync_threadsafe()
                        client.idle()
                try:
                    client.idle_done()
                except Exception:
                    pass
            except Exception:
                if account_id in self._idle:
                    self._idle[account_id]["connected"] = False
                self._idle_stop.wait(15)  # back off, then reconnect
            finally:
                if provider:
                    try:
                        provider.close()
                    except Exception:
                        pass

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.sync_all()
            except Exception:
                log.exception("sync_all failed")
            try:
                await self._process_scheduled()
            except Exception:
                log.exception("scheduled send processing failed")
            try:
                await self._process_action_queue()
            except Exception:
                log.exception("action queue processing failed")
            try:
                from app.providers.pool import pool
                await asyncio.get_running_loop().run_in_executor(self._executor, pool.keepalive)
            except Exception:
                pass
            try:
                await self._maybe_digest()
            except Exception:
                log.exception("morning digest failed")
            with _suppress_timeout():
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=SYNC_INTERVAL_SECONDS)
                except asyncio.TimeoutError:
                    pass
            self._wake.clear()

    async def _process_scheduled(self) -> None:
        if not get_secret_store().is_unlocked:
            return
        from app.api.compose import process_due_scheduled
        loop = asyncio.get_running_loop()
        sent = await loop.run_in_executor(self._executor, process_due_scheduled)
        if sent:
            await self._hub.broadcast("scheduled:sent", {"count": sent})

    async def _process_action_queue(self) -> None:
        if not get_secret_store().is_unlocked:
            return
        from app.api.messages import process_action_queue, queue_counts
        loop = asyncio.get_running_loop()
        flushed = await loop.run_in_executor(self._executor, process_action_queue)
        counts = await loop.run_in_executor(self._executor, queue_counts)
        await self._hub.broadcast("queue", counts)
        if flushed:
            await self._hub.broadcast("sync:done", {"new": 0})

    def _digest_settings(self) -> tuple[bool, int]:
        from app.models import Setting
        with Session(get_engine()) as session:
            row = session.get(Setting, 1)
            data = dict(row.data) if row and row.data else {}
        return bool(data.get("digestEnabled")), int(data.get("digestHour", 8) or 8)

    async def _maybe_digest(self) -> None:
        """Once per day, after the configured morning hour, push an AI inbox brief."""
        if not get_secret_store().is_unlocked:
            return
        enabled, hour = self._digest_settings()
        if not enabled:
            return
        now = datetime.now()  # local time
        today = now.date().isoformat()
        if self._last_digest_day == today or now.hour < hour:
            return
        from app.api.ai import generate_scheduled_digest
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self._executor, generate_scheduled_digest)
        # Mark done for today even if AI is unconfigured, so we don't retry all day.
        self._last_digest_day = today
        if result:
            await self._hub.broadcast("inbox:digest", result)

    async def sync_all(self) -> None:
        store = get_secret_store()
        if not store.is_unlocked:
            return  # cannot decrypt credentials yet
        with Session(get_engine()) as session:
            account_ids = list(session.exec(select(Account.id).where(Account.enabled == True)))  # noqa: E712
        for account_id in account_ids:
            await self.sync_account(account_id)
        self._ensure_idle(account_ids)  # keep near-instant IDLE watchers in sync

    async def sync_account(self, account_id: int) -> None:
        loop = asyncio.get_running_loop()
        now = datetime.now(timezone.utc).isoformat()
        self._set_health(account_id, last_attempt=now, status="syncing")
        try:
            counts = await loop.run_in_executor(self._executor, self._sync_account_blocking, account_id)
        except Exception as exc:
            log.exception("sync failed for account %s", account_id)
            self._set_health(account_id, status="error", last_error=str(exc),
                             last_error_at=datetime.now(timezone.utc).isoformat())
            await self._hub.broadcast("sync:error", {"account_id": account_id})
            return
        self._set_health(account_id, status="ok", last_sync=datetime.now(timezone.utc).isoformat(),
                         last_new=counts.get("new", 0), last_error=None)
        await self._hub.broadcast("sync:done", {"account_id": account_id, **counts})

    # --- blocking worker ----------------------------------------------------
    def _sync_account_blocking(self, account_id: int) -> dict:
        new_count = 0
        previews: list[dict] = []
        account_email = ""
        with Session(get_engine()) as session:
            account = session.get(Account, account_id)
            if account is None:
                return {"new": 0}
            account_email = account.email  # capture before the session closes
            rules = list(session.exec(
                select(Rule).where((Rule.account_id == account_id) | (Rule.account_id == None))  # noqa: E711
            ))
            from app.models import MutedThread, SenderCategory
            overrides = {sc.email.lower(): sc.category for sc in session.exec(select(SenderCategory))}
            muted = {r.thread_key for r in session.exec(select(MutedThread))}
            provider = build_provider(account)
            try:
                self._sync_folders(session, account, provider)
                folders = list(session.exec(select(Folder).where(Folder.account_id == account_id)))
                for folder in folders:
                    try:
                        new_count += self._sync_folder(session, account, folder, provider, rules, overrides, previews, muted)
                    except Exception:
                        # One unselectable/odd folder shouldn't abort the whole account.
                        log.exception("folder sync failed: account %s folder %s", account_id, folder.path)
            finally:
                provider.close()
            session.commit()
            # Refresh the smart address book — throttled, since it scans all mail
            # and we don't want it hogging the CPU on every sync tick.
            import time
            now = time.time()
            if new_count > 0 and now - self._last_contact_scan > 300:
                self._last_contact_scan = now
                try:
                    from app.sync.contacts import scan_contacts
                    scan_contacts(session)
                except Exception:
                    log.exception("contact scan failed for account %s", account_id)
        preview = None
        if previews:
            previews.sort(key=lambda p: p.get("date") or "", reverse=True)
            preview = previews[0]
        return {"new": new_count, "preview": preview, "account": account_email}

    def _sync_folders(self, session: Session, account: Account, provider) -> None:
        existing = {f.path: f for f in session.exec(
            select(Folder).where(Folder.account_id == account.id))}
        for info in provider.list_folders():
            folder = existing.get(info.path)
            if folder is None:
                folder = Folder(account_id=account.id, name=info.name, path=info.path,
                                role=FolderRole(info.role) if info.role in FolderRole._value2member_map_ else FolderRole.other)
                session.add(folder)
            else:
                folder.name = info.name
        session.flush()

    def _sync_folder(self, session: Session, account: Account, folder: Folder,
                     provider, rules: list[Rule], overrides: dict[str, str] | None = None,
                     previews: list[dict] | None = None, muted: set | None = None) -> int:
        max_uid = session.exec(
            select(func.max(Message.uid)).where(Message.folder_id == folder.id)
        ).one()
        min_uid = (max_uid or 0) + 1
        headers = provider.fetch_headers(folder.path, min_uid=min_uid, limit=HEADERS_PER_FOLDER_LIMIT)
        new_count = 0
        for h in headers:
            if h.uid < min_uid:
                continue
            msg = self._upsert_message(session, account, folder, h, overrides or {})
            if msg is None:
                continue
            new_count += 1
            # Restore durable local state by Message-ID.
            self._restore_state(session, account, msg)
            # Muted conversation: auto-done new replies so they never hit the inbox.
            if muted and msg.thread_id in muted and not msg.is_done:
                msg.is_done = True
                self._mark_state_done(session, account, msg)
            # Run rules on fresh inbox mail only.
            if folder.role == FolderRole.inbox and not msg.is_done:
                self._apply_rules(session, account, folder, msg, provider, rules)
            # Collect a preview for desktop notifications (inbox, still-unread).
            if previews is not None and folder.role == FolderRole.inbox and not msg.is_done:
                previews.append({
                    "from": msg.from_name or msg.from_addr or "",
                    "from_addr": msg.from_addr or "",
                    "subject": msg.subject or "(no subject)",
                    "date": (msg.date.isoformat() if getattr(msg, "date", None) else ""),
                })
        return new_count

    def _upsert_message(self, session: Session, account: Account, folder: Folder,
                        h: HeaderInfo, overrides: dict[str, str] | None = None) -> Message | None:
        existing = session.exec(
            select(Message).where(Message.folder_id == folder.id, Message.uid == h.uid)
        ).first()
        if existing is not None:
            return None
        from app.providers.imap_smtp import decode_mime_words
        from app.sync.categorize import categorize
        from app.sync.threading import thread_key
        subject = decode_mime_words(h.subject)
        from_name = decode_mime_words(h.from_name)
        category = (overrides or {}).get((h.from_addr or "").lower()) \
            or categorize(h.from_addr, from_name, subject, h.snippet)
        msg = Message(
            account_id=account.id, folder_id=folder.id, uid=h.uid,
            message_id=h.message_id, from_addr=h.from_addr, from_name=from_name,
            to_addrs=h.to_addrs, cc_addrs=h.cc_addrs, subject=subject,
            snippet=h.snippet, date=h.date,
            thread_id=thread_key(account.id, subject, h.uid),
            is_seen="\\Seen" in h.flags, is_flagged="\\Flagged" in h.flags,
            is_answered="\\Answered" in h.flags, has_attachments=h.has_attachments,
            size=h.size,
            category=category,
        )
        session.add(msg)
        session.flush()  # assign id for FTS rowid
        index_message_fts(session, msg.id, subject=msg.subject, from_addr=msg.from_addr,
                          from_name=msg.from_name, snippet=msg.snippet, body="")
        return msg

    def _restore_state(self, session: Session, account: Account, msg: Message) -> None:
        if not msg.message_id:
            return
        state = session.exec(
            select(MessageState).where(MessageState.account_id == account.id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state:
            msg.is_done = state.is_done
            msg.snooze_until = state.snooze_until
            msg.snooze_presence = getattr(state, "snooze_presence", False)
            msg.pinned = getattr(state, "is_pinned", False)

    def _mark_state_done(self, session: Session, account: Account, msg: Message) -> None:
        if not msg.message_id:
            return
        state = session.exec(
            select(MessageState).where(MessageState.account_id == account.id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state is None:
            state = MessageState(account_id=account.id, message_id=msg.message_id)
            session.add(state)
        state.is_done = True

    # --- presence (Smart Snooze "until I'm back") ---------------------------
    def _presence_watch(self) -> None:
        """Watch local input idle time; when the user returns after being away,
        resurface mail snoozed 'until I'm back'. Windows-only (no-ops elsewhere)."""
        AWAY_SECONDS = 300  # consider "away" after 5 min idle
        try:
            idle_seconds = _make_idle_probe()
        except Exception:
            return  # platform not supported
        if idle_seconds is None:
            return
        was_away = False
        while not self._idle_stop.is_set():
            try:
                idle = idle_seconds()
            except Exception:
                return
            if idle >= AWAY_SECONDS:
                was_away = True
            elif was_away and idle < 5:
                was_away = False
                self._resurface_presence()
            self._idle_stop.wait(5)

    def _resurface_presence(self) -> None:
        with Session(get_engine()) as session:
            rows = list(session.exec(select(Message).where(Message.snooze_presence == True)))  # noqa: E712
            if not rows:
                return
            for m in rows:
                m.snooze_until = None
                m.snooze_presence = False
                if m.message_id:
                    st = session.exec(
                        select(MessageState).where(MessageState.account_id == m.account_id,
                                                   MessageState.message_id == m.message_id)
                    ).first()
                    if st:
                        st.snooze_until = None
                        st.snooze_presence = False
            session.commit()
            count = len(rows)
        # Nudge the UI to refresh.
        if self._loop_ref:
            import asyncio as _asyncio
            try:
                _asyncio.run_coroutine_threadsafe(
                    self._hub.broadcast("presence:back", {"count": count}), self._loop_ref)
            except Exception:
                pass

    def _apply_rules(self, session: Session, account: Account, folder: Folder,
                     msg: Message, provider, rules: list[Rule]) -> None:
        rule = first_matching_action(rules, MessageFields.from_message(msg))
        if rule is None:
            return
        try:
            if rule.action == RuleAction.mark_read:
                provider.set_flags(folder.path, msg.uid, [b"\\Seen"], add=True)
                msg.is_seen = True
            elif rule.action == RuleAction.mark_done:
                msg.is_done = True
                self._persist_state(session, account, msg, done=True)
            elif rule.action in (RuleAction.move, RuleAction.archive):
                dest = rule.action_arg or self._role_folder(session, account, FolderRole.archive)
                if dest:
                    provider.move(folder.path, msg.uid, dest)
                    session.delete(msg)  # it now lives in dest; will resync there
            elif rule.action == RuleAction.delete:
                provider.delete(folder.path, msg.uid)
                session.delete(msg)
            elif rule.action == RuleAction.block:
                self._persist_state(session, account, msg, blocked=True)
                junk = self._role_folder(session, account, FolderRole.junk)
                if junk:
                    provider.move(folder.path, msg.uid, junk)
                else:
                    provider.delete(folder.path, msg.uid)
                session.delete(msg)
        except Exception:
            log.exception("rule action %s failed on uid %s", rule.action, msg.uid)

    def _persist_state(self, session: Session, account: Account, msg: Message,
                       *, done: bool | None = None, blocked: bool | None = None) -> None:
        if not msg.message_id:
            return
        state = session.exec(
            select(MessageState).where(MessageState.account_id == account.id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state is None:
            state = MessageState(account_id=account.id, message_id=msg.message_id)
            session.add(state)
        if done is not None:
            state.is_done = done
        if blocked is not None:
            state.is_blocked = blocked

    def _role_folder(self, session: Session, account: Account, role: FolderRole) -> str | None:
        f = session.exec(
            select(Folder).where(Folder.account_id == account.id, Folder.role == role)
        ).first()
        return f.path if f else None


class _suppress_timeout:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        return exc_type is asyncio.TimeoutError
