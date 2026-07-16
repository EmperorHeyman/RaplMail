<script>
  import { fly } from "svelte/transition";
  import { app, cancelSend } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
</script>

{#if app.pendingSend}
  {#key app.pendingSend}
    <div class="sending" transition:fly={{ y: 20, duration: 180 }}
      style="--dur: {app.pendingSend.delay}s; {app.settings.composePosition === 'bottom-left' ? 'left:18px;' : 'right:18px;'}">
      <div class="top">
        <span class="spin">{@html icons.sync}</span>
        <div class="txt">
          <b>{t("sending.sending")}</b>
          <span class="subj">{app.pendingSend.label}</span>
        </div>
        <button class="cancel" onclick={cancelSend}>{t("sending.cancel")}</button>
      </div>
      <div class="bar"><span class="fill"></span></div>
    </div>
  {/key}
{/if}

<style>
  .sending {
    position: fixed; bottom: 18px; z-index: 60; width: min(360px, 92vw);
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    box-shadow: var(--shadow); overflow: hidden;
  }
  .top { display: flex; align-items: center; gap: 11px; padding: 13px 15px; }
  .spin { display: inline-block; animation: spin 1s linear infinite; color: var(--accent); }
  @keyframes spin { to { transform: rotate(360deg); } }
  .txt { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  .subj { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cancel { color: var(--accent); font-weight: 600; padding: 6px 12px; border-radius: var(--radius-sm); }
  .cancel:hover { background: var(--surface-2); }
  .bar { height: 3px; background: var(--surface-3); }
  .fill { display: block; height: 100%; background: var(--accent); width: 100%; transform-origin: left;
    animation: drain var(--dur) linear forwards; }
  @keyframes drain { from { transform: scaleX(1); } to { transform: scaleX(0); } }
</style>
