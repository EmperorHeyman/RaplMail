<script>
  import { fly, fade } from "svelte/transition";
  import {
    app, openCompose, selectUnifiedInbox, selectFolder, selectSnoozed, selectSmartInbox,
    selectUnifiedSent, selectUnifiedDrafts, selectScreener, selectPaperTrail, selectFollowups,
    syncAllAccounts, toggleShowDone, saveSettings, setCategory, aiEnabled, openAiAssistant, markAllRead,
  } from "../store.svelte.js";
  import { icons, folderIcon } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let query = $state("");
  let active = $state(0);
  let inputEl;

  function close() { app.paletteOpen = false; query = ""; active = 0; }
  function run(fn) { close(); fn(); }
  const goMail = (fn) => () => { app.view = "mail"; fn(); };

  // Build the command list from current state.
  const commands = $derived.by(() => {
    const cmds = [
      { icon: icons.compose, label: t("cmd.composeNew"), run: () => openCompose({ to: "", subject: "", html: "" }) },
      { icon: icons.sent, label: t("cmd.mailMerge"), run: () => (app.mailMergeOpen = true) },
      // Navigation — each "Go to" must actually leave the current view.
      { icon: icons.home || icons.unified, label: t("cmd.goHome"), run: () => (app.view = "dashboard") },
      { icon: icons.smart || icons.unified, label: t("cmd.goSmartInbox"), run: goMail(selectSmartInbox) },
      { icon: icons.unified, label: t("cmd.goAllInboxes"), run: goMail(selectUnifiedInbox) },
      { icon: icons.sent, label: t("cmd.goSent"), run: goMail(selectUnifiedSent) },
      { icon: icons.drafts || icons.compose, label: t("cmd.goDrafts"), run: goMail(selectUnifiedDrafts) },
      { icon: icons.snooze, label: t("cmd.goSnoozed"), run: goMail(selectSnoozed) },
      { icon: icons.screener || icons.shield, label: t("cmd.goScreener"), run: goMail(selectScreener) },
      { icon: icons.receipt || icons.tag, label: t("cmd.goPaperTrail"), run: goMail(selectPaperTrail) },
      { icon: icons.done, label: t("cmd.goFollowups"), run: goMail(selectFollowups) },
      { icon: icons.calendar, label: t("cmd.goCalendar"), run: () => (app.view = "calendar") },
      { icon: icons.receipt || icons.tag, label: t("cmd.goTickets"), run: () => (app.view = "tickets") },
      { icon: icons.clock || icons.snooze, label: t("cmd.goScheduled"), run: () => (app.view = "scheduled") },
      { icon: icons.newspaper || icons.tag, label: t("cmd.goNewsfeed"), run: () => (app.view = "newsfeed") },
      // Actions.
      { icon: icons.mail, label: t("cmd.markAllRead"), run: goMail(markAllRead) },
      { icon: icons.sync, label: t("cmd.syncAll"), run: syncAllAccounts },
      { icon: icons.done, label: app.showDone ? t("cmd.hideDone") : t("cmd.showDone"), run: goMail(toggleShowDone) },
      { icon: "↔", label: app.settings.sidebarCollapsed ? t("cmd.expandSidebar") : t("cmd.collapseSidebar"), run: () => saveSettings({ sidebarCollapsed: !app.settings.sidebarCollapsed }) },
      { icon: icons.settings, label: t("cmd.openSettings"), run: () => (app.view = "settings") },
    ];
    // AI commands whenever a provider is usable (cloud key OR keyless Ollama).
    if (aiEnabled()) {
      cmds.splice(2, 0,
        { icon: icons.bolt, label: t("cmd.aiCatchUp"), run: () => (app.aiInboxOpen = true) },
        { icon: icons.chat || icons.bolt, label: t("cmd.aiAssistant"), run: () => openAiAssistant() });
    }
    for (const c of ["primary", "newsletters", "social", "updates", "promotions"]) {
      cmds.push({ icon: icons.tag, label: t("cmd.category", { name: t("cmd.cat." + c) }), run: () => { app.view = "mail"; if (app.selectedKind !== "unified") selectUnifiedInbox(); setCategory(c); } });
    }
    for (const f of app.folders) {
      const acct = app.accounts.find((a) => a.id === f.account_id);
      cmds.push({ icon: folderIcon(f.role), label: `${f.name}`, hint: acct?.email, run: goMail(() => selectFolder(f)) });
    }
    return cmds;
  });

  // Fuzzy match: a term scores high as a substring (earlier = better), lower as
  // an in-order subsequence ("snz" → "Snoozed"), and disqualifies if absent.
  function termScore(term, hay) {
    const at = hay.indexOf(term);
    if (at >= 0) return 100 - Math.min(at, 40);
    let i = 0;
    for (let k = 0; k < hay.length && i < term.length; k++) if (hay[k] === term[i]) i++;
    return i === term.length ? 20 : -1;
  }
  const filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    const terms = q.split(/\s+/);
    return commands
      .map((c) => {
        const hay = (c.label + " " + (c.hint || "")).toLowerCase();
        let score = 0;
        for (const term of terms) { const s = termScore(term, hay); if (s < 0) return null; score += s; }
        return { c, score };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.c);
  });

  $effect(() => { if (active >= filtered.length) active = Math.max(0, filtered.length - 1); });
  $effect(() => { if (app.paletteOpen) queueMicrotask(() => inputEl?.focus()); });

  function onKey(e) {
    if (e.key === "ArrowDown") { active = Math.min(filtered.length - 1, active + 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(0, active - 1); e.preventDefault(); }
    else if (e.key === "Enter") { if (filtered[active]) run(filtered[active].run); }
    else if (e.key === "Escape") { close(); }
  }
</script>

{#if app.paletteOpen}
  <div class="overlay" transition:fade={{ duration: 120 }} onclick={close}>
    <div class="palette" transition:fly={{ y: -12, duration: 150 }} onclick={(e) => e.stopPropagation()}>
      <input bind:this={inputEl} bind:value={query} onkeydown={onKey}
        placeholder={t("cmd.searchPlaceholder")} />
      <ul>
        {#each filtered as c, i}
          <li class:active={i === active} onmousedown={() => run(c.run)} onmouseenter={() => (active = i)}>
            <span class="ic">{@html c.icon}</span>
            <span class="lbl">{c.label}</span>
            {#if c.hint}<span class="hint">{c.hint}</span>{/if}
          </li>
        {/each}
        {#if filtered.length === 0}<li class="none">{t("cmd.noResults")}</li>{/if}
      </ul>
    </div>
  </div>
{/if}

<style>
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); backdrop-filter: blur(2px); z-index: 200; display: flex; justify-content: center; align-items: flex-start; padding-top: 12vh; animation: fade-in var(--t) var(--ease); }
  .palette { width: min(560px, 92vw); max-height: 60vh; display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); overflow: hidden; animation: pop-in var(--t) var(--ease); transform-origin: top center; }
  input { border: none; border-bottom: 1px solid var(--hairline); border-radius: 0; padding: 15px 18px; font-size: 15px; background: transparent; box-shadow: none; }
  input:focus { border-color: var(--hairline); box-shadow: none; }
  ul { list-style: none; margin: 0; padding: 6px; overflow-y: auto; }
  li { display: flex; align-items: center; gap: 11px; padding: 9px 12px; border-radius: var(--radius-sm); cursor: pointer; }
  li.active { background: var(--accent); color: #fff; }
  .ic { width: 20px; text-align: center; }
  .lbl { flex: 1; }
  .hint { font-size: 12px; color: var(--muted); }
  li.active .hint { color: #dbe4ff; }
  .none { color: var(--muted); justify-content: center; cursor: default; }
</style>
