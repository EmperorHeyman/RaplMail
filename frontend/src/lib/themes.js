// Built-in theme presets (accent-led overrides of the CSS color tokens; any
// token left out falls back to the default dark palette). Shared by the
// Appearance settings and the first-run onboarding wizard so there's one source
// of truth for "the themes we ship".
import { LIGHT_THEME } from "./store.svelte.js";

export const PRESETS = [
  { name: "Dark", theme: {} },
  { name: "Light", theme: LIGHT_THEME },
  { name: "Indigo", theme: { "--accent": "#8b5cf6", "--bg": "#0f0d18", "--surface": "#171425", "--surface-2": "#1f1b30", "--surface-3": "#2a2542" } },
  { name: "Emerald", theme: { "--accent": "#2bd4a0", "--bg": "#0b1310", "--surface": "#101a15", "--surface-2": "#16241d" } },
  { name: "Sunset", theme: { "--accent": "#ff7a59", "--warning": "#ffb02e" } },
  { name: "Rose", theme: { "--accent": "#ff5d8f" } },
  { name: "Slate", theme: { "--accent": "#9aa6bf", "--bg": "#101216", "--surface": "#191c22" } },
  // Editor themes — for those who like their mail like their VSCode.
  { name: "One Dark", theme: { "--bg": "#282c34", "--surface": "#21252b", "--surface-2": "#2c313a", "--surface-3": "#3a3f4b", "--border": "#3a3f4b", "--text": "#abb2bf", "--muted": "#7f848e", "--accent": "#61afef", "--done": "#98c379", "--danger": "#e06c75", "--warning": "#e5c07b" } },
  { name: "Dracula", theme: { "--bg": "#282a36", "--surface": "#21222c", "--surface-2": "#343746", "--surface-3": "#44475a", "--border": "#44475a", "--text": "#f8f8f2", "--muted": "#9aa0c0", "--accent": "#bd93f9", "--done": "#50fa7b", "--danger": "#ff5555", "--warning": "#f1fa8c" } },
  { name: "Monokai", theme: { "--bg": "#272822", "--surface": "#1f201b", "--surface-2": "#34352c", "--surface-3": "#49483e", "--border": "#3e3d32", "--text": "#f8f8f2", "--muted": "#a59f85", "--accent": "#a6e22e", "--done": "#a6e22e", "--danger": "#f92672", "--warning": "#e6db74" } },
  { name: "Nord", theme: { "--bg": "#2e3440", "--surface": "#2b303b", "--surface-2": "#3b4252", "--surface-3": "#434c5e", "--border": "#3b4252", "--text": "#eceff4", "--muted": "#aebacf", "--accent": "#88c0d0", "--done": "#a3be8c", "--danger": "#bf616a", "--warning": "#ebcb8b" } },
  { name: "Gruvbox", theme: { "--bg": "#282828", "--surface": "#1d2021", "--surface-2": "#32302f", "--surface-3": "#3c3836", "--border": "#3c3836", "--text": "#ebdbb2", "--muted": "#a89984", "--accent": "#fabd2f", "--done": "#b8bb26", "--danger": "#fb4934", "--warning": "#fe8019" } },
  { name: "Solarized", theme: { "--bg": "#002b36", "--surface": "#073642", "--surface-2": "#0a4453", "--surface-3": "#0d5263", "--border": "#094352", "--text": "#93a1a1", "--muted": "#6a8186", "--accent": "#268bd2", "--done": "#859900", "--danger": "#dc322f", "--warning": "#b58900" } },
  { name: "Tokyo Night", theme: { "--bg": "#1a1b26", "--surface": "#16161e", "--surface-2": "#24283b", "--surface-3": "#2f334d", "--border": "#292e42", "--text": "#c0caf5", "--muted": "#7f88b3", "--accent": "#7aa2f7", "--done": "#9ece6a", "--danger": "#f7768e", "--warning": "#e0af68" } },
  { name: "GitHub Dark", theme: { "--bg": "#0d1117", "--surface": "#161b22", "--surface-2": "#21262d", "--surface-3": "#30363d", "--border": "#30363d", "--text": "#c9d1d9", "--muted": "#8b949e", "--accent": "#58a6ff", "--done": "#3fb950", "--danger": "#f85149", "--warning": "#d29922" } },
];

// A curated shortlist shown in onboarding (kept small so the step stays calm).
export const ONBOARDING_PRESETS = ["Dark", "Light", "Indigo", "Emerald", "Sunset", "Tokyo Night"]
  .map((n) => PRESETS.find((p) => p.name === n))
  .filter(Boolean);
