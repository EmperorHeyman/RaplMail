<script>
  // A full-screen search palette that opens when you focus the search box: a
  // query builder (chips + typing) with smart suggestions, quick filters, recent
  // searches and a help legend on the left, and LIVE results on the right you can
  // arrow through and open. Picking a result opens the mail but leaves the query
  // in the box and the list filtered — so the palette is a fast way in, not a
  // separate place. Reads/writes the same operator query the bar + backend use.
  import { fly, fade } from "svelte/transition";
  import { messages as messagesApi, contacts as contactsApi } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { relativeTime } from "../time.js";
  import { OPERATORS, smartSplit, isOp, opParts, normalizeChips, buildQuery } from "../searchQuery.js";

  let { open = false, initial = "", smartAvailable = false,
        onclose, onsearch, onsemantic, onopen } = $props();

  let chips = $state([]);
  let text = $state("");
  let smart = $state(false);
  let inputEl;
  let sugg = $state([]);
  let contactCache = [];

  let results = $state([]);
  let loading = $state(false);
  let resultActive = $state(-1);
  let recent = $state([]);
  let searchTimer;

  const RECENT_KEY = "raplmail:recentSearches";
  const query = $derived(buildQuery(chips, text));

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

  // Reflect the current bar contents each time the palette opens, focus the input.
  $effect(() => {
    if (!open) return;
    const tokens = smartSplit(initial);
    chips = normalizeChips(tokens.filter(isOp));
    text = tokens.filter((tk) => !isOp(tk)).join(" ");
    smart = false;
    resultActive = -1;
    loadRecent();
    recompute();
    fetchResults();
    queueMicrotask(() => inputEl?.focus());
  });

  // --- query building -------------------------------------------------------
  function currentWord() {
    const i = text.lastIndexOf(" ");
    return i < 0 ? text : text.slice(i + 1);
  }
  function setCurrentWord(w) {
    const i = text.lastIndexOf(" ");
    text = (i < 0 ? "" : text.slice(0, i + 1)) + w;
  }
  function chipLastWordIfComplete() {
    const tokens = smartSplit(text);
    const last = tokens[tokens.length - 1];
    if (last && isOp(last)) { chips = normalizeChips([...chips, last]); text = tokens.slice(0, -1).join(" "); }
  }

  async function recompute() {
    const w = currentWord();
    const m = /^(from|to|cc):(.*)$/i.exec(w);
    if (m) {
      const q = m[2];
      if (!contactCache.length) { try { contactCache = (await contactsApi.list()) || []; } catch {} }
      const pool = q
        ? contactCache.filter((c) => `${c.name || ""} ${c.email || ""}`.toLowerCase().includes(q.toLowerCase()))
        : contactCache;
      sugg = pool.filter((c) => c.email).slice(0, 8).map((c) => ({
        label: c.name || c.email, sub: c.email, apply: `${m[1].toLowerCase()}:${c.email}`, complete: true,
      }));
    } else if (w) {
      sugg = OPERATORS.filter((o) => o.token.toLowerCase().startsWith(w.toLowerCase()))
        .map((o) => ({ label: o.token, sub: o.hint, apply: o.token, complete: !o.value }));
    } else {
      sugg = OPERATORS.map((o) => ({ label: o.token, sub: o.hint, apply: o.token, complete: !o.value }));
    }
  }

  function onInput(e) {
    text = e.currentTarget.value;
    if (/\s$/.test(text)) chipLastWordIfComplete();
    recompute();
    if (!smart) scheduleFetch();
  }

  function applySugg(s) {
    setCurrentWord(s.apply);
    if (s.complete) chipLastWordIfComplete();
    recompute();
    inputEl?.focus();
    if (!smart) scheduleFetch();
  }

  function toggleChip(token) {
    const has = chips.some((c) => c.toLowerCase() === token.toLowerCase());
    chips = has ? chips.filter((c) => c.toLowerCase() !== token.toLowerCase())
                : normalizeChips([...chips, token]);
    inputEl?.focus();
    if (!smart) scheduleFetch();
  }
  function removeChip(i) { chips = chips.filter((_, j) => j !== i); if (!smart) scheduleFetch(); }
  function clearAll() { chips = []; text = ""; results = []; recompute(); inputEl?.focus(); }
  const chipActive = (token) => chips.some((c) => c.toLowerCase() === token.toLowerCase());

  // --- live results ---------------------------------------------------------
  function scheduleFetch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchResults, 200);
  }
  let fetchSeq = 0;
  async function fetchResults() {
    const q = query.trim();
    if (smart) { results = []; return; }
    if (!q) { results = []; loading = false; return; }
    const seq = ++fetchSeq;
    loading = true;
    try {
      const list = await messagesApi.list({ q, limit: 40 });
      if (seq !== fetchSeq) return;   // a newer query landed first
      results = Array.isArray(list) ? list : [];
      resultActive = results.length ? 0 : -1;
    } catch { if (seq === fetchSeq) results = []; }
    finally { if (seq === fetchSeq) loading = false; }
  }

  // --- actions --------------------------------------------------------------
  function close() { onclose?.(); }
  function commit() {
    const q = query.trim();
    if (smart) { if (q) { pushRecent(q); onsemantic?.(q); } close(); return; }
    pushRecent(q);
    onsearch?.(q);      // keep the bar + main list reflecting the query
    close();
  }
  function pickRecent(q) {
    const tokens = smartSplit(q);
    chips = normalizeChips(tokens.filter(isOp));
    text = tokens.filter((tk) => !isOp(tk)).join(" ");
    smart = false;
    recompute();
    fetchResults();
    inputEl?.focus();
  }
  function openResult(msg) {
    if (!msg) return;
    pushRecent(query.trim());
    onsearch?.(query.trim());   // list stays filtered behind the opened mail
    onopen?.(msg);
    close();
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key === "Backspace" && text === "" && chips.length && document.activeElement === inputEl) {
      // Backspace at the start pops the last chip back into editable text.
      text = chips[chips.length - 1]; chips = chips.slice(0, -1);
      recompute(); scheduleFetch(); e.preventDefault(); return;
    }
    if (smart) { if (e.key === "Enter") { e.preventDefault(); commit(); } return; }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      resultActive = results.length ? (resultActive + 1) % results.length : -1;
      scrollActive();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      resultActive = results.length ? (resultActive - 1 + results.length) % results.length : -1;
      scrollActive();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (resultActive >= 0 && results[resultActive]) openResult(results[resultActive]);
      else commit();
    }
  }

  let resultsEl;
  function scrollActive() {
    queueMicrotask(() => resultsEl?.children?.[resultActive]?.scrollIntoView({ block: "nearest" }));
  }

  const fromLabel = (m) => m.from_name || m.from_addr || "";
</script>

{#if open}
  <div class="overlay" transition:fade={{ duration: 110 }} onclick={close} role="presentation">
    <div class="palette" transition:fly={{ y: -16, duration: 160 }} onclick={(e) => e.stopPropagation()}
      onkeydown={onKey} role="dialog" aria-modal="true" tabindex="-1">
      <!-- Query builder -->
      <div class="qbar">
        <span class="ic">{@html icons.search}</span>
        {#each chips as c, i}
          {@const [op, val] = opParts(c)}
          <span class="chip"><span class="op">{op}</span><span class="val">{val}</span>
            <button class="x" title={t("search.close")} onmousedown={(e) => { e.preventDefault(); removeChip(i); }}>{@html icons.close}</button>
          </span>
        {/each}
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:this={inputEl} class="qinput" type="text" autofocus
          placeholder={chips.length ? "" : t("palette.placeholder")}
          value={text} oninput={onInput} />
        {#if smartAvailable}
          <div class="modeseg" role="tablist">
            <button class:on={!smart} onclick={() => { smart = false; fetchResults(); }}>{t("search.modeKeyword")}</button>
            <button class:on={smart} onclick={() => { smart = true; results = []; }}>✨ {t("search.modeSmart")}</button>
          </div>
        {/if}
        {#if chips.length || text.trim()}
          <button class="clear" title={t("search.clear")} onmousedown={(e) => { e.preventDefault(); clearAll(); }}>{@html icons.close}</button>
        {/if}
        <button class="x close" title={t("search.close")} onclick={close}>{@html icons.close}</button>
      </div>

      <div class="cols">
        <!-- Left: suggestions, filters, recent, help -->
        <div class="side">
          {#if sugg.length}
            <div class="grp">
              <div class="ghead">{t("palette.suggestions")}</div>
              {#each sugg.slice(0, 8) as s}
                <button class="srow" onclick={() => applySugg(s)}>
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

        <!-- Right: live results -->
        <div class="main">
          {#if smart}
            <div class="empty">
              <span class="smartbadge">✨ {t("search.modeSmart")}</span>
              <p>{t("palette.smartHint")}</p>
            </div>
          {:else if !query.trim()}
            <div class="empty"><p>{t("palette.startHint")}</p></div>
          {:else if loading && !results.length}
            <div class="empty"><p>{t("palette.searching")}</p></div>
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

      <div class="foot">
        <code class="qprev" title={query}>{query || t("search.everything")}</code>
        <span class="spacer"></span>
        <span class="kbd-hint">{t("palette.kbdHint")}</span>
        <button class="btn primary" onclick={commit}>{@html icons.search} {smart ? t("search.smartSearch") : t("search.search")}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.42); backdrop-filter: blur(2px); z-index: 210;
    display: flex; justify-content: center; align-items: flex-start; padding-top: 8vh; }
  .palette { width: min(880px, 94vw); max-height: 82vh; display: flex; flex-direction: column; background: var(--surface);
    border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 4px); box-shadow: var(--shadow-lg);
    overflow: hidden; transform-origin: top center; }

  .qbar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 12px 14px; border-bottom: 1px solid var(--hairline); }
  .qbar .ic { color: var(--accent); display: inline-flex; }
  .qinput { flex: 1; min-width: 140px; border: none; background: transparent; padding: 6px 2px; outline: none; font-size: 15px; color: var(--text); }
  .chip { display: inline-flex; align-items: center; gap: 2px; background: var(--accent); color: #fff; border-radius: 6px; padding: 2px 4px 2px 7px; font-size: 12px; max-width: 260px; }
  .chip .op { opacity: 0.8; } .chip .val { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip .x { color: #fff; opacity: 0.85; display: inline-flex; padding: 1px; }
  .modeseg { display: inline-flex; gap: 2px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 2px; }
  .modeseg button { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; color: var(--muted); }
  .modeseg button.on { background: var(--accent); color: #fff; }
  .clear { color: var(--muted); display: inline-flex; padding: 2px; border-radius: 50%; }
  .clear:hover { color: var(--text); background: var(--surface-3); }
  .x.close { color: var(--muted); display: inline-flex; padding: 3px; border-radius: 6px; }
  .x.close:hover { color: var(--text); background: var(--surface-2); }

  .cols { display: flex; min-height: 0; flex: 1; }
  .side { width: 244px; flex: none; border-right: 1px solid var(--hairline); overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 14px; }
  .grp { display: flex; flex-direction: column; gap: 3px; }
  .ghead { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); padding: 0 4px 3px; }
  .srow { display: flex; align-items: baseline; gap: 8px; padding: 6px 9px; border-radius: 6px; text-align: left; width: 100%; }
  .srow:hover { background: var(--surface-2); }
  .s-label { font-weight: 600; font-family: ui-monospace, monospace; font-size: 12px; }
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
  .res.active { background: var(--surface-2); }
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
    padding: 4px 9px; border-radius: 6px; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .spacer { flex: 1; }
  .kbd-hint { font-size: 11.5px; color: var(--faint); }
  .btn.primary { padding: 8px 14px; border-radius: var(--radius-sm); background: var(--accent); color: #fff; font-size: 13px; font-weight: 550; display: inline-flex; align-items: center; gap: 6px; }
  .btn.primary:hover { background: color-mix(in srgb, var(--accent) 88%, #000); }
  .btn.primary :global(svg) { width: 15px; height: 15px; }

  @media (max-width: 640px) {
    .side { display: none; }
    .palette { width: 96vw; }
  }
</style>
