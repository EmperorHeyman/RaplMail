<script>
  import { fly, fade } from "svelte/transition";
  import { app, selectSmartInbox, selectUnifiedInbox, selectSnoozed, selectPaperTrail, selectFollowups } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // "Go to…" quick-jump bar — replaces the old invisible `g`+letter chord with a
  // VS Code-style palette (Ctrl+T feel). The single-letter accelerators still
  // work instantly (type a hint letter while the query is empty), so muscle
  // memory like `g i` survives, but new users get a discoverable, filterable
  // menu instead of guessing blind.
  let { open = false, onclose } = $props();

  let query = $state("");
  let active = $state(0);
  let inputEl;

  const goInbox = () => { app.view = "mail"; (app.settings.smartInbox ? selectSmartInbox : selectUnifiedInbox)(); };

  const dests = $derived.by(() => [
    { hint: "i", icon: icons.inbox, label: t("goto.inbox"), run: goInbox },
    { hint: "u", icon: icons.unified, label: t("goto.allInboxes"), run: () => { app.view = "mail"; selectUnifiedInbox(); } },
    { hint: "s", icon: icons.snooze, label: t("goto.snoozed"), run: () => { app.view = "mail"; selectSnoozed(); } },
    { hint: "f", icon: icons.done, label: t("goto.followups"), run: () => { app.view = "mail"; selectFollowups(); } },
    { hint: "p", icon: icons.receipt, label: t("goto.paperTrail"), run: () => { app.view = "mail"; selectPaperTrail(); } },
    { hint: "n", icon: icons.newspaper, label: t("goto.newsfeed"), run: () => (app.view = "newsfeed") },
    { hint: "c", icon: icons.calendar, label: t("goto.calendar"), run: () => (app.view = "calendar") },
    { hint: "t", icon: icons.clock, label: t("goto.scheduled"), run: () => (app.view = "scheduled") },
    { hint: "a", icon: icons.settings, label: t("goto.settings"), run: () => (app.view = "settings") },
  ]);

  const filtered = $derived(
    query.trim() === "" ? dests
      : dests.filter((d) => d.label.toLowerCase().includes(query.trim().toLowerCase()))
  );

  $effect(() => { if (active >= filtered.length) active = Math.max(0, filtered.length - 1); });
  $effect(() => { if (open) { query = ""; active = 0; queueMicrotask(() => inputEl?.focus()); } });

  function close() { onclose?.(); }
  function run(d) { close(); d.run(); }

  function onKey(e) {
    if (e.key === "Escape") { close(); e.preventDefault(); return; }
    if (e.key === "ArrowDown") { active = Math.min(filtered.length - 1, active + 1); e.preventDefault(); return; }
    if (e.key === "ArrowUp") { active = Math.max(0, active - 1); e.preventDefault(); return; }
    if (e.key === "Enter") { if (filtered[active]) run(filtered[active]); e.preventDefault(); return; }
    // Empty query → a destination's hint letter fires it instantly.
    if (query === "" && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const d = dests.find((x) => x.hint === e.key.toLowerCase());
      if (d) { run(d); e.preventDefault(); }
    }
  }
</script>

{#if open}
  <div class="overlay" transition:fade={{ duration: 110 }} onclick={close}>
    <div class="palette" transition:fly={{ y: -12, duration: 140 }} onclick={(e) => e.stopPropagation()}>
      <div class="qrow">
        <span class="ic">{@html icons.search}</span>
        <input bind:this={inputEl} bind:value={query} onkeydown={onKey}
          placeholder={t("goto.placeholder")} />
      </div>
      <ul>
        {#each filtered as d, i (d.label)}
          <li class:active={i === active} onmousedown={() => run(d)} onmouseenter={() => (active = i)}>
            <span class="ic">{@html d.icon}</span>
            <span class="lbl">{d.label}</span>
            {#if query.trim() === ""}<kbd>{d.hint}</kbd>{/if}
          </li>
        {/each}
        {#if filtered.length === 0}<li class="none">{t("goto.noResults")}</li>{/if}
      </ul>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); backdrop-filter: blur(2px); z-index: 200;
    display: flex; justify-content: center; align-items: flex-start; padding-top: 12vh; animation: fade-in var(--t) var(--ease); }
  .palette { width: min(460px, 92vw); max-height: 62vh; display: flex; flex-direction: column; background: var(--surface);
    border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); overflow: hidden;
    animation: pop-in var(--t) var(--ease); transform-origin: top center; }
  .qrow { display: flex; align-items: center; gap: 9px; padding: 13px 16px; border-bottom: 1px solid var(--hairline); }
  .qrow .ic { color: var(--muted); display: inline-flex; }
  .qrow input { flex: 1; border: none; background: transparent; padding: 0; font-size: 15px; box-shadow: none; }
  .qrow input:focus { border: none; box-shadow: none; }
  ul { list-style: none; margin: 0; padding: 6px; overflow-y: auto; }
  li { display: flex; align-items: center; gap: 11px; padding: 9px 12px; border-radius: var(--radius-sm); cursor: pointer; }
  li.active { background: var(--accent); color: #fff; }
  .ic { width: 20px; display: inline-flex; justify-content: center; }
  li .ic :global(svg) { width: 17px; height: 17px; }
  .lbl { flex: 1; }
  kbd { flex: none; padding: 1px 7px; border-radius: 5px; background: var(--surface-2); border: 1px solid var(--hairline);
    font-size: 11px; font-family: ui-monospace, monospace; color: var(--muted); }
  li.active kbd { background: rgba(255,255,255,0.18); border-color: rgba(255,255,255,0.25); color: #fff; }
  .none { color: var(--muted); justify-content: center; cursor: default; }
</style>
