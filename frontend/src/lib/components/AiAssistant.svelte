<script>
  import { onMount, onDestroy } from "svelte";
  import { app, notify, openCompose, openMessageById } from "../store.svelte.js";
  import { ai, messages as messagesApi } from "../api.js";
  import { icons } from "../icons.js";

  // A NON-modal, docked chat window (like the compose panel): you keep clicking
  // and reading the app while it's open, drag it around, and can minimize it into
  // a floating "AI" circle that reopens it (conversation preserved). It answers
  // over emails you add as CONTEXT — the open message, a whole conversation, or
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

  const QUICK = [
    "Summarize this",
    "What needs a reply?",
    "Draft a reply",
    "Extract action items & deadlines",
    "List the key facts and decisions",
  ];

  function hasCtx(id) { return context.some((c) => c.id === id); }
  function addMsg(m) {
    if (!m || hasCtx(m.id)) return;
    app.aiChatContext = [...app.aiChatContext, { id: m.id, from: m.from_name || m.from_addr || "?", subject: m.subject || "(no subject)", date: m.date }];
  }
  function removeCtx(id) { app.aiChatContext = app.aiChatContext.filter((c) => c.id !== id); }

  function addOpen() {
    const m = app.messages.find((x) => x.id === app.selectedMessageId);
    if (m) addMsg(m); else notify("Open a message first", "error");
  }
  async function addThread() {
    const key = app.threadKey || app.aiAssistantSeed?.threadKey || app.aiAssistantSeed?.threadId;
    if (!key) { notify("No conversation open", "error"); return; }
    try { (await messagesApi.thread(key)).forEach(addMsg); }
    catch { notify("Couldn't load the conversation", "error"); }
  }
  function addList() {
    const take = app.messages.slice(0, 25);
    if (!take.length) { notify("The list is empty", "error"); return; }
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
      const r = await ai.ask({ instruction: q, message_ids: context.map((c) => c.id), history });
      conv = [...conv, { role: "assistant", content: r.answer || "(no answer)" }];
    } catch (e) {
      conv = [...conv, { role: "assistant", content: "⚠ " + (e.message || "AI request failed") }];
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
    try { await navigator.clipboard.writeText(text); notify("Copied"); } catch { notify("Couldn't copy", "error"); }
  }
  function toCompose(text) {
    openCompose({ to: "", subject: "", html: `<p>${text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>` });
  }
  function openCtx(id) { openMessageById?.(id); }
  function close() {
    app.aiAssistantOpen = false; app.aiAssistantSeed = null; app.aiChatContext = [];
    // Free the GPU right away — closing the assistant means we're done for now.
    if ((app.settings.aiProvider || "") === "ollama") ai.ollamaUnload().catch(() => {});
  }

  onMount(seed);
  onDestroy(() => window.removeEventListener("pointermove", onMove));
</script>

{#if minimized}
  <button class="ai-fab" onclick={() => (minimized = false)} title="AI assistant">
    {@html icons.bolt}
    {#if conv.length}<span class="fab-badge">{conv.filter((m) => m.role === "assistant").length}</span>{/if}
  </button>
{:else}
  <div class="panel" style={dockStyle} bind:this={panelEl}>
    <header onpointerdown={onHeaderDown}>
      <span class="title">{@html icons.bolt} AI assistant</span>
      <div class="hbtns">
        {#if conv.length}<button class="hb" title="Clear the conversation (start fresh)" onclick={clearConv}>{@html icons.trash || "🗑"}</button>{/if}
        <button class="hb" title="Minimize to a circle" onclick={() => (minimized = true)}>–</button>
        <button class="hb" title="Close" onclick={close}>{@html icons.close}</button>
      </div>
    </header>

    <div class="ctx">
      <div class="ctx-add">
        <span class="ctx-lbl">Context</span>
        <button class="addbtn" onclick={addOpen}>＋ Open</button>
        <button class="addbtn" onclick={addThread}>＋ Conversation</button>
        <button class="addbtn" onclick={addList}>＋ List</button>
      </div>
      {#if context.length}
        <div class="chips">
          {#each context as c (c.id)}
            <span class="chip" title={c.subject}>
              <button class="chip-open" onclick={() => openCtx(c.id)}>{@html icons.mail} {c.from} — {c.subject}</button>
              <button class="chip-x" title="Remove" onclick={() => removeCtx(c.id)}>{@html icons.close}</button>
            </span>
          {/each}
        </div>
      {:else}
        <p class="ctx-empty">Add emails as context — the open message, a whole conversation, or the current list — then ask. (General questions work with no context too.)</p>
      {/if}
    </div>

    <div class="conv" bind:this={scroller}>
      {#if !conv.length}
        <div class="quick">
          {#each QUICK as q}<button class="qchip" onclick={() => send(q)}>{q}</button>{/each}
        </div>
      {/if}
      {#each conv as m}
        <div class="turn {m.role}">
          <div class="bubble">{m.content}</div>
          {#if m.role === "assistant"}
            <div class="turn-actions">
              <button onclick={() => copy(m.content)}>{@html icons.copy || ""} Copy</button>
              <button onclick={() => toCompose(m.content)}>{@html icons.compose || ""} New email</button>
            </div>
          {/if}
        </div>
      {/each}
      {#if loading}<div class="turn assistant"><div class="bubble thinking">Thinking…</div></div>{/if}
    </div>

    <footer>
      <textarea class="ask" bind:this={askEl} bind:value={input} rows="1" placeholder="Ask…  (Enter to send · Shift+Enter for a new line)"
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
