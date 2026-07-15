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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import get_engine, index_message_fts
from app.core.security import get_secret_store
from app.providers.base import DONE_KEYWORD as _DONE_KW
from app.core.ws import WebSocketHub
from app.models import (
    Account, Folder, FolderRole, Message, MessageState, Provider, Rule, RuleAction,
)
from app.providers import oauth
from app.providers.base import HeaderInfo
from app.providers.imap_smtp import Auth, ImapSmtpProvider
from app.sync.rules import MessageFields, first_matching_action

log = logging.getLogger("raplmail.sync")

SYNC_INTERVAL_SECONDS = 60   # fallback poll; IMAP IDLE pushes new mail sooner
HEADERS_PER_FOLDER_LIMIT = 500  # cap on a single incremental pull


def _make_idle_probe():
    """Return a callable -> seconds since last local input, or None if unsupported.

    Windows: GetLastInputInfo via ctypes. macOS: Quartz's
    CGEventSourceSecondsSinceLastEventType via ctypes (no pyobjc needed).
    Other platforms aren't supported yet (the presence feature stays inert).
    """
    import ctypes
    import sys

    if sys.platform == "darwin":
        try:
            asvc = ctypes.CDLL(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
            )
            fn = asvc.CGEventSourceSecondsSinceLastEventType
        except (OSError, AttributeError):
            return None
        fn.restype = ctypes.c_double
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        COMBINED_SESSION = 1      # kCGEventSourceStateCombinedSessionState
        ANY_INPUT = 0xFFFFFFFF    # kCGAnyInputEventType (~0)

        def idle_seconds_mac() -> float:
            try:
                return float(fn(COMBINED_SESSION, ANY_INPUT))
            except Exception:
                return 0.0

        return idle_seconds_mac

    if not sys.platform.startswith("win"):
        return None

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
        imap_host, imap_port = account.imap_host, account.imap_port
        smtp_host, smtp_port = account.smtp_host, account.smtp_port
        # Heal missing server settings (e.g. an account imported without an SMTP
        # host - the cause of "getaddrinfo failed" on send) from autodiscover.
        if not smtp_host or not imap_host:
            try:
                from app.providers.autodiscover import discover
                d = discover(account.email)
                imap_host = imap_host or d.imap_host
                imap_port = imap_port or d.imap_port
                smtp_host = smtp_host or d.smtp_host
                smtp_port = smtp_port or d.smtp_port
            except Exception:
                pass
        auth = Auth(mechanism="plain", user=account.email, secret=secret)
        return ImapSmtpProvider(auth, imap_host, imap_port, smtp_host, smtp_port)

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
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="sync")
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
            # Outgoing first: flush queued sends/moves BEFORE the (potentially slow)
            # mailbox sync, so a send that fell back to the queue goes out promptly
            # instead of waiting behind a full sync.
            try:
                await self._process_scheduled()
            except Exception:
                log.exception("scheduled send processing failed")
            try:
                await self._process_action_queue()
            except Exception:
                log.exception("action queue processing failed")
            try:
                await self.sync_all()
            except Exception:
                log.exception("sync_all failed")
            try:
                from app.providers.pool import pool
                await asyncio.get_running_loop().run_in_executor(self._executor, pool.keepalive)
            except Exception:
                pass
            try:
                await self._maybe_digest()
            except Exception:
                log.exception("morning digest failed")
            try:
                await self._maybe_embed()
            except Exception:
                log.exception("semantic embedding tick failed")
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

    async def _maybe_embed(self) -> None:
        """Keep the semantic-search index warm: embed a small batch of not-yet-
        indexed messages each cycle. No-op unless the user turned semantic search
        on; index_pending() silently returns 0 if the embedding endpoint is down,
        so a stopped Ollama never spams errors. Bulk (re)indexing of a big backlog
        is the explicit /ai/embed/reindex job - this tick just keeps up with new mail."""
        if not get_secret_store().is_unlocked:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._embed_tick_blocking)

    # Embedding throughput: a bigger batch (one /api/embed request embeds the whole
    # batch on the GPU at once) + back-to-back batches within a wall-clock budget,
    # so a backlog fills fast and the GPU is actually kept busy instead of idling
    # between tiny 48-message batches. Bounded so it yields the GPU each cycle.
    EMBED_BATCH = 128
    EMBED_SECONDS_PER_CYCLE = 20

    def _embed_tick_blocking(self) -> None:
        from app.models import Setting
        with Session(get_engine()) as session:
            row = session.get(Setting, 1)
            data = dict(row.data) if row and row.data else {}
            if not data.get("semanticEnabled"):
                return
            from app.sync import embeddings
            deadline = time.monotonic() + self.EMBED_SECONDS_PER_CYCLE
            while time.monotonic() < deadline:
                if embeddings.index_pending(session, limit=self.EMBED_BATCH) == 0:
                    break   # caught up (or backing off after a failure)

    async def sync_all(self) -> None:
        store = get_secret_store()
        if not store.is_unlocked:
            return  # cannot decrypt credentials yet
        with Session(get_engine()) as session:
            account_ids = list(session.exec(select(Account.id).where(Account.enabled == True)))  # noqa: E712
        # Sync accounts concurrently (was one-at-a-time) - each runs in its own
        # thread, so N mailboxes refresh in parallel instead of serially.
        await asyncio.gather(*(self.sync_account(aid) for aid in account_ids), return_exceptions=True)
        self._ensure_idle(account_ids)  # keep near-instant IDLE watchers in sync

    async def sync_account(self, account_id: int) -> None:
        loop = asyncio.get_running_loop()
        now = datetime.now(timezone.utc).isoformat()
        self._set_health(account_id, last_attempt=now, status="syncing")
        t0 = time.monotonic()
        try:
            counts = await loop.run_in_executor(self._executor, self._sync_account_blocking, account_id)
        except Exception as exc:
            log.exception("sync failed for account %s after %.1fs", account_id, time.monotonic() - t0)
            self._set_health(account_id, status="error", last_error=str(exc),
                             last_error_at=datetime.now(timezone.utc).isoformat())
            await self._hub.broadcast("sync:error", {"account_id": account_id})
            return
        log.info("sync ok: account=%s new=%s in %.1fs", account_id, counts.get("new", 0), time.monotonic() - t0)
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
            # thread_key -> set of muted-conversation sender addresses (empty set
            # = legacy subject-only mute). Used to scope auto-archive on arrival.
            muted = {
                r.thread_key: {p for p in (r.participants or "").split(",") if p}
                for r in session.exec(select(MutedThread))
            }
            # Anti-phishing screening config (Settings → Security): a domain/TLD
            # blocklist that quarantines on arrival + a heuristic spoof flag.
            from app.models import Setting
            from app.sync.screening import normalize_blocklist
            _srow = session.get(Setting, 1)
            _sdata = dict(_srow.data) if _srow and _srow.data else {}
            screen = {
                "blocked_domains": normalize_blocklist(_sdata.get("blockedDomains")),
                "phishing_screen": _sdata.get("phishingScreen", True) is not False,
            }
            provider = build_provider(account)
            try:
                self._sync_folders(session, account, provider)
                folders = list(session.exec(select(Folder).where(Folder.account_id == account_id)))
                for folder in folders:
                    try:
                        new_count += self._sync_folder(session, account, folder, provider, rules, overrides, previews, muted, screen)
                    except IntegrityError:
                        # FK failure mid-sync - typically the account (or folder)
                        # was deleted while this sync was in flight. Roll back so
                        # the session isn't poisoned for the remaining folders.
                        fpath = folder.path  # read before rollback expires the object
                        session.rollback()
                        if session.get(Account, account_id) is None:
                            log.info("account %s deleted mid-sync; aborting", account_id)
                            return {"new": 0}
                        log.exception("integrity error syncing folder %s (account %s)",
                                      fpath, account_id)
                    except Exception as exc:
                        # A folder the server says doesn't exist / can't be selected
                        # (e.g. Gmail's "[Gmail]" \Noselect parent, stored by an
                        # older build) - drop it so it stops erroring every sync.
                        emsg = str(exc)
                        if "NONEXISTENT" in emsg or "Unknown Mailbox" in emsg:
                            log.info("pruning unselectable folder %r (account %s)", folder.path, account_id)
                            self._prune_folder(session, folder)
                        else:
                            # One odd folder shouldn't abort the whole account.
                            log.exception("folder sync failed: account %s folder %s", account_id, folder.path)
                # Device-to-device sync piggybacks on this account's live
                # connection when it's the chosen carrier (best-effort; tick()
                # swallows its own errors so it can't break the mail sync).
                from app.sync import devicesync
                devicesync.tick(session, account, provider)
                # Full-history backfill: page older mail into the cache while the
                # connection is warm, if the user turned it on. Reuses this
                # provider; best-effort so it can't break the forward sync.
                try:
                    self._backfill_account(session, account, provider, muted)
                except Exception:
                    log.exception("history backfill failed for account %s", account_id)
            finally:
                provider.close()
            session.commit()
            # Refresh the smart address book - throttled, since it scans all mail
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
        # `notify` = count of genuinely notify-worthy new inbox mail (drives the
        # desktop notification); `new` = all newly-synced rows across every folder
        # (drives sync bookkeeping / health). Keeping them separate is what stops
        # a Sent/Archive/Junk arrival from firing a phantom empty notification.
        return {"new": new_count, "notify": len(previews), "preview": preview,
                "account": account_email}

    def _prune_folder(self, session: Session, folder: Folder) -> None:
        """Drop a folder row plus its children in FK order (events -> messages ->
        folder); foreign keys are enforced, so deleting the folder alone would
        fail forever and poison every later sync cycle. Best-effort."""
        from sqlalchemy import delete as sa_delete

        from app.models import CalendarEvent
        fpath = folder.path
        try:
            msg_ids = select(Message.id).where(Message.folder_id == folder.id)
            session.exec(sa_delete(CalendarEvent).where(CalendarEvent.message_id.in_(msg_ids)))
            session.exec(sa_delete(Message).where(Message.folder_id == folder.id))
            session.delete(folder)
            session.flush()
        except Exception:
            session.rollback()
            log.exception("failed to prune folder %s", fpath)

    def _sync_folders(self, session: Session, account: Account, provider) -> None:
        from app.sync.devicesync import SYNC_FOLDER_DEFAULT
        existing = {f.path: f for f in session.exec(
            select(Folder).where(Folder.account_id == account.id))}
        for info in provider.list_folders():
            # The device-sync carrier folder is managed out-of-band and must stay
            # invisible - never give it a Folder row (which would list it in the UI).
            if info.name == SYNC_FOLDER_DEFAULT or (info.path or "").endswith(SYNC_FOLDER_DEFAULT):
                continue
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
                     previews: list[dict] | None = None, muted: dict | None = None,
                     screen: dict | None = None) -> int:
        self._check_uidvalidity(session, folder, provider)
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
            # Muted conversation: auto-done new replies so they never hit the
            # inbox - but only when the sender was part of the muted conversation
            # (or it's a legacy subject-only mute with no recorded participants),
            # so a common subject line doesn't mute unrelated strangers.
            if muted and not msg.is_done and msg.thread_id in muted:
                parts = muted[msg.thread_id]
                if not parts or (msg.from_addr or "").strip().lower() in parts:
                    msg.is_done = True
                    self._mark_state_done(session, account, msg)
            # Run rules on fresh mail in the inbox AND custom folders. A server-
            # side filter often files list/automated mail into a subfolder
            # (role "other"); a muted/blocked sender must be caught there too, not
            # only in the inbox. Sent/drafts/trash/junk/archive are left alone.
            notify_ok = True
            if folder.role in (FolderRole.inbox, FolderRole.other) and not msg.is_done:
                # Domain blocklist quarantines on arrival; the heuristic screen only
                # flags. A quarantined mail is gone from the inbox - skip rules +
                # notification for it.
                if self._screen_message(session, account, folder, msg, provider, screen):
                    continue
                notify_ok = self._apply_rules(session, account, folder, msg, provider, rules)
            # Collect a preview for desktop notifications - ONLY for mail the user
            # will actually see arrive: a still-unread inbox message that survived
            # the rules (not moved/deleted/auto-done) and isn't notification-muted.
            # `previews` doubles as the notify count (len), so notifications track
            # genuine inbox arrivals - not new mail that landed in Sent/Archive/Junk
            # or was filtered away, which used to fire empty "New message" popups.
            if (previews is not None and folder.role == FolderRole.inbox
                    and not msg.is_done and notify_ok):
                previews.append({
                    "from": msg.from_name or msg.from_addr or "",
                    "from_addr": msg.from_addr or "",
                    "subject": msg.subject or "(no subject)",
                    "date": (msg.date.isoformat() if getattr(msg, "date", None) else ""),
                })
        self._resync_flags(session, account, folder, provider)
        return new_count

    # --- full-history backfill ----------------------------------------------
    # Wall-clock budget for paging older mail per account per sync cycle. Paging
    # runs back-to-back windows (each HEADERS_PER_FOLDER_LIMIT messages) for this
    # long, then yields so the forward sync stays responsive. Higher = history
    # fills faster; lower = the live sync feels snappier during a big backfill.
    BACKFILL_SECONDS_PER_CYCLE = 20

    def _check_uidvalidity(self, session: Session, folder: Folder, provider) -> None:
        """If the server's UIDVALIDITY for this folder changed, every stored UID is
        stale (it now maps to a different message). Purge the folder's cached
        messages and reset the sync/backfill cursors so it re-syncs cleanly.
        MessageState is keyed by Message-ID (not UID), so done/snooze/pin survive
        and re-apply as the mail comes back."""
        server_uv = provider.folder_uidvalidity(folder.path)
        if server_uv is None:
            return
        if folder.uidvalidity is None:
            folder.uidvalidity = server_uv        # first time we've seen it - record
            session.add(folder)
            return
        if server_uv == folder.uidvalidity:
            return
        log.warning("UIDVALIDITY changed for %s (%s -> %s); purging + resyncing",
                    folder.path, folder.uidvalidity, server_uv)
        self._purge_folder_messages(session, folder)
        folder.uidvalidity = server_uv
        folder.backfill_min_uid = None
        folder.backfill_done = False
        session.add(folder)
        session.flush()

    def _purge_folder_messages(self, session: Session, folder: Folder) -> None:
        """Delete a folder's cached messages (and their derived calendar events)
        but keep the Folder row. FTS is contentless (keyed by rowid), so orphaned
        index entries simply don't resolve - harmless, same as account deletion."""
        from sqlalchemy import delete as sa_delete

        from app.models import CalendarEvent
        msg_ids = select(Message.id).where(Message.folder_id == folder.id)
        session.exec(sa_delete(CalendarEvent).where(CalendarEvent.message_id.in_(msg_ids)))
        session.exec(sa_delete(Message).where(Message.folder_id == folder.id))
        session.flush()

    def _backfill_folder(self, session: Session, account: Account, folder: Folder,
                         provider, muted: dict | None = None, limit: int | None = None) -> int:
        """Page ONE window of older mail (below the current backfill cursor) into
        the cache. Historical mail: no rules, no notifications - just upsert +
        restore local state (+ honor muted threads). Returns the count fetched; 0
        (and sets backfill_done) once the folder is fully paged."""
        if folder.backfill_done:
            return 0
        limit = limit or HEADERS_PER_FOLDER_LIMIT
        cursor = folder.backfill_min_uid
        if cursor is None:
            # Start just below the lowest UID the forward sync already grabbed.
            lowest = session.exec(
                select(func.min(Message.uid)).where(Message.folder_id == folder.id)
            ).one()
            if not lowest:
                # No mail in this folder at all. Forward sync already ran this cycle,
                # so there's genuinely nothing older to page - mark it done so an
                # empty folder (Trash/Junk/Drafts/an empty label…) can't hold overall
                # progress below 100% forever.
                folder.backfill_done = True
                session.add(folder)
                return 0
            cursor = lowest
        if cursor <= 1:
            folder.backfill_done = True
            session.add(folder)
            return 0
        headers = provider.fetch_headers(folder.path, min_uid=1, max_uid=cursor - 1, limit=limit)
        if not headers:
            folder.backfill_done = True
            folder.backfill_min_uid = 1
            session.add(folder)
            return 0
        new_count = 0
        min_seen = cursor
        for h in headers:
            if h.uid < min_seen:
                min_seen = h.uid
            msg = self._upsert_message(session, account, folder, h, {})
            if msg is None:
                continue
            new_count += 1
            self._restore_state(session, account, msg)
            if muted and not msg.is_done and msg.thread_id in muted:
                parts = muted[msg.thread_id]
                if not parts or (msg.from_addr or "").strip().lower() in parts:
                    msg.is_done = True
                    self._mark_state_done(session, account, msg)
        folder.backfill_min_uid = min_seen
        if min_seen <= 1 or len(headers) < limit:
            folder.backfill_done = True   # reached the bottom
        session.add(folder)
        return new_count

    def _backfill_account(self, session: Session, account: Account, provider,
                          muted: dict | None = None) -> int:
        """Page older history for one account if the user enabled it. Runs windows
        back-to-back within a wall-clock budget, then yields; re-runs each sync
        until every folder is fully paged. The per-folder cursor always descends,
        so a window that fetches 0 NEW messages (already cached) still advances -
        we only stop a folder when it marks itself done."""
        from app.api.settings import _get_blob
        if not _get_blob(session).get("backfillHistory"):
            return 0
        deadline = time.monotonic() + self.BACKFILL_SECONDS_PER_CYCLE
        fetched = 0
        errored: set[int] = set()   # folders that errored THIS cycle - retry next sweep
        while time.monotonic() < deadline:
            stmt = select(Folder).where(Folder.account_id == account.id,
                                        Folder.backfill_done == False)  # noqa: E712
            if errored:
                stmt = stmt.where(Folder.id.not_in(errored))
            folder = session.exec(stmt.order_by(Folder.id)).first()
            if folder is None:
                break   # every folder fully paged (or the rest errored this cycle)
            try:
                fetched += self._backfill_folder(session, account, folder, provider, muted)
                session.commit()
            except Exception:
                # Don't let one bad folder wedge the whole backfill: skip it for
                # this cycle (a transient error re-pages on the next sweep).
                log.exception("backfill failed: account %s folder %s", account.id, folder.path)
                session.rollback()
                errored.add(folder.id)
        if fetched:
            log.info("backfilled %s older messages for account %s", fetched, account.id)
        return fetched

    # How many recent messages per folder to re-check FLAGS on each sync, so
    # read/done state changed on another device propagates here too.
    FLAG_RESYNC_WINDOW = 400

    def _resync_flags(self, session: Session, account: Account, folder: Folder, provider) -> None:
        """Pull FLAGS for recent existing messages and reconcile seen/done state
        that may have changed on another device (e.g. the RaplMailDone keyword)."""
        # Flag reconcile touches only flag columns - loading the cached bodies
        # for 400 rows per folder per cycle was the sync loop's biggest churn.
        from sqlalchemy.orm import defer
        rows = session.exec(
            select(Message).options(defer(Message.body_html), defer(Message.body_text))
            .where(Message.folder_id == folder.id)
            .order_by(Message.uid.desc()).limit(self.FLAG_RESYNC_WINDOW)
        ).all()
        if not rows:
            return
        try:
            flagmap = provider.fetch_flags(folder.path, [r.uid for r in rows if r.uid])
        except Exception:
            return
        for m in rows:
            flags = flagmap.get(m.uid)
            if flags is None:
                continue
            # \Seen is a standard flag every server keeps, and we push local
            # changes too - so the server copy is authoritative both ways and
            # read state converges across devices.
            server_seen = "\\Seen" in flags
            if server_seen != m.is_seen:
                m.is_seen = server_seen
                session.add(m)
            server_done = _DONE_KW in flags
            if server_done == m.is_done:
                continue
            # One-directional reconcile of the hero "done" bit. The server may
            # turn done ON (e.g. another device archived this message) and we
            # adopt it. But we must NOT let the server silently turn done OFF for
            # a message marked done locally: the done-keyword push is best-effort
            # and many servers reject custom keywords, so a missing keyword means
            # "the push hasn't landed", not "the user un-done it". Reverting here
            # is what made every local 'done' reappear minutes later. Un-done is
            # the rare case and stays an explicit local action (the Done slider).
            if server_done and not m.is_done:
                m.is_done = True
                self._set_state_done(session, account, m, True)
                session.add(m)

    def _set_state_done(self, session: Session, account: Account, msg: Message, done: bool) -> None:
        if not msg.message_id:
            return
        state = session.exec(
            select(MessageState).where(MessageState.account_id == account.id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state is None:
            state = MessageState(account_id=account.id, message_id=msg.message_id)
            session.add(state)
        state.is_done = done

    def _upsert_message(self, session: Session, account: Account, folder: Folder,
                        h: HeaderInfo, overrides: dict[str, str] | None = None) -> Message | None:
        existing = session.exec(
            select(Message.id).where(Message.folder_id == folder.id, Message.uid == h.uid)
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
        # Prefer real reply-chain threading: a message with In-Reply-To inherits
        # its parent's thread_id (so a Sent reply joins the original's thread even
        # when the recipient set differs). Fall back to subject+participant keying.
        thread_id = ""
        irt = getattr(h, "in_reply_to", "") or ""
        if irt:
            parent_tid = session.exec(
                select(Message.thread_id).where(Message.account_id == account.id,
                                                Message.message_id == irt)
            ).first()
            if parent_tid:
                thread_id = parent_tid
        if not thread_id:
            thread_id = thread_key(account.id, subject, uid=h.uid, folder_id=folder.id,
                                   participants=[h.from_addr, *(h.to_addrs or [])])
        msg = Message(
            account_id=account.id, folder_id=folder.id, uid=h.uid,
            message_id=h.message_id, from_addr=h.from_addr, from_name=from_name,
            to_addrs=h.to_addrs, cc_addrs=h.cc_addrs, subject=subject,
            snippet=h.snippet, date=h.date,
            thread_id=thread_id,
            is_seen="\\Seen" in h.flags, is_flagged="\\Flagged" in h.flags,
            is_answered="\\Answered" in h.flags, has_attachments=h.has_attachments,
            is_done=_DONE_KW in h.flags,   # cross-device "done" mirrored as an IMAP keyword
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
        # The server keyword (set on _to_message) is authoritative for done across
        # devices; fold it together with any local state.
        server_done = bool(msg.is_done)
        state = session.exec(
            select(MessageState).where(MessageState.account_id == account.id,
                                       MessageState.message_id == msg.message_id)
        ).first()
        if state:
            msg.is_done = server_done or state.is_done
            msg.snooze_until = state.snooze_until
            msg.snooze_presence = getattr(state, "snooze_presence", False)
            msg.pinned = getattr(state, "is_pinned", False)
            if server_done and not state.is_done:
                state.is_done = True   # cache another device's "done" locally
        elif server_done:
            self._mark_state_done(session, account, msg)

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

    def _screen_message(self, session: Session, account: Account, folder: Folder,
                        msg: Message, provider, screen: dict | None) -> bool:
        """Anti-phishing screening on a freshly-synced inbox/other message.

        Returns True if the message was QUARANTINED (moved to Junk / deleted) by
        the domain blocklist - the caller then skips rules + notification for it.
        Otherwise returns False; if the heuristic screen is on and the headers look
        spoofed, the message is left in place but flagged `suspicious` (a badge)."""
        if not screen:
            return False
        from app.sync.screening import header_spoof_flags, matches_blocked_domain
        blocked = screen.get("blocked_domains") or []
        if blocked and matches_blocked_domain(msg.from_addr or "", blocked):
            try:
                self._persist_state(session, account, msg, blocked=True)
                junk = self._role_folder(session, account, FolderRole.junk)
                if junk:
                    provider.move(folder.path, msg.uid, junk)
                else:
                    provider.delete(folder.path, msg.uid)
                session.delete(msg)
            except Exception:
                log.exception("domain-block quarantine failed for uid %s", msg.uid)
            return True
        if screen.get("phishing_screen") and header_spoof_flags(msg.from_addr or "", msg.from_name or ""):
            msg.suspicious = True
            session.add(msg)
        return False

    def _apply_rules(self, session: Session, account: Account, folder: Folder,
                     msg: Message, provider, rules: list[Rule]) -> bool:
        """Apply the first matching rule to a freshly-synced message.

        Returns whether the message should still trigger a desktop notification.
        A matched rule always suppresses the "you've got new mail" ding: the mail
        was moved/deleted/read/marked-done, or the user explicitly muted its
        notifications. `mute_notifications` is the only action that leaves the
        message fully delivered (still unread, still in the inbox) - it just
        doesn't ping.
        """
        rule = first_matching_action(rules, MessageFields.from_message(msg))
        if rule is None:
            return True
        try:
            if rule.action == RuleAction.mute_notifications:
                pass  # deliver as normal; only the notification is suppressed
            elif rule.action == RuleAction.mark_read:
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
            elif rule.action == RuleAction.webhook:
                self._fire_webhook(rule.action_arg, msg, account)
            elif rule.action == RuleAction.run_script:
                self._run_script(rule.action_arg, msg, account)
        except Exception:
            log.exception("rule action %s failed on uid %s", rule.action, msg.uid)
        # Webhook/script are side-effects that leave the mail fully delivered, so
        # they still fire the normal new-mail notification; every other action has
        # moved/hidden/muted the message, so it shouldn't ding.
        return rule.action in (RuleAction.webhook, RuleAction.run_script)

    @staticmethod
    def _rule_payload(msg: Message, account: Account) -> dict:
        return {
            "account": account.email or "",
            "from_addr": msg.from_addr or "", "from_name": msg.from_name or "",
            "to": list(msg.to_addrs or []), "cc": list(msg.cc_addrs or []),
            "subject": msg.subject or "", "snippet": msg.snippet or "",
            "date": msg.date.isoformat() if msg.date else "",
            "category": msg.category or "", "message_id": msg.message_id or "",
            "has_attachments": bool(msg.has_attachments),
        }

    def _fire_webhook(self, url: str, msg: Message, account: Account) -> None:
        """POST a small JSON payload to a local automation webhook (n8n / Node-RED
        / Home Assistant). Fire-and-forget with a short timeout; http(s) only."""
        import json as _json
        import urllib.request
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return
        data = _json.dumps(self._rule_payload(msg, account)).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"content-type": "application/json", "user-agent": "RaplMail-rule-webhook"})
        try:
            urllib.request.urlopen(req, timeout=8).close()
        except Exception:
            log.warning("rule webhook POST failed: %s", url)

    def _run_script(self, cmd: str, msg: Message, account: Account) -> None:
        """Launch a user-authored local command on match. The mail context is
        passed via RAPLMAIL_* environment variables (never interpolated into the
        command) so hostile email content can't inject into the shell. The command
        itself is trusted (the user typed it). Fire-and-forget, detached."""
        import os
        import subprocess
        cmd = (cmd or "").strip()
        if not cmd:
            return
        env = dict(os.environ)
        payload = self._rule_payload(msg, account)
        env.update({
            "RAPLMAIL_ACCOUNT": payload["account"],
            "RAPLMAIL_FROM": payload["from_addr"],
            "RAPLMAIL_FROM_NAME": payload["from_name"],
            "RAPLMAIL_SUBJECT": payload["subject"],
            "RAPLMAIL_SNIPPET": payload["snippet"],
            "RAPLMAIL_CATEGORY": payload["category"],
            "RAPLMAIL_MESSAGE_ID": payload["message_id"],
        })
        try:
            subprocess.Popen(cmd, shell=True, env=env,  # noqa: S602 - user-authored command
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL)
        except Exception:
            log.warning("rule script failed to launch: %s", cmd)

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
