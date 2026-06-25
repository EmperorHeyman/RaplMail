<script>
  let { label, icon, count = 0, senders = [], more = 0, expanded = false, focused = false,
        onToggle, onSender } = $props();
  const initial = (s) => (s || "?").trim()[0]?.toUpperCase() || "?";
</script>

<div class="sg" class:focused>
  <button class="sg-head" onclick={onToggle}>
    <span class="ic">{@html icon}</span>
    <span class="lbl">{label}</span>
    <span class="count">{count.toLocaleString()}</span>
    <span class="chev">{expanded ? "▾" : "▸"}</span>
  </button>
  {#if !expanded && senders.length}
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
  .sg-head { display: flex; align-items: center; gap: 9px; width: 100%; padding: 4px 2px; }
  .sg-head:hover .lbl { color: var(--text); }
  .ic { font-size: 15px; width: 20px; text-align: center; }
  .lbl { font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .count { color: var(--accent); font-weight: 600; font-size: 12px; }
  .chev { margin-left: auto; color: var(--faint); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 0 0 28px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px 3px 3px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); max-width: 220px; }
  .chip:hover { border-color: var(--accent); }
  .av { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; font-size: 10px; font-weight: 700; background: linear-gradient(135deg, var(--accent), #8a6df0); color: #fff; flex: none; }
  .nm { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .c { font-size: 11px; color: var(--muted); }
  .morechip { font-size: 11px; color: var(--muted); padding: 4px 10px; border-radius: 999px; background: var(--surface-2); }
  .morechip:hover { color: var(--text); }
</style>
