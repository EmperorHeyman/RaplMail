<script>
  import { app, saveSettings, notify, selectUnifiedInbox, refreshMessages, smartActive, enableNotifications, notificationsAvailable, testNotification, exportConfig, importConfig, exportFullBackup, importFullBackup, checkForUpdates, setAutostart, setCloseToTray, setLanguage } from "../store.svelte.js";
  import { backendBase } from "../api.js";
  import SmartGroupCard from "./SmartGroupCard.svelte";
  import { icons } from "../icons.js";
  import { playSound, SOUND_OPTIONS } from "../sound.js";
  import SoundStudio from "./SoundStudio.svelte";
  import { t, LANGUAGES } from "../i18n.svelte.js";

  const notifVol = $derived(app.settings.notifyVolume ?? 80);

  // Built-in synth sounds + any user-uploaded custom clips, for the per-type
  // sound dropdowns (new mail, calendar reminders).
  const soundOpts = $derived([
    ...SOUND_OPTIONS,
    ...((app.settings.customSounds || []).map((c) => ({ id: `custom:${c.id}`, label: c.name }))),
  ]);
  let studioOpen = $state(false);
  function onStudioClose(picked) {
    studioOpen = false;
    // Newly-created clip becomes the new-mail sound straight away.
    if (typeof picked === "string") { saveSettings({ notifySound: picked }); playSound(picked, notifVol / 100); }
  }
  function deleteCustom(id) {
    const list = (app.settings.customSounds || []).filter((c) => c.id !== id);
    const patch = { customSounds: list };
    // Fall back to a built-in if a now-deleted clip was selected anywhere.
    if (app.settings.notifySound === `custom:${id}`) patch.notifySound = "ding";
    if (app.settings.notifyCalendarSound === `custom:${id}`) patch.notifyCalendarSound = "chime";
    saveSettings(patch);
  }

  // --- Local API / metrics for LAN devices ---------------------------------
  function randomKey() {
    const b = new Uint8Array(24); crypto.getRandomValues(b);
    return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  }
  function toggleLocalApi(on) {
    const patch = { localApiEnabled: on };
    if (on && !app.settings.localApiKey) patch.localApiKey = randomKey();
    saveSettings(patch);
  }
  function regenKey() {
    if (!confirm(t("setgen.regenConfirm"))) return;
    saveSettings({ localApiKey: randomKey() });
  }
  const metricsUrl = $derived(`${backendBase()}/metrics`);
  async function copyText(txt) {
    try { await navigator.clipboard.writeText(txt); notify(t("setgen.copied")); } catch { notify(t("setgen.copyFailed"), "error"); }
  }

  // Labels are i18n keys - translated with t() at render time so they follow
  // live language switches.
  const SMART_CATS = [
    { id: "updates", label: "setgen.catUpdates", icon: icons.bell },
    { id: "newsletters", label: "setgen.catNewsletters", icon: icons.newspaper },
    { id: "social", label: "setgen.catSocial", icon: icons.chat },
    { id: "promotions", label: "setgen.catPromotions", icon: icons.tag },
    { id: "invitations", label: "setgen.catInvitations", icon: icons.calendar },
    { id: "invitation_responses", label: "setgen.catInvitationResponses", icon: icons.done },
  ];
  const META = Object.fromEntries(SMART_CATS.map((c) => [c.id, c]));
  function toggleGroup(id, on) {
    saveSettings({ smartGroups: { ...app.settings.smartGroups, [id]: on } });
    if (smartActive()) refreshMessages();
  }

  // Ordering (recency vs custom drag order).
  const groupedIds = $derived(SMART_CATS.filter((c) => app.settings.smartGroups[c.id]).map((c) => c.id));
  const orderedCats = $derived(
    app.settings.smartOrderMode === "custom"
      ? [...(app.settings.smartOrder || []).filter((c) => groupedIds.includes(c)),
         ...groupedIds.filter((c) => !(app.settings.smartOrder || []).includes(c))]
      : groupedIds
  );
  function setOrderMode(mode) {
    const patch = { smartOrderMode: mode };
    if (mode === "custom" && !(app.settings.smartOrder || []).length) patch.smartOrder = [...groupedIds];
    saveSettings(patch);
  }
  function setPlacement(mode) { saveSettings({ smartGroupPlacement: mode }); }

  let importFile;
  async function doExport() {
    try {
      const bundle = await exportConfig();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `raplmail-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      notify(t("setgen.configExported"));
    } catch { notify(t("setgen.exportFailed"), "error"); }
  }
  async function doImport(e) {
    const file = e.currentTarget.files?.[0];
    if (file) {
      try {
        const bundle = JSON.parse(await file.text());
        const r = await importConfig(bundle);
        notify(t("setgen.importedSummary", { settings: r.settings ? "✓" : "-", rules: r.rules, signatures: r.signatures, tags: r.sender_categories }));
      } catch { notify(t("setgen.importFailed"), "error"); }
    }
    e.currentTarget.value = "";
  }

  // Full encrypted backup (.rmail): config + accounts + passwords, sealed with
  // the master password.
  let rmailFile;
  let backingUp = $state(false);
  async function doExportFull() {
    backingUp = true;
    try {
      const blob = await exportFullBackup();
      const file = new Blob([JSON.stringify(blob)], { type: "application/octet-stream" });
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = `raplmail-backup-${new Date().toISOString().slice(0, 10)}.rmail`;
      a.click();
      URL.revokeObjectURL(url);
      notify(t("setgen.backupSaved"));
    } catch (err) {
      notify(err?.message?.includes("vault") ? t("setgen.unlockVaultFirst") : t("setgen.backupFailed"), "error");
    } finally { backingUp = false; }
  }
  async function doImportFull(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    let blob;
    try { blob = JSON.parse(await file.text()); }
    catch { notify(t("setgen.notRmail"), "error"); return; }
    const pw = prompt(t("setgen.restorePrompt"));
    if (!pw) return;
    try {
      const r = await importFullBackup(blob, pw);
      notify(t("setgen.restoredSummary", { accounts: r.accounts, settings: r.settings ? "✓" : "-", rules: r.rules, signatures: r.signatures }));
    } catch (err) {
      notify(err?.status === 400 ? t("setgen.wrongPassword") : (err?.message || t("setgen.restoreFailed")), "error");
    }
  }

  let notifPerm = $state("default");
  const _isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  async function refreshPerm() {
    if (_isTauri) {
      try { const m = await import("@tauri-apps/plugin-notification"); notifPerm = (await m.isPermissionGranted()) ? "granted" : "default"; return; } catch {}
    }
    notifPerm = typeof Notification !== "undefined" ? Notification.permission : "unsupported";
  }
  refreshPerm();
  async function toggleNotify(on) {
    if (on) {
      const r = await enableNotifications();
      notifPerm = r;
      saveSettings({ notifyNewMail: r === "granted" });
      if (r !== "granted") notify(t("setgen.notifBlockedSystem"), "error");
    } else {
      saveSettings({ notifyNewMail: false });
    }
  }
  async function sendTest() {
    const res = await testNotification();
    await refreshPerm();
    if (res.ok) notify(t("setgen.testSent"));
    else if (res.reason === "denied") notify(t("setgen.testBlocked"), "error");
    else if (res.reason === "unsupported") notify(t("setgen.testUnsupported"), "error");
    else notify(t("setgen.testFailed", { reason: res.reason }), "error");
  }

  let dragCat = $state(null);
  function reorder(targetId) {
    if (!dragCat || dragCat === targetId) return;
    const ids = [...orderedCats];
    const from = ids.indexOf(dragCat), to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    saveSettings({ smartOrder: ids });
  }

  // Live preview sample.
  const SAMPLE = [
    { name: "Trading 212", count: 39 }, { name: "Jobs.cz", count: 27 },
    { name: "OpenRouter", count: 11 }, { name: "UniFi OS", count: 8 },
    { name: "GitHub", count: 6 }, { name: "Comgate", count: 4 },
  ];
  const previewSenders = $derived(SAMPLE.slice(0, app.settings.smartPreviewCount || 4));

  function setCompose(patch) { saveSettings(patch); }

  let bccRules = $state((app.settings.autoBcc || []).map((r) => ({ ...r })));
  function addBcc() { bccRules = [...bccRules, { domain: "", bcc: "" }]; }
  function removeBcc(i) { bccRules = bccRules.filter((_, x) => x !== i); }
  function saveBcc() {
    saveSettings({ autoBcc: bccRules.filter((r) => r.domain && r.bcc) });
    notify(t("setgen.bccSaved"));
  }

  function toggleUnified(e) {
    saveSettings({ unifiedInbox: e.currentTarget.checked });
    if (e.currentTarget.checked) selectUnifiedInbox();
  }


</script>

<div class="wrap">
  <h2 class="group-head">{t("settings.language")}</h2>
  <section class="card">
    <h3>{t("settings.language")}</h3>
    <p class="hint">{t("settings.languageHint")}</p>
    <label class="inline">{t("settings.language")}
      <select value={app.settings.language || "auto"} onchange={(e) => setLanguage(e.currentTarget.value)}>
        {#each LANGUAGES as l}<option value={l.id}>{l.label}</option>{/each}
      </select>
    </label>
  </section>

  <h2 class="group-head">{t("setgen.headMailBehavior")}</h2>
  <section class="card">
    <h3>{t("setgen.composeTitle")}</h3>
    <p class="hint">{t("setgen.composeHint")}</p>
    <label class="radio">
      <input type="radio" name="cmode" value="panel" checked={app.settings.composeMode === "panel"}
        onchange={() => setCompose({ composeMode: "panel" })} />
      <div><b>{t("setgen.composePanel")}</b><span>{t("setgen.composePanelHint")}</span></div>
    </label>
    <label class="radio">
      <input type="radio" name="cmode" value="window" checked={app.settings.composeMode === "window"}
        onchange={() => setCompose({ composeMode: "window" })} />
      <div><b>{t("setgen.composeWindow")}</b><span>{t("setgen.composeWindowHint")}</span></div>
    </label>

    {#if app.settings.composeMode === "panel"}
      <label class="inline">{t("setgen.corner")}
        <select value={app.settings.composePosition} onchange={(e) => setCompose({ composePosition: e.currentTarget.value })}>
          <option value="bottom-right">{t("setgen.cornerBR")}</option>
          <option value="bottom-left">{t("setgen.cornerBL")}</option>
        </select>
      </label>
    {/if}
    <label class="check" style="margin-top:6px">
      <input type="checkbox" checked={app.settings.spellCheck !== false} onchange={(e) => setCompose({ spellCheck: e.currentTarget.checked })} />
      <div><b>{t("setgen.spellCheck")}</b><span>{t("setgen.spellCheckHint")}</span></div>
    </label>
  </section>

  <section class="card">
    <h3>{t("setgen.sendingTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.undoSend} onchange={(e) => setCompose({ undoSend: e.currentTarget.checked })} />
      <div><b>{t("setgen.undoSend")}</b><span>{t("setgen.undoSendHint")}</span></div>
    </label>
    {#if app.settings.undoSend}
      <label class="inline">{t("setgen.cancelWindow")}
        <select value={app.settings.undoSendDelay} onchange={(e) => setCompose({ undoSendDelay: Number(e.currentTarget.value) })}>
          <option value={3}>{t("setgen.seconds", { n: 3 })}</option>
          <option value={5}>{t("setgen.seconds", { n: 5 })}</option>
          <option value={10}>{t("setgen.seconds", { n: 10 })}</option>
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setgen.inboxTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={(app.settings.readMarkMode || "leave") === "leave"}
        onchange={(e) => setCompose({ readMarkMode: e.currentTarget.checked ? "leave" : "instant" })} />
      <div><b>{t("setgen.readOnLeave")}</b><span>{t("setgen.readOnLeaveHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.openNextOnDone} onchange={(e) => setCompose({ openNextOnDone: e.currentTarget.checked })} />
      <div><b>{t("setgen.openNext")}</b><span>{t("setgen.openNextHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.unifiedInbox} onchange={toggleUnified} />
      <div><b>{t("setgen.unified")}</b><span>{t("setgen.unifiedHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.threading} onchange={(e) => setCompose({ threading: e.currentTarget.checked })} />
      <div><b>{t("setgen.threading")}</b><span>{t("setgen.threadingHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.bundles} onchange={(e) => setCompose({ bundles: e.currentTarget.checked })} />
      <div><b>{t("setgen.bundles")}</b><span>{t("setgen.bundlesHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.showNewsletterFeed !== false} onchange={(e) => setCompose({ showNewsletterFeed: e.currentTarget.checked })} />
      <div><b>{t("setgen.nlFeed")}</b><span>{t("setgen.nlFeedHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.showPaperTrail !== false} onchange={(e) => setCompose({ showPaperTrail: e.currentTarget.checked })} />
      <div><b>{t("setgen.paperTrail")}</b><span>{t("setgen.paperTrailHint")}</span></div>
    </label>
    <label class="inline">{t("setgen.followupBefore")}
      <select value={app.settings.followupDays} onchange={(e) => setCompose({ followupDays: Number(e.currentTarget.value) })}>
        <option value={2}>{t("setgen.followupDays", { n: 2 })}</option>
        <option value={3}>{t("setgen.followupDays", { n: 3 })}</option>
        <option value={5}>{t("setgen.followupDays", { n: 5 })}</option>
        <option value={7}>{t("setgen.followupDays", { n: 7 })}</option>
      </select>
      {t("setgen.followupAfter")}
    </label>
    <label class="inline">{t("setgen.searchStyle")}
      <select value={app.settings.searchStyle || "inline"} onchange={(e) => setCompose({ searchStyle: e.currentTarget.value })}>
        <option value="inline">{t("setgen.searchInline")}</option>
        <option value="modal">{t("setgen.searchModal")}</option>
      </select>
    </label>
    <span class="hint" style="margin:2px 0 0 2px">{t("setgen.searchHintA", { key: app.settings.keybinds?.search || "/" })} <code>from:</code> {t("setgen.searchHintB")}</span>
  </section>

  <section class="card">
    <h3>{t("setgen.smartTitle")}</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.smartInbox} onchange={(e) => setCompose({ smartInbox: e.currentTarget.checked })} />
      <div><b>{t("setgen.smartEnable")}</b><span>{t("setgen.smartEnableHint")}</span></div>
    </label>
    {#if app.settings.smartInbox}
      <p class="hint" style="margin-top:10px">{t("setgen.groupThese")}</p>
      <div class="smartcats">
        {#each SMART_CATS as c}
          <label class="grp"><input type="checkbox" checked={!!app.settings.smartGroups[c.id]} onchange={(e) => toggleGroup(c.id, e.currentTarget.checked)} /> <span>{@html c.icon} {t(c.label)}</span></label>
        {/each}
      </div>

      <label class="inline" style="margin-top:14px">{t("setgen.previewCount")}
        <select value={app.settings.smartPreviewCount} onchange={(e) => saveSettings({ smartPreviewCount: Number(e.currentTarget.value) })}>
          <option value={2}>2</option><option value={3}>3</option><option value={4}>4</option><option value={6}>6</option>
        </select>
      </label>

      <p class="hint" style="margin-top:14px">{t("setgen.placement")}</p>
      <label class="grp"><input type="radio" name="splace" checked={(app.settings.smartGroupPlacement ?? "sections") === "sections"} onchange={() => setPlacement("sections")} /> <span><b>{t("setgen.placeSections")}</b> - {t("setgen.placeSectionsDesc")}</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "dateSections"} onchange={() => setPlacement("dateSections")} /> <span><b>{t("setgen.placeDate")}</b> - {t("setgen.placeDateDesc")}</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "timeline"} onchange={() => setPlacement("timeline")} /> <span>{t("setgen.placeTimeline")}</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "top"} onchange={() => setPlacement("top")} /> <span>{t("setgen.placeTop")}</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "afterN"} onchange={() => setPlacement("afterN")} /> <span>{t("setgen.placeAfterBefore")}
        <select value={app.settings.smartGroupsAfter ?? 3} onchange={(e) => saveSettings({ smartGroupsAfter: Number(e.currentTarget.value) })} onclick={(e) => e.stopPropagation()}>
          <option value={1}>1</option><option value={2}>2</option><option value={3}>3</option><option value={4}>4</option><option value={5}>5</option>
        </select>
        {t("setgen.placeAfterAfter")}</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "bottom"} onchange={() => setPlacement("bottom")} /> <span>{t("setgen.placeBottom")}</span></label>

      <p class="hint" style="margin-top:14px">{t("setgen.orderTitle")}</p>
      <label class="grp"><input type="radio" name="sorder" checked={app.settings.smartOrderMode !== "custom"} onchange={() => setOrderMode("recency")} /> <span>{t("setgen.orderRecency")}</span></label>
      <label class="grp"><input type="radio" name="sorder" checked={app.settings.smartOrderMode === "custom"} onchange={() => setOrderMode("custom")} /> <span>{t("setgen.orderCustom")}</span></label>
      {#if app.settings.smartOrderMode === "custom"}
        <div class="orderlist">
          {#each orderedCats as c (c)}
            <div class="orderrow" draggable="true"
              ondragstart={() => (dragCat = c)} ondragend={() => (dragCat = null)}
              ondragover={(e) => { e.preventDefault(); reorder(c); }}>
              ⠿ {@html META[c]?.icon} {META[c] ? t(META[c].label) : ""}
            </div>
          {/each}
        </div>
      {/if}

      <p class="hint" style="margin-top:14px">{t("setgen.preview")}</p>
      <div class="preview-box">
        <SmartGroupCard label={t("setgen.catNewsletters")} icon={icons.newspaper} count={5471} newCount={4} senders={previewSenders}
          more={Math.max(0, 40 - previewSenders.length)} />
      </div>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setgen.bccTitle")}</h3>
    <p class="hint">{t("setgen.bccHintA")} <code>*</code> {t("setgen.bccHintB")}</p>
    {#each bccRules as r, i}
      <div class="bccrow">
        <input placeholder={t("setgen.bccDomainPh")} bind:value={r.domain} />
        <input placeholder="bcc@yoursystem.com" bind:value={r.bcc} />
        <button class="btn ghost danger" onclick={() => removeBcc(i)}>{@html icons.close}</button>
      </div>
    {/each}
    <div class="bccactions">
      <button class="btn" onclick={addBcc}>＋ {t("setgen.bccAdd")}</button>
      <button class="btn primary" onclick={saveBcc}>{t("setgen.save")}</button>
    </div>
  </section>

  <h2 class="group-head">{t("setgen.headAccountSystem")}</h2>
  <section class="card">
    <h3>{t("setgen.backupTitle")}</h3>
    <p class="hint">{@html t("setgen.backupFullHint")}</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={doExportFull} disabled={backingUp}>{@html icons.lock} {backingUp ? t("setgen.backingUp") : t("setgen.exportFull")}</button>
      <button class="btn" onclick={() => rmailFile.click()}>{t("setgen.restoreFrom")}</button>
      <input bind:this={rmailFile} type="file" accept=".rmail,application/octet-stream" hidden onchange={doImportFull} />
    </div>
    <p class="hint" style="margin-top:14px">{@html t("setgen.configOnlyHint")}</p>
    <div class="rowbtns">
      <button class="btn" onclick={doExport}>{@html icons.sent} {t("setgen.exportConfig")}</button>
      <button class="btn" onclick={() => importFile.click()}>{t("setgen.importConfig")}</button>
      <input bind:this={importFile} type="file" accept="application/json,.json" hidden onchange={doImport} />
    </div>
  </section>

  <section class="card">
    <h3>{t("setgen.localApiTitle")} <span class="tag">{t("setgen.tagDeveloper")}</span></h3>
    <p class="hint">{t("setgen.localApiHint")}</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.localApiEnabled}
        onchange={(e) => toggleLocalApi(e.currentTarget.checked)} />
      <div><b>{t("setgen.localApiEnable")}</b><span>{t("setgen.localApiEnableHint")}</span></div>
    </label>
    {#if app.settings.localApiEnabled}
      <div class="apibox">
        <div class="kv"><span>URL</span>
          <code>{metricsUrl}</code>
          <button class="btn ghost" onclick={() => copyText(metricsUrl)}>{t("setgen.copy")}</button>
        </div>
        <div class="kv"><span>{t("setgen.apiKey")}</span>
          <code class="key">{app.settings.localApiKey || "-"}</code>
          <button class="btn ghost" onclick={() => copyText(app.settings.localApiKey)}>{t("setgen.copy")}</button>
          <button class="btn ghost" onclick={regenKey}>{t("setgen.regen")}</button>
        </div>
        <div class="kv"><span>{t("setgen.test")}</span>
          <code>curl -H "X-API-Key: {app.settings.localApiKey}" {metricsUrl}</code>
          <button class="btn ghost" onclick={() => copyText(`curl -H "X-API-Key: ${app.settings.localApiKey}" ${metricsUrl}`)}>{t("setgen.copy")}</button>
        </div>
        <p class="hint">{@html t("setgen.localApiDetails")}</p>
      </div>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setgen.updatesTitle")}</h3>
    <p class="hint">{t("setgen.updatesHint")}</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={() => checkForUpdates()}>{@html icons.sync} {t("setgen.checkUpdates")}</button>
    </div>
  </section>

  <section class="card">
    <h3>{t("setgen.trayTitle")}</h3>
    <p class="hint">{t("setgen.trayHint")}</p>
    <label class="check">
      <input type="checkbox" checked={app.settings.minimizeToTray !== false}
        onchange={(e) => setCloseToTray(e.currentTarget.checked)} />
      <div><b>{t("setgen.minimizeTray")}</b><span>{@html t("setgen.minimizeTrayHint")}</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.launchOnStartup}
        onchange={(e) => setAutostart(e.currentTarget.checked)} />
      <div><b>{t("setgen.launchLogin")}</b><span>{t("setgen.launchLoginHint")}</span></div>
    </label>
    <p class="hint">{t("setgen.trayNote")}</p>
  </section>

  <h2 class="group-head">{t("setgen.headNotifSched")}</h2>
  <section class="card">
    <h3>{t("setgen.notifTitle")}</h3>
    {#if notificationsAvailable()}
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyNewMail !== false && notifPerm === "granted"}
          onchange={(e) => toggleNotify(e.currentTarget.checked)} />
        <div>
          <b>{t("setgen.notifNewMail")}</b>
          <span>{t("setgen.notifNewMailHint")}{#if notifPerm === "denied"} <em>{t("setgen.notifBlockedNote")}</em>{/if}</span>
        </div>
      </label>
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyOnlyUnfocused !== false}
          onchange={(e) => saveSettings({ notifyOnlyUnfocused: e.currentTarget.checked })} />
        <div>
          <b>{t("setgen.onlyUnfocused")}</b>
          <span>{t("setgen.onlyUnfocusedHint")}</span>
        </div>
      </label>
      <label class="check">
        <input type="checkbox" checked={!!app.settings.quietHoursEnabled}
          onchange={(e) => saveSettings({ quietHoursEnabled: e.currentTarget.checked })} />
        <div>
          <b>{t("setgen.quietHours")}</b>
          <span>{t("setgen.quietHoursHint")}</span>
        </div>
      </label>
      {#if app.settings.quietHoursEnabled}
        <label class="inline" style="margin-left:28px">{t("setgen.from")}
          <select value={app.settings.quietStart ?? 22} onchange={(e) => saveSettings({ quietStart: Number(e.currentTarget.value) })}>
            {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
          </select> {t("setgen.to")}
          <select value={app.settings.quietEnd ?? 7} onchange={(e) => saveSettings({ quietEnd: Number(e.currentTarget.value) })}>
            {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
          </select>
        </label>
      {/if}
      <label class="inline" style="margin-top:10px">{t("notif.soundMail")}
        <select value={app.settings.notifySound || "ding"} onchange={(e) => { saveSettings({ notifySound: e.currentTarget.value }); playSound(e.currentTarget.value, notifVol / 100); }}>
          {#each soundOpts as s}<option value={s.id}>{s.label}</option>{/each}
        </select>
        <button class="btn sm" onclick={() => playSound(app.settings.notifySound || "ding", notifVol / 100)}>▶ {t("common.play")}</button>
      </label>
      <label class="inline" style="margin-top:10px">{t("notif.soundCalendar")}
        <select value={app.settings.notifyCalendarSound || "chime"} onchange={(e) => { saveSettings({ notifyCalendarSound: e.currentTarget.value }); playSound(e.currentTarget.value, notifVol / 100); }}>
          {#each soundOpts as s}<option value={s.id}>{s.label}</option>{/each}
        </select>
        <button class="btn sm" onclick={() => playSound(app.settings.notifyCalendarSound || "chime", notifVol / 100)}>▶ {t("common.play")}</button>
      </label>
      <label class="check" style="margin-top:8px">
        <input type="checkbox" checked={app.settings.calendarReminderWindow !== false}
          onchange={(e) => saveSettings({ calendarReminderWindow: e.currentTarget.checked })} />
        <div>
          <b>{t("notif.reminderWindow")}</b>
          <span>{t("notif.reminderWindowHint")}</span>
        </div>
      </label>
      <div class="customsnd">
        <div class="csnd-head">
          <span>{t("notif.customSounds")}</span>
          <button class="btn sm" onclick={() => (studioOpen = true)}>＋ {t("notif.addCustom")}</button>
        </div>
        {#if (app.settings.customSounds || []).length}
          <div class="csnd-list">
            {#each app.settings.customSounds as c (c.id)}
              <div class="csnd-row">
                <button class="csnd-play" title={t("sound.preview")} onclick={() => playSound(`custom:${c.id}`, notifVol / 100)}>▶</button>
                <span class="csnd-name">{c.name}</span>
                <button class="csnd-del" title={t("common.delete")} onclick={() => deleteCustom(c.id)}>{@html icons.close}</button>
              </div>
            {/each}
          </div>
        {:else}
          <p class="hint" style="margin:6px 0 0">{t("notif.customHint")}</p>
        {/if}
      </div>
      <label class="inline" style="margin-top:10px">{t("notif.volume")}
        <input type="range" min="0" max="100" step="5" value={notifVol}
          disabled={(app.settings.notifySound || "ding") === "none"}
          oninput={(e) => saveSettings({ notifyVolume: Number(e.currentTarget.value) })}
          onchange={(e) => playSound(app.settings.notifySound || "ding", Number(e.currentTarget.value) / 100)} />
        <span class="tnum" style="width:38px;text-align:right">{notifVol}%</span>
      </label>
      <span class="hint" style="margin:2px 0 0 2px">{t("setgen.chimeHint")}</span>
      <p class="hint" style="margin-top:8px">{t("notif.muteHint")}</p>
      <button class="btn" style="margin-top:10px" onclick={sendTest}>{t("notif.test")}</button>
      <p class="hint" style="margin-top:8px">{@html t("setgen.noPopupHint")}</p>
    {:else}
      <p class="hint">{t("setgen.notifUnavailable")}</p>
    {/if}
  </section>

  <section class="card">
    <h3>{t("setgen.schedTitle")}</h3>
    <p class="hint">{t("setgen.schedHint")}</p>
    <label class="inline">{t("setgen.laterTodayBefore")}
      <select value={app.settings.scheduleLaterHours ?? 3} onchange={(e) => saveSettings({ scheduleLaterHours: Number(e.currentTarget.value) })}>
        {#each [1,2,3,4,6,8] as h}<option value={h}>{h}</option>{/each}
      </select> {t("setgen.laterTodayAfter")}
    </label>
    <label class="inline">{t("setgen.morningAt")}
      <select value={app.settings.scheduleMorningHour ?? 9} onchange={(e) => saveSettings({ scheduleMorningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
      </select>
    </label>
    <label class="inline">{t("setgen.eveningAt")}
      <select value={app.settings.scheduleEveningHour ?? 18} onchange={(e) => saveSettings({ scheduleEveningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
      </select>
    </label>
    <p class="hint" style="margin-top:8px">{t("setgen.exactTimeHint")}</p>
    <div class="local-note">{@html icons.info || ""}<span>{t("schedule.localOnly")}</span></div>
  </section>

</div>

{#if studioOpen}<SoundStudio onclose={onStudioClose} />{/if}

<style>
  .wrap { max-width: 640px; display: flex; flex-direction: column; gap: 20px; }
  .group-head { margin: 8px 0 -6px; font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--faint); }
  .group-head:first-child { margin-top: 0; }
  .card { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  h3 { margin: 0 0 6px; }
  .hint { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
  .hint.ok { color: var(--done); }
  .radio, .check { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; cursor: pointer; }
  .radio div, .check div { display: flex; flex-direction: column; gap: 2px; }
  .radio span, .check span { color: var(--muted); font-size: 12px; }
  .radio input, .check input { margin-top: 3px; }
  .inline { display: flex; align-items: center; gap: 10px; margin-top: 10px; color: var(--muted); font-size: 13px; }
  select { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; }
  .hint code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
  .smartcats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .rowbtns { display: flex; gap: 18px; }
  .grp { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 3px 0; }
  .orderlist { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
  .orderrow { padding: 8px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; cursor: grab; }
  .orderrow:hover { border-color: var(--accent); }
  .preview-box { border: 1px dashed var(--border); border-radius: var(--radius); margin-top: 6px; pointer-events: none; }
  .bccrow { display: flex; gap: 8px; margin-bottom: 8px; }
  .bccrow input:first-child { flex: 0 0 220px; }
  .bccrow input:nth-child(2) { flex: 1; }
  .bccactions { display: flex; gap: 10px; margin-top: 4px; }
  .warn { background: rgba(240,180,41,0.12); border: 1px solid var(--warning); color: #f0d28a; padding: 12px 14px; border-radius: var(--radius-sm); font-size: 13px; line-height: 1.6; margin-bottom: 12px; }
  .confirm { display: flex; gap: 8px; }
  .confirm input { flex: 1; }
  .tag { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; padding: 2px 7px; border-radius: 999px; background: var(--surface-3); color: var(--accent); vertical-align: middle; margin-left: 6px; }
  .apibox { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
  .kv { display: flex; align-items: center; gap: 10px; }
  .kv > span:first-child { width: 64px; flex: none; color: var(--muted); font-size: 12px; }
  .kv code { flex: 1; min-width: 0; background: var(--surface-2); border: 1px solid var(--border); padding: 5px 9px; border-radius: var(--radius-sm); font-size: 12px; overflow-x: auto; white-space: nowrap; }
  .kv code.key { letter-spacing: 0.04em; }
  .apibox .hint { margin: 4px 0 0; }
  .btn.sm { padding: 4px 9px; font-size: 12px; }
  .local-note { display: flex; gap: 9px; align-items: flex-start; margin-top: 14px; padding: 11px 13px;
    background: color-mix(in srgb, var(--warning) 10%, transparent); border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border));
    border-radius: var(--radius-sm); font-size: 12.5px; line-height: 1.5; color: var(--text); }
  .local-note :global(svg) { width: 16px; height: 16px; flex: none; margin-top: 1px; color: var(--warning); }
  .customsnd { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--hairline); }
  .csnd-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 13px; color: var(--muted); }
  .csnd-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
  .csnd-row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); }
  .csnd-play { flex: none; width: 24px; height: 24px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 11px; }
  .csnd-play:hover { background: var(--accent); color: #fff; }
  .csnd-name { flex: 1; min-width: 0; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .csnd-del { flex: none; color: var(--muted); padding: 3px; border-radius: 5px; }
  .csnd-del:hover { color: var(--danger); background: var(--hover); }
  .csnd-del :global(svg) { width: 13px; height: 13px; }
</style>
