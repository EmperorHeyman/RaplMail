<script>
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { t } from "../i18n.svelte.js";

  let items = $state((app.settings.workspaces || []).map((w) => ({ ...w, accountIds: [...w.accountIds] })));

  function add() {
    const id = (crypto.randomUUID && crypto.randomUUID()) || `ws${items.length}-${Math.floor(performance.now())}`;
    items = [...items, { id, name: t("setws.newName"), accountIds: [] }];
  }
  function remove(i) { items = items.filter((_, idx) => idx !== i); }
  function toggleAccount(w, accId) {
    w.accountIds = w.accountIds.includes(accId) ? w.accountIds.filter((x) => x !== accId) : [...w.accountIds, accId];
    items = [...items];
  }
  function persist() {
    const cleaned = items.map((w) => ({ id: w.id, name: w.name.trim() || t("setws.fallbackName"), accountIds: w.accountIds }));
    saveSettings({ workspaces: cleaned });
    items = cleaned.map((w) => ({ ...w, accountIds: [...w.accountIds] }));
    notify(t("setws.saved"));
  }
</script>

<div class="wrap">
  <p class="lead">
    {t("setws.leadIntro")} <b>A123 Systems</b>,
    <b>RAPL Group</b>, <b>{t("setws.exPersonal")}</b>). {t("setws.leadSwitch")}
    <kbd>Ctrl</kbd>+<kbd>1</kbd>…<kbd>9</kbd> (<kbd>Ctrl</kbd>+<kbd>0</kbd> = {t("setws.leadAll")}).
    {t("setws.leadShow")}
  </p>

  {#each items as w, i}
    <div class="ws">
      <input class="name" bind:value={w.name} placeholder={t("setws.namePh")} />
      <div class="accs">
        {#each app.accounts as a}
          <label class="acc"><input type="checkbox" checked={w.accountIds.includes(a.id)} onchange={() => toggleAccount(w, a.id)} /> {a.email}</label>
        {/each}
        {#if app.accounts.length === 0}<span class="muted">{t("setws.addAccountsFirst")}</span>{/if}
      </div>
      <button class="btn ghost danger" onclick={() => remove(i)}>{t("setws.delete")}</button>
    </div>
  {/each}

  <div class="actions">
    <button class="btn" onclick={add}>{t("setws.add")}</button>
    <button class="btn primary" onclick={persist}>{t("setws.save")}</button>
  </div>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 12px; }
  .lead { color: var(--muted); font-size: 13px; line-height: 1.7; margin: 0 0 6px; }
  kbd { background: var(--surface-3); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; }
  .ws { display: flex; gap: 14px; align-items: flex-start; padding: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .name { flex: 0 0 180px; }
  .accs { flex: 1; display: flex; flex-direction: column; gap: 6px; }
  .acc { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .muted { color: var(--muted); font-size: 12px; }
  .actions { display: flex; gap: 10px; }
</style>
