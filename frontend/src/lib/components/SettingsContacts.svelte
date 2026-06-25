<script>
  import { onMount } from "svelte";
  import { notify } from "../store.svelte.js";
  import { contacts as api } from "../api.js";
  import { icons } from "../icons.js";

  let list = $state([]);
  let q = $state("");
  let busy = $state(false);
  let timer;
  let newEmail = $state("");
  let newName = $state("");

  async function load() {
    list = await api.list(q);
  }
  onMount(load);

  function onSearch(v) {
    q = v;
    clearTimeout(timer);
    timer = setTimeout(load, 160);
  }

  async function rescan() {
    busy = true;
    try {
      const r = await api.rescan();
      notify(`Address book updated — ${r.scanned} contacts from your sent mail`);
      await load();
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
  }

  async function add() {
    if (!newEmail.includes("@")) { notify("Enter a valid email", "error"); return; }
    await api.create({ email: newEmail, name: newName, favorite: false });
    newEmail = ""; newName = "";
    await load();
    notify("Contact added");
  }

  async function toggleFav(c) {
    await api.update(c.id, { email: c.email, name: c.name, favorite: !c.favorite });
    await load();
  }

  async function remove(c) {
    await api.remove(c.id);
    await load();
  }

  function fmtDate(iso) {
    return iso ? new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : "—";
  }
</script>

<div class="wrap">
  <div class="head">
    <input class="search" type="search" placeholder="Search contacts…" value={q} oninput={(e) => onSearch(e.currentTarget.value)} />
    <button class="btn" onclick={rescan} disabled={busy}>{#if !busy}{@html icons.sync} {/if}{busy ? "Scanning…" : "Rescan sent mail"}</button>
  </div>

  <p class="explain">
    RaplMail builds this automatically from people you email. It keeps known domains
    (gmail, seznam, a123systems…) and anyone who replies, and skips one-off cold sends to
    random/unknown domains and no-reply addresses.
  </p>

  <div class="add-row">
    <input placeholder="name (optional)" bind:value={newName} />
    <input placeholder="email@example.com" bind:value={newEmail} />
    <button class="btn primary" onclick={add}>Add manually</button>
  </div>

  <div class="list">
    {#if list.length === 0}
      <p class="muted">No contacts yet. Add an account, sync, then hit “Rescan sent mail”.</p>
    {/if}
    {#each list as c (c.id)}
      <div class="row">
        <button class="fav" class:on={c.favorite} title="Favorite" onclick={() => toggleFav(c)}>{c.favorite ? "★" : "☆"}</button>
        <div class="who">
          <b>{c.name || c.email}</b>
          {#if c.name}<span class="em">{c.email}</span>{/if}
        </div>
        <div class="meta">
          {#if c.is_known_domain}<span class="pill known">known</span>{/if}
          {#if c.source === "manual"}<span class="pill">manual</span>{/if}
          <span class="stat" title="Times you emailed them">↗ {c.times_sent}</span>
          <span class="stat" title="Times they emailed you">↘ {c.times_received}</span>
          <span class="date">{fmtDate(c.last_contacted)}</span>
        </div>
        <button class="btn ghost danger" onclick={() => remove(c)}>Remove</button>
      </div>
    {/each}
  </div>
</div>

<style>
  .wrap { max-width: 820px; }
  .head { display: flex; gap: 10px; margin-bottom: 12px; }
  .search { flex: 1; }
  .explain { color: var(--muted); font-size: 13px; line-height: 1.6; margin: 0 0 18px; }
  .add-row { display: flex; gap: 8px; margin-bottom: 18px; }
  .add-row input:first-child { flex: 0 0 200px; }
  .add-row input:nth-child(2) { flex: 1; }
  .list { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .fav { font-size: 16px; color: var(--faint); }
  .fav.on { color: var(--warning); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .who .em { color: var(--muted); font-size: 12px; }
  .meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--muted); }
  .pill.known { background: rgba(56,211,159,0.16); color: var(--done); }
  .stat { font-variant-numeric: tabular-nums; }
  .date { color: var(--faint); min-width: 88px; text-align: right; }
  .muted { color: var(--muted); }
</style>
