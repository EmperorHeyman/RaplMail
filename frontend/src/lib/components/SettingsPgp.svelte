<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";

  let newPub = $state("");
  const pubs = $derived(app.settings.pgpPublicKeys || []);

  function addPub() {
    const k = newPub.trim();
    if (!k.includes("BEGIN PGP PUBLIC KEY")) { notify(t("setpgp.badPub"), "error"); return; }
    saveSettings({ pgpPublicKeys: [...pubs, k] });
    newPub = "";
    notify(t("setpgp.pubAdded"));
  }
  function removePub(i) { saveSettings({ pgpPublicKeys: pubs.filter((_, j) => j !== i) }); }

  // Show just the UID/fingerprint-ish header line so the list is readable.
  function label(blob) {
    const m = blob.match(/Comment:\s*(.+)/i) || blob.match(/^(.{0,40})/);
    return (m && m[1] ? m[1] : t("setpgp.pubFallback")).trim();
  }
</script>

<div class="wrap">
  <section>
    <h3>{t("setpgp.title")}</h3>
    <p class="lead">{t("setpgp.lead")}</p>
  </section>

  <section>
    <h3>{t("setpgp.privateTitle")}</h3>
    <p class="hint">{t("setpgp.privateHint")}</p>
    <textarea rows="4" placeholder="-----BEGIN PGP PRIVATE KEY BLOCK-----"
      value={app.settings.pgpPrivateKey || ""}
      onchange={(e) => saveSettings({ pgpPrivateKey: e.currentTarget.value.trim() })}></textarea>
    <label class="row"><span>{t("setpgp.passphrase")}</span>
      <input type="password" placeholder={t("setpgp.passphrasePh")} value={app.settings.pgpPassphrase || ""}
        onchange={(e) => saveSettings({ pgpPassphrase: e.currentTarget.value })} />
    </label>
    <p class="hint">{app.settings.pgpPrivateKey ? t("setpgp.privateSet") : t("setpgp.privateNone")}</p>
  </section>

  <section>
    <h3>{t("setpgp.restTitle")}</h3>
    <p class="hint">{t("setpgp.restHint")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.encryptCache}
        onchange={(e) => saveSettings({ encryptCache: e.currentTarget.checked })} />
      <span>{t("setpgp.encryptCache")}</span>
    </label>
  </section>

  <section>
    <h3>{t("setpgp.pubsTitle")} {#if pubs.length}<span class="n">{pubs.length}</span>{/if}</h3>
    <p class="hint">{t("setpgp.pubsHint")}</p>
    {#if pubs.length}
      <div class="keys">
        {#each pubs as k, i}
          <div class="keyrow"><code>{label(k)}</code><button class="btn ghost" onclick={() => removePub(i)}>{t("setpgp.remove")}</button></div>
        {/each}
      </div>
    {/if}
    <textarea rows="4" placeholder="-----BEGIN PGP PUBLIC KEY BLOCK-----" bind:value={newPub}></textarea>
    <button class="btn primary" onclick={addPub} disabled={!newPub.trim()}>{t("setpgp.addPub")}</button>
  </section>
</div>

<style>
  .wrap { max-width: 760px; display: flex; flex-direction: column; gap: 26px; }
  h3 { margin: 0 0 6px; }
  .lead { color: var(--muted); margin: 0 0 8px; font-size: 13px; line-height: 1.5; }
  .hint { color: var(--muted); font-size: 12px; margin: 4px 0; }
  textarea { width: 100%; resize: vertical; font: 12px/1.4 ui-monospace, monospace; }
  .row { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .row > span { width: 90px; flex: none; color: var(--muted); font-size: 13px; }
  .row input { flex: 1; }
  .n { color: var(--accent); font-size: 13px; }
  .keys { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
  .keyrow { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .keyrow code { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
  .check { display: flex; align-items: center; gap: 9px; font-size: 13px; color: var(--text); }
</style>
