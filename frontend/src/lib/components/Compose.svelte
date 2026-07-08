<script>
  import { onMount, onDestroy } from "svelte";
  import { app, notify, loadAccountsAndFolders, queueSend, snoozePresets, presetWhen, confirmDialog, saveSettings, aiEnabled, openAiAssistant } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { signatures as sigApi, compose as composeApi, ai } from "../api.js";
  import RecipientInput from "./RecipientInput.svelte";
  import { t, currentLocale } from "../i18n.svelte.js";
  import { mdToHtml } from "../markdown.js";

  // Native spell-check (WebView2/Chromium + OS dictionaries). One attribute - no
  // dependency, works offline. `lang` steers the dictionary. WebView2 checks one
  // language at a time, so the composer has a language switcher (persisted) for
  // people who write in more than one language (e.g. English UI, Czech mail).
  const spellOn = $derived(app.settings.spellCheck !== false);
  const SPELL_LANGS = [
    { id: "auto", label: "Auto" }, { id: "en", label: "EN" }, { id: "cs", label: "CS" },
    { id: "sk", label: "SK" }, { id: "de", label: "DE" }, { id: "pl", label: "PL" },
    { id: "es", label: "ES" }, { id: "fr", label: "FR" }, { id: "it", label: "IT" },
  ];
  let spellSel = $state(app.settings.spellCheckLang || "auto");
  const spellLang = $derived(spellSel === "auto" ? currentLocale() : spellSel);
  function setSpellLang(v) { spellSel = v; saveSettings({ spellCheckLang: v }); }

  // --- AI writing assistant (rephrase / tone / translate / grammar / ask) ---
  let mdEl;                        // <textarea> ref (markdown mode) for selection ops
  let aiMenu = $state(false);
  let aiBusy = $state(false);
  let aiToneMenu = $state(false);
  let aiTransMenu = $state(false);
  let aiCustom = $state("");
  let _savedRange = null;          // cloned selection range (rich mode; imperative only)
  let _savedText = $state("");     // selected text (either mode); "" ⇒ act on whole body
  const TONES = ["professional", "friendly", "formal", "concise", "confident"];
  const TRANSLATE_LANGS = [
    { label: "English", name: "English" }, { label: "Čeština", name: "Czech" },
    { label: "Slovenčina", name: "Slovak" }, { label: "Deutsch", name: "German" },
    { label: "Español", name: "Spanish" }, { label: "Français", name: "French" },
    { label: "Italiano", name: "Italian" }, { label: "Polski", name: "Polish" },
  ];

  // Capture the current selection when the menu opens (mousedown fires before the
  // click steals focus / collapses the selection). Cloned so it survives the menu.
  function openAiMenu(e) {
    e.preventDefault();
    _savedRange = null; _savedText = "";
    if (mdMode) {
      if (mdEl && mdEl.selectionStart !== mdEl.selectionEnd)
        _savedText = mdEl.value.substring(mdEl.selectionStart, mdEl.selectionEnd);
    } else {
      const sel = window.getSelection();
      if (sel && sel.rangeCount && !sel.isCollapsed && editor &&
          editor.contains(sel.getRangeAt(0).commonAncestorContainer)) {
        _savedRange = sel.getRangeAt(0).cloneRange();
        _savedText = sel.toString();
      }
    }
    aiToneMenu = false; aiTransMenu = false;
    aiMenu = !aiMenu;
  }

  // Replace the editable body (keeping the signature + quoted thread) with text.
  function replaceBody(text) {
    if (!editor) return;
    for (const n of [...editor.childNodes]) {
      if (n.nodeType === 1 && n.classList &&
          (n.classList.contains("rapl-sig-wrap") || n.classList.contains("rapl-quoted-block"))) continue;
      editor.removeChild(n);
    }
    const frag = document.createDocumentFragment();
    for (const line of text.split("\n")) {
      const div = document.createElement("div");
      if (line.trim() === "") div.innerHTML = "<br>"; else div.textContent = line;
      frag.appendChild(div);
    }
    editor.insertBefore(frag, editor.firstChild);
  }

  function applyRewrite(out) {
    if (mdMode) {
      if (_savedText && mdEl && mdEl.selectionStart !== mdEl.selectionEnd) {
        const s = mdEl.selectionStart, en = mdEl.selectionEnd;
        mdSource = mdSource.slice(0, s) + out + mdSource.slice(en);
      } else {
        mdSource = out;
      }
    } else if (_savedRange) {
      editor.focus();
      const sel = window.getSelection();
      sel.removeAllRanges(); sel.addRange(_savedRange);
      document.execCommand("insertText", false, out);   // undoable
    } else {
      replaceBody(out);
    }
    dirty = true; scheduleSave();
    _savedRange = null; _savedText = "";
  }

  async function runRewrite(action, instruction = "") {
    const source = (_savedText && _savedText.trim())
      ? _savedText : (mdMode ? mdSource : bodyPlainNoQuote());
    if (!source.trim()) { notify(t("compose.aiNothing"), "error"); return; }
    aiBusy = true; app.aiBusy = true;
    try {
      const r = await ai.rewrite({ text: source, action, instruction });
      const out = (r.result || "").trim();
      if (!out) { notify(t("compose.aiEmpty"), "error"); return; }
      applyRewrite(out);
      aiMenu = false;
    } catch (e) { notify(e.message, "error"); }
    finally { aiBusy = false; app.aiBusy = false; }
  }
  function runCustom() {
    const q = aiCustom.trim();
    if (!q) return;
    aiCustom = "";
    runRewrite("custom", q);
  }
  function openAssistantFromCompose() {
    aiMenu = false;
    openAiAssistant();   // opens the full assistant; user adds mails as context there
  }

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
  let mdMode = $state(false);       // compose in Markdown (compiled to HTML on send)
  let mdSource = $state("");        // raw markdown body while mdMode is on
  let seededQuote = "";             // reply/forward quoted block, kept aside in md mode

  function defaultSigFor(acctId) {
    // This account's OWN signature always wins - its default first, then any of
    // its signatures - before falling back to a global (all-accounts) one. The
    // old code fell through to sigs[0], so writing from A123 grabbed the
    // rapl-group signature just because it happened to be first / the global
    // default. Never borrow another account's signature.
    return sigs.find((s) => s.account_id === acctId && s.is_default)
        || sigs.find((s) => s.account_id === acctId)
        || sigs.find((s) => s.account_id == null && s.is_default)
        || sigs.find((s) => s.account_id == null)
        || null;
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
  // --- Markdown compose mode ---------------------------------------------
  // The current body as plain text, minus the quoted thread + signature (those
  // are re-attached separately), used to seed the markdown editor.
  function bodyPlainNoQuote() {
    if (!editor) return "";
    const clone = editor.cloneNode(true);
    clone.querySelectorAll(".rapl-quoted-block, .rapl-sig-wrap").forEach((n) => n.remove());
    return (clone.innerText || "").trim();
  }
  // On send: compiled markdown + the chosen signature + the reply/forward quote.
  function composeMdHtml() {
    let out = mdToHtml(mdSource);
    if (signatureId !== "none") {
      const sig = sigs.find((s) => String(s.id) === String(signatureId));
      if (sig) out += `<div><br></div><div class="rapl-sig">${sigHtml(sig)}</div>`;
    }
    if (seededQuote) out += seededQuote;
    return out;
  }
  function toggleMd() {
    if (!mdMode) {
      mdSource = bodyPlainNoQuote();
      mdMode = true;
    } else {
      // Back to rich text: render the markdown into the editor + restore the quote.
      if (editor) { editor.innerHTML = mdToHtml(mdSource) + (seededQuote || ""); applySignature(); }
      mdMode = false;
    }
    dirty = true;
    scheduleSave();
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

  // Local autosave keeps a *list* of recent drafts (newest first). Compose always
  // opens NEW - you restore a previous draft from the "Drafts" menu in the header,
  // rather than having one silently reappear.
  const DRAFTS_KEY = "raplmail.drafts";
  const DRAFTS_MAX = 8;
  let draftTimer;
  let draftId = null;                 // which stored draft this compose maps to
  let recentDrafts = $state([]);      // for the header menu
  let draftsMenu = $state(false);

  function loadRecentDrafts() {
    try { recentDrafts = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "[]"); }
    catch { recentDrafts = []; }
    return recentDrafts;
  }
  function persistDrafts(list) {
    const trimmed = list.slice(0, DRAFTS_MAX);
    try { localStorage.setItem(DRAFTS_KEY, JSON.stringify(trimmed)); } catch {}
    recentDrafts = trimmed;
  }
  // A short label for the menu: subject, else first recipient, else "(empty)".
  function draftLabel(d) {
    const s = (d.subject || "").trim();
    if (s) return s;
    const to = (d.to || "").split(",")[0].trim();
    return to ? `To: ${to}` : "(empty draft)";
  }

  // Is there real user content beyond the auto-inserted signature?
  function userTyped() {
    if (c.to.trim() || (c.cc || "").trim() || c.subject.trim()) return true;
    if (!editor) return false;
    const clone = editor.cloneNode(true);
    clone.querySelector(".rapl-sig-wrap")?.remove();
    return !!clone.innerText.trim();
  }
  function saveDraft() {
    // `closed` = this compose finished (sent/scheduled/discarded) - the
    // onDestroy flush must not resurrect it into the drafts list.
    if (standalone || closed) return;
    const list = loadRecentDrafts().filter((d) => d.id !== draftId);
    if (!userTyped()) { persistDrafts(list); return; }   // nothing worth keeping
    persistDrafts([{
      id: draftId, to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "",
      account_id: accountId, in_reply_to: c.in_reply_to || "", ts: Date.now(),
    }, ...list]);
  }
  function scheduleSave() { clearTimeout(draftTimer); draftTimer = setTimeout(saveDraft, 700); }
  function clearDraft() { persistDrafts(loadRecentDrafts().filter((d) => d.id !== draftId)); }
  function removeDraft(id) { persistDrafts(loadRecentDrafts().filter((d) => d.id !== id)); }
  // Load a stored draft into the current composer (and keep editing under its id).
  function restoreDraft(d) {
    c.to = d.to || ""; c.cc = d.cc || ""; c.subject = d.subject || "";
    if (d.account_id) accountId = d.account_id;
    if (c.cc) showCc = true;
    c.in_reply_to = d.in_reply_to || "";
    if (editor) { editor.innerHTML = d.html || ""; applySignature(); }
    draftId = d.id;
    dirty = true; draftsMenu = false;
    focusTop();
  }
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
    // Honor a seeded send-as identity (the address the mail was addressed to) so
    // replies / new mail go out from the right alias, not just the primary.
    if (c.from_addr) {
      const opts = identitiesFor(accountId).map((o) => o.value);
      if (opts.includes(c.from_addr)) fromIdentity = c.from_addr;
    }
    if (c.cc) showCc = true;
    if (Array.isArray(c.attachments)) attachments = c.attachments;
    seededQuote = c.html || "";   // reply/forward quote - re-appended after markdown on send
    if (editor && c.html) editor.innerHTML = c.html;
    try {
      sigs = await sigApi.list();
      const d = defaultSigFor(accountId);
      signatureId = d ? d.id : "none";
    } catch {}
    applySignature();

    // Always open a fresh message. Previous drafts are never auto-restored - they
    // live in the "Drafts" menu in the header, restored on demand.
    draftId = (crypto.randomUUID ? crypto.randomUUID() : `d${Date.now()}${Math.random()}`);
    loadRecentDrafts();
    focusTop();
    scheduleSave();
    mounted = true;
  });

  // True once the user actually edits something (vs. the seeded reply/forward
  // content), so close() only confirms when there's genuine unsaved work.
  let mounted = false;
  let closed = false;
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

  let confirmDiscard = $state(false);
  function close() {
    // Persist whatever's typed before tearing down so the X never silently
    // drops a draft (the 700ms debounce hadn't fired yet). If there's real
    // unsaved content, ask in-app (no native "tauri.localhost says" box).
    flushSave();
    if (dirty && userTyped()) { confirmDiscard = true; return; }
    doClose();
  }
  function doClose() {
    confirmDiscard = false;
    closed = true;   // whatever should be kept was already flushed/saved
    if (standalone) { window.close(); return; }
    app.composing = null;
  }
  // "Discard": drop the draft close() just flushed, then close for good.
  function discardAndClose() {
    clearDraft();
    doClose();
  }
  async function saveDraftAndClose() {
    confirmDiscard = false;
    try { await saveToDrafts(); } catch {}
    doClose();
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
    const url = prompt(t("compose.linkUrlPrompt"), "https://");
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
  let smimeSign = $state(false);
  let smimeEncrypt = $state(false);
  const smimeConfigured = $derived(!!(app.settings.smimeCert || (app.settings.smimeCerts || []).length));
  let requestReceipt = $state(false);
  const pgpConfigured = $derived(!!(app.settings.pgpPrivateKey || (app.settings.pgpPublicKeys || []).length));

  let savingDraft = $state(false);
  let draftUid = $state(null);   // IMAP UID of the last server-saved draft (for replace)
  async function saveToDrafts() {
    if (!accountId) { notify(t("compose.pickAccount"), "error"); return; }
    savingDraft = true;
    try {
      const r = await composeApi.saveDraft({ ...buildPayload(), replace_uid: draftUid });
      draftUid = r.uid ?? draftUid;
      clearDraft();   // server now holds it; drop the local autosave copy
      notify(t("compose.savedToDrafts", { folder: r.folder }));
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
      smime_sign: smimeSign,
      smime_encrypt: smimeEncrypt,
      request_receipt: requestReceipt,
      to,
      cc,
      bcc: autoBccFor([...to, ...cc]),
      subject: c.subject,
      html: mdMode ? composeMdHtml() : outgoingHtml(),
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
    const text = `${c.subject} ${mdMode ? mdSource : (editor?.innerText || "")}`;
    return _ATTACH_HINTS.test(text);
  }

  async function send() {
    if (!accountId) { notify(t("compose.pickAccount"), "error"); return; }
    if (c.to.trim() === "") { notify(t("compose.addRecipient"), "error"); return; }
    if (c.subject.trim() === "" &&
        !(await confirmDialog({ title: t("compose.sendNoSubjectTitle"), confirmLabel: t("compose.sendAnyway") }))) return;
    if (attachmentMissing() &&
        !(await confirmDialog({ title: t("compose.noAttachmentTitle"), message: t("compose.noAttachmentMsg"), confirmLabel: t("compose.sendAnyway") }))) return;
    const seed = { to: c.to, cc: c.cc, subject: c.subject, html: editor?.innerHTML || "", in_reply_to: c.in_reply_to, account_id: accountId, attachments };
    clearDraft();
    closed = true;   // don't let the unmount flush re-save the sent message
    queueSend(buildPayload(), seed);
  }

  async function sendLater(iso, label) {
    if (!accountId) { notify(t("compose.pickAccount"), "error"); return; }
    if (c.to.trim() === "") { notify(t("compose.addRecipient"), "error"); return; }
    if (c.subject.trim() === "" &&
        !(await confirmDialog({ title: t("compose.scheduleNoSubjectTitle"), confirmLabel: t("compose.scheduleAnyway") }))) return;
    if (attachmentMissing() &&
        !(await confirmDialog({ title: t("compose.noAttachmentTitle"), message: t("compose.noAttachmentMsg"), confirmLabel: t("compose.scheduleAnyway") }))) return;
    laterMenu = false;
    try {
      await composeApi.send({ ...buildPayload(), send_at: iso });
      clearDraft();
      closed = true;
      notify(t("compose.scheduled", { label }));
      if (standalone) window.close(); else app.composing = null;
    } catch (e) { notify(t("compose.couldntSchedule", { error: e.message }), "error"); }
  }

  // datetime-local needs "YYYY-MM-DDTHH:MM" in local time.
  function nowLocal() {
    const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    return d.toISOString().slice(0, 16);
  }
  function sendCustom() {
    if (!customWhen) { notify(t("compose.pickDateTime"), "error"); return; }
    const d = new Date(customWhen);
    if (isNaN(d.getTime()) || d <= new Date()) { notify(t("compose.pickFutureTime"), "error"); return; }
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
        new WebviewWindow(`compose-${Date.now()}`, { url, title: t("compose.newMessage"), width: 720, height: 680 });
      } else {
        window.open(url, "_blank", "width=720,height=680");
      }
      clearDraft();
      app.composing = null;   // close the docked panel; the window now owns it
    } catch (e) { notify(e.message || t("compose.couldntOpenWindow"), "error"); }
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
  // Localized tooltip for each formatting tool (the button faces stay symbolic:
  // B / I / U / • / 1.). A helper keeps the i18n t() out of the {#each TOOLS as t}
  // block, where `t` is the loop item and would otherwise shadow it.
  const toolTitle = (cmd) => t(`compose.tool.${cmd}`);
</script>

<div class="panel" class:standalone style={dockStyle} bind:this={panelEl} onkeydown={onComposeKey}>
  {#if confirmDiscard}
    <div class="discard-veil" role="dialog" aria-modal="true" aria-label={t("compose.unsavedMessage")}>
      <div class="discard-box">
        <b>{t("compose.keepDraft")}</b>
        <p>{t("compose.unsavedChanges")}</p>
        <div class="discard-btns">
          <button class="btn primary" onclick={saveDraftAndClose}>{t("compose.saveToDrafts")}</button>
          <button class="btn ghost" onclick={() => (confirmDiscard = false)}>{t("compose.keepEditing")}</button>
          <button class="btn ghost danger" onclick={discardAndClose}>{t("compose.discard")}</button>
        </div>
      </div>
    </div>
  {/if}
  <header onpointerdown={onHeaderDown}>
    <span>{t("compose.newMessage")}</span>
    <div class="hbtns" onpointerdown={(e) => e.stopPropagation()}>
      {#if !standalone && recentDrafts.length}
        <div class="drafts-pick">
          <button class="hbtn" title={t("compose.restoreSavedDraft")} onclick={() => (draftsMenu = !draftsMenu)}>
            {@html icons.drafts || icons.edit || ""} {t("compose.drafts")} <span class="dcount">{recentDrafts.length}</span> ⌄
          </button>
          {#if draftsMenu}
            <div class="drafts-menu">
              {#each recentDrafts as d (d.id)}
                <div class="drow">
                  <button class="dopen" onclick={() => restoreDraft(d)} title={t("compose.restoreThisDraft")}>{draftLabel(d)}</button>
                  <button class="ddel" title={t("compose.deleteDraft")} onclick={() => removeDraft(d.id)}>{@html icons.close}</button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
      {#if !standalone}
        <button class="x" title={t("compose.openSeparateWindow")} onclick={popOut}>{@html icons.window || icons.external || "⧉"}</button>
      {/if}
      <button class="x" onclick={close}>{@html icons.close}</button>
    </div>
  </header>

  <div class="fields">
    <label class="f"><span>{t("compose.from")}</span>
      <div class="from-row">
        {#if app.accounts.length > 1}
          <span class="from-dot" style="background:{app.accounts.find((a) => a.id === accountId)?.color || 'var(--muted)'}" title={t("compose.sendingFromAccount")}></span>
        {/if}
        <select bind:value={accountId} onchange={() => (fromIdentity = "")}>
          {#each app.accounts as a}<option value={a.id}>{a.display_name && a.display_name !== a.email ? `${a.display_name} <${a.email}>` : a.email}</option>{/each}
        </select>
        {#if identitiesFor(accountId).length > 1}
          <select class="ident" bind:value={fromIdentity} title={t("compose.sendAsIdentity")}>
            {#each identitiesFor(accountId) as id}<option value={id.value}>{id.label}</option>{/each}
          </select>
        {/if}
      </div>
    </label>
    <div class="f"><span>{t("compose.to")}</span>
      <RecipientInput bind:value={c.to} placeholder={t("compose.toPlaceholder")} />
      {#if !showCc}<button class="cc-toggle" onclick={() => (showCc = true)}>{t("compose.cc")}</button>{/if}
    </div>
    {#if showCc}<div class="f"><span>{t("compose.cc")}</span><RecipientInput bind:value={c.cc} /></div>{/if}
    <label class="f"><span>{t("compose.subject")}</span><input bind:value={c.subject} spellcheck={spellOn} lang={spellLang} /></label>
  </div>

  <div class="toolbar">
    {#if !mdMode}
      {#each TOOLS as t}
        <button class="tool" title={toolTitle(t.cmd)} style={t.style || ""} onmousedown={(e) => { e.preventDefault(); exec(t.cmd); }}>{t.label}</button>
      {/each}
      <button class="tool" title={t("compose.insertLink")} onmousedown={(e) => { e.preventDefault(); addLink(); }}>{@html icons.link}</button>
      <button class="tool" title={t("compose.clearFormatting")} onmousedown={(e) => { e.preventDefault(); exec("removeFormat"); }}>{@html icons.clearFormat}</button>
    {/if}
    <button class="tool md-toggle" class:on={mdMode} title={t("compose.markdownMode")} onclick={toggleMd}>{t("compose.markdown")}</button>
    {#if aiEnabled()}
      <div class="ai-pick">
        <button class="tool ai" class:busy={aiBusy} title={t("compose.aiTitle")} onmousedown={openAiMenu} disabled={aiBusy}>
          {@html icons.bolt} {aiBusy ? t("compose.aiWorking") : t("compose.ai")} ⌄
        </button>
        {#if aiMenu}
          <div class="ai-menu">
            <div class="ai-src">{_savedText.trim() ? t("compose.aiOnSelection") : t("compose.aiOnDraft")}</div>
            <button onclick={() => runRewrite("rephrase")}>{@html icons.sparkles || icons.bolt} {t("compose.aiRephrase")}</button>
            <button onclick={() => runRewrite("improve")}>{t("compose.aiImprove")}</button>
            <button onclick={() => runRewrite("shorten")}>{t("compose.aiShorten")}</button>
            <button onclick={() => runRewrite("expand")}>{t("compose.aiExpand")}</button>
            <button onclick={() => runRewrite("grammar")}>{t("compose.aiGrammar")}</button>
            <div class="ai-sub">
              <button class="ai-subhead" onclick={() => { aiToneMenu = !aiToneMenu; aiTransMenu = false; }}>{t("compose.aiTone")} <span>›</span></button>
              {#if aiToneMenu}<div class="ai-submenu">
                {#each TONES as tone}<button onclick={() => runRewrite(tone)}>{t("compose.tone." + tone)}</button>{/each}
              </div>{/if}
            </div>
            <div class="ai-sub">
              <button class="ai-subhead" onclick={() => { aiTransMenu = !aiTransMenu; aiToneMenu = false; }}>{t("compose.aiTranslate")} <span>›</span></button>
              {#if aiTransMenu}<div class="ai-submenu">
                {#each TRANSLATE_LANGS as l}<button onclick={() => runRewrite("translate", l.name)}>{l.label}</button>{/each}
              </div>{/if}
            </div>
            <div class="ai-custom">
              <input placeholder={t("compose.aiAskPlaceholder")} bind:value={aiCustom}
                onkeydown={(e) => { if (e.key === "Enter") runCustom(); }} />
            </div>
            <button class="ai-assistant-link" onclick={openAssistantFromCompose}>{@html icons.chat || icons.mail} {t("compose.aiAssistant")}</button>
          </div>
        {/if}
      </div>
    {/if}
    {#if spellOn}
      <select class="spell-lang" title={t("compose.spellLang")} value={spellSel} onchange={(e) => setSpellLang(e.currentTarget.value)}>
        {#each SPELL_LANGS as l}<option value={l.id}>{l.label}</option>{/each}
      </select>
    {/if}
    <span class="tspace"></span>
    {#if !mdMode && (app.settings.templates || []).length}
      <div class="tpl-pick">
        <button class="tool" title={t("compose.insertTemplate")} onclick={() => (tplMenu = !tplMenu)}>{@html icons.drafts} {t("compose.templates")} ⌄</button>
        {#if tplMenu}
          <div class="tpl-menu">
            {#each app.settings.templates as t}
              <button onmousedown={(e) => { e.preventDefault(); insertTemplate(t); }}>{t.name}</button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
    <button class="tool" title={t("compose.attachFile")} onclick={() => fileInput.click()}>{@html icons.attachment} {t("compose.attach")}</button>
    <input bind:this={fileInput} type="file" multiple hidden onchange={(e) => readFiles(e.currentTarget.files)} />
  </div>

  <div class="editor" class:hidden={mdMode} contenteditable="true" role="textbox" tabindex="0" aria-label={t("compose.messageBody")}
    spellcheck={spellOn} lang={spellLang}
    bind:this={editor} onkeydown={onEditorKey} oninput={onBodyInput} onclick={onEditorClick} ondrop={onDrop} ondragover={(e) => e.preventDefault()}
    data-placeholder={t("compose.bodyPlaceholder")}></div>
  {#if mdMode}
    <textarea class="editor mdbody" bind:this={mdEl} bind:value={mdSource} oninput={onBodyInput} spellcheck={spellOn} lang={spellLang}
      aria-label={t("compose.messageBody")} placeholder={t("compose.markdownPlaceholder")}></textarea>
  {/if}

  {#if attachments.length}
    <div class="attachments">
      {#each attachments as a, i}
        <span class="chip">{@html icons.attachment} {a.filename}<button onclick={() => removeAttachment(i)}>{@html icons.close}</button></span>
      {/each}
    </div>
  {/if}

  <footer>
    <button class="btn primary" onclick={send}>{t("compose.send")}</button>
    <button class="btn" onclick={saveToDrafts} disabled={savingDraft} title={t("compose.saveDraftTitle")}>
      {@html icons.save || icons.folder} {savingDraft ? t("compose.saving") : t("compose.saveDraft")}
    </button>
    <div class="later">
      <button class="btn" onclick={() => (laterMenu = !laterMenu)} title={t("compose.sendLater")}>{@html icons.clock} {t("compose.later")} ⌄</button>
      {#if laterMenu}
        <div class="later-menu">
          {#each snoozePresets().filter((p) => p.iso) as p}
            <button onclick={() => sendLater(p.iso, p.label)}><span>{p.label}</span><span class="when">{presetWhen(p.at)}</span></button>
          {/each}
          <div class="custom">
            <input type="datetime-local" bind:value={customWhen} min={nowLocal()} />
            <button class="btn primary sm" onclick={sendCustom}>{t("compose.schedule")}</button>
          </div>
          <div class="later-note">{t("schedule.localOnlyShort")}</div>
        </div>
      {/if}
    </div>
    {#if pgpConfigured}
      <span class="pgp" title="OpenPGP">
        <button class="pgp-btn" class:on={pgpSign} onclick={() => (pgpSign = !pgpSign)} title={t("compose.signTitle")}>{@html icons.signature} {t("compose.sign")}</button>
        <button class="pgp-btn" class:on={pgpEncrypt} onclick={() => (pgpEncrypt = !pgpEncrypt)} title={t("compose.encryptTitle")}>{@html icons.shieldCheck || icons.shield} {t("compose.encrypt")}</button>
      </span>
    {/if}
    {#if smimeConfigured}
      <span class="pgp" title="S/MIME">
        <button class="pgp-btn" class:on={smimeSign} onclick={() => (smimeSign = !smimeSign)} title={t("compose.smimeSignTitle")}>{@html icons.signature} {t("compose.smimeSign")}</button>
        <button class="pgp-btn" class:on={smimeEncrypt} onclick={() => (smimeEncrypt = !smimeEncrypt)} title={t("compose.smimeEncryptTitle")}>{@html icons.shield || icons.shieldCheck} {t("compose.smimeEncrypt")}</button>
      </span>
    {/if}
    <button class="pgp-btn" class:on={requestReceipt} onclick={() => (requestReceipt = !requestReceipt)} title={t("compose.receiptTitle")}>{@html icons.eye || icons.mail} {t("compose.receipt")}</button>
    {#if sigs.length}
      <label class="sigpick" title={t("compose.signature")}>{@html icons.signature}
        <select bind:value={signatureId} onchange={applySignature}>
          <option value="none">{t("compose.noSignature")}</option>
          {#each sigs as s}<option value={s.id}>{s.name}</option>{/each}
        </select>
      </label>
    {/if}
    <span class="hint">{t("compose.ctrlEnterHint")}</span>
  </footer>
</div>

<style>
  .panel { position: fixed; bottom: 18px; z-index: 50; width: min(720px, 96vw); height: min(640px, 88vh);
    display: flex; flex-direction: column; overflow: hidden; background: var(--surface); color: var(--text);
    border: 1px solid var(--hairline); border-radius: var(--radius); box-shadow: var(--shadow-lg);
    resize: both; min-width: 380px; min-height: 360px; max-width: 96vw; max-height: 92vh;
    animation: rise-in var(--t-slow) var(--ease); }
  .panel.standalone { position: static; width: 100%; height: 100vh; border: none; border-radius: 0; box-shadow: none; resize: none; max-width: none; max-height: none; animation: none; }
  .discard-veil { position: absolute; inset: 0; z-index: 20; background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center; border-radius: var(--radius);
    animation: fade-in var(--t) var(--ease); }
  .discard-box { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius);
    box-shadow: var(--shadow-lg); padding: 18px 20px; max-width: 340px; text-align: center;
    animation: pop-in var(--t) var(--ease); }
  .discard-box b { font-size: 15px; }
  .discard-box p { margin: 6px 0 14px; color: var(--muted); font-size: 13px; }
  .discard-btns { display: flex; flex-direction: column; gap: 8px; }
  .discard-btns .danger { color: var(--danger); }
  header { display: flex; justify-content: space-between; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--border); font-weight: 600; cursor: move; user-select: none; background: var(--surface-2); }
  .panel.standalone header { cursor: default; }
  .hbtns { display: flex; align-items: center; gap: 2px; }
  .x { color: var(--muted); font-size: 14px; padding: 3px 7px; border-radius: 6px; display: inline-flex; }
  .x:hover { background: var(--surface-3); color: var(--text); }
  .drafts-pick { position: relative; margin-right: 4px; }
  .hbtn { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: var(--muted); padding: 4px 9px; border-radius: 6px; }
  .hbtn:hover { background: var(--surface-3); color: var(--text); }
  .dcount { background: var(--accent); color: #fff; border-radius: 999px; font-size: 10px; padding: 0 5px; }
  .drafts-menu { position: absolute; top: 100%; right: 0; margin-top: 6px; z-index: 30; min-width: 240px; max-width: 320px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm); box-shadow: var(--shadow-lg); padding: 4px;
    animation: pop-in var(--t) var(--ease); transform-origin: top right; }
  .drow { display: flex; align-items: center; gap: 4px; }
  .dopen { flex: 1; text-align: left; font-size: 13px; font-weight: 400; padding: 7px 9px; border-radius: 6px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dopen:hover { background: var(--surface-3); }
  .ddel { color: var(--muted); padding: 5px; border-radius: 6px; display: inline-flex; }
  .ddel:hover { color: var(--danger); background: var(--surface-3); }
  .pgp { display: inline-flex; gap: 4px; }
  .pgp-btn { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 4px 9px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); }
  .pgp-btn.on { background: color-mix(in srgb, var(--accent) 18%, transparent); border-color: var(--accent); color: var(--accent); }
  .fields { padding: 4px 14px; }
  .f { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border); position: relative; }
  .f > span { width: 52px; color: var(--muted); font-size: 13px; }
  .f input, .f select { flex: 1; border: none; background: transparent; padding: 4px 0; color: var(--text); }
  .f input:focus, .f select:focus { border: none; }
  .from-row { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
  .from-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
  .from-row select { flex: 1; min-width: 0; }
  .from-row .ident { flex: 0 1 auto; max-width: 50%; color: var(--accent); }
  .cc-toggle { color: var(--accent); font-size: 13px; }
  .toolbar { display: flex; align-items: center; gap: 4px; padding: 7px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .tool { min-width: 28px; padding: 5px 8px; border-radius: 6px; color: var(--muted); font-size: 13px; }
  .tool:hover { background: var(--surface-3); color: var(--text); }
  .tool.md-toggle { font-weight: 700; font-family: ui-monospace, Consolas, monospace; }
  .tool.md-toggle.on { background: var(--accent-soft); color: var(--accent); }
  .tspace { flex: 1; }
  .editor { flex: 1; padding: 14px; overflow-y: auto; outline: none; line-height: 1.6; color: var(--text); caret-color: var(--accent); }
  .editor.hidden { display: none; }
  textarea.editor.mdbody { border: none; background: transparent; width: 100%; resize: none; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; white-space: pre-wrap; }
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
  .later-menu { position: absolute; bottom: 100%; left: 0; margin-bottom: 6px; z-index: 20; background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm); box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column; min-width: 220px; animation: pop-in var(--t) var(--ease); transform-origin: bottom left; }
  .later-menu > button { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; text-align: left; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
  .later-menu > button:hover { background: var(--accent); color: #fff; }
  .later-menu .when { color: var(--muted); font-size: 12px; }
  .later-menu > button:hover .when { color: #e7e9ff; }
  .later-menu .custom { display: flex; gap: 6px; padding: 6px 6px 2px; border-top: 1px solid var(--border); margin-top: 4px; }
  .later-menu .custom input { flex: 1; min-width: 0; font-size: 12px; padding: 5px 6px; }
  .later-menu .custom .sm { padding: 5px 10px; font-size: 12px; }
  .later-menu .later-note { padding: 8px 8px 4px; margin-top: 2px; color: var(--muted); font-size: 11px; line-height: 1.45; }
  .tool.ai { color: var(--accent); font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
  .tool.ai :global(svg) { width: 14px; height: 14px; }
  .tool.ai.busy { opacity: 0.7; }
  .spell-lang { font-size: 11px; padding: 3px 6px; border-radius: 6px; background: var(--surface-2);
    border: 1px solid var(--border); color: var(--muted); }
  .ai-pick { position: relative; }
  .ai-menu { position: absolute; top: 100%; left: 0; margin-top: 6px; z-index: 30; min-width: 210px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column;
    animation: pop-in var(--t) var(--ease); transform-origin: top left; }
  .ai-menu > button, .ai-subhead { display: flex; align-items: center; gap: 7px; text-align: left; width: 100%;
    padding: 7px 10px; border-radius: 6px; font-size: 13px; color: var(--text); }
  .ai-menu > button:hover, .ai-subhead:hover { background: var(--accent); color: #fff; }
  .ai-menu > button :global(svg) { width: 14px; height: 14px; }
  .ai-src { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint);
    padding: 5px 10px 3px; }
  .ai-sub { position: relative; }
  .ai-subhead { justify-content: space-between; }
  .ai-subhead span { color: var(--faint); }
  .ai-submenu { display: flex; flex-direction: column; padding: 2px 0 2px 10px; }
  .ai-submenu button { text-align: left; padding: 6px 10px; border-radius: 6px; font-size: 13px; color: var(--text); }
  .ai-submenu button:hover { background: var(--accent); color: #fff; }
  .ai-custom { padding: 6px 6px 2px; border-top: 1px solid var(--border); margin-top: 4px; }
  .ai-custom input { width: 100%; box-sizing: border-box; font-size: 12px; padding: 6px 8px;
    background: var(--surface-3); border: 1px solid var(--border); border-radius: 6px; color: var(--text); }
  .ai-assistant-link { color: var(--accent) !important; font-size: 12px !important; border-top: 1px solid var(--border); margin-top: 4px; }
  .ai-assistant-link:hover { background: var(--surface-3) !important; color: var(--accent) !important; }
  .tpl-pick { position: relative; }
  .tpl-menu { position: absolute; bottom: 100%; left: 0; margin-bottom: 6px; z-index: 20; background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm); box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column; min-width: 180px; max-height: 260px; overflow-y: auto; animation: pop-in var(--t) var(--ease); transform-origin: bottom left; }
  .tpl-menu button { text-align: left; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
  .tpl-menu button:hover { background: var(--accent); color: #fff; }
  .sigpick { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); }
  .sigpick select { padding: 5px 8px; }
  .hint { color: var(--faint); font-size: 12px; margin-left: auto; }
</style>
