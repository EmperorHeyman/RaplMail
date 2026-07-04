<script>
  import { app, openCompose, notify, refreshMessages, refreshQueue, setMessageSeen, threadPrefetch } from "../store.svelte.js";
  import { messages as messagesApi, openAttachment, openExternal, fetchAttachmentForCompose } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc } from "../email.js";
  import { t } from "../i18n.svelte.js";

  let list = $state([]);          // thread messages, oldest first
  let bodies = $state({});        // id -> detail
  let expanded = $state(new Set());
  let loading = $state(false);
  let _key = null;   // previous threadKey — to tell a switch apart from a live refresh

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
    // The Reader already fetched this thread when it auto-promoted the view —
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
      // clicked, the newest one, and any unread — capped so a long neglected
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
      // sent) — show it without a click.
      expanded = new Set([...expanded, last.id]);
      await loadBody(last.id);
      if (!last.is_seen) setMessageSeen(last, true);
    }
  }

  // Clicking another message of the SAME conversation in the list doesn't
  // reload the thread (key unchanged) — expand + jump to that message here.
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
      // Drop the completed conversation from the list too — it otherwise sat
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

  async function openAtt(m, att) {
    try { await openAttachment(m.id, att.index, att.filename); }
    catch (e) { notify(e.message || t("reader.couldntOpenAttachment"), "error"); }
  }
</script>

<section class="thread">
  {#if loading && list.length === 0}
    <div class="placeholder">{t("reader.loadingConversation")}</div>
  {:else if list.length}
    <header>
      <div class="subject">{subject}</div>
      <div class="sub">{list.length === 1 ? t("reader.messagesInConversationOne") : t("reader.messagesInConversation", { n: list.length })}</div>
      <div class="actions">
        <button class="btn" onclick={() => replyTo(list[list.length - 1])}>{@html icons.reply} {t("reader.reply")}</button>
        <button class="btn" onclick={() => forwardMsg(list[list.length - 1])}>{@html icons.forward} {t("reader.forward")}</button>
        <button class="btn" onclick={archiveAll}>{@html icons.archive} {t("reader.archiveAll")}</button>
        <button class="btn" onclick={doneAll}>{@html icons.done} {t("reader.doneAll")}</button>
      </div>
    </header>
    <div class="scroll">
      {#each list as m (m.id)}
        <div class="msg" class:open={expanded.has(m.id)} id={"tmsg-" + m.id}>
          <div class="mhead" class:unread={!m.is_seen}>
            <button class="mh-main" onclick={() => toggle(m)}>
              <span class="chev">{expanded.has(m.id) ? "▾" : "▸"}</span>
              <span class="who">{m.from_name || m.from_addr}</span>
              {#if !expanded.has(m.id)}<span class="snip">{m.snippet}</span>{/if}
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
                    <button class="att" title={t("reader.openFile", { name: a.filename })} onclick={() => openAtt(m, a)}>
                      {@html icons.attachment} <span class="att-name">{a.filename}</span>
                    </button>
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
  {/if}
</section>

<style>
  .thread { display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  .placeholder { flex: 1; display: grid; place-items: center; color: var(--muted); }
  header { padding: 18px 22px 14px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
  .subject { font-size: 19px; font-weight: 700; }
  .sub { color: var(--muted); font-size: 12px; }
  .actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  .scroll { flex: 1; overflow-y: auto; padding: 10px 16px 24px; display: flex; flex-direction: column; gap: 8px; }
  .msg { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--surface); flex: none; }
  .mhead { display: flex; align-items: center; gap: 10px; padding: 0 10px 0 0; }
  .mhead:hover { background: var(--surface-2); }
  .mhead.unread .who { font-weight: 700; }
  .mh-main { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; text-align: left; padding: 11px 0 11px 14px; }
  .chev { width: 12px; color: var(--muted); flex: none; }
  .who { flex: none; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .snip { flex: 1; min-width: 0; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .warn { color: var(--danger); display: inline-flex; flex: none; }
  .date { color: var(--faint); font-size: 12px; flex: none; }
  .mh-acts { display: flex; gap: 2px; flex: none; }
  .mib { width: 28px; height: 28px; border-radius: 6px; display: grid; place-items: center; color: var(--muted); }
  .mib:hover { background: var(--surface-3); color: var(--accent); }
  .tnote { padding: 6px 14px; font-size: 11px; color: var(--muted); background: var(--surface-2); border-top: 1px solid var(--border); }
  .atts { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px; border-top: 1px solid var(--border); background: var(--surface); }
  .att { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; font-size: 12px;
         border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); max-width: 260px; }
  .att:hover { border-color: var(--accent); }
  .att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  iframe { width: 100%; height: 200px; border: none; border-top: 1px solid var(--border); background: var(--bg); display: block; }
  .loadingbody { padding: 16px; color: var(--muted); }
</style>
