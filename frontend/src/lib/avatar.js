// Stable per-sender avatar color + initial, so the same person always gets the
// same colored disc - the list (and thread) read at a glance instead of a wall
// of identical accent circles. Simple deterministic string hash → hue.
export function senderHue(s) {
  const str = (s || "").toLowerCase();
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return h;
}
// ~45% lightness / 55% saturation reads well under white text in both light and
// dark themes.
export function avatarColor(s) { return `hsl(${senderHue(s)} 55% 45%)`; }
export function initialOf(s) { return ((s || "?").trim()[0] || "?").toUpperCase(); }
