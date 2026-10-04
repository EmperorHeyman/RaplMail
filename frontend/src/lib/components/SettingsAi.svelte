<script>
  import { onDestroy } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import { ai, openExternal } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  const aiProv = $derived(app.settings.aiProvider || "anthropic");
  // AI actions are "on" once a key is set - or immediately for keyless local Ollama.
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
      notify(r.running ? t("sAi.ollamaStarted") : t("sAi.startFailedInstalled"), r.running ? "info" : "error");
    } catch (e) { notify(e.message || t("sAi.startFailed"), "error"); }
    finally { starting = false; refreshOllama(); }
  }
  async function restartOllama() {
    starting = true;
    try {
      const r = await ai.ollamaRestart(app.settings.aiBaseUrl || "");
      notify(r.running ? t("sAi.ollamaRestarted") : t("sAi.restartUnconfirmed"), r.running ? "info" : "error");
    } catch (e) { notify(e.message || t("sAi.restartFailed"), "error"); }
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
    try { await ai.ollamaUpdate(); install = { active: true, status: t("sAi.statusUpdating") }; pollInstall(); }
    catch (e) { notify(t("sAi.openingDownload", { error: e.message || t("sAi.updateStartFailed") }), "error"); openExternal("https://ollama.com/download"); }
  }
  async function freeGpu() {
    unloading = true;
    try { const r = await ai.ollamaUnload(); notify(r.unloaded?.length ? t("sAi.freedGpu", { models: r.unloaded.join(", ") }) : t("sAi.noModelLoaded")); }
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
          if (pull.error) { notify(t("sAi.pullFailed", { error: pull.error }), "error"); }
          else {
            if (_activateAfterPull) { saveSettings({ aiModel: _activateAfterPull }); _activateAfterPull = null; }
            notify(t("sAi.modelReady"));
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
    try { await ai.ollamaPull(m, app.settings.aiBaseUrl || ""); pull = { active: true, model: m, status: t("sAi.statusStarting"), percent: 0 }; pollPull(); }
    catch (e) { notify(e.message, "error"); }
  }

  // One-click setup: switch to Ollama, turn on AI, adaptive GPU, and pull+use the
  // tier's model. If it's already installed, just switch to it. ollamaManaged runs
  // our own hidden serve so the model-runner console windows never flash.
  function quickSetup(model) {
    saveSettings({ aiProvider: "ollama", aiButtons: true, ollamaKeepAlive: "adaptive", ollamaManaged: true });
    ai.ollamaManaged(true).catch(() => {});   // bring the hidden serve up now
    if (isInstalled(model)) { useModel(model, "chat"); notify(t("sAi.allSet", { model })); }
    else startPull(model, true);
  }

  // --- Live model search (ollama.com library - never stale) ---------------
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
            notify(install.action === "upgrade" ? t("sAi.ollamaUpdated", { status: install.status || t("sAi.statusDone") }) : t("sAi.ollamaInstalled"));
            refreshOllama();
          } else notify(install.error || t("sAi.installIncomplete"), "error");
        }
      } catch { clearInterval(_installTimer); }
    }, 1500);
  }
  async function startInstall() {
    try { await ai.ollamaInstall(); install = { active: true, status: t("sAi.statusStarting") }; pollInstall(); }
    catch (e) { notify(t("sAi.openingDownload", { error: e.message || t("sAi.installStartFailed") }), "error"); openExternal("https://ollama.com/download"); }
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
    try { await ai.embedReindex(); notify(t("sAi.buildingIndex")); await refreshEmbed(); pollEmbed(); }
    catch (e) { notify(e.message, "error"); }
  }
  function pullEmbedModel() {
    startPull(embedActive);   // downloads it; embedModel already points here
    setTimeout(refreshEmbed, 1500);
  }
  function turnOffSemantic() {
    saveSettings({ semanticEnabled: false });
    notify(t("sAi.semanticOff"));
  }

  // --- Curated model catalog (there's no official Ollama "list all models" API,
  // so this is a hand-picked, up-to-date-with-releases list; installed state comes
  // live from Ollama's /api/tags). Grouped by the GPU they realistically need. ---
  // $derived.by so the labels/notes re-translate on a language switch.
  const TIER_LABEL = $derived.by(() => ({
    low: t("sAi.tierLow"),
    mid: t("sAi.tierMid"),
    high: t("sAi.tierHigh"),
  }));
  const CHAT_MODELS = $derived.by(() => [
    { name: "llama3.2:3b", size: "2 GB", tier: "low", note: t("sAi.noteLlama32") },
    { name: "qwen2.5:3b", size: "1.9 GB", tier: "low", note: t("sAi.noteQwen3b") },
    { name: "qwen2.5:7b", size: "4.7 GB", tier: "mid", note: t("sAi.noteQwen7b") },
    { name: "mistral:7b", size: "4.1 GB", tier: "mid", note: t("sAi.noteMistral7b") },
    { name: "llama3.1:8b", size: "4.9 GB", tier: "mid", note: t("sAi.noteLlama31") },
    { name: "mistral-nemo:12b", size: "7 GB", tier: "mid", note: t("sAi.noteMistralNemo") },
    { name: "gemma3:12b", size: "8 GB", tier: "mid", note: t("sAi.noteGemma12b") },
    { name: "qwen2.5:14b", size: "9 GB", tier: "high", note: t("sAi.noteQwen14b") },
    { name: "phi4:14b", size: "9 GB", tier: "high", note: t("sAi.notePhi4") },
    { name: "gemma3:27b", size: "17 GB", tier: "high", note: t("sAi.noteGemma27b") },
    { name: "llama3.3:70b", size: "43 GB", tier: "high", note: t("sAi.noteLlama33") },
  ]);
  // Defaults the one-click quick-setup buttons pull for each GPU tier.
  const QUICK_SETUP = $derived.by(() => [
    { tier: "low", model: "llama3.2:3b", label: t("sAi.qsFast"), sub: t("sAi.qsFastSub") },
    { tier: "mid", model: "mistral-nemo:12b", label: t("sAi.qsBalanced"), sub: t("sAi.qsBalancedSub") },
    { tier: "high", model: "qwen2.5:14b", label: t("sAi.qsBest"), sub: t("sAi.qsBestSub") },
  ]);
  const EMBED_MODELS = $derived.by(() => [
    { name: "nomic-embed-text", size: "274 MB", tier: "low", note: t("sAi.noteNomic") },
    { name: "all-minilm", size: "46 MB", tier: "low", note: t("sAi.noteMinilm") },
    { name: "bge-m3", size: "1.2 GB", tier: "mid", note: t("sAi.noteBgeM3") },
    { name: "mxbai-embed-large", size: "670 MB", tier: "mid", note: t("sAi.noteMxbai") },
  ]);
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
              <span class="musing">{@html icons.done} {t("sAi.using")}</span>
            {:else if isInstalled(m.name)}
              <span class="minstalled">{t("sAi.installed")}</span>
              <button class="btn sm" onclick={() => useModel(m.name, kind)}>{t("sAi.use")}</button>
            {:else}
              <button class="btn sm ghost" onclick={() => startPull(m.name)} disabled={pull?.active}>↓ {t("sAi.pull")}</button>
            {/if}
          </div>
        {/each}
      {/if}
    {/each}
  </div>
{/snippet}

<div class="wrap">
  <section class="card">
    <h3>{t("sAi.title")} <span class="tag">{aiProv === "ollama" ? t("sAi.tagLocal") : t("sAi.tagByok")}</span></h3>
    <p class="hint">{t("sAi.introA")} <b>Ollama</b> {t("sAi.introB")}</p>
    <label class="fieldrow"><span>{t("sAi.provider")}</span>
      <select value={aiProv} onchange={(e) => saveSettings({ aiProvider: e.currentTarget.value })}>
        <option value="ollama">{t("sAi.provOllama")}</option>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="openai">OpenAI</option>
        <option value="openai-compatible">{t("sAi.provCompatible")}</option>
      </select>
    </label>

    {#if aiProv === "ollama"}
      <div class="ollama">
        <div class="ollama-head">
          <span class="dot" class:on={ollama.running}></span>
          <b>{ollama.running ? t("sAi.running") : ollama.installed ? t("sAi.installedNotRunning") : t("sAi.notDetected")}</b>
          {#if ollama.version}<span class="ver">v{ollama.version}</span>{/if}
          <button class="btn ghost sm" onclick={refreshOllama} disabled={ollama.loading}>{@html icons.sync} {ollama.loading ? "…" : t("sAi.refresh")}</button>
          {#if ollama.installed || ollama.running}
            <button class="btn ghost sm" onclick={restartOllama} disabled={starting} title={t("sAi.restartTitle")}>{starting ? "…" : t("sAi.restart")}</button>
          {/if}
        </div>
        {#if ollama.installed || ollama.running}
          <label class="autostart">
            <input type="checkbox" checked={app.settings.ollamaAutostart === true}
              onchange={(e) => { saveSettings({ ollamaAutostart: e.currentTarget.checked }); if (e.currentTarget.checked && !ollama.running) startOllama(); }} />
            <span>{t("sAi.autostart")}</span>
          </label>
        {/if}
        {#if !ollama.installed && !ollama.running}
          <p class="hint">{t("sAi.installHint")}</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startInstall} disabled={install?.active}>
              {install?.active ? (install.status || t("sAi.installing")) : t("sAi.install")}
            </button>
            <button class="btn" onclick={() => openExternal("https://ollama.com/download")}>{t("sAi.downloadManually")}</button>
          </div>
          {#if install?.error}<p class="hint err">{install.error}</p>{/if}
        {:else if ollama.running}
          <div class="quicksetup">
            <span class="lab2">{t("sAi.quickSetup")}</span>
            <div class="qsrow">
              {#each QUICK_SETUP as qs}
                <button class="qsbtn" class:on={isActive(qs.model, "chat")} onclick={() => quickSetup(qs.model)} disabled={pull?.active}>
                  <b>{qs.label}</b><span class="qsmodel">{qs.model}</span><span class="qssub">{qs.sub}</span>
                </button>
              {/each}
            </div>
          </div>
          <label class="fieldrow"><span>{t("sAi.activeModel")}</span>
            {#if ollama.models.length}
              <select value={app.settings.aiModel || ollama.models[0]} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value })}>
                {#each ollama.models as m}<option value={m}>{m}</option>{/each}
              </select>
            {:else}
              <input placeholder="llama3.2" value={app.settings.aiModel || ""} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
            {/if}
          </label>
          {#if !ollama.models.length}<p class="hint">{t("sAi.noModels")}</p>{/if}
          <div class="pullrow">
            <span class="lab2">{t("sAi.recommended")}</span>
            {@render modelPicker(CHAT_MODELS, "chat")}
          </div>
          <div class="pullrow">
            <span class="lab2">{t("sAi.searchAll")} <span class="live">{t("sAi.live")}</span></span>
            <input class="msearch" placeholder={t("sAi.searchPlaceholder")} bind:value={modelQuery} oninput={searchModels} />
            {#if searching}
              <p class="hint">{t("sAi.searching")}</p>
            {:else if searchResults.length}
              <div class="mpick">
                {#each searchResults as name}
                  <div class="mrow" class:active={isActive(name, "chat")}>
                    <div class="minfo"><span class="mname">{name}</span></div>
                    {#if isActive(name, "chat")}<span class="musing">{@html icons.done} {t("sAi.using")}</span>
                    {:else if isInstalled(name)}<span class="minstalled">{t("sAi.installed")}</span><button class="btn sm" onclick={() => useModel(name, "chat")}>{t("sAi.use")}</button>
                    {:else}<button class="btn sm ghost" onclick={() => startPull(name)} disabled={pull?.active}>↓ {t("sAi.pull")}</button>{/if}
                  </div>
                {/each}
              </div>
            {:else if modelQuery.trim().length >= 2}
              <p class="hint">{t("sAi.noMatches")}</p>
            {/if}
            <div class="pullcustom">
              <input placeholder={t("sAi.pullPlaceholder")} bind:value={pullName} onkeydown={(e) => { if (e.key === "Enter") startPull(); }} />
              <button class="btn" onclick={() => startPull()} disabled={pull?.active || !pullName.trim()}>{t("sAi.pull")}</button>
            </div>
          </div>
          {#if pull?.active || (pull && !pull.done)}
            <div class="prog"><div class="bar" style="width:{pull.percent || 0}%"></div></div>
            <p class="hint">{pull.model}: {pull.status} {pull.percent ? `(${pull.percent}%)` : ""}</p>
          {/if}
          <label class="fieldrow" style="margin-top:10px"><span>{t("sAi.freeAfter")}</span>
            <select value={app.settings.ollamaKeepAlive || "5m"} onchange={(e) => saveSettings({ ollamaKeepAlive: e.currentTarget.value })}>
              <option value="adaptive">{t("sAi.keepAdaptive")}</option>
              <option value="0">{t("sAi.keepNow")}</option>
              <option value="30s">{t("sAi.keep30s")}</option>
              <option value="1m">{t("sAi.keep1m")}</option>
              <option value="5m">{t("sAi.keep5m")}</option>
              <option value="30m">{t("sAi.keep30m")}</option>
              <option value="-1">{t("sAi.keepForever")}</option>
            </select>
          </label>
          {#if (app.settings.ollamaKeepAlive || "5m") === "adaptive"}
            <p class="hint" style="margin:0">{t("sAi.adaptiveHint")}</p>
          {/if}
          <label class="check" style="margin-top:10px">
            <input type="checkbox" checked={app.settings.ollamaManaged !== false}
              onchange={(e) => { const v = e.currentTarget.checked; saveSettings({ ollamaManaged: v }); ai.ollamaManaged(v).catch(() => {}); refreshOllama(); }} />
            <span>{t("sAi.hideConsole")} <small>- {t("sAi.hideConsoleHint")}</small></span>
          </label>
          <div class="rowbtns" style="margin-top:10px">
            <button class="btn" onclick={freeGpu} disabled={unloading}>{@html icons.bolt} {unloading ? t("sAi.freeing") : t("sAi.freeNow")}</button>
            <button class="btn ghost" onclick={updateOllama} disabled={install?.active}>{install?.active ? (install.status || t("sAi.updating")) : t("sAi.update")}</button>
          </div>
          <p class="hint" style="margin-top:8px">{t("sAi.vramHint")}</p>
        {:else}
          <p class="hint">{t("sAi.notRunningHint")}</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startOllama} disabled={starting}>{@html icons.bolt} {starting ? t("sAi.starting") : t("sAi.start")}</button>
            <button class="btn" onclick={restartOllama} disabled={starting}>{t("sAi.restart")}</button>
          </div>
        {/if}
        <details class="adv"><summary>{t("sAi.advanced")}</summary>
          <label class="fieldrow"><span>{t("sAi.serverUrl")}</span>
            <input placeholder="http://localhost:11434" value={app.settings.aiBaseUrl || ""}
              onchange={(e) => { saveSettings({ aiBaseUrl: e.currentTarget.value.trim() }); refreshOllama(); }} />
          </label>
        </details>
      </div>
    {:else}
      <label class="fieldrow"><span>{t("sAi.apiKey")}</span>
        <input type="password" placeholder={aiProv === "anthropic" ? "sk-ant-…" : "sk-…"}
          value={app.settings.aiApiKey || ""}
          onchange={(e) => saveSettings({ aiApiKey: e.currentTarget.value.trim() })} />
      </label>
      {#if aiProv === "openai-compatible"}
        <label class="fieldrow"><span>{t("sAi.apiBaseUrl")}</span>
          <input placeholder="https://api.groq.com/openai/v1" value={app.settings.aiBaseUrl || ""}
            onchange={(e) => saveSettings({ aiBaseUrl: e.currentTarget.value.trim() })} />
        </label>
      {/if}
      <label class="fieldrow"><span>{t("sAi.modelOptional")}</span>
        <input placeholder={aiProv === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"}
          value={app.settings.aiModel || ""}
          onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
      </label>
      <p class="hint">{app.settings.aiApiKey ? t("sAi.keySet") : t("sAi.noKey")}</p>
    {/if}
    {#if aiActive}
      <label class="check">
        <input type="checkbox" checked={app.settings.aiButtons !== false}
          onchange={(e) => saveSettings({ aiButtons: e.currentTarget.checked })} />
        <div><b>{t("sAi.showButtons")}</b><span>{t("sAi.showButtonsHint")}</span></div>
      </label>
    {/if}
    <label class="check">
      <input type="checkbox" checked={!!app.settings.digestEnabled}
        onchange={(e) => saveSettings({ digestEnabled: e.currentTarget.checked })} />
      <div>
        <b>{t("sAi.digest")}</b>
        <span>{t("sAi.digestHint")}</span>
      </div>
    </label>
    {#if app.settings.digestEnabled}
      <label class="fieldrow"><span>{t("sAi.deliverAt")}</span>
        <select value={app.settings.digestHour ?? 8} onchange={(e) => saveSettings({ digestHour: Number(e.currentTarget.value) })}>
          {#each Array(24) as _, h}<option value={h}>{String(h).padStart(2, "0")}:00</option>{/each}
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>{t("sAi.semTitle")} <span class="tag">{t("sAi.semTag")}</span></h3>
    <p class="hint">{t("sAi.semIntroA")} <b>{t("sAi.semIntroMeaning")}</b>{t("sAi.semIntroB")} <b>Ollama</b>{t("sAi.semIntroC")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.semanticEnabled}
        onchange={(e) => { saveSettings({ semanticEnabled: e.currentTarget.checked }); if (e.currentTarget.checked) refreshEmbed(); }} />
      <div><b>{t("sAi.semEnable")}</b><span>{t("sAi.semEnableHint")}</span></div>
    </label>
    {#if app.settings.semanticEnabled}
      <label class="fieldrow"><span>{t("sAi.embedSource")}</span>
        <select value={app.settings.embedProvider || "ollama"} onchange={(e) => { saveSettings({ embedProvider: e.currentTarget.value }); refreshEmbed(); }}>
          <option value="ollama">{t("sAi.embedOllama")}</option>
          <option value="openai-compatible">{t("sAi.embedCompatible")}</option>
        </select>
      </label>
      {#if (app.settings.embedProvider || "ollama") === "openai-compatible"}
        <label class="fieldrow"><span>{t("sAi.baseUrl")}</span>
          <input placeholder="https://api.openai.com/v1" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
        <label class="fieldrow"><span>{t("sAi.apiKey")}</span>
          <input type="password" placeholder="sk-…" value={app.settings.embedApiKey || ""}
            onchange={(e) => saveSettings({ embedApiKey: e.currentTarget.value.trim() })} />
        </label>
      {:else}
        <label class="fieldrow"><span>{t("sAi.serverUrl")}</span>
          <input placeholder="http://localhost:11434" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
      {/if}
      <label class="fieldrow"><span>{t("sAi.model")}</span>
        <input placeholder={(app.settings.embedProvider || "ollama") === "ollama" ? "nomic-embed-text" : "text-embedding-3-small"}
          value={app.settings.embedModel || ""} onchange={(e) => { saveSettings({ embedModel: e.currentTarget.value.trim() }); refreshEmbed(); }} />
      </label>
      {#if (app.settings.embedProvider || "ollama") === "ollama"}
        {#if ollama.running}
          <div class="pullrow" style="margin-top:6px">
            <span class="lab2">{t("sAi.embedRecommended")}</span>
            {@render modelPicker(EMBED_MODELS, "embed")}
          </div>
        {:else}
          <p class="hint">{t("sAi.embedStartHint")} <code>nomic-embed-text</code>, <code>bge-m3</code> {t("sAi.embedMultilingual")}</p>
        {/if}
      {:else}
        <p class="hint warn-note">{t("sAi.cloudWarn")}</p>
      {/if}

      {#if embed && embed.enabled && embed.model_installed === false}
        <div class="embed-warn">
          <b>{t("sAi.embedMissingTitle")}</b>
          <span>{t("sAi.embedMissingA")} <code>{embed.model}</code> {t("sAi.embedMissingB")}</span>
          <div class="rowbtns">
            <button class="btn primary sm" onclick={pullEmbedModel} disabled={pull?.active}>↓ {t("sAi.pullModel", { model: embed.model })}</button>
            <button class="btn ghost sm" onclick={turnOffSemantic}>{t("sAi.turnOffSemantic")}</button>
          </div>
        </div>
      {/if}

      <div class="embed-status">
        {#if embed}
          <span class="dot" class:on={embed.reachable}></span>
          <span>{embed.reachable ? t("sAi.reachable") : t("sAi.unreachable")} · <b>{embed.indexed}</b> / {embed.total} {t("sAi.indexed")} · {embed.backend}</span>
        {:else}
          <span class="hint">{t("sAi.checking")}</span>
        {/if}
      </div>
      <div class="rowbtns">
        <button class="btn primary" onclick={buildIndex} disabled={embed?.indexing}>
          {@html icons.sync} {embed?.indexing ? t("sAi.indexing") : t("sAi.buildIndex")}
        </button>
        <button class="btn ghost sm" onclick={refreshEmbed}>{t("sAi.refreshStatus")}</button>
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
  .embed-warn { display: flex; flex-direction: column; gap: 6px; margin: 10px 0; padding: 12px 14px;
    border: 1px solid color-mix(in srgb, var(--warning, #d29922) 55%, var(--border)); border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--warning, #d29922) 12%, transparent); }
  .embed-warn b { font-size: 13.5px; }
  .embed-warn span { color: var(--muted); font-size: 12.5px; line-height: 1.5; }
  .embed-warn code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  .embed-warn .rowbtns { margin-top: 4px; }
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
