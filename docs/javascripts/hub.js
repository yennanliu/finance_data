/*
 * hub.js — progressive enhancement for the section indexes and report pages
 * =========================================================================
 * 1. Filter box on the AI Gen Reports / Market News card grids. The grid is
 *    static HTML from build_docs.py (one `[data-hub-item]` per ticker with a
 *    pre-lowercased `data-search` haystack); this only toggles `hidden`.
 *    Without JS the grid is simply unfiltered.
 * 2. A reading-progress bar along the top edge, for the long report pages.
 *
 * MkDocs Material runs in instant-navigation (SPA) mode, so both re-run on
 * every `document$` emission. Scroll handling is passive and rAF-throttled —
 * nothing here may block the scroll thread (see extra.css on mobile lag).
 */
(function () {
  "use strict";

  // ── 1. card-grid filter ────────────────────────────────────────────────────
  function initFilter(toolbar) {
    if (toolbar.dataset.hubReady) return;
    var input = toolbar.querySelector("[data-hub-filter]");
    var scope = toolbar.parentElement;
    var grid = scope && scope.querySelector("[data-hub-grid]");
    if (!input || !grid) return;
    toolbar.dataset.hubReady = "1";

    var items = Array.prototype.slice.call(grid.querySelectorAll("[data-hub-item]"));
    var count = toolbar.querySelector("[data-hub-count]");
    var empty = scope.querySelector("[data-hub-empty]");

    function apply() {
      var terms = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      var shown = 0;
      items.forEach(function (el) {
        var hay = el.getAttribute("data-search") || "";
        var ok = terms.every(function (t) { return hay.indexOf(t) !== -1; });
        el.hidden = !ok;
        if (ok) shown++;
      });
      if (count) count.textContent = String(shown);
      if (empty) empty.hidden = shown > 0;
    }

    input.addEventListener("input", apply);
    // A pre-filled value (browser form restore) must filter immediately.
    if (input.value) apply();
  }

  // ── 2. reading progress ────────────────────────────────────────────────────
  var bar = null;
  var ticking = false;

  function ensureBar() {
    if (bar) return bar;
    bar = document.createElement("div");
    bar.className = "rp-progress";
    bar.setAttribute("role", "presentation");
    document.body.appendChild(bar);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return bar;
  }

  function paint() {
    ticking = false;
    var doc = document.documentElement;
    var max = (doc.scrollHeight || 0) - (window.innerHeight || 0);
    // Short pages have nothing to track; hide the bar rather than show 100%.
    if (max < 600) { bar.classList.remove("is-on"); return; }
    var y = window.pageYOffset || doc.scrollTop || 0;
    var p = Math.min(1, Math.max(0, y / max));
    bar.style.transform = "scaleX(" + p.toFixed(4) + ")";
    bar.classList.toggle("is-on", y > 40);
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(paint);
  }

  // ── boot ──────────────────────────────────────────────────────────────────
  function init() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-hub-toolbar]"), initFilter);
    ensureBar();
    onScroll();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
