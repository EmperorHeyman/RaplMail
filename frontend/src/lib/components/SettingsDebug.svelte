<script>
  import { onMount, onDestroy } from "svelte";
  import { debug, backendBase } from "../api.js";
  import { app, notify, saveSettings, syncAllAccounts, recategorizeOnce } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";
  import { dateLocale } from "../time.svelte.js";

  let records = $state([]);
  let health = $state(null);
  let lastSeq = $state(0);
  let level = $state("");        // "", INFO, WARNING, ERROR
  let paused = $state(false);
  let autoscroll = $state(true);
  let appVersion = $state("");
  // Recent message-body loads and where their time went (app.core.loadtrace).
  let loads = $state([]);
  let slowMs = $state(3000);
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
    try { const d = await debug.loads(); loads = d.loads || []; slowMs = d.slow_ms || 3000; } catch {}
  }

  async function reload() {
    // Level change / manual refresh: refetch the whole window from scratch.
    records = []; lastSeq = 0;
    await poll();
  }

  async function clear() {
    try { await debug.clearLogs(); records = []; lastSeq = 0; notify(t("sDebug.logsCleared")); }
    catch (e) { notify(e.message, "error"); }
  }

  function copyAll() {
    const text = records.map((r) => `${r.ts} ${r.level} ${r.logger}: ${r.msg}`).join("\n");
    navigator.clipboard?.writeText(text).then(
      () => notify(t("sDebug.logsCopied")),
      () => notify(t("sDebug.copyFailed"), "error"));
  }

  const fmtTs = (ts) => { try { return new Date(ts).toLocaleTimeString(dateLocale()); } catch { return ts; } };
  const fmtWhen = (iso) => { if (!iso) return "-"; try { return new Date(iso).toLocaleString(dateLocale()); } catch { return iso; } };
  const lvlClass = (l) => `lvl-${(l || "").toLowerCase()}`;
  const secs = (ms) => `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  // "waiting 3.1 s · downloading 1.2 s · 1.4 MB" - the phases worth naming.
  function phaseSummary(l) {
    const parts = (l.phases || []).filter((p) => p.ms >= 50).map((p) => `${t("sDebug.ph_" + p.name)} ${secs(p.ms)}`);
    if (!l.done && l.phase) parts.push(`${t("sDebug.ph_" + l.phase)} ${secs(l.phase_ms)}…`);
    if (l.info?.bytes) parts.push(`${(l.info.bytes / 1_000_000).toFixed(1)} MB`);
    if (l.info?.first_error && !l.error) parts.push(t("sDebug.retriedAfter", { err: l.info.first_error }));
    return parts.join(" · ") || "-";
  }
  function copyLoads() {
    const text = loads.map((l) => `${l.at} ${l.why} #${l.message_id} ${secs(l.elapsed_ms)} [${phaseSummary(l)}]${l.error ? " ERROR " + l.error : ""}`).join("\n");
    navigator.clipboard?.writeText(text).then(
      () => notify(t("sDebug.logsCopied")),
      () => notify(t("sDebug.copyFailed"), "error"));
  }

  onMount(async () => {
    try { const { getVersion } = await import("@tauri-apps/api/app"); appVersion = await getVersion(); }
    catch { appVersion = "dev"; }
    poll(); timer = setInterval(poll, 1500);
  });
  onDestroy(() => clearInterval(timer));

  // --- Developer tools -------------------------------------------------------
  function copyDiagnostics() {
    // A copy-pasteable snapshot for bug reports - health/system + a redacted
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
      () => notify(t("sDebug.diagCopied")),
      () => notify(t("sDebug.copyFailed"), "error"));
  }
  function relock() {
    saveSettings({ debugUnlocked: false });
    notify(t("sDebug.relocked"));
  }
  const base = (() => { try { return backendBase(); } catch { return "-"; } })();
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sDebug.toolsTitle")}</h3>
    <p class="hint">{t("sDebug.toolsHint")}</p>
    <div class="devgrid">
      <button class="btn ghost" onclick={copyDiagnostics}>{t("sDebug.copyDiag")}</button>
      <button class="btn ghost" onclick={() => { syncAllAccounts(); notify(t("sDebug.syncTriggered")); }}>{t("sDebug.forceSync")}</button>
      <button class="btn ghost" onclick={() => { recategorizeOnce(true); notify(t("sDebug.recategorizing")); }}>{t("sDebug.recategorize")}</button>
      <button class="btn ghost" onclick={() => { app.introTour = true; }}>{t("sDebug.showIntro")}</button>
      <button class="btn ghost danger" onclick={relock}>{t("sDebug.hideDev")}</button>
    </div>
    <div class="kv"><span>Backend</span><code>{base}</code></div>
  </section>

  <section class="card">
    <h3>{t("sDebug.healthTitle")}</h3>
    <p class="hint">{t("sDebug.healthHintA")} <b>syncing</b> {t("sDebug.healthHintB")}</p>
    {#if health?.accounts?.length}
      <div class="acct-grid">
        {#each health.accounts as a}
          <div class="acct">
            <span class="sdot {a.status || 'idle'}" title={a.status || 'idle'}></span>
            <div class="ameta">
              <b>{a.email}</b>
              <span class="sub">{a.provider}{a.idle_active ? " · " + t("sDebug.live") : ""}</span>
            </div>
            <div class="astat">
              <span class="st">{a.status || "idle"}</span>
              <span class="sub">{t("sDebug.synced", { when: fmtWhen(a.last_sync) })}</span>
              {#if a.last_error}<span class="err" title={a.last_error}>⚠ {a.last_error}</span>{/if}
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <p class="hint" style="margin:0">{t("sDebug.noAccounts")}</p>
    {/if}
    {#if health?.system}
      <p class="sysline">RaplMail v{appVersion || health.system.version} · Python {health.system.python} · {health.system.platform}</p>
    {/if}
  </section>

  <section class="card">
    <div class="loghead">
      <h3>{t("sDebug.loadsTitle")}</h3>
      <div class="spacer"></div>
      {#if loads.length}<button class="btn ghost" onclick={copyLoads}>{t("sDebug.copy")}</button>{/if}
    </div>
    <p class="hint">{t("sDebug.loadsHint")}</p>
    {#if loads.length}
      <div class="loads">
        {#each loads.slice(0, 30) as l (l.message_id + "|" + l.at)}
          <div class="load" class:slow={l.elapsed_ms >= slowMs} class:failed={!!l.error} class:running={!l.done}>
            <div class="l-top">
              <span class="l-when tnum">{fmtTs(l.at)}</span>
              <span class="l-why">{t("sDebug.why_" + l.why)}</span>
              <span class="l-subj" title={l.subject}>{l.subject || "#" + l.message_id}</span>
              <span class="l-total tnum">{secs(l.elapsed_ms)}</span>
            </div>
            <div class="l-bar" aria-hidden="true">
              {#each l.phases as p}<i class="ph-{p.name}" style="flex:{Math.max(p.ms, 1)}" title="{t('sDebug.ph_' + p.name)} {secs(p.ms)}"></i>{/each}
              {#if !l.done && l.phase}<i class="ph-{l.phase} live" style="flex:{Math.max(l.phase_ms, 1)}"></i>{/if}
            </div>
            <span class="l-detail">{phaseSummary(l)}</span>
            {#if l.error}<span class="l-err">{l.error}</span>{/if}
          </div>
        {/each}
      </div>
    {:else}
      <p class="hint" style="margin:0">{t("sDebug.noLoads")}</p>
    {/if}
  </section>

  <section class="card logs">
    <div class="loghead">
      <h3>{t("sDebug.logTitle")}</h3>
      <div class="spacer"></div>
      <select bind:value={level} onchange={reload} title={t("sDebug.minLevel")}>
        {#each LEVELS as l}<option value={l}>{l || t("sDebug.all")}</option>{/each}
      </select>
      <button class="btn ghost" class:on={!paused} onclick={() => (paused = !paused)}>{paused ? "▶ " + t("sDebug.resume") : "⏸ " + t("sDebug.pause")}</button>
      <label class="chk"><input type="checkbox" bind:checked={autoscroll} /> {t("sDebug.autoscroll")}</label>
      <button class="btn ghost" onclick={copyAll}>{t("sDebug.copy")}</button>
      <button class="btn ghost danger" onclick={clear}>{t("sDebug.clear")}</button>
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
      {#if !records.length}<p class="hint" style="padding:12px">{t("sDebug.noLogs")}</p>{/if}
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

  /* Opening messages: one row per load, a bar split by phase. */
  .loads { display: flex; flex-direction: column; gap: 10px; max-height: 420px; overflow-y: auto; }
  .load { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border-radius: 10px; background: var(--surface-2); }
  .load.slow { box-shadow: inset 3px 0 0 var(--warning); }
  .load.failed { box-shadow: inset 3px 0 0 var(--danger); }
  .l-top { display: flex; align-items: baseline; gap: 10px; font-size: 13px; min-width: 0; }
  .l-when { color: var(--muted); font-size: 12px; flex: none; }
  .l-why { font-size: 11.5px; font-weight: 600; color: var(--on-sel); background: var(--sel); padding: 1px 7px; border-radius: 6px; flex: none; }
  .l-subj { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .l-total { flex: none; font-weight: 600; }
  .load.slow .l-total { color: var(--warning); }
  .load.failed .l-total { color: var(--danger); }
  .l-bar { display: flex; gap: 2px; height: 6px; border-radius: 3px; overflow: hidden; }
  .l-bar i { display: block; min-width: 2px; background: var(--outline); }
  .l-bar .ph-waiting { background: var(--warning); }
  .l-bar .ph-connecting, .l-bar .ph-retrying { background: var(--tert); }
  .l-bar .ph-downloading { background: var(--accent); }
  .l-bar .ph-parsing, .l-bar .ph-attachments { background: var(--done); }
  .l-bar .live { animation: pulse 1s ease-in-out infinite; }
  .l-detail { font-size: 12px; color: var(--muted); }
  .l-err { font-size: 12px; color: var(--danger); overflow-wrap: anywhere; }
</style>
