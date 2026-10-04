<script>
  // Settings → Compose: everything about writing and sending, in one tab - the
  // compose window and sending options (from the old General tab), Auto-BCC,
  // and the Signatures and Snippets panels that used to be tabs of their own.
  import { app, saveSettings, notify } from "../store.svelte.js";
  import SettingsSignature from "./SettingsSignature.svelte";
  import SettingsSnippets from "./SettingsSnippets.svelte";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let bccRules = $state((app.settings.autoBcc || []).map((r) => ({ ...r })));
  function addBcc() { bccRules = [...bccRules, { domain: "", bcc: "" }]; }
  function removeBcc(i) { bccRules = bccRules.filter((_, x) => x !== i); }
  function saveBcc() {
    saveSettings({ autoBcc: bccRules.filter((r) => r.domain && r.bcc) });
    notify(t("sCompose.bccSaved"));
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{t("sCompose.windowTitle")}</h3>
    <p class="hint">{t("sCompose.windowHint")}</p>
    <label class="radio">
      <input type="radio" name="cmode" checked={app.settings.composeMode === "panel"}
        onchange={() => saveSettings({ composeMode: "panel" })} />
      <div><b>{t("sCompose.docked")}</b><span>{t("sCompose.dockedHint")}</span></div>
    </label>
    <label class="radio">
      <input type="radio" name="cmode" checked={app.settings.composeMode === "window"}
        onchange={() => saveSettings({ composeMode: "window" })} />
      <div><b>{t("sCompose.separate")}</b><span>{t("sCompose.separateHint")}</span></div>
    </label>
    {#if app.settings.composeMode === "panel"}
      <label class="inline">{t("sCompose.corner")}
        <select value={app.settings.composePosition} onchange={(e) => saveSettings({ composePosition: e.currentTarget.value })}>
          <option value="bottom-right">{t("sCompose.bottomRight")}</option>
          <option value="bottom-left">{t("sCompose.bottomLeft")}</option>
        </select>
      </label>
    {/if}
    <label class="check" style="margin-top:6px">
      <input type="checkbox" checked={app.settings.spellCheck !== false} onchange={(e) => saveSettings({ spellCheck: e.currentTarget.checked })} />
      <div><b>{t("sCompose.spell")}</b><span>{t("sCompose.spellHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("sCompose.sendingTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.undoSend} onchange={(e) => saveSettings({ undoSend: e.currentTarget.checked })} />
      <div><b>{t("sCompose.undo")}</b><span>{t("sCompose.undoHint")}</span></div>
    </label>
    {#if app.settings.undoSend}
      <label class="inline">{t("sCompose.undoDelay")}
        <select value={app.settings.undoSendDelay} onchange={(e) => saveSettings({ undoSendDelay: Number(e.currentTarget.value) })}>
          {#each [3, 5, 10] as s}<option value={s}>{t("sCompose.seconds", { n: s })}</option>{/each}
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>{t("sCompose.bccTitle")}</h3>
    <p class="hint">{t("sCompose.bccHint")}</p>
    {#each bccRules as r, i}
      <div class="bccrow">
        <input placeholder={t("sCompose.bccDomain")} bind:value={r.domain} />
        <input placeholder="bcc@yoursystem.com" bind:value={r.bcc} />
        <button class="btn ghost danger" onclick={() => removeBcc(i)} aria-label={t("common.delete")}>{@html icons.close}</button>
      </div>
    {/each}
    <div class="bccactions">
      <button class="btn" onclick={addBcc}>＋ {t("sCompose.bccAdd")}</button>
      <button class="btn primary" onclick={saveBcc}>{t("common.save")}</button>
    </div>
  </section>

  <h2 class="sec">{t("settingsNav.signature")}</h2>
  <SettingsSignature />

  <h2 class="sec">{t("settingsNav.snippets")}</h2>
  <SettingsSnippets />
</div>

<style>
  .wrap { display: flex; flex-direction: column; gap: 20px; }
  .card { max-width: 640px; box-sizing: border-box; padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .radio, .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .radio div, .check div { display: flex; flex-direction: column; gap: 2px; }
  .radio span, .check span { color: var(--muted); font-size: 12px; }
  .radio input, .check input { margin-top: 3px; }
  .inline { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: var(--muted); font-size: 13px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .bccrow { display: flex; gap: 8px; margin-bottom: 8px; }
  .bccrow input:first-child { flex: 0 0 220px; }
  .bccrow input:nth-child(2) { flex: 1; }
  .bccactions { display: flex; gap: 10px; margin-top: 4px; }
  /* Heading over a whole panel shown on this page (Signatures, Snippets). */
  .sec { margin: 14px 0 -6px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); }
</style>
