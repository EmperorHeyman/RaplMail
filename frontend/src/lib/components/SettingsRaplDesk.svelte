<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { rapldesk } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let instances = $state([]);
  let adding = $state(false);
  let form = $state({ name: "", url: "", key: "" });
  let busy = $state(false);

  async function load() { try { instances = (await rapldesk.instances()).instances || []; } catch {} }
  onMount(load);

  async function add() {
    if (!form.url.trim() || !form.key.trim()) { notify(t("rapldesk.urlKeyRequired"), "error"); return; }
    busy = true;
    try {
      await rapldesk.add({ name: form.name.trim(), url: form.url.trim(), key: form.key.trim() });
      form = { name: "", url: "", key: "" };
      adding = false;
      await load();
      notify(t("rapldesk.connected"));
    } catch (e) { notify(e.message || t("rapldesk.couldntConnect"), "error"); }
    finally { busy = false; }
  }
  async function remove(i) {
    if (!confirm(t("rapldesk.removeConfirm", { name: i.name }))) return;
    try { await rapldesk.remove(i.id); await load(); notify(t("rapldesk.removed")); }
    catch (e) { notify(e.message, "error"); }
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("rapldesk.title")}</h3>
    <p class="hint">{t("rapldesk.hintA")}
      <b>{t("rapldesk.hintTickets")}</b>{t("rapldesk.hintB")}
      <b>{t("rapldesk.hintScopes")}</b> {t("rapldesk.hintC")}</p>

    {#each instances as i}
      <div class="inst">
        <span class="dot" class:on={i.connected}></span>
        <div class="meta"><b>{i.name}</b><span>{i.url}{i.connected ? "" : " · " + t("rapldesk.keyMissing")}</span></div>
        <button class="btn ghost danger" onclick={() => remove(i)}>{t("rapldesk.remove")}</button>
      </div>
    {/each}
    {#if instances.length === 0}<p class="hint" style="margin:0">{t("rapldesk.noInstances")}</p>{/if}

    {#if adding}
      <div class="addform">
        <label class="fr"><span>{t("rapldesk.name")}</span><input bind:value={form.name} placeholder={t("rapldesk.phName")} /></label>
        <label class="fr"><span>{t("rapldesk.baseUrl")}</span><input bind:value={form.url} placeholder="https://tickets.a123systems.cz" /></label>
        <label class="fr"><span>{t("rapldesk.apiKey")}</span><input type="password" bind:value={form.key} placeholder={t("rapldesk.phKey")} /></label>
        <div class="rowbtns">
          <button class="btn primary" onclick={add} disabled={busy}>{busy ? t("rapldesk.connecting") : t("rapldesk.connect")}</button>
          <button class="btn ghost" onclick={() => (adding = false)}>{t("rapldesk.cancel")}</button>
        </div>
      </div>
    {:else}
      <div class="rowbtns"><button class="btn primary" onclick={() => (adding = true)}>＋ {t("rapldesk.addInstance")}</button></div>
    {/if}
  </section>

  <section class="card">
    <h3>{t("rapldesk.identityTitle")}</h3>
    <p class="hint">{t("rapldesk.identityHint")}</p>
    <label class="fieldrow"><span>{t("rapldesk.userIdLabel")}</span>
      <input type="number" value={app.settings.raplDeskUserId || ""}
        onchange={(e) => saveSettings({ raplDeskUserId: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
        placeholder={t("rapldesk.phUserId")} />
    </label>
  </section>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 22px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; line-height: 1.5; }
  .inst { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--danger); flex: none; }
  .dot.on { background: var(--done); }
  .inst .meta { flex: 1; display: flex; flex-direction: column; }
  .inst .meta span { font-size: 12px; color: var(--muted); }
  .addform { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
  .fr { display: flex; align-items: center; gap: 10px; }
  .fr > span { width: 90px; flex: none; color: var(--muted); font-size: 13px; }
  .fr input { flex: 1; }
  .fieldrow { display: flex; align-items: center; gap: 10px; }
  .fieldrow > span { width: 130px; flex: none; color: var(--muted); font-size: 13px; }
  .fieldrow input { flex: 1; }
  .rowbtns { display: flex; gap: 10px; margin-top: 10px; }
  .btn.danger { color: var(--danger); }
</style>
