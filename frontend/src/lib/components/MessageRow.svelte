<script>
  import { icons } from "../icons.js";
  import { app, snoozeMessage, snoozePresets, presetWhen, prefetchBody, isVip, isTrustedSender, setMessageSeen } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { messages as messagesApi, avatarUrlDomain } from "../api.js";
  import { listTime, relativeTime } from "../time.js";
  let { message, focused, selected, checked = false, selecting = false, onselect, onopen, ondone, onmenu, onarchive, ondelete } = $props();
  const done = $derived(message.is_done);
  const snoozedView = $derived(app.selectedKind === "snoozed");
  let snoozeMenu = $state(false);
  // Avatar ring is tinted with the receiving account's color (Spark-style).
  const acctColor = $derived(app.accounts.find((a) => a.id === message.account_id)?.color || null);
  const multiAcct = $derived(app.accounts.length > 1);

  // Sender avatar = cached domain favicon. Try the sender's own domain first,
  // then a "brand" domain pulled from links in the body (Spark-style), then fall
  // back to the initial.
  const useAvatar = $derived(app.settings.senderAvatars !== false);
  const senderDomain = $derived((message.from_addr || "").split("@")[1] || "");
  const avatarDomains = $derived.by(() => {
    if (!useAvatar) return [];
    const out = [];
    for (const d of [senderDomain, message.brand_domain]) {
      const dom = (d || "").toLowerCase().trim();
      if (dom && dom.includes(".") && !out.includes(dom)) out.push(dom);
    }
    return out;
  });
  let avIdx = $state(0);
  // Only reset the avatar candidate when the domains actually change — NOT on every
  // background refresh (which swaps the message object and would re-flash the icon).
  let _avKey = "";
  $effect(() => {
    const key = avatarDomains.join("|");
    if (key !== _avKey) { _avKey = key; avIdx = 0; }
  });
  const avSrc = $derived(avatarDomains[avIdx] ? avatarUrlDomain(avatarDomains[avIdx]) : "");
  const hasLogo = $derived(!!avSrc && !done);
  function onAvatarError() {
    if (avIdx < avatarDomains.length - 1) avIdx += 1;  // try the next candidate
    else avIdx = avatarDomains.length;                  // exhausted → show initial
  }

  function toggleFlag() { const v = !message.is_flagged; message.is_flagged = v; messagesApi.setFlag(message.id, v).catch(() => {}); }
  function toggleSeen() { setMessageSeen(message, !message.is_seen); }

  // The two hover buttons are user-configurable (settings.rowActions).
  function actionDef(key) {
    switch (key) {
      case "done": return { icon: done ? icons.restore : icons.done, title: done ? t("list.restoreKey") : t("list.markDoneKey"), cls: "done-btn", run: () => ondone() };
      case "snooze": return { icon: icons.snooze, title: t("list.snooze"), cls: "snooze-btn", run: () => (snoozeMenu = !snoozeMenu) };
      case "flag": return { icon: message.is_flagged ? icons.flagged : icons.flag, title: message.is_flagged ? t("list.unflag") : t("list.flag"), cls: message.is_flagged ? "flag-btn on" : "flag-btn", run: toggleFlag };
      case "read": return { icon: icons.mail, title: message.is_seen ? t("list.markUnread") : t("list.markRead"), cls: "read-btn", run: toggleSeen };
      case "archive": return { icon: icons.archive, title: t("list.archive"), cls: "arch-btn", run: () => onarchive?.() };
      case "delete": return { icon: icons.trash, title: t("list.delete"), cls: "del-btn", run: () => ondelete?.() };
      default: return null;
    }
  }
  const rowBtns = $derived((app.settings.rowActions || ["snooze", "done"]).slice(0, 2).map(actionDef).filter(Boolean));

  // Swipe-to-done gesture state.
  let dx = $state(0);
  let dragging = $state(false);
  let startX = 0;
  const THRESHOLD = 90;

  const fmtTime = (iso) => (app.settings.relativeTime ? relativeTime(iso) : listTime(iso));

  const initial = $derived((message.from_name || message.from_addr || "?").trim()[0]?.toUpperCase() || "?");

  function onPointerDown(e) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Don't start a swipe (and don't capture the pointer) when pressing a button
    // — pointer capture would steal the click from it, so "Done"/select/snooze
    // would silently open the mail instead of running their action.
    if (e.target?.closest?.("button")) return;
    dragging = true;
    startX = e.clientX;
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragging) return;
    dx = Math.max(0, e.clientX - startX); // swipe right to mark done
  }
  // A completed swipe must not ALSO count as a click — dx is reset before the
  // browser dispatches the click, so the dx===0 guard alone let the row open.
  let suppressClick = false;
  function onPointerUp() {
    if (!dragging) return;
    dragging = false;
    if (dx > THRESHOLD) { suppressClick = true; ondone(); }
    dx = 0;
  }
  function onRowClick() {
    if (suppressClick) { suppressClick = false; return; }
    if (dx === 0) onopen();
  }
</script>

<div class="wrap" class:swiping={dragging}>
  {#if multiAcct && acctColor}<span class="acct-stripe" style="background:{acctColor}"></span>{/if}
  <div class="action" style="opacity:{Math.min(1, dx / THRESHOLD)}">
    {@html done ? icons.restore : icons.done} {done ? t("list.restore") : t("list.done")}
  </div>
  <div
    class="row"
    role="button"
    tabindex="-1"
    class:focused
    class:selected
    class:isdone={done}
    class:unread={!message.is_seen && !done}
    style="transform: translateX({dx}px)"
    onpointerdown={onPointerDown}
    onpointermove={onPointerMove}
    onpointerup={onPointerUp}
    onpointercancel={onPointerUp}
    onclick={onRowClick}
    oncontextmenu={(e) => onmenu?.(e)}
    onmouseenter={() => prefetchBody(message.id, true)}
  >
    <button class="avatar" class:checked class:selecting class:haslogo={hasLogo}
      style={acctColor ? `border-color:${acctColor}` : ""}
      title={t("list.select")} onclick={(e) => { e.stopPropagation(); onselect?.(e); }}>
      <span class="initial">
        {#if done}{@html icons.done}
        {:else if hasLogo}<img class="logo-img" src={avSrc} alt="" loading="lazy" decoding="async" onerror={onAvatarError} />
        {:else}{initial}{/if}
      </span>
      <span class="box">{#if checked}{@html icons.done}{/if}</span>
      {#if isTrustedSender(message.from_addr)}
        <span class="shield ok" title={t("list.senderSafe")}>{@html icons.shieldCheck}</span>
      {:else if message.auth_status === "fail"}
        <span class="shield bad" title={t("list.authFail")}>{@html icons.shieldAlert}</span>
      {:else if message.auth_status === "pass"}
        <span class="shield ok" title={t("list.authPass")}>{@html icons.shieldCheck}</span>
      {/if}
    </button>
    <span class="body">
      <span class="line1">
        <span class="from">{message.from_name || message.from_addr}</span>
        <span class="time">{fmtTime(message.date)}</span>
      </span>
      <span class="subject">{message.subject || t("list.noSubject")}</span>
      <span class="snippet">{message.snippet}</span>
    </span>
    <span class="marks">
      {#if isVip(message.from_addr)}<span class="vip" title={t("list.vipSender")}>{@html icons.star}</span>{/if}
      {#if message.pinned}<span class="pin">{@html icons.pin}</span>{/if}
      {#if !message.is_seen && !done}<span class="unread-dot"></span>{/if}
      {#if message.is_flagged}<span class="star">{@html icons.flagged}</span>{/if}
      {#if message.has_attachments}<span class="clip">{@html icons.attachment}</span>{/if}
    </span>
    {#each rowBtns as b}
      <button class="row-btn {b.cls}" title={b.title}
        onclick={(e) => { e.stopPropagation(); b.run(); }}>{@html b.icon}</button>
    {/each}
  </div>

  {#if snoozeMenu}
    <div class="snooze-menu" onpointerdown={(e) => e.stopPropagation()}>
      {#if snoozedView}
        <button onclick={(e) => { e.stopPropagation(); snoozeMenu = false; snoozeMessage(message, null); }}>{t("list.unsnoozeNow")}</button>
      {/if}
      {#each snoozePresets() as p}
        <button onclick={(e) => { e.stopPropagation(); snoozeMenu = false; snoozeMessage(message, p.iso, p.presence); }}>{p.label}{#if p.at} · <span class="when">{presetWhen(p.at)}</span>{/if}</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap { position: relative; }
  .acct-stripe { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; z-index: 3; }
  .action {
    position: absolute; inset: 0; display: flex; align-items: center; padding-left: 22px;
    background: var(--done); color: #06231a; font-weight: 700; border-radius: 0;
    pointer-events: none;
  }
  .row {
    position: relative; width: 100%; text-align: left;
    display: flex; gap: 11px; align-items: flex-start;
    padding: 11px 14px; border-bottom: 1px solid var(--hairline);
    background: var(--bg); transition: background var(--t-fast) var(--ease);
  }
  .wrap.swiping .row { transition: none; }
  .row:hover { background: var(--surface); }
  .row.isdone { opacity: 0.62; }
  .row.isdone .avatar { background: var(--done); color: #06231a; }
  .done-check { font-weight: 800; }
  .row.selected { background: var(--surface-2); }
  .row.focused { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
  .row.unread .from, .row.unread .subject { font-weight: 700; }

  .avatar {
    position: relative; flex: none; width: 34px; height: 34px; border-radius: 50%;
    box-sizing: border-box;
    display: grid; place-items: center; font-weight: 700; font-size: 14px; line-height: 1;
    background: linear-gradient(135deg, var(--accent), #8a6df0); color: #fff;
    cursor: pointer; border: 2px solid transparent;
  }
  .avatar .initial { display: grid; place-items: center; line-height: 1; width: 100%; height: 100%; }
  /* Favicon avatars: neutral disc so the logo reads cleanly. */
  .avatar.haslogo { background: #fff; }
  .avatar .logo-img { width: 22px; height: 22px; object-fit: contain; border-radius: 4px; }
  .shield { position: absolute; bottom: -3px; right: -3px; width: 15px; height: 15px; border-radius: 50%;
            display: grid; place-items: center; font-size: 11px; background: var(--bg); box-shadow: 0 0 0 1.5px var(--bg); }
  .shield.ok { color: var(--done); }
  .shield.bad { color: var(--danger); }
  .avatar .box { position: absolute; inset: 0; display: grid; place-items: center; border-radius: 50%; opacity: 0; transition: opacity 0.1s; }
  /* Show a checkbox on hover, in selection mode, or when checked. */
  /* Keep the favicon/initial visible on hover; only swap to a checkbox once
     selection mode is active (or this row is checked). */
  .avatar.selecting .initial, .avatar.checked .initial { opacity: 0; }
  .avatar.selecting .box, .avatar.checked .box { opacity: 1; background: rgba(0,0,0,0.25); }
  .avatar.checked { background: var(--accent); }
  .avatar.checked .box { background: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
  .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .line1 { display: flex; justify-content: space-between; gap: 8px; }
  .from { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .time { flex: none; color: var(--faint); font-size: 12px; }
  .subject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .snippet { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .marks { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: none; }
  .unread-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent-soft-2); }
  .star { color: var(--warning); font-size: 13px; }
  .pin { color: var(--accent); font-size: 12px; }
  .vip { color: #e8b923; font-size: 12px; }
  .clip { font-size: 11px; }

  .row-btn {
    flex: none; align-self: center; width: 30px; height: 30px; border-radius: 50%;
    border: 1.5px solid var(--border); color: var(--muted); background: var(--bg);
    display: grid; place-items: center; opacity: 0; transform: scale(0.9);
    transition: opacity var(--t-fast) var(--ease), background var(--t-fast) var(--ease),
      color var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease),
      transform var(--t) var(--ease-spring);
  }
  .row:hover .row-btn, .row.focused .row-btn { opacity: 1; transform: scale(1); }
  .row-btn:active { transform: scale(0.92); }
  .done-btn:hover { background: var(--done); border-color: var(--done); color: #06231a; }
  .snooze-btn:hover, .read-btn:hover, .arch-btn:hover { background: var(--surface-3); border-color: var(--accent); }
  .flag-btn:hover { background: var(--surface-3); border-color: var(--warning); color: var(--warning); }
  .flag-btn.on { color: var(--warning); border-color: var(--warning); }
  .del-btn:hover { background: var(--danger); border-color: var(--danger); color: #fff; }
  .snooze-menu {
    position: absolute; right: 14px; top: 50%; z-index: 15;
    background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg); padding: 4px; display: flex; flex-direction: column; min-width: 150px;
    animation: pop-in var(--t) var(--ease); transform-origin: top right;
  }
  .snooze-menu button { text-align: left; padding: 7px 10px; border-radius: 6px; color: var(--text); font-size: 13px; }
  .snooze-menu button:hover { background: var(--accent); color: #fff; }
  .snooze-menu .when { color: var(--faint); font-size: 11px; }
  .snooze-menu button:hover .when { color: #e7e9ff; }
</style>
