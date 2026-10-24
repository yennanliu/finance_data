/*
 * lang-switch.js — keep the 文A language menu pointed at the current page
 * =========================================================================
 * The menu is rendered server-side by overrides/partials/alternate.html with
 * the right targets for the page it was rendered on. But Material runs in
 * instant-navigation mode: an in-site click swaps the page body and syncs
 * <head>, and never re-renders the header that holds this menu. Without this
 * script the menu keeps the links of the first page loaded — usually the home
 * page — so switching language from a report "jumped back to the home page".
 *
 * Every page publishes its own targets in <head> (main.html):
 *   <meta name="fp:alternate" data-lang="en" content="reports/avav/">
 *   <meta name="fp:alternate" data-lang="zh" content="zh/reports/avav/">
 *   <meta name="fp:lang" content="en">
 * as site-root-relative paths. On every `document$` emission this resolves them
 * against the site root (`__md_scope`) onto the menu links, and marks the
 * reader's current language with aria-current. It computes no route itself:
 * the mapping rule lives in one place, alternate-paths.html.
 */
(function () {
  "use strict";

  function siteRoot() {
    if (typeof __md_scope !== "undefined" && __md_scope) return __md_scope;
    return new URL("/", window.location.href);
  }

  function sync() {
    var root = siteRoot();
    var targets = {};
    Array.prototype.forEach.call(
      document.querySelectorAll('meta[name="fp:alternate"]'), function (m) {
        targets[m.getAttribute("data-lang")] = m.getAttribute("content");
      });
    var cur = document.querySelector('meta[name="fp:lang"]');
    var current = cur ? cur.getAttribute("content") : null;

    Array.prototype.forEach.call(
      document.querySelectorAll(".md-select__link[hreflang]"), function (a) {
        // "zh-TW" → "zh": the metas are keyed by tree, not by locale.
        var lang = (a.getAttribute("hreflang") || "").split("-")[0];
        if (lang in targets) {
          a.setAttribute("href", new URL(targets[lang], root).href);
        }
        if (current === null) return;
        if (lang === current) a.setAttribute("aria-current", "true");
        else a.removeAttribute("aria-current");
      });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(sync);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
