<script>
  import { onMount, onDestroy } from "svelte";
  import { app, notify, loadAccountsAndFolders, queueSend, snoozePresets, presetWhen } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { signatures as sigApi, compose as composeApi } from "../api.js";
  import RecipientInput from "./RecipientInput.svelte";

  let { standalone = false } = $props();

  let c = $state({ to: "", cc: "", subject: "", html: "", in_reply_to: "", account_id: null });
  let accountId = $state(null);
  let fromIdentity = $state("");   // chosen send-as identity ("" = account's primary address)
  // Identities available for the selected account: primary address + its aliases.
  const identitiesFor = (id) => {
    const a = app.accounts.find((x) => x.id === id);
    if (!a) return [];
    const primary = a.display_name && a.display_name !== a.email ? `${a.display_name} <${a.email}>` : a.email;
    return [{ value: "", label: primary }, ...(a.aliases || []).map((al) => ({ value: al, label: al }))];
  };
  let showCc = $state(false);
  let editor;
  let attachments = $state([]);
  let fileInput;
  let dragPos = $state(null);
  let dragging = false, ox = 0, oy = 0;
  let panelEl;
  let panelW = $state(null), panelH = $state(null);  // preserve manual resize across re-renders
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
    const quoteBlock = editor.querySelector(".rapl-quoted-block");
    if (signatureId !== "none") {
      const sig = sigs.find((s) => String(s.id) === String(signatureId));
      if (sig) {
        const wrap = document.createElement("div");
        wrap.className = "rapl-sig-wrap";
        // Blank line above the signature so it never butts against your text.
        wrap.innerHTML = `<div><br></div><div class="rapl-sig">${sigHtml(sig)}</div>`;
        // Spark order: reply text → signature → quoted thread. Put the signature
        // right before the quote (not at the very bottom, after their email).
        if (quoteBlock) editor.insertBefore(wrap, quoteBlock);
        else editor.appendChild(wrap);
      }
    }
    // Guarantee an editable line at the very top (before the signature/quote) so
    // you can always start typing your reply on top.
    const hasBody = [...editor.childNodes].some(
      (n) => !(n.nodeType === 1 && n.classList &&
               (n.classList.contains("rapl-sig-wrap") || n.classList.contains("rapl-quoted-block")))
    );
    if (!hasBody) {
      const lead = document.createElement("div");
      lead.innerHTML = "<br>";
      editor.insertBefore(lead, editor.firstChild);
    }
  }
  // Collapse/expand the quoted thread when its "•••" pill is clicked (the pill is
  // contenteditable=false, so this delegated handler drives it).
  function onEditorClick(e) {
    const t = e.target.closest?.(".rapl-quote-toggle");
    if (t) { e.preventDefault(); t.closest(".rapl-quoted-block")?.classList.toggle("collapsed"); }
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

  const DRAFT_KEY = "raplmail.draft";
  let draftTimer;
  // Is there real user content beyond the auto-inserted signature?
  function userTyped() {
    if (c.to.trim() || (c.cc || "").trim() || c.subject.trim()) return true;
    if (!editor) return false;
    const clone = editor.cloneNode(true);
    clone.querySelector(".rapl-sig-wrap")?.remove();
    return !!clone.innerText.trim();
  }
  function saveDraft() {
    if (standalone) return;
    try {
      if (!userTyped()) { localStorage.removeItem(DRAFT_KEY); return; }
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "",
        account_id: accountId, in_reply_to: c.in_reply_to || "",
      }));
    } catch {}
  }
  function scheduleSave() { clearTimeout(draftTimer); draftTimer = setTimeout(saveDraft, 700); }
  function clearDraft() { try { localStorage.removeItem(DRAFT_KEY); } catch {} }
  // Flush the debounced save right now (used on close/unmount so the last
  // keystrokes are never lost between the 700ms debounce and teardown).
  function flushSave() { clearTimeout(draftTimer); saveDraft(); }

  onMount(async () => {
    if (standalone) {
      try {
        c = { ...c, ...JSON.parse(localStorage.getItem("raplmail.compose.seed") || "{}") };
        localStorage.removeItem("raplmail.compose.seed");   // consume it so it doesn't leak
      } catch {}
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

    // Restore an autosaved draft into a blank new compose, OR when resuming the
    // exact same reply (matching in_reply_to) — so closing a half-written reply
    // and reopening it brings the text back instead of losing it.
    const blankSeed = !c.to && !c.subject && !c.html;
    const savedPeek = (() => { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch { return null; } })();
    const sameReply = !!(c.in_reply_to && savedPeek && savedPeek.in_reply_to === c.in_reply_to);
    if (!standalone && (blankSeed || sameReply)) {
      try {
        const saved = savedPeek;
        if (saved && (saved.to || saved.subject || (saved.html || "").trim())) {
          c.to = saved.to || ""; c.cc = saved.cc || ""; c.subject = saved.subject || "";
          if (saved.account_id) accountId = saved.account_id;
          if (saved.cc) showCc = true;
          if (editor && saved.html) editor.innerHTML = saved.html;
          notify("Restored your draft");
        }
      } catch {}
    }
    focusTop();
    // Autosave as fields change.
    scheduleSave();
    mounted = true;
  });

  // True once the user actually edits something (vs. the seeded reply/forward
  // content), so close() only confirms when there's genuine unsaved work.
  let mounted = false;
  let dirty = $state(false);
  function onBodyInput() { dirty = true; scheduleSave(); }

  // Persist subject/recipients as they change (and flag genuine edits).
  $effect(() => { void c.to; void c.cc; void c.subject; if (mounted) dirty = true; if (editor) scheduleSave(); });

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
    // Persist whatever's typed before tearing down so the X never silently
    // drops a draft (the 700ms debounce hadn't fired yet). If there's real
    // unsaved content, confirm — the saved copy is restorable next compose.
    flushSave();
    if (dirty && userTyped() && !confirm("Discard this draft? Your text is saved and can be restored from a new message.")) return;
    if (standalone) { window.close(); return; }
    app.composing = null;
  }
  // Last-resort flush if the component is torn down some other way (route
  // change, parent re-render) without close() running.
  onDestroy(() => { try { flushSave(); } catch {} });

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
  let tplMenu = $state(false);
  function insertTemplate(t) {
    tplMenu = false;
    if (t.subject && !c.subject.trim()) c.subject = fillVars(t.subject);
    const body = fillVars(t.body || "");
    if (editor) {
      // Insert above the signature, leaving it in place.
      const sig = editor.querySelector(".rapl-sig-wrap");
      const block = document.createElement("div");
      block.innerHTML = body;
      if (sig) editor.insertBefore(block, sig); else editor.appendChild(block);
      editor.focus();
    }
  }

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

  let pgpSign = $state(false);
  let pgpEncrypt = $state(false);
  let requestReceipt = $state(false);
  const pgpConfigured = $derived(!!(app.settings.pgpPrivateKey || (app.settings.pgpPublicKeys || []).length));

  let savingDraft = $state(false);
  let draftUid = $state(null);   // IMAP UID of the last server-saved draft (for replace)
  async function saveToDrafts() {
    if (!accountId) { notify("Pick an account", "error"); return; }
    savingDraft = true;
    try {
      const r = await composeApi.saveDraft({ ...buildPayload(), replace_uid: draftUid });
      draftUid = r.uid ?? draftUid;
      clearDraft();   // server now holds it; drop the local autosave copy
      notify(`Saved to Drafts (${r.folder})`);
    } catch (e) {
      notify(e.message, "error");
    } finally { savingDraft = false; }
  }

  // The composer HTML carries UI-only bits (the "•••" collapse pill + its wrapper
  // divs). Strip them so recipients get clean, standard quoted HTML.
  function outgoingHtml() {
    if (!editor) return "";
    const clone = editor.cloneNode(true);
    clone.querySelectorAll(".rapl-quote-toggle").forEach((n) => n.remove());
    clone.querySelectorAll(".rapl-quoted-block, .rapl-quoted-content").forEach((n) => {
      while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n);
      n.remove();
    });
    return clone.innerHTML;
  }

  function buildPayload() {
    const to = c.to.split(",").map((s) => s.trim()).filter(Boolean);
    const cc = (c.cc || "").split(",").map((s) => s.trim()).filter(Boolean);
    return {
      account_id: accountId,
      from_addr: fromIdentity || "",
      pgp_sign: pgpSign,
      pgp_encrypt: pgpEncrypt,
      request_receipt: requestReceipt,
      to,
      cc,
      bcc: autoBccFor([...to, ...cc]),
      subject: c.subject,
      html: outgoingHtml(),
      in_reply_to: c.in_reply_to || "",
      // Signature is rendered directly in the body now, so don't let the server
      // append it again (its data: images become inline CID on send).
      use_default_signature: false,
      signature_id: null,
      attachments: attachments.map(({ filename, content_type, data_b64 }) => ({ filename, content_type, data_b64 })),
    };
  }

  // Warn if the message talks about an attachment but none is attached.
  const _ATTACH_HINTS = /\b(attach(ed|ment|ing)?|enclosed|in the attachment|see attached|find attached|p[řr]ipoj|p[řr]iloh|v p[řr]íloze|p[řr]ikládám)\b/i;
  function attachmentMissing() {
    if (attachments.length > 0) return false;
    const text = `${c.subject} ${editor?.innerText || ""}`;
    return _ATTACH_HINTS.test(text);
  }

  function send() {
    if (!accountId) { notify("Pick an account", "error"); return; }
    if (c.to.trim() === "") { notify("Add a recipient", "error"); return; }
    if (c.subject.trim() === "" && !confirm("Send this message without a subject?")) return;
    if (attachmentMissing() && !confirm("You mention an attachment but nothing is attached. Send anyway?")) return;
    const seed = { to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "", in_reply_to: c.in_reply_to, account_id: accountId, attachments };
    clearDraft();
    queueSend(buildPayload(), seed);
  }

  async function sendLater(iso, label) {
    if (!accountId) { notify("Pick an account", "error"); return; }
    if (c.to.trim() === "") { notify("Add a recipient", "error"); return; }
    if (c.subject.trim() === "" && !confirm("Schedule this message without a subject?")) return;
    if (attachmentMissing() && !confirm("You mention an attachment but nothing is attached. Schedule anyway?")) return;
    laterMenu = false;
    try {
      await composeApi.send({ ...buildPayload(), send_at: iso });
      clearDraft();
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
    if (e.key === "Tab" || e.key === " ") {
      if (tryExpand()) e.preventDefault();
    }
  }
  // Ctrl/Cmd+Enter sends from anywhere in the compose window (To, Subject, body…).
  function onComposeKey(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); e.stopPropagation(); send(); }
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

  // Detach the docked composer into its own OS window, carrying the draft over.
  async function popOut() {
    const seed = { to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "",
                   in_reply_to: c.in_reply_to, account_id: accountId, attachments };
    try { localStorage.setItem("raplmail.compose.seed", JSON.stringify(seed)); } catch {}
    const url = `${location.pathname}${location.search}#compose`;
    try {
      if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
        const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
        new WebviewWindow(`compose-${Date.now()}`, { url, title: "New message", width: 720, height: 680 });
      } else {
        window.open(url, "_blank", "width=720,height=680");
      }
      clearDraft();
      app.composing = null;   // close the docked panel; the window now owns it
    } catch (e) { notify(e.message || "Couldn't open a window", "error"); }
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

  // Keep the manually-resized size (CSS `resize` writes inline w/h) so a re-render
  // from dragging doesn't reset the box to its default size.
  $effect(() => {
    if (standalone || !panelEl) return;
    const ro = new ResizeObserver(() => { panelW = panelEl.offsetWidth; panelH = panelEl.offsetHeight; });
    ro.observe(panelEl);
    return () => ro.disconnect();
  });
  const dockStyle = $derived(
    standalone ? "" :
    (dragPos ? `left:${dragPos.x}px; top:${dragPos.y}px; right:auto; bottom:auto;` :
     app.settings.composePosition === "bottom-left" ? "left:18px; right:auto;" : "right:18px;")
    + (panelW ? ` width:${panelW}px; height:${panelH}px;` : "")
  );

  const TOOLS = [
    { cmd: "bold", label: "B", style: "font-weight:700" },
    { cmd: "italic", label: "I", style: "font-style:italic" },
    { cmd: "underline", label: "U", style: "text-decoration:underline" },
    { cmd: "insertUnorderedList", label: "• List" },
    { cmd: "insertOrderedList", label: "1. List" },
  ];
</script>

<div class="panel" class:standalone style={dockStyle} bind:this={panelEl} onkeydown={onComposeKey}>
  <header onpointerdown={onHeaderDown}>
    <span>New message</span>
    <div class="hbtns" onpointerdown={(e) => e.stopPropagation()}>
      {#if !standalone}
        <button class="x" title="Open in a separate window" onclick={popOut}>{@html icons.window || icons.external || "⧉"}</button>
      {/if}
      <button class="x" onclick={close}>{@html icons.close}</button>
    </div>
  </header>

  <div class="fields">
    <label class="f"><span>From</span>
      <div class="from-row">
        <select bind:value={accountId} onchange={() => (fromIdentity = "")}>
          {#each app.accounts as a}<option value={a.id}>{a.display_name && a.display_name !== a.email ? `${a.display_name} <${a.email}>` : a.email}</option>{/each}
        </select>
        {#if identitiesFor(accountId).length > 1}
          <select class="ident" bind:value={fromIdentity} title="Send as identity">
            {#each identitiesFor(accountId) as id}<option value={id.value}>{id.label}</option>{/each}
          </select>
        {/if}
      </div>
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
    {#if (app.settings.templates || []).length}
      <div class="tpl-pick">
        <button class="tool" title="Insert a template" onclick={() => (tplMenu = !tplMenu)}>{@html icons.drafts} Templates ⌄</button>
        {#if tplMenu}
          <div class="tpl-menu">
            {#each app.settings.templates as t}
              <button onmousedown={(e) => { e.preventDefault(); insertTemplate(t); }}>{t.name}</button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
    <button class="tool" title="Attach file" onclick={() => fileInput.click()}>{@html icons.attachment} Attach</button>
    <input bind:this={fileInput} type="file" multiple hidden onchange={(e) => readFiles(e.currentTarget.files)} />
  </div>

  <div class="editor" contenteditable="true" role="textbox" tabindex="0" aria-label="Message body"
    bind:this={editor} onkeydown={onEditorKey} oninput={onBodyInput} onclick={onEditorClick} ondrop={onDrop} ondragover={(e) => e.preventDefault()}
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
    <button class="btn" onclick={saveToDrafts} disabled={savingDraft} title="Save to your Drafts folder (syncs across devices)">
      {@html icons.save || icons.folder} {savingDraft ? "Saving…" : "Save draft"}
    </button>
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
    {#if pgpConfigured}
      <span class="pgp" title="OpenPGP">
        <button class="pgp-btn" class:on={pgpSign} onclick={() => (pgpSign = !pgpSign)} title="Sign with your PGP key">{@html icons.signature} Sign</button>
        <button class="pgp-btn" class:on={pgpEncrypt} onclick={() => (pgpEncrypt = !pgpEncrypt)} title="Encrypt to recipients' PGP keys">{@html icons.shieldCheck || icons.shield} Encrypt</button>
      </span>
    {/if}
    <button class="pgp-btn" class:on={requestReceipt} onclick={() => (requestReceipt = !requestReceipt)} title="Embed a read-receipt tracking pixel (recipient must be able to reach this app)">{@html icons.eye || icons.mail} Receipt</button>
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
  .panel { position: fixed; bottom: 18px; z-index: 50; width: min(720px, 96vw); height: min(640px, 88vh);
    display: flex; flex-direction: column; overflow: hidden; background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow);
    resize: both; min-width: 380px; min-height: 360px; max-width: 96vw; max-height: 92vh; }
  .panel.standalone { position: static; width: 100%; height: 100vh; border: none; border-radius: 0; box-shadow: none; resize: none; max-width: none; max-height: none; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--border); font-weight: 600; cursor: move; user-select: none; background: var(--surface-2); }
  .panel.standalone header { cursor: default; }
  .hbtns { display: flex; align-items: center; gap: 2px; }
  .x { color: var(--muted); font-size: 14px; padding: 3px 7px; border-radius: 6px; display: inline-flex; }
  .x:hover { background: var(--surface-3); color: var(--text); }
  .pgp { display: inline-flex; gap: 4px; }
  .pgp-btn { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 4px 9px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); }
  .pgp-btn.on { background: color-mix(in srgb, var(--accent) 18%, transparent); border-color: var(--accent); color: var(--accent); }
  .fields { padding: 4px 14px; }
  .f { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border); position: relative; }
  .f > span { width: 52px; color: var(--muted); font-size: 13px; }
  .f input, .f select { flex: 1; border: none; background: transparent; padding: 4px 0; color: var(--text); }
  .f input:focus, .f select:focus { border: none; }
  .from-row { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
  .from-row select { flex: 1; min-width: 0; }
  .from-row .ident { flex: 0 1 auto; max-width: 50%; color: var(--accent); }
  .cc-toggle { color: var(--accent); font-size: 13px; }
  .toolbar { display: flex; align-items: center; gap: 4px; padding: 7px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .tool { min-width: 28px; padding: 5px 8px; border-radius: 6px; color: var(--muted); font-size: 13px; }
  .tool:hover { background: var(--surface-3); color: var(--text); }
  .tspace { flex: 1; }
  .editor { flex: 1; padding: 14px; overflow-y: auto; outline: none; line-height: 1.6; color: var(--text); caret-color: var(--accent); }
  .editor:empty::before { content: attr(data-placeholder); color: var(--faint); }
  .editor :global(a) { color: var(--accent); }
  /* Spark-style collapsible quoted thread: a "•••" pill you type above. */
  .editor :global(.rapl-quoted-block) { margin-top: 10px; }
  .editor :global(.rapl-quote-toggle) {
    display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
    width: 34px; height: 18px; border-radius: 9px; background: var(--surface-3); color: var(--muted);
    font-size: 13px; letter-spacing: 1px; line-height: 1; user-select: none; margin: 2px 0; }
  .editor :global(.rapl-quote-toggle:hover) { background: var(--border); color: var(--text); }
  .editor :global(.rapl-quoted-block.collapsed .rapl-quoted-content) { display: none; }
  .attachments { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px; border-top: 1px solid var(--border); }
  .chip { display: inline-flex; align-items: center; gap: 6px; background: var(--surface-3); padding: 4px 8px; border-radius: 6px; font-size: 12px; }
  .chip button { color: var(--muted); }
  .chip button:hover { color: var(--danger); }
  footer { display: flex; align-items: center; gap: 8px; padding: 11px 14px; border-top: 1px solid var(--border); flex-wrap: wrap; }
  footer > .btn, footer .later > .btn, .pgp-btn { flex: none; white-space: nowrap; }
  .later { position: relative; flex: none; }
  .later-menu { position: absolute; bottom: 100%; left: 0; margin-bottom: 6px; z-index: 20; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; min-width: 220px; }
  .later-menu > button { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; text-align: left; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
  .later-menu > button:hover { background: var(--accent); color: #fff; }
  .later-menu .when { color: var(--muted); font-size: 12px; }
  .later-menu > button:hover .when { color: #e7e9ff; }
  .later-menu .custom { display: flex; gap: 6px; padding: 6px 6px 2px; border-top: 1px solid var(--border); margin-top: 4px; }
  .later-menu .custom input { flex: 1; min-width: 0; font-size: 12px; padding: 5px 6px; }
  .later-menu .custom .sm { padding: 5px 10px; font-size: 12px; }
  .tpl-pick { position: relative; }
  .tpl-menu { position: absolute; bottom: 100%; left: 0; margin-bottom: 6px; z-index: 20; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; min-width: 180px; max-height: 260px; overflow-y: auto; }
  .tpl-menu button { text-align: left; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
  .tpl-menu button:hover { background: var(--accent); color: #fff; }
  .sigpick { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); }
  .sigpick select { padding: 5px 8px; }
  .hint { color: var(--faint); font-size: 12px; margin-left: auto; }
</style>
