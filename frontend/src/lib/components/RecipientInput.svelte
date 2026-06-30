<script>
  import { contacts } from "../api.js";

  // Two-way bound comma-separated recipient string.
  let { value = $bindable(""), placeholder = "" } = $props();

  let suggestions = $state([]);
  let open = $state(false);
  let active = $state(0);
  let inputEl;
  let timer;

  // The fragment after the last comma is what we're completing.
  function currentFragment() {
    const parts = value.split(",");
    return parts[parts.length - 1].trim();
  }

  // Pull the bare address out of a "Name <addr>" token.
  const addrOf = (t) => (String(t).match(/<([^>]+)>/)?.[1] || String(t)).trim();
  const looksValid = (t) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(addrOf(t));
  // Completed tokens (everything but the one still being typed) that don't look
  // like a valid address — surfaced so a typo'd / mis-pasted recipient is caught
  // before send rather than shipped verbatim to the server.
  const invalid = $derived(
    value.split(",").slice(0, -1).map((t) => t.trim()).filter((t) => t && !looksValid(t))
  );

  function onInput() {
    // Accept lists pasted from other clients: Outlook uses ';', some use newlines.
    if (/[;\n\t]/.test(value)) value = value.replace(/[;\n\t]+/g, ", ");
    const frag = currentFragment();
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

  function pick(c) {
    const parts = value.split(",");
    parts[parts.length - 1] = ` ${c.email}`;
    value = parts.join(",").replace(/^\s+/, "") + ", ";
    open = false;
    suggestions = [];
    inputEl?.focus();
  }

  function onKey(e) {
    if (!open) return;
    if (e.key === "ArrowDown") { active = (active + 1) % suggestions.length; e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = (active - 1 + suggestions.length) % suggestions.length; e.preventDefault(); }
    else if (e.key === "Enter" || e.key === "Tab") {
      if (suggestions[active]) { pick(suggestions[active]); e.preventDefault(); }
    } else if (e.key === "Escape") { open = false; }
  }
</script>

<div class="rcpt">
  <input
    bind:this={inputEl}
    bind:value
    {placeholder}
    oninput={onInput}
    onkeydown={onKey}
    onblur={() => setTimeout(() => (open = false), 120)}
    autocomplete="off"
  />
  {#if invalid.length}
    <div class="rcpt-warn">⚠ Check {invalid.length === 1 ? "this address" : "these addresses"}: {invalid.join(", ")}</div>
  {/if}
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

<style>
  .rcpt { position: relative; flex: 1; }
  .rcpt-warn { font-size: 11px; color: var(--warning); padding: 2px 0; }
  input { width: 100%; border: none; background: transparent; padding: 4px 0; }
  input:focus { border: none; }
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
