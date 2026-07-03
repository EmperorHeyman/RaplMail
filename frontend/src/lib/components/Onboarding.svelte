<script>
  import { app, saveSettings, applyTheme, setLanguage, selectSmartInbox,
           setAutostart, enableNotifications, isTauri, notify } from "../store.svelte.js";
  import { t, LANGUAGES } from "../i18n.svelte.js";
  import { ONBOARDING_PRESETS } from "../themes.js";
  import { icons } from "../icons.js";

  // Steps: welcome → language → theme → options → done. The Windows-startup
  // option only makes sense in the packaged desktop app, not the browser dev view.
  const onWindows = isTauri() && (navigator.platform || "").toLowerCase().includes("win");
  const STEPS = ["welcome", "language", "theme", "options", "done"];
  let i = $state(0);
  const step = $derived(STEPS[i]);
  const total = STEPS.length;

  // Live-preview the theme as the user hovers/clicks a preset, then persist it.
  let pickedTheme = $state(app.settings.theme && Object.keys(app.settings.theme).length ? null : "Dark");
  function pickTheme(p) {
    pickedTheme = p.name;
    saveSettings({ theme: { ...p.theme }, themeMode: "manual" });
    applyTheme();
  }

  // Option toggles mirror the real settings and apply immediately.
  function setLang(id) { setLanguage(id); }
  function toggleSmart(on) { saveSettings({ smartInbox: on }); }
  async function toggleNotif(on) {
    saveSettings({ notifyNewMail: on });
    if (on) { const perm = await enableNotifications(); if (perm !== "granted") notify(t("notif.newMail"), "info"); }
  }
  function toggleStartup(on) { setAutostart(on); }

  function next() { if (i < total - 1) i += 1; }
  function back() { if (i > 0) i -= 1; }
  function finish() {
    saveSettings({ onboarded: true });
    // Apply the chosen inbox layout right away so they land where they expect.
    if (app.settings.smartInbox) selectSmartInbox();
  }
  function skip() { saveSettings({ onboarded: true }); }

  // Own the keyboard while the wizard is up — arrows/enter drive the flow and
  // e/j/k must not leak to the mail list behind the veil.
  $effect(() => {
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); skip(); }
      else if (e.key === "Enter" || e.key === "ArrowRight") { e.preventDefault(); e.stopImmediatePropagation(); step === "done" ? finish() : next(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopImmediatePropagation(); back(); }
      else { e.stopImmediatePropagation(); }
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  });
</script>

<div class="veil" role="presentation">
  <div class="box" role="dialog" aria-modal="true" aria-label="Welcome">
    <!-- progress dots -->
    <div class="prog" aria-hidden="true">
      {#each STEPS as _, idx}<span class:done={idx < i} class:cur={idx === i}></span>{/each}
    </div>

    <div class="body">
      {#if step === "welcome"}
        <div class="hero"><span class="glyph">{@html icons.mail}</span></div>
        <h2>{t("onboarding.welcomeTitle")}</h2>
        <p>{t("onboarding.welcomeBody")}</p>

      {:else if step === "language"}
        <h2>{t("onboarding.languageTitle")}</h2>
        <p>{t("onboarding.languageBody")}</p>
        <div class="langs">
          {#each LANGUAGES as l}
            <button class="lang" class:sel={(app.settings.language || "auto") === l.id}
              onclick={() => setLang(l.id)}>{l.label}</button>
          {/each}
        </div>

      {:else if step === "theme"}
        <h2>{t("onboarding.themeTitle")}</h2>
        <p>{t("onboarding.themeBody")}</p>
        <div class="themes">
          {#each ONBOARDING_PRESETS as p}
            <button class="theme" class:sel={pickedTheme === p.name} onclick={() => pickTheme(p)}
              style="--sw:{p.theme['--accent'] || '#5e8bff'}; --bgp:{p.theme['--bg'] || '#0b0d12'}; --sfp:{p.theme['--surface'] || '#12151d'}">
              <span class="chip"><i class="a"></i><i class="b"></i><i class="c"></i></span>
              <span class="tn">{p.name}</span>
            </button>
          {/each}
        </div>

      {:else if step === "options"}
        <h2>{t("onboarding.optionsTitle")}</h2>
        <p>{t("onboarding.optionsBody")}</p>
        <div class="opts">
          <label class="opt">
            <input type="checkbox" checked={app.settings.smartInbox !== false} onchange={(e) => toggleSmart(e.currentTarget.checked)} />
            <div><b>{t("onboarding.smartInbox")}</b><span>{t("onboarding.smartInboxHint")}</span></div>
          </label>
          <label class="opt">
            <input type="checkbox" checked={app.settings.notifyNewMail !== false} onchange={(e) => toggleNotif(e.currentTarget.checked)} />
            <div><b>{t("onboarding.notifications")}</b><span>{t("onboarding.notificationsHint")}</span></div>
          </label>
          {#if onWindows}
            <label class="opt">
              <input type="checkbox" checked={!!app.settings.launchOnStartup} onchange={(e) => toggleStartup(e.currentTarget.checked)} />
              <div><b>{t("onboarding.startWithWindows")}</b><span>{t("onboarding.startWithWindowsHint")}</span></div>
            </label>
          {/if}
        </div>

      {:else}
        <div class="hero ok"><span class="glyph">{@html icons.done ?? icons.mail}</span></div>
        <h2>{t("onboarding.doneTitle")}</h2>
        <p>{t("onboarding.doneBody")}</p>
      {/if}
    </div>

    <div class="foot">
      <span class="stepno">{t("onboarding.stepOf", { n: i + 1, total })}</span>
      <div class="nav">
        {#if i > 0}<button class="btn ghost" onclick={back}>{t("common.back")}</button>{/if}
        {#if step === "done"}
          <button class="btn primary" onclick={finish}>{t("common.finish")}</button>
        {:else}
          <button class="btn ghost sm" onclick={skip}>{t("common.skip")}</button>
          <button class="btn primary" onclick={next}>{i === 0 ? t("common.getStarted") : t("common.next")}</button>
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .veil { position: fixed; inset: 0; z-index: 240; background: rgba(4,6,11,0.62);
    backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center;
    animation: fade-in var(--t) var(--ease); }
  .box { width: min(520px, 94vw); background: var(--surface); border: 1px solid var(--hairline);
    border-radius: calc(var(--radius) + 4px); box-shadow: var(--shadow-lg); overflow: hidden;
    animation: pop-in var(--t) var(--ease-spring); }

  .prog { display: flex; gap: 6px; padding: 16px 22px 0; }
  .prog span { flex: 1; height: 3px; border-radius: 999px; background: var(--surface-3); transition: background var(--t) var(--ease); }
  .prog span.done { background: color-mix(in srgb, var(--accent) 55%, transparent); }
  .prog span.cur { background: var(--accent); }

  .body { padding: 22px 24px 6px; text-align: center; min-height: 232px; }
  .body h2 { font-size: 21px; letter-spacing: -0.02em; margin: 4px 0 8px; color: var(--text); }
  .body p { color: var(--muted); font-size: 13.5px; line-height: 1.6; margin: 0 auto 16px; max-width: 400px; }

  .hero { display: grid; place-items: center; margin: 6px 0 12px; }
  .hero .glyph { width: 62px; height: 62px; border-radius: 18px; display: grid; place-items: center;
    background: var(--accent-soft); color: var(--accent); border: 1px solid var(--hairline);
    box-shadow: 0 8px 26px color-mix(in srgb, var(--accent) 22%, transparent); animation: pop-in var(--t-slow) var(--ease-spring); }
  .hero.ok .glyph { background: color-mix(in srgb, var(--done) 16%, transparent); color: var(--done); box-shadow: 0 8px 26px color-mix(in srgb, var(--done) 22%, transparent); }
  .hero .glyph :global(svg) { width: 30px; height: 30px; }

  /* language chooser */
  .langs { display: flex; flex-direction: column; gap: 8px; max-width: 320px; margin: 0 auto; }
  .lang { padding: 12px 14px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2);
    color: var(--text); font-size: 14px; font-weight: 550; cursor: pointer; text-align: left;
    transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .lang:hover { background: var(--hover); }
  .lang.sel { border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 0 1px var(--accent) inset; }

  /* theme grid */
  .themes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; max-width: 400px; margin: 0 auto; }
  .theme { display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 10px; cursor: pointer;
    border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2);
    transition: border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease-spring); }
  .theme:hover { transform: translateY(-2px); }
  .theme.sel { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
  .theme .chip { display: flex; width: 100%; height: 34px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
  .theme .chip i { flex: 1; }
  .theme .chip .a { background: var(--bgp); }
  .theme .chip .b { background: var(--sfp); }
  .theme .chip .c { background: var(--sw); flex: 0.7; }
  .theme .tn { font-size: 12px; color: var(--muted); font-weight: 550; }

  /* option toggles */
  .opts { display: flex; flex-direction: column; gap: 10px; max-width: 420px; margin: 0 auto; text-align: left; }
  .opt { display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; }
  .opt input { margin-top: 2px; width: 16px; height: 16px; accent-color: var(--accent); flex: none; }
  .opt b { display: block; font-size: 13.5px; color: var(--text); }
  .opt span { display: block; font-size: 12px; color: var(--muted); line-height: 1.5; margin-top: 2px; }

  .foot { display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 14px 22px 18px; border-top: 1px solid var(--hairline); background: var(--surface); }
  .stepno { font-size: 12px; color: var(--faint); }
  .nav { display: flex; gap: 8px; align-items: center; }
  .nav .sm { font-size: 12px; }
</style>
