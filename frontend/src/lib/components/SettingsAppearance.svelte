<script>
  import { app, saveSettings, applyTheme, THEME_TOKENS, notify, LIGHT_THEME } from "../store.svelte.js";
  import { PRESETS, PRESET_CATEGORIES } from "../themes.js";

  // Effective email appearance mode (migrates the old two booleans).
  const emailMode = $derived(
    app.settings.emailTheme ||
    (app.settings.alwaysOriginalHtml ? "original" : (app.settings.emailAdaptColors === false ? "original" : "adaptive"))
  );

  // Configurable quick-action buttons (which buttons show on rows / in the reader).
  const ROW_CHOICES = [
    ["none", "— None —"], ["done", "Done"], ["snooze", "Snooze"], ["flag", "Flag"],
    ["read", "Read / unread"], ["archive", "Archive"], ["delete", "Delete"],
  ];
  const READER_CHOICES = [
    ["reply", "Reply"], ["replyAll", "Reply all"], ["forward", "Forward"],
    ["archive", "Archive"], ["snooze", "Snooze"],
    ["done", "Done"], ["flag", "Flag"], ["delete", "Delete"],
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

  const LABELS = {
    "--bg": "Background", "--surface": "Surface", "--surface-2": "Surface 2",
    "--surface-3": "Surface 3", "--border": "Border", "--text": "Text",
    "--muted": "Muted text", "--accent": "Accent", "--done": "Done / success",
    "--danger": "Danger", "--warning": "Warning",
  };

  // Accent-led presets live in ../themes.js (shared with onboarding).

  // Quick reference shown under the Custom CSS box so users know what to target.
  const SELECTORS = [
    [".sidebar", "Left navigation pane"],
    [".folder", "A nav row (inbox, folder, smart view)"],
    [".folder.active", "The selected nav row"],
    [".btn", "Any button"],
    [".btn.primary", "Primary buttons (Compose, Send)"],
    [".btn.ghost", "Subtle / secondary buttons"],
    [".list", "Message-list column"],
    [".row", "A message row in the list"],
    [".row.unread", "Unread message rows"],
    [".row.focused", "Keyboard-focused row"],
    [".avatar", "Sender avatar disc"],
    [".subject", "Subject line in a row"],
    [".snippet", "Preview text in a row"],
    [".thread, .reader", "Reading pane"],
    [".card", "Settings / grouped panels"],
    [".cat", "Category tab pill"],
    [".bulkbar", "Multi-select action bar"],
    [".sg", "Smart Inbox group card"],
  ];

  const auto = $derived(app.settings.themeMode === "auto");
  function val(token, def) { return app.settings.theme[token] || def; }
  function setToken(token, value) {
    saveSettings({ theme: { ...app.settings.theme, [token]: value }, themeMode: "manual" });
    applyTheme();
  }
  function applyPreset(p) {
    saveSettings({ theme: { ...p.theme }, themeMode: "manual" });
    applyTheme();
    notify(`Theme: ${p.name}`);
  }
  // Presets grouped by category (in the order themes.js declares them).
  const DEF = Object.fromEntries(THEME_TOKENS);   // token -> default (dark) value
  const presetGroups = PRESET_CATEGORIES
    .map((cat) => ({ cat, items: PRESETS.filter((p) => p.category === cat) }))
    .filter((g) => g.items.length);
  // A token's value for a preset, falling back to the default dark palette so the
  // preview chip shows the REAL background/surface, not just the accent (that's
  // why Light's deep-blue accent used to read as "darker" than Dark).
  const pv = (p, token) => p.theme[token] || DEF[token];
  // Highlight the preset currently in effect (Dark = the empty {} theme).
  function isActivePreset(p) {
    const cur = app.settings.theme || {};
    const keys = new Set([...Object.keys(cur), ...Object.keys(p.theme)]);
    for (const k of keys) if ((cur[k] || "") !== (p.theme[k] || "")) return false;
    return true;
  }

  // --- Generate a whole palette from ONE accent color ------------------------
  // Pull the accent's hue, then build a low-saturation grey ramp on that hue for
  // a dark or light base — so you don't hand-tune 11 tokens.
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
    applyPreset({ name: "Generated", theme: generatePalette(genAccent, genBase) });
  }
  // --- Your own saved presets ------------------------------------------------
  function saveAsPreset() {
    const name = (prompt("Name this preset:") || "").trim();
    if (!name) return;
    const id = (crypto.randomUUID?.() || String(Date.now())).replace(/[^a-z0-9]/gi, "").slice(0, 12);
    const list = [...(app.settings.userPresets || []), { id, name, theme: { ...app.settings.theme } }];
    saveSettings({ userPresets: list });
    notify(`Saved preset "${name}"`);
  }
  function deleteUserPreset(id) {
    saveSettings({ userPresets: (app.settings.userPresets || []).filter((p) => p.id !== id) });
  }
  const userPresets = $derived(app.settings.userPresets || []);

  // --- Auto day / night theme assignment -------------------------------------
  // A flat list of everything you can assign to day/night: built-in presets +
  // your saved ones. We store the resolved theme object, matched back by value.
  const themeChoices = $derived([
    { key: "dark", name: "Dark (default)", theme: {} },
    { key: "light", name: "Light", theme: LIGHT_THEME },
    ...PRESETS.filter((p) => p.name !== "Dark" && p.name !== "Light").map((p) => ({ key: "b:" + p.name, name: p.name, theme: p.theme })),
    ...userPresets.map((p) => ({ key: "u:" + p.id, name: p.name + " (yours)", theme: p.theme })),
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
    saveSettings({ [which]: c.theme });
    applyTheme();
  }
  const HOURS = Array.from({ length: 24 }, (_, i) => i);
  function setHour(which, v) { saveSettings({ [which]: Number(v) }); applyTheme(); }

  // --- Live shape/layout preview ---------------------------------------------
  const DENSITY = { comfortable: [11, 11, 34], compact: [6, 9, 28], cozy: [15, 13, 36] };
  const dens = $derived(DENSITY[app.settings.density] || DENSITY.comfortable);

  function setMode(mode) { saveSettings({ themeMode: mode }); applyTheme(); }
  function setRadius(v) { saveSettings({ radius: Number(v) }); applyTheme(); }
  function setScale(v) { saveSettings({ uiScale: Number(v) }); applyTheme(); }
  function setCss(v) { saveSettings({ customCss: v }); applyTheme(); }
  function reset() {
    saveSettings({ theme: {}, themeMode: "manual" });
    applyTheme();
    notify("Theme reset to default");
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>Mode</h3>
    <label class="radio"><input type="radio" name="tmode" checked={!auto} onchange={() => setMode("manual")} />
      <div><b>Manual</b><span>Use the preset / colors you pick below.</span></div></label>
    <label class="radio"><input type="radio" name="tmode" checked={auto} onchange={() => setMode("auto")} />
      <div><b>Auto (day / night)</b><span>Switch themes by time of day. Overrides your manual colors while on.</span></div></label>
    {#if auto}
      <div class="daynight">
        <label class="dn"><span>Day theme</span>
          <select value={keyForTheme(app.settings.dayTheme, "light")} onchange={(e) => setDayNight("dayTheme", e.currentTarget.value)}>
            {#each themeChoices as c}<option value={c.key}>{c.name}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>from</span>
          <select value={app.settings.dayStart ?? 7} onchange={(e) => setHour("dayStart", e.currentTarget.value)}>
            {#each HOURS as h}<option value={h}>{(h % 12 || 12)}:00 {h < 12 ? "AM" : "PM"}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>Night theme</span>
          <select value={keyForTheme(app.settings.nightTheme, "dark")} onchange={(e) => setDayNight("nightTheme", e.currentTarget.value)}>
            {#each themeChoices as c}<option value={c.key}>{c.name}</option>{/each}
          </select>
        </label>
        <label class="dn"><span>from</span>
          <select value={app.settings.nightStart ?? 19} onchange={(e) => setHour("nightStart", e.currentTarget.value)}>
            {#each HOURS as h}<option value={h}>{(h % 12 || 12)}:00 {h < 12 ? "AM" : "PM"}</option>{/each}
          </select>
        </label>
      </div>
      <p class="hint" style="margin:10px 0 0">Tip: build a look under Custom colors, hit <b>Save as preset</b>, then pick it here as your day or night theme.</p>
    {/if}
  </section>

  <section class="card" class:dim={auto}>
    <h3>Presets</h3>
    <p class="hint">Each preview shows the actual background, panel and accent — pick a mood, then fine-tune below.</p>
    {#if userPresets.length}
      <div class="preset-cat">Yours</div>
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
            <button class="updel" title="Delete preset" onclick={() => deleteUserPreset(p.id)}>×</button>
          </div>
        {/each}
      </div>
    {/if}
    {#each presetGroups as g}
      <div class="preset-cat">{g.cat}</div>
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
    {/each}
  </section>

  <section class="card" class:dim={auto}>
    <div class="head"><h3>Custom colors</h3>
      <div class="head-btns">
        <button class="btn ghost" onclick={saveAsPreset}>Save as preset</button>
        <button class="btn ghost" onclick={reset}>Reset all</button>
      </div>
    </div>
    <div class="gen">
      <span class="gen-lbl">Generate from one color</span>
      <input class="gen-swatch" type="color" bind:value={genAccent} title="Accent color" />
      <div class="seg">
        <button class="segbtn" class:on={genBase === "dark"} onclick={() => (genBase = "dark")}>Dark base</button>
        <button class="segbtn" class:on={genBase === "light"} onclick={() => (genBase = "light")}>Light base</button>
      </div>
      <button class="btn" onclick={applyGenerated}>Generate palette</button>
    </div>
    <p class="hint">Or tune each token below — every one is a CSS variable used across the whole app.</p>
    <div class="tokens">
      {#each THEME_TOKENS as [token, def]}
        <label class="token">
          <input type="color" value={val(token, def)} oninput={(e) => setToken(token, e.currentTarget.value)} />
          <span class="tname">{LABELS[token] || token}</span>
          <span class="tval">{val(token, def)}</span>
        </label>
      {/each}
    </div>
  </section>

  <section class="card">
    <h3>Shape & layout</h3>
    <!-- Live preview: a mock message row + button that reflect the roundness and
         density below as you drag, so you see the effect before committing. -->
    <div class="lp" style="--lp-r:{app.settings.radius}px">
      <div class="lp-lbl">Preview</div>
      <div class="lp-card">
        <div class="lp-row" style="padding:{dens[0]}px 12px; gap:{dens[1]}px">
          <span class="lp-av" style="width:{dens[2]}px; height:{dens[2]}px"></span>
          <span class="lp-txt">
            <span class="lp-l1"></span>
            <span class="lp-l2"></span>
          </span>
          <span class="lp-btn">Done</span>
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
      <span>Text &amp; UI size</span>
      <input type="range" min="0.8" max="1.4" step="0.05" value={app.settings.uiScale ?? 1} oninput={(e) => setScale(e.currentTarget.value)} />
      <span class="val">{Math.round((app.settings.uiScale ?? 1) * 100)}%</span>
    </label>
    <label class="slider-row">
      <span>Corner roundness</span>
      <input type="range" min="0" max="22" value={app.settings.radius} oninput={(e) => setRadius(e.currentTarget.value)} />
      <span class="val">{app.settings.radius}px</span>
    </label>
    <div class="field">
      <b>Message density</b>
      <span class="fhint">How tightly rows are packed in the message list.</span>
      <div class="seg">
        {#each [
          { v: "compact", t: "Compact", d: "Tightest — fit the most messages on screen." },
          { v: "comfortable", t: "Comfortable", d: "The default balance of density and breathing room." },
          { v: "cozy", t: "Cozy", d: "Roomiest — extra padding and a larger avatar." },
        ] as o}
          <button class="segbtn" class:on={(app.settings.density || "comfortable") === o.v} title={o.d}
            onclick={() => { saveSettings({ density: o.v }); applyTheme(); }}>{o.t}</button>
        {/each}
      </div>
    </div>
    <div class="field">
      <b>Reading width</b>
      <span class="fhint">Cap the width of email bodies so long lines don't stretch across a wide screen.</span>
      <div class="seg">
        {#each [
          { v: 0, t: "Full" }, { v: 680, t: "Narrow" }, { v: 820, t: "Medium" }, { v: 1000, t: "Wide" },
        ] as o}
          <button class="segbtn" class:on={(app.settings.emailMaxWidth ?? 820) === o.v}
            onclick={() => saveSettings({ emailMaxWidth: o.v })}>{o.t}</button>
        {/each}
      </div>
    </div>
    <div class="field">
      <b>Email appearance</b>
      <span class="fhint">How email bodies are rendered in a dark theme.</span>
      <div class="seg">
        {#each [
          { v: "dark", t: "Dark", d: "Force a dark background on every email — no white, ever." },
          { v: "adaptive", t: "Adaptive", d: "Dark pane for plain mail; branded mail keeps its own design." },
          { v: "original", t: "Original", d: "Show every email exactly as the sender designed it (white)." },
        ] as o}
          <button class="segbtn" class:on={emailMode === o.v} title={o.d}
            onclick={() => saveSettings({ emailTheme: o.v })}>{o.t}</button>
        {/each}
      </div>
      <span class="fhint">{emailMode === "dark" ? "Near-white backgrounds are recolored to your theme; saturated brand colors are kept." : emailMode === "adaptive" ? "Plain emails get a dark pane; designed emails are left untouched on white." : "No adaptation — emails render on a white reading pane as authored."}</span>
    </div>
    <div class="field">
      <b>Reply / action buttons</b>
      <span class="fhint">Where Reply · Forward · Done sit when reading a message.</span>
      <div class="seg">
        <button class="segbtn" class:on={(app.settings.readerActionsPos || "top") === "top"} onclick={() => saveSettings({ readerActionsPos: "top" })}>Top</button>
        <button class="segbtn" class:on={app.settings.readerActionsPos === "bottom"} onclick={() => saveSettings({ readerActionsPos: "bottom" })}>Bottom-right</button>
      </div>
    </div>
    <label class="check">
      <input type="checkbox" checked={app.settings.collapseQuotes !== false}
        onchange={(e) => saveSettings({ collapseQuotes: e.currentTarget.checked })} />
      <div>
        <b>Collapse quoted replies</b>
        <span>Show the new message plus the most-recent quoted reply, with older "On … wrote:" history behind a "Show earlier messages" toggle. Turn off to always show the full thread.</span>
      </div>
    </label>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.linkUnfurls}
        onchange={(e) => saveSettings({ linkUnfurls: e.currentTarget.checked })} />
      <div>
        <b>Rich link previews</b>
        <span>Show a preview card (title, image) for the main link in a message. Off by default — enabling fetches the linked page from your machine.</span>
      </div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.highlightCode !== false}
        onchange={(e) => saveSettings({ highlightCode: e.currentTarget.checked })} />
      <div>
        <b>Syntax-highlight code blocks</b>
        <span>Color keywords, strings, and comments inside <code>&lt;pre&gt;</code> code blocks in messages. Language-agnostic.</span>
      </div>
    </label>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.relativeTime}
        onchange={(e) => saveSettings({ relativeTime: e.currentTarget.checked })} />
      <div>
        <b>Relative timestamps</b>
        <span>Show "3 hours ago" in the message list instead of a date/clock.</span>
      </div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.senderAvatars !== false}
        onchange={(e) => saveSettings({ senderAvatars: e.currentTarget.checked })} />
      <div>
        <b>Sender logos as avatars</b>
        <span>Show each sender's brand logo by fetching their domain's favicon (cached locally after the first time). Falls back to initials. Off = always initials — and no domain lookups leave your machine.</span>
      </div>
    </label>
    <p class="hint" style="margin:12px 0 0">Tip: turn on <b>Customize layout</b> (lock icon in the sidebar) to drag-resize the columns.</p>
  </section>

  <section class="card">
    <h3>Quick-action buttons</h3>
    <p class="fhint">The two buttons that appear on each message row when you hover.</p>
    <div class="rowbtns">
      {#each [0, 1] as idx}
        <label class="inline">{idx === 0 ? "Left" : "Right"}
          <select value={(app.settings.rowActions || ["snooze", "done"])[idx]} onchange={(e) => setRowAction(idx, e.currentTarget.value)}>
            {#each ROW_CHOICES as [val, label]}<option value={val}>{label}</option>{/each}
          </select>
        </label>
      {/each}
    </div>
    <p class="fhint" style="margin-top:16px">Buttons shown under the recipient when reading a message.</p>
    <div class="rdrcats">
      {#each READER_CHOICES as [val, label]}
        <label class="grp"><input type="checkbox"
          checked={(app.settings.readerActions || READER_CHOICES.map((c) => c[0])).includes(val)}
          onchange={(e) => toggleReaderAction(val, e.currentTarget.checked)} /> <span>{label}</span></label>
      {/each}
    </div>
  </section>

  <section class="card">
    <h3>Custom CSS</h3>
    <p class="hint">Power-user escape hatch — applied app-wide and live. Target the classes and
      CSS variables in the reference below.</p>
    <textarea class="css" spellcheck="false" placeholder={'.btn.primary { border-radius: 999px; }\n.row { font-size: 15px; }\n:root { --accent: #ff5d8f; }'}
      value={app.settings.customCss} oninput={(e) => setCss(e.currentTarget.value)}></textarea>

    <label class="check" style="padding-top:12px">
      <input type="checkbox" checked={!!app.settings.customCssInEmails}
        onchange={(e) => saveSettings({ customCssInEmails: e.currentTarget.checked })} />
      <div>
        <b>Apply custom CSS inside emails</b>
        <span>By default your CSS styles only the app, not message bodies. Enable to also inject it into the email reading pane.</span>
      </div>
    </label>

    <details class="docs">
      <summary>Reference — selectors &amp; variables</summary>
      <p class="dh">Elements</p>
      <table>
        <tbody>
          {#each SELECTORS as [sel, desc]}
            <tr><td><code>{sel}</code></td><td>{desc}</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="dh">CSS variables <span class="dim">(override under <code>:root</code>)</span></p>
      <table>
        <tbody>
          <tr><td><code>--radius</code></td><td>Corner roundness (also <code>--radius-sm</code>)</td></tr>
          {#each Object.entries(LABELS) as [token, label]}
            <tr><td><code>{token}</code></td><td>{label}</td></tr>
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
  .segbtn.on { background: var(--accent); color: #fff; }
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
  .presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 10px; }
  .preset { display: flex; flex-direction: column; align-items: stretch; gap: 8px; padding: 8px; border: 1px solid var(--border);
    border-radius: var(--radius); background: var(--surface-2); font-weight: 550; text-align: center;
    transition: border-color var(--t-fast) var(--ease), transform var(--t-fast) var(--ease); }
  .preset:hover { border-color: var(--accent); transform: translateY(-1px); }
  .preset.active { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft-2); }
  /* Mini live-preview of the theme: real background, a panel bar, an accent dot,
     and a "text" line — so light/dark/black read at a glance. */
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
  .lp-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); margin-bottom: 6px; }
  .lp-card { border: 1px solid var(--border); border-radius: var(--lp-r); overflow: hidden; background: var(--surface-2); }
  .lp-row { display: flex; align-items: center; }
  .lp-row.alt { border-top: 1px solid var(--hairline); }
  .lp-av { flex: none; border-radius: 50%; background: var(--accent-soft); }
  .lp-txt { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .lp-l1 { height: 8px; width: 55%; border-radius: 999px; background: var(--muted); opacity: 0.75; }
  .lp-l2 { height: 7px; width: 78%; border-radius: 999px; background: var(--faint); opacity: 0.6; }
  .lp-l1.short { width: 38%; } .lp-l2.short { width: 60%; }
  .lp-btn { flex: none; font-size: 11px; font-weight: 600; color: #fff; background: var(--accent); padding: 5px 12px; border-radius: var(--lp-r); }
</style>
