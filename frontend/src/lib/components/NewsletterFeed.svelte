<script>
  import { onMount } from "svelte";
  import { messages as messagesApi } from "../api.js";
  import { app, markDone, notify } from "../store.svelte.js";
  import { sanitizeTrackers, emailDoc, escapeHtml } from "../email.js";
  import { icons } from "../icons.js";

  let items = $state([]);    // { msg, detail }
  let loading = $state(true);
  const LIMIT = 20;

  async function load() {
    loading = true;
    items = [];
    try {
      const list = await messagesApi.list({ category: "newsletters", include_done: false, limit: LIMIT });
      // Stream bodies in as they arrive so the feed fills progressively.
      for (const msg of list) {
        try {
          const detail = await messagesApi.get(msg.id);
          items = [...items, { msg, detail }];
        } catch {}
      }
    } finally { loading = false; }
  }
  onMount(load);

  function bodyDoc(detail) {
    const p = sanitizeTrackers(detail.html || "", app.settings.blockTrackers);
    return emailDoc(p.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail.text || "")}</pre>`);
  }
  function fmt(iso) { return iso ? new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" }) : ""; }

  async function doneItem(it) {
    items = items.filter((x) => x.msg.id !== it.msg.id);
    await markDone(it.msg, true);
  }
  async function doneAll() {
    const all = [...items];
    items = [];
    for (const it of all) await markDone(it.msg, true);
    notify("Cleared the feed");
  }
</script>

<section class="feed">
  <header>
    <h2>{@html icons.newspaper} Newsletter Feed</h2>
    <div class="actions">
      <button class="btn ghost" onclick={load}>Refresh</button>
      {#if items.length}<button class="btn" onclick={doneAll}>{@html icons.done} Mark all done</button>{/if}
    </div>
  </header>

  <div class="scroll">
    {#if loading && items.length === 0}
      <p class="muted">Gathering your newsletters…</p>
    {:else if items.length === 0}
      <div class="empty"><div class="big">{@html icons.mail}</div>No newsletters right now.</div>
    {/if}

    {#each items as it (it.msg.id)}
      <article class="card">
        <div class="head">
          <div class="meta">
            <b>{it.detail.from_name || it.detail.from_addr}</b>
            <span class="subj">{it.detail.subject || "(no subject)"}</span>
          </div>
          <span class="date">{fmt(it.detail.date)}</span>
          <button class="done" title="Mark done" onclick={() => doneItem(it)}>{@html icons.done}</button>
        </div>
        <iframe title={it.detail.subject} sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc={bodyDoc(it.detail)}></iframe>
      </article>
    {/each}
    {#if loading && items.length > 0}<p class="muted">Loading more…</p>{/if}
  </div>
</section>

<style>
  .feed { display: flex; flex-direction: column; min-width: 0; background: var(--bg); grid-column: 2 / -1; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); }
  h2 { margin: 0; font-size: 18px; }
  .actions { display: flex; gap: 8px; }
  .scroll { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; align-items: center; }
  .card { width: min(720px, 100%); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: flex; flex-direction: column; }
  .head { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
  .meta { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  .subj { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .date { color: var(--faint); font-size: 12px; }
  .done { width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid var(--border); color: var(--muted); }
  .done:hover { background: var(--done); border-color: var(--done); color: #06231a; }
  iframe { width: 100%; height: 420px; border: none; background: var(--bg); }
  .muted { color: var(--muted); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--muted); margin-top: 50px; }
  .empty .big { font-size: 42px; }
</style>
