<script>
  // Shown when the user tries to open an attachment the backend flagged as
  // risky. Offers the safe path (open in the WebAssembly sandbox) prominently,
  // and gates the risky "open anyway" behind a short countdown so a reflexive
  // click can't run a disguised executable.
  import { fly, fade } from "svelte/transition";
  import { onMount, onDestroy } from "svelte";
  import { t } from "../i18n.svelte.js";
  import { icons } from "../icons.js";

  let { att, onclose } = $props();

  const risk = att?.risk || "medium";
  const reasons = att?.risk_reasons || [];
  const typeGuess = att?.type_guess || "";

  let countdown = $state(3);
  let timer = null;
  onMount(() => {
    timer = setInterval(() => {
      countdown -= 1;
      if (countdown <= 0) { clearInterval(timer); timer = null; }
    }, 1000);
  });
  onDestroy(() => { if (timer) clearInterval(timer); });
</script>

<div class="scrim" transition:fade={{ duration: 120 }} onclick={() => onclose?.("cancel")}>
  <div class="modal risk-{risk}" transition:fly={{ y: 14, duration: 160 }} onclick={(e) => e.stopPropagation()}>
    <header>
      <div class="ic">{@html icons.warning || ""}</div>
      <div>
        <h3>{t("threat.title")}</h3>
        <p class="fn">{att?.filename}</p>
      </div>
    </header>

    <p class="lead">{risk === "high" ? t("threat.leadHigh") : t("threat.leadMedium")}</p>

    {#if typeGuess}
      <p class="type">{t("threat.actuallyIs", { type: typeGuess })}</p>
    {/if}

    {#if reasons.length}
      <ul class="reasons">
        {#each reasons as r}<li>{r}</li>{/each}
      </ul>
    {/if}

    <div class="acts">
      <button class="btn" onclick={() => onclose?.("cancel")}>{t("threat.cancel")}</button>
      <div class="sp"></div>
      <button class="btn danger" disabled={countdown > 0} onclick={() => onclose?.("open")}>
        {countdown > 0 ? t("threat.openIn", { n: countdown }) : t("threat.openAnyway")}
      </button>
      <button class="btn primary" onclick={() => onclose?.("sandbox")}>{t("threat.openSandbox")}</button>
    </div>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; background: rgba(0,0,0,0.5); backdrop-filter: blur(2px); z-index: 320; display: flex; align-items: center; justify-content: center; padding: 24px; }
  .modal { width: min(480px, 96vw); background: var(--surface); border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); padding: 20px 22px 18px; }
  header { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 12px; }
  .ic { width: 36px; height: 36px; border-radius: 9px; flex: none; display: grid; place-items: center; background: color-mix(in srgb, var(--danger, #e5484d) 18%, transparent); color: var(--danger, #e5484d); }
  .risk-medium .ic { background: color-mix(in srgb, #e6a23c 20%, transparent); color: #b8801f; }
  .ic :global(svg) { width: 19px; height: 19px; }
  header h3 { margin: 0; font-size: 15px; }
  .fn { margin: 3px 0 0; color: var(--muted); font-size: 12.5px; word-break: break-all; }
  .lead { margin: 0 0 8px; font-size: 13px; }
  .type { margin: 0 0 10px; font-size: 12.5px; font-weight: 600; color: var(--danger, #e5484d); }
  .reasons { margin: 0 0 14px; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; }
  .reasons li { font-size: 12.5px; color: var(--text); }
  .acts { display: flex; align-items: center; gap: 8px; }
  .acts .sp { flex: 1; }
  .btn.danger { background: transparent; color: var(--danger, #e5484d); border: 1px solid color-mix(in srgb, var(--danger, #e5484d) 45%, transparent); }
  .btn.danger:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.danger:not(:disabled):hover { background: color-mix(in srgb, var(--danger, #e5484d) 12%, transparent); }
</style>
