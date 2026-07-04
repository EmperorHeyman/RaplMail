# RaplMail Roadmap

Living doc — add freely. Status: ✅ done · 🚧 in progress · ⬜ planned

## Shipped
- ✅ Local-first architecture: Python (FastAPI) backend + Tauri/Svelte desktop app, bundled sidecar
- ✅ Accounts: IMAP/SMTP, Gmail (OAuth), Microsoft 365 (OAuth device-code)
- ✅ One-field add-account with autodiscovery (MX / ISPDB / autoconfig / SRV) + pre-save connection test
- ✅ Encrypted credential vault (Argon2id + Fernet) + optional auto-unlock ("don't require password")
- ✅ Spark-style triage: `e` / swipe to done, "show done" with done indicator
- ✅ Rules engine + domain blocking, with live preview
- ✅ One-drag inline-image signatures
- ✅ Smart address book (auto-built from sent mail, junk-filtered)
- ✅ Unified inbox, foldable accounts, collapsible icon-rail sidebar, folder create/delete/drag-reorder
- ✅ Compose: rich-text toolbar, attachments, Ctrl+Enter, dock/window modes
- ✅ Undo-send (cancellable "Sending…" with countdown)
- ✅ MIME header decoding, body caching + warm IMAP connection pool, prefetch
- ✅ Sent-mail saved to Sent folder (IMAP APPEND)
- ✅ Typed search operators (`from:`, `to:`, `subject:`, `has:attachment`, `is:unread/done/flagged`) + FTS over body
- ✅ Smart category system (Primary / Newsletters / Social / Updates / Promotions) with tabs
- ✅ Smart remote-image blocking with blocked-URL details + Privacy toggle (idea #6)
- ✅ Signature manager: multiple signatures, per-account assignment, switch in composer, HTML (idea #11)
- ✅ Snippet expander: `;shortcut` → template with `{{first}}`/`{{email}}`/`{{date}}` (idea #10, #2 partial)
- ✅ Command palette (Ctrl+K): compose, jump-to-folder/category, sync, settings, actions
- ✅ In-app theme builder (Appearance settings): live color tokens + distinct presets (Dark/Light/Indigo), corner-roundness slider, and a custom-CSS escape hatch — all live + persisted
- ✅ Customize layout mode: a lockable toggle (🔧/🔓) that reveals drag-to-resize dividers for the sidebar and message-list columns; widths persist, locked by default so they aren't moved by accident
- ✅ Hand-drawn SVG icon set — every UI glyph routes through `lib/icons.js` (single source for the custom-SVG swap); no more hardcoded emoji
- ✅ Spark-style avatars: real sender logos via auto-fetched + locally-cached domain favicons (backend `/avatars/{domain}`, tries the domain directly then Google's favicon service), ring tinted by the receiving account's color, initials fallback, toggle in Appearance (privacy)
- ✅ Configurable quick actions: choose the two hover buttons on each message row (done/snooze/flag/read/archive/delete) and which buttons show under the recipient (reply/reply-all/forward/done/flag)
- ✅ Reader: added Forward + Reply All (Cc = everyone but you & the sender), Reply threads via In-Reply-To, Flag fixed (real styling + active state)
- ✅ Search whisperer: operator suggestions + live contact autocomplete; completed operators (`from:x`, `is:unread`, `/regex/`) render as removable chips
- ✅ Server-side settings: persisted to the DB file (survives installs), loaded on boot, debounced save; localStorage kept as fast cache
- ✅ Config export/import: download settings + rules + signatures + sender tags as JSON, import on another install (dev → prod); emails re-sync from the server
- ✅ Relative timestamps option ("3 hours ago" instead of a date) for list rows
- ✅ Reorderable special nav items (Smart Inbox, Snoozed, Calendar, …) via drag, order persisted
- ✅ Fixed: message list now orders by date in SQL before limiting (smart inbox was showing the oldest synced mail instead of newest)
- ✅ Settings search (filters the tabs by name + keywords) and editor-style theme presets (One Dark, Dracula, Monokai, Nord, Gruvbox, Solarized, Tokyo Night, GitHub Dark)
- ✅ Signature editor: Basic-text / HTML mode toggle + always-on live preview (rendered in a sandboxed iframe, images resolved) so you see exactly what recipients get
- ✅ Signature rendered inline in the compose body (Spark-style, editable), switchable live; body data: images convert to inline CID attachments on send so they always show
- ✅ Fixed: keyboard shortcuts no longer fire while composing / typing in a contenteditable (was marking the open mail done mid-type)
- ✅ Avatars preloaded into the browser cache so they don't pop in when returning to the inbox
- ✅ Reader: long recipient lists collapse to the first 3 + "N more" toggle; copy-address action; address menu closes on outside click
- ✅ Reclassifying a sender (mark as Newsletter/Notification…) moves the mail out of the main flow immediately (optimistic), not after the next sync
- ✅ Smart Inbox "Float by activity" placement: groups ride the recency timeline — a group rises to its newest mail, and newer standalone mail pushes it down
- ✅ Attachments: shown in a bar in the reader with size + one-click download (backend extracts metadata on body fetch; authenticated download endpoint); backfills for previously-opened mail
- ✅ Spark-style brand avatars: when a sender's own domain has no favicon, fall back to the most-prominent link domain in the email body (e.g. a no-reply@ mail that links your project site shows that site's logo); favicons cached locally, multi-source (direct + DuckDuckGo + Google)
- ✅ Custom-CSS reference (selector + variable cheatsheet in Appearance) + opt-in toggle to apply custom CSS inside email bodies
- ✅ Smart Inbox group placement: groups at top / after N newest messages / below all (separate from group order)
- ✅ Faster opens: body prefetch is now a single sequential queue (was 8 parallel fetches flooding the per-account IMAP lock); focused/hovered rows jump the queue so a click isn't stuck behind background prefetches
- ✅ Reader "show original" toggle: view any email with its own original colors/CSS (un-adapted) and back
- ✅ Desktop notifications for new mail (sender + subject preview from the sync engine), with on/off + "only when unfocused" settings and permission request
- ✅ Calendar (email-derived): parses meeting invites (text/calendar / .ics) into events, month grid + day agenda, "Sync invites" backfill scan, local RSVP (Yes/Maybe/No); backend `/calendar` API + `CalendarEvent` table
- ✅ Snooze: hide until a time, Snoozed view, auto-resurface (idea #9 partial, #3 partial)
- ✅ Multi-select + bulk actions (done / read / flag / snooze / archive / delete)
- ✅ Workspaces: group accounts, sidebar pills + `Ctrl+1..9` to switch context (idea #7)
- ✅ One-click unsubscribe via `List-Unsubscribe` (mailto + http)
- ✅ Zero-leak sandboxed HTML rendering: message body in an `<iframe>` with no scripts/same-origin (idea #8)
- ✅ Mute sender: auto-mark future mail from a sender done + clear existing (idea #3 partial)
- ✅ Screener: first-time senders held in a Screener view, approve→contacts / block→rule (idea #1)
- ✅ Send Later: schedule a send, background worker delivers it, Scheduled view + cancel
- ✅ Saved searches / smart folders (save any query, pinned in the sidebar)
- ✅ Newsletter feed: all newsletters stitched into one scrolling view (idea #1)
- ✅ Keyboard-shortcut cheatsheet overlay (`?`)
- ✅ Light theme + Auto day/night mode (theme presets)
- ✅ Paper Trail: dedicated receipts/invoices/orders view (idea #1)
- ✅ Follow-up reminders: sent mail with no reply in N days (idea #2)
- ✅ Per-account colors: editable color/name, colored stripe on rows in unified views
- ✅ Auto-BCC outgoing mail by recipient domain (idea #4)
- ✅ Regex search: `/pattern/` scans subject/from/snippet/body in the local DB (idea #4)
- ✅ Conversation threading: group by subject, full thread reader (toggle)
- ✅ Bundles: collapse 3+ notification messages from one sender into a card (idea #5)
- ✅ Offline action queue: archive/delete/send queue in SQLite, retried by a worker, status indicator (idea #9)
- ✅ IMAP IDLE: near-instant new-mail push per account (polling fallback)
- ✅ Polish: relative timestamps, loading skeletons, per-view empty states, keyboard scroll-into-view
- ✅ Open-next-on-done (Spark triage): marking the open/focused message done opens the next
- ✅ Smart Inbox: important mail in the main flow + chosen categories as group cards showing top-sender previews & live counts, sorted by recency (newest-active on top); per-category configurable; invitations/invitation-responses categories added
- ✅ Right-click context menu on messages: done, read/unread, flag, snooze, archive, delete, show-from-sender, mute, block, create rule, reclassify sender (learned)
- ✅ Smart Inbox tuning: configurable preview-sender count (with live preview), group order (recency or custom drag-order), and "mark sender as <category>" that sticks across syncs

## Planned (details for the brainstormed items in [potential_features.md](potential_features.md))

**Shipped recently**
- ✅ **Pinned mails** — pin messages to the top of the list (durable via MessageState, survives re-sync); pin/unpin in the right-click menu, pin marker on the row
- ✅ **Invitation categorization fix** — subject-prefix detection (meeting/schůzka/porada/…) + a real `text/calendar` event in the body recategorizes to Invitations / Invitation-responses on open
- ✅ **Notifications: test button + diagnosis** — "Send test notification" (bypasses the unfocused rule); clearer Windows/Focus-Assist guidance; fixed the icon
- ✅ **Text & UI size** — Appearance slider (80–140%) scales the whole UI via WebView zoom, persisted
- ✅ **Quiet hours / Do Not Disturb** — suppress notifications during a nightly window (handles past-midnight); toggle + start/end in Settings
- ✅ **Attachment reminder** — warns before send/schedule if the body mentions an attachment (EN+CZ) but none is attached

**Platform & distribution**
- ✅ **Auto-updater** — Tauri updater + process plugins wired; a signing keypair is generated (private key gitignored, public key baked into `tauri.conf.json`), `createUpdaterArtifacts` on, capabilities granted, and Settings → General → Updates has a **Check for updates** button that downloads + signature-verifies + self-installs + relaunches. `cargo check` + frontend build green. Activates once you publish a signed release `latest.json` (sign with `TAURI_SIGNING_PRIVATE_KEY` at build; endpoint set to the GitHub releases pattern — adjust org/repo)
- ✅ **Background / tray mode** — closing the window hides to a system-tray icon (IMAP IDLE + sync keep running); tray menu **Open RaplMail** / **Quit**, left-click reopens. Taskbar/dock **unread badge** + tray tooltip via a `set_unread_badge` command driven by inbox unread totals, and **Launch at login** (autostart plugin, toggle in Settings → General → Updates). Tauri `tray-icon`/`updater`/`process`/`autostart` plugins; `cargo check` + frontend build green (runtime tray/badge UX confirmed only when bundled)
- ✅ **macOS port** — the shell is cross-platform (tray/updater/autostart/dock-badge all work on macOS, mac `icon.icns` present, `run.py` honors `RAPLMAIL_HOST`), with a `.github/workflows/build-macos.yml` CI that builds the PyInstaller mac sidecar + `tauri build` → signed `.dmg`, and a pinned `backend/requirements.txt` for reproducible builds. OAuth (device-code/PKCE) and the encrypted-file vault are already platform-agnostic. (Produced by CI on a mac runner — can't be built on this Windows box; keychain-backed vault is a future nicety)

**AI & productivity (BYOK — keys in the vault, calls straight from the local backend)**
- ✅ Thread summarize, "Catch me up" & morning digest — a **Catch me up** button in the reader summarizes the whole thread (TL;DR + key points + action items); plus an opt-in **daily morning briefing** (Settings → General → AI assistant: toggle + delivery hour) that the sync engine generates once a day and pushes as a desktop notification + into the inbox assistant. BYOK Anthropic key, stored locally
- ✅ Draft & smart reply — reader **AI reply** button drafts a full reply from thread context (in your tone) + one-tap quick-reply chips; both open the composer prefilled and never auto-send
- ✅ AI priority scoring & inbox digest — command palette → **AI: catch me up on my inbox** opens an assistant with a prioritized "catch me up" briefing of unread mail (🔴/🟡/⚪) and a **Prioritize** tab scoring unread 0–100 with one-line reasons, each row clickable straight to the message

**Security & privacy**
- ✅ Encryption-at-rest for the local cache — opt-in (Settings → Encryption (PGP) → "Encrypt the local message cache"): cached `body_html`/`body_text` are sealed with a vault-held data-encryption key (Fernet) on write and transparently decrypted on read. Field-level so it can't corrupt the DB; FTS is indexed from plaintext in-memory so search still works. `app/core/atrest.py` + 4 unit tests green
- ✅ PGP (OpenPGP) — verify signed mail, decrypt encrypted mail, and sign/encrypt outgoing (inline PGP), using your own keys managed in Settings → Encryption (PGP). Reader shows a PGP shield badge (verified signer / decrypted-locally) next to the auth shield; compose has **Sign**/**Encrypt** toggles. Backend `app/sync/pgp.py` (pgpy), 4 round-trip unit tests green. (S/MIME + full PGP/MIME multipart construction still TODO — inline PGP + PGP/MIME detection covered)
- ✅ Lookalike / homoglyph & link-mismatch warnings — reader bar flags confusable/punycode sender domains, display-name domain mismatch, and link-text-vs-href mismatch

**Power-user & developer**
- ✅ Full-text search inside attachments — text/code/CSV/JSON and Office OOXML (.docx/.xlsx/.pptx, parsed via stdlib zip+xml, no deps) are extracted on message open and folded into the FTS index, so search matches words that appear only inside a file. PDF/legacy-binary formats still TODO (need a parser lib)
- ✅ Multiple identities / send-as aliases — manage per-account send-as identities in Settings → Accounts (Identities editor, plain address or `Name <addr>`); compose shows an identity dropdown next to the account when aliases exist; backend only honors a recognized identity and sets a correct envelope sender
- ✅ Mail merge / personalized bulk send — Command palette → "Mail merge": a subject/body template with `{{column}}` vars + a CSV (or one-address-per-line) recipient list → one individualized message per recipient (separate sends, no shared To/Cc), with a live preview and send progress
- ✅ Plus-address / alias generator with per-service tracking — Settings → Aliases & Tracking: generate a `you+service@domain` per site, then a scan of your mail lists every sub-address in use with message count, the senders hitting it, last-seen, a ⚠ leak flag when >1 sender uses one, and one-click **Mute** (auto-creates an archive rule for that alias)
- ✅ Per-account health dashboard — Settings → Accounts shows each account's live status dot (Connected/Syncing/Error/Idle), ⚡live IMAP-IDLE indicator, message + folder counts, last-sync relative time, last error, and a per-account "sync now" ↻ button (auto-refreshes every 5s)
- ✅ Collapse quoted replies ("Just the Diff" lite) — reader hides nested "On … wrote:" history behind a Show/Hide-quoted toggle (EN+CZ markers, blockquote/gmail_quote/Outlook dividers); setting in Appearance. Full git-diff rendering still TODO.
- ✅ Code-block syntax highlighting in the reader — language-agnostic highlighting of `<pre>` blocks (keywords/strings/comments/numbers), injected into the email iframe; toggle in Appearance (on by default)
- ✅ Local API — read-only `/metrics` (JSON) + `/metrics/prometheus` for dashboards/ESP32/Home-Assistant; opt-in (404 when off), authenticated by a stable API key (`X-API-Key`/`?key=`), configured in Settings → General → Local API. LAN access needs `RAPLMAIL_HOST=0.0.0.0`. (Outbound webhooks/push still TODO)
- ✅ Custom CLI — `backend/cli/raplmail_cli.py` (pure stdlib): `unread`, `search`, `accounts`, `metrics`, and `send` (body from `--body` or piped stdin, e.g. `make 2>&1 | raplmail-cli send -t me@x.com -s "build log"`). Points at the backend via `RAPLMAIL_URL`/`RAPLMAIL_TOKEN`

**Triage & UX polish**
- ✅ Universal undo for triage — Undo button on the toast for Done & Snooze (restores the message in place); archive/delete undo still TODO
- ✅ VIP senders & a Priority lane — mark a sender VIP (right-click row / reader sender-menu); their mail floats to the top with a ⭐ and always notifies, bypassing quiet hours + the focused-window rule
- ✅ Drafts autosave + restore — compose autosaves locally as you type and restores into a fresh blank compose; cleared on send/schedule. Plus a **Save draft** button that `APPEND`s to the IMAP Drafts folder for cross-device sync
- ✅ Keyboard chord shortcuts — `g` then i/s/c/f/n/p/t/a jumps to Inbox/Snoozed/Calendar/Follow-ups/Newsfeed/Paper-Trail/Scheduled/Settings (in the cheatsheet)
- ✅ Rich link unfurls in the reader — OpenGraph preview card for the main content link, fetched locally; off by default (toggle in Appearance)
- ✅ Templates / canned replies — full subject+body templates with `{{vars}}`, managed in Settings → Snippets & Templates, inserted from the compose **Templates ⌄** menu

**Larger / longer-horizon**
- ✅ Calendar / contacts integration (CalDAV/CardDAV) — Settings → General → "Calendar & contacts" holds a CalDAV/CardDAV URL + credentials and a **Sync now** that pulls VEVENTs into the calendar and vCards into the address book (stdlib `REPORT` client in `app/sync/caldav.py`, reuses the iCal parser; 3 parsing unit tests green). Read-only server→local for now; live sync verified against fixture responses (needs a real DAV server for end-to-end)
- ✅ Drafts: two-way IMAP `APPEND` to the Drafts folder — compose has a **Save draft** button that builds the MIME and `APPEND`s it (with `\Draft`) to the account's Drafts folder so it syncs across devices; re-saving expunges the prior copy (verified end-to-end against a live account)
- ✅ End-to-end API test harness — `pytest` suite (`backend/tests/`) boots the real app against a throwaway temp DB and exercises health, settings persistence, metrics opt-in + auth, AI graceful-degradation, plus-aliases, message listing, and attachment text extraction (13 tests, green). Live IMAP/SMTP variant against a real test account still TODO

---
_Add your own items below._

### Reference playbooks (remaining, not yet built)

1. **Hey (Basecamp): Ruthless Inbox Defense**
   - ✅ The Screener: first-time senders held for approve/block — shipped.
   - ✅ The Newsletter Scroll: all newsletters stitched into one scrolling feed — shipped.
   - ✅ The Paper Trail: dedicated receipts/invoices/orders view — shipped.

2. **Superhuman: Absolute Speed**
   - ✅ Snippets with variables (`;intro` auto-fills recipient name) — shipped.
   - ✅ Instant Reminders: Follow-ups view surfaces sent mail with no reply in N days — shipped.

3. **Gmail / Outlook: Thread Management**
   - ✅ Mute sender — shipped (auto-done future mail).
   - ✅ **True thread mute** — shipped. Muting a conversation stores its thread key in a `MutedThread` table; new mail in that thread is auto-archived/done on arrival (whole reply-all chain), never hitting the inbox.
   - ✅ Snooze — shipped (basic).
   - ✅ **Presence-aware Smart Snooze** — shipped. "Snooze until I'm back" hides mail with no timer; a local idle-time monitor (Windows `GetLastInputInfo` via ctypes) detects when you return to the desk and instantly resurfaces it via a WebSocket push.

4. **Mailspring / Developer: Power Tools**
   - ✅ Local open-tracking — compose **Receipt** toggle embeds a 1×1 pixel served by the backend (`/track/o/{token}.png`); when the recipient's client loads it, the open is recorded and pushed as a live "📬 opened" notification. `OpenTrack` table + `/track` list endpoint. (Caveat: the recipient must be able to reach this backend — set `trackBaseUrl` to a reachable address; localhost-only won't register remote opens.)
   - ✅ Regex search over the local DB — shipped (`/pattern/`).
   - ✅ Auto-BCC outgoing mail by recipient domain — shipped.

5. **Shortwave: Bundle-Based Triage**
   - ✅ Collapse 3+ notifications from one sender into a "bundle card"; `e` archives the whole bundle — shipped.

9. **Mimestream: Offline Sync Action Queue**
   - ✅ UI updates instantly; archive/delete/send queue in SQLite; a background worker flushes to
     IMAP/SMTP and retries when the connection returns (⏳ N actions syncing) — shipped.

10. **Hardware Hacker: Local Extensibility**
   - ✅ Local API / Webhooks: read-only `/metrics` (+ Prometheus) endpoint — shipped (opt-in, API-key auth; see Power-user section).
   - ✅ Custom CLI tool: `raplmail-cli` (unread/search/accounts/metrics/send, stdin→draft) — shipped.

11. **Developer: Anti-Noise**
   - ✅ "Just the Diff" thread view: collapse-quoted replies — shipped (reader hides nested "On … wrote:" history behind a toggle; EN+CZ markers).
   - ✅ Code-block syntax highlighting: shipped (language-agnostic highlighting of `<pre>` blocks in the reader, toggle in Appearance).

12. **Trust No One: Local Security**
   - ✅ **Local DMARC/DKIM visualizer** — shipped. A red/green shield on the sender avatar: the backend reads the Authentication-Results stamped at your mailbox provider's trust boundary (full SPF/DKIM/DMARC w/ DNS) and surfaces pass (green) / fail (red, likely spoof). The reader shows the breakdown (DKIM/SPF/DMARC) and a "may be spoofed" banner — flagging spoofed `a123systems.eu` / RAPL mail before you read it.


----------------------

### 0.2.18 batch

- ✅ **Boot loading animation** — the blank "Starting RaplMail…" boot screen is now a proper animated splash (rotating accent ring around the mail glyph, shimmering wordmark, bouncing dots) shown while the Python sidecar warms up; honors reduced-motion. Pure frontend, gated on `!app.vault.ready`.
- ✅ **First-run onboarding** — a step-by-step welcome wizard (Welcome → Language → Theme → Preferences → Done) shown once on a fresh install (`onboarded` flag). Reuses the real theme presets (live preview), an EN/CZ language picker, and toggles for Smart Inbox / notifications / Start with Windows — every choice applies immediately and is persisted. Skippable; owns the keyboard while open so shortcuts don't leak to the list.
- ✅ **Smart Inbox is the default** — `smartInbox` now defaults on for new installs, and onboarding enables it explicitly, so the app opens straight into the grouped Smart Inbox instead of a flat list.
- ✅ **Localization (English + Čeština)** — a lightweight, dependency-free i18n (`lib/i18n.svelte.js` + `locales/en.js`/`cs.js`, reactive `t()` that live-switches with no reload, "Auto (system)" detection). Language picker in Settings → General and in onboarding. Primary UI chrome translated (nav/sidebar, settings shell + General, notifications, rules, command palette, mail list, reader, compose, onboarding, boot); remaining long-tail strings fall back to English and are being filled in progressively. The bilingual content-detection heuristics (quoted-reply / attachment / categorization) were already CZ-aware and stay as-is.
- ✅ **"Mute notifications" rule** — a new non-destructive rule action that delivers mail normally (still unread, still in the inbox) but suppresses the ding + popup. Matchable by sender address, sender domain, subject, recipient, **or smart category** (new `category` rule field → "mute notifications from newsletters"). Available in both rule editors and as a one-click "Mute notifications from sender" in the right-click menu. Distinct from "Mute sender" (which auto-marks done).
- ✅ **Empty-notification bug fixed** — root cause: the notification count summed *all* folders (Sent/Archive/Junk/custom, including copies synced from other devices) while the preview was inbox-only, so mail landing outside the inbox fired a titleless "New message" with no body and nothing new to see. The sync engine now counts only genuinely notify-worthy new **inbox** mail (unread, survived rules, not notification-muted) and emits it as a separate `notify` field; the frontend only fires when there's a real preview.
- ✅ **Start with Windows** — the autostart (launch-at-login) toggle is reconciled with the OS on every boot (reads the plugin's live `isEnabled` so the saved preference and the real registration can't silently drift), and is now also offered in onboarding. Setting lives in Settings → General → "Tray & startup".
- ✅ **Notification volume** — a 0–100 volume slider for the new-mail sound (Settings → General → Notifications); the Web-Audio tones scale to it, and the ▶ Play preview + the live "N new" ding respect it.

### 0.3.x

Shipped across **0.3.0** (bug fixes + link hygiene, git-diff, perf), **0.3.1** (multi-provider AI, inline first-run screener, webhook/script rule actions, Subscription Audit, safe-forward pixel stripping), **0.3.2** (Markdown compose + S/MIME crypto core & cert management), **0.3.3** (sanitized `.eml` Safe Export + the full S/MIME pipeline — reader verify/decrypt and compose sign/encrypt), and **0.3.4** (conversation-first reading + anti-"clicking-simulator" pass + deep speed/memory optimization). **Every item in this batch is now ✅** (PDF export intentionally left to the OS "Print to PDF").

**UX de-clicking** — all shipped in 0.3.4
- ✅ **Conversations open as conversations** — clicking a threaded message opens the full conversation directly (no "View conversation" banner, no extra click): siblings in the loaded list flip the thread view instantly, others are auto-promoted the moment the thread check returns >1. The clicked message, the newest one, and unread siblings (capped) auto-expand with bodies loaded in parallel; expanding marks read; the view scrolls to the message you clicked.
- ✅ **Thread view grew up** — per-message Reply / Reply-all / Forward (correct quoting + attachment carry-over), thread-level Reply / Forward / Archive-all / Done-all, per-message attachment chips + auth-warning badge, auto-height message bodies (one natural scroll like Gmail instead of 460px inner scrollboxes), and links inside thread bodies now open in the OS browser (they previously navigated the iframe).
- ✅ **Reader triage gap closed** — Archive, Snooze (with preset menu), and Delete are now reader toolbar buttons (joining Reply/Reply-all/Forward/Done/Flag; all still configurable in Appearance), so triaging an open mail no longer needs a trip back to the list row. "Create rule" added to the sender menu. Single-row archive/delete now confirm with a toast (they were silent).
- ✅ **Escape = back** — Esc closes the open message/conversation back to the list (overlays keep their own Esc).
- ✅ **Keyboard triage completed** — new configurable binds: `r` reply, `f` forward, `a` archive, `Delete` delete, `u` toggle read (work from the list on the focused row; r/f act on the open message/thread). Cheatsheet + Settings → Shortcuts updated.
- ✅ **Screener rows triage inline** — in the Screener view the row hover buttons become **Approve / Block**, so screening no longer requires opening each mail (2 clicks → 1).

**Performance & memory** — all shipped in 0.3.4
- ✅ **Stop hauling bodies through the list** — the list/thread/search/bulk/mute/recategorize queries now defer the cached `body_html`/`body_text` columns (the API never returned them); previously every 100-row page pulled up to 100 full HTML bodies through the ORM. Same for the sync engine's flag resync (was reloading 400 full rows per folder per cycle) and the upsert existence check.
- ✅ **Indexes for the hot paths** — composite `(folder_id, date)` + `(category, date)` and partial snooze indexes, created idempotently on boot for existing DBs.
- ✅ **SQLite tuned** — 128 MB `mmap_size` (file-backed, shared between connections) so reads skip syscalls, per-connection heap cache trimmed to 4 MB (mmap covers reads), WAL size capped via `journal_size_limit`.
- ✅ **Faster serialization, quieter server** — orjson response class for the JSON-heavy endpoints; uvicorn access log off (the UI polls constantly; app logs still feed the Debug window).
- ✅ **Leaner process** — msal, httpx (autodiscover + RaplDesk), and argon2 now import lazily at first use instead of at boot; `gc.freeze()` after startup takes permanent objects out of GC scans; dead `aioimaplib`/`aiosmtplib` deps removed from the bundle.
- ✅ **Frontend caps** — reminder/prefetch bookkeeping sets bounded; thread auto-expand capped so a 20-mail thread doesn't unfold 20 iframes.

**Bug fixes** — all shipped in 0.3.0
- ✅ **Signature encoding corruption (diacritics mangled on send)** — root cause was the outgoing `EmailMessage` using the default policy (`linesep='\n'`), so quoted-printable soft line breaks serialized as bare `=\n`; strict decoders then mis-parsed them, dropping the byte after each soft break ("Lukáš" → "Luká…=A1", "Republic" → "=epublic", `<span>` → `<=pan>`). Fixed by building the MIME with `email.policy.SMTP` (`\r\n`). Verified end-to-end: a Czech signature now round-trips intact.
- ✅ **Auto-select the "From" identity from the open mail** — composing while reading a message now defaults From to the account/alias the mail was addressed to (matched against each account's primary + aliases), instead of always the first account. Applies to blank compose and reply/forward.
- ✅ **Auto-insert the matching signature for the chosen From** — follows the corrected From: the selected account's default signature is inserted automatically and swaps when the From account changes.
- ✅ **Reply reflected in the reopened thread** — replies now reliably join their parent's conversation (the sync inherits the parent's `thread_id` via In-Reply-To instead of the fragile subject+participant discriminator), and the reader showed a **"View conversation"** banner that live-refreshes when a sync lands. (0.3.4 removed the banner entirely — conversations now open as conversations automatically, see below.)
- ✅ **Smart group no longer jumps while its last unread is open** — opening the last unread of a smart group used to drop its `g.new` to 0 and make the card fall to the end of the day mid-read; the open message's category is now pinned to its hot position until you leave.

**Cryptographic armor & privacy shields**
- ✅ **Link hygiene & tracking-parameter stripper** (0.3.0) — every link in rendered mail is cleaned before it's clickable: `utm_*`, `fbclid`, `gclid`, `mc_eid`, `mkt_tok`, HubSpot/Meta/Matomo params, etc. are stripped, and known redirect wrappers (Google `/url?q=`, Outlook SafeLinks, `l.facebook.com`, …) are unwrapped to the real destination, which is also shown on hover. On by default (privacy-first); "Show original" leaves links untouched.
- ✅ **S/MIME support (enterprise PKI)** — full pipeline, alongside OpenPGP, using `cryptography` 49 (pkcs7/pkcs12), no extra deps. **Crypto core** (`app/sync/smime.py`): detached sign, encrypt (enveloped-data), decrypt, inspect. **Cert management** (Settings → S/MIME): import your `.p12`/`.pfx` identity + store recipients' certs. **Incoming** (0.3.3): the reader detects a PKCS#7 part, verifies the signer (identity + cert validity) or decrypts with your key, and shows an S/MIME shield badge — fully guarded so it only ever fires on genuine S/MIME. **Outgoing** (0.3.3): **S/MIME sign / encrypt** toggles in the composer build a proper `multipart/signed` / `application/pkcs7-mime` message in the send path. Round-trip verified (sign→signer, encrypt→decrypt) through the real `build_mime` + 4 unit tests. (Full trust-chain verification of signatures is a future refinement — `cryptography` exposes decrypt but not a one-call verify, so the badge reports signer + validity.)
- ✅ **Sanitized "Safe Forward / Export" mode** — forwarding strips hidden 1×1 tracking pixels from the body by default (0.3.1). **0.3.3** adds sanitized **Export .eml** (reader → sender menu): the backend strips internal routing headers (`Received:`, `X-Originating-IP:`, `Authentication-Results:`, `X-MS-Exchange*`, …) and tracking pixels before download (`GET /messages/{id}/export?sanitize=true`, verified). PDF export is intentionally left to the OS "Print to PDF" (no heavy PDF dependency bundled).

**Developer & power-user ergonomics**
- ✅ **Git patch / diff renderer in the reader** (0.3.0) — `<pre>` blocks (and pasted plain-text patches) that look like a unified diff / `git` patch are auto-detected and rendered color-coded (added/removed/hunk/meta), building on the existing code highlighting.
- ✅ **Markdown compose mode** (0.3.2) — an **MD** toggle in the composer swaps the rich editor for a monospace Markdown pane; on send it compiles to clean inline-styled HTML (headings, bold/italic, inline + fenced code, links, lists, quotes, rules) with the plain-text alternative auto-derived. HTML-escaped (XSS-safe); signature + reply quote are re-attached. `lib/markdown.js`, 10 checks green.
- ✅ **Outbound webhooks & script actions in rules** (0.3.1) — two new rule actions: **POST to a webhook** (fires a JSON payload of the message to a local URL) and **Run a local script** (launches a user-authored command with the mail context in `RAPLMAIL_*` env vars — content passed via env, never interpolated into the shell). Both leave the mail fully delivered and still notify. (Attachment-save-to-folder is a natural follow-on for the script hook.)

**Workflow & inbox mastery**
- ✅ **Subscription Audit utility (new Settings → Utility tab)** (0.3.1) — a new Utility tab lists every mailing-list sender (List-Unsubscribe / newsletter) with total received, 30-day read rate, and last-seen (dormant/unread first), with one-click unsubscribe and one-click / batch **Auto-archive** (creates archive rules). Backend `/subscriptions/audit`.
- ✅ **First-run screener, inline in the reader** (0.3.1) — the reader now shows the "first-time sender — accept?" bar for any inbox mail from an unknown sender (not just inside the Screener view), driven by a computed `first_time_sender` flag on the message detail (same definition as the Screener list filter). Approve adds a contact; block creates a block rule.

**AI**
- ✅ **Multi-provider AI (beyond Claude)** (0.3.1) — Settings → General → AI assistant now has a provider selector (Anthropic / OpenAI / OpenAI-compatible + base URL) that branches the request build + response parse for the summarize / draft / prioritize / digest calls. OpenAI-compatible covers Groq, OpenRouter, Together, Ollama, LM Studio, etc.

**Performance & memory** — all shipped in 0.3.0
- ✅ **SQLite cache-size cap** — per-connection `PRAGMA cache_size=-10000` (≈10 MB) + `temp_store=MEMORY`, so idle pooled connections (one per account poller) don't each pin unbounded page cache.
- ✅ **IMAP socket-pool idle cleanup** — pooled connections idle past 10 min are closed (freeing socket + read buffers) instead of NOOP'd warm forever; the next fetch rebuilds on demand.
- ✅ **Revoke stale object URLs** — verified attachment blob URLs are already revoked (and in the desktop build attachments never create object URLs — they go through Rust to disk); avatars use HTTP-cached `Image().src`, not object URLs. Hardened the avatar warm-set so it can't grow unbounded over a marathon session.
