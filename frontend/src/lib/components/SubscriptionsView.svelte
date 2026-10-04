<script>
  // Tools → Subscriptions: the subscription audit as a page of its own. It used
  // to be the only thing in a Settings tab called "Utility", where nobody went
  // looking for a tool.
  import SettingsUtility from "./SettingsUtility.svelte";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";
</script>

<section class="subs">
  <header><h2>{@html icons.mute} {t("utility.subscriptionsTitle")}</h2></header>
  <div class="body stagger-in">
    <SettingsUtility showTitle={false} />
  </div>
</section>

<style>
  .subs { display: flex; flex-direction: column; min-width: 0; background: var(--bg); grid-column: 2 / -1;
    border-radius: var(--radius-lg); overflow: hidden; }
  header { display: flex; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--hairline); }
  h2 { margin: 0; font-size: 18px; display: flex; align-items: center; gap: 8px; }
  .body { padding: 20px 24px; overflow-y: auto; }
</style>
