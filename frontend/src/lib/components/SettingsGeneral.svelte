<script>
  // Settings → General: the app itself - language, updates, tray and startup.
  // It used to hold ~15 unrelated topics; those now live in Inbox, Compose,
  // Notifications, Backup & sync and Integrations.
  import { app, checkForUpdates, saveSettings, setAutostart, setCloseToTray, setLanguage, WEBSITE } from "../store.svelte.js";
  import { openExternal } from "../api.js";
  import { dateLocale } from "../time.svelte.js";
  import { icons } from "../icons.js";
  import { t, LANGUAGES } from "../i18n.svelte.js";

  const u = $derived(app.update);
  const pct = $derived(u.total ? Math.min(100, Math.round((u.got / u.total) * 100)) : 0);
  const checkedAt = $derived(u.checkedAt
    ? new Date(u.checkedAt).toLocaleTimeString(dateLocale(), { hour: "2-digit", minute: "2-digit" }) : "");
  const status = $derived(
    u.state === "checking" ? t("update.checking")
    : u.state === "downloading" ? t("update.downloadingTitle", { version: u.version }) + " " + t("update.downloading", { pct })
    : u.state === "ready" || u.state === "installing" ? t("update.readyTitle", { version: u.version })
    : u.state === "none" ? t("update.upToDateAt", { time: checkedAt })
    : u.state === "error" ? t("update.checkFailed", { err: u.error }) : "");
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("settings.language")}</h3>
    <p class="hint">{t("settings.languageHint")}</p>
    <label class="inline">{t("settings.language")}
      <select value={app.settings.language || "auto"} onchange={(e) => setLanguage(e.currentTarget.value)}>
        {#each LANGUAGES as l}<option value={l.id}>{l.label}</option>{/each}
      </select>
    </label>
  </section>

  <section class="card">
    <h3>{t("sGen.updates")}</h3>
    <p class="hint">{t("sGen.updatesHint")}</p>
    {#if u.current}<p class="ver">{t("update.version", { version: u.current })}</p>{/if}
    {#if status}<p class="status" class:err={u.state === "error"} class:ok={u.state === "ready"}>{status}</p>{/if}
    {#if u.state === "downloading"}<div class="prog"><div class="bar" style="width:{pct}%"></div></div>{/if}
    <div class="rowbtns">
      {#if u.state === "ready" || u.state === "installing"}
        <button class="btn primary" onclick={() => (app.updateDialog = true)}>{@html icons.reset} {t("update.restartNow")}</button>
      {:else}
        <button class="btn primary" onclick={() => checkForUpdates()} disabled={u.state === "checking" || u.state === "downloading"}>{@html icons.sync} {t("sGen.check")}</button>
      {/if}
      <button class="btn ghost" onclick={() => openExternal(WEBSITE + "/#changelog")}>{t("update.whatsNewSite")}</button>
    </div>
    <label class="check">
      <input type="checkbox" checked={app.settings.autoUpdate !== false} onchange={(e) => saveSettings({ autoUpdate: e.currentTarget.checked })} />
      <div><b>{t("update.auto")}</b><span>{t("update.autoHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("sGen.tray")}</h3>
    <p class="hint">{t("sGen.trayHint")}</p>
    <label class="check">
      <input type="checkbox" checked={app.settings.minimizeToTray !== false}
        onchange={(e) => setCloseToTray(e.currentTarget.checked)} />
      <div><b>{t("sGen.minimize")}</b><span>{t("sGen.minimizeHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.launchOnStartup}
        onchange={(e) => setAutostart(e.currentTarget.checked)} />
      <div><b>{t("sGen.launch")}</b><span>{t("sGen.launchHint")}</span></div>
    </label>
    <p class="hint" style="margin:8px 0 0">{t("sGen.installedOnly")}</p>
  </section>
</div>

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
  .inline { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; }
  .ver { margin: 0 0 4px; font-size: 14px; }
  .status { margin: 0 0 12px; font-size: 13px; color: var(--muted); }
  .status.ok { color: var(--accent); }
  .status.err { color: var(--danger); }
  .prog { height: 4px; border-radius: 999px; background: var(--surface-3); overflow: hidden; margin: -4px 0 14px; }
  .bar { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.2s linear; }
  .rowbtns { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
</style>
