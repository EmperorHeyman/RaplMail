// Device sync settings (SettingsSync.svelte). Flat "dsync.*" keys + the nav
// label. Mirror every en key in cs. {placeholders} filled by t().
export default {
  en: {
    "settingsNav.sync": "Device sync",

    "dsync.intro": "Keep two (or more) RaplMail installs in step without a cloud account. One of your own mailboxes carries the data — every change is encrypted with a passphrase that never leaves your devices and stored in a hidden folder. Your 'done', snooze, pins and settings travel; read/flag already sync via IMAP.",
    "dsync.loading": "Loading…",

    "dsync.enable": "Sync this device",
    "dsync.enableHint": "Publish and pick up changes through the carrier mailbox below.",
    "dsync.account": "Carrier account",
    "dsync.accountHint": "The account that carries the sync data — must be configured on every device you're linking (same mailbox).",
    "dsync.passphrase": "Sync passphrase",
    "dsync.passphraseHint": "Enter the SAME passphrase on every device. It encrypts the sync data; your provider only ever sees ciphertext. At least 8 characters.",
    "dsync.passphraseSet": "Passphrase set",
    "dsync.change": "Change",
    "dsync.passphrasePlaceholder": "a strong shared passphrase",

    "dsync.save": "Save",
    "dsync.saving": "Saving…",
    "dsync.saved": "Device sync settings saved",
    "dsync.syncNow": "Sync now",
    "dsync.syncingNow": "Syncing…",
    "dsync.syncedNow": "Synced",
    "dsync.syncedWithError": "Sync ran, but reported a problem — see the status below.",

    "dsync.needAccount": "Choose a carrier account first.",
    "dsync.needPassphrase": "Set a sync passphrase first.",
    "dsync.passTooShort": "The passphrase must be at least 8 characters.",
    "dsync.never": "never",

    "dsync.stAccount": "Carrier account",
    "dsync.stLastSynced": "Last synced",
    "dsync.stLastError": "Last error",
    "dsync.stDevice": "This device",

    "dsync.howTitle": "How it works",
    "dsync.how1": "On a change (or when you hit Sync now), an encrypted message is appended to a hidden \"RaplMail Sync\" folder in the carrier mailbox.",
    "dsync.how2": "Every device reads that folder, decrypts with the shared passphrase, and merges — newest change wins.",
    "dsync.how3": "Nothing goes to a third party. If you ever see the sync message in another mail app, it's safe to ignore or delete.",
    "dsync.how4": "Use the same carrier account and the same passphrase on each device you link.",
  },
  cs: {
    "settingsNav.sync": "Synchronizace zařízení",

    "dsync.intro": "Udržujte dvě (nebo více) instalace RaplMailu v souladu bez cloudového účtu. Data přenáší jedna z vašich vlastních schránek — každá změna je zašifrována heslem, které nikdy neopustí vaše zařízení, a uložena do skryté složky. Přenáší se 'hotovo', odložení, připnutí a nastavení; přečteno/vlajka se už synchronizují přes IMAP.",
    "dsync.loading": "Načítání…",

    "dsync.enable": "Synchronizovat toto zařízení",
    "dsync.enableHint": "Odesílat a přijímat změny přes níže zvolenou schránku.",
    "dsync.account": "Přenosový účet",
    "dsync.accountHint": "Účet, který přenáší synchronizovaná data — musí být nastaven na každém propojovaném zařízení (stejná schránka).",
    "dsync.passphrase": "Synchronizační heslo",
    "dsync.passphraseHint": "Zadejte STEJNÉ heslo na každém zařízení. Šifruje synchronizovaná data; váš poskytovatel vidí jen šifrovaný text. Alespoň 8 znaků.",
    "dsync.passphraseSet": "Heslo nastaveno",
    "dsync.change": "Změnit",
    "dsync.passphrasePlaceholder": "silné sdílené heslo",

    "dsync.save": "Uložit",
    "dsync.saving": "Ukládání…",
    "dsync.saved": "Nastavení synchronizace uloženo",
    "dsync.syncNow": "Synchronizovat nyní",
    "dsync.syncingNow": "Synchronizuji…",
    "dsync.syncedNow": "Synchronizováno",
    "dsync.syncedWithError": "Synchronizace proběhla, ale hlásí problém — viz stav níže.",

    "dsync.needAccount": "Nejprve zvolte přenosový účet.",
    "dsync.needPassphrase": "Nejprve nastavte synchronizační heslo.",
    "dsync.passTooShort": "Heslo musí mít alespoň 8 znaků.",
    "dsync.never": "nikdy",

    "dsync.stAccount": "Přenosový účet",
    "dsync.stLastSynced": "Naposledy synchronizováno",
    "dsync.stLastError": "Poslední chyba",
    "dsync.stDevice": "Toto zařízení",

    "dsync.howTitle": "Jak to funguje",
    "dsync.how1": "Při změně (nebo po klepnutí na Synchronizovat nyní) se do skryté složky „RaplMail Sync“ v přenosové schránce přidá zašifrovaná zpráva.",
    "dsync.how2": "Každé zařízení tuto složku čte, dešifruje sdíleným heslem a slučuje — vyhrává nejnovější změna.",
    "dsync.how3": "Nic neputuje třetí straně. Pokud synchronizační zprávu někdy uvidíte v jiné aplikaci, můžete ji klidně ignorovat nebo smazat.",
    "dsync.how4": "Na každém propojeném zařízení použijte stejný přenosový účet a stejné heslo.",
  },
};
