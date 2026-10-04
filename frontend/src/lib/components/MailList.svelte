<script>
  import { untrack } from "svelte";
  import { fly, slide } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import { app, refreshMessages, markDone, toggleShowDone, prefetchBody, setCategory, snoozePresets, presetWhen, notify, saveCurrentSearch, openThread, refreshQueue, smartActive, groupedCategories, smartGroupOrder, searchAddress, snoozeMessage, muteSender, muteThread, muteNotificationsFromSender, pinMessage, isVip, isOutgoingView, toggleVip, isTrustedSender, toggleTrusted, blockSender, createRuleFromSender, openRuleModal, setSenderCategory, setMessageSeen, archiveMessage, deleteMessage, readerCommand, kbAll, approveSender, mergeById, runSemanticSearch, aiEnabled, openAiAssistant, addToAiChat, markAllRead, moveMessages, sendToLab } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { messages as messagesApi } from "../api.js";
  import MessageRow from "./MessageRow.svelte";
  import GroupRow from "./GroupRow.svelte";
  import SmartGroupStrip from "./SmartGroupStrip.svelte";
  import CategoryPeek from "./CategoryPeek.svelte";
  import SmartGroupsMenu from "./SmartGroupsMenu.svelte";
  import SigninBanner from "./SigninBanner.svelte";
  import SearchBar from "./SearchBar.svelte";
  import SearchPalette from "./SearchPalette.svelte";
  import { icons } from "../icons.js";
  import { smartGroupMeta } from "../groups.js";
  import { dismiss } from "../dismiss.js";
  import { keyCombo } from "../keys.js";

  let focusIndex = $state(0);
  let searchTimer;
  let expandedKeys = $state(new Set());
  let rowsEl;
  let paletteOpen = $state(false);

  // While the list is actively scrolling, rows sliding under a stationary cursor
  // would each fire :hover - which springs their action buttons in and animates
  // the row background. A whole scroll gesture becomes a rolling wave of spring
  // transitions + repaints (the "sluggish scroll" feel, and it happens at 30
  // rows just as much as at 300). Suppress hover mid-scroll: a class flips
  // pointer-events off on the rows while wheeling and back on ~140ms after it
  // stops, so hover still works normally when you're not scrolling.
  let scrolling = $state(false);
  let _scrollIdle = null;
  let _lastScroll = 0;
  // Scroll events fire every frame - don't allocate a fresh idle timer per event
  // (clearTimeout+setTimeout at 60+Hz). Stamp the last event time and let ONE
  // self-rescheduling timer decide when the gesture actually ended.
  function _scrollIdleCheck() {
    const rest = 140 - (performance.now() - _lastScroll);
    if (rest > 0) _scrollIdle = setTimeout(_scrollIdleCheck, rest);
    else { _scrollIdle = null; scrolling = false; }
  }
  function onRowsScroll() {
    _lastScroll = performance.now();
    if (!scrolling) scrolling = true;
    if (!_scrollIdle) _scrollIdle = setTimeout(_scrollIdleCheck, 140);
    closePeek(true);   // a peek anchored to a row that has scrolled away is wrong
  }

  // --- category hover peek -------------------------------------------------
  // Hovering a group card shows what just arrived in it. Opens on a short delay
  // (so sweeping the cursor across the list doesn't flash panels) and closes on
  // a shorter one, which is what lets the cursor cross the gap INTO the panel to
  // click a message.
  const PEEK_OPEN_MS = 320;
  const PEEK_CLOSE_MS = 140;
  let peek = $state(null);        // { item, rect }
  let _peekOpen, _peekClose;
  function schedulePeek(item, rect) {
    clearTimeout(_peekClose);
    if (scrolling) return;
    if (peek?.item?.key === item.key) { peek = { item, rect }; return; }  // re-anchor, no re-delay
    clearTimeout(_peekOpen);
    _peekOpen = setTimeout(() => { peek = { item, rect }; }, peek ? 0 : PEEK_OPEN_MS);
  }
  function schedulePeekClose() {
    clearTimeout(_peekOpen);
    clearTimeout(_peekClose);
    _peekClose = setTimeout(() => { peek = null; }, PEEK_CLOSE_MS);
  }
  function holdPeek() { clearTimeout(_peekClose); }
  function closePeek(now = false) {
    clearTimeout(_peekOpen);
    if (now) { clearTimeout(_peekClose); peek = null; }
    else schedulePeekClose();
  }
  // Clicking a mail in the peek opens it, and expands its group so the list
  // shows where you landed instead of leaving the reader orphaned.
  function openFromPeek(cat, m) {
    closePeek(true);
    if (!m?.id) return;
    openCategory(cat, "all");
    app.threadKey = null;
    app.selectedMessageId = m.id;
  }

  // Group the flat message list into items: plain messages, conversation threads,
  // or notification bundles, depending on settings.
  // Built-in categories + the user's custom groups (see lib/groups.js).
  const CAT_META = $derived.by(() => smartGroupMeta());
  // Grouped categories: a row from one of these in the main flow is new mail
  // that hasn't folded into its card yet, so it carries the group's tag.
  const groupedSet = $derived(new Set(groupedCategories()));
  let smartCatMsgs = $state({});  // category -> loaded messages (lazy on expand)
  // Bulk category-done hides ids we don't hold objects for; single-row done
  // relies on the row object's own is_done (so the store's undo, which flips
  // that flag back, also un-hides it here - a separate id set desynced).
  let hiddenDone = $state(new Set());
  const visibleIn = (arr) => (app.showDone ? arr : arr.filter((x) => !x.is_done && !hiddenDone.has(x.id)));
  function smartScope() {
    return app.selectedKind === "smart" ? { role: "inbox" } : { folder_id: app.selectedFolderId };
  }
  // Expanded groups fetch a SMALL page (newest first); "Show more" pages in
  // more on demand. Fetching a whole 500-mail category on expand froze the UI.
  // Each group has a MODE: "new" (unread + recent only, from the badge) or
  // "all" (the full category, from the header). Cache is keyed by cat|mode.
  const CAT_PAGE = 30;
  let groupMode = $state({});   // category -> "new" | "all"
  const modeOf = (cat) => groupMode[cat] || "all";
  const catKey = (cat) => cat + "|" + modeOf(cat);
  async function loadCategory(cat, limit = CAT_PAGE) {
    const key = catKey(cat);
    const cur = smartCatMsgs[key];
    if (cur && cur.limit >= limit) return;
    const params = { ...smartScope(), category: cat, include_done: app.showDone, limit };
    if (modeOf(cat) === "new") { params.unread_only = true; params.new_days = app.settings.smartNewDays ?? 3; }
    try {
      const msgs = await messagesApi.list(params);
      smartCatMsgs = { ...smartCatMsgs, [key]: { msgs, limit, full: msgs.length < limit, mode: modeOf(cat) } };
    } catch {}
  }
  function loadMoreCategory(cat) {
    loadCategory(cat, (smartCatMsgs[catKey(cat)]?.limit || CAT_PAGE) + 60);
  }
  // Expand a category group in a given mode (from the header = "all", from the
  // "N new" badge = "new"). Switching mode on an already-open group re-filters.
  function openCategory(cat, mode) {
    groupMode = { ...groupMode, [cat]: mode };
    // One group open at a time - it opens right under the strip, so a second
    // one would stack below the first and push your mail out of view.
    const grouped = new Set(groupedCategories());
    const s = new Set([...expandedKeys].filter((k) => !grouped.has(k)));
    s.add(cat); expandedKeys = s;
    loadCategory(cat);
  }
  function seeAll(cat) { openCategory(cat, "all"); }


  // Expanded bundles can hold hundreds of in-memory mails; render a window.
  const CHUNK = 12;
  let catShown = $state({});               // key -> rows currently rendered
  const shownFor = (key) => catShown[key] ?? CHUNK;
  function bumpShown(key) { catShown = { ...catShown, [key]: shownFor(key) + CHUNK }; }

  // The MAIN list is windowed too: mount 30 rows, stream in more as you
  // scroll. Rendering every message kept hundreds of live rows around, which
  // (combined with content-visibility) made every list mutation costly.
  const MAIN_CHUNK = 30;
  let mainShown = $state(30);
  function mainMore(node) {
    let io;
    io = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) mainShown += MAIN_CHUNK; },
      // Generous lookahead: the 30-row append (component mounts + layout) is the
      // one unavoidable hitch while scrolling - trigger it well before the
      // sentinel is anywhere near the viewport so it never lands mid-view.
      { root: rowsEl || null, rootMargin: "900px 0px" }
    );
    io.observe(node);
    return { destroy() { io?.disconnect(); } };
  }
  // Keyboard navigation can outrun the window - grow it before focus hits the edge.
  $effect(() => {
    const f = focusIndex;
    untrack(() => { if (f >= mainShown - 8) mainShown += MAIN_CHUNK; });
  });

  // Spark-style time buckets for the section headers.
  function dateBucket(iso) {
    if (!iso) return "Older";
    const d = new Date(iso);
    const now = new Date();
    const day = 86400000;
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startYesterday = startToday - day;
    const dow = (now.getDay() + 6) % 7;            // Monday-first
    const startWeek = startToday - dow * day;
    const startLastWeek = startWeek - 7 * day;
    const startMonth = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
    const startLastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1).getTime();
    const t = d.getTime();
    if (t >= startToday) return "Today";
    if (t >= startYesterday) return "Yesterday";
    if (t >= startWeek) return "This week";
    if (t >= startLastWeek) return "Last week";
    if (t >= startMonth) return "This month";
    if (t >= startLastMonth) return "Last month";
    return "Older";
  }
  // Date-bucket ids stay in English (grouping logic compares them); translate
  // only for display.
  const BUCKET_KEYS = { "Today": "list.today", "Yesterday": "list.yesterday", "This week": "list.thisWeek", "Last week": "list.lastWeek", "This month": "list.thisMonth", "Last month": "list.lastMonth", "Older": "list.older" };
  const bucketLabel = (b) => t(BUCKET_KEYS[b] || "list.older");


  // Flatten a group card + (when expanded) its loaded messages into the item
  // stream. Expanded rows are REAL items: keyboard-navigable, and `e` acts on
  // the focused row - previously they lived outside `items`, so focus stayed
  // on the card and `e` marked the ENTIRE group done.
  function expandGroup(g) {
    const out = [g];
    if (!expandedKeys.has(g.key)) return out;
    if (g.gtype === "category") {
      const mode = modeOf(g.category);
      const entry = smartCatMsgs[g.category + "|" + mode];
      if (!entry) { out.push({ kind: "groupload", key: "gl:" + g.key }); return out; }
      for (const m of visibleIn(entry.msgs)) out.push({ kind: "msg", msg: m, inGroup: true });
      const total = mode === "new" ? (g.new || 0) : (g.count || 0);
      const remaining = Math.max(0, total - entry.msgs.length);
      if (!entry.full && remaining > 0)
        out.push({ kind: "groupmore", key: "gm:" + g.key, cat: g.category, remaining });
      // In "new" mode, offer a jump to the whole category (read mail included).
      if (mode === "new")
        out.push({ kind: "groupseeall", key: "sa:" + g.key, cat: g.category, total: g.count || 0 });
      return out;
    }
    // Bundles/threads hold their messages in memory - window the render.
    const vis = visibleIn(g.msgs);
    const lim = shownFor(g.key);
    for (const m of vis.slice(0, lim)) out.push({ kind: "msg", msg: m, inGroup: true });
    if (vis.length > lim) out.push({ kind: "groupmore", key: "gm:" + g.key, gkey: g.key, remaining: vis.length - lim });
    return out;
  }

  function buildItems(msgs) {
    // A search is its own flat result set: refreshMessages() drops the Smart
    // Inbox fetch while app.search is set, so the cached app.smartGroupData
    // describes the *pre-search* folder. Rendering those cards next to results
    // showed unrelated newsletter/social mail (and expanding one fetched by
    // category with no `q`). Sender bundles are skipped for the same reason -
    // a `from:` search is all one sender, so it collapsed to a single bundle.
    if (smartActive() && !app.search) {
      // One fixed place for the groups: a strip at the top, in a stable order
      // (smartGroupOrder). The group you open lists its mail right under it.
      // Below, the timeline in date sections - new grouped mail included,
      // tagged, until it's read (see refreshMessages).
      const grouped = new Set(groupedCategories());
      const groups = [];
      for (const c of smartGroupOrder()) {
        const g = grouped.has(c) ? app.smartGroupData[c] : null;
        if (g && g.count > 0) {
          groups.push({ kind: "group", gtype: "category", key: c, category: c,
                        count: g.count, unread: g.unread || 0, new: g.new || 0,
                        latest: g.latest, recent: g.recent || [] });
        }
      }
      const out = [{ kind: "strip", key: "strip", groups }];
      const open = groups.find((g) => expandedKeys.has(g.key));
      if (open) out.push(...expandGroup(open));
      // With a group open, its new mail is listed under its header - don't
      // show the same message a second time down in the timeline.
      const shown = open ? msgs.filter((m) => m.category !== open.category) : msgs;
      let bucket = null;
      for (const m of shown) {
        const b = dateBucket(m.date);
        if (b !== bucket) { out.push({ kind: "header", key: "h:" + b, label: b }); bucket = b; }
        out.push({ kind: "msg", msg: m });
      }
      return out;
    }
    if (app.settings.threading) {
      const map = new Map();
      for (const m of msgs) {
        if (!map.has(m.thread_id)) map.set(m.thread_id, []);
        map.get(m.thread_id).push(m);
      }
      return [...map.values()].map((g) =>
        g.length > 1
          ? { kind: "group", gtype: "thread", key: g[0].thread_id, msgs: g, latest: g[0] }
          : { kind: "msg", msg: g[0] });
    }
    return msgs.map((m) => ({ kind: "msg", msg: m }));
  }
  const items = $derived.by(() => {
    const built = buildItems(app.messages);
    // Date-section layout has its own ordering (with header rows) - don't pull
    // pinned/VIP to the top or it would orphan the section headers.
    if (smartActive() && !app.search) return built;
    // Pinned first, then VIP-sender mail, then everything else (stable).
    // Never hoist rows living inside an expanded group out of their card.
    // VIP ranking is skipped in Sent/Drafts: every row there was written by you,
    // so the sender is your own identity - having one of your own addresses in
    // the VIP list hoisted that whole sent folder above newer mail from every
    // other account. Explicit pins still hold, since those are per-message.
    const outgoing = isOutgoingView();
    const isP = (it) => it.kind === "msg" && !it.inGroup && it.msg.pinned;
    const isV = (it) => !outgoing && it.kind === "msg" && !it.inGroup
      && !it.msg.pinned && isVip(it.msg.from_addr);
    const pinned = built.filter(isP);
    const vip = built.filter(isV);
    if (!pinned.length && !vip.length) return built;
    return [...pinned, ...vip, ...built.filter((it) => !isP(it) && !isV(it))];
  });

  function itemMsgs(item) { return item.kind === "msg" ? [item.msg] : item.msgs; }

  async function doneGroup(item) {
    const ids = item.msgs.map((m) => m.id);
    if (!app.showDone) { app.messages = app.messages.filter((m) => !ids.includes(m.id)); unselectIfGone(ids); }
    try {
      await messagesApi.bulk(ids, "done");
      notify(t("list.markedDone", { n: ids.length }), "info", () => {
        messagesApi.bulk(ids, "undone")
          .then(() => refreshMessages({ background: true }))
          .catch(() => notify(t("list.couldntUndo"), "error"));
      });
      refreshMessages({ background: true });
    } catch (e) { notify(t("list.couldntUpdate"), "error"); refreshMessages({ background: true }); }
  }

  // Mark an entire Smart Inbox category done (every mail in it, not just the
  // loaded window). Used by the card's "Done all" button and the `e` shortcut.
  async function doneCategory(item) {
    try {
      // "Done all" must cover the ENTIRE category - fetch the full id list
      // unless the paged cache already holds everything.
      const entry = smartCatMsgs[item.category + "|all"];
      let list = entry?.full ? entry.msgs : null;
      if (!list) list = await messagesApi.list({ ...smartScope(), category: item.category, include_done: false, limit: 5000 });
      const ids = list.map((m) => m.id);
      if (!ids.length) return;
      const idset = new Set(ids);
      app.messages = app.messages.filter((m) => !idset.has(m.id));   // optimistic
      unselectIfGone(ids);
      hiddenDone = new Set([...hiddenDone, ...ids]);
      const s = new Set(expandedKeys); s.delete(item.key); expandedKeys = s;  // collapse
      await messagesApi.bulk(ids, "done");
      // A category-done can touch hundreds/thousands of messages - always offer
      // undo (single-message done already does; this destructive bulk must too).
      notify(t("list.markedDone", { n: ids.length }), "info", () => {
        hiddenDone = new Set([...hiddenDone].filter((id) => !idset.has(id)));
        messagesApi.bulk(ids, "undone")
          .then(() => refreshMessages({ background: true }))
          .catch(() => notify(t("list.couldntUndo"), "error"));
      });
      refreshMessages({ background: true });   // also refreshes the group counts
    } catch { notify(t("list.couldntMarkGroupDone"), "error"); refreshMessages({ background: true }); }
  }
  function toggleExpand(key) {
    const s = new Set(expandedKeys);
    s.has(key) ? s.delete(key) : s.add(key);
    expandedKeys = s;
  }
  function activate(item) {
    if (item.gtype === "category") {
      // Header click always means "the whole category". Toggle closed if it's
      // already open in all-mode; otherwise (re)open in all-mode.
      if (expandedKeys.has(item.key) && modeOf(item.category) === "all") toggleExpand(item.key);
      else openCategory(item.category, "all");
      return;
    }
    if (selectedIds.length > 0) { selectGroup(item); return; }
    if (item.gtype === "thread") openThread(item.latest);
    else toggleExpand(item.key);
  }
  function selectGroup(item) {
    const ids = item.msgs.map((m) => m.id);
    const allSel = ids.every((id) => selectedIds.includes(id));
    const set = new Set(selectedIds);
    ids.forEach((id) => (allSel ? set.delete(id) : set.add(id)));
    selectedIds = [...set];
  }
  const groupChecked = (item) => item.msgs.every((m) => selectedIds.includes(m.id));

  // --- multi-select ---
  let selectedIds = $state([]);
  let lastIdx = -1;
  let bulkSnooze = $state(false);
  const isChecked = (id) => selectedIds.includes(id);

  function toggleSelect(msg, index, e) {
    // Shift-range only makes sense for rows that live in `items` (index >= 0).
    // Nested bundle rows pass index < 0 and just toggle themselves - using the
    // group's index produced a zero-width range that selected the whole bundle.
    if (e?.shiftKey && lastIdx >= 0 && index >= 0) {
      const [a, b] = [Math.min(lastIdx, index), Math.max(lastIdx, index)];
      // Ranges can span headers, category cards, and group frames - only rows
      // with actual messages contribute ids.
      const ids = items.slice(a, b + 1).flatMap((it) =>
        it.kind === "msg" ? [it.msg.id] : (it.msgs ? it.msgs.map((m) => m.id) : []));
      const set = new Set(selectedIds);
      ids.forEach((id) => set.add(id));
      selectedIds = [...set];
    } else {
      selectedIds = isChecked(msg.id) ? selectedIds.filter((x) => x !== msg.id) : [...selectedIds, msg.id];
    }
    if (index >= 0) lastIdx = index;
  }
  function clearSelection() { selectedIds = []; lastIdx = -1; bulkSnooze = false; }

  // --- Smart Inbox group picker (search-row button / right-click a card) ---
  let groupsMenu = $state(null);   // { x, y }
  let groupsBtn = $state();
  function toggleGroupsMenu() {
    if (groupsMenu) { groupsMenu = null; return; }
    const r = groupsBtn.getBoundingClientRect();
    groupsMenu = { x: r.left, y: r.bottom + 6 };
  }

  // --- right-click context menu ---
  let ctx = $state(null); // { x, y, msg }
  let ctxSearch = $state("");
  let ctxSub = $state(null);   // label of the open submenu (null = top level)
  function openCtx(e, msg) {
    e.preventDefault();
    ctxSearch = "";
    ctxSub = null;
    // Right-clicking a row that's part of a multi-selection acts on the WHOLE
    // selection (group menu); otherwise it's the usual single-message menu.
    const group = selectedIds.length > 1 && selectedIds.includes(msg.id);
    ctx = { x: e.clientX, y: e.clientY, msg, group };
  }
  function closeCtx() { ctx = null; }
  function ctxDo(fn) { const m = ctx?.msg; closeCtx(); if (m) fn(m); }
  function toggleSeen(m) { setMessageSeen(m, !m.is_seen); }
  function toggleFlag(m) { const v = !m.is_flagged; m.is_flagged = v; messagesApi.setFlag(m.id, v).catch(() => {}); }

  // The right-click menu. Long lists (where to file the sender, snooze times,
  // sender options, rules) live in submenus - `sub` entries open in place with
  // a Back row - so the top level stays short. `kw` adds search keywords;
  // typing searches submenu entries too (see ctxShown).
  function ctxActions(m) {
    return [
      // -1: the right-clicked row isn't necessarily the keyboard-focused one.
      { label: t("list.open"), run: () => open(m, -1) },
      ...(aiEnabled() ? [{ label: t("list.addToAiChat"), icon: icons.bolt, kw: "ai assistant chat context", run: () => addToAiChat(m) }] : []),
      { sep: "" },
      { label: m.is_done ? t("list.markNotDone") : t("list.markDone"), icon: icons.done, kw: "complete e", run: () => markDone(m, !m.is_done) },
      { label: m.is_seen ? t("list.markUnread") : t("list.markRead"), kw: "seen", run: () => toggleSeen(m) },
      { label: m.is_flagged ? t("list.unflag") : t("list.flag"), icon: icons.flag, kw: "star", run: () => toggleFlag(m) },
      { label: m.pinned ? t("list.unpin") : t("list.pinToTop"), icon: icons.pin, run: () => pinMessage(m) },
      { label: t("list.snooze"), icon: icons.snooze, kw: "remind later", sub:
        snoozePresets().map((p) => ({ label: p.label, icon: icons.snooze, kw: "snooze remind later", run: () => snoozeMessage(m, p.iso, p.presence) })) },
      { sep: "" },
      { label: t("list.archive"), icon: icons.archive, run: () => archiveOne(m) },
      { label: t("list.delete"), icon: icons.trash, danger: true, run: () => deleteOne(m) },
      { label: t("list.moveSenderTo"), icon: icons.inboxMove || icons.inbox, kw: "move category group newsletter", sub: [
        { label: t("list.catPrimary"), icon: icons.inbox, kw: "move out newsletter normal queue primary inbox", run: () => setSenderCategory(m, "primary") },
        ...Object.entries(CAT_META).map(([id, meta]) => ({ label: meta.label, icon: meta.icon, kw: "move category " + id, run: () => setSenderCategory(m, id) })),
        { label: t("list.resetCategory"), icon: icons.reset, kw: "move category auto", run: () => setSenderCategory(m, "auto") },
      ] },
      { sep: t("list.senderHead") },
      { label: t("list.showMailFromSender"), kw: "filter from", run: () => searchAddress(m.from_addr) },
      { label: t("list.senderOptions"), icon: icons.contacts, kw: "vip safe mute block", sub: [
        { label: isVip(m.from_addr) ? t("list.removeVip") : t("list.markSenderVip"), icon: icons.star, run: () => toggleVip(m.from_addr) },
        { label: isTrustedSender(m.from_addr) ? t("list.unmarkSafe") : t("list.markSenderSafe"), icon: icons.shieldCheck, run: () => toggleTrusted(m.from_addr) },
        { label: t("list.muteSender"), icon: icons.mute, run: () => muteSender(m) },
        { label: t("rules.muteFromSender"), icon: icons.bell, kw: "notification notify silence", run: () => muteNotificationsFromSender(m) },
        { label: t("list.muteConversation"), icon: icons.mute, kw: "thread", run: () => muteThread(m) },
        { label: t("list.blockSender"), icon: icons.junk, danger: true, run: () => blockSender(m) },
      ] },
      { label: t("list.rulesSub"), icon: icons.bolt, kw: "rule filter automate group", sub: [
        { label: t("list.createRule"), icon: icons.bolt, run: () => createRuleFromSender(m) },
        { label: t("groups.groupRule"), icon: icons.folder, kw: "rule group smart inbox collapse category", run: () => openRuleModal(m, undefined, { action: "set_group", action_arg: (app.settings.customGroups || []).at(-1)?.id || "" }) },
      ] },
      { label: t("list.sendToLab"), icon: icons.shieldCheck, kw: "security lab scan analyze forensics virustotal headers domain ip whois", run: () => sendToLab(m) },
    ];
  }
  // Group right-click menu: the selection-bar actions plus move-to-folder, applied
  // to the whole current selection.
  function moveSelectionTo(f) { const ids = [...selectedIds]; clearSelection(); moveMessages(ids, f); }
  function ctxGroupActions(msg) {
    const targets = app.folders.filter((f) => f.account_id === msg.account_id && f.id !== msg.folder_id);
    return [
      { label: t("list.markDone"), icon: icons.done, kw: "complete e", run: () => bulk("done") },
      { label: t("list.markRead"), kw: "seen", run: () => bulk("seen") },
      { label: t("list.flag"), icon: icons.flag, kw: "star", run: () => bulk("flag") },
      { label: t("list.snooze"), icon: icons.snooze, kw: "remind later", sub:
        snoozePresets().filter((p) => p.iso).map((p) => ({ label: p.label, icon: icons.snooze, kw: "snooze remind later", run: () => bulk("snooze", p.iso) })) },
      { sep: "" },
      { label: t("list.archive"), icon: icons.archive, run: () => bulk("archive") },
      { label: t("list.delete"), icon: icons.trash, danger: true, run: () => bulk("delete") },
      ...(targets.length ? [{ label: t("list.moveToFolder"), icon: icons.folder, kw: "move folder", sub:
        targets.map((f) => ({ label: f.name, icon: icons.folder, kw: "move folder " + f.name, run: () => moveSelectionTo(f) })) }] : []),
      { sep: "" },
      { label: t("list.clearSelection"), icon: icons.close, run: () => clearSelection() },
    ];
  }
  const currentCtxActions = () => (ctx?.group ? ctxGroupActions(ctx.msg) : ctxActions(ctx.msg));
  // What the menu shows right now: a search flattens everything (submenu
  // entries included, so "newsl" still finds "Newsletters"); an open submenu
  // shows its entries under a Back row; otherwise the top level.
  function ctxShown() {
    const acts = currentCtxActions();
    const q = ctxSearch.trim().toLowerCase();
    if (q) {
      const flat = acts.flatMap((a) => (a.sub ? a.sub.map((x) => ({ ...x, label: `${a.label} › ${x.label}` })) : [a]));
      return flat.filter((a) => !a.sep && ((a.label + " " + (a.kw || "")).toLowerCase().includes(q)));
    }
    // (Read-only: this runs while the menu renders, so a stale ctxSub just
    // falls back to the top level instead of being reset here.)
    const parent = ctxSub ? acts.find((a) => a.sub && a.label === ctxSub) : null;
    return parent ? [{ back: true, label: parent.label }, ...parent.sub] : acts;
  }
  function runCtx(a) {
    if (!a) return;
    if (a.back) { ctxSub = null; return; }
    if (a.sub) { ctxSub = a.label; return; }
    if (a.run) ctxDo(a.run);
  }
  function ctxEnter() {
    const first = ctxShown().find((a) => !a.sep && !a.back);
    if (first) runCtx(first);
  }

  // Position the menu fully on-screen - flip up/left near edges, cap height.
  function placeMenu(node, pos) {
    const apply = (p) => {
      // Layout size, not getBoundingClientRect: the menu pops in scaled down,
      // so its on-screen box is still too small here and it would be left
      // hanging off the bottom of the window.
      const r = { width: node.offsetWidth, height: node.offsetHeight };
      const vw = window.innerWidth, vh = window.innerHeight, pad = 8;
      let x = p.x, y = p.y;
      if (x + r.width > vw - pad) x = Math.max(pad, vw - r.width - pad);
      if (y + r.height > vh - pad) y = Math.max(pad, vh - r.height - pad);
      node.style.left = `${x}px`;
      node.style.top = `${y}px`;
    };
    requestAnimationFrame(() => apply(pos));
    return { update: (p) => requestAnimationFrame(() => apply(p)) };
  }
  // Removing the open message must also clear the reader, or it keeps showing
  // (and later re-fetches) mail that's gone.
  function unselectIfGone(ids) {
    if (ids.includes(app.selectedMessageId)) { app.selectedMessageId = null; app.threadKey = null; }
  }
  // Store-level: optimistic removal + advance to the next message + toast.
  const archiveOne = (m) => archiveMessage(m);
  const deleteOne = (m) => deleteMessage(m);

  async function bulk(action, until = null) {
    const ids = [...selectedIds];
    if (!ids.length) return;
    // Optimistic: drop affected rows from the current view for removing actions.
    if (["done", "snooze", "archive", "delete"].includes(action) && !app.showDone) {
      app.messages = app.messages.filter((m) => !ids.includes(m.id));
      unselectIfGone(ids);
    }
    clearSelection();
    try {
      await messagesApi.bulk(ids, action, until);
      const doneKey = { done: "list.markedDone", seen: "list.bulkRead", flag: "list.bulkFlagged", snooze: "list.bulkSnoozed", archive: "list.bulkArchived", delete: "list.bulkDeleted" }[action] || "list.bulkUpdated";
      if (action === "archive" || action === "delete") {
        // Undoable: the backend holds the IMAP move past the toast window.
        notify(t(doneKey, { n: ids.length }), "info", () => {
          messagesApi.restore(ids)
            .then(() => { refreshQueue(); refreshMessages({ background: true }); })
            .catch(() => notify(t("list.couldntUndo"), "error"));
        });
      } else {
        notify(t(doneKey, { n: ids.length }));
      }
      refreshMessages({ background: true });
      if (action === "archive" || action === "delete") refreshQueue();
    } catch (e) { notify(t("list.bulkFailed", { error: e.message }), "error"); refreshMessages({ background: true }); }
  }

  // Drag a message (or the whole multi-selection) onto a sidebar folder to move
  // it. We stash the ids + account in the store so the Sidebar's drop handler can
  // validate (same-account only) and call moveMessages. Native HTML5 DnD.
  function onRowDragStart(e, msg) {
    const ids = selectedIds.length && selectedIds.includes(msg.id) ? [...selectedIds] : [msg.id];
    app.dragMessageIds = ids;
    app.dragAccountId = msg.account_id;
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", ids.join(",")); } catch {}
    }
  }
  function onRowDragEnd() { app.dragMessageIds = []; app.dragAccountId = null; }

  // Clear selection + per-view caches when the view changes (a different scope
  // has different category contents).
  $effect(() => {
    void app.selectedFolderId; void app.selectedKind; void app.category; void app.search;
    clearSelection();
    smartCatMsgs = {};
    hiddenDone = new Set();
    expandedKeys = new Set();   // collapsed cards re-fetch on next expand
    groupMode = {};
    catShown = {};
    mainShown = 30;
    closePeek(true);
  });

  // Row-by-row entrance cascade (like the home screen). Replays on every view
  // switch - the rows block is re-keyed on this same value - then switches OFF a
  // moment later so scrolling more rows in / triage reorders don't re-animate.
  const viewKey = $derived(`${app.selectedKind}|${app.selectedFolderId}|${app.category}|${app.search}`);
  let intro = $state(false);
  let _introTimer;
  $effect(() => {
    void viewKey;
    intro = true;
    clearTimeout(_introTimer);
    _introTimer = setTimeout(() => { intro = false; }, 650);
    return () => clearTimeout(_introTimer);
  });

  // Keep expanded category lists live: refetch them in place when a sync lands
  // (a cleared cache would flash "Loading…" inside every open card). Refetch
  // only at each group's CURRENT page size - not the whole category.
  $effect(() => {
    void app.syncTick;
    const entries = untrack(() => Object.entries(smartCatMsgs));
    for (const [key, entry] of entries) {
      const cat = key.split("|")[0];
      const params = { ...smartScope(), category: cat, include_done: app.showDone, limit: entry.limit };
      if (entry.mode === "new") { params.unread_only = true; params.new_days = app.settings.smartNewDays ?? 3; }
      untrack(() => messagesApi.list(params))
        .then((msgs) => {
          // Preserve row identity across the refetch so open category cards don't
          // flicker every sync (same fix as the main list).
          if (smartCatMsgs[key]) {
            const merged = mergeById(smartCatMsgs[key].msgs, msgs);
            smartCatMsgs = { ...smartCatMsgs, [key]: { msgs: merged, limit: entry.limit, full: msgs.length < entry.limit, mode: entry.mode } };
          }
        })
        .catch(() => {});
    }
  });

  // Keep focusIndex in range as the list changes.
  $effect(() => {
    if (focusIndex >= items.length) focusIndex = Math.max(0, items.length - 1);
  });

  // Prefetch the focused item's latest message (urgent - jumps the queue) plus
  // the next one, so opening / arrowing through is instant.
  const _pfId = (it) => (it?.kind === "msg" ? it.msg.id : it?.latest?.id);
  $effect(() => {
    const id = _pfId(items[focusIndex]);
    if (id) prefetchBody(id, true);
    const nx = _pfId(items[focusIndex + 1]);
    if (nx) prefetchBody(nx);
  });

  // Keep the focused row visible when navigating with the keyboard.
  $effect(() => {
    const el = rowsEl?.children?.[focusIndex];
    if (el) el.scrollIntoView({ block: "nearest" });
  });

  function onSearch(v) {
    clearTimeout(searchTimer);
    // app.search is set WITH the (debounced) fetch, not per keystroke - the
    // rows block is keyed on the view scope (incl. search), so an eager
    // assignment would tear down and remount the whole list on every letter.
    // Typing in the bar is always a keyword search (clears any semantic mode).
    searchTimer = setTimeout(() => { app.search = v; app.semantic = false; refreshMessages(); }, 220);
  }
  // Immediate apply (from the palette): keep the bar + main list in sync at once.
  function applySearch(v) {
    clearTimeout(searchTimer);
    app.search = v; app.semantic = false; refreshMessages();
  }
  function saveSearch() {
    const name = prompt(t("list.namePrompt"), app.search);
    if (name) saveCurrentSearch(name.trim());
  }

  // Pull keyboard focus back to the list. Opening a message loads the reader
  // iframe, which (in the desktop webview) grabs focus - after which shortcuts
  // like `e` land in the iframe and appear dead until you click the list again.
  function refocusList() {
    queueMicrotask(() => {
      const ae = document.activeElement;
      if (ae instanceof HTMLInputElement || ae instanceof HTMLTextAreaElement || ae?.isContentEditable) return;
      rowsEl?.focus?.({ preventScroll: true });
    });
  }

  async function open(message, index, e) {
    // Ctrl/Cmd-click or Shift-click builds a multi-selection instead of opening
    // the mail - the standard way to start selecting without hunting for the
    // avatar checkbox. Shift extends a range; Ctrl/Cmd toggles a single row.
    if (e && (e.ctrlKey || e.metaKey || e.shiftKey)) {
      toggleSelect(message, index, e);
      if (index >= 0) focusIndex = index;
      return;
    }
    // Already in selection mode: a plain click adds/removes from the selection.
    if (selectedIds.length > 0) { toggleSelect(message, index); return; }
    // index < 0 = a message nested inside an expanded bundle/group; it has no
    // slot in `items`, so don't move keyboard focus to the group card (that's
    // what made a subsequent `e` mass-complete the whole category).
    if (index >= 0) focusIndex = index;
    // Conversations open as conversations - but ONLY when the user has
    // "Conversation threading" turned on. With it off, every message opens as a
    // single mail (opening a thread sibling used to still flip the thread view,
    // which looked like the toggle was ignored). Siblings visible in the loaded
    // list flip the thread view instantly; siblings elsewhere are caught by the
    // Reader's thread check (also gated on the setting).
    app.threadKey =
      (app.settings.threading && message.thread_id &&
       app.messages.some((m) => m.thread_id === message.thread_id && m.id !== message.id))
        ? message.thread_id : null;
    app.selectedMessageId = message.id;
    if (!message.is_seen) setMessageSeen(message, true);   // instant -1 on badges
    refocusList();
  }

  function onKey(e) {
    // Never hijack keys while composing, in a dialog, or typing in any field
    // (inputs, textareas, or the contenteditable compose/signature editors).
    if (app.composing || app.paletteOpen || app.confirm) return;
    const t = e.target;
    if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || (t && t.isContentEditable)) return;
    const kb = kbAll();
    const combo = keyCombo(e);
    if (!combo) return;
    if (e.key === "Escape" && peek) { closePeek(true); return; }
    if (peek) closePeek(true);   // keyboard navigation means the cursor isn't driving
    if (combo === kb.search) {
      // Respect the user's preferred search surface: the full modal, or the
      // inline bar in the list header.
      if (app.settings.searchStyle === "modal") paletteOpen = true;
      else document.querySelector(".list .search")?.focus();
      e.preventDefault(); return;
    }
    if (!items.length) return;
    // Skip non-interactive rows (date headers, group loaders) when arrowing.
    const SKIP = new Set(["header", "groupload"]);
    const step = (dir) => {
      let i = focusIndex;
      for (let n = 0; n < items.length; n++) {
        i = Math.min(items.length - 1, Math.max(0, i + dir));
        if (!SKIP.has(items[i]?.kind)) break;
        if (i === 0 || i === items.length - 1) break;
      }
      focusIndex = i;
    };
    if (combo === kb.next || combo === kb.prev) {
      step(combo === kb.next ? 1 : -1);
      // Arrowing through the list opens the focused mail immediately (Spark-style)
      // - no separate Enter needed. Only for real messages; group cards / loaders
      // just move the highlight and open on Enter.
      const it = items[focusIndex];
      if (it?.kind === "msg") open(it.msg, focusIndex);
      e.preventDefault();
    } else if (combo === kb.open) {
      const it = items[focusIndex];
      if (it.kind === "msg") open(it.msg, focusIndex);
      else if (it.kind === "group") activate(it);
      else if (it.kind === "groupmore") { if (it.cat) loadMoreCategory(it.cat); else bumpShown(it.gkey); }
      else if (it.kind === "groupseeall") seeAll(it.cat);
    } else if (combo === kb.done) {
      const it = items[focusIndex];
      if (it.kind !== "msg" && it.kind !== "group") { e.preventDefault(); return; }
      if (it.kind === "msg") {
        // The store's markDone handles open-next-on-done itself (when the done
        // message was the open one) - a second advance here picked a DIFFERENT
        // "next" (items is re-sorted) and marked an unseen message read.
        markDone(it.msg, !it.msg.is_done);
      } else if (it.gtype === "category") doneCategory(it);
      else doneGroup(it);
      refocusList();
      e.preventDefault();
    } else if (combo === kb.reply || combo === kb.forward) {
      // Reply/forward the OPEN message (single or conversation) - the reader
      // surfaces own the bodies needed to build the quote.
      if (app.selectedMessageId != null || app.threadKey) {
        readerCommand(combo === kb.reply ? "reply" : "forward");
        e.preventDefault();
      }
    } else if (combo === kb.archive || combo === kb.delete) {
      const it = items[focusIndex];
      if (it?.kind === "msg") {
        (combo === kb.archive ? archiveOne : deleteOne)(it.msg);
        refocusList();
        e.preventDefault();
      }
    } else if (combo === kb.read) {
      const it = items[focusIndex];
      if (it?.kind === "msg") { toggleSeen(it.msg); e.preventDefault(); }
    }
  }

  const title = $derived(
    app.search ? t("list.titleSearch", { q: app.search }) :
    app.selectedKind === "smart" ? t("list.smartInbox") :
    app.selectedKind === "unified" ? t("list.allInboxes") :
    app.selectedKind === "sent" ? t("list.allSent") :
    app.selectedKind === "snoozed" ? t("list.snoozed") :
    app.selectedKind === "screener" ? t("list.screener") :
    app.selectedKind === "papertrail" ? t("list.paperTrail") :
    app.selectedKind === "followups" ? t("list.followUps") :
    (app.folders.find((f) => f.id === app.selectedFolderId)?.name || t("list.inbox"))
  );

  // Show "Mark all read" when the current view has any unread - either in the
  // loaded stream or hidden inside a Smart Inbox group card.
  const hasUnread = $derived(
    app.messages.some((m) => !m.is_seen) ||
    (smartActive() && !app.search && Object.values(app.smartGroupData || {}).some((g) => (g?.unread || 0) > 0))
  );

  const CATS = $derived.by(() => ([
    { id: null, label: t("list.catAll") },
    { id: "primary", label: t("list.catPrimary") },
    { id: "newsletters", label: t("list.catNewsletters") },
    { id: "social", label: t("list.catSocial") },
    { id: "updates", label: t("list.catUpdates") },
    { id: "promotions", label: t("list.catPromotions") },
    ...(app.settings.customGroups || []).map((g) => ({ id: g.id, label: g.name })),
  ]));
  const showCats = $derived(
    !app.search && !smartActive() && app.selectedKind !== "snoozed" && app.selectedKind !== "screener" &&
    (app.selectedKind === "unified" || app.selectedFolderRole === "inbox")
  );

  const emptyState = $derived(
    app.search ? { icon: icons.search, text: t("list.emptySearch") } :
    app.selectedKind === "snoozed" ? { icon: icons.snooze, text: t("list.emptySnoozed") } :
    app.selectedKind === "screener" ? { icon: icons.screener, text: t("list.emptyScreener") } :
    app.selectedKind === "papertrail" ? { icon: icons.receipt, text: t("list.emptyPapertrail") } :
    app.selectedKind === "followups" ? { icon: icons.done, text: t("list.emptyFollowups") } :
    { icon: icons.inboxZero, text: t("list.emptyInbox") }
  );
</script>

<svelte:window on:keydown={onKey} />

<SearchPalette open={paletteOpen} initial={app.search}
  smartAvailable={aiEnabled() || app.settings.semanticEnabled}
  onclose={() => (paletteOpen = false)}
  onsearch={(q) => applySearch(q)}
  onsemantic={(q) => runSemanticSearch(q)}
  onopen={(m) => open(m, -1)} />

{#if peek}
  <CategoryPeek
    rect={peek.rect}
    label={CAT_META[peek.item.category]?.label || peek.item.category}
    icon={CAT_META[peek.item.category]?.icon || icons.folder}
    tone={CAT_META[peek.item.category]?.tone || ""}
    recent={peek.item.recent}
    count={peek.item.count}
    newCount={peek.item.new}
    onenter={holdPeek}
    onleave={() => schedulePeekClose()}
    onopen={(m) => openFromPeek(peek.item.category, m)}
  />
{/if}

{#if groupsMenu}
  <SmartGroupsMenu x={groupsMenu.x} y={groupsMenu.y} anchor={groupsBtn} onclose={() => (groupsMenu = null)} />
{/if}

{#if ctx}
  <div class="ctxmenu" use:placeMenu={{ x: ctx.x, y: ctx.y }} use:dismiss={closeCtx} onclick={(e) => e.stopPropagation()}>
    {#if ctx.group}<div class="ctx-title">{t("list.selectionActions", { n: selectedIds.length })}</div>{/if}
    <input class="ctx-search" placeholder={t("list.searchActions")} bind:value={ctxSearch} autofocus
      onkeydown={(e) => { if (e.key === "Enter") ctxEnter(); else if (e.key === "Escape") closeCtx(); }} />
    <div class="ctx-list">
      {#each ctxShown() as a}
        {#if a.sep !== undefined}
          {#if a.sep}<div class="ctx-head">{a.sep}</div>{:else}<div class="ctx-sep"></div>{/if}
        {:else if a.back}
          <button class="ctx-back" onclick={() => runCtx(a)}><span class="ctx-ic">{@html icons.back}</span>{a.label}</button>
        {:else}
          <button class:danger={a.danger} class:hassub={!!a.sub} onclick={() => runCtx(a)}>
            <span class="ctx-ic">{@html a.icon || ""}</span>{a.label}{#if a.sub}<span class="ctx-arrow">{@html icons.chevronRight}</span>{/if}
          </button>
        {/if}
      {/each}
      {#if ctxShown().length === 0}<div class="ctx-empty">{t("list.noMatchingAction")}</div>{/if}
    </div>
  </div>
{/if}

<section class="list">
  <header>
    <SigninBanner />
    <!-- Google-style search bar: one pill holding the query, Save, filters and AI. -->
    <div class="searchrow">
      <SearchBar value={app.search} oninput={onSearch} onexpand={() => (paletteOpen = true)} />
      {#if app.search.trim()}<button class="savesearch" title={t("list.saveSmartFolder")} onclick={saveSearch}>{@html icons.star} {t("list.save")}</button>{/if}
      <button class="adv" title={t("search.advancedTitle")} aria-label={t("search.filters")} onclick={() => (paletteOpen = true)}>{@html icons.sliders}</button>
      {#if aiEnabled()}
        <button class="adv aibtn" title={t("list.aiAssistant")} aria-label={t("list.aiAssistant")}
          onclick={() => openAiAssistant({ messageId: app.selectedMessageId, threadKey: app.threadKey || "" })}>{@html icons.sparkles}</button>
      {/if}
    </div>
    <div class="row1">
      {#if app.selectedKind === "smart"}
        <!-- The open group names itself (and closes) in its header under the
             strip, so the title stays put instead of turning into a breadcrumb. -->
        <h2>{t("list.smartInbox")}</h2>
      {:else}
        <h2>{title}</h2>
      {/if}
      <div class="row1-actions">
        {#if hasUnread}
          <button class="markread" title={t("list.markAllReadTip")} aria-label={t("list.markAllRead")} onclick={markAllRead}>
            {@html icons.doneAll}
          </button>
        {/if}
        <label class="slider" title={t("list.showDoneTip")}>
          <input type="checkbox" checked={app.showDone} onchange={toggleShowDone} />
          <span class="track"><span class="knob"></span></span>
          <span class="lbl">{app.showDone ? t("list.showingAll") : t("list.showDone")}</span>
        </label>
      </div>
    </div>
    {#if showCats}
      <div class="cats">
        {#each CATS as cat}
          <button class="cat" class:active={app.category === cat.id} onclick={() => setCategory(cat.id)}>{cat.label}</button>
        {/each}
      </div>
    {/if}
  </header>

  {#if selectedIds.length > 0}
    <div class="bulkbar" transition:slide={{ duration: 140, easing: cubicOut }}>
      <span class="count">{t("list.nSelected", { n: selectedIds.length })}</span>
      <button onclick={() => bulk("done")} title={t("list.markDone")}>{@html icons.done} {t("list.done")}</button>
      <button onclick={() => bulk("seen")} title={t("list.markRead")}>{t("list.read")}</button>
      <button onclick={() => bulk("flag")} title={t("list.flag")}>{@html icons.flag} {t("list.flag")}</button>
      <div class="snz">
        <button onclick={() => (bulkSnooze = !bulkSnooze)}>{@html icons.snooze} {t("list.snooze")}</button>
        {#if bulkSnooze}
          <div class="snz-menu">
            {#each snoozePresets().filter((p) => p.iso) as p}<button onclick={() => bulk("snooze", p.iso)}>{p.label}</button>{/each}
          </div>
        {/if}
      </div>
      <button onclick={() => bulk("archive")} title={t("list.archive")}>{@html icons.archive} {t("list.archive")}</button>
      <button class="danger" onclick={() => bulk("delete")} title={t("list.delete")}>{@html icons.trash} {t("list.delete")}</button>
      <button class="clear" onclick={clearSelection}>{@html icons.close}</button>
    </div>
  {/if}

  <div class="rows" class:intro class:scrolling bind:this={rowsEl} tabindex="-1" onscroll={onRowsScroll}>
    <!-- Keyed on the view scope: switching folder/category/search tears the old
         rows down instantly instead of playing ~100 simultaneous out-flights -
         that mass animation was the "whole app hitches on navigation" feel.
         Triage removals inside one view still animate (each row's own out:fly).
         No animate:flip here on purpose: FLIP measures every kept row on each
         list mutation, and getBoundingClientRect on a content-visibility:auto
         row force-realizes it, so flip + .cv fought each other on every scroll
         append and background sync. -->
    {#key viewKey}
    {#if app.loading && app.messages.length === 0}
      {#each Array(6) as _}
        <div class="skel"><div class="sk-av"></div><div class="sk-lines"><div class="sk-l"></div><div class="sk-l short"></div></div></div>
      {/each}
    {:else if app.messages.length === 0}
      <div class="empty">
        <div class="big">{@html emptyState.icon}</div>
        {emptyState.text}
      </div>
    {:else}
      {#each items.slice(0, mainShown) as item, i (item.kind === "msg" ? (item.inGroup ? "gm" : "m") + item.msg.id : item.kind === "group" ? "g" + item.key : item.key)}
        <div class:bundled={item.kind === "msg" && item.inGroup} class:cv={item.kind !== "header"}
             draggable={item.kind === "msg"}
             ondragstart={item.kind === "msg" ? (e) => onRowDragStart(e, item.msg) : undefined}
             ondragend={item.kind === "msg" ? onRowDragEnd : undefined}
             out:fly={{ x: 48, duration: 140 }}>
          {#if item.kind === "header"}
            <div class="datesep">{bucketLabel(item.label)}</div>
          {:else if item.kind === "msg"}
            <MessageRow
              message={item.msg}
              focused={i === focusIndex}
              selected={app.selectedMessageId === item.msg.id}
              checked={isChecked(item.msg.id)}
              selecting={selectedIds.length > 0}
              screener={app.selectedKind === "screener"}
              onselect={(e) => toggleSelect(item.msg, i, e)}
              onopen={(e) => open(item.msg, i, e)}
              ondone={() => markDone(item.msg, !item.msg.is_done)}
              onarchive={() => archiveOne(item.msg)}
              ondelete={() => deleteOne(item.msg)}
              onapprove={() => approveSender(item.msg)}
              onblock={() => blockSender(item.msg)}
              onmenu={(e) => openCtx(e, item.msg)}
              groupTag={!item.inGroup && smartActive() && !app.search && groupedSet.has(item.msg.category) ? CAT_META[item.msg.category] : null}
            />
          {:else if item.kind === "groupload"}
            <div class="gpart loading"><span class="spin">{@html icons.sync}</span> {t("list.loading")}</div>
          {:else if item.kind === "groupmore"}
            <div class="gpart">
              <button class="morebtn" onclick={() => (item.cat ? loadMoreCategory(item.cat) : bumpShown(item.gkey))}>
                {t("list.showMore", { n: item.remaining })}
              </button>
            </div>
          {:else if item.kind === "groupseeall"}
            <div class="gpart">
              <button class="morebtn" onclick={() => seeAll(item.cat)}>{t("list.seeAllInGroup", { n: item.total.toLocaleString() })}</button>
            </div>
          {:else if item.kind === "strip"}
            <SmartGroupStrip groups={item.groups} meta={CAT_META}
              openKey={item.groups.find((g) => expandedKeys.has(g.key))?.key ?? null}
              editOn={!!groupsMenu} bind:editEl={groupsBtn}
              onToggle={(g) => { closePeek(true); activate(g); }}
              onMenu={(e) => (groupsMenu = { x: e.clientX, y: e.clientY })}
              onPeek={(g, rect) => schedulePeek(g, rect)}
              onPeekOut={() => schedulePeekClose()}
              onEdit={toggleGroupsMenu} />
          {:else if item.gtype === "category"}
            <!-- The open group's header: what you're looking at, Done all, close. -->
            {@const gm = CAT_META[item.category] || {}}
            <div class="ghead" class:focused={i === focusIndex} style="--tone:{gm.tone || 'var(--accent)'}">
              <span class="gic">{@html gm.icon || icons.folder}</span>
              <span class="gname">{gm.label || item.category}</span>
              <span class="gcount tnum">{item.count.toLocaleString()}</span>
              <span class="gsp"></span>
              <button class="gbtn" title={t("list.doneAllTip")}
                onclick={() => { focusIndex = i; doneCategory(item); }}>{@html icons.done} {t("list.doneAll")}</button>
              <button class="gbtn x" title={t("list.collapseGroup")} aria-label={t("list.collapseGroup")}
                onclick={() => toggleExpand(item.key)}>{@html icons.close}</button>
            </div>
          {:else}
            <GroupRow
              gtype={item.gtype} msgs={item.msgs} latest={item.latest}
              focused={i === focusIndex} expanded={expandedKeys.has(item.key)}
              checked={groupChecked(item)}
              onactivate={() => { focusIndex = i; activate(item); }}
              ondoneall={() => doneGroup(item)}
              onselect={() => selectGroup(item)}
            />
          {/if}
        </div>
      {/each}
      {#if items.length > mainShown}
        <div class="loadmore" use:mainMore>
          <span class="spin">{@html icons.sync}</span> {t("list.loadingMore", { n: items.length - mainShown })}
        </div>
      {/if}
    {/if}
    {/key}
  </div>

  {#if app.settings.listHints}
    <footer class="hint">
      <kbd>↓</kbd><kbd>↑</kbd> {t("list.hintMove")} · <kbd>e</kbd> {t("list.hintToggleDone")} · <kbd>↵</kbd> {t("list.hintOpen")}
    </footer>
  {/if}
</section>

<style>
  /* The list sits on the window ground (same tone with the dynamic palette), so
     it reads as part of the page - the reading pane beside it is the raised
     container. Rounded so classic themes still show a soft pane. */
  .list { display: flex; flex-direction: column; min-height: 0; background: var(--bg);
    border-radius: var(--radius-lg); overflow: hidden; }
  header { padding: 2px 6px 6px; display: flex; flex-direction: column; gap: 4px; }

  /* ── Search: one pill, like Gmail's ── */
  .searchrow { display: flex; align-items: center; gap: 2px; min-height: 48px; padding: 0 4px 0 4px;
    border-radius: 28px; background: var(--surface-2);
    transition: background var(--t) var(--ease), box-shadow var(--t) var(--ease); }
  .searchrow:focus-within { background: var(--surface); box-shadow: var(--shadow); }
  .savesearch { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px;
    color: var(--on-sel); background: var(--sel); font-weight: 600; font-size: 13px; border-radius: 8px;
    transition: background var(--t-fast) var(--ease); }
  .savesearch :global(svg) { width: 16px; height: 16px; }
  .savesearch:hover { background: color-mix(in srgb, var(--sel) 88%, var(--on-sel)); }
  .adv { flex: none; display: grid; place-items: center; width: 40px; height: 40px; border-radius: 50%;
    color: var(--muted); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .adv:hover { background: var(--hover); color: var(--text); }
  .adv.aibtn { color: var(--accent); }
  .adv :global(svg) { width: 22px; height: 22px; }

  /* ── Title row ── */
  /* Wraps rather than squeezing: with longer (e.g. Czech) button labels the
     actions drop under the title instead of cutting it down to "C…". */
  .row1 { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 10px; padding: 10px 6px 2px 12px; }
  .row1-actions { display: flex; align-items: center; gap: 8px; flex: none; margin-left: auto; }
  h2 { margin: 0; font-size: 22px; line-height: 28px; font-weight: 400; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* Mark all read: an icon button (the label is its tooltip), so the title
     row keeps to one line at the default list width. */
  .markread { display: grid; place-items: center; flex: none; width: 40px; height: 40px; border-radius: 50%;
    color: var(--muted); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .markread:hover { background: var(--hover); color: var(--text); }
  .markread :global(svg) { width: 22px; height: 22px; }

  /* Category chips (folder views with categories). */
  .cats { display: flex; gap: 8px; flex-wrap: wrap; padding: 6px 6px 2px 12px; }
  .cat { height: 32px; padding: 0 14px; font-size: 13px; font-weight: 500; border-radius: 8px; color: var(--muted);
    box-shadow: inset 0 0 0 1px var(--border); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .cat:hover { background: var(--hover); color: var(--text); }
  .cat.active { background: var(--sel); color: var(--on-sel); box-shadow: none; }

  /* ── Selection toolbar ── */
  .bulkbar { display: flex; align-items: center; gap: 4px; margin: 0 8px 6px; padding: 6px 8px 6px 16px;
    background: var(--sel); color: var(--on-sel); border-radius: var(--radius); flex-wrap: wrap; }
  .bulkbar .count { font-weight: 600; font-size: 14px; margin-right: 6px; font-variant-numeric: tabular-nums; }
  .bulkbar button { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: 999px;
    font-size: 13px; font-weight: 500; color: inherit; transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .bulkbar button :global(svg) { width: 18px; height: 18px; }
  .bulkbar button:hover { background: color-mix(in srgb, var(--on-sel) 10%, transparent); }
  .bulkbar button.danger:hover { background: var(--danger-soft); color: var(--danger); }
  .bulkbar .clear { margin-left: auto; width: 34px; padding: 0; justify-content: center; }
  .snz { position: relative; }
  .snz-menu { position: absolute; top: 100%; left: 0; z-index: 15; margin-top: 4px; background: var(--surface-2); color: var(--text);
    border-radius: var(--radius-menu); box-shadow: var(--shadow-lg); padding: 6px 0; display: flex; flex-direction: column;
    min-width: 180px; animation: pop-in var(--t) var(--ease); transform-origin: top left; }
  .snz-menu button { text-align: left; border-radius: 0; height: auto; padding: 9px 16px; font-size: 14px; }
  .snz-menu button:hover { background: var(--hover); }

  /* Show-done: a Material switch. */
  .slider { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
  .slider input { display: none; }
  .slider .track {
    width: 40px; height: 24px; border-radius: 999px; position: relative; flex: none;
    background: var(--surface-3); box-shadow: inset 0 0 0 2px var(--outline);
    transition: background var(--t) var(--ease), box-shadow var(--t) var(--ease);
  }
  .slider .knob {
    position: absolute; top: 50%; left: 12px; width: 12px; height: 12px; border-radius: 50%;
    background: var(--outline); transform: translate(-50%, -50%);
    transition: left var(--t) var(--ease), width var(--t) var(--ease), height var(--t) var(--ease), background var(--t) var(--ease);
  }
  .slider input:checked + .track { background: var(--accent); box-shadow: none; }
  .slider input:checked + .track .knob { left: 28px; width: 18px; height: 18px; background: var(--on-accent); }
  .slider .lbl { font-size: 13px; color: var(--muted); min-width: 64px; }

  /* layout+paint containment: content-visibility realizes/unrealizes rows while
     scrolling, and each realization is a layout change - containment keeps those
     invalidations inside the scroller instead of rippling out to the app grid.
     No clipping change: as a scroller, .rows already clips its children. */
  .rows { flex: 1; overflow-y: auto; min-height: 0; contain: layout paint; padding-bottom: 8px; }
  .rows:focus { outline: none; }
  /* Kill hover work while scrolling - see onRowsScroll. Rows can't fire :hover
     with pointer-events off, so no button springs / background transitions play
     as they stream past the cursor. Wheel/touch scrolling targets .rows itself,
     so the scroll is unaffected; interaction returns the moment scrolling stops. */
  .rows.scrolling > * { pointer-events: none; }
  /* Row-by-row entrance cascade, gated to the ~650ms after a view switch (the
     .intro class) so windowed appends and triage reorders never replay it.
     Reuses the global rise-in keyframe; `backwards` holds rows hidden until
     their turn. Only the first rows get a stagger delay; the rest rise together. */
  .rows.intro > * { animation: rise-in var(--t-slow) var(--ease) backwards; }
  .rows.intro > *:nth-child(2) { animation-delay: 30ms; }
  .rows.intro > *:nth-child(3) { animation-delay: 60ms; }
  .rows.intro > *:nth-child(4) { animation-delay: 90ms; }
  .rows.intro > *:nth-child(5) { animation-delay: 120ms; }
  .rows.intro > *:nth-child(6) { animation-delay: 150ms; }
  .rows.intro > *:nth-child(7) { animation-delay: 180ms; }
  .rows.intro > *:nth-child(8) { animation-delay: 210ms; }
  .rows.intro > *:nth-child(9) { animation-delay: 240ms; }
  .rows.intro > *:nth-child(n+10) { animation-delay: 270ms; }
  /* Skip layout/paint for offscreen rows entirely - the single biggest scroll
     win. Date headers are excluded: paint containment would clip their sticky
     positioning. The placeholder height matches a real 3-line row (~88px), so
     scroll distance estimates stay honest and the scrollbar doesn't jump. */
  .cv { content-visibility: auto; contain-intrinsic-size: auto 88px; }
  /* Date section header. NOTE: no backdrop-filter here - blur on a sticky
     element repaints every scroll frame in WebView2 (felt "heavy"). */
  .datesep { position: sticky; top: 0; z-index: 4; padding: 12px 20px 6px; font-size: 13px; font-weight: 500;
    color: var(--muted); background: var(--bg); }
  /* Expanded group content: rows indented under the group's header. */
  .bundled :global(.wrap) { margin-left: 18px; }
  /* Header of the group opened from the strip: sits above its mail. */
  .ghead { display: flex; align-items: center; gap: 10px; margin: 4px 6px 4px; padding: 6px 6px 6px 8px;
    border-radius: var(--radius); background: color-mix(in srgb, var(--tone) 12%, transparent); font-size: 14px; }
  .ghead.focused { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--accent) 70%, transparent); }
  .gic { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 50%;
    color: color-mix(in srgb, var(--tone) 75%, var(--text)); background: color-mix(in srgb, var(--tone) 22%, transparent); }
  .gic :global(svg) { width: 18px; height: 18px; }
  .gname { font-weight: 600; font-size: 15px; }
  .gcount { color: var(--muted); font-size: 13px; }
  .gsp { flex: 1; }
  .gbtn { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 14px; border-radius: 999px;
    font-size: 13px; font-weight: 500; color: var(--text); transition: background var(--t-fast) var(--ease); }
  .gbtn :global(svg) { width: 18px; height: 18px; }
  .gbtn:hover { background: var(--hover); }
  .gbtn.x { width: 34px; padding: 0; justify-content: center; color: var(--muted); }
  .gpart { display: flex; align-items: center; gap: 8px; padding: 4px 14px; color: var(--muted); font-size: 13px; margin-left: 18px; }
  .gpart :global(svg) { width: 16px; height: 16px; }
  .gpart.loading { padding: 10px 14px; }
  .morebtn { display: inline-flex; align-items: center; height: 32px; padding: 0 12px; margin: 2px 0;
    color: var(--accent); font-weight: 600; font-size: 13px; border-radius: 999px; transition: background var(--t-fast) var(--ease); }
  .morebtn:hover { background: var(--accent-soft); }
  .loadmore { display: flex; align-items: center; gap: 8px; padding: 12px 22px; color: var(--muted); font-size: 13px; }
  .loadmore :global(svg) { width: 16px; height: 16px; }
  .spin { display: inline-flex; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Right-click menu (Material menu) ── */
  .ctxmenu { position: fixed; z-index: 300; width: 260px; max-height: min(72vh, 560px); background: var(--surface-2);
    border-radius: var(--radius-menu); box-shadow: var(--shadow-lg); padding: 8px 0 6px;
    display: flex; flex-direction: column; min-height: 0; animation: pop-in var(--t) var(--ease); }
  .ctx-title { font-size: 13px; font-weight: 600; color: var(--accent); padding: 4px 16px 8px; }
  .ctx-search { width: auto; margin: 0 8px 6px; padding: 8px 12px; font-size: 13px;
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-field); color: var(--text); }
  .ctx-search:focus { border-color: var(--accent); outline: none; box-shadow: none; }
  .ctx-list { overflow-y: auto; min-height: 0; display: flex; flex-direction: column; }
  .ctx-list > button { text-align: left; padding: 0 16px; min-height: 40px; border-radius: 0; font-size: 14px; color: var(--text);
    display: flex; align-items: center; gap: 12px; transition: background var(--t-fast) var(--ease); }
  .ctx-ic { width: 20px; height: 20px; flex: none; display: grid; place-items: center; color: var(--muted); }
  .ctx-ic :global(svg) { width: 20px; height: 20px; }
  .ctx-list > button:hover { background: var(--hover); }
  .ctx-list > button.danger { color: var(--danger); }
  .ctx-list > button.danger .ctx-ic { color: var(--danger); }
  .ctx-list > button.danger:hover { background: var(--danger-soft); }
  .ctx-head { font-size: 12px; font-weight: 600; color: var(--muted); padding: 10px 16px 4px; }
  .ctx-empty { color: var(--muted); font-size: 13px; padding: 10px 16px; }
  .ctx-sep { height: 1px; margin: 6px 0; background: var(--hairline); }
  .ctx-arrow { margin-left: auto; color: var(--muted); display: grid; place-items: center; }
  .ctx-arrow :global(svg) { width: 20px; height: 20px; }
  .ctx-list > button.ctx-back { color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--hairline); margin-bottom: 4px; }

  /* Loading skeleton */
  .skel { display: flex; gap: 14px; align-items: center; padding: 14px 18px; }
  .sk-av { width: 40px; height: 40px; border-radius: 50%; flex: none; }
  .sk-lines { flex: 1; display: flex; flex-direction: column; gap: 8px; }
  .sk-l { height: 10px; border-radius: 5px; }
  .sk-l.short { width: 55%; }
  .sk-av, .sk-l { background: linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  .muted, .empty { color: var(--muted); padding: 24px 16px; text-align: center; }
  .empty { display: flex; flex-direction: column; gap: 14px; align-items: center; margin-top: 48px; line-height: 1.6; font-size: 15px; animation: rise-in var(--t-slow) var(--ease); }
  .big { display: grid; place-items: center; width: 72px; height: 72px; border-radius: 50%;
    background: var(--sel); color: var(--on-sel); }
  .big :global(svg) { width: 36px; height: 36px; }

  footer.hint { padding: 8px 16px; border-top: 1px solid var(--hairline); color: var(--faint); font-size: 11.5px; }
  kbd {
    display: inline-block; padding: 1px 6px; margin: 0 1px; border-radius: 5px;
    background: var(--surface-2); border: 1px solid var(--hairline); font-size: 10.5px; font-family: ui-monospace, monospace;
  }
</style>
