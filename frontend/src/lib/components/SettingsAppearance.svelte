<script>
  import { app, saveSettings, applyTheme, THEME_TOKENS, notify, LIGHT_THEME, LIST_DENSITY } from "../store.svelte.js";
  import { PRESETS, PRESET_CATEGORIES } from "../themes.js";
  import ColorPicker from "./ColorPicker.svelte";
  import { t } from "../i18n.svelte.js";
  import { hourLabel } from "../time.svelte.js";

  // Dynamic colour (Material You) lives in ColorPicker; the classic themes
  // below switch it off, and this brings it back.
  const dynamic = $derived(app.settings.colorStyle !== "classic");
  function useDynamic() { saveSettings({ colorStyle: "dynamic" }); applyTheme(); }

  // Effective email appearance mode (migrates the old two booleans).
  const emailMode = $derived(
    app.settings.emailTheme ||
    (app.settings.alwaysOriginalHtml ? "original" : (app.settings.emailAdaptColors === false ? "original" : "adaptive"))
  );

  // Configurable quick-action buttons (which buttons show on rows / in the reader).
  // Second element is an i18n key, translated with t() at render time.
  const ROW_CHOICES = [
    ["none", "sAppear.actNone"], ["done", "common.done"], ["snooze", "sAppear.actSnooze"], ["flag", "sAppear.actFlag"],
    ["read", "sAppear.actRead"], ["archive", "sAppear.actArchive"], ["delete", "common.delete"],
  ];
  const READER_CHOICES = [
    ["reply", "sAppear.actReply"], ["replyAll", "sAppear.actReplyAll"], ["forward", "sAppear.actForward"],
    ["archive", "sAppear.actArchive"], ["snooze", "sAppear.actSnooze"],
    ["done", "common.done"], ["flag", "sAppear.actFlag"], ["delete", "common.delete"],
  ];
  function setRowAction(index, key) {
    const cur = [...(app.settings.rowActions || ["snooze", "done"])];
    cur[index] = key;
    saveSettings({ rowActions: cur });
  }
  function toggleReaderAction(key, on) {
    const order = READER_CHOICES.map((c) => c[0]);
    const cur = new Set(app.settings.readerActions || order);
    if (on) cur.add(key); else cur.delete(key);
    saveSettings({ readerActions: order.filter((k) => cur.has(k)) });
  }

  // Token -> i18n key for its label (translated with t() at render time).
  const LABELS = {
    "--app-bg": "sAppear.tokAppBg", "--bg": "sAppear.tokBg", "--surface": "sAppear.tokSurface", "--surface-2": "sAppear.tokSurface2",
    "--surface-3": "sAppear.tokSurface3", "--border": "sAppear.tokBorder", "--text": "sAppear.tokText",
    "--muted": "sAppear.tokMuted", "--accent": "sAppear.tokAccent", "--done": "sAppear.tokDone",
    "--danger": "sAppear.tokDanger", "--warning": "sAppear.tokWarning",
  };
  // PRESET_CATEGORIES (themes.js) are English ids; map them to i18n keys for display.
  const CAT_KEYS = {
    "Essentials": "sAppear.catEssentials", "High contrast": "sAppear.catHighContrast",
    "Neutral": "sAppear.catNeutral", "Color": "sAppear.catColor", "Editor": "sAppear.catEditor",
  };

  // Accent-led presets live in ../themes.js (shared with onboarding).

  // Quick reference shown under the Custom CSS box so users know what to target.
  // Second element is an i18n key for the description (translated at render time).
  const SELECTORS = [
    [".sidebar", "sAppear.selSidebar"],
    [".folder", "sAppear.selFolder"],
    [".folder.active", "sAppear.selFolderActive"],
    [".btn", "sAppear.selBtn"],
    [".btn.primary", "sAppear.selBtnPrimary"],
    [".btn.ghost", "sAppear.selBtnGhost"],
    [".list", "sAppear.selList"],
    [".row", "sAppear.selRow"],
    [".row.unread", "sAppear.selRowUnread"],
    [".row.focused", "sAppear.selRowFocused"],
    [".avatar", "sAppear.selAvatar"],
    [".subject", "sAppear.selSubject"],
    [".snippet", "sAppear.selSnippet"],
    [".thread, .reader", "sAppear.selReader"],
    [".card", "sAppear.selCard"],
    [".cat", "sAppear.selCat"],
    [".bulkbar", "sAppear.selBulkbar"],
    [".sg", "sAppear.selSg"],
  ];

  const auto = $derived(app.settings.themeMode === "auto");
  function val(token, def) { return app.settings.theme[token] || def; }
  function setToken(token, value) {
    saveSettings({ theme: { ...app.settings.theme, [token]: value }, themeMode: "manual", colorStyle: "classic" });
    applyTheme();
  }
  function applyPreset(p) {
    saveSettings({ theme: { ...p.theme }, themeMode: "manual", colorStyle: "classic" });
    applyTheme();
    notify(t("sAppear.themeApplied", { name: p.name }));
  }
  // Presets grouped by category (in the order themes.js declares them).
  const DEF = Object.fromEntries(THEME_TOKENS);   // token -> default (dark) value
  const presetGroups = PRESET_CATEGORIES
    .map((cat) => ({ cat, items: PRESETS.filter((p) => p.category === cat) }))
    .filter((g) => g.items.length);
  // 26 presets filled a whole screen before any real option. Show the first
  // group (Essentials) and whichever group holds the theme in use; the rest
  // fold under "More themes".
  const shownGroups = $derived(presetGroups.filter((g, i) => i === 0 || g.items.some((p) => isActivePreset(p))));
  const moreGroups = $derived(presetGroups.filter((g) => !shownGroups.includes(g)));
  const moreCount = $derived(moreGroups.reduce((n, g) => n + g.items.length, 0));
  // A token's value for a preset, falling back to the default dark palette so the
  // preview chip shows the REAL background/surface, not just the accent (that's
  // why Light's deep-blue accent used to read as "darker" than Dark).
  const pv = (p, token) => p.theme[token] || DEF[token];
  // Highlight the preset currently in effect (Dark = the empty {} theme).
  function isActivePreset(p) {
    if (app.settings.colorStyle !== "classic") return false;
    const cur = app.settings.theme || {};
    const keys = new Set([...Object.keys(cur), ...Object.keys(p.theme)]);
    for (const k of keys) if ((cur[k] || "") !== (p.theme[k] || "")) return false;
    return true;
  }

  // --- Generate a whole palette from ONE accent color ------------------------
  // Pull the accent's hue, then build a low-saturation grey ramp on that hue for
  // a dark or light base - so you don't hand-tune 11 tokens.
  let genAccent = $state(app.settings.theme?.["--accent"] || "#5e8bff");
  let genBase = $state("dark");
  function hexToHsl(hex) {
    let h = (hex || "").replace("#", "");
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const r = parseInt(h.slice(0, 2), 16) / 255, g = parseInt(h.slice(2, 4), 16) / 255, b = parseInt(h.slice(4, 6), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
    let hue = 0, s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      hue = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      hue /= 6;
    }
    return [Math.round(hue * 360), Math.round(s * 100), Math.round(l * 100)];
  }
  function generatePalette(accent, base) {
    const [hue] = hexToHsl(accent);
    const H = (l, s) => `hsl(${hue} ${s}% ${l}%)`;
    if (base === "light") {
      return { "--bg": H(97, 30), "--surface": "#ffffff", "--surface-2": H(95, 26), "--surface-3": H(91, 22),
        "--border": H(85, 18), "--text": H(14, 26), "--muted": H(40, 18), "--accent": accent };
    }
    return { "--bg": H(7, 16), "--surface": H(11, 15), "--surface-2": H(16, 14), "--surface-3": H(22, 14),
      "--border": H(27, 13), "--text": H(93, 16), "--muted": H(62, 12), "--accent": accent };
  }
  function applyGenerated() {
    applyPreset({ name: t("sAppear.generated"), theme: generatePalette(genAccent, genBase) });
  }
  // --- Your own saved presets ------------------------------------------------
  function saveAsPreset() {
    const name = (prompt(t("sAppear.namePrompt")) || "").trim();
    if (!name) return;
    const id = (crypto.randomUUID?.() || String(Date.now())).replace(/[^a-z0-9]/gi, "").slice(0, 12);
    const list = [...(app.settings.userPresets || []), { id, name, theme: { ...app.settings.theme } }];
    saveSettings({ userPresets: list });
    notify(t("sAppear.presetSaved", { name }));
  }
  function deleteUserPreset(id) {
    saveSettings({ userPresets: (app.settings.userPresets || []).filter((p) => p.id !== id) });
  }
  const userPresets = $derived(app.settings.userPresets || []);

  // --- Auto day / night theme assignment -------------------------------------
  // A flat list of everything you can assign to day/night: built-in presets +
  // your saved ones. We store the resolved theme object, matched back by value.
  const themeChoices = $derived([
    { key: "dark", name: t("sAppear.darkDefault"), theme: {} },
    { key: "light", name: "Light", theme: LIGHT_THEME },
    ...PRESETS.filter((p) => p.name !== "Dark" && p.name !== "Light").map((p) => ({ key: "b:" + p.name, name: p.name, theme: p.theme })),
    ...userPresets.map((p) => ({ key: "u:" + p.id, name: t("sAppear.yoursSuffix", { name: p.name }), theme: p.theme })),
  ]);
  // Map a stored theme object back to its dropdown key. null = "not set" → the
  // per-slot default (Light for day, Dark for night).
  const keyForTheme = (th, fallback) => {
    if (th == null) return fallback;
    const j = JSON.stringify(th);
    return (themeChoices.find((c) => JSON.stringify(c.theme) === j) || { key: fallback }).key;
  };
  function setDayNight(which, key) {
    const c = themeChoices.find((x) => x.key === key);
    if (!c) return;
    saveSettings({ [which]: c.theme, colorStyle: "classic" });
    applyTheme();
  }
  const HOURS = Array.from({ length: 24 }, (_, i) => i);
  function setHour(which, v) { saveSettings({ [which]: Number(v) }); applyTheme(); }

  // --- Live shape/layout preview ---------------------------------------------
  const DENSITY = LIST_DENSITY;
  const dens = $derived(DENSITY[app.settings.density] || DENSITY.comfortable);

  function setMode(mode) { saveSettings({ themeMode: mode, colorStyle: "classic" }); applyTheme(); }
  function setRadius(v) { saveSettings({ radius: Number(v) }); applyTheme(); }
  function setScale(v) { saveSettings({ uiScale: Number(v) }); applyTheme(); }
  function setCss(v) { saveSettings({ customCss: v }); applyTheme(); }
  function reset() {
    saveSettings({ theme: {}, themeMode: "manual", colorStyle: "classic" });
    applyTheme();
    notify(t("sAppear.themeReset"));
  }
</script>

<div class="wrap">
  <section class="card color">
    <h3>{t("sColor.title")}</h3>
    {#if !dynamic}
      <div class="classic-note">
        <span>{t("sColor.classicOn")}</span>
        <button class="btn tonal sm" onclick={useDynamic}>{t("sColor.useDynamic")}</button>
      </div>
    {/if}
    <ColorPicker />
  </section>

  <details class="classic" open={!dynamic}>
  <summary>{t("sColor.classicTitle")}</summary>
  <p class="hint">{t("sColor.classicHint")}</p>
  <section class="card">
    <h3>{t("sAppear.modeTitle")}</h3>
    <label class="radio"><input type="radio" name="tmode" checked={!auto} onchange={() => setMode("manual")} />
      <div><b>{t("sAppear.manual")}</b><span>{t("sAppear.manualHint")}</span></div></label>
    <label class="radio"><input type="radio" name="tmode" checked={auto} onchange={() => setMode("auto")} />
      <div><b>{t("sAppear.auto")}</b><span>{t("sAppear.autoHint")}</span></div></label>
    {#if auto}
      <div class="daynight">
        <label class="dn"><span>{t("sAppear.dayTheme")}</span>
          <select value={keyForTheme(app.settings.dayTheme, "light")} onchange={(e) => setDayNight("dayTheme", e.currentTarget.value)}>
            {#each themeChoices as c}<option value={c.key}>{c.name}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>{t("sAppear.from")}</span>
          <select value={app.settings.dayStart ?? 7} onchange={(e) => setHour("dayStart", e.currentTarget.value)}>
            {#each HOURS as h}<option value={h}>{hourLabel(h)}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>{t("sAppear.nightTheme")}</span>
          <select value={keyForTheme(app.settings.nightTheme, "dark")} onchange={(e) => setDayNight("nightTheme", e.currentTarget.value)}>
            {#each themeChoices as c}<option value={c.key}>{c.name}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>{t("sAppear.from")}</span>
          <select value={app.settings.nightStart ?? 19} onchange={(e) => setHour("nightStart", e.currentTarget.value)}>
            {#each HOURS as h}<option value={h}>{hourLabel(h)}</option>{/each}
          </select>
        </label>
      </div>
      <p class="hint" style="margin:10px 0 0">{t("sAppear.tipBuildA")} <b>{t("sAppear.saveAsPreset")}</b>{t("sAppear.tipBuildB")}</p>
    {/if}
  </section>

  <section class="card" class:dim={auto}>
    <h3>{t("sAppear.presetsTitle")}</h3>
    <p class="hint">{t("sAppear.presetsHint")}</p>
    {#if userPresets.length}
      <div class="preset-cat">{t("sAppear.catYours")}</div>
      <div class="presets">
        {#each userPresets as p (p.id)}
          <div class="preset upreset" class:active={isActivePreset(p)}>
            <button class="preset-apply" onclick={() => applyPreset(p)} title={p.name}>
              <span class="chip" style="background:{pv(p, '--bg')}; border-color:{pv(p, '--border')}">
                <span class="chip-bar" style="background:{pv(p, '--surface-2')}"></span>
                <span class="chip-dot" style="background:{pv(p, '--accent')}"></span>
                <span class="chip-line" style="background:{pv(p, '--muted')}"></span>
              </span>
              <span class="preset-name">{p.name}</span>
            </button>
            <button class="updel" title={t("sAppear.deletePreset")} onclick={() => deleteUserPreset(p.id)}>×</button>
          </div>
        {/each}
      </div>
    {/if}
    {#snippet groupBlock(g)}
      <div class="preset-cat">{CAT_KEYS[g.cat] ? t(CAT_KEYS[g.cat]) : g.cat}</div>
      <div class="presets">
        {#each g.items as p}
          <button class="preset" class:active={isActivePreset(p)} onclick={() => applyPreset(p)} title={p.name}>
            <span class="chip" style="background:{pv(p, '--bg')}; border-color:{pv(p, '--border')}">
              <span class="chip-bar" style="background:{pv(p, '--surface-2')}"></span>
              <span class="chip-dot" style="background:{pv(p, '--accent')}"></span>
              <span class="chip-line" style="background:{pv(p, '--muted')}"></span>
            </span>
            <span class="preset-name">{p.name}</span>
          </button>
        {/each}
      </div>
    {/snippet}
    {#each shownGroups as g}{@render groupBlock(g)}{/each}
    {#if moreGroups.length}
      <details class="morethemes">
        <summary>{t("sAppear.moreThemes", { n: moreCount })}</summary>
        {#each moreGroups as g}{@render groupBlock(g)}{/each}
      </details>
    {/if}
  </section>

  <section class="card" class:dim={auto}>
    <div class="head"><h3>{t("sAppear.customTitle")}</h3>
      <div class="head-btns">
        <button class="btn ghost" onclick={saveAsPreset}>{t("sAppear.saveAsPreset")}</button>
        <button class="btn ghost" onclick={reset}>{t("sAppear.resetAll")}</button>
      </div>
    </div>
    <div class="gen">
      <span class="gen-lbl">{t("sAppear.genLabel")}</span>
      <input class="gen-swatch" type="color" bind:value={genAccent} title={t("sAppear.accentColor")} />
      <div class="seg">
        <button class="segbtn" class:on={genBase === "dark"} onclick={() => (genBase = "dark")}>{t("sAppear.darkBase")}</button>
        <button class="segbtn" class:on={genBase === "light"} onclick={() => (genBase = "light")}>{t("sAppear.lightBase")}</button>
      </div>
      <button class="btn" onclick={applyGenerated}>{t("sAppear.genPalette")}</button>
    </div>
    <p class="hint">{t("sAppear.tokensHint")}</p>
    <div class="tokens">
      {#each THEME_TOKENS as [token, def]}
        <label class="token">
          <input type="color" value={val(token, def)} oninput={(e) => setToken(token, e.currentTarget.value)} />
          <span class="tname">{LABELS[token] ? t(LABELS[token]) : token}</span>
          <span class="tval">{val(token, def)}</span>
        </label>
      {/each}
    </div>
  </section>
  </details>

  <section class="card">
    <h3>{t("sAppear.shapeTitle")}</h3>
    <!-- Live preview: a mock message row + button that reflect the roundness and
         density below as you drag, so you see the effect before committing. -->
    <div class="lp" style="--lp-r:{app.settings.radius}px">
      <div class="lp-lbl">{t("common.preview")}</div>
      <div class="lp-card">
        <div class="lp-row" style="padding:{dens[0]}px 12px; gap:{dens[1]}px">
          <span class="lp-av" style="width:{dens[2]}px; height:{dens[2]}px"></span>
          <span class="lp-txt">
            <span class="lp-l1"></span>
            <span class="lp-l2"></span>
          </span>
          <span class="lp-btn">{t("common.done")}</span>
        </div>
        <div class="lp-row alt" style="padding:{dens[0]}px 12px; gap:{dens[1]}px">
          <span class="lp-av" style="width:{dens[2]}px; height:{dens[2]}px"></span>
          <span class="lp-txt">
            <span class="lp-l1 short"></span>
            <span class="lp-l2 short"></span>
          </span>
        </div>
      </div>
    </div>
    <label class="slider-row">
      <span>{t("sAppear.uiSize")}</span>
      <input type="range" min="0.8" max="1.4" step="0.05" value={app.settings.uiScale ?? 1} oninput={(e) => setScale(e.currentTarget.value)} />
      <span class="val">{Math.round((app.settings.uiScale ?? 1) * 100)}%</span>
    </label>
    <label class="slider-row">
      <span>{t("sAppear.cornerRoundness")}</span>
      <input type="range" min="0" max="22" value={app.settings.radius} oninput={(e) => setRadius(e.currentTarget.value)} />
      <span class="val">{app.settings.radius}px</span>
    </label>
    <div class="field">
      <b>{t("sAppear.translucent")}</b>
      <span class="fhint">{t("sAppear.translucentHint")}</span>
      <div class="seg">
        {#each [
          { v: true, t: t("sAppear.translucentOn") },
          { v: false, t: t("sAppear.translucentOff") },
        ] as o}
          <button class="segbtn" class:on={(app.settings.glassBg !== false) === o.v}
            onclick={() => { saveSettings({ glassBg: o.v }); applyTheme(); }}>{o.t}</button>
        {/each}
      </div>
    </div>
    <div class="field">
      <b>{t("sAppear.density")}</b>
      <span class="fhint">{t("sAppear.densityHint")}</span>
      <div class="seg">
        {#each [
          { v: "compact", t: t("sAppear.densCompact"), d: t("sAppear.densCompactHint") },
          { v: "comfortable", t: t("sAppear.densComfortable"), d: t("sAppear.densComfortableHint") },
          { v: "cozy", t: t("sAppear.densCozy"), d: t("sAppear.densCozyHint") },
        ] as o}
          <button class="segbtn" class:on={(app.settings.density || "comfortable") === o.v} title={o.d}
            onclick={() => { saveSettings({ density: o.v }); applyTheme(); }}>{o.t}</button>
        {/each}
      </div>
    </div>
    <div class="field">
      <b>{t("sAppear.readingWidth")}</b>
      <span class="fhint">{t("sAppear.readingWidthHint")}</span>
      <div class="seg">
        {#each [
          { v: 0, t: t("sAppear.widthFull") }, { v: 680, t: t("sAppear.widthNarrow") }, { v: 820, t: t("sAppear.widthMedium") }, { v: 1000, t: t("sAppear.widthWide") },
        ] as o}
          <button class="segbtn" class:on={(app.settings.emailMaxWidth ?? 820) === o.v}
            onclick={() => saveSettings({ emailMaxWidth: o.v })}>{o.t}</button>
        {/each}
      </div>
    </div>
    <div class="field">
      <b>{t("sAppear.emailLook")}</b>
      <span class="fhint">{t("sAppear.emailLookHint")}</span>
      <div class="seg">
        {#each [
          { v: "dark", t: t("sAppear.emailDark"), d: t("sAppear.emailDarkTip") },
          { v: "adaptive", t: t("sAppear.emailAdaptive"), d: t("sAppear.emailAdaptiveTip") },
          { v: "original", t: t("sAppear.emailOriginal"), d: t("sAppear.emailOriginalTip") },
        ] as o}
          <button class="segbtn" class:on={emailMode === o.v} title={o.d}
            onclick={() => saveSettings({ emailTheme: o.v })}>{o.t}</button>
        {/each}
      </div>
      <span class="fhint">{emailMode === "dark" ? t("sAppear.emailDarkNote") : emailMode === "adaptive" ? t("sAppear.emailAdaptiveNote") : t("sAppear.emailOriginalNote")}</span>
    </div>
    <div class="field">
      <b>{t("sAppear.actionsPos")}</b>
      <span class="fhint">{t("sAppear.actionsPosHint")}</span>
      <div class="seg">
        <button class="segbtn" class:on={(app.settings.readerActionsPos || "top") === "top"} onclick={() => saveSettings({ readerActionsPos: "top" })}>{t("sAppear.posTop")}</button>
        <button class="segbtn" class:on={app.settings.readerActionsPos === "bottom"} onclick={() => saveSettings({ readerActionsPos: "bottom" })}>{t("sAppear.posBottomRight")}</button>
      </div>
    </div>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.relativeTime}
        onchange={(e) => saveSettings({ relativeTime: e.currentTarget.checked })} />
      <div>
        <b>{t("sAppear.relTime")}</b>
        <span>{t("sAppear.relTimeHint")}</span>
      </div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.senderAvatars !== false}
        onchange={(e) => saveSettings({ senderAvatars: e.currentTarget.checked })} />
      <div>
        <b>{t("sAppear.senderLogos")}</b>
        <span>{t("sAppear.senderLogosHint")}</span>
      </div>
    </label>
    <p class="hint" style="margin:12px 0 0">{t("sAppear.tipLayoutA")} <b>{t("sAppear.tipLayoutB")}</b>{t("sAppear.tipLayoutC")}</p>
  </section>

  <section class="card">
    <h3>{t("sAppear.quickTitle")}</h3>
    <p class="fhint">{t("sAppear.quickRowHint")}</p>
    <div class="rowbtns">
      {#each [0, 1] as idx}
        <label class="inline">{idx === 0 ? t("sAppear.left") : t("sAppear.right")}
          <select value={(app.settings.rowActions || ["snooze", "done"])[idx]} onchange={(e) => setRowAction(idx, e.currentTarget.value)}>
            {#each ROW_CHOICES as [val, label]}<option value={val}>{t(label)}</option>{/each}
          </select>
        </label>
      {/each}
    </div>
    <p class="fhint" style="margin-top:16px">{t("sAppear.quickReaderHint")}</p>
    <div class="rdrcats">
      {#each READER_CHOICES as [val, label]}
        <label class="grp"><input type="checkbox"
          checked={(app.settings.readerActions || READER_CHOICES.map((c) => c[0])).includes(val)}
          onchange={(e) => toggleReaderAction(val, e.currentTarget.checked)} /> <span>{t(label)}</span></label>
      {/each}
    </div>
  </section>

  <section class="card">
    <h3>{t("sAppear.cssTitle")}</h3>
    <p class="hint">{t("sAppear.cssHint")}</p>
    <textarea class="css" spellcheck="false" placeholder={'.btn.primary { border-radius: 999px; }\n.row { font-size: 15px; }\n:root { --accent: #ff5d8f; }'}
      value={app.settings.customCss} oninput={(e) => setCss(e.currentTarget.value)}></textarea>

    <label class="check" style="padding-top:12px">
      <input type="checkbox" checked={!!app.settings.customCssInEmails}
        onchange={(e) => saveSettings({ customCssInEmails: e.currentTarget.checked })} />
      <div>
        <b>{t("sAppear.cssInEmails")}</b>
        <span>{t("sAppear.cssInEmailsHint")}</span>
      </div>
    </label>

    <details class="docs">
      <summary>{t("sAppear.refSummary")}</summary>
      <p class="dh">{t("sAppear.refElements")}</p>
      <table>
        <tbody>
          {#each SELECTORS as [sel, desc]}
            <tr><td><code>{sel}</code></td><td>{t(desc)}</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="dh">{t("sAppear.refVars")} <span class="dim">({t("sAppear.refOverride")} <code>:root</code>)</span></p>
      <table>
        <tbody>
          <tr><td><code>--radius</code></td><td>{t("sAppear.cornerRoundness")} ({t("sAppear.refAlso")} <code>--radius-sm</code>)</td></tr>
          {#each Object.entries(LABELS) as [token, label]}
            <tr><td><code>{token}</code></td><td>{t(label)}</td></tr>
          {/each}
        </tbody>
      </table>
    </details>
  </section>
</div>

<style>
  .wrap { max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .card.dim { opacity: 0.5; pointer-events: none; }
  .radio { display: flex; gap: 11px; align-items: flex-start; padding: 7px 0; cursor: pointer; }
  .radio div { display: flex; flex-direction: column; gap: 2px; }
  .radio span { color: var(--muted); font-size: 12px; }
  .radio input { margin-top: 3px; }
  .head { display: flex; justify-content: space-between; align-items: center; }
  h3 { margin: 0 0 12px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .slider-row { display: flex; align-items: center; gap: 12px; font-size: 13px; }
  .slider-row input[type=range] { flex: 1; accent-color: var(--accent); }
  .slider-row .val { width: 44px; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 14px 0 2px; cursor: pointer; }
  .check input { margin-top: 3px; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .field { display: flex; flex-direction: column; gap: 6px; padding: 14px 0 2px; }
  .field > b { font-size: 13px; }
  .fhint { color: var(--muted); font-size: 12px; }
  .seg { display: inline-flex; gap: 4px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px; padding: 3px; width: fit-content; }
  .segbtn { font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 999px; color: var(--muted); }
  .segbtn:hover { color: var(--text); }
  .segbtn.on { background: var(--sel); color: var(--on-sel); }
  .segbtn { display: inline-flex; align-items: center; gap: 6px; }
  .segbtn :global(svg) { width: 18px; height: 18px; }
  .css { width: 100%; min-height: 120px; font-family: ui-monospace, monospace; font-size: 12px; resize: vertical; }
  .rowbtns { display: flex; gap: 18px; }
  .inline { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; }
  .rdrcats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px; }
  .grp { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 3px 0; }
  .hint code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  .docs { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 12px; }
  .docs summary { cursor: pointer; color: var(--muted); font-size: 13px; font-weight: 550; }
  .docs summary:hover { color: var(--text); }
  .docs .dh { font-size: 12px; color: var(--faint); text-transform: uppercase; letter-spacing: 0.05em; margin: 14px 0 6px; }
  .docs .dh .dim { text-transform: none; letter-spacing: 0; }
  .docs table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .docs td { padding: 4px 8px 4px 0; vertical-align: top; color: var(--muted); }
  .docs td:first-child { width: 200px; white-space: nowrap; }
  .docs code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; color: var(--text); }
  .preset-cat { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--faint); margin: 14px 0 8px; }
  .preset-cat:first-of-type { margin-top: 6px; }
  .morethemes { margin-top: 14px; }
  .morethemes > summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--accent); padding: 4px 0; }
  .morethemes > summary:hover { text-decoration: underline; }
  .presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 10px; }
  .preset { display: flex; flex-direction: column; align-items: stretch; gap: 8px; padding: 8px; border: 1px solid var(--border);
    border-radius: var(--radius); background: var(--surface-2); font-weight: 550; text-align: center;
    transition: border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease); }
  .preset:hover { border-color: var(--accent); transform: translateY(-1px); }
  .preset.active { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft-2); }
  /* Mini live-preview of the theme: real background, a panel bar, an accent dot,
     and a "text" line - so light/dark/black read at a glance. */
  .chip { position: relative; display: block; height: 46px; border: 1px solid; border-radius: 8px; overflow: hidden; }
  .chip-bar { position: absolute; left: 7px; top: 7px; width: 42%; height: 32px; border-radius: 5px; }
  .chip-dot { position: absolute; right: 8px; top: 9px; width: 11px; height: 11px; border-radius: 50%; }
  .chip-line { position: absolute; right: 8px; bottom: 9px; width: 34%; height: 4px; border-radius: 3px; opacity: 0.85; }
  .preset-name { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gen { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 4px 0 14px;
    padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); }
  .gen-lbl { font-size: 13px; font-weight: 600; }
  .gen-swatch { width: 34px; height: 26px; padding: 2px; border-radius: 6px; cursor: pointer; }
  .tokens { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .token { display: flex; align-items: center; gap: 10px; }
  .token input[type=color] { width: 38px; height: 30px; padding: 2px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); cursor: pointer; }
  .tname { flex: 1; font-size: 13px; }
  .tval { font-size: 11px; color: var(--faint); font-family: ui-monospace, monospace; }
  .head-btns { display: flex; gap: 8px; }
  /* Auto day/night picker grid */
  .daynight { display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; margin-top: 12px; align-items: center; }
  .dn { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
  .dn > span { flex: none; }
  .dn select { flex: 1; }
  /* User presets: apply button + a delete corner */
  .upreset { position: relative; padding: 0; }
  .preset-apply { display: flex; flex-direction: column; align-items: stretch; gap: 8px; padding: 8px; width: 100%; }
  .updel { position: absolute; top: 3px; right: 3px; width: 18px; height: 18px; border-radius: 50%;
    background: var(--surface-3); color: var(--muted); font-size: 13px; line-height: 1; opacity: 0; transition: opacity var(--t-fast) var(--ease); }
  .upreset:hover .updel { opacity: 1; }
  .updel:hover { background: var(--danger); color: #fff; }
  /* Live shape/layout preview */
  .lp { margin-bottom: 16px; }
  .lp-lbl { font-size: 12px; font-weight: 500; color: var(--muted); margin-bottom: 8px; }
  .lp-card { border: 1px solid var(--border); border-radius: var(--lp-r); overflow: hidden; background: var(--surface-2); }
  .lp-row { display: flex; align-items: center; }
  .lp-row.alt { border-top: 1px solid var(--hairline); }
  .lp-av { flex: none; border-radius: 50%; background: var(--accent-soft); }
  .lp-txt { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .lp-l1 { height: 8px; width: 55%; border-radius: 999px; background: var(--muted); opacity: 0.75; }
  .lp-l2 { height: 7px; width: 78%; border-radius: 999px; background: var(--faint); opacity: 0.6; }
  .lp-l1.short { width: 38%; } .lp-l2.short { width: 60%; }
  .lp-btn { flex: none; font-size: 11px; font-weight: 600; color: var(--on-accent); background: var(--accent); padding: 5px 12px; border-radius: var(--lp-r); }
  /* Color card: Windows accent, seed circles (Pixel's split discs), brightness. */
  .classic-note { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    padding: 10px 12px 10px 16px; margin-bottom: 6px; border-radius: var(--radius-sm); background: var(--surface-2); font-size: 13.5px; }
  /* The classic themes, folded under the Color card. */
  .classic { display: flex; flex-direction: column; gap: 20px; }
  .classic > summary { cursor: pointer; font-size: 14px; font-weight: 600; color: var(--accent); padding: 4px 4px; list-style-position: inside; }
  .classic > summary:hover { text-decoration: underline; }
  .classic[open] > summary { margin-bottom: 4px; }
  .classic > .hint { margin: -8px 4px 4px; }
  .classic > .card { margin-top: 16px; }
</style>
