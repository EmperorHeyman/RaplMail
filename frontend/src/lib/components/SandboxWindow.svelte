<script>
  // The isolated attachment sandbox.
  //
  // This runs in its own native window (label "sandbox-*") that is created with
  // NO Tauri capabilities except closing itself: it cannot reach the OS, the
  // network, or the mail backend. The file bytes arrive through a localStorage
  // seed and are parsed entirely inside a sealed WebAssembly module whose only
  // channel to the outside world is a set of host functions we log. So every
  // dangerous thing the file contains becomes a logged *intent* here, never an
  // action. A JS interceptor additionally traps any network/navigation the page
  // itself might attempt. Nothing leaves the box.
  import { onMount, onDestroy } from "svelte";
  import { fly } from "svelte/transition";
  import { t } from "../i18n.svelte.js";
  import { icons } from "../icons.js";
  import { installInterceptor } from "../sandbox/interceptor.js";
  import {
    analyze, K_TYPE, K_EMBED, K_KEYWORD, K_PREVIEW, K_NOTE,
    I_NET, I_EXEC, I_SCRIPT, I_MACRO,
  } from "../sandbox/analyzer.js";

  let seed = $state(null);
  let bytes = null;
  let hexHead = $state("");
  let wasmScore = $state(0);
  let deep = $state(null);      // backend deep report (macros, pdf streams)
  let truncated = $state(false);
  // The verdict is the worst of the in-sandbox wasm scan and the backend deep
  // analysis — a compressed .docm macro is invisible to the raw-byte wasm scan
  // but caught by olevba, so the deep score must be able to raise the verdict.
  const score = $derived(Math.max(wasmScore, deep?.score || 0));
  let running = $state(true);
  let error = $state("");

  // Progressive reveal so the dashboard feels alive as findings "come in".
  let activity = $state([]);   // intents + intercepted page calls (the live feed)
  let findings = $state([]);   // static structural findings
  let previewText = $state("");
  let blockedCalls = $state(0);

  let uninstall = null;
  let revealTimer = null;
  let pendingActivity = [];

  const SEVERITY = {
    [I_EXEC]: { sev: "critical", cat: "exec" },
    [I_NET]: { sev: "danger", cat: "network" },
    [I_SCRIPT]: { sev: "danger", cat: "script" },
    [I_MACRO]: { sev: "danger", cat: "macro" },
  };

  const verdict = $derived.by(() => {
    if (running) return { kind: "scan", key: "sandbox.scanning", sum: "sandbox.sumScan" };
    if (score >= 55) return { kind: "critical", key: "sandbox.verdictDanger", sum: "sandbox.sumDanger" };
    if (score >= 22) return { kind: "danger", key: "sandbox.verdictSuspicious", sum: "sandbox.sumSuspicious" };
    if (score > 0) return { kind: "warn", key: "sandbox.verdictCaution", sum: "sandbox.sumCaution" };
    return { kind: "clean", key: "sandbox.verdictClean", sum: "sandbox.sumClean" };
  });

  const humanSize = (n) => {
    if (n == null) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  };

  function b64ToBytes(b64) {
    const bin = atob(b64 || "");
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function toHex(u8, max = 256) {
    let s = "";
    const n = Math.min(u8.length, max);
    for (let i = 0; i < n; i++) {
      s += u8[i].toString(16).padStart(2, "0") + (((i + 1) % 16 === 0) ? "\n" : " ");
    }
    return s.trim();
  }

  function catLabel(cat) {
    return t(`sandbox.cat.${cat}`);
  }

  const seenActivity = new Set();
  // Returns true only if the row was newly added (deduped by category+text), so
  // the count always matches the number of visible rows.
  function addActivity(row, live) {
    const key = row.cat + "|" + row.text;
    if (seenActivity.has(key)) return false;
    seenActivity.add(key);
    if (live) activity.push(row); else pendingActivity.push(row);
    return true;
  }

  onMount(async () => {
    // Trap the page's own outbound channels first, before anything runs. Only
    // genuinely external (phone-home) attempts reach here; framework/same-origin
    // /loopback traffic is passed through, so this stays 0 for a normal file.
    // Blocked rows are shown live and immediately, each with its target, so the
    // count below can never be a number without a matching log entry.
    uninstall = installInterceptor(({ api, target }) => {
      if (addActivity({ sev: "blocked", cat: "guard", text: `${api} → ${target}` }, true)) blockedCalls += 1;
    });

    try {
      seed = JSON.parse(localStorage.getItem("raplmail.sandbox.seed") || "null");
      // Consume it so it doesn't leak to a future window.
      localStorage.removeItem("raplmail.sandbox.seed");
    } catch { seed = null; }

    if (!seed || !seed.dataB64) { error = t("sandbox.noData"); running = false; return; }
    deep = seed.deepReport || null;
    document.title = `${t("sandbox.title")} — ${seed.name}`;

    try {
      bytes = b64ToBytes(seed.dataB64);
      hexHead = toHex(bytes);
      const preview = [];
      const res = await analyze(bytes, {
        onFinding: (f) => {
          if (f.kind === K_PREVIEW) { preview.push(f.text); return; }
          findings.push({ kind: f.kind, text: f.text, num: f.num });
        },
        onIntent: (i) => {
          const meta = SEVERITY[i.kind] || { sev: "warn", cat: "note" };
          addActivity({ sev: meta.sev, cat: meta.cat, text: i.text }, false);
        },
      });
      wasmScore = res.score;
      truncated = res.truncated;
      previewText = preview.join("\n").slice(0, 8192);
      startReveal();
    } catch (e) {
      error = e?.message || String(e);
      running = false;
    }
  });

  // Reveal the activity feed one item at a time for the live "watching it try
  // things" effect. The analysis is already complete; this only paces display.
  function startReveal() {
    if (!pendingActivity.length) { running = false; return; }
    let i = 0;
    revealTimer = setInterval(() => {
      if (i >= pendingActivity.length) {
        clearInterval(revealTimer);
        revealTimer = null;
        running = false;
        return;
      }
      activity.push(pendingActivity[i]);
      i += 1;
    }, 90);
  }

  onDestroy(() => {
    if (revealTimer) clearInterval(revealTimer);
    if (uninstall) uninstall();
  });

  async function closeWin() {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().close();
    } catch { try { window.close(); } catch {} }
  }

  // Ask the privileged main window (via a storage event) to carry out an action
  // on the OS. The sandbox itself cannot; it only files the request.
  function requestAction(action) {
    if (!seed) return;
    const req = { action, name: seed.name, contentType: seed.contentType, dataB64: seed.dataB64, ts: Date.now() };
    try {
      localStorage.setItem("raplmail.sandbox.action", JSON.stringify(req));
      // Some webviews don't fire "storage" for same-tab writes; a paired remove
      // guarantees the value change is observed cross-window.
      setTimeout(() => { try { localStorage.removeItem("raplmail.sandbox.action"); } catch {} }, 400);
    } catch {}
    actionDone = action;
  }
  let actionDone = $state("");

  // 3-second countdown gating the risky "open anyway" button.
  let countdown = $state(3);
  let cdTimer = null;
  onMount(() => {
    cdTimer = setInterval(() => {
      countdown -= 1;
      if (countdown <= 0) { clearInterval(cdTimer); cdTimer = null; }
    }, 1000);
  });
  onDestroy(() => { if (cdTimer) clearInterval(cdTimer); });
</script>

<div class="sb">
  <header class="head sev-{verdict.kind}">
    <div class="badge">{@html icons.warning || ""}</div>
    <div class="hmeta">
      <h1>{seed?.name || t("sandbox.title")}</h1>
      <p class="sub">
        {#if seed}{seed.typeGuess || seed.contentType || t("sandbox.unknownType")} · {humanSize(bytes?.length)}{/if}
        {#if truncated} · {t("sandbox.truncated")}{/if}
      </p>
    </div>
    <div class="verdict v-{verdict.kind}">
      {#if running}<span class="spin"></span>{/if}
      <span class="vlabel">{t(verdict.key)}</span>
      {#if !running}<span class="vscore">{score}/100</span>{/if}
    </div>
  </header>

  {#if error}
    <div class="err">{@html icons.warning || ""} {error}</div>
  {:else}
    <div class="body">
      <!-- Plain-language verdict + what the sandbox is -->
      <section class="panel summary sev-{verdict.kind}">
        <p class="sumtext">{t(verdict.sum)}</p>
        <p class="explain">{@html icons.shield || ""} {t("sandbox.explain")}</p>
      </section>

      <!-- Live activity feed: what the file is trying to do -->
      <section class="panel live">
        <h2>{t("sandbox.liveTitle")}</h2>
        <p class="hint">{t("sandbox.liveHint")}</p>
        <ul class="feed">
          {#each activity as a, i (i)}
            <li class="row sev-{a.sev}" in:fly={{ y: 8, duration: 160 }}>
              <span class="tag">{catLabel(a.cat)}</span>
              <span class="txt">{a.text}</span>
              <span class="blk">{a.sev === "blocked" ? t("sandbox.blocked") : t("sandbox.intercepted")}</span>
            </li>
          {/each}
          {#if !running && activity.length === 0}
            <li class="row sev-clean"><span class="txt">{t("sandbox.noActivity")}</span></li>
          {/if}
        </ul>
      </section>

      <!-- Deep analysis (backend: macro de-obfuscation, PDF stream decompression) -->
      {#if deep?.office?.has_macros}
        <section class="panel deep">
          <h2>{@html icons.warning || ""} {t("sandbox.macroTitle")}</h2>
          <p class="hint">{t("sandbox.macroHint")}</p>
          {#if deep.office.autoexec?.length}
            <div class="deeprow"><span class="dlabel">{t("sandbox.macroAuto")}</span>
              <span class="chips">{#each deep.office.autoexec as a}<span class="chip danger">{a}</span>{/each}</span>
            </div>
          {/if}
          {#if deep.office.suspicious?.length}
            <div class="deeprow"><span class="dlabel">{t("sandbox.macroSuspicious")}</span>
              <ul class="deeplist">{#each deep.office.suspicious as s}<li><b>{s.keyword}</b> — {s.description}</li>{/each}</ul>
            </div>
          {/if}
          {#if deep.office.iocs?.length}
            <div class="deeprow"><span class="dlabel">{t("sandbox.macroIocs")}</span>
              <ul class="deeplist mono">{#each deep.office.iocs as i}<li>{i.value} <em>({i.kind})</em></li>{/each}</ul>
            </div>
          {/if}
          {#if deep.office.source}
            <details class="src"><summary>{t("sandbox.macroSource")}</summary><pre class="preview">{deep.office.source}</pre></details>
          {/if}
        </section>
      {/if}
      {#if deep?.pdf && (deep.pdf.hits?.length || deep.pdf.urls?.length)}
        <section class="panel deep">
          <h2>{@html icons.warning || ""} {t("sandbox.pdfDeepTitle")}</h2>
          <p class="hint">{t("sandbox.pdfDeepHint")}</p>
          {#if deep.pdf.hits?.length}
            <ul class="deeplist">{#each deep.pdf.hits as h}<li>{h}</li>{/each}</ul>
          {/if}
          {#if deep.pdf.urls?.length}
            <div class="deeprow"><span class="dlabel">{t("sandbox.macroIocs")}</span>
              <ul class="deeplist mono">{#each deep.pdf.urls as u}<li>{u}</li>{/each}</ul>
            </div>
          {/if}
        </section>
      {/if}

      <!-- Static structural findings -->
      <section class="panel">
        <h2>{t("sandbox.findingsTitle")}</h2>
        <ul class="findings">
          {#each findings as f (f.text + f.kind)}
            <li class="fnd k-{f.kind}">
              <span class="txt">{f.text}</span>
              {#if f.num > 1}<span class="cnt">×{f.num}</span>{/if}
            </li>
          {/each}
          {#if findings.length === 0}<li class="fnd"><span class="txt">{t("sandbox.noFindings")}</span></li>{/if}
        </ul>
      </section>

      <!-- Safe read-only preview extracted inside the sandbox -->
      {#if previewText}
        <section class="panel">
          <h2>{t("sandbox.previewTitle")}</h2>
          <pre class="preview">{previewText}</pre>
        </section>
      {/if}

      <!-- Raw bytes -->
      <section class="panel">
        <h2>{t("sandbox.hexTitle")}</h2>
        <pre class="hex">{hexHead}</pre>
      </section>
    </div>

    <footer class="acts">
      <div class="guard" title={t("sandbox.guardTip")}>
        {@html icons.shieldCheck || icons.shield || ""}
        {#if blockedCalls > 0}{t("sandbox.guardBlocked", { n: blockedCalls })}{:else}{t("sandbox.guardSafe")}{/if}
      </div>
      <div class="sp"></div>
      {#if actionDone}
        <span class="done">{actionDone === "save" ? t("sandbox.saveRequested") : t("sandbox.openRequested")}</span>
      {/if}
      <button class="btn" onclick={() => requestAction("save")}>{t("sandbox.saveToDisk")}</button>
      <button class="btn danger" disabled={countdown > 0} onclick={() => requestAction("open")}>
        {countdown > 0 ? t("sandbox.openIn", { n: countdown }) : t("sandbox.openAnyway")}
      </button>
      <button class="btn primary" onclick={closeWin}>{t("sandbox.close")}</button>
    </footer>
  {/if}
</div>

<style>
  :global(body) { background: var(--bg); }
  .sb { display: flex; flex-direction: column; height: 100vh; background: var(--bg); color: var(--text); font-size: 13px; }
  .head { display: flex; align-items: center; gap: 14px; padding: 16px 20px; border-bottom: 1px solid var(--hairline); }
  .badge { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; flex: none; background: var(--hover); }
  .badge :global(svg) { width: 18px; height: 18px; }
  .head.sev-critical .badge, .head.sev-danger .badge { background: color-mix(in srgb, var(--danger, #e5484d) 20%, transparent); color: var(--danger, #e5484d); }
  .head.sev-warn .badge { background: color-mix(in srgb, #e6a23c 22%, transparent); color: #e6a23c; }
  .head.sev-clean .badge { background: color-mix(in srgb, var(--ok, #30a46c) 20%, transparent); color: var(--ok, #30a46c); }
  .hmeta { flex: 1; min-width: 0; }
  .hmeta h1 { margin: 0; font-size: 16px; font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { margin: 2px 0 0; color: var(--muted); font-size: 12px; }
  .verdict { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; font-weight: 650; flex: none; }
  .v-critical, .v-danger { background: color-mix(in srgb, var(--danger, #e5484d) 16%, transparent); color: var(--danger, #e5484d); }
  .v-warn { background: color-mix(in srgb, #e6a23c 18%, transparent); color: #b8801f; }
  .v-clean { background: color-mix(in srgb, var(--ok, #30a46c) 16%, transparent); color: var(--ok, #30a46c); }
  .v-scan { background: var(--hover); color: var(--muted); }
  .vscore { font-variant-numeric: tabular-nums; opacity: 0.8; font-weight: 600; }
  .spin { width: 12px; height: 12px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: sp 0.7s linear infinite; }
  @keyframes sp { to { transform: rotate(360deg); } }

  .body { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 16px; }
  .summary { border-left: 3px solid var(--muted); }
  .summary.sev-critical, .summary.sev-danger { border-left-color: var(--danger, #e5484d); }
  .summary.sev-warn { border-left-color: #e6a23c; }
  .summary.sev-clean { border-left-color: var(--ok, #30a46c); }
  .sumtext { margin: 0 0 8px; font-size: 14px; font-weight: 600; line-height: 1.45; }
  .explain { margin: 0; color: var(--muted); font-size: 12px; display: flex; align-items: center; gap: 6px; }
  .explain :global(svg) { width: 14px; height: 14px; flex: none; }
  .panel { border: 1px solid var(--hairline); border-radius: var(--radius, 10px); background: var(--surface); padding: 12px 14px; }
  .panel h2 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 650; }
  .hint { margin: 0 0 10px; color: var(--muted); font-size: 12px; }

  .feed { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; background: var(--bg); border: 1px solid var(--hairline); }
  .row .tag { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 7px; border-radius: 5px; flex: none; background: var(--hover); color: var(--muted); }
  .row .txt { flex: 1; min-width: 0; word-break: break-all; font-family: ui-monospace, monospace; font-size: 12px; }
  .row .blk { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--danger, #e5484d); flex: none; }
  .row.sev-critical { border-color: color-mix(in srgb, var(--danger, #e5484d) 45%, transparent); }
  .row.sev-critical .tag, .row.sev-danger .tag { background: color-mix(in srgb, var(--danger, #e5484d) 18%, transparent); color: var(--danger, #e5484d); }
  .row.sev-blocked .tag { background: color-mix(in srgb, #e6a23c 20%, transparent); color: #b8801f; }
  .row.sev-clean { color: var(--muted); }

  .findings { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
  .fnd { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; background: var(--hover); font-size: 12px; }
  .fnd .cnt { font-size: 10px; font-weight: 700; color: var(--muted); }
  .fnd.k-6 { background: color-mix(in srgb, #e6a23c 16%, transparent); }
  .fnd.k-4 { background: color-mix(in srgb, var(--accent) 14%, transparent); }

  .deep { border-left: 3px solid var(--danger, #e5484d); }
  .deep h2 { display: flex; align-items: center; gap: 6px; color: var(--danger, #e5484d); }
  .deep h2 :global(svg) { width: 14px; height: 14px; }
  .deeprow { display: flex; gap: 10px; margin-top: 8px; align-items: baseline; }
  .dlabel { flex: none; width: 90px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); font-weight: 650; }
  .deeplist { margin: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 3px; font-size: 12.5px; }
  .deeplist.mono { font-family: ui-monospace, monospace; font-size: 11.5px; word-break: break-all; }
  .deeplist em { color: var(--muted); font-style: normal; }
  .chip { display: inline-flex; padding: 3px 9px; border-radius: 999px; font-size: 12px; background: var(--hover); margin: 2px 4px 2px 0; }
  .chip.danger { background: color-mix(in srgb, var(--danger, #e5484d) 16%, transparent); color: var(--danger, #e5484d); font-weight: 600; }
  details.src { margin-top: 10px; }
  details.src summary { cursor: pointer; color: var(--accent); font-size: 12px; }
  .preview, .hex { margin: 8px 0 0; max-height: 220px; overflow: auto; background: var(--bg); border: 1px solid var(--hairline); border-radius: 8px; padding: 10px; font-family: ui-monospace, monospace; font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; color: var(--text); }
  .hex { white-space: pre; color: var(--muted); }

  .err { margin: 20px; padding: 14px; border-radius: 10px; background: color-mix(in srgb, var(--danger, #e5484d) 12%, transparent); color: var(--danger, #e5484d); display: flex; gap: 8px; align-items: center; }
  .err :global(svg) { width: 18px; height: 18px; }

  .acts { display: flex; align-items: center; gap: 10px; padding: 12px 20px; border-top: 1px solid var(--hairline); background: var(--surface); }
  .acts .sp { flex: 1; }
  .guard { color: var(--muted); font-size: 12px; display: flex; align-items: center; gap: 6px; }
  .guard :global(svg) { width: 14px; height: 14px; }
  .done { color: var(--ok, #30a46c); font-size: 12px; font-weight: 600; }
  .btn.danger { background: var(--danger, #e5484d); color: #fff; }
  .btn.danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
