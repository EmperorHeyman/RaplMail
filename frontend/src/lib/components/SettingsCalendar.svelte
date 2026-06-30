<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify, normalizeFeeds, CAL_PALETTE } from "../store.svelte.js";
  import { calendar as calApi } from "../api.js";
  import { icons } from "../icons.js";

  // Google Calendar write access (OAuth) — lets "New event" actually land on
  // your Google Calendar (the iMIP email trick is unreliable for self-events).
  let gcal = $state({ connected: false, email: "" });
  let gcalBusy = $state(false);
  onMount(async () => { try { gcal = await calApi.googleStatus(); } catch {} });
  async function connectGoogleCal() {
    gcalBusy = true;
    try { gcal = await calApi.googleConnect(); notify(`Google Calendar connected (${gcal.email || "ok"})`); }
    catch (e) { notify(e.message || "Google sign-in failed", "error"); }
    finally { gcalBusy = false; }
  }
  async function disconnectGoogleCal() {
    try { await calApi.googleDisconnect(); gcal = { connected: false, email: "" }; notify("Google Calendar disconnected"); }
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
    { m: 0, t: "At start" }, { m: 5, t: "5 min" }, { m: 10, t: "10 min" },
    { m: 30, t: "30 min" }, { m: 60, t: "1 hour" }, { m: 1440, t: "1 day" }, { m: 10080, t: "1 week" },
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
      if (r.events) bits.push(`${r.events} CalDAV`);
      if (r.ics_events) bits.push(`${r.ics_events} from feeds`);
      if (r.contacts) bits.push(`${r.contacts} contact(s)`);
      const removed = r.ics_removed ? `, removed ${r.ics_removed} stale` : "";
      notify(`Synced ${bits.join(", ") || "0 events"}${removed}`);
    } catch (e) { notify(e.message, "error"); }
    finally { davSyncing = false; }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>Write to Google Calendar</h3>
    <p class="hint">Subscribed iCal feeds are read-only. Connect your Google account once (calendar permission)
      so events you create in RaplMail are written straight to your Google Calendar via the API — reliable,
      unlike emailing yourself an invite.</p>
    {#if gcal.connected}
      <div class="rowbtns" style="align-items:center">
        <span class="hint" style="margin:0">✓ Connected{gcal.email ? ` as ${gcal.email}` : ""}</span>
        <button class="btn" onclick={disconnectGoogleCal}>Disconnect</button>
      </div>
    {:else}
      <div class="rowbtns">
        <button class="btn primary" onclick={connectGoogleCal} disabled={gcalBusy}>{@html icons.google || ""} {gcalBusy ? "Waiting for Google…" : "Connect Google Calendar"}</button>
      </div>
      <p class="hint" style="margin-top:8px">A browser window opens for Google sign-in; approve the calendar permission and come back.</p>
    {/if}
  </section>

  <section class="card">
    <h3>Subscribed calendars (iCal / ICS)</h3>
    <p class="hint">Paste iCal feed URLs — one per line — and RaplMail pulls their events into your calendar.
      Works with Google's "Secret address in iCal format", Outlook published calendars, any <code>.ics</code> or
      <code>webcal://</code> link. Duplicates are merged by event ID and events removed from a feed are deleted on the
      next sync. Read-only.</p>
    <div class="feeds">
      {#each feeds as feed, i (i)}
        <div class="feedrow">
          <input class="swatch" type="color" value={feed.color} title="Calendar color"
            oninput={(e) => setColor(i, e.currentTarget.value)} />
          <input class="url" value={feed.url} placeholder="https://…/basic.ics  or  webcal://…"
            onchange={(e) => setUrl(i, e.currentTarget.value)} />
          <button class="rm" title="Remove feed" onclick={() => removeFeed(i)}>{@html icons.trash}</button>
        </div>
      {/each}
      {#if feeds.length === 0}<p class="hint" style="margin:0">No feeds yet — add one below.</p>{/if}
    </div>
    <div class="rowbtns">
      <button class="btn" onclick={addFeed}>＋ Add feed</button>
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? "Syncing…" : "Sync now"}</button>
    </div>
  </section>

  <section class="card">
    <h3>Reminders &amp; auto-sync</h3>
    <p class="hint">Desktop reminders before an event starts — pick any combination (e.g. 10 minutes <i>and</i> 1 day <i>and</i> 1 week). Respects Quiet hours.</p>
    <div class="chips remind">
      {#each REMINDER_OPTS as o}
        <button class="rchip" class:on={reminders().includes(o.m)} onclick={() => toggleReminder(o.m)}>{o.t}</button>
      {/each}
    </div>
    {#if reminders().length === 0}<p class="hint" style="margin:8px 0 0">No reminders — you won't be notified about events.</p>{/if}
    <label class="fieldrow" style="margin-top:14px"><span>Auto-sync every</span>
      <select value={app.settings.icsSyncMinutes ?? 30} onchange={(e) => saveSettings({ icsSyncMinutes: Number(e.currentTarget.value) })}>
        <option value={15}>15 minutes</option>
        <option value={30}>30 minutes</option>
        <option value={60}>1 hour</option>
        <option value={180}>3 hours</option>
      </select>
    </label>
    <p class="hint" style="margin:6px 0 0">Subscribed calendars (and the “Sync” button on the Calendar) refresh automatically while RaplMail is open. The Calendar's <b>Sync</b> button pulls feeds + mail invites on demand.</p>
  </section>

  <section class="card">
    <h3>Calendar &amp; contacts (CalDAV / CardDAV)</h3>
    <p class="hint">Add an external calendar/address book by CalDAV/CardDAV (Nextcloud, Fastmail, iCloud, Seznam,
      Radicale…). RaplMail pulls events into its calendar and contacts into the address book. Read-only for now.</p>

    <label class="fieldrow"><span>CalDAV URL</span>
      <input placeholder="https://dav.example.com/cal/personal/" value={app.settings.caldavUrl || ""}
        onchange={(e) => saveSettings({ caldavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>CardDAV URL</span>
      <input placeholder="https://dav.example.com/card/default/" value={app.settings.carddavUrl || ""}
        onchange={(e) => saveSettings({ carddavUrl: e.currentTarget.value.trim() })} />
    </label>
    <label class="fieldrow"><span>Username</span>
      <input value={app.settings.caldavUser || ""} onchange={(e) => saveSettings({ caldavUser: e.currentTarget.value })} />
    </label>
    <label class="fieldrow"><span>Password</span>
      <input type="password" value={app.settings.caldavPassword || ""} onchange={(e) => saveSettings({ caldavPassword: e.currentTarget.value })} />
    </label>

    <div class="rowbtns">
      <button class="btn primary" onclick={syncDav} disabled={davSyncing}>{@html icons.sync} {davSyncing ? "Syncing…" : "Sync now"}</button>
    </div>
  </section>

  <section class="card">
    <h3>Finding your CalDAV URL</h3>
    <ul class="tips">
      <li><b>Seznam / emailprofi:</b> <code>https://cal.seznam.cz/calendars/&lt;you@domain&gt;/</code> · contacts: <code>https://contacts.seznam.cz/&lt;you@domain&gt;/</code></li>
      <li><b>Nextcloud:</b> <code>https://&lt;host&gt;/remote.php/dav/calendars/&lt;user&gt;/personal/</code></li>
      <li><b>Fastmail:</b> <code>https://caldav.fastmail.com/dav/calendars/user/&lt;you&gt;/</code> (use an app password)</li>
      <li><b>iCloud:</b> enable then use the per-account CalDAV URL from your Apple ID (app-specific password).</li>
    </ul>
    <p class="hint">Tip: most servers also let you point at the account root (e.g. <code>…/dav/</code>) — RaplMail reads whatever events the URL returns.</p>
  </section>

  <section class="card">
    <h3>Built-in calendar</h3>
    <p class="hint">Separately from CalDAV, RaplMail already extracts meeting invites from your mail into the calendar view —
      open <b>Calendar</b> from the sidebar. The “Scan” button there back-fills events from older invites.</p>
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
