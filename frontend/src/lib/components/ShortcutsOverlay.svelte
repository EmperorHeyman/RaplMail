<script>
  import { fade, fly } from "svelte/transition";
  import { kbAll } from "../store.svelte.js";
  import { comboLabel } from "../keys.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  let { open = false, onclose } = $props();

  const kb = $derived(kbAll());
  const groups = $derived([
    { title: t("shortcuts.gTriage"), items: [
      [`${comboLabel(kb.next)} / ${comboLabel(kb.prev)}`, t("shortcuts.moveUpDown")], [comboLabel(kb.open), t("shortcuts.openMsg")],
      [comboLabel(kb.done), t("shortcuts.markDoneToggle")], [comboLabel(kb.reply), t("shortcuts.reply")],
      [comboLabel(kb.forward), t("shortcuts.forward")], [comboLabel(kb.archive), t("shortcuts.archive")],
      [comboLabel(kb.delete), t("shortcuts.delete")], [comboLabel(kb.read), t("shortcuts.toggleRead")],
      ["Esc", t("shortcuts.backToList")], ["Ctrl/⌘ + Z", t("shortcuts.undo")],
      [t("shortcuts.clickAvatar"), t("shortcuts.selectRange")], [t("shortcuts.rightClick"), t("shortcuts.actionsMenu")],
    ]},
    { title: t("shortcuts.gNavigate"), items: [
      [comboLabel(kb.search), t("shortcuts.focusSearch")], [comboLabel(kb.palette), t("shortcuts.palette")],
      ["Ctrl/⌘ + 1…9 / 0", t("shortcuts.switchWorkspace")], [comboLabel(kb.help), t("shortcuts.cheatsheet")],
      ["g", t("shortcuts.goTo")],
      [t("shortcuts.gJumpKeys1"), t("shortcuts.jump1")],
      [t("shortcuts.gJumpKeys2"), t("shortcuts.jump2")],
    ]},
    { title: t("shortcuts.gCompose"), items: [
      [comboLabel(kb.compose), t("shortcuts.newMessage")], ["Ctrl/⌘ + Enter", t("shortcuts.send")], [t("shortcuts.snippetCombo"), t("shortcuts.expandSnippet")],
    ]},
  ]);

  function onKey(e) { if (e.key === "Escape") onclose?.(); }
</script>

<svelte:window on:keydown={onKey} />

{#if open}
  <div class="overlay" transition:fade={{ duration: 120 }} onclick={onclose}>
    <div class="sheet" transition:fly={{ y: 12, duration: 150 }} onclick={(e) => e.stopPropagation()}>
      <header><h2>{@html icons.keyboard} {t("shortcuts.title")}</h2><button class="x" onclick={onclose}>{@html icons.close}</button></header>
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
