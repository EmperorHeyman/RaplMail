// Misc-UI namespaces: "dash.*" (home dashboard), "newsfeed.*" (Newsletter Feed),
// "merge.*" (mail merge), "vault.*" (master-password gate), "searchbar.*",
// "recip.*" (recipient pills), "sending.*" (send indicator), "grouprow.*".
// Flat "ns.key" → text; {placeholders} are filled by t(key, { ... }).
// Every en key MUST also exist in cs (missing keys fall back to English).
export default {
  en: {
    // Dashboard hero (greeting, stats).
    "dash.greetingNight": "Good night",
    "dash.greetingMorning": "Good morning",
    "dash.greetingAfternoon": "Good afternoon",
    "dash.greetingEvening": "Good evening",
    "dash.statUnread": "unread",
    "dash.statEventOne": "event today",
    "dash.statEventN": "events today",
    "dash.statAccountOne": "account",
    "dash.statAccountN": "accounts",

    // Week strip.
    "dash.thisWeek": "This week",
    "dash.openCalendar": "Open calendar →",
    "dash.today": "Today",
    "dash.tomorrow": "Tomorrow",
    "dash.dowSun": "Sun",
    "dash.dowMon": "Mon",
    "dash.dowTue": "Tue",
    "dash.dowWed": "Wed",
    "dash.dowThu": "Thu",
    "dash.dowFri": "Fri",
    "dash.dowSat": "Sat",

    // Up-next calendar card.
    "dash.upNext": "Up next",
    "dash.calendarLink": "Calendar →",
    "dash.loading": "Loading…",
    "dash.allDay": "all day",
    "dash.untitled": "(untitled)",
    "dash.noEvents": "Nothing scheduled. Add a calendar in Settings → Calendar & Contacts.",

    // Latest-mail card.
    "dash.latestMail": "Latest mail",
    "dash.unreadBadge": "{n} unread",
    "dash.inboxLink": "Inbox →",
    "dash.noSubject": "(no subject)",
    "dash.emptyInbox": "Inbox is empty. 🎉",

    // Ask-AI card.
    "dash.askAi": "Ask AI about your inbox",
    "dash.openChat": "Open chat →",
    "dash.aiPlaceholder": "Ask plainly…  e.g. “shrň nové maily” or “find the audi crash plate email”",
    "dash.ask": "Ask",
    "dash.recapChip": "Recap new mail",
    "dash.needsReplyChip": "Needs a reply?",
    "dash.recapPrompt": "Summarize my new mail",
    "dash.needsReplyPrompt": "Which emails need a reply?",

    // Quick actions.
    "dash.newMessage": "New message",
    "dash.goInbox": "Go to inbox",
    "dash.calendar": "Calendar",

    // Newsletter Feed.
    "newsfeed.title": "Newsletter Feed",
    "newsfeed.refresh": "Refresh",
    "newsfeed.markAllDone": "Mark all done",
    "newsfeed.gathering": "Gathering your newsletters…",
    "newsfeed.empty": "No newsletters right now.",
    "newsfeed.noSubject": "(no subject)",
    "newsfeed.markDone": "Mark done",
    "newsfeed.cleared": "Cleared the feed",
    "newsfeed.loadingMore": "Loading more…",

    // Mail merge: dialog chrome & toasts.
    "merge.title": "Mail merge",
    "merge.close": "Close",
    "merge.pickAccount": "Pick an account",
    "merge.addRecipient": "Add at least one recipient",
    "merge.writeSomething": "Write a subject or body",
    "merge.confirmSendOne": "Send 1 individual message? Each recipient gets their own copy (no shared To/Cc).",
    "merge.confirmSendN": "Send {n} individual messages? Each recipient gets their own copy (no shared To/Cc).",
    "merge.doneOk": "Mail merge done - {sent} sent",
    "merge.doneWithFailures": "Mail merge done - {sent} sent, {failed} failed",

    // Mail merge: template column.
    "merge.from": "From",
    "merge.subject": "Subject",
    "merge.subjectPlaceholder": "Hi {{name}}, your update",
    "merge.bodyLabelPre": "Body - use ",
    "merge.bodyLabelPost": " etc. for columns from your list",
    "merge.bodyPlaceholder": "Hi {{name}},\n\nThanks for…\n\n- Me",
    "merge.appendSignature": "Append my default signature",

    // Mail merge: recipients column & warnings.
    "merge.recipientsLabelPre": "Recipients - paste a CSV (with an ",
    "merge.recipientsLabelPost": " header) or one address per line",
    "merge.recipientOne": "recipient",
    "merge.recipientN": "recipients",
    "merge.columns": "columns:",
    "merge.noColumnPre": "⚠ No column for ",
    "merge.noColumnPost": "- these render empty for every recipient.",
    "merge.blankRowsOne": "⚠ 1 recipient has a blank value for a column you use - they'll get gaps (e.g. \"Hi ,\").",
    "merge.blankRowsN": "⚠ {n} recipients have a blank value for a column you use - they'll get gaps (e.g. \"Hi ,\").",

    // Mail merge: preview & footer.
    "merge.preview": "Preview",
    "merge.prevRecipient": "Previous recipient",
    "merge.nextRecipient": "Next recipient",
    "merge.noSubject": "(no subject)",
    "merge.progress": "{done}/{total} sent",
    "merge.progressFailed": " · {n} failed",
    "merge.cancel": "Cancel",
    "merge.sending": "Sending…",
    "merge.sendOne": "Send 1 message",
    "merge.sendN": "Send {n} messages",

    // Vault gate (master password).
    "vault.noMatch": "Passwords don't match",
    "vault.tooShort": "Use at least 6 characters",
    "vault.unlocked": "Vault unlocked",
    "vault.failed": "Failed",
    "vault.setupSub": "Set a master password to encrypt your accounts on this device.",
    "vault.unlockSub": "Enter your master password to unlock your mail.",
    "vault.masterPassword": "Master password",
    "vault.confirmPassword": "Confirm password",
    "vault.create": "Create vault",
    "vault.unlock": "Unlock",
    "vault.noRecovery": "There's no recovery - if you forget this, your stored credentials are gone.",

    // Search bar.
    "searchbar.remove": "Remove",
    "searchbar.placeholder": "Search…  from:  to:  has:attachment  is:unread  /regex/",
    "searchbar.clear": "Clear search",

    // Recipient input (pills).
    "recip.remove": "Remove",
    "recip.checkOne": "⚠ Check this address: {list}",
    "recip.checkN": "⚠ Check these addresses: {list}",

    // Sending indicator.
    "sending.sending": "Sending…",
    "sending.cancel": "Cancel",

    // Group row (thread / bundle / category rows).
    "grouprow.selectAll": "Select all",
    "grouprow.noSubject": "(no subject)",
    "grouprow.conversation": "conversation",
    "grouprow.bundle": "bundle",
    "grouprow.archiveConversation": "Archive whole conversation",
    "grouprow.doneAll": "Done all",
  },
  cs: {
    // Hlavička nástěnky (pozdrav, statistiky).
    "dash.greetingNight": "Dobrou noc",
    "dash.greetingMorning": "Dobré ráno",
    "dash.greetingAfternoon": "Dobré odpoledne",
    "dash.greetingEvening": "Dobrý večer",
    "dash.statUnread": "nepřečtených",
    "dash.statEventOne": "událost dnes",
    "dash.statEventN": "událostí dnes",
    "dash.statAccountOne": "účet",
    "dash.statAccountN": "účtů",

    // Týdenní pás.
    "dash.thisWeek": "Tento týden",
    "dash.openCalendar": "Otevřít kalendář →",
    "dash.today": "Dnes",
    "dash.tomorrow": "Zítra",
    "dash.dowSun": "Ne",
    "dash.dowMon": "Po",
    "dash.dowTue": "Út",
    "dash.dowWed": "St",
    "dash.dowThu": "Čt",
    "dash.dowFri": "Pá",
    "dash.dowSat": "So",

    // Karta nadcházejících událostí.
    "dash.upNext": "Nadcházející",
    "dash.calendarLink": "Kalendář →",
    "dash.loading": "Načítání…",
    "dash.allDay": "celý den",
    "dash.untitled": "(bez názvu)",
    "dash.noEvents": "Nic není naplánováno. Přidejte kalendář v Nastavení → Kalendář a kontakty.",

    // Karta nejnovější pošty.
    "dash.latestMail": "Nejnovější pošta",
    "dash.unreadBadge": "{n} nepřečtených",
    "dash.inboxLink": "Doručená pošta →",
    "dash.noSubject": "(bez předmětu)",
    "dash.emptyInbox": "Schránka je prázdná. 🎉",

    // Karta AI dotazů.
    "dash.askAi": "Zeptejte se AI na svou schránku",
    "dash.openChat": "Otevřít chat →",
    "dash.aiPlaceholder": "Ptejte se přirozeně…  např. „shrň nové maily“ nebo „najdi e-mail o nabouraném audi“",
    "dash.ask": "Zeptat se",
    "dash.recapChip": "Shrnout novou poštu",
    "dash.needsReplyChip": "Vyžaduje odpověď?",
    "dash.recapPrompt": "Shrň mi nové maily",
    "dash.needsReplyPrompt": "Které maily vyžadují odpověď?",

    // Rychlé akce.
    "dash.newMessage": "Nová zpráva",
    "dash.goInbox": "Přejít do schránky",
    "dash.calendar": "Kalendář",

    // Čtečka newsletterů.
    "newsfeed.title": "Čtečka newsletterů",
    "newsfeed.refresh": "Obnovit",
    "newsfeed.markAllDone": "Označit vše jako hotové",
    "newsfeed.gathering": "Načítám vaše newslettery…",
    "newsfeed.empty": "Momentálně žádné newslettery.",
    "newsfeed.noSubject": "(bez předmětu)",
    "newsfeed.markDone": "Označit jako hotové",
    "newsfeed.cleared": "Čtečka vyčištěna",
    "newsfeed.loadingMore": "Načítám další…",

    // Hromadná korespondence: okno a hlášení.
    "merge.title": "Hromadná korespondence",
    "merge.close": "Zavřít",
    "merge.pickAccount": "Vyberte účet",
    "merge.addRecipient": "Přidejte alespoň jednoho příjemce",
    "merge.writeSomething": "Napište předmět nebo text zprávy",
    "merge.confirmSendOne": "Odeslat 1 samostatnou zprávu? Každý příjemce dostane vlastní kopii (bez společného Komu/Kopie).",
    "merge.confirmSendN": "Odeslat {n} samostatných zpráv? Každý příjemce dostane vlastní kopii (bez společného Komu/Kopie).",
    "merge.doneOk": "Hromadná korespondence dokončena - odesláno: {sent}",
    "merge.doneWithFailures": "Hromadná korespondence dokončena - odesláno: {sent}, selhalo: {failed}",

    // Hromadná korespondence: sloupec šablony.
    "merge.from": "Od",
    "merge.subject": "Předmět",
    "merge.subjectPlaceholder": "Dobrý den, {{name}}, novinky pro vás",
    "merge.bodyLabelPre": "Text zprávy - použijte ",
    "merge.bodyLabelPost": " apod. pro sloupce z vašeho seznamu",
    "merge.bodyPlaceholder": "Dobrý den, {{name}},\n\nděkuji za…\n\n- já",
    "merge.appendSignature": "Připojit můj výchozí podpis",

    // Hromadná korespondence: sloupec příjemců a varování.
    "merge.recipientsLabelPre": "Příjemci - vložte CSV (se sloupcem ",
    "merge.recipientsLabelPost": ") nebo jednu adresu na řádek",
    "merge.recipientOne": "příjemce",
    "merge.recipientN": "příjemců",
    "merge.columns": "sloupce:",
    "merge.noColumnPre": "⚠ Chybí sloupec pro ",
    "merge.noColumnPost": "- u všech příjemců zůstanou prázdné.",
    "merge.blankRowsOne": "⚠ 1 příjemce má prázdnou hodnotu ve sloupci, který používáte - ve zprávě vzniknou mezery (např. „Dobrý den ,“).",
    "merge.blankRowsN": "⚠ {n} příjemců má prázdnou hodnotu ve sloupci, který používáte - ve zprávě vzniknou mezery (např. „Dobrý den ,“).",

    // Hromadná korespondence: náhled a patička.
    "merge.preview": "Náhled",
    "merge.prevRecipient": "Předchozí příjemce",
    "merge.nextRecipient": "Další příjemce",
    "merge.noSubject": "(bez předmětu)",
    "merge.progress": "{done}/{total} odesláno",
    "merge.progressFailed": " · {n} selhalo",
    "merge.cancel": "Zrušit",
    "merge.sending": "Odesílám…",
    "merge.sendOne": "Odeslat 1 zprávu",
    "merge.sendN": "Odeslat zprávy ({n})",

    // Trezor (hlavní heslo).
    "vault.noMatch": "Hesla se neshodují",
    "vault.tooShort": "Použijte alespoň 6 znaků",
    "vault.unlocked": "Trezor odemknut",
    "vault.failed": "Selhalo",
    "vault.setupSub": "Nastavte si hlavní heslo, kterým se na tomto zařízení zašifrují vaše účty.",
    "vault.unlockSub": "Zadejte hlavní heslo pro odemknutí pošty.",
    "vault.masterPassword": "Hlavní heslo",
    "vault.confirmPassword": "Potvrzení hesla",
    "vault.create": "Vytvořit trezor",
    "vault.unlock": "Odemknout",
    "vault.noRecovery": "Obnova neexistuje - pokud heslo zapomenete, uložené přihlašovací údaje budou nenávratně pryč.",

    // Vyhledávací pole.
    "searchbar.remove": "Odebrat",
    "searchbar.placeholder": "Hledat…  from:  to:  has:attachment  is:unread  /regex/",
    "searchbar.clear": "Vymazat hledání",

    // Pole příjemců (štítky adres).
    "recip.remove": "Odebrat",
    "recip.checkOne": "⚠ Zkontrolujte tuto adresu: {list}",
    "recip.checkN": "⚠ Zkontrolujte tyto adresy: {list}",

    // Ukazatel odesílání.
    "sending.sending": "Odesílání…",
    "sending.cancel": "Zrušit",

    // Řádek skupiny (konverzace / balíček / kategorie).
    "grouprow.selectAll": "Vybrat vše",
    "grouprow.noSubject": "(bez předmětu)",
    "grouprow.conversation": "konverzace",
    "grouprow.bundle": "skupina",
    "grouprow.archiveConversation": "Archivovat celou konverzaci",
    "grouprow.doneAll": "Hotovo vše",
  },
};
