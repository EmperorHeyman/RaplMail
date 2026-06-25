<script>
  import { app, saveSettings, refreshVault, notify, selectUnifiedInbox, refreshMessages, smartActive, enableNotifications, notificationsAvailable, exportConfig, importConfig } from "../store.svelte.js";
  import { vault } from "../api.js";
  import SmartGroupCard from "./SmartGroupCard.svelte";
  import { icons } from "../icons.js";

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

  let notifPerm = $state(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
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

  // Configurable quick-action buttons.
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
    on ? cur.add(key) : cur.delete(key);
    saveSettings({ readerActions: order.filter((k) => cur.has(k)) });
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
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "timeline"} onchange={() => setPlacement("timeline")} /> <span>Float by activity (group rises with its newest mail; newer mail pushes it down)</span></label>
      <label class="grp"><input type="radio" name="splace" checked={app.settings.smartGroupPlacement === "top"} onchange={() => setPlacement("top")} /> <span>Always at the top</span></label>
      <label class="grp"><input type="radio" name="splace" checked={(app.settings.smartGroupPlacement ?? "afterN") === "afterN"} onchange={() => setPlacement("afterN")} /> <span>After
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
        <SmartGroupCard label="Newsletters" icon={icons.newspaper} count={5471} senders={previewSenders}
          more={Math.max(0, 40 - previewSenders.length)} />
      </div>
    {/if}
  </section>

  <section class="card">
    <h3>Backup &amp; migrate</h3>
    <p class="hint">Export your settings, rules, signatures and sender tags to a file, then import them on another install (e.g. dev → prod). Emails aren't included — they re-sync from your mail server once you connect the accounts there.</p>
    <div class="rowbtns">
      <button class="btn primary" onclick={doExport}>{@html icons.sent} Export config</button>
      <button class="btn" onclick={() => importFile.click()}>Import config…</button>
      <input bind:this={importFile} type="file" accept="application/json,.json" hidden onchange={doImport} />
    </div>
  </section>

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
    {:else}
      <p class="hint">Desktop notifications aren't available in this environment.</p>
    {/if}
  </section>

  <section class="card">
    <h3>Quick-action buttons</h3>
    <p class="hint">The two buttons that appear on each message row when you hover.</p>
    <div class="rowbtns">
      {#each [0, 1] as idx}
        <label class="inline">{idx === 0 ? "Left" : "Right"}
          <select value={(app.settings.rowActions || ["snooze", "done"])[idx]} onchange={(e) => setRowAction(idx, e.currentTarget.value)}>
            {#each ROW_CHOICES as [val, label]}<option value={val}>{label}</option>{/each}
          </select>
        </label>
      {/each}
    </div>
    <p class="hint" style="margin-top:16px">Buttons shown under the recipient when reading a message.</p>
    <div class="smartcats">
      {#each READER_CHOICES as [val, label]}
        <label class="grp"><input type="checkbox"
          checked={(app.settings.readerActions || READER_CHOICES.map((c) => c[0])).includes(val)}
          onchange={(e) => toggleReaderAction(val, e.currentTarget.checked)} /> <span>{label}</span></label>
      {/each}
    </div>
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
</style>
