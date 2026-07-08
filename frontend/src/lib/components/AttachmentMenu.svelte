<script>
  // Right-click context menu for an attachment: Open, Open in sandbox, Save to
  // Downloads, Save as… Positioned at the cursor and clamped to the viewport.
  import { onMount, onDestroy } from "svelte";
  import { t } from "../i18n.svelte.js";
  import { icons } from "../icons.js";

  let { x = 0, y = 0, sandboxOn = true, risky = false, onaction, onclose } = $props();

  let el = $state(null);
  let pos = $state({ left: x, top: y });

  function reposition() {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pad = 8;
    let left = x, top = y;
    if (left + r.width + pad > window.innerWidth) left = window.innerWidth - r.width - pad;
    if (top + r.height + pad > window.innerHeight) top = window.innerHeight - r.height - pad;
    pos = { left: Math.max(pad, left), top: Math.max(pad, top) };
  }

  // Run the action BEFORE closing: onclose nulls the parent's menu state, which
  // the action handler reads to know which attachment was picked.
  function pick(kind) { onaction?.(kind); onclose?.(); }
  function onKey(e) { if (e.key === "Escape") onclose?.(); }

  onMount(() => {
    reposition();
    // Close on any outside interaction. Defer so the opening right-click doesn't
    // immediately close it.
    const close = () => onclose?.();
    setTimeout(() => {
      window.addEventListener("pointerdown", close);
      window.addEventListener("blur", close);
      window.addEventListener("resize", close);
      document.addEventListener("scroll", close, true);
    }, 0);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("blur", close);
      window.removeEventListener("resize", close);
      document.removeEventListener("scroll", close, true);
    };
  });
</script>

<svelte:window on:keydown={onKey} />

<div bind:this={el} class="menu" style="left:{pos.left}px; top:{pos.top}px"
     onpointerdown={(e) => e.stopPropagation()} oncontextmenu={(e) => e.preventDefault()} role="menu" tabindex="-1">
  <button class="mi" role="menuitem" onclick={() => pick("open")}>{@html icons.attachment || ""} {t("attMenu.open")}</button>
  {#if sandboxOn}
    <button class="mi" role="menuitem" onclick={() => pick("sandbox")} class:accent={risky}>
      {@html icons.shield || ""} {t("attMenu.sandbox")}
    </button>
  {/if}
  <div class="sep"></div>
  <button class="mi" role="menuitem" onclick={() => pick("downloads")}>{@html icons.sent || ""} {t("attMenu.downloads")}</button>
  <button class="mi" role="menuitem" onclick={() => pick("saveas")}>{@html icons.download || icons.sent || ""} {t("attMenu.saveAs")}</button>
</div>

<style>
  .menu {
    position: fixed; z-index: 340; min-width: 210px; padding: 5px;
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 10px; box-shadow: var(--shadow-lg);
    display: flex; flex-direction: column; gap: 1px;
  }
  .mi {
    display: flex; align-items: center; gap: 9px; width: 100%; text-align: left;
    padding: 8px 10px; border-radius: 7px; font-size: 13px; color: var(--text);
  }
  .mi:hover { background: var(--hover); }
  .mi.accent { color: var(--accent); font-weight: 600; }
  .mi :global(svg) { width: 15px; height: 15px; flex: none; color: var(--muted); }
  .mi.accent :global(svg) { color: var(--accent); }
  .sep { height: 1px; background: var(--hairline); margin: 4px 2px; }
</style>
