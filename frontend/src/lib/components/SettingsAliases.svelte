<script>
  import { onMount } from "svelte";
  import { app, notify, loadAccountsAndFolders } from "../store.svelte.js";
  import { messages as msgApi, rules as rulesApi } from "../api.js";
  import { relativeTime } from "../time.js";

  let rows = $state([]);
  let loading = $state(true);

  // --- generator -----------------------------------------------------------
  let genAccount = $state(null);
  let genTag = $state("");
  const generated = $derived.by(() => {
    const a = app.accounts.find((x) => x.id === genAccount) || app.accounts[0];
    if (!a || !a.email.includes("@")) return "";
    const tag = genTag.trim().replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
    if (!tag) return "";
    const [lp, dom] = a.email.split("@");
    return `${lp}+${tag}@${dom}`;
  });

  async function load() {
    loading = true;
    try { rows = await msgApi.plusAliases(); } catch (e) { notify(e.message, "error"); }
    finally { loading = false; }
  }
  onMount(() => { if (app.accounts.length === 0) loadAccountsAndFolders(); genAccount = app.accounts[0]?.id ?? null; load(); });

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify("Copied " + text); }
    catch { notify("Couldn't copy", "error"); }
  }

  // Mute an alias: a rule that archives anything addressed to it.
  async function muteAlias(r) {
    if (!confirm(`Archive all future mail sent to ${r.alias}?`)) return;
    try {
      await rulesApi.create({
        account_id: r.account_id, name: `Mute alias ${r.tag}`,
        match_field: "to", match_op: "contains", match_value: r.alias,
        action: "archive", action_arg: "", enabled: true,
      });
      notify(`Muted ${r.alias} — new mail to it will be archived`);
    } catch (e) { notify(e.message, "error"); }
  }
</script>

<div class="wrap">
  <section>
    <h3>Generate a tracking alias</h3>
    <p class="lead">Hand a unique <code>you+service@domain</code> address to each site. Mail still lands in your inbox,
      but you can see exactly who you gave it to — and if it ever shows up elsewhere, you know who leaked it. Works on
      Gmail, Outlook/M365, Fastmail and most modern servers.</p>
    <div class="gen">
      {#if app.accounts.length > 1}
        <select bind:value={genAccount}>
          {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
        </select>
      {/if}
      <span class="plus">+</span>
      <input bind:value={genTag} placeholder="service name, e.g. netflix" />
      <code class="result">{generated || "…"}</code>
      <button class="btn primary" disabled={!generated} onclick={() => copy(generated)}>Copy</button>
    </div>
  </section>

  <section>
    <div class="head">
      <h3>Aliases in use {#if rows.length}<span class="n">{rows.length}</span>{/if}</h3>
      <button class="btn ghost" onclick={load} disabled={loading}>{loading ? "Scanning…" : "↻ Rescan"}</button>
    </div>
    {#if loading}
      <p class="muted">Scanning your mail for sub-addresses…</p>
    {:else if rows.length === 0}
      <p class="muted">No tracking aliases detected yet. Generate one above and start using it when you sign up for things.</p>
    {:else}
      <div class="list">
        {#each rows as r}
          <div class="alias">
            <div class="atop">
              <code class="aname" title={r.alias}>{r.alias}</code>
              <span class="badge" class:warn={r.distinct_senders > 1}>
                {r.distinct_senders} {r.distinct_senders === 1 ? "sender" : "senders"}
              </span>
              <span class="cnt">{r.count.toLocaleString()} msgs</span>
              {#if r.last_seen}<span class="cnt">· {relativeTime(r.last_seen)}</span>{/if}
              <button class="btn ghost copy" title="Copy" onclick={() => copy(r.alias)}>Copy</button>
              <button class="btn ghost" title="Archive future mail to this alias" onclick={() => muteAlias(r)}>Mute</button>
            </div>
            <div class="senders">
              {#each r.senders as s}
                <span class="schip" title={s.email}>{s.name}{#if s.count > 1}<b> ×{s.count}</b>{/if}</span>
              {/each}
              {#if r.distinct_senders > r.senders.length}<span class="more">+{r.distinct_senders - r.senders.length}</span>{/if}
            </div>
            {#if r.distinct_senders > 1}
              <div class="leak">⚠ More than one sender uses this alias — it may have been shared or leaked.</div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .wrap { max-width: 760px; display: flex; flex-direction: column; gap: 28px; }
  h3 { margin: 0 0 6px; }
  .lead { color: var(--muted); margin: 0 0 14px; font-size: 13px; line-height: 1.5; }
  code { background: var(--surface-3); padding: 1px 6px; border-radius: 4px; font-size: 12px; }
  .gen { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .gen .plus { color: var(--muted); font-weight: 700; }
  .gen input { min-width: 160px; }
  .result { flex: 1; min-width: 200px; font-size: 13px; color: var(--accent); }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .n { color: var(--accent); font-size: 13px; margin-left: 4px; }
  .muted { color: var(--muted); }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .alias { padding: 12px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .atop { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .aname { font-size: 13px; font-weight: 600; color: var(--text); }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--surface-3); color: var(--muted); }
  .badge.warn { background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); }
  .cnt { font-size: 12px; color: var(--faint); }
  .atop .btn { margin-left: 0; padding: 3px 10px; font-size: 12px; }
  .atop .copy { margin-left: auto; }
  .senders { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .schip { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
  .more { font-size: 11px; color: var(--faint); align-self: center; }
  .leak { margin-top: 8px; font-size: 12px; color: var(--danger); }
</style>
