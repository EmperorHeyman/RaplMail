// English UI catalog. Flat "namespace.key" → text. {placeholders} are filled by
// t(key, { placeholder: value }). Keep keys stable; add, don't rename.
//
// Per-component fragments live in ./parts/*.js (each exports { en, cs }); they're
// merged in below so localization can be extended component-by-component without
// one giant file.
import nav from "./parts/nav.js";
import list from "./parts/list.js";
import reader from "./parts/reader.js";
import compose from "./parts/compose.js";
import cmd from "./parts/cmd.js";
import settingsNav from "./parts/settingsNav.js";
import goto from "./parts/goto.js";
import search from "./parts/search.js";
import devicesync from "./parts/devicesync.js";

const base = {
  // Common actions / words reused across the app.
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.close": "Close",
  "common.done": "Done",
  "common.next": "Next",
  "common.back": "Back",
  "common.skip": "Skip",
  "common.finish": "Finish",
  "common.getStarted": "Get started",
  "common.retry": "Retry",
  "common.play": "Play",
  "common.preview": "Preview",
  "common.enabled": "Enabled",
  "common.disabled": "Disabled",

  // Boot / connecting screen.
  "boot.starting": "Starting RaplMail…",
  "boot.cantReach": "Couldn't reach the RaplMail backend.",
  "boot.warmingUp": "Warming things up…",

  // First-run onboarding wizard.
  "onboarding.stepOf": "Step {n} of {total}",
  "onboarding.welcomeTitle": "Welcome to RaplMail",
  "onboarding.welcomeBody": "A fast, local-first email client that runs on your machine. Let's set it up — it only takes a few seconds.",
  "onboarding.languageTitle": "Choose your language",
  "onboarding.languageBody": "You can change this anytime in Settings.",
  "onboarding.themeTitle": "Pick your look",
  "onboarding.themeBody": "Choose a theme to start with. You can fine-tune every color later in Appearance.",
  "onboarding.optionsTitle": "A few preferences",
  "onboarding.optionsBody": "Turn on what you'd like to use. All of this can be changed later in Settings.",
  "onboarding.doneTitle": "You're all set",
  "onboarding.doneBody": "Add an account to start reading mail. Press ? anytime to see keyboard shortcuts.",
  "onboarding.smartInbox": "Smart Inbox",
  "onboarding.smartInboxHint": "Group newsletters, social and updates into tidy cards instead of one long list.",
  "onboarding.notifications": "Desktop notifications",
  "onboarding.notificationsHint": "A gentle ding and a popup when genuinely new mail arrives.",
  "onboarding.startWithWindows": "Start with Windows",
  "onboarding.startWithWindowsHint": "Launch RaplMail automatically when you sign in (into the tray).",
  "onboarding.addAccount": "Add an account",

  // Notifications settings.
  "notif.title": "Notifications",
  "notif.newMail": "Notify me about new mail",
  "notif.onlyUnfocused": "Only when RaplMail isn't focused",
  "notif.sound": "Sound",
  "notif.volume": "Volume",
  "notif.test": "Send test notification",
  "notif.muteHint": "To silence a specific sender or a whole category, add a \"Mute notifications\" rule.",

  // Language settings.
  "settings.language": "Language",
  "settings.languageHint": "The language of the RaplMail interface.",

  // Rules — field / operator / action labels.
  "rules.field.from_domain": "Sender domain",
  "rules.field.from": "Sender address",
  "rules.field.to": "Recipient",
  "rules.field.subject": "Subject",
  "rules.field.body": "Body",
  "rules.field.category": "Category",
  "rules.op.contains": "contains",
  "rules.op.equals": "equals",
  "rules.op.ends_with": "ends with",
  "rules.op.regex": "matches regex",
  "rules.action.move": "Move to folder",
  "rules.action.archive": "Archive",
  "rules.action.delete": "Delete",
  "rules.action.mark_read": "Mark read",
  "rules.action.mark_done": "Mark done",
  "rules.action.block": "Block (quarantine)",
  "rules.action.mute_notifications": "Mute notifications",
  "rules.action.webhook": "POST to a webhook",
  "rules.action.run_script": "Run a local script",
  "rules.categoryHint": "e.g. newsletters, social, updates, promotions",
  "rules.webhookHint": "https://… webhook URL (POST)",
  "rules.scriptHint": "command to run, e.g. python handler.py",
  "rules.muteFromSender": "Mute notifications from sender",

  // Common toasts.
  "toast.muteNotifOn": "Muted notifications from {who}",

  // S/MIME (Settings → S/MIME).
  "smime.identityTitle": "Your S/MIME certificate",
  "smime.identityHint": "Import a .p12 / .pfx file (your X.509 certificate + private key) so RaplMail can sign and decrypt S/MIME mail. Stored locally, like your PGP keys.",
  "smime.certificate": "Certificate imported",
  "smime.p12password": "File password",
  "smime.importP12": "Import .p12 / .pfx…",
  "smime.importing": "Importing…",
  "smime.imported": "S/MIME certificate imported for {who}",
  "smime.remove": "Remove",
  "smime.recipientsTitle": "Recipients' certificates",
  "smime.recipientsHint": "Paste a correspondent's X.509 certificate (PEM) to be able to send them encrypted S/MIME mail.",
  "smime.addCert": "Add certificate",
  "smime.certAdded": "Certificate added",
  "smime.badCert": "That doesn't look like a PEM certificate (expected -----BEGIN CERTIFICATE-----).",

  // Utility → Subscription Audit.
  "utility.subscriptionsTitle": "Subscription Audit",
  "utility.subscriptionsHint": "Every mailing list you receive, with how much you actually read in the last 30 days. Dormant lists come first — unsubscribe or auto-archive them in one sweep.",
  "utility.none": "No mailing lists detected yet. Open a few newsletters and they'll show up here.",
  "utility.selectAll": "Select all",
  "utility.archiveSelected": "Auto-archive {n}",
  "utility.unsubSelected": "Unsubscribe {n}",
  "utility.total": "received",
  "utility.readRate": "read (30d)",
  "utility.lastSeen": "last seen",
  "utility.unsubscribe": "Unsubscribe",
  "utility.archiveFuture": "Auto-archive",
  "utility.archivedRule": "Future mail from {who} will be archived",
  "utility.archivedN": "Auto-archive rule added for {n} sender(s)",
};

export default {
  ...base,
  ...nav.en, ...list.en, ...reader.en, ...compose.en, ...cmd.en, ...settingsNav.en,
  ...goto.en, ...search.en, ...devicesync.en,
};
