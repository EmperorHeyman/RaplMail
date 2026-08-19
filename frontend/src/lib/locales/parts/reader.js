// Reader / ThreadView catalog fragment. Flat "reader.key" → text.
// {placeholders} are filled by t(key, { placeholder: value }).
// en + cs kept in lockstep - every en key must also exist in cs.
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
    "reader.reviewBeforeSending": "Review before sending - nothing is sent automatically.",

    // Empty / loading states.
    "reader.selectMessage": "Select a message to read",
    "reader.loading": "Loading…",
    "reader.loadingConversation": "Loading conversation…",
    "reader.noSubject": "(no subject)",

    // Address quick-menu.
    "reader.copyAddress": "Copy address",
    "reader.copySubject": "Copy subject",
    "reader.subjectCopied": "Subject copied",
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
    "reader.trustSenderTitle": "Trust this sender - show a green check, no more warnings",
    "reader.pgpEncrypted": "PGP encrypted",
    "reader.pgpSigVerified": "· signature verified ({signer})",
    "reader.pgpDecryptedLocally": "· decrypted locally",
    "reader.pgpSignatureVerified": "PGP signature verified",
    "reader.pgpSignatureUnverified": "PGP signature - couldn't verify",
    "reader.importPublicKey": "import the sender's public key",
    "reader.smimeEncrypted": "S/MIME encrypted",
    "reader.smimeDecryptedLocally": "decrypted locally with your certificate",
    "reader.smimeNoKey": "import your S/MIME certificate to decrypt (Settings → S/MIME)",
    "reader.smimeSigned": "S/MIME signed",
    "reader.smimeUnknownSigner": "signer certificate present",
    "reader.failedAuth": "Failed authentication - this message may be spoofed.",
    "reader.failedAuthShort": "Failed auth",
    "reader.senderAuthenticated": "Sender authenticated",
    "reader.securityWarning": "Security warning",

    // AI phishing screening (Settings → Security).
    "reader.aiCheck": "Check with AI",
    "reader.aiChecking": "Checking…",
    "reader.aiSafe": "AI: looks safe",
    "reader.aiSuspicious": "AI: suspicious",
    "reader.aiDangerous": "AI: likely phishing",
    "reader.aiRecheck": "Check again",
    "reader.aiScreenDisclaimer": "AI can and will make mistakes - treat this as a hint, not proof.",

    // Screener badge + expanded detail.
    "reader.newSenderBadge": "New sender",
    "reader.firstTimeSender": "First-time sender - do you want mail from {addr}?",
    "reader.approve": "Approve",
    "reader.block": "Block",

    // Mailing-list badge + expanded detail.
    "reader.mailingListBadge": "Mailing list",
    "reader.mailingList": "This looks like a mailing list.",
    "reader.unsubscribe": "Unsubscribe",

    // Tracker bar (reader - full).
    "reader.blockedTrackerOne": "Blocked 1 tracking pixel · regular images are shown.",
    "reader.blockedTrackerN": "Blocked {n} tracking pixels · regular images are shown.",
    "reader.hide": "Hide",
    "reader.details": "Details",
    "reader.loadEverything": "Load everything",

    // Tracker note (thread - short).
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
    "reader.couldntAttachForwarded": "Couldn't attach the forwarded files - they may need re-attaching",

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

    // Meeting card (MeetingCard.svelte) - when the mail is about a calendar event.
    "reader.meetInvite": "Meeting",
    "reader.meetUpdate": "Meeting updated",
    "reader.meetCancel": "Meeting canceled",
    "reader.meetReply": "Meeting response",
    "reader.meetAllDay": "all day",
    "reader.meetFromCalendar": "from your calendar",
    "reader.meetFromCalendarWhy": "This mail doesn't say when the meeting is - the time was matched from a meeting of the same name in your calendar.",
    "reader.meetRecurring": "Repeating - next occurrence",
    "reader.meetRecurringWhy": "This meeting repeats. The mail doesn't say which occurrence it means, so the next one is shown.",
    "reader.meetNoTime": "This mail doesn't say when the meeting is",
    "reader.meetLinkOnly": "Outlook sent a web link instead of a real invitation. To get invitations with the date attached, open Outlook on the web → Settings → POP and IMAP → \"Send meeting invitations in iCalendar format\".",
    "reader.meetShowInCalendar": "Show in calendar",
    "reader.meetOpenInOutlook": "Open in Outlook",
  },
  cs: {
    // Akční tlačítka (čtečka + vlákno).
    "reader.reply": "Odpovědět",
    "reader.replyAll": "Odpovědět všem",
    "reader.forward": "Přeposlat",
    "reader.done": "Hotovo",
    "reader.restore": "Obnovit",
    "reader.flag": "Praporek",
    "reader.flagged": "S praporkem",
    "reader.doneAll": "Vyřídit vše",

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
    "reader.reviewBeforeSending": "Před odesláním zkontrolujte - nic se neodešle automaticky.",

    // Prázdné stavy / načítání.
    "reader.selectMessage": "Vyberte zprávu ke čtení",
    "reader.loading": "Načítání…",
    "reader.loadingConversation": "Načítání konverzace…",
    "reader.noSubject": "(bez předmětu)",

    // Rychlá nabídka adresy.
    "reader.copyAddress": "Kopírovat adresu",
    "reader.copySubject": "Kopírovat předmět",
    "reader.subjectCopied": "Předmět zkopírován",
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
    "reader.trustSenderTitle": "Důvěřovat tomuto odesílateli - zobrazí se zelená značka a žádná další varování",
    "reader.pgpEncrypted": "Šifrováno pomocí PGP",
    "reader.pgpSigVerified": "· podpis ověřen ({signer})",
    "reader.pgpDecryptedLocally": "· dešifrováno lokálně",
    "reader.pgpSignatureVerified": "Podpis PGP ověřen",
    "reader.pgpSignatureUnverified": "Podpis PGP - nelze ověřit",
    "reader.importPublicKey": "importujte veřejný klíč odesílatele",
    "reader.smimeEncrypted": "Šifrováno pomocí S/MIME",
    "reader.smimeDecryptedLocally": "dešifrováno lokálně vaším certifikátem",
    "reader.smimeNoKey": "pro dešifrování naimportujte svůj certifikát S/MIME (Nastavení → S/MIME)",
    "reader.smimeSigned": "Podepsáno S/MIME",
    "reader.smimeUnknownSigner": "certifikát podepisujícího je přiložen",
    "reader.failedAuth": "Ověření selhalo - tato zpráva může být podvržená.",
    "reader.failedAuthShort": "Ověření selhalo",
    "reader.senderAuthenticated": "Odesílatel ověřen",
    "reader.securityWarning": "Bezpečnostní varování",

    // Prověřování phishingu pomocí AI (Nastavení → Zabezpečení).
    "reader.aiCheck": "Zkontrolovat pomocí AI",
    "reader.aiChecking": "Kontroluji…",
    "reader.aiSafe": "AI: vypadá bezpečně",
    "reader.aiSuspicious": "AI: podezřelé",
    "reader.aiDangerous": "AI: pravděpodobně phishing",
    "reader.aiRecheck": "Zkontrolovat znovu",
    "reader.aiScreenDisclaimer": "AI dělá a bude dělat chyby - berte to jako nápovědu, ne jako důkaz.",

    // Odznak prověřování + rozbalený detail.
    "reader.newSenderBadge": "Nový odesílatel",
    "reader.firstTimeSender": "Odesílatel poprvé - chcete přijímat poštu od {addr}?",
    "reader.approve": "Schválit",
    "reader.block": "Blokovat",

    // Odznak hromadné pošty + rozbalený detail.
    "reader.mailingListBadge": "Hromadná pošta",
    "reader.mailingList": "Vypadá to jako hromadná pošta.",
    "reader.unsubscribe": "Odhlásit odběr",

    // Pruh sledovacích prvků (čtečka - plný).
    "reader.blockedTrackerOne": "Zablokován 1 sledovací pixel · běžné obrázky se zobrazují.",
    "reader.blockedTrackerN": "Zablokováno sledovacích pixelů: {n} · běžné obrázky se zobrazují.",
    "reader.hide": "Skrýt",
    "reader.details": "Podrobnosti",
    "reader.loadEverything": "Načíst vše",

    // Poznámka o sledovacích prvcích (vlákno - krátká).
    "reader.blockedPixelOne": "Zablokován 1 sledovací pixel",
    "reader.blockedPixelN": "Zablokováno sledovacích pixelů: {n}",

    // Přílohy.
    "reader.attachmentOne": "1 příloha",
    "reader.attachmentN": "Přílohy: {n}",
    "reader.openFile": "Otevřít {name}",
    "reader.saveToDownloads": "Uložit do Stažených",
    "reader.saveAllTitle": "Uložit všechny přílohy do Stažených",
    "reader.saving": "Ukládání…",
    "reader.downloadAll": "Stáhnout vše",

    // Hlášení o přílohách.
    "reader.savedTo": "Uloženo do {path}",
    "reader.downloaded": "Staženo",
    "reader.savedToDownloadsOne": "Uložena 1 příloha do Stažených",
    "reader.savedToDownloadsN": "Do Stažených uloženo příloh: {n}",
    "reader.downloadedOne": "Stažena 1 příloha",
    "reader.downloadedN": "Staženo příloh: {n}",
    "reader.couldntOpenAttachment": "Přílohu se nepodařilo otevřít",
    "reader.couldntSaveAttachment": "Přílohu se nepodařilo uložit",
    "reader.couldntSaveAttachments": "Přílohy se nepodařilo uložit",
    "reader.couldntAttachForwarded": "Přeposílané soubory se nepodařilo připojit - možná je bude třeba připojit znovu",

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
    "reader.messagesInConversation": "Zprávy v této konverzaci: {n}",
    "reader.conversationDone": "Konverzace hotova",
    "reader.conversationArchived": "Konverzace archivována",
    "reader.archiveAll": "Archivovat vše",
    "reader.couldntUpdate": "Nepodařilo se aktualizovat",

    // Karta schůzky (MeetingCard.svelte) - když se e-mail týká události v kalendáři.
    "reader.meetInvite": "Schůzka",
    "reader.meetUpdate": "Schůzka změněna",
    "reader.meetCancel": "Schůzka zrušena",
    "reader.meetReply": "Odpověď na schůzku",
    "reader.meetAllDay": "celý den",
    "reader.meetFromCalendar": "z vašeho kalendáře",
    "reader.meetFromCalendarWhy": "V tomto e-mailu není, kdy schůzka je - čas jsme dohledali podle stejně nazvané schůzky ve vašem kalendáři.",
    "reader.meetRecurring": "Opakuje se - nejbližší termín",
    "reader.meetRecurringWhy": "Tato schůzka se opakuje. E-mail neuvádí, o který termín jde, proto zobrazujeme nejbližší.",
    "reader.meetNoTime": "V tomto e-mailu není, kdy schůzka je",
    "reader.meetLinkOnly": "Outlook poslal místo skutečné pozvánky jen webový odkaz. Aby pozvánky obsahovaly datum, otevřete Outlook na webu → Nastavení → POP a IMAP → „Odesílat pozvánky na schůzky ve formátu iCalendar“.",
    "reader.meetShowInCalendar": "Zobrazit v kalendáři",
    "reader.meetOpenInOutlook": "Otevřít v Outlooku",
  },
};
