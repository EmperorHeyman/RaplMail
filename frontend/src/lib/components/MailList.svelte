<script>
  import { untrack } from "svelte";
  import { fly, slide } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import { app, refreshMessages, markDone, toggleShowDone, prefetchBody, setCategory, snoozePresets, presetWhen, notify, saveCurrentSearch, openThread, refreshQueue, smartActive, groupedCategories, searchAddress, snoozeMessage, muteSender, muteThread, muteNotificationsFromSender, pinMessage, isVip, toggleVip, isTrustedSender, toggleTrusted, blockSender, createRuleFromSender, setSenderCategory, setMessageSeen, noteOpened, archiveMessage, deleteMessage, readerCommand, kbAll, approveSender, mergeById, runSemanticSearch, aiEnabled, openAiAssistant, addToAiChat, markAllRead, moveMessages, sendToLab } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { messages as messagesApi } from "../api.js";
  import MessageRow from "./MessageRow.svelte";
  import GroupRow from "./GroupRow.svelte";
  import SmartGroupCard from "./SmartGroupCard.svelte";
  import SearchBar from "./SearchBar.svelte";
  import SearchPalette from "./SearchPalette.svelte";
  import { icons } from "../icons.js";
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
  let _scrollIdle;
  function onRowsScroll() {
    if (!scrolling) scrolling = true;
    clearTimeout(_scrollIdle);
    _scrollIdle = setTimeout(() => { scrolling = false; }, 140);
  }

  // Group the flat message list into items: plain messages, conversation threads,
  // or notification bundles, depending on settings.
  const CAT_META = $derived.by(() => ({
    updates: { label: t("list.catNotifications"), icon: icons.bell },
    newsletters: { label: t("list.catNewsletters"), icon: icons.newspaper },
    social: { label: t("list.catSocial"), icon: icons.chat },
    promotions: { label: t("list.catPromotions"), icon: icons.tag },
    invitations: { label: t("list.catInvitations"), icon: icons.calendar },
    invitation_responses: { label: t("list.catInvitationResponses"), icon: icons.done },
  }));
  const CAT_ORDER = ["updates", "newsletters", "social", "promotions", "invitations", "invitation_responses"];

  // --- Spark-classic "sections" layout: one unified stream sliced into fixed
  // sections - People / Notifications / Newsletters / Pins / Seen. Unread mail
  // lives in its section; read mail settles into Seen; pinned mail into Pins.
  const SEC_META = $derived.by(() => ({
    people:        { label: t("list.secPeople"), icon: icons.accounts },
    notifications: { label: t("list.catNotifications"), icon: icons.bell },
    newsletters:   { label: t("list.catNewsletters"), icon: icons.newspaper },
    pins:          { label: t("list.secPins"), icon: icons.pin },
    seen:          { label: t("list.secSeen"), icon: icons.show },
  }));
  const secOf = (cat) =>
    cat === "updates" || cat === "social" ? "notifications"
    : cat === "newsletters" || cat === "promotions" ? "newsletters"
    : "people";
  const SEC_LIMIT = 5;            // collapsed rows per section ("View all" expands)
  let secExpanded = $state(new Set());
  function toggleSecExpand(id) {
    const s = new Set(secExpanded);
    s.has(id) ? s.delete(id) : s.add(id);
    secExpanded = s;
  }
  const sectionsMode = $derived(
    smartActive() && (app.settings.smartGroupPlacement || "sections") === "sections"
  );

  function buildSections(msgs) {
    const vis = visibleIn(msgs);
    const pinned = [], seen = [], bysec = { people: [], notifications: [], newsletters: [] };
    for (const m of vis) {
      if (m.pinned) pinned.push(m);
      else if (m.is_seen) seen.push(m);
      else bysec[secOf(m.category)].push(m);
    }
    // People: VIP senders first (stable sort keeps date order within each band),
    // then grouped by account so each mailbox reads as its own block.
    bysec.people.sort((a, b) => (isVip(b.from_addr) ? 1 : 0) - (isVip(a.from_addr) ? 1 : 0));
    const multi = app.accounts.length > 1;
    if (multi) {
      const rank = new Map(app.accounts.map((a, i) => [a.id, i]));
      bysec.people.sort((a, b) => (rank.get(a.account_id) ?? 99) - (rank.get(b.account_id) ?? 99));
    }
    const out = [];
    const push = (id, arr, { limit = SEC_LIMIT, doneAll = false, acctGroups = false } = {}) => {
      if (!arr.length) return;
      // sechead carries the section's messages when it offers "done all".
      out.push({ kind: "sechead", key: "sec:" + id, sec: id, count: arr.length,
                 msgs: doneAll ? arr : undefined });
      const rows = secExpanded.has(id) || arr.length <= limit ? arr : arr.slice(0, limit);
      let lastAcct = null;
      for (const m of rows) {
        if (acctGroups && multi && m.account_id !== lastAcct) {
          lastAcct = m.account_id;
          out.push({ kind: "acctsep", key: `as:${id}:${m.account_id}`,
                     account: app.accounts.find((a) => a.id === m.account_id) });
        }
        out.push({ kind: "msg", msg: m });
      }
      if (rows.length < arr.length)
        out.push({ kind: "secmore", key: "sm:" + id, sec: id, total: arr.length });
      else if (secExpanded.has(id) && arr.length > limit)
        out.push({ kind: "secless", key: "sl:" + id, sec: id });
    };
    push("people", bysec.people, { limit: 8, acctGroups: true });
    push("notifications", bysec.notifications, { doneAll: true });
    push("newsletters", bysec.newsletters, { doneAll: true });
    push("pins", pinned, { limit: Infinity });
    push("seen", seen, { limit: Infinity });
    return out;
  }

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
    const s = new Set(expandedKeys); s.add(cat); expandedKeys = s;
    markSticky(cat);   // opening a group holds it at the top while you read it
    loadCategory(cat);
  }
  function seeAll(cat) { openCategory(cat, "all"); }

  // Groups the user has touched this session stay pinned to the top even after
  // their unread count hits 0 - otherwise reading the last new mail in a group
  // makes the whole card drop from the "hot" band to the end of Today mid-click,
  // which reads as "the mail I just opened jumped down". Reset when the view /
  // search changes (or on restart), so it only holds the list stable in-session.
  let stickyHot = $state(new Set());
  function markSticky(cat) {
    if (cat && groupedCategories().includes(cat) && !stickyHot.has(cat))
      stickyHot = new Set([...stickyHot, cat]);
  }
  $effect(() => {
    app.selectedKind; app.selectedFolderId; app.search;   // reset triggers
    untrack(() => {
      if (stickyHot.size) stickyHot = new Set();
      if (secExpanded.size) secExpanded = new Set();
    });
  });

  // Which Smart Inbox category cards are currently expanded (their key IS the
  // category id). Drives the header breadcrumb - the "you're inside this group"
  // indicator that replaces the old static "Smart Inbox" title.
  const openCats = $derived(
    smartActive() ? groupedCategories().filter((c) => expandedKeys.has(c)) : []
  );
  function collapseAllGroups() {
    const s = new Set(expandedKeys);
    for (const c of groupedCategories()) s.delete(c);
    expandedKeys = s;
  }

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
      { root: rowsEl || null, rootMargin: "500px 0px" }
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

  const NOTIF = new Set(["updates", "social", "newsletters"]);

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
    if (smartActive()) {
      if (sectionsMode) return buildSections(msgs);
      const items = msgs.map((m) => ({ kind: "msg", msg: m }));
      const n = app.settings.smartPreviewCount || 4;
      const groups = [];
      for (const c of groupedCategories()) {
        const g = app.smartGroupData[c];
        if (g && g.count > 0) {
          const shown = (g.senders || []).slice(0, n);
          const more = Math.max(0, (g.distinct ?? shown.length) - shown.length);
          groups.push({ kind: "group", gtype: "category", key: c, category: c,
                        count: g.count, unread: g.unread || 0, new: g.new || 0,
                        senders: shown, more, latest: g.latest, recent: g.recent || [] });
        }
      }
      if (app.settings.smartOrderMode === "custom") {
        const order = app.settings.smartOrder || [];
        const rank = (c) => { const i = order.indexOf(c); return i < 0 ? 999 : i; };
        groups.sort((a, b) => rank(a.category) - rank(b.category));
      } else {
        // Most-recently-active group floats to the top.
        groups.sort((a, b) => (b.latest || "").localeCompare(a.latest || ""));
      }
      // Where the group cards sit relative to the classic messages.
      const placement = app.settings.smartGroupPlacement || "dateSections";
      if (placement === "dateSections") {
        // Spark-style date sections (Today / Yesterday / This week / …). Groups
        // with NEW (unread) mail float to the very top so you notice them; quiet
        // (all-read) groups are tucked at the END of Today, out of the way. When
        // Today is empty (you've cleared it), the tucked groups surface at top
        // too instead of sinking below older sections.
        // Pin the group you're currently reading to its hot spot: opening the
        // last unread of a group drops its g.new to 0, which would otherwise make
        // the card fall to the end of Today while the message is still open.
        // Keeping the open category hot holds the list stable under the reader;
        // it settles back once you close/leave (selectedMessageId changes).
        const openId = app.selectedMessageId;
        const openCat = openId == null ? null
          : (msgs.find((m) => m.id === openId)?.category
             ?? groups.find((g) => (g.recent || []).some((r) => r.id === openId))?.category
             ?? null);
        const isHot = (g) => g.new > 0 || g.category === openCat || stickyHot.has(g.category);
        const hot = groups.filter(isHot);    // NEW mail, being read, or touched this session → top
        const cold = groups.filter((g) => !isHot(g)); // otherwise → end of Today
        const hotItems = hot.flatMap(expandGroup);
        const coldItems = cold.flatMap(expandGroup);
        const out = [...hotItems];
        let bucket = null;
        let coldPlaced = false;
        let sawToday = false;
        for (const it of items) {
          const b = dateBucket(it.msg.date);
          if (b !== bucket) {
            if (bucket === "Today" && !coldPlaced) { out.push(...coldItems); coldPlaced = true; }
            out.push({ kind: "header", key: "h:" + b, label: b });
            bucket = b;
          }
          if (b === "Today") sawToday = true;
          out.push(it);
        }
        if (!coldPlaced) {
          // Today was the last (or only) section → cold groups after it. If there
          // were no Today messages at all, they land right under the hot groups
          // at the top rather than below Yesterday/older.
          if (sawToday) out.push(...coldItems);
          else out.splice(hotItems.length, 0, ...coldItems);
        }
        return out;
      }
      if (placement === "top") return [...groups.flatMap(expandGroup), ...items];
      if (placement === "afterN") {
        const k = Math.max(0, app.settings.smartGroupsAfter ?? 3);
        return [...items.slice(0, k), ...groups.flatMap(expandGroup), ...items.slice(k)];
      }
      if (placement === "timeline") {
        // Interleave groups + messages by recency: a group floats to the date of
        // its newest mail, and any newer standalone mail pushes it down.
        const dateOf = (it) => String((it.kind === "group" ? it.latest : it.msg.date) || "");
        return [...items, ...groups].sort((a, b) => dateOf(b).localeCompare(dateOf(a)))
          .flatMap((it) => (it.kind === "group" ? expandGroup(it) : [it]));
      }
      return [...items, ...groups.flatMap(expandGroup)]; // "bottom"
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
    if (app.settings.bundles) {
      const counts = {};
      for (const m of msgs) if (NOTIF.has(m.category)) counts[m.from_addr] = (counts[m.from_addr] || 0) + 1;
      const senders = new Set(Object.keys(counts).filter((s) => counts[s] >= 3));
      const map = new Map(); const items = [];
      for (const m of msgs) {
        if (NOTIF.has(m.category) && senders.has(m.from_addr)) {
          if (!map.has(m.from_addr)) {
            const g = { kind: "group", gtype: "bundle", key: m.from_addr, msgs: [], latest: m };
            map.set(m.from_addr, g); items.push(g);
          }
          map.get(m.from_addr).msgs.push(m);
        } else items.push({ kind: "msg", msg: m });
      }
      return items.flatMap((it) => (it.kind === "group" ? expandGroup(it) : [it]));
    }
    return msgs.map((m) => ({ kind: "msg", msg: m }));
  }
  const items = $derived.by(() => {
    const built = buildItems(app.messages);
    // Sectioned layouts have their own ordering (with header rows) - don't pull
    // pinned/VIP to the top or it would orphan the section headers.
    if (smartActive() && ["dateSections", "sections"].includes(app.settings.smartGroupPlacement || "sections")) return built;
    // Pinned first, then VIP-sender mail, then everything else (stable).
    // Never hoist rows living inside an expanded group out of their card.
    const isP = (it) => it.kind === "msg" && !it.inGroup && it.msg.pinned;
    const isV = (it) => it.kind === "msg" && !it.inGroup && !it.msg.pinned && isVip(it.msg.from_addr);
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

  // --- right-click context menu ---
  let ctx = $state(null); // { x, y, msg }
  let ctxSearch = $state("");
  function openCtx(e, msg) {
    e.preventDefault();
    ctxSearch = "";
    // Right-clicking a row that's part of a multi-selection acts on the WHOLE
    // selection (group menu); otherwise it's the usual single-message menu.
    const group = selectedIds.length > 1 && selectedIds.includes(msg.id);
    ctx = { x: e.clientX, y: e.clientY, msg, group };
  }
  function closeCtx() { ctx = null; }
  function ctxDo(fn) { const m = ctx?.msg; closeCtx(); if (m) fn(m); }
  function toggleSeen(m) { setMessageSeen(m, !m.is_seen); }
  function toggleFlag(m) { const v = !m.is_flagged; m.is_flagged = v; messagesApi.setFlag(m.id, v).catch(() => {}); }

  // Flat, searchable action list for the right-click menu. `kw` adds extra
  // search keywords beyond the label.
  function ctxActions(m) {
    const acts = [
      // -1: the right-clicked row isn't necessarily the keyboard-focused one.
      { label: t("list.open"), run: () => open(m, -1) },
      ...(aiEnabled() ? [{ label: t("list.addToAiChat"), icon: icons.bolt, kw: "ai assistant chat context", run: () => addToAiChat(m) }] : []),
      { label: m.pinned ? t("list.unpin") : t("list.pinToTop"), icon: icons.pin, run: () => pinMessage(m) },
      { label: m.is_done ? t("list.markNotDone") : t("list.markDone"), icon: icons.done, kw: "complete e", run: () => markDone(m, !m.is_done) },
      { label: m.is_seen ? t("list.markUnread") : t("list.markRead"), kw: "seen", run: () => toggleSeen(m) },
      { label: m.is_flagged ? t("list.unflag") : t("list.flag"), icon: icons.flag, kw: "star", run: () => toggleFlag(m) },
      { label: isVip(m.from_addr) ? t("list.removeVip") : t("list.markSenderVip"), icon: icons.star, run: () => toggleVip(m.from_addr) },
      { label: isTrustedSender(m.from_addr) ? t("list.unmarkSafe") : t("list.markSenderSafe"), icon: icons.shieldCheck, run: () => toggleTrusted(m.from_addr) },
      { sep: t("list.moveToCategory"), kw: "" },
      { label: t("list.moveToPrimary"), icon: icons.inbox, kw: "move out newsletter normal queue", run: () => setSenderCategory(m, "primary") },
      ...Object.entries(CAT_META).map(([id, meta]) => ({ label: t("list.moveTo", { cat: meta.label }), icon: meta.icon, kw: "move category " + id, run: () => setSenderCategory(m, id) })),
      { label: t("list.resetCategory"), icon: icons.reset, kw: "move category", run: () => setSenderCategory(m, "auto") },
      { sep: t("list.snooze") },
      ...snoozePresets().map((p) => ({ label: t("list.snoozePrefix", { label: p.label }), icon: icons.snooze, kw: "snooze remind later", run: () => snoozeMessage(m, p.iso, p.presence) })),
      { sep: t("list.more") },
      { label: t("list.archive"), icon: icons.archive, run: () => archiveOne(m) },
      { label: t("list.delete"), icon: icons.trash, danger: true, run: () => deleteOne(m) },
      { label: t("list.showMailFromSender"), kw: "filter from", run: () => searchAddress(m.from_addr) },
      { label: t("list.muteSender"), icon: icons.mute, run: () => muteSender(m) },
      { label: t("rules.muteFromSender"), icon: icons.bell, kw: "notification notify silence", run: () => muteNotificationsFromSender(m) },
      { label: t("list.muteConversation"), icon: icons.mute, kw: "thread", run: () => muteThread(m) },
      { label: t("list.blockSender"), icon: icons.junk, danger: true, run: () => blockSender(m) },
      { label: t("list.createRule"), icon: icons.bolt, run: () => createRuleFromSender(m) },
      { label: t("list.sendToLab"), icon: icons.shieldCheck, kw: "security lab scan analyze forensics virustotal headers domain ip whois", run: () => sendToLab(m) },
    ];
    const q = ctxSearch.trim().toLowerCase();
    if (!q) return acts;
    // When searching, drop section separators and match label + keywords.
    return acts.filter((a) => !a.sep && ((a.label + " " + (a.kw || "")).toLowerCase().includes(q)));
  }
  // Group right-click menu: the selection-bar actions plus move-to-folder, applied
  // to the whole current selection.
  function moveSelectionTo(f) { const ids = [...selectedIds]; clearSelection(); moveMessages(ids, f); }
  function ctxGroupActions(msg) {
    const targets = app.folders.filter((f) => f.account_id === msg.account_id && f.id !== msg.folder_id);
    const acts = [
      { label: t("list.markDone"), icon: icons.done, kw: "complete e", run: () => bulk("done") },
      { label: t("list.markRead"), kw: "seen", run: () => bulk("seen") },
      { label: t("list.flag"), icon: icons.flag, kw: "star", run: () => bulk("flag") },
      { sep: t("list.snooze") },
      ...snoozePresets().filter((p) => p.iso).map((p) => ({ label: p.label, icon: icons.snooze, kw: "snooze remind later", run: () => bulk("snooze", p.iso) })),
      ...(targets.length ? [{ sep: t("list.moveToFolder") },
        ...targets.map((f) => ({ label: f.name, icon: icons.folder, kw: "move folder " + f.name, run: () => moveSelectionTo(f) }))] : []),
      { sep: t("list.more") },
      { label: t("list.archive"), icon: icons.archive, run: () => bulk("archive") },
      { label: t("list.delete"), icon: icons.trash, danger: true, run: () => bulk("delete") },
      { label: t("list.clearSelection"), icon: icons.close, run: () => clearSelection() },
    ];
    const q = ctxSearch.trim().toLowerCase();
    if (!q) return acts;
    return acts.filter((a) => !a.sep && ((a.label + " " + (a.kw || "")).toLowerCase().includes(q)));
  }
  const currentCtxActions = () => (ctx?.group ? ctxGroupActions(ctx.msg) : ctxActions(ctx.msg));
  function runCtx(a) { if (a?.run) ctxDo(a.run); }
  function ctxEnter() {
    const first = currentCtxActions().find((a) => !a.sep);
    if (first) runCtx(first);
  }

  // Position the menu fully on-screen - flip up/left near edges, cap height.
  function placeMenu(node, pos) {
    const apply = (p) => {
      const r = node.getBoundingClientRect();
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
      notify(t(doneKey, { n: ids.length }));
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
    markSticky(message.category);   // keep this mail's group pinned so it doesn't drop mid-click
    noteOpened(message);   // marks read now or when you move on, per readMarkMode
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
    if (combo === kb.search) {
      // Respect the user's preferred search surface: the full modal, or the
      // inline bar in the list header.
      if (app.settings.searchStyle === "modal") paletteOpen = true;
      else document.querySelector(".list .search")?.focus();
      e.preventDefault(); return;
    }
    if (!items.length) return;
    // Skip non-interactive rows (date/section headers, group loaders) when arrowing.
    const SKIP = new Set(["header", "groupload", "sechead", "acctsep"]);
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
      else if (it.kind === "secmore" || it.kind === "secless") toggleSecExpand(it.sec);
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
    (smartActive() && Object.values(app.smartGroupData || {}).some((g) => (g?.unread || 0) > 0))
  );

  const CATS = $derived.by(() => ([
    { id: null, label: t("list.catAll") },
    { id: "primary", label: t("list.catPrimary") },
    { id: "newsletters", label: t("list.catNewsletters") },
    { id: "social", label: t("list.catSocial") },
    { id: "updates", label: t("list.catUpdates") },
    { id: "promotions", label: t("list.catPromotions") },
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

<svelte:window on:keydown={onKey} on:click={() => ctx && closeCtx()} />

<SearchPalette open={paletteOpen} initial={app.search}
  smartAvailable={aiEnabled() || app.settings.semanticEnabled}
  onclose={() => (paletteOpen = false)}
  onsearch={(q) => applySearch(q)}
  onsemantic={(q) => runSemanticSearch(q)}
  onopen={(m) => open(m, -1)} />

{#if ctx}
  <div class="ctxmenu" use:placeMenu={{ x: ctx.x, y: ctx.y }} onclick={(e) => e.stopPropagation()}>
    {#if ctx.group}<div class="ctx-title">{t("list.selectionActions", { n: selectedIds.length })}</div>{/if}
    <input class="ctx-search" placeholder={t("list.searchActions")} bind:value={ctxSearch} autofocus
      onkeydown={(e) => { if (e.key === "Enter") ctxEnter(); else if (e.key === "Escape") closeCtx(); }} />
    <div class="ctx-list">
      {#each currentCtxActions() as a}
        {#if a.sep}
          <div class="ctx-head">{a.sep}</div>
        {:else}
          <button class:danger={a.danger} onclick={() => runCtx(a)}>{#if a.icon}{@html a.icon} {/if}{a.label}</button>
        {/if}
      {/each}
      {#if currentCtxActions().length === 0}<div class="ctx-empty">{t("list.noMatchingAction")}</div>{/if}
    </div>
  </div>
{/if}

<section class="list">
  <header>
    <div class="row1">
      {#if app.selectedKind === "smart" && sectionsMode}
        <h2>{t("list.smartInbox")}</h2>
      {:else if app.selectedKind === "smart"}
        <!-- Smart Inbox: no redundant static title. When a group is open, show a
             breadcrumb so you can see which group folder you're in (and collapse it). -->
        <div class="crumbs">
          {#if openCats.length}
            <button class="crumb root" onclick={collapseAllGroups}>{t("list.smartInbox")}</button>
            {#each openCats as c}
              <span class="csep">›</span>
              <button class="crumb cur" onclick={() => toggleExpand(c)} title={t("list.collapseGroup")}>
                <span class="cic">{@html CAT_META[c]?.icon || icons.folder}</span>
                {CAT_META[c]?.label || c}
                <span class="cx">×</span>
              </button>
            {/each}
          {/if}
        </div>
      {:else}
        <h2>{title}</h2>
      {/if}
      <div class="row1-actions">
        {#if hasUnread}
          <button class="markread" title={t("list.markAllReadTip")} onclick={markAllRead}>
            {@html icons.doneAll || icons.done} {t("list.markAllRead")}
          </button>
        {/if}
        <label class="slider" title={t("list.showDoneTip")}>
          <input type="checkbox" checked={app.showDone} onchange={toggleShowDone} />
          <span class="track"><span class="knob"></span></span>
          <span class="lbl">{app.showDone ? t("list.showingAll") : t("list.showDone")}</span>
        </label>
      </div>
    </div>
    <div class="searchrow">
      <SearchBar value={app.search} oninput={onSearch} onexpand={() => (paletteOpen = true)} />
      <button class="adv" title={t("search.advancedTitle")} onclick={() => (paletteOpen = true)}>{@html icons.sliders}</button>
      {#if aiEnabled()}
        <button class="adv aibtn" title={t("list.aiAssistant")}
          onclick={() => openAiAssistant({ messageId: app.selectedMessageId, threadKey: app.threadKey || "" })}>{@html icons.bolt}</button>
      {/if}
      {#if app.search.trim()}<button class="savesearch" title={t("list.saveSmartFolder")} onclick={saveSearch}>{@html icons.star} {t("list.save")}</button>{/if}
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
      {#each items.slice(0, mainShown) as item, i (item.kind === "msg" ? "m" + item.msg.id : item.kind === "group" ? "g" + item.key : item.key)}
        <div class:bundled={item.kind === "msg" && item.inGroup} class:cv={item.kind !== "header"}
             draggable={item.kind === "msg"}
             ondragstart={item.kind === "msg" ? (e) => onRowDragStart(e, item.msg) : undefined}
             ondragend={item.kind === "msg" ? onRowDragEnd : undefined}
             out:fly={{ x: 48, duration: 140 }}>
          {#if item.kind === "header"}
            <div class="datesep">{bucketLabel(item.label)}</div>
          {:else if item.kind === "sechead"}
            <div class="sechead">
              <span class="sic">{@html SEC_META[item.sec]?.icon || icons.folder}</span>
              <span class="slabel">{SEC_META[item.sec]?.label || item.sec}</span>
              <span class="scount">{item.count}</span>
              {#if item.msgs}
                <button class="sdone" title={t("list.doneAllTip")}
                  onclick={() => doneGroup({ msgs: item.msgs })}>{@html icons.done}</button>
              {/if}
            </div>
          {:else if item.kind === "acctsep"}
            <div class="acctsep">
              <span class="adot" style={`background:${item.account?.color || "var(--accent)"}`}></span>
              {item.account?.email || ""}
            </div>
          {:else if item.kind === "secmore"}
            <div class="gpart">
              <button class="morebtn" onclick={() => toggleSecExpand(item.sec)}>{t("list.viewAll", { n: item.total })}</button>
            </div>
          {:else if item.kind === "secless"}
            <div class="gpart">
              <button class="morebtn" onclick={() => toggleSecExpand(item.sec)}>{t("list.showLess")}</button>
            </div>
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
          {:else if item.gtype === "category"}
            <SmartGroupCard
              label={CAT_META[item.category]?.label || item.category}
              icon={CAT_META[item.category]?.icon || icons.folder}
              count={item.count} unread={item.unread} newCount={item.new} senders={item.senders} more={item.more}
              focused={i === focusIndex} expanded={expandedKeys.has(item.key)} mode={modeOf(item.category)}
              onToggle={() => { focusIndex = i; activate(item); }}
              onNewBadge={() => { focusIndex = i; openCategory(item.category, "new"); }}
              onSender={(email) => searchAddress(email)}
              onDoneAll={() => { focusIndex = i; doneCategory(item); }}
            />
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

  <footer class="hint">
    <kbd>↓</kbd><kbd>↑</kbd> {t("list.hintMove")} · <kbd>e</kbd> {t("list.hintToggleDone")} · <kbd>↵</kbd> {t("list.hintOpen")}
  </footer>
</section>

<style>
  .list { display: flex; flex-direction: column; border-right: 1px solid var(--hairline); min-height: 0; background: var(--bg); }
  header { padding: 14px 16px 11px; border-bottom: 1px solid var(--hairline); display: flex; flex-direction: column; gap: 10px; }
  .row1 { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .row1-actions { display: flex; align-items: center; gap: 10px; flex: none; }
  .markread { display: inline-flex; align-items: center; gap: 5px; flex: none; font-size: 12px; font-weight: 600;
    color: var(--muted); padding: 5px 11px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface-2);
    transition: color var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .markread:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
  .markread :global(svg) { width: 14px; height: 14px; }
  h2 { margin: 0; font-size: 16.5px; font-weight: 700; letter-spacing: -0.02em; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* Smart Inbox breadcrumb - the "you're in this group folder" indicator. Flex:1
     so it holds the header height and pushes the actions to the right even when
     empty (no group open = deliberately blank, no static "Smart Inbox" title). */
  .crumbs { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; min-height: 26px; overflow: hidden; }
  .crumb { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; font-size: 13px; font-weight: 650; white-space: nowrap; transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .crumb.root { color: var(--muted); }
  .crumb.root:hover { background: var(--hover); color: var(--text); }
  .crumb.cur { background: var(--accent-soft); color: var(--text); }
  .crumb.cur:hover { background: var(--accent-soft-2); }
  .crumb .cic { display: inline-flex; color: var(--accent); }
  .crumb .cic :global(svg) { width: 14px; height: 14px; }
  .crumb .cx { color: var(--faint); font-size: 15px; line-height: 1; margin-left: 2px; }
  .crumb.cur:hover .cx { color: var(--text); }
  .csep { color: var(--faint); font-size: 13px; flex: none; }
  .searchrow { display: flex; gap: 8px; align-items: center; }
  .search { flex: 1; }
  .savesearch { flex: none; color: var(--accent); font-weight: 600; font-size: 12px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--accent-soft); transition: background var(--t-fast) var(--ease); }
  .savesearch:hover { background: var(--accent-soft-2); }
  .adv { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
    border-radius: var(--radius-sm); color: var(--muted); background: var(--surface-2); border: 1px solid var(--border);
    transition: color var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease); }
  .adv:hover { color: var(--accent); border-color: var(--accent); }
  .adv.aibtn { color: var(--accent); }
  .adv :global(svg) { width: 16px; height: 16px; }
  .cats { display: flex; gap: 4px; flex-wrap: wrap; }
  .cat { font-size: 12px; font-weight: 550; padding: 4px 11px; border-radius: 999px; color: var(--muted); background: var(--surface-2); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .cat:hover { background: var(--surface-3); color: var(--text); }
  .cat.active { background: var(--accent); color: #fff; }

  .bulkbar { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--surface-2); border-bottom: 1px solid var(--hairline); flex-wrap: wrap; }
  .bulkbar .count { font-weight: 600; font-size: 13px; margin-right: 4px; font-variant-numeric: tabular-nums; }
  .bulkbar button { padding: 6px 10px; border-radius: var(--radius-sm); background: var(--surface-3); font-size: 12px; font-weight: 550; transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .bulkbar button:hover { background: color-mix(in srgb, var(--surface-3) 76%, var(--text) 10%); }
  .bulkbar button.danger:hover { background: var(--danger-soft); color: var(--danger); }
  .bulkbar .clear { margin-left: auto; background: transparent; }
  .snz { position: relative; }
  .snz-menu { position: absolute; top: 100%; left: 0; z-index: 15; margin-top: 4px; background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; min-width: 150px; animation: pop-in var(--t) var(--ease); transform-origin: top left; }
  .snz-menu button { text-align: left; background: transparent; }
  .snz-menu button:hover { background: var(--accent); color: #fff; }

  /* The Spark-style done slider */
  .slider { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
  .slider input { display: none; }
  .slider .track {
    width: 38px; height: 22px; border-radius: 999px; background: var(--surface-3);
    position: relative; transition: background var(--t) var(--ease);
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.18);
  }
  .slider .knob {
    position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
    background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    transition: transform var(--t) var(--ease-spring);
  }
  .slider input:checked + .track { background: var(--done); }
  .slider input:checked + .track .knob { transform: translateX(16px); }
  .slider .lbl { font-size: 12px; color: var(--muted); min-width: 64px; }

  .rows { flex: 1; overflow-y: auto; min-height: 0; }
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
     positioning. The placeholder height matches a real 3-line row (~74px), so
     scroll distance estimates stay honest and the scrollbar doesn't jump. */
  .cv { content-visibility: auto; contain-intrinsic-size: auto 74px; }
  /* Spark-style date section header. NOTE: no backdrop-filter here - blur on a
     sticky element repaints every scroll frame in WebView2 (felt "heavy"). */
  .datesep { position: sticky; top: 0; z-index: 4; padding: 8px 16px 5px; font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.08em; color: var(--faint);
    background: var(--bg);
    border-bottom: 1px solid var(--hairline); }
  /* Spark-classic section header (People / Notifications / Newsletters / Pins /
     Seen). Same no-backdrop-filter rule as .datesep: blur on sticky repaints
     every scroll frame. */
  .sechead { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; gap: 7px;
    padding: 12px 16px 6px; font-size: 12px; font-weight: 700; color: var(--text);
    background: var(--bg); border-bottom: 1px solid var(--hairline); }
  .sechead .sic { display: inline-flex; color: var(--muted); }
  .sechead .sic :global(svg) { width: 14px; height: 14px; }
  .sechead .scount { font-weight: 600; font-size: 11px; color: var(--faint); }
  .sechead .sdone { margin-left: auto; display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 999px; color: var(--muted); opacity: 0;
    transition: opacity var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .sechead:hover .sdone { opacity: 1; }
  .sechead .sdone:hover { background: var(--done-soft); color: var(--done); }
  .sechead .sdone :global(svg) { width: 14px; height: 14px; }
  /* Account sub-label inside the People section (multi-account only). */
  .acctsep { display: flex; align-items: center; gap: 7px; padding: 7px 16px 3px;
    font-size: 11px; font-weight: 600; color: var(--muted); }
  .acctsep .adot { width: 7px; height: 7px; border-radius: 999px; flex: none; }
  /* Expanded group content: flat rows with a quiet accent guide on the left. */
  .bundled :global(.row) { padding-left: 24px; box-shadow: inset 2px 0 0 var(--accent-soft-2); }
  .bundled :global(.row.focused) { box-shadow: inset 3px 0 0 var(--accent); }
  .gpart { display: flex; align-items: center; gap: 8px; padding: 6px 24px; color: var(--muted); font-size: 12px;
    border-bottom: 1px solid var(--hairline); box-shadow: inset 2px 0 0 var(--accent-soft-2); }
  .gpart.loading { padding: 10px 24px; }
  .morebtn { color: var(--accent); font-weight: 600; font-size: 12px; padding: 4px 10px; margin: 2px 0; border-radius: 999px; transition: background var(--t-fast) var(--ease); }
  .morebtn:hover { background: var(--accent-soft); }
  .loadmore { display: flex; align-items: center; gap: 8px; padding: 10px 22px; color: var(--muted); font-size: 12px; }
  .spin { display: inline-flex; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .ctxmenu { position: fixed; z-index: 300; width: 248px; max-height: min(72vh, 560px); background: var(--surface-2);
    border: 1px solid var(--hairline); border-radius: var(--radius); box-shadow: var(--shadow-lg); padding: 6px;
    display: flex; flex-direction: column; min-height: 0; animation: pop-in var(--t) var(--ease); }
  .ctx-title { font-size: 12px; font-weight: 700; color: var(--accent); padding: 4px 6px 7px; }
  .ctx-search { width: 100%; box-sizing: border-box; margin-bottom: 5px; padding: 7px 10px; font-size: 13px;
    background: var(--surface); border: 1px solid var(--hairline); border-radius: 7px; color: var(--text); }
  .ctx-search:focus { border-color: var(--accent); outline: none; box-shadow: none; }
  .ctx-list { overflow-y: auto; min-height: 0; display: flex; flex-direction: column; }
  .ctx-list > button { text-align: left; padding: 8px 11px; border-radius: 7px; font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 8px; transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .ctx-list > button:hover { background: var(--accent); color: #fff; }
  .ctx-list > button.danger:hover { background: var(--danger); }
  .ctx-head { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--faint); padding: 9px 11px 3px; }
  .ctx-empty { color: var(--muted); font-size: 13px; padding: 10px 11px; }

  /* Loading skeleton */
  .skel { display: flex; gap: 11px; align-items: center; padding: 13px 14px; border-bottom: 1px solid var(--hairline); }
  .sk-av { width: 34px; height: 34px; border-radius: 50%; flex: none; }
  .sk-lines { flex: 1; display: flex; flex-direction: column; gap: 7px; }
  .sk-l { height: 9px; border-radius: 5px; }
  .sk-l.short { width: 55%; }
  .sk-av, .sk-l { background: linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  .muted, .empty { color: var(--muted); padding: 24px 16px; text-align: center; }
  .empty { display: flex; flex-direction: column; gap: 12px; align-items: center; margin-top: 48px; line-height: 1.6; animation: rise-in var(--t-slow) var(--ease); }
  .big { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 20px;
    background: var(--accent-soft); color: var(--accent); font-size: 28px; box-shadow: inset 0 0 0 1px var(--accent-soft-2); }
  .big :global(svg) { width: 30px; height: 30px; }

  footer.hint { padding: 8px 14px; border-top: 1px solid var(--hairline); color: var(--faint); font-size: 11px; }
  kbd {
    display: inline-block; padding: 1px 6px; margin: 0 1px; border-radius: 5px;
    background: var(--surface-2); border: 1px solid var(--hairline); font-size: 10px; font-family: ui-monospace, monospace;
  }
</style>
