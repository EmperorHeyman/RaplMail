<script>
  import { saveSettings, notify, KB_DEFAULTS, kbAll } from "../store.svelte.js";
  import { keyCombo, comboLabel } from "../keys.js";
  import { t } from "../i18n.svelte.js";

  // Labels are i18n keys, resolved with t() at render time.
  const ACTIONS = [
    { id: "next", label: "setkeys.actNext" },
    { id: "prev", label: "setkeys.actPrev" },
    { id: "open", label: "setkeys.actOpen" },
    { id: "done", label: "setkeys.actDone" },
    { id: "reply", label: "setkeys.actReply" },
    { id: "forward", label: "setkeys.actForward" },
    { id: "archive", label: "setkeys.actArchive" },
    { id: "delete", label: "setkeys.actDelete" },
    { id: "read", label: "setkeys.actRead" },
    { id: "search", label: "setkeys.actSearch" },
    { id: "compose", label: "setkeys.actCompose" },
    { id: "palette", label: "setkeys.actPalette" },
    { id: "help", label: "setkeys.actHelp" },
  ];
  const DEFAULTS = KB_DEFAULTS;

  let recording = $state(null);

  function onKey(e) {
    if (!recording) return;
    e.preventDefault();
    if (e.key === "Escape") { recording = null; return; }
    const combo = keyCombo(e);
    if (!combo) return; // wait past a lone modifier
    saveSettings({ keybinds: { ...kbAll(), [recording]: combo } });
    notify(t("setkeys.bound", { combo: comboLabel(combo) }));
    recording = null;
  }
  function reset() { saveSettings({ keybinds: { ...DEFAULTS } }); notify(t("setkeys.resetDone")); }
</script>

<svelte:window on:keydown={onKey} />

<div class="wrap">
  <p class="hint">
    {t("setkeys.hint1")} <kbd>Ctrl+N</kbd>, <kbd>Ctrl+Shift+K</kbd>{t("setkeys.hint2")} <kbd>Ctrl+1…9</kbd>.
  </p>
  <div class="list">
    {#each ACTIONS as a}
      <div class="row">
        <span class="label">{t(a.label)}</span>
        <button class="key" class:recording={recording === a.id} onclick={() => (recording = a.id)}>
          {recording === a.id ? t("setkeys.pressKey") : comboLabel(kbAll()[a.id])}
        </button>
      </div>
    {/each}
  </div>
  <button class="btn ghost" onclick={reset}>{t("setkeys.resetBtn")}</button>
</div>

<style>
  .wrap { max-width: 560px; display: flex; flex-direction: column; gap: 14px; }
  .hint { color: var(--muted); font-size: 13px; line-height: 1.7; margin: 0; }
  kbd { background: var(--surface-3); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; }
  .list { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; justify-content: space-between; padding: 11px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .label { font-size: 14px; }
  .key { min-width: 120px; padding: 6px 12px; border-radius: var(--radius-sm); background: var(--surface-3); border: 1px solid var(--border); font-family: ui-monospace, monospace; font-size: 13px; }
  .key:hover { border-color: var(--accent); }
  .key.recording { border-color: var(--accent); color: var(--accent); }
</style>
