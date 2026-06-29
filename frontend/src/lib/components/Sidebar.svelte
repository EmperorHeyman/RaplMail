<script>
  import { flip } from "svelte/animate";
  import { app, selectFolder, selectUnifiedInbox, selectSmartInbox, selectSnoozed, selectScreener, selectPaperTrail, selectFollowups, saveSettings, notify, openCompose, loadAccountsAndFolders, setWorkspace, workspaceAccountIds, runSearch, removeSavedSearch, retryQueue } from "../store.svelte.js";
  import { accounts as accountsApi, folders as foldersApi } from "../api.js";
  import { icons, folderIcon } from "../icons.js";

  const ROLE_ORDER = { inbox: 0, drafts: 1, sent: 2, archive: 3, junk: 4, trash: 5, other: 6 };
  const CORE = new Set(["inbox", "sent"]);

  let manage = $state(false);
  let dragId = $state(null);
  let creatingFor = $state(null);
  let newFolderName = $state("");
  let rootCreating = $state(false);
  let rootName = $state("");
  let rootAccount = $state(null);

  async function rootCreate() {
    const name = rootName.trim();
    const aid = rootAccount ?? app.accounts[0]?.id;
    if (!name || !aid) { notify("Pick an account and name", "error"); return; }
    try {
      await foldersApi.create(aid, name);
      notify(`Creating “${name}”…`);
      rootCreating = false; rootName = "";
      setTimeout(loadAccountsAndFolders, 1500);
    } catch (e) { notify(e.message, "error"); }
  }

  const collapsed = $derived(app.settings.sidebarCollapsed);
  const hasInbox = $derived(app.folders.some((f) => f.role === "inbox"));

  // The "special" nav items (Smart Inbox, Snoozed, Calendar…) — reorderable.
  const specialItems = $derived.by(() => {
    const s = app.settings;
    const items = [];
    if (s.dashboard !== false)
      items.push({ id: "home", icon: icons.home || icons.smart, label: "Home", active: app.view === "dashboard", run: () => { app.view = "dashboard"; } });
    if (hasInbox && s.smartInbox)
      items.push({ id: "smart", icon: icons.smart, label: "Smart Inbox", active: app.selectedKind === "smart" && app.view === "mail", run: () => { app.view = "mail"; selectSmartInbox(); } });
    else if (hasInbox && s.unifiedInbox)
      items.push({ id: "unified", icon: icons.unified, label: "All Inboxes", active: app.selectedKind === "unified" && app.view === "mail", run: () => { app.view = "mail"; selectUnifiedInbox(); } });
    if (s.screener)
      items.push({ id: "screener", icon: icons.screener, label: "Screener", active: app.selectedKind === "screener" && app.view === "mail", run: () => { app.view = "mail"; selectScreener(); } });
    items.push({ id: "snoozed", icon: icons.snooze, label: "Snoozed", active: app.selectedKind === "snoozed" && app.view === "mail", run: () => { app.view = "mail"; selectSnoozed(); } });
    items.push({ id: "calendar", icon: icons.calendar, label: "Calendar", active: app.view === "calendar", run: () => { app.view = "calendar"; } });
    items.push({ id: "scheduled", icon: icons.clock, label: "Scheduled", active: app.view === "scheduled", run: () => { app.view = "scheduled"; } });
    items.push({ id: "newsfeed", icon: icons.newspaper, label: "Newsletter Feed", active: app.view === "newsfeed", run: () => { app.view = "newsfeed"; } });
    items.push({ id: "papertrail", icon: icons.receipt, label: "Paper Trail", active: app.selectedKind === "papertrail" && app.view === "mail", run: () => { app.view = "mail"; selectPaperTrail(); } });
    items.push({ id: "followups", icon: icons.alarm, label: "Follow-ups", active: app.selectedKind === "followups" && app.view === "mail", run: () => { app.view = "mail"; selectFollowups(); } });
    const order = s.specialOrder || [];
    const rank = (id) => { const i = order.indexOf(id); return i < 0 ? 999 : i; };
    return items.sort((a, b) => rank(a.id) - rank(b.id));
  });
  let dragSpecial = $state(null);
  function reorderSpecial(targetId) {
    if (dragSpecial == null || dragSpecial === targetId) return;
    const ids = specialItems.map((i) => i.id);
    const from = ids.indexOf(dragSpecial), to = ids.indexOf(targetId);
    if (from < 0 || to < 0 || from === to) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    saveSettings({ specialOrder: ids });
  }

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
      notify(`Creating “${name}”…`);
      creatingFor = null; newFolderName = "";
      setTimeout(loadAccountsAndFolders, 1500);
    } catch (e) { notify(e.message, "error"); }
  }
  async function removeFolder(f) {
    if (!confirm(`Delete folder “${f.name}” and its cached messages? This deletes it on the server too.`)) return;
    try { await foldersApi.remove(f.id); await loadAccountsAndFolders(); notify("Folder deleted"); }
    catch (e) { notify(e.message, "error"); }
  }
  async function syncAll() {
    app.syncing = true;
    for (const a of app.accounts) await accountsApi.sync(a.id);
    notify("Syncing…");
  }
  const openFolder = (f) => { app.view = "mail"; selectFolder(f); };
</script>

<aside class="sidebar" class:rail={collapsed}>
  <div class="brand">
    {#if !collapsed}<span class="mark">{@html icons.brand}</span><span class="title">RaplMail</span>{/if}
    <button class="collapse" title={collapsed ? "Expand" : "Collapse sidebar"}
      onclick={() => saveSettings({ sidebarCollapsed: !collapsed })}>{collapsed ? "»" : "«"}</button>
  </div>

  <button class="btn primary compose" title="Compose" onclick={() => openCompose({ to: "", subject: "", html: "" })}>
    {@html icons.compose}{#if !collapsed} Compose{/if}
  </button>

  {#if workspaces.length && !collapsed}
    <div class="ws-switch">
      <button class:active={app.settings.activeWorkspace == null} onclick={() => setWorkspace(null)}>All</button>
      {#each workspaces as w}
        <button class:active={app.settings.activeWorkspace === w.id} onclick={() => setWorkspace(w.id)}>{w.name}</button>
      {/each}
    </div>
  {/if}

  {#if app.syncing && !collapsed}
    <div class="syncing"><span class="spin">{@html icons.sync}</span> Syncing your mail…</div>
  {/if}
  {#if (app.queuePending > 0 || app.queueFailed > 0) && !collapsed}
    <div class="queue">
      {#if app.queuePending > 0}<span><span class="spin">⏳</span> {app.queuePending} action{app.queuePending === 1 ? "" : "s"} syncing…</span>{/if}
      {#if app.queueFailed > 0}<span class="failed">⚠ {app.queueFailed} failed <button onclick={retryQueue}>Retry</button></span>{/if}
    </div>
  {/if}

  <div class="scroll">
    {#if grouped.length === 0 && !collapsed}
      <div class="empty">No accounts yet. <button class="link" onclick={() => (app.view = "settings")}>Add one →</button></div>
    {/if}

    {#each specialItems as it (it.id)}
      <button class="folder unified" title={it.label} class:active={it.active}
        class:dragging={dragSpecial === it.id}
        animate:flip={{ duration: 160 }}
        draggable={!collapsed}
        ondragstart={() => (dragSpecial = it.id)}
        ondragend={() => (dragSpecial = null)}
        ondragover={(e) => e.preventDefault()}
        ondragenter={() => reorderSpecial(it.id)}
        onclick={it.run}>
        <span class="ic">{@html it.icon}</span>{#if !collapsed}<span class="name">{it.label}</span>{/if}
      </button>
    {/each}

    {#if !collapsed && app.accounts.length}
      {#if rootCreating}
        <div class="newfolder">
          {#if app.accounts.length > 1}
            <select bind:value={rootAccount}>
              {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
            </select>
          {/if}
          <input placeholder="New folder name" bind:value={rootName} onkeydown={(e) => e.key === "Enter" && rootCreate()} />
          <button class="btn primary" onclick={rootCreate}>Add</button>
          <button class="btn ghost" onclick={() => (rootCreating = false)}>{@html icons.close}</button>
        </div>
      {:else}
        <button class="newfolder-root" onclick={() => { rootCreating = true; rootAccount = app.accounts[0]?.id; }}>
          ＋ New folder
        </button>
      {/if}
    {/if}

    {#each app.settings.savedSearches as ss (ss.id)}
      <div class="folder-row">
        <button class="folder" title={ss.query}
          class:active={app.view === "mail" && app.search === ss.query}
          onclick={() => runSearch(ss.query)}>
          <span class="ic">{@html icons.search}</span>{#if !collapsed}<span class="name">{ss.name}</span>{/if}
        </button>
        {#if !collapsed}<button class="eye" title="Remove saved search" onclick={() => removeSavedSearch(ss.id)}>{@html icons.close}</button>{/if}
      </div>
    {/each}

    {#each grouped as g (g.account.id)}
      <div class="acct">
        {#if !collapsed}
          <button class="acct-head" onclick={() => toggleFold(g.account.id)}>
            <span class="chev">{isFolded(g.account.id) ? "▸" : "▾"}</span>
            <span class="dot" style="background:{g.account.color}"></span>
            <span class="email">{g.account.email}</span>
          </button>
          <button class="addbtn" title="New folder" onclick={() => (creatingFor = creatingFor === g.account.id ? null : g.account.id)}>＋</button>
        {:else}
          <span class="dot rail-dot" style="background:{g.account.color}" title={g.account.email}></span>
        {/if}
      </div>

      {#if creatingFor === g.account.id && !collapsed}
        <div class="newfolder">
          <input placeholder="Folder name" bind:value={newFolderName} onkeydown={(e) => e.key === "Enter" && createFolder(g.account.id)} />
          <button class="btn primary" onclick={() => createFolder(g.account.id)}>Add</button>
        </div>
      {/if}

      {#if !isFolded(g.account.id)}
        {#each g.folders as f (f.id)}
          <div class="folder-row" animate:flip={{ duration: 170 }}
            class:dim={isHidden(f)} class:dragtarget={manage && dragId != null && dragId !== f.id}
            class:gone={!manage && isHidden(f)}
            draggable={manage}
            ondragstart={() => (dragId = f.id)}
            ondragend={() => (dragId = null)}
            ondragover={(e) => { if (manage) e.preventDefault(); }}
            ondragenter={() => { if (manage) reorderLive(g, f.id); }}>
            {#if manage && !collapsed}<span class="grip" title="Drag to reorder">⠿</span>{/if}
            <button class="folder" title={f.name}
              class:active={app.selectedKind === "folder" && app.selectedFolderId === f.id && app.view === "mail"}
              onclick={() => { if (!manage) openFolder(f); }}>
              <span class="ic">{@html folderIcon(f.role)}</span>
              {#if !collapsed}<span class="name">{f.name}</span>{/if}
              {#if f.unread_count > 0 && !manage}<span class="count">{f.unread_count}</span>{/if}
            </button>
            {#if manage && !collapsed}
              <button class="eye" title={isHidden(f) ? "Show" : "Hide"} onclick={() => toggleHidden(f)}>{@html isHidden(f) ? icons.show : icons.hide}</button>
              {#if !CORE.has(f.role)}<button class="del" title="Delete folder" onclick={() => removeFolder(f)}>{@html icons.trash}</button>{/if}
            {/if}
          </div>
        {/each}
      {/if}
    {/each}

    {#if app.folders.length > 0 && !collapsed}
      <button class="manage-toggle" onclick={() => { manage = !manage; creatingFor = null; }}>
        {manage ? "✓ Done managing" : "Manage folders"}
      </button>
      {#if manage}<div class="manage-hint">Drag ⠿ to reorder · {@html icons.hide}/{@html icons.show} hide · ＋ add · {@html icons.trash} delete</div>{/if}
    {/if}
  </div>

  <div class="foot">
    <button class="btn ghost" title="Sync" onclick={syncAll} disabled={app.syncing}>{@html icons.sync}{#if !collapsed} {app.syncing ? "Syncing" : "Sync"}{/if}</button>
    <button class="btn ghost" title={app.customizing ? "Lock layout" : "Customize layout (resize columns)"} class:active={app.customizing} onclick={() => (app.customizing = !app.customizing)}>{@html app.customizing ? icons.unlock : icons.customize}{#if !collapsed} {app.customizing ? "Lock" : "Customize"}{/if}</button>
    <button class="btn ghost" title="Settings" class:active={app.view === "settings"} onclick={() => (app.view = "settings")}>{@html icons.settings}{#if !collapsed} Settings{/if}</button>
  </div>
</aside>

<style>
  .sidebar { background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 14px 12px; gap: 12px; min-height: 0; height: 100%; overflow: hidden; }
  .sidebar.rail { padding: 14px 8px; align-items: stretch; }
  .brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; padding: 4px 6px; }
  .mark { font-size: 17px; }
  .title { flex: 1; }
  .collapse { margin-left: auto; color: var(--muted); padding: 2px 7px; border-radius: 6px; font-size: 13px; }
  .collapse:hover { background: var(--surface-2); color: var(--text); }
  .rail .brand { justify-content: center; }
  .compose { justify-content: center; }
  .ws-switch { display: flex; gap: 4px; flex-wrap: wrap; padding: 0 2px; }
  .ws-switch button { font-size: 11px; padding: 4px 9px; border-radius: 999px; background: var(--surface-2); color: var(--muted); }
  .ws-switch button:hover { background: var(--surface-3); color: var(--text); }
  .ws-switch button.active { background: var(--accent); color: #fff; }
  .syncing { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--accent); padding: 2px 6px; }
  .queue { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--muted); padding: 2px 6px; }
  .queue .failed { color: var(--warning); }
  .queue .failed button { color: var(--accent); font-weight: 600; margin-left: 4px; }
  .spin { display: inline-block; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .scroll { flex: 1 1 auto; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; align-content: flex-start; gap: 2px; min-height: 0; }

  .acct { display: flex; align-items: center; gap: 4px; padding: 10px 0 3px; }
  .acct-head { flex: 1; display: flex; align-items: center; gap: 7px; color: var(--faint); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 6px; border-radius: 6px; min-width: 0; }
  .acct-head:hover { background: var(--surface-2); color: var(--muted); }
  .chev { font-size: 9px; width: 10px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .rail-dot { width: 10px; height: 10px; margin: 8px auto 2px; }
  .email { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .addbtn { color: var(--accent); font-size: 15px; padding: 0 6px; }
  .newfolder { display: flex; gap: 6px; padding: 4px 2px 8px; flex-wrap: wrap; }
  .newfolder select, .newfolder input { flex: 1 1 100%; padding: 6px 8px; }
  .newfolder-root { display: flex; align-items: center; gap: 9px; padding: 8px 12px; border-radius: var(--radius-sm); color: var(--muted); font-size: 13px; width: 100%; text-align: left; }
  .newfolder-root:hover { background: var(--surface-2); color: var(--text); }
  .newfolder input { flex: 1; padding: 6px 8px; }
  .newfolder .btn { padding: 6px 12px; }

  .folder-row { display: flex; align-items: center; gap: 4px; border-radius: var(--radius-sm); }
  .folder-row.dim { opacity: 0.5; }
  .folder-row.gone { display: none; }
  .folder-row.dragtarget { outline: 1px dashed var(--border); }
  .grip { cursor: grab; color: var(--faint); padding: 0 2px; }
  /* flex:0 0 auto so the unified button (a column child) never grows tall */
  .folder { flex: 0 0 auto; display: flex; align-items: center; gap: 9px; padding: 8px 10px; border-radius: var(--radius-sm); color: var(--text); text-align: left; min-width: 0; width: 100%; }
  .folder-row .folder { flex: 1; }
  .folder:hover { background: var(--surface-2); }
  .folder.active { background: var(--surface-3); }
  .folder.unified { font-weight: 600; margin-bottom: 4px; }
  .folder.unified[draggable="true"] { cursor: grab; }
  .folder.dragging { opacity: 0.45; }
  .folder .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .folder .count { font-size: 11px; font-weight: 600; color: var(--accent); }
  .ic { width: 18px; text-align: center; flex: none; }
  .rail .folder, .rail .compose, .rail .foot .btn { justify-content: center; padding: 8px 0; }
  .rail .acct { justify-content: center; }
  .eye, .del { padding: 4px 7px; border-radius: 6px; color: var(--muted); }
  .eye:hover, .del:hover { background: var(--surface-2); }
  .del:hover { color: var(--danger); }
  .manage-toggle { margin-top: 8px; padding: 6px; font-size: 12px; color: var(--muted); border-radius: 6px; }
  .manage-toggle:hover { background: var(--surface-2); color: var(--text); }
  .manage-hint { color: var(--faint); font-size: 10px; padding: 4px 6px; line-height: 1.5; }

  .foot { display: flex; gap: 8px; flex-wrap: wrap; }
  .rail .foot { flex-direction: column; flex-wrap: nowrap; gap: 3px; }
  .foot .btn { flex: 1 1 72px; min-width: 0; justify-content: center; font-size: 13px; white-space: nowrap; overflow: hidden; }
  /* Collapsed rail: icon-only footer buttons shouldn't tower over the nav rows. */
  .rail .foot .btn { flex: none; padding: 6px 0; }
  .foot .btn.active { color: var(--accent); }
  .empty { padding: 16px 8px; color: var(--muted); font-size: 13px; line-height: 1.7; }
  .link { color: var(--accent); }
</style>
