<script>
  import { fly } from "svelte/transition";
  import { app, runUndo } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
</script>

{#if app.toast}
  {#key app.toast.id}
    <div class="toast" class:error={app.toast.kind === "error"} transition:fly={{ y: 20, duration: 180 }}>
      <span>{app.toast.message}</span>
      {#if app.toast.undo}<button class="undo" onclick={runUndo}>{t("cmd.undo")}</button>{/if}
    </div>
  {/key}
{/if}

<style>
  .toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
    background: var(--surface-3); color: var(--text);
    padding: 11px 20px; border-radius: 999px; border: 1px solid var(--hairline);
    box-shadow: var(--shadow-lg); z-index: 100; font-size: 13px; font-weight: 550;
    display: flex; align-items: center; gap: 14px;
  }
  .toast.error { background: color-mix(in srgb, var(--danger) 16%, var(--surface-3)); border-color: color-mix(in srgb, var(--danger) 45%, transparent); color: color-mix(in srgb, var(--danger) 45%, var(--text)); }
  .undo { color: var(--accent); font-weight: 700; padding: 2px 8px; border-radius: 999px; transition: background var(--t-fast) var(--ease); }
  .undo:hover { background: var(--accent-soft-2); }
</style>
