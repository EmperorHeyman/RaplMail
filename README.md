# RaplMail

A fast, local-first, privacy-respecting desktop email client for power users — built to replace Spark/Thunderbird with great keyboard-driven triage, real developer tooling, and no cloud middleman.

- **Local-first & private** — everything runs on your machine. A Python backend (FastAPI) talks IMAP/SMTP directly to your providers; the UI is a Tauri (Rust) desktop shell. There is **no RaplMail server** — your mail, keys, and AI API key never leave your computer.
- **Stack** — Tauri 2 + Svelte 5 frontend · FastAPI + SQLModel/SQLite (WAL + FTS) backend, shipped as a bundled sidecar · packaged to a signed Windows installer (macOS build via CI).

---

## Accounts & sign-in

- **Auto-discovery** — type your email and RaplMail figures out the servers: known-provider table, **MX-based detection** (vanity domains hosted on Seznam, Google Workspace, Microsoft 365, Zoho, Fastmail, iCloud, Centrum…), Thunderbird ISPDB, provider autoconfig, and DNS SRV records.
- **Microsoft 365 / Outlook** — OAuth2 device-code sign-in (no password stored).
- **Gmail / Google Workspace** — OAuth2 sign-in.
- **Any IMAP/SMTP** — verified on add; password sealed in the encrypted vault.
- **Per-account health dashboard** — live status (Connected / Syncing / Error), ⚡ IMAP-IDLE indicator, message/folder counts, last-sync time, errors, and a **Reconnect** button to re-enter a password without removing the account.
- **Multiple identities / send-as aliases** per account.

## Triage (the Spark workflow, done right)

- **Done** (`e`) — hide a message from the inbox without moving it; a slider reveals done mail. Works on individual rows **and inside Smart-Inbox group cards**.
- **Snooze** — presets or an exact time; plus **"until I'm back"** presence snooze that resurfaces mail when an idle-time monitor detects you've returned to the desk.
- **Pin** important mail to the top (survives re-sync).
- **VIP senders** — float to the top with a ⭐ and always notify (bypass quiet hours / focus rule).
- **Bundles** — collapse 3+ notifications from one sender into one card; archive the whole bundle at once.
- **Mute sender / mute conversation** (whole reply-all thread auto-archived on arrival).
- **Rules & blocking** — by sender/domain/subject → move/archive/delete/mark-read/mark-done/block, with live preview.
- **Screener** — first-time senders wait for approval.
- **Universal undo** toast for Done & Snooze.
- **Keyboard-first** — full shortcut set, `g`-then-letter chord navigation, and a `?` cheatsheet. `Ctrl/Cmd+R` checks for new mail.

## Views

- **Home dashboard** — live clock, "up next" calendar, latest mail, quick actions.
- **Smart Inbox** — important mail in the main flow; chosen categories collapse into cards showing the **newest messages** with live counts.
- **All Inboxes** (unified), **Snoozed**, **Scheduled**, **Newsletter Feed**, **Paper Trail** (receipts/invoices/orders), **Follow-ups** (sent mail with no reply in N days), **Calendar**.

## Compose & send

- Rich WYSIWYG editor with **drag-drop inline images**.
- **One-drag signatures** with embedded images (inline CID — they actually render for recipients), live preview, per-account defaults.
- **Templates / canned replies** with `{{variables}}`.
- **Send Later** — schedule a send; background worker delivers it; cancel from the Scheduled view.
- **Mail merge** — one template + a CSV/recipient list → individualized messages (separate sends, no shared To/Cc).
- **Send-as identities/aliases**, **Auto-BCC** by recipient domain.
- **Drafts** — local autosave + restore, and **Save to IMAP Drafts** for cross-device sync.
- **PGP sign / encrypt** (inline) and a **read-receipt** tracking-pixel toggle.
- **Attachment reminder** — warns if you mention an attachment but didn't attach one (EN+CZ).
- Offline-resilient **send/action queue** (retried by a worker when the connection returns).

## Reading

- **Attachments** — open with the OS default app, save individually, or **Download all**.
- **Just-the-diff** — collapse nested "On … wrote:" quote history (EN+CZ markers).
- **Code-block syntax highlighting** in the reader.
- **Rich link unfurls** (OpenGraph preview card; off by default).
- **Anti-spoof shield** — DMARC/DKIM/SPF verdict from your provider's Authentication-Results, plus homoglyph/punycode and link-text-vs-href warnings.
- **PGP** — verify signatures and decrypt encrypted mail with your keys; badge in the reader.
- Tracker-pixel blocking; collapse long recipient lists; per-account color stripes.

## AI assistant (bring-your-own-key)

Your own Anthropic API key, stored locally; calls go straight to the provider.

- **Catch me up** — summarize a whole thread (TL;DR + key points + action items).
- **AI reply** — draft a reply in your tone + one-tap quick replies (never auto-sends).
- **Inbox assistant** — a prioritized "catch me up on my inbox" digest and a **priority score** (0–100) for unread mail.
- **Morning briefing** — optional once-a-day digest delivered as a notification.

AI buttons stay hidden until a key is set, and can be toggled off entirely.

## Search

- **Substring matching across every field** — sender, recipients (to/cc), subject, snippet, and cached body — so partial words match (`ertel` → `erteltrading@…`).
- **Operators** (space-tolerant): `from:`, `to:`, `cc:`, `subject:`, `has:attachment`, `is:unread|read|flagged|done`.
- **Regex** search with `/pattern/`.
- **Full-text inside attachments** — text/code/CSV/JSON and Office files (`.docx/.xlsx/.pptx`) are indexed so search matches words inside files.
- Chip-based search bar with contact suggestions; **save any query as a smart folder**.

## Security & privacy

- **Encrypted vault** — credentials sealed with a master password (Argon2id + Fernet).
- **Encryption-at-rest** — optional sealing of cached message bodies with a vault-held key.
- **PGP (OpenPGP)** — verify / decrypt / sign / encrypt; manage keys in Settings.
- **Plus-address generator + tracking** — mint `you+service@domain` per site and see who leaked your address (⚠ flag when more than one sender uses an alias); mute an alias in one click.
- **Anti-spoof** DMARC/DKIM/SPF visualizer + lookalike-domain warnings.

## Calendar & contacts

- **Email-derived calendar** — meeting invites parsed from mail; RSVP; bulk scan.
- **CalDAV / CardDAV** — sync external calendars and address books (Nextcloud, Fastmail, iCloud, Seznam, Radicale…) from Settings → Calendar & Contacts.

## Developer / power-user tooling

- **Local metrics API** — opt-in read-only `/metrics` (JSON) + `/metrics/prometheus` for Home Assistant / ESP32 / dashboards, protected by a stable API key.
- **`raplmail-cli`** (`backend/cli/raplmail_cli.py`) — `unread`, `search`, `accounts`, `metrics`, and `send` (pipe terminal output into a draft: `make 2>&1 | raplmail-cli send -t me@x.com -s "build log"`).
- **Themes & appearance** — programmer color presets (One Dark, Dracula, Monokai, Nord, Gruvbox, Solarized, Tokyo Night, GitHub Dark), light/auto day-night, UI scale, corner roundness, custom CSS (optionally applied inside email bodies).

## Platform & distribution

- **System tray** — closing the window minimizes to tray (IMAP IDLE + sync keep running); tray menu Open/Quit; taskbar **unread badge**.
- **Launch at login** (autostart).
- **Auto-updater** — Tauri updater plugin checks a signed release feed, verifies the signature, and self-installs (Settings → Updates → Check for updates).
- **Windows installers** — MSI + NSIS, signed. **macOS** build via the included GitHub Actions workflow (`.dmg`).

---

## Building from source

**Prerequisites:** Python 3.13, Node 20+, Rust (stable), and the Tauri prerequisites for your OS.

```bash
# 1. Backend deps
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Windows; use bin/pip on macOS/Linux

# 2. Frontend deps
cd ../frontend
npm install

# 3. Run in dev
#   backend (terminal 1):
cd ../backend && RAPLMAIL_DEV=1 .venv/Scripts/python -m uvicorn app.main:app --port 8765
#   frontend (terminal 2):
cd ../frontend && npm run dev          # http://localhost:1420

# 4. Build a desktop installer
#   freeze the backend sidecar:
cd ../backend && .venv/Scripts/python -m PyInstaller raplmail-backend.spec --noconfirm
cp dist/raplmail-backend.exe ../frontend/src-tauri/binaries/raplmail-backend-x86_64-pc-windows-msvc.exe
#   build the app:
cd ../frontend && npx tauri build
# → installers in frontend/src-tauri/target/release/bundle/
```

**Auto-updater signing:** releases are signed with a minisign key (private key gitignored at `frontend/src-tauri/.tauri-updater.key`; public key baked into `tauri.conf.json`). Set `TAURI_SIGNING_PRIVATE_KEY` (+ password) when building to emit signed update artifacts, and publish them with a `latest.json` at the configured endpoint.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

Covers the API surface (health, settings, metrics auth, AI graceful-degradation, plus-aliases), attachment text extraction, OpenPGP round-trips, encryption-at-rest, and CalDAV/CardDAV parsing.

---

Made by [RAPL Group](https://rapl-group.eu/).
