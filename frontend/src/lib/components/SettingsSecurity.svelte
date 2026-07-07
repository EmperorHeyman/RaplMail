<script>
  import { app, saveSettings, refreshVault, notify, aiEnabled } from "../store.svelte.js";
  import { vault } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import SecurityLab from "./SecurityLab.svelte";

  const set = (patch) => saveSettings(patch);

  // --- domain blocker ------------------------------------------------------
  const blocked = $derived(Array.isArray(app.settings.blockedDomains) ? app.settings.blockedDomains : []);
  let newDomain = $state("");
  // Match the backend's normalize: lowercase, drop a leading @ / dot, trim.
  function normDomain(d) {
    return (d || "").trim().toLowerCase().replace(/^@/, "").replace(/^\.+/, "").replace(/\.+$/, "");
  }
  function addDomain() {
    const d = normDomain(newDomain);
    if (!d) return;
    if (blocked.includes(d)) { notify(t("security.domainDupe"), "error"); newDomain = ""; return; }
    set({ blockedDomains: [...blocked, d] });
    newDomain = "";
  }
  function removeDomain(d) {
    set({ blockedDomains: blocked.filter((x) => x !== d) });
  }

  // --- AI screening mode ---------------------------------------------------
  const aiOn = $derived(aiEnabled());
  const aiMode = $derived(app.settings.aiScreen || "off");
  const AI_MODES = $derived.by(() => [
    { id: "off", label: t("security.aiOff"), hint: t("security.aiOffHint") },
    { id: "manual", label: t("security.aiManual"), hint: t("security.aiManualHint") },
    { id: "auto", label: t("security.aiAuto"), hint: t("security.aiAutoHint") },
  ]);

  // --- startup password (moved from General) -------------------------------
  let autoPw = $state("");
  let showAutoPw = $state(false);
  let busy = $state(false);
  async function enableAuto() {
    if (!autoPw) { notify(t("security.enterPwToConfirm"), "error"); return; }
    busy = true;
    try {
      await vault.setAutoUnlock(true, autoPw);
      await refreshVault();
      autoPw = ""; showAutoPw = false;
      notify(t("security.startupOff"));
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
  }
  async function disableAuto() {
    busy = true;
    try {
      await vault.setAutoUnlock(false);
      await refreshVault();
      notify(t("security.startupOn"));
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
  }
</script>

<div class="wrap">
  <h2 class="group-head">{t("security.labGroup")}</h2>
  <SecurityLab />

  <h2 class="group-head">{t("security.screenGroup")}</h2>

  <section class="card">
    <h3>{t("security.phishingTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.phishingScreen !== false}
        onchange={(e) => set({ phishingScreen: e.currentTarget.checked })} />
      <div><b>{t("security.phishingToggle")}</b><span>{t("security.phishingHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("security.domainTitle")}</h3>
    <p class="hint">{t("security.domainHint")}</p>
    <div class="adder">
      <input type="text" bind:value={newDomain} placeholder={t("security.domainPlaceholder")}
        onkeydown={(e) => { if (e.key === "Enter") addDomain(); }} />
      <button class="btn primary" onclick={addDomain}>{@html icons.shield} {t("security.domainAdd")}</button>
    </div>
    {#if blocked.length}
      <div class="chips">
        {#each blocked as d}
          <span class="chip">
            {d}
            <button class="x" title={t("security.domainRemove", { domain: d })} onclick={() => removeDomain(d)}>{@html icons.close}</button>
          </span>
        {/each}
      </div>
    {:else}
      <p class="hint empty">{t("security.domainEmpty")}</p>
    {/if}
    <p class="hint note">{@html icons.rules} {t("security.rulesNote")}</p>
  </section>

  <section class="card">
    <h3>{t("security.aiTitle")}</h3>
    <p class="hint">{t("security.aiHint")}</p>
    {#if !aiOn}
      <p class="hint warn-note">{@html icons.warning} {t("security.aiUnavailable")}</p>
    {/if}
    <div class="modes" class:disabled={!aiOn}>
      {#each AI_MODES as m}
        <label class="radio">
          <input type="radio" name="aiScreen" value={m.id} checked={aiMode === m.id}
            disabled={!aiOn && m.id !== "off"}
            onchange={() => set({ aiScreen: m.id })} />
          <div><b>{m.label}</b><span>{m.hint}</span></div>
        </label>
      {/each}
    </div>
    <p class="disclaimer">{@html icons.warning} {t("security.aiDisclaimer")}</p>
  </section>

  <h2 class="group-head">{t("security.privacyGroup")}</h2>
  <section class="card">
    <label class="check">
      <input type="checkbox" checked={app.settings.blockTrackers}
        onchange={(e) => set({ blockTrackers: e.currentTarget.checked })} />
      <div><b>{t("security.trackToggle")}</b><span>{t("security.trackHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.screener}
        onchange={(e) => set({ screener: e.currentTarget.checked })} />
      <div><b>{t("security.screenerToggle")}</b><span>{t("security.screenerHint")}</span></div>
    </label>
  </section>

  <h2 class="group-head">{t("security.startupGroup")}</h2>
  <section class="card">
    {#if app.vault.auto_unlock}
      <p class="hint ok">{@html icons.done} {t("security.startupAuto")}</p>
      <button class="btn" onclick={disableAuto} disabled={busy}>{t("security.startupRequireAgain")}</button>
    {:else}
      <p class="hint">{t("security.startupDefault")}</p>
      {#if !showAutoPw}
        <button class="btn" onclick={() => (showAutoPw = true)}>{t("security.startupDisable")}</button>
      {:else}
        <div class="warn">{@html icons.warning} {t("security.startupWarn")}</div>
        <div class="confirm">
          <input type="password" placeholder={t("security.startupConfirm")} bind:value={autoPw}
            onkeydown={(e) => e.key === "Enter" && enableAuto()} />
          <button class="btn primary" onclick={enableAuto} disabled={busy}>{busy ? "…" : t("security.startupEnable")}</button>
          <button class="btn ghost" onclick={() => { showAutoPw = false; autoPw = ""; }}>{t("common.cancel")}</button>
        </div>
      {/if}
    {/if}
  </section>
</div>

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .group-head { margin: 8px 0 -6px; font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--faint); }
  .group-head:first-child { margin-top: 0; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
  .hint.ok { color: var(--done); }
  .hint.empty { margin: 4px 0 0; font-style: italic; }
  .hint.note { display: flex; align-items: center; gap: 6px; margin: 12px 0 0; }
  .hint.note :global(svg) { width: 14px; height: 14px; flex: none; }
  .warn-note { display: flex; align-items: flex-start; gap: 7px; color: var(--warning); }
  .warn-note :global(svg) { width: 15px; height: 15px; flex: none; margin-top: 1px; }
  .check, .radio { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .check div, .radio div { display: flex; flex-direction: column; gap: 2px; }
  .check span, .radio span { color: var(--muted); font-size: 12px; }
  .check input, .radio input { margin-top: 3px; }

  .adder { display: flex; gap: 8px; align-items: center; }
  .adder input { flex: 1; min-width: 0; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 11px; color: var(--text); font-size: 13px; }
  .adder input:focus { border-color: var(--accent); outline: none; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 13px; border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--surface-2); font-size: 13px; font-weight: 600; color: var(--text); flex: none; }
  .btn:hover { border-color: var(--accent); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn :global(svg) { width: 14px; height: 14px; }

  .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 6px 4px 11px; border-radius: 999px;
    background: var(--danger-soft); color: var(--danger); border: 1px solid color-mix(in srgb, var(--danger) 32%, transparent);
    font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .chip .x { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
    border-radius: 50%; color: inherit; opacity: 0.7; }
  .chip .x:hover { opacity: 1; background: color-mix(in srgb, var(--danger) 20%, transparent); }
  .chip .x :global(svg) { width: 11px; height: 11px; }

  .modes.disabled { opacity: 0.55; }
  .disclaimer { display: flex; align-items: flex-start; gap: 7px; margin: 12px 0 0; padding: 10px 12px;
    background: color-mix(in srgb, var(--warning) 12%, var(--surface)); border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--border));
    border-radius: var(--radius-sm); color: var(--text); font-size: 12px; line-height: 1.5; }
  .disclaimer :global(svg) { width: 15px; height: 15px; flex: none; color: var(--warning); margin-top: 1px; }

  .warn { display: flex; align-items: flex-start; gap: 8px; padding: 11px 13px; margin: 4px 0 12px;
    background: color-mix(in srgb, var(--warning) 12%, var(--surface)); border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--border));
    border-radius: var(--radius-sm); color: var(--text); font-size: 12.5px; line-height: 1.5; }
  .warn :global(svg) { width: 16px; height: 16px; flex: none; color: var(--warning); margin-top: 1px; }
  .confirm { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .confirm input { flex: 1; min-width: 180px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 11px; color: var(--text); font-size: 13px; }
</style>
