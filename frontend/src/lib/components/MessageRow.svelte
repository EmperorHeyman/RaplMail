<script>
  import { icons } from "../icons.js";
  import { app, snoozeMessage, snoozePresets, presetWhen, prefetchBody, isVip, isTrustedSender, setMessageSeen, accountFor, isOutgoingView } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { messages as messagesApi, avatarUrlDomain } from "../api.js";
  import { avatarColor } from "../avatar.js";
  import { listTime, relativeTime } from "../time.svelte.js";
  let { message, focused, selected, checked = false, selecting = false, screener = false, groupTag = null, onselect, onopen, ondone, onmenu, onarchive, ondelete, onapprove, onblock } = $props();
  const done = $derived(message.is_done);
  const snoozedView = $derived(app.selectedKind === "snoozed");
  // In Sent/Drafts the sender is your own identity, so a "VIP sender" star would
  // sit on every single row and mean nothing.
  const outgoingView = $derived(isOutgoingView());
  let snoozeMenu = $state(false);
  // Avatar ring is tinted with the receiving account's color (Spark-style).
  const acctColor = $derived(accountFor(message.account_id)?.color || null);
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
  // Only reset the avatar candidate when the domains actually change - NOT on every
  // background refresh (which swaps the message object and would re-flash the icon).
  let _avKey = "";
  $effect(() => {
    const key = avatarDomains.join("|");
    if (key !== _avKey) { _avKey = key; avIdx = 0; }
  });
  // The favicon <img> is deliberately NOT loading="lazy": offscreen rows are
  // already gated by content-visibility, so lazy-loading double-gated it - the
  // fetch only started once the row was IN the viewport, and the fetch + decode
  // then landed mid-scroll instead of while the row was still approaching.
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
  // In the Screener, the hover buttons ARE the triage decision - approve/block
  // a first-time sender straight from the row, no need to open the mail first.
  const rowBtns = $derived(
    screener
      ? [{ icon: icons.done, title: t("reader.approve"), cls: "done-btn", run: () => onapprove?.() },
         { icon: icons.close, title: t("reader.block"), cls: "del-btn", run: () => onblock?.() }]
      : (app.settings.rowActions || ["snooze", "done"]).slice(0, 2).map(actionDef).filter(Boolean)
  );

  // Swipe-to-done gesture state.
  let dx = $state(0);
  let dragging = $state(false);
  let startX = 0;
  const THRESHOLD = 90;

  const fmtTime = (iso) => (app.settings.relativeTime ? relativeTime(iso) : listTime(iso));

  const initial = $derived((message.from_name || message.from_addr || "?").trim()[0]?.toUpperCase() || "?");
  // Stable per-sender color for the initial-fallback disc (only when there's no
  // favicon logo and the row isn't marked done - those have their own look).
  const initialBg = $derived(avatarColor(message.from_addr || message.from_name));

  function onPointerDown(e) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Don't start a swipe (and don't capture the pointer) when pressing a button
    // - pointer capture would steal the click from it, so "Done"/select/snooze
    // would silently open the mail instead of running their action.
    if (e.target?.closest?.("button")) return;
    // Leave the mouse to native drag-and-drop (drag a message onto a folder to
    // move it). Swipe-to-done stays a touch/pen gesture - capturing the mouse
    // pointer here would suppress the row's HTML5 drag.
    if (e.pointerType === "mouse") return;
    dragging = true;
    startX = e.clientX;
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragging) return;
    dx = Math.max(0, e.clientX - startX); // swipe right to mark done
  }
  // A completed swipe must not ALSO count as a click - dx is reset before the
  // browser dispatches the click, so the dx===0 guard alone let the row open.
  let suppressClick = false;
  function onPointerUp() {
    if (!dragging) return;
    dragging = false;
    if (dx > THRESHOLD) { suppressClick = true; ondone(); }
    dx = 0;
  }
  function onRowClick(e) {
    if (suppressClick) { suppressClick = false; return; }
    // Pass the event through so the list can turn Ctrl/Cmd/Shift-click into a
    // multi-selection instead of opening the mail.
    if (dx === 0) onopen(e);
  }

  // Prefetch on hover only after a short DWELL. Wheel-scrolling sweeps rows
  // under a stationary cursor, and an immediate mouseenter prefetch fired a
  // full-body fetch (+ JSON parse on the main thread) for every row that passed
  // - a request storm that made scrolling feel sluggish. A 120ms dwell means a
  // scroll pass (enter→leave in a few ms) fetches nothing, while a real hover
  // still warms the body long before the click lands.
  let _dwell;
  function onEnter() {
    clearTimeout(_dwell);
    _dwell = setTimeout(() => prefetchBody(message.id, true), 120);
  }
  function onLeave() { clearTimeout(_dwell); }
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
    onmouseenter={onEnter}
    onmouseleave={onLeave}
  >
    <button class="avatar" class:checked class:selecting class:haslogo={hasLogo}
      style={`${acctColor ? `border-color:${acctColor};` : ""}${!hasLogo && !done ? `--av:${initialBg};` : ""}`}
      title={t("list.select")} onclick={(e) => { e.stopPropagation(); onselect?.(e); }}>
      <span class="initial">
        {#if done}{@html icons.done}
        {:else if hasLogo}<img class="logo-img" src={avSrc} alt="" draggable="false" decoding="async" onerror={onAvatarError} />
        {:else}{initial}{/if}
      </span>
      <span class="box">{#if checked}{@html icons.done}{/if}</span>
      {#if isTrustedSender(message.from_addr)}
        <span class="shield ok" title={t("list.senderSafe")}>{@html icons.shieldCheck}</span>
      {:else if message.ai_verdict === "dangerous" || message.suspicious}
        <span class="shield bad" title={t("list.suspiciousSender")}>{@html icons.shieldAlert}</span>
      {:else if message.auth_status === "fail"}
        <span class="shield bad" title={t("list.authFail")}>{@html icons.shieldAlert}</span>
      {:else if message.auth_status === "pass"}
        <span class="shield ok" title={t("list.authPass")}>{@html icons.shieldCheck}</span>
      {/if}
    </button>
    <span class="body">
      <span class="line1">
        <span class="from">{message.from_name || message.from_addr}</span>
        {#if !outgoingView && message.is_reply_to_me}
          <!-- An answer to mail YOU sent. Sits next to the sender, where the eye
               already is when scanning the list, rather than among the small
               marks on the right - the whole point is that you don't miss it. -->
          <span class="replied" title={t("list.replyToYouTitle")}>{@html icons.reply} {t("list.replyToYou")}</span>
        {/if}
        <span class="time">{fmtTime(message.date)}</span>
      </span>
      <span class="subject">{message.subject || t("list.noSubject")}</span>
      <span class="snippet">
        {#if groupTag}
          <!-- New mail from a Smart Inbox group, shown in the timeline until it's
               read; the tag says where it will fold away to. On the preview
               line, so it never squeezes the sender or the subject. -->
          <span class="gtag" style="--tone:{groupTag.tone}" title={t("list.groupTagTip", { group: groupTag.label })}>{@html groupTag.icon} {groupTag.label}</span>
        {/if}{message.snippet}</span>
    </span>
    <span class="marks">
      {#if !outgoingView && isVip(message.from_addr)}<span class="vip" title={t("list.vipSender")}>{@html icons.star}</span>{/if}
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
        <button onclick={(e) => { e.stopPropagation(); snoozeMenu = false; snoozeMessage(message, p.iso, p.presence); }}>{p.label}{#if p.at}{" · "}<span class="when">{presetWhen(p.at)}</span>{/if}</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  /* A Material list item: flat on the list's ground, a state layer on hover,
     the selection tint once opened. */
  .wrap { position: relative; margin: 1px 6px; border-radius: var(--radius); overflow: hidden; }
  /* Which account it came to (several accounts): a short mark at the row's
     edge, beside the avatar - not a full-height line. */
  .acct-stripe { position: absolute; left: 4px; top: 50%; height: 22px; margin-top: -11px; width: 4px; border-radius: 2px; z-index: 3; }
  .action {
    position: absolute; inset: 0; display: flex; align-items: center; gap: 8px; padding-left: 22px;
    background: var(--done); color: var(--on-done); font-weight: 600;
    pointer-events: none;
  }
  .action :global(svg) { width: 20px; height: 20px; }
  .row {
    position: relative; width: 100%; text-align: left;
    display: flex; gap: var(--row-gap, 14px); align-items: flex-start;
    padding: var(--row-pad-y, 12px) 12px var(--row-pad-y, 12px) 14px; border-radius: inherit;
    background: transparent; color: var(--text);
    transition: background var(--t-fast) var(--ease);
  }
  .wrap.swiping .row { transition: none; background: var(--bg); }
  .row:hover { background: var(--hover); }
  .row.isdone { opacity: 0.6; }
  .row.isdone .avatar { background: var(--done); color: var(--on-done); }
  .done-check { font-weight: 800; }
  .row.selected { background: var(--sel); color: var(--on-sel); }
  .row.selected .snippet, .row.selected .time { color: color-mix(in srgb, var(--on-sel) 78%, transparent); }
  /* Keyboard focus (j/k / arrows): a ring, so it reads apart from the opened row. */
  .row.focused { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--accent) 70%, transparent); }
  .row.unread .from, .row.unread .subject { font-weight: 700; }
  .row.unread .time { font-weight: 700; color: var(--text); }
  .row.selected.unread .time { color: var(--on-sel); }

  /* Letter avatar: a tonal disc in the sender's own hue (Gmail-style) - tinted
     container + a deeper/lighter tone of the same hue for the letter. */
  .avatar {
    position: relative; flex: none; width: var(--row-av, 40px); height: var(--row-av, 40px); border-radius: 50%;
    box-sizing: border-box; margin-top: 1px;
    display: grid; place-items: center; font-weight: 500; font-size: calc(var(--row-av, 40px) * 0.42); line-height: 1;
    background: color-mix(in srgb, var(--av, var(--accent)) 34%, var(--surface));
    color: color-mix(in srgb, var(--av, var(--accent)) 55%, var(--text));
    cursor: pointer; border: 2px solid transparent;
  }
  .avatar .initial { display: grid; place-items: center; line-height: 1; width: 100%; height: 100%; }
  .avatar .initial :global(svg) { width: 22px; height: 22px; }
  /* Favicon avatars: neutral disc so the logo reads cleanly. */
  .avatar.haslogo { background: #fff; }
  .avatar .logo-img { width: 24px; height: 24px; object-fit: contain; border-radius: 5px; }
  .shield { position: absolute; bottom: -3px; right: -3px; width: 16px; height: 16px; border-radius: 50%;
            display: grid; place-items: center; font-size: 12px; background: var(--bg); box-shadow: 0 0 0 1.5px var(--bg); }
  .shield :global(svg) { width: 13px; height: 13px; }
  .row.selected .shield { background: var(--sel); box-shadow: 0 0 0 1.5px var(--sel); }
  .shield.ok { color: var(--done); }
  .shield.bad { color: var(--danger); }
  .avatar .box { position: absolute; inset: 0; display: grid; place-items: center; border-radius: 50%; opacity: 0; transition: opacity 0.1s; }
  .avatar .box :global(svg) { width: 22px; height: 22px; }
  /* Keep the favicon/initial visible on hover; only swap to a checkbox once
     selection mode is active (or this row is checked). */
  .avatar.selecting .initial, .avatar.checked .initial { opacity: 0; }
  .avatar.selecting .box, .avatar.checked .box { opacity: 1; background: var(--surface-3); }
  .avatar.selecting .box { box-shadow: inset 0 0 0 2px var(--outline); }
  .avatar.checked { background: var(--accent); color: var(--on-accent); }
  .avatar.checked .box { background: var(--accent); box-shadow: none; color: var(--on-accent); }

  .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .line1 { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .from { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; line-height: 21px; }
  .replied {
    flex: none; margin-right: auto; align-self: center; display: inline-flex; align-items: center; gap: 3px;
    font-size: 11px; font-weight: 600; line-height: 1;
    padding: 3px 7px; border-radius: 6px;
    color: var(--on-accent-cont); background: var(--accent-cont);
  }
  .replied :global(svg) { width: 12px; height: 12px; }
  /* Group tag on new grouped mail - the group's own hue, like its chip icon. */
  .gtag {
    display: inline-flex; align-items: center; gap: 3px; max-width: 150px; margin-right: 6px; vertical-align: 1px;
    font-size: 11px; font-weight: 600; line-height: 1;
    padding: 3px 7px; border-radius: 6px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
    color: color-mix(in srgb, var(--tone) 70%, var(--text)); background: color-mix(in srgb, var(--tone) 16%, transparent);
  }
  .gtag :global(svg) { width: 12px; height: 12px; flex: none; }
  .time { flex: none; color: var(--muted); font-size: 12px; }
  .subject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; line-height: 20px; }
  .snippet { color: var(--muted); font-size: 13.5px; line-height: 19px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .marks { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: none; padding-top: 4px; }
  .marks :global(svg) { width: 17px; height: 17px; }
  .unread-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
  .star { color: var(--warning); }
  .pin { color: var(--accent); }
  .vip { color: #e8b923; }
  .clip { color: var(--muted); }

  .row-btn {
    flex: none; align-self: center; width: 36px; height: 36px; border-radius: 50%;
    color: var(--muted); background: var(--surface-2);
    display: grid; place-items: center; opacity: 0; transform: scale(0.9);
    transition: opacity var(--t-fast) var(--ease), background var(--t-fast) var(--ease),
      color var(--t-fast) var(--ease), transform var(--t) var(--ease-spring);
  }
  .row-btn :global(svg) { width: 20px; height: 20px; }
  .row:hover .row-btn, .row.focused .row-btn { opacity: 1; transform: scale(1); }
  .row-btn:hover { color: var(--text); background: var(--surface-3); }
  .row-btn:active { transform: scale(0.92); }
  .done-btn:hover { background: var(--done); color: var(--on-done); }
  .flag-btn.on, .flag-btn:hover { color: var(--warning); }
  .del-btn:hover { background: var(--danger); color: #fff; }
  .snooze-menu {
    position: absolute; right: 14px; top: 50%; z-index: 15;
    background: var(--surface-2); border-radius: var(--radius-menu);
    box-shadow: var(--shadow-lg); padding: 6px 0; display: flex; flex-direction: column; min-width: 180px;
    animation: pop-in var(--t) var(--ease); transform-origin: top right;
  }
  .snooze-menu button { text-align: left; padding: 9px 16px; border-radius: 0; color: var(--text); font-size: 14px; }
  .snooze-menu button:hover { background: var(--hover); }
  .snooze-menu .when { color: var(--muted); font-size: 12px; }
</style>
