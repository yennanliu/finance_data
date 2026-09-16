/*
 * tab_anchors_harness.mjs — assertions over docs/javascripts/tab-anchors.js
 * =========================================================================
 * The Market Data pages put ~22 charts into five content tabs. The table of
 * contents still lists every heading, so a TOC link into a tab that is not open
 * scrolls to a `display: none` panel and appears to do nothing. tab-anchors.js
 * opens the owning tab first.
 *
 * What is worth verifying is exactly that: given a fragment, the right radio
 * ends up checked and the target is scrolled to — including for a nested tab
 * set, and without touching a page that has no tabs at all.
 *
 * Runs the shipping file against a purpose-built DOM stub (the `.pchart` shim
 * in dom_shim.mjs models a widget's innerHTML; this script walks a real tree).
 *
 * Run directly:   node tests/js/tab_anchors_harness.mjs
 * Run via pytest: tests/test_tab_anchors_js.py
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const SCRIPT = path.join(ROOT, "docs", "javascripts", "tab-anchors.js");

let passed = 0;
const failures = [];

function check(name, cond, detail) {
  if (cond) { passed++; return; }
  failures.push(detail ? `${name}\n      ${detail}` : name);
}

// ── the smallest tree the script walks ──────────────────────────────────────
class El {
  constructor(tag, opts = {}) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = opts.attrs || {};
    this.id = opts.id || "";
    this.type = opts.type || "";
    this.checked = !!opts.checked;
    this.scrolled = 0;
    const set = new Set(opts.classes || []);
    this.classList = { contains: (c) => set.has(c), add: (c) => set.add(c) };
  }
  append(...kids) {
    kids.forEach((k) => { k.parentNode = this; this.children.push(k); });
    return this;
  }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  scrollIntoView() { this.scrolled++; }
  closest(sel) {
    // Only `a[href*="#"]` is ever asked for.
    let n = this;
    while (n) {
      if (n.tagName === "A" && (n.getAttribute("href") || "").includes("#")) return n;
      n = n.parentNode;
    }
    return null;
  }
}

/** A `.tabbed-set` of `n` panes; pane `i` holds the elements given for it.
 *
 * The inputs behave as one radio group — checking one unchecks the rest, the
 * way a browser does. Without that, "opened the right tab" would pass while the
 * page still showed the first one. */
function tabbedSet(panes) {
  const set = new El("div", { classes: ["tabbed-set", "tabbed-alternate"] });
  const content = new El("div", { classes: ["tabbed-content"] });
  const group = [];
  panes.forEach((_, i) => {
    const input = new El("input", { type: "radio" });
    let on = i === 0;
    Object.defineProperty(input, "checked", {
      get: () => on,
      set: (v) => {
        on = !!v;
        if (on) group.forEach((o) => { if (o !== input) o.checked = false; });
      },
    });
    group.push(input);
    set.append(input);
  });
  set.append(new El("div", { classes: ["tabbed-labels"] }));
  panes.forEach((kids) => {
    const block = new El("div", { classes: ["tabbed-block"] });
    block.append(...kids);
    content.append(block);
  });
  set.append(content);
  return { set, inputs: set.children.filter((c) => c.tagName === "INPUT") };
}

function run(body, hash, act) {
  const ids = {};
  (function index(n) {
    if (n.id) ids[n.id] = n;
    n.children.forEach(index);
  })(body);

  const listeners = {};
  const document = {
    body,
    getElementById: (id) => ids[id] || null,
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
  };
  const window = {
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
  };
  const location = { hash: hash || "" };

  const sandbox = {
    document, window, location, console,
    requestAnimationFrame: (fn) => fn(),
    decodeURIComponent,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SCRIPT, "utf8"), sandbox, { filename: SCRIPT });

  // The script wires itself on DOMContentLoaded when Material's document$ is absent.
  (listeners.DOMContentLoaded || []).forEach((fn) => fn());
  if (act) act(listeners, location);
  return { ids, listeners };
}

// ── 1. a fragment into a collapsed tab opens it and scrolls there ───────────
{
  const heading = new El("h3", { id: "pe-bands" });
  const { set, inputs } = tabbedSet([
    [new El("h3", { id: "returns" })],
    [new El("h3", { id: "drawdown" })],
    [heading],
  ]);
  const body = new El("body").append(set);

  run(body, "#pe-bands");

  check("opens the tab that owns the target",
        inputs[2].checked === true,
        `checked = ${inputs.map((i) => i.checked).join(",")}`);
  check("leaves the other tabs closed",
        inputs[0].checked === false && inputs[1].checked === false);
  check("scrolls to the target once it is visible", heading.scrolled === 1,
        String(heading.scrolled));
}

// ── 2. a nested tab set is opened outermost-first ───────────────────────────
{
  const heading = new El("h4", { id: "deep" });
  const inner = tabbedSet([[new El("p")], [heading]]);
  const outer = tabbedSet([[new El("p")], [inner.set]]);
  const body = new El("body").append(outer.set);

  run(body, "#deep");

  check("nested: the inner tab is opened", inner.inputs[1].checked === true);
  check("nested: the outer tab is opened too", outer.inputs[1].checked === true);
}

// ── 3. clicking a TOC link works even when the fragment is already current ──
// A click on the current hash fires no hashchange, so the click is handled too.
{
  const heading = new El("h3", { id: "valuation" });
  const { set, inputs } = tabbedSet([[new El("p")], [heading]]);
  const link = new El("a", { attrs: { href: "#valuation" } });
  const body = new El("body").append(set, link);

  run(body, "#valuation", (listeners) => {
    inputs[1].checked = false;          // as if the reader clicked back to tab 1
    inputs[0].checked = true;
    listeners.click.forEach((fn) => fn({ target: link }));
  });

  check("a click re-opens the tab without a hashchange",
        inputs[1].checked === true);
}

// ── 4. hashchange is handled ────────────────────────────────────────────────
{
  const heading = new El("h3", { id: "later" });
  const { set, inputs } = tabbedSet([[new El("p")], [heading]]);
  const body = new El("body").append(set);

  run(body, "", (listeners, location) => {
    location.hash = "#later";
    listeners.hashchange.forEach((fn) => fn({}));
  });

  check("hashchange opens the tab", inputs[1].checked === true);
}

// ── 5. it is inert where it has nothing to do ───────────────────────────────
{
  const heading = new El("h3", { id: "plain" });
  const body = new El("body").append(heading);
  run(body, "#plain");
  check("a page with no tabs still scrolls to the target",
        heading.scrolled === 1, String(heading.scrolled));
}

{
  const body = new El("body").append(new El("h3", { id: "here" }));
  run(body, "#nowhere");
  check("an unknown fragment is ignored rather than throwing", true);
}

{
  const body = new El("body").append(new El("h3", { id: "here" }));
  run(body, "");
  check("no fragment at all is a no-op", true);
}

console.log(`${passed} passed, ${failures.length} failed`);
failures.forEach((f) => console.log(`  ✗ ${f}`));
process.exit(failures.length ? 1 : 0);
