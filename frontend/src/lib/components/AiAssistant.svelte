<script>
  import { onMount, onDestroy } from "svelte";
  import { app, notify, openCompose, openMessageById, refreshMessages } from "../store.svelte.js";
  import { ai, messages as messagesApi, rules as rulesApi } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // A NON-modal, docked chat window (like the compose panel): you keep clicking
  // and reading the app while it's open, drag it around, and can minimize it into
  // a floating "AI" circle that reopens it (conversation preserved). It answers
  // over emails you add as CONTEXT - the open message, a whole conversation, or
  // the current list. Nothing is ever sent.
  // Context lives in the store so "Add to AI chat" (right-click a message) can add
  // to it whether or not the window is already open.
  const context = $derived(app.aiChatContext);
  let conv = $state([]);           // [{ role: "user"|"assistant", content }]
  let input = $state("");
  let loading = $state(false);
  let minimized = $state(false);
  let scroller, askEl;
  function autogrow() { if (askEl) { askEl.style.height = "auto"; askEl.style.height = Math.min(askEl.scrollHeight, 140) + "px"; } }

  // Drag + resize (docked panel, like Compose). The CSS `resize` handle writes
  // inline width/height; a ResizeObserver captures them so re-applying `style`
  // during a drag doesn't reset the box to its default size (that was the bug).
  let panelEl;
  let dragPos = $state(null);
  let dragging = false, ox = 0, oy = 0;
  let panelW = $state(null), panelH = $state(null);
  $effect(() => {
    if (minimized || !panelEl) return;
    const ro = new ResizeObserver(() => { panelW = panelEl.offsetWidth; panelH = panelEl.offsetHeight; });
    ro.observe(panelEl);
    return () => ro.disconnect();
  });
  const dockStyle = $derived(
    (dragPos ? `left:${dragPos.x}px; top:${dragPos.y}px; right:auto; bottom:auto;`
             : "right:20px; bottom:20px;")
    + (panelW ? ` width:${panelW}px; height:${panelH}px;` : ""));
  function onHeaderDown(e) {
    if (e.target.closest("button")) return;   // clicking header buttons shouldn't drag
    dragging = true;
    const r = panelEl.getBoundingClientRect();
    ox = e.clientX - r.left; oy = e.clientY - r.top;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stopDrag, { once: true });
  }
  function onMove(e) {
    if (!dragging) return;
    dragPos = { x: Math.max(0, Math.min(window.innerWidth - 220, e.clientX - ox)),
                y: Math.max(0, Math.min(window.innerHeight - 60, e.clientY - oy)) };
  }
  function stopDrag() { dragging = false; window.removeEventListener("pointermove", onMove); }

  // (quick prompts and action/rule vocabularies are i18n keys, resolved with t())
  const QUICK = [
    "aichat.qSummarize",
    "aichat.qNeedsReply",
    "aichat.qDraftReply",
    "aichat.qMarkAllRead",
    "aichat.qHowMarkDone",
  ];

  // Human labels for a proposed mailbox action (returned by /ai/agent).
  const OP_VERB = {
    mark_seen: "aichat.opMarkSeen", mark_unseen: "aichat.opMarkUnseen",
    mark_done: "aichat.opMarkDone", mark_undone: "aichat.opMarkUndone",
    flag: "aichat.opFlag", unflag: "aichat.opUnflag", archive: "aichat.opArchive", delete: "aichat.opDelete",
  };
  function filterDesc(f) {
    const p = [];
    if (f.unread) p.push(t("aichat.fUnread"));
    if (f.seen) p.push(t("aichat.fRead"));
    if (f.flagged) p.push(t("aichat.fFlagged"));
    if (f.from) p.push(t("aichat.fFrom", { v: f.from }));
    if (f.subject) p.push(t("aichat.fAbout", { v: f.subject }));
    return p.length ? ` (${p.join(", ")})` : "";
  }
  function actionLabel(a) {
    const verb = OP_VERB[a.op] ? t(OP_VERB[a.op]) : a.op;
    if (!a.count) return t("aichat.nothingMatches", { verb: verb.toLowerCase(), filters: filterDesc(a.filters) });
    const noun = a.count === 1 ? t("aichat.emailOne") : t("aichat.emailN");
    const cap = a.capped ? ` (${t("aichat.firstN", { n: a.ids.length })})` : "";
    return t("aichat.actionQuestion", { verb, count: a.count, noun, filters: filterDesc(a.filters), cap });
  }
  async function runAction(m) {
    const a = m.action;
    if (a.status !== "pending" || !a.ids.length) return;
    a.status = "running"; app.aiBusy = true;
    try {
      await messagesApi.bulk(a.ids, a.action);
      a.status = "done";
      refreshMessages({ background: true });
    } catch (e) {
      a.status = "error"; a.error = e.message || t("aichat.actionFailed");
    } finally { app.aiBusy = false; }
  }
  function cancelAction(m) { if (m.action.status === "pending") m.action.status = "cancelled"; }

  // A proposed filtering RULE from the agent ("automatically mark … done").
  const RULE_FIELD = { from: "aichat.rfSender", from_domain: "aichat.rfSenderDomain", to: "aichat.rfRecipient", subject: "aichat.rfSubject", body: "aichat.rfBody", category: "aichat.rfCategory" };
  const RULE_OP = { contains: "aichat.roContains", equals: "aichat.roEquals", ends_with: "aichat.roEndsWith", regex: "aichat.roRegex" };
  const RULE_ACT = { mark_done: "aichat.raMarkDone", mark_read: "aichat.raMarkRead", archive: "aichat.raArchive", delete: "aichat.raDelete", move: "aichat.raMove", block: "aichat.raBlock", mute_notifications: "aichat.raMute" };
  function ruleLabel(rl) {
    const to = rl.action === "move" && rl.action_arg ? t("aichat.ruleTo", { arg: rl.action_arg }) : "";
    return t("aichat.ruleLabel", {
      field: RULE_FIELD[rl.match_field] ? t(RULE_FIELD[rl.match_field]) : rl.match_field,
      op: RULE_OP[rl.match_op] ? t(RULE_OP[rl.match_op]) : rl.match_op,
      value: rl.match_value,
      action: RULE_ACT[rl.action] ? t(RULE_ACT[rl.action]) : rl.action,
      to,
    });
  }
  const ruleSpec = (rl) => ({ name: rl.name || "", enabled: true, order: 0, account_id: null,
    match_field: rl.match_field, match_op: rl.match_op, match_value: rl.match_value,
    action: rl.action, action_arg: rl.action_arg || "" });
  async function runRule(m) {
    const rl = m.rule;
    if (rl.status !== "pending") return;
    rl.status = "running"; app.aiBusy = true;
    try {
      const spec = ruleSpec(rl);
      await rulesApi.create(spec);
      let applied = 0;
      try { applied = (await rulesApi.apply(spec)).applied || 0; } catch {}
      rl.status = "done"; rl.applied = applied;
      refreshMessages({ background: true });
    } catch (e) {
      rl.status = "error"; rl.error = e.message || t("aichat.ruleCreateFailed");
    } finally { app.aiBusy = false; }
  }
  function cancelRule(m) { if (m.rule.status === "pending") m.rule.status = "cancelled"; }

  function hasCtx(id) { return context.some((c) => c.id === id); }
  function addMsg(m) {
    if (!m || hasCtx(m.id)) return;
    app.aiChatContext = [...app.aiChatContext, { id: m.id, from: m.from_name || m.from_addr || "?", subject: m.subject || t("aichat.noSubject"), date: m.date }];
  }
  function removeCtx(id) { app.aiChatContext = app.aiChatContext.filter((c) => c.id !== id); }

  function addOpen() {
    const m = app.messages.find((x) => x.id === app.selectedMessageId);
    if (m) addMsg(m); else notify(t("aichat.openFirst"), "error");
  }
  async function addThread() {
    const key = app.threadKey || app.aiAssistantSeed?.threadKey || app.aiAssistantSeed?.threadId;
    if (!key) { notify(t("aichat.noConvOpen"), "error"); return; }
    try { (await messagesApi.thread(key)).forEach(addMsg); }
    catch { notify(t("aichat.convLoadFailed"), "error"); }
  }
  function addList() {
    const take = app.messages.slice(0, 25);
    if (!take.length) { notify(t("aichat.listEmpty"), "error"); return; }
    take.forEach(addMsg);
  }

  async function seed() {
    const s = app.aiAssistantSeed;
    if (!s) return;
    // "new" scope: load the unread inbox as context (Home → recap new mail).
    if (s.scope === "new") {
      try { (await messagesApi.list({ role: "inbox", unread_only: true, limit: 30 }) || []).forEach(addMsg); }
      catch {}
    }
    if (s.threadKey || s.threadId) {
      try { (await messagesApi.thread(s.threadKey || s.threadId)).forEach(addMsg); } catch {}
    }
    if (s.messageId) {
      const m = app.messages.find((x) => x.id === s.messageId);
      if (m) addMsg(m);
    }
    // Auto-ask a seeded prompt once context is loaded (e.g. "Shrň nové maily").
    if (s.prompt) send(s.prompt);
  }

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    conv = [...conv, { role: "user", content: q }];
    input = "";
    queueMicrotask(autogrow);   // shrink the textarea back after send
    loading = true; app.aiBusy = true;
    const history = conv.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
    scrollSoon();
    try {
      // The agent both answers questions AND can propose a mailbox action to run.
      const r = await ai.agent({ instruction: q, message_ids: context.map((c) => c.id), history });
      if (r.kind === "action") {
        conv = [...conv, { role: "assistant", content: actionLabel(r),
                           action: { ...r, status: r.count ? "pending" : "empty" } }];
      } else if (r.kind === "rule") {
        // Preview how many EXISTING emails it would touch, so the user can sanity-
        // check the rule (e.g. spot a 0-match / wrong proposal) before creating it.
        let count = null, sample = [];
        try { const p = await rulesApi.preview(ruleSpec(r.rule)); count = p.match_count; sample = p.sample_subjects || []; } catch {}
        conv = [...conv, { role: "assistant", content: ruleLabel(r.rule),
                           rule: { ...r.rule, status: "pending", count, sample } }];
      } else {
        conv = [...conv, { role: "assistant", content: r.answer || t("aichat.noAnswer") }];
      }
    } catch (e) {
      conv = [...conv, { role: "assistant", content: "⚠ " + (e.message || t("aichat.requestFailed")) }];
    } finally {
      loading = false; app.aiBusy = false;
      scrollSoon();
    }
  }
  function scrollSoon() { queueMicrotask(() => { if (scroller) scroller.scrollTop = scroller.scrollHeight; }); }
  // Enter sends; Shift+Enter inserts a newline (so you can write multi-line prompts).
  function onAskKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }
  function clearConv() { conv = []; input = ""; queueMicrotask(autogrow); }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify(t("aichat.copied")); } catch { notify(t("aichat.copyFailed"), "error"); }
  }
  function toCompose(text) {
    openCompose({ to: "", subject: "", html: `<p>${text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>` });
  }
  function openCtx(id) { openMessageById?.(id); }
  function close() {
    app.aiAssistantOpen = false; app.aiAssistantSeed = null; app.aiChatContext = [];
    // Free the GPU right away - closing the assistant means we're done for now.
    if ((app.settings.aiProvider || "") === "ollama") ai.ollamaUnload().catch(() => {});
  }

  onMount(seed);
  onDestroy(() => window.removeEventListener("pointermove", onMove));
</script>

{#if minimized}
  <button class="ai-fab" onclick={() => (minimized = false)} title={t("aichat.title")}>
    {@html icons.bolt}
    {#if conv.length}<span class="fab-badge">{conv.filter((m) => m.role === "assistant").length}</span>{/if}
  </button>
{:else}
  <div class="panel" style={dockStyle} bind:this={panelEl}>
    <header onpointerdown={onHeaderDown}>
      <span class="title">{@html icons.bolt} {t("aichat.title")}</span>
      <div class="hbtns">
        {#if conv.length}<button class="hb" title={t("aichat.clearTip")} onclick={clearConv}>{@html icons.trash || "🗑"}</button>{/if}
        <button class="hb" title={t("aichat.minimizeTip")} onclick={() => (minimized = true)}>-</button>
        <button class="hb" title={t("aichat.close")} onclick={close}>{@html icons.close}</button>
      </div>
    </header>

    <div class="ctx">
      <div class="ctx-add">
        <span class="ctx-lbl">{t("aichat.context")}</span>
        <button class="addbtn" onclick={addOpen}>{t("aichat.addOpen")}</button>
        <button class="addbtn" onclick={addThread}>{t("aichat.addConversation")}</button>
        <button class="addbtn" onclick={addList}>{t("aichat.addList")}</button>
      </div>
      {#if context.length}
        <div class="chips">
          {#each context as c (c.id)}
            <span class="chip" title={c.subject}>
              <button class="chip-open" onclick={() => openCtx(c.id)}>{@html icons.mail} {c.from} - {c.subject}</button>
              <button class="chip-x" title={t("aichat.remove")} onclick={() => removeCtx(c.id)}>{@html icons.close}</button>
            </span>
          {/each}
        </div>
      {:else}
        <p class="ctx-empty">{t("aichat.ctxEmpty")}</p>
      {/if}
    </div>

    <div class="conv" bind:this={scroller}>
      {#if !conv.length}
        <div class="quick">
          {#each QUICK as q}<button class="qchip" onclick={() => send(t(q))}>{t(q)}</button>{/each}
        </div>
      {/if}
      {#each conv as m}
        <div class="turn {m.role}">
          {#if m.action}
            <div class="bubble action">
              <div class="act-head">{@html icons.bolt} {m.content}</div>
              {#if m.action.sample?.length}
                <ul class="act-sample">
                  {#each m.action.sample as s}<li><b>{s.from}</b> - {s.subject || t("aichat.noSubject")}</li>{/each}
                  {#if m.action.count > m.action.sample.length}<li class="more">{t("aichat.andMore", { n: m.action.count - m.action.sample.length })}</li>{/if}
                </ul>
              {/if}
              {#if m.action.status === "pending"}
                <div class="act-btns">
                  <button class="act-go" onclick={() => runAction(m)}>{@html icons.done || ""} {t("aichat.doIt")}</button>
                  <button class="act-no" onclick={() => cancelAction(m)}>{t("aichat.cancel")}</button>
                </div>
              {:else if m.action.status === "running"}
                <div class="act-status">{t("aichat.working")}</div>
              {:else if m.action.status === "done"}
                <div class="act-status ok">{@html icons.done || "✓"} {t("aichat.done")}</div>
              {:else if m.action.status === "cancelled"}
                <div class="act-status">{t("aichat.cancelled")}</div>
              {:else if m.action.status === "error"}
                <div class="act-status err">⚠ {m.action.error}</div>
              {/if}
            </div>
          {:else if m.rule}
            <div class="bubble action">
              <div class="act-head">{@html icons.bolt} {m.content}</div>
              {#if m.rule.count != null}
                <div class="act-affect">
                  {m.rule.count === 0
                    ? t("aichat.ruleNoMatch")
                    : t(m.rule.count === 1 ? "aichat.ruleAffectOne" : "aichat.ruleAffectN", { n: m.rule.count })}
                </div>
                {#if m.rule.sample?.length}
                  <ul class="act-sample">
                    {#each m.rule.sample.slice(0, 4) as s}<li>{s || t("aichat.noSubject")}</li>{/each}
                    {#if m.rule.count > 4}<li class="more">{t("aichat.andMore", { n: m.rule.count - 4 })}</li>{/if}
                  </ul>
                {/if}
              {/if}
              {#if m.rule.status === "pending"}
                <div class="act-btns">
                  <button class="act-go" onclick={() => runRule(m)}>{@html icons.done || ""} {t("aichat.createRule")}</button>
                  <button class="act-no" onclick={() => cancelRule(m)}>{t("aichat.cancel")}</button>
                </div>
              {:else if m.rule.status === "running"}
                <div class="act-status">{t("aichat.creating")}</div>
              {:else if m.rule.status === "done"}
                <div class="act-status ok">{@html icons.done || "✓"} {t("aichat.ruleCreated")}{m.rule.applied ? " · " + t("aichat.appliedExisting", { n: m.rule.applied }) : ""}</div>
              {:else if m.rule.status === "cancelled"}
                <div class="act-status">{t("aichat.cancelled")}</div>
              {:else if m.rule.status === "error"}
                <div class="act-status err">⚠ {m.rule.error}</div>
              {/if}
            </div>
          {:else}
            <div class="bubble">{m.content}</div>
            {#if m.role === "assistant"}
              <div class="turn-actions">
                <button onclick={() => copy(m.content)}>{@html icons.copy || ""} {t("aichat.copy")}</button>
                <button onclick={() => toCompose(m.content)}>{@html icons.compose || ""} {t("aichat.newEmail")}</button>
              </div>
            {/if}
          {/if}
        </div>
      {/each}
      {#if loading}<div class="turn assistant"><div class="bubble thinking">{t("aichat.thinking")}</div></div>{/if}
    </div>

    <footer>
      <textarea class="ask" bind:this={askEl} bind:value={input} rows="1" placeholder={t("aichat.askPh")}
        onkeydown={onAskKey} oninput={autogrow}></textarea>
      <button class="btn primary" onclick={() => send()} disabled={loading || !input.trim()}>{@html icons.sent || ""}</button>
    </footer>
  </div>
{/if}

<style>
  .panel { position: fixed; z-index: 60; width: 400px; height: 560px; display: flex; flex-direction: column;
    background: var(--surface); color: var(--text); border: 1px solid var(--hairline); border-radius: var(--radius);
    box-shadow: var(--shadow-lg); overflow: hidden; resize: both; min-width: 320px; min-height: 360px;
    max-width: 96vw; max-height: 92vh; animation: rise-in var(--t-slow) var(--ease); }
  header { display: flex; align-items: center; gap: 8px; padding: 11px 14px; border-bottom: 1px solid var(--border);
    background: var(--surface-2); cursor: move; user-select: none; }
  .title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; flex: 1; }
  .title :global(svg) { color: var(--accent); width: 16px; height: 16px; }
  .hbtns { display: flex; align-items: center; gap: 2px; }
  .hb { color: var(--muted); font-size: 14px; padding: 3px 8px; border-radius: 6px; display: inline-flex; line-height: 1; }
  .hb:hover { background: var(--surface-3); color: var(--text); }
  .ctx { padding: 10px 14px; border-bottom: 1px solid var(--border); }
  .ctx-add { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .ctx-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); margin-right: 2px; }
  .addbtn { font-size: 11.5px; padding: 3px 9px; border-radius: 999px; border: 1px solid var(--border); color: var(--text); background: var(--surface-2); }
  .addbtn:hover { border-color: var(--accent); color: var(--accent); }
  .chips { display: flex; flex-direction: column; gap: 5px; margin-top: 8px; max-height: 92px; overflow-y: auto; }
  .chip { display: inline-flex; align-items: center; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .chip-open { display: inline-flex; align-items: center; gap: 6px; padding: 5px 4px 5px 9px; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .chip-open :global(svg) { width: 12px; height: 12px; color: var(--muted); flex: none; }
  .chip-open:hover { color: var(--accent); }
  .chip-x { padding: 5px 8px; color: var(--muted); display: inline-flex; flex: none; }
  .chip-x:hover { color: var(--danger); }
  .ctx-empty { margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
  .conv { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  .quick { display: flex; flex-wrap: wrap; gap: 7px; }
  .qchip { font-size: 12.5px; padding: 6px 11px; border-radius: 999px; border: 1px solid var(--border); color: var(--text); background: var(--surface); text-align: left; }
  .qchip:hover { border-color: var(--accent); color: var(--accent); }
  .turn { display: flex; flex-direction: column; gap: 4px; max-width: 90%; }
  .turn.user { align-self: flex-end; align-items: flex-end; }
  .turn.assistant { align-self: flex-start; }
  .bubble { padding: 9px 12px; border-radius: 13px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .turn.user .bubble { background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
  .turn.assistant .bubble { background: var(--surface-2); color: var(--text); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .bubble.thinking { color: var(--muted); font-style: italic; }
  /* Proposed mailbox action (confirm before it runs). */
  .bubble.action { background: color-mix(in srgb, var(--accent) 8%, var(--surface)); border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border)); display: flex; flex-direction: column; gap: 8px; }
  .act-head { display: flex; align-items: center; gap: 7px; font-weight: 600; font-size: 13px; }
  .act-head :global(svg) { width: 14px; height: 14px; color: var(--accent); flex: none; }
  .act-affect { font-size: 12.5px; color: var(--text); }
  .act-sample { margin: 0; padding-left: 2px; list-style: none; display: flex; flex-direction: column; gap: 3px; }
  .act-sample li { font-size: 11.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .act-sample li b { color: var(--text); font-weight: 600; }
  .act-sample li.more { color: var(--faint); font-style: italic; }
  .act-btns { display: flex; gap: 8px; margin-top: 2px; }
  .act-go { display: inline-flex; align-items: center; gap: 5px; background: var(--accent); color: #fff; font-weight: 600; font-size: 12.5px; padding: 6px 14px; border-radius: 999px; }
  .act-go :global(svg) { width: 13px; height: 13px; }
  .act-go:hover { filter: brightness(1.08); }
  .act-no { font-size: 12.5px; color: var(--muted); padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); }
  .act-no:hover { color: var(--text); border-color: var(--muted); }
  .act-status { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 600; color: var(--muted); }
  .act-status :global(svg) { width: 13px; height: 13px; }
  .act-status.ok { color: var(--done); }
  .act-status.err { color: var(--danger); }
  .turn-actions { display: flex; gap: 6px; }
  .turn-actions button { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); padding: 2px 6px; border-radius: 6px; }
  .turn-actions button:hover { color: var(--accent); background: var(--surface-2); }
  .turn-actions :global(svg) { width: 12px; height: 12px; }
  footer { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--border); align-items: flex-end; }
  .ask { flex: 1; background: var(--surface-2); border: 1px solid var(--border); border-radius: 16px; padding: 8px 13px;
    color: var(--text); font-size: 13px; font-family: inherit; line-height: 1.4; resize: none; max-height: 140px; min-height: 20px; }
  .ask:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent); }
  .btn.primary { display: inline-flex; align-items: center; justify-content: center; background: var(--accent); color: #fff; width: 40px; border-radius: 999px; }
  .btn.primary:disabled { opacity: 0.5; }
  .btn.primary :global(svg) { width: 15px; height: 15px; }
  /* Minimized: floating AI circle */
  .ai-fab { position: fixed; right: 24px; bottom: 24px; z-index: 60; width: 52px; height: 52px; border-radius: 50%;
    background: var(--accent); color: #fff; display: grid; place-items: center; box-shadow: var(--shadow-lg);
    animation: pop-in var(--t) var(--ease); }
  .ai-fab:hover { filter: brightness(1.08); transform: translateY(-1px); }
  .ai-fab :global(svg) { width: 24px; height: 24px; }
  .fab-badge { position: absolute; top: -2px; right: -2px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 999px;
    background: var(--surface); color: var(--accent); border: 1px solid var(--accent); font-size: 11px; font-weight: 700;
    display: grid; place-items: center; }
</style>
