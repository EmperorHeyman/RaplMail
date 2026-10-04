<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify, normalizeFeeds, CAL_PALETTE } from "../store.svelte.js";
  import { calendar as calApi } from "../api.js";
  import { icons } from "../icons.js";
  import { playSound, SOUND_OPTIONS } from "../sound.js";
  import { t } from "../i18n.svelte.js";

  // Reminder sound + popup window - moved here from General → Notifications so
  // everything about calendar reminders sits in one place.
  const vol = $derived(app.settings.notifyVolume ?? 80);
  const soundOpts = $derived([
    ...SOUND_OPTIONS,
    ...((app.settings.customSounds || []).map((c) => ({ id: `custom:${c.id}`, label: c.name }))),
  ]);

  // Google Calendar write access (OAuth) - lets "New event" actually land on
  // your Google Calendar (the iMIP email trick is unreliable for self-events).
  let gcal = $state({ connected: false, email: "" });
  let gcalBusy = $state(false);
  onMount(async () => { try { gcal = await calApi.googleStatus(); } catch {} });
  async function connectGoogleCal() {
    gcalBusy = true;
    try { gcal = await calApi.googleConnect(); notify(t("sCal.gcalConnected", { email: gcal.email || "ok" })); }
    catch (e) { notify(e.message || t("sCal.gcalFailed"), "error"); }
    finally { gcalBusy = false; }
  }
  async function disconnectGoogleCal() {
    try { await calApi.googleDisconnect(); gcal = { connected: false, email: "" }; notify(t("sCal.gcalDisconnected")); }
    catch (e) { notify(e.message, "error"); }
  }

  // Each subscribed feed is { url, color }. Edited as a list with a color swatch.
  let feeds = $state(normalizeFeeds(app.settings.icsFeeds));
  function persist() {
    saveSettings({ icsFeeds: feeds.filter((f) => (f.url || "").trim()) });
  }
  function addFeed() {
    feeds = [...feeds, { url: "", color: CAL_PALETTE[feeds.length % CAL_PALETTE.length] }];
  }
  function removeFeed(i) { feeds = feeds.filter((_, j) => j !== i); persist(); }
  function setUrl(i, v) { feeds[i].url = v.trim(); feeds = [...feeds]; persist(); }
  function setColor(i, v) { feeds[i].color = v; feeds = [...feeds]; persist(); }

  // Reminders: combinable lead times (minutes before the event).
  const REMINDER_OPTS = $derived.by(() => [
    { m: 0, t: t("sCal.remAtStart") }, { m: 5, t: t("sCal.remMin", { n: 5 }) }, { m: 10, t: t("sCal.remMin", { n: 10 }) },
    { m: 30, t: t("sCal.remMin", { n: 30 }) }, { m: 60, t: t("sCal.rem1h") }, { m: 1440, t: t("sCal.rem1d") }, { m: 10080, t: t("sCal.rem1w") },
  ]);
  const reminders = () => app.settings.calendarReminders || [];
  function toggleReminder(m) {
    const cur = reminders();
    const next = cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m].sort((a, b) => a - b);
    saveSettings({ calendarReminders: next });
  }

  let davSyncing = $state(false);
  async function syncDav() {
    persist();
    davSyncing = true;
    try {
      const r = await calApi.caldavSync();
      if (r.error) { notify(r.error, "error"); return; }
      const bits = [];
      if (r.events) bits.push(t("sCal.syncedBitCaldav", { n: r.events }));
      if (r.ics_events) bits.push(t("sCal.syncedBitFeeds", { n: r.ics_events }));
      if (r.contacts) bits.push(t("sCal.syncedBitContacts", { n: r.contacts }));
      const removed = r.ics_removed ? t("sCal.syncedRemoved", { n: r.ics_removed }) : "";
      notify(t("sCal.synced", { items: bits.join(", ") || t("sCal.syncedNone"), removed }));
    } catch (e) { notify(e.message, "error"); }
    finally { davSyncing = false; }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sCal.gcalTitle")}</h3>
    <p class="hint">{t("sCal.gcalHint")}</p>
    {#if gcal.connected}
      <div class="rowbtns" style="align-items:center">
        <span class="hint" style="margin:0">✓ {gcal.email ? t("sCal.connectedAs", { email: gcal.email }) : t("sCal.connected")}</span>
        <button class="btn" onclick={disconnectGoogleCal}>{t("sCal.disconnect")}</button>
      </div>
    {:else}
      <div class="rowbtns">
        <button class="btn primary" onclick={connectGoogleCal} disabled={gcalBusy}>{@html icons.google || ""} {gcalBusy ? t("sCal.waitingGoogle") : t("sCal.connectGcal")}</button>
      </div>
      <p class="hint" style="margin-top:8px">{t("sCal.gcalBrowserHint")}</p>
    {/if}
  </section>

  <section class="card">
    <h3>{t("sCal.subsTitle")}</h3>
    <p class="hint">{t("sCal.subsHintA")} <code>.ics</code> {t("sCal.or")}
      <code>webcal://</code> {t("sCal.subsHintB")}</p>
    <div class="feeds">
      {#each feeds as feed, i (i)}
        <div class="feedrow">
          <input class="swatch" type="color" value={feed.color} title={t("sCal.feedColor")}
            oninput={(e) => setColor(i, e.currentTarget.value)} />
          <input class="url" value={feed.url} placeholder={t("sCal.feedPlaceholder")}
            onchange={(e) => setUrl(i, e.currentTarget.value)} />
          <button class="rm" title={t("sCal.removeFeed")} onclick={() => removeFeed(i)}>{@html icons.trash}</button>
        </div>
      {/each}
      {#if feeds.length === 0}<p class="hint" style="margin:0">{t("sCal.noFeeds")}</p>{/if}
    </div>
    <div class="rowbtns">
      <button class="btn" onclick={addFeed}>＋ {t("sCal.addFeed")}</button>
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? t("sCal.syncing") : t("sCal.syncNow")}</button>
    </div>
  </section>

  <section class="card">
    <h3>{t("sCal.remTitle")}</h3>
    <p class="hint">{t("sCal.remHintA")} <i>{t("sCal.remAnd")}</i> {t("sCal.remHintDay")} <i>{t("sCal.remAnd")}</i> {t("sCal.remHintB")}</p>
    <div class="chips remind">
      {#each REMINDER_OPTS as o}
        <button class="rchip" class:on={reminders().includes(o.m)} onclick={() => toggleReminder(o.m)}>{o.t}</button>
      {/each}
    </div>
    {#if reminders().length === 0}<p class="hint" style="margin:8px 0 0">{t("sCal.noReminders")}</p>{/if}
    <label class="fieldrow" style="margin-top:14px"><span>{t("notif.soundCalendar")}</span>
      <select value={app.settings.notifyCalendarSound || "chime"} onchange={(e) => { saveSettings({ notifyCalendarSound: e.currentTarget.value }); playSound(e.currentTarget.value, vol / 100); }}>
        {#each soundOpts as s}<option value={s.id}>{s.label}</option>{/each}
      </select>
      <button class="btn sm" onclick={() => playSound(app.settings.notifyCalendarSound || "chime", vol / 100)}>▶ {t("common.play")}</button>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.calendarReminderWindow !== false}
        onchange={(e) => saveSettings({ calendarReminderWindow: e.currentTarget.checked })} />
      <div><b>{t("notif.reminderWindow")}</b><span>{t("notif.reminderWindowHint")}</span></div>
    </label>
    <label class="fieldrow" style="margin-top:14px"><span>{t("sCal.autoSync")}</span>
      <select value={app.settings.icsSyncMinutes ?? 30} onchange={(e) => saveSettings({ icsSyncMinutes: Number(e.currentTarget.value) })}>
        <option value={15}>{t("sCal.every15m")}</option>
        <option value={30}>{t("sCal.every30m")}</option>
        <option value={60}>{t("sCal.every1h")}</option>
        <option value={180}>{t("sCal.every3h")}</option>
      </select>
    </label>
    <p class="hint" style="margin:6px 0 0">{t("sCal.autoHintA")} <b>{t("sCal.syncBtnName")}</b> {t("sCal.autoHintB")}</p>
  </section>

  <section class="card">
    <h3>{t("sCal.davTitle")}</h3>
    <p class="hint">{t("sCal.davHint")}</p>

    <label class="fieldrow"><span>{t("sCal.caldavUrl")}</span>
      <input placeholder="https://dav.example.com/cal/personal/" value={app.settings.caldavUrl || ""}
        onchange={(e) => saveSettings({ caldavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>{t("sCal.carddavUrl")}</span>
      <input placeholder="https://dav.example.com/card/default/" value={app.settings.carddavUrl || ""}
        onchange={(e) => saveSettings({ carddavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>{t("sCal.username")}</span>
      <input value={app.settings.caldavUser || ""} onchange={(e) => saveSettings({ caldavUser: e.currentTarget.value })} />
    </label>
    <label class="fieldrow"><span>{t("sCal.password")}</span>
      <input type="password" value={app.settings.caldavPassword || ""} onchange={(e) => saveSettings({ caldavPassword: e.currentTarget.value })} />
    </label>

    <div class="rowbtns">
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? t("sCal.syncing") : t("sCal.syncNow")}</button>
    </div>
  </section>

  <section class="card">
    <h3>{t("sCal.findTitle")}</h3>
    <ul class="tips">
      <li><b>Seznam / emailprofi:</b> <code>https://cal.seznam.cz/calendars/&lt;you@domain&gt;/</code> · {t("sCal.tipContacts")} <code>https://contacts.seznam.cz/&lt;you@domain&gt;/</code></li>
      <li><b>Nextcloud:</b> <code>https://&lt;host&gt;/remote.php/dav/calendars/&lt;user&gt;/personal/</code></li>
      <li><b>Fastmail:</b> <code>https://caldav.fastmail.com/dav/calendars/user/&lt;you&gt;/</code> {t("sCal.tipFastmail")}</li>
      <li><b>iCloud:</b> {t("sCal.tipIcloud")}</li>
    </ul>
    <p class="hint">{t("sCal.tipRootA")} ({t("sCal.eg")} <code>…/dav/</code>) - {t("sCal.tipRootB")}</p>
  </section>

  <section class="card">
    <h3>{t("sCal.builtinTitle")}</h3>
    <p class="hint">{t("sCal.builtinHintA")} <b>{t("sCal.calendarName")}</b> {t("sCal.builtinHintB")}</p>
  </section>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 22px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .hint code, .tips code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .fieldrow { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .fieldrow > span { width: 110px; flex: none; color: var(--muted); font-size: 13px; }
  .fieldrow input { flex: 1; }
  .fieldrow select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .btn.sm { padding: 4px 9px; font-size: 12px; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 6px 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
  .rowbtns { display: flex; gap: 12px; margin-top: 8px; }
  textarea { width: 100%; resize: vertical; font: 12px/1.5 ui-monospace, monospace;
    background: var(--surface-2); color: var(--text); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 10px; margin-bottom: 10px; }
  textarea:focus { border-color: var(--accent); outline: none; }
  .tips { margin: 0 0 8px; padding-left: 18px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.5; }
  .feeds { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
  .feedrow { display: flex; align-items: center; gap: 8px; }
  .feedrow .url { flex: 1; }
  .swatch { flex: none; width: 30px; height: 30px; padding: 0; border: 1px solid var(--border); border-radius: 8px; background: none; cursor: pointer; }
  .swatch::-webkit-color-swatch-wrapper { padding: 3px; }
  .swatch::-webkit-color-swatch { border: none; border-radius: 5px; }
  .rm { flex: none; width: 32px; height: 32px; border-radius: 8px; color: var(--muted); border: 1px solid var(--border); display: grid; place-items: center; }
  .rm:hover { color: var(--danger); border-color: var(--danger); }
  .chips.remind { display: flex; flex-wrap: wrap; gap: 7px; }
  .rchip { font-size: 12px; font-weight: 600; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); background: var(--surface-2); }
  .rchip:hover { color: var(--text); border-color: var(--accent); }
  .rchip.on { background: var(--sel); border-color: var(--sel); color: var(--on-sel); }
</style>
