# RaplMail — Potential Features

A brainstorm of candidate features, biased toward what makes RaplMail distinct:
**local-first, privacy-respecting, power-user / developer-oriented**. Shipped
items live in [ROADMAP.md](ROADMAP.md); this is the "what next" pool. Each entry
notes *what*, *why it fits*, and a rough *how*.

---

## AI & productivity (BYOK — keys in the vault, calls straight from the local backend)

1. **Thread summarize & "Catch me up"**
   *What:* one-click TL;DR of a long thread, and a morning "here's what happened while you were away" digest across the inbox.
   *Why:* the a123/RAPL threads get long and reply-all-heavy; a summary beats re-reading 30 messages.
   *How:* `POST /ai/summarize` feeds the thread's plain-text bodies to the user's chosen model (OpenAI/Anthropic/local Ollama); render the summary above the thread. Cache per thread_id.

2. **Draft & smart reply**
   *What:* "Reply with AI" → drafts a response in your tone from the thread context; quick-reply chips ("Acknowledge", "Decline politely", "Ask for a time").
   *Why:* the Thunderbird pain was friction; this kills the blank-page problem.
   *How:* prompt = thread + a short style sample from the user's Sent folder; insert into the compose editor (still fully editable, never auto-sends).

3. **AI auto-categorize & priority scoring**
   *What:* let the model refine the heuristic categories and assign a 0–100 "importance" score → a "Priority" group at the top of Smart Inbox.
   *Why:* the rule/heuristic categorizer is good but rigid; a model catches nuance ("this newsletter is actually a renewal notice").
   *How:* batch-score new mail in the sync worker (cheap model), store `importance` on Message; opt-in, throttled, cached by Message-ID.

---

## Security & privacy

4. **Encryption-at-rest for the local cache**
   *What:* encrypt the SQLite message DB + cached bodies, unlocked by the existing master password.
   *Why:* the vault already protects credentials, but cached mail sits in plaintext SQLite — a laptop theft reads everything.
   *How:* SQLCipher (or app-level Fernet on body columns) keyed from the Argon2-derived key already in memory after unlock.

5. **PGP / S-MIME sign · encrypt · verify**
   *What:* verify incoming signatures, show a verified badge, and sign/encrypt outgoing mail.
   *Why:* complements the DMARC shield; real end-to-end trust for sensitive RAPL/a123 mail.
   *How:* `python-gnupg` / `cryptography`; key management UI in Settings; inline status in the reader next to the auth shield.

6. **Lookalike / homoglyph & link-mismatch warnings**
   *What:* flag display-name spoofing ("Lukáš Peterek <attacker@evil.ru>"), homoglyph domains (`a123systеms.eu` with a Cyrillic е), and "link text says X but goes to Y".
   *Why:* DMARC catches spoofed *envelopes*; this catches the social-engineering layer DMARC can't.
   *How:* compare display-name domain vs from-domain, normalize Unicode confusables, diff anchor text vs href on body fetch; surface in the reader.

7. **Quiet hours / Do Not Disturb**
   *What:* suppress desktop notifications (and optionally sync) during configured hours or while screen-sharing.
   *Why:* presence-aware snooze proved you like local awareness; this is the inverse.
   *How:* schedule check in the notify path; reuse the idle/presence monitor; setting in General.

---

## Power-user & developer

8. **Full-text search *inside* attachments**
   *What:* index the text of PDFs / Office docs / .txt so search finds content within attachments, not just filenames.
   *Why:* "where's that invoice that mentioned PO-4471" should just work — Paper Trail + deep search.
   *How:* extract text on body fetch (`pypdf`, `python-docx`), add to the FTS row; show a "matched in attachment" hint.

9. **Multiple identities / send-as aliases**
   *What:* per-account aliases (e.g. `isitavancova@` and a `support@` alias) selectable in the From dropdown.
   *Why:* one mailbox often sends under several addresses.
   *How:* `Identity` table (account_id, email, display_name, signature_id); From picker lists them; SMTP envelope-from handling.

10. **Mail merge / personalized bulk send**
    *What:* compose one templated message with `{{name}}`, pick a recipient list (from contacts/CSV), send individualized copies.
    *Why:* the snippet variables already exist; this scales them to outreach without a separate tool.
    *How:* reuse `fillVars`; iterate recipients through the existing send/queue path with a rate limit + per-recipient preview.

11. **Plus-address / alias generator with per-service tracking**
    *What:* generate `you+github@…` style aliases per signup, track which alias a message arrived on, one-click "mute everything to this alias" when it leaks/spams.
    *Why:* privacy power-move; turns the inbox into a tripwire for who sold your address.
    *How:* store generated aliases; on receive, parse the `+tag`; a view grouping mail by alias; mute = rule on the alias.

12. **Per-account health dashboard**
    *What:* connection status, last successful sync, IDLE state, mailbox quota, token expiry, queued/failed actions — at a glance.
    *Why:* with multiple IMAP/OAuth accounts, silent failures are the worst; make them visible.
    *How:* expose `/accounts/{id}/status` (last sync ts, IDLE alive, quota via IMAP `QUOTA`, token exp from MSAL); a Settings panel.

---

## Triage & UX polish

13. **Universal undo for triage**
    *What:* extend the undo-send pattern to archive / delete / move / done / snooze — a brief "Undone? Undo" toast on every destructive action.
    *Why:* fast triage means fat-finger mistakes; undo removes the fear.
    *How:* a small action-history stack in the store; each action records its inverse; toast with Undo wired to it.

14. **VIP senders & a Priority lane**
    *What:* mark people/domains as VIP → a pinned VIP group, stronger notifications, never auto-bundled/screened.
    *Why:* the boss/family should never get lost in Promotions.
    *How:* `vip` flag on Contact / a `vipSenders` setting; Smart Inbox shows a VIP group first; notify path bypasses Quiet Hours for VIPs.

15. **Attachment reminder**
    *What:* if the body says "attached / přikládám / see attachment" but there's no attachment, warn before send.
    *Why:* the universal embarrassment, prevented locally.
    *How:* regex on the body (multi-language list) in `send()`; block with a confirm if no attachments.

16. **Drafts that sync + autosave**
    *What:* autosave compose to a local draft and `APPEND` to the IMAP Drafts folder so an unfinished mail survives a crash and shows on other devices.
    *Why:* the docked compose can be lost; real clients never lose a draft.
    *How:* debounced autosave to a `Draft` table + periodic IMAP APPEND to the Drafts-role folder; restore on reopen.

17. **Keyboard chord shortcuts (`g i`, `g s`, `g c`)**
    *What:* Gmail/Superhuman-style two-key sequences to jump between views.
    *Why:* you already rebound everything to arrows/Ctrl-n; chords are the next speed tier.
    *How:* a small chord state machine layered onto `keyCombo`; configurable in Settings → Shortcuts.

18. **Rich link unfurls in the reader**
    *What:* expand the first prominent link into a title/description/thumbnail card (locally fetched, respecting the tracker blocker).
    *Why:* faster context without opening the browser.
    *How:* backend fetches OpenGraph tags for a link on demand (same TLS-relaxed fetch as favicons); render a card; off by default for privacy.

19. pinned mails

20. fix notifications -- says blocked by OS but I didnt get any popup

21. font size change

22. Invitation fix... : Meeting ohledně celozávodky - plán + co je třeba udělat doesnt categorize as inv even tho it should...