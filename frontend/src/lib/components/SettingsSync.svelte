<script>
  import { onMount } from "svelte";
  import { app, notify, initSettings, saveSettings } from "../store.svelte.js";
  import { api } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let status = $state(null);
  let loading = $state(true);
  let enabled = $state(false);
  let accountId = $state(null);
  let deviceLabel = $state("");
  let passphrase = $state("");
  let changingPass = $state(false);
  let saving = $state(false);
  let syncing = $state(false);
  let pushing = $state(false);
  let pulling = $state(false);
  let snapshots = $state(null);   // null = picker closed; [] = open, none found
  let applyingUid = $state(null);

  async function load() {
    loading = true;
    try {
      status = await api.get("/sync/status");
      enabled = !!status.enabled;
      accountId = status.account_id ?? (app.accounts[0]?.id ?? null);
      deviceLabel = status.device_label || "";
    } catch (e) { notify(e.message, "error"); }
    finally { loading = false; }
  }
  onMount(load);

  const acctEmail = (id) => app.accounts.find((a) => a.id === id)?.email || "";
  const needsPass = $derived(enabled && !status?.has_passphrase && !passphrase);

  async function save() {
    if (enabled && accountId == null) { notify(t("dsync.needAccount"), "error"); return; }
    if (needsPass) { notify(t("dsync.needPassphrase"), "error"); return; }
    if (passphrase && passphrase.length < 8) { notify(t("dsync.passTooShort"), "error"); return; }
    saving = true;
    try {
      status = await api.put("/sync/config", {
        enabled,
        account_id: enabled ? accountId : null,
        passphrase: passphrase || null,
        device_label: deviceLabel,
      });
      passphrase = ""; changingPass = false;
      enabled = !!status.enabled;
      accountId = status.account_id ?? accountId;
      deviceLabel = status.device_label || "";
      notify(t("dsync.saved"));
    } catch (e) { notify(e.message, "error"); }
    finally { saving = false; }
  }

  async function syncNow() {
    syncing = true;
    try {
      status = await api.post("/sync/now");
      notify(status.last_error ? t("dsync.syncedWithError") : t("dsync.syncedNow"));
    } catch (e) { notify(e.message, "error"); }
    finally { syncing = false; }
  }

  function fmt(iso) {
    if (!iso) return t("dsync.never");
    try { return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  }

  async function pushConfig() {
    pushing = true;
    try {
      await api.post("/sync/push-config");
      notify(t("dsync.pushed"));
    } catch (e) { notify(e.message, "error"); }
    finally { pushing = false; }
  }

  async function openPull() {
    pulling = true;
    try {
      const res = await api.get("/sync/config-snapshots");
      snapshots = res.snapshots || [];
    } catch (e) { notify(e.message, "error"); snapshots = null; }
    finally { pulling = false; }
  }

  async function applySnapshot(snap) {
    applyingUid = snap.uid;
    try {
      const res = await api.post("/sync/pull-config", { uid: snap.uid });
      await initSettings();   // rehydrate the live UI from the freshly-applied blob
      notify(t("dsync.applied", { label: res.label || snap.device_label }));
      snapshots = null;
    } catch (e) { notify(e.message, "error"); }
    finally { applyingUid = null; }
  }

  // --- encrypted credential sync (opt-in, second independent key) ----------
  const credEnabled = $derived(app.settings.syncCredEnabled === true);
  let credMode = $state(app.settings.syncCredMode || "passphrase");
  let credPushSecret = $state("");
  let credPushing = $state(false);
  let credPulling = $state(false);
  let credSnaps = $state(null);        // null = closed; [] = open, none found
  let credStage = $state("list");      // list | secret | accounts
  let credSecret = $state("");         // secret entered for the pull in progress
  let credAccounts = $state([]);       // decrypted preview list
  let credChosen = $state({});         // email -> import?
  let credUid = $state(null);
  let credBusy = $state(false);
  const credPromptHint = $derived(credMode === "master" ? t("dsync.credMasterHint") : t("dsync.credPassHint"));

  function setCredEnabled(on) { saveSettings({ syncCredEnabled: on }); }
  function setCredMode(m) { credMode = m; saveSettings({ syncCredMode: m }); }

  async function credPush() {
    if (!credPushSecret || credPushSecret.length < 8) { notify(t("dsync.passTooShort"), "error"); return; }
    credPushing = true;
    try {
      const res = await api.post("/sync/push-credentials", { secret: credPushSecret });
      notify(t("dsync.credPushed", { n: res.count }));
      credPushSecret = "";
    } catch (e) { notify(e.message, "error"); }
    finally { credPushing = false; }
  }

  async function credOpenPull() {
    credPulling = true;
    try {
      const res = await api.get("/sync/credential-snapshots");
      credSnaps = res.snapshots || [];
      credStage = "list"; credSecret = ""; credAccounts = []; credChosen = {}; credUid = null;
    } catch (e) { notify(e.message, "error"); credSnaps = null; }
    finally { credPulling = false; }
  }

  function credChoose(snap) { credUid = snap.uid; credSecret = ""; credStage = "secret"; }

  async function credUnlock() {
    if (!credSecret) return;
    credBusy = true;
    try {
      const res = await api.post("/sync/credential-preview", { uid: credUid, secret: credSecret });
      credAccounts = res.accounts || [];
      // Pre-tick every account this device doesn't already have.
      credChosen = Object.fromEntries(credAccounts.filter((a) => !a.exists).map((a) => [a.email, true]));
      credStage = "accounts";
    } catch (e) { notify(e.message, "error"); }
    finally { credBusy = false; }
  }

  async function credApply() {
    const emails = Object.entries(credChosen).filter(([, v]) => v).map(([k]) => k);
    if (!emails.length) { notify(t("dsync.credPickOne"), "error"); return; }
    credBusy = true;
    try {
      const res = await api.post("/sync/pull-credentials", { uid: credUid, secret: credSecret, emails });
      notify(t("dsync.credImported", { n: res.imported }));
      credSnaps = null; credSecret = "";
      await initSettings();
    } catch (e) { notify(e.message, "error"); }
    finally { credBusy = false; }
  }
</script>

<div class="sync">
  <p class="intro">{t("dsync.intro")}</p>

  {#if loading}
    <div class="muted">{t("dsync.loading")}</div>
  {:else}
    <div class="card">
      <label class="row toggle">
        <span class="lbl">
          <b>{t("dsync.enable")}</b>
          <span class="hint">{t("dsync.enableHint")}</span>
        </span>
        <input type="checkbox" bind:checked={enabled} />
      </label>

      {#if enabled}
        <label class="row">
          <span class="lbl"><b>{t("dsync.deviceName")}</b><span class="hint">{t("dsync.deviceNameHint")}</span></span>
          <input type="text" bind:value={deviceLabel} maxlength="40"
            placeholder={t("dsync.deviceNamePlaceholder")} />
        </label>

        <label class="row">
          <span class="lbl"><b>{t("dsync.account")}</b><span class="hint">{t("dsync.accountHint")}</span></span>
          <select bind:value={accountId}>
            {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
          </select>
        </label>

        <div class="row">
          <span class="lbl"><b>{t("dsync.passphrase")}</b><span class="hint">{t("dsync.passphraseHint")}</span></span>
          <div class="passcol">
            {#if status?.has_passphrase && !changingPass}
              <div class="passset">{@html icons.shieldCheck} {t("dsync.passphraseSet")}
                <button class="link" onclick={() => (changingPass = true)}>{t("dsync.change")}</button>
              </div>
            {:else}
              <input type="password" bind:value={passphrase} placeholder={t("dsync.passphrasePlaceholder")}
                autocomplete="new-password" />
            {/if}
          </div>
        </div>
      {/if}

      <div class="actions">
        <button class="btn primary" onclick={save} disabled={saving}>{saving ? t("dsync.saving") : t("dsync.save")}</button>
        {#if status?.enabled}
          <button class="btn" onclick={syncNow} disabled={syncing}>
            {@html icons.sync} {syncing ? t("dsync.syncingNow") : t("dsync.syncNow")}
          </button>
        {/if}
      </div>
    </div>

    {#if status?.enabled}
      <div class="card statuscard">
        <div class="st"><span>{t("dsync.stAccount")}</span><b>{acctEmail(status.account_id) || "-"}</b></div>
        <div class="st"><span>{t("dsync.stLastSynced")}</span><b>{fmt(status.last_at)}</b></div>
        {#if status.last_error}
          <div class="st err"><span>{t("dsync.stLastError")}</span><b>{status.last_error}</b></div>
        {/if}
        <div class="st"><span>{t("dsync.stDevice")}</span>
          <b>{status.device_label || "-"} <span class="devid">{(status.device_id || "").slice(0, 8)}</span></b></div>
      </div>

      {#if status.has_passphrase}
        <div class="card">
          <div class="cfghead">
            <b>{t("dsync.cfgTitle")}</b>
            <span class="hint">{t("dsync.cfgIntro")}</span>
          </div>
          <div class="actions">
            <button class="btn" onclick={pushConfig} disabled={pushing}>
              {@html icons.upload || icons.sync} {pushing ? t("dsync.pushing") : t("dsync.pushBtn")}
            </button>
            <button class="btn" onclick={openPull} disabled={pulling}>
              {@html icons.download || icons.sync} {pulling ? t("dsync.pullLoading") : t("dsync.pullBtn")}
            </button>
          </div>
        </div>

        <div class="card credcard">
          <label class="row toggle">
            <span class="lbl">
              <b>{@html icons.shieldCheck || ""} {t("dsync.credTitle")}</b>
              <span class="hint">{t("dsync.credIntro")}</span>
            </span>
            <input type="checkbox" checked={credEnabled} onchange={(e) => setCredEnabled(e.currentTarget.checked)} />
          </label>

          {#if credEnabled}
            <div class="warn">{@html icons.warning || ""} {t("dsync.credWarn")}</div>

            <div class="row">
              <span class="lbl"><b>{t("dsync.credMode")}</b><span class="hint">{t("dsync.credModeHint")}</span></span>
              <select value={credMode} onchange={(e) => setCredMode(e.currentTarget.value)}>
                <option value="passphrase">{t("dsync.credModePass")}</option>
                <option value="master">{t("dsync.credModeMaster")}</option>
              </select>
            </div>

            <div class="row">
              <span class="lbl"><b>{t("dsync.credPushLabel")}</b><span class="hint">{credPromptHint}</span></span>
              <div class="passcol">
                <input type="password" bind:value={credPushSecret} autocomplete="new-password"
                  placeholder={credMode === "master" ? t("dsync.credMasterPh") : t("dsync.credPassPh")} />
              </div>
            </div>

            <div class="actions">
              <button class="btn" onclick={credPush} disabled={credPushing || !credPushSecret}>
                {@html icons.upload || icons.sync} {credPushing ? t("dsync.pushing") : t("dsync.credPushBtn")}
              </button>
              <button class="btn" onclick={credOpenPull} disabled={credPulling}>
                {@html icons.download || icons.sync} {credPulling ? t("dsync.pullLoading") : t("dsync.credPullBtn")}
              </button>
            </div>
          {/if}
        </div>
      {/if}
    {/if}

    {#if snapshots !== null}
      <div class="modal-backdrop" onclick={() => (snapshots = null)} role="presentation">
        <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          <h2>{t("dsync.snapTitle")}</h2>
          <p class="snaphint">{t("dsync.snapHint")}</p>
          {#if snapshots.length === 0}
            <div class="muted empty">{t("dsync.noSnapshots")}</div>
          {:else}
            <div class="snaps">
              {#each snapshots as snap (snap.uid)}
                <div class="snap">
                  <div class="snapinfo">
                    <div class="snaptop">
                      <b>{snap.device_label}</b>
                      {#if snap.is_me}<span class="tag">{t("dsync.snapThisDevice")}</span>{/if}
                    </div>
                    <div class="snapmeta">{t("dsync.snapPushed")}: {fmt(snap.published_at)}</div>
                    {#if snap.config_changed_at}
                      <div class="snapmeta">{t("dsync.snapChanged")}: {fmt(snap.config_changed_at)}</div>
                    {/if}
                    <div class="snapmeta">
                      {t("dsync.snapSummary", { rules: snap.summary.rules, signatures: snap.summary.signatures, cats: snap.summary.sender_categories })}
                    </div>
                  </div>
                  <button class="btn primary" onclick={() => applySnapshot(snap)} disabled={applyingUid != null}>
                    {applyingUid === snap.uid ? t("dsync.applying") : t("dsync.snapApply")}
                  </button>
                </div>
              {/each}
            </div>
          {/if}
          <div class="modal-actions">
            <button class="btn" onclick={() => (snapshots = null)}>{t("dsync.close")}</button>
          </div>
        </div>
      </div>
    {/if}

    {#if credSnaps !== null}
      <div class="modal-backdrop" onclick={() => (credSnaps = null)} role="presentation">
        <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          {#if credStage === "list"}
            <h2>{t("dsync.credPullTitle")}</h2>
            <p class="snaphint">{t("dsync.credPullHint")}</p>
            {#if credSnaps.length === 0}
              <div class="muted empty">{t("dsync.credNone")}</div>
            {:else}
              <div class="snaps">
                {#each credSnaps as snap (snap.uid)}
                  <div class="snap">
                    <div class="snapinfo">
                      <div class="snaptop">
                        <b>{snap.device_label}</b>
                        {#if snap.is_me}<span class="tag">{t("dsync.snapThisDevice")}</span>{/if}
                      </div>
                      <div class="snapmeta">{t("dsync.snapPushed")}: {fmt(snap.published_at)}</div>
                      <div class="snapmeta">{t("dsync.credCount", { n: snap.count })}</div>
                    </div>
                    <button class="btn primary" onclick={() => credChoose(snap)}>{t("dsync.credChoose")}</button>
                  </div>
                {/each}
              </div>
            {/if}
          {:else if credStage === "secret"}
            <h2>{t("dsync.credEnterTitle")}</h2>
            <p class="snaphint">{credPromptHint}</p>
            <input class="fullpw" type="password" bind:value={credSecret} autocomplete="off"
              placeholder={credMode === "master" ? t("dsync.credMasterPh") : t("dsync.credPassPh")}
              onkeydown={(e) => e.key === "Enter" && credUnlock()} />
          {:else}
            <h2>{t("dsync.credChooseTitle")}</h2>
            <p class="snaphint">{t("dsync.credChooseHint")}</p>
            <div class="credlist">
              {#each credAccounts as a (a.email)}
                <label class="credrow" class:dim={a.exists}>
                  <input type="checkbox" checked={!!credChosen[a.email]} disabled={a.exists}
                    onchange={(e) => (credChosen = { ...credChosen, [a.email]: e.currentTarget.checked })} />
                  <div class="credmeta">
                    <b>{a.email}</b>
                    <span>{a.provider}{a.exists ? " · " + t("dsync.credExists") : ""}</span>
                  </div>
                </label>
              {/each}
            </div>
          {/if}
          <div class="modal-actions">
            <button class="btn" onclick={() => (credSnaps = null)}>{t("dsync.close")}</button>
            {#if credStage === "secret"}
              <button class="btn primary" onclick={credUnlock} disabled={credBusy || !credSecret}>
                {credBusy ? t("dsync.pullLoading") : t("dsync.credUnlock")}</button>
            {:else if credStage === "accounts"}
              <button class="btn primary" onclick={credApply} disabled={credBusy}>
                {credBusy ? t("dsync.applying") : t("dsync.credImport")}</button>
            {/if}
          </div>
        </div>
      </div>
    {/if}

    <div class="how">
      <h3>{t("dsync.howTitle")}</h3>
      <ul>
        <li>{t("dsync.how1")}</li>
        <li>{t("dsync.how2")}</li>
        <li>{t("dsync.how3")}</li>
        <li>{t("dsync.how4")}</li>
      </ul>
    </div>
  {/if}
</div>

<style>
  .sync { max-width: 640px; display: flex; flex-direction: column; gap: 16px; }
  .intro { color: var(--muted); font-size: 13.5px; line-height: 1.6; margin: 0; }
  .muted { color: var(--muted); }
  .card { display: flex; flex-direction: column; gap: 14px; padding: 16px; border: 1px solid var(--border);
    border-radius: var(--radius); background: var(--surface); }
  .row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
  .row.toggle { align-items: center; }
  .lbl { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .lbl b { font-size: 14px; font-weight: 600; }
  .hint { color: var(--muted); font-size: 12.5px; line-height: 1.5; }
  select, input[type="password"], input[type="text"] { flex: none; width: 260px; max-width: 50%; padding: 8px 10px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); }
  select:focus, input:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent); }
  .passcol { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
  .passset { display: inline-flex; align-items: center; gap: 6px; color: var(--done); font-size: 13px; font-weight: 550; }
  .passset :global(svg) { width: 15px; height: 15px; }
  .link { color: var(--accent); font-size: 12px; font-weight: 600; margin-left: 4px; }
  input[type="checkbox"] { width: auto; }
  .actions { display: flex; gap: 10px; padding-top: 4px; }
  .btn { padding: 8px 14px; border-radius: var(--radius-sm); background: var(--surface-3); font-size: 13px; font-weight: 550;
    display: inline-flex; align-items: center; gap: 7px; }
  .btn:hover { background: color-mix(in srgb, var(--surface-3) 76%, var(--text) 10%); }
  .btn:disabled { opacity: 0.6; }
  .btn :global(svg) { width: 15px; height: 15px; }
  .btn.primary { background: var(--accent); color: #fff; }
  .btn.primary:hover { background: color-mix(in srgb, var(--accent) 88%, #000); }
  .statuscard { gap: 8px; }
  .st { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
  .st span { color: var(--muted); }
  .st.err b { color: var(--danger); font-weight: 550; text-align: right; }
  .devid { font-family: ui-monospace, monospace; color: var(--faint); font-weight: 400; font-size: 12px; }
  .how { padding: 0 2px; }
  .how h3 { margin: 0 0 8px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); }
  .how ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; color: var(--muted); font-size: 13px; line-height: 1.55; }

  .cfghead { display: flex; flex-direction: column; gap: 4px; }
  .cfghead b { font-size: 14px; font-weight: 600; }

  .credcard .lbl b { display: inline-flex; align-items: center; gap: 6px; }
  .credcard .lbl b :global(svg) { width: 15px; height: 15px; }
  .warn { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger);
    font-size: 12.5px; line-height: 1.5; }
  .warn :global(svg) { width: 16px; height: 16px; flex: none; margin-top: 1px; }
  .fullpw { width: 100%; padding: 9px 11px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text); }
  .credlist { display: flex; flex-direction: column; gap: 6px; max-height: 46vh; overflow-y: auto; }
  .credrow { display: flex; align-items: center; gap: 11px; padding: 10px 12px; border: 1px solid var(--border);
    border-radius: var(--radius-sm); background: var(--surface-2); cursor: pointer; }
  .credrow.dim { opacity: 0.55; cursor: default; }
  .credrow input { width: 16px; height: 16px; accent-color: var(--accent); flex: none; }
  .credmeta { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .credmeta b { font-size: 13.5px; }
  .credmeta span { font-size: 12px; color: var(--muted); }

  .modal-backdrop { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,0.45);
    display: flex; align-items: center; justify-content: center; padding: 20px; }
  .modal { width: 100%; max-width: 520px; max-height: 80vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px;
    padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    box-shadow: 0 12px 40px rgba(0,0,0,0.35); }
  .modal h2 { margin: 0; font-size: 16px; font-weight: 650; }
  .snaphint { margin: 0; color: var(--muted); font-size: 12.5px; line-height: 1.55; }
  .empty { padding: 18px 4px; text-align: center; font-size: 13px; }
  .snaps { display: flex; flex-direction: column; gap: 10px; }
  .snap { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px;
    border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); }
  .snapinfo { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .snaptop { display: flex; align-items: center; gap: 8px; }
  .snaptop b { font-size: 13.5px; font-weight: 600; }
  .tag { font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); }
  .snapmeta { color: var(--muted); font-size: 12px; }
  .modal-actions { display: flex; justify-content: flex-end; padding-top: 4px; }
</style>
