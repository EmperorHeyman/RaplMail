<script>
  import { app, saveSettings, applyTheme, THEME_TOKENS, LIGHT_THEME, notify } from "../store.svelte.js";

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
    ["done", "Done"], ["flag", "Flag"],
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

  // Accent-led presets (override a few tokens; rest stay default).
  const PRESETS = [
    { name: "Dark", theme: {} },
    { name: "Light", theme: LIGHT_THEME },
    { name: "Indigo", theme: { "--accent": "#8b5cf6", "--bg": "#0f0d18", "--surface": "#171425", "--surface-2": "#1f1b30", "--surface-3": "#2a2542" } },
    { name: "Emerald", theme: { "--accent": "#2bd4a0", "--bg": "#0b1310", "--surface": "#101a15", "--surface-2": "#16241d" } },
    { name: "Sunset", theme: { "--accent": "#ff7a59", "--warning": "#ffb02e" } },
    { name: "Rose", theme: { "--accent": "#ff5d8f" } },
    { name: "Slate", theme: { "--accent": "#9aa6bf", "--bg": "#101216", "--surface": "#191c22" } },
    // Editor themes — for those who like their mail like their VSCode.
    { name: "One Dark", theme: { "--bg": "#282c34", "--surface": "#21252b", "--surface-2": "#2c313a", "--surface-3": "#3a3f4b", "--border": "#3a3f4b", "--text": "#abb2bf", "--muted": "#7f848e", "--accent": "#61afef", "--done": "#98c379", "--danger": "#e06c75", "--warning": "#e5c07b" } },
    { name: "Dracula", theme: { "--bg": "#282a36", "--surface": "#21222c", "--surface-2": "#343746", "--surface-3": "#44475a", "--border": "#44475a", "--text": "#f8f8f2", "--muted": "#9aa0c0", "--accent": "#bd93f9", "--done": "#50fa7b", "--danger": "#ff5555", "--warning": "#f1fa8c" } },
    { name: "Monokai", theme: { "--bg": "#272822", "--surface": "#1f201b", "--surface-2": "#34352c", "--surface-3": "#49483e", "--border": "#3e3d32", "--text": "#f8f8f2", "--muted": "#a59f85", "--accent": "#a6e22e", "--done": "#a6e22e", "--danger": "#f92672", "--warning": "#e6db74" } },
    { name: "Nord", theme: { "--bg": "#2e3440", "--surface": "#2b303b", "--surface-2": "#3b4252", "--surface-3": "#434c5e", "--border": "#3b4252", "--text": "#eceff4", "--muted": "#aebacf", "--accent": "#88c0d0", "--done": "#a3be8c", "--danger": "#bf616a", "--warning": "#ebcb8b" } },
    { name: "Gruvbox", theme: { "--bg": "#282828", "--surface": "#1d2021", "--surface-2": "#32302f", "--surface-3": "#3c3836", "--border": "#3c3836", "--text": "#ebdbb2", "--muted": "#a89984", "--accent": "#fabd2f", "--done": "#b8bb26", "--danger": "#fb4934", "--warning": "#fe8019" } },
    { name: "Solarized", theme: { "--bg": "#002b36", "--surface": "#073642", "--surface-2": "#0a4453", "--surface-3": "#0d5263", "--border": "#094352", "--text": "#93a1a1", "--muted": "#6a8186", "--accent": "#268bd2", "--done": "#859900", "--danger": "#dc322f", "--warning": "#b58900" } },
    { name: "Tokyo Night", theme: { "--bg": "#1a1b26", "--surface": "#16161e", "--surface-2": "#24283b", "--surface-3": "#2f334d", "--border": "#292e42", "--text": "#c0caf5", "--muted": "#7f88b3", "--accent": "#7aa2f7", "--done": "#9ece6a", "--danger": "#f7768e", "--warning": "#e0af68" } },
    { name: "GitHub Dark", theme: { "--bg": "#0d1117", "--surface": "#161b22", "--surface-2": "#21262d", "--surface-3": "#30363d", "--border": "#30363d", "--text": "#c9d1d9", "--muted": "#8b949e", "--accent": "#58a6ff", "--done": "#3fb950", "--danger": "#f85149", "--warning": "#d29922" } },
  ];

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
      <div><b>Auto (day / night)</b><span>Light theme 7am–7pm, dark otherwise. Overrides custom colors while on.</span></div></label>
  </section>

  <section class="card" class:dim={auto}>
    <h3>Presets</h3>
    <div class="presets">
      {#each PRESETS as p}
        <button class="preset" onclick={() => applyPreset(p)}>
          <span class="swatch" style="background:{p.theme['--accent'] || '#5b8def'}"></span>{p.name}
        </button>
      {/each}
    </div>
  </section>

  <section class="card" class:dim={auto}>
    <div class="head"><h3>Custom colors</h3><button class="btn ghost" onclick={reset}>Reset all</button></div>
    <p class="hint">Changes apply live. Each is a CSS variable used across the whole app.</p>
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
  .presets { display: flex; gap: 10px; flex-wrap: wrap; }
  .preset { display: flex; align-items: center; gap: 8px; padding: 9px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); font-weight: 550; }
  .preset:hover { border-color: var(--accent); }
  .swatch { width: 14px; height: 14px; border-radius: 50%; }
  .tokens { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .token { display: flex; align-items: center; gap: 10px; }
  .token input[type=color] { width: 38px; height: 30px; padding: 2px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); cursor: pointer; }
  .tname { flex: 1; font-size: 13px; }
  .tval { font-size: 11px; color: var(--faint); font-family: ui-monospace, monospace; }
</style>
