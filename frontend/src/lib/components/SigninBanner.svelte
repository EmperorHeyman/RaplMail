<script>
  // "Sign in again" bar over the mail list, one line per OAuth account whose
  // token died (revoked after an org turned on 2FA, expired, password reset).
  // Until then that mailbox silently stops syncing - this says so and fixes it.
  import { app } from "../store.svelte.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const dead = $derived(app.signinNeeded
    .map((id) => app.accounts.find((a) => a.id === id))
    .filter(Boolean));
</script>

{#each dead as a (a.id)}
  <div class="signin" role="alert">
    <span class="ic">{@html icons.warning}</span>
    <span class="txt"><b>{t("reauth.bannerTitle", { email: a.email })}</b> {t("reauth.bannerBody")}</span>
    <button class="btn primary" onclick={() => (app.reauthAccountId = a.id)}>{t("reauth.signIn")}</button>
  </div>
{/each}

<style>
  .signin { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px 10px; margin: 0 0 10px; padding: 9px 10px 9px 12px;
    border: 1px solid color-mix(in srgb, var(--warning) 45%, transparent);
    background: color-mix(in srgb, var(--warning) 12%, transparent);
    border-radius: var(--radius); font-size: 12.5px; line-height: 1.4; }
  .ic { color: var(--warning); font-size: 16px; flex: 0 0 auto; margin-top: 1px; }
  .txt { flex: 1 1 220px; min-width: 0; }
  .txt b { font-weight: 650; }
  .btn { flex: 0 0 auto; white-space: nowrap; margin-left: auto; }
</style>
