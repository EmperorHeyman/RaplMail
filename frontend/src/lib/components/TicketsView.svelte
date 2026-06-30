<script>
  import { onMount } from "svelte";
  import { app, notify } from "../store.svelte.js";
  import { rapldesk } from "../api.js";
  import { icons } from "../icons.js";

  let instances = $state([]);
  let instanceId = $state(null);
  let tab = $state("list");           // list | detail | new
  let loading = $state(false);
  let err = $state("");

  // list
  let tickets = $state([]);
  let pagination = $state({ page: 1, total_pages: 1, total: 0 });
  let fStatus = $state("");
  let fPriority = $state("");
  let search = $state("");
  let page = $state(1);
  let stats = $state(null);
  let me = $state(null);              // GET /me (the key's identity), when available
  let listTab = $state("all");        // all | mine | created | unassigned | department
  let counts = $state(null);          // GET /tickets/counts → tab badges
  const myId = $derived(me?.id ?? app.settings.raplDeskUserId ?? null);
  const TABS = [
    { id: "all", label: "All" },
    { id: "mine", label: "My tickets" },
    { id: "department", label: "My dept" },
    { id: "unassigned", label: "Unassigned" },
    { id: "created", label: "Created" },
  ];

  // detail
  let ticket = $state(null);
  let replies = $state([]);
  let replyText = $state("");
  let replyInternal = $state(false);
  let sending = $state(false);

  // new
  let firms = $state([]);
  let departments = $state([]);
  let users = $state([]);
  let nf = $state(null);
  let creating = $state(false);

  const STATUSES = ["open", "assigned", "in_progress", "on_hold", "closed"];
  const PRIORITIES = ["low", "normal", "high", "critical"];
  const inst = $derived(instances.find((i) => i.id === instanceId) || null);

  onMount(async () => {
    try {
      const r = await rapldesk.instances();
      instances = r.instances || [];
      const connected = instances.find((i) => i.connected) || instances[0];
      if (connected) { instanceId = connected.id; await fetchMe(); await loadList(); loadStats(); loadCounts(); }
    } catch (e) { err = e.message; }
  });

  // Identity from the API key (lights up the "my" tabs without a manual id).
  // Degrades gracefully if the instance doesn't implement GET /me yet.
  async function fetchMe() {
    try { me = (await rd("GET", "me")).user || null; } catch { me = null; }
  }

  // Unwrap the {http, data:{status,data}} envelope; throw a useful error.
  async function rd(method, endpoint, query = {}, body = null) {
    const r = await rapldesk.call(instanceId, { method, endpoint, query, body });
    if (r.http === 401 || r.http === 403) throw new Error(`Not allowed (${r.http}) — this API key is missing the required scope.`);
    if (r.http === 404) throw new Error(`404 Not Found — check the instance Base URL. Called: ${r.url || "?"}`);
    if (r.http >= 400) throw new Error(r.data?.message || `HTTP ${r.http} (${r.url || ""})`);
    if (r.data?.status === "error") throw new Error(r.data.message || "RaplDesk error");
    return r.data?.data ?? r.data;
  }

  async function selectInstance(id) { instanceId = id; tab = "list"; page = 1; me = null; await fetchMe(); await loadList(); loadStats(); loadCounts(); }

  function setTab(t) { listTab = t; page = 1; loadList(); }

  async function loadList() {
    if (!instanceId) return;
    loading = true; err = "";
    try {
      const q = { page, per_page: 25 };
      if (fStatus) q.status = fStatus;
      if (fPriority) q.priority = fPriority;
      if (search.trim()) q.search = search.trim();
      // v2 resolves these against the key's bound user (GET /me) — no ids needed.
      if (listTab !== "all") q.scope = listTab;
      const d = await rd("GET", "tickets", q);
      tickets = d.tickets || [];
      pagination = d.pagination || { page: 1, total_pages: 1, total: tickets.length };
    } catch (e) { err = e.message; tickets = []; }
    finally { loading = false; }
  }
  async function loadStats() {
    try { stats = await rd("GET", "stats/overview"); } catch { stats = null; }
  }
  async function loadCounts() {
    try { counts = await rd("GET", "tickets/counts"); } catch { counts = null; }
  }
  const tabCount = (id) => (id === "all" ? counts?.all : counts?.[id]);

  async function openTicket(t) {
    tab = "detail"; ticket = null; replies = []; loading = true; err = "";
    try {
      const d = await rd("GET", `tickets/${t.id}`);
      ticket = d.ticket || d;
      const rr = await rd("GET", `tickets/${t.id}/replies`);
      replies = rr.replies || [];
    } catch (e) { err = e.message; }
    finally { loading = false; }
  }

  function myUserId() {
    // Prefer the key's real identity (GET /me); fall back to the manually-set id.
    return me?.id || app.settings.raplDeskUserId || ticket?.assigned_to_user_id || ticket?.created_by_user_id || null;
  }
  async function sendReply() {
    if (!replyText.trim()) return;
    // v2 accepts "me" (bound key); fall back to a manual id only if /me is absent.
    const uid = me ? "me" : myUserId();
    if (!uid) { notify("Set your RaplDesk user id in Settings → RAPL Desk first", "error"); return; }
    sending = true;
    try {
      await rd("POST", `tickets/${ticket.id}/replies`, {}, {
        message: replyText.trim(), user_id: uid, is_internal_note: replyInternal ? 1 : 0,
      });
      replyText = ""; replyInternal = false;
      const rr = await rd("GET", `tickets/${ticket.id}/replies`);
      replies = rr.replies || [];
      notify("Reply posted");
    } catch (e) { notify(e.message, "error"); }
    finally { sending = false; }
  }
  async function setField(field, value) {
    try {
      await rd("PUT", `tickets/${ticket.id}`, {}, { [field]: value });
      ticket = { ...ticket, [field]: value };
      notify(`Ticket ${field} → ${value}`);
      loadStats();
    } catch (e) { notify(e.message, "error"); }
  }

  async function startNew() {
    tab = "new";
    // v2 defaults firm + creator to the bound user, so these are pre-filled / optional.
    nf = { title: "", description: "", firm_id: me?.firm_id || "", priority: "normal",
           department_id: "", created_by_user_id: me ? "me" : (app.settings.raplDeskUserId || ""),
           assign_me: true };
    try { firms = (await rd("GET", "firms")).firms || []; } catch { firms = []; }
    try { departments = (await rd("GET", "departments")).departments || []; } catch { departments = []; }
    try { users = (await rd("GET", "users", { per_page: 100 })).users || []; } catch { users = []; }
  }
  async function createTicket() {
    if (!nf.title.trim() || !nf.description.trim()) { notify("Title and description are required", "error"); return; }
    if (!me && (!nf.firm_id || !nf.created_by_user_id)) { notify("Firm and 'created by' user are required", "error"); return; }
    creating = true;
    try {
      const body = { title: nf.title.trim(), description: nf.description.trim(), priority: nf.priority };
      if (nf.firm_id) body.firm_id = Number(nf.firm_id);
      body.created_by_user_id = nf.created_by_user_id === "me" ? "me" : Number(nf.created_by_user_id);
      if (nf.assign_me) body.assigned_to_user_id = "me";
      if (nf.department_id) body.department_id = Number(nf.department_id);
      const d = await rd("POST", "tickets", {}, body);
      notify("Ticket created");
      tab = "list"; page = 1; await loadList(); loadStats(); loadCounts();
    } catch (e) { notify(e.message, "error"); }
    finally { creating = false; }
  }

  const fmt = (s) => (s ? s.replace("T", " ").slice(0, 16) : "");
  const prioClass = (p) => `p-${p || "normal"}`;
</script>

<section class="tickets">
  <header>
    <div class="htop">
      <h2>{@html icons.receipt || ""} Tickets</h2>
      {#if instances.length > 1}
        <select class="inst" bind:value={instanceId} onchange={() => selectInstance(instanceId)}>
          {#each instances as i}<option value={i.id}>{i.name}</option>{/each}
        </select>
      {/if}
      <div class="hspace"></div>
      {#if stats}
        <div class="stats">
          <span><b>{stats.total ?? stats.total_tickets ?? "—"}</b> total</span>
          <span class="ok"><b>{stats.open ?? "—"}</b> open</span>
          <span class="muted"><b>{stats.closed ?? "—"}</b> closed</span>
        </div>
      {/if}
      <button class="btn" onclick={loadList} disabled={loading} title="Refresh">{@html icons.sync}</button>
      <button class="btn primary" onclick={startNew}>＋ New ticket</button>
    </div>
    {#if tab === "list"}
      <div class="tabbar">
        {#each TABS as t}
          <button class="tab" class:on={listTab === t.id} onclick={() => setTab(t.id)}>
            {t.label}{#if tabCount(t.id) != null}<span class="cnt">{tabCount(t.id)}</span>{/if}
          </button>
        {/each}
        {#if me}<span class="who" title="Signed in via this API key">· {me.name}</span>{/if}
      </div>
      <div class="filters">
        <input class="search" placeholder="Search tickets…" bind:value={search}
          onkeydown={(e) => e.key === "Enter" && (page = 1, loadList())} />
        <select bind:value={fStatus} onchange={() => (page = 1, loadList())}>
          <option value="">Any status</option>{#each STATUSES as s}<option value={s}>{s}</option>{/each}
        </select>
        <select bind:value={fPriority} onchange={() => (page = 1, loadList())}>
          <option value="">Any priority</option>{#each PRIORITIES as p}<option value={p}>{p}</option>{/each}
        </select>
      </div>
      {#if (listTab === "mine" || listTab === "created") && !myId}
        <p class="tabhint">Set your RaplDesk user id in <b>Settings → RAPL Desk</b> (or add <code>GET /me</code> to the API) to use this tab.</p>
      {/if}
    {/if}
  </header>

  {#if instances.length === 0}
    <div class="empty">
      <div class="big">{@html icons.receipt || ""}</div>
      <p>No RAPL Desk connected.</p>
      <button class="btn primary" onclick={() => { app.view = "settings"; app.settingsTab = "rapldesk"; }}>Connect in Settings → RAPL Desk</button>
    </div>
  {:else if err && tab === "list" && tickets.length === 0}
    <div class="empty"><div class="big">⚠</div><p>{err}</p></div>
  {:else if tab === "list"}
    <div class="list">
      {#if loading}<p class="muted pad">Loading…</p>{/if}
      {#each tickets as t}
        <button class="trow" class:unread={t.unread} onclick={() => openTicket(t)}>
          {#if t.unread}<span class="udot" title="Unread"></span>{/if}
          <span class="pri {prioClass(t.priority)}" title={t.priority}></span>
          <span class="tmain">
            <span class="ttitle">#{t.id} · {t.title}</span>
            <span class="tmeta">{t.firm_name || ""}{t.department_name ? " · " + t.department_name : ""}{t.assigned_to_name ? " · " + t.assigned_to_name : " · unassigned"}</span>
          </span>
          <span class="tright">
            {#if t.is_overdue}<span class="badge overdue" title="Past deadline">overdue</span>{/if}
            <span class="badge st-{t.status}">{t.status}</span>
            {#if t.reply_count}<span class="rc">{@html icons.chat} {t.reply_count}</span>{/if}
            <span class="tdate">{fmt(t.last_reply_at || t.created_at)}</span>
          </span>
        </button>
      {/each}
      {#if !loading && tickets.length === 0}<p class="muted pad">No tickets match.</p>{/if}
      {#if pagination.total_pages > 1}
        <div class="pager">
          <button class="btn ghost" disabled={page <= 1} onclick={() => (page--, loadList())}>‹ Prev</button>
          <span>Page {pagination.page} / {pagination.total_pages} · {pagination.total} total</span>
          <button class="btn ghost" disabled={page >= pagination.total_pages} onclick={() => (page++, loadList())}>Next ›</button>
        </div>
      {/if}
    </div>
  {:else if tab === "detail"}
    <div class="detail">
      <button class="back" onclick={() => { tab = "list"; }}>‹ All tickets</button>
      {#if loading}<p class="muted pad">Loading…</p>{/if}
      {#if ticket}
        <div class="d-head">
          <h3><span class="pri {prioClass(ticket.priority)}"></span>#{ticket.id} · {ticket.title}</h3>
          <div class="d-controls">
            <label>Status
              <select value={ticket.status} onchange={(e) => setField("status", e.currentTarget.value)}>
                {#each STATUSES as s}<option value={s}>{s}</option>{/each}
              </select>
            </label>
            <label>Priority
              <select value={ticket.priority} onchange={(e) => setField("priority", e.currentTarget.value)}>
                {#each PRIORITIES as p}<option value={p}>{p}</option>{/each}
              </select>
            </label>
          </div>
        </div>
        <div class="d-meta">{ticket.firm_name || ""}{ticket.department_name ? " · " + ticket.department_name : ""}{ticket.created_by_name ? " · by " + ticket.created_by_name : ""}</div>
        {#if ticket.description}<div class="d-desc">{ticket.description}</div>{/if}

        <div class="replies">
          {#each replies as r}
            <div class="reply" class:internal={r.is_internal_note}>
              <div class="rhead"><b>{r.user_name || "?"}</b> <span class="rrole">{r.user_role || ""}</span>{#if r.is_internal_note}<span class="note">internal</span>{/if}<span class="rtime">{fmt(r.created_at)}</span></div>
              <div class="rbody">{@html r.message}</div>
            </div>
          {/each}
          {#if replies.length === 0 && !loading}<p class="muted">No replies yet.</p>{/if}
        </div>

        <div class="reply-box">
          <textarea rows="3" bind:value={replyText} placeholder="Write a reply…"></textarea>
          <div class="rb-actions">
            <label class="chk"><input type="checkbox" bind:checked={replyInternal} /> Internal note</label>
            <button class="btn primary" onclick={sendReply} disabled={sending || !replyText.trim()}>{sending ? "Sending…" : "Reply"}</button>
          </div>
        </div>
      {:else if err}
        <p class="muted pad">{err}</p>
      {/if}
    </div>
  {:else if tab === "new"}
    <div class="newform">
      <button class="back" onclick={() => { tab = "list"; }}>‹ Cancel</button>
      <h3>New ticket</h3>
      <label class="fr"><span>Title</span><input bind:value={nf.title} /></label>
      <label class="fr"><span>Description</span><textarea rows="4" bind:value={nf.description}></textarea></label>
      <label class="fr"><span>Firm</span>
        {#if firms.length}<select bind:value={nf.firm_id}><option value="">—</option>{#each firms as f}<option value={f.id}>{f.name}</option>{/each}</select>
        {:else}<input type="number" bind:value={nf.firm_id} placeholder="firm id" />{/if}
      </label>
      <label class="fr"><span>Created by</span>
        {#if users.length}<select bind:value={nf.created_by_user_id}><option value="">—</option>{#each users as u}<option value={u.id}>{u.name} ({u.email})</option>{/each}</select>
        {:else}<input type="number" bind:value={nf.created_by_user_id} placeholder="user id" />{/if}
      </label>
      <label class="fr"><span>Department</span>
        {#if departments.length}<select bind:value={nf.department_id}><option value="">—</option>{#each departments as d}<option value={d.id}>{d.name}</option>{/each}</select>
        {:else}<input type="number" bind:value={nf.department_id} placeholder="optional" />{/if}
      </label>
      <label class="fr"><span>Priority</span>
        <select bind:value={nf.priority}>{#each PRIORITIES as p}<option value={p}>{p}</option>{/each}</select>
      </label>
      <label class="fr"><span>Assign</span><label class="chk"><input type="checkbox" bind:checked={nf.assign_me} /> Assign to me</label></label>
      <div class="modal-btns">
        <button class="btn ghost" onclick={() => (tab = "list")}>Cancel</button>
        <button class="btn primary" onclick={createTicket} disabled={creating}>{creating ? "Creating…" : "Create ticket"}</button>
      </div>
    </div>
  {/if}
</section>

<style>
  .tickets { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--bg); }
  header { padding: 14px 18px 12px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 11px; }
  .htop { display: flex; align-items: center; gap: 10px; }
  .htop h2 { margin: 0; font-size: 17px; display: flex; align-items: center; gap: 7px; }
  .hspace { flex: 1; }
  .inst { max-width: 200px; }
  .stats { display: flex; gap: 12px; font-size: 12px; color: var(--muted); }
  .stats b { color: var(--text); }
  .stats .ok b { color: var(--done); }
  .tabbar { display: flex; align-items: center; gap: 4px; }
  .tab { font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 999px; color: var(--muted); }
  .tab:hover { color: var(--text); background: var(--surface-2); }
  .tab.on { background: var(--accent); color: #fff; }
  .tab .cnt { margin-left: 6px; font-size: 11px; background: var(--surface-3); color: var(--muted); border-radius: 999px; padding: 0 6px; }
  .tab.on .cnt { background: rgba(255,255,255,0.25); color: #fff; }
  .who { font-size: 12px; color: var(--faint); margin-left: 6px; }
  .udot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex: none; }
  .trow.unread .ttitle { font-weight: 800; }
  .badge.overdue { background: color-mix(in srgb, var(--danger) 22%, transparent); color: var(--danger); }
  .tabhint { font-size: 12px; color: var(--muted); margin: 0; }
  .tabhint code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .filters { display: flex; gap: 8px; }
  .filters .search { flex: 1; }
  .list { flex: 1; overflow-y: auto; min-height: 0; }
  .trow { display: flex; align-items: center; gap: 11px; width: 100%; text-align: left; padding: 11px 16px; border-bottom: 1px solid var(--border); }
  .trow:hover { background: var(--surface); }
  .pri { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--muted); }
  .pri.p-low { background: #6b7280; } .pri.p-normal { background: #2f86d6; } .pri.p-high { background: #dd8a17; } .pri.p-critical { background: #e0556e; }
  .tmain { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .ttitle { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tmeta { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tright { display: flex; align-items: center; gap: 10px; flex: none; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--muted); text-transform: capitalize; }
  .badge.st-open { background: color-mix(in srgb, #2f86d6 22%, transparent); color: #6db3f0; }
  .badge.st-in_progress { background: color-mix(in srgb, #dd8a17 22%, transparent); color: #e0a948; }
  .badge.st-closed { background: var(--surface-3); }
  .rc { font-size: 11px; color: var(--muted); display: inline-flex; gap: 3px; align-items: center; }
  .tdate { font-size: 11px; color: var(--faint); }
  .pager { display: flex; align-items: center; justify-content: center; gap: 14px; padding: 12px; font-size: 12px; color: var(--muted); }
  .empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--muted); }
  .empty .big { font-size: 42px; }
  .pad { padding: 16px; }
  .muted { color: var(--muted); }

  .detail, .newform { flex: 1; overflow-y: auto; min-height: 0; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
  .back { align-self: flex-start; color: var(--accent); font-size: 13px; font-weight: 600; }
  .d-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .d-head h3 { margin: 0; display: flex; align-items: center; gap: 8px; }
  .d-controls { display: flex; gap: 10px; }
  .d-controls label { font-size: 11px; color: var(--muted); display: flex; flex-direction: column; gap: 3px; }
  .d-meta { color: var(--muted); font-size: 12px; }
  .d-desc { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
  .replies { display: flex; flex-direction: column; gap: 10px; margin-top: 6px; }
  .reply { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; }
  .reply.internal { background: color-mix(in srgb, var(--warning) 9%, transparent); border-color: color-mix(in srgb, var(--warning) 35%, var(--border)); }
  .rhead { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 5px; }
  .rrole { color: var(--faint); }
  .note { font-size: 10px; color: var(--warning); border: 1px solid var(--warning); border-radius: 4px; padding: 0 4px; }
  .rtime { margin-left: auto; color: var(--faint); }
  .rbody { font-size: 13px; line-height: 1.5; }
  .reply-box { margin-top: 6px; display: flex; flex-direction: column; gap: 8px; }
  .reply-box textarea { width: 100%; resize: vertical; }
  .rb-actions { display: flex; align-items: center; justify-content: space-between; }
  .chk { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
  .fr { display: flex; gap: 12px; margin: 4px 0; align-items: flex-start; }
  .fr > span { width: 100px; flex: none; color: var(--muted); font-size: 13px; padding-top: 6px; }
  .fr input, .fr select, .fr textarea { flex: 1; }
  .modal-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
</style>
