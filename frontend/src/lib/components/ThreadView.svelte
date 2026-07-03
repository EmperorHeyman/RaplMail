<script>
  import { app, markDone, openCompose, notify, refreshMessages } from "../store.svelte.js";
  import { messages as messagesApi } from "../api.js";
  import { icons } from "../icons.js";
  import { sanitizeTrackers, escapeHtml, emailDoc } from "../email.js";
  import { t } from "../i18n.svelte.js";

  let list = $state([]);          // thread messages, oldest first
  let bodies = $state({});        // id -> detail
  let expanded = $state(new Set());
  let loading = $state(false);
  let _key = null;   // previous threadKey — to tell a switch apart from a live refresh

  $effect(() => {
    const key = app.threadKey;
    void app.syncTick;                 // re-fetch when a sync lands (new reply arrives)
    // Only wipe state on an actual conversation switch, not on a sync refresh, so
    // the user's expanded messages / loaded bodies survive a live update.
    if (key !== _key) { _key = key; list = []; bodies = {}; expanded = new Set(); }
    if (!key) return;
    loading = true;
    // Guard against a slow response landing after the user switched threads.
    messagesApi.thread(key).then(async (msgs) => {
      if (app.threadKey !== key) return;
      const firstLoad = list.length === 0;
      list = msgs;
      if (!msgs.length) return;
      const last = msgs[msgs.length - 1];
      // On first open expand the newest; on a live refresh, expand a newly-arrived
      // newest message (e.g. the reply you just sent) so it shows without a click.
      if (firstLoad || !expanded.has(last.id)) {
        expanded = new Set([...expanded, last.id]);
        await loadBody(last.id);
      }
    }).finally(() => { if (app.threadKey === key) loading = false; });
  });

  async function loadBody(id) {
    if (bodies[id]) return;
    try { bodies = { ...bodies, [id]: await messagesApi.get(id) }; } catch {}
  }
  async function toggle(m) {
    const s = new Set(expanded);
    if (s.has(m.id)) s.delete(m.id);
    else { s.add(m.id); await loadBody(m.id); }
    expanded = s;
  }
  function fmt(iso) { return iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : ""; }

  const subject = $derived(list.length ? (list[list.length - 1].subject || t("reader.noSubject")) : "");
  function reply() {
    const last = list[list.length - 1];
    if (!last) return;
    const re = /^re:/i.test(subject) ? subject : `Re: ${subject}`;
    // Quote the latest message so the reply carries thread context (and thread
    // correctly at the recipient via in_reply_to). Body is preloaded on open.
    const body = bodies[last.id];
    const orig = body ? (body.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(body.text || "")}</pre>`)
                      : `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(last.snippet || "")}</pre>`;
    const who = last.from_name ? `${last.from_name} <${last.from_addr || ""}>` : (last.from_addr || "");
    const quote = `<br><br><div style="color:#888">On ${escapeHtml(fmt(last.date))}, ${escapeHtml(who)} wrote:</div>` +
      `<blockquote style="margin:0 0 0 8px;padding-left:10px;border-left:2px solid #888;color:#888">${orig}</blockquote>`;
    openCompose({ to: last.from_addr, subject: re, in_reply_to: last.message_id || "",
                  account_id: last.account_id, html: quote });
  }
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
</script>

<section class="thread">
  {#if loading && list.length === 0}
    <div class="placeholder">{t("reader.loadingConversation")}</div>
  {:else if list.length}
    <header>
      <div class="subject">{subject}</div>
      <div class="sub">{list.length === 1 ? t("reader.messagesInConversationOne") : t("reader.messagesInConversation", { n: list.length })}</div>
      <div class="actions">
        <button class="btn" onclick={reply}>{@html icons.reply} {t("reader.reply")}</button>
        <button class="btn" onclick={doneAll}>{@html icons.done} {t("reader.doneAll")}</button>
      </div>
    </header>
    <div class="scroll">
      {#each list as m (m.id)}
        <div class="msg" class:open={expanded.has(m.id)}>
          <button class="mhead" onclick={() => toggle(m)}>
            <span class="chev">{expanded.has(m.id) ? "▾" : "▸"}</span>
            <span class="who"><b>{m.from_name || m.from_addr}</b></span>
            <span class="date">{fmt(m.date)}</span>
          </button>
          {#if expanded.has(m.id)}
            {#if bodies[m.id]}
              {@const s = sanitizeTrackers(bodies[m.id].html || "", app.settings.blockTrackers)}
              {#if s.blocked > 0}<div class="tnote">{@html icons.shield} {s.blocked === 1 ? t("reader.blockedPixelOne") : t("reader.blockedPixelN", { n: s.blocked })}</div>{/if}
              <iframe title={t("reader.messageFrameTitle")} sandbox="allow-popups allow-popups-to-escape-sandbox"
                srcdoc={emailDoc(s.html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(bodies[m.id].text || "")}</pre>`)}></iframe>
            {:else}
              <div class="loadingbody">{t("reader.loading")}</div>
            {/if}
          {:else}
            <div class="collapsed-snip">{m.snippet}</div>
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
  .actions { display: flex; gap: 8px; margin-top: 8px; }
  .scroll { flex: 1; overflow-y: auto; padding: 10px 16px; display: flex; flex-direction: column; gap: 8px; }
  .msg { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--surface); }
  .mhead { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; padding: 11px 14px; }
  .mhead:hover { background: var(--surface-2); }
  .chev { width: 12px; color: var(--muted); }
  .who { flex: 1; }
  .date { color: var(--faint); font-size: 12px; }
  .collapsed-snip { padding: 0 14px 11px 36px; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tnote { padding: 6px 14px; font-size: 11px; color: var(--muted); background: var(--surface-2); border-top: 1px solid var(--border); }
  iframe { width: 100%; height: 460px; border: none; border-top: 1px solid var(--border); background: var(--bg); }
  .loadingbody { padding: 16px; color: var(--muted); }
</style>
