<script>
  import { onMount } from "svelte";
  import { subscriptions, rules as rulesApi, openExternal } from "../api.js";
  import { openCompose, notify, markUnsubscribed, isUnsubscribed } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let lists = $state([]);
  let loading = $state(true);
  let selected = $state(new Set());
  let busy = $state(false);
  let sort = $state("dormant");
  let filter = $state("");
  let onlyUnsub = $state(false);   // show only senders that expose an unsubscribe target

  const SORTS = [
    ["dormant", "utility.sortDormant"],
    ["most", "utility.sortMost"],
    ["recent", "utility.sortRecent"],
    ["unread", "utility.sortUnread"],
    ["name", "utility.sortName"],
  ];

  async function load() {
    loading = true;
    try { lists = (await subscriptions.audit(sort)).lists || []; }
    catch (e) { notify(e.message, "error"); }
    finally { loading = false; }
  }
  onMount(load);

  // Client-side filters over the server-sorted list: text (name/address) + an
  // "only unsubscribable" toggle.
  const shown = $derived.by(() => {
    const q = filter.trim().toLowerCase();
    return lists.filter((l) => {
      if (onlyUnsub && !l.unsubscribe) return false;
      if (q && !(l.from_name + " " + l.from_addr).toLowerCase().includes(q)) return false;
      return true;
    });
  });

  function toggle(addr) {
    const s = new Set(selected);
    if (s.has(addr)) s.delete(addr); else s.add(addr);
    selected = s;
  }
  function toggleAll() {
    selected = selected.size === shown.length ? new Set() : new Set(shown.map((l) => l.from_addr));
  }
  function setSort(v) { sort = v; load(); }
  const chosen = $derived(lists.filter((l) => selected.has(l.from_addr)));

  function fmtDate(iso) { return iso ? new Date(iso).toLocaleDateString() : "-"; }
  function ratePct(l) { return l.recent30 ? `${Math.round(l.read_rate * 100)}%` : "-"; }

  async function doUnsub(l) {
    const u = l.unsubscribe || "";
    if (u.startsWith("mailto:")) {
      const addr = u.slice(7).split("?")[0];
      openCompose({ to: addr, subject: "Unsubscribe", html: "Please unsubscribe me from this list." });
      markUnsubscribed(l.from_addr);
      return;
    }
    if (!u.startsWith("http")) return;
    // Try RFC 8058 one-click POST first (fixes senders like Humble Bundle whose
    // link errors on a plain browser GET). Fall back to opening the page.
    try {
      const r = await subscriptions.unsubscribe(u);
      if (r?.ok) {
        markUnsubscribed(l.from_addr);
        notify(t("utility.unsubDone", { who: l.from_name || l.from_addr }));
        return;
      }
    } catch {}
    openExternal(u);
    markUnsubscribed(l.from_addr);
    notify(t("utility.unsubOpened", { who: l.from_name || l.from_addr }));
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
  async function batchUnsub() {
    busy = true;
    for (const l of chosen) if (l.unsubscribe) await doUnsub(l);
    busy = false;
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
      <div class="filters">
        <div class="seg">
          {#each SORTS as [v, key]}
            <button class="segbtn" class:on={sort === v} onclick={() => setSort(v)}>{t(key)}</button>
          {/each}
        </div>
        <label class="onlyunsub" class:on={onlyUnsub}>
          <input type="checkbox" bind:checked={onlyUnsub} />
          {t("utility.onlyUnsub")}
        </label>
        <input class="find" type="search" placeholder={t("utility.filterPlaceholder")} bind:value={filter} />
      </div>
      <div class="bar">
        <label class="selall">
          <input type="checkbox" checked={selected.size === shown.length && shown.length > 0} onchange={toggleAll} />
          {t("utility.selectAll")}
        </label>
        <button class="btn" disabled={!chosen.length || busy} onclick={batchArchive}>{t("utility.archiveSelected", { n: chosen.length })}</button>
        <button class="btn" disabled={!chosen.length} onclick={batchUnsub}>{t("utility.unsubSelected", { n: chosen.length })}</button>
      </div>
      <div class="tbl">
        {#each shown as l (l.from_addr)}
          <div class="row" class:dormant={l.recent30 === 0}>
            <input type="checkbox" checked={selected.has(l.from_addr)} onchange={() => toggle(l.from_addr)} />
            <div class="who"><b>{l.from_name || l.from_addr}</b><span>{l.from_addr}</span></div>
            <div class="stat"><span class="num">{l.total}</span><span class="lbl">{t("utility.total")}</span></div>
            <div class="stat"><span class="num">{ratePct(l)}</span><span class="lbl">{t("utility.readRate")}</span></div>
            <div class="stat"><span class="num">{fmtDate(l.last_seen)}</span><span class="lbl">{t("utility.lastSeen")}</span></div>
            <div class="acts">
              {#if l.unsubscribe}
                {#if isUnsubscribed(l.from_addr)}
                  <span class="unsub-done" title={t("utility.unsubscribed")}>{@html icons.done} {t("utility.unsubscribed")}</span>
                {:else}
                  <button class="btn ghost" onclick={() => doUnsub(l)}>{t("utility.unsubscribe")}</button>
                {/if}
              {/if}
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
  .filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 0 4px; }
  .seg { display: inline-flex; gap: 3px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 3px; flex-wrap: wrap; }
  .segbtn { font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 999px; color: var(--muted); }
  .segbtn:hover { color: var(--text); }
  .segbtn.on { background: var(--accent); color: #fff; }
  .find { margin-left: auto; min-width: 180px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); font-size: 13px; }
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
  .acts { display: flex; gap: 6px; align-items: center; }
  .onlyunsub { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: var(--muted); cursor: pointer; }
  .onlyunsub.on { color: var(--text); }
  .onlyunsub input { width: auto; }
  .unsub-done { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 600;
    color: var(--done); padding: 6px 10px; border-radius: 8px; background: color-mix(in srgb, var(--done) 14%, transparent); }
  .unsub-done :global(svg) { width: 14px; height: 14px; }
</style>
