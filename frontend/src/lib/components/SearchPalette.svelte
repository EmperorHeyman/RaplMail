<script>
  // A SOLID, non-fragile search window - built like the compose / AI windows:
  // a floating, draggable, resizable panel that only closes on an explicit
  // action (Esc, the X, running a search, or opening a result). It never closes
  // on an outside click, and it KEEPS whatever you typed across close/reopen, so
  // an accidental click can't lose your query.
  //
  // Query building uses "operator chips": typing `from:` turns into a from chip
  // and the suggestions become matching contacts, so `from: apa` proposes
  // apavlik's addresses. Free text and chips together make the operator query
  // the bar + backend already understand.
  import { untrack, onDestroy } from "svelte";
  import { fly, fade } from "svelte/transition";
  import { messages as messagesApi, contacts as contactsApi, ai } from "../api.js";
  import { app, aiEnabled } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { relativeTime } from "../time.js";
  import { OPERATORS, smartSplit, isOp, opParts, normalizeChips, buildQuery, parseQuery } from "../searchQuery.js";

  let { open = false, initial = "", smartAvailable = false,
        onclose, onsearch, onsemantic, onopen } = $props();

  const VALUE_OPS = new Set(["from:", "to:", "cc:", "subject:"]);
  const CONTACT_OPS = new Set(["from:", "to:", "cc:"]);

  // --- query state (persists across open/close - the component isn't destroyed) --
  let chips = $state([]);        // completed operator chips: from:x, is:unread …
  let pendingOp = $state("");    // a value operator being filled: "from:" / ""
  let text = $state("");         // input contents: the pending value, or free text
  let smart = $state(false);
  let inputEl;

  let sugg = $state([]);         // left-column suggestions (contacts or operators)
  let suggActive = $state(-1);
  let contactCache = [];

  let results = $state([]);
  let loading = $state(false);
  let resultActive = $state(-1);
  let recent = $state([]);
  let searchTimer;

  const RECENT_KEY = "raplmail:recentSearches";

  // The pending operator only contributes to the query once it has a value.
  const pendingChip = $derived(pendingOp && text.trim()
    ? pendingOp + (/\s/.test(text.trim()) ? `"${text.trim().replace(/"/g, "")}"` : text.trim())
    : "");
  const query = $derived(pendingOp
    ? buildQuery([...chips, pendingChip].filter(Boolean), "")
    : buildQuery(chips, text));
  const hasDraft = () => !!(chips.length || pendingOp || text.trim());

  function loadRecent() {
    try { recent = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]") || []; } catch { recent = []; }
  }
  function pushRecent(q) {
    q = (q || "").trim();
    if (!q) return;
    const next = [q, ...recent.filter((r) => r !== q)].slice(0, 8);
    recent = next;
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch {}
  }

  // Seed from the bar ONLY when opening with an empty draft - otherwise keep what
  // the user already had (so reopening never wipes their in-progress query). Only
  // `open`/`initial` are tracked; the seeding reads/writes state untracked so it
  // can't re-run on every keystroke (that bug made the palette impossible to type
  // into).
  let _wasOpen = false;
  $effect(() => {
    const isOpen = open;
    const init = initial;
    if (isOpen && !_wasOpen) {
      untrack(() => {
        if (!hasDraft() && (init || "").trim()) {
          const p = parseQuery(init);
          chips = p.chips; text = p.text; pendingOp = ""; smart = false;
        }
        loadRecent();
        recompute();
        fetchResults();
        queueMicrotask(() => inputEl?.focus());
      });
    }
    _wasOpen = isOpen;
  });

  // --- suggestions ----------------------------------------------------------
  async function recompute() {
    if (pendingOp && CONTACT_OPS.has(pendingOp)) {
      const q = text.trim().toLowerCase();
      if (!contactCache.length) { try { contactCache = (await contactsApi.list()) || []; } catch {} }
      const pool = q
        ? contactCache.filter((c) => `${c.name || ""} ${c.email || ""}`.toLowerCase().includes(q))
        : contactCache;
      sugg = pool.filter((c) => c.email).slice(0, 8)
        .map((c) => ({ kind: "contact", label: c.name || c.email, sub: c.email, value: c.email }));
    } else if (pendingOp) {
      sugg = [];   // subject: - free value, nothing to suggest
    } else {
      const cur = (text.trim().split(/\s+/).pop() || "").toLowerCase();
      sugg = OPERATORS.filter((o) => !cur || o.token.toLowerCase().startsWith(cur))
        .map((o) => ({ kind: "op", label: o.token, sub: o.hint, token: o.token, value: !!o.value }));
    }
    suggActive = -1;
  }

  // --- input handling -------------------------------------------------------
  function onInput(e) {
    let v = e.currentTarget.value;
    // Starting a value operator ("from:", "to: apa", …) opens a pending chip.
    if (!pendingOp) {
      const m = /^\s*(from|to|cc|subject):(.*)$/i.exec(v);
      if (m) {
        pendingOp = m[1].toLowerCase() + ":";
        text = m[2].replace(/^\s+/, "");
        recompute(); if (!smart) scheduleFetch();
        return;
      }
    }
    text = v;
    // A completed operator typed inline + space becomes a chip (e.g. "is:unread ").
    if (!pendingOp && /\s$/.test(v)) {
      const toks = smartSplit(v.trim());
      const last = toks[toks.length - 1];
      if (last && isOp(last) && !/^(from|to|cc|subject):$/i.test(last)) {
        chips = normalizeChips([...chips, last]);
        text = toks.slice(0, -1).join(" ");
        if (text) text += " ";
      }
    }
    recompute();
    if (!smart) scheduleFetch();
  }

  function commitPending(value) {
    if (!pendingOp) return false;
    const v = (value ?? text).trim();
    if (!v) { pendingOp = ""; text = ""; recompute(); return true; }
    const val = /\s/.test(v) ? `"${v.replace(/"/g, "")}"` : v;
    chips = normalizeChips([...chips, pendingOp + val]);
    pendingOp = ""; text = "";
    recompute(); if (!smart) scheduleFetch();
    return true;
  }

  function applySugg(s) {
    if (s.kind === "contact") commitPending(s.value);
    else if (s.value) { pendingOp = s.token; text = ""; recompute(); }
    else { chips = normalizeChips([...chips, s.token]); text = ""; recompute(); if (!smart) scheduleFetch(); }
    inputEl?.focus();
  }

  function toggleChip(token) {
    const has = chips.some((c) => c.toLowerCase() === token.toLowerCase());
    chips = has ? chips.filter((c) => c.toLowerCase() !== token.toLowerCase())
                : normalizeChips([...chips, token]);
    inputEl?.focus();
    if (!smart) scheduleFetch();
  }
  function removeChip(i) { chips = chips.filter((_, j) => j !== i); if (!smart) scheduleFetch(); }
  function clearAll() { chips = []; text = ""; pendingOp = ""; results = []; recompute(); inputEl?.focus(); }
  const chipActive = (token) => chips.some((c) => c.toLowerCase() === token.toLowerCase());

  // --- live results ---------------------------------------------------------
  function scheduleFetch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchResults, 200);
  }
  let fetchSeq = 0;
  async function fetchResults() {
    const q = query.trim();
    if (smart) { results = []; return; }   // smart runs explicitly, see runSmart()
    if (!q) { results = []; loading = false; return; }
    const seq = ++fetchSeq;
    loading = true;
    try {
      const list = await messagesApi.list({ q, limit: 40 });
      if (seq !== fetchSeq) return;
      results = Array.isArray(list) ? list : [];
      resultActive = -1;
    } catch { if (seq === fetchSeq) results = []; }
    finally { if (seq === fetchSeq) loading = false; }
  }

  // Smart (meaning-based) search runs on demand - it's expensive (embeddings / an
  // AI call), so never per keystroke. Results show IN the panel, same as keyword
  // mode. Pipeline mirrors the store: local embeddings → AI keyword extraction →
  // plain keyword, so you always get *something* rather than an empty close.
  async function runSmart() {
    const q = query.trim();
    if (!q) return;
    pushRecent(q);
    const seq = ++fetchSeq;
    loading = true; results = [];
    try {
      let list = [];
      if (app.settings?.semanticEnabled) {
        try { list = (await ai.semantic(q, 60)) || []; } catch {}
      }
      if (!list.length && aiEnabled()) {
        try { const r = await ai.search(q); if (r?.query) list = (await messagesApi.list({ q: r.query, limit: 40 })) || []; } catch {}
      }
      if (!list.length) {
        try { list = (await messagesApi.list({ q, limit: 40 })) || []; } catch {}
      }
      if (seq !== fetchSeq) return;
      results = Array.isArray(list) ? list : [];
      resultActive = -1;
    } finally { if (seq === fetchSeq) loading = false; }
  }

  // --- actions --------------------------------------------------------------
  function close() { onclose?.(); }
  function commit() {
    if (pendingOp && text.trim()) commitPending();
    const q = query.trim();
    // Smart search shows results IN the panel (doesn't close) - you pick a result
    // to open, or Esc/X to dismiss. Keyword search applies to the inbox + closes.
    if (smart) { if (q) runSmart(); return; }
    pushRecent(q);
    onsearch?.(q);
    close();
  }
  function pickRecent(q) {
    const p = parseQuery(q);
    chips = p.chips; text = p.text; pendingOp = ""; smart = false;
    recompute(); fetchResults(); inputEl?.focus();
  }
  function openResult(msg) {
    if (!msg) return;
    if (pendingOp && text.trim()) commitPending();
    const q = query.trim();
    pushRecent(q);
    // Leave the inbox filtered behind the opened mail - by meaning for smart mode,
    // by keyword otherwise.
    if (smart) onsemantic?.(q); else onsearch?.(q);
    onopen?.(msg);
    close();
  }
  function setSmart(v) {
    smart = v;
    results = []; resultActive = -1;
    if (!smart) fetchResults();   // keyword mode previews live; smart waits for Enter
    inputEl?.focus();
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key === "Backspace" && text === "" && document.activeElement === inputEl) {
      if (pendingOp) { pendingOp = ""; recompute(); e.preventDefault(); return; }
      if (chips.length) {
        const last = chips[chips.length - 1];
        chips = chips.slice(0, -1);
        const [op, val] = opParts(last);
        if (val && VALUE_OPS.has(op)) { pendingOp = op; text = val.replace(/^"|"$/g, ""); }
        recompute(); scheduleFetch(); e.preventDefault(); return;
      }
    }
    const contactMode = pendingOp && CONTACT_OPS.has(pendingOp) && sugg.length;
    if (e.key === "Tab" && pendingOp) {
      e.preventDefault();
      if (contactMode) applySugg(sugg[suggActive >= 0 ? suggActive : 0]);
      else if (text.trim()) commitPending();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (contactMode) suggActive = (suggActive + 1) % sugg.length;
      else if (results.length) { resultActive = (resultActive + 1) % results.length; scrollActive(); }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (contactMode) suggActive = (suggActive - 1 + sugg.length) % sugg.length;
      else if (results.length) { resultActive = (resultActive - 1 + results.length) % results.length; scrollActive(); }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (contactMode && suggActive >= 0) { applySugg(sugg[suggActive]); return; }
      if (pendingOp && text.trim()) { commitPending(); return; }   // lock the operator first
      if (resultActive >= 0 && results[resultActive]) { openResult(results[resultActive]); return; }
      commit();
    }
  }

  let resultsEl;
  function scrollActive() {
    queueMicrotask(() => resultsEl?.children?.[resultActive]?.scrollIntoView({ block: "nearest" }));
  }

  // --- drag + resize (same pattern as the compose / AI windows) -------------
  let panelEl;
  let dragPos = $state(null);
  let dragging = false, ox = 0, oy = 0;
  let panelW = $state(null), panelH = $state(null);
  $effect(() => {
    if (!open || !panelEl) return;
    const ro = new ResizeObserver(() => { panelW = panelEl.offsetWidth; panelH = panelEl.offsetHeight; });
    ro.observe(panelEl);
    return () => ro.disconnect();
  });
  const dockStyle = $derived(
    (dragPos ? `left:${dragPos.x}px; top:${dragPos.y}px;` : "")
    + (panelW ? ` width:${panelW}px; height:${panelH}px;` : ""));
  function onHeaderDown(e) {
    if (e.target.closest("button")) return;
    dragging = true;
    const r = panelEl.getBoundingClientRect();
    ox = e.clientX - r.left; oy = e.clientY - r.top;
    if (!dragPos) dragPos = { x: r.left, y: r.top };   // pin current spot before dragging
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stopDrag, { once: true });
  }
  function onMove(e) {
    if (!dragging) return;
    dragPos = { x: Math.max(0, Math.min(window.innerWidth - 240, e.clientX - ox)),
                y: Math.max(0, Math.min(window.innerHeight - 60, e.clientY - oy)) };
  }
  function stopDrag() { dragging = false; window.removeEventListener("pointermove", onMove); }
  onDestroy(() => window.removeEventListener("pointermove", onMove));

  const fromLabel = (m) => m.from_name || m.from_addr || "";
  const placeholder = $derived(
    pendingOp && CONTACT_OPS.has(pendingOp) ? t("palette.contactsHint") :
    pendingOp === "subject:" ? t("palette.subjectHint") :
    chips.length ? "" : t("palette.placeholder"));
</script>

{#if open}
  <!-- Non-closing scrim: focuses the window and blocks stray clicks on the app
       behind, but clicking it does NOTHING (no accidental close). -->
  <div class="scrim" transition:fade={{ duration: 110 }}></div>
  <div class="palette" class:dragged={!!dragPos} style={dockStyle} bind:this={panelEl}
    transition:fly={{ y: -14, duration: 160 }} role="dialog" aria-modal="false" tabindex="-1"
    onkeydown={(e) => { onKey(e); e.stopPropagation(); }}>

    <header onpointerdown={onHeaderDown}>
      <span class="title">{@html icons.search} {t("palette.title")}</span>
      {#if smartAvailable}
        <div class="modeseg" role="tablist">
          <button class:on={!smart} onclick={() => setSmart(false)}>{t("search.modeKeyword")}</button>
          <button class:on={smart} onclick={() => setSmart(true)}>✨ {t("search.modeSmart")}</button>
        </div>
      {/if}
      <button class="hb" title={t("search.close")} onclick={close}>{@html icons.close}</button>
    </header>

    <!-- Query field: the whole bar is the styled input; chips + a pending chip
         live inside it alongside the text cursor. -->
    <div class="field">
      <span class="ic">{@html icons.search}</span>
      {#each chips as c, i}
        {@const [op, val] = opParts(c)}
        <span class="chip"><span class="op">{op}</span><span class="val">{val}</span>
          <button class="x" title={t("search.close")} onmousedown={(e) => { e.preventDefault(); removeChip(i); }}>{@html icons.close}</button>
        </span>
      {/each}
      {#if pendingOp}
        <span class="chip pending"><span class="op">{pendingOp}</span></span>
      {/if}
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:this={inputEl} class="qinput" type="text" autofocus autocomplete="off"
        placeholder={placeholder} value={text} oninput={onInput} />
      {#if hasDraft()}
        <button class="clear" title={t("search.clear")} onmousedown={(e) => { e.preventDefault(); clearAll(); }}>{@html icons.close}</button>
      {/if}
    </div>

    <div class="cols">
      <div class="side">
        {#if sugg.length}
          <div class="grp">
            <div class="ghead">{pendingOp && CONTACT_OPS.has(pendingOp) ? t("palette.contacts") : t("palette.suggestions")}</div>
            {#each sugg as s, i}
              <button class="srow" class:active={i === suggActive}
                onmouseenter={() => (suggActive = i)} onclick={() => applySugg(s)}>
                <span class="s-label">{s.label}</span>
                {#if s.sub}<span class="s-sub">{s.sub}</span>{/if}
              </button>
            {/each}
          </div>
        {/if}

        <div class="grp">
          <div class="ghead">{t("palette.filters")}</div>
          <div class="pills">
            <button class="pill" class:on={chipActive("is:unread")} onclick={() => toggleChip("is:unread")}>{t("search.stUnread")}</button>
            <button class="pill" class:on={chipActive("is:read")} onclick={() => toggleChip("is:read")}>{t("search.stRead")}</button>
            <button class="pill" class:on={chipActive("is:flagged")} onclick={() => toggleChip("is:flagged")}>{t("search.stFlagged")}</button>
            <button class="pill" class:on={chipActive("is:done")} onclick={() => toggleChip("is:done")}>{t("search.stDone")}</button>
            <button class="pill" class:on={chipActive("has:attachment")} onclick={() => toggleChip("has:attachment")}>{t("search.hasAttachment")}</button>
          </div>
        </div>

        {#if recent.length}
          <div class="grp">
            <div class="ghead">{t("palette.recent")}</div>
            {#each recent as r}
              <button class="srow recent" onclick={() => pickRecent(r)} title={r}>
                <span class="ric">{@html icons.search}</span><span class="rq">{r}</span>
              </button>
            {/each}
          </div>
        {/if}

        <div class="grp help">
          <div class="ghead">{t("palette.help")}</div>
          <ul>
            <li><code>from:</code> · <code>to:</code> · <code>cc:</code></li>
            <li><code>subject:</code> <span>{t("palette.helpSubject")}</span></li>
            <li><code>has:attachment</code></li>
            <li><code>is:unread</code> · <code>is:done</code></li>
            <li><code>/regex/</code> <span>{t("palette.helpRegex")}</span></li>
          </ul>
        </div>
      </div>

      <div class="main">
        {#if loading && !results.length}
          <div class="empty"><p>{t("palette.searching")}</p></div>
        {:else if !results.length && smart}
          <div class="empty">
            <span class="smartbadge">✨ {t("search.modeSmart")}</span>
            <p>{t("palette.smartHint")}</p>
          </div>
        {:else if !results.length && !query.trim()}
          <div class="empty"><p>{t("palette.startHint")}</p></div>
        {:else if !results.length}
          <div class="empty"><p>{t("palette.noResults")}</p></div>
        {:else}
          <div class="rescount">{t("palette.resultsCount", { n: results.length })}{results.length >= 40 ? "+" : ""}</div>
          <div class="results" bind:this={resultsEl}>
            {#each results as m, i (m.id)}
              <button class="res" class:active={i === resultActive}
                onmouseenter={() => (resultActive = i)} onclick={() => openResult(m)}>
                <div class="res-top">
                  <span class="res-from" class:unread={!m.is_seen}>{fromLabel(m)}</span>
                  <span class="res-date">{m.date ? relativeTime(m.date) : ""}</span>
                </div>
                <div class="res-subj" class:unread={!m.is_seen}>
                  {#if m.has_attachments}<span class="clip">{@html icons.paperclip || ""}</span>{/if}
                  {m.subject || t("palette.noSubject")}
                </div>
                {#if m.snippet}<div class="res-snip">{m.snippet}</div>{/if}
              </button>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    <footer class="foot">
      <code class="qprev" title={query}>{query || t("search.everything")}</code>
      <span class="spacer"></span>
      <span class="kbd-hint">{t("palette.kbdHint")}</span>
      <button class="btn primary" onclick={commit}>{@html icons.search} {smart ? t("search.smartSearch") : t("search.search")}</button>
    </footer>
  </div>
{/if}

<style>
  .scrim { position: fixed; inset: 0; background: rgba(0,0,0,0.32); z-index: 210; }
  .palette { position: fixed; left: 50%; top: 7vh; transform: translateX(-50%);
    width: min(760px, 94vw); height: min(620px, 82vh); z-index: 211;
    display: flex; flex-direction: column; background: var(--surface);
    border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 4px); box-shadow: var(--shadow-lg);
    overflow: hidden; resize: both; min-width: 420px; min-height: 380px; max-width: 96vw; max-height: 90vh; }
  .palette.dragged { transform: none; }

  /* Header doubles as the drag handle (like compose / AI). */
  header { display: flex; align-items: center; gap: 10px; padding: 10px 12px 10px 14px;
    border-bottom: 1px solid var(--hairline); background: var(--surface-2); cursor: move; user-select: none; }
  .title { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; flex: 1; }
  .title :global(svg) { width: 15px; height: 15px; color: var(--accent); }
  .hb { color: var(--muted); display: inline-flex; padding: 5px; border-radius: 7px; }
  .hb:hover { color: var(--text); background: var(--surface-3); }
  .modeseg { display: inline-flex; gap: 2px; background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 2px; }
  .modeseg button { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; color: var(--muted); }
  .modeseg button.on { background: var(--accent); color: #fff; }

  /* The query field - a real, styled input surface (chips + text inside it). */
  .field { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 12px 14px 0;
    padding: 9px 10px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px;
    transition: border-color var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease); }
  .field:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
  .field .ic { color: var(--muted); display: inline-flex; flex: none; }
  .field .ic :global(svg) { width: 16px; height: 16px; }
  .qinput { flex: 1; min-width: 160px; border: none; background: transparent; padding: 3px 2px; outline: none;
    font-size: 15px; color: var(--text); }
  .chip { display: inline-flex; align-items: center; gap: 2px; background: var(--accent); color: #fff; border-radius: 7px;
    padding: 3px 4px 3px 8px; font-size: 12.5px; max-width: 280px; }
  .chip .op { opacity: 0.82; } .chip .val { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip .x { color: #fff; opacity: 0.85; display: inline-flex; padding: 1px; }
  .chip .x:hover { opacity: 1; }
  .chip.pending { background: color-mix(in srgb, var(--accent) 22%, var(--surface)); color: var(--accent);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent); padding: 3px 9px; }
  .chip.pending .op { opacity: 1; font-weight: 600; }
  .clear { color: var(--muted); display: inline-flex; padding: 3px; border-radius: 50%; flex: none; margin-left: auto; }
  .clear:hover { color: var(--text); background: var(--surface-3); }

  .cols { display: flex; min-height: 0; flex: 1; margin-top: 12px; border-top: 1px solid var(--hairline); }
  .side { width: 236px; flex: none; border-right: 1px solid var(--hairline); overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 14px; }
  .grp { display: flex; flex-direction: column; gap: 3px; }
  .ghead { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); padding: 0 4px 3px; }
  .srow { display: flex; align-items: baseline; gap: 8px; padding: 6px 9px; border-radius: 7px; text-align: left; width: 100%; }
  .srow:hover, .srow.active { background: var(--surface-2); }
  .srow.active { box-shadow: inset 2px 0 0 var(--accent); }
  .s-label { font-weight: 600; font-size: 12.5px; }
  .s-sub { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .srow.recent { align-items: center; gap: 7px; }
  .ric { color: var(--faint); display: inline-flex; }
  .ric :global(svg) { width: 13px; height: 13px; }
  .rq { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pills { display: flex; flex-wrap: wrap; gap: 5px; padding: 2px 4px; }
  .pill { font-size: 12px; padding: 4px 10px; border-radius: 999px; background: var(--surface-2); color: var(--muted); border: 1px solid transparent; }
  .pill:hover { color: var(--text); }
  .pill.on { background: var(--accent); color: #fff; }
  .help ul { margin: 0; padding: 0 4px; list-style: none; display: flex; flex-direction: column; gap: 5px; }
  .help li { font-size: 12px; color: var(--muted); }
  .help code { font-family: ui-monospace, monospace; font-size: 11.5px; background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  .help span { font-size: 11.5px; }

  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
  .rescount { padding: 8px 14px 4px; font-size: 11px; color: var(--faint); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
  .results { flex: 1; overflow-y: auto; padding: 4px 8px 8px; display: flex; flex-direction: column; gap: 2px; }
  .res { display: flex; flex-direction: column; gap: 2px; padding: 8px 11px; border-radius: 8px; text-align: left; width: 100%; }
  .res:hover, .res.active { background: var(--surface-2); }
  .res-top { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
  .res-from { font-size: 12.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .res-from.unread { color: var(--text); font-weight: 600; }
  .res-date { font-size: 11.5px; color: var(--faint); flex: none; }
  .res-subj { font-size: 13.5px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: flex; align-items: center; gap: 5px; }
  .res-subj.unread { font-weight: 650; }
  .clip { color: var(--faint); display: inline-flex; }
  .clip :global(svg) { width: 12px; height: 12px; }
  .res-snip { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--muted); padding: 40px 20px; text-align: center; }
  .empty p { margin: 0; font-size: 13px; max-width: 360px; line-height: 1.5; }
  .smartbadge { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 3px 9px; border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); }

  .foot { display: flex; align-items: center; gap: 10px; padding: 11px 14px; border-top: 1px solid var(--hairline); background: var(--surface-2); }
  .qprev { font-size: 11.5px; font-family: ui-monospace, monospace; color: var(--muted); background: var(--surface); border: 1px solid var(--border);
    padding: 4px 9px; border-radius: 6px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .spacer { flex: 1; }
  .kbd-hint { font-size: 11.5px; color: var(--faint); }
  .btn.primary { padding: 8px 14px; border-radius: var(--radius-sm); background: var(--accent); color: #fff; font-size: 13px; font-weight: 550; display: inline-flex; align-items: center; gap: 6px; }
  .btn.primary:hover { background: color-mix(in srgb, var(--accent) 88%, #000); }
  .btn.primary :global(svg) { width: 15px; height: 15px; }

  @media (max-width: 640px) {
    .side { display: none; }
    .palette { width: 96vw; min-width: 0; }
  }
</style>
