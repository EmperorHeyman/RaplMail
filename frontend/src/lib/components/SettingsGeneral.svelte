<script>
  import { app, saveSettings, refreshVault, notify, selectUnifiedInbox, refreshMessages, smartActive, enableNotifications, notificationsAvailable, testNotification, exportConfig, importConfig, exportFullBackup, importFullBackup, checkForUpdates, setAutostart, setCloseToTray, setLanguage } from "../store.svelte.js";
  import { vault, backendBase } from "../api.js";
  import SmartGroupCard from "./SmartGroupCard.svelte";
  import { icons } from "../icons.js";
  import { playSound, SOUND_OPTIONS } from "../sound.js";
  import { t, LANGUAGES } from "../i18n.svelte.js";

  const notifVol = $derived(app.settings.notifyVolume ?? 80);

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
    if (!confirm("Generate a new API key? Devices using the old key will stop working until updated.")) return;
    saveSettings({ localApiKey: randomKey() });
  }
  const metricsUrl = $derived(`${backendBase()}/metrics`);
  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); notify("Copied"); } catch { notify("Couldn't copy", "error"); }
  }

  const SMART_CATS = [
    { id: "updates", label: "Notifications", icon: icons.bell },
    { id: "newsletters", label: "Newsletters", icon: icons.newspaper },
    { id: "social", label: "Social", icon: icons.chat },
    { id: "promotions", label: "Promotions", icon: icons.tag },
    { id: "invitations", label: "Invitations", icon: icons.calendar },
    { id: "invitation_responses", label: "Invitation responses", icon: icons.done },
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
      notify("Config exported");
    } catch { notify("Export failed", "error"); }
  }
  async function doImport(e) {
    const file = e.currentTarget.files?.[0];
    if (file) {
      try {
        const bundle = JSON.parse(await file.text());
        const r = await importConfig(bundle);
        notify(`Imported: settings ${r.settings ? "✓" : "–"} · ${r.rules} rules · ${r.signatures} signatures · ${r.sender_categories} sender tags`);
      } catch { notify("Import failed — invalid file", "error"); }
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
      notify("Encrypted backup saved (.rmail)");
    } catch (err) {
      notify(err?.message?.includes("vault") ? "Unlock your vault first" : "Backup failed", "error");
    } finally { backingUp = false; }
  }
  async function doImportFull(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    let blob;
    try { blob = JSON.parse(await file.text()); }
    catch { notify("Not a valid .rmail file", "error"); return; }
    const pw = prompt("Enter the master password from the machine this backup was made on:");
    if (!pw) return;
    try {
      const r = await importFullBackup(blob, pw);
      notify(`Restored: ${r.accounts} account(s) · settings ${r.settings ? "✓" : "–"} · ${r.rules} rules · ${r.signatures} signatures. Syncing…`);
    } catch (err) {
      notify(err?.status === 400 ? "Wrong password or corrupt backup" : (err?.message || "Restore failed"), "error");
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
      if (r !== "granted") notify("Notifications were blocked by the system", "error");
    } else {
      saveSettings({ notifyNewMail: false });
    }
  }
  async function sendTest() {
    const res = await testNotification();
    await refreshPerm();
    if (res.ok) notify("Test notification sent — check your desktop");
    else if (res.reason === "denied") notify("Blocked — allow notifications for this app in Windows Settings → Notifications (and turn off Focus Assist)", "error");
    else if (res.reason === "unsupported") notify("Notifications aren't supported here", "error");
    else notify("Couldn't show notification: " + res.reason, "error");
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

  let autoPw = $state("");
  let showAutoPw = $state(false);
  let busy = $state(false);

  function setCompose(patch) { saveSettings(patch); }

  let bccRules = $state((app.settings.autoBcc || []).map((r) => ({ ...r })));
  function addBcc() { bccRules = [...bccRules, { domain: "", bcc: "" }]; }
  function removeBcc(i) { bccRules = bccRules.filter((_, x) => x !== i); }
  function saveBcc() {
    saveSettings({ autoBcc: bccRules.filter((r) => r.domain && r.bcc) });
    notify("Auto-BCC rules saved");
  }

  function toggleUnified(e) {
    saveSettings({ unifiedInbox: e.currentTarget.checked });
    if (e.currentTarget.checked) selectUnifiedInbox();
  }

  async function enableAuto() {
    if (!autoPw) { notify("Enter your master password to confirm", "error"); return; }
    busy = true;
    try {
      await vault.setAutoUnlock(true, autoPw);
      await refreshVault();
      autoPw = ""; showAutoPw = false;
      notify("RaplMail will no longer ask for your password on startup");
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
  }

  async function disableAuto() {
    busy = true;
    try {
      await vault.setAutoUnlock(false);
      await refreshVault();
      notify("Password will be required on startup again");
    } catch (e) { notify(e.message, "error"); } finally { busy = false; }
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

  <h2 class="group-head">Mail behavior</h2>
  <section class="card">
    <h3>Compose window</h3>
    <p class="hint">How a new message or reply opens.</p>
    <label class="radio">
      <input type="radio" name="cmode" value="panel" checked={app.settings.composeMode === "panel"}
        onchange={() => setCompose({ composeMode: "panel" })} />
      <div><b>Docked panel</b><span>Opens in a corner, non-blocking — keep reading and clicking while you write (like Spark).</span></div>
    </label>
    <label class="radio">
      <input type="radio" name="cmode" value="window" checked={app.settings.composeMode === "window"}
        onchange={() => setCompose({ composeMode: "window" })} />
      <div><b>Separate window</b><span>Opens in its own movable window.</span></div>
    </label>

    {#if app.settings.composeMode === "panel"}
      <label class="inline">Corner
        <select value={app.settings.composePosition} onchange={(e) => setCompose({ composePosition: e.currentTarget.value })}>
          <option value="bottom-right">Bottom-right</option>
          <option value="bottom-left">Bottom-left</option>
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>Sending</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.undoSend} onchange={(e) => setCompose({ undoSend: e.currentTarget.checked })} />
      <div><b>Undo send</b><span>After hitting Send, hold the message briefly so you can cancel — it shows a “Sending…” bar with a Cancel button.</span></div>
    </label>
    {#if app.settings.undoSend}
      <label class="inline">Cancel window
        <select value={app.settings.undoSendDelay} onchange={(e) => setCompose({ undoSendDelay: Number(e.currentTarget.value) })}>
          <option value={3}>3 seconds</option>
          <option value={5}>5 seconds</option>
          <option value={10}>10 seconds</option>
        </select>
      </label>
    {/if}
  </section>

  <section class="card">
    <h3>Inbox</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.openNextOnDone} onchange={(e) => setCompose({ openNextOnDone: e.currentTarget.checked })} />
      <div><b>Open next after Done</b><span>When you mark the open message done, immediately open the next one — fast keyboard triage.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.unifiedInbox} onchange={toggleUnified} />
      <div><b>Unified inbox</b><span>Show one combined “All Inboxes” across every account.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.threading} onchange={(e) => setCompose({ threading: e.currentTarget.checked })} />
      <div><b>Conversation threading</b><span>Group messages with the same subject into one conversation; opening it shows the whole thread.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.bundles} onchange={(e) => setCompose({ bundles: e.currentTarget.checked })} />
      <div><b>Bundle notifications</b><span>Collapse 3+ messages from the same newsletter/social/update sender into one expandable card.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.showNewsletterFeed !== false} onchange={(e) => setCompose({ showNewsletterFeed: e.currentTarget.checked })} />
      <div><b>Newsletter Feed</b><span>Show the “Newsletter Feed” item in the sidebar. Turn off to hide it.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.showPaperTrail !== false} onchange={(e) => setCompose({ showPaperTrail: e.currentTarget.checked })} />
      <div><b>Paper Trail</b><span>Show the “Paper Trail” item (receipts, orders, confirmations) in the sidebar. Turn off to hide it.</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={app.settings.screener} onchange={(e) => setCompose({ screener: e.currentTarget.checked })} />
      <div><b>Screener (first-time senders)</b><span>Mail from people you've never corresponded with is held in a “Screener” instead of the inbox — approve or block each new sender once (Hey-style).</span></div>
    </label>
    <label class="inline">Follow-up nudge after
      <select value={app.settings.followupDays} onchange={(e) => setCompose({ followupDays: Number(e.currentTarget.value) })}>
        <option value={2}>2 days</option>
        <option value={3}>3 days</option>
        <option value={5}>5 days</option>
        <option value={7}>7 days</option>
      </select>
      with no reply
    </label>
  </section>

  <section class="card">
    <h3>Smart Inbox</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.smartInbox} onchange={(e) => setCompose({ smartInbox: e.currentTarget.checked })} />
      <div><b>Enable Smart Inbox</b><span>Replaces “All Inboxes” (and inbox folders) with a focused list — important mail stays in the main flow while the categories you pick collapse into expandable groups with live counts.</span></div>
    </label>
    {#if app.settings.smartInbox}
      <p class="hint" style="margin-top:10px">Group these (unchecked = left inline so you won't miss them):</p>
      <div class="smartcats">
        {#each SMART_CATS as c}
          <label class="grp"><input type="checkbox" checked={!!app.settings.smartGroups[c.id]} onchange={(e) => toggleGroup(c.id, e.currentTarget.checked)} /> <span>{@html c.icon} {c.label}</span></label>
        {/each}
      </div>

      <label class="inline" style="margin-top:14px">Senders shown per group
        <select value={app.settings.smartPreviewCount} onchange={(e) => saveSettings({ smartPreviewCount: Number(e.currentTarget.value) })}>
          <option value={2}>2</option><option value={3}>3</option><option value={4}>4</option><option value={6}>6</option>
        </select>
      </label>

      <p class="hint" style="margin-top:14px">Where the groups sit</p>
      <label class="grp"><input type="radio" name="splace" checked={(app.settings.smartGroupPlacement ?? "dateSections") === "dateSections"} onchange={() => setPlacement("dateSections")} /> <span><b>Date sections (Spark-style)</b> — Today / Yesterday / This week… with the group cards parked at the end of Today</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "timeline"} onchange={() => setPlacement("timeline")} /> <span>Float by activity (group rises with its newest mail; newer mail pushes it down)</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "top"} onchange={() => setPlacement("top")} /> <span>Always at the top</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "afterN"} onchange={() => setPlacement("afterN")} /> <span>After
        <select value={app.settings.smartGroupsAfter ?? 3} onchange={(e) => saveSettings({ smartGroupsAfter: Number(e.currentTarget.value) })} onclick={(e) => e.stopPropagation()}>
          <option value={1}>1</option><option value={2}>2</option><option value={3}>3</option><option value={4}>4</option><option value={5}>5</option>
        </select>
        newest messages</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "bottom"} onchange={() => setPlacement("bottom")} /> <span>Below all messages</span></label>

      <p class="hint" style="margin-top:14px">Group order</p>
      <label class="grp"><input type="radio" name="sorder" checked={app.settings.smartOrderMode !== "custom"} onchange={() => setOrderMode("recency")} /> <span>By recency (newest-active group on top)</span></label>
      <label class="grp"><input type="radio" name="sorder" checked={app.settings.smartOrderMode === "custom"} onchange={() => setOrderMode("custom")} /> <span>Custom (drag to order)</span></label>
      {#if app.settings.smartOrderMode === "custom"}
        <div class="orderlist">
          {#each orderedCats as c (c)}
            <div class="orderrow" draggable="true"
              ondragstart={() => (dragCat = c)} ondragend={() => (dragCat = null)}
              ondragover={(e) => { e.preventDefault(); reorder(c); }}>
              ⠿ {@html META[c]?.icon} {META[c]?.label}
            </div>
          {/each}
        </div>
      {/if}

      <p class="hint" style="margin-top:14px">Preview</p>
      <div class="preview-box">
        <SmartGroupCard label="Newsletters" icon={icons.newspaper} count={5471} newCount={4} senders={previewSenders}
          more={Math.max(0, 40 - previewSenders.length)} />
      </div>
    {/if}
  </section>

  <section class="card">
    <h3>Auto-BCC</h3>
    <p class="hint">Automatically BCC outgoing mail by the recipient's domain — e.g. blind-copy your CRM or ticketing system. Use <code>*</code> to match every recipient.</p>
    {#each bccRules as r, i}
      <div class="bccrow">
        <input placeholder="domain (client.com or *)" bind:value={r.domain} />
        <input placeholder="bcc@yoursystem.com" bind:value={r.bcc} />
        <button class="btn ghost danger" onclick={() => removeBcc(i)}>{@html icons.close}</button>
      </div>
    {/each}
    <div class="bccactions">
      <button class="btn" onclick={addBcc}>＋ Add rule</button>
      <button class="btn primary" onclick={saveBcc}>Save</button>
    </div>
  </section>

  <h2 class="group-head">Account &amp; system</h2>
  <section class="card">
    <h3>Backup &amp; migrate</h3>
    <p class="hint"><b>Full backup (.rmail)</b> — the easy one. Includes <b>everything</b>: your accounts, passwords,
      calendars, rules, signatures and settings, all encrypted with your master password. Move the file to another
      computer, install RaplMail, set the <b>same master password</b>, and import — you're fully set up, no re-adding accounts.</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={doExportFull} disabled={backingUp}>{@html icons.lock} {backingUp ? "Backing up…" : "Export full backup (.rmail)"}</button>
      <button class="btn" onclick={() => rmailFile.click()}>Restore from .rmail…</button>
      <input bind:this={rmailFile} type="file" accept=".rmail,application/octet-stream" hidden onchange={doImportFull} />
    </div>
    <p class="hint" style="margin-top:14px">Or a lighter <b>config-only</b> export (settings, rules, signatures, sender tags — no accounts or passwords) as plain JSON.</p>
    <div class="rowbtns">
      <button class="btn" onclick={doExport}>{@html icons.sent} Export config</button>
      <button class="btn" onclick={() => importFile.click()}>Import config…</button>
      <input bind:this={importFile} type="file" accept="application/json,.json" hidden onchange={doImport} />
    </div>
  </section>

  <section class="card">
    <h3>Local API <span class="tag">developer</span></h3>
    <p class="hint">Expose a read-only mailbox metrics endpoint for dashboards and home-automation
      (Home Assistant, ESP32, Grafana). It returns counts only — never message content — and is
      protected by the API key below.</p>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.localApiEnabled}
        onchange={(e) => toggleLocalApi(e.currentTarget.checked)} />
      <div><b>Enable local metrics API</b><span>When off, the endpoint returns 404.</span></div>
    </label>
    {#if app.settings.localApiEnabled}
      <div class="apibox">
        <div class="kv"><span>URL</span>
          <code>{metricsUrl}</code>
          <button class="btn ghost" onclick={() => copyText(metricsUrl)}>Copy</button>
        </div>
        <div class="kv"><span>API key</span>
          <code class="key">{app.settings.localApiKey || "—"}</code>
          <button class="btn ghost" onclick={() => copyText(app.settings.localApiKey)}>Copy</button>
          <button class="btn ghost" onclick={regenKey}>Regenerate</button>
        </div>
        <div class="kv"><span>Test</span>
          <code>curl -H "X-API-Key: {app.settings.localApiKey}" {metricsUrl}</code>
          <button class="btn ghost" onclick={() => copyText(`curl -H "X-API-Key: ${app.settings.localApiKey}" ${metricsUrl}`)}>Copy</button>
        </div>
        <p class="hint">JSON at <code>/metrics</code>, Prometheus text at <code>/metrics/prometheus</code>. Pass the key as
          the <code>X-API-Key</code> header or <code>?key=</code> query param. To reach it from <b>other devices on your
          LAN</b>, start the backend with <code>RAPLMAIL_HOST=0.0.0.0</code> and use this machine's LAN IP in place of the host.</p>
      </div>
    {/if}
  </section>

  <section class="card">
    <h3>Updates</h3>
    <p class="hint">RaplMail checks a signed release feed and updates itself in place. Updates are verified against
      a built-in public key, so only releases signed with your private key install.</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={() => checkForUpdates()}>{@html icons.sync} Check for updates</button>
    </div>
  </section>

  <section class="card">
    <h3>Tray &amp; startup</h3>
    <p class="hint">RaplMail can keep running in the system tray so new-mail sync and notifications keep working
      with the window closed.</p>
    <label class="check">
      <input type="checkbox" checked={app.settings.minimizeToTray !== false}
        onchange={(e) => setCloseToTray(e.currentTarget.checked)} />
      <div><b>Minimize to tray on close</b><span>Clicking the window's ✕ hides RaplMail to the tray instead of quitting. Use the tray icon's <b>Quit</b> to exit fully. (Off = ✕ quits the app.)</span></div>
    </label>
    <label class="check">
      <input type="checkbox" checked={!!app.settings.launchOnStartup}
        onchange={(e) => setAutostart(e.currentTarget.checked)} />
      <div><b>Launch at login</b><span>Start RaplMail automatically when you sign in (into the tray).</span></div>
    </label>
    <p class="hint">These take effect in the installed app — not in the browser dev view.</p>
  </section>

  <section class="card">
    <h3>AI assistant <span class="tag">bring your own key</span></h3>
    <p class="hint">Powers “Catch me up”, AI reply, and inbox triage. Your key is stored locally and calls go
      straight from this app to the provider you choose — there's no RaplMail server in between.</p>
    <label class="fieldrow"><span>Provider</span>
      <select value={app.settings.aiProvider || "anthropic"}
        onchange={(e) => saveSettings({ aiProvider: e.currentTarget.value })}>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="openai">OpenAI</option>
        <option value="openai-compatible">OpenAI-compatible (Groq, OpenRouter, Ollama, …)</option>
      </select>
    </label>
    <label class="fieldrow"><span>API key</span>
      <input type="password" placeholder={(app.settings.aiProvider || "anthropic") === "anthropic" ? "sk-ant-…" : "sk-…"}
        value={app.settings.aiApiKey || ""}
        onchange={(e) => saveSettings({ aiApiKey: e.currentTarget.value.trim() })} />
    </label>
    {#if (app.settings.aiProvider || "anthropic") === "openai-compatible"}
      <label class="fieldrow"><span>API base URL</span>
        <input placeholder="https://api.groq.com/openai/v1" value={app.settings.aiBaseUrl || ""}
          onchange={(e) => saveSettings({ aiBaseUrl: e.currentTarget.value.trim() })} />
      </label>
    {/if}
    <label class="fieldrow"><span>Model (optional)</span>
      <input placeholder={(app.settings.aiProvider || "anthropic") === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"}
        value={app.settings.aiModel || ""}
        onchange={(e) => saveSettings({ aiModel: e.currentTarget.value.trim() })} />
    </label>
    <p class="hint">{app.settings.aiApiKey ? "✓ Key set — AI actions are active." : "No key — AI buttons stay hidden until you add one."}</p>
    {#if app.settings.aiApiKey}
      <label class="check">
        <input type="checkbox" checked={app.settings.aiButtons !== false}
          onchange={(e) => saveSettings({ aiButtons: e.currentTarget.checked })} />
        <div><b>Show AI buttons</b><span>“Catch me up” / “AI reply” in the reader and the inbox-assistant command. Turn off to hide them even with a key set.</span></div>
      </label>
    {/if}
    <label class="check">
      <input type="checkbox" checked={!!app.settings.digestEnabled}
        onchange={(e) => saveSettings({ digestEnabled: e.currentTarget.checked })} />
      <div>
        <b>Daily morning briefing</b>
        <span>Once a day, deliver an AI digest of your unread inbox as a notification (needs the key above).</span>
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

  <h2 class="group-head">Notifications &amp; scheduling</h2>
  <section class="card">
    <h3>Notifications</h3>
    {#if notificationsAvailable()}
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyNewMail !== false && notifPerm === "granted"}
          onchange={(e) => toggleNotify(e.currentTarget.checked)} />
        <div>
          <b>Desktop notification for new mail</b>
          <span>Pops a system notification with the sender and subject when mail arrives.{#if notifPerm === "denied"} <em>Currently blocked in your OS/browser settings — re-enable it there first.</em>{/if}</span>
        </div>
      </label>
      <label class="check">
        <input type="checkbox" checked={app.settings.notifyOnlyUnfocused !== false}
          onchange={(e) => saveSettings({ notifyOnlyUnfocused: e.currentTarget.checked })} />
        <div>
          <b>Only when RaplMail isn't focused</b>
          <span>Stay quiet while you're already looking at the app.</span>
        </div>
      </label>
      <label class="check">
        <input type="checkbox" checked={!!app.settings.quietHoursEnabled}
          onchange={(e) => saveSettings({ quietHoursEnabled: e.currentTarget.checked })} />
        <div>
          <b>Quiet hours</b>
          <span>Silence notifications overnight.</span>
        </div>
      </label>
      {#if app.settings.quietHoursEnabled}
        <label class="inline" style="margin-left:28px">From
          <select value={app.settings.quietStart ?? 22} onchange={(e) => saveSettings({ quietStart: Number(e.currentTarget.value) })}>
            {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
          </select> to
          <select value={app.settings.quietEnd ?? 7} onchange={(e) => saveSettings({ quietEnd: Number(e.currentTarget.value) })}>
            {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
          </select>
        </label>
      {/if}
      <label class="inline" style="margin-top:10px">{t("notif.sound")}
        <select value={app.settings.notifySound || "ding"} onchange={(e) => { saveSettings({ notifySound: e.currentTarget.value }); playSound(e.currentTarget.value, notifVol / 100); }}>
          {#each SOUND_OPTIONS as s}<option value={s.id}>{s.label}</option>{/each}
        </select>
        <button class="btn sm" onclick={() => playSound(app.settings.notifySound || "ding", notifVol / 100)}>▶ {t("common.play")}</button>
      </label>
      <label class="inline" style="margin-top:10px">{t("notif.volume")}
        <input type="range" min="0" max="100" step="5" value={notifVol}
          disabled={(app.settings.notifySound || "ding") === "none"}
          oninput={(e) => saveSettings({ notifyVolume: Number(e.currentTarget.value) })}
          onchange={(e) => playSound(app.settings.notifySound || "ding", Number(e.currentTarget.value) / 100)} />
        <span class="tnum" style="width:38px;text-align:right">{notifVol}%</span>
      </label>
      <span class="hint" style="margin:2px 0 0 2px">A short chime plays when new mail arrives (even while the app is focused).</span>
      <p class="hint" style="margin-top:8px">{t("notif.muteHint")}</p>
      <button class="btn" style="margin-top:10px" onclick={sendTest}>{t("notif.test")}</button>
      <p class="hint" style="margin-top:8px">No popup? It's almost always the OS: Windows <b>Settings → Notifications</b> must allow this app, and <b>Focus Assist / Do Not Disturb</b> must be off.</p>
    {:else}
      <p class="hint">Desktop notifications aren't available in this environment.</p>
    {/if}
  </section>

  <section class="card">
    <h3>Scheduling &amp; snooze times</h3>
    <p class="hint">What the snooze / send-later presets actually mean.</p>
    <label class="inline">“Later today” = now +
      <select value={app.settings.scheduleLaterHours ?? 3} onchange={(e) => saveSettings({ scheduleLaterHours: Number(e.currentTarget.value) })}>
        {#each [1,2,3,4,6,8] as h}<option value={h}>{h}</option>{/each}
      </select> hours
    </label>
    <label class="inline">Morning (Tomorrow / weekend / next week) at
      <select value={app.settings.scheduleMorningHour ?? 9} onchange={(e) => saveSettings({ scheduleMorningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
      </select>
    </label>
    <label class="inline">“This evening” at
      <select value={app.settings.scheduleEveningHour ?? 18} onchange={(e) => saveSettings({ scheduleEveningHour: Number(e.currentTarget.value) })}>
        {#each Array.from({length:24},(_,i)=>i) as h}<option value={h}>{(h%12||12)}:00 {h<12?"AM":"PM"}</option>{/each}
      </select>
    </label>
    <p class="hint" style="margin-top:8px">Need an exact time? The compose “Later ⌄” menu has a date &amp; time picker.</p>
  </section>

  <h2 class="group-head">Security &amp; privacy</h2>
  <section class="card">
    <h3>Privacy</h3>
    <label class="check">
      <input type="checkbox" checked={app.settings.blockTrackers} onchange={(e) => setCompose({ blockTrackers: e.currentTarget.checked })} />
      <div><b>Block tracking pixels</b><span>Blocks invisible 1×1 pixels and known open-tracking images so senders can't tell when you read. Real images (logos, photos, content) still load normally — you can also “Load everything” per message.</span></div>
    </label>
  </section>

  <section class="card">
    <h3>Startup password</h3>
    {#if app.vault.auto_unlock}
      <p class="hint ok">{@html icons.done} RaplMail unlocks automatically on startup.</p>
      <button class="btn" onclick={disableAuto} disabled={busy}>Require password again</button>
    {:else}
      <p class="hint">By default you enter your master password each time RaplMail starts.</p>
      {#if !showAutoPw}
        <button class="btn" onclick={() => (showAutoPw = true)}>Don't require password on startup</button>
      {:else}
        <div class="warn">
          {@html icons.warning} This stores your master password on this device so anyone with access to your
          computer can open your mail. Your account credentials are still encrypted, and this
          same password will be used to encrypt exports later.
        </div>
        <div class="confirm">
          <input type="password" placeholder="Confirm master password" bind:value={autoPw}
            onkeydown={(e) => e.key === "Enter" && enableAuto()} />
          <button class="btn primary" onclick={enableAuto} disabled={busy}>{busy ? "…" : "Enable"}</button>
          <button class="btn ghost" onclick={() => { showAutoPw = false; autoPw = ""; }}>Cancel</button>
        </div>
      {/if}
    {/if}
  </section>
</div>

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
  .fieldrow { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .fieldrow > span { width: 140px; flex: none; color: var(--muted); font-size: 13px; }
  .fieldrow input { flex: 1; }
</style>
