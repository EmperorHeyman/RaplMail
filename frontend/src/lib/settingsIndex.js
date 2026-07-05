// A flat index of the individual settings the search box can jump to, so typing
// "undo send" or "keep alive" surfaces the EXACT control — not just the category
// it happens to live in. Each entry: { tab, label, kw }.
//   tab   — settings tab id (must match Settings.svelte `tabs`)
//   label — the human name of the setting (also used to flash it in the panel)
//   kw    — extra search terms / synonyms (EN + a few CZ) so fuzzy queries hit
//
// Labels stay concise and match the on-screen wording where possible so the
// "flash the setting" jump can find it in the rendered panel.
export const SETTINGS_INDEX = [
  // ── General ────────────────────────────────────────────────────────────────
  { tab: "general", label: "Undo send delay", kw: "undo send cancel recall window seconds zpět odeslání" },
  { tab: "general", label: "Confirm before sending", kw: "confirm warning send potvrdit" },
  { tab: "general", label: "Smart Inbox", kw: "smart inbox group categories chytrá schránka" },
  { tab: "general", label: "Conversation threading", kw: "thread threading conversation group vlákna konverzace" },
  { tab: "general", label: "Bundle notification senders", kw: "bundle bundles newsletters collapse senders" },
  { tab: "general", label: "New mail notifications", kw: "notify desktop notification new mail oznámení" },
  { tab: "general", label: "Notification sound", kw: "sound ding chime pop zvuk" },
  { tab: "general", label: "Notification volume", kw: "volume loud hlasitost" },
  { tab: "general", label: "Only notify when unfocused", kw: "focus background unfocused notify" },
  { tab: "general", label: "Quiet hours", kw: "quiet hours do not disturb night silence tiché hodiny" },
  { tab: "general", label: "Follow-up reminders", kw: "followup follow up nudge reply days vyřízení" },
  { tab: "general", label: "Screener", kw: "screener first time sender hey approve filtr odesílatelů" },
  { tab: "general", label: "Auto-BCC", kw: "bcc auto blind copy domain skrytá kopie" },
  { tab: "general", label: "Start with Windows", kw: "startup launch login boot autostart tray spustit" },
  { tab: "general", label: "Minimize to tray", kw: "tray minimize close background lišta" },
  { tab: "general", label: "Check for updates", kw: "update updates version upgrade aktualizace" },
  { tab: "general", label: "Read receipts", kw: "read receipt tracking confirmation potvrzení" },
  { tab: "general", label: "Block trackers", kw: "tracker pixel privacy block images spy sledování" },
  { tab: "general", label: "Language", kw: "language english czech cs locale jazyk" },
  { tab: "general", label: "Backup & export settings", kw: "export backup save settings import migrate záloha" },

  // ── Appearance ───────────────────────────────────────────────────────────────
  { tab: "appearance", label: "Theme preset", kw: "theme preset dark light true black high contrast color motiv vzhled" },
  { tab: "appearance", label: "Theme mode", kw: "auto day night manual mode režim" },
  { tab: "appearance", label: "Custom colors", kw: "custom color colour token variable palette accent barvy" },
  { tab: "appearance", label: "Text & UI size", kw: "scale zoom font size ui bigger smaller velikost" },
  { tab: "appearance", label: "Corner roundness", kw: "radius corner rounded roh zaoblení" },
  { tab: "appearance", label: "Email appearance", kw: "email dark adaptive original render white body vzhled emailu" },
  { tab: "appearance", label: "Reply / action buttons", kw: "reader actions reply forward done position top bottom tlačítka" },
  { tab: "appearance", label: "Collapse quoted replies", kw: "quote collapse quoted reply history citace" },
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
  { tab: "rules", label: "Rules & domain blocking", kw: "rule rules block domain sender filter move archive delete pravidla" },
  { tab: "rules", label: "Mute notifications from sender", kw: "mute notification silence sender ztlumit" },
  { tab: "signature", label: "Signature", kw: "signature footer image html podpis" },
  { tab: "snippets", label: "Snippets & templates", kw: "snippet template canned reply expander šablony" },
  { tab: "shortcuts", label: "Keyboard shortcuts", kw: "keyboard shortcut keybinding hotkey zkratky" },
  { tab: "aliases", label: "Aliases", kw: "alias aliases plus address subaddress" },
  { tab: "pgp", label: "PGP encryption", kw: "pgp gpg openpgp encrypt sign key" },
  { tab: "smime", label: "S/MIME certificate", kw: "smime s/mime certificate p12 pfx x509" },
  { tab: "calendar", label: "Calendar & contacts (CalDAV)", kw: "calendar caldav carddav contacts subscribe kalendář" },
  { tab: "sync", label: "Device sync", kw: "sync device link cross machine passphrase synchronizace" },
  { tab: "rapldesk", label: "RaplDesk tickets", kw: "rapldesk ticket api helpdesk support" },
  { tab: "utility", label: "Subscription audit", kw: "subscription unsubscribe audit newsletter cleanup dormant" },
  { tab: "debug", label: "Debug logs", kw: "debug log logs console diagnostics troubleshoot" },
];
