<script>
  import { app, openCompose, notify, refreshMessages, refreshQueue, setMessageSeen, threadPrefetch, sandboxAttachment } from "../store.svelte.js";
  import { messages as messagesApi, openAttachment, saveAttachment, saveAttachmentAs, revealPath, openExternal, fetchAttachmentForCompose } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc } from "../email.js";
  import { senderHue, avatarColor, initialOf as initialFor } from "../avatar.js";
  import { fileExt, fileKind } from "../attachments.js";
  import { t } from "../i18n.svelte.js";
  import SuspiciousModal from "./SuspiciousModal.svelte";
  import AttachmentMenu from "./AttachmentMenu.svelte";

  let list = $state([]);          // thread messages, oldest first
  let bodies = $state({});        // id -> detail
  let expanded = $state(new Set());
  let loading = $state(false);
  let _key = null;   // previous threadKey - to tell a switch apart from a live refresh
  // Honor the Appearance setting for where Reply/Forward/… sit (top vs bottom),
  // same as the single-message reader - otherwise conversations always showed top.
  const actionsBottom = $derived(app.settings.readerActionsPos === "bottom");

  // Cap how many messages auto-expand: the clicked one + the newest + unread,
  // but never a wall of 20 open bodies at once.
  const AUTO_EXPAND_MAX = 5;

  $effect(() => {
    const key = app.threadKey;
    void app.syncTick;                 // re-fetch when a sync lands (new reply arrives)
    // Only wipe state on an actual conversation switch, not on a sync refresh, so
    // the user's expanded messages / loaded bodies survive a live update.
    if (key !== _key) { _key = key; list = []; bodies = {}; expanded = new Set(); }
    if (!key) return;
    // The Reader already fetched this thread when it auto-promoted the view -
    // consume that result instead of asking again.
    if (list.length === 0 && threadPrefetch.key === key && threadPrefetch.msgs) {
      const pre = threadPrefetch.msgs;
      threadPrefetch.key = null; threadPrefetch.msgs = null;
      apply(key, pre);
      return;
    }
    loading = true;
    // Guard against a slow response landing after the user switched threads.
    messagesApi.thread(key)
      .then((msgs) => { if (app.threadKey === key) return apply(key, msgs); })
      .finally(() => { if (app.threadKey === key) loading = false; });
  });

  async function apply(key, msgs) {
    const firstLoad = list.length === 0;
    list = msgs;
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    if (firstLoad) {
      // Open what the user came for without another click: the message they
      // clicked, the newest one, and any unread - capped so a long neglected
      // thread doesn't unfold entirely.
      const want = new Set([last.id]);
      const sel = msgs.find((x) => x.id === app.selectedMessageId);
      if (sel) want.add(sel.id);
      for (const m of msgs) {
        if (want.size >= AUTO_EXPAND_MAX) break;
        if (!m.is_seen) want.add(m.id);
      }
      expanded = new Set([...expanded, ...want]);
      await Promise.all([...want].map(loadBody));
      for (const m of msgs) if (want.has(m.id) && !m.is_seen) setMessageSeen(m, true);
      // Land the view on the message the user opened (threads can be long).
      const target = sel || last;
      requestAnimationFrame(() => {
        document.getElementById(`tmsg-${target.id}`)?.scrollIntoView({ block: "start" });
      });
    } else if (!expanded.has(last.id)) {
      // A live refresh brought a new newest message (e.g. the reply you just
      // sent) - show it without a click.
      expanded = new Set([...expanded, last.id]);
      await loadBody(last.id);
      if (!last.is_seen) setMessageSeen(last, true);
    }
  }

  // Clicking another message of the SAME conversation in the list doesn't
  // reload the thread (key unchanged) - expand + jump to that message here.
  let _selSeen = null;
  $effect(() => {
    const sel = app.selectedMessageId;
    if (sel === _selSeen) return;
    _selSeen = sel;
    const m = list.find((x) => x.id === sel);
    if (!m) return;
    if (!expanded.has(m.id)) {
      expanded = new Set([...expanded, m.id]);
      if (!m.is_seen) setMessageSeen(m, true);
      loadBody(m.id);
    }
    requestAnimationFrame(() => {
      document.getElementById(`tmsg-${m.id}`)?.scrollIntoView({ block: "start" });
    });
  });

  async function loadBody(id) {
    if (bodies[id]) return;
    try { bodies = { ...bodies, [id]: await messagesApi.get(id) }; } catch {}
  }
  async function toggle(m) {
    const s = new Set(expanded);
    if (s.has(m.id)) s.delete(m.id);
    else {
      s.add(m.id);
      if (!m.is_seen) setMessageSeen(m, true);   // reading it = it's read
      await loadBody(m.id);
    }
    expanded = s;
  }
  function fmt(iso) { return iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : ""; }

  const subject = $derived(list.length ? (list[list.length - 1].subject || t("reader.noSubject")) : "");

  // --- per-message compose actions -----------------------------------------
  function quoteOf(m) {
    const body = bodies[m.id];
    const orig = body
      ? (body.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(body.text || "")}</pre>`)
      : `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(m.snippet || "")}</pre>`;
    const who = m.from_name ? `${m.from_name} <${m.from_addr || ""}>` : (m.from_addr || "");
    return `<br><br><div style="color:#888">On ${escapeHtml(fmt(m.date))}, ${escapeHtml(who)} wrote:</div>` +
      `<blockquote style="margin:0 0 0 8px;padding-left:10px;border-left:2px solid #888;color:#888">${orig}</blockquote>`;
  }
  function reSubjectOf(m) {
    const s = m.subject || subject || t("reader.noSubject");
    return /^re:/i.test(s) ? s : `Re: ${s}`;
  }
  function myIdentities(m) {
    const acct = app.accounts.find((a) => a.id === m.account_id);
    if (!acct) return [];
    return [acct.email, ...(acct.aliases || [])].map((x) => (x || "").toLowerCase().trim()).filter(Boolean);
  }

  // Per-sender identity: a stable color + initial (shared with the list, via
  // avatar.js) so a person looks the same everywhere, plus whether it's from ME
  // (mine = accent + right-aligned, chat-style).
  function isMine(m) { return myIdentities(m).includes((m.from_addr || "").toLowerCase()); }
  function avatarBg(m) {
    return isMine(m) ? "background: var(--accent);"
                     : `background: ${avatarColor(m.from_addr || m.from_name)};`;
  }
  function initialOf(m) { return initialFor(m.from_name || m.from_addr); }
  function replyTo(m) {
    openCompose({ to: m.from_addr, subject: reSubjectOf(m), in_reply_to: m.message_id || "",
                  account_id: m.account_id, html: quoteOf(m) });
  }
  function replyAllTo(m) {
    const d = bodies[m.id];
    if (!d) return replyTo(m);
    const all = [...(d.to_addrs || []), ...(d.cc_addrs || [])];
    const seen = new Set([...myIdentities(m), (m.from_addr || "").toLowerCase()]);
    const cc = [];
    for (const a of all) {
      const k = (a || "").toLowerCase();
      const addr = (k.match(/<([^>]+)>/)?.[1] || k).trim();
      if (addr && !seen.has(addr)) { seen.add(addr); cc.push(a); }
    }
    openCompose({ to: m.from_addr, cc: cc.join(", "), subject: reSubjectOf(m),
                  in_reply_to: m.message_id || "", account_id: m.account_id, html: quoteOf(m) });
  }
  async function forwardMsg(m) {
    const d = bodies[m.id];
    const subjBase = m.subject || subject || t("reader.noSubject");
    const subj = /^fwd:/i.test(subjBase) ? subjBase : `Fwd: ${subjBase}`;
    let src = d?.html || "";
    if (src && app.settings.sanitizeForward !== false) src = sanitizeTrackers(src, true).html;
    const orig = src || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(d?.text || m.snippet || "")}</pre>`;
    const quote = `<br><br><div style="color:#888">---------- Forwarded message ----------<br>` +
      `From: ${escapeHtml(m.from_name || "")} &lt;${escapeHtml(m.from_addr || "")}&gt;<br>` +
      `Date: ${escapeHtml(fmt(m.date))}<br>` +
      `Subject: ${escapeHtml(subjBase)}</div><br>${orig}`;
    const atts = (d?.attachments || []).filter((a) => !a.inline);
    let attachments = [];
    if (atts.length) {
      try { attachments = await Promise.all(atts.map((a) => fetchAttachmentForCompose(m.id, a))); }
      catch { notify(t("reader.couldntAttachForwarded"), "error"); }
    }
    openCompose({ subject: subj, html: quote, account_id: m.account_id, attachments });
  }

  // Keyboard-routed actions (r/f) act on the newest message of the thread.
  let _cmdSeen = app.readerCmd?.n || 0;
  $effect(() => {
    const rc = app.readerCmd;
    if (!rc || rc.n === _cmdSeen) return;
    _cmdSeen = rc.n;
    const last = list[list.length - 1];
    if (!last) return;
    if (rc.cmd === "reply") replyTo(last);
    else if (rc.cmd === "forward") forwardMsg(last);
  });

  // --- whole-conversation actions -------------------------------------------
  async function doneAll() {
    const ids = new Set(list.map((m) => m.id));
    try {
      await messagesApi.bulk([...ids], "done");
      // Drop the completed conversation from the list too - it otherwise sat
      // there (done-hidden view) until the next sync refresh.
      if (!app.showDone) app.messages = app.messages.filter((m) => !ids.has(m.id));
      notify(t("reader.conversationDone"));
      app.threadKey = null; app.selectedMessageId = null;
      refreshMessages({ background: true });
    }
    catch (e) { notify(t("reader.couldntUpdate"), "error"); }
  }
  async function archiveAll() {
    const ids = new Set(list.map((m) => m.id));
    try {
      await messagesApi.bulk([...ids], "archive");
      app.messages = app.messages.filter((m) => !ids.has(m.id));
      notify(t("reader.conversationArchived"));
      app.threadKey = null; app.selectedMessageId = null;
      refreshQueue();
      refreshMessages({ background: true });
    }
    catch (e) { notify(t("reader.couldntUpdate"), "error"); }
  }

  // --- message body iframe: auto-height + external links --------------------
  // Same-origin sandbox (like the Reader) so we can measure the document and
  // route link clicks to the OS browser; content itself is sanitized upstream.
  function frameAuto(node, m) {
    let ro = null;
    const fit = () => {
      let doc;
      try { doc = node.contentDocument; } catch { doc = null; }
      if (!doc?.documentElement) return;
      const h = Math.min(Math.max(doc.documentElement.scrollHeight, 56) + 4, 6000);
      node.style.height = `${h}px`;
    };
    const wire = () => {
      let doc;
      try { doc = node.contentDocument; } catch { doc = null; }
      if (!doc) return;
      doc.addEventListener("click", (e) => {
        const a = e.target?.closest?.("a[href]");
        if (!a) return;
        const href = (a.getAttribute("href") || "").trim();
        if (/^https?:\/\//i.test(href)) { e.preventDefault(); openExternal(href); }
        else if (href.toLowerCase().startsWith("mailto:")) {
          e.preventDefault();
          openCompose({ to: href.slice(7).split("?")[0], subject: "", html: "", account_id: m.account_id });
        }
      }, true);
      fit();
      ro?.disconnect();
      if (doc.body && typeof ResizeObserver !== "undefined") {
        ro = new ResizeObserver(fit);   // images/fonts landing later change the height
        ro.observe(doc.body);
      }
    };
    node.addEventListener("load", wire);
    wire();
    return {
      update(next) { m = next; },
      destroy() { node.removeEventListener("load", wire); ro?.disconnect(); },
    };
  }

  const sandboxOn = $derived(app.settings.sandboxEnabled !== false);
  let suspicious = $state(null);
  let suspiciousMsgId = null;
  async function openAtt(m, att) {
    if (sandboxOn && (att.risk === "high" || att.risk === "medium")) { suspicious = att; suspiciousMsgId = m.id; return; }
    await openAttOS(m.id, att);
  }
  async function openAttOS(mid, att) {
    try { await openAttachment(mid, att.index, att.filename); }
    catch (e) { notify(e.message || t("reader.couldntOpenAttachment"), "error"); }
  }
  async function sandboxAtt(m, att) {
    try { await sandboxAttachment(m.id, att); } catch {}
  }
  async function saveAtt(mid, att) {
    try {
      const path = await saveAttachment(mid, att.index, att.filename);
      if (path) { notify(t("reader.savedTo", { path })); revealPath(path); }
      else notify(t("reader.downloaded"));
    } catch (e) { notify(e.message || t("reader.couldntSaveAttachment"), "error"); }
  }
  async function saveAsAtt(mid, att) {
    try {
      const path = await saveAttachmentAs(mid, att.index, att.filename);
      if (path) { notify(t("reader.savedTo", { path })); revealPath(path); }
    } catch (e) { notify(e.message || t("reader.couldntSaveAttachment"), "error"); }
  }
  function onSuspiciousClose(action) {
    const att = suspicious, mid = suspiciousMsgId; suspicious = null;
    if (!att) return;
    if (action === "sandbox") sandboxAttachment(mid, att);
    else if (action === "open") openAttOS(mid, att);
  }

  let attMenu = $state(null);  // { m, att, x, y }
  function openAttMenu(m, att, e) { e.preventDefault(); attMenu = { m, att, x: e.clientX, y: e.clientY }; }
  function onAttMenuAction(kind) {
    const it = attMenu; if (!it) return;
    if (kind === "open") openAtt(it.m, it.att);
    else if (kind === "sandbox") sandboxAtt(it.m, it.att);
    else if (kind === "downloads") saveAtt(it.m.id, it.att);
    else if (kind === "saveas") saveAsAtt(it.m.id, it.att);
  }
</script>

<section class="thread">
  {#if loading && list.length === 0}
    <div class="placeholder">{t("reader.loadingConversation")}</div>
  {:else if list.length}
    <header>
      <div class="subject">{subject}</div>
      <div class="sub">{list.length === 1 ? t("reader.messagesInConversationOne") : t("reader.messagesInConversation", { n: list.length })}</div>
      {#if !actionsBottom}<div class="actions">{@render threadActions()}</div>{/if}
    </header>
    <div class="scroll">
      {#each list as m (m.id)}
        <div class="msg" class:open={expanded.has(m.id)} class:mine={isMine(m)} id={"tmsg-" + m.id}
             style="--sender: hsl({senderHue(m.from_addr || m.from_name)} 52% 48%);">
          <div class="mhead" class:unread={!m.is_seen}>
            <button class="mh-main" onclick={() => toggle(m)}>
              <span class="avatar" style={avatarBg(m)}>{initialOf(m)}</span>
              <span class="who-wrap">
                <span class="who">{m.from_name || m.from_addr}</span>
                {#if !expanded.has(m.id)}<span class="snip">{m.snippet}</span>{/if}
              </span>
            </button>
            {#if bodies[m.id]?.warnings?.length}
              <span class="warn" title={bodies[m.id].warnings.join(" · ")}>{@html icons.shieldAlert}</span>
            {/if}
            <span class="date">{fmt(m.date)}</span>
            {#if expanded.has(m.id)}
              <span class="mh-acts">
                <button class="mib" title={t("reader.reply")} onclick={() => replyTo(m)}>{@html icons.reply}</button>
                <button class="mib" title={t("reader.replyAll")} onclick={() => replyAllTo(m)}>{@html icons.replyAll}</button>
                <button class="mib" title={t("reader.forward")} onclick={() => forwardMsg(m)}>{@html icons.forward}</button>
              </span>
            {/if}
          </div>
          {#if expanded.has(m.id)}
            {#if bodies[m.id]}
              {@const s = sanitizeTrackers(bodies[m.id].html || "", app.settings.blockTrackers)}
              {@const atts = (bodies[m.id].attachments || []).filter((a) => !a.inline)}
              {#if s.blocked > 0}<div class="tnote">{@html icons.shield} {s.blocked === 1 ? t("reader.blockedPixelOne") : t("reader.blockedPixelN", { n: s.blocked })}</div>{/if}
              {#if atts.length}
                <div class="atts">
                  {#each atts as a}
                    <span class="att-wrap" class:risky={a.risk === "high" || a.risk === "medium"}
                          oncontextmenu={(e) => openAttMenu(m, a, e)}>
                      <button class="att" title={t("reader.openFile", { name: a.filename })} onclick={() => openAtt(m, a)}>
                        <span class="att-badge {fileKind(a.filename)}" class:risk={a.risk === "high" || a.risk === "medium"}>{fileExt(a.filename)}</span>
                        <span class="att-name">
                          {#if a.risk === "high" || a.risk === "medium"}<span class="att-warn" title={t("threat.riskBadge")}>{@html icons.warning || "!"}</span>{/if}
                          {a.filename}
                        </span>
                      </button>
                      {#if sandboxOn}
                        <button class="att-sb" title={t("threat.openSandbox")} onclick={() => sandboxAtt(m, a)}>{@html icons.shield || "▣"}</button>
                      {/if}
                    </span>
                  {/each}
                </div>
              {/if}
              <iframe title={t("reader.messageFrameTitle")} use:frameAuto={m}
                sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
                srcdoc={emailDoc(s.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(bodies[m.id].text || "")}</pre>`)}></iframe>
            {:else}
              <div class="loadingbody">{t("reader.loading")}</div>
            {/if}
          {/if}
        </div>
      {/each}
    </div>
    {#if actionsBottom}<div class="actions actions-bottom">{@render threadActions()}</div>{/if}
  {/if}
</section>

{#if suspicious}
  <SuspiciousModal att={suspicious} onclose={onSuspiciousClose} />
{/if}
{#if attMenu}
  <AttachmentMenu x={attMenu.x} y={attMenu.y} sandboxOn={sandboxOn}
    risky={attMenu.att.risk === "high" || attMenu.att.risk === "medium"}
    onaction={onAttMenuAction} onclose={() => (attMenu = null)} />
{/if}

{#snippet threadActions()}
  <button class="btn" onclick={() => replyTo(list[list.length - 1])}>{@html icons.reply} {t("reader.reply")}</button>
  <button class="btn" onclick={() => forwardMsg(list[list.length - 1])}>{@html icons.forward} {t("reader.forward")}</button>
  <button class="btn" onclick={archiveAll}>{@html icons.archive} {t("reader.archiveAll")}</button>
  <button class="btn" onclick={doneAll}>{@html icons.done} {t("reader.doneAll")}</button>
{/snippet}

<style>
  .thread { display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  .placeholder { flex: 1; display: grid; place-items: center; color: var(--muted); }
  header { padding: 18px 22px 14px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
  .subject { font-size: 19px; font-weight: 700; }
  .sub { color: var(--muted); font-size: 12px; }
  .actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  .actions-bottom { margin-top: 0; padding: 12px 22px; border-top: 1px solid var(--border); background: var(--surface); }
  .scroll { flex: 1; overflow-y: auto; padding: 14px 16px 28px; display: flex; flex-direction: column; gap: 12px; }
  /* Each reply is its own rounded card, tagged with the sender's color + initial
     so multiple people in one conversation read at a glance. Mine align right
     with an accent tint (chat-style); everyone else's align left. */
  .msg { border: 1px solid var(--border); border-left: 3px solid color-mix(in srgb, var(--sender) 62%, var(--border));
    border-radius: 16px; overflow: hidden; background: var(--surface); flex: none;
    max-width: 94%; align-self: flex-start; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    transition: box-shadow var(--t-fast) var(--ease); }
  .msg.open { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.10); }
  .msg.mine { align-self: flex-end; border-left: 1px solid var(--border); border-right: 3px solid var(--accent);
    background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
  .mhead { display: flex; align-items: center; gap: 10px; padding: 0 12px 0 0; }
  .mhead:hover { background: var(--surface-2); }
  .msg.mine .mhead:hover { background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
  .mhead.unread .who { font-weight: 700; }
  .mh-main { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; text-align: left; padding: 10px 0 10px 12px; }
  .avatar { width: 30px; height: 30px; border-radius: 50%; flex: none; display: grid; place-items: center;
    color: #fff; font-size: 13px; font-weight: 700; }
  .who-wrap { display: flex; flex-direction: column; min-width: 0; gap: 1px; }
  .who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; font-size: 13.5px; }
  .snip { min-width: 0; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .warn { color: var(--danger); display: inline-flex; flex: none; }
  .date { color: var(--faint); font-size: 11.5px; flex: none; }
  .mh-acts { display: flex; gap: 2px; flex: none; }
  .mib { width: 28px; height: 28px; border-radius: 6px; display: grid; place-items: center; color: var(--muted); }
  .mib:hover { background: var(--surface-3); color: var(--accent); }
  .tnote { padding: 6px 14px; font-size: 11px; color: var(--muted); background: var(--surface-2); border-top: 1px solid var(--border); }
  .atts { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px; border-top: 1px solid var(--border); background: var(--surface); }
  .att { display: inline-flex; align-items: center; gap: 7px; padding: 4px 10px 4px 5px; font-size: 12px;
         border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); max-width: 260px; }
  .att:hover { border-color: var(--accent); }
  .att-badge { flex: none; display: grid; place-items: center; width: 28px; height: 22px; border-radius: 5px;
    font-size: 8.5px; font-weight: 800; color: #fff; background: var(--muted); }
  .att-badge.pdf { background: #d84a4a; } .att-badge.image { background: #2ba36b; }
  .att-badge.doc { background: #3e6fe6; } .att-badge.sheet { background: #1a9d5c; }
  .att-badge.slide { background: #e07b2e; } .att-badge.archive { background: #c9922b; }
  .att-badge.code { background: #6d5bd0; } .att-badge.audio { background: #b2478f; }
  .att-badge.video { background: #c0453f; }
  .att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-flex; align-items: center; }
  .att-wrap { display: inline-flex; align-items: stretch; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
  .att-wrap .att { border: none; border-radius: 0; }
  .att-wrap.risky { border-color: color-mix(in srgb, var(--danger, #e5484d) 45%, var(--border)); }
  .att-badge.risk { background: var(--danger, #e5484d); }
  .att-warn { display: inline-flex; vertical-align: -2px; margin-right: 3px; color: var(--danger, #e5484d); }
  .att-warn :global(svg) { width: 11px; height: 11px; }
  .att-sb { display: inline-flex; align-items: center; padding: 0 8px; border-left: 1px solid var(--border); color: var(--muted); background: var(--surface-2); }
  .att-sb:hover { color: var(--accent); background: var(--surface-3); }
  .att-sb :global(svg) { width: 13px; height: 13px; }
  iframe { width: 100%; height: 200px; border: none; border-top: 1px solid var(--border); background: var(--bg); display: block; }
  .loadingbody { padding: 16px; color: var(--muted); }
</style>
