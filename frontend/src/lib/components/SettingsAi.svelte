<script>
  import { onDestroy } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { ai, openExternal } from "../api.js";
  import { icons } from "../icons.js";

  const aiProv = $derived(app.settings.aiProvider || "anthropic");
  // AI actions are "on" once a key is set — or immediately for keyless local Ollama.
  const aiActive = $derived(!!app.settings.aiApiKey || aiProv === "ollama");

  // --- Ollama (local, keyless AI) -----------------------------------------
  let ollama = $state({ loading: false, installed: false, running: false, models: [], base_url: "", version: "" });
  let pullName = $state("");
  let pull = $state(null);       // { active, model, status, percent, error, done }
  let install = $state(null);    // { active, status, error, done, ok }
  let unloading = $state(false);
  let starting = $state(false);
  let _pullTimer, _installTimer;

  async function startOllama() {
    starting = true;
    try {
      const r = await ai.ollamaStart(app.settings.aiBaseUrl || "");
      notify(r.running ? "Ollama started" : "Couldn't start Ollama — is it installed?", r.running ? "info" : "error");
    } catch (e) { notify(e.message || "Couldn't start Ollama", "error"); }
    finally { starting = false; refreshOllama(); }
  }
  async function restartOllama() {
    starting = true;
    try {
      const r = await ai.ollamaRestart(app.settings.aiBaseUrl || "");
      notify(r.running ? "Ollama restarted" : "Restarted, but couldn't confirm it's up", r.running ? "info" : "error");
    } catch (e) { notify(e.message || "Couldn't restart Ollama", "error"); }
    finally { starting = false; refreshOllama(); }
  }

  async function refreshOllama() {
    ollama.loading = true;
    try {
      ollama = { loading: false, ...(await ai.ollamaStatus(app.settings.aiBaseUrl || "")) };
      // Fix the #1 Ollama footgun: if the selected model isn't actually pulled (or
      // none is set), the backend falls back to its default (llama3.2) and every
      // call 404s. Auto-select the first installed model so it just works.
      if ((app.settings.aiProvider || "") === "ollama" && (ollama.models || []).length) {
        const cur = (app.settings.aiModel || "").trim();
        const ok = cur && ollama.models.some((m) => sameModel(m, cur));
        if (!ok) saveSettings({ aiModel: ollama.models[0] });
      }
    } catch { ollama = { ...ollama, loading: false }; }
  }
  async function updateOllama() {
    try { await ai.ollamaUpdate(); install = { active: true, status: "updating…" }; pollInstall(); }
    catch (e) { notify((e.message || "Couldn't start update") + " — opening the download page", "error"); openExternal("https://ollama.com/download"); }
  }
  async function freeGpu() {
    unloading = true;
    try { const r = await ai.ollamaUnload(); notify(r.unloaded?.length ? `Freed GPU (unloaded ${r.unloaded.join(", ")})` : "No model was loaded"); }
    catch (e) { notify(e.message, "error"); }
    finally { unloading = false; }
  }
  let _activateAfterPull = null;   // model to switch to once its pull finishes
  function pollPull() {
    clearInterval(_pullTimer);
    _pullTimer = setInterval(async () => {
      try {
        pull = await ai.ollamaPullStatus();
        if (pull?.done) {
          clearInterval(_pullTimer);
          if (pull.error) { notify("Pull failed: " + pull.error, "error"); }
          else {
            if (_activateAfterPull) { saveSettings({ aiModel: _activateAfterPull }); _activateAfterPull = null; }
            notify("Model ready");
          }
          refreshOllama();
        }
      } catch { clearInterval(_pullTimer); }
    }, 900);
  }
  async function startPull(model, activate = false) {
    const m = (model || pullName).trim();
    if (!m) return;
    _activateAfterPull = activate ? m : null;
    try { await ai.ollamaPull(m, app.settings.aiBaseUrl || ""); pull = { active: true, model: m, status: "starting", percent: 0 }; pollPull(); }
    catch (e) { notify(e.message, "error"); }
  }

  // One-click setup: switch to Ollama, turn on AI, adaptive GPU, and pull+use the
  // tier's model. If it's already installed, just switch to it. ollamaManaged runs
  // our own hidden serve so the model-runner console windows never flash.
  function quickSetup(model) {
    saveSettings({ aiProvider: "ollama", aiButtons: true, ollamaKeepAlive: "adaptive", ollamaManaged: true });
    ai.ollamaManaged(true).catch(() => {});   // bring the hidden serve up now
    if (isInstalled(model)) { useModel(model, "chat"); notify("All set — " + model + " is ready."); }
    else startPull(model, true);
  }

  // --- Live model search (ollama.com library — never stale) ---------------
  let modelQuery = $state("");
  let searchResults = $state([]);
  let searching = $state(false);
  let _searchTimer;
  function searchModels() {
    clearTimeout(_searchTimer);   // debounce
    const q = modelQuery.trim();
    if (q.length < 2) { searchResults = []; return; }
    searching = true;
    _searchTimer = setTimeout(async () => {
      try { const r = await ai.ollamaSearch(q); searchResults = r.models || []; }
      catch { searchResults = []; }
      finally { searching = false; }
    }, 350);
  }
  function pollInstall() {
    clearInterval(_installTimer);
    _installTimer = setInterval(async () => {
      try {
        install = await ai.ollamaInstallStatus();
        if (install?.done) {
          clearInterval(_installTimer);
          if (install.ok) {
            notify(install.action === "upgrade" ? "Ollama updated (" + (install.status || "done") + ")" : "Ollama installed — start it, then refresh");
            refreshOllama();
          } else notify(install.error || "Didn't complete — try the manual download", "error");
        }
      } catch { clearInterval(_installTimer); }
    }, 1500);
  }
  async function startInstall() {
    try { await ai.ollamaInstall(); install = { active: true, status: "starting" }; pollInstall(); }
    catch (e) { notify((e.message || "Couldn't start install") + " — opening the download page", "error"); openExternal("https://ollama.com/download"); }
  }

  // --- Semantic search index ----------------------------------------------
  let embed = $state(null);      // { enabled, reachable, indexed, total, model, backend, indexing }
  let _embedTimer;
  async function refreshEmbed() {
    try { embed = await ai.embedStatus(); }
    catch { embed = null; }
  }
  function pollEmbed() {
    clearInterval(_embedTimer);
    _embedTimer = setInterval(async () => {
      await refreshEmbed();
      if (!embed?.indexing) clearInterval(_embedTimer);
    }, 2000);
  }
  async function buildIndex() {
    try { await ai.embedReindex(); notify("Building semantic index in the background…"); await refreshEmbed(); pollEmbed(); }
    catch (e) { notify(e.message, "error"); }
  }

  // --- Curated model catalog (there's no official Ollama "list all models" API,
  // so this is a hand-picked, up-to-date-with-releases list; installed state comes
  // live from Ollama's /api/tags). Grouped by the GPU they realistically need. ---
  const TIER_LABEL = {
    low: "⚡ Runs on most machines (small / CPU-friendly)",
    mid: "⚖ Mid-range GPU (~8 GB VRAM)",
    high: "🚀 High-end GPU",
  };
  const CHAT_MODELS = [
    { name: "llama3.2:3b", size: "2 GB", tier: "low", note: "Fast, great default" },
    { name: "qwen2.5:3b", size: "1.9 GB", tier: "low", note: "Small, strong multilingual" },
    { name: "qwen2.5:7b", size: "4.7 GB", tier: "mid", note: "Great multilingual — good for Czech" },
    { name: "gemma3:12b", size: "8 GB", tier: "mid", note: "Google Gemma 3" },
    { name: "llama3.1:8b", size: "4.9 GB", tier: "mid", note: "Well-rounded" },
    { name: "mistral:7b", size: "4.1 GB", tier: "mid", note: "Fast and capable" },
    { name: "qwen2.5:14b", size: "9 GB", tier: "high", note: "Excellent multilingual" },
    { name: "gemma3:27b", size: "17 GB", tier: "high", note: "Top quality (Gemma 3)" },
    { name: "llama3.3:70b", size: "43 GB", tier: "high", note: "Best — needs lots of VRAM" },
  ];
  // Defaults the one-click quick-setup buttons pull for each GPU tier.
  const QUICK_SETUP = [
    { tier: "low", model: "llama3.2:3b", label: "⚡ Fast", sub: "Any PC · 2 GB" },
    { tier: "mid", model: "qwen2.5:7b", label: "⚖ Balanced", sub: "Good GPU · 4.7 GB · multilingual" },
    { tier: "high", model: "gemma3:27b", label: "🚀 Best", sub: "Strong GPU · 17 GB" },
  ];
  const EMBED_MODELS = [
    { name: "nomic-embed-text", size: "274 MB", tier: "low", note: "Default. Fast, good quality" },
    { name: "all-minilm", size: "46 MB", tier: "low", note: "Tiny, very fast" },
    { name: "bge-m3", size: "1.2 GB", tier: "mid", note: "Multilingual — great for Czech search" },
    { name: "mxbai-embed-large", size: "670 MB", tier: "mid", note: "Higher-quality embeddings" },
  ];
  const TIERS = ["low", "mid", "high"];
  // Model identity, tag-aware but tolerant of the default tag:
  //  - gemma3:12b vs gemma3:27b  -> DIFFERENT (both explicit sizes)
  //  - mistral:7b (our catalog) vs mistral / mistral:latest (what you pulled) -> SAME
  // i.e. a bare name or ":latest" is the family default and matches any single
  // catalog tag; two explicit non-latest tags must match exactly. (The old
  // base-name match lit up every gemma3 variant as "Using" at once.)
  const _parts = (s) => {
    s = (s || "").trim(); const i = s.indexOf(":");
    return i < 0 ? [s.toLowerCase(), ""] : [s.slice(0, i).toLowerCase(), s.slice(i + 1).toLowerCase()];
  };
  function sameModel(a, b) {
    const [ba, ta] = _parts(a), [bb, tb] = _parts(b);
    if (ba !== bb) return false;
    const defA = !ta || ta === "latest", defB = !tb || tb === "latest";
    return defA || defB ? true : ta === tb;
  }
  const isInstalled = (name) => (ollama.models || []).some((m) => sameModel(m, name));
  const chatActive = $derived(app.settings.aiModel || (ollama.models || [])[0] || "");
  const embedActive = $derived(app.settings.embedModel || "nomic-embed-text");
  const isActive = (name, kind) => sameModel(kind === "embed" ? embedActive : chatActive, name);
  function useModel(name, kind) { saveSettings(kind === "embed" ? { embedModel: name } : { aiModel: name }); }

  // Keep Ollama status fresh whenever it's the chat OR the embeddings provider.
  $effect(() => {
    if ((app.settings.aiProvider || "anthropic") === "ollama"
        || (app.settings.semanticEnabled && (app.settings.embedProvider || "ollama") === "ollama")) refreshOllama();
  });
  $effect(() => { if (app.settings.semanticEnabled) refreshEmbed(); });
  onDestroy(() => { clearInterval(_pullTimer); clearInterval(_installTimer); clearInterval(_embedTimer); clearTimeout(_searchTimer); });
</script>

{#snippet modelPicker(catalog, kind)}
  <div class="mpick">
    {#each TIERS as tier}
      {@const items = catalog.filter((m) => m.tier === tier)}
      {#if items.length}
        <div class="tierhead">{TIER_LABEL[tier]}</div>
        {#each items as m}
          <div class="mrow" class:active={isActive(m.name, kind)}>
            <div class="minfo">
              <span class="mname">{m.name}</span><span class="msize">{m.size}</span>
              <span class="mnote">{m.note}</span>
            </div>
            {#if isActive(m.name, kind)}
              <span class="musing">{@html icons.done} Using</span>
            {:else if isInstalled(m.name)}
              <span class="minstalled">Installed</span>
              <button class="btn sm" onclick={() => useModel(m.name, kind)}>Use</button>
            {:else}
              <button class="btn sm ghost" onclick={() => startPull(m.name)} disabled={pull?.active}>↓ Pull</button>
            {/if}
          </div>
        {/each}
      {/if}
    {/each}
  </div>
{/snippet}

<div class="wrap">
  <section class="card">
    <h3>AI assistant <span class="tag">{aiProv === "ollama" ? "local · private" : "bring your own key"}</span></h3>
    <p class="hint">Powers the AI assistant, “Catch me up”, AI reply, compose rewrites, and inbox triage. Calls go
      straight from this app to the provider you choose — there's no RaplMail server in between. Pick <b>Ollama</b> for a
      fully local, offline model (nothing leaves your machine).</p>
    <label class="fieldrow"><span>Provider</span>
      <select value={aiProv} onchange={(e) => saveSettings({ aiProvider: e.currentTarget.value })}>
        <option value="ollama">Ollama (local, private)</option>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="openai">OpenAI</option>
        <option value="openai-compatible">OpenAI-compatible (Groq, OpenRouter, LM Studio, …)</option>
      </select>
    </label>

    {#if aiProv === "ollama"}
      <div class="ollama">
        <div class="ollama-head">
          <span class="dot" class:on={ollama.running}></span>
          <b>{ollama.running ? "Ollama is running" : ollama.installed ? "Ollama installed (not running)" : "Ollama not detected"}</b>
          {#if ollama.version}<span class="ver">v{ollama.version}</span>{/if}
          <button class="btn ghost sm" onclick={refreshOllama} disabled={ollama.loading}>{@html icons.sync} {ollama.loading ? "…" : "Refresh"}</button>
          {#if ollama.installed || ollama.running}
            <button class="btn ghost sm" onclick={restartOllama} disabled={starting} title="Stop and start the Ollama server (fixes a stuck server)">{starting ? "…" : "Restart"}</button>
          {/if}
        </div>
        {#if ollama.installed || ollama.running}
          <label class="autostart">
            <input type="checkbox" checked={app.settings.ollamaAutostart === true}
              onchange={(e) => { saveSettings({ ollamaAutostart: e.currentTarget.checked }); if (e.currentTarget.checked && !ollama.running) startOllama(); }} />
            <span>Start Ollama automatically when RaplMail launches</span>
          </label>
        {/if}
        {#if !ollama.installed && !ollama.running}
          <p class="hint">Ollama runs open models (Llama, Qwen, Mistral…) locally. Install it once, then pull a model.</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startInstall} disabled={install?.active}>
              {install?.active ? (install.status || "Installing…") : "Install Ollama (winget)"}
            </button>
            <button class="btn" onclick={() => openExternal("https://ollama.com/download")}>Download manually</button>
          </div>
          {#if install?.error}<p class="hint err">{install.error}</p>{/if}
        {:else if ollama.running}
          <div class="quicksetup">
            <span class="lab2">✨ One-click setup — pick your hardware, RaplMail pulls the model &amp; switches everything on</span>
            <div class="qsrow">
              {#each QUICK_SETUP as qs}
                <button class="qsbtn" class:on={isActive(qs.model, "chat")} onclick={() => quickSetup(qs.model)} disabled={pull?.active}>
                  <b>{qs.label}</b><span class="qsmodel">{qs.model}</span><span class="qssub">{qs.sub}</span>
                </button>
              {/each}
            </div>
          </div>
          <label class="fieldrow"><span>Active model</span>
            {#if ollama.models.length}
              <select value={app.settings.aiModel || ollama.models[0]} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value })}>
                {#each ollama.models as m}<option value={m}>{m}</option>{/each}
              </select>
            {:else}
              <input placeholder="llama3.2" value={app.settings.aiModel || ""} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
            {/if}
          </label>
          {#if !ollama.models.length}<p class="hint">No models yet — use one-click setup above, or pick/search below.</p>{/if}
          <div class="pullrow">
            <span class="lab2">Recommended — “Use” to switch, “Pull” to download</span>
            {@render modelPicker(CHAT_MODELS, "chat")}
          </div>
          <div class="pullrow">
            <span class="lab2">Search all Ollama models <span class="live">live</span></span>
            <input class="msearch" placeholder="Search… e.g. gemma, qwen, deepseek, phi" bind:value={modelQuery} oninput={searchModels} />
            {#if searching}
              <p class="hint">Searching ollama.com…</p>
            {:else if searchResults.length}
              <div class="mpick">
                {#each searchResults as name}
                  <div class="mrow" class:active={isActive(name, "chat")}>
                    <div class="minfo"><span class="mname">{name}</span></div>
                    {#if isActive(name, "chat")}<span class="musing">{@html icons.done} Using</span>
                    {:else if isInstalled(name)}<span class="minstalled">Installed</span><button class="btn sm" onclick={() => useModel(name, "chat")}>Use</button>
                    {:else}<button class="btn sm ghost" onclick={() => startPull(name)} disabled={pull?.active}>↓ Pull</button>{/if}
                  </div>
                {/each}
              </div>
            {:else if modelQuery.trim().length >= 2}
              <p class="hint">No matches — or couldn't reach ollama.com (you can still “Pull” a name directly below).</p>
            {/if}
            <div class="pullcustom">
              <input placeholder="…or pull an exact name/tag (e.g. gemma3:12b)" bind:value={pullName} onkeydown={(e) => { if (e.key === "Enter") startPull(); }} />
              <button class="btn" onclick={() => startPull()} disabled={pull?.active || !pullName.trim()}>Pull</button>
            </div>
          </div>
          {#if pull?.active || (pull && !pull.done)}
            <div class="prog"><div class="bar" style="width:{pull.percent || 0}%"></div></div>
            <p class="hint">{pull.model}: {pull.status} {pull.percent ? `(${pull.percent}%)` : ""}</p>
          {/if}
          <label class="fieldrow" style="margin-top:10px"><span>Free GPU after</span>
            <select value={app.settings.ollamaKeepAlive || "5m"} onchange={(e) => saveSettings({ ollamaKeepAlive: e.currentTarget.value })}>
              <option value="adaptive">Adaptive — load when RaplMail is focused, free when it isn't</option>
              <option value="0">Immediately (unload after each request)</option>
              <option value="30s">30 seconds idle</option>
              <option value="1m">1 minute idle</option>
              <option value="5m">5 minutes idle (default)</option>
              <option value="30m">30 minutes idle</option>
              <option value="-1">Keep loaded (fastest, most GPU)</option>
            </select>
          </label>
          {#if (app.settings.ollamaKeepAlive || "5m") === "adaptive"}
            <p class="hint" style="margin:0">Adaptive: the model loads into VRAM when the RaplMail window is focused and is freed a few seconds after you switch away — unless you're mid-question. Ready when you are, off when you're not.</p>
          {/if}
          <label class="check" style="margin-top:10px">
            <input type="checkbox" checked={app.settings.ollamaManaged !== false}
              onchange={(e) => { const v = e.currentTarget.checked; saveSettings({ ollamaManaged: v }); ai.ollamaManaged(v).catch(() => {}); refreshOllama(); }} />
            <span>Hide Ollama's console windows <small>— RaplMail runs its own hidden Ollama server so the model loader never flashes black windows on load/unload (Windows). Your tray Ollama is left running but idle.</small></span>
          </label>
          <div class="rowbtns" style="margin-top:10px">
            <button class="btn" onclick={freeGpu} disabled={unloading}>{@html icons.bolt} {unloading ? "Freeing…" : "Free GPU now"}</button>
            <button class="btn ghost" onclick={updateOllama} disabled={install?.active}>{install?.active ? (install.status || "Updating…") : "Update Ollama"}</button>
          </div>
          <p class="hint" style="margin-top:8px">Ollama keeps the model in VRAM after each request for fast follow-ups — that's the idle GPU use. Lower “Free GPU after” frees it sooner (at the cost of a reload on the next request). RaplMail also unloads the model when you close the AI assistant or leave a message where you used AI.</p>
        {:else}
          <p class="hint">Ollama is installed but the server isn't running. Start it here to use local AI.</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startOllama} disabled={starting}>{@html icons.bolt} {starting ? "Starting…" : "Start Ollama"}</button>
            <button class="btn" onclick={restartOllama} disabled={starting}>Restart</button>
          </div>
        {/if}
        <details class="adv"><summary>Advanced</summary>
          <label class="fieldrow"><span>Server URL</span>
            <input placeholder="http://localhost:11434" value={app.settings.aiBaseUrl || ""}
              onchange={(e) => { saveSettings({ aiBaseUrl: e.currentTarget.value.trim() }); refreshOllama(); }} />
          </label>
        </details>
      </div>
    {:else}
      <label class="fieldrow"><span>API key</span>
        <input type="password" placeholder={aiProv === "anthropic" ? "sk-ant-…" : "sk-…"}
          value={app.settings.aiApiKey || ""}
          onchange={(e) => saveSettings({ aiApiKey: e.currentTarget.value.trim() })} />
      </label>
      {#if aiProv === "openai-compatible"}
        <label class="fieldrow"><span>API base URL</span>
          <input placeholder="https://api.groq.com/openai/v1" value={app.settings.aiBaseUrl || ""}
            onchange={(e) => saveSettings({ aiBaseUrl: e.currentTarget.value.trim() })} />
        </label>
      {/if}
      <label class="fieldrow"><span>Model (optional)</span>
        <input placeholder={aiProv === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"}
          value={app.settings.aiModel || ""}
          onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
      </label>
      <p class="hint">{app.settings.aiApiKey ? "✓ Key set — AI actions are active." : "No key — AI buttons stay hidden until you add one."}</p>
    {/if}
    {#if aiActive}
      <label class="check">
        <input type="checkbox" checked={app.settings.aiButtons !== false}
          onchange={(e) => saveSettings({ aiButtons: e.currentTarget.checked })} />
        <div><b>Show AI buttons</b><span>“Catch me up” / “AI reply” in the reader, the composer AI menu, and the assistant. Turn off to hide them even when a provider is set.</span></div>
      </label>
    {/if}
    <label class="check">
      <input type="checkbox" checked={!!app.settings.digestEnabled}
        onchange={(e) => saveSettings({ digestEnabled: e.currentTarget.checked })} />
      <div>
        <b>Daily morning briefing</b>
        <span>Once a day, deliver an AI digest of your unread inbox as a notification (needs a provider above).</span>
      </div>
    </label>
    {#if app.settings.digestEnabled}
      <label class="fieldrow"><span>Deliver at</span>
        <select value={app.settings.digestHour ?? 8} onchange={(e) => saveSettings({ digestHour: Number(e.currentTarget.value) })}>
          {#each Array(24) as _, h}<option value={h}>{String(h).padStart(2, "0")}:00</option>{/each}
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>Semantic search <span class="tag">local · offline</span></h3>
    <p class="hint">Search your mail by <b>meaning</b>, not just exact words — “that quote about server migration costs”
      finds the right message even if it never used those exact words. RaplMail builds a local vector index using an
      embedding model; the vectors stay on this machine. Default source is <b>Ollama</b>, so nothing leaves your network.</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.semanticEnabled}
        onchange={(e) => { saveSettings({ semanticEnabled: e.currentTarget.checked }); if (e.currentTarget.checked) refreshEmbed(); }} />
      <div><b>Enable semantic search</b><span>Adds a “Smart” mode to the advanced search modal. Indexing runs quietly in the background.</span></div>
    </label>
    {#if app.settings.semanticEnabled}
      <label class="fieldrow"><span>Embeddings source</span>
        <select value={app.settings.embedProvider || "ollama"} onchange={(e) => { saveSettings({ embedProvider: e.currentTarget.value }); refreshEmbed(); }}>
          <option value="ollama">Ollama (local)</option>
          <option value="openai-compatible">OpenAI-compatible</option>
        </select>
      </label>
      {#if (app.settings.embedProvider || "ollama") === "openai-compatible"}
        <label class="fieldrow"><span>Base URL</span>
          <input placeholder="https://api.openai.com/v1" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
        <label class="fieldrow"><span>API key</span>
          <input type="password" placeholder="sk-…" value={app.settings.embedApiKey || ""}
            onchange={(e) => saveSettings({ embedApiKey: e.currentTarget.value.trim() })} />
        </label>
      {:else}
        <label class="fieldrow"><span>Server URL</span>
          <input placeholder="http://localhost:11434" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
      {/if}
      <label class="fieldrow"><span>Model</span>
        <input placeholder={(app.settings.embedProvider || "ollama") === "ollama" ? "nomic-embed-text" : "text-embedding-3-small"}
          value={app.settings.embedModel || ""} onchange={(e) => { saveSettings({ embedModel: e.currentTarget.value.trim() }); refreshEmbed(); }} />
      </label>
      {#if (app.settings.embedProvider || "ollama") === "ollama"}
        {#if ollama.running}
          <div class="pullrow" style="margin-top:6px">
            <span class="lab2">Recommended embedding models</span>
            {@render modelPicker(EMBED_MODELS, "embed")}
          </div>
        {:else}
          <p class="hint">Start Ollama (in the AI assistant tab above) to pick or pull an embedding model. Suggested: <code>nomic-embed-text</code>, <code>bge-m3</code> (multilingual).</p>
        {/if}
      {:else}
        <p class="hint warn-note">⚠ A cloud embeddings endpoint will send every indexed message's subject &amp; snippet to that provider and may cost money. For true zero-cloud, use Ollama.</p>
      {/if}

      <div class="embed-status">
        {#if embed}
          <span class="dot" class:on={embed.reachable}></span>
          <span>{embed.reachable ? "Endpoint reachable" : "Endpoint unreachable"} · <b>{embed.indexed}</b> / {embed.total} indexed · {embed.backend}</span>
        {:else}
          <span class="hint">Checking…</span>
        {/if}
      </div>
      <div class="rowbtns">
        <button class="btn primary" onclick={buildIndex} disabled={embed?.indexing}>
          {@html icons.sync} {embed?.indexing ? "Indexing…" : "Build / update index"}
        </button>
        <button class="btn ghost sm" onclick={refreshEmbed}>Refresh status</button>
      </div>
    {/if}
  </section>
</div>

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .hint.err { color: var(--danger); }
  .hint.warn-note { color: var(--warning); }
  .hint code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .check div { display: flex; flex-direction: column; gap: 2px; }
  .check span { color: var(--muted); font-size: 12px; }
  .check input { margin-top: 3px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .rowbtns { display: flex; gap: 12px; flex-wrap: wrap; }
  .tag { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 2px 7px; border-radius: 999px; background: var(--surface-3); color: var(--accent); vertical-align: middle; margin-left: 6px; }
  .fieldrow { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .fieldrow > span { width: 140px; flex: none; color: var(--muted); font-size: 13px; }
  .fieldrow input, .fieldrow select { flex: 1; }
  /* Ollama local-AI panel */
  .ollama { margin-top: 12px; padding: 12px 14px; background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); display: flex; flex-direction: column; gap: 10px; }
  .ollama-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .ollama-head b { font-size: 13px; }
  .ollama-head .ver { font-size: 11px; color: var(--faint); font-family: ui-monospace, monospace; }
  /* Right-align the action buttons as a group (Refresh, Restart). */
  .ollama-head > button:first-of-type { margin-left: auto; }
  .autostart { display: flex; align-items: center; gap: 8px; margin: 8px 0 2px; font-size: 13px; color: var(--text); cursor: pointer; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--faint); flex: none; }
  .dot.on { background: var(--done); box-shadow: 0 0 0 3px color-mix(in srgb, var(--done) 25%, transparent); }
  .pullrow { display: flex; flex-direction: column; gap: 8px; }
  .lab2 { font-size: 12px; color: var(--muted); }
  .lab2 .live { font-size: 9px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--done);
    border: 1px solid var(--done); border-radius: 999px; padding: 0 5px; margin-left: 4px; }
  /* One-click quick setup */
  .quicksetup { display: flex; flex-direction: column; gap: 8px; padding-bottom: 4px; }
  .qsrow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .qsbtn { display: flex; flex-direction: column; gap: 2px; align-items: flex-start; text-align: left; padding: 10px 12px;
    border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text); }
  .qsbtn:hover:not(:disabled) { border-color: var(--accent); }
  .qsbtn.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
  .qsbtn:disabled { opacity: 0.5; }
  .qsbtn b { font-size: 13px; }
  .qsmodel { font-size: 11px; font-family: ui-monospace, monospace; color: var(--accent); }
  .qssub { font-size: 10.5px; color: var(--faint); }
  .msearch { width: 100%; box-sizing: border-box; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 11px; color: var(--text); font-size: 13px; }
  .msearch:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent); }
  /* Tiered model picker */
  .mpick { display: flex; flex-direction: column; gap: 3px; }
  .tierhead { font-size: 11px; color: var(--faint); font-weight: 600; margin: 8px 0 2px; }
  .mrow { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--surface); }
  .mrow.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--surface)); }
  .minfo { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .mname { font-size: 13px; font-weight: 600; font-family: ui-monospace, monospace; }
  .msize { font-size: 11px; color: var(--faint); }
  .mnote { font-size: 12px; color: var(--muted); }
  .musing { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: var(--accent); white-space: nowrap; }
  .musing :global(svg) { width: 13px; height: 13px; }
  /* Installed-but-not-active: a quiet tag so you can see what you already have. */
  .minstalled { font-size: 11px; font-weight: 600; color: var(--done); white-space: nowrap;
    padding: 2px 8px; border-radius: 999px; background: var(--done-soft); }
  .pullcustom { display: flex; gap: 8px; }
  .pullcustom input { flex: 1; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; color: var(--text); }
  .prog { height: 6px; background: var(--surface-3); border-radius: 999px; overflow: hidden; }
  .prog .bar { height: 100%; background: var(--accent); transition: width 0.3s ease; }
  .adv { margin-top: 2px; }
  .adv summary { font-size: 12px; color: var(--muted); cursor: pointer; }
  .btn.sm { padding: 4px 9px; font-size: 12px; }
  .embed-status { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); margin: 12px 0; }
</style>
