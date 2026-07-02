# Changelog

All notable changes to **RaplMail** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project loosely follows semantic-ish versioning (`0.MINOR.PATCH`).

Newest releases first. Categories: **Added**, **Changed**, **Fixed**, **Removed**.

## [Unreleased]

_Work in progress lands here, then moves under a version number when bundled._

## [0.2.16] — 2026-07-02

The design + deep-sweep release: a full design overhaul plus a logical sweep
of the whole codebase (40 confirmed bugs fixed — several of them silent
mail-loss or sync-breaking issues).

### Fixed — smart groups & performance
- **Pressing `e` on a mail inside an expanded smart group marked the WHOLE
  group done.** Expanded group messages are now first-class rows: keyboard
  focus moves onto them, `↓`/`↑` walk through them, and `e` completes just the
  focused message. `e` on the group header itself still means "done all".
- **Opening a smart group no longer loads the entire category.** It fetches
  the newest 30, and a "Show more" control pages in the rest on demand —
  expanding a 500-mail Newsletters group is instant now. Background sync
  refreshes only what's on screen, not the whole category.
- **Scrolling feels light again.** The sticky date headers used a blur effect
  that forced a repaint on every scroll frame — removed. Off-screen rows are
  now skipped entirely by the renderer, the list mounts 30 rows and streams
  in more as you scroll, and sender logos load lazily.
- **Mail-list actions no longer lag the whole app.** Two root causes: every
  settings change rebuilt the entire settings object (so even collapsing the
  sidebar recomputed hundreds of per-row values), and the list rendered *all*
  messages and measured every row for the removal animation on each triage
  action. Settings updates are granular now — `e`-streaks, collapsing the
  sidebar, and view switches feel instant.
- **Undoing a done inside a group** restores the message into the group (it
  used to stay hidden until a resync, or reappear in the wrong list).

### Changed — smart group design
- Group headers are **flat and quiet** (Spark-style): a small icon, the group
  name, a "N new" badge, the count, and one muted line of top senders — no
  boxes, no chips. Expanded messages sit right under the header with a subtle
  accent guide, and a "Show more" control pages in older mail.

### Changed — the 1.0 design
- **New design system.** A refreshed dark palette (deeper background, cleaner
  surfaces, richer accent), a matching refined light theme, layered shadows,
  hairline borders, consistent focus rings, and fast, decisive animations
  everywhere (90–200 ms — nothing floaty). Buttons, inputs, scrollbars, menus,
  and dialogs all share the same language now.
- **Sidebar reworked.** Nav items are grouped into sections — your inboxes on
  top, then **Mail** (Drafts, Sent, Snoozed, Follow-ups, Paper Trail), then
  **Tools** (Calendar, Tickets, Scheduled, Newsletter Feed) — instead of one
  long flat list. The active item gets a clear accent pill, the Smart Inbox
  shows a live unread badge, folder unread counts are proper badges, sync/queue
  status moved to a compact strip at the bottom, and the footer is a tidy
  icon row (Sync · Layout · Settings). Compose shows its keyboard shortcut.
  Drag-reordering still works (within a section).
- **Settings reworked.** The 15 horizontal tabs became a searchable vertical
  sidebar — like every modern app — with the section title above the content.
- **Smart Inbox cards** now show a bright "N new" badge when a group has unread
  mail (that's what floats it to the top), and expanded cards refresh live as
  new mail syncs instead of going stale.
- **Premium touches everywhere:** the lock screen got a proper brand mark and
  glow; Home cards ease in with a subtle stagger; modals (confirm, rules,
  command palette) pop in with a blurred backdrop; empty states have friendly
  icon tiles; row action buttons spring in on hover.

### Fixed (logical sweep — mail safety)
- **Sending two messages quickly could silently lose the first.** With undo-send
  on, queuing a second send while the first was still counting down overwrote
  the first one's state — it was never delivered, with no error. Now the first
  message is flushed out immediately when a second send starts.
- **The pop-out compose window could double-send.** A separate compose window
  ran the full app boot, including "recover interrupted send" — which could
  deliver a message the main window was still counting down (you'd send twice,
  and Cancel did nothing). It also duplicated new-mail notifications.
- **Sent messages no longer reappear in the compose Drafts menu.** Closing the
  composer after Send / Schedule / Discard re-saved the message as a local
  draft, so the Drafts list slowly filled with already-sent mail.
- **Signature and pasted images actually reach recipients again.** A regression
  dropped inline images from every normal send (they were only attached when
  the mail carried a calendar invite — and even then to the wrong MIME part).

### Fixed (logical sweep — sync & accounts)
- **The "FOREIGN KEY constraint failed" sync crash** after removing/re-adding
  an account: a sync already in flight kept inserting mail against the deleted
  account's folders. The sync now detects the deletion, rolls back cleanly and
  stops, and account removal also closes the account's live IMAP connections.
- **A folder deleted server-side (e.g. in webmail) no longer bricks the whole
  account's sync.** Pruning it hit a foreign-key error every cycle, which
  rolled back all new mail for that account, forever.
- **Read state now syncs both ways.** Reading a message in RaplMail marks it
  read on the server (so your phone/webmail agree), and messages you read
  elsewhere show as read here on the next sync. Previously the read flag was
  captured once at download and never reconciled.
- **Archiving or deleting an opened calendar invite failed forever** (foreign-key
  error retried 8× in the queue while the server-side move had already
  happened). Same root cause fixed in folder deletion.
- **Body search now works with "encrypt cached mail" enabled** (it was matching
  against ciphertext and finding nothing) — body terms go through the full-text
  index, which is built from plaintext.

### Fixed (logical sweep — correctness & UX)
- **Scheduled sends and read-receipt times showed in UTC** (2 h off in Prague) —
  same bug the calendar had; they now carry the UTC marker.
- **Fast navigation can no longer show the wrong list/message.** Every async
  load (message list, reader, conversation view, calendar grid, rule preview)
  now ignores stale responses — previously a slow search could overwrite the
  folder you'd already switched to, and a slow message fetch could replace the
  message you were reading (Reply would then quote the wrong mail!).
- **Confirm dialogs own the keyboard.** Pressing Enter in a "Delete folder?"
  dialog also opened the focused message; `e` marked mail done behind the
  dialog. All keys are now swallowed while a dialog is up.
- **Swiping a row to Done no longer also opens it.**
- **Sync button couldn't get stuck anymore** — one failing account aborted the
  loop and left "Syncing…" spinning forever with the button disabled.
- **A single-day all-day event was invisible** in the calendar, week strip, and
  Home (start == end with an exclusive end matched no day). New all-day events
  now store a proper exclusive end date.
- **New mail arriving while the connection was briefly down was invisible until
  the next sync** — the app now catches up automatically when the event stream
  reconnects.
- **A setting toggled right before quitting** could silently revert on the next
  launch (the save was debounced and lost); it's now flushed on exit.
- **The remaining "tauri.localhost says" popups are gone** — "send without
  subject?" and "no attachment attached" now use the proper in-app dialog.
- **More small fixes:** command-palette "Go to All Inboxes / Snoozed" now
  actually leaves Settings/Calendar; "Manage all rules →" opens the right
  Settings section even when Settings is already open; deleting/archiving the
  open message clears the reader; conversation "Done all" removes the thread
  from the list immediately; undo restores a message into the *right* view (not
  whatever list you're looking at now); Ctrl+1..9 no longer switches workspaces
  while typing; Home's unread stat shows the real inbox count (was capped at 6);
  the newsletter Unsubscribe button works in the desktop app; calendar-feed
  events without a UID no longer duplicate on every restart; changing the
  calendar auto-sync interval applies without a restart; event reminders aren't
  skipped when the machine was asleep at the exact minute; the vault password
  change no longer silently breaks auto-unlock; two confirmation dialogs
  triggered back-to-back no longer hang the second one.

## [0.2.15] — 2026-07-01

### Changed
- **Smart Inbox groups behave properly now.** A group with **new (unread) mail
  floats to the top** so you notice it; quiet, all-read groups stay tucked at the
  end of Today (the Spark way). When you've cleared all of Today's mail, the
  groups surface at the top instead of sinking below older date sections.
- **Home stays live.** The Home dashboard now refreshes as new mail arrives,
  instead of only updating when you navigate to it.
- **Snappier triage.** The done (`e`) animation is quicker, so marking messages
  done in a streak feels instant.
- **Faster mail delivery.** The fallback sync poll dropped from 120s to 60s (on
  top of the instant IMAP IDLE push), so new mail shows up sooner.

## [0.2.14] — 2026-07-01

### Fixed
- **Calendar/Home event times were 2 hours off** (showing UTC instead of local).
  Event times are stored in UTC but were sent to the UI without a timezone marker,
  so the app read them as local time. They now carry a UTC offset and render in
  your local zone (both the Calendar and the Home tab's agenda).

## [0.2.13] — 2026-07-01

### Fixed
- **Sync broke** ("cannot DELETE from contentless fts5 table") when indexing new
  mail into the search index — it aborted the folder on the first new message.
  Indexing is now resilient on older databases (the replace-delete is wrapped in
  a savepoint so it can't break the message insert), and new databases create the
  search index with delete support so re-indexing is clean.

## [0.2.12] — 2026-07-01

### Changed
- When a Microsoft Graph send token can't be acquired, the Debug log now shows
  the exact reason from Microsoft (the `AADSTS…` code) instead of a generic
  "re-authentication required" — so a consent vs propagation vs stale-token
  problem can be told apart.

## [0.2.11] — 2026-07-01

### Changed
- **Microsoft 365 now sends via Graph first.** Instead of always attempting SMTP
  (which fails after ~13s on tenants with SMTP AUTH disabled), M365 sends go
  straight through Microsoft Graph, falling back to SMTP only if Graph isn't
  available. Sends are instant once Graph `Mail.Send` is granted.

### Fixed
- SMTP protocol errors (e.g. the 535 "SMTP disabled") were being caught by the
  socket-error handler first (because `SMTPException` subclasses `OSError`), so
  the intended handling never ran. Reordered so send errors are classified
  correctly — a genuine bad password is retried, a tenant-disabled/permission
  error is reported clearly.

## [0.2.10] — 2026-07-01

### Added
- **Reorder accounts** in Settings → Accounts (▲/▼) — the order flows through to
  the sidebar and unified views.
- **Remove an account from the sidebar**: enter "Manage folders" and each account
  gets a remove (🗑) button, with an in-app confirm.

### Fixed
- **Adding a Google account** failed with "could not determine account email" —
  the sign-in now requests the identity scopes needed to read your address, and
  tolerates Google's scope reordering that previously aborted the flow.
- **Microsoft 365 send** with SMTP disabled: RaplMail now decides based on the
  actual error (not the stored server host), so a password-connected M365 mailbox
  gets a clear "reconnect with Sign in with Microsoft" message instead of silently
  queuing a doomed retry, and a Graph permission problem is reported rather than
  retried forever.

## [0.2.9] — 2026-07-01

### Fixed
- **Account removal still failed** on the full-text search index (`cannot DELETE
  from contentless fts5 table`). Removal no longer touches that index — leftover
  search entries for deleted mail are harmless (they simply stop resolving) — so
  accounts now delete cleanly.

## [0.2.8] — 2026-07-01

### Fixed
- **Account removal failing** ("Failed to fetch"). Deleting an account whose mail
  included calendar invites hit a foreign-key ordering bug (calendar events were
  removed after their messages). Deletion now happens in the correct dependency
  order inside one transaction, rolling back with a clear error if anything goes
  wrong — so an account always removes cleanly.

## [0.2.7] — 2026-07-01

### Changed
- **Compose always opens a fresh message.** It no longer silently reopens your
  last draft. Instead, a **Drafts** menu in the compose header lists your recent
  drafts (by subject, or recipient when there's no subject) so you restore one on
  demand — and can delete any from the list.
- **No more "tauri.localhost says" popups.** Confirmations (removing an account,
  applying a bulk rule, discarding a draft) now use a proper in-app dialog.

### Fixed
- **Removing an account failed** when it had synced mail (a foreign-key error),
  and could error on a broken Microsoft account ("no cached Microsoft account").
  Removal now cleanly deletes the account, its cached mail/folders/events, and
  its credentials regardless of token state.

## [0.2.6] — 2026-07-01

### Added
- **Drafts** now has its own sidebar item, showing draft messages across all
  accounts.
- **Hide the Newsletter Feed and/or Paper Trail** sidebar items (Settings →
  General) if you don't use them.

### Changed (Settings organization)
- **Quick-action buttons** moved from General to **Appearance** (it's about how
  the UI looks).
- **General** is now grouped under scannable headers — *Mail behavior*,
  *Notifications & scheduling*, *Account & system*, *Security & privacy* —
  instead of one long list.

### Changed
- **"Create rule…" now opens a quick New-rule modal** instead of jumping to
  Settings. Pick a field (Subject, Sender domain, etc.) and the value auto-fills
  from the email you clicked, with a live count of how many existing messages
  match. A "Manage all rules in Settings →" link is there when you want the full
  list.
- **Closing a draft with unsaved changes** now shows an in-app prompt (Save to
  Drafts / Keep editing / Discard) instead of the browser's "tauri.localhost
  says" popup.
- The Debug window now reports the **correct app version** (was always showing
  0.1.0) and no longer floods with harmless Windows socket-close (WinError 10054)
  noise.

### Fixed
- **Gmail sync error** for the `[Gmail]` container folder (`NONEXISTENT Unknown
  Mailbox`): container-only folders are no longer selected, and any such folder
  left over from an older build is pruned automatically.
- A **Microsoft 365 mailbox connected as a plain IMAP/password account** that
  hits "SMTP disabled for the tenant" now shows a clear message explaining how to
  fix it (reconnect with "Sign in with Microsoft", or have the admin re-enable
  SMTP) instead of silently retrying a doomed send.

## [0.2.5] — 2026-07-01

### Fixed
- **Debug log now shows exception details.** Errors that carried a stack trace
  were being swallowed as `<unformattable log record>` (the ring-buffer handler
  called a method that only exists on a `Formatter`). Tracebacks are now captured
  in full, and lines with mismatched format args no longer vanish.

## [0.2.4] — 2026-07-01

### Added
- **Debug window** (Settings → Debug): a live tail of the backend log with a
  level filter (All/INFO/WARNING/ERROR), pause, auto-scroll, copy-to-clipboard,
  and clear — plus a per-account **health panel** (idle / syncing / ok / error
  dots, last-sync time, IDLE state, and the exact error text). Logs stay in
  memory only; nothing is written to disk or leaves the machine.
- **Microsoft Graph send fallback.** When an M365 send is rejected with
  "SmtpClientAuthentication is disabled for the Tenant" (a common admin policy),
  RaplMail automatically re-sends via Microsoft Graph `Mail.Send`, which also
  saves a copy to Sent. Requires the Graph `Mail.Send` permission on the Azure
  app registration (admin consent), or the admin re-enabling SMTP AUTH.

### Changed
- **Spark-style reply box.** Your signature now sits directly below the reply
  text, with the quoted thread collapsed behind a `•••` pill (forwards stay
  expanded) instead of the signature landing after the whole quoted email. The
  composer is wider by default. The collapse pill and wrappers are stripped from
  the sent message so recipients get clean, standard quoted HTML.
- A permanent send rejection (e.g. missing Graph consent) now surfaces a clear
  error toast instead of being silently queued for doomed retries.

### Fixed
- **M365 "syncing for minutes" hang.** The IMAP client had no socket timeout, so
  a stalled connection blocked the sync until the OS TCP timeout. Added bounded
  connect (20s) / read (120s) timeouts so a stall fails fast and the sync loop
  recovers. The read timeout stays above the 60s IDLE poll so push isn't cut off.
- Added INFO logging to the send and per-account sync paths (with timings), so
  stalls and failures are visible in the Debug window.

## [0.2.3] — 2026-07-01

### Added
- **RaplDesk API v2 integration.** The Tickets view now uses v2:
  - Identity is resolved automatically via `GET /me` — no more hand-typing a
    numeric user id. Replies and new tickets post `user_id: "me"`.
  - Tabs driven by the key's identity: **All · My tickets · My dept · Unassigned
    · Created** (server-resolved `scope`, no ids sent from the client).
  - Live per-tab **count badges** from `GET /tickets/counts`.
  - Ticket rows show an unread dot, an `overdue` badge, "unassigned" when nobody
    owns it, and the last-reply time.
  - New-ticket form has an **"Assign to me"** checkbox and pre-fills firm/creator
    from your identity.

## Earlier releases

Summarized from git history; these predate the detailed changelog.

- **0.2.x** — auto-heal IMAP settings; M365 fixes and cross-device "Done" status
  sync; settings redesign; calendar add-event.
- **0.1.x** — encrypted full export/import (`.rmail`); macOS build fixes; Gmail
  support; new-message bug fixes; build-script fixes (BOM/encoding); README;
  initial quality-of-life passes.
- **0.1.0** — initial RaplMail commit.
