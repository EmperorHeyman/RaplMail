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
    notify(t("sSnip.saved"));
  }

  // Full canned messages (subject + body), inserted from the compose "Templates" menu.
  // (Loop variables are `tpl`, not `t`, so they don't shadow the i18n t().)
  let templates = $state((app.settings.templates || []).map((tpl) => ({ ...tpl })));
  const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `t${Date.now()}${Math.random()}`);
  function addTpl() { templates = [...templates, { id: newId(), name: t("sSnip.newTemplate"), subject: "", body: "" }]; }
  function removeTpl(i) { templates = templates.filter((_, idx) => idx !== i); }
  function persistTpl() {
    const untitled = t("sSnip.untitledTemplate");
    const cleaned = templates
      .map((tpl) => ({ id: tpl.id || newId(), name: (tpl.name || "").trim() || untitled, subject: tpl.subject || "", body: tpl.body || "" }));
    saveSettings({ templates: cleaned });
    templates = cleaned.map((tpl) => ({ ...tpl }));
    notify(t("sSnip.templatesSaved"));
  }
</script>

<div class="wrap">
  <p class="lead">
    {t("sSnip.leadA")} <kbd>{t("sSnip.keySpace")}</kbd> {t("sSnip.or")} <kbd>Tab</kbd>
    {t("sSnip.leadB")} <code>{"{{first}}"}</code> {t("sSnip.varFirst")},
    <code>{"{{email}}"}</code>, <code>{"{{date}}"}</code>. {t("sSnip.htmlAllowed")}
  </p>

  {#each items as s, i}
    <div class="snip">
      <input class="short" bind:value={s.shortcut} placeholder={t("sSnip.shortcutPh")} />
      <textarea class="body" rows="2" bind:value={s.body} placeholder={t("sSnip.bodyPh")}></textarea>
      <button class="btn ghost danger" onclick={() => remove(i)}>{t("sSnip.remove")}</button>
    </div>
  {/each}

  <div class="actions">
    <button class="btn" onclick={add}>＋ {t("sSnip.addSnippet")}</button>
    <button class="btn primary" onclick={persist}>{t("common.save")}</button>
  </div>

  <hr />
  <h3>{t("sSnip.templates")}</h3>
  <p class="lead">{t("sSnip.tplLeadA")} <b>{t("sSnip.templates")}</b> {t("sSnip.tplLeadB")} <code>{"{{first}}"}</code>/<code>{"{{email}}"}</code>/<code>{"{{date}}"}</code> {t("sSnip.tplLeadC")}</p>

  {#each templates as tpl, i}
    <div class="tpl">
      <div class="tpl-row">
        <input class="tname" bind:value={tpl.name} placeholder={t("sSnip.tplNamePh")} />
        <input class="tsubj" bind:value={tpl.subject} placeholder={t("sSnip.tplSubjectPh")} />
        <button class="btn ghost danger" onclick={() => removeTpl(i)}>{t("sSnip.remove")}</button>
      </div>
      <textarea class="body" rows="3" bind:value={tpl.body} placeholder={t("sSnip.tplBodyPh")}></textarea>
    </div>
  {/each}
  <div class="actions">
    <button class="btn" onclick={addTpl}>＋ {t("sSnip.addTemplate")}</button>
    <button class="btn primary" onclick={persistTpl}>{t("sSnip.saveTemplates")}</button>
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
