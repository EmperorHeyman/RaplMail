<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { rapldesk } from "../api.js";
  import { icons } from "../icons.js";

  let instances = $state([]);
  let adding = $state(false);
  let form = $state({ name: "", url: "", key: "" });
  let busy = $state(false);

  async function load() { try { instances = (await rapldesk.instances()).instances || []; } catch {} }
  onMount(load);

  async function add() {
    if (!form.url.trim() || !form.key.trim()) { notify("URL and API key are required", "error"); return; }
    busy = true;
    try {
      await rapldesk.add({ name: form.name.trim(), url: form.url.trim(), key: form.key.trim() });
      form = { name: "", url: "", key: "" };
      adding = false;
      await load();
      notify("RAPL Desk connected");
    } catch (e) { notify(e.message || "Couldn't connect", "error"); }
    finally { busy = false; }
  }
  async function remove(i) {
    if (!confirm(`Remove ${i.name}?`)) return;
    try { await rapldesk.remove(i.id); await load(); notify("Removed"); }
    catch (e) { notify(e.message, "error"); }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>RAPL Desk (ticketing)</h3>
    <p class="hint">Connect one or more RaplDesk instances by base URL + API key. Tickets show up under
      <b>Tickets</b> in the sidebar. Keys are stored encrypted in your vault (and never leave your machine
      except to call that instance). The key's <b>scopes</b> decide what you can do — for full use grant
      tickets.read/write, users.read, departments.read, firms.read and reports.read.</p>

    {#each instances as i}
      <div class="inst">
        <span class="dot" class:on={i.connected}></span>
        <div class="meta"><b>{i.name}</b><span>{i.url}{i.connected ? "" : " · key missing"}</span></div>
        <button class="btn ghost danger" onclick={() => remove(i)}>Remove</button>
      </div>
    {/each}
    {#if instances.length === 0}<p class="hint" style="margin:0">No instances yet.</p>{/if}

    {#if adding}
      <div class="addform">
        <label class="fr"><span>Name</span><input bind:value={form.name} placeholder="A123 Tickets" /></label>
        <label class="fr"><span>Base URL</span><input bind:value={form.url} placeholder="https://tickets.a123systems.cz" /></label>
        <label class="fr"><span>API key</span><input type="password" bind:value={form.key} placeholder="Bearer token" /></label>
        <div class="rowbtns">
          <button class="btn primary" onclick={add} disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
          <button class="btn ghost" onclick={() => (adding = false)}>Cancel</button>
        </div>
      </div>
    {:else}
      <div class="rowbtns"><button class="btn primary" onclick={() => (adding = true)}>＋ Add instance</button></div>
    {/if}
  </section>

  <section class="card">
    <h3>Your agent identity</h3>
    <p class="hint">RaplDesk requires a user id when posting replies or creating tickets. Enter the user id of
      your agent account so replies are attributed to you.</p>
    <label class="fieldrow"><span>RaplDesk user id</span>
      <input type="number" value={app.settings.raplDeskUserId || ""}
        onchange={(e) => saveSettings({ raplDeskUserId: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
        placeholder="e.g. 25" />
    </label>
  </section>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 22px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .inst { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--danger); flex: none; }
  .dot.on { background: var(--done); }
  .inst .meta { flex: 1; display: flex; flex-direction: column; }
  .inst .meta span { font-size: 12px; color: var(--muted); }
  .addform { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
  .fr { display: flex; align-items: center; gap: 10px; }
  .fr > span { width: 90px; flex: none; color: var(--muted); font-size: 13px; }
  .fr input { flex: 1; }
  .fieldrow { display: flex; align-items: center; gap: 10px; }
  .fieldrow > span { width: 130px; flex: none; color: var(--muted); font-size: 13px; }
  .fieldrow input { flex: 1; }
  .rowbtns { display: flex; gap: 10px; margin-top: 10px; }
  .btn.danger { color: var(--danger); }
</style>
