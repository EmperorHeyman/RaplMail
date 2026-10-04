<script>
  import { app, saveSettings, notify, KB_DEFAULTS, kbAll } from "../store.svelte.js";
  import { keyCombo, comboLabel } from "../keys.js";
  import { t } from "../i18n.svelte.js";

  const ACTIONS = ["next", "prev", "open", "done", "reply", "forward", "archive", "delete",
                   "read", "search", "compose", "palette", "help"];
  const DEFAULTS = KB_DEFAULTS;

  let recording = $state(null);

  function onKey(e) {
    if (!recording) return;
    e.preventDefault();
    if (e.key === "Escape") { recording = null; return; }
    const combo = keyCombo(e);
    if (!combo) return; // wait past a lone modifier
    saveSettings({ keybinds: { ...kbAll(), [recording]: combo } });
    notify(t("sShort.bound", { key: comboLabel(combo) }));
    recording = null;
  }
  function reset() { saveSettings({ keybinds: { ...DEFAULTS } }); notify(t("sShort.resetDone")); }
</script>

<svelte:window on:keydown={onKey} />

<div class="wrap">
  <p class="hint">{t("sShort.intro")}</p>
  <div class="list">
    {#each ACTIONS as id}
      <div class="row">
        <span class="label">{t("sShort.a." + id)}</span>
        <button class="key" class:recording={recording === id} onclick={() => (recording = id)}>
          {recording === id ? t("sShort.pressKey") : comboLabel(kbAll()[id])}
        </button>
      </div>
    {/each}
  </div>
  <button class="btn ghost" onclick={reset}>{t("sShort.reset")}</button>

  <!-- Moved here from General: what the search key opens, and the hint bar. -->
  <section class="card">
    <h3>{t("sShort.optionsTitle")}</h3>
    <label class="inline">{t("sShort.searchOpens")}
      <select value={app.settings.searchStyle || "inline"} onchange={(e) => saveSettings({ searchStyle: e.currentTarget.value })}>
        <option value="inline">{t("sShort.searchInline")}</option>
        <option value="modal">{t("sShort.searchModal")}</option>
      </select>
    </label>
    <p class="hint" style="margin:6px 0 4px">{t("sShort.searchHint")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.listHints} onchange={(e) => saveSettings({ listHints: e.currentTarget.checked })} />
      <div><b>{t("sShort.listHints")}</b><span>{t("sShort.listHintsHint")}</span></div>
    </label>
  </section>
</div>

<style>
  .wrap { max-width: 560px; display: flex; flex-direction: column; gap: 14px; }
  .hint { color: var(--muted); font-size: 13px; line-height: 1.6; margin: 0; }
  .list { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; justify-content: space-between; padding: 11px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .label { font-size: 14px; }
  .key { min-width: 120px; padding: 6px 12px; border-radius: var(--radius-sm); background: var(--surface-3); border: 1px solid var(--border); font-family: ui-monospace, monospace; font-size: 13px; }
  .key:hover { border-color: var(--accent); }
  .key.recording { border-color: var(--accent); color: var(--accent); }
  .card { margin-top: 10px; padding: 18px 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 10px; }
  .inline { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
</style>
