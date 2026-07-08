<script>
  // Search box with operator "chips" + a suggestion whisperer.
  // Completed operators (from:x, is:unread, /regex/) render as removable chips;
  // the trailing free text stays editable. As you type, suggestions appear -
  // operators by prefix, and real contacts once you start a from:/to:/cc:.
  import { contacts as contactsApi } from "../api.js";
  import { icons } from "../icons.js";
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
      <button class="x" title="Remove" onmousedown={(e) => { e.preventDefault(); removeChip(i); }}>{@html icons.close}</button>
    </span>
  {/each}
  <input
    class="search"
    bind:this={inputEl}
    type="text"
    placeholder={chips.length ? "" : "Search…  from:  to:  has:attachment  is:unread  /regex/"}
    value={text}
    oninput={onInput}
    onkeydown={onKey}
    onfocus={focus}
    onblur={() => setTimeout(() => (open = false), 120)}
  />
  {#if chips.length || text.trim()}
    <button class="clear" title="Clear search" onmousedown={(e) => { e.preventDefault(); clearAll(); }}>{@html icons.close}</button>
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
  .sb { position: relative; flex: 1; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
        background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px 8px; }
  .sb.focused { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent); }
  .clear { margin-left: auto; color: var(--muted); display: inline-flex; padding: 2px; border-radius: 50%; flex: none; }
  .clear:hover { color: var(--text); background: var(--surface-3); }
  .ic { color: var(--muted); display: inline-flex; }
  .chip { display: inline-flex; align-items: center; gap: 2px; background: var(--accent); color: #fff;
          border-radius: 6px; padding: 2px 4px 2px 7px; font-size: 12px; max-width: 240px; }
  .chip .op { opacity: 0.8; }
  .chip .val { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip .x { color: #fff; opacity: 0.8; display: inline-flex; padding: 1px; font-size: 10px; }
  .chip .x:hover { opacity: 1; }
  .search { flex: 1; min-width: 120px; border: none; background: transparent; padding: 4px 2px; outline: none; }
  .whisper { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 40; list-style: none;
             margin: 0; padding: 4px; background: var(--surface-3); border: 1px solid var(--border);
             border-radius: var(--radius-sm); box-shadow: var(--shadow); max-height: 280px; overflow-y: auto; }
  .whisper li { display: flex; align-items: baseline; gap: 10px; padding: 7px 10px; border-radius: 6px; cursor: pointer; }
  .whisper li.active { background: var(--accent); color: #fff; }
  .s-label { font-weight: 600; font-family: ui-monospace, monospace; font-size: 12px; }
  .s-sub { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .whisper li.active .s-sub { color: #e7e9ff; }
</style>
