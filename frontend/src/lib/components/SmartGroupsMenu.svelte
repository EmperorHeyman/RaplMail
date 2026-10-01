<script>
  // Choose the Smart Inbox groups right where they're used: tick a group to
  // collapse it into a card, untick to keep its mail in the main list, make a
  // new one, or give a custom group a rule. Opened from the list's groups
  // button or by right-clicking a group card. Settings → General keeps the
  // rarer options (order, placement).
  import { onMount } from "svelte";
  import { app, setGroupEnabled, createCustomGroup, openGroupRuleModal } from "../store.svelte.js";
  import { smartGroupList } from "../groups.js";
  import { dismiss } from "../dismiss.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let { x = 0, y = 0, anchor = null, onclose } = $props();

  const groups = $derived(smartGroupList());
  const count = (id) => app.smartGroupData?.[id]?.count || 0;

  let el = $state();
  let pos = $state({ left: x, top: y });
  let newName = $state("");

  onMount(() => {
    const r = el.getBoundingClientRect(), pad = 8;
    pos = { left: Math.max(pad, Math.min(x, window.innerWidth - r.width - pad)),
            top: Math.max(pad, Math.min(y, window.innerHeight - r.height - pad)) };
  });

  function add() {
    const n = newName.trim();
    if (!n) return;
    const id = createCustomGroup(n);
    newName = "";
    onclose?.();
    openGroupRuleModal(id);   // a new group is empty until a rule fills it
  }
  function addRule(id) { onclose?.(); openGroupRuleModal(id); }
  function moreOptions() { onclose?.(); app.settingsTab = "general"; app.view = "settings"; }
</script>

<div bind:this={el} class="sgm" role="menu" tabindex="-1" style="left:{pos.left}px; top:{pos.top}px"
     use:dismiss={{ close: () => onclose?.(), ignore: [anchor] }}
     oncontextmenu={(e) => e.preventDefault()}>
  <div class="head">{t("groups.menuTitle")}</div>
  <p class="hint">{t("groups.menuHint")}</p>
  <div class="rows">
    {#each groups as g (g.id)}
      <div class="row">
        <label>
          <input type="checkbox" checked={!!app.settings.smartGroups?.[g.id]}
            onchange={(e) => setGroupEnabled(g.id, e.currentTarget.checked)} />
          <span class="ic" style="--tone:{g.tone}">{@html g.icon}</span>
          <span class="lbl">{g.label}</span>
          {#if g.custom && !count(g.id)}
            <span class="empty">{t("groups.emptyGroup")}</span>
          {:else}
            <span class="cnt tnum">{count(g.id).toLocaleString()}</span>
          {/if}
        </label>
        {#if g.custom}
          <button class="rulebtn" title={t("groups.addRule")} aria-label={t("groups.addRule")}
            onclick={() => addRule(g.id)}>{@html icons.bolt}</button>
        {/if}
      </div>
    {/each}
  </div>
  <div class="new">
    <input bind:value={newName} placeholder={t("groups.namePlaceholder")}
      onkeydown={(e) => { if (e.key === "Enter") add(); }} />
    <button class="btn" onclick={add} disabled={!newName.trim()}>＋</button>
  </div>
  <button class="more" onclick={moreOptions}>{t("groups.moreOptions")}</button>
</div>

<style>
  /* Solid like the list's right-click menu: --surface is translucent with the
     glass window ground, which let the cards underneath read through. */
  .sgm { position: fixed; z-index: 300; width: 300px; padding: 10px; display: flex; flex-direction: column; gap: 6px;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 2px);
    box-shadow: var(--shadow-lg); animation: pop-in var(--t) var(--ease); }
  .head { font-weight: 650; font-size: 13px; padding: 2px 4px 0; }
  .hint { margin: 0 4px 2px; font-size: 12px; color: var(--muted); line-height: 1.4; }
  .rows { display: flex; flex-direction: column; max-height: 50vh; overflow-y: auto; }
  .row { display: flex; align-items: center; gap: 4px; border-radius: var(--radius-sm); }
  .row:hover { background: var(--surface-3); }
  .row label { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; padding: 5px 6px; cursor: pointer; font-size: 13px; }
  .ic { flex: 0 0 auto; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 7px; font-size: 13px;
    color: var(--tone); background: color-mix(in srgb, var(--tone) 15%, transparent); }
  .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cnt { font-size: 12px; color: var(--faint); }
  .empty { font-size: 11px; color: var(--faint); font-style: italic; }
  .rulebtn { flex: 0 0 auto; width: 26px; height: 26px; display: grid; place-items: center; border-radius: var(--radius-sm); color: var(--muted); }
  .rulebtn:hover { background: var(--surface); color: var(--accent); }
  .new { display: flex; gap: 6px; padding-top: 6px; border-top: 1px solid var(--hairline); }
  .new input { flex: 1; min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; font-size: 13px; }
  .more { align-self: flex-start; font-size: 12px; color: var(--accent); padding: 2px 4px; }
  .more:hover { text-decoration: underline; }
</style>
