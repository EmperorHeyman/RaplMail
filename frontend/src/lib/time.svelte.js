// Timestamp formatting for list rows and metadata lines.
//
// This is a `.svelte.js` module for one reason: a relative timestamp has a hidden
// dependency on the CLOCK, not just on its date. `fmtTime(m.date)` recomputes only
// when `m.date` changes - and it never does - so a row that first rendered the
// moment its mail arrived kept saying "just now" an hour later. Both formatters
// read the shared tick below, which makes every call site (templates are reactive)
// re-render on its own without a single change at the call site.
//
// 30 seconds is the coarsest interval that still flips "just now" -> "1 minute
// ago" promptly; the cost is one integer write per half minute for the whole app.
let tick = $state(0);
if (typeof window !== "undefined") {
  setInterval(() => { tick += 1; }, 30_000);
}

/** Subscribe the caller to the shared clock. Exported for anything that formats a
 *  time itself (e.g. Intl) and needs the same self-updating behaviour. */
export function clockTick() {
  return tick;
}

// Full relative phrasing, e.g. "3 hours ago" / "in 2 days".
export function relativeTime(iso) {
  clockTick();
  if (!iso) return "";
  const d = new Date(iso);
  // An unparseable date used to fall all the way through the unit loop (every
  // comparison against NaN being false) and return "just now" - a wrong timestamp
  // presented as a confident one. Say nothing instead.
  if (Number.isNaN(d.getTime())) return "";
  let s = Math.round((Date.now() - d.getTime()) / 1000);
  const future = s < 0;
  s = Math.abs(s);
  if (s < 45) return future ? "in a moment" : "just now";
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800],
                 ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, secs] of units) {
    const v = Math.floor(s / secs);
    if (v >= 1) { const label = `${v} ${name}${v > 1 ? "s" : ""}`; return future ? `in ${label}` : `${label} ago`; }
  }
  return future ? "in a moment" : "just now";
}

// Compact, friendly timestamps for list rows.
export function listTime(iso) {
  clockTick();
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const ms = now - d;
  const min = ms / 60000;
  if (min < 1) return "now";
  if (min < 60) return `${Math.floor(min)}m`;
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  if (ms < 7 * 86400000) return d.toLocaleDateString([], { weekday: "short" });
  if (d.getFullYear() === now.getFullYear()) return d.toLocaleDateString([], { month: "short", day: "numeric" });
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "2-digit" });
}
