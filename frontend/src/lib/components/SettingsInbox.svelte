<script>
  // Settings → Inbox: how the inbox is organized and read. Split out of the old
  // catch-all General tab. The Smart Inbox groups are ONE list here - tick to
  // group, drag to order, edit your own groups in place - where they used to be
  // three separate sub-sections (which to group, your groups, their order).
  import { onMount } from "svelte";
  import { app, saveSettings, selectSmartInbox, selectUnifiedInbox, selectFolder, setGroupEnabled,
           setSmartNewInline, smartGroupOrder, createCustomGroup, updateCustomGroup, deleteCustomGroup,
           openGroupRuleModal, GROUP_TONES } from "../store.svelte.js";
  import { rules as rulesApi } from "../api.js";
  import { smartGroupMeta, GROUP_ICONS } from "../groups.js";
  import { icons } from "../icons.js";
  import { hourLabel } from "../time.svelte.js";
  import { t } from "../i18n.svelte.js";

  // --- inbox view: the old "Unified inbox" + "Smart Inbox" toggles as one choice
  const view = $derived(app.settings.smartInbox ? "smart" : (app.settings.unifiedInbox ? "all" : "separate"));
  function setView(v) {
    saveSettings({ smartInbox: v === "smart", unifiedInbox: v !== "separate" });
    if (v === "smart") selectSmartInbox();
    else if (v === "all") selectUnifiedInbox();
    else {
      const inbox = app.folders.find((f) => f.role === "inbox");
      if (inbox) selectFolder(inbox);
    }
  }

  // --- groups: one ordered list --------------------------------------------
  const meta = $derived(smartGroupMeta());
  const order = $derived(smartGroupOrder());
  let ruleCounts = $state({});      // custom group id -> rules that fill it
  onMount(async () => {
    try {
      const counts = {};
      for (const r of await rulesApi.list()) {
        if (r.action === "set_group" && r.action_arg) counts[r.action_arg] = (counts[r.action_arg] || 0) + 1;
      }
      ruleCounts = counts;
    } catch {}
  });
  let dragId = $state(null);
  function dragOver(e, targetId) {
    e.preventDefault();
    if (!dragId || dragId === targetId) return;
    const ids = [...order];
    const from = ids.indexOf(dragId), to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    saveSettings({ smartOrder: ids });
  }
  let lookOpen = $state(null);      // custom group whose color/icon picker is open
  let newName = $state("");
  function addGroup() {
    const n = newName.trim();
    if (!n) return;
    const id = createCustomGroup(n);
    newName = "";
    openGroupRuleModal(id);         // a new group is empty until a rule fills it
  }
  function rename(id, current, value) {
    const n = value.trim();
    if (n && n !== current) updateCustomGroup(id, { name: n });
  }
  const customIcon = (id) => (app.settings.customGroups || []).find((g) => g.id === id)?.icon;
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sInbox.viewTitle")}</h3>
    <p class="hint">{t("sInbox.viewHint")}</p>
    <label class="radio">
      <input type="radio" name="iview" checked={view === "smart"} onchange={() => setView("smart")} />
      <div><b>{t("sInbox.viewSmart")}</b><span>{t("sInbox.viewSmartHint")}</span></div>
    </label>
    <label class="radio">
      <input type="radio" name="iview" checked={view === "all"} onchange={() => setView("all")} />
      <div><b>{t("sInbox.viewAll")}</b><span>{t("sInbox.viewAllHint")}</span></div>
    </label>
    <label class="radio">
      <input type="radio" name="iview" checked={view === "separate"} onchange={() => setView("separate")} />
      <div><b>{t("sInbox.viewSeparate")}</b><span>{t("sInbox.viewSeparateHint")}</span></div>
    </label>
  </section>

  {#if view === "smart"}
    <section class="card">
      <h3>{t("groups.menuTitle")}</h3>
      <label class="check">
        <input type="checkbox" checked={app.settings.smartNewInline !== false} onchange={(e) => setSmartNewInline(e.currentTarget.checked)} />
        <div><b>{t("groups.newInline")}</b><span>{t("groups.newInlineHint")}</span></div>
      </label>
      <p class="hint" style="margin-top:6px">{t("sInbox.groupsHint")}</p>
      <div class="glist">
        {#each order as id (id)}
          {@const g = meta[id]}
          {#if g}
            <div class="grow" class:dragging={dragId === id} draggable="true" role="listitem"
              ondragstart={() => (dragId = id)} ondragend={() => (dragId = null)}
              ondragover={(e) => dragOver(e, id)}>
              <span class="handle" title={t("sInbox.dragTip")} aria-hidden="true">⠿</span>
              <input type="checkbox" checked={!!app.settings.smartGroups?.[id]} aria-label={g.label}
                onchange={(e) => setGroupEnabled(id, e.currentTarget.checked)} />
              {#if g.custom}
                <button class="gic" style="--tone:{g.tone}" title={t("groups.changeLook")} aria-label={t("groups.changeLook")}
                  onclick={() => (lookOpen = lookOpen === id ? null : id)}>{@html g.icon}</button>
                <input class="gname" value={g.label} aria-label={t("groups.name")}
                  onchange={(e) => rename(id, g.label, e.currentTarget.value)}
                  onkeydown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                <span class="grules" class:none={!ruleCounts[id]}>{ruleCounts[id] ? t("groups.ruleCount", { n: ruleCounts[id] }) : t("groups.noRules")}</span>
                <button class="mini" title={t("groups.addRule")} aria-label={t("groups.addRule")} onclick={() => openGroupRuleModal(id)}>{@html icons.bolt}</button>
                <button class="mini danger" title={t("groups.delete")} aria-label={t("groups.delete")} onclick={() => deleteCustomGroup(id)}>{@html icons.trash}</button>
              {:else}
                <span class="gic" style="--tone:{g.tone}">{@html g.icon}</span>
                <span class="glabel">{g.label}</span>
              {/if}
            </div>
            {#if g.custom && lookOpen === id}
              <div class="glook">
                <div class="tones">
                  {#each GROUP_TONES as c}
                    <button class="tone" class:on={g.tone === c} style="--tone:{c}" aria-label={c}
                      onclick={() => updateCustomGroup(id, { tone: c })}></button>
                  {/each}
                </div>
                <div class="icopts">
                  {#each GROUP_ICONS as ic}
                    <button class="icopt" class:on={customIcon(id) === ic} style="--tone:{g.tone}" aria-label={ic}
                      onclick={() => updateCustomGroup(id, { icon: ic })}>{@html icons[ic]}</button>
                  {/each}
                </div>
              </div>
            {/if}
          {/if}
        {/each}
      </div>
      <div class="gnew">
        <input bind:value={newName} placeholder={t("groups.namePlaceholder")}
          onkeydown={(e) => { if (e.key === "Enter") addGroup(); }} />
        <button class="btn" onclick={addGroup} disabled={!newName.trim()}>＋ {t("groups.create")}</button>
      </div>
    </section>
  {/if}

  <section class="card">
    <h3>{t("sInbox.readingTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.openNextOnDone} onchange={(e) => saveSettings({ openNextOnDone: e.currentTarget.checked })} />
      <div><b>{t("sInbox.openNext")}</b><span>{t("sInbox.openNextHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.threading} onchange={(e) => saveSettings({ threading: e.currentTarget.checked })} />
      <div><b>{t("sInbox.threading")}</b><span>{t("sInbox.threadingHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.collapseQuotes !== false} onchange={(e) => saveSettings({ collapseQuotes: e.currentTarget.checked })} />
      <div><b>{t("sInbox.collapseQuotes")}</b><span>{t("sInbox.collapseQuotesHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.highlightCode !== false} onchange={(e) => saveSettings({ highlightCode: e.currentTarget.checked })} />
      <div><b>{t("sInbox.highlightCode")}</b><span>{t("sInbox.highlightCodeHint")}</span></div>
    </label>
    <label class="inline">{t("sInbox.followup")}
      <select value={app.settings.followupDays} onchange={(e) => saveSettings({ followupDays: Number(e.currentTarget.value) })}>
        {#each [2, 3, 5, 7] as d}<option value={d}>{t("sInbox.followupDays", { n: d })}</option>{/each}
      </select>
      {t("sInbox.followupSuffix")}
    </label>
  </section>

  <section class="card">
    <h3>{t("sInbox.viewsTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.showNewsletterFeed !== false} onchange={(e) => saveSettings({ showNewsletterFeed: e.currentTarget.checked })} />
      <div><b>{t("nav.newsletterFeed")}</b><span>{t("sInbox.newsletterFeedHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.showPaperTrail !== false} onchange={(e) => saveSettings({ showPaperTrail: e.currentTarget.checked })} />
      <div><b>{t("nav.paperTrail")}</b><span>{t("sInbox.paperTrailHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("sInbox.snoozeTitle")}</h3>
    <p class="hint">{t("sInbox.snoozeHint")}</p>
    <label class="inline">{t("sInbox.laterToday")}
      <select value={app.settings.scheduleLaterHours ?? 3} onchange={(e) => saveSettings({ scheduleLaterHours: Number(e.currentTarget.value) })}>
        {#each [1, 2, 3, 4, 6, 8] as h}<option value={h}>{h} {t("sInbox.hoursShort")}</option>{/each}
      </select>
    </label>
    <label class="inline">{t("sInbox.morning")}
      <select value={app.settings.scheduleMorningHour ?? 9} onchange={(e) => saveSettings({ scheduleMorningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({ length: 24 }, (_, i) => i) as h}<option value={h}>{hourLabel(h)}</option>{/each}
      </select>
    </label>
    <label class="inline">{t("sInbox.evening")}
      <select value={app.settings.scheduleEveningHour ?? 18} onchange={(e) => saveSettings({ scheduleEveningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({ length: 24 }, (_, i) => i) as h}<option value={h}>{hourLabel(h)}</option>{/each}
      </select>
    </label>
    <p class="hint" style="margin-top:10px">{t("sInbox.exactTime")}</p>
    <div class="local-note">{@html icons.warning || ""}<span>{t("schedule.localOnly")}</span></div>
  </section>
</div>

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .radio, .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .radio div, .check div { display: flex; flex-direction: column; gap: 2px; }
  .radio span, .check span { color: var(--muted); font-size: 12px; }
  .radio input, .check input { margin-top: 3px; }
  .inline { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: var(--muted); font-size: 13px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }

  /* The one groups list. */
  .glist { display: flex; flex-direction: column; gap: 4px; }
  .grow { display: flex; align-items: center; gap: 9px; padding: 5px 8px; border-radius: var(--radius-sm);
    background: var(--surface-2); border: 1px solid var(--hairline); }
  .grow.dragging { opacity: 0.5; }
  .handle { color: var(--faint); cursor: grab; font-size: 14px; padding: 0 2px; user-select: none; }
  .gic { flex: none; width: 26px; height: 26px; display: grid; place-items: center; border-radius: 50%; font-size: 13px;
    color: var(--tone); background: color-mix(in srgb, var(--tone) 16%, transparent); }
  button.gic:hover { background: color-mix(in srgb, var(--tone) 26%, transparent); }
  .glabel { flex: 1; font-size: 13px; }
  .gname { flex: 1; min-width: 0; padding: 5px 8px; font-size: 13px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .grules { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .grules.none { color: var(--faint); }
  .mini { flex: none; width: 28px; height: 28px; display: grid; place-items: center; border-radius: var(--radius-sm); color: var(--muted); }
  .mini:hover { background: var(--hover); color: var(--accent); }
  .mini.danger:hover { color: var(--danger); }
  .glook { display: flex; flex-direction: column; gap: 8px; margin: 0 0 4px 52px; padding: 10px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .tones, .icopts { display: flex; flex-wrap: wrap; gap: 6px; }
  .tone { width: 20px; height: 20px; border-radius: 50%; background: var(--tone); border: 2px solid transparent; }
  .tone.on { border-color: var(--text); }
  .icopt { width: 28px; height: 28px; display: grid; place-items: center; border-radius: var(--radius-sm); color: var(--muted); font-size: 15px; }
  .icopt:hover { background: var(--hover); color: var(--text); }
  .icopt.on { color: var(--tone); background: color-mix(in srgb, var(--tone) 15%, transparent); }
  .gnew { display: flex; gap: 8px; margin-top: 10px; }
  .gnew input { flex: 1; }

  .local-note { display: flex; gap: 9px; align-items: flex-start; margin-top: 12px; padding: 11px 13px;
    background: color-mix(in srgb, var(--warning) 10%, transparent); border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border));
    border-radius: var(--radius-sm); font-size: 12.5px; line-height: 1.5; color: var(--text); }
  .local-note :global(svg) { width: 16px; height: 16px; flex: none; margin-top: 1px; color: var(--warning); }
</style>
