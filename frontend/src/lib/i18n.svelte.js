// Lightweight, dependency-free i18n for the Tauri-bundled app.
//
// Why not a library: this is an offline desktop app behind a strict CSP; every
// catalog must ship in-bundle regardless, and the app already has a clean
// reactive settings model. A tiny `t()` reading a module-level $state gives us
// live language switching (no reload, no network) for free - a component that
// calls t() in its markup re-runs automatically when the locale changes.
//
// The dictionaries are flat { "some.key": "text" } maps. Missing keys fall back
// to English, then to the key itself, so a partially-translated screen degrades
// gracefully rather than showing blanks.
import en from "./locales/en.js";
import cs from "./locales/cs.js";

const DICTS = { en, cs };

export const LANGUAGES = [
  { id: "auto", label: "Auto (system)" },
  { id: "en", label: "English" },
  { id: "cs", label: "Čeština" },
];

// Resolve "auto" against the OS language (Czech/Slovak → cs, else English).
function detect() {
  try {
    const n = (navigator.language || navigator.userLanguage || "en").toLowerCase();
    return n.startsWith("cs") || n.startsWith("sk") ? "cs" : "en";
  } catch {
    return "en";
  }
}

function resolve(pref) {
  const l = !pref || pref === "auto" ? detect() : pref;
  return DICTS[l] ? l : "en";
}

// Seed synchronously from the persisted setting so the first paint is already in
// the right language (no English flash before initSettings() resolves).
function _seed() {
  try {
    const s = JSON.parse(localStorage.getItem("raplmail.settings") || "{}");
    return resolve(s.language);
  } catch {
    return "en";
  }
}

let _locale = $state(_seed());

/** Switch the active UI language. `pref` is "auto" | "en" | "cs". */
export function setLocale(pref) {
  _locale = resolve(pref);
  if (typeof document !== "undefined") document.documentElement.lang = _locale;
}

/** The resolved locale code ("en" | "cs"). Reactive - read it to subscribe. */
export function currentLocale() {
  return _locale;
}

/**
 * Translate `key`, interpolating {name} placeholders from `params`.
 * Falls back English → key. Reads the reactive locale, so any markup using
 * t() re-renders when the language changes.
 */
export function t(key, params) {
  const dict = DICTS[_locale] || en;
  let s = dict[key];
  if (s == null) s = en[key];
  if (s == null) s = key;
  if (params) {
    for (const k in params) s = s.split(`{${k}}`).join(String(params[k]));
  }
  return s;
}
