<script>
  import { contacts } from "../api.js";
  import { icons } from "../icons.js";

  // Spark-style recipient field. Committed recipients render as pills (showing a
  // name when we know one, not the raw address); the trailing text stays an
  // editable input. The public contract is unchanged: `value` is still the
  // two-way-bound, comma-separated recipient string the composer sends.
  let { value = $bindable(""), placeholder = "" } = $props();

  let pills = $state([]);          // [{ raw, addr, name, label, valid }]
  let draft = $state("");
  let suggestions = $state([]);
  let open = $state(false);
  let active = $state(0);
  let inputEl;
  let timer;
  let nameCache = {};              // addr(lower) -> name, from picks + the contact book

  // Pull the bare address / display name out of a "Name <addr>" token.
  const addrOf = (t) => (String(t).match(/<([^>]+)>/)?.[1] || String(t)).trim();
  const nameOf = (t) => {
    const m = String(t).match(/^\s*"?([^"<]+?)"?\s*<[^>]+>\s*$/);
    return m ? m[1].trim() : "";
  };
  const looksValid = (t) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(addrOf(t));

  function mkPill(raw) {
    const r = String(raw).trim();
    const addr = addrOf(r);
    const name = nameOf(r) || nameCache[addr.toLowerCase()] || "";
    return { raw: r, addr, name, label: name || addr, valid: looksValid(r) };
  }

  // Serialize back to the comma-separated string. The draft is included so a
  // half-typed address still ships if the user sends without committing it.
  let lastEmitted = "";
  function emit() {
    const parts = pills.map((p) => p.raw);
    if (draft.trim()) parts.push(draft.trim());
    value = parts.join(", ");
    lastEmitted = value;
  }

  // Outlook uses ';', pastes bring newlines/tabs - treat them all as separators.
  const SPLIT = /[;,\n\t]+/;
  // Re-parse when `value` changes from OUTSIDE (reply/forward prefill, clear).
  $effect(() => {
    if (value === lastEmitted) return;
    lastEmitted = value;
    const toks = String(value || "").split(SPLIT).map((s) => s.trim()).filter(Boolean);
    pills = toks.map(mkPill);
    draft = "";
  });

  // Warn once about committed recipients that don't look like an address, so a
  // typo'd / mis-pasted entry is caught before send.
  const invalid = $derived(pills.filter((p) => !p.valid));

  // Load the contact book once so pills built from bare addresses can resolve a
  // friendly name (and re-label any already on screen).
  let _loaded = false;
  async function ensureContacts() {
    if (_loaded) return;
    _loaded = true;
    try {
      const all = (await contacts.list()) || [];
      for (const c of all) if (c.email && c.name) nameCache[c.email.toLowerCase()] = c.name;
      pills = pills.map((p) => (p.name ? p : mkPill(p.raw)));
    } catch { _loaded = false; }
  }

  function commitDraft() {
    const d = draft.trim();
    if (!d) return;
    pills = [...pills, mkPill(d)];
    draft = "";
    open = false; suggestions = [];
    emit();
  }

  function pick(c) {
    if (c.email && c.name) nameCache[c.email.toLowerCase()] = c.name;
    pills = [...pills, mkPill(c.email)];
    draft = "";
    open = false; suggestions = [];
    emit();
    inputEl?.focus();
  }

  function removePill(i) { pills = pills.filter((_, j) => j !== i); emit(); inputEl?.focus(); }

  function onInput(e) {
    let v = e.currentTarget.value;
    // A separator in the text commits everything before the last one as pills.
    if (SPLIT.test(v)) {
      const toks = v.split(SPLIT);
      draft = toks.pop();                              // remainder keeps typing
      const done = toks.map((s) => s.trim()).filter(Boolean);
      if (done.length) pills = [...pills, ...done.map(mkPill)];
    } else {
      draft = v;
    }
    emit();
    const frag = draft.trim();
    clearTimeout(timer);
    if (frag.length < 2) { open = false; suggestions = []; return; }
    timer = setTimeout(async () => {
      try {
        suggestions = await contacts.list(frag);
        active = 0;
        open = suggestions.length > 0;
      } catch { open = false; }
    }, 140);
  }

  function onKey(e) {
    if (open && suggestions.length) {
      if (e.key === "ArrowDown") { active = (active + 1) % suggestions.length; e.preventDefault(); return; }
      if (e.key === "ArrowUp") { active = (active - 1 + suggestions.length) % suggestions.length; e.preventDefault(); return; }
      if (e.key === "Enter" || e.key === "Tab") { if (suggestions[active]) { pick(suggestions[active]); e.preventDefault(); return; } }
      if (e.key === "Escape") { open = false; e.preventDefault(); return; }
    }
    // Comma / Enter / Tab commit the current draft into a pill.
    if ((e.key === "Enter" || e.key === "Tab" || e.key === ",") && draft.trim()) {
      commitDraft(); e.preventDefault(); return;
    }
    // Backspace on an empty draft peels the last pill back into the input to edit.
    if (e.key === "Backspace" && draft === "" && pills.length) {
      const last = pills[pills.length - 1];
      pills = pills.slice(0, -1);
      draft = last.raw;
      emit();
      e.preventDefault();
    }
  }
</script>

<div class="rcpt" onclick={() => inputEl?.focus()} role="presentation">
  {#each pills as p, i (i + "|" + p.raw)}
    <span class="pill" class:bad={!p.valid} title={p.name ? `${p.name} <${p.addr}>` : p.addr}>
      <span class="pl">{p.label}</span>
      <button class="x" title="Remove" onmousedown={(e) => { e.preventDefault(); removePill(i); }}>{@html icons.close}</button>
    </span>
  {/each}
  <input
    bind:this={inputEl}
    value={draft}
    placeholder={pills.length ? "" : placeholder}
    oninput={onInput}
    onkeydown={onKey}
    onfocus={ensureContacts}
    onblur={() => setTimeout(() => { open = false; commitDraft(); }, 140)}
    autocomplete="off"
  />
  {#if open}
    <ul class="suggest" role="listbox">
      {#each suggestions as c, i (c.id)}
        <li role="option" aria-selected={i === active} class:active={i === active} onmousedown={() => pick(c)}>
          <span class="nm">{c.name || c.email}</span>
          {#if c.name}<span class="em">{c.email}</span>{/if}
          {#if c.favorite}<span class="fav">★</span>{/if}
          <span class="cnt">{c.times_sent}×</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>
{#if invalid.length}
  <div class="rcpt-warn">⚠ Check {invalid.length === 1 ? "this address" : "these addresses"}: {invalid.map((p) => p.addr).join(", ")}</div>
{/if}

<style>
  .rcpt { position: relative; flex: 1; display: flex; flex-wrap: wrap; align-items: center; gap: 5px; min-width: 0; cursor: text; }
  .rcpt-warn { flex-basis: 100%; font-size: 11px; color: var(--warning); padding: 2px 0; }
  .pill {
    display: inline-flex; align-items: center; gap: 3px; max-width: 100%;
    background: var(--accent-soft); color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-radius: 999px; padding: 2px 4px 2px 10px; font-size: 12.5px; font-weight: 550; line-height: 1.5;
    animation: pop-in var(--t-fast) var(--ease);
  }
  .pill.bad { background: var(--danger-soft); color: var(--danger); border-color: color-mix(in srgb, var(--danger) 30%, transparent); }
  .pill .pl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill .x { display: inline-flex; padding: 2px; border-radius: 50%; color: inherit; opacity: 0.6; flex: none; }
  .pill .x :global(svg) { width: 11px; height: 11px; }
  .pill .x:hover { opacity: 1; background: color-mix(in srgb, currentColor 18%, transparent); }
  input { flex: 1; min-width: 120px; border: none; background: transparent; padding: 4px 0; color: var(--text); }
  input:focus { border: none; outline: none; box-shadow: none; }
  .suggest {
    position: absolute; top: 100%; left: 0; right: 0; z-index: 10; margin: 4px 0 0; padding: 4px;
    list-style: none; background: var(--surface-3); border: 1px solid var(--border);
    border-radius: var(--radius-sm); box-shadow: var(--shadow); max-height: 240px; overflow-y: auto;
  }
  .suggest li {
    display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 6px; cursor: pointer;
  }
  .suggest li.active, .suggest li:hover { background: var(--accent); color: #fff; }
  .nm { font-weight: 550; }
  .em { color: var(--muted); font-size: 12px; }
  .suggest li.active .em { color: #e7eaf0; }
  .fav { color: var(--warning); }
  .cnt { margin-left: auto; font-size: 11px; color: var(--faint); }
  .suggest li.active .cnt { color: #dbe4ff; }
</style>
