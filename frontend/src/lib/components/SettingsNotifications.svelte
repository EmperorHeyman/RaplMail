<script>
  // Settings → Notifications: new-mail alerts and sounds, out of the old General
  // tab. Calendar reminders (their sound and popup window) live with the rest of
  // the calendar settings; this page links there.
  import { app, saveSettings, notify, enableNotifications, notificationsAvailable, testNotification } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { playSound, SOUND_OPTIONS } from "../sound.js";
  import SoundStudio from "./SoundStudio.svelte";
  import { hourLabel } from "../time.svelte.js";
  import { t } from "../i18n.svelte.js";

  const vol = $derived(app.settings.notifyVolume ?? 80);
  // Built-in sounds + your own uploaded clips.
  const soundOpts = $derived([
    ...SOUND_OPTIONS,
    ...((app.settings.customSounds || []).map((c) => ({ id: `custom:${c.id}`, label: c.name }))),
  ]);
  let studioOpen = $state(false);
  function onStudioClose(picked) {
    studioOpen = false;
    // A freshly made clip becomes the new-mail sound straight away.
    if (typeof picked === "string") { saveSettings({ notifySound: picked }); playSound(picked, vol / 100); }
  }
  function deleteCustom(id) {
    const patch = { customSounds: (app.settings.customSounds || []).filter((c) => c.id !== id) };
    // Fall back to a built-in wherever the deleted clip was in use.
    if (app.settings.notifySound === `custom:${id}`) patch.notifySound = "ding";
    if (app.settings.notifyCalendarSound === `custom:${id}`) patch.notifyCalendarSound = "chime";
    saveSettings(patch);
  }

  let perm = $state("default");
  const _isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  async function refreshPerm() {
    if (_isTauri) {
      try { const m = await import("@tauri-apps/plugin-notification"); perm = (await m.isPermissionGranted()) ? "granted" : "default"; return; } catch {}
    }
    perm = typeof Notification !== "undefined" ? Notification.permission : "unsupported";
  }
  refreshPerm();
  async function toggleNotify(on) {
    if (!on) { saveSettings({ notifyNewMail: false }); return; }
    const r = await enableNotifications();
    perm = r;
    saveSettings({ notifyNewMail: r === "granted" });
    if (r !== "granted") notify(t("sNotif.toastBlocked"), "error");
  }
  async function sendTest() {
    const res = await testNotification();
    await refreshPerm();
    if (res.ok) notify(t("sNotif.testSent"));
    else if (res.reason === "denied") notify(t("sNotif.testDenied"), "error");
    else if (res.reason === "unsupported") notify(t("sNotif.testUnsupported"), "error");
    else notify(t("sNotif.testFailed", { reason: res.reason }), "error");
  }
</script>

<div class="wrap">
  <section class="card">
    {#if notificationsAvailable()}
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyNewMail !== false && perm === "granted"}
          onchange={(e) => toggleNotify(e.currentTarget.checked)} />
        <div>
          <b>{t("notif.newMail")}</b>
          <span>{t("sNotif.newMailHint")}{#if perm === "denied"} <em>{t("sNotif.blocked")}</em>{/if}</span>
        </div>
      </label>
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyOnlyUnfocused !== false}
          onchange={(e) => saveSettings({ notifyOnlyUnfocused: e.currentTarget.checked })} />
        <div><b>{t("notif.onlyUnfocused")}</b><span>{t("sNotif.unfocusedHint")}</span></div>
      </label>
      <label class="check">
        <input type="checkbox" checked={!!app.settings.quietHoursEnabled}
          onchange={(e) => saveSettings({ quietHoursEnabled: e.currentTarget.checked })} />
        <div><b>{t("sNotif.quiet")}</b><span>{t("sNotif.quietHint")}</span></div>
      </label>
      {#if app.settings.quietHoursEnabled}
        <label class="inline" style="margin-left:28px">{t("sNotif.from")}
          <select value={app.settings.quietStart ?? 22} onchange={(e) => saveSettings({ quietStart: Number(e.currentTarget.value) })}>
            {#each Array.from({ length: 24 }, (_, i) => i) as h}<option value={h}>{hourLabel(h)}</option>{/each}
          </select> {t("sNotif.to")}
          <select value={app.settings.quietEnd ?? 7} onchange={(e) => saveSettings({ quietEnd: Number(e.currentTarget.value) })}>
            {#each Array.from({ length: 24 }, (_, i) => i) as h}<option value={h}>{hourLabel(h)}</option>{/each}
          </select>
        </label>
      {/if}
    {:else}
      <p class="hint">{t("sNotif.unavailable")}</p>
    {/if}
  </section>

  <section class="card">
    <h3>{t("otp.settingsTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.autoCopyCodes !== false}
        onchange={(e) => saveSettings({ autoCopyCodes: e.currentTarget.checked })} />
      <div><b>{t("otp.autoCopy")}</b><span>{t("otp.autoCopyHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("notif.sound")}</h3>
    <label class="inline" style="margin-top:0">{t("notif.soundMail")}
      <select value={app.settings.notifySound || "ding"} onchange={(e) => { saveSettings({ notifySound: e.currentTarget.value }); playSound(e.currentTarget.value, vol / 100); }}>
        {#each soundOpts as s}<option value={s.id}>{s.label}</option>{/each}
      </select>
      <button class="btn sm" onclick={() => playSound(app.settings.notifySound || "ding", vol / 100)}>▶ {t("common.play")}</button>
    </label>
    <label class="inline">{t("notif.volume")}
      <input type="range" min="0" max="100" step="5" value={vol}
        disabled={(app.settings.notifySound || "ding") === "none"}
        oninput={(e) => saveSettings({ notifyVolume: Number(e.currentTarget.value) })}
        onchange={(e) => playSound(app.settings.notifySound || "ding", Number(e.currentTarget.value) / 100)} />
      <span class="tnum" style="width:38px;text-align:right">{vol}%</span>
    </label>
    <p class="hint" style="margin:6px 0 0">{t("sNotif.chimeHint")}</p>
    <div class="customsnd">
      <div class="csnd-head">
        <span>{t("notif.customSounds")}</span>
        <button class="btn sm" onclick={() => (studioOpen = true)}>＋ {t("notif.addCustom")}</button>
      </div>
      {#if (app.settings.customSounds || []).length}
        <div class="csnd-list">
          {#each app.settings.customSounds as c (c.id)}
            <div class="csnd-row">
              <button class="csnd-play" title={t("sound.preview")} onclick={() => playSound(`custom:${c.id}`, vol / 100)}>▶</button>
              <span class="csnd-name">{c.name}</span>
              <button class="csnd-del" title={t("common.delete")} onclick={() => deleteCustom(c.id)}>{@html icons.close}</button>
            </div>
          {/each}
        </div>
      {:else}
        <p class="hint" style="margin:6px 0 0">{t("notif.customHint")}</p>
      {/if}
    </div>
  </section>

  {#if notificationsAvailable()}
    <section class="card">
      <button class="btn" onclick={sendTest}>{t("notif.test")}</button>
      <p class="hint" style="margin:10px 0 0">{t("sNotif.noPopup")}</p>
      <p class="hint" style="margin:8px 0 0">{t("notif.muteHint")}</p>
      <p class="hint" style="margin:8px 0 0">{t("sNotif.calendarMoved")}
        <button class="link" onclick={() => (app.settingsTab = "calendar")}>{t("sNotif.openCalendar")} →</button></p>
    </section>
  {/if}
</div>

{#if studioOpen}<SoundStudio onclose={onStudioClose} />{/if}

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 10px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
  .inline { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: var(--muted); font-size: 13px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .btn.sm { padding: 4px 9px; font-size: 12px; }
  .link { color: var(--accent); font-size: 13px; padding: 0; }
  .link:hover { text-decoration: underline; }
  .customsnd { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--hairline); }
  .csnd-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 13px; color: var(--muted); }
  .csnd-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
  .csnd-row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .csnd-play { flex: none; width: 24px; height: 24px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 11px; }
  .csnd-play:hover { background: var(--hover); color: var(--text); }
  .csnd-name { flex: 1; min-width: 0; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .csnd-del { flex: none; color: var(--muted); padding: 3px; border-radius: 5px; }
  .csnd-del:hover { color: var(--danger); background: var(--hover); }
  .csnd-del :global(svg) { width: 13px; height: 13px; }
</style>
