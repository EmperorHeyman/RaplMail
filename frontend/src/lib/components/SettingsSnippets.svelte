<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";

  let items = $state(app.settings.snippets.map((s) => ({ ...s })));

  function add() { items = [...items, { shortcut: ";new", body: "" }]; }
  function remove(i) { items = items.filter((_, idx) => idx !== i); }
  function persist() {
    const cleaned = items
      .map((s) => ({ shortcut: s.shortcut.trim(), body: s.body }))
      .filter((s) => s.shortcut);
    saveSettings({ snippets: cleaned });
    items = cleaned.map((s) => ({ ...s }));
    notify(t("setsnip.saved"));
  }

  // Full canned messages (subject + body), inserted from the compose "Templates" menu.
  let templates = $state((app.settings.templates || []).map((tp) => ({ ...tp })));
  const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `t${Date.now()}${Math.random()}`);
  function addTpl() { templates = [...templates, { id: newId(), name: t("setsnip.newTemplate"), subject: "", body: "" }]; }
  function removeTpl(i) { templates = templates.filter((_, idx) => idx !== i); }
  function persistTpl() {
    const cleaned = templates
      .map((tp) => ({ id: tp.id || newId(), name: (tp.name || "").trim() || t("setsnip.tplFallback"), subject: tp.subject || "", body: tp.body || "" }));
    saveSettings({ templates: cleaned });
    templates = cleaned.map((tp) => ({ ...tp }));
    notify(t("setsnip.tplSaved"));
  }
</script>

<div class="wrap">
  <p class="lead">
    {t("setsnip.lead1")} <kbd>space</kbd> {t("setsnip.leadOr")} <kbd>Tab</kbd>
    {t("setsnip.lead2")} <code>{"{{first}}"}</code> {t("setsnip.leadFirst")}
    <code>{"{{email}}"}</code>, <code>{"{{date}}"}</code>{t("setsnip.leadEnd")}
  </p>

  {#each items as s, i}
    <div class="snip">
      <input class="short" bind:value={s.shortcut} placeholder={t("setsnip.shortcutPh")} />
      <textarea class="body" rows="2" bind:value={s.body} placeholder={t("setsnip.bodyPh")}></textarea>
      <button class="btn ghost danger" onclick={() => remove(i)}>{t("setsnip.remove")}</button>
    </div>
  {/each}

  <div class="actions">
    <button class="btn" onclick={add}>＋ {t("setsnip.addSnippet")}</button>
    <button class="btn primary" onclick={persist}>{t("setsnip.save")}</button>
  </div>

  <hr />
  <h3>{t("setsnip.templates")}</h3>
  <p class="lead">{t("setsnip.tplLead1")} <b>{t("setsnip.templates")}</b> {t("setsnip.tplLead2")} <code>{"{{first}}"}</code>/<code>{"{{email}}"}</code>/<code>{"{{date}}"}</code>{t("setsnip.tplLead3")}</p>

  {#each templates as tp, i}
    <div class="tpl">
      <div class="tpl-row">
        <input class="tname" bind:value={tp.name} placeholder={t("setsnip.tplNamePh")} />
        <input class="tsubj" bind:value={tp.subject} placeholder={t("setsnip.tplSubjPh")} />
        <button class="btn ghost danger" onclick={() => removeTpl(i)}>{t("setsnip.remove")}</button>
      </div>
      <textarea class="body" rows="3" bind:value={tp.body} placeholder={t("setsnip.tplBodyPh")}></textarea>
    </div>
  {/each}
  <div class="actions">
    <button class="btn" onclick={addTpl}>＋ {t("setsnip.addTemplate")}</button>
    <button class="btn primary" onclick={persistTpl}>{t("setsnip.saveTemplates")}</button>
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
