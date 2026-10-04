<script>
  // Settings → General: the app itself - language, updates, tray and startup.
  // It used to hold ~15 unrelated topics; those now live in Inbox, Compose,
  // Notifications, Backup & sync and Integrations.
  import { app, checkForUpdates, setAutostart, setCloseToTray, setLanguage } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t, LANGUAGES } from "../i18n.svelte.js";
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
    <button class="btn primary" onclick={() => checkForUpdates()}>{@html icons.sync} {t("sGen.check")}</button>
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
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
</style>
