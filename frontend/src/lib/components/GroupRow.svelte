<script>
  import { app } from "../store.svelte.js";
  import { listTime, relativeTime } from "../time.js";
  import { icons } from "../icons.js";
  import { avatarUrl } from "../api.js";
  let { gtype, msgs = [], latest = null, focused = false, expanded = false, checked = false,
        label = "", count = 0, icon = icons.folder, onactivate, ondoneall, onselect } = $props();

  const msgCount = $derived(msgs.length);
  const anyUnread = $derived(msgs.some((m) => !m.is_seen && !m.is_done));
  const initial = $derived(latest ? ((latest.from_name || latest.from_addr || "?").trim()[0]?.toUpperCase() || "?") : "?");
  const acctColor = $derived(latest ? (app.accounts.find((a) => a.id === latest.account_id)?.color || null) : null);
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
      {:else if hasLogo}<img class="logo-img" src={avSrc} alt="" loading="lazy" onerror={() => (imgFailed = true)} />
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
  .wrap { position: relative; }
  .acct-stripe { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; z-index: 3; }
  .row { display: flex; gap: 11px; align-items: flex-start; padding: 11px 14px; border-bottom: 1px solid var(--border); background: var(--bg); cursor: pointer; }
  .row:hover { background: var(--surface); }
  .row.focused { box-shadow: inset 3px 0 0 var(--accent); }
  .row.unread .from, .row.unread .subject { font-weight: 700; }
  .avatar { flex: none; box-sizing: border-box; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 14px; line-height: 1; background: linear-gradient(135deg, var(--accent), #8a6df0); color: #fff; cursor: pointer; border: 2px solid transparent; }
  .avatar.haslogo { background: #fff; }
  .avatar .logo-img { width: 22px; height: 22px; object-fit: contain; border-radius: 4px; }
  .avatar.checked { background: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
  .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .line1 { display: flex; justify-content: space-between; gap: 8px; }
  .from { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .time { flex: none; color: var(--faint); font-size: 12px; }
  .subject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .snippet { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip { flex: none; align-self: center; font-size: 12px; font-weight: 700; color: var(--accent); background: var(--surface-2); padding: 2px 9px; border-radius: 999px; }
  .done-all { flex: none; align-self: center; width: 30px; height: 30px; border-radius: 50%; border: 1.5px solid var(--border); color: var(--muted); opacity: 0; transition: opacity 0.12s; }
  .row:hover .done-all, .row.focused .done-all { opacity: 1; }
  .done-all:hover { background: var(--done); border-color: var(--done); color: #06231a; }
  .catrow { align-items: center; cursor: pointer; }
  .cat-ic { font-size: 16px; width: 22px; text-align: center; }
  .cat-label { flex: 1; font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
</style>
