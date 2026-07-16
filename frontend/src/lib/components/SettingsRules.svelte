<script>
  import { onMount } from "svelte";
  import { app, notify } from "../store.svelte.js";
  import { rules as api } from "../api.js";
  import { t } from "../i18n.svelte.js";

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
  const ACTIONS = ["move", "archive", "delete", "mark_read", "mark_done", "block", "mute_notifications", "webhook", "run_script", "save_attachments"];

  async function load() { list = await api.list(); }
  onMount(load);

  async function runPreview() {
    try { preview = await api.preview(draft); } catch (e) { notify(e.message, "error"); }
  }
  const DESTRUCTIVE = new Set(["delete", "archive", "block"]);
  async function create() {
    // Catch an invalid regex before it silently never-matches (or errors per-message).
    if (draft.match_op === "regex") {
      try { new RegExp(draft.match_value); }
      catch (e) { notify(`Invalid regex: ${e.message}`, "error"); return; }
    }
    // Destructive rules (delete/archive/block) get a blast-radius confirm so a
    // catch-all like `from_domain ends_with ".com"` can't quietly nuke the inbox.
    if (DESTRUCTIVE.has(draft.action)) {
      let count = preview?.match_count;
      try { const p = await api.preview(draft); preview = p; count = p.match_count; } catch {}
      const verb = t("rules.action." + draft.action).toLowerCase();
      if (count != null &&
          !confirm(`This rule will ${verb} ${count} existing message${count === 1 ? "" : "s"} and keep applying to future mail. Continue?`)) {
        return;
      }
    }
    try {
      await api.create(draft);
      // Also apply to mail already in the box (rules otherwise only run on new mail).
      let applied = 0;
      try { applied = (await api.apply(draft)).applied || 0; } catch {}
      notify(applied ? `Rule saved · applied to ${applied} existing email${applied === 1 ? "" : "s"}` : "Rule saved");
      draft = newDraft(); preview = null; await load();
    }
    catch (e) { notify(e.message, "error"); }
  }
  async function remove(r) { await api.remove(r.id); await load(); }
  async function toggle(r) { await api.update(r.id, { ...r, enabled: !r.enabled }); await load(); }

  const needsArg = $derived(["move", "webhook", "run_script", "save_attachments"].includes(draft.action));
  const argPlaceholder = $derived(
    draft.action === "webhook" ? t("rules.webhookHint")
      : draft.action === "run_script" ? t("rules.scriptHint")
      : draft.action === "save_attachments" ? t("rules.saveDirHint")
      : "folder, e.g. Archive"
  );
</script>

<div class="wrap">
  <section>
    <h3>Your rules</h3>
    {#if list.length === 0}<p class="muted">No rules yet. Mail flows straight to the inbox.</p>{/if}
    <div class="rules">
      {#each list as r (r.id)}
        <div class="rule" class:off={!r.enabled}>
          <button class="toggle" class:on={r.enabled} onclick={() => toggle(r)} title="Enable/disable" aria-label={r.enabled ? "Enabled" : "Disabled"}><span class="dot"></span></button>
          <div class="desc">
            <b>{r.name || "Rule"}</b>
            <span>If {t("rules.field." + r.match_field)} {t("rules.op." + r.match_op)} “{r.match_value}” → {t("rules.action." + r.action)}{["move", "webhook", "run_script"].includes(r.action) && r.action_arg ? ` (${r.action_arg})` : ""}</span>
          </div>
          <button class="btn ghost danger" onclick={() => remove(r)}>Delete</button>
        </div>
      {/each}
    </div>
  </section>

  <section class="builder">
    <h3>New rule</h3>
    <input class="name" bind:value={draft.name} placeholder="Rule name (optional)" />
    <div class="cond">
      <span>If</span>
      <select bind:value={draft.match_field}>{#each FIELDS as f}<option value={f}>{t("rules.field." + f)}</option>{/each}</select>
      <select bind:value={draft.match_op}>{#each OPS as o}<option value={o}>{t("rules.op." + o)}</option>{/each}</select>
      <input bind:value={draft.match_value} placeholder={draft.match_field === "category" ? t("rules.categoryHint") : "value, e.g. newsletters.com"} oninput={runPreview} />
    </div>
    <div class="cond">
      <span>then</span>
      <select bind:value={draft.action}>{#each ACTIONS as a}<option value={a}>{t("rules.action." + a)}</option>{/each}</select>
      {#if needsArg}<input bind:value={draft.action_arg} placeholder="folder, e.g. Archive" />{/if}
    </div>

    <div class="actions">
      <button class="btn" onclick={runPreview}>Preview matches</button>
      <button class="btn primary" onclick={create} disabled={!draft.match_value}>Save rule</button>
    </div>

    {#if preview}
      <div class="preview">
        <b>{preview.match_count}</b> existing message{preview.match_count === 1 ? "" : "s"} would match.
        {#if preview.sample_subjects.length}
          <ul>{#each preview.sample_subjects as s}<li>{s || "(no subject)"}</li>{/each}</ul>
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
</style>
