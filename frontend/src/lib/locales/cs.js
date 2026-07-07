// Czech UI catalog. Mirrors en.js keys. Missing keys fall back to English.
// Per-component fragments live in ./parts/*.js (each exports { en, cs }).
import nav from "./parts/nav.js";
import list from "./parts/list.js";
import reader from "./parts/reader.js";
import compose from "./parts/compose.js";
import cmd from "./parts/cmd.js";
import settingsNav from "./parts/settingsNav.js";
import goto from "./parts/goto.js";
import search from "./parts/search.js";
import devicesync from "./parts/devicesync.js";
import security from "./parts/security.js";

const base = {
  // Běžné akce / opakující se slova.
  "common.save": "Uložit",
  "common.cancel": "Zrušit",
  "common.close": "Zavřít",
  "common.done": "Hotovo",
  "common.next": "Další",
  "common.back": "Zpět",
  "common.skip": "Přeskočit",
  "common.finish": "Dokončit",
  "common.getStarted": "Začít",
  "common.retry": "Zkusit znovu",
  "common.play": "Přehrát",
  "common.preview": "Náhled",
  "common.enabled": "Zapnuto",
  "common.disabled": "Vypnuto",

  // Úvodní / spouštěcí obrazovka.
  "boot.starting": "Spouštím RaplMail…",
  "boot.cantReach": "Nepodařilo se spojit s jádrem RaplMailu.",
  "boot.warmingUp": "Zahřívám motory…",

  // Průvodce prvním spuštěním.
  "onboarding.stepOf": "Krok {n} z {total}",
  "onboarding.welcomeTitle": "Vítejte v RaplMailu",
  "onboarding.welcomeBody": "Rychlý e-mailový klient, který běží přímo u vás v počítači. Pojďme ho nastavit — zabere to jen pár vteřin.",
  "onboarding.languageTitle": "Vyberte si jazyk",
  "onboarding.languageBody": "Kdykoli to můžete změnit v Nastavení.",
  "onboarding.themeTitle": "Vyberte si vzhled",
  "onboarding.themeBody": "Zvolte motiv, se kterým začnete. Každou barvu si můžete doladit později v Nastavení vzhledu.",
  "onboarding.optionsTitle": "Několik předvoleb",
  "onboarding.optionsBody": "Zapněte, co chcete používat. Všechno lze později změnit v Nastavení.",
  "onboarding.doneTitle": "Máte hotovo",
  "onboarding.doneBody": "Přidejte účet a začněte číst poštu. Klávesou ? kdykoli zobrazíte klávesové zkratky.",
  "onboarding.smartInbox": "Chytrá schránka",
  "onboarding.smartInboxHint": "Seskupí newslettery, sociální sítě a upozornění do přehledných karet místo jednoho dlouhého seznamu.",
  "onboarding.notifications": "Oznámení na ploše",
  "onboarding.notificationsHint": "Jemné cinknutí a upozornění, když dorazí opravdu nová pošta.",
  "onboarding.startWithWindows": "Spouštět s Windows",
  "onboarding.startWithWindowsHint": "Spustí RaplMail automaticky po přihlášení (do lišty).",
  "onboarding.addAccount": "Přidat účet",
  "onboarding.highlightsTitle": "Co RaplMail umí",
  "onboarding.highlightsBody": "Rychlý pohled na funkce, které budete používat nejvíc. U každé z nich najdete nastavení, které si můžete doladit později.",
  "onboarding.hlTriageTitle": "Vyčistěte schránku",
  "onboarding.hlTriageBody": "Klávesou e označíte poštu jako hotovou — vyklouzne ze schránky. Přepínačem Hotové ji zase zobrazíte.",
  "onboarding.hlSmartTitle": "Chytrá schránka",
  "onboarding.hlSmartBody": "Newslettery, sociální sítě a upozornění se složí do přehledných karet, aby vynikla důležitá pošta.",
  "onboarding.hlPrivacyTitle": "Soukromí ve výchozím stavu",
  "onboarding.hlPrivacyBody": "Sledovací pixely a vzdálené obrázky zůstanou blokované, dokud je sami nenačtete, a odkazy se zbaví sledovačů.",
  "onboarding.hlRulesTitle": "Pravidla a blokování",
  "onboarding.hlRulesBody": "Směrujte poštu podle odesílatele nebo domény a doménu můžete natrvalo zablokovat — přímo ze zprávy.",
  "onboarding.hlSignatureTitle": "Podpis přetažením",
  "onboarding.hlSignatureBody": "Přetáhněte obrázek přímo do podpisu — vloží se tak, že ho příjemci opravdu uvidí.",
  "onboarding.hlSnoozeTitle": "Odložení a plánování",
  "onboarding.hlSnoozeBody": "Odložte poštu na později a naplánujte odeslání zpráv na ten správný čas.",
  "onboarding.hlAiTitle": "Lokální AI asistent",
  "onboarding.hlAiBody": "Shrnování, návrhy odpovědí, třídění a hledání — vše běží u vás v počítači, cloud není potřeba.",
  "onboarding.hlKeysTitle": "Na prvním místě klávesnice",
  "onboarding.hlKeysBody": "Proletíte poštou pomocí zkratek. Klávesou ? je kdykoli zobrazíte všechny.",
  "onboarding.settingsTitle": "Přizpůsobte si to",
  "onboarding.settingsBody": "Vše níže si můžete nastavit podle sebe. Klepnutím na oblast tam rovnou přejdete — nebo dejte Dokončit a prozkoumejte to později.",
  "onboarding.setAccounts": "Připojte Microsoft 365, Gmail nebo libovolnou schránku IMAP/SMTP.",
  "onboarding.setAppearance": "Motivy, barvy, rozvržení, písma a jak se e-maily přizpůsobí tmavému režimu.",
  "onboarding.setRules": "Automaticky filtrujte, směrujte a blokujte poštu podle odesílatele nebo domény.",
  "onboarding.setSignature": "Vytvořte bohatý podpis s vloženým obrázkem, pro každý účet zvlášť.",
  "onboarding.setAi": "Zvolte lokální model Ollama nebo API klíč a nastavte, co asistent dělá.",
  "onboarding.setSync": "Synchronizujte stav Hotové/přečteno mezi zařízeními přes vlastní schránku.",
  "onboarding.setShortcuts": "Zobrazte a změňte všechny klávesové zkratky.",
  "onboarding.setGeneral": "Odesílání, oznámení, časy odložení, spouštění, zálohy a další.",

  // Nastavení oznámení.
  "notif.title": "Oznámení",
  "notif.newMail": "Upozorňovat na novou poštu",
  "notif.onlyUnfocused": "Jen když RaplMail není aktivní",
  "notif.sound": "Zvuk",
  "notif.volume": "Hlasitost",
  "notif.test": "Odeslat zkušební oznámení",
  "notif.muteHint": "Chcete-li ztlumit konkrétního odesílatele nebo celou kategorii, přidejte pravidlo „Ztlumit oznámení“.",

  // Nastavení jazyka.
  "settings.language": "Jazyk",
  "settings.languageHint": "Jazyk rozhraní RaplMailu.",

  // Pravidla — popisky polí / operátorů / akcí.
  "rules.field.from_domain": "Doména odesílatele",
  "rules.field.from": "Adresa odesílatele",
  "rules.field.to": "Příjemce",
  "rules.field.subject": "Předmět",
  "rules.field.body": "Text",
  "rules.field.category": "Kategorie",
  "rules.op.contains": "obsahuje",
  "rules.op.equals": "rovná se",
  "rules.op.ends_with": "končí na",
  "rules.op.regex": "odpovídá regexu",
  "rules.action.move": "Přesunout do složky",
  "rules.action.archive": "Archivovat",
  "rules.action.delete": "Smazat",
  "rules.action.mark_read": "Označit jako přečtené",
  "rules.action.mark_done": "Označit jako hotové",
  "rules.action.block": "Blokovat (do karantény)",
  "rules.action.mute_notifications": "Ztlumit oznámení",
  "rules.action.webhook": "Odeslat na webhook",
  "rules.action.run_script": "Spustit lokální skript",
  "rules.categoryHint": "např. newsletters, social, updates, promotions",
  "rules.webhookHint": "https://… URL webhooku (POST)",
  "rules.scriptHint": "příkaz ke spuštění, např. python handler.py",
  "rules.muteFromSender": "Ztlumit oznámení od odesílatele",

  // Běžná hlášení.
  "toast.muteNotifOn": "Oznámení od {who} ztlumena",

  // S/MIME (Nastavení → S/MIME).
  "smime.identityTitle": "Váš certifikát S/MIME",
  "smime.identityHint": "Naimportujte soubor .p12 / .pfx (váš certifikát X.509 + soukromý klíč), aby RaplMail mohl podepisovat a dešifrovat poštu S/MIME. Uloženo lokálně, stejně jako klíče PGP.",
  "smime.certificate": "Certifikát naimportován",
  "smime.p12password": "Heslo souboru",
  "smime.importP12": "Importovat .p12 / .pfx…",
  "smime.importing": "Importuji…",
  "smime.imported": "Certifikát S/MIME naimportován pro {who}",
  "smime.remove": "Odebrat",
  "smime.recipientsTitle": "Certifikáty příjemců",
  "smime.recipientsHint": "Vložte certifikát X.509 (PEM) protistrany, abyste jí mohli posílat šifrovanou poštu S/MIME.",
  "smime.addCert": "Přidat certifikát",
  "smime.certAdded": "Certifikát přidán",
  "smime.badCert": "Tohle nevypadá jako certifikát PEM (očekává se -----BEGIN CERTIFICATE-----).",

  // Nástroje → Audit odběrů.
  "utility.subscriptionsTitle": "Audit odběrů",
  "utility.subscriptionsHint": "Všechny newslettery, které dostáváte, a kolik jste jich za posledních 30 dní opravdu přečetli. Nečinné jsou nahoře — odhlaste je nebo automaticky archivujte jedním tahem.",
  "utility.none": "Zatím nebyly zjištěny žádné newslettery. Otevřete pár a objeví se tu.",
  "utility.selectAll": "Vybrat vše",
  "utility.archiveSelected": "Auto-archivovat {n}",
  "utility.unsubSelected": "Odhlásit {n}",
  "utility.total": "přijato",
  "utility.readRate": "přečteno (30 d)",
  "utility.lastSeen": "naposledy",
  "utility.unsubscribe": "Odhlásit",
  "utility.archiveFuture": "Auto-archivace",
  "utility.archivedRule": "Budoucí pošta od {who} se bude archivovat",
  "utility.archivedN": "Přidáno pravidlo auto-archivace pro {n} odesílatelů",
};

export default {
  ...base,
  ...nav.cs, ...list.cs, ...reader.cs, ...compose.cs, ...cmd.cs, ...settingsNav.cs,
  ...goto.cs, ...search.cs, ...devicesync.cs, ...security.cs,
};
