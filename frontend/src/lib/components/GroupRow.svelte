<script>
  import { app, accountFor } from "../store.svelte.js";
  import { listTime, relativeTime } from "../time.svelte.js";
  import { icons } from "../icons.js";
  import { avatarUrl } from "../api.js";
  let { gtype, msgs = [], latest = null, focused = false, expanded = false, checked = false,
        label = "", count = 0, icon = icons.folder, onactivate, ondoneall, onselect } = $props();

  const msgCount = $derived(msgs.length);
  const anyUnread = $derived(msgs.some((m) => !m.is_seen && !m.is_done));
  const initial = $derived(latest ? ((latest.from_name || latest.from_addr || "?").trim()[0]?.toUpperCase() || "?") : "?");
  const acctColor = $derived(latest ? (accountFor(latest.account_id)?.color || null) : null);
  const multiAcct = $derived(app.accounts.length > 1);
  let imgFailed = $state(false);
  const avSrc = $derived(latest && app.settings.senderAvatars !== false ? avatarUrl(latest.from_addr) : "");
  // Reset only when the sender actually changes (avoids re-flashing on refresh).
  let _gKey = "";
  $effect(() => {
    const k = latest?.from_addr || "";
    if (k !== _gKey) { _gKey = k; imgFailed = false; }
  });
  const hasLogo = $derived(!!avSrc && !imgFailed && !checked);

  const fmtTime = (iso) => (app.settings.relativeTime ? relativeTime(iso) : listTime(iso));
</script>

{#if gtype === "category"}
  <div class="wrap">
    <div class="row catrow" role="button" tabindex="-1" class:focused onclick={onactivate}>
      <span class="cat-ic">{@html icon}</span>
      <span class="cat-label">{label}</span>
      <span class="chip">{expanded ? "▾" : "▸"} {count.toLocaleString()}</span>
    </div>
  </div>
{:else}
<div class="wrap">
  {#if multiAcct && acctColor}<span class="acct-stripe" style="background:{acctColor}"></span>{/if}
  <div class="row" role="button" tabindex="-1" class:focused class:unread={anyUnread} onclick={onactivate}>
    <button class="avatar" class:checked class:haslogo={hasLogo}
      style={acctColor ? `border-color:${acctColor}` : ""}
      title="Select all" onclick={(e) => { e.stopPropagation(); onselect?.(); }}>
      {#if checked}{@html icons.done}
      {:else if hasLogo}<img class="logo-img" src={avSrc} alt="" onerror={() => (imgFailed = true)} />
      {:else}{initial}{/if}
    </button>
    <span class="body">
      <span class="line1">
        <span class="from">{latest.from_name || latest.from_addr}</span>
        <span class="time">{fmtTime(latest.date)}</span>
      </span>
      <span class="subject">{latest.subject || "(no subject)"}</span>
      <span class="snippet">{@html gtype === "thread" ? icons.chat : icons.folder} {gtype === "thread" ? "conversation" : "bundle"} · {latest.snippet}</span>
    </span>
    <span class="chip">{gtype === "bundle" ? (expanded ? "▾" : "▸") : ""} {msgCount}</span>
    <button class="done-all" title={gtype === "thread" ? "Archive whole conversation" : "Done all"}
      onclick={(e) => { e.stopPropagation(); ondoneall?.(); }}>{@html icons.done}</button>
  </div>
</div>
{/if}

<style>
  .wrap { position: relative; margin: 1px 6px; border-radius: var(--radius); overflow: hidden; }
  /* Which account it came to (several accounts): a short mark at the row's
     edge, beside the avatar - not a full-height line. */
  .acct-stripe { position: absolute; left: 4px; top: 50%; height: 22px; margin-top: -11px; width: 4px; border-radius: 2px; z-index: 3; }
  .row { display: flex; gap: var(--row-gap, 14px); align-items: flex-start; padding: var(--row-pad-y, 12px) 12px var(--row-pad-y, 12px) 14px; border-radius: inherit;
    background: transparent; cursor: pointer; transition: background var(--t-fast) var(--ease); }
  .row:hover { background: var(--hover); }
  .row.focused { box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--accent) 70%, transparent); }
  .row.unread .from, .row.unread .subject { font-weight: 700; }
  .avatar { flex: none; box-sizing: border-box; width: var(--row-av, 40px); height: var(--row-av, 40px); border-radius: 50%; display: grid; place-items: center;
    font-weight: 500; font-size: calc(var(--row-av, 40px) * 0.42); line-height: 1;
    background: var(--accent-cont); color: var(--on-accent-cont); cursor: pointer; border: 2px solid transparent; }
  .avatar :global(svg) { width: 22px; height: 22px; }
  .avatar.haslogo { background: #fff; }
  .avatar .logo-img { width: 24px; height: 24px; object-fit: contain; border-radius: 5px; }
  .avatar.checked { background: var(--accent); color: var(--on-accent); }
  .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .line1 { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .from { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; line-height: 21px; }
  .time { flex: none; color: var(--muted); font-size: 12px; }
  .subject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; line-height: 20px; }
  .snippet { color: var(--muted); font-size: 13.5px; line-height: 19px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .snippet :global(svg) { width: 14px; height: 14px; }
  .chip { flex: none; align-self: center; font-size: 12px; font-weight: 600; color: var(--on-sel); background: var(--sel); padding: 3px 10px; border-radius: 8px; }
  .done-all { flex: none; align-self: center; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface-2); color: var(--muted); opacity: 0; transition: opacity 0.12s, background var(--t-fast) var(--ease); }
  .done-all :global(svg) { width: 20px; height: 20px; }
  .row:hover .done-all, .row.focused .done-all { opacity: 1; }
  .done-all:hover { background: var(--done); color: var(--on-done); }
  .catrow { align-items: center; cursor: pointer; }
  .cat-ic { width: 24px; display: grid; place-items: center; }
  .cat-ic :global(svg) { width: 20px; height: 20px; }
  .cat-label { flex: 1; font-weight: 500; font-size: 14px; color: var(--muted); }
</style>
