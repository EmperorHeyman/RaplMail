<script>
  // The dynamic (Material You) colour controls: the Windows accent switch, the
  // seed circles (Pixel's split discs: primary on top, secondary and tertiary
  // below), light / dark / system, and pure black. Shared by Settings →
  // Appearance and the first-run wizard. Any change here switches a classic
  // theme back to dynamic colour.
  import { app, saveSettings, applyTheme, notify, refreshWindowsAccent, dynamicIsDark } from "../store.svelte.js";
  import { seedSwatch } from "../palette.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const dynamic = $derived(app.settings.colorStyle !== "classic");
  const usingWindows = $derived(dynamic && !!app.settings.seedFromWindows);
  const darkNow = $derived(dynamicIsDark());
  const SEEDS = [["blue", "#5e8bff"], ["violet", "#6750a4"], ["teal", "#00897b"], ["green", "#3f8a3a"],
                 ["orange", "#c2410c"], ["rose", "#d6336c"], ["olive", "#7c6f2a"], ["grey", "#8a8a8a"]];
  const seedNow = $derived((app.settings.seedColor || "#5e8bff").toLowerCase());
  const customSeed = $derived(!SEEDS.some(([, h]) => h === seedNow));
  const swatches = $derived(SEEDS.map(([id, hex]) => ({
    id, hex, ...seedSwatch(hex, darkNow), on: dynamic && !usingWindows && hex === seedNow,
  })));
  const customOn = $derived(dynamic && !usingWindows && customSeed);
  const customDisc = $derived(customSeed ? seedSwatch(seedNow, darkNow) : null);
  const scheme = $derived(app.settings.colorScheme || "dark");

  function setDynamic(patch = {}) {
    saveSettings({ colorStyle: "dynamic", ...patch });
    applyTheme();
  }
  function pickSeed(hex) { setDynamic({ seedColor: hex.toLowerCase(), seedFromWindows: false }); }
  async function toggleWindows(on) {
    setDynamic({ seedFromWindows: on });
    if (!on) return;
    await refreshWindowsAccent();
    if (!app.settings.windowsAccent) notify(t("sColor.windowsNone"));
  }
</script>

<div class="cp">
  <label class="srow">
    <span class="stext">
      <b>{t("sColor.windows")}{#if usingWindows && app.settings.windowsAccent}<span class="acc-dot" style="background:{app.settings.windowsAccent}"></span>{/if}</b>
      <span>{t("sColor.windowsHint")}</span>
    </span>
    <input class="switch" type="checkbox" role="switch" checked={usingWindows} onchange={(e) => toggleWindows(e.currentTarget.checked)} />
  </label>

  <div class="seeds" class:off={usingWindows}>
    <b>{t("sColor.pick")}</b>
    <span class="sub">{t("sColor.pickHint")}</span>
    <div class="swatches">
      {#each swatches as sw (sw.id)}
        <button class="sw" class:on={sw.on} title={t("sColor.sw." + sw.id)} aria-label={t("sColor.sw." + sw.id)}
          aria-pressed={sw.on} onclick={() => pickSeed(sw.hex)}>
          <span class="disc"><i style="background:{sw.p}"></i><i style="background:{sw.s}"></i><i style="background:{sw.t}"></i></span>
          {#if sw.on}<span class="tick">{@html icons.done}</span>{/if}
        </button>
      {/each}
      <label class="sw custom" class:on={customOn} title={t("sColor.custom")}>
        <input type="color" value={app.settings.seedColor || "#5e8bff"} aria-label={t("sColor.custom")}
          onchange={(e) => pickSeed(e.currentTarget.value)} />
        {#if customDisc}
          <span class="disc"><i style="background:{customDisc.p}"></i><i style="background:{customDisc.s}"></i><i style="background:{customDisc.t}"></i></span>
        {:else}
          <span class="disc rainbow"></span>
        {/if}
        <span class="tick" class:plus={!customOn}>{@html customOn ? icons.done : icons.palette}</span>
      </label>
    </div>
  </div>

  <div class="mode">
    <b>{t("sColor.mode")}</b>
    <div class="seg" role="group" aria-label={t("sColor.mode")}>
      {#each [["light", t("sColor.light"), icons.lightMode], ["dark", t("sColor.dark"), icons.darkMode], ["system", t("sColor.system"), icons.autoMode]] as [v, label, ic]}
        {@const on = dynamic && scheme === v}
        <button class="segbtn" class:on aria-pressed={on} onclick={() => setDynamic({ colorScheme: v })}>{@html on ? icons.done : ic} {label}</button>
      {/each}
    </div>
  </div>

  {#if darkNow}
    <label class="srow">
      <span class="stext"><b>{t("sColor.black")}</b><span>{t("sColor.blackHint")}</span></span>
      <input class="switch" type="checkbox" role="switch" checked={!!app.settings.pureBlack}
        onchange={(e) => setDynamic({ pureBlack: e.currentTarget.checked })} />
    </label>
  {/if}
</div>

<style>
  .cp { display: flex; flex-direction: column; }
  b { font-size: 14.5px; font-weight: 500; }
  /* A setting row: text left, Material switch right. */
  .srow { display: flex; align-items: center; gap: 20px; padding: 10px 0; cursor: pointer; }
  .stext { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .stext > span, .sub { color: var(--muted); font-size: 13px; }
  .acc-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-left: 8px; vertical-align: -1px;
    box-shadow: 0 0 0 1px var(--border); }
  .switch {
    appearance: none; -webkit-appearance: none; flex: none; position: relative;
    width: 52px; height: 32px; margin: 0; border-radius: 16px; cursor: pointer;
    background: var(--surface-3); box-shadow: inset 0 0 0 2px var(--outline);
    transition: background var(--t) var(--ease), box-shadow var(--t) var(--ease);
  }
  .switch::before {
    content: ""; position: absolute; top: 50%; left: 16px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--outline); transform: translate(-50%, -50%);
    transition: left var(--t) var(--ease), width var(--t) var(--ease), height var(--t) var(--ease), background var(--t) var(--ease);
  }
  .switch:checked { background: var(--accent); box-shadow: none; }
  .switch:checked::before { left: 36px; width: 24px; height: 24px; background: var(--on-accent); }
  .switch:hover, .switch:focus { border: none; }
  .switch:focus-visible { box-shadow: var(--ring); }

  .seeds { display: flex; flex-direction: column; gap: 2px; padding: 12px 0 6px; transition: opacity var(--t) var(--ease); }
  .seeds.off { opacity: 0.45; }
  .swatches { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .sw { position: relative; width: 58px; height: 58px; border-radius: 50%; display: grid; place-items: center; cursor: pointer;
    transition: box-shadow var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .sw:hover { background: var(--hover); }
  .sw.on { box-shadow: inset 0 0 0 2px var(--accent); }
  .disc { width: 44px; height: 44px; border-radius: 50%; overflow: hidden; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
  .disc > i:first-child { grid-column: 1 / 3; }
  .disc.rainbow { background: conic-gradient(#f44336, #ffeb3b, #4caf50, #00bcd4, #3f51b5, #e91e63, #f44336); }
  .tick { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 24px; height: 24px; border-radius: 50%;
    display: grid; place-items: center; background: var(--accent); color: var(--on-accent); pointer-events: none; }
  .tick :global(svg) { width: 16px; height: 16px; }
  .tick.plus { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .sw.custom input[type="color"] { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; padding: 0; border: none; }

  .mode { display: flex; flex-direction: column; gap: 10px; padding: 14px 0 8px; }
  .seg { display: inline-flex; width: fit-content; border: 1px solid var(--outline); border-radius: 999px; overflow: hidden; }
  .segbtn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 18px; border-radius: 0; font-size: 13.5px; font-weight: 500; color: var(--text);
    transition: background var(--t-fast) var(--ease); }
  .segbtn + .segbtn { border-left: 1px solid var(--outline); }
  .segbtn :global(svg) { width: 18px; height: 18px; }
  .segbtn:hover { background: var(--hover); }
  .segbtn.on { background: var(--sel); color: var(--on-sel); }
</style>
