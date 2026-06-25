<script>
  import { fly } from "svelte/transition";
  import { app } from "../store.svelte.js";
</script>

{#if app.toast}
  {#key app.toast.id}
    <div class="toast" class:error={app.toast.kind === "error"} transition:fly={{ y: 20, duration: 180 }}>
      {app.toast.message}
    </div>
  {/key}
{/if}

<style>
  .toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
    background: var(--surface-3); color: var(--text);
    padding: 11px 20px; border-radius: 999px; border: 1px solid var(--border);
    box-shadow: var(--shadow); z-index: 100; font-size: 13px; font-weight: 550;
  }
  .toast.error { background: #3a1f23; border-color: var(--danger); color: #ffd7da; }
</style>
