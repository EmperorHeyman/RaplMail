<script>
  /* Hover peek for a Smart Inbox group card.
     Hovering a category shows what just landed in it - the newest mail in full,
     then the next few as one line each - so you can tell whether a group is
     worth opening without expanding it and losing your place in the list.

     Rendered as ONE instance owned by the list (not one per card): the panel is
     position:fixed and re-anchored on each hover, so a mailbox with a dozen
     groups doesn't carry a dozen idle popovers in the DOM. */
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { app } from "../store.svelte.js";
  import { listTime, relativeTime } from "../time.svelte.js";

  let { rect, label, icon, tone = "", recent = [], count = 0, newCount = 0,
        onopen, onenter, onleave } = $props();

  const newest = $derived(recent[0] || null);
  const rest = $derived(recent.slice(1, 4));
  const fmtTime = (iso) => (app.settings.relativeTime ? relativeTime(iso) : listTime(iso));

  /* Anchor beside the card: to its right when there's room, otherwise to its
     left, and vertically clamped to the viewport. Measured after paint so the
     panel's real height is known. */
  function place(node) {
    const apply = (r) => {
      if (!r) return;
      const pad = 10;
      const box = node.getBoundingClientRect();
      const vw = window.innerWidth, vh = window.innerHeight;
      let left = r.right + pad;
      if (left + box.width > vw - pad) left = r.left - box.width - pad;
      if (left < pad) left = Math.max(pad, vw - box.width - pad);
      let top = r.top - 6;
      if (top + box.height > vh - pad) top = vh - box.height - pad;
      if (top < pad) top = pad;
      node.style.left = `${Math.round(left)}px`;
      node.style.top = `${Math.round(top)}px`;
      node.style.visibility = "visible";
    };
    requestAnimationFrame(() => apply(rect));
    return { update: (r) => requestAnimationFrame(() => apply(r)) };
  }
</script>

<div class="peek" style={tone ? `--tone:${tone}` : ""} use:place={rect}
     onmouseenter={onenter} onmouseleave={onleave} role="tooltip">
  <div class="phead">
    <span class="pic">{@html icon}</span>
    <span class="plabel">{label}</span>
    {#if newCount > 0}<span class="pnew tnum">{t("list.newCount", { n: newCount })}</span>{/if}
    <span class="pcount tnum">{count.toLocaleString()}</span>
  </div>

  {#if newest}
    <button class="lead" class:unread={!newest.is_seen} onclick={() => onopen?.(newest)}>
      <span class="l-top">
        <span class="l-from">{newest.name || newest.email}</span>
        <span class="l-time">{fmtTime(newest.date)}</span>
      </span>
      <span class="l-subject">{newest.subject}</span>
      {#if newest.snippet}<span class="l-snippet">{newest.snippet}</span>{/if}
    </button>

    {#if rest.length}
      <div class="more">
        {#each rest as m (m.id ?? m.subject)}
          <button class="mrow" class:unread={!m.is_seen} onclick={() => onopen?.(m)}>
            <span class="m-dot" class:on={!m.is_seen}></span>
            <span class="m-from">{m.name || m.email}</span>
            <span class="m-subject">{m.subject}</span>
            <span class="m-time">{fmtTime(m.date)}</span>
          </button>
        {/each}
      </div>
    {/if}
  {:else}
    <div class="pempty">{@html icons.done} {t("list.peekEmpty")}</div>
  {/if}
</div>

<style>
  .peek {
    position: fixed; z-index: 280; visibility: hidden;
    width: 340px; max-width: calc(100vw - 24px);
    background: var(--surface-2); border: 1px solid var(--hairline);
    border-radius: var(--radius); box-shadow: var(--shadow-lg);
    padding: 9px; display: flex; flex-direction: column; gap: 7px;
    animation: peek-in var(--t) var(--ease);
  }
  @keyframes peek-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }

  .phead { display: flex; align-items: center; gap: 8px; padding: 1px 3px 0; min-width: 0; }
  .pic { display: grid; place-items: center; width: 22px; height: 22px; flex: none; border-radius: 7px;
    background: color-mix(in srgb, var(--tone, var(--accent)) 18%, transparent); color: var(--tone, var(--accent)); }
  .pic :global(svg) { width: 13px; height: 13px; }
  .plabel { flex: 1; min-width: 0; font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pnew { flex: none; font-size: 10px; font-weight: 700; color: #fff; background: var(--accent); border-radius: 999px; padding: 2px 7px; }
  .pcount { flex: none; font-size: 11px; font-weight: 600; color: var(--faint); }

  /* The newest mail, in full - the reason to hover. */
  .lead { display: flex; flex-direction: column; gap: 3px; text-align: left; width: 100%;
    padding: 9px 10px; border-radius: 9px; background: var(--surface);
    border: 1px solid transparent; transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .lead:hover { background: var(--hover); border-color: var(--border); }
  .l-top { display: flex; justify-content: space-between; gap: 8px; min-width: 0; }
  .l-from { font-size: 12.5px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .l-time { flex: none; font-size: 11px; color: var(--faint); }
  .l-subject { font-size: 13px; color: var(--text); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .l-snippet { font-size: 11.5px; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .lead.unread .l-from, .lead.unread .l-subject { font-weight: 700; }

  /* Then one line each, so the panel stays a glance not a second list. */
  .more { display: flex; flex-direction: column; }
  .mrow { display: flex; align-items: center; gap: 7px; width: 100%; text-align: left;
    padding: 5px 10px; border-radius: 7px; min-width: 0;
    transition: background var(--t-fast) var(--ease); }
  .mrow:hover { background: var(--hover); }
  .m-dot { flex: none; width: 5px; height: 5px; border-radius: 50%; background: transparent; }
  .m-dot.on { background: var(--accent); }
  .m-from { flex: none; max-width: 33%; font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .m-subject { flex: 1; min-width: 0; font-size: 12px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .m-time { flex: none; font-size: 10.5px; color: var(--faint); }
  .mrow.unread .m-subject { font-weight: 650; }

  .pempty { display: flex; align-items: center; gap: 7px; padding: 8px 10px; font-size: 12.5px; color: var(--muted); }
  .pempty :global(svg) { width: 14px; height: 14px; color: var(--done); }

  @media (prefers-reduced-motion: reduce) { .peek { animation: none; } }
</style>
