<script>
  // The Smart Inbox groups as one compact strip at the top of the list, in a
  // fixed order. It replaced a card per group that floated up and down with new
  // mail and filled the first screen. Click a group to open its mail right
  // below; new mail itself already shows in the timeline (tagged), so a group
  // only marks that it has some with a dot.
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let { groups = [], meta = {}, openKey = null, editOn = false,
        onToggle, onMenu, onPeek, onPeekOut, onEdit, editEl = $bindable() } = $props();

  // The hover preview anchors beside whatever it's given. Hand it the strip's
  // width at the pill's height, so it opens next to the list column (as it did
  // for the old full-width cards) instead of on top of the neighbouring pills.
  function peekRect(pill) {
    const s = pill.closest(".strip").getBoundingClientRect();
    const p = pill.getBoundingClientRect();
    return { left: s.left, right: s.right, top: p.top, bottom: p.bottom };
  }
</script>

<div class="strip" role="toolbar" aria-label={t("groups.menuTitle")}>
  {#each groups as g (g.key)}
    {@const m = meta[g.category] || {}}
    <button class="pill" class:open={openKey === g.key} style="--tone:{m.tone || 'var(--accent)'}"
      title={g.new ? t("groups.pillNewTip", { n: g.new }) : (m.label || g.category)}
      onclick={() => onToggle?.(g)}
      oncontextmenu={(e) => { e.preventDefault(); onPeekOut?.(); onMenu?.(e); }}
      onmouseenter={(e) => { if (openKey !== g.key) onPeek?.(g, peekRect(e.currentTarget)); }}
      onmouseleave={() => onPeekOut?.()}>
      <span class="ic">{@html m.icon || icons.folder}</span>
      <span class="lbl">{m.label || g.category}</span>
      <span class="cnt tnum">{g.count.toLocaleString()}</span>
      {#if g.new}<span class="dot" aria-label={t("groups.pillNewTip", { n: g.new })}></span>{/if}
    </button>
  {/each}
  <button class="pill edit" class:on={editOn} bind:this={editEl} title={t("groups.chooseTip")}
    aria-label={t("groups.chooseTip")} onclick={() => onEdit?.()}>
    <span class="ic">{@html icons.groups}</span>
  </button>
</div>

<style>
  /* Material filter chips. The open group takes its own hue, matching the
     group header that opens under the strip. */
  .strip { display: flex; flex-wrap: wrap; gap: 8px; padding: 6px 12px 10px; }
  .pill { position: relative; display: inline-flex; align-items: center; gap: 7px; max-width: 100%;
    height: 32px; padding: 0 12px 0 8px; border-radius: 8px; font-size: 13px; font-weight: 500;
    background: transparent; box-shadow: inset 0 0 0 1px var(--border); color: var(--muted);
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease); }
  .pill:hover { background: var(--hover); color: var(--text); }
  .pill.open { color: var(--text); background: color-mix(in srgb, var(--tone) 18%, transparent);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 40%, transparent); }
  .ic { flex: none; width: 20px; height: 20px; display: grid; place-items: center;
    color: color-mix(in srgb, var(--tone) 75%, var(--text)); }
  .ic :global(svg) { width: 18px; height: 18px; }
  .lbl { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cnt { color: var(--text); font-weight: 600; font-size: 12.5px; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex: none; margin-left: -2px; }
  .pill.edit { width: 32px; padding: 0; justify-content: center; box-shadow: none; color: var(--muted); }
  .pill.edit .ic { color: inherit; }
  .pill.edit:hover { background: var(--hover); color: var(--text); }
  .pill.edit.on { background: var(--sel); color: var(--on-sel); }
</style>
