// RaplMail wiki: the page holds both languages (data-l="en" / "cs") and the
// stylesheet shows the one matching <html lang>; this script picks it (shared
// with the main page's choice), filters articles as you type, marks the article
// you're reading in the contents and folds the contents away on phones.
(() => {
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  let lang = store.get("raplmail.site.lang") || ((navigator.language || "").toLowerCase().startsWith("cs") ? "cs" : "en");
  const filter = document.querySelector(".js-filter");

  function applyLang() {
    document.documentElement.lang = lang;
    document.querySelectorAll(".lang [data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    document.title = lang === "cs" ? "Wiki RaplMailu - návody a odpovědi" : "RaplMail wiki - guides and answers";
    filter.placeholder = filter.dataset[lang === "cs" ? "phCs" : "phEn"];
    runFilter();
  }
  document.querySelectorAll(".lang [data-lang]").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang; store.set("raplmail.site.lang", lang); applyLang();
  }));

  // --- filter ---------------------------------------------------------------
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const articles = [...document.querySelectorAll(".art")];
  const tocLink = (id) => document.querySelector(`.js-toc a[href="#${id}"]`);
  function runFilter() {
    const words = fold(filter.value.trim()).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const art of articles) {
      const body = art.querySelector(`[data-l="${lang}"]`)?.textContent || "";
      const hay = fold(body + " " + (art.dataset.k || ""));
      const hit = words.every((w) => hay.includes(w));
      art.hidden = !hit;
      tocLink(art.id).parentElement.hidden = !hit;
      if (hit) shown++;
    }
    // a category heading shows while any of its articles does
    let cat = null, any = false;
    for (const el of document.querySelector(".wiki-main").children) {
      if (el.matches("[data-cat]")) { if (cat) cat.hidden = !any; cat = el; any = false; }
      else if (el.matches(".art") && !el.hidden) any = true;
    }
    if (cat) cat.hidden = !any;
    document.querySelectorAll(".js-toc ul").forEach((ul) => {
      const h = ul.previousElementSibling;
      const has = [...ul.children].some((li) => !li.hidden);
      ul.hidden = !has; if (h) h.hidden = !has;
    });
    document.querySelector(".js-none").hidden = shown > 0;
    document.querySelector(".js-empty").hidden = shown > 0;
    document.querySelector(".wiki-hero").hidden = words.length > 0;
  }
  filter.addEventListener("input", runFilter);
  filter.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { filter.value = ""; runFilter(); }
    if (e.key === "Enter") {                // jump to the first match
      const first = articles.find((a) => !a.hidden);
      if (first) { location.hash = first.id; closeToc(); }
    }
  });

  // --- contents on phones -------------------------------------------------------
  const toggle = document.querySelector(".js-toc-toggle");
  const toc = document.querySelector(".js-toc");
  function closeToc() { toc.hidden = true; toggle.setAttribute("aria-expanded", "false"); }
  toggle.addEventListener("click", () => {
    toc.hidden = !toc.hidden;
    toggle.setAttribute("aria-expanded", String(!toc.hidden));
  });
  toc.addEventListener("click", (e) => { if (e.target.closest("a") && getComputedStyle(toggle).display !== "none") closeToc(); });

  // --- the article you're reading -------------------------------------------------
  let current = null;
  const mark = (id) => {
    if (id === current) return;
    current = id;
    document.querySelectorAll(".js-toc a.on").forEach((a) => a.classList.remove("on"));
    tocLink(id)?.classList.add("on");
  };
  // the last article whose heading has passed under the top bar
  let ticking = false;
  function spy() {
    ticking = false;
    let at = null;
    for (const a of articles) if (!a.hidden && a.getBoundingClientRect().top <= 140) at = a;
    if (at) mark(at.id);
    else if (current) { document.querySelectorAll(".js-toc a.on").forEach((a) => a.classList.remove("on")); current = null; }
  }
  window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(spy); } }, { passive: true });
  window.addEventListener("hashchange", () => requestAnimationFrame(spy));

  const bar = document.getElementById("bar");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 4);
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll();

  applyLang();
  spy();
})();
