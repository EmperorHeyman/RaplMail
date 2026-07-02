// New-mail notification sounds, synthesized with the Web Audio API so there are
// no bundled audio files (works offline and inside the sandboxed desktop
// webview, where <audio src> and remote fetches are blocked).

let _ctx = null;
function ctx() {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!_ctx) _ctx = new AC();
  // Autoplay policy: the context may start suspended until a user gesture.
  if (_ctx.state === "suspended") _ctx.resume().catch(() => {});
  return _ctx;
}

// One tone: frequency ramp + a quick attack / exponential decay envelope.
function tone(ac, { freq, type = "sine", start = 0, dur = 0.3, gain = 0.18, glideTo = null }) {
  const t0 = ac.currentTime + start;
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012);           // fast attack
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);           // decay
  osc.connect(g).connect(ac.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.02);
}

// Each sound = a small recipe of tones. Tuned to be pleasant, short, and quiet.
const SOUNDS = {
  ding(ac)   { tone(ac, { freq: 880, type: "sine", dur: 0.5, gain: 0.2 }); },
  chime(ac)  { tone(ac, { freq: 587.33, dur: 0.45, gain: 0.16 });          // D5
               tone(ac, { freq: 880, start: 0.10, dur: 0.55, gain: 0.16 }); }, // A5
  marimba(ac){ tone(ac, { freq: 659.25, type: "triangle", dur: 0.28, gain: 0.22 });   // E5
               tone(ac, { freq: 987.77, type: "triangle", start: 0.13, dur: 0.34, gain: 0.18 }); }, // B5
  pop(ac)    { tone(ac, { freq: 420, type: "sine", dur: 0.16, gain: 0.22, glideTo: 720 }); },
  glass(ac)  { tone(ac, { freq: 1174.66, type: "sine", dur: 0.6, gain: 0.13 });        // D6
               tone(ac, { freq: 1567.98, type: "sine", start: 0.02, dur: 0.5, gain: 0.09 }); }, // G6
};

export const SOUND_OPTIONS = [
  { id: "none", label: "None" },
  { id: "ding", label: "Ding" },
  { id: "chime", label: "Chime" },
  { id: "marimba", label: "Marimba" },
  { id: "pop", label: "Pop" },
  { id: "glass", label: "Glass" },
];

/** Play a named notification sound. No-op for "none"/unknown or if audio is unavailable. */
export function playSound(name) {
  if (!name || name === "none") return;
  const recipe = SOUNDS[name];
  if (!recipe) return;
  const ac = ctx();
  if (!ac) return;
  try { recipe(ac); } catch {}
}
