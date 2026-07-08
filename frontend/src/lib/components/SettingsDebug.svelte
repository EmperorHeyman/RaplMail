<script>
  import { onMount, onDestroy } from "svelte";
  import { debug, backendBase } from "../api.js";
  import { app, notify, saveSettings, syncAllAccounts, recategorizeOnce } from "../store.svelte.js";

  let records = $state([]);
  let health = $state(null);
  let lastSeq = $state(0);
  let level = $state("");        // "", INFO, WARNING, ERROR
  let paused = $state(false);
  let autoscroll = $state(true);
  let appVersion = $state("");
  let logEl;
  let timer;

  const LEVELS = ["", "INFO", "WARNING", "ERROR"];

  async function poll() {
    if (paused) return;
    try {
      const d = await debug.logs(lastSeq, level || undefined);
      if (d.records?.length) {
        records = [...records, ...d.records].slice(-1500);
        lastSeq = d.last_seq;
        if (autoscroll && logEl) queueMicrotask(() => (logEl.scrollTop = logEl.scrollHeight));
      }
    } catch {}
    try { health = await debug.health(); } catch {}
  }

  async function reload() {
    // Level change / manual refresh: refetch the whole window from scratch.
    records = []; lastSeq = 0;
    await poll();
  }

  async function clear() {
    try { await debug.clearLogs(); records = []; lastSeq = 0; notify("Logs cleared"); }
    catch (e) { notify(e.message, "error"); }
  }

  function copyAll() {
    const text = records.map((r) => `${r.ts} ${r.level} ${r.logger}: ${r.msg}`).join("\n");
    navigator.clipboard?.writeText(text).then(
      () => notify("Copied logs to clipboard"),
      () => notify("Couldn't copy", "error"));
  }

  const fmtTs = (ts) => { try { return new Date(ts).toLocaleTimeString(); } catch { return ts; } };
  const fmtWhen = (iso) => { if (!iso) return "—"; try { return new Date(iso).toLocaleString(); } catch { return iso; } };
  const lvlClass = (l) => `lvl-${(l || "").toLowerCase()}`;

  onMount(async () => {
    try { const { getVersion } = await import("@tauri-apps/api/app"); appVersion = await getVersion(); }
    catch { appVersion = "dev"; }
    poll(); timer = setInterval(poll, 1500);
  });
  onDestroy(() => clearInterval(timer));

  // --- Developer tools -------------------------------------------------------
  function copyDiagnostics() {
    // A copy-pasteable snapshot for bug reports — health/system + a redacted
    // settings dump (secrets/keys stripped) so nothing sensitive leaks.
    const SECRET = /(key|token|password|secret|pgp|smime|cert|refresh|caldav|carddav)/i;
    const redacted = {};
    for (const [k, v] of Object.entries(app.settings || {})) redacted[k] = SECRET.test(k) ? "«redacted»" : v;
    const blob = {
      version: appVersion, when: new Date().toISOString(),
      system: health?.system || null,
      accounts: (health?.accounts || []).map((a) => ({ provider: a.provider, status: a.status, idle: a.idle_active, last_error: a.last_error || null })),
      backend: (() => { try { return backendBase(); } catch { return null; } })(),
      settings: redacted,
    };
    navigator.clipboard?.writeText(JSON.stringify(blob, null, 2)).then(
      () => notify("Copied diagnostics to clipboard"),
      () => notify("Couldn't copy", "error"));
  }
  function relock() {
    saveSettings({ debugUnlocked: false });
    notify("Developer mode hidden. Tap the version 5× to re-enable.");
  }
  const base = (() => { try { return backendBase(); } catch { return "—"; } })();
</script>

<div class="wrap">
  <section class="card">
    <h3>Developer tools</h3>
    <p class="hint">Diagnostics and manual triggers. This section stays hidden until you tap the version 5 times.</p>
    <div class="devgrid">
      <button class="btn ghost" onclick={copyDiagnostics}>Copy diagnostics</button>
      <button class="btn ghost" onclick={() => { syncAllAccounts(); notify("Sync triggered"); }}>Force sync all</button>
      <button class="btn ghost" onclick={() => { recategorizeOnce(true); notify("Recategorizing inbox…"); }}>Recategorize inbox</button>
      <button class="btn ghost danger" onclick={relock}>Hide developer mode</button>
    </div>
    <div class="kv"><span>Backend</span><code>{base}</code></div>
  </section>

  <section class="card">
    <h3>Account health</h3>
    <p class="hint">Live sync status per account. If one is stuck on <b>syncing</b> or shows an error, that's the culprit.</p>
    {#if health?.accounts?.length}
      <div class="acct-grid">
        {#each health.accounts as a}
          <div class="acct">
            <span class="sdot {a.status || 'idle'}" title={a.status || 'idle'}></span>
            <div class="ameta">
              <b>{a.email}</b>
              <span class="sub">{a.provider}{a.idle_active ? " · live (IDLE)" : ""}</span>
            </div>
            <div class="astat">
              <span class="st">{a.status || "idle"}</span>
              <span class="sub">synced {fmtWhen(a.last_sync)}</span>
              {#if a.last_error}<span class="err" title={a.last_error}>⚠ {a.last_error}</span>{/if}
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <p class="hint" style="margin:0">No accounts.</p>
    {/if}
    {#if health?.system}
      <p class="sysline">RaplMail v{appVersion || health.system.version} · Python {health.system.python} · {health.system.platform}</p>
    {/if}
  </section>

  <section class="card logs">
    <div class="loghead">
      <h3>Backend log</h3>
      <div class="spacer"></div>
      <select bind:value={level} onchange={reload} title="Minimum level">
        {#each LEVELS as l}<option value={l}>{l || "All"}</option>{/each}
      </select>
      <button class="btn ghost" class:on={!paused} onclick={() => (paused = !paused)}>{paused ? "▶ Resume" : "⏸ Pause"}</button>
      <label class="chk"><input type="checkbox" bind:checked={autoscroll} /> Auto-scroll</label>
      <button class="btn ghost" onclick={copyAll}>Copy</button>
      <button class="btn ghost danger" onclick={clear}>Clear</button>
    </div>
    <div class="logview" bind:this={logEl}>
      {#each records as r (r.seq)}
        <div class="line {lvlClass(r.level)}">
          <span class="t">{fmtTs(r.ts)}</span>
          <span class="lv">{r.level}</span>
          <span class="lg">{r.logger}</span>
          <span class="msg">{r.msg}</span>
        </div>
      {/each}
      {#if !records.length}<p class="hint" style="padding:12px">No log lines yet. Trigger a sync or send a message.</p>{/if}
    </div>
  </section>
</div>

<style>
  .wrap { max-width: 860px; display: flex; flex-direction: column; gap: 22px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .acct-grid { display: flex; flex-direction: column; gap: 2px; }
  .acct { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); }
  .ameta { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  .ameta .sub, .astat .sub { font-size: 12px; color: var(--muted); }
  .astat { display: flex; flex-direction: column; align-items: flex-end; text-align: right; min-width: 0; }
  .astat .st { font-size: 13px; text-transform: capitalize; }
  .astat .err { font-size: 12px; color: var(--danger); max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sdot { width: 9px; height: 9px; border-radius: 50%; background: var(--faint); flex: none; }
  .sdot.ok { background: var(--done); }
  .sdot.syncing { background: var(--accent); animation: pulse 1s ease-in-out infinite; }
  .sdot.error { background: var(--danger); }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .sysline { margin: 12px 0 0; font-size: 12px; color: var(--faint); }
  .devgrid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .devgrid .btn { padding: 7px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); font-size: 13px; }
  .devgrid .btn:hover { background: var(--surface-3); }
  .devgrid .btn.danger { color: var(--danger); }
  .kv { display: flex; align-items: center; gap: 10px; font-size: 12px; }
  .kv > span { color: var(--muted); width: 60px; flex: none; }
  .kv code { flex: 1; min-width: 0; background: var(--surface-2); border: 1px solid var(--border); padding: 4px 8px; border-radius: 6px; overflow-x: auto; white-space: nowrap; }

  .logs { display: flex; flex-direction: column; }
  .loghead { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .loghead .spacer { flex: 1; }
  .loghead select { padding: 4px 6px; }
  .chk { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
  .btn.on { color: var(--text); }
  .btn.danger { color: var(--danger); }
  .logview { height: 380px; overflow-y: auto; background: var(--bg); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px; font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 12px; line-height: 1.5; }
  .line { display: flex; gap: 8px; padding: 1px 4px; white-space: pre-wrap; word-break: break-word; }
  .line .t { color: var(--faint); flex: none; }
  .line .lv { flex: none; width: 62px; color: var(--muted); }
  .line .lg { flex: none; color: var(--accent); opacity: 0.8; }
  .line .msg { flex: 1; color: var(--text); }
  .line.lvl-warning .lv { color: #e0a83b; }
  .line.lvl-warning { background: color-mix(in srgb, #e0a83b 8%, transparent); }
  .line.lvl-error .lv, .line.lvl-error .msg { color: var(--danger); }
  .line.lvl-error { background: color-mix(in srgb, var(--danger) 10%, transparent); }
</style>
