<script>
  // "RaplMail X is ready": what's new, the download's progress, and the restart
  // into it. Opened from the sidebar's Update button, the toast, or Settings.
  import { app, installUpdate, composeOpen, WEBSITE } from "../store.svelte.js";
  import { openExternal } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const u = $derived(app.update);
  const pct = $derived(u.total ? Math.min(100, Math.round((u.got / u.total) * 100)) : 0);
  // The feed's notes are the changelog section as plain lines: "Added" / "Fixed"
  // headings and "- " points (wrapped lines continue the point above).
  const notes = $derived.by(() => {
    const out = [];
    for (const raw of String(u.notes || "").split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      if (line.startsWith("- ")) out.push({ li: true, text: line.slice(2) });
      else if (out.length && out[out.length - 1].li && raw.startsWith(" ")) out[out.length - 1].text += " " + line;
      else out.push({ li: false, text: line });
    }
    return out;
  });
  const title = $derived(u.state === "ready" || u.state === "installing"
    ? t("update.readyTitle", { version: u.version })
    : u.state === "downloading" ? t("update.downloadingTitle", { version: u.version }) : t("update.title"));

  let writing = $state(false);
  $effect(() => { if (app.updateDialog) composeOpen().then((v) => (writing = v)); });

  function close() { app.updateDialog = false; }
  $effect(() => {
    if (!app.updateDialog) return;
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); close(); }
      else e.stopImmediatePropagation();      // keep j/k/e/Enter away from the list behind
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  });
</script>

{#if app.updateDialog}
  <div class="veil" role="presentation" onclick={close}>
    <div class="box" role="dialog" aria-modal="true" aria-labelledby="upd-title" onclick={(e) => e.stopPropagation()}>
      <div class="ic">{@html u.state === "ready" || u.state === "installing" ? icons.reset : icons.download}</div>
      <h2 id="upd-title">{title}</h2>
      {#if u.current}<p class="sub">{t("update.youHave", { version: u.current })}</p>{/if}

      {#if u.state === "downloading"}
        <div class="prog" role="progressbar" aria-valuenow={pct} aria-valuemin="0" aria-valuemax="100"><div class="bar" style="width:{pct}%"></div></div>
        <p class="sub tnum">{t("update.downloading", { pct })}</p>
      {/if}

      {#if notes.length}
        <div class="notes">
          <b>{t("update.whatsNew")}</b>
          {#each notes as n}
            {#if n.li}<p class="li">{n.text}</p>{:else}<p class="h">{n.text}</p>{/if}
          {/each}
        </div>
      {/if}

      {#if writing && (u.state === "ready" || u.state === "downloading")}<p class="warn">{t("update.composeOpen")}</p>{/if}
      {#if u.state === "error"}<p class="err">{u.error}</p>{/if}
      {#if u.state === "ready"}<p class="sub">{t("update.restartHint")}</p>{/if}

      <div class="btns">
        <button class="link" onclick={() => openExternal(WEBSITE + "/#changelog")}>{t("update.fullChangelog")}</button>
        <span class="sp"></span>
        <button class="btn ghost" onclick={close}>{u.state === "downloading" ? t("update.hide") : t("update.later")}</button>
        {#if u.state === "ready" || u.state === "installing"}
          <button class="btn primary" onclick={installUpdate} disabled={u.state === "installing"}>
            {u.state === "installing" ? t("update.installing") : t("update.restartNow")}
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .veil { position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,0.5);
    backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center;
    animation: fade-in var(--t) var(--ease); }
  .box { width: min(480px, 92vw); max-height: 86vh; display: flex; flex-direction: column;
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 24px;
    animation: pop-in var(--t) var(--ease); }
  .ic { color: var(--accent); width: 24px; height: 24px; margin: 0 auto 12px; }
  .ic :global(svg) { width: 24px; height: 24px; }
  h2 { margin: 0; font-size: 22px; font-weight: 400; text-align: center; letter-spacing: 0; }
  .sub { margin: 6px 0 0; color: var(--muted); font-size: 13px; text-align: center; }
  .prog { height: 4px; border-radius: 999px; background: var(--surface-3); overflow: hidden; margin: 16px 0 0; }
  .bar { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.2s linear; }
  .notes { margin: 18px 0 0; padding: 14px 16px; border-radius: var(--radius); background: var(--surface-2);
    overflow-y: auto; min-height: 0; font-size: 13px; line-height: 1.5; }
  .notes > b { display: block; font-size: 14px; font-weight: 500; margin-bottom: 4px; }
  .notes .h { margin: 10px 0 2px; color: var(--accent); font-weight: 500; font-size: 12px; }
  .notes .li { margin: 4px 0 0 16px; text-indent: -12px; color: var(--text); }
  .notes .li::before { content: "•"; display: inline-block; width: 12px; text-indent: 0; color: var(--muted); }
  .warn { margin: 14px 0 0; font-size: 13px; color: var(--warning); }
  .err { margin: 14px 0 0; font-size: 13px; color: var(--danger); overflow-wrap: anywhere; }
  .btns { display: flex; align-items: center; gap: 8px; margin-top: 20px; }
  .sp { flex: 1; }
  .link { background: none; border: 0; padding: 0; color: var(--accent); font-size: 13px; cursor: pointer; }
  .link:hover { text-decoration: underline; }
</style>
