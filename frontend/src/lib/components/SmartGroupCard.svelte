<script>
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  let { label, icon, count = 0, unread = 0, newCount = 0, senders = [], more = 0,
        expanded = false, focused = false, mode = "all",
        onToggle, onNewBadge, onSender, onDoneAll } = $props();

  // One quiet line: "Netflix, GitHub, Medium +9"
  const sendersLine = $derived.by(() => {
    const names = senders.map((s) => (s.name || (s.email || "").split("@")[0] || "").trim()).filter(Boolean);
    const shown = names.slice(0, 3);
    const extra = more + Math.max(0, names.length - shown.length);
    return shown.join(", ") + (extra > 0 ? `  +${extra}` : "");
  });
</script>

<div class="sg" class:focused class:open={expanded} class:hasnew={newCount > 0}>
  <button class="sg-head" onclick={onToggle}>
    <span class="ic">{@html icon}</span>
    <span class="main">
      <span class="l1">
        <span class="lbl">{label}</span>
        {#if newCount > 0}
          <button class="new tnum" class:active={expanded && mode === "new"}
            title={t("list.showNewTip")}
            onclick={(e) => { e.stopPropagation(); onNewBadge?.(); }}>{t("list.newCount", { n: newCount })}</button>
        {/if}
        <span class="count tnum">{count.toLocaleString()}</span>
      </span>
      {#if !expanded && sendersLine}
        <span class="who">{sendersLine}</span>
      {/if}
    </span>
    <span class="chev" aria-hidden="true">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 9 7 7 7-7"/></svg>
    </span>
  </button>
  <button class="doneall" title={t("list.doneAllTip")}
    onclick={(e) => { e.stopPropagation(); onDoneAll?.(); }}>{@html icons.done} {t("list.doneAll")}</button>
</div>

<style>
  /* Flat, Spark-style group section - no box, sits in the list like a row. */
  .sg {
    position: relative; display: flex; align-items: center; gap: 8px;
    padding: 0 14px 0 0; border-bottom: 1px solid var(--hairline);
    background: var(--bg);
    transition: background var(--t-fast) var(--ease);
  }
  .sg:hover { background: var(--surface); }
  .sg.focused { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
  .sg.open { box-shadow: inset 2px 0 0 var(--accent-soft-2); }
  .sg.open.focused { box-shadow: inset 3px 0 0 var(--accent); }

  .sg-head { flex: 1; display: flex; align-items: center; gap: 11px; min-width: 0; padding: 10px 0 10px 14px; text-align: left; }
  .ic { display: grid; place-items: center; width: 20px; flex: none; color: var(--muted); transition: color var(--t-fast) var(--ease); }
  .ic :global(svg) { width: 17px; height: 17px; }
  .hasnew .ic, .open .ic { color: var(--accent); }

  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .l1 { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .lbl { font-weight: 650; font-size: 13.5px; letter-spacing: -0.01em; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .new { flex: none; font-size: 10.5px; font-weight: 700; color: #fff; background: var(--accent);
    border-radius: 999px; padding: 2px 8px; cursor: pointer;
    box-shadow: 0 0 0 0 var(--accent-soft-2);
    transition: box-shadow var(--t-fast) var(--ease), filter var(--t-fast) var(--ease); }
  .new:hover { filter: brightness(1.08); box-shadow: 0 0 0 3px var(--accent-soft-2); }
  .new.active { box-shadow: 0 0 0 2px var(--accent-soft-2); outline: 1px solid #fff3; }
  .count { flex: none; color: var(--faint); font-weight: 600; font-size: 12px; }
  .who { color: var(--faint); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .chev { display: inline-flex; flex: none; color: var(--faint); transition: transform var(--t-slow) var(--ease-spring), color var(--t-fast) var(--ease), opacity var(--t-fast) var(--ease); }
  .sg:hover .chev { color: var(--muted); }
  .open .chev { transform: rotate(180deg); color: var(--accent); }
  /* The Done-all button reveals in the chevron's spot on hover/focus - fade the
     chevron out so the two don't visibly stack (the "something behind the button"
     clutter). */
  .sg:hover .chev, .sg.focused .chev { opacity: 0; }

  /* Revealed on hover / keyboard focus, like the row actions. */
  .doneall { flex: none; display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
    padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); background: var(--bg);
    opacity: 0; transform: scale(0.94);
    transition: opacity var(--t-fast) var(--ease), background var(--t-fast) var(--ease),
      color var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease), transform var(--t) var(--ease-spring); }
  .sg:hover .doneall, .sg.focused .doneall { opacity: 1; transform: scale(1); }
  .doneall:hover { background: var(--done); border-color: var(--done); color: #06231a; }
</style>
