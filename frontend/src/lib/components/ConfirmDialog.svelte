<script>
  import { app, resolveConfirm } from "../store.svelte.js";

  const c = $derived(app.confirm);
  // Capture-phase listener while the dialog is up: Enter/Escape must resolve
  // the dialog ONLY - without this, the mail list's window listener also saw
  // the keystroke (Enter opened the focused message behind the veil).
  $effect(() => {
    if (!c) return;
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); resolveConfirm(false); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopImmediatePropagation(); resolveConfirm(true); }
      else { e.stopImmediatePropagation(); }  // swallow e/j/k/etc. too
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  });
</script>

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
    backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center;
    animation: fade-in var(--t) var(--ease); }
  .box { width: min(420px, 92vw); background: var(--surface); border: 1px solid var(--hairline);
    border-radius: var(--radius); box-shadow: var(--shadow-lg); padding: 20px 22px;
    animation: pop-in var(--t) var(--ease); }
  .title { font-size: 16px; letter-spacing: -0.01em; }
  .msg { margin: 8px 0 18px; color: var(--muted); font-size: 13px; line-height: 1.55; }
  .btns { display: flex; justify-content: flex-end; gap: 10px; }
  .btn.primary.danger { background: var(--danger); border-color: var(--danger); color: #fff; }
</style>
