// Reader / ThreadView catalog fragment. Flat "reader.key" → text.
// {placeholders} are filled by t(key, { placeholder: value }).
// en + cs kept in lockstep — every en key must also exist in cs.
export default {
  en: {
    // Action buttons (reader + thread).
    "reader.reply": "Reply",
    "reader.replyAll": "Reply all",
    "reader.forward": "Forward",
    "reader.done": "Done",
    "reader.restore": "Restore",
    "reader.flag": "Flag",
    "reader.flagged": "Flagged",
    "reader.doneAll": "Done all",

    // AI actions.
    "reader.catchMeUp": "Catch me up",
    "reader.summarizing": "Summarizing…",
    "reader.aiReply": "AI reply",
    "reader.drafting": "Drafting…",
    "reader.catchMeUpTitle": "Summarize this thread with AI",
    "reader.aiReplyTitle": "Draft a reply with AI",

    // AI panels.
    "reader.summary": "Summary",
    "reader.suggestedReply": "Suggested reply",
    "reader.dismiss": "Dismiss",
    "reader.editAndSend": "Edit & send →",
    "reader.reviewBeforeSending": "Review before sending — nothing is sent automatically.",

    // Empty / loading states.
    "reader.selectMessage": "Select a message to read",
    "reader.loading": "Loading…",
    "reader.loadingConversation": "Loading conversation…",
    "reader.noSubject": "(no subject)",

    // Address quick-menu.
    "reader.copyAddress": "Copy address",
    "reader.showMailFromTo": "Show mail from/to this address",
    "reader.newEmailTo": "New email to this address",
    "reader.markVip": "Mark as VIP",
    "reader.removeVip": "Remove VIP",
    "reader.muteSender": "Mute this sender",
    "reader.muteConversation": "Mute this conversation",
    "reader.exportEml": "Export .eml (safe)",

    // Recipients line.
    "reader.toLabel": "to",
    "reader.showLess": "show less",
    "reader.moreN": "+{n} more",

    // Security / authentication bars.
    "reader.markedSafe": "Marked safe",
    "reader.youTrust": "You trust {addr}",
    "reader.undo": "Undo",
    "reader.removeSafeMarkTitle": "Remove the safe mark",
    "reader.markSafe": "Mark safe",
    "reader.trustSenderTitle": "Trust this sender — show a green check, no more warnings",
    "reader.pgpEncrypted": "PGP encrypted",
    "reader.pgpSigVerified": "· signature verified ({signer})",
    "reader.pgpDecryptedLocally": "· decrypted locally",
    "reader.pgpSignatureVerified": "PGP signature verified",
    "reader.pgpSignatureUnverified": "PGP signature — couldn't verify",
    "reader.importPublicKey": "import the sender's public key",
    "reader.smimeEncrypted": "S/MIME encrypted",
    "reader.smimeDecryptedLocally": "decrypted locally with your certificate",
    "reader.smimeNoKey": "import your S/MIME certificate to decrypt (Settings → S/MIME)",
    "reader.smimeSigned": "S/MIME signed",
    "reader.smimeUnknownSigner": "signer certificate present",
    "reader.failedAuth": "Failed authentication — this message may be spoofed.",
    "reader.senderAuthenticated": "Sender authenticated",

    // Screener bar.
    "reader.firstTimeSender": "First-time sender — do you want mail from {addr}?",
    "reader.approve": "Approve",
    "reader.block": "Block",

    // Unsubscribe bar.
    "reader.mailingList": "This looks like a mailing list.",
    "reader.unsubscribe": "Unsubscribe",

    // Tracker bar (reader — full).
    "reader.blockedTrackerOne": "Blocked 1 tracking pixel · regular images are shown.",
    "reader.blockedTrackerN": "Blocked {n} tracking pixels · regular images are shown.",
    "reader.hide": "Hide",
    "reader.details": "Details",
    "reader.loadEverything": "Load everything",

    // Tracker note (thread — short).
    "reader.blockedPixelOne": "Blocked 1 tracking pixel",
    "reader.blockedPixelN": "Blocked {n} tracking pixels",

    // Attachments.
    "reader.attachmentOne": "1 attachment",
    "reader.attachmentN": "{n} attachments",
    "reader.openFile": "Open {name}",
    "reader.saveToDownloads": "Save to Downloads",
    "reader.saveAllTitle": "Save all attachments to Downloads",
    "reader.saving": "Saving…",
    "reader.downloadAll": "Download all",

    // Attachment toasts.
    "reader.savedTo": "Saved to {path}",
    "reader.downloaded": "Downloaded",
    "reader.savedToDownloadsOne": "Saved 1 attachment to Downloads",
    "reader.savedToDownloadsN": "Saved {n} attachments to Downloads",
    "reader.downloadedOne": "Downloaded 1 attachment",
    "reader.downloadedN": "Downloaded {n} attachments",
    "reader.couldntOpenAttachment": "Couldn't open attachment",
    "reader.couldntSaveAttachment": "Couldn't save attachment",
    "reader.couldntSaveAttachments": "Couldn't save attachments",
    "reader.couldntAttachForwarded": "Couldn't attach the forwarded files — they may need re-attaching",

    // Address toasts.
    "reader.addressCopied": "Address copied",
    "reader.couldntCopy": "Couldn't copy",

    // View bar (quoted / original styling toggles).
    "reader.showHideEarlierTitle": "Show / hide the earlier quoted messages",
    "reader.hideEarlier": "Hide earlier",
    "reader.showEarlier": "Show earlier messages",
    "reader.stylingToggleTitle": "Toggle between the sender's original styling and your theme",
    "reader.originalStyling": "Original styling",
    "reader.dark": "Dark",
    "reader.adaptedToTheme": "Adapted to theme",

    // Iframe accessibility title.
    "reader.messageFrameTitle": "Message",

    // Thread view.
    "reader.messagesInConversationOne": "1 message in this conversation",
    "reader.messagesInConversation": "{n} messages in this conversation",
    "reader.conversationDone": "Conversation done",
    "reader.conversationArchived": "Conversation archived",
    "reader.archiveAll": "Archive all",
    "reader.couldntUpdate": "Couldn't update",
  },
  cs: {
    // Akční tlačítka (čtečka + vlákno).
    "reader.reply": "Odpovědět",
    "reader.replyAll": "Odpovědět všem",
    "reader.forward": "Přeposlat",
    "reader.done": "Hotovo",
    "reader.restore": "Obnovit",
    "reader.flag": "Vlajka",
    "reader.flagged": "Označeno vlajkou",
    "reader.doneAll": "Vše hotovo",

    // Akce AI.
    "reader.catchMeUp": "Shrň mi to",
    "reader.summarizing": "Shrnuji…",
    "reader.aiReply": "Odpověď od AI",
    "reader.drafting": "Připravuji…",
    "reader.catchMeUpTitle": "Shrnout toto vlákno pomocí AI",
    "reader.aiReplyTitle": "Navrhnout odpověď pomocí AI",

    // Panely AI.
    "reader.summary": "Shrnutí",
    "reader.suggestedReply": "Navržená odpověď",
    "reader.dismiss": "Zavřít",
    "reader.editAndSend": "Upravit a odeslat →",
    "reader.reviewBeforeSending": "Před odesláním zkontrolujte — nic se neodešle automaticky.",

    // Prázdné stavy / načítání.
    "reader.selectMessage": "Vyberte zprávu ke čtení",
    "reader.loading": "Načítání…",
    "reader.loadingConversation": "Načítání konverzace…",
    "reader.noSubject": "(bez předmětu)",

    // Rychlá nabídka adresy.
    "reader.copyAddress": "Kopírovat adresu",
    "reader.showMailFromTo": "Zobrazit poštu od/pro tuto adresu",
    "reader.newEmailTo": "Nový e-mail na tuto adresu",
    "reader.markVip": "Označit jako VIP",
    "reader.removeVip": "Zrušit VIP",
    "reader.muteSender": "Ztlumit tohoto odesílatele",
    "reader.muteConversation": "Ztlumit tuto konverzaci",
    "reader.exportEml": "Exportovat .eml (bezpečně)",

    // Řádek příjemců.
    "reader.toLabel": "komu",
    "reader.showLess": "zobrazit méně",
    "reader.moreN": "+{n} dalších",

    // Bezpečnostní / ověřovací pruhy.
    "reader.markedSafe": "Označeno jako bezpečné",
    "reader.youTrust": "Důvěřujete adrese {addr}",
    "reader.undo": "Zpět",
    "reader.removeSafeMarkTitle": "Odebrat označení bezpečné",
    "reader.markSafe": "Označit jako bezpečné",
    "reader.trustSenderTitle": "Důvěřovat tomuto odesílateli — zobrazí se zelená značka a žádná další varování",
    "reader.pgpEncrypted": "Šifrováno pomocí PGP",
    "reader.pgpSigVerified": "· podpis ověřen ({signer})",
    "reader.pgpDecryptedLocally": "· dešifrováno lokálně",
    "reader.pgpSignatureVerified": "Podpis PGP ověřen",
    "reader.pgpSignatureUnverified": "Podpis PGP — nelze ověřit",
    "reader.importPublicKey": "importujte veřejný klíč odesílatele",
    "reader.smimeEncrypted": "Šifrováno S/MIME",
    "reader.smimeDecryptedLocally": "dešifrováno lokálně vaším certifikátem",
    "reader.smimeNoKey": "pro dešifrování naimportujte svůj certifikát S/MIME (Nastavení → S/MIME)",
    "reader.smimeSigned": "Podepsáno S/MIME",
    "reader.smimeUnknownSigner": "certifikát podepisujícího je přítomen",
    "reader.failedAuth": "Ověření selhalo — tato zpráva může být podvržená.",
    "reader.senderAuthenticated": "Odesílatel ověřen",

    // Pruh prověřování prvních odesílatelů.
    "reader.firstTimeSender": "Odesílatel poprvé — chcete přijímat poštu od {addr}?",
    "reader.approve": "Schválit",
    "reader.block": "Blokovat",

    // Pruh odhlášení odběru.
    "reader.mailingList": "Vypadá to jako hromadná pošta.",
    "reader.unsubscribe": "Odhlásit odběr",

    // Pruh sledovacích prvků (čtečka — plný).
    "reader.blockedTrackerOne": "Zablokován 1 sledovací pixel · běžné obrázky se zobrazují.",
    "reader.blockedTrackerN": "Zablokováno {n} sledovacích pixelů · běžné obrázky se zobrazují.",
    "reader.hide": "Skrýt",
    "reader.details": "Podrobnosti",
    "reader.loadEverything": "Načíst vše",

    // Poznámka o sledovacích prvcích (vlákno — krátká).
    "reader.blockedPixelOne": "Zablokován 1 sledovací pixel",
    "reader.blockedPixelN": "Zablokováno {n} sledovacích pixelů",

    // Přílohy.
    "reader.attachmentOne": "1 příloha",
    "reader.attachmentN": "{n} příloh",
    "reader.openFile": "Otevřít {name}",
    "reader.saveToDownloads": "Uložit do Stažených",
    "reader.saveAllTitle": "Uložit všechny přílohy do Stažených",
    "reader.saving": "Ukládání…",
    "reader.downloadAll": "Stáhnout vše",

    // Hlášení o přílohách.
    "reader.savedTo": "Uloženo do {path}",
    "reader.downloaded": "Staženo",
    "reader.savedToDownloadsOne": "Uložena 1 příloha do Stažených",
    "reader.savedToDownloadsN": "Uloženo {n} příloh do Stažených",
    "reader.downloadedOne": "Stažena 1 příloha",
    "reader.downloadedN": "Staženo {n} příloh",
    "reader.couldntOpenAttachment": "Přílohu se nepodařilo otevřít",
    "reader.couldntSaveAttachment": "Přílohu se nepodařilo uložit",
    "reader.couldntSaveAttachments": "Přílohy se nepodařilo uložit",
    "reader.couldntAttachForwarded": "Přeposílané soubory se nepodařilo připojit — možná je bude třeba připojit znovu",

    // Hlášení o adrese.
    "reader.addressCopied": "Adresa zkopírována",
    "reader.couldntCopy": "Nepodařilo se zkopírovat",

    // Pruh zobrazení (přepínače citací / původního vzhledu).
    "reader.showHideEarlierTitle": "Zobrazit / skrýt starší citované zprávy",
    "reader.hideEarlier": "Skrýt starší",
    "reader.showEarlier": "Zobrazit starší zprávy",
    "reader.stylingToggleTitle": "Přepínat mezi původním vzhledem odesílatele a vaším motivem",
    "reader.originalStyling": "Původní vzhled",
    "reader.dark": "Tmavý",
    "reader.adaptedToTheme": "Přizpůsobeno motivu",

    // Titulek rámce zprávy (pro čtečky obrazovky).
    "reader.messageFrameTitle": "Zpráva",

    // Zobrazení vlákna.
    "reader.messagesInConversationOne": "1 zpráva v této konverzaci",
    "reader.messagesInConversation": "{n} zpráv v této konverzaci",
    "reader.conversationDone": "Konverzace hotova",
    "reader.conversationArchived": "Konverzace archivována",
    "reader.archiveAll": "Archivovat vše",
    "reader.couldntUpdate": "Nepodařilo se aktualizovat",
  },
};
