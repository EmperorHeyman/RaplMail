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

  // Full canned messages (subject + body), inserted from the compose "Templates" menu.
  let templates = $state((app.settings.templates || []).map((t) => ({ ...t })));
  const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `t${Date.now()}${Math.random()}`);
  function addTpl() { templates = [...templates, { id: newId(), name: "New template", subject: "", body: "" }]; }
  function removeTpl(i) { templates = templates.filter((_, idx) => idx !== i); }
  function persistTpl() {
    const cleaned = templates
      .map((t) => ({ id: t.id || newId(), name: (t.name || "").trim() || "Template", subject: t.subject || "", body: t.body || "" }));
    saveSettings({ templates: cleaned });
    templates = cleaned.map((t) => ({ ...t }));
    notify("Templates saved");
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

  <hr />
  <h3>Templates</h3>
  <p class="lead">Full canned messages (subject + body) you can drop into a new mail from the compose <b>Templates</b> menu. Same <code>{"{{first}}"}</code>/<code>{"{{email}}"}</code>/<code>{"{{date}}"}</code> variables apply.</p>

  {#each templates as t, i}
    <div class="tpl">
      <div class="tpl-row">
        <input class="tname" bind:value={t.name} placeholder="Template name" />
        <input class="tsubj" bind:value={t.subject} placeholder="Subject (optional)" />
        <button class="btn ghost danger" onclick={() => removeTpl(i)}>Remove</button>
      </div>
      <textarea class="body" rows="3" bind:value={t.body} placeholder="Body (HTML allowed)…"></textarea>
    </div>
  {/each}
  <div class="actions">
    <button class="btn" onclick={addTpl}>＋ Add template</button>
    <button class="btn primary" onclick={persistTpl}>Save templates</button>
  </div>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 12px; }
  .lead { color: var(--muted); font-size: 13px; line-height: 1.7; margin: 0 0 6px; }
  .lead code { background: var(--surface-2); padding: 1px 6px; border-radius: 5px; font-size: 12px; }
  kbd { background: var(--surface-3); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; }
  .snip { display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .short { flex: 0 0 140px; font-family: ui-monospace, monospace; }
  .body { flex: 1; resize: vertical; width: 100%; }
  .actions { display: flex; gap: 10px; }
  hr { border: none; border-top: 1px solid var(--border); margin: 18px 0 4px; }
  h3 { margin: 0; }
  .tpl { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .tpl-row { display: flex; gap: 10px; }
  .tname { flex: 0 0 200px; }
  .tsubj { flex: 1; }
</style>
