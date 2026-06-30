<script>
  import { onMount, onDestroy } from "svelte";
  import { app, loadAccountsAndFolders, notify } from "../store.svelte.js";
  import { accounts as api } from "../api.js";
  import { relativeTime } from "../time.js";

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
  onMount(() => { refreshHealth(); healthTimer = setInterval(refreshHealth, 5000); });
  onDestroy(() => clearInterval(healthTimer));

  const STATUS = {
    ok:       { dot: "#3fb950", text: "Connected" },
    syncing:  { dot: "#3b82f6", text: "Syncing…" },
    error:    { dot: "#f85149", text: "Error" },
    idle:     { dot: "#8b949e", text: "Idle" },
    disabled: { dot: "#6e7681", text: "Disabled" },
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
    if (!email.includes("@")) { error = "Enter a full email address."; return; }
    busy = true;
    try {
      disc = await api.autodiscover(email);
      step = "config";
    } catch (e) { error = e.message; } finally { busy = false; }
  }

  // Override a wrong auto-detect (e.g. an M365 tenant that looks like plain IMAP).
  function forceProvider(p) {
    usePassword = false; msFlow = null; error = "";
    if (p === "m365") disc = { ...disc, provider: "m365", auth: "oauth", source: "manual choice", note: "" };
    else if (p === "gmail") disc = { ...disc, provider: "gmail", auth: "oauth", source: "manual choice", note: "" };
    else disc = { ...disc, provider: "imap", auth: "password", source: "manual choice",
                  imap_host: disc.imap_host || "", smtp_host: disc.smtp_host || "" };
  }

  // OAuth providers — the sign-in itself is the connection test.
  async function connectGoogle() {
    busy = true; error = "";
    notify("Opening browser to sign in with Google…");
    try { await api.googleConnect(); notify("Gmail connected"); app.syncing = true; await loadAccountsAndFolders(); reset(); }
    catch (e) { error = e.message; } finally { busy = false; }
  }

  async function startMs() {
    busy = true; error = "";
    try {
      msFlow = await api.msStart();
      openMsLogin();  // auto-open the Microsoft page + copy the code
      api.msComplete(msFlow.flow_id)
        .then(async () => { notify("Microsoft account connected"); app.syncing = true; await loadAccountsAndFolders(); reset(); })
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

  // Password account — verifies the connection before adding.
  async function testAndAdd() {
    error = "";
    if (!password) { error = "Enter your password."; return; }
    busy = true;
    try {
      await api.createImap({
        email, display_name: displayName,
        password,
        imap_host: disc.imap_host, imap_port: disc.imap_port, imap_ssl: disc.imap_ssl,
        smtp_host: disc.smtp_host, smtp_port: disc.smtp_port,
      });
      notify("Connected ✓ — syncing your mail");
      app.syncing = true;
      await loadAccountsAndFolders();
      reset();
    } catch (e) { error = e.message; } finally { busy = false; }
  }

  async function remove(a) {
    if (!confirm(`Remove ${a.email}? Stored credentials will be deleted.`)) return;
    await api.remove(a.id);
    await loadAccountsAndFolders();
    notify("Account removed");
  }

  async function triggerSync(a) {
    try { await api.sync(a.id); notify(`Syncing ${a.email}…`); setTimeout(refreshHealth, 600); }
    catch (e) { notify(e.message, "error"); }
  }

  // Re-enter the password for a password account (fixes "no saved password").
  async function reconnect(a) {
    const pw = prompt(`Enter the password for ${a.email}:`);
    if (!pw) return;
    try {
      await api.reconnect(a.id, pw);
      notify("Reconnected ✓ — syncing");
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
    try { await api.update(a.id, { aliases }); await loadAccountsAndFolders(); idEdit = null; notify("Identities saved"); }
    catch (e) { notify(e.message, "error"); }
  }

  async function setColor(a, color) { await api.update(a.id, { color }); await loadAccountsAndFolders(); }
  async function rename(a, name) { await api.update(a.id, { display_name: name }); await loadAccountsAndFolders(); }

  const providerLabel = { imap: "IMAP / SMTP", gmail: "Google", m365: "Microsoft 365" };
</script>

<div class="wrap">
  <div class="accounts">
    {#each app.accounts as a}
      {@const h = health[a.id]}
      {@const st = stMeta(h?.status)}
      <div class="acct-card">
        <input class="colorpick" type="color" value={a.color} title="Account color"
          onchange={(e) => setColor(a, e.currentTarget.value)} />
        <div class="info">
          <input class="namei" value={a.display_name} onchange={(e) => rename(a, e.currentTarget.value)} />
          <span>{a.email} · {a.provider.toUpperCase()}</span>
          {#if h}
            <div class="health">
              <span class="st" title={st.text}><span class="sdot" style="background:{st.dot}"></span>{st.text}</span>
              {#if h.idle_active}<span class="tag idle" title="Live push connection (IMAP IDLE) is active">⚡ live</span>{/if}
              <span class="meta">{h.messages.toLocaleString()} msgs · {h.folders} folders</span>
              {#if h.last_sync}<span class="meta">synced {relativeTime(h.last_sync)}</span>{/if}
            </div>
            {#if h.last_error}
              <span class="herr" title={h.last_error}>⚠ {h.last_error.slice(0, 80)}{h.last_error.length > 80 ? "…" : ""}</span>
            {/if}
          {/if}
        </div>
        <button class="btn ghost" onclick={() => openIdentities(a)} title="Send-as identities">
          Identities{a.aliases?.length ? ` (${a.aliases.length})` : ""}
        </button>
        {#if a.provider === "imap"}
          <button class="btn ghost" onclick={() => reconnect(a)} title="Re-enter / fix the password for this account">Reconnect</button>
        {/if}
        <button class="btn ghost" onclick={() => triggerSync(a)} disabled={h?.status === "syncing"} title="Sync now">↻</button>
        <button class="btn ghost danger" onclick={() => remove(a)}>Remove</button>
      </div>
      {#if idEdit === a.id}
        <div class="idedit">
          <p class="muted">One identity per line — a plain address or <code>Name &lt;addr@host&gt;</code>. The server sends as it only if it recognizes the address. Your primary address ({a.email}) is always available.</p>
          <textarea bind:value={idText} rows="3" placeholder={"Sales <sales@" + (a.email.split("@")[1] || "company.com") + ">\nme+side@" + (a.email.split("@")[1] || "company.com")}></textarea>
          <div class="idactions">
            <button class="btn primary" onclick={() => saveAliases(a)}>Save identities</button>
            <button class="btn ghost" onclick={() => (idEdit = null)}>Cancel</button>
          </div>
        </div>
      {/if}
    {/each}
    {#if app.accounts.length === 0}
      <p class="muted">No accounts yet. Add your first below — just type your email.</p>
    {/if}
  </div>

  <div class="add">
    <h3>Add an account</h3>

    {#if step === "email"}
      <p class="lead">Type your email address — RaplMail figures out the rest.</p>
      <div class="email-row">
        <input
          type="email" placeholder="you@example.com" bind:value={email}
          onkeydown={(e) => e.key === "Enter" && continueEmail()} autofocus
        />
        <button class="btn primary" onclick={continueEmail} disabled={busy}>
          {busy ? "Checking…" : "Continue"}
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
            <span class="src">detected via {disc.source}</span>
          </div>
          <button class="link" onclick={reset}>← change</button>
        </div>
        <div class="force">
          <span>Wrong? Connect as:</span>
          {#each [["m365","Microsoft 365"],["gmail","Google"],["imap","IMAP / SMTP"]] as [p, lbl]}
            <button class="fbtn" class:on={disc.provider === p} onclick={() => forceProvider(p)}>{lbl}</button>
          {/each}
        </div>
        {#if disc.note}<p class="note">{disc.note}</p>{/if}

        {#if disc.auth === "oauth" && !usePassword}
          <!-- OAuth providers: one button; sign-in is the test -->
          {#if disc.provider === "gmail"}
            <button class="btn primary big" onclick={connectGoogle} disabled={busy}>
              {busy ? "Waiting for Google…" : "Sign in with Google"}
            </button>
          {:else if disc.provider === "m365"}
            {#if !msFlow}
              <button class="btn primary big" onclick={startMs} disabled={busy}>
                {busy ? "Starting…" : "Sign in with Microsoft"}
              </button>
            {:else}
              <div class="device">
                <p>A Microsoft sign-in page should have opened (code copied to your clipboard).</p>
                <button class="btn primary" onclick={openMsLogin}>Open Microsoft sign-in again</button>
                <ol>
                  <li>On the page, sign in as your a123systems account.</li>
                  <li>If asked for a code, paste / enter: <code class="code">{msFlow.user_code}</code></li>
                  <li>Come back here — it connects automatically.</li>
                </ol>
                <p class="muted">Didn't open? <a href={msFlow.verification_uri_complete || msFlow.verification_uri} target="_blank" rel="noreferrer">{msFlow.verification_uri}</a></p>
              </div>
            {/if}
          {/if}
          <button class="link appass" onclick={() => { usePassword = true; error = ''; }}>
            Use an app password instead (no Google/Microsoft sign-in)
          </button>
        {:else}
          <!-- Password account (incl. OAuth providers via an app password) -->
          {#if usePassword && disc.provider === "gmail"}
            <p class="note">Create an app password at <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">myaccount.google.com/apppasswords</a> (needs 2-Step Verification on), then paste the 16-character code below — no Google verification required.</p>
          {:else if usePassword}
            <p class="note">Use an app password from your provider (not your normal login password).</p>
          {/if}
          <label class="fld">Your name (optional)
            <input bind:value={displayName} placeholder="Jan Novák" />
          </label>
          <label class="fld">Password{(usePassword || disc.note?.includes("app")) ? " (app password)" : ""}
            <input type="password" bind:value={password}
              onkeydown={(e) => e.key === "Enter" && testAndAdd()} autofocus />
          </label>

          <button class="adv-toggle" onclick={() => (advanced = !advanced)}>
            {advanced ? "▾" : "▸"} Server settings ({disc.imap_host})
          </button>
          {#if advanced}
            <div class="grid">
              <label>IMAP host<input bind:value={disc.imap_host} /></label>
              <label>IMAP port<input type="number" bind:value={disc.imap_port} /></label>
              <label>SMTP host<input bind:value={disc.smtp_host} /></label>
              <label>SMTP port<input type="number" bind:value={disc.smtp_port} /></label>
            </div>
          {/if}

          <button class="btn primary big" onclick={testAndAdd} disabled={busy}>
            {busy ? "Testing connection…" : "Test connection & add"}
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
</style>
