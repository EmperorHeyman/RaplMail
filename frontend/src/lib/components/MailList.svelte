<script>
  import { flip } from "svelte/animate";
  import { fly, slide } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import { app, refreshMessages, markDone, toggleShowDone, prefetchBody, setCategory, snoozePresets, presetWhen, notify, saveCurrentSearch, openThread, refreshQueue, smartActive, groupedCategories, searchAddress, snoozeMessage, muteSender, muteThread, pinMessage, isVip, toggleVip, isTrustedSender, toggleTrusted, blockSender, createRuleFromSender, setSenderCategory } from "../store.svelte.js";
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
  const CAT_META = {
    updates: { label: "Notifications", icon: icons.bell },
    newsletters: { label: "Newsletters", icon: icons.newspaper },
    social: { label: "Social", icon: icons.chat },
    promotions: { label: "Promotions", icon: icons.tag },
    invitations: { label: "Invitations", icon: icons.calendar },
    invitation_responses: { label: "Invitation responses", icon: icons.done },
  };
  const CAT_ORDER = ["updates", "newsletters", "social", "promotions", "invitations", "invitation_responses"];
  let smartCatMsgs = $state({});  // category -> loaded messages (lazy on expand)
  // Messages marked done from *inside* a group/bundle row — markDone only manages
  // the main list, so we hide these from the grouped views ourselves.
  let hiddenDone = $state(new Set());
  function doneRow(m, doneNow) {
    markDone(m, doneNow);
    const next = new Set(hiddenDone);
    if (doneNow) next.add(m.id); else next.delete(m.id);
    hiddenDone = next;
  }
  const visibleIn = (arr) => (app.showDone ? arr : arr.filter((x) => !hiddenDone.has(x.id)));
  function smartScope() {
    return app.selectedKind === "smart" ? { role: "inbox" } : { folder_id: app.selectedFolderId };
  }
  async function loadCategory(cat) {
    if (smartCatMsgs[cat]) return;
    try {
      const msgs = await messagesApi.list({ ...smartScope(), category: cat, include_done: app.showDone, limit: 500 });
      smartCatMsgs = { ...smartCatMsgs, [cat]: msgs };
    } catch {}
  }

  // Expanded groups can hold hundreds of mails; render a window and grow it as
  // the user scrolls to the bottom, so opening a big group stays snappy.
  const CHUNK = 12;
  let catShown = $state({});               // key -> rows currently rendered
  const shownFor = (key) => catShown[key] ?? CHUNK;
  function bumpShown(key) { catShown = { ...catShown, [key]: shownFor(key) + CHUNK }; }
  // Svelte action: when the sentinel scrolls into view, render the next chunk.
  function loadMore(node, key) {
    let io;
    const start = () => {
      io?.disconnect();
      io = new IntersectionObserver(
        (entries) => { if (entries.some((e) => e.isIntersecting)) bumpShown(key); },
        { root: rowsEl || null, rootMargin: "240px 0px" }
      );
      io.observe(node);
    };
    start();
    return { destroy() { io?.disconnect(); } };
  }

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

  const NOTIF = new Set(["updates", "social", "newsletters"]);
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
                        count: g.count, senders: shown, more, latest: g.latest, recent: g.recent || [] });
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
        // Spark-style: messages split into Today / Yesterday / This week / …
        // with the category cards parked at the END of Today.
        const out = [];
        let bucket = null;
        let groupsDone = false;
        for (const it of items) {
          const b = dateBucket(it.msg.date);
          if (b !== bucket) {
            // Leaving Today → drop the group cards before the next section.
            if (bucket === "Today" && !groupsDone) { out.push(...groups); groupsDone = true; }
            out.push({ kind: "header", key: "h:" + b, label: b });
            bucket = b;
          }
          out.push(it);
        }
        if (!groupsDone) {
          // No section followed Today (everything is today, or there's no today
          // mail) — put the cards after today's messages, else at the very top.
          out.push(...groups);
        }
        return out;
      }
      if (placement === "top") return [...groups, ...items];
      if (placement === "afterN") {
        const k = Math.max(0, app.settings.smartGroupsAfter ?? 3);
        return [...items.slice(0, k), ...groups, ...items.slice(k)];
      }
      if (placement === "timeline") {
        // Interleave groups + messages by recency: a group floats to the date of
        // its newest mail, and any newer standalone mail pushes it down.
        const dateOf = (it) => String((it.kind === "group" ? it.latest : it.msg.date) || "");
        return [...items, ...groups].sort((a, b) => dateOf(b).localeCompare(dateOf(a)));
      }
      return [...items, ...groups]; // "bottom"
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
      return items;
    }
    return msgs.map((m) => ({ kind: "msg", msg: m }));
  }
  const items = $derived.by(() => {
    const built = buildItems(app.messages);
    // Date-section layout has its own ordering (with header rows) — don't pull
    // pinned/VIP to the top or it would orphan the section headers.
    if (smartActive() && (app.settings.smartGroupPlacement || "dateSections") === "dateSections") return built;
    // Pinned first, then VIP-sender mail, then everything else (stable).
    const isP = (it) => it.kind === "msg" && it.msg.pinned;
    const isV = (it) => it.kind === "msg" && !it.msg.pinned && isVip(it.msg.from_addr);
    const pinned = built.filter(isP);
    const vip = built.filter(isV);
    if (!pinned.length && !vip.length) return built;
    return [...pinned, ...vip, ...built.filter((it) => !isP(it) && !isV(it))];
  });

  function itemMsgs(item) { return item.kind === "msg" ? [item.msg] : item.msgs; }

  async function doneGroup(item) {
    const ids = item.msgs.map((m) => m.id);
    if (!app.showDone) app.messages = app.messages.filter((m) => !ids.includes(m.id));
    try {
      await messagesApi.bulk(ids, "done");
      notify(`${ids.length} marked done`, "info", () => {
        messagesApi.bulk(ids, "undone")
          .then(() => refreshMessages({ background: true }))
          .catch(() => notify("Couldn't undo", "error"));
      });
      refreshMessages({ background: true });
    } catch (e) { notify("Couldn't update", "error"); refreshMessages({ background: true }); }
  }

  // Mark an entire Smart Inbox category done (every mail in it, not just the
  // loaded window). Used by the card's "Done all" button and the `e` shortcut.
  async function doneCategory(item) {
    try {
      let list = smartCatMsgs[item.key];
      if (!list) list = await messagesApi.list({ ...smartScope(), category: item.category, include_done: false, limit: 5000 });
      const ids = list.map((m) => m.id);
      if (!ids.length) return;
      const idset = new Set(ids);
      app.messages = app.messages.filter((m) => !idset.has(m.id));   // optimistic
      hiddenDone = new Set([...hiddenDone, ...ids]);
      const s = new Set(expandedKeys); s.delete(item.key); expandedKeys = s;  // collapse
      await messagesApi.bulk(ids, "done");
      // A category-done can touch hundreds/thousands of messages — always offer
      // undo (single-message done already does; this destructive bulk must too).
      notify(`${ids.length} marked done`, "info", () => {
        hiddenDone = new Set([...hiddenDone].filter((id) => !idset.has(id)));
        messagesApi.bulk(ids, "undone")
          .then(() => refreshMessages({ background: true }))
          .catch(() => notify("Couldn't undo", "error"));
      });
      refreshMessages({ background: true });   // also refreshes the group counts
    } catch { notify("Couldn't mark group done", "error"); refreshMessages({ background: true }); }
  }
  function toggleExpand(key) {
    const s = new Set(expandedKeys);
    s.has(key) ? s.delete(key) : s.add(key);
    expandedKeys = s;
  }
  function activate(item) {
    if (item.gtype === "category") { toggleExpand(item.key); loadCategory(item.category); return; }
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
      const ids = items.slice(a, b + 1).flatMap((it) => it.kind === "msg" ? [it.msg.id] : it.msgs.map((m) => m.id));
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
  function toggleSeen(m) { const v = !m.is_seen; m.is_seen = v; messagesApi.setSeen(m.id, v).catch(() => {}); }
  function toggleFlag(m) { const v = !m.is_flagged; m.is_flagged = v; messagesApi.setFlag(m.id, v).catch(() => {}); }

  // Flat, searchable action list for the right-click menu. `kw` adds extra
  // search keywords beyond the label.
  function ctxActions(m) {
    const acts = [
      { label: "Open", run: () => open(m, focusIndex) },
      { label: m.pinned ? "Unpin" : "Pin to top", icon: icons.pin, run: () => pinMessage(m) },
      { label: m.is_done ? "Mark not done" : "Mark done", icon: icons.done, kw: "complete e", run: () => markDone(m, !m.is_done) },
      { label: m.is_seen ? "Mark unread" : "Mark read", kw: "seen", run: () => toggleSeen(m) },
      { label: m.is_flagged ? "Unflag" : "Flag", icon: icons.flag, kw: "star", run: () => toggleFlag(m) },
      { label: isVip(m.from_addr) ? "Remove VIP" : "Mark sender VIP", icon: icons.star, run: () => toggleVip(m.from_addr) },
      { label: isTrustedSender(m.from_addr) ? "Unmark safe" : "Mark sender safe", icon: icons.shieldCheck, run: () => toggleTrusted(m.from_addr) },
      { sep: "Move to category", kw: "" },
      { label: "Move to Primary (normal inbox)", icon: icons.inbox, kw: "move out newsletter normal queue", run: () => setSenderCategory(m, "primary") },
      ...Object.entries(CAT_META).map(([id, meta]) => ({ label: `Move to ${meta.label}`, icon: meta.icon, kw: "move category " + id, run: () => setSenderCategory(m, id) })),
      { label: "Reset category (auto)", icon: icons.reset, kw: "move category", run: () => setSenderCategory(m, "auto") },
      { sep: "Snooze" },
      ...snoozePresets().map((p) => ({ label: `Snooze: ${p.label}`, icon: icons.snooze, kw: "snooze remind later", run: () => snoozeMessage(m, p.iso, p.presence) })),
      { sep: "More" },
      { label: "Archive", icon: icons.archive, run: () => archiveOne(m) },
      { label: "Delete", icon: icons.trash, danger: true, run: () => deleteOne(m) },
      { label: "Show mail from sender", kw: "filter from", run: () => searchAddress(m.from_addr) },
      { label: "Mute sender", icon: icons.mute, run: () => muteSender(m) },
      { label: "Mute conversation", icon: icons.mute, kw: "thread", run: () => muteThread(m) },
      { label: "Block sender", icon: icons.junk, danger: true, run: () => blockSender(m) },
      { label: "Create rule…", icon: icons.bolt, run: () => createRuleFromSender(m) },
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
  function archiveOne(m) { app.messages = app.messages.filter((x) => x.id !== m.id); messagesApi.bulk([m.id], "archive").then(refreshQueue); }
  function deleteOne(m) { app.messages = app.messages.filter((x) => x.id !== m.id); messagesApi.bulk([m.id], "delete").then(refreshQueue); }

  async function bulk(action, until = null) {
    const ids = [...selectedIds];
    if (!ids.length) return;
    // Optimistic: drop affected rows from the current view for removing actions.
    if (["done", "snooze", "archive", "delete"].includes(action) && !app.showDone) {
      app.messages = app.messages.filter((m) => !ids.includes(m.id));
    }
    clearSelection();
    try {
      await messagesApi.bulk(ids, action, until);
      notify(`${ids.length} ${action === "delete" ? "deleted" : action === "archive" ? "archived" : action + "d"}`);
      refreshMessages({ background: true });
      if (action === "archive" || action === "delete") refreshQueue();
    } catch (e) { notify("Bulk action failed: " + e.message, "error"); refreshMessages({ background: true }); }
  }

  // Clear selection when the view changes.
  $effect(() => { void app.selectedFolderId; void app.selectedKind; void app.category; void app.search; clearSelection(); });

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
    const name = prompt("Name this saved search:", app.search);
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
    app.threadKey = null;
    app.selectedMessageId = message.id;
    if (!message.is_seen) {
      message.is_seen = true;
      messagesApi.setSeen(message.id, true).catch(() => {});
    }
    refocusList();
  }

  function onKey(e) {
    // Never hijack keys while composing, in a dialog, or typing in any field
    // (inputs, textareas, or the contenteditable compose/signature editors).
    if (app.composing || app.paletteOpen) return;
    const t = e.target;
    if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || (t && t.isContentEditable)) return;
    const kb = app.settings.keybinds;
    const combo = keyCombo(e);
    if (!combo) return;
    if (combo === kb.search) {
      document.querySelector(".list .search")?.focus(); e.preventDefault(); return;
    }
    if (!items.length) return;
    // Skip non-interactive date-section headers when arrowing.
    const step = (dir) => {
      let i = focusIndex;
      for (let n = 0; n < items.length; n++) {
        i = Math.min(items.length - 1, Math.max(0, i + dir));
        if (items[i]?.kind !== "header") break;
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
      if (it.kind === "msg") open(it.msg, focusIndex); else if (it.kind === "group") activate(it);
    } else if (combo === kb.done) {
      const it = items[focusIndex];
      if (it.kind === "header") { e.preventDefault(); return; }
      if (it.kind === "msg") {
        const doneNow = !it.msg.is_done;
        markDone(it.msg, doneNow);
        if (doneNow && app.settings.openNextOnDone && selectedIds.length === 0) {
          queueMicrotask(() => { const nx = items[focusIndex]; if (nx?.kind === "msg") open(nx.msg, focusIndex); });
        }
      } else if (it.gtype === "category") doneCategory(it);
      else doneGroup(it);
      refocusList();
      e.preventDefault();
    }
  }

  const title = $derived(
    app.search ? `Search: "${app.search}"` :
    app.selectedKind === "smart" ? "Smart Inbox" :
    app.selectedKind === "unified" ? "All Inboxes" :
    app.selectedKind === "sent" ? "All Sent" :
    app.selectedKind === "snoozed" ? "Snoozed" :
    app.selectedKind === "screener" ? "Screener" :
    app.selectedKind === "papertrail" ? "Paper Trail" :
    app.selectedKind === "followups" ? "Follow-ups" :
    (app.folders.find((f) => f.id === app.selectedFolderId)?.name || "Inbox")
  );

  const CATS = [
    { id: null, label: "All" },
    { id: "primary", label: "Primary" },
    { id: "newsletters", label: "Newsletters" },
    { id: "social", label: "Social" },
    { id: "updates", label: "Updates" },
    { id: "promotions", label: "Promotions" },
  ];
  const showCats = $derived(
    !app.search && !smartActive() && app.selectedKind !== "snoozed" && app.selectedKind !== "screener" &&
    (app.selectedKind === "unified" || app.selectedFolderRole === "inbox")
  );

  const emptyState = $derived(
    app.search ? { icon: icons.search, text: "No matches for that search." } :
    app.selectedKind === "snoozed" ? { icon: icons.snooze, text: "Nothing snoozed." } :
    app.selectedKind === "screener" ? { icon: icons.screener, text: "Screener's clear — no first-time senders waiting." } :
    app.selectedKind === "papertrail" ? { icon: icons.receipt, text: "No receipts or invoices here yet." } :
    app.selectedKind === "followups" ? { icon: icons.done, text: "Nothing's waiting on a reply." } :
    { icon: icons.inboxZero, text: "Inbox zero. You're all caught up." }
  );
</script>

<svelte:window on:keydown={onKey} on:click={() => ctx && closeCtx()} />

{#if ctx}
  <div class="ctxmenu" use:placeMenu={{ x: ctx.x, y: ctx.y }} onclick={(e) => e.stopPropagation()}>
    <input class="ctx-search" placeholder="Search actions…" bind:value={ctxSearch} autofocus
      onkeydown={(e) => { if (e.key === "Enter") ctxEnter(); else if (e.key === "Escape") closeCtx(); }} />
    <div class="ctx-list">
      {#each ctxActions(ctx.msg) as a}
        {#if a.sep}
          <div class="ctx-head">{a.sep}</div>
        {:else}
          <button class:danger={a.danger} onclick={() => runCtx(a)}>{#if a.icon}{@html a.icon} {/if}{a.label}</button>
        {/if}
      {/each}
      {#if ctxActions(ctx.msg).length === 0}<div class="ctx-empty">No matching action</div>{/if}
    </div>
  </div>
{/if}

<section class="list">
  <header>
    <div class="row1">
      <h2>{title}</h2>
      <label class="slider" title="Show messages you've marked done alongside the rest">
        <input type="checkbox" checked={app.showDone} onchange={toggleShowDone} />
        <span class="track"><span class="knob"></span></span>
        <span class="lbl">{app.showDone ? "Showing all" : "Show done"}</span>
      </label>
    </div>
    <div class="searchrow">
      <SearchBar value={app.search} oninput={onSearch} />
      {#if app.search.trim()}<button class="savesearch" title="Save as smart folder" onclick={saveSearch}>{@html icons.star} Save</button>{/if}
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
    <div class="bulkbar">
      <span class="count">{selectedIds.length} selected</span>
      <button onclick={() => bulk("done")} title="Mark done">{@html icons.done} Done</button>
      <button onclick={() => bulk("seen")} title="Mark read">Read</button>
      <button onclick={() => bulk("flag")} title="Flag">{@html icons.flag} Flag</button>
      <div class="snz">
        <button onclick={() => (bulkSnooze = !bulkSnooze)}>{@html icons.snooze} Snooze</button>
        {#if bulkSnooze}
          <div class="snz-menu">
            {#each snoozePresets().filter((p) => p.iso) as p}<button onclick={() => bulk("snooze", p.iso)}>{p.label}</button>{/each}
          </div>
        {/if}
      </div>
      <button onclick={() => bulk("archive")} title="Archive">{@html icons.archive} Archive</button>
      <button class="danger" onclick={() => bulk("delete")} title="Delete">{@html icons.trash} Delete</button>
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
      {#each items as item, i (item.kind === "msg" ? "m" + item.msg.id : "g" + item.key)}
        <div animate:flip={{ duration: 220 }} out:fly={{ x: 60, duration: 200 }}>
          {#if item.kind === "header"}
            <div class="datesep">{item.label}</div>
          {:else if item.kind === "msg"}
            <MessageRow
              message={item.msg}
              focused={i === focusIndex}
              selected={app.selectedMessageId === item.msg.id}
              checked={isChecked(item.msg.id)}
              selecting={selectedIds.length > 0}
              onselect={(e) => toggleSelect(item.msg, i, e)}
              onopen={() => open(item.msg, i)}
              ondone={() => markDone(item.msg, !item.msg.is_done)}
              onarchive={() => archiveOne(item.msg)}
              ondelete={() => deleteOne(item.msg)}
              onmenu={(e) => openCtx(e, item.msg)}
            />
          {:else if item.gtype === "category"}
            <SmartGroupCard
              label={CAT_META[item.category]?.label || item.category}
              icon={CAT_META[item.category]?.icon || icons.folder}
              count={item.count} senders={item.senders} more={item.more}
              focused={i === focusIndex} expanded={expandedKeys.has(item.key)}
              onToggle={() => { focusIndex = i; activate(item); }}
              onSender={(email) => searchAddress(email)}
              onDoneAll={() => { focusIndex = i; doneCategory(item); }}
            />
            {#if expandedKeys.has(item.key)}
              <div class="catbody" transition:slide={{ duration: 160, easing: cubicOut }}>
                {#if smartCatMsgs[item.key]}
                  {@const loaded = visibleIn(smartCatMsgs[item.key])}
                  {#each loaded.slice(0, shownFor(item.key)) as m (m.id)}
                    <div class="bundled">
                      <MessageRow message={m} selected={app.selectedMessageId === m.id}
                        checked={isChecked(m.id)} selecting={selectedIds.length > 0}
                        onselect={(e) => toggleSelect(m, -1, e)}
                        onopen={() => open(m, -1)} ondone={() => doneRow(m, !m.is_done)}
                        onarchive={() => archiveOne(m)} ondelete={() => deleteOne(m)}
                        onmenu={(e) => openCtx(e, m)} />
                    </div>
                  {/each}
                  {#if loaded.length > shownFor(item.key)}
                    <div class="bundled loadmore" use:loadMore={item.key}>
                      <span class="spin">{@html icons.sync}</span> Loading {loaded.length - shownFor(item.key)} more…
                    </div>
                  {/if}
                {:else}
                  <div class="bundled muted" style="padding:10px 22px">Loading…</div>
                {/if}
              </div>
            {/if}
          {:else}
            <GroupRow
              gtype={item.gtype} msgs={item.msgs} latest={item.latest}
              focused={i === focusIndex} expanded={expandedKeys.has(item.key)}
              checked={groupChecked(item)}
              onactivate={() => { focusIndex = i; activate(item); }}
              ondoneall={() => doneGroup(item)}
              onselect={() => selectGroup(item)}
            />
            {#if item.gtype === "bundle" && expandedKeys.has(item.key)}
              <div class="catbody" transition:slide={{ duration: 160, easing: cubicOut }}>
                {#if item.msgs.length}
                  {@const loaded = visibleIn(item.msgs)}
                  {#each loaded.slice(0, shownFor(item.key)) as m (m.id)}
                    <div class="bundled">
                      <MessageRow message={m} selected={app.selectedMessageId === m.id}
                        checked={isChecked(m.id)} selecting={selectedIds.length > 0}
                        onselect={(e) => toggleSelect(m, -1, e)}
                        onopen={() => open(m, -1)} ondone={() => doneRow(m, !m.is_done)}
                        onarchive={() => archiveOne(m)} ondelete={() => deleteOne(m)}
                        onmenu={(e) => openCtx(e, m)} />
                    </div>
                  {/each}
                  {#if loaded.length > shownFor(item.key)}
                    <div class="bundled loadmore" use:loadMore={item.key}>
                      <span class="spin">{@html icons.sync}</span> Loading {loaded.length - shownFor(item.key)} more…
                    </div>
                  {/if}
                {/if}
              </div>
            {/if}
          {/if}
        </div>
      {/each}
    {/if}
  </div>

  <footer class="hint">
    <kbd>↓</kbd><kbd>↑</kbd> move · <kbd>e</kbd> toggle done · <kbd>↵</kbd> open
  </footer>
</section>

<style>
  .list { display: flex; flex-direction: column; border-right: 1px solid var(--border); min-height: 0; background: var(--bg); }
  header { padding: 14px 16px 12px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 11px; }
  .row1 { display: flex; align-items: center; justify-content: space-between; }
  h2 { margin: 0; font-size: 16px; letter-spacing: -0.01em; }
  .searchrow { display: flex; gap: 8px; align-items: center; }
  .search { flex: 1; }
  .savesearch { flex: none; color: var(--accent); font-weight: 600; font-size: 12px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--surface-2); }
  .savesearch:hover { background: var(--surface-3); }
  .cats { display: flex; gap: 4px; flex-wrap: wrap; }
  .cat { font-size: 12px; padding: 4px 11px; border-radius: 999px; color: var(--muted); background: var(--surface-2); }
  .cat:hover { background: var(--surface-3); color: var(--text); }
  .cat.active { background: var(--accent); color: #fff; }

  .bulkbar { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--surface-2); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .bulkbar .count { font-weight: 600; font-size: 13px; margin-right: 4px; }
  .bulkbar button { padding: 6px 10px; border-radius: var(--radius-sm); background: var(--surface-3); font-size: 12px; font-weight: 550; }
  .bulkbar button:hover { background: #2f3545; }
  .bulkbar button.danger:hover { background: #3a1f23; color: var(--danger); }
  .bulkbar .clear { margin-left: auto; background: transparent; }
  .snz { position: relative; }
  .snz-menu { position: absolute; top: 100%; left: 0; z-index: 15; margin-top: 4px; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 4px; display: flex; flex-direction: column; min-width: 150px; }
  .snz-menu button { text-align: left; background: transparent; }
  .snz-menu button:hover { background: var(--accent); color: #fff; }

  /* The Spark-style done slider */
  .slider { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
  .slider input { display: none; }
  .slider .track {
    width: 38px; height: 22px; border-radius: 999px; background: var(--surface-3);
    position: relative; transition: background 0.16s;
  }
  .slider .knob {
    position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
    background: #fff; transition: transform 0.16s;
  }
  .slider input:checked + .track { background: var(--done); }
  .slider input:checked + .track .knob { transform: translateX(16px); }
  .slider .lbl { font-size: 12px; color: var(--muted); min-width: 64px; }

  .rows { flex: 1; overflow-y: auto; min-height: 0; }
  .rows:focus { outline: none; }
  /* Spark-style date section header */
  .datesep { position: sticky; top: 0; z-index: 4; padding: 7px 16px 5px; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted);
    background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(6px);
    border-bottom: 1px solid var(--border); }
  .catbody { overflow: hidden; }
  .bundled { padding-left: 22px; background: var(--surface); box-shadow: inset 2px 0 0 var(--surface-3); }
  .loadmore { display: flex; align-items: center; gap: 8px; padding: 11px 22px; color: var(--muted); font-size: 12px; }
  .loadmore .spin { display: inline-flex; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .ctxmenu { position: fixed; z-index: 300; width: 244px; max-height: min(72vh, 560px); background: var(--surface-3);
    border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: 6px;
    display: flex; flex-direction: column; min-height: 0; }
  .ctx-search { width: 100%; box-sizing: border-box; margin-bottom: 5px; padding: 7px 10px; font-size: 13px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; color: var(--text); }
  .ctx-search:focus { border-color: var(--accent); outline: none; }
  .ctx-list { overflow-y: auto; min-height: 0; display: flex; flex-direction: column; }
  .ctx-list > button { text-align: left; padding: 8px 11px; border-radius: 6px; font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 8px; }
  .ctx-list > button:hover { background: var(--accent); color: #fff; }
  .ctx-list > button.danger:hover { background: var(--danger); }
  .ctx-head { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); padding: 8px 11px 3px; }
  .ctx-empty { color: var(--muted); font-size: 13px; padding: 10px 11px; }

  /* Loading skeleton */
  .skel { display: flex; gap: 11px; align-items: center; padding: 13px 14px; border-bottom: 1px solid var(--border); }
  .sk-av { width: 34px; height: 34px; border-radius: 50%; flex: none; }
  .sk-lines { flex: 1; display: flex; flex-direction: column; gap: 7px; }
  .sk-l { height: 9px; border-radius: 5px; }
  .sk-l.short { width: 55%; }
  .sk-av, .sk-l { background: linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  .muted, .empty { color: var(--muted); padding: 24px 16px; text-align: center; }
  .empty { display: flex; flex-direction: column; gap: 8px; align-items: center; margin-top: 40px; line-height: 1.6; }
  .big { font-size: 40px; }

  footer.hint { padding: 9px 14px; border-top: 1px solid var(--border); color: var(--faint); font-size: 11px; }
  kbd {
    display: inline-block; padding: 1px 6px; margin: 0 1px; border-radius: 5px;
    background: var(--surface-3); border: 1px solid var(--border); font-size: 10px; font-family: ui-monospace, monospace;
  }
</style>
