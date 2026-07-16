<script>
  import { app, notify } from "../store.svelte.js";
  import { compose as composeApi } from "../api.js";
  import { escapeHtml } from "../email.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let accountId = $state(app.accounts[0]?.id ?? null);
  let subjectTpl = $state("");
  let bodyTpl = $state("");
  let recipientsRaw = $state("");
  let useSignature = $state(true);
  let sending = $state(false);
  let progress = $state(null);   // { done, total, failed }

  // --- recipient parsing ---------------------------------------------------
  // Accepts CSV with a header row (must include an "email" column) or a plain
  // list of bare addresses (one per line). Returns [{email, ...vars}].
  function parseCsvLine(line) {
    const out = []; let cur = "", q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (q) {
        if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') q = false;
        else cur += c;
      } else if (c === '"') q = true;
      else if (c === ",") { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    return out.map((s) => s.trim());
  }

  const recipients = $derived.by(() => {
    const lines = recipientsRaw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return [];
    const first = parseCsvLine(lines[0]).map((h) => h.toLowerCase());
    const hasHeader = first.includes("email");
    if (!hasHeader) {
      // plain list of addresses
      return lines.filter((l) => l.includes("@")).map((email) => ({ email }));
    }
    const headers = first;
    const rows = [];
    for (const line of lines.slice(1)) {
      const cells = parseCsvLine(line);
      const row = {};
      headers.forEach((h, i) => { row[h] = cells[i] ?? ""; });
      if (row.email && row.email.includes("@")) rows.push(row);
    }
    return rows;
  });

  const vars = $derived.by(() => {
    const set = new Set();
    if (recipients.length) Object.keys(recipients[0]).forEach((k) => set.add(k));
    return [...set];
  });

  function fill(tpl, row) {
    return (tpl || "").replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_m, k) => row[k.toLowerCase()] ?? row[k] ?? "");
  }
  function bodyHtml(text) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  // Variables actually referenced in the templates.
  const usedVars = $derived.by(() => {
    const set = new Set();
    const re = /\{\{\s*([\w.-]+)\s*\}\}/g;
    for (const tpl of [subjectTpl, bodyTpl]) { let m; while ((m = re.exec(tpl || ""))) set.add(m[1].toLowerCase()); }
    return [...set];
  });
  // Referenced placeholders with no matching CSV column - these render empty for
  // EVERYONE (e.g. a typo'd {{naem}}). Surfaced so it's not discovered post-send.
  const missingVars = $derived(usedVars.filter((v) => v !== "email" && !vars.includes(v)));
  // How many recipients have a blank value for a referenced (and existing) column.
  const rowsMissingData = $derived(
    recipients.filter((r) => usedVars.some((v) => vars.includes(v) && !String(r[v] ?? "").trim())).length
  );

  // Preview is steppable across all recipients (not just row #1), so what every
  // recipient actually receives is inspectable before sending.
  let previewIdx = $state(0);
  const previewRow = $derived(recipients.length ? recipients[Math.min(previewIdx, recipients.length - 1)] : null);
  const preview = $derived(previewRow
    ? { to: previewRow.email, subject: fill(subjectTpl, previewRow), body: fill(bodyTpl, previewRow) }
    : null);

  function close() { if (!sending) app.mailMergeOpen = false; }

  async function send() {
    if (!accountId) { notify(t("merge.pickAccount"), "error"); return; }
    if (!recipients.length) { notify(t("merge.addRecipient"), "error"); return; }
    if (!subjectTpl.trim() && !bodyTpl.trim()) { notify(t("merge.writeSomething"), "error"); return; }
    if (!confirm(recipients.length === 1 ? t("merge.confirmSendOne") : t("merge.confirmSendN", { n: recipients.length }))) return;
    sending = true;
    progress = { done: 0, total: recipients.length, failed: 0 };
    for (const row of recipients) {
      try {
        await composeApi.send({
          account_id: accountId,
          to: [row.email],
          subject: fill(subjectTpl, row),
          html: bodyHtml(fill(bodyTpl, row)),
          use_default_signature: useSignature,
          signature_id: null,
        });
      } catch {
        progress.failed++;
      }
      progress.done++;
      progress = { ...progress };
    }
    sending = false;
    notify(progress.failed
      ? t("merge.doneWithFailures", { sent: progress.done - progress.failed, failed: progress.failed })
      : t("merge.doneOk", { sent: progress.done - progress.failed }));
    if (!progress.failed) app.mailMergeOpen = false;
  }
</script>

<div class="overlay" onclick={close} role="presentation">
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={t("merge.title")}>
    <header>
      <h2>{@html icons.sent} {t("merge.title")}</h2>
      <button class="x" onclick={close} aria-label={t("merge.close")}>{@html icons.close}</button>
    </header>

    <div class="body">
      <div class="col">
        <label class="f"><span>{t("merge.from")}</span>
          <select bind:value={accountId}>
            {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
          </select>
        </label>
        <label class="f"><span>{t("merge.subject")}</span>
          <input bind:value={subjectTpl} placeholder={t("merge.subjectPlaceholder")} />
        </label>
        <label class="lbl">{t("merge.bodyLabelPre")}<code>{'{{'}name{'}}'}</code>{t("merge.bodyLabelPost")}</label>
        <textarea class="bodyta" bind:value={bodyTpl} rows="8"
          placeholder={t("merge.bodyPlaceholder")}></textarea>
        <label class="check">
          <input type="checkbox" bind:checked={useSignature} />
          <span>{t("merge.appendSignature")}</span>
        </label>
      </div>

      <div class="col">
        <label class="lbl">{t("merge.recipientsLabelPre")}<code>email</code>{t("merge.recipientsLabelPost")}</label>
        <textarea class="recipta" bind:value={recipientsRaw} rows="8"
          placeholder={"email,name\nalice@x.com,Alice\nbob@y.com,Bob"}></textarea>
        <div class="status">
          <b>{recipients.length}</b> {recipients.length === 1 ? t("merge.recipientOne") : t("merge.recipientN")}
          {#if vars.length}· {t("merge.columns")} {#each vars as v}<code class="vchip">{'{{'}{v}{'}}'}</code>{/each}{/if}
        </div>
        {#if missingVars.length}
          <div class="mm-warn">{t("merge.noColumnPre")}{#each missingVars as v}<code>{'{{'}{v}{'}}'}</code> {/each}{t("merge.noColumnPost")}</div>
        {/if}
        {#if rowsMissingData}
          <div class="mm-warn">{rowsMissingData === 1 ? t("merge.blankRowsOne") : t("merge.blankRowsN", { n: rowsMissingData })}</div>
        {/if}
        {#if preview}
          <div class="preview">
            <div class="pv-h">
              <span>{t("merge.preview")} · {preview.to}</span>
              {#if recipients.length > 1}
                <span class="pv-nav">
                  <button onclick={() => (previewIdx = (previewIdx - 1 + recipients.length) % recipients.length)} title={t("merge.prevRecipient")}>‹</button>
                  {Math.min(previewIdx, recipients.length - 1) + 1}/{recipients.length}
                  <button onclick={() => (previewIdx = (previewIdx + 1) % recipients.length)} title={t("merge.nextRecipient")}>›</button>
                </span>
              {/if}
            </div>
            <div class="pv-s">{preview.subject || t("merge.noSubject")}</div>
            <div class="pv-b">{preview.body}</div>
          </div>
        {/if}
      </div>
    </div>

    <footer>
      {#if progress}<span class="prog">{t("merge.progress", { done: progress.done, total: progress.total })}{progress.failed ? t("merge.progressFailed", { n: progress.failed }) : ""}</span>{/if}
      <button class="btn ghost" onclick={close} disabled={sending}>{t("merge.cancel")}</button>
      <button class="btn primary" onclick={send} disabled={sending || !recipients.length}>
        {sending ? t("merge.sending") : recipients.length === 1 ? t("merge.sendOne") : t("merge.sendN", { n: recipients.length })}
      </button>
    </footer>
  </div>
</div>

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: grid; place-items: center; z-index: 200; }
  .dialog { width: min(900px, 94vw); max-height: 90vh; display: flex; flex-direction: column; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: 0 24px 60px rgba(0,0,0,0.45); overflow: hidden; }
  header { display: flex; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); }
  header h2 { margin: 0; font-size: 16px; display: flex; align-items: center; gap: 9px; }
  .x { margin-left: auto; color: var(--muted); display: inline-flex; }
  .x:hover { color: var(--text); }
  .body { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; padding: 18px; overflow: auto; }
  .col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .f { display: flex; align-items: center; gap: 10px; }
  .f > span { width: 60px; flex: none; color: var(--muted); font-size: 13px; }
  .f select, .f input { flex: 1; }
  .lbl { color: var(--muted); font-size: 12px; }
  .lbl code, .status code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  textarea { width: 100%; resize: vertical; font: 13px/1.5 ui-monospace, monospace; }
  .bodyta { font-family: system-ui, sans-serif; }
  .check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
  .status { font-size: 12px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .vchip { color: var(--accent); }
  .preview { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
  .pv-h { background: var(--surface-2); padding: 5px 10px; font-size: 11px; color: var(--muted); display: flex; align-items: center; justify-content: space-between; }
  .pv-nav { display: inline-flex; align-items: center; gap: 6px; }
  .pv-nav button { padding: 0 6px; border-radius: 4px; font-size: 14px; line-height: 1; }
  .pv-nav button:hover { background: var(--surface-3); }
  .mm-warn { font-size: 12px; color: var(--warning); }
  .mm-warn code { background: var(--surface-2); padding: 0 4px; border-radius: 4px; }
  .pv-s { padding: 6px 10px 2px; font-weight: 600; font-size: 13px; }
  .pv-b { padding: 2px 10px 10px; font-size: 13px; color: var(--text); white-space: pre-wrap; max-height: 160px; overflow: auto; }
  footer { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 12px 18px; border-top: 1px solid var(--border); }
  footer .prog { margin-right: auto; color: var(--muted); font-size: 12px; }
</style>
