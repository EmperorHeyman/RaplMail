<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify, normalizeFeeds, CAL_PALETTE } from "../store.svelte.js";
  import { calendar as calApi } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // Google Calendar write access (OAuth) - lets "New event" actually land on
  // your Google Calendar (the iMIP email trick is unreliable for self-events).
  let gcal = $state({ connected: false, email: "" });
  let gcalBusy = $state(false);
  onMount(async () => { try { gcal = await calApi.googleStatus(); } catch {} });
  async function connectGoogleCal() {
    gcalBusy = true;
    try { gcal = await calApi.googleConnect(); notify(t("setcal.googleConnected", { email: gcal.email || "ok" })); }
    catch (e) { notify(e.message || t("setcal.googleSigninFailed"), "error"); }
    finally { gcalBusy = false; }
  }
  async function disconnectGoogleCal() {
    try { await calApi.googleDisconnect(); gcal = { connected: false, email: "" }; notify(t("setcal.googleDisconnected")); }
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
  const REMINDER_OPTS = [
    { m: 0, k: "setcal.remAtStart" }, { m: 5, k: "setcal.rem5m" }, { m: 10, k: "setcal.rem10m" },
    { m: 30, k: "setcal.rem30m" }, { m: 60, k: "setcal.rem1h" }, { m: 1440, k: "setcal.rem1d" }, { m: 10080, k: "setcal.rem1w" },
  ];
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
      if (r.events) bits.push(t("setcal.bitCaldav", { n: r.events }));
      if (r.ics_events) bits.push(t("setcal.bitFeeds", { n: r.ics_events }));
      if (r.contacts) bits.push(t("setcal.bitContacts", { n: r.contacts }));
      const removed = r.ics_removed ? t("setcal.bitRemoved", { n: r.ics_removed }) : "";
      notify(t("setcal.synced", { list: bits.join(", ") || t("setcal.zeroEvents") }) + removed);
    } catch (e) { notify(e.message, "error"); }
    finally { davSyncing = false; }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("setcal.googleTitle")}</h3>
    <p class="hint">{t("setcal.googleHint")}</p>
    {#if gcal.connected}
      <div class="rowbtns" style="align-items:center">
        <span class="hint" style="margin:0">{gcal.email ? t("setcal.connectedAs", { email: gcal.email }) : t("setcal.connected")}</span>
        <button class="btn" onclick={disconnectGoogleCal}>{t("setcal.disconnect")}</button>
      </div>
    {:else}
      <div class="rowbtns">
        <button class="btn primary" onclick={connectGoogleCal} disabled={gcalBusy}>{@html icons.google || ""} {gcalBusy ? t("setcal.waitingGoogle") : t("setcal.connectGoogle")}</button>
      </div>
      <p class="hint" style="margin-top:8px">{t("setcal.googleBrowserHint")}</p>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setcal.feedsTitle")}</h3>
    <p class="hint">{@html t("setcal.feedsHint")}</p>
    <div class="feeds">
      {#each feeds as feed, i (i)}
        <div class="feedrow">
          <input class="swatch" type="color" value={feed.color} title={t("setcal.calColor")}
            oninput={(e) => setColor(i, e.currentTarget.value)} />
          <input class="url" value={feed.url} placeholder={t("setcal.feedUrlPh")}
            onchange={(e) => setUrl(i, e.currentTarget.value)} />
          <button class="rm" title={t("setcal.removeFeed")} onclick={() => removeFeed(i)}>{@html icons.trash}</button>
        </div>
      {/each}
      {#if feeds.length === 0}<p class="hint" style="margin:0">{t("setcal.noFeeds")}</p>{/if}
    </div>
    <div class="rowbtns">
      <button class="btn" onclick={addFeed}>＋ {t("setcal.addFeed")}</button>
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? t("setcal.syncing") : t("setcal.syncNow")}</button>
    </div>
  </section>

  <section class="card">
    <h3>{t("setcal.remindersTitle")}</h3>
    <p class="hint">{@html t("setcal.remindersHint")}</p>
    <div class="chips remind">
      {#each REMINDER_OPTS as o}
        <button class="rchip" class:on={reminders().includes(o.m)} onclick={() => toggleReminder(o.m)}>{t(o.k)}</button>
      {/each}
    </div>
    {#if reminders().length === 0}<p class="hint" style="margin:8px 0 0">{t("setcal.noReminders")}</p>{/if}
    <label class="fieldrow" style="margin-top:14px"><span>{t("setcal.autoSyncEvery")}</span>
      <select value={app.settings.icsSyncMinutes ?? 30} onchange={(e) => saveSettings({ icsSyncMinutes: Number(e.currentTarget.value) })}>
        <option value={15}>{t("setcal.min15")}</option>
        <option value={30}>{t("setcal.min30")}</option>
        <option value={60}>{t("setcal.hour1")}</option>
        <option value={180}>{t("setcal.hours3")}</option>
      </select>
    </label>
    <p class="hint" style="margin:6px 0 0">{@html t("setcal.autoSyncHint")}</p>
  </section>

  <section class="card">
    <h3>{t("setcal.davTitle")}</h3>
    <p class="hint">{t("setcal.davHint")}</p>

    <label class="fieldrow"><span>{t("setcal.caldavUrl")}</span>
      <input placeholder="https://dav.example.com/cal/personal/" value={app.settings.caldavUrl || ""}
        onchange={(e) => saveSettings({ caldavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>{t("setcal.carddavUrl")}</span>
      <input placeholder="https://dav.example.com/card/default/" value={app.settings.carddavUrl || ""}
        onchange={(e) => saveSettings({ carddavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>{t("setcal.username")}</span>
      <input value={app.settings.caldavUser || ""} onchange={(e) => saveSettings({ caldavUser: e.currentTarget.value })} />
    </label>
    <label class="fieldrow"><span>{t("setcal.password")}</span>
      <input type="password" value={app.settings.caldavPassword || ""} onchange={(e) => saveSettings({ caldavPassword: e.currentTarget.value })} />
    </label>

    <div class="rowbtns">
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? t("setcal.syncing") : t("setcal.syncNow")}</button>
    </div>
  </section>

  <section class="card">
    <h3>{t("setcal.tipsTitle")}</h3>
    <ul class="tips">
      <li><b>Seznam / emailprofi:</b> <code>https://cal.seznam.cz/calendars/&lt;you@domain&gt;/</code> · {t("setcal.tipContacts")}: <code>https://contacts.seznam.cz/&lt;you@domain&gt;/</code></li>
      <li><b>Nextcloud:</b> <code>https://&lt;host&gt;/remote.php/dav/calendars/&lt;user&gt;/personal/</code></li>
      <li><b>Fastmail:</b> <code>https://caldav.fastmail.com/dav/calendars/user/&lt;you&gt;/</code> {t("setcal.tipFastmail")}</li>
      <li><b>iCloud:</b> {t("setcal.tipIcloud")}</li>
    </ul>
    <p class="hint">{@html t("setcal.tipsHint")}</p>
  </section>

  <section class="card">
    <h3>{t("setcal.builtinTitle")}</h3>
    <p class="hint">{@html t("setcal.builtinHint")}</p>
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
  .rchip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
