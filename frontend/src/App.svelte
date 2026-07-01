<script>
  import { onMount } from "svelte";
  import { app, refreshVault, loadAccountsAndFolders, startEvents, recategorizeOnce, applyTheme, setWorkspace, openCompose, saveSettings, initSettings, selectSmartInbox, selectUnifiedInbox, selectSnoozed, selectPaperTrail, selectFollowups, syncAllAccounts, syncTrayPref, startCalendarServices, runUndo, hasUndo, recoverPendingSend } from "./lib/store.svelte.js";
  import { openExternal } from "./lib/api.js";
  import { keyCombo } from "./lib/keys.js";
  import { icons } from "./lib/icons.js";
  import CommandPalette from "./lib/components/CommandPalette.svelte";
  import VaultGate from "./lib/components/VaultGate.svelte";
  import Sidebar from "./lib/components/Sidebar.svelte";
  import MailList from "./lib/components/MailList.svelte";
  import Reader from "./lib/components/Reader.svelte";
  import Compose from "./lib/components/Compose.svelte";
  import MailMerge from "./lib/components/MailMerge.svelte";
  import AiInbox from "./lib/components/AiInbox.svelte";
  import RuleModal from "./lib/components/RuleModal.svelte";
  import ConfirmDialog from "./lib/components/ConfirmDialog.svelte";
  import Settings from "./lib/components/Settings.svelte";
  import ScheduledView from "./lib/components/ScheduledView.svelte";
  import NewsletterFeed from "./lib/components/NewsletterFeed.svelte";
  import CalendarView from "./lib/components/CalendarView.svelte";
  import TicketsView from "./lib/components/TicketsView.svelte";
  import Dashboard from "./lib/components/Dashboard.svelte";
  import ShortcutsOverlay from "./lib/components/ShortcutsOverlay.svelte";
  import Toast from "./lib/components/Toast.svelte";
  import SendingIndicator from "./lib/components/SendingIndicator.svelte";

  // When opened as a separate compose window (openCompose with "window" mode),
  // render only the compose surface.
  const composeWindow = typeof location !== "undefined" && location.hash === "#compose";

  let bootError = $state("");
  let shortcutsOpen = $state(false);

  // Customize mode: drag column dividers to resize (locked unless enabled).
  // During a drag we update a transient width (cheap, rAF-throttled) and only
  // persist to settings ONCE on release — calling saveSettings() per pointermove
  // (full settings reassign + localStorage write + app-wide reactivity) made the
  // resize unusably laggy.
  let resizing = $state(null);
  let rafId = 0;
  let lastX = 0;
  let dragW = $state({ sidebar: null, list: null });
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // Effective sidebar width — collapsed rail is a fixed 60px regardless of the stored width.
  const effSidebarW = () => (app.settings.sidebarCollapsed ? 60 : (dragW.sidebar ?? app.settings.sidebarWidth));
  function startResize(which, e) {
    resizing = which; e.preventDefault();
    window.addEventListener("pointermove", onResize);
    window.addEventListener("pointerup", endResize, { once: true });
  }
  function onResize(e) {
    lastX = e.clientX;
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      if (resizing === "sidebar") dragW.sidebar = clamp(lastX, 150, 460);
      else if (resizing === "list") dragW.list = clamp(lastX - effSidebarW(), 280, 760);
    });
  }
  function endResize() {
    window.removeEventListener("pointermove", onResize);
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    const patch = {};
    if (dragW.sidebar != null) patch.sidebarWidth = dragW.sidebar;
    if (dragW.list != null) patch.listWidth = dragW.list;
    if (Object.keys(patch).length) saveSettings(patch);
    dragW = { sidebar: null, list: null };
    resizing = null;
  }

  function isTyping(e) {
    const t = e.target;
    return t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || (t && t.isContentEditable);
  }

  async function boot() {
    bootError = "";
    // Retry briefly: the bundled backend can take a moment to come up.
    for (let attempt = 0; attempt < 24; attempt++) {
      try {
        await refreshVault();
        return;
      } catch (e) {
        await new Promise((r) => setTimeout(r, 500));
        if (attempt === 23) bootError = e?.message || "Couldn't reach the RaplMail backend.";
      }
    }
  }

  onMount(() => {
    applyTheme();
    initSettings();  // pull persisted settings from the backend file
    boot();
    // Re-evaluate auto day/night theme periodically.
    const t = setInterval(() => { if (app.settings.themeMode === "auto") applyTheme(); }, 600000);
    return () => clearInterval(t);
  });

  // Chord ("g" then a letter) navigation.
  let chordArmed = false;
  let chordTimer = null;
  const goInbox = () => { app.view = "mail"; (app.settings.smartInbox ? selectSmartInbox : selectUnifiedInbox)(); };
  const chordTargets = {
    i: goInbox,
    s: () => { app.view = "mail"; selectSnoozed(); },
    c: () => (app.view = "calendar"),
    t: () => (app.view = "scheduled"),
    f: () => { app.view = "mail"; selectFollowups(); },
    n: () => (app.view = "newsfeed"),
    p: () => { app.view = "mail"; selectPaperTrail(); },
    a: () => { app.view = "settings"; },
  };

  function onGlobalKey(e) {
    if (composeWindow) return;
    const kb = app.settings.keybinds || {};
    // Ctrl/Cmd+R → check for new mail (override the webview's reload-the-app
    // default). Always block the reload, but don't trigger a sync mid-typing.
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "r" || e.key === "R")) {
      e.preventDefault();
      if (!isTyping(e)) syncAllAccounts();
      return;
    }
    // Ctrl/Cmd+Z → undo the most recent reversible action (done/snooze/etc.).
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key === "z" || e.key === "Z") && !isTyping(e)) {
      if (hasUndo()) { e.preventDefault(); runUndo(); }
      return;
    }
    const combo = keyCombo(e);
    if (!combo) return;

    // Chord shortcuts: press "g" then a letter to jump between views.
    if (chordArmed && !isTyping(e)) {
      chordArmed = false;
      const go = chordTargets[e.key.toLowerCase()];
      if (go) { go(); e.preventDefault(); return; }
    }
    if (combo === "g" && !isTyping(e)) {
      chordArmed = true;
      clearTimeout(chordTimer);
      chordTimer = setTimeout(() => (chordArmed = false), 1200);
      e.preventDefault();
      return;
    }
    // Ctrl+1..9 switch workspace, Ctrl+0 = All (fixed).
    if ((e.ctrlKey || e.metaKey) && /^[0-9]$/.test(e.key)) {
      const ws = app.settings.workspaces || [];
      if (e.key === "0") { setWorkspace(null); e.preventDefault(); }
      else { const w = ws[Number(e.key) - 1]; if (w) { setWorkspace(w.id); e.preventDefault(); } }
      return;
    }
    if (combo === kb.palette) { app.paletteOpen = !app.paletteOpen; e.preventDefault(); }
    else if (combo === kb.help && !isTyping(e)) { shortcutsOpen = !shortcutsOpen; e.preventDefault(); }
    else if (combo === kb.compose && !isTyping(e)) { openCompose({ to: "", subject: "", html: "" }); e.preventDefault(); }
  }

  // Open any external (http/https) link in the OS browser — the desktop webview
  // doesn't navigate target=_blank anchors on its own.
  function onDocClick(e) {
    const a = e.target?.closest?.("a[href]");
    if (!a) return;
    const href = (a.getAttribute("href") || "").trim();
    if (/^https?:\/\//i.test(href)) { e.preventDefault(); openExternal(href); }
  }

  // Once unlocked, load data and open the live event stream. Settings are pulled
  // first so the default view honors Smart Inbox (avoids defaulting to All Inboxes).
  let _booted = false;
  $effect(() => {
    if (app.vault.unlocked && !_booted) {
      _booted = true;
      (async () => { await initSettings(); syncTrayPref(); await loadAccountsAndFolders(); startCalendarServices(); })();
      startEvents();
      recategorizeOnce();
      recoverPendingSend();  // redeliver a send interrupted by a quit mid-undo-countdown
    }
  });
</script>

{#if composeWindow}
  <Compose standalone />
{:else if !app.vault.ready}
  <div class="boot">
    {#if bootError}
      <div class="boot-err">
        <div class="big">{@html icons.warning}</div>
        <p>Couldn't reach the RaplMail backend.</p>
        <code>{bootError}</code>
        <button class="btn primary" onclick={boot}>Retry</button>
      </div>
    {:else}
      Starting RaplMail…
    {/if}
  </div>
{:else if !app.vault.unlocked}
  <VaultGate />
{:else}
  <div class="app" class:customizing={app.customizing} class:resizing={!!resizing}
       style="--sidebar-w: {app.settings.sidebarCollapsed ? '60px' : (dragW.sidebar ?? app.settings.sidebarWidth) + 'px'}; --list-w: {(dragW.list ?? app.settings.listWidth)}px">
    <Sidebar />
    {#if app.view === "settings"}
      <Settings />
    {:else if app.view === "scheduled"}
      <ScheduledView />
    {:else if app.view === "newsfeed"}
      <NewsletterFeed />
    {:else if app.view === "calendar"}
      <CalendarView />
    {:else if app.view === "tickets"}
      <TicketsView />
    {:else if app.view === "dashboard"}
      <Dashboard />
    {:else}
      <MailList />
      <Reader />
    {/if}

    {#if app.customizing}
      {#if !app.settings.sidebarCollapsed}
        <div class="resizer" style="left: var(--sidebar-w)" title="Drag to resize the sidebar"
             onpointerdown={(e) => startResize("sidebar", e)}></div>
      {/if}
      {#if app.view === "mail"}
        <div class="resizer" style="left: calc(var(--sidebar-w) + var(--list-w))" title="Drag to resize the message list"
             onpointerdown={(e) => startResize("list", e)}></div>
      {/if}
      <div class="customize-banner">
        {@html icons.customize} Customize mode — drag the dividers to resize columns.
        <button class="btn primary sm" onclick={() => (app.customizing = false)}>Done</button>
      </div>
    {/if}
  </div>
{/if}

{#if app.composing}
  <Compose />
{/if}
{#if app.mailMergeOpen}
  <MailMerge />
{/if}
{#if app.aiInboxOpen}
  <AiInbox />
{/if}
{#if app.ruleModal}
  <RuleModal />
{/if}
<SendingIndicator />
<svelte:window on:keydown={onGlobalKey} />
<svelte:document on:click={onDocClick} />
{#if !composeWindow}
  <CommandPalette />
  <ShortcutsOverlay open={shortcutsOpen} onclose={() => (shortcutsOpen = false)} />
{/if}
<ConfirmDialog />
<Toast />

<style>
  .app {
    display: grid;
    grid-template-columns: var(--sidebar-w) var(--list-w) 1fr;
    height: 100%;
    position: relative;
  }
  .app.customizing { user-select: none; }
  /* While dragging a divider, stop the message iframe (and other panes) from
     capturing pointer events — otherwise the drag stalls over the reader. */
  .app.resizing :global(iframe) { pointer-events: none; }
  .app.resizing { cursor: col-resize; }
  .resizer {
    position: absolute; top: 0; bottom: 0; width: 9px; margin-left: -4px;
    cursor: col-resize; z-index: 120;
    background: linear-gradient(90deg, transparent 40%, var(--accent) 40%, var(--accent) 60%, transparent 60%);
    opacity: 0.55; transition: opacity 0.12s;
  }
  .resizer:hover { opacity: 1; }
  .customize-banner {
    position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
    z-index: 130; display: flex; align-items: center; gap: 12px;
    background: var(--surface-3); border: 1px solid var(--border); box-shadow: var(--shadow);
    padding: 9px 9px 9px 16px; border-radius: 999px; font-size: 13px; color: var(--text);
  }
  .customize-banner .sm { padding: 4px 12px; font-size: 12px; }
  .boot {
    height: 100%;
    display: grid;
    place-items: center;
    color: var(--muted);
  }
  .boot-err { display: flex; flex-direction: column; gap: 12px; align-items: center; text-align: center; max-width: 460px; }
  .boot-err .big { font-size: 40px; }
  .boot-err code { font-size: 12px; color: var(--danger); background: var(--surface-2); padding: 8px 12px; border-radius: 6px; word-break: break-all; }
  /* Full-width views (settings, calendar, scheduled, newsletter feed) span the
     remaining width instead of sitting in the message-list column. */
  :global(.app:has(.settings)),
  :global(.app:has(.cal)),
  :global(.app:has(.sched)),
  :global(.app:has(.feed)),
  :global(.app:has(.tickets)),
  :global(.app:has(.dash)) {
    grid-template-columns: var(--sidebar-w) 1fr;
  }
</style>
