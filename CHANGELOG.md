# Changelog

All notable changes to **RaplMail** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project loosely follows semantic-ish versioning (`0.MINOR.PATCH`).

Newest releases first. Categories: **Added**, **Changed**, **Fixed**, **Removed**.

## [Unreleased]

_Work in progress lands here, then moves under a version number when bundled._

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
