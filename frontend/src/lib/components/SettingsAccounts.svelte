<script>
  import { app, loadAccountsAndFolders, notify } from "../store.svelte.js";
  import { accounts as api } from "../api.js";

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

  function reset() {
    step = "email"; email = ""; disc = null; password = ""; displayName = "";
    advanced = false; error = ""; msFlow = null; busy = false;
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

  async function setColor(a, color) { await api.update(a.id, { color }); await loadAccountsAndFolders(); }
  async function rename(a, name) { await api.update(a.id, { display_name: name }); await loadAccountsAndFolders(); }

  const providerLabel = { imap: "IMAP / SMTP", gmail: "Google", m365: "Microsoft 365" };
</script>

<div class="wrap">
  <div class="accounts">
    {#each app.accounts as a}
      <div class="acct-card">
        <input class="colorpick" type="color" value={a.color} title="Account color"
          onchange={(e) => setColor(a, e.currentTarget.value)} />
        <div class="info">
          <input class="namei" value={a.display_name} onchange={(e) => rename(a, e.currentTarget.value)} />
          <span>{a.email} · {a.provider.toUpperCase()}</span>
        </div>
        <button class="btn ghost danger" onclick={() => remove(a)}>Remove</button>
      </div>
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
        {#if disc.note}<p class="note">{disc.note}</p>{/if}

        {#if disc.auth === "oauth"}
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
        {:else}
          <!-- Password account -->
          <label class="fld">Your name (optional)
            <input bind:value={displayName} placeholder="Jan Novák" />
          </label>
          <label class="fld">Password{disc.note?.includes("app") ? " (app password)" : ""}
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
  h3 { margin: 0 0 6px; }
  .lead { color: var(--muted); margin: 0 0 14px; }
  .email-row { display: flex; gap: 10px; }
  .email-row input { flex: 1; }
  .discovered { padding: 18px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .dhead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .prov { margin-left: 8px; font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--surface-3); color: var(--accent); }
  .src { margin-left: 8px; font-size: 11px; color: var(--faint); }
  .note { color: var(--muted); font-size: 13px; margin: 4px 0 14px; }
  .fld { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); margin-bottom: 12px; }
  .adv-toggle { color: var(--muted); font-size: 12px; margin-bottom: 12px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
  .grid label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  .btn.big { width: 100%; justify-content: center; margin-top: 4px; }
  .link { color: var(--accent); font-size: 13px; }
  .error { color: var(--danger); font-size: 13px; margin-top: 12px; }
  .muted { color: var(--muted); }
  .device ol { line-height: 2; }
  .code { font-size: 18px; font-weight: 700; letter-spacing: 0.1em; background: var(--surface-3); padding: 3px 10px; border-radius: 6px; }
</style>
