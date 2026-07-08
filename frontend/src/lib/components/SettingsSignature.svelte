<script>
  import { onMount } from "svelte";
  import { app, notify } from "../store.svelte.js";
  import { signatures as api } from "../api.js";
  import { icons } from "../icons.js";

  let list = $state([]);
  let selected = $state(null);      // signature being edited
  let name = $state("");
  let accountId = $state(null);     // null = all accounts (global)
  let isDefault = $state(true);
  let mode = $state("rich");        // "rich" (WYSIWYG) | "html" (raw source)
  let htmlSource = $state("");      // single source of truth for the signature HTML
  let editor;                       // contenteditable (rich mode)
  let saving = $state(false);
  let fileInput;

  async function load() {
    list = await api.list();
    if (!selected && list.length) select(list[0]);
  }
  onMount(load);

  function restoreImages(html, inline) {
    for (const img of inline || []) {
      html = html.replaceAll(`cid:${img.cid}`, `data:${img.content_type};base64,${img.data_b64}`);
    }
    return html;
  }

  function select(s) {
    selected = s;
    name = s.name;
    accountId = s.account_id;
    isDefault = s.is_default;
    htmlSource = restoreImages(s.html || "", s.inline_images);
    syncEditor();
  }

  function newSig() {
    selected = { id: null, name: "New signature", html: "", inline_images: [], account_id: null, is_default: false };
    name = "New signature"; accountId = null; isDefault = list.length === 0;
    htmlSource = "";
    syncEditor();
  }

  // Push the source into the rich editor (only when in rich mode).
  function syncEditor() {
    if (mode !== "rich") return;
    queueMicrotask(() => { if (editor) editor.innerHTML = htmlSource; });
  }
  function setMode(m) {
    mode = m;
    syncEditor();
  }
  function onEditorInput() { if (editor) htmlSource = editor.innerHTML; }

  function insertImageFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const r = new FileReader();
    r.onload = () => {
      const dataUrl = String(r.result);
      if (mode === "rich" && editor) {
        const img = document.createElement("img");
        img.src = dataUrl; img.style.maxWidth = "320px";
        editor.appendChild(img);
        onEditorInput();
      } else {
        htmlSource += `<img src="${dataUrl}" style="max-width:320px" />`;
      }
    };
    r.readAsDataURL(file);
  }

  // Pull data: images out into inline CID attachments (works on the raw string,
  // so it handles both rich and HTML modes). http(s) images are left as-is.
  function extractInline(html) {
    const imgs = [];
    let i = 0;
    const out = html.replace(
      /(<img\b[^>]*\bsrc=["'])(data:([^;"']+);base64,([^"']+))(["'][^>]*>)/gi,
      (_full, pre, _src, ctype, b64, post) => {
        const cid = `sigimg${i++}@raplmail`;
        imgs.push({ cid, filename: `image${i}.png`, content_type: ctype, data_b64: b64 });
        return `${pre}cid:${cid}${post}`;
      }
    );
    return { html: out, inline_images: imgs };
  }

  // Minimal white-pane document so the preview matches what a recipient sees.
  const previewDoc = (html) =>
    `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">` +
    `<style>body{font:14px/1.6 system-ui,-apple-system,sans-serif;color:#1a1a1a;background:#fff;margin:12px}` +
    `a{color:#1a56db}img{max-width:100%;height:auto}</style></head><body>${html || ""}</body></html>`;
  const preview = $derived(previewDoc(restoreImages(htmlSource, selected?.inline_images)));

  async function save() {
    saving = true;
    try {
      if (mode === "rich" && editor) htmlSource = editor.innerHTML;
      const { html, inline_images } = extractInline(htmlSource);
      const payload = { name, html, inline_images, is_default: isDefault, account_id: accountId };
      const saved = selected.id ? await api.update(selected.id, payload) : await api.create(payload);
      notify("Signature saved");
      await load();
      select(list.find((s) => s.id === saved.id) || saved);
    } catch (e) { notify(e.message, "error"); } finally { saving = false; }
  }

  async function del(s) {
    if (!s.id) { selected = null; return; }
    if (!confirm(`Delete signature “${s.name}”?`)) return;
    await api.remove(s.id);
    selected = null;
    await load();
  }

  const acctLabel = (id) => id == null ? "All accounts" : (app.accounts.find((a) => a.id === id)?.email || "-");
</script>

<div class="wrap">
  <aside class="siglist">
    <button class="btn primary" onclick={newSig}>＋ New signature</button>
    {#each list as s (s.id)}
      <button class="sig" class:active={selected && selected.id === s.id} onclick={() => select(s)}>
        <b>{s.name}</b>
        <span>{acctLabel(s.account_id)}{s.is_default ? " · default" : ""}</span>
      </button>
    {/each}
    {#if list.length === 0 && !selected}<p class="muted">No signatures yet.</p>{/if}
  </aside>

  {#if selected}
    <div class="editorpane">
      <div class="row">
        <label class="fld">Name<input bind:value={name} /></label>
        <label class="fld">Use for
          <select bind:value={accountId}>
            <option value={null}>All accounts</option>
            {#each app.accounts as a}<option value={a.id}>{a.email}</option>{/each}
          </select>
        </label>
        <label class="chk"><input type="checkbox" bind:checked={isDefault} /> Default</label>
      </div>

      <div class="modebar">
        <div class="seg">
          <button class:on={mode === "rich"} onclick={() => setMode("rich")}>Basic text</button>
          <button class:on={mode === "html"} onclick={() => setMode("html")}>HTML</button>
        </div>
        {#if mode === "rich"}
          <div class="tools">
            <button class="tool" onmousedown={(e) => { e.preventDefault(); document.execCommand("bold"); onEditorInput(); }} style="font-weight:700">B</button>
            <button class="tool" onmousedown={(e) => { e.preventDefault(); document.execCommand("italic"); onEditorInput(); }} style="font-style:italic">I</button>
            <button class="tool" onmousedown={(e) => { e.preventDefault(); document.execCommand("createLink", false, prompt("URL:", "https://")); onEditorInput(); }}>{@html icons.link}</button>
            <button class="tool" onclick={() => fileInput.click()}>{@html icons.image} Image</button>
            <input bind:this={fileInput} type="file" accept="image/*" hidden onchange={(e) => insertImageFile(e.currentTarget.files[0])} />
          </div>
        {:else}
          <button class="tool" onclick={() => fileInput.click()}>{@html icons.image} Embed image</button>
          <input bind:this={fileInput} type="file" accept="image/*" hidden onchange={(e) => insertImageFile(e.currentTarget.files[0])} />
        {/if}
      </div>

      {#if mode === "rich"}
        <div class="editor" contenteditable="true" role="textbox" tabindex="0" aria-label="Signature editor"
          bind:this={editor} oninput={onEditorInput}
          ondrop={(e) => { e.preventDefault(); for (const f of e.dataTransfer.files) insertImageFile(f); }}
          ondragover={(e) => e.preventDefault()} data-placeholder="Type your signature; drag an image right in…"></div>
      {:else}
        <textarea class="htmlsrc" spellcheck="false" bind:value={htmlSource}
          placeholder={'<table>…</table>  or  <img src="https://…"/>  - paste your HTML here'}></textarea>
      {/if}

      <div class="preview-wrap">
        <div class="preview-label">Live preview {@html icons.bulb}<span>exactly how recipients see it</span></div>
        <iframe class="preview" title="Signature preview" sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc={preview}></iframe>
      </div>

      <div class="actions">
        <button class="btn primary" onclick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        <button class="btn ghost danger" onclick={() => del(selected)}>Delete</button>
        <span class="note">{@html icons.bulb} Inline (pasted/embedded) images are attached so they always show; external URLs load on the recipient's side.</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .wrap { display: grid; grid-template-columns: 240px 1fr; gap: 20px; max-width: 940px; }
  .siglist { display: flex; flex-direction: column; gap: 6px; }
  .siglist .btn { justify-content: center; margin-bottom: 6px; }
  .sig { display: flex; flex-direction: column; gap: 2px; text-align: left; padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); }
  .sig:hover { border-color: var(--accent); }
  .sig.active { background: var(--surface-2); box-shadow: inset 3px 0 0 var(--accent); }
  .sig span { color: var(--muted); font-size: 11px; }
  .editorpane { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .row { display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; }
  .fld { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  .chk { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .modebar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
  .seg button { padding: 6px 14px; font-size: 13px; color: var(--muted); }
  .seg button.on { background: var(--accent); color: #fff; }
  .tools { display: flex; gap: 4px; }
  .tool { min-width: 30px; padding: 6px 9px; border-radius: 6px; color: var(--muted); }
  .tool:hover { background: var(--surface-2); color: var(--text); }
  .editor { min-height: 160px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); outline: none; line-height: 1.6; color: var(--text); }
  .editor:empty::before { content: attr(data-placeholder); color: var(--faint); }
  .htmlsrc { min-height: 160px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--text); font-family: ui-monospace, monospace; font-size: 12px; resize: vertical; outline: none; }
  .htmlsrc:focus { border-color: var(--accent); }
  .preview-wrap { display: flex; flex-direction: column; gap: 6px; }
  .preview-label { display: flex; align-items: center; gap: 6px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); }
  .preview-label span { text-transform: none; letter-spacing: 0; }
  .preview { width: 100%; min-height: 160px; border: 1px solid var(--border); border-radius: var(--radius); background: #fff; }
  .actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .note { color: var(--faint); font-size: 12px; margin-left: auto; max-width: 380px; }
  .muted { color: var(--muted); }
</style>
