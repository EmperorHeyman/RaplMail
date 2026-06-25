<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { keyCombo, comboLabel } from "../keys.js";

  const ACTIONS = [
    { id: "next", label: "Next message" },
    { id: "prev", label: "Previous message" },
    { id: "open", label: "Open message / thread" },
    { id: "done", label: "Mark done" },
    { id: "search", label: "Focus search" },
    { id: "compose", label: "Compose new message" },
    { id: "palette", label: "Command palette" },
    { id: "help", label: "Shortcut cheatsheet" },
  ];
  const DEFAULTS = { next: "ArrowDown", prev: "ArrowUp", open: "Enter", done: "e",
                     search: "/", compose: "Ctrl+n", palette: "Ctrl+k", help: "?" };

  let recording = $state(null);

  function onKey(e) {
    if (!recording) return;
    e.preventDefault();
    if (e.key === "Escape") { recording = null; return; }
    const combo = keyCombo(e);
    if (!combo) return; // wait past a lone modifier
    saveSettings({ keybinds: { ...app.settings.keybinds, [recording]: combo } });
    notify(`Bound ${comboLabel(combo)}`);
    recording = null;
  }
  function reset() { saveSettings({ keybinds: { ...DEFAULTS } }); notify("Shortcuts reset"); }
</script>

<svelte:window on:keydown={onKey} />

<div class="wrap">
  <p class="hint">
    Click a binding, then press the key (or a combo like <kbd>Ctrl+N</kbd>, <kbd>Ctrl+Shift+K</kbd>).
    Esc cancels. Single keys and modifier combos both work.
    Workspace switching stays on <kbd>Ctrl+1…9</kbd>.
  </p>
  <div class="list">
    {#each ACTIONS as a}
      <div class="row">
        <span class="label">{a.label}</span>
        <button class="key" class:recording={recording === a.id} onclick={() => (recording = a.id)}>
          {recording === a.id ? "Press a key…" : comboLabel(app.settings.keybinds[a.id])}
        </button>
      </div>
    {/each}
  </div>
  <button class="btn ghost" onclick={reset}>Reset to defaults</button>
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
