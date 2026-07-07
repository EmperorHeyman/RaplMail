<script>
  import { app, notify, openCompose, saveSettings } from "../store.svelte.js";
  import { security, openExternal } from "../api.js";
  import { icons } from "../icons.js";
  import { t } from "../i18n.svelte.js";

  let report = $state(null);
  let loading = $state(false);
  let error = $state("");
  let openHeaders = $state(false);

  let _loadedId = null;
  $effect(() => {
    const id = app.lab?.id ?? null;
    if (id == null) { report = null; error = ""; _loadedId = null; return; }
    if (id === _loadedId) return;
    _loadedId = id;
    run(id);
  });
  async function run(id) {
    loading = true; error = ""; report = null;
    try { report = await security.analyze(id); }
    catch (e) { error = e.message || String(e); }
    finally { loading = false; }
  }
  function clear() { app.lab = null; report = null; error = ""; _loadedId = null; }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify(t("security.labCopied")); }
    catch { notify(t("reader.couldntCopy"), "error"); }
  }

  // Defang so a report can be pasted into a ticket without live links.
  const defang = (s) => (s || "").replace(/https?/gi, (m) => m.replace(/t/gi, "x"))
    .replace(/\./g, "[.]").replace(/@/g, "[@]");
  function defangedReport() {
    if (!report) return "";
    const r = report, L = [];
    L.push(`Subject: ${r.subject}`);
    L.push(`From: ${defang(r.from.addr)} (${defang(r.from.domain)})`);
    if (r.reply_to) L.push(`Reply-To: ${defang(r.reply_to)}`);
    L.push(`Auth: ${r.auth.detail || r.auth.status}`);
    if (r.domain_age?.age_days != null) L.push(`Domain age: ${r.domain_age.age_days} days (${r.domain_age.created})`);
    if (r.originating_ip) L.push(`Origin IP: ${defang(r.originating_ip)}  ${r.origin_intel?.asn || ""} ${r.origin_intel?.country || ""}${r.origin_intel?.dnsbl?.length ? "  DNSBL: " + r.origin_intel.dnsbl.join(",") : ""}`);
    if (r.heuristics?.length) L.push("Findings:\n  - " + r.heuristics.map(defang).join("\n  - "));
    if (r.links?.length) L.push("Links:\n  - " + r.links.map((l) => defang(l.url)).join("\n  - "));
    if (r.attachments?.length) L.push("Attachments:\n  - " + r.attachments.map((a) => `${a.filename} sha256=${a.sha256}${a.flags?.length ? " [" + a.flags.join("; ") + "]" : ""}`).join("\n  - "));
    return L.join("\n");
  }
  function blockDomain() {
    const d = report?.from?.reg_domain; if (!d) return;
    const cur = Array.isArray(app.settings.blockedDomains) ? app.settings.blockedDomains : [];
    if (!cur.includes(d)) saveSettings({ blockedDomains: [...cur, d] });
    notify(t("security.labBlocked", { domain: d }));
  }
  function reportAbuse() {
    const d = report?.from?.reg_domain; if (!d) return;
    openCompose({ to: `abuse@${d}`, subject: `Reported: ${report.subject || ""}`,
      html: `<pre>${defangedReport().replace(/</g, "&lt;")}</pre>` });
  }

  // External-tool deep links.
  const enc = encodeURIComponent;
  const vtDomain = (d) => `https://www.virustotal.com/gui/domain/${enc(d)}`;
  const vtIp = (ip) => `https://www.virustotal.com/gui/ip-address/${enc(ip)}`;
  const vtUrl = (u) => `https://www.virustotal.com/gui/search/${enc(u)}`;
  const vtFile = (h) => `https://www.virustotal.com/gui/file/${enc(h)}`;
  const urlscan = (q) => `https://urlscan.io/search/#${enc(q)}`;
  const mxtoolbox = (d) => `https://mxtoolbox.com/SuperTool.aspx?action=mx%3a${enc(d)}&run=toolpage`;
  const mxBlacklist = (ip) => `https://mxtoolbox.com/SuperTool.aspx?action=blacklist%3a${enc(ip)}&run=toolpage`;
  const abuseipdb = (ip) => `https://www.abuseipdb.com/check/${enc(ip)}`;
  const whois = (d) => `https://www.whois.com/whois/${enc(d)}`;
  const safeBrowsing = (u) => `https://transparencyreport.google.com/safe-browsing/search?url=${enc(u)}`;
  const talos = (q) => `https://talosintelligence.com/reputation_center/lookup?search=${enc(q)}`;
  const urlhaus = (q) => `https://urlhaus.abuse.ch/browse.php?search=${enc(q)}`;
  const hybrid = (q) => `https://www.hybrid-analysis.com/search?query=${enc(q)}`;
  const shodan = (ip) => `https://www.shodan.io/host/${enc(ip)}`;

  const dom = $derived(report?.from?.reg_domain || report?.from?.domain || "");
  const origin = $derived(report?.originating_ip || "");
  const oi = $derived(report?.origin_intel || {});
  const age = $derived(report?.domain_age || {});
  const align = $derived(report?.auth_alignment || {});
  const tl = $derived(report?.timeline || {});
</script>

<section class="lab">
  <div class="lab-head">
    <h3>{@html icons.shieldCheck} {t("security.labTitle")}</h3>
    {#if app.lab}
      <div class="lh-actions">
        <button class="mini" onclick={() => run(app.lab.id)} disabled={loading}>{@html icons.reset} {t("security.labRecheck")}</button>
        <button class="mini" onclick={clear}>{@html icons.close} {t("security.labClear")}</button>
      </div>
    {/if}
  </div>

  {#if !app.lab}
    <p class="empty">{t("security.labEmpty")}</p>
  {:else if loading}
    <p class="empty">{t("security.labLoading")}</p>
  {:else if error}
    <p class="empty err">{t("security.labError", { err: error })}</p>
  {:else if report}
    <div class="subj">{report.subject || "(no subject)"}</div>

    <!-- Report actions -->
    <div class="ractions">
      <button class="mini" onclick={() => copy(defangedReport())}>{@html icons.copy} {t("security.labCopyDefanged")}</button>
      <button class="mini" onclick={() => copy(JSON.stringify(report, null, 2))}>{@html icons.save || icons.download} {t("security.labExportJson")}</button>
      {#if dom}
        <button class="mini danger" onclick={blockDomain}>{@html icons.junk || icons.shieldAlert} {t("security.labBlockDomain", { domain: dom })}</button>
        <button class="mini" onclick={reportAbuse}>{@html icons.mail} {t("security.labReportAbuse", { domain: dom })}</button>
      {/if}
    </div>

    <!-- Findings -->
    {#if report.heuristics.length || report.reply_to_mismatch || oi.dnsbl?.length || (age.age_days != null && age.age_days < 30) || tl.backdated}
      <div class="findings bad">
        {#each report.heuristics as w}<div class="f">{@html icons.shieldAlert} {w}</div>{/each}
        {#if report.reply_to_mismatch}<div class="f">{@html icons.shieldAlert} {t("security.labReplyMismatch")}</div>{/if}
        {#if age.age_days != null && age.age_days < 30}<div class="f">{@html icons.shieldAlert} {t("security.labDomainAge")}: {age.age_days}d — {t("security.labVeryYoung")}</div>{/if}
        {#if oi.dnsbl?.length}<div class="f">{@html icons.shieldAlert} {t("security.labDnsblListed", { list: oi.dnsbl.join(", ") })}</div>{/if}
        {#if tl.backdated}<div class="f">{@html icons.shieldAlert} {t("security.labBackdated", { mins: Math.round((tl.skew_seconds || 0) / 60) })}</div>{/if}
      </div>
    {:else}
      <div class="findings ok">{@html icons.shieldCheck} {t("security.labNoFindings")}</div>
    {/if}

    <!-- External tools -->
    <div class="block">
      <div class="b-title">{t("security.labExternal")}</div>
      <div class="tools">
        {#if dom}
          <button onclick={() => openExternal(vtDomain(dom))}>{@html icons.shield} {t("security.labVtDomain")}</button>
          <button onclick={() => openExternal(mxtoolbox(dom))}>{@html icons.mail} {t("security.labMxtoolbox")}</button>
          <button onclick={() => openExternal(whois(dom))}>{@html icons.search} {t("security.labWhois")}</button>
          <button onclick={() => openExternal(urlscan(dom))}>{@html icons.search} {t("security.labUrlscan")}</button>
          <button onclick={() => openExternal(talos(dom))}>{@html icons.shield} {t("security.labTalos")}</button>
          <button onclick={() => openExternal(urlhaus(dom))}>{@html icons.shieldAlert} {t("security.labUrlhaus")}</button>
          <button onclick={() => openExternal(hybrid(dom))}>{@html icons.shield} {t("security.labHybrid")}</button>
        {/if}
        {#if origin}
          <button onclick={() => openExternal(vtIp(origin))}>{@html icons.shield} {t("security.labVtIp")}</button>
          <button onclick={() => openExternal(abuseipdb(origin))}>{@html icons.shieldAlert} {t("security.labAbuse")}</button>
          <button onclick={() => openExternal(mxBlacklist(origin))}>{@html icons.shield} {t("security.labBlacklist")}</button>
          <button onclick={() => openExternal(shodan(origin))}>{@html icons.search} {t("security.labShodan")}</button>
        {/if}
      </div>
    </div>

    <!-- Sender / auth / domain age -->
    <div class="block">
      <div class="b-title">{t("security.labSender")}</div>
      <dl class="kv">
        {#if report.from.name}<dt>{t("security.labFromName")}</dt><dd>{report.from.name}</dd>{/if}
        <dt>{t("security.labFromAddr")}</dt><dd class="mono">{report.from.addr}</dd>
        <dt>{t("security.labDomain")}</dt><dd class="mono">{report.from.domain}</dd>
        {#if report.reply_to}<dt>{t("security.labReplyTo")}</dt><dd class="mono" class:warn={report.reply_to_mismatch}>{report.reply_to}</dd>{/if}
        {#if report.return_path}<dt>{t("security.labReturnPath")}</dt><dd class="mono">{report.return_path}</dd>{/if}
        <dt>{t("security.labDomainAge")}</dt>
        <dd class:warn={age.age_days != null && age.age_days < 30}>
          {#if age.age_days != null}{t("security.labRegistered", { date: age.created, days: age.age_days })}{:else}{t("security.labAgeUnknown")}{/if}
        </dd>
        <dt>SPF / DKIM / DMARC</dt>
        <dd><span class="auth {report.auth.status}">{report.auth.detail || report.auth.status}</span></dd>
        {#if report.date}<dt>{t("security.labDate")}</dt><dd class="mono">{report.date}</dd>{/if}
        {#if report.rfc_message_id}<dt>{t("security.labRfcId")}</dt><dd class="mono small">{report.rfc_message_id}</dd>{/if}
      </dl>
    </div>

    <!-- DMARC alignment -->
    {#if align.dkim_domain || align.return_path_domain}
      <div class="block">
        <div class="b-title">{t("security.labAlignment")}</div>
        <dl class="kv">
          {#if align.dkim_domain}
            <dt>{t("security.labDkimD")}</dt>
            <dd class="mono">{align.dkim_domain}{#if align.dkim_selector} ({align.dkim_selector}){/if}
              <span class="tag {align.dkim_aligned ? 'ok' : 'bad'}">{align.dkim_aligned ? t("security.labAligned") : t("security.labMisaligned")}</span></dd>
          {/if}
          {#if align.return_path_domain}
            <dt>{t("security.labReturnPathA")}</dt>
            <dd class="mono">{align.return_path_domain}
              <span class="tag {align.return_path_aligned ? 'ok' : 'bad'}">{align.return_path_aligned ? t("security.labAligned") : t("security.labMisaligned")}</span></dd>
          {/if}
        </dl>
      </div>
    {/if}

    <!-- Origin IP intel -->
    {#if origin}
      <div class="block">
        <div class="b-title">{t("security.labOrigin")}: <code>{origin}</code></div>
        <dl class="kv">
          {#if oi.ptr}<dt>{t("security.labPtr")}</dt><dd class="mono">{oi.ptr}</dd>{/if}
          {#if oi.asn || oi.org}<dt>{t("security.labAsn")}</dt><dd>{oi.asn} {oi.org}</dd>{/if}
          {#if oi.country}<dt>{t("security.labGeo")}</dt><dd>{oi.city ? oi.city + ", " : ""}{oi.country}</dd>{/if}
          <dt>{t("security.labDnsbl")}</dt>
          <dd class:warn={oi.dnsbl?.length}>{oi.dnsbl?.length ? t("security.labDnsblListed", { list: oi.dnsbl.join(", ") }) : t("security.labDnsblClean")}</dd>
        </dl>
      </div>
    {/if}

    <!-- Timeline -->
    {#if tl.date}
      <div class="block">
        <div class="b-title">{t("security.labTimeline")}</div>
        <dl class="kv">
          <dt>{t("security.labSent")}</dt><dd class="mono">{tl.date}</dd>
          {#if tl.received}<dt>{t("security.labReceivedAt")}</dt><dd class="mono" class:warn={tl.backdated}>{tl.received}</dd>{/if}
        </dl>
      </div>
    {/if}

    <!-- Hops -->
    {#if report.hops.length}
      <div class="block">
        <div class="b-title">{t("security.labHops")}</div>
        <ol class="hops">
          {#each report.hops as h}
            <li>
              {#if h.from}<span class="mono">{t("security.labHopFrom")} {h.from}</span>{/if}
              {#if h.by}<span class="mono dim">{t("security.labHopBy")} {h.by}</span>{/if}
              {#if h.ip}<button class="ipbtn mono" title={t("security.labAbuse")} onclick={() => openExternal(abuseipdb(h.ip))}>{h.ip}</button>{/if}
              {#if h.ts}<span class="ts">{h.ts}</span>{/if}
            </li>
          {/each}
        </ol>
      </div>
    {/if}

    <!-- Links -->
    {#if report.links.length}
      <div class="block">
        <div class="b-title">{t("security.labLinks", { n: report.links.length })}</div>
        <ul class="rows">
          {#each report.links as l}
            <li>
              <span class="mono url" title={l.url}>{l.url}</span>
              {#if l.punycode}<span class="tag bad">{t("security.labPunycode")}</span>{/if}
              {#if l.final_url}<span class="final mono">{t("security.labFinalUrl")} {l.final_url}</span>{/if}
              <span class="rowtools">
                <button class="mini" onclick={() => openExternal(vtUrl(l.url))} title="VirusTotal">{@html icons.shield}</button>
                <button class="mini" onclick={() => openExternal(safeBrowsing(l.url))} title={t("security.labSafeBrowsing")}>{@html icons.shieldCheck}</button>
                <button class="mini" onclick={() => copy(l.url)} title={t("security.labCopy")}>{@html icons.copy}</button>
              </span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Attachments -->
    {#if report.attachments.length}
      <div class="block">
        <div class="b-title">{t("security.labAttachments", { n: report.attachments.length })}</div>
        <ul class="rows">
          {#each report.attachments as a}
            <li class="att-row">
              <span class="att"><b>{a.filename}</b> <span class="dim">{a.content_type} · {a.size} B{#if a.magic} · {t("security.labMagic")}: {a.magic}{/if}</span></span>
              {#if a.flags?.length}<span class="flags">{#each a.flags as f}<span class="tag bad">{f}</span>{/each}</span>{/if}
              {#if a.contents?.length}<span class="arch">{t("security.labArchive")}: <span class="mono">{a.contents.join(", ")}</span></span>{/if}
              {#if a.sha256}
                <span class="mono hash" title={a.sha256}>sha256 {a.sha256}</span>
                <span class="rowtools">
                  <button class="mini" onclick={() => openExternal(vtFile(a.sha256))} title="VirusTotal">{@html icons.shield}</button>
                  <button class="mini" onclick={() => openExternal(hybrid(a.sha256))} title={t("security.labHybrid")}>{@html icons.search}</button>
                  <button class="mini" onclick={() => copy(a.sha256)} title="sha256">{@html icons.copy}</button>
                  {#if a.md5}<button class="mini" onclick={() => copy(a.md5)} title="md5">md5</button>{/if}
                  {#if a.sha1}<button class="mini" onclick={() => copy(a.sha1)} title="sha1">sha1</button>{/if}
                </span>
              {/if}
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Raw headers -->
    <div class="block">
      <button class="b-title toggle" onclick={() => (openHeaders = !openHeaders)}>
        <span class="caret" class:open={openHeaders}>▸</span> {t("security.labHeaders")} ({report.headers.length})
      </button>
      {#if openHeaders}
        <pre class="headers">{#each report.headers as h}<span class="hn">{h.name}:</span> {h.value}
{/each}</pre>
      {/if}
    </div>
  {/if}
</section>

<style>
  .lab { padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; gap: 14px; }
  .lab-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .lab-head h3 { margin: 0; display: flex; align-items: center; gap: 7px; }
  .lab-head h3 :global(svg) { width: 17px; height: 17px; color: var(--accent); }
  .lh-actions { display: flex; gap: 6px; }
  .empty { color: var(--muted); font-size: 13px; margin: 0; line-height: 1.6; }
  .empty.err { color: var(--danger); }
  .subj { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; word-break: break-word; }
  .ractions { display: flex; flex-wrap: wrap; gap: 7px; }

  .findings { display: flex; flex-direction: column; gap: 6px; padding: 11px 13px; border-radius: var(--radius-sm); font-size: 12.5px; line-height: 1.5; }
  .findings.bad { background: var(--danger-soft); color: var(--danger); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); }
  .findings.ok { background: var(--done-soft); color: var(--done); border: 1px solid color-mix(in srgb, var(--done) 28%, transparent); }
  .findings .f { display: flex; align-items: flex-start; gap: 7px; }
  .findings :global(svg) { width: 14px; height: 14px; flex: none; margin-top: 1px; }

  .block { border-top: 1px solid var(--hairline); padding-top: 12px; }
  .b-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
  .b-title code { color: var(--danger); text-transform: none; letter-spacing: 0; }
  .b-title.toggle { cursor: pointer; background: none; border: none; padding: 0; }
  .caret { transition: transform var(--t-fast) var(--ease); display: inline-block; }
  .caret.open { transform: rotate(90deg); }

  .tools { display: flex; flex-wrap: wrap; gap: 7px; }
  .tools button, .mini { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600;
    padding: 5px 10px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); }
  .tools button:hover, .mini:hover { border-color: var(--accent); color: var(--accent); }
  .mini.danger:hover { border-color: var(--danger); color: var(--danger); }
  .tools button :global(svg), .mini :global(svg) { width: 13px; height: 13px; }

  .kv { display: grid; grid-template-columns: minmax(120px, auto) 1fr; gap: 4px 14px; margin: 0; font-size: 12.5px; }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; word-break: break-word; }
  .mono { font-family: ui-monospace, monospace; }
  .mono.small { font-size: 11px; color: var(--faint); }
  .kv dd.warn, .warn { color: var(--warning); }
  .auth { font-family: ui-monospace, monospace; font-size: 11.5px; padding: 1px 7px; border-radius: 5px; }
  .auth.pass { background: var(--done-soft); color: var(--done); }
  .auth.fail { background: var(--danger-soft); color: var(--danger); }
  .auth.none { background: var(--surface-2); color: var(--muted); }
  .tag { font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 999px; margin-left: 6px; }
  .tag.ok { background: var(--done-soft); color: var(--done); }
  .tag.bad { background: var(--danger-soft); color: var(--danger); }

  .hops { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
  .hops li { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .dim { color: var(--faint); }
  .hops .ts { color: var(--faint); font-size: 11px; }
  .ipbtn { font-size: 12px; color: var(--accent); text-decoration: underline; }
  .ipbtn:hover { color: var(--danger); }

  .rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .rows li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; padding: 6px 8px; background: var(--surface-2); border-radius: var(--radius-sm); }
  .url { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .final { flex-basis: 100%; color: var(--warning); font-size: 11px; word-break: break-all; }
  .rowtools { display: flex; gap: 5px; flex: none; margin-left: auto; }
  .mini { padding: 3px 7px; }
  .att-row { flex-wrap: wrap; }
  .att { flex: 1; min-width: 160px; }
  .flags { display: flex; flex-wrap: wrap; gap: 4px; flex-basis: 100%; }
  .flags .tag { margin-left: 0; }
  .arch { flex-basis: 100%; font-size: 11px; color: var(--faint); }
  .hash { flex-basis: 100%; font-size: 11px; color: var(--faint); word-break: break-all; }

  .headers { margin: 0; padding: 12px; background: var(--surface-2); border: 1px solid var(--hairline); border-radius: var(--radius-sm);
    font-size: 11.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-height: 340px; overflow-y: auto; }
  .headers .hn { color: var(--accent); font-weight: 600; }
</style>
