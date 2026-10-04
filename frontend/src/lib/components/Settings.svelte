<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import SettingsAccounts from "./SettingsAccounts.svelte";
  import SettingsRules from "./SettingsRules.svelte";
  import SettingsSecurity from "./SettingsSecurity.svelte";
  import SettingsContacts from "./SettingsContacts.svelte";
  import SettingsGeneral from "./SettingsGeneral.svelte";
  import SettingsAi from "./SettingsAi.svelte";
  import SettingsAppearance from "./SettingsAppearance.svelte";
  import SettingsWorkspaces from "./SettingsWorkspaces.svelte";
  import SettingsShortcuts from "./SettingsShortcuts.svelte";
  import SettingsAliases from "./SettingsAliases.svelte";
  import SettingsPgp from "./SettingsPgp.svelte";
  import SettingsSmime from "./SettingsSmime.svelte";
  import SettingsCalendar from "./SettingsCalendar.svelte";
  import SettingsDebug from "./SettingsDebug.svelte";
  import SettingsInbox from "./SettingsInbox.svelte";
  import SettingsCompose from "./SettingsCompose.svelte";
  import SettingsNotifications from "./SettingsNotifications.svelte";
  import SettingsBackup from "./SettingsBackup.svelte";
  import SettingsIntegrations from "./SettingsIntegrations.svelte";
  import { icons, filledIcon } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { SETTINGS_INDEX } from "../settingsIndex.js";

  // Tabs that were folded into others keep working as links: an old id opens
  // the tab its panel lives in now.
  const TAB_ALIAS = { workspaces: "accounts", aliases: "security", pgp: "encryption", smime: "encryption",
                      signature: "compose", snippets: "compose", sync: "backup", rapldesk: "integrations",
                      utility: "general" };
  const resolveTab = (id) => TAB_ALIAS[id] || id;
  let tab = $state(resolveTab(app.settingsTab || "accounts"));
  if (app.settingsTab) app.settingsTab = null;
  // Deep-links (e.g. RuleModal → "Manage all rules") must also work while
  // Settings is already mounted - consuming settingsTab only at init missed those.
  $effect(() => {
    if (app.settingsTab) { tab = resolveTab(app.settingsTab); app.settingsTab = null; }
  });
  // Grouped under section headings in the nav. 19 flat tabs (with a General
  // tab of ~15 unrelated topics) became these: small tabs folded into the one
  // they belong to, General split into Inbox / Compose / Notifications /
  // Backup & sync / Integrations. `kw` = search keywords for the nav filter.
  const SECTIONS = $derived.by(() => [
    { id: "mail", label: t("settingsNav.secMail") },
    { id: "people", label: t("settingsNav.secPeople") },
    { id: "privacy", label: t("settingsNav.secPrivacy") },
    { id: "look", label: t("settingsNav.secLook") },
    { id: "system", label: t("settingsNav.secSystem") },
  ]);
  const tabs = $derived.by(() => [
    { id: "accounts", ik: "accounts", sec: "mail", label: t("settingsNav.accounts"), icon: icons.accounts, kw: "email imap smtp oauth microsoft m365 google gmail add account password connect sign in reconnect history backfill workspace workspaces group accounts switch context" },
    { id: "inbox", ik: "inbox", sec: "mail", label: t("settingsNav.inbox"), icon: icons.inbox, kw: "inbox smart inbox groups group strip unified all inboxes per account new mail threading conversation open next done follow-up followup nudge quoted replies code highlight newsletter feed paper trail snooze later today morning evening schedule" },
    { id: "compose", ik: "compose", sec: "mail", label: t("settingsNav.compose"), icon: icons.compose, kw: "compose window docked panel separate corner spell check spelling undo send cancel delay auto-bcc bcc blind copy signature signatures snippets templates canned replies expander" },
    { id: "rules", ik: "rules", sec: "mail", label: t("settingsNav.rules"), icon: icons.rules, kw: "rules blocking filter domain move archive delete block sender group" },
    { id: "notifications", ik: "bell", sec: "mail", label: t("settingsNav.notifications"), icon: icons.bell, kw: "notifications notification desktop notify popup sound ding chime volume quiet hours night custom sound test" },
    { id: "contacts", ik: "contacts", sec: "people", label: t("settingsNav.contacts"), icon: icons.contacts, kw: "address book contacts people favorites rescan carddav" },
    { id: "calendar", ik: "calendar", sec: "people", label: t("settingsNav.calendar"), icon: icons.calendar, kw: "calendar caldav carddav events sync nextcloud fastmail icloud seznam radicale subscribe ical ics google reminders reminder sound popup window" },
    { id: "security", ik: "shieldCheck", sec: "privacy", label: t("settingsNav.securityPrivacy"), icon: icons.shieldCheck, kw: "security privacy phishing spoof spoofing impersonation brand lookalike domain blocker blocklist tld scam junk quarantine tracking pixel screener first-time sender ai screening suspicious link previews unfurl alias aliases plus address tracking leak who shared generate" },
    { id: "encryption", ik: "lock", sec: "privacy", label: t("settingsNav.encryption"), icon: icons.lock, kw: "encryption encrypt sign verify decrypt pgp gpg openpgp key smime s/mime x509 certificate p12 pfx" },
    { id: "appearance", ik: "palette", sec: "look", label: t("settingsNav.appearance"), icon: icons.palette, kw: "theme themes color colour preset dark light css radius corner rounded avatar logo favicon relative time email adapt customize layout density reading width font size quick action buttons reply forward done" },
    { id: "shortcuts", ik: "keyboard", sec: "look", label: t("settingsNav.shortcuts"), icon: icons.keyboard, kw: "keyboard shortcuts keybindings keys hotkeys palette search key hints" },
    { id: "ai", ik: "bolt", sec: "system", label: t("settingsNav.ai"), icon: icons.bolt, kw: "ai assistant ollama local llm model gpt claude anthropic openai api key provider keep alive gpu vram unload catch me up reply rewrite triage briefing digest semantic search embeddings vector nomic keyless offline private" },
    { id: "backup", ik: "sync", sec: "system", label: t("settingsNav.backup"), icon: icons.sync, kw: "backup export import migrate restore rmail move another computer device sync devices link two computers laptop settings encrypted passphrase" },
    { id: "integrations", ik: "link", sec: "system", label: t("settingsNav.integrations"), icon: icons.link, kw: "integrations local api metrics prometheus home assistant webhook n8n node-red rapl desk rapldesk tickets helpdesk" },
    { id: "general", ik: "general", sec: "system", label: t("settingsNav.general"), icon: icons.general, kw: "general language english czech updates update version tray startup launch login minimize" },
    // Debug is hidden until unlocked with 5 taps on the version (Android-style).
    ...(app.settings.debugUnlocked ? [{ id: "debug", ik: "bug", sec: "system", label: t("settingsNav.debug"), icon: icons.bug, kw: "debug log logs console backend diagnostics sync health error troubleshoot stuck hang stall developer verbose activity" }] : []),
  ]);

  // 5 consecutive clicks on the version string reveal the Debug section.
  let verClicks = 0;
  let _verTimer;
  function tapVersion() {
    if (app.settings.debugUnlocked) return;
    verClicks++;
    clearTimeout(_verTimer);
    _verTimer = setTimeout(() => (verClicks = 0), 1200);
    const left = 5 - verClicks;
    if (verClicks >= 5) {
      verClicks = 0;
      saveSettings({ debugUnlocked: true });
      notify(t("settingsNav.debugUnlocked"));
      tab = "debug";
    } else if (left <= 3) {
      notify(t("settingsNav.debugCountdown", { n: left }));
    }
  }

  let appVersion = $state("");
  onMount(async () => {
    try { const { getVersion } = await import("@tauri-apps/api/app"); appVersion = await getVersion(); }
    catch { appVersion = "dev"; }
  });

  let query = $state("");
  // Normalize so punctuation/hyphens don't matter: "quick-action" matches
  // "quick action". Every word in the query must appear somewhere in the tab.
  const _norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const filtered = $derived.by(() => {
    const q = _norm(query);
    if (!q) return tabs;
    const terms = q.split(" ");
    return tabs.filter((t) => {
      const hay = _norm(t.label + " " + t.kw);
      return terms.every((w) => hay.includes(w));
    });
  });
  const tabLabel = (id) => tabs.find((tb) => tb.id === id)?.label || id;
  // Matching INDIVIDUAL settings - so search jumps to the exact control, not just
  // its category. Ranked so a label hit beats a keyword-only hit.
  const results = $derived.by(() => {
    const q = _norm(query);
    if (!q) return [];
    const terms = q.split(" ");
    return SETTINGS_INDEX
      .map((r) => {
        const label = _norm(r.label);
        const hay = label + " " + _norm(r.kw) + " " + _norm(tabLabel(r.tab));
        if (!terms.every((w) => hay.includes(w))) return null;
        const score = terms.every((w) => label.includes(w)) ? 0 : 1;   // label match first
        return { ...r, score };
      })
      .filter(Boolean)
      .sort((a, b) => a.score - b.score)
      .slice(0, 24);
  });
  // If the current tab is filtered out, jump to the first match (only while the
  // category list is what's showing - not while the user is scanning results).
  $effect(() => {
    if (query.trim()) return;
    if (filtered.length && !filtered.some((t) => t.id === tab)) tab = filtered[0].id;
  });

  // Jump to a specific setting: open its tab, clear the search, then briefly
  // flash the matching control in the panel so the eye lands on it. Best-effort -
  // if the label isn't found (e.g. localized text), we still land on the tab.
  function openSetting(r) {
    tab = r.tab;
    query = "";
    requestAnimationFrame(() => requestAnimationFrame(() => flashSetting(r.label)));
  }
  function flashSetting(label) {
    const panel = document.querySelector(".settings .panel");
    if (!panel) return;
    const target = _norm(label);
    const els = panel.querySelectorAll("label, h2, h3, h4, .field > b, .field, .row, .token, button, summary");
    let best = null;
    for (const el of els) {
      const txt = _norm(el.textContent);
      // Match, but skip big wrapper elements so we flash the actual control.
      if (txt.includes(target) && txt.length < target.length + 80) { best = el; break; }
    }
    if (!best) return;
    best.scrollIntoView({ block: "center", behavior: "smooth" });
    best.classList.add("setting-flash");
    setTimeout(() => best.classList.remove("setting-flash"), 1700);
  }
</script>

<section class="settings">
  <aside class="snav">
    <button class="back" onclick={() => (app.view = "mail")}>{@html icons.back} {t("settingsNav.backToMail")}</button>
    <div class="search"><span class="s-ic">{@html icons.search}</span>
      <input type="search" placeholder={t("settingsNav.searchPlaceholder")} bind:value={query} />
    </div>
    <nav>
      {#if query.trim() && results.length}
        <div class="nav-head">{t("settingsNav.settingsHead")}</div>
        {#each results as r}
          <button class="result" onclick={() => openSetting(r)}>
            <span class="r-label">{r.label}</span>
            <span class="r-cat">{tabLabel(r.tab)}</span>
          </button>
        {/each}
        <div class="nav-head">{t("settingsNav.sectionsHead")}</div>
      {/if}
      {#each filtered as tb, i (tb.id)}
        {#if !query.trim() && tb.sec !== filtered[i - 1]?.sec}
          <div class="nav-head grp">{SECTIONS.find((x) => x.id === tb.sec)?.label}</div>
        {/if}
        <button class="tab" class:active={tab === tb.id} onclick={() => (tab = tb.id)}>
          <span class="t-ic">{@html tab === tb.id ? filledIcon(tb.ik) : tb.icon}</span> {tb.label}
        </button>
      {/each}
      {#if filtered.length === 0 && results.length === 0}<span class="no-match">{t("settingsNav.noMatch", { query })}</span>{/if}
    </nav>
  </aside>
  <div class="panel stagger-in">
    <h1>{tabs.find((tb) => tb.id === tab)?.label || t("settingsNav.title")}</h1>
    {#if tab === "accounts"}
      <SettingsAccounts />
      <h2 class="subsec">{t("settingsNav.workspaces")}</h2>
      <SettingsWorkspaces />
    {:else if tab === "inbox"}<SettingsInbox />
    {:else if tab === "compose"}<SettingsCompose />
    {:else if tab === "rules"}<SettingsRules />
    {:else if tab === "notifications"}<SettingsNotifications />
    {:else if tab === "contacts"}
      <SettingsContacts />
      <p class="xref">{t("settingsNav.contactsCardDav")}
        <button class="xlink" onclick={() => (tab = "calendar")}>{t("sNotif.openCalendar")} →</button></p>
    {:else if tab === "calendar"}<SettingsCalendar />
    {:else if tab === "security"}
      <SettingsSecurity />
      <h2 class="subsec">{t("settingsNav.trackingAliases")}</h2>
      <SettingsAliases />
    {:else if tab === "encryption"}
      <SettingsPgp />
      <div class="gap"></div>
      <SettingsSmime />
    {:else if tab === "appearance"}<SettingsAppearance />
    {:else if tab === "shortcuts"}<SettingsShortcuts />
    {:else if tab === "ai"}<SettingsAi />
    {:else if tab === "backup"}<SettingsBackup />
    {:else if tab === "integrations"}<SettingsIntegrations />
    {:else if tab === "debug"}<SettingsDebug />
    {:else}<SettingsGeneral />{/if}
    <footer class="madeby">
      RaplMail <button class="ver" title={app.settings.debugUnlocked ? "" : t("settingsNav.debugHintTip")} onclick={tapVersion}>v{appVersion}</button> · {t("settingsNav.madeBy")} <a href="https://rapl-group.eu/" target="_blank" rel="noreferrer">RAPL Group</a>
    </footer>
  </div>
</section>

<style>
  /* Pixel-style settings: the section list and the page both sit on the window
     ground; each panel's groups are rounded cards on it. */
  .settings { display: flex; min-width: 0; overflow: hidden; }
  /* Vertical settings nav - 15 sections don't fit a horizontal tab strip. */
  .snav {
    flex: none; width: 264px; display: flex; flex-direction: column; gap: 8px;
    padding: 2px 8px 8px 0; min-height: 0; overflow: hidden;
  }
  .back {
    flex: none; align-self: flex-start; display: flex; align-items: center; gap: 10px;
    height: 44px; padding: 0 18px 0 12px; border-radius: 999px;
    color: var(--text); font-size: 15px; font-weight: 500;
    transition: background var(--t-fast) var(--ease);
  }
  .back :global(svg) { width: 22px; height: 22px; }
  .back:hover { background: var(--hover); }
  h1 { margin: 0 0 28px 4px; font-size: 36px; line-height: 44px; font-weight: 400; letter-spacing: 0; }
  .search { display: flex; align-items: center; gap: 10px; height: 44px; padding: 0 16px; flex: none;
    background: var(--surface-2); border-radius: 22px; transition: background var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease); }
  .search:focus-within { background: var(--surface); box-shadow: var(--shadow); }
  .search .s-ic { color: var(--muted); display: inline-flex; flex: none; }
  .search .s-ic :global(svg) { width: 20px; height: 20px; }
  .search input { border: none; background: transparent; outline: none; box-shadow: none; width: 100%; min-width: 0; padding: 2px 0; font-size: 14px; }
  .search input:hover, .search input:focus { border: none; box-shadow: none; }
  .no-match { color: var(--muted); font-size: 13px; padding: 9px 16px; display: block; }
  nav { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; padding-bottom: 8px; }
  .nav-head { font-size: 13px; font-weight: 500; color: var(--muted); padding: 12px 16px 6px; }
  .nav-head:first-child { padding-top: 4px; }
  .nav-head.grp { padding-top: 16px; }
  .nav-head.grp:first-child { padding-top: 4px; }
  /* Heading over a second panel shown on the same page (e.g. Workspaces). */
  .subsec { margin: 36px 0 16px 4px; font-size: 22px; line-height: 28px; font-weight: 400; color: var(--text); }
  .gap { height: 24px; }
  .xref { margin: 18px 0 0 4px; max-width: 640px; color: var(--muted); font-size: 13.5px; }
  .xlink { color: var(--accent); font-size: 13.5px; padding: 0; }
  .xlink:hover { text-decoration: underline; }
  /* Exact-setting result: setting name on top, its category underneath. */
  .result { display: flex; flex-direction: column; gap: 1px; padding: 8px 16px; border-radius: 16px; text-align: left; width: 100%;
    transition: background var(--t-fast) var(--ease); }
  .result:hover { background: var(--hover); }
  .r-label { font-size: 14px; font-weight: 500; color: var(--text); }
  .r-cat { font-size: 12px; color: var(--muted); }
  .tab {
    position: relative; display: flex; align-items: center; gap: 12px; flex: none;
    height: 40px; padding: 0 16px 0 14px; border-radius: 999px; color: var(--muted); font-weight: 500;
    font-size: 14px; text-align: left; width: 100%;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .t-ic { display: grid; place-items: center; width: 24px; flex: none; }
  .t-ic :global(svg) { width: 22px; height: 22px; }
  .tab:hover { background: var(--hover); color: var(--text); }
  .tab.active { background: var(--sel); color: var(--on-sel); font-weight: 650; }
  .panel { flex: 1; overflow-y: auto; padding: 40px 40px 32px 32px; min-width: 0; }
  .madeby { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--hairline); text-align: center; color: var(--muted); font-size: 12px; }
  .madeby a { color: var(--accent); text-decoration: none; }
  .madeby a:hover { text-decoration: underline; }
  .madeby .ver { color: var(--text); font-variant-numeric: tabular-nums; font: inherit; cursor: pointer; padding: 0 2px; border-radius: 4px; -webkit-user-select: none; user-select: none; }
  .madeby .ver:hover { background: var(--hover); }

  /* ── Shared look for every settings panel ──
     The panels each style their own cards and toggles; these rules give them
     one Material look without touching each file: groups are borderless
     rounded cards, group titles are Android's coloured section headers, and
     every "check" setting becomes a row with a switch on the right. */
  .panel :global(.card) {
    background: var(--surface); border: none; border-radius: var(--radius-lg); padding: 20px 24px;
  }
  .panel :global(.card > h3), .panel :global(.card > .head h3), .panel :global(.card > header h3) {
    font-size: 14px; font-weight: 600; letter-spacing: 0.1px; color: var(--accent);
  }
  .panel :global(.hint), .panel :global(.fhint) { color: var(--muted); }
  .panel :global(label.check) {
    flex-direction: row-reverse; justify-content: space-between; align-items: center; gap: 20px;
  }
  .panel :global(label.check > div), .panel :global(label.check > span) { flex: 1; min-width: 0; }
  .panel :global(label.check b) { font-weight: 500; font-size: 14.5px; }
  .panel :global(label.check input[type="checkbox"]) {
    appearance: none; -webkit-appearance: none; flex: none; position: relative;
    width: 52px; height: 32px; margin: 0; border-radius: 16px; cursor: pointer;
    background: var(--surface-3); box-shadow: inset 0 0 0 2px var(--outline);
    transition: background var(--t) var(--ease), box-shadow var(--t) var(--ease);
  }
  .panel :global(label.check input[type="checkbox"]::before) {
    content: ""; position: absolute; top: 50%; left: 16px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--outline); transform: translate(-50%, -50%);
    transition: left var(--t) var(--ease), width var(--t) var(--ease), height var(--t) var(--ease), background var(--t) var(--ease);
  }
  .panel :global(label.check input[type="checkbox"]:checked) { background: var(--accent); box-shadow: none; }
  .panel :global(label.check input[type="checkbox"]:checked::before) { left: 36px; width: 24px; height: 24px; background: var(--on-accent); }
  .panel :global(label.check:hover input[type="checkbox"]:not(:disabled)::before) { box-shadow: 0 0 0 8px var(--hover); }
  .panel :global(label.check input[type="checkbox"]:focus-visible) { box-shadow: var(--ring); }
  .panel :global(label.check input[type="checkbox"]:disabled) { opacity: 0.38; cursor: default; }
  /* Segmented buttons. */
  .panel :global(.seg) { background: transparent; border: 1px solid var(--outline); border-radius: 999px; padding: 0; gap: 0; overflow: hidden; }
  .panel :global(.segbtn) { border-radius: 0; padding: 8px 16px; font-size: 13px; font-weight: 500; color: var(--text); }
  .panel :global(.segbtn + .segbtn) { border-left: 1px solid var(--outline); }
  .panel :global(.segbtn:hover) { background: var(--hover); color: var(--text); }
  .panel :global(.segbtn.on) { background: var(--sel); color: var(--on-sel); }
</style>
