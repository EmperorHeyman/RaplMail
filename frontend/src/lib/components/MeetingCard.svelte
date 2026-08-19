<script>
  // "When is this meeting?" card for calendar mail.
  //
  // Exchange/M365 strips the iCalendar part out of invitations, updates and
  // cancellations sent to IMAP mailboxes and leaves only an Outlook Web link, so
  // the body itself never says when the meeting is. The backend recovers the time
  // (from the mail's own ics, else by matching the local calendar - see
  // app/sync/meeting.py) and this renders it above the body.
  //
  // A time matched from the calendar is an inference, not something the mail
  // stated, so it is always labelled as such - never presented as fact.
  import { app } from "../store.svelte.js";
  import { openExternal } from "../api.js";
  import { icons } from "../icons.js";
  import { t, currentLocale } from "../i18n.svelte.js";

  let { meeting, subject = "" } = $props();

  const loc = $derived(currentLocale());
  const start = $derived(meeting?.start ? new Date(meeting.start) : null);
  const end = $derived(meeting?.end ? new Date(meeting.end) : null);
  const cancelled = $derived(meeting?.kind === "cancel");
  const title = $derived(meeting?.summary || subject || "");

  const KIND_KEY = { invite: "reader.meetInvite", update: "reader.meetUpdate",
                     cancel: "reader.meetCancel", reply: "reader.meetReply" };

  const fmt = (d, o) => d.toLocaleString(loc, o);
  const sameDay = $derived(!!(start && end) && start.toDateString() === end.toDateString());

  // "Friday 21 August · 11:00 - 12:00" - weekday first, because the question the
  // card answers is "which day?" before "which hour?".
  const whenText = $derived.by(() => {
    if (!start) return "";
    const day = fmt(start, { weekday: "long", day: "numeric", month: "long" });
    if (meeting.all_day) {
      if (end && !sameDay) return `${day} - ${fmt(end, { day: "numeric", month: "long" })}`;
      return `${day} · ${t("reader.meetAllDay")}`;
    }
    const from = fmt(start, { hour: "2-digit", minute: "2-digit", hour12: false });
    if (!end) return `${day} · ${from}`;
    const to = fmt(end, { hour: "2-digit", minute: "2-digit", hour12: false });
    return sameDay ? `${day} · ${from} - ${to}`
                   : `${day} ${from} - ${fmt(end, { weekday: "long", day: "numeric", month: "long" })} ${to}`;
  });

  // "in 2 days" / "3 hours ago", localized via Intl so cs gets "za 2 dny".
  const relText = $derived.by(() => {
    if (!start) return "";
    const secs = (start.getTime() - Date.now()) / 1000;
    try {
      const rtf = new Intl.RelativeTimeFormat(loc, { numeric: "auto" });
      if (Math.abs(secs) >= 86400) return rtf.format(Math.round(secs / 86400), "day");
      if (Math.abs(secs) >= 3600) return rtf.format(Math.round(secs / 3600), "hour");
      return rtf.format(Math.round(secs / 60), "minute");
    } catch {
      return "";
    }
  });

  const chipMonth = $derived(start ? fmt(start, { month: "short" }).replace(".", "") : "");
  const chipDay = $derived(start ? fmt(start, { day: "numeric" }) : "");

  function showInCalendar() {
    app.calendarFocus = meeting.start;   // CalendarView jumps to this day on mount
    app.view = "calendar";
  }
</script>

{#if meeting}
  <div class="meet" class:cancelled class:noTime={!start}>
    {#if start}
      <div class="chip" aria-hidden="true">
        <span class="chip-m">{chipMonth}</span>
        <span class="chip-d">{chipDay}</span>
      </div>
    {:else}
      <div class="chip empty" aria-hidden="true">{@html icons.calendar}</div>
    {/if}

    <div class="info">
      <div class="kind">
        {t(KIND_KEY[meeting.kind] || "reader.meetInvite")}
        {#if meeting.source === "calendar"}
          <span class="tag" title={t("reader.meetFromCalendarWhy")}>{t("reader.meetFromCalendar")}</span>
        {/if}
      </div>

      {#if start}
        <div class="when">{whenText}</div>
        {#if relText}<span class="rel">{relText}</span>{/if}
      {:else}
        <div class="when muted">{t("reader.meetNoTime")}</div>
      {/if}

      {#if title}<div class="title" class:strike={cancelled}>{title}</div>{/if}

      <div class="meta">
        {#if meeting.location}<span>{@html icons.pin} {meeting.location}</span>{/if}
        {#if meeting.organizer}<span>{@html icons.accounts} {meeting.organizer}</span>{/if}
        {#if meeting.occurrences > 1}
          <span title={t("reader.meetRecurringWhy")}>{@html icons.sync} {t("reader.meetRecurring")}</span>
        {/if}
      </div>

      {#if meeting.link_only}
        <div class="hint">{t("reader.meetLinkOnly")}</div>
      {/if}
    </div>

    <div class="acts">
      {#if meeting.event_id}
        <button class="mact" onclick={showInCalendar}>{@html icons.calendar} {t("reader.meetShowInCalendar")}</button>
      {/if}
      {#if meeting.owa_url}
        <button class="mact" onclick={() => openExternal(meeting.owa_url)}>{@html icons.link} {t("reader.meetOpenInOutlook")}</button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .meet {
    display: flex; align-items: flex-start; gap: 14px;
    margin: 10px 16px; padding: 12px 14px;
    border: 1px solid var(--border); border-left: 3px solid var(--accent);
    border-radius: var(--radius); background: var(--surface);
  }
  .meet.cancelled { border-left-color: var(--danger); }
  .meet.noTime { border-left-color: var(--warning); }

  .chip {
    flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center;
    width: 52px; padding: 6px 0; border-radius: var(--radius-sm);
    background: var(--accent-soft); color: var(--accent);
  }
  .cancelled .chip { background: var(--danger-soft); color: var(--danger); }
  .chip-m { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  .chip-d { font-size: 22px; font-weight: 700; line-height: 1.1; }
  .chip.empty { background: var(--warning-soft); color: var(--warning); min-height: 46px; }
  .chip.empty :global(svg) { width: 20px; height: 20px; }

  .info { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .kind {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--accent); display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .cancelled .kind { color: var(--danger); }
  .noTime .kind { color: var(--warning); }
  .tag {
    font-size: 10px; font-weight: 600; text-transform: none; letter-spacing: 0;
    color: var(--muted); border: 1px solid var(--hairline); border-radius: 999px; padding: 1px 7px;
  }
  .when { font-size: 15px; font-weight: 600; color: var(--text); }
  .when.muted { font-weight: 500; color: var(--muted); }
  .rel { font-size: 12px; color: var(--muted); }
  .title { font-size: 13px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .title.strike { text-decoration: line-through; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 4px; font-size: 12px; color: var(--muted); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta :global(svg) { width: 13px; height: 13px; flex: none; }
  .hint { margin-top: 6px; font-size: 11.5px; color: var(--faint); line-height: 1.4; }

  .acts { flex: none; display: flex; flex-direction: column; gap: 6px; }
  .mact {
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
    padding: 5px 10px; font-size: 12px; color: var(--text);
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
    cursor: pointer; transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease);
  }
  .mact:hover { border-color: var(--accent); background: var(--surface-3); }
  .mact :global(svg) { width: 14px; height: 14px; }

  @media (max-width: 720px) {
    .meet { flex-wrap: wrap; }
    .acts { flex-direction: row; width: 100%; }
  }
</style>
