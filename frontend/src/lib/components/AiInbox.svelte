<script>
  import { onMount } from "svelte";
  import { app, notify, openMessageById } from "../store.svelte.js";
  import { ai } from "../api.js";
  import { icons } from "../icons.js";

  let tab = $state("digest");      // "digest" | "priority"
  let loading = $state(false);
  let digest = $state("");
  let scores = $state(null);       // [{id, score, reason}]

  async function loadDigest(force = false) {
    // Prefer a freshly-pushed scheduled briefing if we have one.
    if (!force && app.aiDigest) { digest = app.aiDigest; return; }
    loading = true;
    try { const r = await ai.digest(); digest = r.digest || "(empty)"; app.aiDigest = ""; }
    catch (e) { notify(e.message, "error"); close(); }
    finally { loading = false; }
  }
  async function loadPriority() {
    loading = true; scores = null;
    try { const r = await ai.triage(25); scores = (r.scores || []).slice().sort((a, b) => (b.score || 0) - (a.score || 0)); }
    catch (e) { notify(e.message, "error"); }
    finally { loading = false; }
  }
  function pick(t) { tab = t; if (t === "digest" && !digest) loadDigest(); if (t === "priority" && !scores) loadPriority(); }
  function close() { app.aiInboxOpen = false; }
  function open(id) { close(); openMessageById?.(id); }
  function band(s) { return s >= 70 ? "hi" : s >= 40 ? "mid" : "lo"; }

  onMount(loadDigest);
</script>

<div class="overlay" onclick={close} role="presentation">
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="AI inbox assistant">
    <header>
      <h2>{@html icons.bolt} Inbox assistant</h2>
      <div class="tabs">
        <button class:active={tab === "digest"} onclick={() => pick("digest")}>Catch me up</button>
        <button class:active={tab === "priority"} onclick={() => pick("priority")}>Prioritize</button>
      </div>
      <button class="x" onclick={close} aria-label="Close">{@html icons.close}</button>
    </header>

    <div class="body">
      {#if loading}
        <div class="muted">Asking the model…</div>
      {:else if tab === "digest"}
        <pre class="digest">{digest}</pre>
      {:else if scores && scores.length}
        <div class="scores">
          {#each scores as s}
            <button class="srow" onclick={() => open(s.id)}>
              <span class="score {band(s.score)}">{s.score}</span>
              <span class="reason">{s.reason || ""}</span>
              <span class="go">{@html icons.chevronRight || "›"}</span>
            </button>
          {/each}
        </div>
      {:else}
        <div class="muted">No unread mail to prioritize. 🎉</div>
      {/if}
    </div>
    <footer>
      <span class="hint">{@html icons.bolt} Runs on your configured AI provider · nothing is sent automatically</span>
      <button class="btn ghost" onclick={() => (tab === "digest" ? loadDigest(true) : loadPriority())} disabled={loading}>↻ Refresh</button>
    </footer>
  </div>
</div>

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: grid; place-items: center; z-index: 200; }
  .dialog { width: min(680px, 94vw); max-height: 86vh; display: flex; flex-direction: column; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: 0 24px 60px rgba(0,0,0,0.45); overflow: hidden; }
  header { display: flex; align-items: center; gap: 14px; padding: 14px 18px; border-bottom: 1px solid var(--border); }
  header h2 { margin: 0; font-size: 16px; display: flex; align-items: center; gap: 9px; }
  .tabs { display: flex; gap: 4px; }
  .tabs button { padding: 5px 12px; border-radius: 999px; color: var(--muted); font-size: 13px; font-weight: 550; }
  .tabs button.active { background: var(--surface-2); color: var(--text); }
  .x { margin-left: auto; color: var(--muted); display: inline-flex; }
  .x:hover { color: var(--text); }
  .body { padding: 18px; overflow: auto; }
  .muted { color: var(--muted); }
  .digest { white-space: pre-wrap; font: 13px/1.6 system-ui, sans-serif; color: var(--text); margin: 0; }
  .scores { display: flex; flex-direction: column; gap: 4px; }
  .srow { display: flex; align-items: center; gap: 12px; width: 100%; padding: 8px 10px; border-radius: var(--radius-sm); text-align: left; }
  .srow:hover { background: var(--surface-2); }
  .score { flex: none; width: 38px; text-align: center; font-weight: 700; font-size: 13px; padding: 3px 0; border-radius: 6px; }
  .score.hi { background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); }
  .score.mid { background: color-mix(in srgb, var(--warning, #d2a000) 20%, transparent); color: var(--warning, #d2a000); }
  .score.lo { background: var(--surface-3); color: var(--muted); }
  .reason { flex: 1; font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .go { color: var(--faint); }
  footer { display: flex; align-items: center; gap: 10px; padding: 11px 18px; border-top: 1px solid var(--border); }
  footer .hint { margin-right: auto; color: var(--muted); font-size: 11px; display: inline-flex; align-items: center; gap: 6px; }
</style>
