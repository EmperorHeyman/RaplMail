// Material You colour: the whole UI palette from ONE seed colour (the user's
// pick, or the Windows accent - Android's "wallpaper colours").
//
// Tones follow Material 3: a tone is CIE L* (0 = black, 100 = white), and every
// role sits on a fixed tone (primary 80 in dark / 40 in light, containers 30 /
// 90, ...). Hue and chroma come from the seed, worked in OKLCH so a blue seed
// and a yellow one land equally bright at the same tone. Output is plain hex:
// colour inputs, the email renderer and canvas code all read these tokens.
//
// Kept calm on purpose: neutrals carry only a whisper of the seed's hue, and
// real colour is saved for what means something (selection, Compose, unread).

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/** hex "#rgb" / "#rrggbb" -> [r, g, b] in 0..1, or null. */
function parseHex(hex) {
  let h = String(hex || "").trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-f]{6}$/i.test(h)) return null;
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
}

const toLinear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const fromLinear = (v) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);

/** sRGB hex -> { L, C, H } in OKLCH (H in degrees). */
export function hexToOklch(hex) {
  const rgb = parseHex(hex);
  if (!rgb) return null;
  const [r, g, b] = rgb.map(toLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { L, C: Math.hypot(A, B), H: ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360 };
}

function oklchToLinear(L, C, H) {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}
const inGamut = (rgb) => rgb.every((v) => v >= -1e-5 && v <= 1 + 1e-5);

/** OKLCH -> hex. Out-of-gamut colours keep their lightness and hue and give up
 *  chroma (binary search), which is how CSS gamut-maps too. */
function oklchToHex(L, C, H) {
  let rgb = oklchToLinear(L, C, H);
  if (!inGamut(rgb)) {
    let lo = 0, hi = C;
    for (let i = 0; i < 18; i++) {
      const mid = (lo + hi) / 2;
      if (inGamut(oklchToLinear(L, mid, H))) lo = mid; else hi = mid;
    }
    rgb = oklchToLinear(L, lo, H);
  }
  return "#" + rgb.map((v) => Math.round(clamp(fromLinear(clamp(v, 0, 1)), 0, 1) * 255).toString(16).padStart(2, "0")).join("");
}

// Material tone (= CIE L*) -> OKLab L. For greys OKLab L is the cube root of
// luminance, and L* is defined from that same cube root, so this is exact on
// the neutral axis.
const toneL = (t) => (t > 8 ? (t + 16) / 116 : Math.cbrt(t / 903.3));
// Very dark and very light tones can't hold much colour - taper chroma there
// so the ends of a ramp stay clean instead of muddy or neon.
const taper = (t) => clamp(Math.min(t / 22, (100 - t) / 14), 0, 1);

/** Tone ramps for a seed: P(rimary), S(econdary), T(ertiary), N(eutral),
 *  NV (neutral variant), each a function tone -> hex. */
export function tonalRamps(seed) {
  const o = hexToOklch(seed) || hexToOklch("#5e8bff");
  // A grey or black seed (a black Windows accent is common) has no hue to speak
  // of - atan2 of ~0 would invent a red. Build a neutral scheme instead.
  const mono = o.C < 0.035;
  const H = o.H;
  const pc = mono ? 0 : clamp(o.C, 0.09, 0.14);
  const ramp = (c, dh = 0) => (t) => oklchToHex(toneL(t), c * taper(t), (H + dh + 360) % 360);
  return {
    mono,
    P: ramp(pc),
    S: ramp(mono ? 0 : 0.045),
    T: ramp(mono ? 0 : 0.09, 60),
    N: ramp(mono ? 0 : 0.012),
    NV: ramp(mono ? 0 : 0.022),
  };
}

/**
 * The full set of CSS tokens for a seed. Covers the classic tokens every
 * component already reads (--bg, --surface, --accent, ...) plus the Material
 * roles the redesign adds (--on-accent, --sel, --accent-cont, ...).
 *
 * Mapping, dark: the window ground (nav + list) is tone 6, the reading pane
 * and cards tone 12, fields 17, raised/selected 22 - Material's surface /
 * container / container-high / -highest.
 */
export function materialTokens(seed, { dark = true, black = false } = {}) {
  const { P, S, T, N, NV } = tonalRamps(seed);
  if (dark) {
    return {
      "--app-bg": black ? "#000000" : N(6),
      "--bg": black ? "#000000" : N(6),
      "--surface": black ? N(8) : N(12),
      "--surface-2": black ? N(13) : N(17),
      "--surface-3": black ? N(18) : N(22),
      "--border": NV(32),
      "--outline": NV(60),
      "--text": N(90),
      "--muted": NV(80),
      "--accent": P(80),
      "--on-accent": P(20),
      "--accent-cont": P(30),
      "--on-accent-cont": P(90),
      "--sel": black ? S(24) : S(30),
      "--on-sel": S(90),
      "--tert": T(80),
      "--tert-cont": T(30),
      "--on-tert-cont": T(90),
      "--done": "#5fd4a0",
      "--on-done": "#003822",
      "--danger": "#f2727f",
      "--warning": "#f5b83d",
    };
  }
  return {
    "--app-bg": N(95),
    "--bg": N(95),
    "--surface": "#ffffff",
    "--surface-2": N(92),
    "--surface-3": N(88),
    "--border": NV(82),
    "--outline": NV(50),
    "--text": N(10),
    "--muted": NV(30),
    "--accent": P(40),
    "--on-accent": P(100),
    "--accent-cont": P(90),
    "--on-accent-cont": P(10),
    "--sel": S(88),
    "--on-sel": S(10),
    "--tert": T(40),
    "--tert-cont": T(90),
    "--on-tert-cont": T(10),
    "--done": "#16855a",
    "--on-done": "#ffffff",
    "--danger": "#ba1a1a",
    "--warning": "#8a5a00",
  };
}

/** Swatch colours for a seed picker tile: the primary, secondary and tertiary
 *  a scheme from that seed would use (Pixel's split circles). */
export function seedSwatch(seed, dark = true) {
  const { P, S, T } = tonalRamps(seed);
  return dark ? { p: P(80), s: S(40), t: T(60) } : { p: P(40), s: S(80), t: T(70) };
}

/** Is a hex colour light (for picking a light vs dark scheme from a theme)? */
export function isLightHex(hex) {
  const o = hexToOklch(hex);
  return !!o && o.L > 0.6;
}
