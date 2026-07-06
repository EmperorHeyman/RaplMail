# Changelog

All notable changes to **RaplMail** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project loosely follows semantic-ish versioning (`0.MINOR.PATCH`).

Newest releases first. Categories: **Added**, **Changed**, **Fixed**, **Removed**.

## [Unreleased]

_Work in progress lands here, then moves under a version number when bundled._

## [0.5.10] — 2026-07-06

### Fixed
- **Inline images sent as `application/octet-stream` now render.** Some clients
  (e.g. Foxmail/Coremail) send pasted inline images with a generic content type
  instead of `image/*`. The reader now sniffs the actual image bytes (PNG/JPEG/
  GIF/WEBP/BMP/ICO) rather than trusting the declared type, so those images embed
  correctly and stay off the attachment strip (they had appeared as generic
  "attachment-1/-2"). Fixes the case where 0.5.9 still showed empty image boxes.
- **Self-heals mail blanked by 0.5.9.** 0.5.9 stripped unresolved `cid:` refs on
  re-cache, which could leave an inline image with an empty `src`. Such a body is
  now detected on open, re-fetched and re-embedded, then re-cached — no resync.

## [0.5.9] — 2026-07-06

### Fixed
- **Inline images now render in the reader.** Pasted/embedded images (typically
  from Outlook) carry a `Content-ID` but no filename, so the parser named them
  after their `cid:` — which meant they slipped past the inline-image detection.
  They now render inline as intended, and no longer clutter the attachment strip
  as phantom "CBE34110@…"-style attachments. Matching is also more forgiving:
  images are looked up by Content-ID, its local part, and filename, and both
  quoted and unquoted `cid:` references are rewritten.
- **Already-cached mail with broken inline images self-heals.** A message whose
  body was cached before this fix (raw `cid:` refs, so broken images) is
  re-fetched and re-embedded once on open, then re-cached — no full resync needed.

### Changed
- **Richer first-run onboarding.** The welcome wizard now introduces the app: a
  feature-highlights step (triage-to-done, Smart Inbox, privacy/tracker blocking,
  rules, drag-in signatures, snooze, local AI, keyboard-first) and a "make it
  yours" step that tours the main settings areas — tap any to jump straight in.
  The final step gets a prominent "Add an account" button.

## [0.5.8] — 2026-07-05

### Fixed
- **Drag a message onto a folder to move it now works.** The sender's favicon was
  draggable by default and hijacked the drag (so the folder showed a no-drop
  cursor). The favicon is no longer draggable, the drag always starts from the
  row, and folder drop targets accept a same-account move reliably. Dragging over
  a folder in a different account now shows a clear "can't drop here" highlight
  instead of a bare slashed circle (a move can't cross accounts).

### Added
- **Multi-select with Ctrl/Cmd-click and Shift-click.** Ctrl/Cmd-click toggles a
  row into the selection; Shift-click selects a range. No need to find the avatar
  checkbox first. The selection bar (mark done/read, flag, snooze, archive,
  delete) works as before.
- **Group right-click menu.** Right-clicking one of several selected messages
  opens a menu that acts on the whole selection: mark done/read, flag, snooze,
  move to a folder, archive, delete, or clear the selection.

### Changed
- **Better local-model recommendations.** The one-click "Best" setup used to pull
  `gemma3:27b` (17 GB), which overflows a 16 GB GPU and runs slowly. It now pulls
  `qwen2.5:14b` (9 GB) — excellent all-round quality that fits without spilling.
  "Balanced" now pulls `mistral-nemo:12b` (fast and far more coherent than
  `mistral:7b`, and strong in Czech). The catalog notes now flag which models
  need more VRAM.
- **AI commands are sturdier with small models.** Rewrite/translate output is
  now stripped of the code fences, surrounding quotes and "Sure, here's..."
  preambles that models like `mistral:7b` add despite being asked for text only.
  Added automated tests covering every built-in AI command (summarize, draft,
  digest, triage, rewrite, ask, search, agent).

## [0.5.7] — 2026-07-05

### Fixed
- **AI assistant no longer dumps raw protocol text.** Asking a plain question
  (e.g. "summarize my new mail") could make a smaller local model spit out its
  internal scaffolding: an `ANSWER:` prefix plus tacked-on `ACT:`, `RULE: {...}`
  and `MAKE A RULE:` lines. The assistant now strips any of that leaked
  scaffolding before showing an answer, so a question always comes back as clean
  prose and never as a half-parsed command.

### Changed
- **Stricter assistant instructions.** The model is now told to pick exactly one
  mode per reply (a plain answer, one action, or one rule), to never mix them, and
  to never print the `ANSWER:` / `ACT:` / `RULE:` / `MAKE A RULE:` labels in an
  answer. Summaries, questions and drafts are always plain answers and never
  trigger an unrequested action or rule.

## [0.5.6] — 2026-07-05

### Fixed
- **Ollama console windows are gone for good.** The earlier fixes reduced the
  flashes but couldn't stop them entirely, because the model-runner process
  inherits its console visibility from whatever started the server, and the Ollama
  tray app starts it with a visible console. RaplMail now runs its *own* hidden
  `ollama serve` on a private loopback port (started with a hidden console, which
  the model runner inherits) and routes all of the app's AI traffic to it. The
  tray Ollama is left running but idle, so it never spawns a runner and never
  flashes a window. Loading a model, unloading it, and freeing the GPU are all
  silent now.

### Added
- **"Hide Ollama's console windows" toggle** (Settings → AI assistant, on by
  default on Windows). Turns the managed hidden server on or off at runtime; off
  falls back to the tray/configured server.
- The hidden server replicates the tray server's `OLLAMA_*` configuration (models
  directory, GPU backend, context length) so it sees exactly the same models. As a
  safety net, RaplMail only routes traffic to the hidden server if it can see every
  model the configured server has; otherwise it leaves the configured server in
  charge (correctness over cosmetics).

### Changed
- **Restart** now restarts RaplMail's hidden server (not the user's tray Ollama)
  when managed mode is on, and the hidden server is shut down cleanly when the app
  exits or the toggle is turned off.

## [0.5.5] — 2026-07-05

### Fixed
- **"Free GPU" no longer flashes console windows.** It used to ping the configured
  model when nothing was loaded, which made Ollama load a model (spawning a runner
  process / console window) just to unload it. It now only unloads what's actually
  resident, so freeing does nothing when nothing is loaded.
- **Broader detection of the windowless Ollama app.** Start/Restart now find
  `ollama app.exe` in more locations (Program Files, the uninstall registry key),
  so RaplMail launches the windowless desktop service instead of a console
  `ollama serve` whose model-runners pop black windows.

_Note: any remaining console windows on model load come from Ollama itself and are
version-dependent (older builds ran model runners with a visible console). Updating
Ollama (Settings → AI assistant → Update Ollama) and hitting Restart once, so the
windowless app takes over, resolves them._

## [0.5.4] — 2026-07-05

### Fixed
- **Rules matched nothing (preview showed 0) even when mail clearly matched.** The
  match scan only looked at ~2000 rows in no particular order, so recent mail (a
  daily report) was never checked. Rules now match across the whole mailbox in the
  database — accurate and fast.
- **Sender rules match the display name, not just the address.** "from contains
  ZERV Reporter" now hits mail from `ZERV Reporter <tickety@…>`.
- **Ollama no longer opens black console windows.** It's now launched via the
  windowless Ollama desktop app (its own model-runner processes were what popped
  the consoles); falls back to a hidden `ollama serve` if the app isn't installed.
- **Model picker recognises what you actually pulled.** `mistral:7b` in the
  recommended list now matches an installed `mistral` / `mistral:latest`, while
  `gemma3:12b` and `gemma3:27b` stay distinct.

### Changed
- The AI's **Create rule** card now shows how many emails you already have would
  be affected (with a sample), so you can sanity-check the rule before creating it.

## [0.5.3] — 2026-07-05

### Added
- **The AI assistant can create rules.** Ask it to handle mail automatically
  ("always mark the ZERV daily report as done") and it proposes a rule (field,
  operator, value, action) for you to confirm. On confirm it creates the rule and
  applies it to matching mail you already have.
- **Rules apply to existing mail.** Creating a rule (from the quick modal, the
  Rules settings, or the AI) now also runs it against mail already in the box, not
  just future arrivals (new `POST /rules/apply`).

### Fixed
- **Subject rules now actually do something.** They previously only ran on newly
  arrived mail, so a rule for a report already in your inbox looked broken. It now
  applies on create; contains, exact, and regex all work.
- **Ollama no longer flashes black console windows** when it starts or restarts
  (CREATE_NO_WINDOW instead of a detached process, so its model runners stay
  hidden too).
- **Model picker is tag-aware.** gemma3:12b and gemma3:27b are distinct now, so
  only the model you're actually using shows "Using"; installed-but-inactive
  models show an "Installed" tag so you can see what you have.

### Changed
- The rule editor modal is larger and roomier.

## [0.5.2] — 2026-07-05

### Added
- **Start Ollama with RaplMail.** A checkbox in Settings > AI assistant brings the
  local Ollama server up on launch (if you opted in and it isn't already running).
- **Start / Restart Ollama buttons.** When Ollama is installed but not running you
  can start it in one click, and a Restart button recovers a stuck server (handy
  after an app update) instead of only being told to run `ollama serve` yourself.

### Fixed
- The "Ollama installed but not running" state now offers a real Start action
  rather than just a hint.

## [0.5.1] — 2026-07-05

### Fixed
- **Signatures used the wrong account's default.** Composing from one account
  could insert another account's signature (it fell through to the first/global
  one). An account's own signature now always wins before any global fallback.
- **Sluggish scrolling in Settings** — a redundant `zoom: 1` was forcing the
  browser off its fast-scroll path; `zoom` is now only applied when the UI scale
  is actually not 100%.
- **The “Default” signature checkbox jumped when clicked** — checkboxes/radios
  were inheriting text-input padding + a focus ring; reset to clean native
  accent-colored controls (across all of Settings).
- **Semantic indexing was extremely slow (0 GPU).** It embedded one message per
  request and let the model unload every 30s. Now it uses Ollama's batch
  `/api/embed` endpoint (whole batch in one request, GPU-batched) and keeps the
  model warm, falling back to per-text on older Ollama builds.

### Changed
- The email body now sits in a framed card (border, rounded corners, subtle
  shadow) matching the header and conversation cards.

## [0.5.0] — 2026-07-05

A big polish-and-capability release: the AI assistant grows hands, the whole app
gets a visual pass, and the theming system is rebuilt.

### Added
- **Agentic AI assistant.** The assistant now knows RaplMail and can *do* things:
  ask “how do I snooze a mail?” and it explains, or “mark all unread as read” /
  “archive everything from noreply@…” and it proposes the exact action (with a
  sample of the affected mail) for you to confirm before anything runs. Backed by
  a new `/ai/agent` endpoint; actions execute through the existing bulk path.
- **Mark all as seen** button on the mail-list header — clears every unread in the
  current view (including mail tucked inside Smart Inbox cards), with undo.
- **Drag a message onto a folder** to move it (single or a whole multi-selection);
  the target folder highlights, and the move is queued + flushed to IMAP in the
  background with retry. New `POST /messages/move` endpoint.
- **10+ new theme presets**, categorized (Essentials · High contrast · Neutral ·
  Color · Editor): **True Black** (OLED), Contrast Dark/Light, Paper, Snow,
  Carbon, Graphite, Mono, Sepia, Ocean, Amethyst, Crimson. Neutral/black presets
  set the whole grey ramp, so “everything looks blue” is gone.
- **Generate a palette from one color** — pick an accent + Dark/Light base and the
  full grey ramp is derived on that hue.
- **Reading width** (Appearance) — cap email bodies to a centered column on wide
  screens (Full / Narrow / Medium / Wide; default Medium).
- **Message density** (Appearance) — Compact / Comfortable / Cozy row spacing.
- **Attachment type badges + image thumbnails** in the reader and thread view.
- **Home-screen greeting tint** — the hero aurora shifts with the time of day.
- **Command palette**: fuzzy matching plus Home, Smart Inbox, Sent, Drafts,
  Screener, Paper Trail, Follow-ups, Calendar, Tickets, Scheduled, Newsletter
  Feed, and Mark-all-read.

### Changed
- **Settings search finds the exact setting**, not just the category — results
  jump to and briefly flash the specific control.
- **Conversation view redesigned** — each reply is a rounded card tagged with the
  sender’s colored avatar; your own replies align right (chat-style).
- **Colored per-sender avatars** in the list (stable color per sender) instead of
  one identical accent disc; shared with the conversation view.
- **Row-by-row entrance animation** extended from Home to the mail list and the
  other tabs.
- **Reader header** is now a rounded card (with a per-account color accent),
  matching the conversation cards; switching messages cross-fades.
- Empty states use the accent treatment; the theme-preset swatches are real
  mini-previews (background + panel + accent), fixing the light/dark mix-up.
- On the desktop, dragging a message row with the mouse now starts a
  drag-to-folder; swipe-to-done remains a touch/pen gesture.

### Fixed
- **Conversation threading “off” is respected** — with threading disabled, mail no
  longer opens as a thread (both the list-open and the reader auto-promote paths).
- Arrow-up/down now opens the focused mail immediately (Spark-style), no separate
  Enter needed.
- The folded sidebar’s non-clickable account circles are gone (a quiet hairline
  separates each account’s folders; hovering a rail folder shows its account).

## [0.4.10] — 2026-07-04

### Added
- **Live Ollama model search.** Settings → AI assistant searches Ollama's library
  in real time — type “gemma” and get gemma, gemma2, **gemma3, gemma4**, … as
  they're published (no more stale hardcoded list). Pull or switch straight from
  the results, or search “qwen”, “deepseek”, “phi”, anything.
- **One-click setup.** Three buttons — ⚡ Fast / ⚖ Balanced / 🚀 Best — each
  switches you to Ollama, turns AI on, sets adaptive GPU, and pulls + activates
  the right model for that hardware. Nothing else to configure.

### Changed
- Refreshed the recommended-models list (Gemma 3, not Gemma 2) — but it's now
  just a starting point; **live search covers the whole library**.

## [0.4.9] — 2026-07-04

### Added
- **Home-screen AI chat.** An “Ask AI about your inbox” card on Home: type plainly
  (e.g. “shrň nové maily”) or tap **Recap new mail** — it opens the assistant with
  your unread inbox loaded as context and answers in your language.
- **Tiered Ollama model picker.** Settings → AI assistant now lists recommended
  chat **and** embedding models grouped by the GPU they need (runs-anywhere /
  mid-range / high-end), each with size and a one-line note (multilingual models
  flagged for Czech). Installed models show a one-tap **Use**; others show **Pull**
  with progress. Install-state is read live from Ollama; you can still pull any
  model by name.

## [0.4.8] — 2026-07-04

### Added
- **Adaptive GPU mode for Ollama.** A new “Free GPU after → Adaptive” option: the
  model loads into VRAM when the RaplMail window is focused and is freed a few
  seconds after you switch away — unless you're mid-question. Ready when you are,
  off when you're not.
- **Natural-language search.** With AI enabled, the advanced-search **Smart** mode
  lets you type plainly — e.g. “najdi email kde se jedná o audi crash plate” — and
  the model turns it into a search. Uses your local embedding index if you built
  one, otherwise AI keyword extraction, then falls back to keyword search.
  (Requires an AI provider enabled.)

## [0.4.7] — 2026-07-04

### Added
- **Dedicated “AI assistant” settings tab.** The AI provider / Ollama controls
  (model, keep-alive, install/update, free-GPU) and semantic search moved out of
  General into their own tab, so it's easy to find.
- **Right-click → “Add to AI chat.”** From the message list, add any email to the
  assistant as context — it opens the assistant (or adds to it if it's already
  open) so you can ask across several messages.
- **Clear-conversation button** in the AI assistant, to start a fresh chat
  without closing the window.

### Changed
- **AI assistant input is multi-line now: Enter sends, Shift+Enter starts a new
  line.** The box grows as you type.

## [0.4.6] — 2026-07-04

### Fixed
- **AI now answers in your language, everywhere.** A universal “reply in the same
  language as the user” instruction is sent on every AI action (assistant, ask,
  summary, reply), so writing in Czech gets a Czech answer — not English.
- **AI assistant window keeps its size when you move it.** Resizing then dragging
  no longer snaps it back to the default width; it behaves like the compose window.
- **Reply / Forward buttons honor the position setting in conversations too.** The
  threaded view always showed them at the top regardless of Appearance → “Reader
  actions” = bottom; it now respects the setting.

### Added
- **Aggressive GPU freeing for Ollama.** A “Free GPU after” setting (immediately /
  30s / 1m / 5m / 30m / keep loaded) controls how long Ollama keeps the model in
  VRAM — set via the native `/api/chat` `keep_alive`. On top of that, RaplMail
  unloads the model when you **close the AI assistant** and when you **leave a
  message** where you used AI, so the GPU frees as soon as you’re done.

## [0.4.5] — 2026-07-04

### Fixed
- **AI reply now answers in the email’s language** (it was always English). The
  drafter is instructed to match the thread’s language — a Czech email gets a
  Czech reply.
- **No more “###CHIPS” gibberish in AI replies.** Small local models don’t emit
  the exact quick-reply marker we ask for (they write `###CHIPS|`, `CHIPS:`, …),
  so it leaked into the reply. Parsing now tolerates those variants and the
  marker never reaches the reply body; the quick-reply chips still work.
- **The AI assistant, Catch-me-up, and AI reply now read the full email** — not
  just the subject and sender. Message bodies are fetched on demand (and cached)
  when building AI context, so answers are based on the real content.
- **Ctrl+K (command palette) works while a message is open.** The email-preview
  iframe was swallowing the shortcut; it’s now forwarded to the app (along with
  Ctrl+N and Escape).

### Added
- **The AI assistant is one click away.** An AI button in the message-list header
  opens it — seeded with the open message/conversation as context — alongside
  Ctrl+K and the reader’s Assistant chip.

## [0.4.4] — 2026-07-04

### Fixed
- **Ollama “model not found” (404).** If no model was explicitly chosen, the
  backend fell back to a default (`llama3.2`) you may not have pulled, so every
  AI call 404’d. RaplMail now auto-selects an installed model when the configured
  one isn’t actually present — AI works out of the box once Ollama has any model.

### Added
- **AI assistant is now a movable, minimizable window** (not a modal). It docks
  like the compose window, so you can keep clicking and reading while it’s open,
  drag it anywhere, and **minimize it into a floating “AI” circle** that reopens
  it with your conversation intact.
- **Free the GPU on demand.** A “Free GPU (unload model)” button in Settings →
  AI assistant tells Ollama to evict the loaded model from VRAM immediately.
  Ollama keeps a model resident for a few minutes after each request (for fast
  follow-ups) — this is the idle GPU use you may notice; now you can reclaim it
  instantly. Background semantic indexing also uses a 30-second keep-alive so it
  never pins the GPU.
- **Manage Ollama from RaplMail.** The Ollama panel shows the running version and
  has an **Update Ollama** button (`winget upgrade`), alongside the existing
  install/pull controls.

## [0.4.3] — 2026-07-04

### Added
- **AI writing assistant in the composer.** An “✨ AI” button in the compose
  toolbar: rephrase, improve, shorten, expand, fix spelling & grammar, change
  tone (professional/friendly/formal/concise/confident), and translate to 8
  languages — plus a freeform “Ask AI to…” box. Works on your selection or the
  whole draft, in both rich-text and Markdown, and drops the result straight in.
- **Ask about an email.** In the reader, type “tl;dr” (or anything) about the
  open message or thread, with one-tap TL;DR / Action items / Key points chips.
- **AI assistant with context.** A chat window (Ctrl+K → “AI assistant”, the
  reader’s Assistant chip, or the composer’s AI menu) where you add emails as
  context — the open message, a whole conversation, or the current list — and
  ask across them (“summarize these”, “who still needs a reply?”, “draft an
  answer from these three”). Multi-turn; copy an answer or turn it into a new email.
- **Multi-language spell-check.** The composer has a spell-check language
  switcher (Auto/EN/CS/SK/DE/PL/ES/FR/IT, remembered) so an English UI can still
  check Czech mail. (WebView2 checks one language at a time; needs the OS’s
  dictionary for that language installed.)

### Fixed
- **AI buttons no longer hidden when using Ollama.** “Show AI buttons” had no
  effect with the keyless local Ollama provider because every gate still required
  an API key. AI actions now appear whenever a provider is usable — a cloud key
  **or** local Ollama.

## [0.4.2] — 2026-07-04

### Added
- **Spell check in the composer.** Misspellings are underlined as you type in the
  subject, message body, and Markdown editor, with right-click corrections —
  using your OS dictionaries for the current UI language. Native to the WebView,
  fully offline, no dependency. Toggle in Settings → General → Compose window.
- **Ollama — first-class local AI.** A new keyless "Ollama (local, private)"
  provider defaults to `http://localhost:11434` and powers all AI features
  (Catch-me-up, AI reply, triage scores, morning briefing) **completely
  offline** — nothing leaves your machine. The setup panel detects Ollama,
  lists your pulled models, pulls a model with a live progress bar, and offers
  a one-click install (winget) with a manual-download fallback.
- **Semantic search (meaning-based).** Opt-in local vector search: find "that
  quote about server migration costs" even when the message never used those
  words. Messages are embedded via Ollama or any OpenAI-compatible embeddings
  endpoint and stored locally; search ranks by cosine similarity. Surfaced as a
  **Smart** toggle in the advanced-search modal, with a background indexer and a
  "Build / update index" button in Settings. Vectors never leave the machine.

### Changed
- The AI assistant's "morning briefing", summaries, and triage now work with a
  keyless local provider (Ollama), not only with a cloud API key.

## [0.4.1] — 2026-07-04

### Performance
- **Smoother scrolling.** Hovering a row prefetches its body only after a 120 ms
  dwell — previously, wheel-scrolling swept rows under the cursor and fired a
  full-body fetch (+ JSON parse on the UI thread) for every row that passed,
  which is what made scrolling feel sluggish. Offscreen row placeholders also
  now match the real row height, so the scrollbar doesn't drift.
- **Instant view switches.** Changing folder/category/search used to animate
  ~100 rows flying out at once (keeping old + new lists mounted while they did);
  switches now tear down instantly. Triage animations within a view are kept.
- **WebView memory released when hidden.** When the window hides to the tray or
  minimizes, the shell now tells WebView2 to aggressively release renderer
  memory (JS heap, image/GPU caches) and restores normal behavior on show/focus.
  A tray-resident window previously kept hundreds of MB alive while invisible.

## [0.4.0] — 2026-07-04

### Added
- **Device sync over your own mailbox — local-first, no cloud, no server.**
  Settings → **Device sync**: enable it, pick a **carrier account** (configured on
  both machines) and set a **sync passphrase** (the same on every device), and
  RaplMail keeps your installs in step. On a change (or **Sync now**), your
  changed per-message state (done / snooze / pin) plus config (settings, rules,
  signatures, sender tags) is encrypted with a passphrase-derived key (the
  provider only sees ciphertext) and appended to a hidden `RaplMail Sync` folder;
  every device reads that folder, decrypts, and merges.
  - Fixes cross-device **"done" not propagating**: the old mechanism used a custom
    IMAP keyword that Exchange/M365 (and many servers) silently drop. This channel
    doesn't depend on custom-keyword support, so it works everywhere.
  - Merge is keyed by **(account email + Message-ID)** with **last-writer-wins** by
    timestamp; state for not-yet-synced mail is parked and applied when it arrives.
    Device-local sync settings are protected, so a peer's config can't disable your
    sync or change your carrier account.
  - The sync folder is hidden from the app, and each sync message is self-describing
    (marked read, plain-language body) so it never looks alarming in another mail
    client. Verified by 8 unit tests + the full 36-test backend suite; end-to-end
    two-machine validation is left to the user.

## [0.3.5] — 2026-07-04

### Changed
- **Security shown as pills, not stacked rows.** A signed-and-authenticated
  message used to stack two or three full-width bars in the reader header
  (S/MIME + "sender authenticated" + trust/warnings), wasting vertical space.
  Trust, authentication, PGP and S/MIME now collapse into a single compact **pill
  strip** — each pill shows its detail on hover and expands inline (with its
  action, e.g. Mark safe / Undo) when clicked.
- **Spark-style recipient pills.** Compose **To:/Cc:** now render committed
  recipients as name pills — a picked contact shows as "Jane Doe", not the raw
  address — with backspace-to-edit and one-click removal. The value RaplMail
  sends is unchanged (still a comma-separated address string); only the input got
  friendlier.
- **`g` is now a quick-jump palette.** The invisible `g`+letter chord became a
  VS Code Ctrl+T-style palette: `g` opens a searchable list of destinations
  (Inbox, All Inboxes, Snoozed, Follow-ups, Paper Trail, Newsletter feed,
  Calendar, Scheduled, Settings) with hint letters shown. The single-letter
  accelerators still fire instantly, so `g i` etc. stay fast — the menu just
  makes them discoverable and type-to-filter.

### Added
- **Advanced search modal.** A new button beside the search bar opens a structured
  builder: From / To with live contact autocomplete, Subject, "has the words"
  (body), a status segment (Unread / Read / Flagged / Done), a has-attachment
  toggle, and quick presets. It reads and writes the same query the inline bar and
  backend understand, previews the query it will run, and only emits operators the
  backend actually supports.

### Fixed
- **List no longer flickers on sync.** Background syncs used to replace every row
  object wholesale, re-rendering the whole list (avatars, shields, focus) and
  making it blink each cycle. The refresh now merges results **by id in place**,
  reusing the existing row object and only updating fields that changed — so
  unchanged rows don't re-render. Applied to the main list and expanded
  Smart-Inbox category cards.

## [0.3.4] — 2026-07-04

### Changed
- **Conversations open as conversations.** Clicking a threaded message now shows
  the whole conversation immediately — the "View conversation" banner (and its
  extra click) is gone. The message you clicked, the newest one, and unread
  replies auto-expand (and are marked read); the view scrolls to the one you
  opened. Message bodies auto-size into one natural scroll instead of fixed-height
  inner scrollboxes, and links inside them open in your browser like everywhere
  else.
- **Thread view got real actions.** Reply / Reply-all / Forward on every expanded
  message (with proper quoting and attachment carry-over), Reply / Forward /
  **Archive all** / Done all for the whole conversation, per-message attachment
  chips, and a warning badge on messages that failed authentication.
- **Triage without leaving the reader.** Archive, Snooze (with the preset menu),
  and Delete joined the reader's action bar (configurable in Appearance, like
  before), and the sender menu gained **Create rule**. Archiving/deleting a single
  row now shows a toast instead of silently vanishing the mail.
- **Escape goes back.** Esc closes the open message/conversation and returns to
  the list.

### Added
- **Full keyboard triage.** New (rebindable) shortcuts: `r` reply, `f` forward,
  `a` archive, `Delete` delete, `u` toggle read — `a`/`Delete`/`u` act on the
  focused row, `r`/`f` on the open message or conversation. The `?` cheatsheet and
  Settings → Shortcuts cover them.
- **One-click screening.** In the Screener, hovering a row now offers
  **Approve / Block** directly — no need to open each first-time sender's mail.

### Performance
- **Much lighter message queries.** Listing, searching, threads, bulk actions and
  the sync engine's flag reconcile no longer load the cached HTML/text bodies
  they never used — previously every list page dragged up to 100 full bodies
  through the ORM, and every sync cycle re-read 400 per folder.
- **Database tuned.** New composite (folder+date, category+date) and snooze
  indexes; a 128 MB shared memory-map for reads (per-connection heap cache
  trimmed to 4 MB in exchange); WAL size capped.
- **Leaner, quieter backend.** JSON responses now serialize with orjson; the
  per-request access log is off (app logs still feed the Debug window); OAuth/
  HTTP/KDF libraries load on first use instead of at boot; long-lived objects are
  frozen out of garbage-collector scans; two unused libraries dropped from the
  bundle.

## [0.3.3] — 2026-07-03

### Added
- **Export .eml (Safe Export).** From a message's sender menu, download it as a
  `.eml` with internal routing headers (Received / X-Originating-IP / provider
  internals) and hidden tracking pixels stripped out first.
- **S/MIME — end to end.** Building on the 0.3.2 foundation: the reader now shows
  an S/MIME shield for signed mail (with the signer) and decrypts encrypted mail
  with your imported certificate, and the composer gained **S/MIME sign / encrypt**
  toggles (shown once a certificate is set up) that send a proper signed/encrypted
  message. Sits alongside OpenPGP.

## [0.3.2] — 2026-07-03

### Added
- **Markdown compose.** A new **MD** button in the composer lets you write in
  Markdown (headings, bold/italic, inline + fenced code, links, lists, quotes);
  it's compiled to clean, inline-styled HTML on send, with a plain-text version
  attached automatically. Toggle back to rich text anytime.
- **S/MIME (X.509) — foundation.** A new **Settings → S/MIME** tab imports your
  `.p12`/`.pfx` certificate + key and stores correspondents' certificates. Under
  the hood, the crypto engine (sign, encrypt, decrypt, inspect signed mail) is in
  place and unit-tested. Reading/writing S/MIME mail from the reader and composer
  is wired up in a follow-up.

## [0.3.1] — 2026-07-03

### Added
- **Multiple AI providers.** Settings → General → AI assistant now lets you pick
  Anthropic (Claude), OpenAI, or any OpenAI-compatible endpoint (Groq, OpenRouter,
  Together, Ollama, LM Studio — with a base-URL field). Your key still stays local
  and calls go straight to the provider.
- **Inline first-time screener.** Opening inbox mail from a sender you've never
  heard from now shows an "accept this sender?" bar right in the reader (Approve
  adds them to contacts, Block creates a block rule) — no need to live in the
  separate Screener view.
- **Webhook & script rule actions.** Rules can now **POST to a webhook** (sends a
  JSON summary of the message to a local URL — n8n / Node-RED / Home Assistant) or
  **run a local script** (your command, with the mail details in `RAPLMAIL_*`
  environment variables). The mail is still delivered normally.
- **Subscription Audit** (Settings → Utility). Lists every mailing list you get
  with how much you've actually read in the last 30 days (dormant ones first), plus
  one-click unsubscribe and one-click / batch auto-archive.

### Changed
- **Safer forwarding.** Forwarding a message now strips hidden 1×1 tracking pixels
  from the body by default, so you don't re-arm the sender's trackers for whoever
  you forward to.

## [0.3.0] — 2026-07-03

### Fixed
- **Signature diacritics no longer mangled on send.** Outgoing mail was serialized
  with `\n` line endings, so quoted-printable soft breaks went out as bare `=\n`;
  strict decoders then corrupted the byte after each break ("Lukáš" → "Luká…=A1",
  "Republic" → "=epublic", `<span>` → `<=pan>`). Mail is now built with the SMTP
  policy (`\r\n`), so Czech characters and markup survive intact.
- **Compose picks the right From.** Composing while reading a message now defaults
  the From to the account/alias the mail was addressed to (not always account #1),
  and inserts that account's signature automatically.
- **Your reply shows up in the conversation.** Replies reliably thread onto the
  original (threaded via In-Reply-To), and the reader gained a **View conversation**
  banner — works in Smart Inbox too — that live-updates when a sync lands, so a
  reply you just sent appears without reopening the message.
- **Smart Inbox groups stay put while you read.** Opening the last unread message
  of a group no longer makes the group card jump to the end of the day mid-read.

### Added
- **Link hygiene / tracking-parameter stripper.** Links in mail are cleaned before
  you click: `utm_*`, `fbclid`, `gclid`, `mc_eid`, `mkt_tok`, HubSpot/Meta/Matomo
  params, etc. are removed, and redirect wrappers (Google `/url?q=`, Outlook
  SafeLinks, `l.facebook.com`, …) are unwrapped to — and hover-previewed as — the
  real destination. On by default; "Show original" leaves links untouched.
- **Git patch / diff rendering in the reader.** `<pre>` blocks and pasted patches
  that look like a unified diff are auto-detected and color-coded (added / removed /
  hunk / file headers).

### Changed
- **Lower memory footprint.** Per-connection SQLite page cache capped (`cache_size`
  ≈ 10 MB, `temp_store=MEMORY`); idle IMAP pool connections are dropped after 10
  minutes instead of kept warm forever; the avatar warm-set is bounded.

## [0.2.18] — 2026-07-03

### Added
- **English + Czech localization.** A new in-app language setting (Auto / English
  / Čeština) in Settings → General and in onboarding. The UI switches language
  live - no restart. Primary chrome is translated (sidebar, settings, notifications,
  rules, command palette, mail list, reader, compose, onboarding, boot screen);
  anything not yet translated falls back to English.
- **First-run onboarding.** A short welcome wizard on a fresh install: pick your
  language, pick a theme (live preview), and flip on Smart Inbox / notifications /
  Start with Windows. Everything applies as you go and can be changed later; press
  Skip anytime.
- **Boot loading animation.** Starting RaplMail now shows an animated splash
  (ring + wordmark + dots) instead of a blank "Starting…" line while the backend
  warms up. Respects reduced-motion.
- **"Mute notifications" mail rule.** A new rule action that lets mail arrive
  normally but stops the ding + popup — mute by sender, domain, subject, or a
  whole **category** (e.g. "mute notifications from newsletters"). Also a one-click
  **Mute notifications from sender** in the right-click menu. Different from "Mute
  sender", which hides the mail entirely.
- **Notification volume.** A volume slider for the new-mail sound in
  Settings → General → Notifications (the Play preview and live ding follow it).

### Changed
- **Smart Inbox is the default view.** New installs open straight into the grouped
  Smart Inbox instead of a flat list (existing preferences are respected).
- **Start with Windows** is reconciled with the OS on every launch, so the toggle
  and the real startup registration can't drift out of sync; it's also offered
  during onboarding.

### Fixed
- **No more empty notifications.** RaplMail sometimes popped a blank "New message"
  with nothing new in the inbox — it was counting mail that landed in Sent /
  Archive / Junk / other folders (including copies synced from another device).
  Notifications now fire only for genuinely new **inbox** mail that you'll actually
  see (unread, not filtered away by a rule, not notification-muted).

## [0.2.17] — 2026-07-02

### Changed
- **"New" now means recent unread.** The Smart Inbox "N new" badge counts mail
  that's **unread AND arrived in the last 3 days** — not every unread message
  ever. So a group with 4 mails from today reads "4 new" instead of "75".
- **Click the "N new" badge** to open just those new mails inline; a **"See all
  in this group"** link below them jumps to the whole category (read included).
  The group header (or chevron) still opens everything directly.
- Groups float to the top based on **new** mail now (recent unread), matching
  what the badge shows.

### Fixed
- **Unread counts update instantly.** Opening or reading a message now
  decrements the group badge, the sidebar folder count, and the taskbar badge
  **immediately**, instead of waiting for the next sync to catch up.

### Added
- **New-mail sound.** A short chime plays when new mail arrives (even while the
  app is focused). Pick from several tones — Ding, Chime, Marimba, Pop, Glass —
  or turn it off, in Settings → General → Notifications, with a Play button to
  preview. Sounds are generated on the fly (no files, works offline).

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
