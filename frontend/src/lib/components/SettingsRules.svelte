<script>
  import { onMount } from "svelte";
  import { app, notify, refreshMessages, categoryLabel, groupArgFor } from "../store.svelte.js";
  import { rules as api } from "../api.js";
  import { t } from "../i18n.svelte.js";
  import GroupPicker from "./GroupPicker.svelte";

  let list = $state([]);
  let preview = $state(null);
  // Prefill from a "Create rule…" context-menu action if present.
  let draft = $state(app.ruleDraft ? { ...app.ruleDraft } : newDraft());
  if (app.ruleDraft) app.ruleDraft = null;

  function newDraft() {
    return { name: "", match_field: "from_domain", match_op: "ends_with", match_value: "",
             action: "move", action_arg: "Archive", enabled: true, order: 0 };
  }

  const FIELDS = ["from_domain", "from", "to", "subject", "body", "category"];
  const OPS = ["contains", "equals", "ends_with", "regex"];
  const ACTIONS = ["move", "set_group", "archive", "delete", "mark_read", "mark_done", "block", "mute_notifications", "webhook", "run_script", "save_attachments"];

  async function load() { list = await api.list(); }
  onMount(load);

  async function runPreview() {
    try { preview = await api.preview(draft); } catch (e) { notify(e.message, "error"); }
  }
  const DESTRUCTIVE = new Set(["delete", "archive", "block"]);
  let lastAction = draft.action;
  function onActionChange() {
    draft.action_arg = groupArgFor(lastAction, draft.action, draft.action_arg);
    lastAction = draft.action;
  }
  async function create() {
    if (draft.action === "set_group" && !draft.action_arg) { notify(t("groups.pickFirst"), "error"); return; }
    // Catch an invalid regex before it silently never-matches (or errors per-message).
    if (draft.match_op === "regex") {
      try { new RegExp(draft.match_value); }
      catch (e) { notify(t("sRules.invalidRegex", { error: e.message }), "error"); return; }
    }
    // Destructive rules (delete/archive/block) get a blast-radius confirm so a
    // catch-all like `from_domain ends_with ".com"` can't quietly nuke the inbox.
    if (DESTRUCTIVE.has(draft.action)) {
      let count = preview?.match_count;
      try { const p = await api.preview(draft); preview = p; count = p.match_count; } catch {}
      const verb = t("rules.action." + draft.action).toLowerCase();
      if (count != null &&
          !confirm(t("sRules.confirmDestructive", { verb, n: count }))) {
        return;
      }
    }
    try {
      await api.create(draft);
      // Also apply to mail already in the box (rules otherwise only run on new mail).
      let applied = 0;
      try { applied = (await api.apply(draft)).applied || 0; } catch {}
      notify(applied ? t("sRules.savedApplied", { n: applied }) : t("sRules.saved"));
      if (applied) refreshMessages({ background: true });
      draft = newDraft(); lastAction = draft.action; preview = null; await load();
    }
    catch (e) { notify(e.message, "error"); }
  }
  // A group rule's mail is re-filed server-side on toggle/delete, so refresh.
  async function remove(r) { await api.remove(r.id); await load(); if (r.action === "set_group") refreshMessages({ background: true }); }
  async function toggle(r) { await api.update(r.id, { ...r, enabled: !r.enabled }); await load(); if (r.action === "set_group") refreshMessages({ background: true }); }
  function argLabel(r) {
    if (r.action === "set_group") return r.action_arg ? ` (${categoryLabel(r.action_arg)})` : "";
    return ["move", "webhook", "run_script"].includes(r.action) && r.action_arg ? ` (${r.action_arg})` : "";
  }

  const needsArg = $derived(["move", "webhook", "run_script", "save_attachments"].includes(draft.action));
  const argPlaceholder = $derived(
    draft.action === "webhook" ? t("rules.webhookHint")
      : draft.action === "run_script" ? t("rules.scriptHint")
      : draft.action === "save_attachments" ? t("rules.saveDirHint")
      : t("sRules.folderPh")
  );
</script>

<div class="wrap">
  <section>
    <h3>{t("sRules.yourRules")}</h3>
    {#if list.length === 0}<p class="muted">{t("sRules.empty")}</p>{/if}
    <div class="rules">
      {#each list as r (r.id)}
        <div class="rule" class:off={!r.enabled}>
          <button class="toggle" class:on={r.enabled} onclick={() => toggle(r)} title={t("sRules.toggleTip")} aria-label={r.enabled ? t("common.enabled") : t("common.disabled")}><span class="dot"></span></button>
          <div class="desc">
            <b>{r.name || t("sRules.untitled")}</b>
            <span>{t("sRules.summary", { field: t("rules.field." + r.match_field), op: t("rules.op." + r.match_op), action: t("rules.action." + r.action), arg: argLabel(r), value: r.match_value })}</span>
          </div>
          <button class="btn ghost danger" onclick={() => remove(r)}>{t("common.delete")}</button>
        </div>
      {/each}
    </div>
  </section>

  <section class="builder">
    <h3>{t("sRules.newRule")}</h3>
    <input class="name" bind:value={draft.name} placeholder={t("sRules.namePh")} />
    <div class="cond">
      <span>{t("sRules.if")}</span>
      <select bind:value={draft.match_field}>{#each FIELDS as f}<option value={f}>{t("rules.field." + f)}</option>{/each}</select>
      <select bind:value={draft.match_op}>{#each OPS as o}<option value={o}>{t("rules.op." + o)}</option>{/each}</select>
      <input bind:value={draft.match_value} placeholder={draft.match_field === "category" ? t("rules.categoryHint") : t("sRules.valuePhExample")} oninput={runPreview} />
    </div>
    <div class="cond">
      <span>{t("sRules.then")}</span>
      <select bind:value={draft.action} onchange={onActionChange}>{#each ACTIONS as a}<option value={a}>{t("rules.action." + a)}</option>{/each}</select>
      {#if draft.action === "set_group"}<GroupPicker bind:value={draft.action_arg} />
      {:else if needsArg}<input bind:value={draft.action_arg} placeholder={argPlaceholder} />{/if}
    </div>
    {#if draft.action === "set_group"}<p class="note">{t("groups.ruleNote")}</p>{/if}

    <div class="actions">
      <button class="btn" onclick={runPreview}>{t("sRules.previewMatches")}</button>
      <button class="btn primary" onclick={create} disabled={!draft.match_value}>{t("sRules.saveRule")}</button>
    </div>

    {#if preview}
      <div class="preview">
        {t("sRules.matchCount")} <b>{preview.match_count}</b>
        {#if preview.sample_subjects.length}
          <ul>{#each preview.sample_subjects as s}<li>{s || t("sRules.noSubject")}</li>{/each}</ul>
        {/if}
      </div>
    {/if}
  </section>
</div>

<style>
  .wrap { max-width: 760px; display: flex; flex-direction: column; gap: 28px; }
  h3 { margin: 0 0 12px; }
  .rules { display: flex; flex-direction: column; gap: 8px; }
  .rule { display: flex; align-items: center; gap: 12px; padding: 12px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .rule.off { opacity: 0.55; }
  .toggle { padding: 4px; border-radius: 50%; }
  .toggle .dot { display: block; width: 12px; height: 12px; border-radius: 50%; background: var(--surface-3); border: 1.5px solid var(--border); transition: background 0.12s, border-color 0.12s; }
  .toggle.on .dot { background: var(--done); border-color: var(--done); }
  .desc { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .desc span { color: var(--muted); font-size: 12px; }
  .builder { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .name { width: 100%; margin-bottom: 12px; }
  .cond { display: flex; align-items: center; gap: 9px; margin-bottom: 11px; flex-wrap: wrap; }
  .cond > span { color: var(--muted); width: 36px; }
  .cond select, .cond input { background: var(--surface-2); }
  .cond input { flex: 1; min-width: 160px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 10px; }
  .actions { display: flex; gap: 10px; margin-top: 4px; }
  .preview { margin-top: 14px; padding: 12px 14px; background: var(--surface-2); border-radius: var(--radius-sm); font-size: 13px; }
  .preview ul { margin: 8px 0 0; padding-left: 18px; color: var(--muted); }
  .muted { color: var(--muted); }
  .note { margin: -4px 0 12px 45px; font-size: 12px; color: var(--muted); }
</style>
