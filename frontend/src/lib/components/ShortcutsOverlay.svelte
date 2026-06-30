<script>
  import { fade, fly } from "svelte/transition";
  import { app } from "../store.svelte.js";
  import { comboLabel } from "../keys.js";
  import { icons } from "../icons.js";
  let { open = false, onclose } = $props();

  const kb = $derived(app.settings.keybinds || {});
  const groups = $derived([
    { title: "Triage", items: [
      [`${comboLabel(kb.next)} / ${comboLabel(kb.prev)}`, "Move down / up"], [comboLabel(kb.open), "Open message / thread"],
      [comboLabel(kb.done), "Mark done (toggle)"], ["Ctrl/⌘ + Z", "Undo last action"],
      ["Click avatar", "Select (Shift-click for a range)"], ["Right-click", "Actions menu"],
    ]},
    { title: "Navigate", items: [
      [comboLabel(kb.search), "Focus search"], [comboLabel(kb.palette), "Command palette"],
      ["Ctrl/⌘ + 1…9 / 0", "Switch workspace / All"], [comboLabel(kb.help), "This cheatsheet"],
      ["g then i / s / c", "Jump: Inbox / Snoozed / Calendar"],
      ["g then f / n / p / t", "Follow-ups / Newsfeed / Paper Trail / Scheduled"],
      ["g then a", "Jump: Settings"],
    ]},
    { title: "Compose", items: [
      [comboLabel(kb.compose), "New message"], ["Ctrl/⌘ + Enter", "Send"], [";shortcut + Space", "Expand a snippet"],
    ]},
  ]);

  function onKey(e) { if (e.key === "Escape") onclose?.(); }
</script>

<svelte:window on:keydown={onKey} />

{#if open}
  <div class="overlay" transition:fade={{ duration: 120 }} onclick={onclose}>
    <div class="sheet" transition:fly={{ y: 12, duration: 150 }} onclick={(e) => e.stopPropagation()}>
      <header><h2>{@html icons.keyboard} Keyboard shortcuts</h2><button class="x" onclick={onclose}>{@html icons.close}</button></header>
      <div class="cols">
        {#each groups as g}
          <div class="group">
            <h3>{g.title}</h3>
            {#each g.items as [keys, desc]}
              <div class="row"><kbd>{keys}</kbd><span>{desc}</span></div>
            {/each}
          </div>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 210; display: grid; place-items: center; }
  .sheet { width: min(640px, 92vw); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); }
  h2 { margin: 0; font-size: 16px; }
  .x { color: var(--muted); padding: 4px 8px; border-radius: 6px; }
  .x:hover { background: var(--surface-2); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 28px; padding: 18px; }
  .group h3 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); }
  .row { display: flex; align-items: center; gap: 12px; padding: 5px 0; }
  .row span { color: var(--muted); font-size: 13px; }
  kbd { flex: none; min-width: 96px; text-align: center; padding: 3px 8px; border-radius: 6px; background: var(--surface-3); border: 1px solid var(--border); font-size: 11px; font-family: ui-monospace, monospace; }
</style>
