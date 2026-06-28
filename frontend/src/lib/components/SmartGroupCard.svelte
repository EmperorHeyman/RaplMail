<script>
  import { icons } from "../icons.js";
  let { label, icon, count = 0, senders = [], more = 0, expanded = false, focused = false,
        onToggle, onSender, onDoneAll } = $props();
  const initial = (s) => (s || "?").trim()[0]?.toUpperCase() || "?";
</script>

<div class="sg" class:focused class:open={expanded}>
  <div class="sg-row">
    <button class="sg-head" onclick={onToggle}>
      <span class="ic">{@html icon}</span>
      <span class="lbl">{label}</span>
      <span class="count">{count.toLocaleString()}</span>
      <span class="chev" aria-hidden="true">⌄</span>
      <span class="state">{expanded ? "Hide" : "Show"}</span>
    </button>
    <button class="doneall" title="Mark this whole group done (e)"
      onclick={(e) => { e.stopPropagation(); onDoneAll?.(); }}>{@html icons.done} Done all</button>
  </div>
  {#if !expanded && senders.length}
    <!-- Compact sender chips with counts (matches the Settings preview). -->
    <div class="chips">
      {#each senders as s}
        <button class="chip" title={s.email} onclick={(e) => { e.stopPropagation(); onSender?.(s.email); }}>
          <span class="av">{initial(s.name || s.email)}</span>
          <span class="nm">{s.name || s.email}</span>
          <span class="c">{s.count}</span>
        </button>
      {/each}
      {#if more > 0}<button class="morechip" onclick={onToggle}>+{more}</button>{/if}
    </div>
  {/if}
</div>

<style>
  .sg { border-bottom: 1px solid var(--border); padding: 8px 14px 10px; }
  .sg.focused { box-shadow: inset 3px 0 0 var(--accent); }
  /* Open state: tint the whole card + accent bar so it's obvious it's expanded. */
  .sg.open { background: color-mix(in srgb, var(--accent) 9%, transparent); box-shadow: inset 3px 0 0 var(--accent); border-radius: var(--radius-sm); }
  .sg-row { display: flex; align-items: center; gap: 8px; }
  .sg-head { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; padding: 4px 2px; }
  /* Hidden until you hover the card (or it's focused), like the row actions. */
  .doneall { flex: none; display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
    padding: 4px 9px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted);
    opacity: 0; transition: opacity 0.12s, background 0.12s, color 0.12s, border-color 0.12s; }
  .sg:hover .doneall, .sg.focused .doneall { opacity: 1; }
  .doneall:hover { background: var(--done); border-color: var(--done); color: #06231a; }
  .sg-head:hover .lbl { color: var(--text); }
  .sg-head:hover .chev { border-color: var(--accent); color: var(--accent); }
  .ic { font-size: 15px; width: 20px; text-align: center; }
  .lbl { font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .sg.open .lbl { color: var(--accent); }
  .count { color: var(--accent); font-weight: 600; font-size: 12px; }
  .state { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); width: 34px; text-align: right; }
  .sg.open .state { color: var(--accent); }
  /* A real, sized chevron in a round chip that flips when open — hard to miss. */
  .chev { margin-left: auto; display: inline-flex; align-items: center; justify-content: center;
    width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--border);
    font-size: 14px; line-height: 1; color: var(--muted); flex: none;
    transition: transform 0.18s ease, color 0.15s, border-color 0.15s, background 0.15s; }
  .sg.open .chev { transform: rotate(180deg); color: #fff; background: var(--accent); border-color: var(--accent); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 0 0 28px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px 3px 3px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); max-width: 220px; }
  .chip:hover { border-color: var(--accent); }
  .av { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; font-size: 10px; font-weight: 700; background: linear-gradient(135deg, var(--accent), #8a6df0); color: #fff; flex: none; }
  .nm { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .c { font-size: 11px; color: var(--muted); }
  .morechip { font-size: 11px; color: var(--muted); padding: 4px 10px; border-radius: 999px; background: var(--surface-2); }
  .morechip:hover { color: var(--text); }
</style>
