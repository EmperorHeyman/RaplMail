<script>
  // Standalone calendar-reminder window ("You've got X till …"). Opened by the
  // store's fireReminder() as a separate #reminder WebviewWindow; reads its event
  // from localStorage (same seed pattern as the compose window) and can close
  // itself. Purely presentational - runs no app services.
  import { onMount } from "svelte";
  import { icons } from "./../icons.js";
  import { t } from "./../i18n.svelte.js";

  const SNOOZE = [5, 10, 15];

  let ev = $state(null);
  let now = $state(Date.now());
  let timer;

  onMount(() => {
    try { ev = JSON.parse(localStorage.getItem("raplmail.reminder.seed") || "null"); } catch {}
    timer = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(timer);
  });

  // Live countdown to the event start.
  const left = $derived.by(() => {
    if (!ev?.start) return "";
    const ms = new Date(ev.start).getTime() - now;
    if (ms <= 0) return t("cal.remNow");
    const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
    if (m >= 60) { const h = Math.floor(m / 60); return `${h}h ${m % 60}m`; }
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  });
  const startText = $derived.by(() => {
    if (!ev?.start) return "";
    try { return new Date(ev.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
    catch { return ""; }
  });

  async function closeWin() {
    try { const { getCurrentWindow } = await import("@tauri-apps/api/window"); await getCurrentWindow().close(); }
    catch { window.close(); }
  }

  // This window carries no Tauri capabilities beyond closing itself, so it can't
  // touch the reminder scheduler directly. Queue the action in localStorage; the
  // main window drains it (store: _drainReminderActions, every 3s).
  function post(action, minutes) {
    try {
      const q = JSON.parse(localStorage.getItem("raplmail.reminder.actions") || "[]");
      q.push({ action, minutes, key: ev?.key, nameKey: ev?.nameKey });
      localStorage.setItem("raplmail.reminder.actions", JSON.stringify(q));
    } catch {}
    closeWin();
  }
</script>

<div class="rw">
  <div class="ic">{@html icons.calendar || icons.clock}</div>
  <div class="head">{@html t("cal.remUntil", { left: `<b>${left}</b>` })}</div>
  <div class="title">{ev?.summary || t("cal.remEvent")}</div>
  <div class="meta">
    {#if startText}<span>{@html icons.clock} {startText}</span>{/if}
    {#if ev?.location}<span>{@html icons.pin || icons.folder} {ev.location}</span>{/if}
  </div>
  <div class="snooze">
    <span class="lbl">{t("cal.remSnooze")}</span>
    {#each SNOOZE as m}
      <button class="pill" onclick={() => post("snooze", m)}>{t("cal.remSnoozeMin", { n: m })}</button>
    {/each}
  </div>
  <div class="acts">
    {#if ev?.hasLater}
      <button class="ghost" onclick={() => post("mute")}>{t("cal.remMute")}</button>
    {/if}
    <button class="dismiss" onclick={closeWin}>{t("cal.remDismiss")}</button>
  </div>
</div>

<style>
  :global(body) { background: transparent; }
  .rw {
    height: 100vh; box-sizing: border-box; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 6px; text-align: center;
    padding: 18px 22px; background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 14px;
  }
  .ic { color: var(--accent); margin-bottom: 2px; }
  .ic :global(svg) { width: 26px; height: 26px; }
  .head { font-size: 14px; color: var(--muted); }
  .head b { color: var(--accent); font-size: 16px; }
  .title { font-size: 18px; font-weight: 700; letter-spacing: -0.01em; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { display: flex; gap: 14px; color: var(--muted); font-size: 12px; margin-top: 2px; flex-wrap: wrap; justify-content: center; }
  .meta span { display: inline-flex; align-items: center; gap: 4px; }
  .meta :global(svg) { width: 13px; height: 13px; }
  .snooze { display: flex; align-items: center; gap: 6px; margin-top: 12px; flex-wrap: wrap; justify-content: center; }
  .snooze .lbl { color: var(--muted); font-size: 12px; }
  .pill { padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border); background: transparent; color: var(--text); font-size: 12px; font-weight: 600; }
  .pill:hover { border-color: var(--accent); color: var(--accent); }
  .acts { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; justify-content: center; }
  .ghost { padding: 8px 14px; border-radius: 999px; background: transparent; color: var(--muted); font-size: 12px; font-weight: 600; }
  .ghost:hover { color: var(--text); background: var(--hover, rgba(127,127,127,0.12)); }
  .dismiss { padding: 8px 22px; border-radius: 999px; background: var(--accent); color: #fff; font-weight: 600; font-size: 13px; }
  .dismiss:hover { filter: brightness(1.06); }
</style>
