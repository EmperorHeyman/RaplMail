<script>
  import { onMount } from "svelte";
  import { app, saveSettings, notify } from "../store.svelte.js";
  import SettingsAccounts from "./SettingsAccounts.svelte";
  import SettingsRules from "./SettingsRules.svelte";
  import SettingsSecurity from "./SettingsSecurity.svelte";
  import SettingsSignature from "./SettingsSignature.svelte";
  import SettingsContacts from "./SettingsContacts.svelte";
  import SettingsGeneral from "./SettingsGeneral.svelte";
  import SettingsAi from "./SettingsAi.svelte";
  import SettingsSnippets from "./SettingsSnippets.svelte";
  import SettingsAppearance from "./SettingsAppearance.svelte";
  import SettingsWorkspaces from "./SettingsWorkspaces.svelte";
  import SettingsShortcuts from "./SettingsShortcuts.svelte";
  import SettingsAliases from "./SettingsAliases.svelte";
  import SettingsPgp from "./SettingsPgp.svelte";
  import SettingsSmime from "./SettingsSmime.svelte";
  import SettingsCalendar from "./SettingsCalendar.svelte";
  import SettingsSync from "./SettingsSync.svelte";
  import SettingsRaplDesk from "./SettingsRaplDesk.svelte";
  import SettingsUtility from "./SettingsUtility.svelte";
  import SettingsDebug from "./SettingsDebug.svelte";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
  import { SETTINGS_INDEX } from "../settingsIndex.js";

  let tab = $state(app.settingsTab || "accounts");
  if (app.settingsTab) app.settingsTab = null;
  // Deep-links (e.g. RuleModal → "Manage all rules") must also work while
  // Settings is already mounted — consuming settingsTab only at init missed those.
  $effect(() => {
    if (app.settingsTab) { tab = app.settingsTab; app.settingsTab = null; }
  });
  const tabs = $derived.by(() => [
    { id: "accounts", label: t("settingsNav.accounts"), icon: icons.accounts, kw: "email imap smtp oauth microsoft m365 google gmail add account password connect sign in" },
    { id: "workspaces", label: t("settingsNav.workspaces"), icon: icons.workspaces, kw: "workspace group accounts switch context" },
    { id: "contacts", label: t("settingsNav.contacts"), icon: icons.contacts, kw: "address book contacts people favorites rescan" },
    { id: "rules", label: t("settingsNav.rules"), icon: icons.rules, kw: "rules blocking filter domain move archive delete block sender" },
    { id: "security", label: t("settingsNav.security"), icon: icons.shieldCheck || icons.shield || icons.rules, kw: "security phishing spoof spoofing impersonation brand lookalike domain blocker blocklist tld ru scam junk quarantine tracking pixel screener first-time sender startup password lock unlock privacy ai screening check suspicious dangerous" },
    { id: "aliases", label: t("settingsNav.aliases"), icon: icons.shield || icons.rules, kw: "alias aliases plus address subaddress sub-address tracking privacy leak who shared service generate tag mute" },
    { id: "pgp", label: t("settingsNav.pgp"), icon: icons.shieldCheck || icons.shield || icons.rules, kw: "pgp gpg openpgp encryption sign verify decrypt key public private secure" },
    { id: "smime", label: t("settingsNav.smime"), icon: icons.shield || icons.shieldCheck || icons.rules, kw: "smime s/mime x509 x.509 pkcs7 pkcs12 p12 pfx certificate enterprise encryption sign encrypt" },
    { id: "signature", label: t("settingsNav.signature"), icon: icons.signature, kw: "signature html image preview text footer" },
    { id: "snippets", label: t("settingsNav.snippets"), icon: icons.bolt, kw: "snippets templates canned replies expander shortcut variables" },
    { id: "appearance", label: t("settingsNav.appearance"), icon: icons.palette, kw: "theme color colour preset dark light css radius corner rounded avatar logo favicon relative time email adapt customize layout font style vscode quick action quick-action buttons row buttons hover reader actions reply forward done flag" },
    { id: "ai", label: t("settingsNav.ai"), icon: icons.bolt, kw: "ai assistant ollama local llm model gpt claude anthropic openai api key provider keep alive gpu vram unload catch me up reply rewrite triage briefing digest semantic search embeddings vector nomic keyless offline private" },
    { id: "shortcuts", label: t("settingsNav.shortcuts"), icon: icons.keyboard, kw: "keyboard shortcuts keybindings keys hotkeys palette" },
    { id: "calendar", label: t("settingsNav.calendar"), icon: icons.calendar || icons.general, kw: "calendar contacts caldav carddav events sync nextcloud fastmail icloud seznam radicale subscribe add calendar" },
    { id: "sync", label: t("settingsNav.sync"), icon: icons.sync || icons.general, kw: "sync device devices link two computers pc laptop desktop cross-device settings done read state encrypted passphrase mailbox self-mail multi-device share between machines" },
    { id: "rapldesk", label: t("settingsNav.rapldesk"), icon: icons.receipt || icons.general, kw: "rapldesk tickets ticketing api key support helpdesk instance" },
    { id: "utility", label: t("settingsNav.utility"), icon: icons.bolt || icons.general, kw: "utility utilities subscription audit unsubscribe mailing list newsletter cleanup read rate dormant tools" },
    { id: "general", label: t("settingsNav.general"), icon: icons.general, kw: "mail behavior compose sending undo send smart inbox notifications desktop notification snooze presence backup export import migrate auto-bcc bcc startup launch login tray minimize updates ai assistant local api metrics read receipt scheduling snooze times follow-up screener threading bundles group placement privacy tracking password security newsletter paper trail drafts" },
    // Debug is hidden until unlocked with 5 taps on the version (Android-style).
    ...(app.settings.debugUnlocked ? [{ id: "debug", label: t("settingsNav.debug"), icon: icons.bolt || icons.general, kw: "debug log logs console backend diagnostics sync health error troubleshoot stuck hang stall developer verbose activity" }] : []),
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
  // Matching INDIVIDUAL settings — so search jumps to the exact control, not just
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
  // category list is what's showing — not while the user is scanning results).
  $effect(() => {
    if (query.trim()) return;
    if (filtered.length && !filtered.some((t) => t.id === tab)) tab = filtered[0].id;
  });

  // Jump to a specific setting: open its tab, clear the search, then briefly
  // flash the matching control in the panel so the eye lands on it. Best-effort —
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
    <button class="back" onclick={() => (app.view = "mail")}>← {t("settingsNav.backToMail")}</button>
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
      {#each filtered as t}
        <button class="tab" class:active={tab === t.id} onclick={() => (tab = t.id)}>
          <span class="t-ic">{@html t.icon}</span> {t.label}
        </button>
      {/each}
      {#if filtered.length === 0 && results.length === 0}<span class="no-match">{t("settingsNav.noMatch", { query })}</span>{/if}
    </nav>
  </aside>
  <div class="panel stagger-in">
    <h1>{tabs.find((tb) => tb.id === tab)?.label || t("settingsNav.title")}</h1>
    {#if tab === "accounts"}<SettingsAccounts />
    {:else if tab === "workspaces"}<SettingsWorkspaces />
    {:else if tab === "contacts"}<SettingsContacts />
    {:else if tab === "rules"}<SettingsRules />
    {:else if tab === "security"}<SettingsSecurity />
    {:else if tab === "aliases"}<SettingsAliases />
    {:else if tab === "pgp"}<SettingsPgp />
    {:else if tab === "smime"}<SettingsSmime />
    {:else if tab === "calendar"}<SettingsCalendar />
    {:else if tab === "sync"}<SettingsSync />
    {:else if tab === "rapldesk"}<SettingsRaplDesk />
    {:else if tab === "signature"}<SettingsSignature />
    {:else if tab === "snippets"}<SettingsSnippets />
    {:else if tab === "appearance"}<SettingsAppearance />
    {:else if tab === "ai"}<SettingsAi />
    {:else if tab === "shortcuts"}<SettingsShortcuts />
    {:else if tab === "utility"}<SettingsUtility />
    {:else if tab === "debug"}<SettingsDebug />
    {:else}<SettingsGeneral />{/if}
    <footer class="madeby">
      RaplMail <button class="ver" title={app.settings.debugUnlocked ? "" : t("settingsNav.debugHintTip")} onclick={tapVersion}>v{appVersion}</button> · {t("settingsNav.madeBy")} <a href="https://rapl-group.eu/" target="_blank" rel="noreferrer">RAPL Group</a>
    </footer>
  </div>
</section>

<style>
  .settings { display: flex; min-width: 0; overflow: hidden; }
  /* Vertical settings nav — 15 sections don't fit a horizontal tab strip. */
  .snav {
    flex: none; width: 220px; display: flex; flex-direction: column; gap: 10px;
    padding: 16px 12px; border-right: 1px solid var(--hairline); background: var(--surface);
    min-height: 0; overflow: hidden;
  }
  .back {
    flex: none; text-align: left; padding: 7px 10px; border-radius: 8px;
    color: var(--muted); font-size: 13px; font-weight: 550;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .back:hover { background: var(--hover); color: var(--text); }
  h1 { margin: 0 0 18px; font-size: 21px; font-weight: 700; letter-spacing: -0.02em; }
  .search { display: flex; align-items: center; gap: 6px; background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm); padding: 5px 10px; transition: border-color var(--t-fast) var(--ease); }
  .search:focus-within { border-color: var(--accent); }
  .search .s-ic { color: var(--muted); display: inline-flex; flex: none; }
  .search input { border: none; background: transparent; outline: none; box-shadow: none; width: 100%; min-width: 0; padding: 2px 0; }
  .search input:focus { box-shadow: none; }
  .no-match { color: var(--muted); font-size: 12.5px; padding: 9px 10px; display: block; }
  nav { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
  .nav-head { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--faint); padding: 10px 10px 4px; }
  .nav-head:first-child { padding-top: 2px; }
  /* Exact-setting result: setting name on top, its category underneath. */
  .result { display: flex; flex-direction: column; gap: 1px; padding: 7px 10px; border-radius: 8px; text-align: left; width: 100%;
    transition: background var(--t-fast) var(--ease); }
  .result:hover { background: var(--hover); }
  .r-label { font-size: 13px; font-weight: 550; color: var(--text); }
  .r-cat { font-size: 11px; color: var(--faint); }
  .result:hover .r-cat { color: var(--muted); }
  .tab {
    position: relative; display: flex; align-items: center; gap: 10px;
    padding: 8px 10px; border-radius: 8px; color: var(--muted); font-weight: 550;
    font-size: 13px; text-align: left; width: 100%;
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
  }
  .t-ic { display: grid; place-items: center; width: 18px; flex: none; }
  .t-ic :global(svg) { width: 16px; height: 16px; }
  .tab:hover { background: var(--hover); color: var(--text); }
  .tab.active { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .tab.active .t-ic { color: var(--accent); }
  .tab.active::before {
    content: ""; position: absolute; left: 0; top: 7px; bottom: 7px; width: 3px;
    border-radius: 999px; background: var(--accent);
  }
  .panel { flex: 1; overflow-y: auto; padding: 26px 30px; min-width: 0; }
  .madeby { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--hairline); text-align: center; color: var(--muted); font-size: 12px; }
  .madeby a { color: var(--accent); text-decoration: none; }
  .madeby a:hover { text-decoration: underline; }
  .madeby .ver { color: var(--text); font-variant-numeric: tabular-nums; font: inherit; cursor: pointer; padding: 0 2px; border-radius: 4px; -webkit-user-select: none; user-select: none; }
  .madeby .ver:hover { background: var(--hover); }
</style>
