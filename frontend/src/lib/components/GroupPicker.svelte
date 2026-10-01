<script>
  // Picks the Smart Inbox group a "Put in group" rule files mail into: a
  // built-in category or a custom group, with "New group…" creating one inline
  // (so a rule for your HR system doesn't need a detour through Settings).
  import { tick } from "svelte";
  import { createCustomGroup } from "../store.svelte.js";
  import { smartGroupList } from "../groups.js";
  import { t } from "../i18n.svelte.js";

  let { value = $bindable("") } = $props();

  const groups = $derived(smartGroupList());
  const custom = $derived(groups.filter((g) => g.custom));
  const builtin = $derived(groups.filter((g) => !g.custom));
  const known = $derived(groups.some((g) => g.id === value));

  let naming = $state(false);
  let name = $state("");
  let input = $state();

  async function onPick(e) {
    const v = e.currentTarget.value;
    if (v === "__new__") {
      e.currentTarget.value = known ? value : "";
      naming = true;
      await tick();
      input?.focus();
      return;
    }
    value = v;
  }
  // Enter, the check button and blur all commit - blur so that clicking
  // "Save rule" straight from the name box still files into the new group.
  function commit() {
    if (!naming) return;
    const n = name.trim();
    naming = false;
    name = "";
    if (n) value = createCustomGroup(n);
  }
  function cancel() { naming = false; name = ""; }
</script>

{#if naming}
  <span class="new">
    <input bind:this={input} bind:value={name} placeholder={t("groups.namePlaceholder")}
      onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } else if (e.key === "Escape") { e.stopPropagation(); cancel(); } }}
      onblur={commit} />
  </span>
{:else}
  <select value={known ? value : ""} onchange={onPick}>
    {#if !known}<option value="" disabled>{t("groups.choose")}</option>{/if}
    {#if custom.length}
      <optgroup label={t("groups.yourGroups")}>
        {#each custom as g (g.id)}<option value={g.id}>{g.label}</option>{/each}
      </optgroup>
    {/if}
    <optgroup label={t("groups.builtIn")}>
      {#each builtin as g (g.id)}<option value={g.id}>{g.label}</option>{/each}
    </optgroup>
    <option value="__new__">{t("groups.newOption")}</option>
  </select>
{/if}

<style>
  .new { display: inline-flex; flex: 1; min-width: 160px; }
  .new input { flex: 1; }
</style>
