// Compose window catalog (namespace: compose.*). Mirrors Compose.svelte's
// user-facing strings. {placeholders} are filled by t(key, { ... }). English is
// the source of truth; every en key must also exist in cs. Missing keys fall
// back to English, then to the key itself.
export default {
  en: {
    // Rich-text link prompt.
    "compose.linkUrlPrompt": "Link URL:",

    // Validation / status toasts.
    "compose.pickAccount": "Pick an account",
    "compose.addRecipient": "Add a recipient",
    "compose.savedToDrafts": "Saved to Drafts ({folder})",
    "compose.scheduled": "Scheduled — {label}",
    "compose.couldntSchedule": "Couldn't schedule: {error}",
    "compose.pickDateTime": "Pick a date & time",
    "compose.pickFutureTime": "Pick a future time",
    "compose.couldntOpenWindow": "Couldn't open a window",

    // Confirm dialogs (send / schedule guards + attachment reminder).
    "compose.sendNoSubjectTitle": "Send without a subject?",
    "compose.sendAnyway": "Send anyway",
    "compose.scheduleNoSubjectTitle": "Schedule without a subject?",
    "compose.scheduleAnyway": "Schedule anyway",
    "compose.noAttachmentTitle": "No attachment",
    "compose.noAttachmentMsg": "You mention an attachment but nothing is attached.",

    // Unsaved-changes veil.
    "compose.unsavedMessage": "Unsaved message",
    "compose.keepDraft": "Keep this draft?",
    "compose.unsavedChanges": "You have unsaved changes.",
    "compose.saveToDrafts": "Save to Drafts",
    "compose.keepEditing": "Keep editing",
    "compose.discard": "Discard",

    // Header.
    "compose.newMessage": "New message",
    "compose.restoreSavedDraft": "Restore a saved draft",
    "compose.drafts": "Drafts",
    "compose.restoreThisDraft": "Restore this draft",
    "compose.deleteDraft": "Delete draft",
    "compose.openSeparateWindow": "Open in a separate window",

    // Recipient / subject fields.
    "compose.from": "From",
    "compose.sendAsIdentity": "Send as",
    "compose.to": "To",
    "compose.toPlaceholder": "Start typing a name or email…",
    "compose.cc": "Cc",
    "compose.subject": "Subject",

    // Formatting toolbar tooltips (button faces stay symbolic: B / I / U).
    "compose.tool.bold": "Bold",
    "compose.tool.italic": "Italic",
    "compose.tool.underline": "Underline",
    "compose.tool.insertUnorderedList": "Bulleted list",
    "compose.tool.insertOrderedList": "Numbered list",
    "compose.insertLink": "Insert link",
    "compose.clearFormatting": "Clear formatting",
    "compose.insertTemplate": "Insert a template",
    "compose.templates": "Templates",
    "compose.attachFile": "Attach file",
    "compose.attach": "Attach",

    // Editor body.
    "compose.messageBody": "Message body",
    "compose.bodyPlaceholder": "Write your message…  (Ctrl+Enter to send)",
    "compose.markdown": "MD",
    "compose.markdownMode": "Markdown mode — write Markdown, sent as formatted HTML",
    "compose.markdownPlaceholder": "Write in Markdown…  **bold**, *italic*, `code`, [link](url), - lists, ``` fenced code ```",

    // Footer actions.
    "compose.send": "Send",
    "compose.saveDraftTitle": "Save to your Drafts folder (syncs across devices)",
    "compose.saving": "Saving…",
    "compose.saveDraft": "Save draft",
    "compose.sendLater": "Send later",
    "compose.later": "Later",
    "compose.schedule": "Schedule",
    "compose.signTitle": "Sign with your PGP key",
    "compose.sign": "Sign",
    "compose.encryptTitle": "Encrypt to recipients' PGP keys",
    "compose.encrypt": "Encrypt",
    "compose.smimeSignTitle": "Sign with your S/MIME certificate",
    "compose.smimeSign": "S/MIME sign",
    "compose.smimeEncryptTitle": "Encrypt to recipients' S/MIME certificates",
    "compose.smimeEncrypt": "S/MIME encrypt",
    "compose.receiptTitle": "Embed a read-receipt tracking pixel (recipient must be able to reach this app)",
    "compose.receipt": "Receipt",
    "compose.signature": "Signature",
    "compose.noSignature": "No signature",
    "compose.ctrlEnterHint": "Ctrl+Enter to send",
  },
  cs: {
    // Dotaz na adresu odkazu.
    "compose.linkUrlPrompt": "Adresa odkazu:",

    // Ověření / stavová hlášení.
    "compose.pickAccount": "Vyberte účet",
    "compose.addRecipient": "Přidejte příjemce",
    "compose.savedToDrafts": "Uloženo do konceptů ({folder})",
    "compose.scheduled": "Naplánováno — {label}",
    "compose.couldntSchedule": "Nepodařilo se naplánovat: {error}",
    "compose.pickDateTime": "Vyberte datum a čas",
    "compose.pickFutureTime": "Vyberte čas v budoucnosti",
    "compose.couldntOpenWindow": "Nepodařilo se otevřít okno",

    // Potvrzovací dialogy (kontrola před odesláním / naplánováním + připomínka přílohy).
    "compose.sendNoSubjectTitle": "Odeslat bez předmětu?",
    "compose.sendAnyway": "Přesto odeslat",
    "compose.scheduleNoSubjectTitle": "Naplánovat bez předmětu?",
    "compose.scheduleAnyway": "Přesto naplánovat",
    "compose.noAttachmentTitle": "Žádná příloha",
    "compose.noAttachmentMsg": "Zmiňujete přílohu, ale nic není přiloženo.",

    // Panel neuložených změn.
    "compose.unsavedMessage": "Neuložená zpráva",
    "compose.keepDraft": "Ponechat tento koncept?",
    "compose.unsavedChanges": "Máte neuložené změny.",
    "compose.saveToDrafts": "Uložit do konceptů",
    "compose.keepEditing": "Pokračovat v úpravách",
    "compose.discard": "Zahodit",

    // Záhlaví.
    "compose.newMessage": "Nová zpráva",
    "compose.restoreSavedDraft": "Obnovit uložený koncept",
    "compose.drafts": "Koncepty",
    "compose.restoreThisDraft": "Obnovit tento koncept",
    "compose.deleteDraft": "Smazat koncept",
    "compose.openSeparateWindow": "Otevřít v samostatném okně",

    // Pole příjemců / předmětu.
    "compose.from": "Od",
    "compose.sendAsIdentity": "Odeslat jako",
    "compose.to": "Komu",
    "compose.toPlaceholder": "Začněte psát jméno nebo e-mail…",
    "compose.cc": "Kopie",
    "compose.subject": "Předmět",

    // Tooltipy panelu formátování (tlačítka zůstávají symbolická: B / I / U).
    "compose.tool.bold": "Tučné",
    "compose.tool.italic": "Kurzíva",
    "compose.tool.underline": "Podtržené",
    "compose.tool.insertUnorderedList": "Odrážkový seznam",
    "compose.tool.insertOrderedList": "Číslovaný seznam",
    "compose.insertLink": "Vložit odkaz",
    "compose.clearFormatting": "Vymazat formátování",
    "compose.insertTemplate": "Vložit šablonu",
    "compose.templates": "Šablony",
    "compose.attachFile": "Přiložit soubor",
    "compose.attach": "Přiložit",

    // Tělo zprávy.
    "compose.messageBody": "Tělo zprávy",
    "compose.bodyPlaceholder": "Napište zprávu…  (Ctrl+Enter odešle)",
    "compose.markdown": "MD",
    "compose.markdownMode": "Režim Markdown — pište v Markdownu, odešle se jako formátované HTML",
    "compose.markdownPlaceholder": "Pište v Markdownu…  **tučně**, *kurzíva*, `kód`, [odkaz](url), - odrážky, ``` blok kódu ```",

    // Akce v zápatí.
    "compose.send": "Odeslat",
    "compose.saveDraftTitle": "Uložit do složky Koncepty (synchronizuje se mezi zařízeními)",
    "compose.saving": "Ukládám…",
    "compose.saveDraft": "Uložit koncept",
    "compose.sendLater": "Odeslat později",
    "compose.later": "Později",
    "compose.schedule": "Naplánovat",
    "compose.signTitle": "Podepsat vaším PGP klíčem",
    "compose.sign": "Podepsat",
    "compose.encryptTitle": "Zašifrovat PGP klíči příjemců",
    "compose.encrypt": "Zašifrovat",
    "compose.smimeSignTitle": "Podepsat vaším certifikátem S/MIME",
    "compose.smimeSign": "Podepsat S/MIME",
    "compose.smimeEncryptTitle": "Zašifrovat certifikáty S/MIME příjemců",
    "compose.smimeEncrypt": "Zašifrovat S/MIME",
    "compose.receiptTitle": "Vložit sledovací pixel pro potvrzení o přečtení (příjemce musí mít přístup k této aplikaci)",
    "compose.receipt": "Potvrzení",
    "compose.signature": "Podpis",
    "compose.noSignature": "Bez podpisu",
    "compose.ctrlEnterHint": "Ctrl+Enter odešle",
  },
};
