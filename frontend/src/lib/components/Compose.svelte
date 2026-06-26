<script>
  import { onMount } from "svelte";
  import { app, notify, loadAccountsAndFolders, queueSend, snoozePresets, presetWhen } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { signatures as sigApi, compose as composeApi } from "../api.js";
  import RecipientInput from "./RecipientInput.svelte";

  let { standalone = false } = $props();

  let c = $state({ to: "", cc: "", subject: "", html: "", in_reply_to: "", account_id: null });
  let accountId = $state(null);
  let showCc = $state(false);
  let editor;
  let attachments = $state([]);
  let fileInput;
  let dragPos = $state(null);
  let dragging = false, ox = 0, oy = 0;
  let sigs = $state([]);
  let signatureId = $state("none"); // "none" | <signature id>

  function defaultSigFor(acctId) {
    return sigs.find((s) => s.account_id === acctId && s.is_default)
        || sigs.find((s) => s.account_id == null && s.is_default)
        || sigs[0] || null;
  }

  // Render the signature into the body (Spark-style), restoring inline images so
  // they show while editing. Replaces any previously-inserted signature block.
  function sigHtml(sig) {
    let html = sig?.html || "";
    for (const img of sig?.inline_images || []) {
      html = html.replaceAll(`cid:${img.cid}`, `data:${img.content_type};base64,${img.data_b64}`);
    }
    return html;
  }
  function applySignature() {
    if (!editor) return;
    editor.querySelector(".rapl-sig-wrap")?.remove();
    if (signatureId !== "none") {
      const sig = sigs.find((s) => String(s.id) === String(signatureId));
      if (sig) {
        const wrap = document.createElement("div");
        wrap.className = "rapl-sig-wrap";
        // Blank line above the signature so it never butts against your text.
        wrap.innerHTML = `<div><br></div><div class="rapl-sig">${sigHtml(sig)}</div>`;
        editor.appendChild(wrap);
      }
    }
    // Guarantee at least one editable line that isn't the signature, so you can
    // always type above it (fixes "signature stuck at the very top").
    const hasBody = [...editor.childNodes].some(
      (n) => !(n.nodeType === 1 && n.classList && n.classList.contains("rapl-sig-wrap"))
    );
    if (!hasBody) {
      const lead = document.createElement("div");
      lead.innerHTML = "<br>";
      editor.insertBefore(lead, editor.firstChild);
    }
  }
  function focusTop() {
    if (!editor) return;
    editor.focus();
    try {
      const sel = window.getSelection();
      const r = document.createRange();
      r.setStart(editor, 0); r.collapse(true);
      sel.removeAllRanges(); sel.addRange(r);
    } catch {}
  }

  onMount(async () => {
    if (standalone) {
      try { c = { ...c, ...JSON.parse(sessionStorage.getItem("raplmail.compose.seed") || "{}") }; } catch {}
      if (app.accounts.length === 0) await loadAccountsAndFolders();
    } else {
      c = { ...c, ...(app.composing || {}) };
    }
    accountId = c.account_id ?? app.accounts[0]?.id ?? null;
    if (c.cc) showCc = true;
    if (Array.isArray(c.attachments)) attachments = c.attachments;
    if (editor && c.html) editor.innerHTML = c.html;
    try {
      sigs = await sigApi.list();
      const d = defaultSigFor(accountId);
      signatureId = d ? d.id : "none";
    } catch {}
    applySignature();
    focusTop();
  });

  // Re-pick the default signature when the From account changes.
  let _lastAcct = null;
  $effect(() => {
    if (accountId !== _lastAcct && sigs.length) {
      _lastAcct = accountId;
      const d = defaultSigFor(accountId);
      signatureId = d ? d.id : "none";
      applySignature();
    }
  });

  function close() {
    if (standalone) { window.close(); return; }
    app.composing = null;
  }

  // Rich-text commands (contenteditable).
  function exec(cmd, value = null) {
    document.execCommand(cmd, false, value);
    editor?.focus();
  }
  function addLink() {
    const url = prompt("Link URL:", "https://");
    if (url) exec("createLink", url);
  }

  function readFiles(files) {
    for (const file of files) {
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = String(reader.result).split(",")[1] || "";
        attachments = [...attachments, {
          filename: file.name, content_type: file.type || "application/octet-stream",
          data_b64: b64, size: file.size,
        }];
      };
      reader.readAsDataURL(file);
    }
  }
  function removeAttachment(i) { attachments = attachments.filter((_, idx) => idx !== i); }

  let laterMenu = $state(false);
  let customWhen = $state("");

  function autoBccFor(recipients) {
    const rules = app.settings.autoBcc || [];
    const out = new Set();
    for (const r of recipients) {
      const dom = (r.split("@")[1] || "").toLowerCase();
      for (const rule of rules) {
        const d = (rule.domain || "").toLowerCase().replace(/^@/, "");
        if (rule.bcc && d && (d === "*" || dom === d || dom.endsWith("." + d))) out.add(rule.bcc);
      }
    }
    return [...out];
  }

  function buildPayload() {
    const to = c.to.split(",").map((s) => s.trim()).filter(Boolean);
    const cc = (c.cc || "").split(",").map((s) => s.trim()).filter(Boolean);
    return {
      account_id: accountId,
      to,
      cc,
      bcc: autoBccFor([...to, ...cc]),
      subject: c.subject,
      html: editor?.innerHTML || "",
      in_reply_to: c.in_reply_to || "",
      // Signature is rendered directly in the body now, so don't let the server
      // append it again (its data: images become inline CID on send).
      use_default_signature: false,
      signature_id: null,
      attachments: attachments.map(({ filename, content_type, data_b64 }) => ({ filename, content_type, data_b64 })),
    };
  }

  function send() {
    if (!accountId) { notify("Pick an account", "error"); return; }
    if (c.to.trim() === "") { notify("Add a recipient", "error"); return; }
    const seed = { to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "", in_reply_to: c.in_reply_to, account_id: accountId, attachments };
    queueSend(buildPayload(), seed);
  }

  async function sendLater(iso, label) {
    if (!accountId) { notify("Pick an account", "error"); return; }
    if (c.to.trim() === "") { notify("Add a recipient", "error"); return; }
    laterMenu = false;
    try {
      await composeApi.send({ ...buildPayload(), send_at: iso });
      notify(`Scheduled — ${label}`);
      if (standalone) window.close(); else app.composing = null;
    } catch (e) { notify("Couldn't schedule: " + e.message, "error"); }
  }

  // datetime-local needs "YYYY-MM-DDTHH:MM" in local time.
  function nowLocal() {
    const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    return d.toISOString().slice(0, 16);
  }
  function sendCustom() {
    if (!customWhen) { notify("Pick a date & time", "error"); return; }
    const d = new Date(customWhen);
    if (isNaN(d.getTime()) || d <= new Date()) { notify("Pick a future time", "error"); return; }
    sendLater(d.toISOString(), d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }));
  }

  function fillVars(body) {
    const firstEmail = (c.to.split(",")[0] || "").trim();
    const local = firstEmail.split("@")[0] || "";
    const first = (local.split(/[._-]/)[0] || "").replace(/^\w/, (ch) => ch.toUpperCase());
    const date = new Date().toLocaleDateString();
    return body
      .replaceAll("{{first}}", first).replaceAll("{{first_name}}", first).replaceAll("{{name}}", first)
      .replaceAll("{{email}}", firstEmail).replaceAll("{{date}}", date);
  }

  // Expand a ;shortcut typed just before the caret.
  function tryExpand() {
    const snippets = app.settings.snippets || [];
    if (!snippets.length) return false;
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return false;
    const range = sel.getRangeAt(0);
    if (!range.collapsed || range.startContainer.nodeType !== Node.TEXT_NODE) return false;
    const node = range.startContainer;
    const offset = range.startOffset;
    const word = (node.textContent.slice(0, offset).match(/(\S+)$/) || [])[1];
    if (!word) return false;
    const snip = snippets.find((s) => s.shortcut === word);
    if (!snip) return false;
    const r2 = document.createRange();
    r2.setStart(node, offset - word.length);
    r2.setEnd(node, offset);
    r2.deleteContents();
    sel.removeAllRanges();
    sel.addRange(r2);
    document.execCommand("insertHTML", false, fillVars(snip.body));
    return true;
  }

  function onEditorKey(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); send(); return; }
    if (e.key === "Tab" || e.key === " ") {
      if (tryExpand()) e.preventDefault();
    }
  }
  function onDrop(e) {
    e.preventDefault();
    const imgs = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/"));
    for (const file of imgs) {
      const reader = new FileReader();
      reader.onload = () => { const img = document.createElement("img"); img.src = String(reader.result); img.style.maxWidth = "100%"; editor.appendChild(img); };
      reader.readAsDataURL(file);
    }
  }

  function onHeaderDown(e) {
    if (standalone) return;
    dragging = true;
    const rect = e.currentTarget.parentElement.getBoundingClientRect();
    ox = e.clientX - rect.left; oy = e.clientY - rect.top;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", () => { dragging = false; window.removeEventListener("pointermove", onMove); }, { once: true });
  }
  function onMove(e) {
    if (!dragging) return;
    dragPos = { x: Math.max(0, Math.min(window.innerWidth - 200, e.clientX - ox)), y: Math.max(0, Math.min(window.innerHeight - 80, e.clientY - oy)) };
  }

  const dockStyle = $derived(
    standalone ? "" :
    dragPos ? `left:${dragPos.x}px; top:${dragPos.y}px; right:auto; bottom:auto;` :
    app.settings.composePosition === "bottom-left" ? "left:18px; right:auto;" : "right:18px;"
  );

  const TOOLS = [
    { cmd: "bold", label: "B", style: "font-weight:700" },
    { cmd: "italic", label: "I", style: "font-style:italic" },
    { cmd: "underline", label: "U", style: "text-decoration:underline" },
    { cmd: "insertUnorderedList", label: "• List" },
    { cmd: "insertOrderedList", label: "1. List" },
  ];
</script>

<div class="panel" class:standalone style={dockStyle}>
  <header onpointerdown={onHeaderDown}>
    <span>New message</span>
    <button class="x" onpointerdown={(e) => e.stopPropagation()} onclick={close}>{@html icons.close}</button>
  </header>

  <div class="fields">
    <label class="f"><span>From</span>
      <select bind:value={accountId}>
        {#each app.accounts as a}<option value={a.id}>{a.display_name && a.display_name !== a.email ? `${a.display_name} <${a.email}>` : a.email}</option>{/each}
      </select>
    </label>
    <div class="f"><span>To</span>
      <RecipientInput bind:value={c.to} placeholder="Start typing a name or email…" />
      {#if !showCc}<button class="cc-toggle" onclick={() => (showCc = true)}>Cc</button>{/if}
    </div>
    {#if showCc}<div class="f"><span>Cc</span><RecipientInput bind:value={c.cc} /></div>{/if}
    <label class="f"><span>Subject</span><input bind:value={c.subject} /></label>
  </div>

  <div class="toolbar">
    {#each TOOLS as t}
      <button class="tool" title={t.cmd} style={t.style || ""} onmousedown={(e) => { e.preventDefault(); exec(t.cmd); }}>{t.label}</button>
    {/each}
    <button class="tool" title="Insert link" onmousedown={(e) => { e.preventDefault(); addLink(); }}>{@html icons.link}</button>
    <button class="tool" title="Clear formatting" onmousedown={(e) => { e.preventDefault(); exec("removeFormat"); }}>{@html icons.clearFormat}</button>
    <span class="tspace"></span>
    <button class="tool" title="Attach file" onclick={() => fileInput.click()}>{@html icons.attachment} Attach</button>
    <input bind:this={fileInput} type="file" multiple hidden onchange={(e) => readFiles(e.currentTarget.files)} />
  </div>

  <div class="editor" contenteditable="true" role="textbox" tabindex="0" aria-label="Message body"
    bind:this={editor} onkeydown={onEditorKey} ondrop={onDrop} ondragover={(e) => e.preventDefault()}
    data-placeholder="Write your message…  (Ctrl+Enter to send)"></div>

  {#if attachments.length}
    <div class="attachments">
      {#each attachments as a, i}
        <span class="chip">{@html icons.attachment} {a.filename}<button onclick={() => removeAttachment(i)}>{@html icons.close}</button></span>
      {/each}
    </div>
  {/if}

  <footer>
    <button class="btn primary" onclick={send}>Send</button>
    <div class="later">
      <button class="btn" onclick={() => (laterMenu = !laterMenu)} title="Send later">{@html icons.clock} Later ⌄</button>
      {#if laterMenu}
        <div class="later-menu">
          {#each snoozePresets().filter((p) => p.iso) as p}
            <button onclick={() => sendLater(p.iso, p.label)}><span>{p.label}</span><span class="when">{presetWhen(p.at)}</span></button>
          {/each}
          <div class="custom">
            <input type="datetime-local" bind:value={customWhen} min={nowLocal()} />
            <button class="btn primary sm" onclick={sendCustom}>Schedule</button>
          </div>
        </div>
      {/if}
    </div>
    {#if sigs.length}
      <label class="sigpick" title="Signature">{@html icons.signature}
        <select bind:value={signatureId} onchange={applySignature}>
          <option value="none">No signature</option>
          {#each sigs as s}<option value={s.id}>{s.name}</option>{/each}
        </select>
      </label>
    {/if}
    <span class="hint">Ctrl+Enter to send</span>
  </footer>
</div>

<style>
  .panel { position: fixed; bottom: 18px; z-index: 50; width: min(580px, 94vw); height: min(600px, 86vh);
    display: flex; flex-direction: column; overflow: hidden; background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); }
  .panel.standalone { position: static; width: 100%; height: 100vh; border: none; border-radius: 0; box-shadow: none; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--border); font-weight: 600; cursor: move; user-select: none; background: var(--surface-2); }
  .panel.standalone header { cursor: default; }
  .x { color: var(--muted); font-size: 14px; padding: 3px 7px; border-radius: 6px; }
  .x:hover { background: var(--surface-3); }
  .fields { padding: 4px 14px; }
  .f { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border); position: relative; }
  .f > span { width: 52px; color: var(--muted); font-size: 13px; }
  .f input, .f select { flex: 1; border: none; background: transparent; padding: 4px 0; color: var(--text); }
  .f input:focus, .f select:focus { border: none; }
  .cc-toggle { color: var(--accent); font-size: 13px; }
  .toolbar { display: flex; align-items: center; gap: 4px; padding: 7px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .tool { min-width: 28px; padding: 5px 8px; border-radius: 6px; color: var(--muted); font-size: 13px; }
  .tool:hover { background: var(--surface-3); color: var(--text); }
  .tspace { flex: 1; }
  .editor { flex: 1; padding: 14px; overflow-y: auto; outline: none; line-height: 1.6; color: var(--text); caret-color: var(--accent); }
  .editor:empty::before { content: attr(data-placeholder); color: var(--faint); }
  .editor :global(a) { color: var(--accent); }
  .attachments { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px; border-top: 1px solid var(--border); }
  .chip { display: inline-flex; align-items: center; gap: 6px; background: var(--surface-3); padding: 4px 8px; border-radius: 6px; font-size: 12px; }
  .chip button { color: var(--muted); }
  .chip button:hover { color: var(--danger); }
  footer { display: flex; align-items: center; gap: 12px; padding: 11px 14px; border-top: 1px solid var(--border); }
  .later { position: relative; }
  .later-menu { position: absolute; bottom: 100%; left: 0; margin-bottom: 6px; z-index: 20; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; min-width: 220px; }
  .later-menu > button { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; text-align: left; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
  .later-menu > button:hover { background: var(--accent); color: #fff; }
  .later-menu .when { color: var(--muted); font-size: 12px; }
  .later-menu > button:hover .when { color: #e7e9ff; }
  .later-menu .custom { display: flex; gap: 6px; padding: 6px 6px 2px; border-top: 1px solid var(--border); margin-top: 4px; }
  .later-menu .custom input { flex: 1; min-width: 0; font-size: 12px; padding: 5px 6px; }
  .later-menu .custom .sm { padding: 5px 10px; font-size: 12px; }
  .sigpick { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); }
  .sigpick select { padding: 5px 8px; }
  .hint { color: var(--faint); font-size: 12px; margin-left: auto; }
</style>
