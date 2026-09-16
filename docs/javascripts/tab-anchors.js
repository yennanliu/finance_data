/*
 * tab-anchors.js — make anchors reach headings inside a collapsed tab
 * ===================================================================
 * The Market Data pages put ~22 charts into five content tabs (pymdownx.tabbed,
 * alternate_style). The table of contents still lists every heading on the
 * page, including the ones in tabs that are not open — and an inactive tab's
 * panel is `display: none`, so clicking "P/E Bands" in the TOC scrolls to
 * nothing at all. The same is true of any link arriving with a #fragment.
 *
 * This opens whichever tab contains the target (outermost first, so nesting
 * works) and then scrolls to it. Tabs are radio inputs, so "opening" one is
 * checking the input that sits at the target block's index within its set.
 *
 * Small, defensive and page-agnostic: it does nothing on a page with no tabs.
 */
(function () {
  "use strict";

  /** Check the radio that owns `block` inside its `.tabbed-set`. */
  function open(block) {
    var content = block.parentNode;            // .tabbed-content
    if (!content) return null;
    var set = content.parentNode;              // .tabbed-set
    if (!set) return null;

    var blocks = [], inputs = [];
    Array.prototype.forEach.call(content.children, function (el) {
      if (el.classList && el.classList.contains("tabbed-block")) blocks.push(el);
    });
    Array.prototype.forEach.call(set.children, function (el) {
      if (el.tagName === "INPUT" && el.type === "radio") inputs.push(el);
    });

    var i = blocks.indexOf(block);
    if (i >= 0 && inputs[i]) inputs[i].checked = true;
    return set;
  }

  /** Open every tab between `el` and the document root. */
  function reveal(el) {
    var node = el;
    while (node && node !== document.body) {
      if (node.classList && node.classList.contains("tabbed-block")) {
        node = open(node) || node.parentNode;
      }
      node = node.parentNode;
    }
  }

  function target(hash) {
    var id = (hash || "").replace(/^#/, "");
    if (!id) return null;
    try {
      return document.getElementById(decodeURIComponent(id));
    } catch (e) {
      return document.getElementById(id);
    }
  }

  function go(hash) {
    var el = target(hash);
    if (!el) return;
    reveal(el);
    // After the frame in which the tab became visible: scrolling to an element
    // that is still display:none lands nowhere.
    requestAnimationFrame(function () { el.scrollIntoView(); });
  }

  function wire() {
    go(location.hash);
  }

  // A click on a link whose fragment is already current fires no hashchange,
  // so the click itself is handled as well as the event.
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href*="#"]') : null;
    if (!a) return;
    var href = a.getAttribute("href") || "";
    var hash = href.slice(href.indexOf("#"));
    if (hash.length > 1 && target(hash)) go(hash);
  });

  window.addEventListener("hashchange", function () { go(location.hash); });

  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(wire);   // MkDocs Material instant navigation
  } else {
    document.addEventListener("DOMContentLoaded", wire);
  }
})();
