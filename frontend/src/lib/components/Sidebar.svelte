<script>
  import { flip } from "svelte/animate";
  import { slide } from "svelte/transition";
  import { app, selectFolder, selectUnifiedInbox, selectSmartInbox, selectSnoozed, selectScreener, selectPaperTrail, selectFollowups, saveSettings, notify, openCompose, loadAccountsAndFolders, setWorkspace, workspaceAccountIds, runSearch, removeSavedSearch, retryQueue, selectUnifiedSent, selectUnifiedDrafts, confirmDialog, syncAllAccounts, moveMessages } from "../store.svelte.js";
  import { accounts as accountsApi, folders as foldersApi, messages as messagesApi } from "../api.js";
  import { icons, folderIcon } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  // Failed/queued action details (so you can see *what* failed and why).
  let queueOpen = $state(false);
  let queueList = $state([]);
  async function loadQueue() { try { queueList = await messagesApi.queueItems(); } catch {} }
  async function toggleQueue() { queueOpen = !queueOpen; if (queueOpen) await loadQueue(); }
  async function discardItem(id) { try { await messagesApi.queueDiscard(id); await loadQueue(); } catch {} }

  const ROLE_ORDER = { inbox: 0, drafts: 1, sent: 2, archive: 3, junk: 4, trash: 5, other: 6 };
  const CORE = new Set(["inbox", "sent"]);

  let manage = $state(false);
  let dragId = $state(null);
  // Folder that a dragged message is hovering over (drag-a-message-to-move). Only
  // same-account folders are valid targets (an IMAP move stays within one account).
  let dropTarget = $state(null);
  let dropBad = $state(null);   // folder a drag is over but can't land on (wrong account)
  // A message move stays within one account (IMAP). Compare ids as strings so a
  // number/string mismatch never silently blocks the drop, and allow it when the
  // source account is unknown (the backend re-validates and skips cross-account).
  const sameAcct = (f) => app.dragAccountId == null || String(app.dragAccountId) === String(f.account_id);
  const canDropMsg = (f) => app.dragMessageIds.length > 0 && !manage && sameAcct(f);
  function onFolderDrop(e, f) {
    e.preventDefault();
    dropTarget = null; dropBad = null;
    if (!canDropMsg(f)) return;
    moveMessages(app.dragMessageIds, f);
    app.dragMessageIds = []; app.dragAccountId = null;
  }
  let creatingFor = $state(null);
  let newFolderName = $state("");
  let rootCreating = $state(false);
  let rootName = $state("");
  let rootAccount = $state(null);

  async function rootCreate() {
    const name = rootName.trim();
    const aid = rootAccount ?? app.accounts[0]?.id;
    if (!name || !aid) { notify(t("nav.pickAccountAndName"), "error"); return; }
    try {
      await foldersApi.create(aid, name);
      notify(t("nav.creatingFolder", { name }));
      rootCreating = false; rootName = "";
      setTimeout(loadAccountsAndFolders, 1500);
    } catch (e) { notify(e.message, "error"); }
  }

  const collapsed = $derived(app.settings.sidebarCollapsed);
  const hasInbox = $derived(app.folders.some((f) => f.role === "inbox"));
  // Total unread across all inboxes - badge on the Smart Inbox / All Inboxes item.
  const inboxUnread = $derived(
    app.folders.filter((f) => f.role === "inbox").reduce((n, f) => n + (f.unread_count || 0), 0)
  );

  // Nav items grouped into sections: primary (no label) / Mail / Tools.
  // Order inside a section is still user-draggable (settings.specialOrder).
  const navSections = $derived.by(() => {
    const s = app.settings;
    const primary = [];
    if (s.dashboard !== false)
      primary.push({ id: "home", icon: icons.home || icons.smart, label: t("nav.home"), active: app.view === "dashboard", run: () => { app.view = "dashboard"; } });
    if (hasInbox && s.smartInbox)
      primary.push({ id: "smart", icon: icons.smart, label: t("nav.smartInbox"), badge: inboxUnread, active: app.selectedKind === "smart" && app.view === "mail", run: () => { app.view = "mail"; selectSmartInbox(); } });
    else if (hasInbox && s.unifiedInbox)
      primary.push({ id: "unified", icon: icons.unified, label: t("nav.allInboxes"), badge: inboxUnread, active: app.selectedKind === "unified" && app.view === "mail", run: () => { app.view = "mail"; selectUnifiedInbox(); } });
    if (s.screener)
      primary.push({ id: "screener", icon: icons.screener, label: t("nav.screener"), active: app.selectedKind === "screener" && app.view === "mail", run: () => { app.view = "mail"; selectScreener(); } });

    const mail = [
      { id: "drafts", icon: icons.drafts || icons.edit, label: t("nav.drafts"), active: app.selectedKind === "drafts" && app.view === "mail", run: () => { app.view = "mail"; selectUnifiedDrafts(); } },
      { id: "allsent", icon: icons.sent, label: t("nav.sent"), active: app.selectedKind === "sent" && app.view === "mail", run: () => { app.view = "mail"; selectUnifiedSent(); } },
      { id: "snoozed", icon: icons.snooze, label: t("nav.snoozed"), active: app.selectedKind === "snoozed" && app.view === "mail", run: () => { app.view = "mail"; selectSnoozed(); } },
      { id: "followups", icon: icons.alarm, label: t("nav.followups"), active: app.selectedKind === "followups" && app.view === "mail", run: () => { app.view = "mail"; selectFollowups(); } },
    ];
    if (s.showPaperTrail !== false)
      mail.push({ id: "papertrail", icon: icons.receipt, label: t("nav.paperTrail"), active: app.selectedKind === "papertrail" && app.view === "mail", run: () => { app.view = "mail"; selectPaperTrail(); } });

    const tools = [
      { id: "calendar", icon: icons.calendar, label: t("nav.calendar"), active: app.view === "calendar", run: () => { app.view = "calendar"; } },
      { id: "tickets", icon: icons.receipt, label: t("nav.tickets"), active: app.view === "tickets", run: () => { app.view = "tickets"; } },
      { id: "scheduled", icon: icons.clock, label: t("nav.scheduled"), active: app.view === "scheduled", run: () => { app.view = "scheduled"; } },
    ];
    if (s.showNewsletterFeed !== false)
      tools.push({ id: "newsfeed", icon: icons.newspaper, label: t("nav.newsletterFeed"), active: app.view === "newsfeed", run: () => { app.view = "newsfeed"; } });

    const order = s.specialOrder || [];
    const rank = (id) => { const i = order.indexOf(id); return i < 0 ? 999 : i; };
    const sort = (arr) => arr.sort((a, b) => rank(a.id) - rank(b.id));
    return [
      { key: "primary", label: null, items: sort(primary) },
      { key: "mail", label: t("nav.mail"), items: sort(mail) },
      { key: "tools", label: t("nav.tools"), items: sort(tools) },
    ].filter((sec) => sec.items.length);
  });

  let dragSpecial = $state(null); // { id, sec }
  function reorderSpecial(targetId, sec) {
    if (!dragSpecial || dragSpecial.sec !== sec || dragSpecial.id === targetId) return;
    const section = navSections.find((x) => x.key === sec);
    if (!section) return;
    const ids = section.items.map((i) => i.id);
    const from = ids.indexOf(dragSpecial.id), to = ids.indexOf(targetId);
    if (from < 0 || to < 0 || from === to) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    // Persist the full order: other sections keep their relative ranks.
    const rest = (app.settings.specialOrder || []).filter((id) => !ids.includes(id));
    saveSettings({ specialOrder: [...ids, ...rest] });
  }

  // Formatted keyboard hint for Compose (e.g. "Ctrl+n" → "Ctrl N").
  const composeHint = $derived.by(() => {
    const c = app.settings.keybinds?.compose || "";
    return c ? c.split("+").map((p) => (p.length === 1 ? p.toUpperCase() : p)).join(" ") : "";
  });

  function orderKey(f) {
    const o = app.settings.folderOrder[f.id];
    return o !== undefined ? o : 100 + (ROLE_ORDER[f.role] ?? 9);
  }
  const grouped = $derived(
    app.accounts
      .filter((a) => { const ids = workspaceAccountIds(); return !ids || ids.includes(a.id); })
      .map((a) => ({
        account: a,
        folders: app.folders.filter((f) => f.account_id === a.id).sort((x, y) => orderKey(x) - orderKey(y)),
      }))
  );
  const workspaces = $derived(app.settings.workspaces || []);

  const isHidden = (f) => app.settings.hiddenFolders.includes(f.id);
  function toggleHidden(f) {
    const s = new Set(app.settings.hiddenFolders);
    s.has(f.id) ? s.delete(f.id) : s.add(f.id);
    saveSettings({ hiddenFolders: [...s] });
  }

  const isFolded = (aid) => app.settings.collapsedAccounts.includes(aid);
  function toggleFold(aid) {
    const s = new Set(app.settings.collapsedAccounts);
    s.has(aid) ? s.delete(aid) : s.add(aid);
    saveSettings({ collapsedAccounts: [...s] });
  }

  // Live reorder: rearrange as you drag over a row, with flip animation.
  function reorderLive(group, targetId) {
    if (dragId == null || dragId === targetId) return;
    const ids = group.folders.map((f) => f.id);
    const from = ids.indexOf(dragId), to = ids.indexOf(targetId);
    if (from < 0 || to < 0 || from === to) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    const order = { ...app.settings.folderOrder };
    ids.forEach((id, i) => (order[id] = i));
    saveSettings({ folderOrder: order });
  }

  async function createFolder(accountId) {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await foldersApi.create(accountId, name);
      notify(t("nav.creatingFolder", { name }));
      creatingFor = null; newFolderName = "";
      setTimeout(loadAccountsAndFolders, 1500);
    } catch (e) { notify(e.message, "error"); }
  }
  async function removeFolder(f) {
    const ok = await confirmDialog({
      title: t("nav.deleteFolderTitle", { name: f.name }),
      message: t("nav.deleteFolderMsg"),
      confirmLabel: t("nav.deleteFolder"), danger: true,
    });
    if (!ok) return;
    try { await foldersApi.remove(f.id); await loadAccountsAndFolders(); notify(t("nav.folderDeleted")); }
    catch (e) { notify(e.message, "error"); }
  }
  async function removeAccount(a) {
    const ok = await confirmDialog({
      title: t("nav.removeAccountTitle", { email: a.email }),
      message: t("nav.removeAccountMsg"),
      confirmLabel: t("nav.removeAccount"), danger: true,
    });
    if (!ok) return;
    try { await accountsApi.remove(a.id); await loadAccountsAndFolders(); notify(t("nav.accountRemoved")); }
    catch (e) { notify(t("nav.couldntRemove", { error: e.message }), "error"); }
  }
  const openFolder = (f) => { app.view = "mail"; selectFolder(f); };
</script>

<aside class="sidebar" class:rail={collapsed}>
  <div class="brand">
    <span class="mark">{@html icons.brand}</span>
    {#if !collapsed}<span class="title">RaplMail</span>{/if}
    <button class="collapse" title={collapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
      onclick={() => saveSettings({ sidebarCollapsed: !collapsed })}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        {#if collapsed}<path d="m6.5 5 7 7-7 7"/><path d="m12.5 5 7 7-7 7"/>{:else}<path d="m17.5 5-7 7 7 7"/><path d="m11.5 5-7 7 7 7"/>{/if}
      </svg>
    </button>
  </div>

  <button class="btn primary compose" title={composeHint ? t("nav.composeWithHint", { hint: composeHint }) : t("nav.compose")} onclick={() => openCompose({ to: "", subject: "", html: "" })}>
    {@html icons.compose}{#if !collapsed}<span class="compose-label">{t("nav.compose")}</span>{#if composeHint}<kbd>{composeHint}</kbd>{/if}{/if}
  </button>

  {#if workspaces.length && !collapsed}
    <div class="ws-switch">
      <button class:active={app.settings.activeWorkspace == null} onclick={() => setWorkspace(null)}>{t("nav.allWorkspaces")}</button>
      {#each workspaces as w}
        <button class:active={app.settings.activeWorkspace === w.id} onclick={() => setWorkspace(w.id)}>{w.name}</button>
      {/each}
    </div>
  {/if}

  <div class="scroll">
    {#if grouped.length === 0 && !collapsed}
      <div class="empty">{t("nav.noAccounts")} <button class="link" onclick={() => (app.view = "settings")}>{t("nav.addOne")}</button></div>
    {/if}

    {#each navSections as sec (sec.key)}
      {#if sec.label}
        {#if collapsed}<div class="sec-rule"></div>{:else}<div class="sec-label">{sec.label}</div>{/if}
      {/if}
      {#each sec.items as it (it.id)}
        <button class="nav-it" title={it.label} class:active={it.active}
          class:dragging={dragSpecial?.id === it.id}
          animate:flip={{ duration: 150 }}
          draggable={!collapsed}
          ondragstart={() => (dragSpecial = { id: it.id, sec: sec.key })}
          ondragend={() => (dragSpecial = null)}
          ondragover={(e) => e.preventDefault()}
          ondragenter={() => reorderSpecial(it.id, sec.key)}
          onclick={it.run}>
          <span class="ic">{@html it.icon}</span>
          {#if !collapsed}
            <span class="name">{it.label}</span>
            {#if it.badge > 0}<span class="badge tnum">{it.badge > 999 ? "999+" : it.badge}</span>{/if}
          {:else if it.badge > 0}
            <span class="rail-badge"></span>
          {/if}
        </button>
      {/each}
    {/each}

    {#if app.settings.savedSearches.length}
      {#if collapsed}<div class="sec-rule"></div>{:else}<div class="sec-label">{t("nav.searches")}</div>{/if}
    {/if}
    {#each app.settings.savedSearches as ss (ss.id)}
      <div class="folder-row">
        <button class="nav-it" title={ss.query}
          class:active={app.view === "mail" && app.search === ss.query}
          onclick={() => runSearch(ss.query)}>
          <span class="ic">{@html icons.search}</span>{#if !collapsed}<span class="name">{ss.name}</span>{/if}
        </button>
        {#if !collapsed}<button class="eye" title={t("nav.removeSavedSearch")} onclick={() => removeSavedSearch(ss.id)}>{@html icons.close}</button>{/if}
      </div>
    {/each}

    {#each grouped as g (g.account.id)}
      <div class="acct">
        {#if !collapsed}
          <button class="acct-head" onclick={() => toggleFold(g.account.id)}>
            <span class="chev" class:open={!isFolded(g.account.id)}>
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m8 5 8 7-8 7"/></svg>
            </span>
            <span class="dot" style="background:{g.account.color}"></span>
            <span class="email">{g.account.email}</span>
          </button>
          <button class="addbtn" title={t("nav.newFolder")} onclick={() => (creatingFor = creatingFor === g.account.id ? null : g.account.id)}>＋</button>
          {#if manage}<button class="addbtn del" title={t("nav.removeThisAccount")} onclick={() => removeAccount(g.account)}>{@html icons.trash}</button>{/if}
        {:else}
          <!-- Collapsed rail: the old per-account color circle wasn't clickable
               and just looked noisy. Replace it with a quiet hairline that still
               separates each account's folder icons (email on hover). -->
          <span class="rail-sep" title={g.account.email}></span>
        {/if}
      </div>

      {#if creatingFor === g.account.id && !collapsed}
        <div class="newfolder" transition:slide={{ duration: 150 }}>
          <input placeholder={t("nav.folderNamePlaceholder")} bind:value={newFolderName} onkeydown={(e) => e.key === "Enter" && createFolder(g.account.id)} />
          <button class="btn primary" onclick={() => createFolder(g.account.id)}>{t("nav.add")}</button>
        </div>
      {/if}

      {#if !isFolded(g.account.id)}
        {#each g.folders as f (f.id)}
          <div class="folder-row" animate:flip={{ duration: 150 }}
            class:dim={isHidden(f)} class:dragtarget={manage && dragId != null && dragId !== f.id}
            class:dropok={dropTarget === f.id}
            class:dropbad={dropBad === f.id}
            class:gone={!manage && isHidden(f)}
            draggable={manage}
            ondragstart={() => (dragId = f.id)}
            ondragend={() => (dragId = null)}
            ondragover={(e) => {
              if (manage) { e.preventDefault(); return; }
              if (app.dragMessageIds.length === 0) return;   // not a message drag
              if (canDropMsg(f)) { e.preventDefault(); dropTarget = f.id; dropBad = null; }
              else { dropBad = f.id; }                       // wrong account: show why
            }}
            ondragenter={() => { if (manage) reorderLive(g, f.id); }}
            ondragleave={() => { if (dropTarget === f.id) dropTarget = null; if (dropBad === f.id) dropBad = null; }}
            ondrop={(e) => onFolderDrop(e, f)}>
            {#if manage && !collapsed}<span class="grip" title={t("nav.dragToReorder")}>⠿</span>{/if}
            <button class="nav-it" title={collapsed ? `${f.name} - ${g.account.email}` : f.name}
              class:active={app.selectedKind === "folder" && app.selectedFolderId === f.id && app.view === "mail"}
              onclick={() => { if (!manage) openFolder(f); }}>
              <span class="ic">{@html folderIcon(f.role)}</span>
              {#if !collapsed}<span class="name">{f.name}</span>{/if}
              {#if f.unread_count > 0 && !manage && !collapsed}<span class="badge tnum">{f.unread_count > 999 ? "999+" : f.unread_count}</span>{/if}
            </button>
            {#if manage && !collapsed}
              <button class="eye" title={isHidden(f) ? t("nav.show") : t("nav.hide")} onclick={() => toggleHidden(f)}>{@html isHidden(f) ? icons.show : icons.hide}</button>
              {#if !CORE.has(f.role)}<button class="del" title={t("nav.deleteFolder")} onclick={() => removeFolder(f)}>{@html icons.trash}</button>{/if}
            {/if}
          </div>
        {/each}
      {/if}
    {/each}

    {#if !collapsed && app.accounts.length}
      {#if rootCreating}
        <div class="newfolder" transition:slide={{ duration: 150 }}>
          {#if app.accounts.length > 1}
            <select bind:value={rootAccount}>
              {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
            </select>
          {/if}
          <input placeholder={t("nav.newFolderNamePlaceholder")} bind:value={rootName} onkeydown={(e) => e.key === "Enter" && rootCreate()} />
          <button class="btn primary" onclick={rootCreate}>{t("nav.add")}</button>
          <button class="btn ghost" onclick={() => (rootCreating = false)}>{@html icons.close}</button>
        </div>
      {:else}
        <button class="quiet-action" onclick={() => { rootCreating = true; rootAccount = app.accounts[0]?.id; }}>{t("nav.newFolderAction")}</button>
      {/if}
    {/if}

    {#if app.folders.length > 0 && !collapsed}
      <button class="quiet-action" class:on={manage} onclick={() => { manage = !manage; creatingFor = null; }}>
        {manage ? t("nav.doneManaging") : t("nav.manageFolders")}
      </button>
      {#if manage}<div class="manage-hint" transition:slide={{ duration: 150 }}>{t("nav.hintReorder")} · {@html icons.hide}/{@html icons.show} {t("nav.hintHide")} · ＋ {t("nav.hintAdd")} · {@html icons.trash} {t("nav.hintDelete")}</div>{/if}
    {/if}
  </div>

  {#if (app.syncing || app.queuePending > 0 || app.queueFailed > 0) && !collapsed}
    <div class="status" transition:slide={{ duration: 150 }}>
      {#if app.syncing}<span class="st-line"><span class="spin">{@html icons.sync}</span> {t("nav.syncing")}</span>{/if}
      {#if app.queuePending > 0}<span class="st-line"><span class="spin">⏳</span> {app.queuePending === 1 ? t("nav.actionSyncing", { n: app.queuePending }) : t("nav.actionsSyncing", { n: app.queuePending })}</span>{/if}
      {#if app.queueFailed > 0}
        <span class="st-line failed">{t("nav.failedCount", { n: app.queueFailed })}
          <button onclick={toggleQueue}>{queueOpen ? t("nav.hide") : t("nav.details")}</button>
          <button onclick={retryQueue}>{t("nav.retry")}</button>
        </span>
        {#if queueOpen}
          <div class="qitems">
            {#each queueList as q (q.id)}
              <div class="qitem">
                <div class="qsum">{q.summary}</div>
                {#if q.last_error}<div class="qerr">{q.last_error}</div>{/if}
                <div class="qmeta">
                  <span>{q.status}{q.attempts ? ` · ${t("nav.tries", { n: q.attempts })}` : ""}</span>
                  <button onclick={() => discardItem(q.id)}>{t("nav.discard")}</button>
                </div>
              </div>
            {/each}
            {#if queueList.length === 0}<div class="qitem muted">{t("nav.nothingQueued")}</div>{/if}
          </div>
        {/if}
      {/if}
    </div>
  {/if}

  <div class="foot">
    <button class="foot-btn" class:spin-ic={app.syncing} title={t("nav.checkNewMail")} onclick={syncAllAccounts} disabled={app.syncing}>{@html icons.sync}{#if !collapsed}<span>{t("nav.sync")}</span>{/if}</button>
    <button class="foot-btn" title={app.customizing ? t("nav.lockLayout") : t("nav.customizeLayout")} class:active={app.customizing} onclick={() => (app.customizing = !app.customizing)}>{@html app.customizing ? icons.unlock : icons.customize}{#if !collapsed}<span>{t("nav.layout")}</span>{/if}</button>
    <button class="foot-btn" title={t("nav.settings")} class:active={app.view === "settings"} onclick={() => (app.view = "settings")}>{@html icons.settings}{#if !collapsed}<span>{t("nav.settings")}</span>{/if}</button>
  </div>
</aside>

<style>
  .sidebar {
    background: var(--surface);
    border-right: 1px solid var(--hairline);
    display: flex; flex-direction: column;
    padding: 12px 10px 10px; gap: 10px;
    min-height: 0; height: 100%; overflow: hidden;
  }
  .sidebar.rail { padding: 12px 8px 10px; align-items: stretch; }

  /* ── Brand ── */
  .brand { display: flex; align-items: center; gap: 9px; padding: 2px 4px 2px 6px; }
  .mark {
    display: grid; place-items: center; width: 26px; height: 26px; flex: none;
    border-radius: 8px; color: #fff;
    background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 45%, #a06df0));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), var(--shadow-sm);
  }
  .mark :global(svg) { width: 15px; height: 15px; }
  .title { flex: 1; font-weight: 700; font-size: 14.5px; letter-spacing: -0.01em; }
  .collapse {
    margin-left: auto; color: var(--faint); padding: 4px 6px; border-radius: 7px;
    display: grid; place-items: center;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .collapse:hover { background: var(--hover); color: var(--text); }
  .rail .brand { justify-content: center; padding: 2px 0; flex-direction: column; gap: 6px; }
  .rail .collapse { margin: 0; }

  /* ── Compose ── */
  .compose { justify-content: center; padding: 9px 12px; font-weight: 600; }
  .compose-label { flex: 1; text-align: left; margin-left: 2px; }
  .compose kbd {
    font: 600 10px/1 inherit; letter-spacing: 0.03em; color: rgba(255, 255, 255, 0.85);
    background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 5px; padding: 3px 6px;
  }
  .rail .compose { padding: 9px 0; }

  /* ── Workspaces ── */
  .ws-switch { display: flex; gap: 4px; flex-wrap: wrap; padding: 0 2px; }
  .ws-switch button {
    font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 999px;
    background: var(--surface-2); color: var(--muted);
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .ws-switch button:hover { background: var(--surface-3); color: var(--text); }
  .ws-switch button.active { background: var(--accent); color: #fff; }

  /* ── Nav ── */
  .scroll { flex: 1 1 auto; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: 1px; min-height: 0; padding: 2px 0; }

  .sec-label {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--faint); padding: 14px 10px 5px; user-select: none;
  }
  .sec-rule { height: 1px; background: var(--hairline); margin: 10px 10px; flex: none; }

  .nav-it {
    position: relative; flex: 0 0 auto;
    display: flex; align-items: center; gap: 10px;
    width: 100%; min-width: 0; padding: 7px 10px;
    border-radius: 8px; color: var(--text); text-align: left; font-size: 13.5px;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .folder-row .nav-it { flex: 1; }
  .nav-it:hover { background: var(--hover); }
  .nav-it.active { background: var(--accent-soft); }
  .nav-it.active .ic { color: var(--accent); }
  .nav-it.active .name { font-weight: 600; }
  .nav-it.active::before {
    content: ""; position: absolute; left: 0; top: 7px; bottom: 7px; width: 3px;
    border-radius: 999px; background: var(--accent);
  }
  .nav-it[draggable="true"] { cursor: pointer; }
  .nav-it.dragging { opacity: 0.45; }
  .nav-it .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ic { width: 18px; display: grid; place-items: center; flex: none; color: var(--muted); transition: color var(--t-fast) var(--ease); }
  .ic :global(svg) { width: 16.5px; height: 16.5px; }
  .badge {
    flex: none; font-size: 10.5px; font-weight: 700; color: var(--accent);
    background: var(--accent-soft); border-radius: 999px; padding: 2px 7px; min-width: 20px; text-align: center;
  }
  .rail-badge { position: absolute; top: 6px; right: 6px; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
  .rail .nav-it { justify-content: center; padding: 8px 0; }
  .rail .ic { width: auto; }

  /* ── Accounts & folders ── */
  .acct { display: flex; align-items: center; gap: 4px; padding: 12px 0 3px; }
  .acct-head {
    flex: 1; display: flex; align-items: center; gap: 7px;
    color: var(--faint); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
    padding: 3px 6px; border-radius: 7px; min-width: 0;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .acct-head:hover { background: var(--hover); color: var(--muted); }
  .chev { display: grid; place-items: center; width: 10px; flex: none; transition: transform var(--t) var(--ease); }
  .chev.open { transform: rotate(90deg); }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; box-shadow: 0 0 0 2.5px color-mix(in srgb, currentColor 0%, transparent); }
  .rail-sep { display: block; height: 1px; margin: 9px 12px 3px; background: var(--hairline); border-radius: 1px; }
  .email { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .addbtn { color: var(--accent); font-size: 15px; padding: 0 6px; opacity: 0; transition: opacity var(--t-fast) var(--ease); }
  .acct:hover .addbtn, .addbtn:focus-visible { opacity: 1; }
  .addbtn.del { color: var(--danger); font-size: 13px; display: inline-flex; align-items: center; opacity: 1; }
  .newfolder { display: flex; gap: 6px; padding: 4px 2px 8px; flex-wrap: wrap; }
  .newfolder select, .newfolder input { flex: 1 1 100%; padding: 6px 8px; }
  .newfolder input { flex: 1; }
  .newfolder .btn { padding: 6px 12px; }

  .folder-row { display: flex; align-items: center; gap: 4px; border-radius: 8px; }
  .folder-row.dim { opacity: 0.5; }
  .folder-row.gone { display: none; }
  .folder-row.dragtarget { outline: 1px dashed var(--border); }
  /* A message is being dragged onto this folder - highlight it as a drop target. */
  .folder-row.dropok { background: var(--accent-soft); box-shadow: inset 0 0 0 2px var(--accent); }
  .folder-row.dropok :global(.nav-it) { color: var(--accent); }
  /* Hovering a folder in another account - a move can't cross accounts. */
  .folder-row.dropbad { background: var(--danger-soft); box-shadow: inset 0 0 0 1px var(--danger); }
  .folder-row.dropbad :global(.nav-it) { color: var(--danger); cursor: no-drop; }
  .grip { cursor: grab; color: var(--faint); padding: 0 2px; }
  .eye, .del { padding: 4px 7px; border-radius: 7px; color: var(--muted); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .eye:hover, .del:hover { background: var(--hover); }
  .del:hover { color: var(--danger); }

  .quiet-action {
    margin-top: 2px; padding: 6px 10px; font-size: 12.5px; color: var(--faint);
    border-radius: 8px; text-align: left;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .quiet-action:hover { background: var(--hover); color: var(--text); }
  .quiet-action.on { color: var(--accent); }
  .manage-hint { color: var(--faint); font-size: 10px; padding: 4px 10px; line-height: 1.5; }

  /* ── Status strip (sync / offline queue) ── */
  .status {
    display: flex; flex-direction: column; gap: 3px;
    font-size: 11.5px; color: var(--muted);
    background: var(--surface-2); border: 1px solid var(--hairline);
    border-radius: var(--radius-sm); padding: 7px 9px;
  }
  .st-line { display: flex; align-items: center; gap: 7px; }
  .st-line.failed { color: var(--warning); flex-wrap: wrap; }
  .st-line.failed button { color: var(--accent); font-weight: 600; padding: 0 2px; }
  .qitems { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; max-height: 220px; overflow-y: auto; }
  .qitem { background: var(--surface); border: 1px solid var(--hairline); border-radius: 8px; padding: 7px 9px; }
  .qitem.muted { color: var(--muted); }
  .qsum { font-size: 11px; color: var(--text); font-weight: 600; word-break: break-word; }
  .qerr { font-size: 10px; color: var(--danger); margin-top: 3px; word-break: break-word; line-height: 1.4; }
  .qmeta { display: flex; align-items: center; justify-content: space-between; margin-top: 5px; font-size: 10px; color: var(--faint); }
  .qmeta button { color: var(--accent); font-weight: 600; }
  .spin { display: inline-flex; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Footer ── */
  .foot { display: flex; gap: 2px; border-top: 1px solid var(--hairline); padding-top: 8px; }
  .foot-btn {
    flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px;
    padding: 6px 4px; border-radius: 8px; color: var(--muted); font-size: 10.5px; font-weight: 600;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .foot-btn :global(svg) { width: 16px; height: 16px; }
  .foot-btn:hover { background: var(--hover); color: var(--text); }
  .foot-btn.active { color: var(--accent); }
  .foot-btn:disabled { opacity: 0.6; }
  .foot-btn.spin-ic :global(svg) { animation: spin 1s linear infinite; }
  .rail .foot { flex-direction: column; gap: 2px; }
  .rail .foot-btn span { display: none; }

  .empty { padding: 16px 8px; color: var(--muted); font-size: 13px; line-height: 1.7; }
  .link { color: var(--accent); }
</style>
