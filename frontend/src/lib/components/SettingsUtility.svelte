<script>
  import { onMount } from "svelte";
  import { subscriptions, rules as rulesApi, openExternal } from "../api.js";
  import { openCompose, notify } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";

  let lists = $state([]);
  let loading = $state(true);
  let selected = $state(new Set());
  let busy = $state(false);

  async function load() {
    loading = true;
    try { lists = (await subscriptions.audit()).lists || []; }
    catch (e) { notify(e.message, "error"); }
    finally { loading = false; }
  }
  onMount(load);

  function toggle(addr) {
    const s = new Set(selected);
    if (s.has(addr)) s.delete(addr); else s.add(addr);
    selected = s;
  }
  function toggleAll() {
    selected = selected.size === lists.length ? new Set() : new Set(lists.map((l) => l.from_addr));
  }
  const chosen = $derived(lists.filter((l) => selected.has(l.from_addr)));

  function fmtDate(iso) { return iso ? new Date(iso).toLocaleDateString() : "—"; }
  function ratePct(l) { return l.recent30 ? `${Math.round(l.read_rate * 100)}%` : "—"; }

  function doUnsub(l) {
    const u = l.unsubscribe || "";
    if (u.startsWith("http")) openExternal(u);
    else if (u.startsWith("mailto:")) {
      const addr = u.slice(7).split("?")[0];
      openCompose({ to: addr, subject: "Unsubscribe", html: "Please unsubscribe me from this list." });
    }
  }
  function makeArchiveRule(l) {
    return rulesApi.create({
      name: `Archive ${l.from_name || l.from_addr}`,
      match_field: "from", match_op: "equals", match_value: l.from_addr,
      action: "archive", action_arg: "Archive", enabled: true, order: 0,
    });
  }
  async function archiveFuture(l) {
    try { await makeArchiveRule(l); notify(t("utility.archivedRule", { who: l.from_name || l.from_addr })); }
    catch (e) { notify(e.message, "error"); }
  }
  async function batchArchive() {
    busy = true;
    let n = 0;
    for (const l of chosen) { try { await makeArchiveRule(l); n++; } catch {} }
    busy = false;
    selected = new Set();
    notify(t("utility.archivedN", { n }));
  }
  function batchUnsub() {
    for (const l of chosen) if (l.unsubscribe) doUnsub(l);
    selected = new Set();
  }
</script>

<div class="wrap">
  <section>
    <h3>{t("utility.subscriptionsTitle")}</h3>
    <p class="muted">{t("utility.subscriptionsHint")}</p>
    {#if loading}
      <p class="muted">…</p>
    {:else if lists.length === 0}
      <p class="muted">{t("utility.none")}</p>
    {:else}
      <div class="bar">
        <label class="selall">
          <input type="checkbox" checked={selected.size === lists.length && lists.length > 0} onchange={toggleAll} />
          {t("utility.selectAll")}
        </label>
        <button class="btn" disabled={!chosen.length || busy} onclick={batchArchive}>{t("utility.archiveSelected", { n: chosen.length })}</button>
        <button class="btn" disabled={!chosen.length} onclick={batchUnsub}>{t("utility.unsubSelected", { n: chosen.length })}</button>
      </div>
      <div class="tbl">
        {#each lists as l (l.from_addr)}
          <div class="row" class:dormant={l.recent30 === 0}>
            <input type="checkbox" checked={selected.has(l.from_addr)} onchange={() => toggle(l.from_addr)} />
            <div class="who"><b>{l.from_name || l.from_addr}</b><span>{l.from_addr}</span></div>
            <div class="stat"><span class="num">{l.total}</span><span class="lbl">{t("utility.total")}</span></div>
            <div class="stat"><span class="num">{ratePct(l)}</span><span class="lbl">{t("utility.readRate")}</span></div>
            <div class="stat"><span class="num">{fmtDate(l.last_seen)}</span><span class="lbl">{t("utility.lastSeen")}</span></div>
            <div class="acts">
              {#if l.unsubscribe}<button class="btn ghost" onclick={() => doUnsub(l)}>{t("utility.unsubscribe")}</button>{/if}
              <button class="btn ghost" onclick={() => archiveFuture(l)}>{t("utility.archiveFuture")}</button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 14px; max-width: 920px; }
  h3 { margin: 0 0 4px; }
  .muted { color: var(--muted); font-size: 13px; }
  .bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 10px 0; }
  .selall { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-right: auto; }
  .btn { padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; font-size: 13px; }
  .btn:disabled { opacity: 0.4; cursor: default; }
  .btn.ghost { background: transparent; }
  .btn:hover:not(:disabled) { background: var(--surface-3); }
  .tbl { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .row { display: flex; align-items: center; gap: 14px; padding: 10px 14px; border-bottom: 1px solid var(--hairline); }
  .row:last-child { border-bottom: none; }
  .row.dormant { background: var(--surface-2); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .who b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .who span { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stat { display: flex; flex-direction: column; align-items: flex-end; min-width: 66px; }
  .stat .num { font-weight: 600; font-size: 13px; }
  .stat .lbl { color: var(--faint); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
  .acts { display: flex; gap: 6px; }
</style>
