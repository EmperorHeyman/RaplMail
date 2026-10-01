// Smart Inbox groups - the built-in categories plus the user's own - as one
// list for the mail list, the settings, the rule builders and the palette.
// Call these inside $derived so labels follow the language and group edits.
import { app, categoryLabel, BUILTIN_GROUPS } from "./store.svelte.js";
import { icons } from "./icons.js";

// `tone` colours each group's icon tile. Deliberately fixed hues rather than
// theme tokens: the point is telling the groups apart, which a single accent
// can't do, and a 15% tint of any of these reads fine on light and dark alike.
const BUILTIN = {
  updates: { icon: "bell", tone: "#3b82f6" },
  newsletters: { icon: "newspaper", tone: "#a855f7" },
  social: { icon: "chat", tone: "#14b8a6" },
  promotions: { icon: "tag", tone: "#f0a53a" },
  invitations: { icon: "calendar", tone: "#22c55e" },
  invitation_responses: { icon: "done", tone: "#0ea5e9" },
};

// Icons offered for a custom group (keys into icons.js).
export const GROUP_ICONS = ["folder", "accounts", "contacts", "receipt", "star",
  "bolt", "shield", "lock", "clock", "pin", "bell", "tag", "calendar", "chat", "newspaper"];

/** Every group, built-ins first: { id, label, icon (svg markup), tone, custom }. */
export function smartGroupList() {
  const builtin = BUILTIN_GROUPS.map((id) => ({
    id, label: categoryLabel(id), icon: icons[BUILTIN[id].icon], tone: BUILTIN[id].tone, custom: false,
  }));
  const custom = (app.settings.customGroups || []).map((g) => ({
    id: g.id, label: g.name, icon: icons[g.icon] || icons.folder, tone: g.tone || "", custom: true,
  }));
  return [...builtin, ...custom];
}

/** The same, keyed by id. */
export function smartGroupMeta() {
  return Object.fromEntries(smartGroupList().map((g) => [g.id, g]));
}
