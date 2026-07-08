# RaplMail

A fast, local-first desktop email client for people who live in their inbox.

RaplMail brings the keyboard-driven triage of modern email apps to your own machine, with no cloud middleman. A Python backend speaks IMAP and SMTP directly to your providers, a Tauri (Rust) shell renders a Svelte interface, and everything (your mail, your keys, your AI settings) stays on your computer. There is no RaplMail server to route your mail through.

## At a glance

- **Local-first and private.** No RaplMail account, no proxy, no telemetry. Your data never leaves your device.
- **Keyboard-driven triage.** Press `e` to mark a message done, snooze it, pin it, bundle it, or split your inbox. The workflow power users miss from Spark, done right.
- **Optional local AI.** Run models on your own machine with Ollama (no API key needed), or bring your own OpenAI, Anthropic, or OpenAI-compatible key. Summaries, replies, meaning-based search, and an assistant that can act on your mailbox when you ask it to.
- **Real search.** Substring matching across every field, operators, regex, and full-text search inside attachments.
- **A compose window that respects you.** WYSIWYG editor, one-drag signatures with inline images, templates, send later, and mail merge.
- **Small and quick.** Roughly 100 to 200 MB of RAM, instant SQLite full-text search, and smooth scrolling over large mailboxes.

## Requirements

- Windows 10 or 11 (64-bit). A macOS build is produced by the included CI workflow.
- An email account: Microsoft 365 / Outlook, Gmail / Google Workspace, or any IMAP/SMTP provider.

## Install

Grab the latest installer from the releases page and run it:

- `RaplMail_x.y.z_x64-setup.exe` (NSIS), or
- `RaplMail_x.y.z_x64_en-US.msi` (MSI)

On first launch you choose a master password. It unlocks a local encrypted vault that seals your account credentials and keys. Add an account and RaplMail auto-discovers the server settings for you. "Check for updates" in Settings queries the GitHub Releases API and points you at the newest installer to download; there is no update server in between.

## Accounts and sign-in

- **Auto-discovery.** Type your email address and RaplMail figures out the servers using a known-provider table, MX-based detection (vanity domains hosted on Seznam, Google Workspace, Microsoft 365, Zoho, Fastmail, iCloud, Centrum, and more), the Thunderbird ISPDB, provider autoconfig, and DNS SRV records.
- **Microsoft 365 / Outlook** via OAuth2 device-code sign-in (no password stored).
- **Gmail / Google Workspace** via OAuth2 sign-in.
- **Any IMAP/SMTP** account, verified when you add it, with the password sealed in the encrypted vault.
- **Per-account health dashboard** with live status (Connected, Syncing, Error), an IMAP-IDLE indicator, message and folder counts, last-sync time, error details, and a Reconnect button to re-enter a password without removing the account.
- **Multiple identities and send-as aliases** per account.

## Triage

- **Done** (`e`): hide a message from the inbox without moving it on the server, then reveal done mail with a toggle. Works on individual rows and inside Smart Inbox group cards.
- **Snooze** to a preset or an exact time, plus an "until I'm back" presence snooze that resurfaces mail when an idle-time monitor notices you have returned to the desk.
- **Pin** important mail to the top (it survives re-sync).
- **VIP senders** float to the top and always notify, bypassing quiet hours and focus rules.
- **Bundles** collapse three or more notifications from one sender into a single card you can archive at once.
- **Mute sender** or **mute conversation** (the whole reply-all thread is auto-archived on arrival).
- **Rules and blocking** by sender, domain, or subject, with actions to move, archive, delete, mark read, mark done, or block, and a live preview against existing mail.
- **Screener** holds first-time senders for your approval.
- **Subscription audit** (Settings > Utility): every mailing list you receive with its 30-day read rate, sorted so dormant and never-opened lists surface first. One-click unsubscribe (RFC 8058, with a browser fallback for confirmation-style links), a filter to show only senders you can actually leave, and a green marker on lists you have already unsubscribed from so you never re-click one. Auto-archive a whole list in one step.
- **Drag a message onto a folder** to move it, single or multi-selected.
- **Universal undo** toast for done, snooze, move, and bulk actions.
- **Keyboard-first**, with a full customizable shortcut set and a command palette (`Ctrl+K`) that also doubles as live search: start typing a `from:` / `subject:` / `is:` operator (or a `/regex/`) and it flips to matching mail you can open on the spot. Arrow keys move through the list and open mail as you go.

## Views

- **Home dashboard** with a live clock, an "up next" calendar strip, latest mail, an inbox AI chat, and quick actions.
- **Smart Inbox** keeps important mail in the main flow while chosen categories collapse into cards that show the newest messages with live counts.
- **All Inboxes** (unified), **Snoozed**, **Scheduled**, **Newsletter Feed**, **Paper Trail** (receipts, invoices, orders), **Follow-ups** (sent mail with no reply after N days), and **Calendar**.

## Compose and send

- Rich WYSIWYG editor with drag-and-drop inline images, and a Markdown mode.
- **One-drag signatures** with embedded images (inline CID, so they actually render for recipients), a live preview, and per-account defaults.
- **Templates and canned replies** with `{{variables}}`.
- **Send Later**: schedule a send and cancel it from the Scheduled view; a background worker delivers it.
- **Mail merge**: one template plus a recipient list becomes individualized messages (separate sends, never a shared To or Cc).
- **Send-as identities and aliases**, and **auto-BCC** by recipient domain.
- **Drafts** with local autosave and restore, plus save to IMAP Drafts for cross-device sync.
- **PGP sign and encrypt** (inline), and a read-receipt tracking-pixel toggle.
- **Attachment reminder** that warns if you mention an attachment but forgot to attach one (English and Czech).
- An offline-resilient send and action queue that a worker retries when the connection returns.

## Reading

- **Attachments** open with the OS default app, save individually, or download all at once, with file-type badges and image thumbnails.
- **Just the new text**: collapse nested "On ... wrote:" quote history (English and Czech markers).
- **Code-block syntax highlighting** in the reader.
- **Rich link unfurls** with an OpenGraph preview card (off by default).
- **Anti-spoof shield**: a DMARC, DKIM, and SPF verdict read from your provider's Authentication-Results, plus homoglyph and punycode warnings and link-text-versus-href checks.
- **PGP**: verify signatures and decrypt encrypted mail with your keys, shown as a badge in the reader.
- Tracker-pixel blocking, collapsible long recipient lists, per-account color accents, and an adjustable reading width so long lines do not stretch across a wide screen.

## Attachment safety

RaplMail inspects risky attachments without ever running them. Every check is static: files are parsed, decoded, and byte-scanned, never executed.

- **Pre-open warning.** Executables, macro documents, decoy double extensions (like `payroll.pdf.exe`), right-to-left-override filename spoofing, and files whose bytes do not match their extension are flagged before you open them, with a short countdown on "Open anyway".
- **Content-based flagging.** A PDF or Office file with a clean name but active content inside (a `/Launch` action, embedded JavaScript, `/OpenAction`, embedded files, or VBA macros) is flagged on the same warning.
- **Automatic background analysis.** Office, PDF, and archive attachments are analyzed as a message opens and get a verdict badge (Clean, Suspicious, or Dangerous). A high score escalates the pre-open warning even for a file whose name looked harmless.
- **Macro de-obfuscation.** VBA macros are extracted and decoded (unwrapping `Chr()`, Base64, and hex tricks) so a disguised downloader is shown in plain language: auto-run triggers, behaviour, indicators such as URLs and dropped filenames, and the decoded source. Compressed PDF object streams are inflated and re-scanned so hidden content is not missed.
- **Isolated inspection view.** Open any flagged file, or any file on your PC, in an isolated view that parses it inside a WebAssembly module with no access to your files, your network, or the backend. It lists everything the file would attempt (launch a program, run a script, contact a URL) as detected intents, next to a safe text preview and a raw hex view, and scores it from 0 to 100.

This is deep static analysis and de-obfuscation, not detonation. RaplMail never runs the file in a virtual machine, so there is no code execution at any point.

## AI assistant

RaplMail's AI is optional and private by design. Run models locally with Ollama and no API key ever leaves your machine, point it at any OpenAI-compatible endpoint (LM Studio, llama.cpp, vLLM), or bring your own OpenAI or Anthropic key. When you use a cloud key, calls go straight from your machine to that provider. There is never a RaplMail server in the middle.

- **One-click local setup.** Install Ollama and pull a recommended model from Settings, or search the whole model library live and pull anything (chat or embedding).
- **An assistant that can act.** Ask how a feature works and it explains, or ask it to change your mail ("mark all unread as read", "archive everything from noreply@..."). It proposes the exact action with a sample of the affected messages and only runs it after you confirm.
- **Catch me up.** Summarize a whole thread into a TL;DR with key points and action items.
- **AI reply.** Draft a reply in your tone with one-tap quick replies. It never sends on its own.
- **Composer rewrites.** Rephrase, fix grammar, change tone, translate, shorten, or expand the text you are writing.
- **Inbox digest and priority triage.** A prioritized "catch me up on my inbox" and a priority score from 0 to 100 for unread mail, plus an optional once-a-day morning briefing.
- Replies and rewrites match the language you write in.

AI buttons stay hidden until a provider is usable and can be turned off entirely.

## Search

- **Substring matching across every field**: sender, recipients (to and cc), subject, snippet, and cached body, so partial words match (`ertel` finds `erteltrading@...`).
- **Operators** (space-tolerant): `from:`, `to:`, `cc:`, `subject:`, `has:attachment`, and `is:unread|read|flagged|done`.
- **Regex** search with `/pattern/`.
- **Semantic search**: an optional local embedding index finds mail by meaning, not just keywords, and a natural-language mode turns a plain request into a query.
- **Full-text inside attachments**: text, code, CSV, and JSON files plus Office documents (`.docx`, `.xlsx`, `.pptx`) are indexed, so search matches words inside files.
- A chip-based search bar with contact suggestions, and the option to save any query as a smart folder.

## Security and privacy

- **Encrypted vault**: credentials are sealed with your master password (Argon2id and Fernet).
- **Encryption at rest**: optional sealing of cached message bodies with a vault-held key.
- **PGP (OpenPGP)**: verify, decrypt, sign, and encrypt, with key management in Settings.
- **Plus-address generator and tracking**: mint `you+service@domain` per site and see who leaked your address (flagged when more than one sender uses an alias), then mute an alias in one click.
- **Anti-spoof**: a DMARC, DKIM, and SPF visualizer with lookalike-domain warnings.

## Calendar and contacts

- **Email-derived calendar**: meeting invites are parsed from mail, with RSVP and a bulk scan.
- **CalDAV and CardDAV**: sync external calendars and address books (Nextcloud, Fastmail, iCloud, Seznam, Radicale, and more) from Settings > Calendar and Contacts.
- **Reminder windows and sounds**: event reminders can pop a small always-on-top window ("you have X until ...") with its own sound. New mail and calendar reminders have separate sounds, and you can upload an audio file and trim a short clip to use as your own notification sound.

## Appearance

- A large set of themes grouped by category (Essentials, High contrast, Neutral, Color, Editor), including a true-black OLED theme and programmer favorites (One Dark, Dracula, Monokai, Nord, Gruvbox, Solarized, Tokyo Night, GitHub Dark).
- Generate a full palette from a single accent color, or tune each color token by hand, and save your custom palettes as named presets.
- Light, dark, and automatic day-and-night modes, adjustable UI scale, corner roundness, message density, and optional custom CSS (which can also be applied inside email bodies).

## For power users and developers

- **Local metrics API**: an opt-in, read-only `/metrics` (JSON) and `/metrics/prometheus` for Home Assistant, an ESP32, or a dashboard, protected by a stable API key.
- **`raplmail-cli`** (`backend/cli/raplmail_cli.py`) with `unread`, `search`, `accounts`, `metrics`, and `send`. Pipe terminal output straight into a draft, for example `make 2>&1 | raplmail-cli send -t me@x.com -s "build log"`.
- English and Czech interface languages, switchable in Settings.

## Platform and distribution

- **System tray**: closing the window minimizes to the tray (IMAP IDLE and sync keep running), with an Open/Quit menu and a taskbar unread badge.
- **Launch at login** (autostart).
- **Update check (serverless)**: "Check for updates" asks the GitHub Releases API for the newest published version, compares it to the running one, and opens the download page for the latest installer. No update server and no signing feed sit in the middle.
- **Windows installers**: MSI and NSIS, signed. A macOS build (`.dmg`) is produced by the included GitHub Actions workflow.

## Building from source

**Prerequisites:** Python 3.13, Node 20 or newer, Rust (stable), and the Tauri prerequisites for your OS.

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
# installers land in frontend/src-tauri/target/release/bundle/
```

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

The suite covers the API surface (health, settings, metrics auth, AI graceful degradation, plus-aliases, message moves), attachment text extraction, OpenPGP round-trips, encryption at rest, and CalDAV/CardDAV parsing.

## Why RaplMail?

Most email clients make you pick one of two compromises: fast workflows trapped inside a paid cloud middleman (Superhuman, Spark), or local privacy bundled with a heavy legacy interface (Thunderbird, Mailspring). RaplMail gives you the speed and triage of a modern client while keeping 100 percent of your data, keys, and credentials on your own machine.

| Feature / Architecture | RaplMail | Spark | Thunderbird | Superhuman | Mimestream | Hey | MS Outlook |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Pricing | **Free, local** | Freemium | Free | $30 / mo | $50 / yr | $99 / yr | Included with the bloatware |
| Any IMAP/SMTP | **Yes** | Yes | Yes | No | No | No | Yes, if you survive four nested wizards |
| Zero cloud middleman | **100% local** | No | 100% local | No | Direct API | No | No, routes everything to Microsoft |
| UI stack | **Tauri 2 + Svelte 5** | Web / Electron | C++ / Gecko | Web wrapper | Native macOS | Web wrapper | Win32 legacy layer cake |
| Spark-style triage (`e` to done) | **Yes** | Yes | No | Yes | Partial | Partial | No, only delete or archive loops |
| Hey-style defenses (Screener, Feed, Receipts) | **Yes** | No | No | No | No | Yes | No, prepare for infinite spam |
| Custom IMAP auto-discovery | **Instant (DNS/MX/ISPDB)** | Yes | Yes | N/A | N/A | N/A | Fails, then drops you into an M365 upsell funnel |
| Offline action queue | **Instant local UX, background retry** | Partial | Blocking UI | Yes | Yes | No | "Outlook is not responding" |
| Local AI (no cloud required) | **Yes (Ollama)** | No | No | No | No | No | No |
| RAM footprint | **~100 to 200 MB** | ~400 MB and up | ~200 MB and up | ~300 MB and up | ~60 MB | ~300 MB and up | your entire available memory pool |

### The short version

- **Versus Spark and Superhuman:** the same keyboard-first triage (`e` to complete, snooze, bundle cards, split inboxes) without routing your sensitive email through a third-party proxy or paying $30 or more per month.
- **Versus Thunderbird:** a lightweight, modern interface with fast SQLite full-text search, inline WYSIWYG and Markdown compose, and advanced workflows out of the box, without fighting twenty-year-old UI paradigms.
- **Versus Hey:** modern inbox defenses (a first-time-sender Screener, newsletter feeds, order and receipt paper trails) on your existing custom domains and IMAP accounts, instead of a walled garden that forces an `@hey.com` address.
- **Versus Microsoft Outlook:** Outlook was not designed for the person at the keyboard, it was designed for corporate IT compliance. If you enjoy manual port configuration hidden behind four legacy modal dialogs, loading-spinner crashes while it syncs a local `.ost` file, and an interface that looks optimized for Windows 2000, keep using Outlook. If you want an app that instantly auto-discovers custom-domain SMTP settings and lets you triage from the keyboard, use RaplMail.

Made by [RAPL Group](https://rapl-group.eu/).
