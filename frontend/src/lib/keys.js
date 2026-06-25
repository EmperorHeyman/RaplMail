// Keyboard-combo helpers so shortcuts can be any single key OR a modifier combo
// (e.g. "ArrowDown", "Ctrl+n", "Ctrl+Shift+k", "?").

export function keyCombo(e) {
  const k = e.key;
  if (["Control", "Shift", "Alt", "Meta"].includes(k)) return ""; // modifier alone
  let key = k.length === 1 ? k.toLowerCase() : k;
  if (k === " ") key = "Space";
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey && (e.ctrlKey || e.metaKey || e.altKey)) parts.push("Shift");
  parts.push(key);
  return parts.join("+");
}

const SYM = { ArrowDown: "↓", ArrowUp: "↑", ArrowLeft: "←", ArrowRight: "→", Enter: "↵", Escape: "Esc" };
export function comboLabel(combo) {
  if (!combo) return "—";
  return combo.split("+").map((p) => SYM[p] || (p.length === 1 ? p.toUpperCase() : p)).join("+");
}
