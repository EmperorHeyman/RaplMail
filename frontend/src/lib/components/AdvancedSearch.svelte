<script>
  import { fly, fade } from "svelte/transition";
  import { contacts } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // A friendly, structured search builder. It reads and writes the SAME query
  // string the inline search bar (and the backend) understand — from:/to:/
  // subject:/has:attachment/is:… + free text — so it's an "expand the search"
  // surface, not a separate engine. Contact autocomplete on From/To makes it
  // smarter than typing operators by hand.
  let { open = false, onclose, initial = "", onsearch, onsemantic, smartAvailable = false } = $props();

  let from = $state("");
  let to = $state("");
  let subject = $state("");
  let words = $state("");
  let attach = $state(false);
  let status = $state("any");   // any | unread | read | flagged | done
  // Smart (meaning-based) mode — only offered when the local embedding index is
  // enabled. It searches by semantic similarity, so the operator fields (from/
  // subject/status) don't apply: the whole query is a natural-language phrase.
  let smart = $state(false);

  const TOKEN_RE = /(\w+):\s*(?:"([^"]*)"|(\S+))/g;
  // Mirror the backend's _parse_query so opening the modal reflects whatever is
  // already in the search bar.
  function parse(q) {
    let free = String(q || "");
    let nf = "", nt = "", ns = "", att = false, st = "any";
    free = free.replace(TOKEN_RE, (m, key, quoted, bare) => {
      const val = (quoted != null ? quoted : bare || "").trim();
      const k = key.toLowerCase(), v = val.toLowerCase();
      if (k === "from") { nf = val; return ""; }
      if (k === "to") { nt = val; return ""; }
      if (k === "subject") { ns = val; return ""; }
      if (k === "has" && ["attachment", "attachments", "file"].includes(v)) { att = true; return ""; }
      if (k === "is") {
        if (v === "unread") st = "unread";
        else if (v === "read" || v === "seen") st = "read";
        else if (v === "done") st = "done";
        else if (v === "flagged" || v === "starred") st = "flagged";
        else return m;
        return "";
      }
      return m;   // unknown operator → keep as free text
    });
    from = nf; to = nt; subject = ns; attach = att; status = st;
    words = free.replace(/\s+/g, " ").trim();
  }

  // Reflect the current search bar contents each time the modal opens.
  $effect(() => { if (open) { parse(initial); ac = { field: null, sugg: [], active: 0 }; if (!smartAvailable) smart = false; } });

  const opTok = (op, val) => { const v = String(val).trim(); return v ? (/\s/.test(v) ? `${op}:"${v}"` : `${op}:${v}`) : ""; };
  const query = $derived.by(() => {
    const parts = [];
    for (const p of [opTok("from", from), opTok("to", to), opTok("subject", subject)]) if (p) parts.push(p);
    if (attach) parts.push("has:attachment");
    if (status === "unread") parts.push("is:unread");
    else if (status === "read") parts.push("is:read");
    else if (status === "flagged") parts.push("is:flagged");
    else if (status === "done") parts.push("is:done");
    if (words.trim()) parts.push(words.trim());
    return parts.join(" ");
  });

  // --- shared contact autocomplete for From / To ---
  let ac = $state({ field: null, sugg: [], active: 0 });
  let acTimer;
  function acInput(field, val) {
    if (field === "from") from = val; else to = val;
    clearTimeout(acTimer);
    const frag = val.trim();
    if (frag.length < 2) { ac = { field: null, sugg: [], active: 0 }; return; }
    acTimer = setTimeout(async () => {
      try { const s = (await contacts.list(frag)) || []; ac = { field, sugg: s.slice(0, 6), active: 0 }; }
      catch { ac = { field: null, sugg: [], active: 0 }; }
    }, 140);
  }
  function acPick(field, c) {
    if (field === "from") from = c.email; else to = c.email;
    ac = { field: null, sugg: [], active: 0 };
  }
  function acKey(field, e) {
    if (ac.field === field && ac.sugg.length) {
      if (e.key === "ArrowDown") { ac.active = (ac.active + 1) % ac.sugg.length; e.preventDefault(); return; }
      if (e.key === "ArrowUp") { ac.active = (ac.active - 1 + ac.sugg.length) % ac.sugg.length; e.preventDefault(); return; }
      if (e.key === "Enter" || e.key === "Tab") { acPick(field, ac.sugg[ac.active]); e.preventDefault(); return; }
      if (e.key === "Escape") { ac = { field: null, sugg: [], active: 0 }; e.stopPropagation(); return; }
    }
    if (e.key === "Enter") { doSearch(); e.preventDefault(); }
  }

  const PRESETS = $derived.by(() => [
    { label: t("search.presetUnreadAttach"), run: () => { reset(); status = "unread"; attach = true; } },
    { label: t("search.presetFlagged"), run: () => { reset(); status = "flagged"; } },
    { label: t("search.presetUnread"), run: () => { reset(); status = "unread"; } },
    { label: t("search.presetAttach"), run: () => { reset(); attach = true; } },
  ]);

  function reset() { from = ""; to = ""; subject = ""; words = ""; attach = false; status = "any"; ac = { field: null, sugg: [], active: 0 }; }
  function close() { onclose?.(); }
  function doSearch() {
    if (smart) { const q = words.trim() || query; if (q) onsemantic?.(q); else return; }
    else onsearch?.(query);
    close();
  }

  const STATUSES = $derived.by(() => [
    { id: "any", label: t("search.stAny") },
    { id: "unread", label: t("search.stUnread") },
    { id: "read", label: t("search.stRead") },
    { id: "flagged", label: t("search.stFlagged") },
    { id: "done", label: t("search.stDone") },
  ]);
</script>

{#if open}
  <div class="overlay" transition:fade={{ duration: 120 }} onclick={close}>
    <div class="modal" transition:fly={{ y: -14, duration: 160 }} onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => { if (e.key === "Escape") close(); }} role="dialog" tabindex="-1">
      <div class="head">
        <span class="ic">{@html icons.search}</span>
        <b>{t("search.title")}</b>
        {#if smartAvailable}
          <div class="modeseg" role="tablist">
            <button class:on={!smart} onclick={() => (smart = false)}>{t("search.modeKeyword")}</button>
            <button class:on={smart} onclick={() => (smart = true)}>✨ {t("search.modeSmart")}</button>
          </div>
        {/if}
        <button class="x" title={t("search.close")} onclick={close}>{@html icons.close}</button>
      </div>

      {#if smart}
        <div class="body smart">
          <span class="smartbadge">✨ {t("search.smartBadge")}</span>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="smartinput" bind:value={words} autofocus
            placeholder={t("search.smartPlaceholder")}
            onkeydown={(e) => { if (e.key === "Enter") doSearch(); }} />
          <p class="smarthint">{t("search.smartHint")}</p>
        </div>
      {:else}
      <div class="body">
        <label class="row">
          <span class="lab">{t("search.from")}</span>
          <span class="field">
            <input value={from} oninput={(e) => acInput("from", e.currentTarget.value)}
              onkeydown={(e) => acKey("from", e)} placeholder={t("search.fromPlaceholder")} autocomplete="off" />
            {#if ac.field === "from"}
              <ul class="ac">
                {#each ac.sugg as c, i (c.id)}
                  <li class:active={i === ac.active} onmousedown={() => acPick("from", c)} onmouseenter={() => (ac.active = i)}>
                    <span class="nm">{c.name || c.email}</span>{#if c.name}<span class="em">{c.email}</span>{/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </span>
        </label>

        <label class="row">
          <span class="lab">{t("search.to")}</span>
          <span class="field">
            <input value={to} oninput={(e) => acInput("to", e.currentTarget.value)}
              onkeydown={(e) => acKey("to", e)} placeholder={t("search.toPlaceholder")} autocomplete="off" />
            {#if ac.field === "to"}
              <ul class="ac">
                {#each ac.sugg as c, i (c.id)}
                  <li class:active={i === ac.active} onmousedown={() => acPick("to", c)} onmouseenter={() => (ac.active = i)}>
                    <span class="nm">{c.name || c.email}</span>{#if c.name}<span class="em">{c.email}</span>{/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </span>
        </label>

        <label class="row">
          <span class="lab">{t("search.subject")}</span>
          <input class="field" bind:value={subject} onkeydown={(e) => { if (e.key === "Enter") doSearch(); }} placeholder={t("search.subjectPlaceholder")} />
        </label>

        <label class="row">
          <span class="lab">{t("search.words")}</span>
          <input class="field" bind:value={words} onkeydown={(e) => { if (e.key === "Enter") doSearch(); }} placeholder={t("search.wordsPlaceholder")} />
        </label>

        <div class="row">
          <span class="lab">{t("search.status")}</span>
          <div class="seg">
            {#each STATUSES as s}
              <button class:on={status === s.id} onclick={() => (status = s.id)}>{s.label}</button>
            {/each}
          </div>
        </div>

        <div class="row">
          <span class="lab">{t("search.attachment")}</span>
          <label class="chk">
            <input type="checkbox" bind:checked={attach} />
            <span>{t("search.hasAttachment")}</span>
          </label>
        </div>

        <div class="presets">
          <span class="plabel">{t("search.quick")}</span>
          {#each PRESETS as p}<button class="preset" onclick={p.run}>{p.label}</button>{/each}
        </div>
      </div>
      {/if}

      <div class="foot">
        {#if smart}
          <code class="qprev" title={words}>{words.trim() || t("search.everything")}</code>
        {:else}
          <code class="qprev" title={query}>{query || t("search.everything")}</code>
        {/if}
        <span class="spacer"></span>
        {#if !smart}<button class="btn" onclick={reset}>{t("search.clear")}</button>{/if}
        <button class="btn primary" onclick={doSearch}>{@html icons.search} {smart ? t("search.smartSearch") : t("search.search")}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.42); backdrop-filter: blur(2px); z-index: 210;
    display: flex; justify-content: center; align-items: flex-start; padding-top: 10vh; animation: fade-in var(--t) var(--ease); }
  .modal { width: min(600px, 94vw); display: flex; flex-direction: column; background: var(--surface);
    border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 4px); box-shadow: var(--shadow-lg);
    overflow: hidden; animation: pop-in var(--t) var(--ease); transform-origin: top center; }
  .head { display: flex; align-items: center; gap: 9px; padding: 14px 16px; border-bottom: 1px solid var(--hairline); font-size: 15px; }
  .head .ic { color: var(--accent); display: inline-flex; }
  .head b { flex: 1; }
  .modeseg { display: inline-flex; gap: 2px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 2px; }
  .modeseg button { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; color: var(--muted); }
  .modeseg button.on { background: var(--accent); color: #fff; }
  .body.smart { gap: 8px; padding: 18px 16px 16px; }
  .smartbadge { align-self: flex-start; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
    padding: 2px 8px; border-radius: 999px; background: var(--accent-soft, color-mix(in srgb, var(--accent) 18%, transparent)); color: var(--accent); }
  .smartinput { width: 100%; box-sizing: border-box; padding: 12px 14px; font-size: 15px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); }
  .smartinput:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent); }
  .smarthint { margin: 0; color: var(--muted); font-size: 12.5px; line-height: 1.5; }
  .head .x { color: var(--muted); display: inline-flex; padding: 3px; border-radius: 6px; }
  .head .x:hover { color: var(--text); background: var(--surface-2); }
  .body { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
  .row { display: flex; align-items: center; gap: 12px; }
  .lab { width: 96px; flex: none; color: var(--muted); font-size: 13px; }
  .field { flex: 1; position: relative; min-width: 0; }
  input.field, .row > input { flex: 1; }
  .body input[type="text"], .body input:not([type]) { width: 100%; box-sizing: border-box; padding: 8px 11px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); }
  .body input:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent); }
  .ac { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 5; list-style: none; margin: 0; padding: 4px;
    background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); max-height: 200px; overflow-y: auto; }
  .ac li { display: flex; align-items: baseline; gap: 8px; padding: 7px 9px; border-radius: 6px; cursor: pointer; }
  .ac li.active { background: var(--accent); color: #fff; }
  .ac .nm { font-weight: 550; }
  .ac .em { font-size: 12px; color: var(--muted); }
  .ac li.active .em { color: #e7eaf0; }
  .seg { display: inline-flex; flex-wrap: wrap; gap: 4px; }
  .seg button { font-size: 12px; padding: 5px 12px; border-radius: 999px; background: var(--surface-2); color: var(--muted); }
  .seg button:hover { background: var(--surface-3); color: var(--text); }
  .seg button.on { background: var(--accent); color: #fff; }
  .chk { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
  .chk input { width: auto; }
  .presets { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding-top: 2px; }
  .plabel { font-size: 12px; color: var(--faint); margin-right: 2px; }
  .preset { font-size: 12px; padding: 4px 11px; border-radius: 999px; border: 1px solid var(--border); color: var(--text); background: transparent; }
  .preset:hover { border-color: var(--accent); color: var(--accent); }
  .foot { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--hairline); background: var(--surface-2); }
  .qprev { font-size: 11.5px; font-family: ui-monospace, monospace; color: var(--muted); background: var(--surface);
    border: 1px solid var(--border); padding: 4px 9px; border-radius: 6px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .spacer { flex: 1; }
  .btn { padding: 8px 14px; border-radius: var(--radius-sm); background: var(--surface-3); font-size: 13px; font-weight: 550; }
  .btn:hover { background: color-mix(in srgb, var(--surface-3) 76%, var(--text) 10%); }
  .btn.primary { background: var(--accent); color: #fff; display: inline-flex; align-items: center; gap: 6px; }
  .btn.primary:hover { background: color-mix(in srgb, var(--accent) 88%, #000); }
  .btn.primary :global(svg) { width: 15px; height: 15px; }
</style>
