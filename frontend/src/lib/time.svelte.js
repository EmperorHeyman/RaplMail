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
import { currentLocale } from "./i18n.svelte.js";

let tick = $state(0);
if (typeof window !== "undefined") {
  setInterval(() => { tick += 1; }, 30_000);
}

/** Subscribe the caller to the shared clock. Exported for anything that formats a
 *  time itself (e.g. Intl) and needs the same self-updating behaviour. */
export function clockTick() {
  return tick;
}

// The app's language drives the wording, not the OS: Czech gets "před 3 hodinami",
// English keeps exactly what it always said ("3 hours ago"). Formatters are cached.
const _rtf = {};
function rtf(loc) {
  return (_rtf[loc] ||= new Intl.RelativeTimeFormat(loc, { numeric: "always" }));
}
const _cs = () => currentLocale() === "cs";

/** The locale to format a shown date or time in: a Czech UI always gets Czech;
 *  English keeps the system's own date and time conventions (as it always did).
 *  Reactive, like currentLocale() - templates re-render on a language switch. */
export function dateLocale() {
  return _cs() ? "cs" : [];
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
  const momentary = () => (_cs() ? (future ? "za okamžik" : "právě teď") : (future ? "in a moment" : "just now"));
  if (s < 45) return momentary();
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800],
                 ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, secs] of units) {
    const v = Math.floor(s / secs);
    if (v >= 1) return rtf(_cs() ? "cs" : "en").format(future ? v : -v, name);
  }
  return momentary();
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
  // English keeps the OS's date/time format (as before); Czech always gets Czech.
  const cs = _cs();
  const loc = dateLocale();
  if (min < 1) return cs ? "teď" : "now";
  if (min < 60) return cs ? `${Math.floor(min)} min` : `${Math.floor(min)}m`;
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString(loc, { hour: "numeric", minute: "2-digit" });
  }
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return cs ? "Včera" : "Yesterday";
  if (ms < 7 * 86400000) return d.toLocaleDateString(loc, { weekday: "short" });
  if (d.getFullYear() === now.getFullYear()) return d.toLocaleDateString(loc, { month: "short", day: "numeric" });
  return d.toLocaleDateString(loc, { month: "short", day: "numeric", year: "2-digit" });
}

/** An hour of the day for a picker: "9:00 AM" in English, "9:00" (24-hour) in Czech. */
export function hourLabel(h) {
  return currentLocale() === "cs" ? `${h}:00` : `${h % 12 || 12}:00 ${h < 12 ? "AM" : "PM"}`;
}
