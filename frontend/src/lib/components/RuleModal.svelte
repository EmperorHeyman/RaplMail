<script>
  import { onMount } from "svelte";
  import { app, notify, ruleValueForField, ruleOpForField, confirmDialog, refreshMessages, groupArgFor } from "../store.svelte.js";
  import { rules as api } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import GroupPicker from "./GroupPicker.svelte";

  // Draft + source message come from app.ruleModal (set by openRuleModal).
  let draft = $state({ ...app.ruleModal.draft });
  const message = app.ruleModal.message;

  let preview = $state(null);
  let busy = $state(false);
  let previewing = $state(false);

  const FIELDS = ["from_domain", "from", "to", "subject", "body", "category"];
  const OPS = ["contains", "equals", "ends_with", "regex"];
  const ACTIONS = ["move", "set_group", "archive", "delete", "mark_read", "mark_done", "block", "mute_notifications", "webhook", "run_script", "save_attachments"];
  const DESTRUCTIVE = new Set(["delete", "archive", "block"]);
  const needsArg = $derived(["move", "webhook", "run_script", "save_attachments"].includes(draft.action));
  const argPlaceholder = $derived(
    draft.action === "webhook" ? t("rules.webhookHint")
      : draft.action === "run_script" ? t("rules.scriptHint")
      : draft.action === "save_attachments" ? t("rules.saveDirHint")
      : t("sRules.folderPh")
  );

  // When the field changes, auto-fill the value + operator from the clicked mail.
  function onFieldChange() {
    draft.match_op = ruleOpForField(draft.match_field);
    draft.match_value = ruleValueForField(draft.match_field, message);
    preview = null;
    runPreview();
  }

  let previewTimer;
  function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(runPreview, 350); }
  let _previewGen = 0;   // latest-request-wins: typing fires overlapping previews
  async function runPreview() {
    const gen = ++_previewGen;
    if (!draft.match_value.trim()) { preview = null; return; }
    previewing = true;
    try { const p = await api.preview(draft); if (gen === _previewGen) preview = p; }
    catch { if (gen === _previewGen) preview = null; }
    finally { if (gen === _previewGen) previewing = false; }
  }

  // Folder paths and group ids don't mix: switching to/from "Put in group"
  // swaps the argument for a sensible one instead of carrying "Archive" over.
  let lastAction = draft.action;
  function onActionChange() {
    draft.action_arg = groupArgFor(lastAction, draft.action, draft.action_arg);
    lastAction = draft.action;
  }

  async function save() {
    if (draft.action === "set_group" && !draft.action_arg) { notify(t("groups.pickFirst"), "error"); return; }
    if (draft.match_op === "regex") {
      try { new RegExp(draft.match_value); }
      catch (e) { notify(t("sRules.invalidRegex", { error: e.message }), "error"); return; }
    }
    if (DESTRUCTIVE.has(draft.action)) {
      let count = preview?.match_count;
      try { const p = await api.preview(draft); preview = p; count = p.match_count; } catch {}
      const verb = t("rules.action." + draft.action).toLowerCase();
      if (count != null) {
        const ok = await confirmDialog({
          title: t("sRules.applyTitle"),
          message: t("sRules.applyBody", { verb, n: count }),
          confirmLabel: `${t("rules.action." + draft.action)} ${count}`, danger: true,
        });
        if (!ok) return;
      }
    }
    busy = true;
    try {
      await api.create(draft);
      // Rules otherwise only run on new mail - apply to what's already here too,
      // so the rule visibly does something right away.
      let applied = 0;
      try { applied = (await api.apply(draft)).applied || 0; } catch {}
      notify(applied ? t("sRules.savedApplied", { n: applied }) : t("sRules.saved"));
      if (applied) refreshMessages({ background: true });
      close();
    }
    catch (e) { notify(e.message, "error"); }
    finally { busy = false; }
  }

  function close() { app.ruleModal = null; }
  function manageAll() { close(); app.settingsTab = "rules"; app.view = "settings"; }
  function onKey(e) { if (e.key === "Escape") close(); }

  // Kick off ONE initial preview for the prefilled draft. onMount (not $effect):
  // runPreview reads every draft field, so an effect re-fired it un-debounced
  // on each keystroke, racing the 350ms schedulePreview path.
  onMount(() => { if (app.ruleModal) runPreview(); });
</script>

<svelte:window on:keydown={onKey} />

<div class="backdrop" onclick={close} role="presentation">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={t("sRules.newRule")}>
    <header>
      <h2>{@html icons.bolt || ""} {t("sRules.newRule")}</h2>
      <button class="x" onclick={close} aria-label={t("common.close")}>{@html icons.close}</button>
    </header>

    {#if message}
      <p class="src">{t("sRules.fromThisEmail")} <b>{message.from_name || message.from_addr}</b>
        {#if message.subject}· <span class="subj">{message.subject}</span>{/if}</p>
    {/if}

    <label class="fld"><span>{t("sRules.name")}</span>
      <input bind:value={draft.name} placeholder={t("sRules.namePh")} />
    </label>

    <div class="cond">
      <span class="lead">{t("sRules.if")}</span>
      <select bind:value={draft.match_field} onchange={onFieldChange}>{#each FIELDS as f}<option value={f}>{t("rules.field." + f)}</option>{/each}</select>
      <select bind:value={draft.match_op}>{#each OPS as o}<option value={o}>{t("rules.op." + o)}</option>{/each}</select>
      <input bind:value={draft.match_value} placeholder={draft.match_field === "category" ? t("rules.categoryHint") : t("sRules.valuePh")} oninput={schedulePreview} />
    </div>
    <div class="cond">
      <span class="lead">{t("sRules.then")}</span>
      <select bind:value={draft.action} onchange={onActionChange}>{#each ACTIONS as a}<option value={a}>{t("rules.action." + a)}</option>{/each}</select>
      {#if draft.action === "set_group"}<GroupPicker bind:value={draft.action_arg} />
      {:else if needsArg}<input bind:value={draft.action_arg} placeholder={argPlaceholder} />{/if}
    </div>
    {#if draft.action === "set_group"}<p class="note">{t("groups.ruleNote")}</p>{/if}

    <div class="preview" class:empty={!preview}>
      {#if previewing}
        <span class="muted">{t("sRules.checking")}</span>
      {:else if preview}
        {t("sRules.matchCount")} <b>{preview.match_count}</b>
        {#if preview.sample_subjects?.length}
          <ul>{#each preview.sample_subjects.slice(0, 4) as s}<li>{s || t("sRules.noSubject")}</li>{/each}</ul>
        {/if}
      {:else}
        <span class="muted">{t("sRules.pickFieldHint")}</span>
      {/if}
    </div>

    <footer>
      <button class="link" onclick={manageAll}>{t("sRules.manageAll")} →</button>
      <div class="spacer"></div>
      <button class="btn ghost" onclick={close}>{t("common.cancel")}</button>
      <button class="btn primary" onclick={save} disabled={busy || !draft.match_value.trim()}>{busy ? t("sRules.saving") : t("sRules.saveRule")}</button>
    </footer>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,0.45);
    backdrop-filter: blur(2px);
    display: flex; align-items: flex-start; justify-content: center; padding-top: 12vh;
    animation: fade-in var(--t) var(--ease); }
  .modal { width: min(720px, 96vw); background: var(--surface); border: 1px solid var(--hairline);
    border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); padding: 22px 26px; display: flex; flex-direction: column; gap: 14px;
    animation: pop-in var(--t) var(--ease); }
  header { display: flex; align-items: center; }
  header h2 { margin: 0; font-size: 17px; display: flex; align-items: center; gap: 8px; }
  .x { margin-left: auto; color: var(--muted); }
  .x:hover { color: var(--text); }
  .src { margin: 0; font-size: 12px; color: var(--muted); }
  .src .subj { font-style: italic; }
  .fld { display: flex; align-items: center; gap: 10px; }
  .fld > span { width: 44px; color: var(--muted); font-size: 13px; }
  .fld input { flex: 1; }
  .cond { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .cond .lead { width: 44px; color: var(--muted); font-size: 13px; }
  .cond input { flex: 1; min-width: 150px; }
  select, input { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; }
  .preview { min-height: 40px; padding: 10px 12px; background: var(--surface-2); border-radius: var(--radius-sm); font-size: 13px; }
  .preview.empty { color: var(--muted); }
  .preview ul { margin: 6px 0 0; padding-left: 18px; color: var(--muted); }
  .muted { color: var(--muted); }
  .note { margin: -6px 0 0 52px; font-size: 12px; color: var(--muted); }
  footer { display: flex; align-items: center; gap: 8px; margin-top: 2px; }
  footer .spacer { flex: 1; }
  .link { color: var(--accent); font-size: 13px; }
  .link:hover { text-decoration: underline; }
</style>
