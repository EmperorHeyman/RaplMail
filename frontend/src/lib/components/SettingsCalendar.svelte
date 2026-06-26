<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { calendar as calApi } from "../api.js";
  import { icons } from "../icons.js";

  let davSyncing = $state(false);
  async function syncDav() {
    davSyncing = true;
    try {
      const r = await calApi.caldavSync();
      if (r.error) notify(r.error, "error");
      else notify(`Synced ${r.events} event(s), ${r.contacts} contact(s)`);
    } catch (e) { notify(e.message, "error"); }
    finally { davSyncing = false; }
  }
</script>

<div class="wrap">
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
  .tips { margin: 0 0 8px; padding-left: 18px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.5; }
</style>
