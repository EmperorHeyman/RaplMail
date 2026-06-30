# RaplMail — Logical Sweep (Power-User Audit)

> Findings from a logical sweep of the mail client, ranked by how badly they bite a power user.
> Items marked ✓ were verified by reading the actual source lines. Others are high-confidence audit findings.
>
> **Status legend:** `[ ]` open · `[~]` in progress · `[x]` fixed · `[-]` won't fix / deferred

**Fix order:** #4 → #11 → #1 → #2 → #6 → #7 → then the rest.

---

## 🔴 Tier 1 — Silent data loss & "my action didn't stick"

- [x] **#1 ✓ "Done" silently un-dones itself after sync.** — FIXED
  `backend/app/sync/engine.py:438-441` — `_resync_flags` is server-wins (`if server_done != m.is_done: m.is_done = server_done`). The done-keyword IMAP push is best-effort/swallowed; servers that reject custom keywords (Exchange, many vanity hosts) cause every `e` to reappear ~2 min later and overwrite the durable `MessageState`.
  *Fix applied:* made the done-resync one-directional — server may turn done ON (cross-device archive), but never silently OFF a locally-done message. Un-done stays an explicit local action.

- [x] **#2 ✓ A permanently-failed archive/delete hides mail forever.** — FIXED
  `backend/app/api/messages.py:1056-1086` — `pending_action` set at `:1000`, filtered out of every list query at `:148`. After 8 attempts the queue item → `"failed"` but `pending_action` is never reset, so the message vanishes from all views while still on the server.
  *Fix applied:* on `status="failed"`, clear `pending_action` on the affected archive/delete message rows so they reappear in the normal views.

- [x] **#3 ✓ Send Later loses the message on any transient blip.** — FIXED
  `backend/app/api/compose.py:335-346` — scheduled send that throws → `status="failed"`, no retry (immediate sends fall back to the 8-attempt `ActionQueue`). `list_scheduled` only returns `pending`, so it disappears from the Scheduled view too.
  *Fix applied:* on failure the payload is handed to the resilient `ActionQueue` (8 retries w/ backoff), same path as a failed immediate send. ⚠ follow-up: `_deliver_blocking` re-embeds a fresh read-receipt pixel each delivery — dedupe before relying on retries heavily.

- [x] **#4 ✓ The new "auto-heal IMAP" path is dead code that throws.** — FIXED
  `backend/app/api/compose.py:256` references `Provider.imap`, but `Provider` is never imported (`:15`). First SMTP `OSError` → `NameError` instead of healing. (Latest commit `0.1.21->auto-heal imap`.)
  *Fix applied:* added `Provider` to the `app.models` import.

- [x] **#5 ✓ Closing the composer discards a reply with no confirm and no restore.** — FIXED
  `frontend/src/lib/components/Compose.svelte:156-159` — `close()` nulls `app.composing`; nothing flushes the 700 ms autosave debounce. Restore guard `if (!c.to && !c.subject && !c.html)` (`:125`) never matches a reply (always has a subject).
  *Fix applied:* `close()` now `flushSave()`s and confirms if there's real unsaved content; `onDestroy` flushes too; the draft records `in_reply_to` and restores when resuming the same reply (not just blank composes).

---

## 🔴 Tier 2 — Triage logic that does the wrong thing

- [x] **#6 ✓ Subject-only threading + "Mute conversation" mass-mutes that subject for everyone.** — FIXED (mute-thread part)
  `backend/app/sync/threading.py:25-30` keys threads `account|subject`. `mute_thread` (`backend/app/api/messages.py:1126-1132`) stores that key and auto-archives all future mail with that subject from anyone (`engine.py:400`).
  *Fix applied:* `MutedThread` now records the conversation's sender addresses (new `participants` column + migration); arrival auto-archive only fires when the new sender is a participant (legacy mutes stay subject-only). The broader thread-key over-merge (affecting reply/AI context too) is left as a deeper follow-up — needs References/Message-ID headers.

- [x] **#7 ✓ `e` on a focused Smart-group card mass-completes the category with no undo.** — FIXED
  `frontend/src/lib/components/MailList.svelte:389` → `doneCategory` marks up to 5000 done; `notify("… marked done")` at `:222` passes no undo callback.
  *Fix applied:* `doneCategory` and `doneGroup` now pass an undo callback that bulk-`undone`s the ids and clears `hiddenDone`.

- [x] **#8 ✓ Rows inside expanded bundles pass the wrong (outer) index.** — FIXED
  `frontend/src/lib/components/MailList.svelte:560-563` & `:593-596` — `open(m, i)` / `toggleSelect(m, i, e)` use the group's index `i`. `open` sets `focusIndex = i` (`:340`), snapping focus to the bundle header; next `e` triggers #7. Shift-select inside a bundle selects the whole bundle.
  *Fix applied:* nested rows now pass index `-1`; `open` skips `focusIndex` and `toggleSelect` skips shift-range when index < 0 (just toggles the single message).

- [x] **#9 ✓ Screener & regex search silently drop results.** — FIXED
  Screener: fetch `max(limit*5,200)`, Python-filter, then paginate (`backend/app/api/messages.py:219`, `:233`) — page 2 re-slices the same fetch. Regex: only newest 4000 scanned (`:127`).
  *Fix applied:* screener known/unknown filter pushed into SQL (`func.lower(from_addr) in known OR like '%@domain'`), so `offset`/`limit` page the whole mailbox. Regex now scans in 2000-row date-desc batches until `limit` matches or exhausted — no 4000-row blind spot.

- [x] **#10 "Mute sender" only fires for mail landing directly in INBOX.** — FIXED
  Rules run only for `folder.role == inbox` (`backend/app/sync/engine.py:404`). Muted sender routed to a subfolder is never auto-done.
  *Fix applied:* rules now run on `inbox` **and** `other` (custom) folders, where server-side filters file list/automated mail; sent/drafts/trash/junk/archive still skipped.

---

## 🔴 Tier 3 — Compose / reply nonsense

- [x] **#11 ✓ Reply and Reply-All quote NOTHING.** — FIXED
  `frontend/src/lib/components/Reader.svelte:160-168` — `reply()`/`replyAll()` pass no body. Forward quotes (`:169`); reply doesn't. `ThreadView.svelte:40` also omits `in_reply_to` and uses case-sensitive `startsWith("Re:")`.
  *Fix applied:* added `quotedOriginal()` ("On <date>, <name> wrote:" + blockquote) wired into `reply`/`replyAll`/`useDraft` in Reader.svelte. ThreadView.reply now quotes the latest message, sets `in_reply_to`, and uses case-insensitive `/^re:/i`.

- [x] **#12 Recipient input does zero validation; pasted Outlook lists break.** — FIXED
  `frontend/src/lib/components/RecipientInput.svelte` — raw comma string; semicolons become one malformed recipient.
  *Fix applied:* semicolons/newlines/tabs normalize to commas on input (Outlook paste works); completed tokens that don't look like a valid address surface a ⚠ warning line.

- [x] **#13 ✓ Reply-All self-CCs you when mail hit an alias.** — FIXED
  `frontend/src/lib/components/Reader.svelte:147-156` — "me" is only the account's primary `email`; aliases not excluded.
  *Fix applied:* `replyAllCc` now excludes every account identity (primary + aliases) and compares on the bare address parsed from "Name <addr>".

- [x] **#14 ✓ Forward drops attachments.** — FIXED
  `Reader.svelte:169-180` quotes body but never copies `detail.attachments`.
  *Fix applied:* `forward()` re-fetches the original non-inline attachments (new `fetchAttachmentForCompose` API helper) and seeds them into the composer.

---

## 🟠 Tier 4 — Calendar / CalDAV

- [x] **#15 ✓ CalDAV/CardDAV disables TLS verification globally.** — FIXED
  `backend/app/sync/caldav.py:44-45,103-104` — `check_hostname=False` + `CERT_NONE` for every server; password sent as HTTP Basic.
  *Fix applied:* new `_ssl_context()` verifies certs + hostname by default; the insecure mode is opt-in only via `RAPLMAIL_CALDAV_INSECURE_TLS=1` (for self-signed self-hosted boxes).

- [x] **#16 ✓ One failing ICS feed deletes that calendar's events.** — FIXED
  `backend/app/api/calendar.py:190-194` — reconcile-delete removes any `source=="ics"` event not seen this run; a feed that `except: continue`s loses all its events.
  *Fix applied:* track per-feed UID prefixes that fetched OK this run; the delete pass only prunes events belonging to feeds that actually responded.

- [x] **#17 RSVP is local-only — organizer never told.** — FIXED
  `backend/app/api/calendar.py:338-349` flips a DB column only; no `METHOD:REPLY` email / CalDAV PUT.
  *Fix applied:* `rsvp` now emails an iMIP `METHOD:REPLY` (with the right `PARTSTAT`) to the organizer; best-effort, local status still saved if SMTP is offline. Skips self-organized/local events.

- [x] **#18 Timezone handling puts events on the wrong day/hour.** — FIXED
  All-day pinned to UTC midnight (`backend/app/sync/ics.py:61-64`); floating times assumed UTC (`:70-72`).
  *Fix applied:* all-day events anchored at **noon UTC** (won't slip a day on local-zone display); floating times now fall back to the **machine's local zone** (correct since the backend is local-first) instead of UTC.

---

## 🟡 Tier 5 — Smaller nonsense & inconsistencies

- [x] **#19 ✓ Calendar reminders suppressed during email quiet hours.** — FIXED. Removed the `inQuietHours()` gate from `_checkReminders`; quiet hours now only governs new-mail notifications.
- [x] **#20 ✓ Every `e` refetches the entire folder list.** — FIXED. Added debounced `refreshFoldersSoon()` (350ms); `markDone` + undo use it instead of awaiting `folders.list()` per action.
- [x] **#21 ✓ Undo only ever undoes the last action.** — FIXED. `notify` pushes onto a 20-deep LIFO `_undoStack`; `runUndo` pops it; added Ctrl+Z. Done/snooze undo now background-refresh to correct stale-`idx` reinsertion.
- [x] **#22 ✓ `Ctrl+N`/`Ctrl+R` fire while typing; hardcoded `Ctrl+N` shadows the rebindable `kb.compose`.** — FIXED. Removed the hardcoded `Ctrl+N` (compose flows through rebindable `kb.compose`, which respects `!isTyping`); `Ctrl+R` still blocks reload but only syncs when not typing.
- [x] **#23 ✓ Search chips are pure AND with no dedup.** — FIXED. `normalizeChips` de-dupes identical chips and enforces mutual exclusion (`is:read`⟷`is:unread`).
- [x] **#24 ✓ Undo-send is a renderer `setTimeout`.** — FIXED. Pending send persisted to localStorage during countdown; `recoverPendingSend()` redelivers on boot if a quit interrupted it; cleared just before normal delivery to avoid double-send.
- [x] **#25 Cheatsheet drift.** — FIXED. Documented `g a` (Settings), `Ctrl+0` (All), new `Ctrl+Z` (Undo); reworded `e` to "Mark done (toggle)". NB: `Ctrl+Enter Send` **does** exist (`Compose.svelte:361`) — that part of the audit was wrong, kept as-is.
- [x] **#26 Rules editor allows catch-all disasters.** — FIXED. `create()` now validates regex client-side and, for destructive actions (delete/archive/block), runs a preview and confirms the blast radius ("will delete N existing messages…") before saving.
- [x] **#27 Mail-merge preview only renders row #1; missing CSV column → silent empty.** — FIXED. Preview is now steppable across all recipients (‹ n/N ›); warns when a referenced `{{var}}` has no column (empty for everyone) and counts recipients with blank values for a used column.
- [x] **#28 AI thread transcript isn't account-scoped.** — FIXED (defensive). `thread_id` is `"<account_id>|<subject>"`, so it's already single-account by construction; added a defensive same-account filter in `_thread_text` so a future thread-key scheme can't leak one mailbox into another's AI prompt.
- [x] **#29 Pin/snooze don't sync across devices.** — RESOLVED AS BY-DESIGN. There is no RaplMail server; `done` syncs cross-device only because it's mirrored as an IMAP keyword. Pin/snooze are intentionally local (no shared store for a snooze timestamp). The README claims pin "survives re-sync" (local) — which it does via `_restore_state` — **not** cross-device, so nothing is overpromised. Mirroring pin as a `RaplMailPinned` keyword is a possible future enhancement, not a correctness fix.

---

## Systemic themes

1. **"Best-effort, swallowed" collides with "server-is-authoritative" resync** → #1, #2, #3, #4. Local intent must win until provably persisted.
2. **Subject-only threading is load-bearing for features it can't support** → #6, #11, #28.
3. **Destructive bulk actions lack the undo/confirm that single actions have** → #7, #26, #27.
4. **Reply quoting (#11) is the most visible "not a real mail client yet" gap** — high impact-per-effort.

---

## Work log

### Batch 1 — Tier-1/2/3 priority fixes (#4, #11, #1, #2, #6, #7)
Fixed in this order. Files touched:
- `backend/app/api/compose.py` — #4 (`Provider` import), #3 (scheduled-send → ActionQueue on failure)
- `backend/app/api/messages.py` — #2 (reset `pending_action` on permanently-failed queue items), #6 (record mute participants)
- `backend/app/sync/engine.py` — #1 (one-directional done-resync), #6 (gate auto-archive on participants)
- `backend/app/models/__init__.py` + `backend/app/core/db.py` — #6 (`MutedThread.participants` column + migration)
- `frontend/src/lib/components/Reader.svelte` — #11 (reply/replyAll/useDraft quote the original)
- `frontend/src/lib/components/ThreadView.svelte` — #11 (quote + `in_reply_to` + case-insensitive Re:)
- `frontend/src/lib/components/MailList.svelte` — #7 (undo on `doneCategory`/`doneGroup`)

**Verification:** all changed Python byte-compiles; backend test suite = **23 passed, 1 failed**. The 1 failure (`test_compose_smoke.py::test_inline_signature_image_embeds_with_content_id`) is **pre-existing** — confirmed by stashing all 5 backend edits and re-running: it still fails on clean HEAD. It exercises `inject_signature`/`build_mime`, which this batch never touched. *(Worth fixing separately — inline CID signature images aren't embedding.)*

### Open follow-ups noted during the batch
- #3: the ActionQueue send path re-embeds a fresh read-receipt pixel per delivery → add an idempotency/"already sent" guard before relying on retries.
- #6: deeper thread-key over-merge (subject-only) still affects threaded reply targeting and AI context (#28) — needs References/Message-ID in the key.
- Pre-existing test failure: inline CID signature image embedding (`build_mime`).

### Batch 2 — everything else (#5, #8, #9, #10, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29)
All remaining items resolved. Additional files touched beyond batch 1:
- `frontend/src/lib/components/Compose.svelte` — #5 (flush draft on close/destroy + confirm + reply restore)
- `frontend/src/lib/components/MailList.svelte` — #8 (nested-row index `-1`)
- `frontend/src/lib/components/Reader.svelte` — #13 (alias-aware reply-all), #14 (forward attachments)
- `frontend/src/lib/api.js` — #14 (`fetchAttachmentForCompose`)
- `frontend/src/lib/components/RecipientInput.svelte` — #12 (separator normalize + invalid warning)
- `frontend/src/lib/store.svelte.js` — #19, #20 (`refreshFoldersSoon`), #21 (undo stack), #24 (`recoverPendingSend`)
- `frontend/src/App.svelte` — #22 (key handler), #21 (Ctrl+Z), #24 (boot recovery)
- `frontend/src/lib/components/SearchBar.svelte` — #23 (`normalizeChips`)
- `frontend/src/lib/components/ShortcutsOverlay.svelte` — #25 (cheatsheet)
- `frontend/src/lib/components/SettingsRules.svelte` — #26 (destructive-rule confirm + regex validate)
- `frontend/src/lib/components/MailMerge.svelte` — #27 (steppable preview + warnings)
- `backend/app/api/messages.py` — #9 (SQL screener + batched regex)
- `backend/app/sync/engine.py` — #10 (rules on `other` folders)
- `backend/app/sync/caldav.py` — #15 (`_ssl_context`)
- `backend/app/api/calendar.py` — #16 (scoped ICS prune), #17 (iMIP REPLY)
- `backend/app/sync/ics.py` — #18 (noon-anchored all-day + local-zone floating)
- `backend/app/api/ai.py` — #28 (defensive account scope)

**Verification (final):**
- `npx vite build` → ✓ builds clean (only a pre-existing unused-CSS warning in `SettingsCalendar.svelte`, not mine).
- `pytest -q` → **23 passed, 1 failed**. The 1 failure is the same pre-existing `test_inline_signature_image_embeds_with_content_id` (CID signature images), unrelated to any change here.
- All changed Python byte-compiles.

### Remaining known issue (NOT in this sweep's list)
- **Inline CID signature images aren't embedding** (`build_mime`/`inject_signature`) — pre-existing test failure surfaced during verification. Real bug, worth a follow-up; out of scope for this audit list.
- **#3 follow-up still open:** the ActionQueue resend re-embeds a fresh read-receipt pixel each delivery — add an idempotency guard.
- **#6 depth still open:** subject-only thread key over-merges (affects thread reply targeting); needs real References/Message-ID threading.

### Status: ✅ all 29 sweep items addressed (27 fixed, #28 hardened, #29 resolved as by-design).
