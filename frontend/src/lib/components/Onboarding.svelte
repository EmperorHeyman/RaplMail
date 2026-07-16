<script>
  import { app, saveSettings, applyTheme, setLanguage, selectSmartInbox,
           setAutostart, enableNotifications, isTauri, notify } from "../store.svelte.js";
  import { t, LANGUAGES } from "../i18n.svelte.js";
  import { ONBOARDING_PRESETS } from "../themes.js";
  import { icons } from "../icons.js";

  // Full-screen first-run experience: a brand rail with the step list on the
  // left, roomy content on the right. Steps: welcome → language → highlights →
  // theme → options → settings → done. Also re-openable any time via the debug
  // "Show intro" button (app.introTour).
  const onWindows = isTauri() && (navigator.platform || "").toLowerCase().includes("win");
  const STEPS = $derived.by(() => [
    { id: "welcome", label: t("onboarding.navWelcome") },
    { id: "language", label: t("onboarding.navLanguage") },
    { id: "highlights", label: t("onboarding.navHighlights") },
    { id: "theme", label: t("onboarding.navTheme") },
    { id: "options", label: t("onboarding.navOptions") },
    { id: "settings", label: t("onboarding.navSettings") },
    { id: "done", label: t("onboarding.navDone") },
  ]);
  let i = $state(0);
  const step = $derived(STEPS[i].id);
  const total = $derived(STEPS.length);
  // Re-run (from debug): everything is optional, so any visited step is jumpable.
  let maxVisited = $state(0);
  $effect(() => { if (i > maxVisited) maxVisited = i; });

  // Live-preview the theme as the user clicks a preset, then persist it.
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

  // The hero features, introduced before the user dives in. Icons are decorative.
  const HIGHLIGHTS = $derived.by(() => [
    { icon: icons.done, title: t("onboarding.hlTriageTitle"), body: t("onboarding.hlTriageBody") },
    { icon: icons.inbox, title: t("onboarding.hlSmartTitle"), body: t("onboarding.hlSmartBody") },
    { icon: icons.shield, title: t("onboarding.hlPrivacyTitle"), body: t("onboarding.hlPrivacyBody") },
    { icon: icons.rules, title: t("onboarding.hlRulesTitle"), body: t("onboarding.hlRulesBody") },
    { icon: icons.signature, title: t("onboarding.hlSignatureTitle"), body: t("onboarding.hlSignatureBody") },
    { icon: icons.snooze, title: t("onboarding.hlSnoozeTitle"), body: t("onboarding.hlSnoozeBody") },
    { icon: icons.bolt, title: t("onboarding.hlAiTitle"), body: t("onboarding.hlAiBody") },
    { icon: icons.keyboard, title: t("onboarding.hlKeysTitle"), body: t("onboarding.hlKeysBody") },
  ]);

  // The settings areas the user can tailor - tapping a card jumps straight there.
  const SETTINGS_AREAS = $derived.by(() => [
    { tab: "accounts", icon: icons.accounts, title: t("settingsNav.accounts"), body: t("onboarding.setAccounts") },
    { tab: "appearance", icon: icons.palette, title: t("settingsNav.appearance"), body: t("onboarding.setAppearance") },
    { tab: "rules", icon: icons.rules, title: t("settingsNav.rules"), body: t("onboarding.setRules") },
    { tab: "signature", icon: icons.signature, title: t("settingsNav.signature"), body: t("onboarding.setSignature") },
    { tab: "ai", icon: icons.bolt, title: t("settingsNav.ai"), body: t("onboarding.setAi") },
    { tab: "sync", icon: icons.sync, title: t("settingsNav.sync"), body: t("onboarding.setSync") },
    { tab: "shortcuts", icon: icons.keyboard, title: t("settingsNav.shortcuts"), body: t("onboarding.setShortcuts") },
    { tab: "general", icon: icons.general, title: t("settingsNav.general"), body: t("onboarding.setGeneral") },
  ]);

  function next() { if (i < total - 1) i += 1; }
  function back() { if (i > 0) i -= 1; }
  function jump(idx) { if (idx <= maxVisited) i = idx; }
  function close() {
    saveSettings({ onboarded: true });
    app.introTour = false;
  }
  function finish() {
    close();
    // Apply the chosen inbox layout right away so they land where they expect.
    if (app.settings.smartInbox) selectSmartInbox();
  }
  // Close the wizard and jump straight to a settings area.
  function finishTo(tab) {
    finish();
    app.settingsTab = tab;
    app.view = "settings";
  }
  function skip() { close(); }

  // Own the keyboard while the wizard is up - arrows/enter drive the flow and
  // e/j/k must not leak to the mail list behind.
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

<div class="screen" role="dialog" aria-modal="true" aria-label="Welcome">
  <div class="glow g1"></div>
  <div class="glow g2"></div>

  <!-- brand + step rail -->
  <aside class="rail">
    <div class="brand">
      <span class="mark">{@html icons.mail}</span>
      <div class="bt">
        <b>RaplMail</b>
        <span>{t("onboarding.tagline")}</span>
      </div>
    </div>

    <nav class="steps" aria-label="Setup steps">
      {#each STEPS as s, idx}
        <button class="stp" class:cur={idx === i} class:done={idx < i} class:reach={idx <= maxVisited}
          onclick={() => jump(idx)} disabled={idx > maxVisited}>
          <span class="dot">{#if idx < i}{@html icons.done}{:else}{idx + 1}{/if}</span>
          <span class="sl">{s.label}</span>
        </button>
      {/each}
    </nav>

    <div class="railfoot">
      <span>{t("onboarding.stepOf", { n: i + 1, total })}</span>
    </div>
  </aside>

  <!-- step content -->
  <main class="pane">
    <div class="content" class:centered={step === "welcome" || step === "done"}>
      {#if step === "welcome"}
        <div class="hero"><span class="glyph">{@html icons.mail}</span></div>
        <h1>{t("onboarding.welcomeTitle")}</h1>
        <p class="lead">{t("onboarding.welcomeBody")}</p>
        <div class="pillars">
          <div class="pillar"><span>{@html icons.shield}</span>{t("onboarding.pillarLocal")}</div>
          <div class="pillar"><span>{@html icons.bolt}</span>{t("onboarding.pillarFast")}</div>
          <div class="pillar"><span>{@html icons.keyboard}</span>{t("onboarding.pillarKeys")}</div>
        </div>

      {:else if step === "language"}
        <h1>{t("onboarding.languageTitle")}</h1>
        <p class="lead">{t("onboarding.languageBody")}</p>
        <div class="langs">
          {#each LANGUAGES as l}
            <button class="lang" class:sel={(app.settings.language || "auto") === l.id}
              onclick={() => setLang(l.id)}>
              <span class="ln">{l.label}</span>
              {#if (app.settings.language || "auto") === l.id}<span class="chk">{@html icons.done}</span>{/if}
            </button>
          {/each}
        </div>

      {:else if step === "highlights"}
        <h1>{t("onboarding.highlightsTitle")}</h1>
        <p class="lead">{t("onboarding.highlightsBody")}</p>
        <div class="feats">
          {#each HIGHLIGHTS as f}
            <div class="feat">
              <span class="fic">{@html f.icon}</span>
              <div class="ft"><b>{f.title}</b><span>{f.body}</span></div>
            </div>
          {/each}
        </div>

      {:else if step === "theme"}
        <h1>{t("onboarding.themeTitle")}</h1>
        <p class="lead">{t("onboarding.themeBody")}</p>
        <div class="themes">
          {#each ONBOARDING_PRESETS as p}
            <button class="theme" class:sel={pickedTheme === p.name} onclick={() => pickTheme(p)}
              style="--sw:{p.theme['--accent'] || '#5e8bff'}; --bgp:{p.theme['--bg'] || '#0b0d12'}; --sfp:{p.theme['--surface'] || '#12151d'}">
              <span class="chip">
                <i class="win">
                  <i class="bar"></i>
                  <i class="row"></i><i class="row short"></i><i class="row"></i>
                </i>
              </span>
              <span class="tn">{p.name}</span>
            </button>
          {/each}
        </div>

      {:else if step === "options"}
        <h1>{t("onboarding.optionsTitle")}</h1>
        <p class="lead">{t("onboarding.optionsBody")}</p>
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

      {:else if step === "settings"}
        <h1>{t("onboarding.settingsTitle")}</h1>
        <p class="lead">{t("onboarding.settingsBody")}</p>
        <div class="areas">
          {#each SETTINGS_AREAS as a}
            <button class="area" onclick={() => finishTo(a.tab)}>
              <span class="aic">{@html a.icon}</span>
              <span class="at"><b>{a.title}</b><span>{a.body}</span></span>
            </button>
          {/each}
        </div>

      {:else}
        <div class="hero ok"><span class="glyph">{@html icons.done ?? icons.mail}</span></div>
        <h1>{t("onboarding.doneTitle")}</h1>
        <p class="lead">{t("onboarding.doneBody")}</p>
        <button class="cta" onclick={() => finishTo("accounts")}>
          {@html icons.accounts} {t("onboarding.addAccount")}
        </button>
      {/if}
    </div>

    <div class="foot">
      {#if i > 0}<button class="btn ghost" onclick={back}>{t("common.back")}</button>{/if}
      <div class="spacer"></div>
      {#if step === "done"}
        <button class="btn primary big" onclick={finish}>{t("common.finish")}</button>
      {:else}
        <button class="btn ghost sm" onclick={skip}>{t("common.skip")}</button>
        <button class="btn primary big" onclick={next}>{i === 0 ? t("common.getStarted") : t("common.next")}</button>
      {/if}
    </div>
  </main>
</div>

<style>
  .screen { position: fixed; inset: 0; z-index: 240; display: flex; background: var(--bg);
    overflow: hidden; animation: fade-in var(--t) var(--ease); }

  /* soft decorative glows behind everything */
  .glow { position: absolute; border-radius: 50%; filter: blur(90px); opacity: 0.5; pointer-events: none; }
  .g1 { width: 520px; height: 520px; top: -180px; left: -120px;
    background: color-mix(in srgb, var(--accent) 26%, transparent); }
  .g2 { width: 460px; height: 460px; bottom: -200px; right: -140px;
    background: color-mix(in srgb, var(--accent) 16%, transparent); }

  /* ── brand + stepper rail ──────────────────────────────────────────────── */
  .rail { position: relative; z-index: 1; flex: none; width: 264px; display: flex; flex-direction: column;
    padding: 30px 22px 22px; border-right: 1px solid var(--hairline);
    background: color-mix(in srgb, var(--surface) 62%, transparent); backdrop-filter: blur(10px); }
  .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 34px; }
  .mark { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; flex: none;
    background: var(--accent); color: #fff;
    box-shadow: 0 8px 24px color-mix(in srgb, var(--accent) 40%, transparent); }
  .mark :global(svg) { width: 22px; height: 22px; }
  .bt b { display: block; font-size: 17px; letter-spacing: -0.02em; color: var(--text); }
  .bt span { display: block; font-size: 11.5px; color: var(--muted); margin-top: 1px; }

  .steps { display: flex; flex-direction: column; gap: 2px; }
  .stp { display: flex; align-items: center; gap: 12px; padding: 9px 10px; border-radius: var(--radius);
    text-align: left; color: var(--muted); cursor: pointer;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .stp:disabled { cursor: default; opacity: 0.55; }
  .stp.reach:not(.cur):hover { background: var(--hover); }
  .stp .dot { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
    font-size: 12px; font-weight: 650; background: var(--surface-3); color: var(--muted);
    border: 1px solid var(--border); transition: all var(--t-fast) var(--ease); }
  .stp .dot :global(svg) { width: 13px; height: 13px; }
  .stp.done .dot { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
  .stp.cur { color: var(--text); }
  .stp.cur .dot { background: var(--accent); color: #fff; border-color: var(--accent);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 18%, transparent); }
  .sl { font-size: 13.5px; font-weight: 550; }

  .railfoot { margin-top: auto; font-size: 12px; color: var(--faint); padding: 0 10px; }

  /* ── content pane ──────────────────────────────────────────────────────── */
  .pane { position: relative; z-index: 1; flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .content { flex: 1; overflow-y: auto; padding: clamp(28px, 6vh, 64px) clamp(28px, 6vw, 88px) 20px;
    animation: fade-in var(--t) var(--ease); }
  .content.centered { display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center; }
  h1 { font-size: clamp(24px, 3.4vw, 34px); letter-spacing: -0.025em; margin: 0 0 10px; color: var(--text); }
  .lead { color: var(--muted); font-size: 14.5px; line-height: 1.65; margin: 0 0 28px; max-width: 640px; }
  .centered .lead { margin-bottom: 22px; }

  .hero { display: grid; place-items: center; margin: 0 0 22px; }
  .hero .glyph { width: 88px; height: 88px; border-radius: 26px; display: grid; place-items: center;
    background: var(--accent-soft); color: var(--accent); border: 1px solid var(--hairline);
    box-shadow: 0 14px 44px color-mix(in srgb, var(--accent) 26%, transparent);
    animation: pop-in var(--t-slow) var(--ease-spring); }
  .hero.ok .glyph { background: color-mix(in srgb, var(--done) 16%, transparent); color: var(--done);
    box-shadow: 0 14px 44px color-mix(in srgb, var(--done) 24%, transparent); }
  .hero .glyph :global(svg) { width: 42px; height: 42px; }

  .pillars { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
  .pillar { display: inline-flex; align-items: center; gap: 8px; padding: 9px 16px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--surface-2); color: var(--muted);
    font-size: 13px; font-weight: 550; }
  .pillar span { display: grid; place-items: center; color: var(--accent); }
  .pillar :global(svg) { width: 15px; height: 15px; }

  /* language chooser */
  .langs { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; max-width: 560px; }
  .lang { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 15px 17px;
    border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2);
    color: var(--text); font-size: 14.5px; font-weight: 550; cursor: pointer; text-align: left;
    transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .lang:hover { background: var(--hover); }
  .lang.sel { border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 0 1px var(--accent) inset; }
  .lang .chk { color: var(--accent); display: grid; place-items: center; }
  .lang .chk :global(svg) { width: 16px; height: 16px; }

  /* feature highlights */
  .feats { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; max-width: 860px; }
  .feat { display: flex; gap: 13px; align-items: flex-start; padding: 15px 16px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface-2); }
  .fic { flex: none; width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center;
    background: var(--accent-soft); color: var(--accent); }
  .fic :global(svg) { width: 19px; height: 19px; }
  .ft b { display: block; font-size: 13.5px; color: var(--text); }
  .ft span { display: block; font-size: 12px; color: var(--muted); line-height: 1.55; margin-top: 3px; }

  /* theme grid - each preset renders a tiny fake app window in its palette */
  .themes { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; max-width: 700px; }
  .theme { display: flex; flex-direction: column; align-items: stretch; gap: 9px; padding: 11px; cursor: pointer;
    border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2);
    transition: border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease-spring); }
  .theme:hover { transform: translateY(-2px); }
  .theme.sel { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
  .theme .chip { display: block; height: 74px; border-radius: 9px; overflow: hidden;
    border: 1px solid var(--border); background: var(--bgp); padding: 8px; }
  .theme .win { display: flex; flex-direction: column; gap: 5px; height: 100%; border-radius: 6px;
    background: var(--sfp); padding: 7px; }
  .theme .bar { display: block; height: 7px; width: 46%; border-radius: 4px; background: var(--sw); }
  .theme .row { display: block; height: 5px; width: 88%; border-radius: 3px;
    background: color-mix(in srgb, var(--sw) 16%, transparent); }
  .theme .row.short { width: 62%; }
  .theme .tn { font-size: 12.5px; color: var(--muted); font-weight: 550; text-align: center; }

  /* option toggles */
  .opts { display: flex; flex-direction: column; gap: 12px; max-width: 560px; }
  .opt { display: flex; gap: 14px; align-items: flex-start; padding: 15px 17px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface-2); cursor: pointer;
    transition: border-color var(--t-fast) var(--ease); }
  .opt:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
  .opt input { margin-top: 2px; width: 17px; height: 17px; accent-color: var(--accent); flex: none; }
  .opt b { display: block; font-size: 14px; color: var(--text); }
  .opt span { display: block; font-size: 12.5px; color: var(--muted); line-height: 1.55; margin-top: 3px; }

  /* settings tour */
  .areas { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; max-width: 860px; }
  .area { display: flex; gap: 13px; align-items: flex-start; padding: 15px 16px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; text-align: left;
    transition: border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease-spring); }
  .area:hover { border-color: var(--accent); transform: translateY(-2px); }
  .aic { flex: none; width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center;
    background: var(--accent-soft); color: var(--accent); }
  .aic :global(svg) { width: 19px; height: 19px; }
  .at b { display: block; font-size: 13.5px; color: var(--text); }
  .at span { display: block; font-size: 12px; color: var(--muted); line-height: 1.55; margin-top: 3px; }

  /* "Add an account" CTA on the final step */
  .cta { display: inline-flex; align-items: center; gap: 9px; margin: 4px auto 0; padding: 12px 24px;
    border-radius: 999px; background: var(--accent); color: #fff; font-size: 15px; font-weight: 600;
    box-shadow: 0 8px 26px color-mix(in srgb, var(--accent) 32%, transparent); cursor: pointer;
    transition: filter var(--t-fast) var(--ease), transform var(--t-fast) var(--ease-spring); }
  .cta:hover { filter: brightness(1.06); transform: translateY(-1px); }
  .cta :global(svg) { width: 18px; height: 18px; }

  .foot { display: flex; align-items: center; gap: 10px;
    padding: 16px clamp(28px, 6vw, 88px) 22px; border-top: 1px solid var(--hairline);
    background: color-mix(in srgb, var(--surface) 40%, transparent); backdrop-filter: blur(8px); }
  .foot .spacer { flex: 1; }
  .foot .sm { font-size: 12.5px; }
  .btn.big { padding: 10px 22px; font-size: 14px; }

  @media (max-width: 760px) {
    .rail { width: 76px; padding: 24px 12px 16px; }
    .bt, .sl, .railfoot { display: none; }
    .brand { justify-content: center; margin-bottom: 26px; }
    .steps { align-items: center; }
    .stp { padding: 6px; }
  }
</style>
