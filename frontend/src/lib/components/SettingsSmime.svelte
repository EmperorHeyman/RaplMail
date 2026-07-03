<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { smime as smimeApi } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let password = $state("");
  let importing = $state(false);
  let newCert = $state("");

  const certs = $derived(app.settings.smimeCerts || []);
  const identityEmail = $derived(app.settings.smimeEmail || "");
  const haveIdentity = $derived(!!(app.settings.smimeCert && app.settings.smimeKey));

  function fileToB64(file) {
    return new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result).split(",")[1] || "");
      r.onerror = rej;
      r.readAsDataURL(file);
    });
  }
  async function onFile(e) {
    const input = e.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    importing = true;
    try {
      const b64 = await fileToB64(file);
      const info = await smimeApi.importP12(b64, password);
      saveSettings({ smimeCert: info.cert, smimeKey: info.key, smimeEmail: info.email });
      notify(t("smime.imported", { who: info.email || info.subject || "certificate" }));
      password = "";
    } catch (err) { notify(err.message, "error"); }
    finally { importing = false; input.value = ""; }
  }
  function removeIdentity() {
    saveSettings({ smimeCert: "", smimeKey: "", smimeEmail: "" });
  }
  async function addCert() {
    const pem = newCert.trim();
    if (!pem.includes("BEGIN CERTIFICATE")) { notify(t("smime.badCert"), "error"); return; }
    try {
      const info = await smimeApi.certInfo(pem);
      saveSettings({ smimeCerts: [...certs, pem] });
      newCert = "";
      notify(t("smime.certAdded", { who: info.email || info.subject || "" }));
    } catch (err) { notify(err.message, "error"); }
  }
  function removeCert(i) {
    saveSettings({ smimeCerts: certs.filter((_, idx) => idx !== i) });
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("smime.identityTitle")} <span class="tag">X.509 / PKCS#7</span></h3>
    <p class="hint">{t("smime.identityHint")}</p>
    {#if haveIdentity}
      <div class="idrow">{@html icons.shieldCheck || icons.shield || ""}<b>{identityEmail || t("smime.certificate")}</b>
        <button class="btn ghost danger" onclick={removeIdentity}>{t("smime.remove")}</button></div>
    {/if}
    <label class="fieldrow"><span>{t("smime.p12password")}</span>
      <input type="password" bind:value={password} placeholder="••••••" />
    </label>
    <label class="btn filebtn">
      {@html icons.attachment || ""} {importing ? t("smime.importing") : t("smime.importP12")}
      <input type="file" accept=".p12,.pfx" hidden onchange={onFile} />
    </label>
  </section>

  <section class="card">
    <h3>{t("smime.recipientsTitle")}</h3>
    <p class="hint">{t("smime.recipientsHint")}</p>
    {#each certs as c, i}
      <div class="idrow"><span class="mono">{c.replace(/-----[^-]+-----/g, "").trim().slice(0, 44)}…</span>
        <button class="btn ghost danger" onclick={() => removeCert(i)}>{t("smime.remove")}</button></div>
    {/each}
    <textarea bind:value={newCert} rows="4" placeholder="-----BEGIN CERTIFICATE-----&#10;…&#10;-----END CERTIFICATE-----"></textarea>
    <button class="btn" onclick={addCert}>{t("smime.addCert")}</button>
  </section>
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 14px; max-width: 720px; }
  .card { display: flex; flex-direction: column; gap: 10px; }
  h3 { margin: 0; }
  .tag { font-size: 11px; font-weight: 600; color: var(--muted); background: var(--surface-2); padding: 2px 7px; border-radius: 999px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0; }
  .fieldrow { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .fieldrow input { padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); }
  .idrow { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-2); }
  .idrow b { flex: 1; }
  .mono { flex: 1; font-family: ui-monospace, Consolas, monospace; font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  textarea { width: 100%; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); font-family: ui-monospace, Consolas, monospace; font-size: 12px; resize: vertical; }
  .btn { align-self: flex-start; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); cursor: pointer; font-size: 13px; }
  .btn:hover { background: var(--surface-3); }
  .btn.ghost { background: transparent; }
  .btn.danger { color: var(--danger); }
  .filebtn { display: inline-flex; align-items: center; gap: 6px; }
</style>
