<script>
  import { app, saveSettings, notify } from "../store.svelte.js";

  let newPub = $state("");
  const pubs = $derived(app.settings.pgpPublicKeys || []);

  function addPub() {
    const k = newPub.trim();
    if (!k.includes("BEGIN PGP PUBLIC KEY")) { notify("That doesn't look like an armored public key", "error"); return; }
    saveSettings({ pgpPublicKeys: [...pubs, k] });
    newPub = "";
    notify("Public key added");
  }
  function removePub(i) { saveSettings({ pgpPublicKeys: pubs.filter((_, j) => j !== i) }); }

  // Show just the UID/fingerprint-ish header line so the list is readable.
  function label(blob) {
    const m = blob.match(/Comment:\s*(.+)/i) || blob.match(/^(.{0,40})/);
    return (m && m[1] ? m[1] : "public key").trim();
  }
</script>

<div class="wrap">
  <section>
    <h3>OpenPGP encryption</h3>
    <p class="lead">Verify signed mail, read encrypted mail, and sign/encrypt what you send - all locally with your
      own keys. Keys are stored in your settings and never leave this machine. Paste ASCII-armored keys
      (exported from GnuPG, Proton, etc.).</p>
  </section>

  <section>
    <h3>Your private key</h3>
    <p class="hint">Used to decrypt incoming mail and to sign what you send. Leave blank if you only verify.</p>
    <textarea rows="4" placeholder="-----BEGIN PGP PRIVATE KEY BLOCK-----"
      value={app.settings.pgpPrivateKey || ""}
      onchange={(e) => saveSettings({ pgpPrivateKey: e.currentTarget.value.trim() })}></textarea>
    <label class="row"><span>Passphrase</span>
      <input type="password" placeholder="(if the key is protected)" value={app.settings.pgpPassphrase || ""}
        onchange={(e) => saveSettings({ pgpPassphrase: e.currentTarget.value })} />
    </label>
    <p class="hint">{app.settings.pgpPrivateKey ? "✓ Private key set - decrypt & sign enabled." : "No private key."}</p>
  </section>

  <section>
    <h3>Encryption at rest</h3>
    <p class="hint">Seal cached message bodies on disk with your vault key, so the local database doesn't store
      readable mail. Applies to messages opened after you enable it. Requires the vault to be unlocked to read them.</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.encryptCache}
        onchange={(e) => saveSettings({ encryptCache: e.currentTarget.checked })} />
      <span>Encrypt the local message cache</span>
    </label>
  </section>

  <section>
    <h3>Correspondents' public keys {#if pubs.length}<span class="n">{pubs.length}</span>{/if}</h3>
    <p class="hint">Needed to verify someone's signature and to encrypt mail to them (matched by the key's email UID).</p>
    {#if pubs.length}
      <div class="keys">
        {#each pubs as k, i}
          <div class="keyrow"><code>{label(k)}</code><button class="btn ghost" onclick={() => removePub(i)}>Remove</button></div>
        {/each}
      </div>
    {/if}
    <textarea rows="4" placeholder="-----BEGIN PGP PUBLIC KEY BLOCK-----" bind:value={newPub}></textarea>
    <button class="btn primary" onclick={addPub} disabled={!newPub.trim()}>Add public key</button>
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
