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
      notify(r.running ? t("setai.ollamaStarted") : t("setai.ollamaStartFail"), r.running ? "info" : "error");
    } catch (e) { notify(e.message || t("setai.ollamaStartErr"), "error"); }
    finally { starting = false; refreshOllama(); }
  }
  async function restartOllama() {
    starting = true;
    try {
      const r = await ai.ollamaRestart(app.settings.aiBaseUrl || "");
      notify(r.running ? t("setai.ollamaRestarted") : t("setai.ollamaRestartUnsure"), r.running ? "info" : "error");
    } catch (e) { notify(e.message || t("setai.ollamaRestartErr"), "error"); }
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
    try { await ai.ollamaUpdate(); install = { active: true, status: t("setai.statusUpdating") }; pollInstall(); }
    catch (e) { notify((e.message || t("setai.couldntStartUpdate")) + " - " + t("setai.openingDownload"), "error"); openExternal("https://ollama.com/download"); }
  }
  async function freeGpu() {
    unloading = true;
    try { const r = await ai.ollamaUnload(); notify(r.unloaded?.length ? t("setai.freedGpu", { models: r.unloaded.join(", ") }) : t("setai.noModelLoaded")); }
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
          if (pull.error) { notify(t("setai.pullFailed", { error: pull.error }), "error"); }
          else {
            if (_activateAfterPull) { saveSettings({ aiModel: _activateAfterPull }); _activateAfterPull = null; }
            notify(t("setai.modelReady"));
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
    try { await ai.ollamaPull(m, app.settings.aiBaseUrl || ""); pull = { active: true, model: m, status: t("setai.statusStarting"), percent: 0 }; pollPull(); }
    catch (e) { notify(e.message, "error"); }
  }

  // One-click setup: switch to Ollama, turn on AI, adaptive GPU, and pull+use the
  // tier's model. If it's already installed, just switch to it. ollamaManaged runs
  // our own hidden serve so the model-runner console windows never flash.
  function quickSetup(model) {
    saveSettings({ aiProvider: "ollama", aiButtons: true, ollamaKeepAlive: "adaptive", ollamaManaged: true });
    ai.ollamaManaged(true).catch(() => {});   // bring the hidden serve up now
    if (isInstalled(model)) { useModel(model, "chat"); notify(t("setai.allSetReady", { model })); }
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
            notify(install.action === "upgrade" ? t("setai.ollamaUpdated", { status: install.status || t("setai.statusDone") }) : t("setai.ollamaInstalledMsg"));
            refreshOllama();
          } else notify(install.error || t("setai.installIncomplete"), "error");
        }
      } catch { clearInterval(_installTimer); }
    }, 1500);
  }
  async function startInstall() {
    try { await ai.ollamaInstall(); install = { active: true, status: t("setai.statusStarting") }; pollInstall(); }
    catch (e) { notify((e.message || t("setai.couldntStartInstall")) + " - " + t("setai.openingDownload"), "error"); openExternal("https://ollama.com/download"); }
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
    try { await ai.embedReindex(); notify(t("setai.buildingIndex")); await refreshEmbed(); pollEmbed(); }
    catch (e) { notify(e.message, "error"); }
  }
  function pullEmbedModel() {
    startPull(embedActive);   // downloads it; embedModel already points here
    setTimeout(refreshEmbed, 1500);
  }
  function turnOffSemantic() {
    saveSettings({ semanticEnabled: false });
    notify(t("setai.semanticOffMsg"));
  }

  // --- Curated model catalog (there's no official Ollama "list all models" API,
  // so this is a hand-picked, up-to-date-with-releases list; installed state comes
  // live from Ollama's /api/tags). Grouped by the GPU they realistically need. ---
  // (labels/notes are i18n keys, resolved with t() in the markup)
  const TIER_LABEL = {
    low: "setai.tierLow",
    mid: "setai.tierMid",
    high: "setai.tierHigh",
  };
  const CHAT_MODELS = [
    { name: "llama3.2:3b", size: "2 GB", tier: "low", note: "setai.noteLlama32_3b" },
    { name: "qwen2.5:3b", size: "1.9 GB", tier: "low", note: "setai.noteQwen25_3b" },
    { name: "qwen2.5:7b", size: "4.7 GB", tier: "mid", note: "setai.noteQwen25_7b" },
    { name: "mistral:7b", size: "4.1 GB", tier: "mid", note: "setai.noteMistral7b" },
    { name: "llama3.1:8b", size: "4.9 GB", tier: "mid", note: "setai.noteLlama31_8b" },
    { name: "mistral-nemo:12b", size: "7 GB", tier: "mid", note: "setai.noteMistralNemo" },
    { name: "gemma3:12b", size: "8 GB", tier: "mid", note: "setai.noteGemma3_12b" },
    { name: "qwen2.5:14b", size: "9 GB", tier: "high", note: "setai.noteQwen25_14b" },
    { name: "phi4:14b", size: "9 GB", tier: "high", note: "setai.notePhi4" },
    { name: "gemma3:27b", size: "17 GB", tier: "high", note: "setai.noteGemma3_27b" },
    { name: "llama3.3:70b", size: "43 GB", tier: "high", note: "setai.noteLlama33_70b" },
  ];
  // Defaults the one-click quick-setup buttons pull for each GPU tier.
  const QUICK_SETUP = [
    { tier: "low", model: "llama3.2:3b", label: "setai.qsFastLabel", sub: "setai.qsFastSub" },
    { tier: "mid", model: "mistral-nemo:12b", label: "setai.qsBalancedLabel", sub: "setai.qsBalancedSub" },
    { tier: "high", model: "qwen2.5:14b", label: "setai.qsBestLabel", sub: "setai.qsBestSub" },
  ];
  const EMBED_MODELS = [
    { name: "nomic-embed-text", size: "274 MB", tier: "low", note: "setai.noteNomic" },
    { name: "all-minilm", size: "46 MB", tier: "low", note: "setai.noteMinilm" },
    { name: "bge-m3", size: "1.2 GB", tier: "mid", note: "setai.noteBgeM3" },
    { name: "mxbai-embed-large", size: "670 MB", tier: "mid", note: "setai.noteMxbai" },
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
        <div class="tierhead">{t(TIER_LABEL[tier])}</div>
        {#each items as m}
          <div class="mrow" class:active={isActive(m.name, kind)}>
            <div class="minfo">
              <span class="mname">{m.name}</span><span class="msize">{m.size}</span>
              <span class="mnote">{t(m.note)}</span>
            </div>
            {#if isActive(m.name, kind)}
              <span class="musing">{@html icons.done} {t("setai.using")}</span>
            {:else if isInstalled(m.name)}
              <span class="minstalled">{t("setai.installed")}</span>
              <button class="btn sm" onclick={() => useModel(m.name, kind)}>{t("setai.use")}</button>
            {:else}
              <button class="btn sm ghost" onclick={() => startPull(m.name)} disabled={pull?.active}>{t("setai.pullArrow")}</button>
            {/if}
          </div>
        {/each}
      {/if}
    {/each}
  </div>
{/snippet}

<div class="wrap">
  <section class="card">
    <h3>{t("setai.title")} <span class="tag">{aiProv === "ollama" ? t("setai.tagLocal") : t("setai.tagByok")}</span></h3>
    <p class="hint">{t("setai.introA")}<b>Ollama</b>{t("setai.introB")}</p>
    <label class="fieldrow"><span>{t("setai.provider")}</span>
      <select value={aiProv} onchange={(e) => saveSettings({ aiProvider: e.currentTarget.value })}>
        <option value="ollama">{t("setai.provOllama")}</option>
        <option value="anthropic">{t("setai.provAnthropic")}</option>
        <option value="openai">{t("setai.provOpenai")}</option>
        <option value="openai-compatible">{t("setai.provOpenaiCompat")}</option>
      </select>
    </label>

    {#if aiProv === "ollama"}
      <div class="ollama">
        <div class="ollama-head">
          <span class="dot" class:on={ollama.running}></span>
          <b>{ollama.running ? t("setai.olRunning") : ollama.installed ? t("setai.olInstalledNotRunning") : t("setai.olNotDetected")}</b>
          {#if ollama.version}<span class="ver">v{ollama.version}</span>{/if}
          <button class="btn ghost sm" onclick={refreshOllama} disabled={ollama.loading}>{@html icons.sync} {ollama.loading ? "…" : t("setai.refresh")}</button>
          {#if ollama.installed || ollama.running}
            <button class="btn ghost sm" onclick={restartOllama} disabled={starting} title={t("setai.restartTip")}>{starting ? "…" : t("setai.restart")}</button>
          {/if}
        </div>
        {#if ollama.installed || ollama.running}
          <label class="autostart">
            <input type="checkbox" checked={app.settings.ollamaAutostart === true}
              onchange={(e) => { saveSettings({ ollamaAutostart: e.currentTarget.checked }); if (e.currentTarget.checked && !ollama.running) startOllama(); }} />
            <span>{t("setai.autostart")}</span>
          </label>
        {/if}
        {#if !ollama.installed && !ollama.running}
          <p class="hint">{t("setai.olIntro")}</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startInstall} disabled={install?.active}>
              {install?.active ? (install.status || t("setai.installing")) : t("setai.installBtn")}
            </button>
            <button class="btn" onclick={() => openExternal("https://ollama.com/download")}>{t("setai.downloadManually")}</button>
          </div>
          {#if install?.error}<p class="hint err">{install.error}</p>{/if}
        {:else if ollama.running}
          <div class="quicksetup">
            <span class="lab2">{t("setai.quickSetupLab")}</span>
            <div class="qsrow">
              {#each QUICK_SETUP as qs}
                <button class="qsbtn" class:on={isActive(qs.model, "chat")} onclick={() => quickSetup(qs.model)} disabled={pull?.active}>
                  <b>{t(qs.label)}</b><span class="qsmodel">{qs.model}</span><span class="qssub">{t(qs.sub)}</span>
                </button>
              {/each}
            </div>
          </div>
          <label class="fieldrow"><span>{t("setai.activeModel")}</span>
            {#if ollama.models.length}
              <select value={app.settings.aiModel || ollama.models[0]} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value })}>
                {#each ollama.models as m}<option value={m}>{m}</option>{/each}
              </select>
            {:else}
              <input placeholder="llama3.2" value={app.settings.aiModel || ""} onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
            {/if}
          </label>
          {#if !ollama.models.length}<p class="hint">{t("setai.noModels")}</p>{/if}
          <div class="pullrow">
            <span class="lab2">{t("setai.recommendedLab")}</span>
            {@render modelPicker(CHAT_MODELS, "chat")}
          </div>
          <div class="pullrow">
            <span class="lab2">{t("setai.searchAllLab")} <span class="live">{t("setai.liveTag")}</span></span>
            <input class="msearch" placeholder={t("setai.searchPh")} bind:value={modelQuery} oninput={searchModels} />
            {#if searching}
              <p class="hint">{t("setai.searchingOllama")}</p>
            {:else if searchResults.length}
              <div class="mpick">
                {#each searchResults as name}
                  <div class="mrow" class:active={isActive(name, "chat")}>
                    <div class="minfo"><span class="mname">{name}</span></div>
                    {#if isActive(name, "chat")}<span class="musing">{@html icons.done} {t("setai.using")}</span>
                    {:else if isInstalled(name)}<span class="minstalled">{t("setai.installed")}</span><button class="btn sm" onclick={() => useModel(name, "chat")}>{t("setai.use")}</button>
                    {:else}<button class="btn sm ghost" onclick={() => startPull(name)} disabled={pull?.active}>{t("setai.pullArrow")}</button>{/if}
                  </div>
                {/each}
              </div>
            {:else if modelQuery.trim().length >= 2}
              <p class="hint">{t("setai.searchNoMatches")}</p>
            {/if}
            <div class="pullcustom">
              <input placeholder={t("setai.pullExactPh")} bind:value={pullName} onkeydown={(e) => { if (e.key === "Enter") startPull(); }} />
              <button class="btn" onclick={() => startPull()} disabled={pull?.active || !pullName.trim()}>{t("setai.pull")}</button>
            </div>
          </div>
          {#if pull?.active || (pull && !pull.done)}
            <div class="prog"><div class="bar" style="width:{pull.percent || 0}%"></div></div>
            <p class="hint">{pull.model}: {pull.status} {pull.percent ? `(${pull.percent}%)` : ""}</p>
          {/if}
          <label class="fieldrow" style="margin-top:10px"><span>{t("setai.freeGpuAfter")}</span>
            <select value={app.settings.ollamaKeepAlive || "5m"} onchange={(e) => saveSettings({ ollamaKeepAlive: e.currentTarget.value })}>
              <option value="adaptive">{t("setai.kaAdaptive")}</option>
              <option value="0">{t("setai.kaImmediately")}</option>
              <option value="30s">{t("setai.ka30s")}</option>
              <option value="1m">{t("setai.ka1m")}</option>
              <option value="5m">{t("setai.ka5m")}</option>
              <option value="30m">{t("setai.ka30m")}</option>
              <option value="-1">{t("setai.kaKeep")}</option>
            </select>
          </label>
          {#if (app.settings.ollamaKeepAlive || "5m") === "adaptive"}
            <p class="hint" style="margin:0">{t("setai.adaptiveHint")}</p>
          {/if}
          <label class="check" style="margin-top:10px">
            <input type="checkbox" checked={app.settings.ollamaManaged !== false}
              onchange={(e) => { const v = e.currentTarget.checked; saveSettings({ ollamaManaged: v }); ai.ollamaManaged(v).catch(() => {}); refreshOllama(); }} />
            <span>{t("setai.hideConsole")} <small>{t("setai.hideConsoleSub")}</small></span>
          </label>
          <div class="rowbtns" style="margin-top:10px">
            <button class="btn" onclick={freeGpu} disabled={unloading}>{@html icons.bolt} {unloading ? t("setai.freeing") : t("setai.freeGpuNow")}</button>
            <button class="btn ghost" onclick={updateOllama} disabled={install?.active}>{install?.active ? (install.status || t("setai.updating")) : t("setai.updateOllama")}</button>
          </div>
          <p class="hint" style="margin-top:8px">{t("setai.vramHint")}</p>
        {:else}
          <p class="hint">{t("setai.olNotRunningHint")}</p>
          <div class="rowbtns">
            <button class="btn primary" onclick={startOllama} disabled={starting}>{@html icons.bolt} {starting ? t("setai.starting") : t("setai.startOllama")}</button>
            <button class="btn" onclick={restartOllama} disabled={starting}>{t("setai.restart")}</button>
          </div>
        {/if}
        <details class="adv"><summary>{t("setai.advanced")}</summary>
          <label class="fieldrow"><span>{t("setai.serverUrl")}</span>
            <input placeholder="http://localhost:11434" value={app.settings.aiBaseUrl || ""}
              onchange={(e) => { saveSettings({ aiBaseUrl: e.currentTarget.value.trim() }); refreshOllama(); }} />
          </label>
        </details>
      </div>
    {:else}
      <label class="fieldrow"><span>{t("setai.apiKey")}</span>
        <input type="password" placeholder={aiProv === "anthropic" ? "sk-ant-…" : "sk-…"}
          value={app.settings.aiApiKey || ""}
          onchange={(e) => saveSettings({ aiApiKey: e.currentTarget.value.trim() })} />
      </label>
      {#if aiProv === "openai-compatible"}
        <label class="fieldrow"><span>{t("setai.apiBaseUrl")}</span>
          <input placeholder="https://api.groq.com/openai/v1" value={app.settings.aiBaseUrl || ""}
            onchange={(e) => saveSettings({ aiBaseUrl: e.currentTarget.value.trim() })} />
        </label>
      {/if}
      <label class="fieldrow"><span>{t("setai.modelOptional")}</span>
        <input placeholder={aiProv === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"}
          value={app.settings.aiModel || ""}
          onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
      </label>
      <p class="hint">{app.settings.aiApiKey ? t("setai.keySet") : t("setai.noKey")}</p>
    {/if}
    {#if aiActive}
      <label class="check">
        <input type="checkbox" checked={app.settings.aiButtons !== false}
          onchange={(e) => saveSettings({ aiButtons: e.currentTarget.checked })} />
        <div><b>{t("setai.showAiButtons")}</b><span>{t("setai.showAiButtonsSub")}</span></div>
      </label>
    {/if}
    <label class="check">
      <input type="checkbox" checked={!!app.settings.digestEnabled}
        onchange={(e) => saveSettings({ digestEnabled: e.currentTarget.checked })} />
      <div>
        <b>{t("setai.digestTitle")}</b>
        <span>{t("setai.digestSub")}</span>
      </div>
    </label>
    {#if app.settings.digestEnabled}
      <label class="fieldrow"><span>{t("setai.deliverAt")}</span>
        <select value={app.settings.digestHour ?? 8} onchange={(e) => saveSettings({ digestHour: Number(e.currentTarget.value) })}>
          {#each Array(24) as _, h}<option value={h}>{String(h).padStart(2, "0")}:00</option>{/each}
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setai.semTitle")} <span class="tag">{t("setai.tagLocalOffline")}</span></h3>
    <p class="hint">{t("setai.semIntroA")}<b>{t("setai.semIntroMeaning")}</b>{t("setai.semIntroB")}<b>Ollama</b>{t("setai.semIntroC")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.semanticEnabled}
        onchange={(e) => { saveSettings({ semanticEnabled: e.currentTarget.checked }); if (e.currentTarget.checked) refreshEmbed(); }} />
      <div><b>{t("setai.semEnable")}</b><span>{t("setai.semEnableSub")}</span></div>
    </label>
    {#if app.settings.semanticEnabled}
      <label class="fieldrow"><span>{t("setai.embedSource")}</span>
        <select value={app.settings.embedProvider || "ollama"} onchange={(e) => { saveSettings({ embedProvider: e.currentTarget.value }); refreshEmbed(); }}>
          <option value="ollama">{t("setai.embedOllama")}</option>
          <option value="openai-compatible">{t("setai.embedOpenaiCompat")}</option>
        </select>
      </label>
      {#if (app.settings.embedProvider || "ollama") === "openai-compatible"}
        <label class="fieldrow"><span>{t("setai.baseUrl")}</span>
          <input placeholder="https://api.openai.com/v1" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
        <label class="fieldrow"><span>{t("setai.apiKey")}</span>
          <input type="password" placeholder="sk-…" value={app.settings.embedApiKey || ""}
            onchange={(e) => saveSettings({ embedApiKey: e.currentTarget.value.trim() })} />
        </label>
      {:else}
        <label class="fieldrow"><span>{t("setai.serverUrl")}</span>
          <input placeholder="http://localhost:11434" value={app.settings.embedBaseUrl || ""}
            onchange={(e) => { saveSettings({ embedBaseUrl: e.currentTarget.value.trim() }); refreshEmbed(); }} />
        </label>
      {/if}
      <label class="fieldrow"><span>{t("setai.model")}</span>
        <input placeholder={(app.settings.embedProvider || "ollama") === "ollama" ? "nomic-embed-text" : "text-embedding-3-small"}
          value={app.settings.embedModel || ""} onchange={(e) => { saveSettings({ embedModel: e.currentTarget.value.trim() }); refreshEmbed(); }} />
      </label>
      {#if (app.settings.embedProvider || "ollama") === "ollama"}
        {#if ollama.running}
          <div class="pullrow" style="margin-top:6px">
            <span class="lab2">{t("setai.recommendedEmbed")}</span>
            {@render modelPicker(EMBED_MODELS, "embed")}
          </div>
        {:else}
          <p class="hint">{t("setai.embedStartHintA")}<code>nomic-embed-text</code>, <code>bge-m3</code>{t("setai.embedStartHintB")}</p>
        {/if}
      {:else}
        <p class="hint warn-note">{t("setai.cloudWarn")}</p>
      {/if}

      {#if embed && embed.enabled && embed.model_installed === false}
        <div class="embed-warn">
          <b>{t("setai.embedMissingTitle")}</b>
          <span>{t("setai.embedMissingA")}<code>{embed.model}</code>{t("setai.embedMissingB")}</span>
          <div class="rowbtns">
            <button class="btn primary sm" onclick={pullEmbedModel} disabled={pull?.active}>{t("setai.pullModel", { model: embed.model })}</button>
            <button class="btn ghost sm" onclick={turnOffSemantic}>{t("setai.turnOffSemantic")}</button>
          </div>
        </div>
      {/if}

      <div class="embed-status">
        {#if embed}
          <span class="dot" class:on={embed.reachable}></span>
          <span>{embed.reachable ? t("setai.epReachable") : t("setai.epUnreachable")} · <b>{embed.indexed}</b> / {embed.total} {t("setai.indexedWord")} · {embed.backend}</span>
        {:else}
          <span class="hint">{t("setai.checking")}</span>
        {/if}
      </div>
      <div class="rowbtns">
        <button class="btn primary" onclick={buildIndex} disabled={embed?.indexing}>
          {@html icons.sync} {embed?.indexing ? t("setai.indexing") : t("setai.buildIndexBtn")}
        </button>
        <button class="btn ghost sm" onclick={refreshEmbed}>{t("setai.refreshStatus")}</button>
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
