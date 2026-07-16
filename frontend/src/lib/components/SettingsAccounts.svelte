<script>
  import { onMount, onDestroy } from "svelte";
  import { app, loadAccountsAndFolders, notify, confirmDialog } from "../store.svelte.js";
  import { accounts as api } from "../api.js";
  import { relativeTime } from "../time.js";
  import { t } from "../i18n.svelte.js";

  // --- per-account health dashboard ----------------------------------------
  let health = $state({});   // keyed by account id
  let healthTimer;
  async function refreshHealth() {
    try {
      const rows = await api.health();
      const m = {};
      for (const r of rows) m[r.id] = r;
      health = m;
    } catch {}
  }

  // --- full-history backfill -----------------------------------------------
  let backfill = $state(null);
  let backfillBusy = $state(false);
  async function refreshBackfill() {
    try { backfill = await api.backfillStatus(); } catch {}
  }
  async function toggleBackfill() {
    backfillBusy = true;
    try {
      backfill = await api.setBackfill(!backfill?.enabled);
      notify(backfill.enabled ? t("setacc.backfillOn") : t("setacc.backfillPaused"));
    } catch (e) { notify(e.message, "error"); }
    finally { backfillBusy = false; }
  }

  function tick() { refreshHealth(); refreshBackfill(); }
  onMount(() => { tick(); healthTimer = setInterval(tick, 5000); });
  onDestroy(() => clearInterval(healthTimer));

  // `text` holds i18n keys - translated with t() at render time so the labels
  // follow live language switches.
  const STATUS = {
    ok:       { dot: "#3fb950", text: "setacc.stConnected" },
    syncing:  { dot: "#3b82f6", text: "setacc.stSyncing" },
    error:    { dot: "#f85149", text: "setacc.stError" },
    idle:     { dot: "#8b949e", text: "setacc.stIdle" },
    disabled: { dot: "#6e7681", text: "setacc.stDisabled" },
  };
  const stMeta = (s) => STATUS[s] || STATUS.idle;

  // Add-account wizard state.
  let step = $state("email");   // "email" | "config"
  let email = $state("");
  let busy = $state(false);
  let error = $state("");
  let disc = $state(null);      // autodiscover result
  let password = $state("");
  let displayName = $state("");
  let advanced = $state(false);
  let msFlow = $state(null);
  let usePassword = $state(false);   // OAuth provider, but add via an app password

  function reset() {
    step = "email"; email = ""; disc = null; password = ""; displayName = "";
    advanced = false; error = ""; msFlow = null; busy = false; usePassword = false;
  }

  async function continueEmail() {
    error = "";
    if (!email.includes("@")) { error = t("setacc.enterFullEmail"); return; }
    busy = true;
    try {
      disc = await api.autodiscover(email);
      step = "config";
    } catch (e) { error = e.message; } finally { busy = false; }
  }

  // Override a wrong auto-detect (e.g. an M365 tenant that looks like plain IMAP).
  function forceProvider(p) {
    usePassword = false; msFlow = null; error = "";
    if (p === "m365") disc = { ...disc, provider: "m365", auth: "oauth", source: t("setacc.manualChoice"), note: "" };
    else if (p === "gmail") disc = { ...disc, provider: "gmail", auth: "oauth", source: t("setacc.manualChoice"), note: "" };
    else disc = { ...disc, provider: "imap", auth: "password", source: t("setacc.manualChoice"),
                  imap_host: disc.imap_host || "", smtp_host: disc.smtp_host || "" };
  }

  // OAuth providers - the sign-in itself is the connection test.
  async function connectGoogle() {
    busy = true; error = "";
    notify(t("setacc.openingGoogle"));
    try { await api.googleConnect(); notify(t("setacc.gmailConnected")); app.syncing = true; await loadAccountsAndFolders(); reset(); }
    catch (e) { error = e.message; } finally { busy = false; }
  }

  async function startMs() {
    busy = true; error = "";
    try {
      msFlow = await api.msStart();
      openMsLogin();  // auto-open the Microsoft page + copy the code
      api.msComplete(msFlow.flow_id)
        .then(async () => { notify(t("setacc.msConnected")); app.syncing = true; await loadAccountsAndFolders(); reset(); })
        .catch((e) => { error = e.message; msFlow = null; });
    } catch (e) { error = e.message; } finally { busy = false; }
  }
  function openMsLogin() {
    if (!msFlow) return;
    try { navigator.clipboard?.writeText(msFlow.user_code); } catch {}
    // Prefer the URL with the code pre-filled when Microsoft returns one.
    const url = msFlow.verification_uri_complete || msFlow.verification_uri;
    try { window.open(url, "_blank", "noreferrer"); } catch {}
  }

  // Password account - verifies the connection before adding.
  async function testAndAdd() {
    error = "";
    if (!password) { error = t("setacc.enterPassword"); return; }
    busy = true;
    try {
      await api.createImap({
        email, display_name: displayName,
        password,
        imap_host: disc.imap_host, imap_port: disc.imap_port, imap_ssl: disc.imap_ssl,
        smtp_host: disc.smtp_host, smtp_port: disc.smtp_port,
      });
      notify(t("setacc.connectedSyncing"));
      app.syncing = true;
      await loadAccountsAndFolders();
      reset();
    } catch (e) { error = e.message; } finally { busy = false; }
  }

  async function remove(a) {
    const ok = await confirmDialog({
      title: t("setacc.removeTitle", { email: a.email }),
      message: t("setacc.removeMsg"),
      confirmLabel: t("setacc.removeConfirm"), danger: true,
    });
    if (!ok) return;
    try {
      await api.remove(a.id);
      await loadAccountsAndFolders();
      notify(t("setacc.removed"));
    } catch (e) {
      notify(t("setacc.removeFailed", { error: e.message }), "error");
    }
  }

  async function triggerSync(a) {
    try { await api.sync(a.id); notify(t("setacc.syncingAccount", { email: a.email })); setTimeout(refreshHealth, 600); }
    catch (e) { notify(e.message, "error"); }
  }

  // Re-enter the password for a password account (fixes "no saved password").
  async function reconnect(a) {
    const pw = prompt(t("setacc.reconnectPrompt", { email: a.email }));
    if (!pw) return;
    try {
      await api.reconnect(a.id, pw);
      notify(t("setacc.reconnected"));
      setTimeout(refreshHealth, 800);
    } catch (e) { notify(e.message, "error"); }
  }

  // --- send-as identities / aliases ----------------------------------------
  let idEdit = $state(null);     // account id whose identity editor is open
  let idText = $state("");
  function openIdentities(a) {
    idEdit = idEdit === a.id ? null : a.id;
    if (idEdit) idText = (a.aliases || []).join("\n");
  }
  async function saveAliases(a) {
    const aliases = idText.split("\n").map((s) => s.trim()).filter(Boolean);
    try { await api.update(a.id, { aliases }); await loadAccountsAndFolders(); idEdit = null; notify(t("setacc.identitiesSaved")); }
    catch (e) { notify(e.message, "error"); }
  }

  // --- server settings (fix a wrong/empty IMAP or SMTP host) ----------------
  let srvEdit = $state(null);
  let srv = $state(null);
  function openServer(a) {
    srvEdit = srvEdit === a.id ? null : a.id;
    if (srvEdit) srv = { imap_host: a.imap_host || "", imap_port: a.imap_port || 993, smtp_host: a.smtp_host || "", smtp_port: a.smtp_port || 465 };
  }
  async function saveServer(a) {
    try {
      await api.update(a.id, { imap_host: srv.imap_host.trim(), imap_port: Number(srv.imap_port),
                               smtp_host: srv.smtp_host.trim(), smtp_port: Number(srv.smtp_port) });
      await loadAccountsAndFolders();
      srvEdit = null;
      notify(t("setacc.serverSaved"));
    } catch (e) { notify(e.message, "error"); }
  }
  // Re-run provider detection (MX/known-host) for this account's domain and fill
  // the form - fixes a stale/guessed SMTP host (e.g. a Seznam vanity domain).
  async function autodetectServer(a) {
    try {
      const d = await api.autodiscover(a.email);
      srv = { imap_host: d.imap_host || srv.imap_host, imap_port: d.imap_port || srv.imap_port,
              smtp_host: d.smtp_host || srv.smtp_host, smtp_port: d.smtp_port || srv.smtp_port };
      notify(t("setacc.detectedVia", { host: d.smtp_host || "?", source: d.source }));
    } catch (e) { notify(e.message, "error"); }
  }

  async function setColor(a, color) { await api.update(a.id, { color }); await loadAccountsAndFolders(); }
  async function rename(a, name) { await api.update(a.id, { display_name: name }); await loadAccountsAndFolders(); }

  // Reorder accounts (persisted as sort_order; the sidebar + unified views follow).
  async function move(a, dir) {
    const list = [...app.accounts];
    const i = list.findIndex((x) => x.id === a.id);
    const j = i + dir;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    try {
      await Promise.all(list.map((acc, idx) =>
        acc.sort_order === idx ? null : api.update(acc.id, { sort_order: idx })));
      await loadAccountsAndFolders();
    } catch (e) { notify(e.message, "error"); }
  }

  const providerLabel = { imap: "IMAP / SMTP", gmail: "Google", m365: "Microsoft 365" };
</script>

<div class="wrap">
  <div class="accounts">
    {#each app.accounts as a, i}
      {@const h = health[a.id]}
      {@const st = stMeta(h?.status)}
      <div class="acct-card">
        {#if app.accounts.length > 1}
          <div class="reorder">
            <button class="ord" title={t("setacc.moveUp")} disabled={i === 0} onclick={() => move(a, -1)}>▲</button>
            <button class="ord" title={t("setacc.moveDown")} disabled={i === app.accounts.length - 1} onclick={() => move(a, 1)}>▼</button>
          </div>
        {/if}
        <input class="colorpick" type="color" value={a.color} title={t("setacc.accountColor")}
          onchange={(e) => setColor(a, e.currentTarget.value)} />
        <div class="info">
          <input class="namei" value={a.display_name} onchange={(e) => rename(a, e.currentTarget.value)} />
          <span>{a.email} · {a.provider.toUpperCase()}</span>
          {#if h}
            <div class="health">
              <span class="st" title={t(st.text)}><span class="sdot" style="background:{st.dot}"></span>{t(st.text)}</span>
              {#if h.idle_active}<span class="tag idle" title={t("setacc.liveTip")}>⚡ {t("setacc.liveTag")}</span>{/if}
              <span class="meta">{t("setacc.msgsFolders", { msgs: h.messages.toLocaleString(), folders: h.folders })}</span>
              {#if h.last_sync}<span class="meta">{t("setacc.syncedAgo", { when: relativeTime(h.last_sync) })}</span>{/if}
            </div>
            {#if h.last_error}
              <span class="herr" title={h.last_error}>⚠ {h.last_error.slice(0, 80)}{h.last_error.length > 80 ? "…" : ""}</span>
            {/if}
          {/if}
        </div>
        <button class="btn ghost" onclick={() => openIdentities(a)} title={t("setacc.identitiesTip")}>
          {t("setacc.identities")}{a.aliases?.length ? ` (${a.aliases.length})` : ""}
        </button>
        {#if a.provider === "imap"}
          <button class="btn ghost" onclick={() => reconnect(a)} title={t("setacc.reconnectTip")}>{t("setacc.reconnectBtn")}</button>
          <button class="btn ghost" onclick={() => openServer(a)} title={t("setacc.serverTip")}>{t("setacc.serverBtn")}</button>
        {/if}
        <button class="btn ghost" onclick={() => triggerSync(a)} disabled={h?.status === "syncing"} title={t("setacc.syncNow")}>↻</button>
        <button class="btn ghost danger" onclick={() => remove(a)}>{t("setacc.removeBtn")}</button>
      </div>
      {#if srvEdit === a.id && srv}
        <div class="idedit">
          <p class="muted">{@html t("setacc.serverFixHint")}</p>
          <div class="srvgrid">
            <label>{t("setacc.imapHost")}<input bind:value={srv.imap_host} placeholder="imap.seznam.cz" /></label>
            <label>{t("setacc.imapPort")}<input type="number" bind:value={srv.imap_port} /></label>
            <label>{t("setacc.smtpHost")}<input bind:value={srv.smtp_host} placeholder="smtp.seznam.cz" /></label>
            <label>{t("setacc.smtpPort")}<input type="number" bind:value={srv.smtp_port} /></label>
          </div>
          <div class="idactions">
            <button class="btn primary" onclick={() => saveServer(a)}>{t("setacc.saveServer")}</button>
            <button class="btn" onclick={() => autodetectServer(a)} title={t("setacc.autoDetectTip")}>{t("setacc.autoDetect")}</button>
            <button class="btn ghost" onclick={() => (srvEdit = null)}>{t("setacc.cancel")}</button>
          </div>
        </div>
      {/if}
      {#if idEdit === a.id}
        <div class="idedit">
          <p class="muted">{t("setacc.identitiesHintA")} <code>Name &lt;addr@host&gt;</code>{t("setacc.identitiesHintB", { email: a.email })}</p>
          <textarea bind:value={idText} rows="3" placeholder={"Sales <sales@" + (a.email.split("@")[1] || "company.com") + ">\nme+side@" + (a.email.split("@")[1] || "company.com")}></textarea>
          <div class="idactions">
            <button class="btn primary" onclick={() => saveAliases(a)}>{t("setacc.saveIdentities")}</button>
            <button class="btn ghost" onclick={() => (idEdit = null)}>{t("setacc.cancel")}</button>
          </div>
        </div>
      {/if}
    {/each}
    {#if app.accounts.length === 0}
      <p class="muted">{t("setacc.noAccounts")}</p>
    {/if}
  </div>

  {#if app.accounts.length > 0}
    <div class="backfill">
      <div class="bf-head">
        <div class="bf-copy">
          <h3>{t("setacc.historyTitle")}</h3>
          <p class="muted">{t("setacc.historyHint")}</p>
        </div>
        <button class="btn {backfill?.enabled ? '' : 'primary'}" onclick={toggleBackfill} disabled={backfillBusy}>
          {backfill?.enabled ? t("setacc.pause") : t("setacc.syncFull")}
        </button>
      </div>
      {#if backfill?.enabled}
        <div class="bf-prog">
          {#if backfill.complete}
            <span class="bf-done">✓ {t("setacc.backfillDone", { n: backfill.messages.toLocaleString() })}</span>
          {:else}
            <span>{t("setacc.backfillProgress", { done: backfill.folders_done, total: backfill.folders_total, n: backfill.messages.toLocaleString() })}</span>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  <div class="add">
    <h3>{t("setacc.addTitle")}</h3>

    {#if step === "email"}
      <p class="lead">{t("setacc.addLead")}</p>
      <div class="email-row">
        <input
          type="email" placeholder="you@example.com" bind:value={email}
          onkeydown={(e) => e.key === "Enter" && continueEmail()} autofocus
        />
        <button class="btn primary" onclick={continueEmail} disabled={busy}>
          {busy ? t("setacc.checking") : t("setacc.continue")}
        </button>
      </div>
      {#if error}<div class="error">{error}</div>{/if}
    {/if}

    {#if step === "config" && disc}
      <div class="discovered">
        <div class="dhead">
          <div>
            <b>{email}</b>
            <span class="prov">{providerLabel[disc.provider]}</span>
            <span class="src">{t("setacc.detectedViaShort", { source: disc.source })}</span>
          </div>
          <button class="link" onclick={reset}>← {t("setacc.change")}</button>
        </div>
        <div class="force">
          <span>{t("setacc.wrongConnectAs")}</span>
          {#each [["m365","Microsoft 365"],["gmail","Google"],["imap","IMAP / SMTP"]] as [p, lbl]}
            <button class="fbtn" class:on={disc.provider === p} onclick={() => forceProvider(p)}>{lbl}</button>
          {/each}
        </div>
        {#if disc.note}<p class="note">{disc.note}</p>{/if}

        {#if disc.auth === "oauth" && !usePassword}
          <!-- OAuth providers: one button; sign-in is the test -->
          {#if disc.provider === "gmail"}
            <button class="btn primary big" onclick={connectGoogle} disabled={busy}>
              {busy ? t("setacc.waitingGoogle") : t("setacc.signInGoogle")}
            </button>
          {:else if disc.provider === "m365"}
            {#if !msFlow}
              <button class="btn primary big" onclick={startMs} disabled={busy}>
                {busy ? t("setacc.starting") : t("setacc.signInMs")}
              </button>
            {:else}
              <div class="device">
                <p>{t("setacc.msPageOpened")}</p>
                <button class="btn primary" onclick={openMsLogin}>{t("setacc.msOpenAgain")}</button>
                <ol>
                  <li>{t("setacc.msStep1")}</li>
                  <li>{t("setacc.msStep2")} <code class="code">{msFlow.user_code}</code></li>
                  <li>{t("setacc.msStep3")}</li>
                </ol>
                <p class="muted">{t("setacc.msDidntOpen")} <a href={msFlow.verification_uri_complete || msFlow.verification_uri} target="_blank" rel="noreferrer">{msFlow.verification_uri}</a></p>
              </div>
            {/if}
          {/if}
          <button class="link appass" onclick={() => { usePassword = true; error = ''; }}>
            {t("setacc.useAppPass")}
          </button>
        {:else}
          <!-- Password account (incl. OAuth providers via an app password) -->
          {#if usePassword && disc.provider === "gmail"}
            <p class="note">{t("setacc.gmailAppPassA")} <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">myaccount.google.com/apppasswords</a> {t("setacc.gmailAppPassB")}</p>
          {:else if usePassword}
            <p class="note">{t("setacc.providerAppPass")}</p>
          {/if}
          <label class="fld">{t("setacc.yourName")}
            <input bind:value={displayName} placeholder="Jan Novák" />
          </label>
          <label class="fld">{t("setacc.password")}{(usePassword || disc.note?.includes("app")) ? ` ${t("setacc.appPassSuffix")}` : ""}
            <input type="password" bind:value={password}
              onkeydown={(e) => e.key === "Enter" && testAndAdd()} autofocus />
          </label>

          <button class="adv-toggle" onclick={() => (advanced = !advanced)}>
            {advanced ? "▾" : "▸"} {t("setacc.serverSettings")} ({disc.imap_host})
          </button>
          {#if advanced}
            <div class="grid">
              <label>{t("setacc.imapHost")}<input bind:value={disc.imap_host} /></label>
              <label>{t("setacc.imapPort")}<input type="number" bind:value={disc.imap_port} /></label>
              <label>{t("setacc.smtpHost")}<input bind:value={disc.smtp_host} /></label>
              <label>{t("setacc.smtpPort")}<input type="number" bind:value={disc.smtp_port} /></label>
            </div>
          {/if}

          <button class="btn primary big" onclick={testAndAdd} disabled={busy}>
            {busy ? t("setacc.testing") : t("setacc.testAdd")}
          </button>
        {/if}

        {#if error}<div class="error">{error}</div>{/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 26px; }
  .accounts { display: flex; flex-direction: column; gap: 10px; }
  .acct-card { display: flex; align-items: center; gap: 12px; padding: 13px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .reorder { display: flex; flex-direction: column; gap: 1px; flex: none; }
  .ord { color: var(--muted); font-size: 9px; line-height: 1; padding: 3px 4px; border-radius: 4px; }
  .ord:hover:not(:disabled) { background: var(--surface-3); color: var(--text); }
  .ord:disabled { opacity: 0.3; cursor: default; }
  .dot { width: 11px; height: 11px; border-radius: 50%; }
  .colorpick { width: 28px; height: 28px; padding: 2px; border-radius: 50%; border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; flex: none; }
  .info { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .info .namei { border: none; background: transparent; padding: 0; font-weight: 700; color: var(--text); }
  .info .namei:focus { border: none; }
  .info span { color: var(--muted); font-size: 12px; }
  .health { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; margin-top: 5px; }
  .health .st { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text); font-weight: 550; }
  .sdot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .health .meta { font-size: 11px; color: var(--faint); }
  .tag.idle { font-size: 10px; padding: 1px 7px; border-radius: 999px; background: var(--surface-3); color: var(--accent); font-weight: 600; }
  .herr { display: block; margin-top: 4px; font-size: 11px; color: var(--danger); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .idedit { margin: -4px 0 4px; padding: 14px 16px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; gap: 10px; }
  .idedit .muted { font-size: 12px; margin: 0; }
  .idedit code { background: var(--surface-3); padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .idedit textarea { width: 100%; resize: vertical; font-family: var(--mono, monospace); font-size: 13px; }
  .idactions { display: flex; gap: 8px; }
  .srvgrid { display: grid; grid-template-columns: 1fr 110px; gap: 8px 10px; }
  .srvgrid label { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted); }
  .srvgrid input { font-size: 13px; }
  h3 { margin: 0 0 6px; }
  .lead { color: var(--muted); margin: 0 0 14px; }
  .email-row { display: flex; gap: 10px; }
  .email-row input { flex: 1; }
  .discovered { padding: 18px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .dhead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .prov { margin-left: 8px; font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--surface-3); color: var(--accent); }
  .src { margin-left: 8px; font-size: 11px; color: var(--faint); }
  .note { color: var(--muted); font-size: 13px; margin: 4px 0 14px; }
  .force { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 0 0 12px; font-size: 12px; color: var(--muted); }
  .fbtn { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); background: var(--surface-2); }
  .fbtn:hover { color: var(--text); border-color: var(--accent); }
  .fbtn.on { background: var(--accent); border-color: var(--accent); color: #fff; }
  .fld { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); margin-bottom: 12px; }
  .adv-toggle { color: var(--muted); font-size: 12px; margin-bottom: 12px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
  .grid label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  .btn.big { width: 100%; justify-content: center; margin-top: 4px; }
  .link { color: var(--accent); font-size: 13px; }
  .link.appass { display: block; margin-top: 12px; text-align: center; }
  .note a { color: var(--accent); }
  .error { color: var(--danger); font-size: 13px; margin-top: 12px; }
  .muted { color: var(--muted); }
  .device ol { line-height: 2; }
  .code { font-size: 18px; font-weight: 700; letter-spacing: 0.1em; background: var(--surface-3); padding: 3px 10px; border-radius: 6px; }

  .backfill { margin-top: 18px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--surface); }
  .bf-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
  .bf-copy { min-width: 0; }
  .bf-copy h3 { margin: 0 0 4px; font-size: 14px; font-weight: 650; }
  .bf-copy p { margin: 0; font-size: 12.5px; line-height: 1.55; }
  .bf-head .btn { flex: none; white-space: nowrap; }
  .bf-prog { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 13px; color: var(--muted); }
  .bf-done { color: var(--done, #3fb950); font-weight: 550; }
</style>
