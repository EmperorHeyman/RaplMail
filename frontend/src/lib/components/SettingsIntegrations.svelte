<script>
  // Settings → Integrations: RaplMail talking to other systems - the local
  // metrics API and new-mail webhook (from the old General tab) and RAPL Desk
  // ticketing (which used to be a tab of its own).
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { backendBase } from "../api.js";
  import SettingsRaplDesk from "./SettingsRaplDesk.svelte";
  import { t } from "../i18n.svelte.js";

  function randomKey() {
    const b = new Uint8Array(24); crypto.getRandomValues(b);
    return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  }
  function toggleLocalApi(on) {
    const patch = { localApiEnabled: on };
    if (on && !app.settings.localApiKey) patch.localApiKey = randomKey();
    saveSettings(patch);
  }
  function regenKey() {
    if (!confirm(t("sInteg.regenConfirm"))) return;
    saveSettings({ localApiKey: randomKey() });
  }
  const metricsUrl = $derived(`${backendBase()}/metrics`);
  const curl = $derived(`curl -H "X-API-Key: ${app.settings.localApiKey}" ${metricsUrl}`);
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify(t("reader.copied")); }
    catch { notify(t("reader.couldntCopy"), "error"); }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sInteg.apiTitle")} <span class="tag">{t("sInteg.developer")}</span></h3>
    <p class="hint">{t("sInteg.apiHint")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.localApiEnabled}
        onchange={(e) => toggleLocalApi(e.currentTarget.checked)} />
      <div><b>{t("sInteg.enable")}</b><span>{t("sInteg.enableHint")}</span></div>
    </label>
    {#if app.settings.localApiEnabled}
      <div class="apibox">
        <div class="kv"><span>{t("sInteg.url")}</span>
          <code>{metricsUrl}</code>
          <button class="btn ghost" onclick={() => copy(metricsUrl)}>{t("sInteg.copy")}</button>
        </div>
        <div class="kv"><span>{t("sInteg.key")}</span>
          <code class="key">{app.settings.localApiKey || "-"}</code>
          <button class="btn ghost" onclick={() => copy(app.settings.localApiKey)}>{t("sInteg.copy")}</button>
          <button class="btn ghost" onclick={regenKey}>{t("sInteg.regen")}</button>
        </div>
        <div class="kv"><span>{t("sInteg.test")}</span>
          <code>{curl}</code>
          <button class="btn ghost" onclick={() => copy(curl)}>{t("sInteg.copy")}</button>
        </div>
        <p class="hint">{t("sInteg.apiDoc")}</p>
      </div>
    {/if}
    <div class="hookrow">
      <div class="lblcol"><b>{t("sInteg.webhook")}</b>
        <span class="hint" style="margin:2px 0 0">{t("sInteg.webhookHint")}</span></div>
      <input type="url" placeholder="http://127.0.0.1:5678/webhook/raplmail" value={app.settings.newMailWebhook || ""}
        onchange={(e) => saveSettings({ newMailWebhook: e.currentTarget.value.trim() })} />
    </div>
  </section>

  <h2 class="sec">RAPL Desk</h2>
  <SettingsRaplDesk />
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 20px; }
  .card { max-width: 640px; box-sizing: border-box; padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
  .tag { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 2px 7px; border-radius: 999px; background: var(--surface-3); color: var(--accent); vertical-align: middle; margin-left: 6px; }
  .apibox { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
  .apibox .hint { margin: 4px 0 0; }
  .kv { display: flex; align-items: center; gap: 10px; }
  .kv > span:first-child { width: 64px; flex: none; color: var(--muted); font-size: 12px; }
  .kv code { flex: 1; min-width: 0; background: var(--surface-2); border: 1px solid var(--border); padding: 5px 9px; border-radius: var(--radius-sm); font-size: 12px; overflow-x: auto; white-space: nowrap; }
  .kv code.key { letter-spacing: 0.04em; }
  .hookrow { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
  .hookrow .lblcol { display: flex; flex-direction: column; }
  .hookrow .lblcol b { font-size: 13.5px; }
  .hookrow input { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; font-size: 13px; max-width: 420px; }
  .sec { margin: 14px 0 -6px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); }
</style>
