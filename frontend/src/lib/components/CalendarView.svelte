<script>
  import { onMount } from "svelte";
  import { calendar } from "../api.js";
  import { icons } from "../icons.js";

  let cursor = $state(new Date());   // any day within the visible month
  let events = $state([]);
  let selected = $state(new Date());
  let loading = $state(false);
  let scanning = $state(false);

  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

  async function load() {
    loading = true;
    const a = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const b = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0, 23, 59, 59);
    a.setDate(a.getDate() - 7); b.setDate(b.getDate() + 7);
    try { events = await calendar.list(a.toISOString(), b.toISOString()) || []; }
    catch { events = []; }
    finally { loading = false; }
  }
  async function scan() {
    scanning = true;
    try { await calendar.scan(150); await load(); } catch {} finally { scanning = false; }
  }
  onMount(async () => { await load(); scan(); });

  function prev() { cursor = new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1); load(); }
  function next() { cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1); load(); }
  function today() { const n = new Date(); cursor = new Date(n.getFullYear(), n.getMonth(), 1); selected = n; load(); }

  const weeks = $derived.by(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const startDow = (first.getDay() + 6) % 7; // Monday-first
    const gridStart = new Date(first); gridStart.setDate(1 - startDow);
    const cells = [];
    for (let i = 0; i < 42; i++) { const d = new Date(gridStart); d.setDate(gridStart.getDate() + i); cells.push(d); }
    return [0, 1, 2, 3, 4, 5].map((r) => cells.slice(r * 7, r * 7 + 7));
  });

  const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const isToday = (d) => sameDay(d, new Date());
  const inMonth = (d) => d.getMonth() === cursor.getMonth();
  function eventsOn(day) {
    return events.filter((e) => e.start && sameDay(new Date(e.start), day))
                 .sort((x, y) => new Date(x.start) - new Date(y.start));
  }
  const dayEvents = $derived(selected ? eventsOn(selected) : []);

  const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const fmtDayHeader = (d) => d ? d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }) : "";

  async function setRsvp(ev, status) {
    try { const u = await calendar.rsvp(ev.id, status); ev.status = u.status; events = [...events]; } catch {}
  }
  const STATUS_LABEL = { accepted: "Going", declined: "Declined", tentative: "Maybe", needsAction: "" };
</script>

<section class="cal">
  <header>
    <div class="nav">
      <button class="btn ghost" onclick={prev} title="Previous month">‹</button>
      <button class="btn ghost" onclick={today}>Today</button>
      <button class="btn ghost" onclick={next} title="Next month">›</button>
      <h2>{MONTHS[cursor.getMonth()]} {cursor.getFullYear()}</h2>
    </div>
    <button class="btn" onclick={scan} disabled={scanning}>
      {@html icons.sync} {scanning ? "Scanning invites…" : "Sync invites"}
    </button>
  </header>

  <div class="body">
    <div class="grid">
      <div class="dow">{#each DOW as d}<span>{d}</span>{/each}</div>
      {#each weeks as week}
        <div class="week">
          {#each week as day}
            {@const evs = eventsOn(day)}
            <button class="cell" class:dim={!inMonth(day)} class:today={isToday(day)} class:sel={sameDay(day, selected)}
              onclick={() => (selected = day)}>
              <span class="num">{day.getDate()}</span>
              <span class="evs">
                {#each evs.slice(0, 3) as e}
                  <span class="pill" class:cancelled={e.cancelled} class:accepted={e.status === "accepted"} class:declined={e.status === "declined"}>
                    {#if !e.all_day}<b>{fmtTime(e.start)}</b> {/if}{e.summary || "(untitled)"}
                  </span>
                {/each}
                {#if evs.length > 3}<span class="more">+{evs.length - 3} more</span>{/if}
              </span>
            </button>
          {/each}
        </div>
      {/each}
    </div>

    <aside class="agenda">
      <h3>{fmtDayHeader(selected)}</h3>
      {#if dayEvents.length === 0}
        <p class="empty">No events. {#if loading}Loading…{/if}</p>
      {:else}
        {#each dayEvents as e}
          <div class="event" class:cancelled={e.cancelled}>
            <div class="time">{e.all_day ? "All day" : `${fmtTime(e.start)}${e.end ? " – " + fmtTime(e.end) : ""}`}</div>
            <div class="title">{e.summary || "(untitled)"}{#if e.cancelled} <span class="cx">Cancelled</span>{/if}</div>
            {#if e.location}<div class="meta">{@html icons.inbox} {e.location}</div>{/if}
            {#if e.organizer}<div class="meta">{@html icons.accounts} {e.organizer}</div>{/if}
            {#if !e.cancelled}
              <div class="rsvp">
                <button class:on={e.status === "accepted"} onclick={() => setRsvp(e, "accepted")}>{@html icons.done} Yes</button>
                <button class:on={e.status === "tentative"} onclick={() => setRsvp(e, "tentative")}>Maybe</button>
                <button class:on={e.status === "declined"} onclick={() => setRsvp(e, "declined")}>{@html icons.close} No</button>
              </div>
            {/if}
          </div>
        {/each}
      {/if}
    </aside>
  </div>
</section>

<style>
  .cal { display: flex; flex-direction: column; min-width: 0; height: 100%; background: var(--bg); }
  header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--border); }
  .nav { display: flex; align-items: center; gap: 8px; }
  .nav h2 { margin: 0 0 0 8px; font-size: 18px; }
  .body { flex: 1; display: grid; grid-template-columns: 1fr 320px; min-height: 0; }
  .grid { display: flex; flex-direction: column; min-width: 0; padding: 10px; }
  .dow { display: grid; grid-template-columns: repeat(7, 1fr); padding: 0 2px 6px; }
  .dow span { font-size: 11px; color: var(--faint); text-transform: uppercase; letter-spacing: 0.04em; text-align: left; padding-left: 4px; }
  .week { display: grid; grid-template-columns: repeat(7, 1fr); flex: 1; }
  .cell { text-align: left; border: 1px solid var(--border); margin: -0.5px 0 0 -0.5px; padding: 4px 5px; display: flex; flex-direction: column; gap: 3px; min-height: 0; overflow: hidden; background: var(--bg); }
  .cell:hover { background: var(--surface); }
  .cell.dim { color: var(--faint); background: transparent; }
  .cell.dim .num { opacity: 0.4; }
  .cell.today .num { background: var(--accent); color: #fff; border-radius: 50%; }
  .cell.sel { box-shadow: inset 0 0 0 2px var(--accent); }
  .num { font-size: 12px; width: 22px; height: 22px; display: grid; place-items: center; font-weight: 600; }
  .evs { display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
  .pill { font-size: 11px; background: var(--surface-2); border-left: 3px solid var(--accent); padding: 1px 5px; border-radius: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pill.accepted { border-left-color: var(--done); }
  .pill.declined { border-left-color: var(--danger); opacity: 0.6; }
  .pill.cancelled { text-decoration: line-through; opacity: 0.5; }
  .pill b { font-weight: 600; }
  .more { font-size: 10px; color: var(--muted); padding-left: 4px; }

  .agenda { border-left: 1px solid var(--border); padding: 16px; overflow-y: auto; background: var(--surface); }
  .agenda h3 { margin: 0 0 12px; font-size: 15px; }
  .agenda .empty { color: var(--muted); font-size: 13px; }
  .event { padding: 10px 0; border-bottom: 1px solid var(--border); }
  .event.cancelled { opacity: 0.6; }
  .event .time { font-size: 12px; color: var(--accent); font-weight: 600; }
  .event .title { font-weight: 600; margin: 2px 0; }
  .event .cx { font-size: 11px; color: var(--danger); font-weight: 600; }
  .event .meta { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; margin-top: 2px; }
  .rsvp { display: flex; gap: 6px; margin-top: 8px; }
  .rsvp button { font-size: 12px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--border); color: var(--muted); display: inline-flex; align-items: center; gap: 4px; }
  .rsvp button:hover { border-color: var(--accent); color: var(--text); }
  .rsvp button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
