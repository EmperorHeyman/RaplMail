<script>
  import { fly } from "svelte/transition";
  import { app, runUndo } from "../store.svelte.js";
</script>

{#if app.toast}
  {#key app.toast.id}
    <div class="toast" class:error={app.toast.kind === "error"} transition:fly={{ y: 20, duration: 180 }}>
      <span>{app.toast.message}</span>
      {#if app.toast.undo}<button class="undo" onclick={runUndo}>Undo</button>{/if}
    </div>
  {/key}
{/if}

<style>
  .toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
    background: var(--surface-3); color: var(--text);
    padding: 11px 20px; border-radius: 999px; border: 1px solid var(--border);
    box-shadow: var(--shadow); z-index: 100; font-size: 13px; font-weight: 550;
    display: flex; align-items: center; gap: 14px;
  }
  .toast.error { background: #3a1f23; border-color: var(--danger); color: #ffd7da; }
  .undo { color: var(--accent); font-weight: 700; padding: 2px 6px; border-radius: 6px; }
  .undo:hover { background: var(--surface-2); }
</style>
