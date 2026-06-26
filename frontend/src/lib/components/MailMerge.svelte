<script>
  import { app, notify } from "../store.svelte.js";
  import { compose as composeApi } from "../api.js";
  import { escapeHtml } from "../email.js";
  import { icons } from "../icons.js";

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

  const preview = $derived(recipients.length
    ? { to: recipients[0].email, subject: fill(subjectTpl, recipients[0]), body: fill(bodyTpl, recipients[0]) }
    : null);

  function close() { if (!sending) app.mailMergeOpen = false; }

  async function send() {
    if (!accountId) { notify("Pick an account", "error"); return; }
    if (!recipients.length) { notify("Add at least one recipient", "error"); return; }
    if (!subjectTpl.trim() && !bodyTpl.trim()) { notify("Write a subject or body", "error"); return; }
    if (!confirm(`Send ${recipients.length} individual message${recipients.length > 1 ? "s" : ""}? Each recipient gets their own copy (no shared To/Cc).`)) return;
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
    notify(`Mail merge done — ${progress.done - progress.failed} sent${progress.failed ? `, ${progress.failed} failed` : ""}`);
    if (!progress.failed) app.mailMergeOpen = false;
  }
</script>

<div class="overlay" onclick={close} role="presentation">
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Mail merge">
    <header>
      <h2>{@html icons.sent} Mail merge</h2>
      <button class="x" onclick={close} aria-label="Close">{@html icons.close}</button>
    </header>

    <div class="body">
      <div class="col">
        <label class="f"><span>From</span>
          <select bind:value={accountId}>
            {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
          </select>
        </label>
        <label class="f"><span>Subject</span>
          <input bind:value={subjectTpl} placeholder="Hi {'{{'}name{'}}'}, your update" />
        </label>
        <label class="lbl">Body — use <code>{'{{'}name{'}}'}</code> etc. for columns from your list</label>
        <textarea class="bodyta" bind:value={bodyTpl} rows="8"
          placeholder={"Hi {{name}},\n\nThanks for…\n\n— Me"}></textarea>
        <label class="check">
          <input type="checkbox" bind:checked={useSignature} />
          <span>Append my default signature</span>
        </label>
      </div>

      <div class="col">
        <label class="lbl">Recipients — paste a CSV (with an <code>email</code> header) or one address per line</label>
        <textarea class="recipta" bind:value={recipientsRaw} rows="8"
          placeholder={"email,name\nalice@x.com,Alice\nbob@y.com,Bob"}></textarea>
        <div class="status">
          <b>{recipients.length}</b> recipient{recipients.length === 1 ? "" : "s"}
          {#if vars.length}· columns: {#each vars as v}<code class="vchip">{'{{'}{v}{'}}'}</code>{/each}{/if}
        </div>
        {#if preview}
          <div class="preview">
            <div class="pv-h">Preview · {preview.to}</div>
            <div class="pv-s">{preview.subject || "(no subject)"}</div>
            <div class="pv-b">{preview.body}</div>
          </div>
        {/if}
      </div>
    </div>

    <footer>
      {#if progress}<span class="prog">{progress.done}/{progress.total} sent{progress.failed ? ` · ${progress.failed} failed` : ""}</span>{/if}
      <button class="btn ghost" onclick={close} disabled={sending}>Cancel</button>
      <button class="btn primary" onclick={send} disabled={sending || !recipients.length}>
        {sending ? "Sending…" : `Send ${recipients.length || ""} message${recipients.length === 1 ? "" : "s"}`}
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
  .pv-h { background: var(--surface-2); padding: 5px 10px; font-size: 11px; color: var(--muted); }
  .pv-s { padding: 6px 10px 2px; font-weight: 600; font-size: 13px; }
  .pv-b { padding: 2px 10px 10px; font-size: 13px; color: var(--text); white-space: pre-wrap; max-height: 160px; overflow: auto; }
  footer { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 12px 18px; border-top: 1px solid var(--border); }
  footer .prog { margin-right: auto; color: var(--muted); font-size: 12px; }
</style>
