<script>
  // Upload a sound file and cut a short clip out of it for a notification. The
  // whole file is decoded in-memory; the user drags a selection window over the
  // waveform, previews it, and saves - we trim to a small WAV and store it (as a
  // base64 data URL) in settings.customSounds via the store. No files on disk.
  import { fly, fade } from "svelte/transition";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { getAudioContext, playBuffer, sliceBuffer, bufferToWavDataUrl } from "../sound.js";
  import { t } from "../i18n.svelte.js";
  import { icons } from "../icons.js";

  let { onclose } = $props();

  let fileName = $state("");
  let buffer = $state(null);      // decoded AudioBuffer
  let duration = $state(0);
  let start = $state(0);          // clip start (seconds)
  let clipLen = $state(3);        // clip length (seconds)
  let name = $state("");
  let busy = $state(false);
  let canvasEl = $state(null);

  const MAX_LEN = 6;
  const maxStart = $derived(Math.max(0, duration - Math.min(clipLen, duration)));

  async function onFile(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    busy = true;
    try {
      const ac = getAudioContext();
      if (!ac) throw new Error("no audio");
      const arr = await file.arrayBuffer();
      buffer = await ac.decodeAudioData(arr);
      duration = buffer.duration;
      start = 0;
      clipLen = Math.min(3, duration);
      fileName = file.name;
      if (!name) name = file.name.replace(/\.[^.]+$/, "").slice(0, 40);
      queueMicrotask(drawWave);
    } catch {
      notify(t("sound.decodeFailed"), "error");
    } finally { busy = false; }
  }

  function drawWave() {
    const c = canvasEl;
    if (!c || !buffer) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr; c.height = h * dpr;
    const ctx2 = c.getContext("2d");
    ctx2.scale(dpr, dpr);
    ctx2.clearRect(0, 0, w, h);
    const data = buffer.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / w));
    const mid = h / 2;
    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue("--muted") || "#888";
    const accent = css.getPropertyValue("--accent") || "#5e8bff";
    // Selection band.
    const x0 = duration ? (start / duration) * w : 0;
    const x1 = duration ? ((start + Math.min(clipLen, duration - start)) / duration) * w : w;
    ctx2.fillStyle = css.getPropertyValue("--accent-soft") || "rgba(94,139,255,0.2)";
    ctx2.fillRect(x0, 0, Math.max(2, x1 - x0), h);
    // Waveform bars.
    for (let i = 0; i < w; i++) {
      let peak = 0;
      const s = i * step;
      for (let j = 0; j < step; j++) { const v = Math.abs(data[s + j] || 0); if (v > peak) peak = v; }
      const bar = Math.max(1, peak * (h * 0.9));
      const inSel = i >= x0 && i <= x1;
      ctx2.fillStyle = inSel ? accent.trim() : muted.trim();
      ctx2.globalAlpha = inSel ? 0.95 : 0.4;
      ctx2.fillRect(i, mid - bar / 2, 1, bar);
    }
    ctx2.globalAlpha = 1;
  }

  $effect(() => { start; clipLen; duration; if (buffer) drawWave(); });

  function preview() {
    if (!buffer) return;
    const ac = getAudioContext();
    playBuffer(ac, sliceBuffer(ac, buffer, start, Math.min(clipLen, duration - start)), (app.settings.notifyVolume ?? 80) / 100);
  }

  function save() {
    if (!buffer || !name.trim()) return;
    const ac = getAudioContext();
    const clip = sliceBuffer(ac, buffer, start, Math.min(clipLen, duration - start));
    const data = bufferToWavDataUrl(clip);
    const id = (crypto.randomUUID?.() || String(start) + name).replace(/[^a-z0-9]/gi, "").slice(0, 16);
    const list = [...(app.settings.customSounds || []), { id, name: name.trim(), data }];
    saveSettings({ customSounds: list });
    notify(t("sound.saved", { name: name.trim() }));
    onclose?.(`custom:${id}`);
  }

  const fmt = (s) => `${s.toFixed(1)}s`;
</script>

<div class="scrim" transition:fade={{ duration: 120 }} onclick={() => onclose?.()}>
  <div class="studio" transition:fly={{ y: 14, duration: 160 }} onclick={(e) => e.stopPropagation()}>
    <header>
      <h3>{@html icons.bolt || ""} {t("sound.studioTitle")}</h3>
      <button class="x" onclick={() => onclose?.()}>{@html icons.close}</button>
    </header>

    {#if !buffer}
      <label class="drop">
        <input type="file" accept="audio/*" onchange={onFile} hidden />
        <div class="dropinner">
          {@html icons.upload || icons.sent}
          <b>{busy ? t("sound.decoding") : t("sound.pickFile")}</b>
          <span>{t("sound.pickHint")}</span>
        </div>
      </label>
    {:else}
      <p class="fname">{fileName} · {fmt(duration)}</p>
      <canvas bind:this={canvasEl} class="wave"></canvas>
      <label class="rng">
        <span>{t("sound.start")}</span>
        <input type="range" min="0" max={maxStart} step="0.05" bind:value={start} />
        <span class="v">{fmt(start)}</span>
      </label>
      <label class="rng">
        <span>{t("sound.length")}</span>
        <input type="range" min="0.5" max={Math.min(MAX_LEN, duration)} step="0.1" bind:value={clipLen} />
        <span class="v">{fmt(Math.min(clipLen, duration - start))}</span>
      </label>
      <label class="nm">
        <span>{t("sound.name")}</span>
        <input type="text" bind:value={name} maxlength="40" placeholder={t("sound.namePlaceholder")} />
      </label>
      <div class="acts">
        <button class="btn ghost" onclick={preview}>▶ {t("sound.preview")}</button>
        <div class="sp"></div>
        <button class="btn" onclick={() => { buffer = null; fileName = ""; }}>{t("sound.chooseAnother")}</button>
        <button class="btn primary" disabled={!name.trim()} onclick={save}>{t("sound.save")}</button>
      </div>
    {/if}
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; background: rgba(0,0,0,0.45); backdrop-filter: blur(2px); z-index: 300; display: flex; align-items: center; justify-content: center; padding: 24px; }
  .studio { width: min(520px, 96vw); background: var(--surface); border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); padding: 18px 20px 20px; }
  header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  header h3 { margin: 0; display: flex; align-items: center; gap: 8px; }
  header :global(svg) { width: 16px; height: 16px; }
  .x { color: var(--muted); padding: 4px; border-radius: 6px; }
  .x:hover { background: var(--hover); color: var(--text); }
  .drop { display: block; border: 2px dashed var(--border); border-radius: var(--radius); cursor: pointer; transition: border-color var(--t-fast) var(--ease); }
  .drop:hover { border-color: var(--accent); }
  .dropinner { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 34px 20px; text-align: center; }
  .dropinner :global(svg) { width: 26px; height: 26px; color: var(--accent); }
  .dropinner span { color: var(--muted); font-size: 12px; }
  .fname { color: var(--muted); font-size: 12px; margin: 0 0 8px; }
  .wave { width: 100%; height: 84px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); display: block; }
  .rng { display: flex; align-items: center; gap: 10px; margin-top: 12px; font-size: 13px; }
  .rng > span:first-child { width: 60px; color: var(--muted); flex: none; }
  .rng input[type=range] { flex: 1; accent-color: var(--accent); }
  .rng .v { width: 46px; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  .nm { display: flex; align-items: center; gap: 10px; margin-top: 12px; font-size: 13px; }
  .nm > span { width: 60px; color: var(--muted); flex: none; }
  .nm input { flex: 1; }
  .acts { display: flex; align-items: center; gap: 8px; margin-top: 18px; }
  .acts .sp { flex: 1; }
</style>
