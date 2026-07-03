<script>
  import { app, markDone, openCompose, searchAddress, approveSender, blockSender, muteSender, muteThread, notify, isVip, toggleVip, trustSender, untrustSender, isTrustedSender } from "../store.svelte.js";
  import { messages as messagesApi, openAttachment, saveAttachment, saveEml, revealPath, openExternal, unfurl, ai, fetchAttachmentForCompose } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc, splitQuoted, autoLink } from "../email.js";
  import { t } from "../i18n.svelte.js";
  import ThreadView from "./ThreadView.svelte";

  // A conversation opened explicitly (threadKey set) always shows as a thread,
  // independent of the list-grouping setting — so "View conversation" works even
  // in Smart Inbox mode where the list never produces thread rows.
  const threadMode = $derived(!!app.threadKey);
  let detail = $state(null);
  let loading = $state(false);
  let error = $state("");
  let menuAddr = $state(null); // address whose quick-menu is open
  let loadImages = $state(false); // user override to show blocked images

  $effect(() => {
    const id = app.selectedMessageId;
    detail = null;
    error = "";
    menuAddr = null;
    loadImages = false;
    if (id == null || app.threadKey) return;
    loading = true;
    // Only apply the response if this is still the selected message — a slow
    // fetch for a previous click must not overwrite the one now on screen.
    messagesApi
      .get(id)
      .then((d) => { if (app.selectedMessageId === id) detail = d; })
      .catch((e) => { if (app.selectedMessageId === id) error = e.message; })
      .finally(() => { if (app.selectedMessageId === id) loading = false; });
  });

  // Does the open message belong to a multi-message conversation (e.g. it now has
  // the reply you just sent)? Re-checked on open and after every sync, so a reply
  // surfaces without reopening the message.
  let convoCount = $state(0);
  $effect(() => {
    void app.syncTick;                 // refresh when a sync lands
    const d = detail;
    convoCount = 0;
    if (!d || !d.thread_id) return;
    const tid = d.thread_id, mid = d.id;
    messagesApi.thread(tid)
      .then((msgs) => { if (app.selectedMessageId === mid) convoCount = (msgs || []).length; })
      .catch(() => {});
  });
  function viewConversation() { if (detail?.thread_id) app.threadKey = detail.thread_id; }

  function fmtDate(iso) {
    return iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
  }

  // AI actions only appear once a key is configured (and not explicitly disabled).
  const aiOn = $derived(!!(app.settings.aiApiKey || "").trim() && app.settings.aiButtons !== false);
  // AI "Catch me up" summary.
  let summary = $state("");
  let summarizing = $state(false);
  // AI smart reply.
  let aiDraft = $state(null);    // { draft, chips }
  let drafting = $state(false);
  $effect(() => { void app.selectedMessageId; summary = ""; aiDraft = null; });
  async function catchMeUp() {
    if (!detail) return;
    summarizing = true; summary = "";
    try {
      const r = await ai.summarize({ message_id: detail.id, thread_id: detail.thread_id || "" });
      summary = r.summary || "(no summary returned)";
    } catch (e) {
      notify(e.message, "error");
    } finally { summarizing = false; }
  }
  async function smartReply() {
    if (!detail) return;
    drafting = true; aiDraft = null;
    try {
      aiDraft = await ai.draft({ message_id: detail.id, thread_id: detail.thread_id || "" });
    } catch (e) {
      notify(e.message, "error");
    } finally { drafting = false; }
  }
  function useDraft(text) {
    if (!detail) return;
    const html = `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>` + quotedOriginal();
    openCompose({ to: detail.from_addr, subject: reSubject(),
                  in_reply_to: detail.message_id || "", account_id: detail.account_id, html });
    aiDraft = null;
  }

  let showTrackers = $state(false);
  let showOriginal = $state(false); // view the email with its own original styling
  let showAllTo = $state(false);    // expand a long recipient list
  let showQuoted = $state(false);   // reveal collapsed quoted reply history
  $effect(() => { void app.selectedMessageId; showOriginal = false; showAllTo = false; showQuoted = false; });
  const shownTo = $derived(detail ? (showAllTo ? detail.to_addrs : (detail.to_addrs || []).slice(0, 3)) : []);
  const processed = $derived(
    detail ? sanitizeTrackers(detail.html || "", app.settings.blockTrackers && !loadImages)
           : { html: "", blocked: 0, urls: [] }
  );
  // Show the new message + the most-recent quoted reply by default; older history
  // (quoteSplit.earlier) stays behind a "Show earlier messages" toggle.
  const quoteSplit = $derived(detail ? splitQuoted(processed.html || "") : { main: "", recent: "", earlier: "" });
  const hasQuote = $derived(!!(quoteSplit.recent || quoteSplit.earlier));
  const hasEarlier = $derived(!!quoteSplit.earlier);
  const collapseOn = $derived(app.settings.collapseQuotes !== false);
  const bodyHtml = $derived.by(() => {
    const fallback = processed.html || `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit">${autoLink(detail?.text || "")}</pre>`;
    if (!detail) return "";
    if (!hasQuote || !collapseOn || showQuoted) return fallback; // full message, exact original nesting
    return quoteSplit.main + quoteSplit.recent;                  // new text + most-recent reply only
  });
  // Rich link unfurl (opt-in): preview the first content link in the body.
  let unfurlData = $state(null);
  const _UF_SKIP = /(google|gstatic|googleapis|doubleclick|fonts\.|w3\.org|schema\.org|list-manage|mailchimp|sendgrid|sparkpost|facebook|fbcdn|twitter|x\.com|linkedin|youtube|cdn|unsubscribe|\/track|\/click|\/wf\/|beacon|pixel|\.(?:png|jpg|jpeg|gif|svg|css|js)(?:\?|$))/i;
  function firstContentLink(html) {
    const re = /href=["'](https?:\/\/[^"'\s>]+)["']/gi;
    let m;
    while ((m = re.exec(html || ""))) { if (!_UF_SKIP.test(m[1])) return m[1]; }
    return "";
  }
  $effect(() => {
    const id = app.selectedMessageId;
    unfurlData = null;
    if (!detail || app.settings.linkUnfurls !== true || !detail.html) return;
    const link = firstContentLink(processed.html || detail.html);
    if (!link) return;
    unfurl(link).then((d) => { if (app.selectedMessageId === id && d && (d.title || d.image)) unfurlData = d; }).catch(() => {});
  });

  const srcdoc = $derived(
    detail ? emailDoc(bodyHtml, { raw: showOriginal }) : ""
  );

  // Links inside the sandboxed email iframe don't navigate on their own in the
  // desktop shell — intercept clicks and open them in the real browser (mailto
  // opens a compose). Re-wired on every iframe load (each message reload).
  let frame;
  function wireFrameLinks() {
    let doc;
    try { doc = frame?.contentDocument; } catch { doc = null; }
    if (!doc) return;
    doc.addEventListener("click", (e) => {
      const a = e.target?.closest?.("a[href]");
      if (!a) return;
      const href = (a.getAttribute("href") || "").trim();
      if (/^https?:\/\//i.test(href)) { e.preventDefault(); openExternal(href); }
      else if (href.toLowerCase().startsWith("mailto:")) {
        e.preventDefault();
        openCompose({ to: href.slice(7).split("?")[0], subject: "", html: "", account_id: detail?.account_id });
      }
    }, true);
    // Keep Ctrl/Cmd+N working even when focus is inside the email iframe.
    doc.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key === "n" || e.key === "N")) {
        e.preventDefault();
        openCompose({ to: "", subject: "", html: "" });
      }
    }, true);
  }
  const emailMode = $derived(
    app.settings.emailTheme ||
    (app.settings.alwaysOriginalHtml ? "original" : (app.settings.emailAdaptColors === false ? "original" : "adaptive"))
  );
  // Reply/Forward/Done bar position: top (in the header) or bottom (sticky footer).
  const actionsBottom = $derived(app.settings.readerActionsPos === "bottom");

  const myAddr = $derived(app.accounts.find((a) => a.id === detail?.account_id)?.email || "");
  // All of my identities for this account (primary + aliases), so Reply-All
  // never Cc's me when the mail was addressed to one of my aliases.
  function myIdentities() {
    const acct = app.accounts.find((a) => a.id === detail?.account_id);
    if (!acct) return [];
    const ids = [acct.email, ...(acct.aliases || [])];
    return ids.map((x) => (x || "").toLowerCase().trim()).filter(Boolean);
  }

  // Everyone on the thread except me (any identity) and the original sender.
  function replyAllCc() {
    if (!detail) return [];
    const all = [...(detail.to_addrs || []), ...(detail.cc_addrs || [])];
    const seen = new Set([...myIdentities(), (detail.from_addr || "").toLowerCase()]);
    const out = [];
    for (const a of all) {
      // to_addrs/cc_addrs entries may be "Name <addr>" — compare on the address.
      const k = (a || "").toLowerCase();
      const addr = (k.match(/<([^>]+)>/)?.[1] || k).trim();
      if (addr && !seen.has(addr)) { seen.add(addr); out.push(a); }
    }
    return out;
  }
  const reSubject = () => (/^re:/i.test(detail.subject || "") ? detail.subject : `Re: ${detail.subject || t("reader.noSubject")}`);

  // Wrap quote content in a Spark-style collapsible block. The composer inserts
  // your signature *above* this block and (for replies) shows it collapsed behind
  // a "···" pill, so you type on top with the thread tucked out of the way.
  // The toggle is contenteditable=false so it survives inside the editor.
  function collapsibleQuote(inner, { collapsed = true } = {}) {
    return `<div class="rapl-quoted-block${collapsed ? " collapsed" : ""}">` +
      `<div class="rapl-quote-toggle" contenteditable="false" role="button" title="Show/hide quoted text">•••</div>` +
      `<div class="rapl-quoted-content">${inner}</div></div>`;
  }

  // Build the quoted original ("On <date>, <name> wrote:") so replies carry the
  // thread context the recipient expects. Collapsed by default (Spark-style).
  function quotedOriginal() {
    const orig = detail.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail.text || "")}</pre>`;
    const who = detail.from_name ? `${detail.from_name} <${detail.from_addr || ""}>` : (detail.from_addr || "");
    const inner = `<div class="rapl-quote" style="color:#888">` +
      `On ${escapeHtml(fmtDate(detail.date))}, ${escapeHtml(who)} wrote:</div>` +
      `<blockquote style="margin:0 0 0 8px;padding-left:10px;border-left:2px solid #888;color:#888">${orig}</blockquote>`;
    return collapsibleQuote(inner, { collapsed: true });
  }

  function reply() {
    if (!detail) return;
    openCompose({ to: detail.from_addr, subject: reSubject(), in_reply_to: detail.message_id || "",
                  account_id: detail.account_id, html: quotedOriginal() });
  }
  function replyAll() {
    if (!detail) return;
    openCompose({ to: detail.from_addr, cc: replyAllCc().join(", "), subject: reSubject(),
                  in_reply_to: detail.message_id || "", account_id: detail.account_id, html: quotedOriginal() });
  }
  async function forward() {
    if (!detail) return;
    const subj = /^fwd:/i.test(detail.subject || "") ? detail.subject : `Fwd: ${detail.subject || t("reader.noSubject")}`;
    // Safe Forward (on by default): strip hidden 1×1 tracking pixels from the body
    // so forwarding doesn't re-arm the sender's trackers for the new recipient.
    let src = detail.html || "";
    if (src && app.settings.sanitizeForward !== false) src = sanitizeTrackers(src, true).html;
    const orig = src || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail.text || "")}</pre>`;
    const quote = collapsibleQuote(
      `<div style="color:#888">---------- Forwarded message ----------<br>` +
      `From: ${escapeHtml(detail.from_name || "")} &lt;${escapeHtml(detail.from_addr || "")}&gt;<br>` +
      `Date: ${escapeHtml(fmtDate(detail.date))}<br>` +
      `Subject: ${escapeHtml(detail.subject || "")}<br>` +
      `To: ${escapeHtml((detail.to_addrs || []).join(", "))}</div><br>${orig}`,
      { collapsed: false });
    // Carry the original (non-inline) attachments — a forward without them is
    // surprising. Inline images already live in the quoted HTML.
    const atts = (detail.attachments || []).filter((a) => !a.inline);
    let attachments = [];
    if (atts.length) {
      try { attachments = await Promise.all(atts.map((a) => fetchAttachmentForCompose(detail.id, a))); }
      catch { notify(t("reader.couldntAttachForwarded"), "error"); }
    }
    openCompose({ subject: subj, html: quote, account_id: detail.account_id, attachments });
  }
  function toggleFlag() {
    if (!detail) return;
    messagesApi.setFlag(detail.id, !detail.is_flagged).then(() => (detail.is_flagged = !detail.is_flagged)).catch(() => {});
  }
  // Safe Export: download this message as a sanitized .eml (internal routing
  // headers + hidden tracking pixels stripped by the backend).
  async function exportEml() {
    if (!detail) return;
    const name = ((detail.subject || "message").replace(/[^\w.-]+/g, "_").slice(0, 60) || "message") + ".eml";
    try {
      const path = await saveEml(detail.id, true, name);
      if (path) { notify(t("reader.savedTo", { path })); revealPath(path); }
      else notify(t("reader.downloaded"));
    } catch (e) { notify(e.message || t("reader.couldntSaveAttachment"), "error"); }
  }

  // The action buttons under the recipient line are user-configurable.
  function actionDef(key) {
    switch (key) {
      case "reply": return { icon: icons.reply, label: t("reader.reply"), run: reply };
      case "replyAll": return { icon: icons.replyAll, label: t("reader.replyAll"), run: replyAll, hide: replyAllCc().length === 0 };
      case "forward": return { icon: icons.forward, label: t("reader.forward"), run: forward };
      case "done": return { icon: detail.is_done ? icons.restore : icons.done, label: detail.is_done ? t("reader.restore") : t("reader.done"), run: () => markDone(detail, !detail.is_done) };
      case "flag": return { icon: detail.is_flagged ? icons.flagged : icons.flag, label: detail.is_flagged ? t("reader.flagged") : t("reader.flag"), run: toggleFlag, cls: detail.is_flagged ? "on" : "" };
      default: return null;
    }
  }
  const readerBtns = $derived(
    (app.settings.readerActions || ["reply", "replyAll", "forward", "done", "flag"])
      .map(actionDef).filter((b) => b && !b.hide)
  );

  const attachments = $derived((detail?.attachments || []).filter((a) => !a.inline));
  function humanSize(n) {
    if (!n) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  }
  let downloading = $state(null);
  // Click an attachment → open it with the OS default app.
  async function openAtt(att) {
    downloading = att.index;
    try { await openAttachment(detail.id, att.index, att.filename); }
    catch (e) { notify(e.message || t("reader.couldntOpenAttachment"), "error"); }
    finally { downloading = null; }
  }
  // Save one attachment to disk (Downloads).
  async function saveAtt(att) {
    downloading = att.index;
    try {
      const path = await saveAttachment(detail.id, att.index, att.filename);
      if (path) { notify(t("reader.savedTo", { path })); revealPath(path); }
      else notify(t("reader.downloaded"));
    } catch (e) { notify(e.message || t("reader.couldntSaveAttachment"), "error"); }
    finally { downloading = null; }
  }
  let savingAll = $state(false);
  async function saveAll() {
    savingAll = true;
    let last = null, ok = 0;
    try {
      for (const a of attachments) {
        try { last = await saveAttachment(detail.id, a.index, a.filename); ok++; }
        catch {}
      }
      if (last) { notify(ok === 1 ? t("reader.savedToDownloadsOne") : t("reader.savedToDownloadsN", { n: ok })); revealPath(last); }
      else if (ok) notify(ok === 1 ? t("reader.downloadedOne") : t("reader.downloadedN", { n: ok }));
      else notify(t("reader.couldntSaveAttachments"), "error");
    } finally { savingAll = false; }
  }

  function showFrom(addr) { searchAddress(addr); menuAddr = null; }
  function mailTo(addr) { openCompose({ to: addr, account_id: detail?.account_id }); menuAddr = null; }
  async function copyAddress(addr) {
    try { await navigator.clipboard.writeText(addr); notify(t("reader.addressCopied")); }
    catch { notify(t("reader.couldntCopy"), "error"); }
    menuAddr = null;
  }
  function toggleMenu(e, addr) { e.stopPropagation(); menuAddr = menuAddr === addr ? null : addr; }

  function unsubscribe() {
    const parts = [...(detail.unsubscribe || "").matchAll(/<([^>]+)>/g)].map((m) => m[1].trim());
    const http = parts.find((p) => p.startsWith("http"));
    const mailto = parts.find((p) => p.startsWith("mailto:"));
    if (http) {
      // window.open is a no-op in the desktop webview — route via the OS browser.
      openExternal(http);
    } else if (mailto) {
      const addr = mailto.slice(7).split("?")[0];
      openCompose({ to: addr, subject: "Unsubscribe", html: "Please unsubscribe me from this list.", account_id: detail.account_id });
    }
  }
</script>

<svelte:window onclick={() => (menuAddr = null)} />

<section class="reader">
  {#if threadMode}
    <ThreadView />
  {:else if app.selectedMessageId == null}
    <div class="placeholder">
      <div class="big">{@html icons.placeholderMail}</div>
      <p>{t("reader.selectMessage")}</p>
      <a class="rapl-link" href="https://rapl-group.eu/" target="_blank" rel="noreferrer">rapl-group.eu</a>
    </div>
  {:else if loading}
    <div class="placeholder">{t("reader.loading")}</div>
  {:else if error}
    <div class="placeholder err">{error}</div>
  {:else if detail}
    <header>
      <div class="subject">{detail.subject || t("reader.noSubject")}</div>
      <div class="meta">
        <span class="addr-wrap">
          <button class="addr from" onclick={(e) => toggleMenu(e, detail.from_addr)}>
            <b>{detail.from_name || detail.from_addr}</b> &lt;{detail.from_addr}&gt;
          </button>
          {#if menuAddr === detail.from_addr}
            <div class="menu" onclick={(e) => e.stopPropagation()}>
              <button onclick={() => copyAddress(detail.from_addr)}>{@html icons.copy} {t("reader.copyAddress")}</button>
              <button onclick={() => showFrom(detail.from_addr)}>{@html icons.inbox} {t("reader.showMailFromTo")}</button>
              <button onclick={() => mailTo(detail.from_addr)}>{@html icons.compose} {t("reader.newEmailTo")}</button>
              <button onclick={() => { menuAddr = null; toggleVip(detail.from_addr); }}>{@html icons.star} {isVip(detail.from_addr) ? t("reader.removeVip") : t("reader.markVip")}</button>
              <button onclick={() => { menuAddr = null; muteSender(detail); }}>{@html icons.mute} {t("reader.muteSender")}</button>
              <button onclick={() => { menuAddr = null; muteThread(detail); }}>{@html icons.mute} {t("reader.muteConversation")}</button>
              <button onclick={() => { menuAddr = null; exportEml(); }}>{@html icons.save || icons.download} {t("reader.exportEml")}</button>
            </div>
          {/if}
        </span>
        <span class="date">{fmtDate(detail.date)}</span>
      </div>
      <div class="to">
        {t("reader.toLabel")}
        {#each shownTo as addr, i}
          <span class="addr-wrap">
            <button class="addr small" onclick={(e) => toggleMenu(e, addr)}>{addr}</button>
            {#if menuAddr === addr}
              <div class="menu" onclick={(e) => e.stopPropagation()}>
                <button onclick={() => copyAddress(addr)}>{@html icons.copy} {t("reader.copyAddress")}</button>
                <button onclick={() => showFrom(addr)}>{@html icons.inbox} {t("reader.showMailFromTo")}</button>
                <button onclick={() => mailTo(addr)}>{@html icons.compose} {t("reader.newEmailTo")}</button>
              </div>
            {/if}
          </span>{i < shownTo.length - 1 ? ", " : ""}
        {/each}
        {#if detail.to_addrs.length > 3}
          <button class="more-to" onclick={() => (showAllTo = !showAllTo)}>
            {showAllTo ? t("reader.showLess") : t("reader.moreN", { n: detail.to_addrs.length - 3 })}
          </button>
        {/if}
      </div>
      {#if !actionsBottom}{@render actionsBar()}{/if}
    </header>
    {#if convoCount > 1}
      <button class="convo-bar" onclick={viewConversation}>
        {@html icons.reply}
        <span>{t("reader.viewConversation", { n: convoCount })}</span>
      </button>
    {/if}
    {#if summary}
      <div class="ai-summary">
        <div class="ai-head">{@html icons.bolt} <b>{t("reader.summary")}</b>
          <button class="ai-close" title={t("reader.dismiss")} onclick={() => (summary = "")}>{@html icons.close}</button>
        </div>
        <pre>{summary}</pre>
      </div>
    {/if}
    {#if aiDraft}
      <div class="ai-summary">
        <div class="ai-head">{@html icons.reply} <b>{t("reader.suggestedReply")}</b>
          <button class="ai-close" title={t("reader.dismiss")} onclick={() => (aiDraft = null)}>{@html icons.close}</button>
        </div>
        {#if aiDraft.chips?.length}
          <div class="ai-chips">
            {#each aiDraft.chips as c}<button class="ai-chip" onclick={() => useDraft(c)}>{c}</button>{/each}
          </div>
        {/if}
        <pre>{aiDraft.draft}</pre>
        <div class="ai-actions">
          <button class="btn primary" onclick={() => useDraft(aiDraft.draft)}>{t("reader.editAndSend")}</button>
          <span class="ai-note">{t("reader.reviewBeforeSending")}</span>
        </div>
      </div>
    {/if}
    {#if isTrustedSender(detail.from_addr)}
      <div class="auth-bar ok">{@html icons.shieldCheck} <b>{t("reader.markedSafe")}</b>
        <span class="auth-detail">{t("reader.youTrust", { addr: detail.from_addr })}</span>
        <button class="trust" title={t("reader.removeSafeMarkTitle")} onclick={() => untrustSender(detail.from_addr)}>{t("reader.undo")}</button>
      </div>
    {:else if detail.warnings?.length}
      <div class="auth-bar bad">{@html icons.shieldAlert}
        <span>{detail.warnings.join(" · ")}</span>
        <button class="trust" title={t("reader.trustSenderTitle")} onclick={() => trustSender(detail.from_addr)}>{@html icons.done} {t("reader.markSafe")}</button>
      </div>
    {/if}
    {#if detail.pgp?.type === "encrypted"}
      <div class="auth-bar {detail.pgp.decrypted || detail.text ? 'ok' : 'bad'}">{@html icons.shieldCheck}
        <b>{t("reader.pgpEncrypted")}</b>
        <span class="auth-detail">{detail.pgp.verified ? t("reader.pgpSigVerified", { signer: detail.pgp.signer }) : t("reader.pgpDecryptedLocally")}</span>
      </div>
    {:else if detail.pgp?.type === "signed"}
      <div class="auth-bar {detail.pgp.verified ? 'ok' : 'bad'}">{@html detail.pgp.verified ? icons.shieldCheck : icons.shieldAlert}
        <b>{detail.pgp.verified ? t("reader.pgpSignatureVerified") : t("reader.pgpSignatureUnverified")}</b>
        <span class="auth-detail">{detail.pgp.verified ? detail.pgp.signer : t("reader.importPublicKey")}</span>
      </div>
    {/if}
    {#if detail.smime?.type === "encrypted"}
      <div class="auth-bar {detail.smime.decrypted ? 'ok' : 'bad'}">{@html icons.shieldCheck || icons.shield}
        <b>{t("reader.smimeEncrypted")}</b>
        <span class="auth-detail">{detail.smime.decrypted ? t("reader.smimeDecryptedLocally") : t("reader.smimeNoKey")}</span>
      </div>
    {:else if detail.smime?.type === "signed"}
      <div class="auth-bar {detail.smime.verified ? 'ok' : 'bad'}">{@html detail.smime.verified ? icons.shieldCheck : icons.shieldAlert}
        <b>{t("reader.smimeSigned")}</b>
        <span class="auth-detail">{detail.smime.signer || t("reader.smimeUnknownSigner")}</span>
      </div>
    {/if}
    {#if detail.auth?.status === "fail"}
      <div class="auth-bar bad">{@html icons.shieldAlert} <b>{t("reader.failedAuth")}</b> <span class="auth-detail">{detail.auth.detail}</span></div>
    {:else if detail.auth?.status === "pass" && !isTrustedSender(detail.from_addr)}
      <div class="auth-bar ok">{@html icons.shieldCheck} {t("reader.senderAuthenticated")} <span class="auth-detail">{detail.auth.detail}</span></div>
    {/if}
    {#if app.selectedKind === "screener" || detail.first_time_sender}
      <div class="screener-bar">
        {@html icons.screener} {t("reader.firstTimeSender", { addr: detail.from_addr })}
        <button class="ok" onclick={() => approveSender(detail)}>{@html icons.done} {t("reader.approve")}</button>
        <button class="no" onclick={() => blockSender(detail)}>{@html icons.close} {t("reader.block")}</button>
      </div>
    {/if}
    {#if detail.unsubscribe}
      <div class="unsub-bar">
        {@html icons.mail} {t("reader.mailingList")}
        <button onclick={unsubscribe}>{t("reader.unsubscribe")}</button>
      </div>
    {/if}
    {#if processed.blocked > 0 && !loadImages}
      <div class="tracker-wrap">
        <div class="tracker-bar">
          {@html icons.shield} {processed.blocked === 1 ? t("reader.blockedTrackerOne") : t("reader.blockedTrackerN", { n: processed.blocked })}
          <button class="tlink" onclick={() => (showTrackers = !showTrackers)}>{showTrackers ? t("reader.hide") : t("reader.details")}</button>
          <button class="tlink" onclick={() => (loadImages = true)}>{t("reader.loadEverything")}</button>
        </div>
        {#if showTrackers}
          <ul class="tracker-list">
            {#each processed.urls as u}<li title={u}>{u}</li>{/each}
          </ul>
        {/if}
      </div>
    {/if}
    {#if attachments.length}
      <div class="attachments">
        <span class="att-label">{@html icons.attachment} {attachments.length === 1 ? t("reader.attachmentOne") : t("reader.attachmentN", { n: attachments.length })}</span>
        {#each attachments as a}
          <span class="att" class:busy={downloading === a.index}>
            <button class="att-open" title={t("reader.openFile", { name: a.filename })} onclick={() => openAtt(a)}>
              <span class="att-name">{a.filename}</span>
              {#if a.size}<span class="att-size">{humanSize(a.size)}</span>{/if}
              {#if downloading === a.index}<span class="att-dl">…</span>{/if}
            </button>
            <button class="att-save" title={t("reader.saveToDownloads")} onclick={() => saveAtt(a)}>{@html icons.sent || "↓"}</button>
          </span>
        {/each}
        {#if attachments.length > 1}
          <button class="att-all" onclick={saveAll} disabled={savingAll} title={t("reader.saveAllTitle")}>
            {savingAll ? t("reader.saving") : t("reader.downloadAll")}
          </button>
        {/if}
      </div>
    {/if}
    {#if detail.html}
      <div class="viewbar">
        {#if hasEarlier && collapseOn}
          <button class="vtoggle" class:on={showQuoted} title={t("reader.showHideEarlierTitle")}
            onclick={() => (showQuoted = !showQuoted)}>
            ••• {showQuoted ? t("reader.hideEarlier") : t("reader.showEarlier")}
          </button>
        {/if}
        <button class="vtoggle" class:on={showOriginal} title={t("reader.stylingToggleTitle")}
          onclick={() => (showOriginal = !showOriginal)}>
          {@html icons.palette} {showOriginal ? t("reader.originalStyling") : (emailMode === "original" ? t("reader.originalStyling") : emailMode === "dark" ? t("reader.dark") : t("reader.adaptedToTheme"))}
        </button>
      </div>
    {/if}
    {#if unfurlData}
      <a class="unfurl" href={unfurlData.url} target="_blank" rel="noreferrer">
        {#if unfurlData.image}<img src={unfurlData.image} alt="" />{/if}
        <span class="uf-text">
          {#if unfurlData.site}<span class="uf-site">{unfurlData.site}</span>{/if}
          <span class="uf-title">{unfurlData.title || unfurlData.url}</span>
          {#if unfurlData.description}<span class="uf-desc">{unfurlData.description}</span>{/if}
        </span>
      </a>
    {/if}
    <iframe title={t("reader.messageFrameTitle")} bind:this={frame} onload={wireFrameLinks}
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" srcdoc={srcdoc}></iframe>
    {#if actionsBottom}{@render actionsBar()}{/if}
  {/if}
</section>

{#snippet actionsBar()}
  <div class="actions" class:bottom={actionsBottom}>
    {#each readerBtns as b}
      <button class="btn {b.cls || ''}" onclick={b.run}>{@html b.icon} {b.label}</button>
    {/each}
    {#if aiOn}
      <button class="btn ai" onclick={catchMeUp} disabled={summarizing} title={t("reader.catchMeUpTitle")}>
        {@html icons.bolt} {summarizing ? t("reader.summarizing") : t("reader.catchMeUp")}
      </button>
      <button class="btn ai" onclick={smartReply} disabled={drafting} title={t("reader.aiReplyTitle")}>
        {@html icons.reply} {drafting ? t("reader.drafting") : t("reader.aiReply")}
      </button>
    {/if}
  </div>
{/snippet}

<style>
  .reader { display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  .placeholder { flex: 1; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; color: var(--muted); animation: rise-in var(--t-slow) var(--ease); }
  .placeholder .big { display: grid; place-items: center; width: 72px; height: 72px; border-radius: 22px;
    background: var(--surface-2); color: var(--muted); font-size: 32px;
    box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text) 5%, transparent); }
  .placeholder .big :global(svg) { width: 34px; height: 34px; }
  .placeholder.err { color: var(--danger); }
  .placeholder .rapl-link { margin-top: 2px; font-size: 12px; color: var(--accent); text-decoration: none; opacity: 0.8; }
  .placeholder .rapl-link:hover { opacity: 1; text-decoration: underline; }
  header { padding: 18px 22px 14px; border-bottom: 1px solid var(--hairline); display: flex; flex-direction: column; gap: 6px; }
  .subject { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.3; }
  .meta { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; align-items: flex-start; }
  .to { color: var(--faint); font-size: 12px; }
  .more-to { color: var(--accent); font-size: 12px; font-weight: 600; padding: 1px 5px; border-radius: 5px; }
  .more-to:hover { background: var(--surface-2); }
  .addr-wrap { position: relative; display: inline-block; }
  .addr { color: inherit; text-align: left; border-radius: 5px; padding: 1px 4px; cursor: pointer; }
  .addr:hover { background: var(--surface-2); color: var(--accent); }
  .addr.small { color: var(--faint); }
  .menu {
    position: absolute; top: 100%; left: 0; z-index: 20; margin-top: 4px; min-width: 240px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column;
    animation: pop-in var(--t) var(--ease); transform-origin: top left;
  }
  .menu button { text-align: left; padding: 8px 10px; border-radius: 6px; color: var(--text); font-size: 13px; }
  .menu button:hover { background: var(--accent); color: #fff; }
  .actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  /* Bottom mode: a sticky, right-aligned action bar pinned to the foot of the reader. */
  /* Solid background — backdrop blur on a sticky bar repaints every scroll frame. */
  .actions.bottom { margin-top: 0; position: sticky; bottom: 0; z-index: 5; justify-content: flex-end;
    padding: 10px 18px; background: var(--bg);
    border-top: 1px solid var(--hairline); }
  .btn.ai { color: var(--accent); }
  .ai-summary { margin: 0 22px 4px; padding: 12px 14px; background: color-mix(in srgb, var(--accent) 8%, var(--surface)); border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border)); border-radius: var(--radius); }
  .ai-head { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--accent); margin-bottom: 6px; }
  .ai-close { margin-left: auto; color: var(--muted); display: inline-flex; }
  .ai-close:hover { color: var(--text); }
  .ai-summary pre { white-space: pre-wrap; font: 13px/1.55 system-ui, sans-serif; color: var(--text); margin: 0; }
  .ai-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .ai-chip { padding: 4px 12px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); font-size: 12px; color: var(--text); }
  .ai-chip:hover { border-color: var(--accent); color: var(--accent); }
  .ai-actions { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
  .ai-note { font-size: 11px; color: var(--muted); }
  .actions .btn.on { color: var(--warning); border-color: var(--warning); }
  .unsub-bar { display: flex; align-items: center; gap: 10px; padding: 8px 22px; background: var(--surface); border-bottom: 1px solid var(--border); color: var(--muted); font-size: 12px; }
  .unsub-bar button { margin-left: auto; color: var(--accent); font-weight: 600; }
  .auth-bar { display: flex; align-items: center; gap: 8px; padding: 8px 22px; font-size: 13px; border-bottom: 1px solid var(--hairline); }
  .auth-bar.bad { background: var(--danger-soft); color: var(--danger); }
  .auth-bar.ok { background: var(--done-soft); color: var(--done); }
  .auth-bar .auth-detail { color: var(--muted); font-size: 12px; margin-left: auto; }
  .auth-bar .trust { margin-left: auto; flex: none; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid currentColor; color: inherit; }
  .auth-bar .trust:hover { background: var(--surface-2); }
  .convo-bar { display: flex; align-items: center; gap: 8px; width: 100%; padding: 9px 22px; font-size: 13px; font-weight: 600; text-align: left; color: var(--accent, #4f8cff); background: var(--accent-soft); border: none; border-bottom: 1px solid var(--hairline); cursor: pointer; }
  .convo-bar:hover { filter: brightness(1.06); }
  .screener-bar { display: flex; align-items: center; gap: 10px; padding: 10px 22px; background: var(--accent-soft); border-bottom: 1px solid var(--hairline); font-size: 13px; }
  .screener-bar .ok { margin-left: auto; color: var(--done); font-weight: 600; }
  .screener-bar .no { color: var(--danger); font-weight: 600; }
  .attachments { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .att-label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); margin-right: 4px; }
  .att { display: inline-flex; align-items: stretch; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); max-width: 300px; overflow: hidden; }
  .att:hover { border-color: var(--accent); }
  .att.busy { opacity: 0.6; }
  .att-open { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; min-width: 0; }
  .att-save { display: inline-flex; align-items: center; padding: 0 9px; border-left: 1px solid var(--border); color: var(--muted); }
  .att-save:hover { background: var(--surface-3); color: var(--accent); }
  .att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .att-size { font-size: 11px; color: var(--faint); flex: none; }
  .att-dl { color: var(--accent); }
  .att-all { font-size: 12px; padding: 6px 12px; border-radius: var(--radius-sm); border: 1px solid var(--accent); color: var(--accent); background: transparent; }
  .att-all:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); }
  .unfurl { display: flex; gap: 12px; margin: 10px 16px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); text-decoration: none; color: inherit; max-height: 110px; overflow: hidden; }
  .unfurl:hover { border-color: var(--accent); }
  .unfurl img { width: 96px; height: 88px; object-fit: cover; border-radius: var(--radius-sm); flex: none; }
  .unfurl .uf-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .unfurl .uf-site { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .unfurl .uf-title { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .unfurl .uf-desc { font-size: 12px; color: var(--muted); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .viewbar { display: flex; justify-content: flex-end; gap: 8px; padding: 5px 16px; background: var(--bg); border-bottom: 1px solid var(--border); }
  .vtoggle { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); padding: 3px 9px; border-radius: 999px; border: 1px solid var(--border); }
  .vtoggle:hover { color: var(--text); border-color: var(--accent); }
  .vtoggle.on { color: var(--accent); border-color: var(--accent); background: var(--surface-2); }
  .tracker-wrap { border-bottom: 1px solid var(--border); background: var(--surface); }
  .tracker-bar { display: flex; align-items: center; gap: 12px; padding: 8px 22px; color: var(--muted); font-size: 12px; }
  .tracker-bar .tlink { color: var(--accent); font-weight: 600; }
  .tracker-bar .tlink:first-of-type { margin-left: auto; }
  .tracker-list { margin: 0; padding: 0 22px 10px 40px; max-height: 120px; overflow-y: auto; }
  .tracker-list li { color: var(--faint); font-size: 11px; font-family: ui-monospace, monospace; word-break: break-all; line-height: 1.6; }
  iframe { flex: 1; border: none; width: 100%; background: var(--bg); }
</style>
