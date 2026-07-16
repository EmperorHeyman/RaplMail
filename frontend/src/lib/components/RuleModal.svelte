<script>
  import { onMount } from "svelte";
  import { app, notify, ruleValueForField, ruleOpForField, confirmDialog } from "../store.svelte.js";
  import { rules as api } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // Draft + source message come from app.ruleModal (set by openRuleModal).
  let draft = $state({ ...app.ruleModal.draft });
  const message = app.ruleModal.message;

  let preview = $state(null);
  let busy = $state(false);
  let previewing = $state(false);

  const FIELDS = ["from_domain", "from", "to", "subject", "body", "category"];
  const OPS = ["contains", "equals", "ends_with", "regex"];
  const ACTIONS = ["move", "archive", "delete", "mark_read", "mark_done", "block", "mute_notifications", "webhook", "run_script", "save_attachments"];
  const DESTRUCTIVE = new Set(["delete", "archive", "block"]);
  const needsArg = $derived(["move", "webhook", "run_script", "save_attachments"].includes(draft.action));
  const argPlaceholder = $derived(
    draft.action === "webhook" ? t("rules.webhookHint")
      : draft.action === "run_script" ? t("rules.scriptHint")
      : draft.action === "save_attachments" ? t("rules.saveDirHint")
      : "folder, e.g. Archive"
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

  async function save() {
    if (draft.match_op === "regex") {
      try { new RegExp(draft.match_value); }
      catch (e) { notify(`Invalid regex: ${e.message}`, "error"); return; }
    }
    if (DESTRUCTIVE.has(draft.action)) {
      let count = preview?.match_count;
      try { const p = await api.preview(draft); preview = p; count = p.match_count; } catch {}
      const verb = t("rules.action." + draft.action).toLowerCase();
      if (count != null) {
        const ok = await confirmDialog({
          title: "Apply this rule?",
          message: `It will ${verb} ${count} existing message${count === 1 ? "" : "s"} and keep applying to future mail.`,
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
      notify(applied ? `Rule saved · applied to ${applied} existing email${applied === 1 ? "" : "s"}` : "Rule saved");
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
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="New rule">
    <header>
      <h2>{@html icons.bolt || ""} New rule</h2>
      <button class="x" onclick={close} aria-label="Close">{@html icons.close}</button>
    </header>

    {#if message}
      <p class="src">From this email: <b>{message.from_name || message.from_addr}</b>
        {#if message.subject}· <span class="subj">{message.subject}</span>{/if}</p>
    {/if}

    <label class="fld"><span>Name</span>
      <input bind:value={draft.name} placeholder="Rule name (optional)" />
    </label>

    <div class="cond">
      <span class="lead">If</span>
      <select bind:value={draft.match_field} onchange={onFieldChange}>{#each FIELDS as f}<option value={f}>{t("rules.field." + f)}</option>{/each}</select>
      <select bind:value={draft.match_op}>{#each OPS as o}<option value={o}>{t("rules.op." + o)}</option>{/each}</select>
      <input bind:value={draft.match_value} placeholder={draft.match_field === "category" ? t("rules.categoryHint") : "value"} oninput={schedulePreview} />
    </div>
    <div class="cond">
      <span class="lead">then</span>
      <select bind:value={draft.action}>{#each ACTIONS as a}<option value={a}>{t("rules.action." + a)}</option>{/each}</select>
      {#if needsArg}<input bind:value={draft.action_arg} placeholder={argPlaceholder} />{/if}
    </div>

    <div class="preview" class:empty={!preview}>
      {#if previewing}
        <span class="muted">Checking matches…</span>
      {:else if preview}
        <b>{preview.match_count}</b> existing message{preview.match_count === 1 ? "" : "s"} match.
        {#if preview.sample_subjects?.length}
          <ul>{#each preview.sample_subjects.slice(0, 4) as s}<li>{s || "(no subject)"}</li>{/each}</ul>
        {/if}
      {:else}
        <span class="muted">Pick a field to auto-fill from this email, then adjust.</span>
      {/if}
    </div>

    <footer>
      <button class="link" onclick={manageAll}>Manage all rules in Settings →</button>
      <div class="spacer"></div>
      <button class="btn ghost" onclick={close}>Cancel</button>
      <button class="btn primary" onclick={save} disabled={busy || !draft.match_value.trim()}>{busy ? "Saving…" : "Save rule"}</button>
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
  footer { display: flex; align-items: center; gap: 8px; margin-top: 2px; }
  footer .spacer { flex: 1; }
  .link { color: var(--accent); font-size: 13px; }
  .link:hover { text-decoration: underline; }
</style>
