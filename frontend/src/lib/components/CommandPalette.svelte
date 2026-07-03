<script>
  import { fly, fade } from "svelte/transition";
  import {
    app, openCompose, selectUnifiedInbox, selectFolder, selectSnoozed,
    syncAllAccounts, toggleShowDone, saveSettings, setCategory,
  } from "../store.svelte.js";
  import { icons, folderIcon } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let query = $state("");
  let active = $state(0);
  let inputEl;

  function close() { app.paletteOpen = false; query = ""; active = 0; }
  function run(fn) { close(); fn(); }

  // Build the command list from current state.
  const commands = $derived.by(() => {
    const cmds = [
      { icon: icons.compose, label: t("cmd.composeNew"), run: () => openCompose({ to: "", subject: "", html: "" }) },
      { icon: icons.sent, label: t("cmd.mailMerge"), run: () => (app.mailMergeOpen = true) },
      // "Go to" must actually leave the current view (Settings/Calendar/…).
      { icon: icons.unified, label: t("cmd.goAllInboxes"), run: () => { app.view = "mail"; selectUnifiedInbox(); } },
      { icon: icons.snooze, label: t("cmd.goSnoozed"), run: () => { app.view = "mail"; selectSnoozed(); } },
      { icon: icons.sync, label: t("cmd.syncAll"), run: syncAllAccounts },
      { icon: icons.done, label: app.showDone ? t("cmd.hideDone") : t("cmd.showDone"), run: () => { app.view = "mail"; toggleShowDone(); } },
      { icon: "↔", label: app.settings.sidebarCollapsed ? t("cmd.expandSidebar") : t("cmd.collapseSidebar"), run: () => saveSettings({ sidebarCollapsed: !app.settings.sidebarCollapsed }) },
      { icon: icons.settings, label: t("cmd.openSettings"), run: () => (app.view = "settings") },
    ];
    // AI command only when a key is configured.
    if ((app.settings.aiApiKey || "").trim() && app.settings.aiButtons !== false) {
      cmds.splice(2, 0, { icon: icons.bolt, label: t("cmd.aiCatchUp"), run: () => (app.aiInboxOpen = true) });
    }
    for (const c of ["primary", "newsletters", "social", "updates", "promotions"]) {
      cmds.push({ icon: icons.tag, label: t("cmd.category", { name: t("cmd.cat." + c) }), run: () => { app.view = "mail"; if (app.selectedKind !== "unified") selectUnifiedInbox(); setCategory(c); } });
    }
    for (const f of app.folders) {
      const acct = app.accounts.find((a) => a.id === f.account_id);
      cmds.push({ icon: folderIcon(f.role), label: `${f.name}`, hint: acct?.email, run: () => { app.view = "mail"; selectFolder(f); } });
    }
    return cmds;
  });

  const filtered = $derived(
    query.trim() === "" ? commands :
    commands.filter((c) => (c.label + " " + (c.hint || "")).toLowerCase().includes(query.toLowerCase()))
  );

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
