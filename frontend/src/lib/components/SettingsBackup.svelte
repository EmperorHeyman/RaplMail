<script>
  // Settings → Backup & sync: moving RaplMail between computers and keeping two
  // in step - the backup/restore card from the old General tab, then the
  // Device sync panel that used to be a tab of its own.
  import { notify, exportConfig, importConfig, exportFullBackup, importFullBackup } from "../store.svelte.js";
  import SettingsSync from "./SettingsSync.svelte";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const tick = (on) => (on ? "✓" : "-");

  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }
  const today = () => new Date().toISOString().slice(0, 10);

  let importFile;
  async function doExport() {
    try {
      const bundle = await exportConfig();
      download(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }), `raplmail-config-${today()}.json`);
      notify(t("sBackup.exported"));
    } catch { notify(t("sBackup.exportFailed"), "error"); }
  }
  async function doImport(e) {
    const file = e.currentTarget.files?.[0];
    if (file) {
      try {
        const r = await importConfig(JSON.parse(await file.text()));
        notify(t("sBackup.imported", { settings: tick(r.settings), rules: r.rules, sigs: r.signatures, tags: r.sender_categories }));
      } catch { notify(t("sBackup.importFailed"), "error"); }
    }
    e.currentTarget.value = "";
  }

  // Full encrypted backup (.rmail): config + accounts + passwords, sealed with
  // the master password.
  let rmailFile;
  let backingUp = $state(false);
  async function doExportFull() {
    backingUp = true;
    try {
      const blob = await exportFullBackup();
      download(new Blob([JSON.stringify(blob)], { type: "application/octet-stream" }), `raplmail-backup-${today()}.rmail`);
      notify(t("sBackup.backupSaved"));
    } catch (err) {
      notify(err?.message?.includes("vault") ? t("sBackup.unlockFirst") : t("sBackup.backupFailed"), "error");
    } finally { backingUp = false; }
  }
  async function doImportFull(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    let blob;
    try { blob = JSON.parse(await file.text()); }
    catch { notify(t("sBackup.notRmail"), "error"); return; }
    const pw = prompt(t("sBackup.askPassword"));
    if (!pw) return;
    try {
      const r = await importFullBackup(blob, pw);
      notify(t("sBackup.restored", { accounts: r.accounts, settings: tick(r.settings), rules: r.rules, sigs: r.signatures }));
    } catch (err) {
      notify(err?.status === 400 ? t("sBackup.wrongPassword") : (err?.message || t("sBackup.restoreFailed")), "error");
    }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sBackup.title")}</h3>
    <p class="hint">{t("sBackup.fullHint")}</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={doExportFull} disabled={backingUp}>{@html icons.lock} {backingUp ? t("sBackup.backingUp") : t("sBackup.exportFull")}</button>
      <button class="btn" onclick={() => rmailFile.click()}>{t("sBackup.restore")}</button>
      <input bind:this={rmailFile} type="file" accept=".rmail,application/octet-stream" hidden onchange={doImportFull} />
    </div>
    <p class="hint" style="margin-top:16px">{t("sBackup.configHint")}</p>
    <div class="rowbtns">
      <button class="btn" onclick={doExport}>{@html icons.sent} {t("sBackup.exportConfig")}</button>
      <button class="btn" onclick={() => importFile.click()}>{t("sBackup.importConfig")}</button>
      <input bind:this={importFile} type="file" accept="application/json,.json" hidden onchange={doImport} />
    </div>
  </section>

  <h2 class="sec">{t("settingsNav.sync")}</h2>
  <SettingsSync />
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 20px; }
  .card { max-width: 640px; box-sizing: border-box; padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .rowbtns { display: flex; flex-wrap: wrap; gap: 10px; }
  .sec { margin: 14px 0 -6px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); }
</style>
