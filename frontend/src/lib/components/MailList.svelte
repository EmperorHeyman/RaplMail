<script>
  import { untrack } from "svelte";
  import { flip } from "svelte/animate";
  import { fly, slide } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import { app, refreshMessages, markDone, toggleShowDone, prefetchBody, setCategory, snoozePresets, presetWhen, notify, saveCurrentSearch, openThread, refreshQueue, smartActive, groupedCategories, searchAddress, snoozeMessage, muteSender, muteThread, muteNotificationsFromSender, pinMessage, isVip, toggleVip, isTrustedSender, toggleTrusted, blockSender, createRuleFromSender, setSenderCategory, setMessageSeen, archiveMessage, deleteMessage, readerCommand, kbAll, approveSender } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { messages as messagesApi } from "../api.js";
  import MessageRow from "./MessageRow.svelte";
  import GroupRow from "./GroupRow.svelte";
  import SmartGroupCard from "./SmartGroupCard.svelte";
  import SearchBar from "./SearchBar.svelte";
  import { icons } from "../icons.js";
  import { keyCombo } from "../keys.js";

  let focusIndex = $state(0);
  let searchTimer;
  let expandedKeys = $state(new Set());
  let rowsEl;

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
  let smartCatMsgs = $state({});  // category -> loaded messages (lazy on expand)
  // Bulk category-done hides ids we don't hold objects for; single-row done
  // relies on the row object's own is_done (so the store's undo, which flips
  // that flag back, also un-hides it here — a separate id set desynced).
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
    loadCategory(cat);
  }
  function seeAll(cat) { openCategory(cat, "all"); }

  // Expanded bundles can hold hundreds of in-memory mails; render a window.
  const CHUNK = 12;
  let catShown = $state({});               // key -> rows currently rendered
  const shownFor = (key) => catShown[key] ?? CHUNK;
  function bumpShown(key) { catShown = { ...catShown, [key]: shownFor(key) + CHUNK }; }

  // The MAIN list is windowed too: mount 30 rows, stream in more as you
  // scroll. Rendering every message meant the flip animation measured hundreds
  // of rows on each triage action — that was the "whole app lags" feel.
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
  // Keyboard navigation can outrun the window — grow it before focus hits the edge.
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
  // the focused row — previously they lived outside `items`, so focus stayed
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
    // Bundles/threads hold their messages in memory — window the render.
    const vis = visibleIn(g.msgs);
    const lim = shownFor(g.key);
    for (const m of vis.slice(0, lim)) out.push({ kind: "msg", msg: m, inGroup: true });
    if (vis.length > lim) out.push({ kind: "groupmore", key: "gm:" + g.key, gkey: g.key, remaining: vis.length - lim });
    return out;
  }

  function buildItems(msgs) {
    if (smartActive()) {
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
        const hot = groups.filter((g) => g.new > 0 || g.category === openCat);   // NEW mail or being read → top
        const cold = groups.filter((g) => !(g.new > 0 || g.category === openCat)); // otherwise → end of Today
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
    // Date-section layout has its own ordering (with header rows) — don't pull
    // pinned/VIP to the top or it would orphan the section headers.
    if (smartActive() && (app.settings.smartGroupPlacement || "dateSections") === "dateSections") return built;
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
      // "Done all" must cover the ENTIRE category — fetch the full id list
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
      // A category-done can touch hundreds/thousands of messages — always offer
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
    // Nested bundle rows pass index < 0 and just toggle themselves — using the
    // group's index produced a zero-width range that selected the whole bundle.
    if (e?.shiftKey && lastIdx >= 0 && index >= 0) {
      const [a, b] = [Math.min(lastIdx, index), Math.max(lastIdx, index)];
      // Ranges can span headers, category cards, and group frames — only rows
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
  function openCtx(e, msg) { e.preventDefault(); ctxSearch = ""; ctx = { x: e.clientX, y: e.clientY, msg }; }
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
    ];
    const q = ctxSearch.trim().toLowerCase();
    if (!q) return acts;
    // When searching, drop section separators and match label + keywords.
    return acts.filter((a) => !a.sep && ((a.label + " " + (a.kw || "")).toLowerCase().includes(q)));
  }
  function runCtx(a) { if (a?.run) ctxDo(a.run); }
  function ctxEnter() {
    const first = ctxActions(ctx.msg).find((a) => !a.sep);
    if (first) runCtx(first);
  }

  // Position the menu fully on-screen — flip up/left near edges, cap height.
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

  // Keep expanded category lists live: refetch them in place when a sync lands
  // (a cleared cache would flash "Loading…" inside every open card). Refetch
  // only at each group's CURRENT page size — not the whole category.
  $effect(() => {
    void app.syncTick;
    const entries = untrack(() => Object.entries(smartCatMsgs));
    for (const [key, entry] of entries) {
      const cat = key.split("|")[0];
      const params = { ...smartScope(), category: cat, include_done: app.showDone, limit: entry.limit };
      if (entry.mode === "new") { params.unread_only = true; params.new_days = app.settings.smartNewDays ?? 3; }
      untrack(() => messagesApi.list(params))
        .then((msgs) => {
          if (smartCatMsgs[key]) smartCatMsgs = { ...smartCatMsgs, [key]: { msgs, limit: entry.limit, full: msgs.length < entry.limit, mode: entry.mode } };
        })
        .catch(() => {});
    }
  });

  // Keep focusIndex in range as the list changes.
  $effect(() => {
    if (focusIndex >= items.length) focusIndex = Math.max(0, items.length - 1);
  });

  // Prefetch the focused item's latest message (urgent — jumps the queue) plus
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
    app.search = v;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshMessages(), 220);
  }
  function saveSearch() {
    const name = prompt(t("list.namePrompt"), app.search);
    if (name) saveCurrentSearch(name.trim());
  }

  // Pull keyboard focus back to the list. Opening a message loads the reader
  // iframe, which (in the desktop webview) grabs focus — after which shortcuts
  // like `e` land in the iframe and appear dead until you click the list again.
  function refocusList() {
    queueMicrotask(() => {
      const ae = document.activeElement;
      if (ae instanceof HTMLInputElement || ae instanceof HTMLTextAreaElement || ae?.isContentEditable) return;
      rowsEl?.focus?.({ preventScroll: true });
    });
  }

  async function open(message, index) {
    // In selection mode, a row click adds/removes from the selection instead of opening.
    if (selectedIds.length > 0) { toggleSelect(message, index); return; }
    // index < 0 = a message nested inside an expanded bundle/group; it has no
    // slot in `items`, so don't move keyboard focus to the group card (that's
    // what made a subsequent `e` mass-complete the whole category).
    if (index >= 0) focusIndex = index;
    // Conversations open as conversations — no extra "View conversation" click.
    // Siblings visible in the loaded list flip the thread view on instantly;
    // siblings elsewhere (other folders/pages) are caught by the Reader's
    // thread check, which promotes the view once the thread comes back >1.
    app.threadKey =
      (message.thread_id && app.messages.some((m) => m.thread_id === message.thread_id && m.id !== message.id))
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
    if (combo === kb.search) {
      document.querySelector(".list .search")?.focus(); e.preventDefault(); return;
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
    if (combo === kb.next) {
      step(1); e.preventDefault();
    } else if (combo === kb.prev) {
      step(-1); e.preventDefault();
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
        // message was the open one) — a second advance here picked a DIFFERENT
        // "next" (items is re-sorted) and marked an unseen message read.
        markDone(it.msg, !it.msg.is_done);
      } else if (it.gtype === "category") doneCategory(it);
      else doneGroup(it);
      refocusList();
      e.preventDefault();
    } else if (combo === kb.reply || combo === kb.forward) {
      // Reply/forward the OPEN message (single or conversation) — the reader
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

{#if ctx}
  <div class="ctxmenu" use:placeMenu={{ x: ctx.x, y: ctx.y }} onclick={(e) => e.stopPropagation()}>
    <input class="ctx-search" placeholder={t("list.searchActions")} bind:value={ctxSearch} autofocus
      onkeydown={(e) => { if (e.key === "Enter") ctxEnter(); else if (e.key === "Escape") closeCtx(); }} />
    <div class="ctx-list">
      {#each ctxActions(ctx.msg) as a}
        {#if a.sep}
          <div class="ctx-head">{a.sep}</div>
        {:else}
          <button class:danger={a.danger} onclick={() => runCtx(a)}>{#if a.icon}{@html a.icon} {/if}{a.label}</button>
        {/if}
      {/each}
      {#if ctxActions(ctx.msg).length === 0}<div class="ctx-empty">{t("list.noMatchingAction")}</div>{/if}
    </div>
  </div>
{/if}

<section class="list">
  <header>
    <div class="row1">
      <h2>{title}</h2>
      <label class="slider" title={t("list.showDoneTip")}>
        <input type="checkbox" checked={app.showDone} onchange={toggleShowDone} />
        <span class="track"><span class="knob"></span></span>
        <span class="lbl">{app.showDone ? t("list.showingAll") : t("list.showDone")}</span>
      </label>
    </div>
    <div class="searchrow">
      <SearchBar value={app.search} oninput={onSearch} />
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

  <div class="rows" bind:this={rowsEl} tabindex="-1">
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
             animate:flip={{ duration: 130 }} out:fly={{ x: 48, duration: 140 }}>
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
              onopen={() => open(item.msg, i)}
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
  </div>

  <footer class="hint">
    <kbd>↓</kbd><kbd>↑</kbd> {t("list.hintMove")} · <kbd>e</kbd> {t("list.hintToggleDone")} · <kbd>↵</kbd> {t("list.hintOpen")}
  </footer>
</section>

<style>
  .list { display: flex; flex-direction: column; border-right: 1px solid var(--hairline); min-height: 0; background: var(--bg); }
  header { padding: 14px 16px 11px; border-bottom: 1px solid var(--hairline); display: flex; flex-direction: column; gap: 10px; }
  .row1 { display: flex; align-items: center; justify-content: space-between; }
  h2 { margin: 0; font-size: 16.5px; font-weight: 700; letter-spacing: -0.02em; }
  .searchrow { display: flex; gap: 8px; align-items: center; }
  .search { flex: 1; }
  .savesearch { flex: none; color: var(--accent); font-weight: 600; font-size: 12px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--accent-soft); transition: background var(--t-fast) var(--ease); }
  .savesearch:hover { background: var(--accent-soft-2); }
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
  /* Skip layout/paint for offscreen rows entirely — the single biggest scroll
     win. Date headers are excluded: paint containment would clip their sticky
     positioning. */
  .cv { content-visibility: auto; contain-intrinsic-size: auto 64px; }
  /* Spark-style date section header. NOTE: no backdrop-filter here — blur on a
     sticky element repaints every scroll frame in WebView2 (felt "heavy"). */
  .datesep { position: sticky; top: 0; z-index: 4; padding: 8px 16px 5px; font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.08em; color: var(--faint);
    background: var(--bg);
    border-bottom: 1px solid var(--hairline); }
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
    background: var(--surface-2); color: var(--muted); font-size: 28px; box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text) 5%, transparent); }
  .big :global(svg) { width: 30px; height: 30px; }

  footer.hint { padding: 8px 14px; border-top: 1px solid var(--hairline); color: var(--faint); font-size: 11px; }
  kbd {
    display: inline-block; padding: 1px 6px; margin: 0 1px; border-radius: 5px;
    background: var(--surface-2); border: 1px solid var(--hairline); font-size: 10px; font-family: ui-monospace, monospace;
  }
</style>
