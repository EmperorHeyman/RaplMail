<script>
  import { vault } from "../api.js";
  import { app, refreshVault, notify } from "../store.svelte.js";
  import { icons } from "../icons.js";

  let password = $state("");
  let confirm = $state("");
  let busy = $state(false);
  let error = $state("");

  const isNew = $derived(!app.vault.exists);

  async function submit(e) {
    e.preventDefault();
    error = "";
    if (isNew && password !== confirm) { error = "Passwords don't match"; return; }
    if (password.length < 6) { error = "Use at least 6 characters"; return; }
    busy = true;
    try {
      if (isNew) await vault.initialize(password);
      else await vault.unlock(password);
      await refreshVault();
      notify("Vault unlocked");
    } catch (err) {
      error = err.message || "Failed";
    } finally {
      busy = false;
    }
  }
</script>

<div class="gate">
  <form class="card" onsubmit={submit}>
    <div class="logo">{@html icons.brand}</div>
    <h1>RaplMail</h1>
    <p class="sub">
      {isNew
        ? "Set a master password to encrypt your accounts on this device."
        : "Enter your master password to unlock your mail."}
    </p>

    <input type="password" placeholder="Master password" bind:value={password} autofocus />
    {#if isNew}
      <input type="password" placeholder="Confirm password" bind:value={confirm} />
    {/if}

    {#if error}<div class="error">{error}</div>{/if}

    <button class="btn primary" type="submit" disabled={busy}>
      {busy ? "…" : isNew ? "Create vault" : "Unlock"}
    </button>
    {#if isNew}
      <p class="hint">There's no recovery - if you forget this, your stored credentials are gone.</p>
    {/if}
  </form>
</div>

<style>
  .gate {
    height: 100%; display: grid; place-items: center; position: relative; overflow: hidden;
  }
  /* A quiet radial glow so the lock screen doesn't feel like a void. */
  .gate::before {
    content: ""; position: absolute; width: 720px; height: 720px; border-radius: 50%;
    background: radial-gradient(circle, var(--accent-soft) 0%, transparent 62%);
    pointer-events: none;
  }
  .card {
    position: relative;
    width: 350px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 34px 32px 30px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: calc(var(--radius) + 5px);
    box-shadow: var(--shadow-lg);
    text-align: center;
    animation: rise-in var(--t-slow) var(--ease);
  }
  .logo {
    display: grid; place-items: center; width: 52px; height: 52px; margin: 0 auto 2px;
    border-radius: 16px; color: #fff;
    background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 45%, #a06df0));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), var(--shadow);
  }
  .logo :global(svg) { width: 27px; height: 27px; }
  h1 { margin: 0; font-size: 22px; letter-spacing: -0.02em; }
  .sub { margin: 0 0 6px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .error { color: var(--danger); font-size: 13px; }
  .hint { margin: 4px 0 0; color: var(--faint); font-size: 11px; }
  button { margin-top: 4px; justify-content: center; }
</style>
