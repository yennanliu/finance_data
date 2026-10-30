/*
 * math.js — render report equations with KaTeX
 * ============================================
 * build_docs.display_math() rewrites each report `$$ … $$` to `\( … \)`, which
 * pymdownx.arithmatex (generic mode) wraps in `<span class="arithmatex">`.
 * Without a renderer that span shows raw LaTeX (`\text{MOS} = \frac{…}`).
 *
 * KaTeX is ~300 KB with its stylesheet, and only report pages with worked
 * equations need it, so it is fetched on the first page that has an
 * `.arithmatex` element and reused on every later instant-navigation page.
 */
(function () {
  "use strict";

  var BASE = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/";
  var loading = null;

  function load() {
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      var css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = BASE + "katex.min.css";
      document.head.appendChild(css);
      var js = document.createElement("script");
      js.src = BASE + "katex.min.js";
      js.onload = resolve;
      js.onerror = reject;
      document.head.appendChild(js);
    });
    return loading;
  }

  function render(el) {
    var tex = el.textContent.trim();
    // build_docs.display_math() marks an equation that had a line to itself
    // with \displaystyle; it keeps that line (minify-html drops the newline).
    if (tex.indexOf("\\(\\displaystyle") === 0) el.classList.add("arithmatex--line");
    // Generic arithmatex output keeps the delimiters: \( … \) or \[ … \].
    var display = tex.slice(0, 2) === "\\[";
    tex = tex.replace(/^\\[(\[]/, "").replace(/\\[)\]]$/, "");
    try {
      // throwOnError off: a formula KaTeX cannot parse stays readable source.
      window.katex.render(tex, el, { displayMode: display, throwOnError: false, strict: "ignore" });
    } catch (e) { /* leave the source text in place */ }
  }

  function init() {
    var nodes = document.querySelectorAll(".arithmatex");
    if (!nodes.length) return;
    load().then(function () {
      Array.prototype.forEach.call(nodes, render);
    }, function () { /* CDN unreachable: the source text stays */ });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
