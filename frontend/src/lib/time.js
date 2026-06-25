// Full relative phrasing, e.g. "3 hours ago" / "in 2 days".
export function relativeTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  let s = Math.round((new Date() - d) / 1000);
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
  if (!iso) return "";
  const d = new Date(iso);
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
