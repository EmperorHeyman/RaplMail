<script>
  // Sign an existing OAuth account in again after its token died. Microsoft:
  // the same device-code sign-in as adding the account (2FA happens on
  // Microsoft's page), but the backend stores the result on THIS account and
  // refuses a different mailbox. Google: the browser loopback sign-in.
  import { onMount } from "svelte";
  import { app, notify, refreshSigninNeeded } from "../store.svelte.js";
  import { accounts as api, openExternal } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const account = app.accounts.find((a) => a.id === app.reauthAccountId);
  let flow = $state(null);
  let busy = $state(false);
  let error = $state("");
  let copied = $state(false);
  let runId = 0;   // a retry or close abandons the previous attempt's result

  function close() { runId++; app.reauthAccountId = null; }
  function done() {
    notify(t("reauth.done", { email: account.email }));
    app.signinNeeded = app.signinNeeded.filter((id) => id !== account.id);
    close();
    setTimeout(refreshSigninNeeded, 4000);   // after the sync it kicked off
  }
  const verifyUrl = () => flow?.verification_uri_complete || flow?.verification_uri;
  async function copyCode() {
    try { await navigator.clipboard.writeText(flow.user_code); copied = true; } catch {}
  }

  async function startMicrosoft() {
    const run = ++runId;
    error = ""; flow = null; busy = true; copied = false;
    try {
      flow = await api.msStart();
      if (run !== runId) return;
      await copyCode();
      openExternal(verifyUrl());
      await api.msReauth(account.id, flow.flow_id);   // resolves once you finish on Microsoft's page
      if (run === runId) done();
    } catch (e) {
      if (run === runId) { error = e.message || String(e); flow = null; }
    } finally { if (run === runId) busy = false; }
  }
  async function startGoogle() {
    const run = ++runId;
    error = ""; busy = true;
    try { await api.googleReauth(account.id); if (run === runId) done(); }
    catch (e) { if (run === runId) error = e.message || String(e); }
    finally { if (run === runId) busy = false; }
  }
  const isMs = account?.provider === "m365";
  // Conditional Access can block the device-code method outright; signing in
  // again won't help then, so say what will.
  const blocked = $derived(/AADSTS(53003|50199|530033|50097)/.test(error));

  onMount(() => { if (!account) close(); else if (isMs) startMicrosoft(); });
</script>

<svelte:window onkeydown={(e) => { if (e.key === "Escape") close(); }} />

{#if account}
<div class="backdrop" onclick={close} role="presentation">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={t("reauth.title")}>
    <header>
      <h2>{@html icons.lock} {t("reauth.title")}</h2>
      <button class="x" onclick={close} aria-label={t("reauth.close")}>{@html icons.close}</button>
    </header>
    <p class="who"><b>{account.email}</b></p>
    <p class="why">{t(isMs ? "reauth.whyMs" : "reauth.whyGoogle")}</p>

    {#if isMs}
      {#if flow}
        <ol class="steps">
          <li>{t("reauth.step1")} <button class="link" onclick={() => openExternal(verifyUrl())}>{t("reauth.openAgain")}</button></li>
          <li>{t("reauth.step2")}
            <span class="code tnum">{flow.user_code}</span>
            <button class="link" onclick={copyCode}>{copied ? t("reauth.copied") : t("reauth.copy")}</button></li>
          <li>{t("reauth.step3", { email: account.email })}</li>
          <li>{t("reauth.step4")}</li>
        </ol>
        <p class="waiting"><span class="spin"></span> {t("reauth.waiting")}</p>
      {:else if busy}
        <p class="waiting"><span class="spin"></span> {t("reauth.starting")}</p>
      {/if}
    {:else}
      <button class="btn primary" onclick={startGoogle} disabled={busy}>{busy ? t("reauth.waitingGoogle") : t("reauth.signInGoogle")}</button>
    {/if}

    {#if error}
      <div class="err">
        <p>{error}</p>
        {#if blocked}<p class="hint">{t("reauth.blockedHint")}</p>{/if}
        {#if isMs}<button class="btn" onclick={startMicrosoft}>{t("reauth.retry")}</button>{/if}
      </div>
    {/if}
  </div>
</div>
{/if}

<style>
  .backdrop { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,0.45); backdrop-filter: blur(2px);
    display: flex; align-items: flex-start; justify-content: center; padding-top: 12vh; animation: fade-in var(--t) var(--ease); }
  .modal { width: min(520px, 94vw); background: var(--surface); border: 1px solid var(--hairline);
    border-radius: calc(var(--radius) + 3px); box-shadow: var(--shadow-lg); padding: 22px 26px;
    display: flex; flex-direction: column; gap: 12px; animation: pop-in var(--t) var(--ease); }
  header { display: flex; align-items: center; }
  header h2 { margin: 0; font-size: 17px; display: flex; align-items: center; gap: 8px; }
  .x { margin-left: auto; color: var(--muted); }
  .x:hover { color: var(--text); }
  .who { margin: 0; }
  .why { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .steps { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.5; }
  .code { display: inline-block; margin: 0 6px; padding: 2px 8px; border-radius: var(--radius-sm);
    background: var(--surface-2); border: 1px solid var(--border); font-weight: 700; letter-spacing: 0.08em; }
  .link { color: var(--accent); font-size: 13px; }
  .link:hover { text-decoration: underline; }
  .waiting { margin: 0; display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
  .spin { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--border); border-top-color: var(--accent);
    animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .err { padding: 10px 12px; border-radius: var(--radius-sm); background: var(--danger-soft); font-size: 13px;
    display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
  .err p { margin: 0; word-break: break-word; }
  .err .hint { color: var(--muted); }
</style>
