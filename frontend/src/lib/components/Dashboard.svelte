<script>
  import { onMount, onDestroy } from "svelte";
  import { app, openMessageById, selectSmartInbox, selectUnifiedInbox, openCompose } from "../store.svelte.js";
  import { messages as msgApi, calendar as calApi } from "../api.js";
  import { listTime, relativeTime } from "../time.js";
  import { icons } from "../icons.js";

  // --- live clock ----------------------------------------------------------
  let now = $state(new Date());
  let timer;
  onMount(() => { timer = setInterval(() => (now = new Date()), 1000); load(); });
  onDestroy(() => clearInterval(timer));

  const greeting = $derived.by(() => {
    const h = now.getHours();
    return h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  });
  const clock = $derived(now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  const dateStr = $derived(now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }));
  const firstName = $derived((app.accounts[0]?.display_name || app.accounts[0]?.email || "").split(/[ @]/)[0]);

  // --- data ----------------------------------------------------------------
  let recent = $state([]);
  let events = $state([]);
  let unread = $state(0);
  let loading = $state(true);

  async function load() {
    loading = true;
    try {
      const rows = await msgApi.list({ role: "inbox", limit: 6 });
      recent = Array.isArray(rows) ? rows : (rows.items || []);
      unread = recent.filter((m) => !m.is_seen).length;
    } catch {}
    try {
      const start = new Date(now); start.setHours(0, 0, 0, 0);
      const end = new Date(start); end.setDate(end.getDate() + 14);
      const evs = await calApi.list(start.toISOString(), end.toISOString());
      events = (Array.isArray(evs) ? evs : []).filter((e) => e.start).slice(0, 6);
    } catch {}
    loading = false;
  }

  function openMail(m) { openMessageById(m.id); }
  function goInbox() { app.view = "mail"; if (app.settings.smartInbox) selectSmartInbox(); else selectUnifiedInbox(); }
  const initial = (s) => (s || "?").trim()[0]?.toUpperCase() || "?";
  function evWhen(iso) {
    const d = new Date(iso);
    const today = new Date(now); today.setHours(0, 0, 0, 0);
    const day = new Date(d); day.setHours(0, 0, 0, 0);
    const diff = Math.round((day - today) / 86400000);
    const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff === 0) return `Today · ${t}`;
    if (diff === 1) return `Tomorrow · ${t}`;
    return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + ` · ${t}`;
  }
</script>

<section class="dash">
  <header class="hero">
    <div>
      <h1>{greeting}{firstName ? `, ${firstName}` : ""}</h1>
      <p class="date">{dateStr}</p>
    </div>
    <div class="clock">{clock}</div>
  </header>

  <div class="grid">
    <!-- Up next: calendar -->
    <section class="card cal">
      <div class="card-h">{@html icons.calendar} <b>Up next</b>
        <button class="link" onclick={() => (app.view = "calendar")}>Calendar →</button>
      </div>
      {#if loading}
        <p class="muted">Loading…</p>
      {:else if events.length}
        <ul class="events">
          {#each events as e}
            <li>
              <span class="when">{evWhen(e.start)}</span>
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
  .dash { flex: 1; overflow-y: auto; padding: 30px 34px; display: flex; flex-direction: column; gap: 24px; min-width: 0; }
  .hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
  .hero h1 { margin: 0; font-size: 28px; }
  .date { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
  .clock { font-size: 46px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--accent); line-height: 1; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 880px) { .grid { grid-template-columns: 1fr; } }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; }
  .card-h { display: flex; align-items: center; gap: 8px; font-size: 14px; margin-bottom: 12px; }
  .card-h .link { margin-left: auto; color: var(--accent); font-size: 12px; }
  .badge { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); font-weight: 600; }
  .muted { color: var(--muted); font-size: 13px; }
  .events { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  .events li { display: flex; flex-direction: column; gap: 2px; padding-left: 11px; border-left: 2px solid var(--accent); }
  .events .when { font-size: 11px; color: var(--accent); font-weight: 600; }
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
  .qbtn { display: inline-flex; align-items: center; gap: 7px; padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); font-size: 13px; color: var(--text); }
  .qbtn:hover { border-color: var(--accent); color: var(--accent); }
  .qbtn.rapl { margin-left: auto; color: var(--muted); }
</style>
