<script>
  import { app, markDone, openCompose, searchAddress, approveSender, blockSender, muteSender, muteThread, notify, isVip, toggleVip } from "../store.svelte.js";
  import { messages as messagesApi, openAttachment, saveAttachment, revealPath, unfurl, ai } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc, splitQuoted } from "../email.js";
  import ThreadView from "./ThreadView.svelte";

  const threadMode = $derived(!!app.threadKey && app.settings.threading);
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
    if (id == null || (app.threadKey && app.settings.threading)) return;
    loading = true;
    messagesApi
      .get(id)
      .then((d) => { detail = d; })
      .catch((e) => { error = e.message; })
      .finally(() => { loading = false; });
  });

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
    const html = `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>`;
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
  // Collapse quoted reply history unless the user expands it (or the setting is off).
  const quoteSplit = $derived(detail ? splitQuoted(processed.html || "") : { main: "", quoted: "" });
  const collapsing = $derived(app.settings.collapseQuotes !== false && !!quoteSplit.quoted && !showQuoted);
  const bodyHtml = $derived(
    collapsing ? quoteSplit.main
               : (processed.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail?.text || "")}</pre>`)
  );
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
  const adaptOn = $derived(app.settings.emailAdaptColors !== false);

  const myAddr = $derived(app.accounts.find((a) => a.id === detail?.account_id)?.email || "");

  // Everyone on the thread except me and the original sender (for Reply All Cc).
  function replyAllCc() {
    if (!detail) return [];
    const all = [...(detail.to_addrs || []), ...(detail.cc_addrs || [])];
    const seen = new Set([myAddr.toLowerCase(), (detail.from_addr || "").toLowerCase()]);
    const out = [];
    for (const a of all) { const k = (a || "").toLowerCase(); if (k && !seen.has(k)) { seen.add(k); out.push(a); } }
    return out;
  }
  const reSubject = () => (/^re:/i.test(detail.subject || "") ? detail.subject : `Re: ${detail.subject || "(no subject)"}`);

  function reply() {
    if (!detail) return;
    openCompose({ to: detail.from_addr, subject: reSubject(), in_reply_to: detail.message_id || "", account_id: detail.account_id });
  }
  function replyAll() {
    if (!detail) return;
    openCompose({ to: detail.from_addr, cc: replyAllCc().join(", "), subject: reSubject(),
                  in_reply_to: detail.message_id || "", account_id: detail.account_id });
  }
  function forward() {
    if (!detail) return;
    const subj = /^fwd:/i.test(detail.subject || "") ? detail.subject : `Fwd: ${detail.subject || "(no subject)"}`;
    const orig = detail.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detail.text || "")}</pre>`;
    const quote =
      `<br><br><div style="color:#888">---------- Forwarded message ----------<br>` +
      `From: ${escapeHtml(detail.from_name || "")} &lt;${escapeHtml(detail.from_addr || "")}&gt;<br>` +
      `Date: ${escapeHtml(fmtDate(detail.date))}<br>` +
      `Subject: ${escapeHtml(detail.subject || "")}<br>` +
      `To: ${escapeHtml((detail.to_addrs || []).join(", "))}</div><br>${orig}`;
    openCompose({ subject: subj, html: quote, account_id: detail.account_id });
  }
  function toggleFlag() {
    if (!detail) return;
    messagesApi.setFlag(detail.id, !detail.is_flagged).then(() => (detail.is_flagged = !detail.is_flagged)).catch(() => {});
  }

  // The action buttons under the recipient line are user-configurable.
  function actionDef(key) {
    switch (key) {
      case "reply": return { icon: icons.reply, label: "Reply", run: reply };
      case "replyAll": return { icon: icons.replyAll, label: "Reply all", run: replyAll, hide: replyAllCc().length === 0 };
      case "forward": return { icon: icons.forward, label: "Forward", run: forward };
      case "done": return { icon: detail.is_done ? icons.restore : icons.done, label: detail.is_done ? "Restore" : "Done", run: () => markDone(detail, !detail.is_done) };
      case "flag": return { icon: detail.is_flagged ? icons.flagged : icons.flag, label: detail.is_flagged ? "Flagged" : "Flag", run: toggleFlag, cls: detail.is_flagged ? "on" : "" };
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
    catch (e) { notify(e.message || "Couldn't open attachment", "error"); }
    finally { downloading = null; }
  }
  // Save one attachment to disk (Downloads).
  async function saveAtt(att) {
    downloading = att.index;
    try {
      const path = await saveAttachment(detail.id, att.index, att.filename);
      if (path) { notify(`Saved to ${path}`); revealPath(path); }
      else notify("Downloaded");
    } catch (e) { notify(e.message || "Couldn't save attachment", "error"); }
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
      if (last) { notify(`Saved ${ok} attachment${ok === 1 ? "" : "s"} to Downloads`); revealPath(last); }
      else if (ok) notify(`Downloaded ${ok} attachment${ok === 1 ? "" : "s"}`);
      else notify("Couldn't save attachments", "error");
    } finally { savingAll = false; }
  }

  function showFrom(addr) { searchAddress(addr); menuAddr = null; }
  function mailTo(addr) { openCompose({ to: addr, account_id: detail?.account_id }); menuAddr = null; }
  async function copyAddress(addr) {
    try { await navigator.clipboard.writeText(addr); notify("Address copied"); }
    catch { notify("Couldn't copy", "error"); }
    menuAddr = null;
  }
  function toggleMenu(e, addr) { e.stopPropagation(); menuAddr = menuAddr === addr ? null : addr; }

  function unsubscribe() {
    const parts = [...(detail.unsubscribe || "").matchAll(/<([^>]+)>/g)].map((m) => m[1].trim());
    const http = parts.find((p) => p.startsWith("http"));
    const mailto = parts.find((p) => p.startsWith("mailto:"));
    if (http) {
      window.open(http, "_blank");
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
      <p>Select a message to read</p>
      <a class="rapl-link" href="https://rapl-group.eu/" target="_blank" rel="noreferrer">rapl-group.eu</a>
    </div>
  {:else if loading}
    <div class="placeholder">Loading…</div>
  {:else if error}
    <div class="placeholder err">{error}</div>
  {:else if detail}
    <header>
      <div class="subject">{detail.subject || "(no subject)"}</div>
      <div class="meta">
        <span class="addr-wrap">
          <button class="addr from" onclick={(e) => toggleMenu(e, detail.from_addr)}>
            <b>{detail.from_name || detail.from_addr}</b> &lt;{detail.from_addr}&gt;
          </button>
          {#if menuAddr === detail.from_addr}
            <div class="menu" onclick={(e) => e.stopPropagation()}>
              <button onclick={() => copyAddress(detail.from_addr)}>{@html icons.copy} Copy address</button>
              <button onclick={() => showFrom(detail.from_addr)}>{@html icons.inbox} Show mail from/to this address</button>
              <button onclick={() => mailTo(detail.from_addr)}>{@html icons.compose} New email to this address</button>
              <button onclick={() => { menuAddr = null; toggleVip(detail.from_addr); }}>{@html icons.star} {isVip(detail.from_addr) ? "Remove VIP" : "Mark as VIP"}</button>
              <button onclick={() => { menuAddr = null; muteSender(detail); }}>{@html icons.mute} Mute this sender</button>
              <button onclick={() => { menuAddr = null; muteThread(detail); }}>{@html icons.mute} Mute this conversation</button>
            </div>
          {/if}
        </span>
        <span class="date">{fmtDate(detail.date)}</span>
      </div>
      <div class="to">
        to
        {#each shownTo as t, i}
          <span class="addr-wrap">
            <button class="addr small" onclick={(e) => toggleMenu(e, t)}>{t}</button>
            {#if menuAddr === t}
              <div class="menu" onclick={(e) => e.stopPropagation()}>
                <button onclick={() => copyAddress(t)}>{@html icons.copy} Copy address</button>
                <button onclick={() => showFrom(t)}>{@html icons.inbox} Show mail from/to this address</button>
                <button onclick={() => mailTo(t)}>{@html icons.compose} New email to this address</button>
              </div>
            {/if}
          </span>{i < shownTo.length - 1 ? ", " : ""}
        {/each}
        {#if detail.to_addrs.length > 3}
          <button class="more-to" onclick={() => (showAllTo = !showAllTo)}>
            {showAllTo ? "show less" : `+${detail.to_addrs.length - 3} more`}
          </button>
        {/if}
      </div>
      <div class="actions">
        {#each readerBtns as b}
          <button class="btn {b.cls || ''}" onclick={b.run}>{@html b.icon} {b.label}</button>
        {/each}
        {#if aiOn}
          <button class="btn ai" onclick={catchMeUp} disabled={summarizing} title="Summarize this thread with AI">
            {@html icons.bolt} {summarizing ? "Summarizing…" : "Catch me up"}
          </button>
          <button class="btn ai" onclick={smartReply} disabled={drafting} title="Draft a reply with AI">
            {@html icons.reply} {drafting ? "Drafting…" : "AI reply"}
          </button>
        {/if}
      </div>
    </header>
    {#if summary}
      <div class="ai-summary">
        <div class="ai-head">{@html icons.bolt} <b>Summary</b>
          <button class="ai-close" title="Dismiss" onclick={() => (summary = "")}>{@html icons.close}</button>
        </div>
        <pre>{summary}</pre>
      </div>
    {/if}
    {#if aiDraft}
      <div class="ai-summary">
        <div class="ai-head">{@html icons.reply} <b>Suggested reply</b>
          <button class="ai-close" title="Dismiss" onclick={() => (aiDraft = null)}>{@html icons.close}</button>
        </div>
        {#if aiDraft.chips?.length}
          <div class="ai-chips">
            {#each aiDraft.chips as c}<button class="ai-chip" onclick={() => useDraft(c)}>{c}</button>{/each}
          </div>
        {/if}
        <pre>{aiDraft.draft}</pre>
        <div class="ai-actions">
          <button class="btn primary" onclick={() => useDraft(aiDraft.draft)}>Edit &amp; send →</button>
          <span class="ai-note">Review before sending — nothing is sent automatically.</span>
        </div>
      </div>
    {/if}
    {#if detail.warnings?.length}
      <div class="auth-bar bad">{@html icons.shieldAlert}
        <span>{detail.warnings.join(" · ")}</span>
      </div>
    {/if}
    {#if detail.pgp?.type === "encrypted"}
      <div class="auth-bar {detail.pgp.decrypted || detail.text ? 'ok' : 'bad'}">{@html icons.shieldCheck}
        <b>PGP encrypted</b>
        <span class="auth-detail">{detail.pgp.verified ? `· signature verified (${detail.pgp.signer})` : "· decrypted locally"}</span>
      </div>
    {:else if detail.pgp?.type === "signed"}
      <div class="auth-bar {detail.pgp.verified ? 'ok' : 'bad'}">{@html detail.pgp.verified ? icons.shieldCheck : icons.shieldAlert}
        <b>{detail.pgp.verified ? "PGP signature verified" : "PGP signature — couldn't verify"}</b>
        <span class="auth-detail">{detail.pgp.verified ? detail.pgp.signer : "import the sender's public key"}</span>
      </div>
    {/if}
    {#if detail.auth?.status === "fail"}
      <div class="auth-bar bad">{@html icons.shieldAlert} <b>Failed authentication — this message may be spoofed.</b> <span class="auth-detail">{detail.auth.detail}</span></div>
    {:else if detail.auth?.status === "pass"}
      <div class="auth-bar ok">{@html icons.shieldCheck} Sender authenticated <span class="auth-detail">{detail.auth.detail}</span></div>
    {/if}
    {#if app.selectedKind === "screener"}
      <div class="screener-bar">
        {@html icons.screener} First-time sender — do you want mail from <b>{detail.from_addr}</b>?
        <button class="ok" onclick={() => approveSender(detail)}>{@html icons.done} Approve</button>
        <button class="no" onclick={() => blockSender(detail)}>{@html icons.close} Block</button>
      </div>
    {/if}
    {#if detail.unsubscribe}
      <div class="unsub-bar">
        {@html icons.mail} This looks like a mailing list.
        <button onclick={unsubscribe}>Unsubscribe</button>
      </div>
    {/if}
    {#if processed.blocked > 0 && !loadImages}
      <div class="tracker-wrap">
        <div class="tracker-bar">
          {@html icons.shield} Blocked {processed.blocked} tracking {processed.blocked === 1 ? "pixel" : "pixels"} · regular images are shown.
          <button class="tlink" onclick={() => (showTrackers = !showTrackers)}>{showTrackers ? "Hide" : "Details"}</button>
          <button class="tlink" onclick={() => (loadImages = true)}>Load everything</button>
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
        <span class="att-label">{@html icons.attachment} {attachments.length} attachment{attachments.length === 1 ? "" : "s"}</span>
        {#each attachments as a}
          <span class="att" class:busy={downloading === a.index}>
            <button class="att-open" title={`Open ${a.filename}`} onclick={() => openAtt(a)}>
              <span class="att-name">{a.filename}</span>
              {#if a.size}<span class="att-size">{humanSize(a.size)}</span>{/if}
              {#if downloading === a.index}<span class="att-dl">…</span>{/if}
            </button>
            <button class="att-save" title="Save to Downloads" onclick={() => saveAtt(a)}>{@html icons.sent || "↓"}</button>
          </span>
        {/each}
        {#if attachments.length > 1}
          <button class="att-all" onclick={saveAll} disabled={savingAll} title="Save all attachments to Downloads">
            {savingAll ? "Saving…" : "Download all"}
          </button>
        {/if}
      </div>
    {/if}
    {#if detail.html}
      <div class="viewbar">
        {#if quoteSplit.quoted && app.settings.collapseQuotes !== false}
          <button class="vtoggle" class:on={showQuoted} title="Show / hide the quoted reply history"
            onclick={() => (showQuoted = !showQuoted)}>
            ••• {showQuoted ? "Hide quoted" : "Show quoted"}
          </button>
        {/if}
        <button class="vtoggle" class:on={showOriginal} title="Show the email with its own original colors & CSS"
          onclick={() => (showOriginal = !showOriginal)}>
          {@html icons.palette} {showOriginal ? "Original styling" : (adaptOn ? "Adapted to theme" : "Reading view")}
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
    <iframe title="message" sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc={srcdoc}></iframe>
  {/if}
</section>

<style>
  .reader { display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  .placeholder { flex: 1; display: flex; flex-direction: column; gap: 10px; align-items: center; justify-content: center; color: var(--muted); }
  .placeholder .big { font-size: 46px; }
  .placeholder.err { color: var(--danger); }
  .placeholder .rapl-link { margin-top: 2px; font-size: 12px; color: var(--accent); text-decoration: none; opacity: 0.8; }
  .placeholder .rapl-link:hover { opacity: 1; text-decoration: underline; }
  header { padding: 18px 22px 14px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
  .subject { font-size: 19px; font-weight: 700; letter-spacing: -0.01em; }
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
    background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
    box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column;
  }
  .menu button { text-align: left; padding: 8px 10px; border-radius: 6px; color: var(--text); font-size: 13px; }
  .menu button:hover { background: var(--accent); color: #fff; }
  .actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
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
  .auth-bar { display: flex; align-items: center; gap: 8px; padding: 8px 22px; font-size: 13px; border-bottom: 1px solid var(--border); }
  .auth-bar.bad { background: rgba(229,72,77,0.12); color: var(--danger); }
  .auth-bar.ok { background: rgba(46,160,67,0.10); color: var(--done); }
  .auth-bar .auth-detail { color: var(--muted); font-size: 12px; margin-left: auto; }
  .screener-bar { display: flex; align-items: center; gap: 10px; padding: 10px 22px; background: rgba(91,141,239,0.1); border-bottom: 1px solid var(--border); font-size: 13px; }
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
