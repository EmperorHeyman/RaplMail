// Shared search-query helpers used by the inline SearchBar and the SearchPalette.
// The query is a single string the backend understands: operator tokens
// (from:/to:/cc:/subject:/has:/is:) + a /regex/ + free text. These helpers parse
// it into removable "chips" (completed operators) plus trailing free text, and
// build it back.

export const OP_RE = /^(from|to|cc|subject|has|is):.+$|^\/.+\/$/i;

export const OPERATORS = [
  { token: "from:", hint: "From a sender", value: true },
  { token: "to:", hint: "Sent to", value: true },
  { token: "cc:", hint: "Cc'd to", value: true },
  { token: "subject:", hint: "Subject contains", value: true },
  { token: "has:attachment", hint: "Has an attachment" },
  { token: "is:unread", hint: "Unread only" },
  { token: "is:read", hint: "Read only" },
  { token: "is:flagged", hint: "Flagged" },
  { token: "is:done", hint: "Marked done" },
];

// Split respecting /regex/ and "quoted phrases".
export const smartSplit = (s) => (String(s || "").match(/\/[^/]+\/|"[^"]*"|\S+/g)) || [];
export const isOp = (t) => OP_RE.test(t);
export const opParts = (t) => { const i = t.indexOf(":"); return i < 0 ? [t, ""] : [t.slice(0, i + 1), t.slice(i + 1)]; };

// Operators that can't sensibly coexist (would AND to an always-empty result).
const EXCLUSIVE = [["is:read", "is:unread"]];

// De-dupe identical chips (last wins) and drop earlier members of a mutually
// exclusive group, so `is:unread` + `is:read` can't silently zero out results.
export function normalizeChips(list) {
  const seen = new Set();
  const out = [];
  for (let i = list.length - 1; i >= 0; i--) {
    const key = list[i].toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.unshift(list[i]);
  }
  for (const group of EXCLUSIVE) {
    const members = out.filter((c) => group.includes(c.toLowerCase()));
    if (members.length > 1) {
      const keep = members[members.length - 1];
      for (let i = out.length - 1; i >= 0; i--) {
        if (group.includes(out[i].toLowerCase()) && out[i] !== keep) out.splice(i, 1);
      }
    }
  }
  return out;
}

// Parse a query string into { chips, text }.
export function parseQuery(value) {
  const tokens = smartSplit(value);
  return {
    chips: normalizeChips(tokens.filter(isOp)),
    text: tokens.filter((t) => !isOp(t)).join(" "),
  };
}

// Build a query string from chips + trailing free text.
export function buildQuery(chips, text) {
  return [...chips, (text || "").trim()].filter(Boolean).join(" ");
}
