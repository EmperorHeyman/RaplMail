<script>
  import { onMount } from "svelte";
  import { app, notify, saveSettings } from "../store.svelte.js";
  import { calendar } from "../api.js";
  import { icons } from "../icons.js";

  let cursor = $state(new Date());   // any day within the visible month/week
  let events = $state([]);
  let selected = $state(new Date());
  let loading = $state(false);
  let scanning = $state(false);
  let view = $state(app.settings.calendarDefaultView === "week" ? "week" : "month");
  function setView(v) { view = v; saveSettings({ calendarDefaultView: v }); load(); }

  const _dpad = (n) => String(n).padStart(2, "0");
  const fmtDate = (d) => `${d.getFullYear()}-${_dpad(d.getMonth() + 1)}-${_dpad(d.getDate())}`;
  function weekStart(d) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() - ((x.getDay() + 6) % 7));  // Monday-first
    return x;
  }
  const weekDays = $derived.by(() => {
    const ws = weekStart(cursor);
    return Array.from({ length: 7 }, (_, i) => { const d = new Date(ws); d.setDate(ws.getDate() + i); return d; });
  });

  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

  let _loadGen = 0;   // latest-request-wins: clicking ‹ › quickly overlaps loads
  async function load() {
    const gen = ++_loadGen;
    loading = true;
    let a, b;
    if (view === "week") {
      const ws = weekStart(cursor);
      a = new Date(ws); a.setDate(a.getDate() - 1);
      b = new Date(ws); b.setDate(b.getDate() + 8); b.setHours(23, 59, 59);
    } else {
      a = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
      b = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0, 23, 59, 59);
      a.setDate(a.getDate() - 7); b.setDate(b.getDate() + 7);
    }
    try { const list = await calendar.list(a.toISOString(), b.toISOString()) || []; if (gen === _loadGen) events = list; }
    catch { if (gen === _loadGen) events = []; }
    finally { if (gen === _loadGen) loading = false; }
  }
  // "Sync" pulls BOTH mail-derived invites AND any configured calendar
  // subscriptions (ICS feeds / CalDAV) — otherwise a subscription added in
  // Settings would never show up here.
  async function scan() {
    scanning = true;
    const davConfigured = (app.settings.icsFeeds?.length > 0)
      || !!app.settings.caldavUrl || !!app.settings.carddavUrl;
    try {
      await Promise.all([
        calendar.scan(150).catch(() => {}),
        davConfigured ? calendar.caldavSync().catch(() => {}) : Promise.resolve(),
      ]);
    } finally {
      await load();
      scanning = false;
    }
  }
  let gcal = $state({ connected: false, email: "" });
  onMount(async () => {
    try { gcal = await calendar.googleStatus(); } catch {}
    await load(); scan();
  });

  // --- week time grid ------------------------------------------------------
  const HOURS = Array.from({ length: 24 }, (_, i) => i);
  const HOUR_H = 44;   // px per hour
  const timedOn = (day) => events.filter((e) => !e.all_day && !isMultiDay(e) && coversDay(e, day))
    .sort((a, b) => new Date(a.start) - new Date(b.start));
  const allDayOn = (day) => events.filter((e) => (e.all_day || isMultiDay(e)) && coversDay(e, day));
  function evTop(e) { const d = new Date(e.start); return (d.getHours() + d.getMinutes() / 60) * HOUR_H; }
  function evHeight(e) {
    const s = new Date(e.start); const en = e.end ? new Date(e.end) : new Date(s.getTime() + 3600000);
    let h = (en - s) / 3600000; if (!isFinite(h) || h <= 0) h = 1;
    return Math.max(22, h * HOUR_H);
  }
  let detailEv = $state(null);
  function openDetail(e) { detailEv = e; }
  function dblDay(day) { form = blankForm(day); creating = true; }
  function dblTime(day, ev) {
    const rect = ev.currentTarget.getBoundingClientRect();
    const hour = Math.max(0, Math.min(23, Math.floor((ev.clientY - rect.top) / HOUR_H)));
    form = blankForm(day);
    form.start = `${pad(hour)}:00`; form.end = `${pad(Math.min(23, hour + 1))}:00`; form.all_day = false;
    creating = true;
  }
  async function deleteEvent(e) {
    if (!e?.id || !confirm(`Delete "${e.summary || "(untitled)"}"?`)) return;
    try {
      const r = await calendar.remove(e.id);
      notify(r.google ? "Deleted from Google Calendar" : "Event deleted");
      await load();
    } catch (err) { notify(err.message || "Couldn't delete", "error"); }
  }

  // --- new event (iMIP) ----------------------------------------------------
  let creating = $state(false);
  let saving = $state(false);
  let form = $state(null);
  const pad = _dpad;
  function blankForm(d, endD, allDay) {
    const h = Math.min(23, new Date().getHours() + 1);
    return {
      summary: "", date: fmtDate(d), endDate: fmtDate(endD || d),
      start: `${pad(h)}:00`, end: `${pad(Math.min(23, h + 1))}:00`,
      all_day: !!allDay, location: "", description: "",
      account_id: app.accounts[0]?.id ?? null,
    };
  }
  function newEvent() { form = blankForm(selected || new Date()); creating = true; }
  function newEventRange(a, b) { form = blankForm(a, b, true); creating = true; }   // multi-day all-day
  async function saveEvent() {
    if (!form?.summary.trim() || !form.account_id) { notify("Add a title and pick an account", "error"); return; }
    saving = true;
    try {
      const startIso = form.all_day ? `${form.date}T00:00:00` : `${form.date}T${form.start}:00`;
      // All-day DTEND is EXCLUSIVE (the render side treats it that way): the
      // form's endDate is the last covered day, so send the day after it —
      // start==end made single-day all-day events invisible everywhere.
      let endIso;
      if (form.all_day) {
        const dayAfter = new Date(`${form.endDate || form.date}T00:00:00`);
        dayAfter.setDate(dayAfter.getDate() + 1);
        endIso = `${fmtDate(dayAfter)}T00:00:00`;
      } else {
        endIso = `${form.date}T${form.end}:00`;
      }
      const r = await calendar.create({
        account_id: form.account_id, summary: form.summary.trim(),
        start: new Date(startIso).toISOString(),
        end: new Date(endIso).toISOString(),
        all_day: form.all_day, location: form.location.trim(), description: form.description.trim(),
      });
      if (r.error) notify(r.error, "error");
      else if (r.google) notify("Added to your Google Calendar ✓");
      else notify(r.sent ? "Event created — accept the invite in your inbox to add it" : "Saved locally (invite couldn't be sent)");
      if (!r.error) creating = false;
      await load();
    } catch (e) { notify(e.message || "Couldn't create event", "error"); }
    finally { saving = false; }
  }

  function shift(dir) {
    if (view === "week") { const c = new Date(cursor); c.setDate(c.getDate() + dir * 7); cursor = c; }
    else cursor = new Date(cursor.getFullYear(), cursor.getMonth() + dir, 1);
    load();
  }
  function prev() { shift(-1); }
  function next() { shift(1); }
  function today() { const n = new Date(); cursor = n; selected = n; load(); }

  // --- drag to select a day range -> new multi-day event -------------------
  let drag = $state(null);   // { a: Date, b: Date }
  function dragDown(day) { drag = { a: day, b: day }; }
  function dragOver(day) { if (drag) drag = { a: drag.a, b: day }; }
  function dragUp() {
    const d = drag; drag = null;
    if (!d) return;
    const lo = dayKey(d.a) <= dayKey(d.b) ? d.a : d.b;
    const hi = dayKey(d.a) <= dayKey(d.b) ? d.b : d.a;
    if (dayKey(lo) !== dayKey(hi)) newEventRange(lo, hi);   // multi-day selection
  }
  function inDrag(day) {
    if (!drag) return false;
    const lo = Math.min(dayKey(drag.a), dayKey(drag.b)), hi = Math.max(dayKey(drag.a), dayKey(drag.b));
    return dayKey(day) >= lo && dayKey(day) <= hi;
  }

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
  const dayKey = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  // True if a (possibly multi-day) event covers `day`. All-day DTEND is exclusive.
  function coversDay(e, day) {
    if (!e.start) return false;
    const s = new Date(e.start);
    if (!e.end) return sameDay(s, day);
    let end = new Date(e.end);
    if (e.all_day) end = new Date(end.getTime() - 1); // exclusive end -> last covered day
    const d = dayKey(day);
    return d >= dayKey(s) && d <= dayKey(end);
  }
  const isMultiDay = (e) => e.all_day || (e.end && dayKey(new Date(e.start)) !== dayKey(new Date(e.end)));
  function eventsOn(day) {
    return events.filter((e) => coversDay(e, day))
      // Spanning / all-day bars first (like Google), then timed events by start.
      .sort((x, y) => (isMultiDay(y) - isMultiDay(x)) || (new Date(x.start) - new Date(y.start)));
  }
  const dayEvents = $derived(selected ? eventsOn(selected) : []);

  const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const fmtDayHeader = (d) => d ? d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }) : "";

  async function setRsvp(ev, status) {
    try { const u = await calendar.rsvp(ev.id, status); ev.status = u.status; events = [...events]; } catch {}
  }
  const STATUS_LABEL = { accepted: "Going", declined: "Declined", tentative: "Maybe", needsAction: "" };

  const title = $derived.by(() => {
    if (view === "week") {
      const f = weekDays[0], l = weekDays[6];
      const mf = MONTHS[f.getMonth()].slice(0, 3), ml = MONTHS[l.getMonth()].slice(0, 3);
      return f.getMonth() === l.getMonth()
        ? `${mf} ${f.getDate()} – ${l.getDate()}, ${f.getFullYear()}`
        : `${mf} ${f.getDate()} – ${ml} ${l.getDate()}`;
    }
    return `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`;
  });
</script>

<svelte:window onpointerup={dragUp} />

<section class="cal">
  <header>
    <div class="nav">
      <button class="btn ghost" onclick={prev} title={view === "week" ? "Previous week" : "Previous month"}>‹</button>
      <button class="btn ghost" onclick={today}>Today</button>
      <button class="btn ghost" onclick={next} title={view === "week" ? "Next week" : "Next month"}>›</button>
      <h2>{title}</h2>
    </div>
    <div class="hbtns">
      <div class="seg">
        <button class="segbtn" class:on={view === "month"} onclick={() => setView("month")}>Month</button>
        <button class="segbtn" class:on={view === "week"} onclick={() => setView("week")}>Week</button>
      </div>
      <button class="btn primary" onclick={newEvent} title="Create an event">＋ New event</button>
      <button class="btn" onclick={scan} disabled={scanning} title="Pull mail invites and refresh calendar subscriptions">
        {@html icons.sync} {scanning ? "Syncing…" : "Sync"}
      </button>
    </div>
  </header>

  {#if creating && form}
    <div class="modal-bg" onclick={() => (creating = false)}>
      <div class="modal" onclick={(e) => e.stopPropagation()}>
        <h3>New event</h3>
        <label class="fr"><span>Title</span><input bind:value={form.summary} placeholder="Dentist" /></label>
        <label class="fr"><span>{form.all_day ? "Start date" : "Date"}</span><input type="date" bind:value={form.date} /></label>
        {#if form.all_day}
          <label class="fr"><span>End date</span><input type="date" bind:value={form.endDate} min={form.date} /></label>
        {:else}
          <div class="fr"><span>Time</span>
            <div class="times"><input type="time" bind:value={form.start} /> – <input type="time" bind:value={form.end} /></div>
          </div>
        {/if}
        <label class="fr"><span>All day</span><input type="checkbox" bind:checked={form.all_day} /></label>
        <label class="fr"><span>Location</span><input bind:value={form.location} placeholder="optional" /></label>
        <label class="fr"><span>Notes</span><textarea rows="2" bind:value={form.description} placeholder="optional"></textarea></label>
        {#if gcal.connected}
          <div class="fr"><span>Calendar</span><span class="tgt">{@html icons.google || ""} {gcal.email || "Google Calendar"}</span></div>
        {:else if app.accounts.length > 1}
          <label class="fr"><span>Send via</span>
            <select bind:value={form.account_id}>
              {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
            </select>
          </label>
        {/if}
        <p class="modal-hint">{gcal.connected ? "Written straight to your Google Calendar." : "No Google Calendar connected — an invite is emailed to the chosen account's own inbox. Connect Google in Settings → Calendar for direct writes."}</p>
        <div class="modal-btns">
          <button class="btn ghost" onclick={() => (creating = false)}>Cancel</button>
          <button class="btn primary" onclick={saveEvent} disabled={saving}>{saving ? "Creating…" : "Create event"}</button>
        </div>
      </div>
    </div>
  {/if}

  {#if detailEv}
    <div class="modal-bg" onclick={() => (detailEv = null)}>
      <div class="modal" onclick={(e) => e.stopPropagation()}>
        <div class="d-top" style="--evc:{detailEv.color || 'var(--accent)'}">
          <span class="d-dot"></span>
          <h3>{detailEv.summary || "(untitled)"}{#if detailEv.cancelled} <span class="cx">Cancelled</span>{/if}</h3>
        </div>
        <p class="d-when">
          {#if detailEv.all_day || isMultiDay(detailEv)}
            {fmtDayHeader(new Date(detailEv.start))}{#if detailEv.end && dayKey(new Date(detailEv.start)) !== dayKey(new Date(new Date(detailEv.end).getTime() - 1))} – {fmtDayHeader(new Date(new Date(detailEv.end).getTime() - 1))}{/if} · all day
          {:else}
            {fmtDayHeader(new Date(detailEv.start))} · {fmtTime(detailEv.start)}{#if detailEv.end} – {fmtTime(detailEv.end)}{/if}
          {/if}
        </p>
        {#if detailEv.location}<p class="d-meta">{@html icons.inbox} {detailEv.location}</p>{/if}
        {#if detailEv.organizer}<p class="d-meta">{@html icons.accounts} {detailEv.organizer}</p>{/if}
        {#if detailEv.description}<p class="d-desc">{detailEv.description}</p>{/if}
        {#if !detailEv.cancelled && detailEv.organizer}
          <div class="rsvp">
            <button class:on={detailEv.status === "accepted"} onclick={() => setRsvp(detailEv, "accepted")}>{@html icons.done} Yes</button>
            <button class:on={detailEv.status === "tentative"} onclick={() => setRsvp(detailEv, "tentative")}>Maybe</button>
            <button class:on={detailEv.status === "declined"} onclick={() => setRsvp(detailEv, "declined")}>{@html icons.close} No</button>
          </div>
        {/if}
        <div class="modal-btns">
          <button class="btn danger" onclick={() => { const e = detailEv; detailEv = null; deleteEvent(e); }}>{@html icons.trash} Delete</button>
          <button class="btn primary" onclick={() => (detailEv = null)}>Close</button>
        </div>
      </div>
    </div>
  {/if}

  <div class="body">
    {#if view === "month"}
      <div class="grid">
        <div class="dow">{#each DOW as d}<span>{d}</span>{/each}</div>
        {#each weeks as week}
          <div class="week">
            {#each week as day}
              {@const evs = eventsOn(day)}
              <button class="cell" class:dim={!inMonth(day)} class:today={isToday(day)} class:sel={sameDay(day, selected)} class:indrag={inDrag(day)}
                onclick={(ev) => { const p = ev.target.closest?.("[data-evid]"); const hit = p && events.find((x) => String(x.id) === p.dataset.evid); if (hit) openDetail(hit); else selected = day; }}
                ondblclick={() => dblDay(day)}
                onpointerdown={() => dragDown(day)} onpointerenter={() => dragOver(day)}>
                <span class="num">{day.getDate()}</span>
                <span class="evs">
                  {#each evs.slice(0, 3) as e}
                    <span class="pill" data-evid={e.id} class:span={isMultiDay(e)} class:cancelled={e.cancelled} class:declined={e.status === "declined"}
                      style={e.color ? `--evc:${e.color}` : ""}>
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
    {:else}
      <div class="weekview">
        <div class="wg-header">
          <div class="wg-corner"></div>
          {#each weekDays as day}
            <button class="wg-dhead" class:today={isToday(day)} class:sel={sameDay(day, selected)} class:indrag={inDrag(day)}
              onclick={() => (selected = day)} ondblclick={() => dblDay(day)}
              onpointerdown={() => dragDown(day)} onpointerenter={() => dragOver(day)}>
              <span class="wdow">{DOW[(day.getDay() + 6) % 7]}</span>
              <span class="wnum" class:istoday={isToday(day)}>{day.getDate()}</span>
            </button>
          {/each}
        </div>
        <div class="wg-scroll">
          <div class="wg-allday">
            <div class="wg-rowlabel">all-day</div>
            {#each weekDays as day}
              <div class="wg-allcell" class:indrag={inDrag(day)} ondblclick={() => dblDay(day)}
                onpointerdown={() => dragDown(day)} onpointerenter={() => dragOver(day)}>
                {#each allDayOn(day) as e}
                  <button class="pill span" style="--evc:{e.color || 'var(--accent)'}" onclick={(ev) => { ev.stopPropagation(); openDetail(e); }}>{e.summary || "(untitled)"}</button>
                {/each}
              </div>
            {/each}
          </div>
          <div class="wg-grid">
            <div class="wg-gutter">
              {#each HOURS as h}<div class="wg-hr" style="height:{HOUR_H}px">{pad(h)}:00</div>{/each}
            </div>
            {#each weekDays as day}
              <div class="wg-daycol" style="height:{HOUR_H * 24}px; --hh:{HOUR_H}px" ondblclick={(ev) => dblTime(day, ev)}>
                {#each timedOn(day) as e}
                  <button class="wg-ev" class:cancelled={e.cancelled} style="top:{evTop(e)}px; height:{evHeight(e)}px; --evc:{e.color || 'var(--accent)'}"
                    onclick={(ev) => { ev.stopPropagation(); openDetail(e); }}>
                    <b>{fmtTime(e.start)}</b> {e.summary || "(untitled)"}
                  </button>
                {/each}
              </div>
            {/each}
          </div>
        </div>
      </div>
    {/if}

    <aside class="agenda">
      <h3>{fmtDayHeader(selected)}</h3>
      {#if dayEvents.length === 0}
        <p class="empty">No events. {#if loading}Loading…{/if}</p>
      {:else}
        {#each dayEvents as e}
          <div class="event" class:cancelled={e.cancelled} style={e.color ? `--evc:${e.color}` : ""}>
            <div class="time"><span class="dot"></span>{e.all_day ? "All day" : `${fmtTime(e.start)}${e.end ? " – " + fmtTime(e.end) : ""}`}
              <button class="del" title="Delete event" onclick={() => deleteEvent(e)}>{@html icons.trash}</button>
            </div>
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
  .hbtns { display: flex; gap: 8px; align-items: center; }
  .seg { display: inline-flex; gap: 3px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 3px; }
  .segbtn { font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 999px; color: var(--muted); }
  .segbtn:hover { color: var(--text); }
  .segbtn.on { background: var(--accent); color: #fff; }
  .cell.indrag, .wg-dhead.indrag, .wg-allcell.indrag { background: color-mix(in srgb, var(--accent) 22%, transparent); box-shadow: inset 0 0 0 1px var(--accent); }
  .tgt { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text); }
  .event .del { margin-left: auto; color: var(--faint); font-size: 12px; opacity: 0; transition: opacity 0.1s; }
  .event:hover .del { opacity: 1; }
  .event .del:hover { color: var(--danger); }

  /* Week view: Google-style time grid (hour rows + day columns). */
  .weekview { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .wg-header { display: grid; grid-template-columns: 56px repeat(7, 1fr); border-bottom: 1px solid var(--border); }
  .wg-corner { border-right: 1px solid var(--border); }
  .wg-dhead { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 7px 2px 5px; border-left: 1px solid var(--border); background: var(--bg); }
  .wg-dhead:hover { background: var(--surface); }
  .wg-dhead.today { background: color-mix(in srgb, var(--accent) 8%, transparent); }
  .wg-dhead.sel { box-shadow: inset 0 -2px 0 var(--accent); }
  .wdow { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--faint); }
  .wnum { font-size: 17px; font-weight: 700; width: 28px; height: 28px; display: grid; place-items: center; }
  .wnum.istoday { background: var(--accent); color: #fff; border-radius: 50%; }
  .wg-scroll { flex: 1; overflow-y: auto; min-height: 0; }
  .wg-allday { display: grid; grid-template-columns: 56px repeat(7, 1fr); border-bottom: 1px solid var(--border); min-height: 26px; }
  .wg-rowlabel { font-size: 9px; color: var(--faint); text-align: right; padding: 4px 6px 0 0; text-transform: uppercase; }
  .wg-allcell { border-left: 1px solid var(--border); padding: 3px; display: flex; flex-direction: column; gap: 2px; }
  .wg-grid { display: grid; grid-template-columns: 56px repeat(7, 1fr); position: relative; }
  .wg-gutter { position: relative; }
  .wg-hr { font-size: 10px; color: var(--faint); text-align: right; padding: 0 6px; box-sizing: border-box; transform: translateY(-6px); }
  .wg-daycol { position: relative; border-left: 1px solid var(--border);
    background-image: repeating-linear-gradient(to bottom, transparent 0, transparent calc(var(--hh) - 1px), var(--border) calc(var(--hh) - 1px), var(--border) var(--hh)); }
  .wg-daycol:hover { background-color: color-mix(in srgb, var(--surface) 40%, transparent); }
  .wg-ev { position: absolute; left: 2px; right: 2px; overflow: hidden; text-align: left;
    background: color-mix(in srgb, var(--evc) 22%, var(--surface)); border-left: 3px solid var(--evc);
    border-radius: 4px; padding: 2px 5px; font-size: 11px; line-height: 1.25; color: var(--text); }
  .wg-ev b { color: var(--evc); }
  .wg-ev.cancelled { text-decoration: line-through; opacity: 0.5; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 200; display: grid; place-items: center; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 22px; width: 420px; max-width: 92vw; box-shadow: var(--shadow); }
  .modal h3 { margin: 0 0 14px; }
  .modal .fr { display: flex; align-items: center; gap: 10px; margin: 9px 0; }
  .modal .fr > span { width: 78px; flex: none; color: var(--muted); font-size: 13px; }
  .modal .fr input[type=text], .modal .fr input:not([type]), .modal .fr input[type=date], .modal .fr input[type=time], .modal .fr select, .modal .fr textarea { flex: 1; }
  .modal .times { flex: 1; display: flex; align-items: center; gap: 8px; }
  .modal-hint { color: var(--muted); font-size: 12px; line-height: 1.5; margin: 12px 0 6px; }
  .modal-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
  .modal-btns .btn.danger { margin-right: auto; color: var(--danger); }
  .modal-btns .btn.danger:hover { background: var(--danger); color: #fff; }
  .d-top { display: flex; align-items: center; gap: 9px; margin-bottom: 8px; }
  .d-top h3 { margin: 0; }
  .d-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--evc); flex: none; }
  .d-when { color: var(--accent); font-weight: 600; font-size: 13px; margin: 0 0 10px; }
  .d-meta { color: var(--muted); font-size: 13px; display: flex; align-items: center; gap: 6px; margin: 4px 0; }
  .d-desc { font-size: 13px; line-height: 1.5; white-space: pre-wrap; margin: 10px 0; color: var(--text); max-height: 240px; overflow-y: auto; }
  .cx { font-size: 11px; color: var(--danger); font-weight: 600; }
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
  .pill { --evc: var(--accent); font-size: 11px; background: var(--surface-2); border-left: 3px solid var(--evc); padding: 1px 5px; border-radius: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  /* Multi-day / all-day events read as a solid colored bar, like Google. */
  .pill.span { background: color-mix(in srgb, var(--evc) 80%, transparent); border-left: none; color: #fff; font-weight: 600; }
  .pill.declined { opacity: 0.55; }
  .pill.cancelled { text-decoration: line-through; opacity: 0.5; }
  .pill b { font-weight: 600; color: var(--evc); }
  .pill.span b { color: inherit; }
  .more { font-size: 10px; color: var(--muted); padding-left: 4px; }

  .agenda { border-left: 1px solid var(--border); padding: 16px; overflow-y: auto; background: var(--surface); }
  .agenda h3 { margin: 0 0 12px; font-size: 15px; }
  .agenda .empty { color: var(--muted); font-size: 13px; }
  .event { --evc: var(--accent); padding: 10px 0; border-bottom: 1px solid var(--border); }
  .event.cancelled { opacity: 0.6; }
  .event .time { font-size: 12px; color: var(--evc); font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .event .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--evc); flex: none; }
  .event .title { font-weight: 600; margin: 2px 0; }
  .event .cx { font-size: 11px; color: var(--danger); font-weight: 600; }
  .event .meta { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; margin-top: 2px; }
  .rsvp { display: flex; gap: 6px; margin-top: 8px; }
  .rsvp button { font-size: 12px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--border); color: var(--muted); display: inline-flex; align-items: center; gap: 4px; }
  .rsvp button:hover { border-color: var(--accent); color: var(--text); }
  .rsvp button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
