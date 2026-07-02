<script>
  import { onMount, onDestroy } from "svelte";
  import { app, openMessageById, selectSmartInbox, selectUnifiedInbox, openCompose } from "../store.svelte.js";
  import { messages as msgApi, calendar as calApi } from "../api.js";
  import { listTime } from "../time.js";
  import { icons } from "../icons.js";

  // --- live clock ----------------------------------------------------------
  let now = $state(new Date());
  let timer;
  let mounted = false;
  onMount(() => { timer = setInterval(() => (now = new Date()), 1000); load().then(() => (mounted = true)); });
  onDestroy(() => clearInterval(timer));
  // Live-refresh when new mail syncs (quietly, no loading flash), so Home stays
  // current without needing to navigate away and back.
  $effect(() => { void app.syncTick; if (mounted) load(true); });

  const greeting = $derived.by(() => {
    const h = now.getHours();
    return h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  });
  const clock = $derived(now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }));
  const dateStr = $derived(now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }));
  const firstName = $derived((app.accounts[0]?.display_name || app.accounts[0]?.email || "").split(/[ @]/)[0]);

  // --- data ----------------------------------------------------------------
  let recent = $state([]);
  let events = $state([]);     // events across the next ~2 weeks (for "up next" + week strip)
  let loading = $state(true);
  // Real inbox unread across all accounts — counting the 6 fetched rows capped
  // the hero stat at 6.
  const unread = $derived(
    app.folders.filter((f) => f.role === "inbox").reduce((n, f) => n + (f.unread_count || 0), 0)
  );

  async function load(quiet = false) {
    if (!quiet) loading = true;
    try {
      const rows = await msgApi.list({ role: "inbox", limit: 6 });
      recent = Array.isArray(rows) ? rows : (rows.items || []);
    } catch {}
    try {
      const start = new Date(now); start.setHours(0, 0, 0, 0);
      const end = new Date(start); end.setDate(end.getDate() + 21);
      const evs = await calApi.list(start.toISOString(), end.toISOString());
      events = (Array.isArray(evs) ? evs : []).filter((e) => e.start && !e.cancelled);
    } catch {}
    loading = false;
  }

  function openMail(m) { openMessageById(m.id); }
  function goInbox() { app.view = "mail"; if (app.settings.smartInbox) selectSmartInbox(); else selectUnifiedInbox(); }
  const initial = (s) => (s || "?").trim()[0]?.toUpperCase() || "?";
  const evColor = (e) => e.color || "var(--accent)";

  // Events sorted by start, only those from now on, for "Up next".
  const upNext = $derived(
    [...events].filter((e) => new Date(e.end || e.start) >= now)
      .sort((a, b) => new Date(a.start) - new Date(b.start)).slice(0, 6)
  );

  function evWhen(iso) {
    const d = new Date(iso);
    const today = new Date(now); today.setHours(0, 0, 0, 0);
    const day = new Date(d); day.setHours(0, 0, 0, 0);
    const diff = Math.round((day - today) / 86400000);
    const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    if (diff === 0) return `Today · ${t}`;
    if (diff === 1) return `Tomorrow · ${t}`;
    return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + ` · ${t}`;
  }

  // --- week strip ----------------------------------------------------------
  const dayKey = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  function coversDay(e, day) {
    if (!e.start) return false;
    const s = new Date(e.start);
    if (!e.end) return dayKey(s) === dayKey(day);
    let end = new Date(e.end);
    if (e.all_day) end = new Date(end.getTime() - 1);
    const d = dayKey(day);
    return d >= dayKey(s) && d <= dayKey(end);
  }
  const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const week = $derived.by(() => {
    const base = new Date(now); base.setHours(0, 0, 0, 0);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base); d.setDate(base.getDate() + i);
      const evs = events.filter((e) => coversDay(e, d)).sort((a, b) => new Date(a.start) - new Date(b.start));
      return { d, evs };
    });
  });
  const eventsToday = $derived(week[0]?.evs.length || 0);
</script>

<section class="dash">
  <header class="hero">
    <div class="aurora" aria-hidden="true"><span></span><span></span><span></span></div>
    <div class="hero-in">
      <div>
        <h1>{greeting}{firstName ? `, ${firstName}` : ""}</h1>
        <p class="date">{dateStr}</p>
        <div class="stats">
          <span class="stat"><b>{unread}</b> unread</span>
          <span class="dot">·</span>
          <span class="stat"><b>{eventsToday}</b> event{eventsToday === 1 ? "" : "s"} today</span>
          <span class="dot">·</span>
          <span class="stat"><b>{app.accounts.length}</b> account{app.accounts.length === 1 ? "" : "s"}</span>
        </div>
      </div>
      <div class="clock">{clock}</div>
    </div>
  </header>

  <!-- Week at a glance -->
  <section class="card week">
    <div class="card-h">{@html icons.calendar} <b>This week</b>
      <button class="link" onclick={() => (app.view = "calendar")}>Open calendar →</button>
    </div>
    <div class="weekgrid">
      {#each week as col, i}
        <button class="day" class:today={i === 0} onclick={() => (app.view = "calendar")}>
          <span class="dname">{i === 0 ? "Today" : DOW[col.d.getDay()]}</span>
          <span class="dnum">{col.d.getDate()}</span>
          <span class="dots">
            {#each col.evs.slice(0, 4) as e}<span class="d" style="background:{evColor(e)}" title={e.summary}></span>{/each}
            {#if col.evs.length > 4}<span class="dmore">+{col.evs.length - 4}</span>{/if}
          </span>
        </button>
      {/each}
    </div>
  </section>

  <div class="grid">
    <!-- Up next: calendar -->
    <section class="card cal">
      <div class="card-h">{@html icons.calendar} <b>Up next</b>
        <button class="link" onclick={() => (app.view = "calendar")}>Calendar →</button>
      </div>
      {#if loading}
        <p class="muted">Loading…</p>
      {:else if upNext.length}
        <ul class="events">
          {#each upNext as e}
            <li style="--evc:{evColor(e)}">
              <span class="when">{e.all_day ? evWhen(e.start).split(" · ")[0] + " · all day" : evWhen(e.start)}</span>
              <span class="summary">{e.summary || "(untitled)"}</span>
              {#if e.location}<span class="loc">{e.location}</span>{/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted">Nothing scheduled. Add a calendar in Settings → Calendar &amp; Contacts.</p>
      {/if}
    </section>

    <!-- Latest mail -->
    <section class="card mail">
      <div class="card-h">{@html icons.inbox} <b>Latest mail</b>
        {#if unread}<span class="badge">{unread} unread</span>{/if}
        <button class="link" onclick={goInbox}>Inbox →</button>
      </div>
      {#if loading}
        <p class="muted">Loading…</p>
      {:else if recent.length}
        <ul class="mails">
          {#each recent as m}
            <li>
              <button class="mrow" class:unread={!m.is_seen} onclick={() => openMail(m)}>
                <span class="av">{initial(m.from_name || m.from_addr)}</span>
                <span class="who">{m.from_name || m.from_addr}</span>
                <span class="subj">{m.subject || "(no subject)"}</span>
                <span class="t">{listTime(m.date)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted">Inbox is empty. 🎉</p>
      {/if}
    </section>
  </div>

  <div class="quick">
    <button class="qbtn" onclick={() => openCompose({ to: "", subject: "", html: "" })}>{@html icons.compose} New message</button>
    <button class="qbtn" onclick={goInbox}>{@html icons.inbox} Go to inbox</button>
    <button class="qbtn" onclick={() => (app.view = "calendar")}>{@html icons.calendar} Calendar</button>
    <a class="qbtn rapl" href="https://rapl-group.eu/" target="_blank" rel="noreferrer">{@html icons.globe || ""} rapl-group.eu</a>
  </div>
</section>

<style>
  .dash { flex: 1; overflow-y: auto; padding: 26px 30px 34px; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
  /* Staggered entrance: hero, then cards, then quick actions. */
  .dash > * { animation: rise-in var(--t-slow) var(--ease) backwards; }
  .dash > *:nth-child(2) { animation-delay: 40ms; }
  .dash > *:nth-child(3) { animation-delay: 80ms; }
  .dash > *:nth-child(4) { animation-delay: 120ms; }

  /* Hero with a soft animated aurora — feels alive without any external image. */
  .hero { position: relative; overflow: hidden; border-radius: calc(var(--radius) + 3px); border: 1px solid var(--hairline);
    background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 22%, var(--surface)), var(--surface) 70%); padding: 26px 28px;
    box-shadow: var(--shadow-sm); }
  .aurora { position: absolute; inset: 0; z-index: 0; filter: blur(46px); opacity: 0.6; pointer-events: none; }
  .aurora span { position: absolute; width: 240px; height: 240px; border-radius: 50%; }
  .aurora span:nth-child(1) { background: var(--accent); top: -90px; left: 8%; }
  .aurora span:nth-child(2) { background: #8a6df0; top: -60px; right: 14%; width: 200px; height: 200px; }
  .aurora span:nth-child(3) { background: #0fa3a3; bottom: -130px; left: 38%; width: 280px; height: 280px; opacity: 0.5; }
  .hero-in { position: relative; z-index: 1; display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
  .hero h1 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  .date { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
  .stats { margin-top: 12px; display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); flex-wrap: wrap; }
  .stats .stat b { color: var(--text); font-weight: 700; }
  .stats .dot { color: var(--faint); }
  .clock { font-size: 46px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); line-height: 1; }

  .card { background: var(--surface); border: 1px solid var(--hairline); border-radius: calc(var(--radius) + 3px); padding: 16px 18px; box-shadow: var(--shadow-sm); }
  .card-h { display: flex; align-items: center; gap: 8px; font-size: 14px; margin-bottom: 12px; }
  .card-h .link { margin-left: auto; color: var(--accent); font-size: 12px; }
  .badge { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); font-weight: 600; }
  .muted { color: var(--muted); font-size: 13px; }

  /* Week strip */
  .weekgrid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; }
  .day { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 10px 4px 8px; border-radius: 10px; border: 1px solid var(--hairline); background: var(--bg); min-height: 78px; transition: border-color var(--t-fast) var(--ease), transform var(--t) var(--ease-spring); }
  .day:hover { border-color: var(--accent); transform: translateY(-1px); }
  .day.today { background: color-mix(in srgb, var(--accent) 12%, transparent); border-color: var(--accent); }
  .dname { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--faint); }
  .day.today .dname { color: var(--accent); font-weight: 700; }
  .dnum { font-size: 17px; font-weight: 700; }
  .dots { display: flex; flex-wrap: wrap; gap: 3px; justify-content: center; margin-top: 2px; min-height: 9px; }
  .dots .d { width: 7px; height: 7px; border-radius: 50%; }
  .dmore { font-size: 9px; color: var(--muted); line-height: 7px; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 880px) { .grid { grid-template-columns: 1fr; } }
  .events { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  .events li { --evc: var(--accent); display: flex; flex-direction: column; gap: 2px; padding-left: 11px; border-left: 3px solid var(--evc); }
  .events .when { font-size: 11px; color: var(--evc); font-weight: 600; }
  .events .summary { font-size: 13px; color: var(--text); font-weight: 550; }
  .events .loc { font-size: 11px; color: var(--muted); }
  .mails { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .mrow { display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 8px; border-radius: 8px; text-align: left; }
  .mrow:hover { background: var(--surface-2); }
  .av { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700; background: linear-gradient(135deg, var(--accent), #8a6df0); color: #fff; flex: none; }
  .who { font-size: 13px; font-weight: 600; color: var(--text); flex: none; max-width: 30%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mrow.unread .who { color: var(--accent); }
  .subj { font-size: 13px; color: var(--muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .t { font-size: 11px; color: var(--faint); flex: none; }
  .quick { display: flex; flex-wrap: wrap; gap: 10px; }
  .qbtn { display: inline-flex; align-items: center; gap: 7px; padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--hairline); background: var(--surface); font-size: 13px; color: var(--text); transition: border-color var(--t-fast) var(--ease), color var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .qbtn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
  .qbtn.rapl { margin-left: auto; color: var(--muted); }
</style>
