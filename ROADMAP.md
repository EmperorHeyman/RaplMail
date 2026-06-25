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

## Planned
- ⬜ Templates / canned replies (beyond snippets)

## Ideas / backlog
- ⬜ Calendar / contacts integration
- ⬜ End-to-end test harness for IMAP/SMTP against a test account

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
   - ⬜ Local open-tracking (your own read-receipt pixel served by FastAPI).
   - ✅ Regex search over the local DB — shipped (`/pattern/`).
   - ✅ Auto-BCC outgoing mail by recipient domain — shipped.

5. **Shortwave: Bundle-Based Triage**
   - ✅ Collapse 3+ notifications from one sender into a "bundle card"; `e` archives the whole bundle — shipped.

9. **Mimestream: Offline Sync Action Queue**
   - ✅ UI updates instantly; archive/delete/send queue in SQLite; a background worker flushes to
     IMAP/SMTP and retries when the connection returns (⏳ N actions syncing) — shipped.

10. **Hardware Hacker: Local Extensibility**
   - ⬜ Local API / Webhooks: a read-only `http://localhost:port/metrics` endpoint so external hardware (ESP32 e-ink display, Home Assistant) can query unread counts / telemetry over the LAN, no cloud.
   - ⬜ Custom CLI tool: a `raplmail-cli` to pipe terminal output into a draft or fire off mail without opening the UI.

11. **Developer: Anti-Noise**
   - ⬜ "Just the Diff" thread view: a Python regex pipeline that strips nested quote garbage (`> On Jun 26, … wrote:`) and renders a reply like a clean git diff of net-new text.
   - ⬜ Code-block syntax highlighting: detect code blocks in the HTML body and apply Prism/Highlight.js so pasted code looks like an IDE (toggle in Settings).

12. **Trust No One: Local Security**
   - ✅ **Local DMARC/DKIM visualizer** — shipped. A red/green shield on the sender avatar: the backend reads the Authentication-Results stamped at your mailbox provider's trust boundary (full SPF/DKIM/DMARC w/ DNS) and surfaces pass (green) / fail (red, likely spoof). The reader shows the breakdown (DKIM/SPF/DMARC) and a "may be spoofed" banner — flagging spoofed `a123systems.eu` / RAPL mail before you read it.
