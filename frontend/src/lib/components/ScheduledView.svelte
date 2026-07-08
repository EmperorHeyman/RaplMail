<script>
  import { onMount } from "svelte";
  import { compose } from "../api.js";
  import { notify } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let list = $state([]);
  let loading = $state(true);

  async function load() {
    loading = true;
    try { list = await compose.scheduled(); } finally { loading = false; }
  }
  onMount(load);

  async function cancel(s) {
    await compose.cancelScheduled(s.id);
    notify("Scheduled send cancelled");
    await load();
  }
  const fmt = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
</script>

<section class="sched">
  <header><h2>{@html icons.clock} Scheduled</h2><button class="btn ghost" onclick={load}>Refresh</button></header>
  <div class="body stagger-in">
    <div class="local-note">{@html icons.info || icons.clock}<span>{t("schedule.localOnly")}</span></div>
    {#if loading}
      <p class="muted">Loading…</p>
    {:else if list.length === 0}
      <div class="empty"><div class="big">{@html icons.clock}</div>No scheduled messages. Use “Later” in the compose window.</div>
    {:else}
      {#each list as s (s.id)}
        <div class="row">
          <div class="info">
            <b>{s.subject || "(no subject)"}</b>
            <span>to {s.to_summary} · sends {fmt(s.send_at)}</span>
          </div>
          <button class="btn ghost danger" onclick={() => cancel(s)}>Cancel</button>
        </div>
      {/each}
    {/if}
  </div>
</section>

<style>
  .sched { display: flex; flex-direction: column; min-width: 0; background: var(--bg); grid-column: 2 / -1; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); }
  h2 { margin: 0; font-size: 18px; }
  .body { padding: 20px 24px; overflow-y: auto; max-width: 760px; }
  .local-note { display: flex; gap: 9px; align-items: flex-start; margin-bottom: 16px; padding: 11px 13px;
    background: color-mix(in srgb, var(--warning) 10%, transparent); border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border));
    border-radius: var(--radius-sm); font-size: 12.5px; line-height: 1.5; color: var(--text); }
  .local-note :global(svg) { width: 16px; height: 16px; flex: none; margin-top: 1px; color: var(--warning); }
  .row { display: flex; align-items: center; gap: 12px; padding: 13px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 8px; }
  .info { flex: 1; display: flex; flex-direction: column; }
  .info span { color: var(--muted); font-size: 12px; }
  .muted { color: var(--muted); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--muted); margin-top: 50px; }
  .empty .big { font-size: 42px; }
</style>
