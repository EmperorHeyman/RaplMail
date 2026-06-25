<script>
  import { app } from "../store.svelte.js";
  import SettingsAccounts from "./SettingsAccounts.svelte";
  import SettingsRules from "./SettingsRules.svelte";
  import SettingsSignature from "./SettingsSignature.svelte";
  import SettingsContacts from "./SettingsContacts.svelte";
  import SettingsGeneral from "./SettingsGeneral.svelte";
  import SettingsSnippets from "./SettingsSnippets.svelte";
  import SettingsAppearance from "./SettingsAppearance.svelte";
  import SettingsWorkspaces from "./SettingsWorkspaces.svelte";
  import SettingsShortcuts from "./SettingsShortcuts.svelte";
  import { icons } from "../icons.js";

  let tab = $state(app.settingsTab || "accounts");
  if (app.settingsTab) app.settingsTab = null;
  const tabs = [
    { id: "accounts", label: "Accounts", icon: icons.accounts, kw: "email imap smtp oauth microsoft m365 google gmail add account password connect sign in" },
    { id: "workspaces", label: "Workspaces", icon: icons.workspaces, kw: "workspace group accounts switch context" },
    { id: "contacts", label: "Address Book", icon: icons.contacts, kw: "address book contacts people favorites rescan" },
    { id: "rules", label: "Rules & Blocking", icon: icons.rules, kw: "rules blocking filter domain move archive delete block sender" },
    { id: "signature", label: "Signatures", icon: icons.signature, kw: "signature html image preview text footer" },
    { id: "snippets", label: "Snippets", icon: icons.bolt, kw: "snippets templates canned expander shortcut variables" },
    { id: "appearance", label: "Appearance", icon: icons.palette, kw: "theme color colour preset dark light css radius corner rounded avatar logo favicon relative time notifications email adapt customize layout font style vscode" },
    { id: "shortcuts", label: "Shortcuts", icon: icons.keyboard, kw: "keyboard shortcuts keybindings keys hotkeys palette" },
    { id: "general", label: "General", icon: icons.general, kw: "smart inbox notifications desktop snooze presence quick actions row buttons backup export import migrate auto-bcc bcc startup password follow-up screener threading bundles group placement" },
  ];

  let query = $state("");
  const filtered = $derived(
    query.trim()
      ? tabs.filter((t) => (t.label + " " + t.kw).toLowerCase().includes(query.trim().toLowerCase()))
      : tabs
  );
  // If the current tab is filtered out, jump to the first match.
  $effect(() => {
    if (filtered.length && !filtered.some((t) => t.id === tab)) tab = filtered[0].id;
  });
</script>

<section class="settings">
  <header>
    <button class="btn ghost back" onclick={() => (app.view = "mail")}>← Back to mail</button>
    <h1>Settings</h1>
    <div class="search"><span class="s-ic">{@html icons.search}</span>
      <input type="search" placeholder="Search settings…" bind:value={query} />
    </div>
  </header>
  <nav>
    {#each filtered as t}
      <button class="tab" class:active={tab === t.id} onclick={() => (tab = t.id)}>
        <span>{@html t.icon}</span> {t.label}
      </button>
    {/each}
    {#if filtered.length === 0}<span class="no-match">No settings match “{query}”</span>{/if}
  </nav>
  <div class="panel">
    {#if tab === "accounts"}<SettingsAccounts />
    {:else if tab === "workspaces"}<SettingsWorkspaces />
    {:else if tab === "contacts"}<SettingsContacts />
    {:else if tab === "rules"}<SettingsRules />
    {:else if tab === "signature"}<SettingsSignature />
    {:else if tab === "snippets"}<SettingsSnippets />
    {:else if tab === "appearance"}<SettingsAppearance />
    {:else if tab === "shortcuts"}<SettingsShortcuts />
    {:else}<SettingsGeneral />{/if}
  </div>
</section>

<style>
  .settings { display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
  header { display: flex; align-items: center; gap: 16px; padding: 18px 26px; border-bottom: 1px solid var(--border); }
  .back { flex: none; }
  h1 { margin: 0; font-size: 20px; }
  .search { margin-left: auto; display: flex; align-items: center; gap: 6px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 10px; }
  .search:focus-within { border-color: var(--accent); }
  .search .s-ic { color: var(--muted); display: inline-flex; }
  .search input { border: none; background: transparent; outline: none; width: 200px; }
  .no-match { color: var(--muted); font-size: 13px; padding: 9px 6px; }
  nav { display: flex; gap: 6px; padding: 12px 22px 0; border-bottom: 1px solid var(--border); }
  .tab { padding: 9px 14px; border-radius: var(--radius-sm) var(--radius-sm) 0 0; color: var(--muted); font-weight: 550; }
  .tab:hover { background: var(--surface); }
  .tab.active { color: var(--text); background: var(--surface-2); box-shadow: inset 0 -2px 0 var(--accent); }
  .panel { flex: 1; overflow-y: auto; padding: 26px; }
</style>
