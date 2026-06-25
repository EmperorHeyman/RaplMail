<script>
  import { app, saveSettings, notify } from "../store.svelte.js";

  let items = $state(app.settings.snippets.map((s) => ({ ...s })));

  function add() { items = [...items, { shortcut: ";new", body: "" }]; }
  function remove(i) { items = items.filter((_, idx) => idx !== i); }
  function persist() {
    const cleaned = items
      .map((s) => ({ shortcut: s.shortcut.trim(), body: s.body }))
      .filter((s) => s.shortcut);
    saveSettings({ snippets: cleaned });
    items = cleaned.map((s) => ({ ...s }));
    notify("Snippets saved");
  }
</script>

<div class="wrap">
  <p class="lead">
    Type a shortcut in the compose window followed by <kbd>space</kbd> or <kbd>Tab</kbd> and it
    expands. Use variables: <code>{"{{first}}"}</code> (recipient's first name),
    <code>{"{{email}}"}</code>, <code>{"{{date}}"}</code>. HTML is allowed.
  </p>

  {#each items as s, i}
    <div class="snip">
      <input class="short" bind:value={s.shortcut} placeholder=";shortcut" />
      <textarea class="body" rows="2" bind:value={s.body} placeholder="Expansion (HTML allowed)…"></textarea>
      <button class="btn ghost danger" onclick={() => remove(i)}>Remove</button>
    </div>
  {/each}

  <div class="actions">
    <button class="btn" onclick={add}>＋ Add snippet</button>
    <button class="btn primary" onclick={persist}>Save</button>
  </div>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 12px; }
  .lead { color: var(--muted); font-size: 13px; line-height: 1.7; margin: 0 0 6px; }
  .lead code { background: var(--surface-2); padding: 1px 6px; border-radius: 5px; font-size: 12px; }
  kbd { background: var(--surface-3); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; }
  .snip { display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .short { flex: 0 0 140px; font-family: ui-monospace, monospace; }
  .body { flex: 1; resize: vertical; }
  .actions { display: flex; gap: 10px; }
</style>
