// RaplMail website: English / Czech, the download buttons and "What's new".
// Both come from updates/ - the same latest.json the app's updater reads, and a
// changelog.json written next to it by stage-release.py.
// data-t = text, data-th = text with markup (<b>, <kbd>, <code> - this file's own
// strings only), data-t-alt / data-t-label = an image's alt / an aria-label.
(() => {
  const T = {
    en: {
      "nav.features": "Features", "nav.privacy": "Privacy", "nav.ai": "AI", "nav.wiki": "Wiki", "nav.new": "What's new", "nav.download": "Download",
      "hero.eyebrow": "Mail for Windows",
      "hero.title": "Your inbox, done.",
      "hero.lead": "A fast, private mail app for people who live in their inbox. Clear mail from the keyboard (press <kbd>e</kbd> and it's done), find anything in a keystroke, and keep every message, password and key on your own computer.",
      "hero.download": "Download for Windows",
      "hero.tour": "See how it works",
      "hero.meta": "Version {v} · {size} · Windows 10 and 11, 64-bit",
      "hero.metaNone": "Windows 10 and 11, 64-bit",
      "hero.soon": "The first version is on its way - check back soon.",
      "hero.t1": "Free", "hero.t2": "No account", "hero.t3": "No telemetry", "hero.t4": "English and Czech",
      "hero.shotAlt": "RaplMail showing the Smart Inbox and an open message",
      "glance.label": "At a glance",
      "g1": "RaplMail servers between you and your mail",
      "g2": "of memory, even with big mailboxes",
      "g3": "is all it takes to mark mail done",
      "g4.n": "Free", "g4": "no subscription, no sign-up",

      "tri.eyebrow": "Triage",
      "tri.title": "Clear your inbox from the keyboard",
      "tri.lead": "Press <kbd>e</kbd> and a message is done: gone from your inbox, still safe on the server. Snooze what can wait, pin what can't, and let the noise fold into groups. Every action can be undone.",
      "tri.p1": "<b>Snooze, pin and VIP.</b> Snooze to an exact time or <i>until I'm back</i>, and mail returns when you sit back down at your desk. VIP senders always float to the top.",
      "tri.p2": "<b>The noise, grouped.</b> Newsletters, notifications and promotions wait in their own groups, and three or more notifications from one sender fold into a single bundle.",
      "tri.p3": "<b>Screener and rules.</b> First-time senders wait for your approval. Rules move, archive, mark done or block by sender, domain or subject, with a live preview.",
      "tri.p4": "<b>Undo anything.</b> Done, snooze, archive, delete, move and bulk actions all come with an undo, and archive and delete wait for it before they touch the server.",
      "k.done": "Done", "k.reply": "Reply", "k.archive": "Archive", "k.search": "Search", "k.palette": "Commands", "k.all": "All shortcuts",
      "mk.inbox": "Smart Inbox", "mk.notif": "Notifications", "mk.news": "Newsletters",
      "mk.n1": "Sophie Bennett", "mk.av1": "S", "mk.n2": "Daniel Kim", "mk.n3": "Marta Novak", "mk.from": "from:sophie",
      "mk.s1": "Design review moved to Thursday", "mk.s2": "Q4 roadmap - your input by Friday",
      "mk.s3": "Team offsite in Brno", "mk.s4": "Build #2841 passed",
      "mk.doneToast": "Marked done", "mk.undo": "Undo",

      "srch.eyebrow": "Search",
      "srch.title": "Find it, even from half a word",
      "srch.lead": "Search matches parts of words across the sender, recipients, subject and body, so <code>ertel</code> finds <code>erteltrading@...</code>. Narrow it down with operators, or just describe what you're after.",
      "srch.p1": "<b>Operators and regex.</b> <code>from:</code> <code>to:</code> <code>subject:</code> <code>has:attachment</code> <code>is:unread</code>, or a <code>/regex/</code> when you need one.",
      "srch.p2": "<b>Inside attachments.</b> Words in Word, Excel and PowerPoint files, plain text, CSV, JSON and code are indexed too.",
      "srch.p3": "<b>By meaning.</b> An optional local index finds \"that quote about server costs\" even when the mail never used those words.",
      "srch.p4": "<b>Instant, from anywhere.</b> <kbd>Ctrl</kbd> <kbd>K</kbd> opens a command palette that turns into live search as soon as you type an operator. Save any search as a smart folder.",
      "mk.q": "road", "mk.results": "2 results",
      "mk.r1": "Q4 <mark>road</mark>map - your input by Friday", "mk.r2": "Re: <mark>Road</mark>map draft v2",
      "mk.r2f": "q4-<mark>road</mark>map.docx", "mk.inFile": "match inside the file",

      "att.eyebrow": "Attachment safety",
      "att.title": "Know what a file does before you open it",
      "att.lead": "RaplMail checks risky attachments without ever running them. Every file is parsed, decoded and scanned, and you get a verdict before you double-click.",
      "att.p1": "<b>Warned before you open.</b> Executables, macro documents, decoy names like <code>payroll.pdf.exe</code>, right-to-left filename tricks and files whose contents don't match their extension.",
      "att.p2": "<b>Hidden content found.</b> A clean-looking PDF or Office file with a launch action, JavaScript, embedded files or VBA macros is flagged all the same.",
      "att.p3": "<b>Macros in plain language.</b> Obfuscated VBA is decoded, so a disguised downloader shows what it really does: its triggers, the URLs it calls and the files it drops.",
      "att.p4": "<b>An isolated inspection view.</b> Open any file in a WebAssembly view with no access to your files, your network or the app, see everything it would attempt, and get a score from 0 to 100.",
      "att.note": "Static analysis only. RaplMail never executes a file, not even in a virtual machine.",
      "mk.thTitle": "Suspicious attachment", "mk.thFile": "payroll_october.pdf.exe", "mk.thVerdict": "Dangerous",
      "mk.thLead": "This file has the hallmarks of malware. Opening it in your normal apps could run code on your PC.",
      "mk.thIntents": "What it would try to do",
      "mk.i1": "Hide behind a double extension (.pdf.exe)", "mk.i2": "Start a program", "mk.i3": "Download from a web address",
      "mk.openAnyway": "Open anyway (5)", "mk.cancel": "Cancel",

      "priv.title": "Private by design",
      "priv.lead": "Your mail is nobody's business, ours included. There is no RaplMail server, so there is nothing for us to see.",
      "p1.t": "No middleman", "p1.d": "RaplMail talks IMAP and SMTP straight to your provider. No RaplMail account, no proxy, nothing to sign up for.",
      "p2.t": "An encrypted vault", "p2.d": "Passwords and keys are sealed with your master password (Argon2id and Fernet). Cached mail can be encrypted at rest too.",
      "p3.t": "No tracking, either way", "p3.d": "No ads, no analytics, no telemetry. Tracking pixels are blocked, so senders can't tell when you read their mail.",
      "p4.t": "Sync without a cloud", "p4.d": "Link your PCs through one of your own mailboxes, encrypted with a passphrase that never leaves your devices.",

      "ai.eyebrow": "AI, if you want it",
      "ai.title": "AI that works for you, or not at all",
      "ai.lead": "Run a model on your own PC with Ollama, and nothing leaves your machine. Or bring your own OpenAI, Anthropic or OpenAI-compatible key: calls go straight to that provider, never through us. Don't want AI? One switch turns it all off.",
      "ai.p1": "<b>Catch me up.</b> A long thread becomes a TL;DR with the key points and action items, and your whole inbox can get a daily briefing.",
      "ai.p2": "<b>Replies and rewrites.</b> Drafts in your tone and in the language you write in. Rephrase, fix grammar, translate or shorten. It never sends anything on its own.",
      "ai.p3": "<b>An assistant that asks first.</b> Ask it to archive or mark mail and it shows the exact action and a sample of the affected messages before anything happens.",
      "ai.p4": "<b>Connect your AI apps.</b> Let Claude and other MCP apps search, sort and draft in your mailbox: read only, read and organize, or full access.",
      "mk.aiAsk": "Archive everything from noreply@shop.example",
      "mk.aiSays": "I found <b>14 messages</b> from noreply@shop.example. Archive them?",
      "mk.a1": "Your order has shipped", "mk.a2": "How did we do? Rate your purchase",
      "mk.archive14": "Archive 14", "mk.ollama": "Ollama, on this PC",

      "more.title": "Everything else a mail app should do",
      "more.lead": "Built for people who get a lot of mail and want to be done with it.",
      "m1.t": "Every account, found for you", "m1.d": "Type your address and RaplMail finds the servers. Microsoft 365 and Gmail sign in with OAuth, and any IMAP mailbox works.",
      "m2.t": "Views that sort themselves", "m2.d": "All Inboxes, a Newsletter Feed, Paper Trail for receipts and orders, and Follow-ups for sent mail nobody answered.",
      "m3.t": "A compose window that respects you", "m3.d": "WYSIWYG or Markdown, one-drag signatures with images, templates, send later and mail merge.",
      "m4.t": "Calendar and contacts", "m4.d": "Invitations turn into events you can answer. CalDAV and CardDAV sync with Nextcloud, Fastmail, iCloud, Seznam and more.",
      "m5.t": "PGP and S/MIME", "m5.d": "Sign, encrypt, verify and decrypt, with your keys and certificates managed in Settings.",
      "m6.t": "Works offline", "m6.d": "Archive, move and send without a connection. A queue catches up the moment you're back online.",
      "m7.t": "Sign-in codes, copied", "m7.d": "When a verification code arrives, it's already on your clipboard. Paste it and carry on.",
      "m8.t": "Subscription audit", "m8.d": "Every mailing list you get with its 30-day read rate, the ones you never open first, and one-click unsubscribe.",
      "m9.t": "Anti-spoof shield", "m9.d": "DMARC, DKIM and SPF results, warnings for lookalike and punycode domains, and links whose text lies about where they go.",
      "m10.t": "Made to fit you", "m10.d": "Colours from one seed or your Windows accent, light, dark or automatic, plus classic themes from OLED black to Dracula and Nord.",
      "m11.t": "For power users", "m11.d": "Custom shortcuts for everything, a command palette for every action, and a local metrics API for Home Assistant or Prometheus.",
      "m12.t": "There when you need it", "m12.d": "Closes to the tray while mail keeps arriving, shows unread mail on the taskbar and can start with Windows.",

      "cmp.title": "Why RaplMail?",
      "cmp.lead": "Most mail apps make you choose: fast workflows behind a paid cloud middleman, or local privacy inside a heavy, dated interface. RaplMail gives you both halves.",
      "cmp.r1": "Price", "cmp.r2": "Any IMAP/SMTP account", "cmp.r3": "No cloud middleman",
      "cmp.r4": "Keyboard triage (<kbd>e</kbd> to done)", "cmp.r5": "Screener, Feed and Paper Trail", "cmp.r6": "Local AI, no cloud needed",
      "cmp.free": "Free", "cmp.bundled": "With Windows", "cmp.month": "$30 / month", "cmp.year": "$99 / year",
      "cmp.partial": "Partial", "cmp.yes": "Yes", "cmp.no": "No",
      "cmp.note": "Prices in USD as listed by each vendor. Check their sites for current plans.",

      "dl.title": "Get RaplMail",
      "dl.lead": "Free for Windows 10 and 11. Install it, choose a master password, add an account. That's the whole setup.",
      "dl.guide": "Setup guide",
      "dl.msi": "Prefer MSI? Download the MSI installer",
      "dl.updates": "RaplMail keeps itself up to date. New versions download in the background, install when you click Restart & update, and are only accepted with the RaplMail release signature.",
      "dl.sum": "SHA-256",

      "faq.title": "Questions", "faq.lead": "The short answers. The wiki has the long ones.", "faq.wiki": "Browse the wiki",
      "q1": "Is RaplMail really free?", "a1": "Yes. There is no subscription and no account to create: download it and use it.",
      "q2": "Does my mail pass through a RaplMail server?", "a2": "No. RaplMail connects straight to your mail provider over IMAP and SMTP. If you add a cloud AI key, those calls also go straight from your PC to that provider.",
      "q3": "Which mail accounts work?", "a3": "Microsoft 365 and Outlook, Gmail and Google Workspace, and any provider with IMAP and SMTP, such as Seznam, Fastmail, iCloud or your own domain. Type your address and RaplMail finds the server settings.",
      "q4": "Do I have to use AI?", "a4": "No. AI buttons stay hidden until you set up a provider, and one switch in Settings turns every AI feature off.",
      "q5": "Does RaplMail run attachments to check them?", "a5": "Never. Files are parsed and scanned as data, not run. Even the isolated inspection view only reads the file, inside a WebAssembly module with no access to your PC.",
      "q6": "Can I use it on two computers?", "a6": "Yes. Device sync links your installs through a hidden folder in one of your own mailboxes, encrypted with a passphrase. Done, snooze, pin and your rules sync automatically.",
      "q7": "How do updates work?", "a7": "RaplMail checks for a new version every few hours, downloads it in the background and installs it when you click Restart & update. A file without a valid RaplMail signature is refused.",

      "new.title": "What's new", "new.lead": "Every version and what changed in it.",
      "new.loading": "Loading...", "new.none": "Release notes appear here with the first version.",
      "new.latest": "Latest", "new.older": "Show older versions",
      "foot.tag": "Fast, private mail for Windows.",
      "foot.by": "Made by",
    },
    cs: {
      "nav.features": "Funkce", "nav.privacy": "Soukromí", "nav.ai": "AI", "nav.wiki": "Wiki", "nav.new": "Novinky", "nav.download": "Stáhnout",
      "hero.eyebrow": "Pošta pro Windows",
      "hero.title": "Schránka? Hotovo.",
      "hero.lead": "Rychlá a soukromá poštovní aplikace pro lidi, kteří žijí v e-mailu. Poštu vyřizujete z klávesnice (stisknete <kbd>e</kbd> a je hotovo), cokoli najdete během pár úhozů a každá zpráva, heslo i klíč zůstávají ve vašem počítači.",
      "hero.download": "Stáhnout pro Windows",
      "hero.tour": "Jak to funguje",
      "hero.meta": "Verze {v} · {size} · Windows 10 a 11, 64bitové",
      "hero.metaNone": "Windows 10 a 11, 64bitové",
      "hero.soon": "První verze je na cestě - zastavte se brzy znovu.",
      "hero.t1": "Zdarma", "hero.t2": "Bez registrace", "hero.t3": "Bez telemetrie", "hero.t4": "Česky i anglicky",
      "hero.shotAlt": "RaplMail s chytrou schránkou a otevřenou zprávou",
      "glance.label": "V kostce",
      "g1": "serverů RaplMailu mezi vámi a vaší poštou",
      "g2": "paměti, i s velkými schránkami",
      "g3": "a zpráva je vyřízená",
      "g4.n": "Zdarma", "g4": "bez předplatného a registrace",

      "tri.eyebrow": "Třídění",
      "tri.title": "Vyřiďte poštu z klávesnice",
      "tri.lead": "Stiskněte <kbd>e</kbd> a zpráva je hotová: zmizí ze schránky, ale na serveru zůstane. Co počká, odložte, co nepočká, připněte, a šum se sám složí do skupin. Každou akci jde vrátit zpět.",
      "tri.p1": "<b>Odložit, připnout, VIP.</b> Odložte na přesný čas nebo <i>až se vrátím</i> a pošta se vrátí, jakmile se posadíte zpátky k počítači. Odesílatelé VIP jsou vždy nahoře.",
      "tri.p2": "<b>Šum ve skupinách.</b> Newslettery, upozornění a akce čekají ve vlastních skupinách a tři a více upozornění od jednoho odesílatele se složí do jednoho balíčku.",
      "tri.p3": "<b>Filtr odesílatelů a pravidla.</b> Noví odesílatelé čekají na vaše schválení. Pravidla podle odesílatele, domény nebo předmětu přesouvají, archivují, vyřizují nebo blokují, s živým náhledem.",
      "tri.p4": "<b>Vše jde vrátit.</b> Hotovo, odložení, archivace, mazání, přesun i hromadné akce mají tlačítko Zpět. Archivace a mazání se na serveru provedou, až lhůta pro vrácení uplyne.",
      "k.done": "Hotovo", "k.reply": "Odpovědět", "k.archive": "Archivovat", "k.search": "Hledat", "k.palette": "Příkazy", "k.all": "Všechny zkratky",
      "mk.inbox": "Chytrá schránka", "mk.notif": "Upozornění", "mk.news": "Newslettery",
      "mk.n1": "Klára Benešová", "mk.av1": "K", "mk.n2": "Daniel Kovář", "mk.n3": "Marta Horáková", "mk.from": "from:klara",
      "mk.s1": "Revize návrhu se přesouvá na čtvrtek", "mk.s2": "Plán na Q4 - váš názor do pátku",
      "mk.s3": "Týmový výjezd do Brna", "mk.s4": "Build #2841 prošel",
      "mk.doneToast": "Označeno jako hotové", "mk.undo": "Zpět",

      "srch.eyebrow": "Hledání",
      "srch.title": "Najdete to, i když si pamatujete půl slova",
      "srch.lead": "Hledání porovnává i části slov v odesílateli, příjemcích, předmětu a těle zprávy, takže <code>ertel</code> najde <code>erteltrading@...</code>. Zužte ho operátory, nebo prostě popište, co hledáte.",
      "srch.p1": "<b>Operátory a regulární výrazy.</b> <code>from:</code> <code>to:</code> <code>subject:</code> <code>has:attachment</code> <code>is:unread</code>, nebo <code>/regex/</code>, když je potřeba.",
      "srch.p2": "<b>Uvnitř příloh.</b> Indexují se i slova v souborech Word, Excel a PowerPoint, v prostém textu, CSV, JSON a kódu.",
      "srch.p3": "<b>Podle významu.</b> Volitelný místní index najde „tu nabídku na náklady na servery“, i když v e-mailu tahle slova vůbec nebyla.",
      "srch.p4": "<b>Hned a odkudkoli.</b> <kbd>Ctrl</kbd> <kbd>K</kbd> otevře paletu příkazů, která se po napsání operátoru změní v živé hledání. Jakékoli hledání si uložíte jako chytrou složku.",
      "mk.q": "plán", "mk.results": "2 výsledky",
      "mk.r1": "<mark>Plán</mark> na Q4 - váš názor do pátku", "mk.r2": "Re: Návrh <mark>plán</mark>u v2",
      "mk.r2f": "q4-<mark>plán</mark>.docx", "mk.inFile": "shoda uvnitř souboru",

      "att.eyebrow": "Bezpečné přílohy",
      "att.title": "Víte, co soubor udělá, dřív než ho otevřete",
      "att.lead": "RaplMail prověřuje rizikové přílohy, aniž by je kdy spustil. Každý soubor rozebere, dekóduje a prohledá a verdikt máte dřív, než na něj dvakrát kliknete.",
      "att.p1": "<b>Varování před otevřením.</b> Spustitelné soubory, dokumenty s makry, klamné názvy jako <code>vyplata.pdf.exe</code>, triky s obráceným směrem textu v názvu a soubory, jejichž obsah neodpovídá příponě.",
      "att.p2": "<b>Skrytý obsah odhalen.</b> Nevinně vypadající PDF nebo dokument Office se spouštěcí akcí, JavaScriptem, vloženými soubory nebo makry VBA se označí stejně.",
      "att.p3": "<b>Makra srozumitelně.</b> Zamaskované VBA se dekóduje, takže skrytý stahovač ukáže, co doopravdy dělá: čím se spouští, jaké adresy volá a jaké soubory vytváří.",
      "att.p4": "<b>Izolované zobrazení k prozkoumání.</b> Otevřete jakýkoli soubor v zobrazení WebAssembly bez přístupu k vašim souborům, síti i aplikaci, uvidíte vše, o co by se pokusil, a dostanete skóre od 0 do 100.",
      "att.note": "Jen statická analýza. RaplMail soubor nikdy nespouští, ani ve virtuálním počítači.",
      "mk.thTitle": "Podezřelá příloha", "mk.thFile": "vyplata_rijen.pdf.exe", "mk.thVerdict": "Nebezpečné",
      "mk.thLead": "Tento soubor má znaky škodlivého kódu. Otevření v běžných aplikacích může na vašem PC spustit kód.",
      "mk.thIntents": "O co by se pokusil",
      "mk.i1": "Schovat se za dvojitou příponu (.pdf.exe)", "mk.i2": "Spustit program", "mk.i3": "Stáhnout soubor z internetu",
      "mk.openAnyway": "Přesto otevřít (5)", "mk.cancel": "Zrušit",

      "priv.title": "Soukromí od základu",
      "priv.lead": "Do vaší pošty nikomu nic není, ani nám. RaplMail nemá žádný server, takže ani není co vidět.",
      "p1.t": "Žádný prostředník", "p1.d": "RaplMail komunikuje přes IMAP a SMTP přímo s vaším poskytovatelem. Žádný účet u RaplMailu, žádná proxy, nikde se neregistrujete.",
      "p2.t": "Šifrovaný trezor", "p2.d": "Hesla a klíče jsou zapečetěné vaším hlavním heslem (Argon2id a Fernet). Šifrovat lze i poštu uloženou v počítači.",
      "p3.t": "Žádné sledování, ani jedním směrem", "p3.d": "Žádné reklamy, analytika ani telemetrie. Sledovací pixely jsou blokované, takže odesílatelé nepoznají, kdy jste jejich zprávu četli.",
      "p4.t": "Synchronizace bez cloudu", "p4.d": "Propojte své počítače přes jednu z vlastních schránek, šifrovaně heslem, které nikdy neopustí vaše zařízení.",

      "ai.eyebrow": "AI, pokud o ni stojíte",
      "ai.title": "AI, která pracuje pro vás, nebo vůbec",
      "ai.lead": "Spusťte model přímo ve svém počítači přes Ollama a nic neopustí váš stroj. Nebo použijte vlastní klíč od OpenAI, Anthropicu či služby kompatibilní s OpenAI: požadavky jdou rovnou k poskytovateli, nikdy přes nás. Nechcete AI? Jeden přepínač ji celou vypne.",
      "ai.p1": "<b>Shrň mi to.</b> Z dlouhé konverzace je krátké shrnutí s hlavními body a úkoly a celá schránka může dostávat denní přehled.",
      "ai.p2": "<b>Odpovědi a úpravy textu.</b> Návrhy ve vašem tónu a v jazyce, kterým píšete. Přeformulování, oprava gramatiky, překlad nebo zkrácení. Sama nikdy nic neodešle.",
      "ai.p3": "<b>Asistent, který se nejdřív zeptá.</b> Požádejte ho o archivaci nebo označení pošty a než se cokoli stane, ukáže vám přesnou akci a ukázku dotčených zpráv.",
      "ai.p4": "<b>Propojte své AI aplikace.</b> Dovolte Claudovi a dalším MCP aplikacím hledat, třídit a psát koncepty ve vaší poště: jen číst, číst a třídit, nebo vše.",
      "mk.aiAsk": "Archivuj všechno od noreply@shop.example",
      "mk.aiSays": "Našel jsem <b>14 zpráv</b> od noreply@shop.example. Mám je archivovat?",
      "mk.a1": "Vaše objednávka byla odeslána", "mk.a2": "Jak jsme si vedli? Ohodnoťte nákup",
      "mk.archive14": "Archivovat 14", "mk.ollama": "Ollama, v tomto PC",

      "more.title": "A všechno ostatní, co má pošta umět",
      "more.lead": "Pro lidi, kterým chodí hodně pošty a chtějí ji mít rychle vyřízenou.",
      "m1.t": "Každý účet, nastavený za vás", "m1.d": "Napište adresu a RaplMail sám najde servery. Microsoft 365 a Gmail se přihlásí přes OAuth a funguje jakákoli schránka IMAP.",
      "m2.t": "Pohledy, které se třídí samy", "m2.d": "Všechny schránky, Kanál newsletterů, Doklady pro účtenky a objednávky a K vyřízení pro odeslané zprávy, na které nikdo neodpověděl.",
      "m3.t": "Psaní, které vás nezdržuje", "m3.d": "WYSIWYG nebo Markdown, podpisy s obrázky na jedno přetažení, šablony, odeslání později a hromadná korespondence.",
      "m4.t": "Kalendář a kontakty", "m4.d": "Z pozvánek jsou události, na které rovnou odpovíte. CalDAV a CardDAV se synchronizují s Nextcloudem, Fastmailem, iCloudem, Seznamem a dalšími.",
      "m5.t": "PGP a S/MIME", "m5.d": "Podepisujte, šifrujte, ověřujte a dešifrujte, klíče i certifikáty spravujete v Nastavení.",
      "m6.t": "Funguje i offline", "m6.d": "Archivujte, přesouvejte a odesílejte i bez připojení. Fronta vše dožene, jakmile budete zpět online.",
      "m7.t": "Kódy rovnou zkopírované", "m7.d": "Když dorazí ověřovací kód, už ho máte ve schránce. Stačí vložit a pokračovat.",
      "m8.t": "Přehled odběrů", "m8.d": "Všechny rozesílky, které dostáváte, s mírou přečtení za 30 dní, ty nikdy neotevřené nahoře, a odhlášení jedním kliknutím.",
      "m9.t": "Ochrana proti podvrhům", "m9.d": "Výsledky DMARC, DKIM a SPF, varování před podobnými a punycode doménami a před odkazy, jejichž text lže o cíli.",
      "m10.t": "Přizpůsobí se vám", "m10.d": "Barvy z jednoho odstínu nebo z akcentu Windows, světlý, tmavý nebo automatický režim a klasické motivy od OLED černé po Draculu a Nord.",
      "m11.t": "Pro pokročilé", "m11.d": "Vlastní klávesové zkratky na všechno, paleta příkazů pro každou akci a místní API s metrikami pro Home Assistant nebo Prometheus.",
      "m12.t": "Po ruce, když je potřeba", "m12.d": "Zavře se do oznamovací oblasti a pošta dál chodí, na hlavním panelu ukazuje nepřečtené a může se spouštět s Windows.",

      "cmp.title": "Proč RaplMail?",
      "cmp.lead": "Většina poštovních aplikací vás nutí vybrat si: rychlou práci přes placeného cloudového prostředníka, nebo soukromí v těžkopádném a zastaralém rozhraní. RaplMail vám dá obojí.",
      "cmp.r1": "Cena", "cmp.r2": "Jakýkoli účet IMAP/SMTP", "cmp.r3": "Bez cloudového prostředníka",
      "cmp.r4": "Třídění z klávesnice (<kbd>e</kbd> = hotovo)", "cmp.r5": "Filtr odesílatelů, kanál a doklady", "cmp.r6": "Místní AI bez cloudu",
      "cmp.free": "Zdarma", "cmp.bundled": "Součást Windows", "cmp.month": "30 $ / měsíc", "cmp.year": "99 $ / rok",
      "cmp.partial": "Částečně", "cmp.yes": "Ano", "cmp.no": "Ne",
      "cmp.note": "Ceny v USD podle jednotlivých výrobců. Aktuální tarify ověřte na jejich webu.",

      "dl.title": "Stáhněte si RaplMail",
      "dl.lead": "Zdarma pro Windows 10 a 11. Nainstalujte, zvolte hlavní heslo, přidejte účet. To je celé nastavení.",
      "dl.guide": "Návod k instalaci",
      "dl.msi": "Raději MSI? Stáhnout instalátor MSI",
      "dl.updates": "RaplMail se aktualizuje sám. Nové verze se stáhnou na pozadí, nainstalují se, až kliknete na Restartovat a aktualizovat, a přijme jen ty, které nesou podpis vydání RaplMailu.",
      "dl.sum": "SHA-256",

      "faq.title": "Časté otázky", "faq.lead": "Krátké odpovědi. Ty dlouhé najdete ve wiki.", "faq.wiki": "Projít wiki",
      "q1": "Je RaplMail opravdu zdarma?", "a1": "Ano. Žádné předplatné a žádný účet: stáhnete a používáte.",
      "q2": "Prochází moje pošta přes server RaplMailu?", "a2": "Ne. RaplMail se připojuje přímo k vašemu poskytovateli pošty přes IMAP a SMTP. Pokud přidáte klíč ke cloudové AI, i tyto požadavky jdou z vašeho počítače rovnou k danému poskytovateli.",
      "q3": "Jaké e-mailové účty fungují?", "a3": "Microsoft 365 a Outlook, Gmail a Google Workspace a jakýkoli poskytovatel s IMAP a SMTP, třeba Seznam, Fastmail, iCloud nebo vlastní doména. Napíšete adresu a RaplMail nastavení serverů najde sám.",
      "q4": "Musím používat AI?", "a4": "Ne. Tlačítka AI zůstanou skrytá, dokud nenastavíte poskytovatele, a jeden přepínač v Nastavení vypne všechny funkce AI.",
      "q5": "Spouští RaplMail přílohy, aby je prověřil?", "a5": "Nikdy. Soubory se rozebírají a prohledávají jako data, nespouštějí se. I izolované zobrazení soubor jen čte, uvnitř modulu WebAssembly bez přístupu k vašemu počítači.",
      "q6": "Můžu ho používat na dvou počítačích?", "a6": "Ano. Synchronizace zařízení propojí vaše instalace přes skrytou složku v jedné z vašich schránek, zašifrovanou heslem. Hotové, odložené a připnuté zprávy i pravidla se synchronizují automaticky.",
      "q7": "Jak fungují aktualizace?", "a7": "RaplMail každých pár hodin zkontroluje novou verzi, stáhne ji na pozadí a nainstaluje, až kliknete na Restartovat a aktualizovat. Soubor bez platného podpisu RaplMailu odmítne.",

      "new.title": "Co je nového", "new.lead": "Všechny verze a co se v nich změnilo. Poznámky k vydání jsou v angličtině.",
      "new.loading": "Načítání...", "new.none": "Poznámky k vydání se tu objeví s první verzí.",
      "new.latest": "Nejnovější", "new.older": "Zobrazit starší verze",
      "foot.tag": "Rychlá a soukromá pošta pro Windows.",
      "foot.by": "Vytvořila společnost",
    },
  };

  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  let lang = store.get("raplmail.site.lang") || ((navigator.language || "").toLowerCase().startsWith("cs") ? "cs" : "en");
  let feed = null, log = null;

  const t = (k, vars) => (T[lang][k] ?? T.en[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => (vars && n in vars ? vars[n] : ""));
  const mb = (n) => Math.round(n / 1e6) + " MB";

  function apply() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
    document.querySelectorAll("[data-th]").forEach((el) => { el.innerHTML = t(el.dataset.th); });
    document.querySelectorAll("[data-t-alt]").forEach((el) => { el.alt = t(el.dataset.tAlt); });
    document.querySelectorAll("[data-t-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.tLabel)); });
    document.querySelectorAll(".lang [data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    document.querySelector(".js-shot").src = `assets/img/app-${lang}-light.webp`;
    document.querySelector(".js-shot-dark").srcset = `assets/img/app-${lang}-dark.webp`;
    document.title = lang === "cs" ? "RaplMail - rychlá a soukromá pošta pro Windows" : "RaplMail - fast, private mail for Windows";
    renderDownloads();
    renderLog();
  }

  function renderDownloads() {
    const d = feed?.downloads?.nsis;
    document.querySelectorAll(".js-meta").forEach((el) => {
      el.textContent = d ? t("hero.meta", { v: feed.version, size: mb(d.size) }) : feed === false ? t("hero.soon") : t("hero.metaNone");
    });
    document.querySelectorAll(".js-dl").forEach((a, i) => {
      if (d) a.href = d.url;
      else if (i > 0) a.href = "#download";
    });
    const msi = feed?.downloads?.msi;
    document.querySelector(".js-msi").hidden = !msi;
    if (msi) document.querySelector(".js-msi-link").href = msi.url;
    const sum = document.querySelector(".js-sum");
    sum.hidden = !d;
    if (d) sum.textContent = `${t("dl.sum")} (${d.file}): ${d.sha256}`;
    document.querySelector(".js-ver").textContent = feed?.version ? `v${feed.version}` : "";
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // A point is { lead, text }: the changelog's bold opening sentence, then the rest.
  const point = (it) => (typeof it === "string" ? esc(it) : (it.lead ? `<b>${esc(it.lead)}</b> ` : "") + esc(it.text || ""));
  function fmtDate(iso) {
    if (!iso) return "";
    try { return new Date(iso + "T12:00:00Z").toLocaleDateString(lang === "cs" ? "cs-CZ" : "en-GB", { day: "numeric", month: "long", year: "numeric" }); }
    catch { return iso; }
  }
  function renderLog() {
    const box = document.querySelector(".js-log");
    if (log === null) return;
    if (!log.length) { box.innerHTML = `<p class="note">${esc(t("new.none"))}</p>`; return; }
    const chev = document.getElementById("chev").innerHTML;
    const one = (v, i) => `<details${i === 0 ? " open" : ""}>
      <summary>${esc(v.version)} <span class="date">${esc(fmtDate(v.date))}</span>${i === 0 ? ` <span class="tag">${esc(t("new.latest"))}</span>` : ""}<span class="chev">${chev}</span></summary>
      ${v.sections.map((s) => `<h4>${esc(s.title)}</h4><ul>${s.items.map((it) => `<li>${point(it)}</li>`).join("")}</ul>`).join("")}
    </details>`;
    const first = log.slice(0, 4), rest = log.slice(4);
    box.innerHTML = first.map(one).join("") +
      (rest.length ? `<div class="js-older" hidden>${rest.map((v, i) => one(v, i + 4)).join("")}</div>
        <p class="note"><button class="btn btn-text js-more" type="button">${esc(t("new.older"))}</button></p>` : "");
    box.querySelector(".js-more")?.addEventListener("click", (e) => {
      box.querySelector(".js-older").hidden = false;
      e.currentTarget.parentElement.remove();
    });
  }

  document.querySelectorAll(".lang [data-lang]").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang; store.set("raplmail.site.lang", lang); apply();
  }));
  const bar = document.getElementById("bar");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 4);
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll();

  apply();
  fetch("updates/latest.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((j) => { feed = j; }, () => { feed = false; })
    .then(renderDownloads);
  fetch("updates/changelog.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((j) => { log = Array.isArray(j) ? j : []; }, () => { log = []; })
    .then(renderLog);
})();
