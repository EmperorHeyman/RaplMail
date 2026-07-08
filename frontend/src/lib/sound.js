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
/** Shared AudioContext, exposed so the sound editor decodes/previews on the same
 *  context the notifications play through. */
export function getAudioContext() { return ctx(); }

// Master volume multiplier (0..1), applied to every tone's peak gain. Set by
// playSound() from the user's notifyVolume setting just before a recipe runs.
let _vol = 1;

// One tone: frequency ramp + a quick attack / exponential decay envelope.
function tone(ac, { freq, type = "sine", start = 0, dur = 0.3, gain = 0.18, glideTo = null }) {
  const t0 = ac.currentTime + start;
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  // exponentialRampToValueAtTime can't hit 0, so floor the scaled peak.
  const peak = Math.max(0.0002, gain * _vol);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + 0.012);           // fast attack
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

// --- User-uploaded custom clips --------------------------------------------
// Custom sounds are referenced by the id "custom:<id>" and stored (as base64
// WAV data URLs) in settings. The store pushes the current list here on load /
// change; we decode each clip to an AudioBuffer lazily on first play and cache
// it. No files on disk — everything lives in settings so it syncs + backs up.
let _customData = {};             // id -> data URL
const _customBuffers = {};        // id -> decoded AudioBuffer

export function setCustomSounds(list) {
  const next = {};
  for (const c of list || []) if (c && c.id && c.data) next[c.id] = c.data;
  // Drop decoded buffers whose data changed / was removed.
  for (const id of Object.keys(_customBuffers)) {
    if (_customData[id] !== next[id]) delete _customBuffers[id];
  }
  _customData = next;
}

function dataUrlToArrayBuffer(dataUrl) {
  const b64 = String(dataUrl).split(",")[1] || "";
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

async function playCustom(id, v) {
  const ac = ctx();
  if (!ac) return;
  let buf = _customBuffers[id];
  if (!buf) {
    const data = _customData[id];
    if (!data) return;
    try { buf = await ac.decodeAudioData(dataUrlToArrayBuffer(data)); _customBuffers[id] = buf; }
    catch { return; }
  }
  playBuffer(ac, buf, v);
}

/** Play a decoded AudioBuffer through the shared context at `vol` (0..1). Used
 *  for custom clips and by the sound editor's preview. */
export function playBuffer(ac, buffer, vol = 1) {
  if (!ac || !buffer) return;
  const src = ac.createBufferSource();
  const g = ac.createGain();
  g.gain.value = Math.max(0, Math.min(1, Number(vol)));
  src.buffer = buffer;
  src.connect(g).connect(ac.destination);
  try { src.start(); } catch {}
}

/** Encode an AudioBuffer to a 16-bit PCM WAV data URL (for storing a clip). */
export function bufferToWavDataUrl(buffer) {
  const numCh = buffer.numberOfChannels;
  const len = buffer.length;
  const sr = buffer.sampleRate;
  const bytesPerSample = 2;
  const blockAlign = numCh * bytesPerSample;
  const dataLen = len * blockAlign;
  const buf = new ArrayBuffer(44 + dataLen);
  const view = new DataView(buf);
  const ws = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  ws(0, "RIFF"); view.setUint32(4, 36 + dataLen, true); ws(8, "WAVE");
  ws(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, numCh, true); view.setUint32(24, sr, true);
  view.setUint32(28, sr * blockAlign, true); view.setUint16(32, blockAlign, true);
  view.setUint16(34, 8 * bytesPerSample, true);
  ws(36, "data"); view.setUint32(40, dataLen, true);
  let off = 44;
  const chans = [];
  for (let c = 0; c < numCh; c++) chans.push(buffer.getChannelData(c));
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < numCh; c++) {
      let s = Math.max(-1, Math.min(1, chans[c][i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
  }
  // Assemble a base64 data URL without a Blob/FileReader round-trip.
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return "data:audio/wav;base64," + btoa(bin);
}

/** Slice `lenSec` seconds out of `buffer` starting at `startSec`. */
export function sliceBuffer(ac, buffer, startSec, lenSec) {
  const sr = buffer.sampleRate;
  const start = Math.max(0, Math.floor(startSec * sr));
  const len = Math.max(1, Math.min(Math.floor(lenSec * sr), buffer.length - start));
  const numCh = buffer.numberOfChannels;
  const out = ac.createBuffer(numCh, len, sr);
  for (let c = 0; c < numCh; c++)
    out.getChannelData(c).set(buffer.getChannelData(c).subarray(start, start + len));
  return out;
}

/** Play a named notification sound at `vol` (0..1). Handles built-in synth
 *  recipes and "custom:<id>" clips. No-op for "none"/unknown, vol<=0, or no audio. */
export function playSound(name, vol = 1) {
  if (!name || name === "none") return;
  const v = Math.max(0, Math.min(1, Number(vol)));
  if (v <= 0) return;
  if (String(name).startsWith("custom:")) { playCustom(name.slice(7), v); return; }
  const recipe = SOUNDS[name];
  if (!recipe) return;
  const ac = ctx();
  if (!ac) return;
  _vol = v;
  try { recipe(ac); } catch {}
}
