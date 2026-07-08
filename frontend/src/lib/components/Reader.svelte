<script>
  import { app, markDone, openCompose, searchAddress, approveSender, blockSender, muteSender, muteThread, notify, isVip, toggleVip, trustSender, untrustSender, isTrustedSender, archiveMessage, deleteMessage, snoozeMessage, snoozePresets, presetWhen, createRuleFromSender, threadPrefetch, aiEnabled, sendToLab, sandboxAttachment, deepScanAttachment, markUnsubscribed } from "../store.svelte.js";
  import { untrack } from "svelte";
  import { messages as messagesApi, openAttachment, saveAttachment, saveAttachmentAs, saveEml, revealPath, openExternal, unfurl, ai, fetchAttachmentForCompose, fetchAttachment, subscriptions } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc, splitQuoted, autoLink } from "../email.js";
  import { fileExt, fileKind, isImageName } from "../attachments.js";
  import { t } from "../i18n.svelte.js";
  import { fade } from "svelte/transition";
  import ThreadView from "./ThreadView.svelte";
  import SuspiciousModal from "./SuspiciousModal.svelte";
  import AttachmentMenu from "./AttachmentMenu.svelte";

  // A conversation opened explicitly (threadKey set) always shows as a thread,
  // independent of the list-grouping setting - so "View conversation" works even
  // in Smart Inbox mode where the list never produces thread rows.
  const threadMode = $derived(!!app.threadKey);
  let detail = $state(null);
  let loading = $state(false);
  let error = $state("");
  let menuAddr = $state(null); // address whose quick-menu is open
  let loadImages = $state(false); // user override to show blocked images
  let ctxMenu = $state(null);  // reader right-click menu { x, y }

  $effect(() => {
    const id = app.selectedMessageId;
    detail = null;
    error = "";
    menuAddr = null;
    loadImages = false;
    if (id == null || app.threadKey) return;
    loading = true;
    // Only apply the response if this is still the selected message - a slow
    // fetch for a previous click must not overwrite the one now on screen.
    messagesApi
      .get(id)
      .then((d) => { if (app.selectedMessageId === id) detail = d; })
      .catch((e) => { if (app.selectedMessageId === id) error = e.message; })
      .finally(() => { if (app.selectedMessageId === id) loading = false; });
  });

  // Conversations open AS conversations - when the open message turns out to
  // have thread siblings (they may live in other folders/pages, so the list
  // couldn't know), promote the pane to the thread view automatically. The
  // fetched thread is handed to ThreadView so it doesn't re-fetch.
  // Gated on the "Conversation threading" setting: with it off, a mail always
  // stays a single message (this effect was the other half of the "threading
  // off but I still see threads" bug).
  $effect(() => {
    void app.syncTick;                 // re-check when a sync lands (your reply arrived)
    const d = detail;
    if (!app.settings.threading || !d || !d.thread_id || app.threadKey) return;
    const tid = d.thread_id, mid = d.id;
    messagesApi.thread(tid)
      .then((msgs) => {
        if (app.selectedMessageId !== mid || app.threadKey) return;
        if ((msgs || []).length > 1) {
          threadPrefetch.key = tid;
          threadPrefetch.msgs = msgs;
          app.threadKey = tid;
        }
      })
      .catch(() => {});
  });

  // Keyboard-routed actions (r = reply, f = forward) for the single-message
  // view; ThreadView handles them when a conversation is showing.
  let _cmdSeen = 0;
  $effect(() => {
    const rc = app.readerCmd;
    if (!rc || rc.n === _cmdSeen) return;
    _cmdSeen = rc.n;
    if (threadMode || !detail) return;
    if (rc.cmd === "reply") reply();
    else if (rc.cmd === "forward") forward();
  });

  function fmtDate(iso) {
    return iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
  }

  // AI actions only appear once a key is configured (and not explicitly disabled).
  const aiOn = $derived(aiEnabled());
  // AI "Catch me up" summary.
  let summary = $state("");
  let summarizing = $state(false);
  // AI smart reply.
  let aiDraft = $state(null);    // { draft, chips }
  let drafting = $state(false);
  // AI phishing screening (Settings → Security: off | manual | auto).
  const aiScreenMode = $derived(app.settings.aiScreen || "off");
  let aiVerdict = $state(null);  // { verdict: safe|suspicious|dangerous, reason }
  let aiScreening = $state(false);
  let usedAI = false;   // did we run a local-model call on this message? → free GPU on leave
  // On navigating to a different message/thread: reset the AI panels, and if we
  // used a local (Ollama) model here, unload it so the GPU frees when you move on.
  $effect(() => {
    void app.selectedMessageId; void app.threadKey;
    if (usedAI && (app.settings.aiProvider || "") === "ollama") ai.ollamaUnload().catch(() => {});
    usedAI = false;
    summary = ""; aiDraft = null; aiVerdict = null; aiScreening = false;
  });

  // Seed the AI verdict from the cached value the detail carries, and - in
  // "automatic" mode - screen a mail the first time it's opened (the backend
  // caches the result, so re-opens don't re-spend tokens).
  $effect(() => {
    const d = detail;
    if (!d) return;
    if (d.ai_verdict) { aiVerdict = { verdict: d.ai_verdict, reason: d.ai_reason || "" }; return; }
    if (aiOn && aiScreenMode === "auto" && !aiScreening) screenNow(false);
  });
  async function screenNow(force) {
    if (!detail) return;
    aiScreening = true; usedAI = true; app.aiBusy = true;
    try {
      const r = await ai.screen(detail.id, !!force);
      aiVerdict = { verdict: r.verdict, reason: r.reason || "" };
      if (detail) { detail.ai_verdict = r.verdict; detail.ai_reason = r.reason || ""; }
    } catch (e) { notify(e.message, "error"); }
    finally { aiScreening = false; app.aiBusy = false; }
  }
  const aiVerdictPill = $derived.by(() => {
    if (!aiVerdict) return null;
    const v = aiVerdict.verdict;
    if (v === "dangerous") return { kind: "bad", icon: icons.shieldAlert, label: t("reader.aiDangerous") };
    if (v === "suspicious") return { kind: "warn", icon: icons.shieldAlert, label: t("reader.aiSuspicious") };
    return { kind: "ok", icon: icons.shieldCheck, label: t("reader.aiSafe") };
  });

  async function catchMeUp() {
    if (!detail) return;
    summarizing = true; summary = ""; usedAI = true; app.aiBusy = true;
    try {
      const r = await ai.summarize({ message_id: detail.id, thread_id: detail.thread_id || "" });
      summary = r.summary || "(no summary returned)";
    } catch (e) {
      notify(e.message, "error");
    } finally { summarizing = false; app.aiBusy = false; }
  }
  async function smartReply() {
    if (!detail) return;
    drafting = true; aiDraft = null; usedAI = true; app.aiBusy = true;
    try {
      aiDraft = await ai.draft({ message_id: detail.id, thread_id: detail.thread_id || "" });
    } catch (e) {
      notify(e.message, "error");
    } finally { drafting = false; app.aiBusy = false; }
  }
  function useDraft(text) {
    if (!detail) return;
    const html = `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>` + quotedOriginal();
    openCompose({ to: detail.from_addr, subject: reSubject(),
                  in_reply_to: detail.message_id || "", account_id: detail.account_id, html });
    aiDraft = null;
  }

  let showOriginal = $state(false); // view the email with its own original styling
  let showAllTo = $state(false);    // expand a long recipient list
  let showQuoted = $state(false);   // reveal collapsed quoted reply history
  let secOpen = $state(null);       // which security pill is expanded (key) - one at a time
  $effect(() => { void app.selectedMessageId; showOriginal = false; showAllTo = false; showQuoted = false; secOpen = null; frameH = 360; ctxMenu = null; });

  // Trust / auth / encryption status as COMPACT PILLS instead of stacked
  // full-width bars - an S/MIME-signed + authenticated mail used to eat 2-3
  // lines of header. Each pill carries its detail (hover) + optional action,
  // revealed inline when clicked.
  const secPills = $derived.by(() => {
    if (!detail) return [];
    const out = [];
    const trusted = isTrustedSender(detail.from_addr);
    if (trusted) {
      out.push({ key: "trust", kind: "ok", icon: icons.shieldCheck, label: t("reader.markedSafe"),
        detail: t("reader.youTrust", { addr: detail.from_addr }),
        act: { label: t("reader.undo"), title: t("reader.removeSafeMarkTitle"), run: () => untrustSender(detail.from_addr) } });
    } else if (detail.warnings?.length) {
      out.push({ key: "warn", kind: "bad", icon: icons.shieldAlert, label: t("reader.securityWarning"),
        detail: detail.warnings.join(" · "),
        act: { label: t("reader.markSafe"), icon: icons.done, title: t("reader.trustSenderTitle"), run: () => trustSender(detail.from_addr) } });
    }
    if (detail.pgp?.type === "encrypted") {
      out.push({ key: "pgp", kind: (detail.pgp.decrypted || detail.text) ? "ok" : "bad", icon: icons.lock, label: t("reader.pgpEncrypted"),
        detail: detail.pgp.verified ? t("reader.pgpSigVerified", { signer: detail.pgp.signer }) : t("reader.pgpDecryptedLocally") });
    } else if (detail.pgp?.type === "signed") {
      out.push({ key: "pgp", kind: detail.pgp.verified ? "ok" : "bad", icon: detail.pgp.verified ? icons.shieldCheck : icons.shieldAlert,
        label: detail.pgp.verified ? t("reader.pgpSignatureVerified") : t("reader.pgpSignatureUnverified"),
        detail: detail.pgp.verified ? detail.pgp.signer : t("reader.importPublicKey") });
    }
    if (detail.smime?.type === "encrypted") {
      out.push({ key: "smime", kind: detail.smime.decrypted ? "ok" : "bad", icon: icons.lock, label: t("reader.smimeEncrypted"),
        detail: detail.smime.decrypted ? t("reader.smimeDecryptedLocally") : t("reader.smimeNoKey") });
    } else if (detail.smime?.type === "signed") {
      out.push({ key: "smime", kind: detail.smime.verified ? "ok" : "bad", icon: detail.smime.verified ? icons.shieldCheck : icons.shieldAlert,
        label: t("reader.smimeSigned"), detail: detail.smime.signer || t("reader.smimeUnknownSigner") });
    }
    if (detail.auth?.status === "fail") {
      out.push({ key: "auth", kind: "bad", icon: icons.shieldAlert, label: t("reader.failedAuthShort"), detail: detail.auth.detail || t("reader.failedAuth") });
    } else if (detail.auth?.status === "pass" && !trusted) {
      out.push({ key: "auth", kind: "ok", icon: icons.shieldCheck, label: t("reader.senderAuthenticated"), detail: detail.auth.detail || "" });
    }
    return out;
  });
  const secOpenPill = $derived(secPills.find((p) => p.key === secOpen) || null);
  // Inbox mail from an unknown sender → an inline "accept the sender?" prompt,
  // now folded into the same badge strip as the security pills.
  const screenerActive = $derived(!!detail && (app.selectedKind === "screener" || detail.first_time_sender));
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
  // desktop shell - intercept clicks and open them in the real browser (mailto
  // opens a compose). Re-wired on every iframe load (each message reload).
  let frame;
  // The reader scrolls as ONE document (header included) instead of pinning the
  // header and scrolling only the body - so the iframe sizes itself to its
  // content. Measured on load and on any later reflow (images finishing, theme
  // re-adapt, quote toggles). Reset small on nav so a tall old mail doesn't leave
  // a blank gap before the next one measures.
  let frameH = $state(360);
  let _ro = null;
  function measureFrame() {
    try {
      const doc = frame?.contentDocument;
      if (!doc) return;
      const h = Math.max(doc.documentElement?.scrollHeight || 0, doc.body?.scrollHeight || 0);
      if (h > 0) frameH = h + 6;
    } catch {}
  }
  function wireFrameLinks() {
    let doc;
    try { doc = frame?.contentDocument; } catch { doc = null; }
    if (!doc) return;
    // Size to content now, and keep tracking: images/fonts land after load, and
    // the window can resize (reflowing the body to a new width).
    measureFrame();
    setTimeout(measureFrame, 60);
    setTimeout(measureFrame, 300);
    try {
      _ro?.disconnect();
      _ro = new ResizeObserver(() => measureFrame());
      if (doc.documentElement) _ro.observe(doc.documentElement);
    } catch {}
    // Right-click inside the sandboxed email → our reader menu. The event's
    // coords are relative to the iframe, so offset by the frame's position.
    doc.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const rect = frame?.getBoundingClientRect();
      ctxMenu = { x: (rect?.left || 0) + e.clientX, y: (rect?.top || 0) + e.clientY };
    }, true);
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
    // The email iframe grabs focus on load, so app keyboard shortcuts (Ctrl+K
    // command palette, Ctrl+N compose) "die" while reading - the keydowns land in
    // the iframe document, not the app window. Handle the important ones here.
    doc.addEventListener("keydown", (e) => {
      const cmd = e.ctrlKey || e.metaKey;
      if (cmd && !e.shiftKey && !e.altKey && (e.key === "n" || e.key === "N")) {
        e.preventDefault();
        openCompose({ to: "", subject: "", html: "" });
      } else if (cmd && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        app.paletteOpen = true;
      } else if (e.key === "Escape") {
        app.threadKey = null; app.selectedMessageId = null;   // back to the list
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
      // to_addrs/cc_addrs entries may be "Name <addr>" - compare on the address.
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
    // Carry the original (non-inline) attachments - a forward without them is
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
  let snoozeMenu = $state(false);
  $effect(() => { void app.selectedMessageId; snoozeMenu = false; });
  function actionDef(key) {
    switch (key) {
      case "reply": return { icon: icons.reply, label: t("reader.reply"), run: reply };
      case "replyAll": return { icon: icons.replyAll, label: t("reader.replyAll"), run: replyAll, hide: replyAllCc().length === 0 };
      case "forward": return { icon: icons.forward, label: t("reader.forward"), run: forward };
      case "done": return { icon: detail.is_done ? icons.restore : icons.done, label: detail.is_done ? t("reader.restore") : t("reader.done"), run: () => markDone(detail, !detail.is_done) };
      case "flag": return { icon: detail.is_flagged ? icons.flagged : icons.flag, label: detail.is_flagged ? t("reader.flagged") : t("reader.flag"), run: toggleFlag, cls: detail.is_flagged ? "on" : "" };
      case "archive": return { icon: icons.archive, label: t("list.archive"), run: () => archiveMessage(detail) };
      case "snooze": return { icon: icons.snooze, label: t("list.snooze"), run: () => (snoozeMenu = !snoozeMenu), snooze: true };
      case "delete": return { icon: icons.trash, label: t("list.delete"), run: () => deleteMessage(detail), cls: "del" };
      default: return null;
    }
  }
  // Triage from the reader without a trip back to the list: archive/snooze/
  // delete ride along even for saves from before they existed. A customized
  // set (≠ the old default) is respected as-is.
  const _OLD_DEFAULT = "reply,replyAll,forward,done,flag";
  const readerBtns = $derived.by(() => {
    const conf = app.settings.readerActions;
    const keys = (!conf || conf.join(",") === _OLD_DEFAULT)
      ? ["reply", "replyAll", "forward", "archive", "snooze", "done", "flag", "delete"]
      : conf;
    return keys.map(actionDef).filter((b) => b && !b.hide);
  });

  const attachments = $derived((detail?.attachments || []).filter((a) => !a.inline));
  // Per-account color for the reader header accent (multi-account cohesion - the
  // same color that stripes this account's rows in the list).
  const readerAcctColor = $derived(app.accounts.find((a) => a.id === detail?.account_id)?.color || null);
  const multiAcct = $derived(app.accounts.length > 1);

  // Image attachments get an inline thumbnail: fetch the bytes (authenticated),
  // make an object URL, and revoke it when the message changes / on unmount.
  let thumbs = $state({});
  let _thumbUrls = [];
  $effect(() => {
    const id = detail?.id;
    const atts = attachments;
    _thumbUrls.forEach((u) => { try { URL.revokeObjectURL(u); } catch {} });
    _thumbUrls = []; thumbs = {};
    if (!id) return;
    for (const a of atts) {
      if (!isImageName(a.filename)) continue;
      fetchAttachment(id, a.index).then((blob) => {
        if (app.selectedMessageId !== id) return;
        const url = URL.createObjectURL(blob); _thumbUrls.push(url);
        thumbs = { ...thumbs, [a.index]: url };
      }).catch(() => {});
    }
    return () => { _thumbUrls.forEach((u) => { try { URL.revokeObjectURL(u); } catch {} }); };
  });
  function humanSize(n) {
    if (!n) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  }
  let downloading = $state(null);
  let suspicious = $state(null);  // an attachment awaiting the risk confirmation
  // Click an attachment → open it with the OS default app. A file the backend
  // flagged as risky is intercepted here: the user is offered the sandbox first.
  async function openAtt(att) {
    if (sandboxOn && isFlagged(att)) { suspicious = withDeep(att); return; }
    await openAttOS(att);
  }
  async function openAttOS(att) {
    downloading = att.index;
    try { await openAttachment(detail.id, att.index, att.filename); }
    catch (e) { notify(e.message || t("reader.couldntOpenAttachment"), "error"); }
    finally { downloading = null; }
  }
  // Analyze an attachment in the isolated WebAssembly sandbox (never the OS).
  async function sandboxAtt(att) {
    downloading = att.index;
    try { await sandboxAttachment(detail.id, att); }
    finally { downloading = null; }
  }
  async function saveAsAtt(att) {
    downloading = att.index;
    try {
      const path = await saveAttachmentAs(detail.id, att.index, att.filename);
      if (path) { notify(t("reader.savedTo", { path })); revealPath(path); }
    } catch (e) { notify(e.message || t("reader.couldntSaveAttachment"), "error"); }
    finally { downloading = null; }
  }
  function onSuspiciousClose(action) {
    const att = suspicious; suspicious = null;
    if (!att) return;
    if (action === "sandbox") sandboxAtt(att);
    else if (action === "open") openAttOS(att);
  }

  // Right-click context menu.
  const sandboxOn = $derived(app.settings.sandboxEnabled !== false);

  // Automatic background deep-scan of Office / PDF / archive attachments: fetch
  // + de-obfuscate in the backend (never executes), cache, and surface a verdict
  // badge. A high deep score escalates the pre-click warning even for a file the
  // fast filename/magic heuristic didn't flag.
  const DEEP_KINDS = new Set(["pdf", "doc", "sheet", "slide", "archive"]);
  let deepV = $state({});   // index -> { score, verdict, summary[] }
  let _deepFor = null;
  const _deepStarted = new Set();
  $effect(() => {
    const id = detail?.id;
    const atts = attachments;
    if (_deepFor !== id) { _deepFor = id; _deepStarted.clear(); deepV = {}; }
    if (!id || !sandboxOn) return;
    untrack(() => {
      for (const a of atts) {
        if (!DEEP_KINDS.has(fileKind(a.filename))) continue;
        if (_deepStarted.has(a.index)) continue;
        _deepStarted.add(a.index);
        deepScanAttachment(id, a).then((rep) => {
          if (app.selectedMessageId !== id || !rep) return;
          const s = rep.score || 0;
          const verdict = s >= 55 ? "high" : s >= 22 ? "medium" : s > 0 ? "low" : "none";
          deepV = { ...deepV, [a.index]: { score: s, verdict, summary: rep.summary || [] } };
        }).catch(() => {});
      }
    });
  });
  // Worst of the fast heuristic risk and the deep-scan verdict.
  const RANK = { high: 3, medium: 2, low: 1, none: 0, "": 0, undefined: 0 };
  function effRisk(a) {
    const d = deepV[a.index]?.verdict || "none";
    return RANK[d] >= RANK[a.risk || "none"] ? d : (a.risk || "none");
  }
  function isFlagged(a) {
    const r = effRisk(a);
    return r === "high" || r === "medium";
  }
  // Build the attachment object the modal sees, merging deep-scan reasons in.
  function withDeep(a) {
    const dv = deepV[a.index];
    if (!dv || !dv.summary?.length) return { ...a, risk: effRisk(a) };
    return { ...a, risk: effRisk(a), risk_reasons: [...(a.risk_reasons || []), ...dv.summary] };
  }
  let attMenu = $state(null);  // { att, x, y }
  function openAttMenu(att, e) {
    e.preventDefault();
    attMenu = { att, x: e.clientX, y: e.clientY };
  }
  function onAttMenuAction(kind) {
    const att = attMenu?.att; if (!att) return;
    if (kind === "open") openAtt(att);
    else if (kind === "sandbox") sandboxAtt(att);
    else if (kind === "downloads") saveAtt(att);
    else if (kind === "saveas") saveAsAtt(att);
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

  // Reader right-click menu - long overdue. Opens over the header and (via the
  // forwarded iframe event) anywhere inside the email body.
  function openReaderCtx(e) {
    if (!detail) return;
    e.preventDefault();
    ctxMenu = { x: e.clientX, y: e.clientY };
  }
  async function copySubject() {
    try { await navigator.clipboard.writeText(detail?.subject || ""); notify(t("reader.subjectCopied")); }
    catch { notify(t("reader.couldntCopy"), "error"); }
  }
  const readerCtxActions = $derived.by(() => {
    if (!detail) return [];
    return [
      { label: t("reader.reply"), icon: icons.reply, run: reply },
      ...(replyAllCc().length ? [{ label: t("reader.replyAll"), icon: icons.replyAll, run: replyAll }] : []),
      { label: t("reader.forward"), icon: icons.forward, run: forward },
      { sep: true },
      { label: t("reader.copyAddress"), icon: icons.copy, run: () => copyAddress(detail.from_addr) },
      { label: t("reader.copySubject"), icon: icons.copy, run: copySubject },
      { label: t("reader.showMailFromTo"), icon: icons.inbox, run: () => showFrom(detail.from_addr) },
      { sep: true },
      { label: t("list.sendToLab"), icon: icons.shieldCheck, run: () => sendToLab(detail) },
      { label: t("reader.exportEml"), icon: icons.save || icons.download, run: exportEml },
    ];
  });
  function runCtx(a) { ctxMenu = null; a.run(); }

  async function unsubscribe() {
    const parts = [...(detail.unsubscribe || "").matchAll(/<([^>]+)>/g)].map((m) => m[1].trim());
    const http = parts.find((p) => p.startsWith("http"));
    const mailto = parts.find((p) => p.startsWith("mailto:"));
    const who = detail.from_addr;
    if (http) {
      // Try RFC 8058 one-click POST first (some links error on a plain browser
      // GET); fall back to the OS browser (window.open is a no-op in the webview).
      try {
        const r = await subscriptions.unsubscribe(http);
        if (r?.ok) { markUnsubscribed(who); notify(t("utility.unsubDone", { who })); return; }
      } catch {}
      openExternal(http);
      markUnsubscribed(who);
    } else if (mailto) {
      const addr = mailto.slice(7).split("?")[0];
      openCompose({ to: addr, subject: "Unsubscribe", html: "Please unsubscribe me from this list.", account_id: detail.account_id });
      markUnsubscribed(who);
    }
  }
</script>

<svelte:window onclick={() => { menuAddr = null; snoozeMenu = false; ctxMenu = null; }}
  onkeydown={(e) => { if (e.key === "Escape") ctxMenu = null; }} />

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
    {#key app.selectedMessageId}
    <div class="msgfade" in:fade={{ duration: 120 }}>
    <header oncontextmenu={openReaderCtx} style={multiAcct && readerAcctColor ? `border-left:3px solid ${readerAcctColor}` : ""}>
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
              <button onclick={() => { menuAddr = null; createRuleFromSender(detail); }}>{@html icons.bolt} {t("list.createRule")}</button>
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
    {#if secPills.length || screenerActive || detail.unsubscribe || (processed.blocked > 0 && !loadImages) || aiVerdict || aiScreening || (aiOn && aiScreenMode === "manual")}
      <div class="sec-strip">
        {#each secPills as p (p.key)}
          <button class="sec-pill {p.kind}" class:open={secOpen === p.key} title={p.detail}
            onclick={() => (secOpen = secOpen === p.key ? null : p.key)}>
            {@html p.icon}<span class="sp-label">{p.label}</span>
            {#if p.detail}<span class="sp-caret" class:up={secOpen === p.key}>▾</span>{/if}
          </button>
        {/each}
        {#if screenerActive}
          <button class="sec-pill warn" class:open={secOpen === "screener"}
            onclick={() => (secOpen = secOpen === "screener" ? null : "screener")}>
            {@html icons.screener}<span class="sp-label">{t("reader.newSenderBadge")}</span>
            <span class="sp-caret" class:up={secOpen === "screener"}>▾</span>
          </button>
        {/if}
        {#if detail.unsubscribe}
          <button class="sec-pill neutral" class:open={secOpen === "unsub"}
            onclick={() => (secOpen = secOpen === "unsub" ? null : "unsub")}>
            {@html icons.mail}<span class="sp-label">{t("reader.mailingListBadge")}</span>
            <span class="sp-caret" class:up={secOpen === "unsub"}>▾</span>
          </button>
        {/if}
        {#if processed.blocked > 0 && !loadImages}
          <button class="sec-pill neutral" class:open={secOpen === "trackers"}
            onclick={() => (secOpen = secOpen === "trackers" ? null : "trackers")}>
            {@html icons.shield}<span class="sp-label">{processed.blocked === 1 ? t("reader.blockedPixelOne") : t("reader.blockedPixelN", { n: processed.blocked })}</span>
            <span class="sp-caret" class:up={secOpen === "trackers"}>▾</span>
          </button>
        {/if}
        {#if aiScreening}
          <span class="sec-pill neutral"><span class="ai-spin">{@html icons.bolt}</span><span class="sp-label">{t("reader.aiChecking")}</span></span>
        {:else if aiVerdictPill}
          <button class="sec-pill {aiVerdictPill.kind}" class:open={secOpen === "ai"}
            onclick={() => (secOpen = secOpen === "ai" ? null : "ai")}>
            {@html aiVerdictPill.icon}<span class="sp-label">{aiVerdictPill.label}</span>
            <span class="sp-caret" class:up={secOpen === "ai"}>▾</span>
          </button>
        {:else if aiOn && aiScreenMode === "manual"}
          <button class="sec-pill neutral" onclick={() => screenNow(false)}>
            {@html icons.bolt}<span class="sp-label">{t("reader.aiCheck")}</span>
          </button>
        {/if}
      </div>
      {#if secOpenPill}
        <div class="sec-detail {secOpenPill.kind}">
          <span class="sd-text">{secOpenPill.detail}</span>
          {#if secOpenPill.act}
            <button class="sd-act" title={secOpenPill.act.title || ""} onclick={secOpenPill.act.run}>
              {#if secOpenPill.act.icon}{@html secOpenPill.act.icon} {/if}{secOpenPill.act.label}
            </button>
          {/if}
        </div>
      {/if}
      {#if secOpen === "screener"}
        <div class="sec-detail warn">
          <span class="sd-text">{t("reader.firstTimeSender", { addr: detail.from_addr })}</span>
          <button class="sd-act" onclick={() => approveSender(detail)}>{@html icons.done} {t("reader.approve")}</button>
          <button class="sd-act danger" onclick={() => blockSender(detail)}>{@html icons.close} {t("reader.block")}</button>
        </div>
      {/if}
      {#if secOpen === "unsub"}
        <div class="sec-detail neutral">
          <span class="sd-text">{t("reader.mailingList")}</span>
          <button class="sd-act" onclick={unsubscribe}>{t("reader.unsubscribe")}</button>
        </div>
      {/if}
      {#if secOpen === "trackers"}
        <div class="sec-detail neutral trackers">
          <span class="sd-text">{processed.blocked === 1 ? t("reader.blockedTrackerOne") : t("reader.blockedTrackerN", { n: processed.blocked })}</span>
          <button class="sd-act" onclick={() => (loadImages = true)}>{t("reader.loadEverything")}</button>
          {#if processed.urls.length}
            <ul class="tracker-list">
              {#each processed.urls as u}<li title={u}>{u}</li>{/each}
            </ul>
          {/if}
        </div>
      {/if}
      {#if secOpen === "ai" && aiVerdictPill}
        <div class="sec-detail {aiVerdictPill.kind} aiverdict">
          {#if aiVerdict.reason}<span class="sd-text">{aiVerdict.reason}</span>{/if}
          <button class="sd-act" onclick={() => screenNow(true)} disabled={aiScreening}>
            {@html icons.bolt} {t("reader.aiRecheck")}
          </button>
          <span class="ai-disclaimer">{t("reader.aiScreenDisclaimer")}</span>
        </div>
      {/if}
    {/if}
    {#if attachments.length}
      <div class="attachments">
        <span class="att-label">{@html icons.attachment} {attachments.length === 1 ? t("reader.attachmentOne") : t("reader.attachmentN", { n: attachments.length })}</span>
        {#each attachments as a}
          <span class="att" class:busy={downloading === a.index} class:risky={isFlagged(a)}
                oncontextmenu={(e) => openAttMenu(a, e)}>
            <button class="att-open" title={t("reader.openFile", { name: a.filename })} onclick={() => openAtt(a)}>
              {#if thumbs[a.index]}
                <img class="att-thumb" src={thumbs[a.index]} alt="" />
              {:else}
                <span class="att-badge {fileKind(a.filename)}" class:risk={isFlagged(a)}>{fileExt(a.filename)}</span>
              {/if}
              <span class="att-meta">
                <span class="att-name">
                  {#if isFlagged(a)}<span class="att-warn" title={t("threat.riskBadge")}>{@html icons.warning || "!"}</span>{/if}
                  {a.filename}
                </span>
                <span class="att-sub">
                  {#if a.size}<span class="att-size">{humanSize(a.size)}</span>{/if}
                  {#if deepV[a.index]}
                    <span class="scan v-{deepV[a.index].verdict}" title={t("sandbox.scanTip")}>
                      {@html (deepV[a.index].verdict === "none" || deepV[a.index].verdict === "low") ? (icons.shieldCheck || icons.shield || "") : (icons.shieldAlert || icons.warning || "")}
                      {t("sandbox.scan_" + deepV[a.index].verdict)}
                    </span>
                  {:else if DEEP_KINDS.has(fileKind(a.filename)) && sandboxOn}
                    <span class="scan v-scanning" title={t("sandbox.scanTip")}>{t("sandbox.scanning")}</span>
                  {/if}
                </span>
              </span>
              {#if downloading === a.index}<span class="att-dl">…</span>{/if}
            </button>
            {#if sandboxOn}
              <button class="att-sandbox" title={t("threat.openSandbox")} onclick={() => sandboxAtt(a)}>{@html icons.shield || icons.lock || "▣"}</button>
            {/if}
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
    {#if suspicious}
      <SuspiciousModal att={suspicious} onclose={onSuspiciousClose} />
    {/if}
    {#if attMenu}
      <AttachmentMenu x={attMenu.x} y={attMenu.y} sandboxOn={sandboxOn}
        risky={isFlagged(attMenu.att)}
        onaction={onAttMenuAction} onclose={() => (attMenu = null)} />
    {/if}
    {#if detail.html || detail.text}
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
    <div class="body-card" oncontextmenu={openReaderCtx}>
      <iframe title={t("reader.messageFrameTitle")} bind:this={frame} onload={wireFrameLinks}
        style="height:{frameH}px"
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" srcdoc={srcdoc}></iframe>
    </div>
    {#if actionsBottom}{@render actionsBar()}{/if}
    </div>
    {/key}
  {/if}
</section>

{#if ctxMenu}
  <div class="reader-ctx" style="left:{ctxMenu.x}px; top:{ctxMenu.y}px"
    onclick={(e) => e.stopPropagation()} oncontextmenu={(e) => e.preventDefault()}>
    {#each readerCtxActions as a}
      {#if a.sep}<div class="rc-sep"></div>
      {:else}<button class="rc-item" onclick={() => runCtx(a)}>{@html a.icon} {a.label}</button>{/if}
    {/each}
  </div>
{/if}

{#snippet actionsBar()}
  <div class="actions" class:bottom={actionsBottom}>
    {#each readerBtns as b}
      {#if b.snooze}
        <span class="snz-wrap">
          <button class="btn" class:on={snoozeMenu} onclick={(e) => { e.stopPropagation(); b.run(); }}>{@html b.icon} {b.label}</button>
          {#if snoozeMenu}
            <div class="snz-menu" class:up={actionsBottom} onclick={(e) => e.stopPropagation()}>
              {#each snoozePresets() as p}
                <button onclick={() => { snoozeMenu = false; snoozeMessage(detail, p.iso, p.presence); }}>
                  {p.label}{#if p.at} · <span class="when">{presetWhen(p.at)}</span>{/if}
                </button>
              {/each}
            </div>
          {/if}
        </span>
      {:else}
        <button class="btn {b.cls || ''}" onclick={b.run}>{@html b.icon} {b.label}</button>
      {/if}
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
  /* The reader is the scroll container: the header + badge strip scroll away with
     the message body (they used to be pinned while only the iframe scrolled, which
     ate half the pane on tall headers). The body iframe sizes itself to content. */
  .reader { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; background: var(--bg); }
  /* Wraps the single message so it cross-fades in when you switch mails (keyed on
     the selected id) instead of hard-popping. */
  .msgfade { display: flex; flex-direction: column; min-width: 0; }
  .placeholder { flex: 1; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; color: var(--muted); animation: rise-in var(--t-slow) var(--ease); }
  .placeholder .big { display: grid; place-items: center; width: 72px; height: 72px; border-radius: 22px;
    background: var(--accent-soft); color: var(--accent); font-size: 32px;
    box-shadow: inset 0 0 0 1px var(--accent-soft-2); }
  .placeholder .big :global(svg) { width: 34px; height: 34px; }
  .placeholder.err { color: var(--danger); }
  .placeholder .rapl-link { margin-top: 2px; font-size: 12px; color: var(--accent); text-decoration: none; opacity: 0.8; }
  .placeholder .rapl-link:hover { opacity: 1; text-decoration: underline; }
  /* Rounded "message header" card - mirrors the thread's per-message cards for a
     unified feel (was a flat full-width bar with a bottom border). */
  header { margin: 14px 16px 8px; padding: 15px 18px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05); display: flex; flex-direction: column; gap: 6px; }
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
  /* Solid background - backdrop blur on a sticky bar repaints every scroll frame. */
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
  .actions .btn.del:hover { background: var(--danger); border-color: var(--danger); color: #fff; }
  .snz-wrap { position: relative; display: inline-block; }
  .snz-menu {
    position: absolute; top: calc(100% + 4px); left: 0; z-index: 25; min-width: 170px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column;
    animation: pop-in var(--t) var(--ease); transform-origin: top left;
  }
  .snz-menu.up { top: auto; bottom: calc(100% + 4px); transform-origin: bottom left; }
  .snz-menu button { text-align: left; padding: 7px 10px; border-radius: 6px; color: var(--text); font-size: 13px; }
  .snz-menu button:hover { background: var(--accent); color: #fff; }
  .snz-menu .when { color: var(--faint); font-size: 11px; }
  .snz-menu button:hover .when { color: #e7e9ff; }
  /* Security pills: trust / auth / PGP / S/MIME + screener / mailing-list /
     trackers, all collapsed into one compact badge row. Click a badge to reveal
     its detail + actions below. */
  .sec-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 22px; border-bottom: 1px solid var(--hairline); }
  .sec-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600;
    padding: 3px 10px; border-radius: 999px; border: 1px solid; cursor: pointer; line-height: 1.4;
    transition: filter var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease); }
  .sec-pill :global(svg) { width: 13px; height: 13px; }
  .sec-pill.ok { color: var(--done); background: var(--done-soft); border-color: color-mix(in srgb, var(--done) 32%, transparent); }
  .sec-pill.bad { color: var(--danger); background: var(--danger-soft); border-color: color-mix(in srgb, var(--danger) 32%, transparent); }
  .sec-pill.warn { color: var(--warning); background: color-mix(in srgb, var(--warning) 13%, transparent); border-color: color-mix(in srgb, var(--warning) 32%, transparent); }
  .sec-pill.neutral { color: var(--muted); background: var(--surface-2); border-color: var(--border); }
  .sec-pill:hover { filter: brightness(1.06); }
  .sec-pill.open { box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 28%, transparent); }
  .sp-caret { font-size: 9px; opacity: 0.65; transition: transform var(--t-fast) var(--ease); }
  .sp-caret.up { transform: rotate(180deg); }
  .sec-detail { display: flex; align-items: center; gap: 10px; padding: 8px 22px; font-size: 12px; border-bottom: 1px solid var(--hairline);
    animation: pop-in var(--t) var(--ease); }
  .sec-detail.ok { background: var(--done-soft); color: var(--done); }
  .sec-detail.bad { background: var(--danger-soft); color: var(--danger); }
  .sec-detail.warn { background: color-mix(in srgb, var(--warning) 13%, transparent); color: var(--warning); }
  .sec-detail.neutral { background: var(--surface); color: var(--muted); }
  .sec-detail.trackers { flex-wrap: wrap; }
  .sd-text { flex: 1; min-width: 0; }
  .sd-act { flex: none; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
    border: 1px solid currentColor; color: inherit; display: inline-flex; align-items: center; gap: 5px; }
  .sd-act:first-of-type { margin-left: auto; }
  .sd-act.danger { color: var(--danger); }
  .sd-act :global(svg) { width: 13px; height: 13px; }
  .sd-act:hover { background: var(--surface-2); }
  .tracker-list { flex-basis: 100%; margin: 4px 0 0; padding: 0 0 0 18px; max-height: 120px; overflow-y: auto; }
  .tracker-list li { color: var(--faint); font-size: 11px; font-family: ui-monospace, monospace; word-break: break-all; line-height: 1.6; }
  .sec-detail.aiverdict { flex-wrap: wrap; }
  .ai-disclaimer { flex-basis: 100%; font-size: 11px; opacity: 0.75; margin-top: 2px; }
  .ai-spin { display: inline-flex; animation: ai-pulse 1s var(--ease) infinite; }
  @keyframes ai-pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
  /* Reader right-click menu. */
  .reader-ctx { position: fixed; z-index: 60; min-width: 210px; max-width: 280px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column;
    animation: pop-in var(--t) var(--ease); transform-origin: top left; }
  .rc-item { display: flex; align-items: center; gap: 9px; text-align: left; padding: 8px 10px;
    border-radius: 6px; color: var(--text); font-size: 13px; }
  .rc-item:hover { background: var(--accent); color: #fff; }
  .rc-item :global(svg) { width: 15px; height: 15px; flex: none; }
  .rc-sep { height: 1px; background: var(--hairline); margin: 4px 6px; }
  .attachments { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .att-label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); margin-right: 4px; }
  .att { display: inline-flex; align-items: stretch; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); max-width: 300px; overflow: hidden; }
  .att:hover { border-color: var(--accent); }
  .att.busy { opacity: 0.6; }
  .att-open { display: inline-flex; align-items: center; gap: 9px; padding: 5px 10px 5px 6px; min-width: 0; }
  .att-save { display: inline-flex; align-items: center; padding: 0 9px; border-left: 1px solid var(--border); color: var(--muted); }
  .att-save:hover { background: var(--surface-3); color: var(--accent); }
  .att-sandbox { display: inline-flex; align-items: center; padding: 0 9px; border-left: 1px solid var(--border); color: var(--muted); }
  .att-sandbox:hover { background: var(--surface-3); color: var(--accent); }
  .att-sandbox :global(svg) { width: 14px; height: 14px; }
  .att.risky { border-color: color-mix(in srgb, var(--danger, #e5484d) 45%, var(--border)); }
  .att-badge.risk { background: var(--danger, #e5484d); }
  .att-warn { display: inline-flex; vertical-align: -2px; margin-right: 3px; color: var(--danger, #e5484d); }
  .att-warn :global(svg) { width: 12px; height: 12px; }
  .att-sub { display: flex; align-items: center; gap: 8px; }
  .scan { display: inline-flex; align-items: center; gap: 3px; font-size: 10.5px; font-weight: 600; }
  .scan :global(svg) { width: 11px; height: 11px; }
  .scan.v-none, .scan.v-low { color: var(--ok, #30a46c); }
  .scan.v-medium { color: #b8801f; }
  .scan.v-high { color: var(--danger, #e5484d); }
  .scan.v-scanning { color: var(--muted); font-weight: 500; }
  .att-thumb { width: 28px; height: 28px; border-radius: 5px; object-fit: cover; flex: none; background: var(--surface-3); }
  .att-badge { flex: none; display: grid; place-items: center; width: 30px; height: 24px; border-radius: 5px;
    font-size: 9px; font-weight: 800; letter-spacing: 0.02em; color: #fff; background: var(--muted); }
  .att-badge.pdf { background: #d84a4a; } .att-badge.image { background: #2ba36b; }
  .att-badge.doc { background: #3e6fe6; } .att-badge.sheet { background: #1a9d5c; }
  .att-badge.slide { background: #e07b2e; } .att-badge.archive { background: #c9922b; }
  .att-badge.code { background: #6d5bd0; } .att-badge.audio { background: #b2478f; }
  .att-badge.video { background: #c0453f; }
  .att-meta { display: flex; flex-direction: column; min-width: 0; align-items: flex-start; }
  .att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; max-width: 200px; }
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
  /* The message body sits in its own framed card (border + shadow + rounded)
     instead of a bare full-bleed div, so it reads as "the email" - matching the
     header card and the conversation cards. */
  .body-card { display: flex; flex-direction: column; margin: 0 16px 14px;
    border: 1px solid var(--border); border-radius: 16px; overflow: hidden; background: var(--surface);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06); }
  /* Height is set inline from the measured content height (see measureFrame) so
     the whole message scrolls in the reader rather than inside the frame. */
  iframe { display: block; border: none; width: 100%; background: var(--bg); }
</style>
