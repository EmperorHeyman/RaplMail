<script>
  import { app, resolveConfirm } from "../store.svelte.js";

  const c = $derived(app.confirm);
  function onKey(e) {
    if (!c) return;
    if (e.key === "Escape") resolveConfirm(false);
    else if (e.key === "Enter") resolveConfirm(true);
  }
</script>

<svelte:window on:keydown={onKey} />

{#if c}
  <div class="veil" role="presentation" onclick={() => resolveConfirm(false)}>
    <div class="box" role="dialog" aria-modal="true" aria-label={c.title} onclick={(e) => e.stopPropagation()}>
      <b class="title">{c.title}</b>
      {#if c.message}<p class="msg">{c.message}</p>{/if}
      <div class="btns">
        <button class="btn ghost" onclick={() => resolveConfirm(false)}>{c.cancelLabel}</button>
        <button class="btn primary" class:danger={c.danger} onclick={() => resolveConfirm(true)}>{c.confirmLabel}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .veil { position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,0.5);
    display: flex; align-items: center; justify-content: center; }
  .box { width: min(420px, 92vw); background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 22px; }
  .title { font-size: 16px; }
  .msg { margin: 8px 0 18px; color: var(--muted); font-size: 13px; line-height: 1.55; }
  .btns { display: flex; justify-content: flex-end; gap: 10px; }
  .btn.primary.danger { background: var(--danger); border-color: var(--danger); color: #fff; }
</style>
