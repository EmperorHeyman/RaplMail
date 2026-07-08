// Built-in theme presets. Each preset overrides the core CSS color tokens (see
// THEME_TOKENS); anything left out falls back to the default dark palette. All
// the derived tones (--faint, --hairline, --accent-soft, --hover, …) are
// color-mixed off these in app.css, so a full palette propagates everywhere -
// that's why the neutral/true-black presets below set the whole grey ramp, not
// just the accent (setting only --accent leaves the bluish default background,
// which is exactly why "everything looked blue").
//
// `category` groups them in Settings → Appearance and keeps one source of truth
// shared with the first-run onboarding wizard.
import { LIGHT_THEME } from "./store.svelte.js";

export const PRESETS = [
  // ── Essentials ────────────────────────────────────────────────────────────
  { name: "Dark", category: "Essentials", theme: {} },
  { name: "Light", category: "Essentials", theme: LIGHT_THEME },

  // ── High contrast - pure black / pure white, strong separation ─────────────
  // True black (great for OLED): neutral greys, no blue tint.
  { name: "True Black", category: "High contrast", theme: { "--bg": "#000000", "--surface": "#0a0a0a", "--surface-2": "#141414", "--surface-3": "#1f1f1f", "--border": "#2b2b2b", "--text": "#f5f5f5", "--muted": "#a3a3a3", "--accent": "#4f8cff", "--done": "#34d399", "--danger": "#f26d79", "--warning": "#f5b83d" } },
  // Maximum legibility: black bg, pure-white text, brighter muted + stronger borders.
  { name: "Contrast Dark", category: "High contrast", theme: { "--bg": "#000000", "--surface": "#0d0d0d", "--surface-2": "#171717", "--surface-3": "#232323", "--border": "#454545", "--text": "#ffffff", "--muted": "#c8c8c8", "--accent": "#74a7ff", "--done": "#3ee6a0", "--danger": "#ff6b78", "--warning": "#ffc93c" } },
  // Maximum legibility, light: white bg, black text, strong borders, deep accents.
  { name: "Contrast Light", category: "High contrast", theme: { "--bg": "#ffffff", "--surface": "#ffffff", "--surface-2": "#f0f0f0", "--surface-3": "#e4e4e4", "--border": "#a8a8a8", "--text": "#000000", "--muted": "#333333", "--accent": "#0b48c9", "--done": "#077a4c", "--danger": "#bd1a29", "--warning": "#7a5200" } },
  // Warm off-white - easy on the eyes for long reading.
  { name: "Paper", category: "High contrast", theme: { "--bg": "#f6f1e7", "--surface": "#fffcf5", "--surface-2": "#efe8d8", "--surface-3": "#e6ddc9", "--border": "#d9cfb6", "--text": "#2c2519", "--muted": "#6e6350", "--accent": "#a65d2e", "--done": "#4e7a3f", "--danger": "#b23a48", "--warning": "#9a6a12" } },
  // Cool, crisp light.
  { name: "Snow", category: "High contrast", theme: { "--bg": "#eef2f8", "--surface": "#ffffff", "--surface-2": "#e4ebf4", "--surface-3": "#d6e0ee", "--border": "#c7d4e4", "--text": "#0e1a2b", "--muted": "#51617a", "--accent": "#2f7ad6", "--done": "#128a5f", "--danger": "#d1435a", "--warning": "#a06f04" } },

  // ── Neutral - true greys, zero blue tint ───────────────────────────────────
  { name: "Carbon", category: "Neutral", theme: { "--bg": "#0e0e0e", "--surface": "#161616", "--surface-2": "#1e1e1e", "--surface-3": "#292929", "--border": "#343434", "--text": "#eaeaea", "--muted": "#9a9a9a", "--accent": "#6ea8fe", "--done": "#34d399", "--danger": "#f26d79", "--warning": "#f5b83d" } },
  { name: "Graphite", category: "Neutral", theme: { "--bg": "#17181a", "--surface": "#202124", "--surface-2": "#292a2e", "--surface-3": "#34363b", "--border": "#3b3d42", "--text": "#e7e8ea", "--muted": "#9a9da4", "--accent": "#8ab4f8", "--done": "#34d399", "--danger": "#f26d79", "--warning": "#f5b83d" } },
  // Grayscale UI, colors only kept lightly for status legibility.
  { name: "Mono", category: "Neutral", theme: { "--bg": "#101010", "--surface": "#191919", "--surface-2": "#222222", "--surface-3": "#2d2d2d", "--border": "#383838", "--text": "#ededed", "--muted": "#9b9b9b", "--accent": "#c9c9c9", "--done": "#8fb89a", "--danger": "#cf8b90", "--warning": "#cbb079" } },
  // Warm, cozy dark for reading.
  { name: "Sepia", category: "Neutral", theme: { "--bg": "#211b13", "--surface": "#2a2318", "--surface-2": "#342b1d", "--surface-3": "#3f3423", "--border": "#453923", "--text": "#ece0cf", "--muted": "#b3a486", "--accent": "#d8a657", "--done": "#a9b665", "--danger": "#ea6962", "--warning": "#e78a4e" } },

  // ── Color - a distinct hue, full palette so it isn't a blue base + tint ─────
  { name: "Indigo", category: "Color", theme: { "--accent": "#8b5cf6", "--bg": "#0f0d18", "--surface": "#171425", "--surface-2": "#1f1b30", "--surface-3": "#2a2542" } },
  { name: "Emerald", category: "Color", theme: { "--accent": "#2bd4a0", "--bg": "#0b1310", "--surface": "#101a15", "--surface-2": "#16241d" } },
  { name: "Ocean", category: "Color", theme: { "--bg": "#071417", "--surface": "#0c1e22", "--surface-2": "#12292f", "--surface-3": "#1a373f", "--border": "#1e3d45", "--text": "#dbf1f5", "--muted": "#7ba7b0", "--accent": "#22d3ee", "--done": "#34d399", "--danger": "#f2717f", "--warning": "#f5b83d" } },
  { name: "Amethyst", category: "Color", theme: { "--bg": "#120e1a", "--surface": "#1a1425", "--surface-2": "#241b33", "--surface-3": "#2f2442", "--border": "#352a49", "--text": "#ece6f5", "--muted": "#a99cc0", "--accent": "#c084fc", "--done": "#34d399", "--danger": "#f26d79", "--warning": "#f5b83d" } },
  { name: "Crimson", category: "Color", theme: { "--bg": "#130f11", "--surface": "#1b1518", "--surface-2": "#241b1f", "--surface-3": "#302329", "--border": "#35272c", "--text": "#f3e9ec", "--muted": "#b39ba3", "--accent": "#ff4d6d", "--done": "#34d399", "--danger": "#ff6b78", "--warning": "#f5b83d" } },
  { name: "Sunset", category: "Color", theme: { "--accent": "#ff7a59", "--warning": "#ffb02e" } },
  { name: "Rose", category: "Color", theme: { "--accent": "#ff5d8f" } },
  { name: "Slate", category: "Color", theme: { "--accent": "#9aa6bf", "--bg": "#101216", "--surface": "#191c22" } },

  // ── Editor - for those who like their mail like their VSCode ───────────────
  { name: "One Dark", category: "Editor", theme: { "--bg": "#282c34", "--surface": "#21252b", "--surface-2": "#2c313a", "--surface-3": "#3a3f4b", "--border": "#3a3f4b", "--text": "#abb2bf", "--muted": "#7f848e", "--accent": "#61afef", "--done": "#98c379", "--danger": "#e06c75", "--warning": "#e5c07b" } },
  { name: "Dracula", category: "Editor", theme: { "--bg": "#282a36", "--surface": "#21222c", "--surface-2": "#343746", "--surface-3": "#44475a", "--border": "#44475a", "--text": "#f8f8f2", "--muted": "#9aa0c0", "--accent": "#bd93f9", "--done": "#50fa7b", "--danger": "#ff5555", "--warning": "#f1fa8c" } },
  { name: "Monokai", category: "Editor", theme: { "--bg": "#272822", "--surface": "#1f201b", "--surface-2": "#34352c", "--surface-3": "#49483e", "--border": "#3e3d32", "--text": "#f8f8f2", "--muted": "#a59f85", "--accent": "#a6e22e", "--done": "#a6e22e", "--danger": "#f92672", "--warning": "#e6db74" } },
  { name: "Nord", category: "Editor", theme: { "--bg": "#2e3440", "--surface": "#2b303b", "--surface-2": "#3b4252", "--surface-3": "#434c5e", "--border": "#3b4252", "--text": "#eceff4", "--muted": "#aebacf", "--accent": "#88c0d0", "--done": "#a3be8c", "--danger": "#bf616a", "--warning": "#ebcb8b" } },
  { name: "Gruvbox", category: "Editor", theme: { "--bg": "#282828", "--surface": "#1d2021", "--surface-2": "#32302f", "--surface-3": "#3c3836", "--border": "#3c3836", "--text": "#ebdbb2", "--muted": "#a89984", "--accent": "#fabd2f", "--done": "#b8bb26", "--danger": "#fb4934", "--warning": "#fe8019" } },
  { name: "Solarized", category: "Editor", theme: { "--bg": "#002b36", "--surface": "#073642", "--surface-2": "#0a4453", "--surface-3": "#0d5263", "--border": "#094352", "--text": "#93a1a1", "--muted": "#6a8186", "--accent": "#268bd2", "--done": "#859900", "--danger": "#dc322f", "--warning": "#b58900" } },
  { name: "Tokyo Night", category: "Editor", theme: { "--bg": "#1a1b26", "--surface": "#16161e", "--surface-2": "#24283b", "--surface-3": "#2f334d", "--border": "#292e42", "--text": "#c0caf5", "--muted": "#7f88b3", "--accent": "#7aa2f7", "--done": "#9ece6a", "--danger": "#f7768e", "--warning": "#e0af68" } },
  { name: "GitHub Dark", category: "Editor", theme: { "--bg": "#0d1117", "--surface": "#161b22", "--surface-2": "#21262d", "--surface-3": "#30363d", "--border": "#30363d", "--text": "#c9d1d9", "--muted": "#8b949e", "--accent": "#58a6ff", "--done": "#3fb950", "--danger": "#f85149", "--warning": "#d29922" } },
];

// The order categories appear in Settings → Appearance.
export const PRESET_CATEGORIES = ["Essentials", "High contrast", "Neutral", "Color", "Editor"];

// A curated shortlist shown in onboarding (kept small so the step stays calm).
export const ONBOARDING_PRESETS = ["Dark", "Light", "True Black", "Indigo", "Emerald", "Tokyo Night"]
  .map((n) => PRESETS.find((p) => p.name === n))
  .filter(Boolean);
