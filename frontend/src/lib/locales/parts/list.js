// Mail-list namespace ("list.*"): the message list, rows, smart-group cards,
// context menu, bulk bar, date-section headers and their toasts.
// Flat "list.key" → text; {placeholders} are filled by t(key, { ... }).
// Every en key MUST also exist in cs (missing keys fall back to English).
export default {
  en: {
    // Reused short action words.
    "list.done": "Done",
    "list.read": "Read",
    "list.flag": "Flag",
    "list.unflag": "Unflag",
    "list.snooze": "Snooze",
    "list.archive": "Archive",
    "list.delete": "Delete",
    "list.open": "Open",
    "list.save": "Save",
    "list.restore": "Restore",
    "list.more": "More",

    // Row / context-menu action labels & tooltips.
    "list.markDone": "Mark done",
    "list.markNotDone": "Mark not done",
    "list.markRead": "Mark read",
    "list.markUnread": "Mark unread",
    "list.markDoneKey": "Mark done (e)",
    "list.restoreKey": "Restore (e)",
    "list.select": "Select",
    "list.senderSafe": "You marked this sender safe",
    "list.authFail": "Failed sender authentication — possible spoof",
    "list.authPass": "Sender authenticated (SPF/DKIM/DMARC)",
    "list.vipSender": "VIP sender",
    "list.noSubject": "(no subject)",
    "list.unsnoozeNow": "Unsnooze now",
    "list.pinToTop": "Pin to top",
    "list.unpin": "Unpin",
    "list.removeVip": "Remove VIP",
    "list.markSenderVip": "Mark sender VIP",
    "list.unmarkSafe": "Unmark safe",
    "list.markSenderSafe": "Mark sender safe",
    "list.moveToCategory": "Move to category",
    "list.moveToPrimary": "Move to Primary (normal inbox)",
    "list.moveTo": "Move to {cat}",
    "list.resetCategory": "Reset category (auto)",
    "list.snoozePrefix": "Snooze: {label}",
    "list.showMailFromSender": "Show mail from sender",
    "list.muteSender": "Mute sender",
    "list.muteConversation": "Mute conversation",
    "list.blockSender": "Block sender",
    "list.createRule": "Create rule…",

    // Show-done toggle & save search.
    "list.showDone": "Show done",
    "list.showingAll": "Showing all",
    "list.showDoneTip": "Show messages you've marked done alongside the rest",
    "list.saveSmartFolder": "Save as smart folder",
    "list.namePrompt": "Name this saved search:",

    // Context-menu search box.
    "list.searchActions": "Search actions…",
    "list.noMatchingAction": "No matching action",

    // Category labels (filter chips + smart-group cards).
    "list.catAll": "All",
    "list.catPrimary": "Primary",
    "list.catNewsletters": "Newsletters",
    "list.catSocial": "Social",
    "list.catUpdates": "Updates",
    "list.catPromotions": "Promotions",
    "list.catNotifications": "Notifications",
    "list.catInvitations": "Invitations",
    "list.catInvitationResponses": "Invitation responses",

    // List title (per view).
    "list.titleSearch": "Search: \"{q}\"",
    "list.smartInbox": "Smart Inbox",
    "list.allInboxes": "All Inboxes",
    "list.allSent": "All Sent",
    "list.snoozed": "Snoozed",
    "list.screener": "Screener",
    "list.paperTrail": "Paper Trail",
    "list.followUps": "Follow-ups",
    "list.inbox": "Inbox",

    // Empty states.
    "list.emptySearch": "No matches for that search.",
    "list.emptySnoozed": "Nothing snoozed.",
    "list.emptyScreener": "Screener's clear — no first-time senders waiting.",
    "list.emptyPapertrail": "No receipts or invoices here yet.",
    "list.emptyFollowups": "Nothing's waiting on a reply.",
    "list.emptyInbox": "Inbox zero. You're all caught up.",

    // Toasts.
    "list.markedDone": "{n} marked done",
    "list.couldntUndo": "Couldn't undo",
    "list.couldntUpdate": "Couldn't update",
    "list.couldntMarkGroupDone": "Couldn't mark group done",
    "list.bulkRead": "{n} marked read",
    "list.bulkFlagged": "{n} flagged",
    "list.bulkSnoozed": "{n} snoozed",
    "list.bulkArchived": "{n} archived",
    "list.bulkDeleted": "{n} deleted",
    "list.bulkUpdated": "{n} updated",
    "list.bulkFailed": "Bulk action failed: {error}",

    // Loading / paging.
    "list.loading": "Loading…",
    "list.showMore": "Show more ({n})",
    "list.seeAllInGroup": "See all in this group ({n}) →",
    "list.loadingMore": "Loading {n} more…",

    // Bulk bar & footer hint.
    "list.nSelected": "{n} selected",
    "list.hintMove": "move",
    "list.hintToggleDone": "toggle done",
    "list.hintOpen": "open",

    // Date-section headers.
    "list.today": "Today",
    "list.yesterday": "Yesterday",
    "list.thisWeek": "This week",
    "list.lastWeek": "Last week",
    "list.thisMonth": "This month",
    "list.lastMonth": "Last month",
    "list.older": "Older",

    // Smart-group card.
    "list.newCount": "{n} new",
    "list.showNewTip": "Show just the new mail in this group",
    "list.doneAll": "Done all",
    "list.doneAllTip": "Mark this whole group done",
  },
  cs: {
    // Opakující se krátká slova akcí.
    "list.done": "Hotovo",
    "list.read": "Přečteno",
    "list.flag": "Vlajka",
    "list.unflag": "Zrušit vlajku",
    "list.snooze": "Odložit",
    "list.archive": "Archivovat",
    "list.delete": "Smazat",
    "list.open": "Otevřít",
    "list.save": "Uložit",
    "list.restore": "Obnovit",
    "list.more": "Více",

    // Popisky a nápovědy akcí řádku / kontextové nabídky.
    "list.markDone": "Označit jako hotové",
    "list.markNotDone": "Označit jako nehotové",
    "list.markRead": "Označit jako přečtené",
    "list.markUnread": "Označit jako nepřečtené",
    "list.markDoneKey": "Označit jako hotové (e)",
    "list.restoreKey": "Obnovit (e)",
    "list.select": "Vybrat",
    "list.senderSafe": "Tohoto odesílatele jste označili jako bezpečného",
    "list.authFail": "Ověření odesílatele selhalo — možné podvržení",
    "list.authPass": "Odesílatel ověřen (SPF/DKIM/DMARC)",
    "list.vipSender": "Odesílatel VIP",
    "list.noSubject": "(bez předmětu)",
    "list.unsnoozeNow": "Zrušit odložení",
    "list.pinToTop": "Připnout nahoru",
    "list.unpin": "Odepnout",
    "list.removeVip": "Odebrat VIP",
    "list.markSenderVip": "Označit odesílatele jako VIP",
    "list.unmarkSafe": "Zrušit označení bezpečný",
    "list.markSenderSafe": "Označit odesílatele jako bezpečného",
    "list.moveToCategory": "Přesunout do kategorie",
    "list.moveToPrimary": "Přesunout do Hlavní (běžná schránka)",
    "list.moveTo": "Přesunout do {cat}",
    "list.resetCategory": "Obnovit kategorii (automaticky)",
    "list.snoozePrefix": "Odložit: {label}",
    "list.showMailFromSender": "Zobrazit poštu od odesílatele",
    "list.muteSender": "Ztlumit odesílatele",
    "list.muteConversation": "Ztlumit konverzaci",
    "list.blockSender": "Blokovat odesílatele",
    "list.createRule": "Vytvořit pravidlo…",

    // Přepínač hotových a uložení hledání.
    "list.showDone": "Zobrazit hotové",
    "list.showingAll": "Zobrazuji vše",
    "list.showDoneTip": "Zobrazit i zprávy označené jako hotové společně s ostatními",
    "list.saveSmartFolder": "Uložit jako chytrou složku",
    "list.namePrompt": "Pojmenujte toto uložené hledání:",

    // Vyhledávací pole kontextové nabídky.
    "list.searchActions": "Hledat akce…",
    "list.noMatchingAction": "Žádná odpovídající akce",

    // Popisky kategorií (filtrovací štítky + karty chytrých skupin).
    "list.catAll": "Vše",
    "list.catPrimary": "Hlavní",
    "list.catNewsletters": "Newslettery",
    "list.catSocial": "Sociální sítě",
    "list.catUpdates": "Aktualizace",
    "list.catPromotions": "Akce",
    "list.catNotifications": "Upozornění",
    "list.catInvitations": "Pozvánky",
    "list.catInvitationResponses": "Odpovědi na pozvánky",

    // Nadpis seznamu (podle zobrazení).
    "list.titleSearch": "Hledání: „{q}“",
    "list.smartInbox": "Chytrá schránka",
    "list.allInboxes": "Všechny schránky",
    "list.allSent": "Všechny odeslané",
    "list.snoozed": "Odložené",
    "list.screener": "Filtr odesílatelů",
    "list.paperTrail": "Doklady",
    "list.followUps": "K vyřízení",
    "list.inbox": "Doručená pošta",

    // Prázdné stavy.
    "list.emptySearch": "Tomuto hledání nic neodpovídá.",
    "list.emptySnoozed": "Nic není odloženo.",
    "list.emptyScreener": "Filtr je prázdný — žádní noví odesílatelé nečekají.",
    "list.emptyPapertrail": "Zatím žádné účtenky ani faktury.",
    "list.emptyFollowups": "Nic nečeká na odpověď.",
    "list.emptyInbox": "Prázdná schránka. Máte vše vyřízeno.",

    // Hlášení.
    "list.markedDone": "{n} označeno jako hotové",
    "list.couldntUndo": "Nelze vrátit zpět",
    "list.couldntUpdate": "Nepodařilo se aktualizovat",
    "list.couldntMarkGroupDone": "Nepodařilo se označit skupinu jako hotovou",
    "list.bulkRead": "{n} označeno jako přečtené",
    "list.bulkFlagged": "{n} označeno vlajkou",
    "list.bulkSnoozed": "{n} odloženo",
    "list.bulkArchived": "{n} archivováno",
    "list.bulkDeleted": "{n} smazáno",
    "list.bulkUpdated": "{n} aktualizováno",
    "list.bulkFailed": "Hromadná akce selhala: {error}",

    // Načítání / stránkování.
    "list.loading": "Načítání…",
    "list.showMore": "Zobrazit další ({n})",
    "list.seeAllInGroup": "Zobrazit vše v této skupině ({n}) →",
    "list.loadingMore": "Načítání dalších {n}…",

    // Lišta hromadných akcí a nápověda v patičce.
    "list.nSelected": "{n} vybráno",
    "list.hintMove": "pohyb",
    "list.hintToggleDone": "přepnout hotové",
    "list.hintOpen": "otevřít",

    // Nadpisy sekcí podle data.
    "list.today": "Dnes",
    "list.yesterday": "Včera",
    "list.thisWeek": "Tento týden",
    "list.lastWeek": "Minulý týden",
    "list.thisMonth": "Tento měsíc",
    "list.lastMonth": "Minulý měsíc",
    "list.older": "Starší",

    // Karta chytré skupiny.
    "list.newCount": "{n} nových",
    "list.showNewTip": "Zobrazit jen novou poštu v této skupině",
    "list.doneAll": "Hotovo vše",
    "list.doneAllTip": "Označit celou skupinu jako hotovou",
  },
};
