<script>
  // Search box with operator "chips" + a suggestion whisperer.
  // Completed operators (from:x, is:unread, /regex/) render as removable chips;
  // the trailing free text stays editable. As you type, suggestions appear -
  // operators by prefix, and real contacts once you start a from:/to:/cc:.
  import { contacts as contactsApi } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { OPERATORS, smartSplit, isOp, opParts, normalizeChips } from "../searchQuery.js";

  // `onexpand`, when provided, means a richer palette owns the search UX: focusing
  // the bar opens it instead of the inline whisper dropdown.
  let { value = "", oninput, onexpand } = $props();

  let chips = $state([]);
  let text = $state("");
  let inputEl;
  let open = $state(false);
  let sugg = $state([]);
  let active = $state(0);
  let contactCache = [];

  // Re-parse when the value changes from the outside (e.g. searchAddress()).
  let lastEmitted = "";
  $effect(() => {
    if (value === lastEmitted) return;
    const tokens = smartSplit(value || "");
    chips = normalizeChips(tokens.filter(isOp));
    text = tokens.filter((t) => !isOp(t)).join(" ");
    lastEmitted = value;
  });

  function emit() {
    const combined = [...chips, text.trim()].filter(Boolean).join(" ");
    lastEmitted = combined;
    oninput?.(combined);
  }

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
      sugg = pool.filter((c) => c.email).slice(0, 7).map((c) => ({
        label: c.name || c.email, sub: c.email, apply: `${m[1].toLowerCase()}:${c.email}`, complete: true,
      }));
    } else if (w) {
      sugg = OPERATORS.filter((o) => o.token.toLowerCase().startsWith(w.toLowerCase()))
        .map((o) => ({ label: o.token, sub: o.hint, apply: o.token, complete: !o.value }));
    } else {
      sugg = OPERATORS.map((o) => ({ label: o.token, sub: o.hint, apply: o.token, complete: !o.value }));
    }
    active = 0;
  }

  function onInput(e) {
    text = e.currentTarget.value;
    // Completing an operator with a trailing space turns it into a chip; plain
    // words keep their spaces so free-text phrases still work.
    if (/\s$/.test(text)) {
      const tokens = smartSplit(text);
      const last = tokens[tokens.length - 1];
      if (last && isOp(last)) { chips = normalizeChips([...chips, last]); text = tokens.slice(0, -1).join(" "); }
    }
    emit();
    recompute();
  }

  function applySugg(s) {
    setCurrentWord(s.apply);
    if (s.complete) chipLastWordIfComplete();
    emit();
    inputEl?.focus();
    recompute();
  }

  function removeChip(i) { chips = chips.filter((_, j) => j !== i); emit(); inputEl?.focus(); }
  function clearAll() { chips = []; text = ""; emit(); inputEl?.focus(); recompute(); }

  function onKey(e) {
    if (e.key === "Backspace" && text === "" && chips.length) {
      text = chips[chips.length - 1];
      chips = chips.slice(0, -1);
      emit(); recompute(); e.preventDefault(); return;
    }
    if (!open || !sugg.length) return;
    if (e.key === "ArrowDown") { active = (active + 1) % sugg.length; e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = (active - 1 + sugg.length) % sugg.length; e.preventDefault(); }
    else if (e.key === "Enter" && currentWord()) { applySugg(sugg[active]); e.preventDefault(); }
    else if (e.key === "Escape") { open = false; e.stopPropagation(); }
  }

  function focus() {
    if (onexpand) { inputEl?.blur(); onexpand(); return; }   // palette takes over
    open = true; recompute();
  }
</script>

<div class="sb" class:focused={open}>
  <span class="ic">{@html icons.search}</span>
  {#each chips as c, i}
    {@const [op, val] = opParts(c)}
    <span class="chip"><span class="op">{op}</span><span class="val">{val}</span>
      <button class="x" title={t("search.removeChip")} onmousedown={(e) => { e.preventDefault(); removeChip(i); }}>{@html icons.close}</button>
    </span>
  {/each}
  <input
    class="search"
    bind:this={inputEl}
    type="text"
    placeholder={chips.length ? "" : t("search.barPlaceholder")}
    value={text}
    oninput={onInput}
    onkeydown={onKey}
    onfocus={focus}
    onblur={() => setTimeout(() => (open = false), 120)}
  />
  {#if chips.length || text.trim()}
    <button class="clear" title={t("search.clear")} onmousedown={(e) => { e.preventDefault(); clearAll(); }}>{@html icons.close}</button>
  {/if}

  {#if open && sugg.length}
    <ul class="whisper">
      {#each sugg as s, i}
        <li class:active={i === active} onmousedown={(e) => { e.preventDefault(); applySugg(s); }} onmouseenter={() => (active = i)}>
          <span class="s-label">{s.label}</span>
          {#if s.sub}<span class="s-sub">{s.sub}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  /* Lives inside the list's search pill (MailList .searchrow), which paints the
     container - the bar itself is transparent. */
  .sb { position: relative; flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
        min-height: 40px; padding: 4px 4px 4px 10px; }
  .clear { margin-left: auto; color: var(--muted); width: 32px; height: 32px; display: grid; place-items: center; border-radius: 50%; flex: none; }
  .clear :global(svg) { width: 20px; height: 20px; }
  .clear:hover { color: var(--text); background: var(--hover); }
  .ic { color: var(--muted); display: inline-flex; margin-right: 6px; }
  .ic :global(svg) { width: 22px; height: 22px; }
  /* Operator chips: Material input chips. */
  .chip { display: inline-flex; align-items: center; gap: 2px; height: 28px; background: var(--sel); color: var(--on-sel);
          border-radius: 8px; padding: 0 2px 0 10px; font-size: 13px; max-width: 240px; }
  .chip .op { opacity: 0.75; }
  .chip .val { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip .x { color: inherit; opacity: 0.75; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%; }
  .chip .x :global(svg) { width: 16px; height: 16px; }
  .chip .x:hover { opacity: 1; background: color-mix(in srgb, var(--on-sel) 12%, transparent); }
  .search { flex: 1; min-width: 120px; border: none; background: transparent; padding: 6px 2px; outline: none; font-size: 16px; }
  .search:hover, .search:focus { border: none; box-shadow: none; }
  .whisper { position: absolute; top: calc(100% + 10px); left: -4px; right: -4px; z-index: 40; list-style: none;
             margin: 0; padding: 6px 0; background: var(--surface-2);
             border-radius: var(--radius-menu); box-shadow: var(--shadow-lg); max-height: 300px; overflow-y: auto; }
  .whisper li { display: flex; align-items: baseline; gap: 12px; padding: 9px 16px; cursor: pointer; }
  .whisper li.active { background: var(--hover); }
  .s-label { font-weight: 600; font-family: ui-monospace, monospace; font-size: 12.5px; }
  .s-sub { font-size: 13px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
