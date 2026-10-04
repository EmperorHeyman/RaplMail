// A flat index of the individual settings the search box can jump to, so typing
// "undo send" or "keep alive" surfaces the EXACT control - not just the category
// it happens to live in. Each entry: { tab, label, kw }.
//   tab   - settings tab id (must match Settings.svelte `tabs`)
//   label - the human name of the setting (also used to flash it in the panel)
//   kw    - extra search terms / synonyms (EN + a few CZ) so fuzzy queries hit
//
// Labels stay concise and match the on-screen wording where possible so the
// "flash the setting" jump can find it in the rendered panel.
export const SETTINGS_INDEX = [
  // ── Inbox ──────────────────────────────────────────────────────────────────
  { tab: "inbox", label: "Inbox view", kw: "smart inbox unified all inboxes combined per account chytrá schránka zobrazení" },
  { tab: "inbox", label: "Smart Inbox groups", kw: "smart inbox group groups categories strip order newsletters skupiny chytrá schránka" },
  { tab: "inbox", label: "Show new mail in the list until it's read", kw: "new mail inline grouped tag nová pošta" },
  { tab: "inbox", label: "Open next after Done", kw: "open next done triage další" },
  { tab: "inbox", label: "Conversation threading", kw: "thread threading conversation group vlákna konverzace" },
  { tab: "inbox", label: "Collapse quoted replies", kw: "quote collapse quoted reply history citace" },
  { tab: "inbox", label: "Syntax-highlight code blocks", kw: "code highlight syntax pre kód" },
  { tab: "inbox", label: "Follow-up nudge", kw: "followup follow up nudge reply days vyřízení připomenout" },
  { tab: "inbox", label: "Newsletter Feed", kw: "newsletter feed sidebar kanál" },
  { tab: "inbox", label: "Paper Trail", kw: "paper trail receipts orders sidebar doklady" },
  { tab: "inbox", label: "Snooze & send-later times", kw: "snooze later today morning evening schedule time odložit čas" },

  // ── Compose ────────────────────────────────────────────────────────────────
  { tab: "compose", label: "Compose window", kw: "compose docked panel separate window corner psaní okno" },
  { tab: "compose", label: "Spell check", kw: "spell check spelling dictionary pravopis" },
  { tab: "compose", label: "Undo send", kw: "undo send cancel recall window seconds delay zpět odeslání zrušit" },
  { tab: "compose", label: "Auto-BCC", kw: "bcc auto blind copy domain skrytá kopie" },
  { tab: "compose", label: "Signatures", kw: "signature footer image html podpis" },
  { tab: "compose", label: "Snippets & templates", kw: "snippet template canned reply expander šablony úryvky" },

  // ── Notifications ────────────────────────────────────────────────────────────
  { tab: "notifications", label: "Notify me about new mail", kw: "notify desktop notification new mail popup oznámení" },
  { tab: "notifications", label: "Only when RaplMail isn't focused", kw: "focus background unfocused notify" },
  { tab: "notifications", label: "Quiet hours", kw: "quiet hours do not disturb night silence tiché hodiny" },
  { tab: "notifications", label: "New-mail sound", kw: "sound ding chime pop zvuk" },
  { tab: "notifications", label: "Volume", kw: "volume loud hlasitost" },
  { tab: "notifications", label: "Your own sounds", kw: "custom sound upload clip vlastní zvuk" },

  // ── Backup & sync / Integrations / General ───────────────────────────────────
  { tab: "backup", label: "Backup & move to another PC", kw: "export backup save settings import migrate restore rmail záloha" },
  { tab: "backup", label: "Device sync", kw: "sync device link cross machine passphrase synchronizace" },
  { tab: "backup", label: "Device name", kw: "device name friendly label rename main work pc název zařízení" },
  { tab: "backup", label: "Sync account passwords (encrypted)", kw: "credential password sync accounts encrypted vault chacha aead hesla účty" },
  { tab: "integrations", label: "Local API", kw: "local api metrics prometheus home assistant esp32 grafana" },
  { tab: "integrations", label: "New-mail webhook", kw: "webhook automation n8n node-red home assistant post url outbound" },
  { tab: "integrations", label: "RAPL Desk", kw: "rapldesk ticket tickets api helpdesk support" },
  { tab: "general", label: "Language", kw: "language english czech cs locale jazyk" },
  { tab: "general", label: "Check for updates", kw: "update updates version upgrade aktualizace" },
  { tab: "general", label: "Minimize to tray on close", kw: "tray minimize close background lišta" },
  { tab: "general", label: "Launch at login", kw: "startup launch login boot autostart tray spustit" },

  // ── Security ─────────────────────────────────────────────────────────────────
  { tab: "security", label: "Suspicious-sender screening", kw: "phishing spoof spoofing impersonation brand lookalike suspicious flag scam prověřování podvrh" },
  { tab: "security", label: "Blocked domains", kw: "domain blocker blocklist tld ru block sender quarantine junk zablokované domény" },
  { tab: "security", label: "AI screening", kw: "ai screening scam phishing check verdict manual automatic prověření ai" },
  { tab: "security", label: "Block tracking pixels", kw: "tracker pixel privacy block images spy sledování" },
  { tab: "security", label: "Screener", kw: "screener first time sender hey approve filtr odesílatelů" },
  { tab: "security", label: "Startup password", kw: "startup password lock unlock master boot auto-unlock heslo" },
  { tab: "security", label: "Rich link previews", kw: "link preview unfurl card og image náhled odkazu" },
  { tab: "security", label: "Tracking aliases", kw: "alias aliases plus address subaddress tracking leak" },

  // ── Appearance ───────────────────────────────────────────────────────────────
  { tab: "appearance", label: "Use the Windows accent color", kw: "dynamic color colour material you windows accent wallpaper system barva zvýraznění dynamické barvy" },
  { tab: "appearance", label: "Or pick a color", kw: "dynamic color colour seed accent palette material you pick barva" },
  { tab: "appearance", label: "Light or dark", kw: "light dark system mode theme brightness světlý tmavý režim" },
  { tab: "appearance", label: "Pure black background", kw: "pure black oled amoled true black dark černé pozadí" },
  { tab: "appearance", label: "Theme preset", kw: "classic theme preset dark light true black high contrast color motiv vzhled klasické motivy" },
  { tab: "appearance", label: "Theme mode", kw: "classic auto day night manual mode režim" },
  { tab: "appearance", label: "Custom colors", kw: "custom color colour token variable palette accent barvy" },
  { tab: "appearance", label: "Text & UI size", kw: "scale zoom font size ui bigger smaller velikost" },
  { tab: "appearance", label: "Corner roundness", kw: "radius corner rounded roh zaoblení" },
  { tab: "appearance", label: "Email appearance", kw: "email dark adaptive original render white body vzhled emailu" },
  { tab: "appearance", label: "Reply / action buttons", kw: "reader actions reply forward done position top bottom tlačítka" },
  { tab: "appearance", label: "Relative time", kw: "relative time ago date čas" },
  { tab: "appearance", label: "Avatar style", kw: "avatar initials image sender disc logo" },
  { tab: "appearance", label: "Custom CSS", kw: "css custom style stylesheet advanced" },

  // ── AI assistant ─────────────────────────────────────────────────────────────
  { tab: "ai", label: "AI provider", kw: "ai provider ollama openai anthropic claude gpt local keyless" },
  { tab: "ai", label: "API key", kw: "api key token secret" },
  { tab: "ai", label: "Active model", kw: "model llm gpt claude gemma qwen mistral llama" },
  { tab: "ai", label: "Find & download models", kw: "ollama search library model download pull install" },
  { tab: "ai", label: "One-click setup", kw: "ollama install setup quick fast balanced best" },
  { tab: "ai", label: "Free GPU after", kw: "gpu vram keep alive unload adaptive free memory" },
  { tab: "ai", label: "Semantic search", kw: "semantic vector embedding meaning search index" },
  { tab: "ai", label: "Embedding model", kw: "embedding model nomic vector reindex" },

  // ── Other tabs (jump to the section; these are single-purpose) ───────────────
  { tab: "accounts", label: "Add an account", kw: "account add email imap smtp oauth microsoft google gmail m365 účet" },
  { tab: "accounts", label: "Workspaces", kw: "workspace workspaces group accounts context pracovní prostory" },
  { tab: "rules", label: "Rules & domain blocking", kw: "rule rules block domain sender filter move archive delete pravidla" },
  { tab: "rules", label: "Mute notifications from sender", kw: "mute notification silence sender ztlumit" },
  { tab: "shortcuts", label: "Keyboard shortcuts", kw: "keyboard shortcut keybinding hotkey zkratky" },
  { tab: "shortcuts", label: "The search key opens", kw: "search key inline bar window modal hledání" },
  { tab: "shortcuts", label: "Keyboard hints under the mail list", kw: "hints hint bar keyboard nápověda" },
  { tab: "encryption", label: "PGP encryption", kw: "pgp gpg openpgp encrypt sign key" },
  { tab: "encryption", label: "S/MIME certificate", kw: "smime s/mime certificate p12 pfx x509" },
  { tab: "contacts", label: "Contacts", kw: "address book contacts people adresář kontakty" },
  { tab: "calendar", label: "Calendar & contacts (CalDAV)", kw: "calendar caldav carddav contacts subscribe kalendář" },
  { tab: "calendar", label: "Calendar reminder sound", kw: "reminder sound calendar chime připomínka zvuk" },
  { tab: "calendar", label: "Pop a reminder window", kw: "reminder window popup always on top připomínka okno" },
  { tab: "debug", label: "Debug logs", kw: "debug log logs console diagnostics troubleshoot" },
];
