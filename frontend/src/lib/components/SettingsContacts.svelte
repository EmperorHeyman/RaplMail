<script>
  import { onMount } from "svelte";
  import { notify } from "../store.svelte.js";
  import { contacts as api } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

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
      notify(t("setcontacts.rescanDone", { n: r.scanned }));
      await load();
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
  }

  async function add() {
    if (!newEmail.includes("@")) { notify(t("setcontacts.invalidEmail"), "error"); return; }
    await api.create({ email: newEmail, name: newName, favorite: false });
    newEmail = ""; newName = "";
    await load();
    notify(t("setcontacts.added"));
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
    return iso ? new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : "-";
  }
</script>

<div class="wrap">
  <div class="head">
    <input class="search" type="search" placeholder={t("setcontacts.searchPh")} value={q} oninput={(e) => onSearch(e.currentTarget.value)} />
    <button class="btn" onclick={rescan} disabled={busy}>{#if !busy}{@html icons.sync} {/if}{busy ? t("setcontacts.scanning") : t("setcontacts.rescan")}</button>
  </div>

  <p class="explain">{t("setcontacts.explain")}</p>

  <div class="add-row">
    <input placeholder={t("setcontacts.namePh")} bind:value={newName} />
    <input placeholder="email@example.com" bind:value={newEmail} />
    <button class="btn primary" onclick={add}>{t("setcontacts.addManually")}</button>
  </div>

  <div class="list">
    {#if list.length === 0}
      <p class="muted">{t("setcontacts.empty")}</p>
    {/if}
    {#each list as c (c.id)}
      <div class="row">
        <button class="fav" class:on={c.favorite} title={t("setcontacts.favorite")} onclick={() => toggleFav(c)}>{c.favorite ? "★" : "☆"}</button>
        <div class="who">
          <b>{c.name || c.email}</b>
          {#if c.name}<span class="em">{c.email}</span>{/if}
        </div>
        <div class="meta">
          {#if c.is_known_domain}<span class="pill known">{t("setcontacts.known")}</span>{/if}
          {#if c.source === "manual"}<span class="pill">{t("setcontacts.manual")}</span>{/if}
          <span class="stat" title={t("setcontacts.timesSent")}>↗ {c.times_sent}</span>
          <span class="stat" title={t("setcontacts.timesReceived")}>↘ {c.times_received}</span>
          <span class="date">{fmtDate(c.last_contacted)}</span>
        </div>
        <button class="btn ghost danger" onclick={() => remove(c)}>{t("setcontacts.remove")}</button>
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
