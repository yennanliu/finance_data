/*
 * dom_shim.mjs — the minimal DOM + fake Lightweight Charts the widget needs
 * ========================================================================
 * Shared by tests/js/kline_chart_harness.mjs (assertions against fixtures) and
 * the end-to-end check (assertions against the real derived payload), so both
 * drive docs/javascripts/kline-chart.js through exactly the same path.
 *
 * No npm dependencies on purpose: a jsdom install would make this unrunnable in
 * CI without a package.json, and the widget only touches a small, stable slice
 * of the DOM. The shim covers exactly that slice.
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(HERE, "..", "..");
export const WIDGET_JS = path.join(ROOT, "docs", "javascripts", "kline-chart.js");

// ── the smallest DOM the widget actually uses ───────────────────────────────
// innerHTML is assigned as a string and then queried, so the shim has to parse
// it. Only tags with class/id/data attributes matter for the queries the widget
// makes, so this parser handles those and ignores the rest of HTML.
export class El {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.attrs = {};
    this.children = [];
    this.parent = null;
    this.style = {};
    this.listeners = {};
    this._text = "";
    this.classList = {
      _set: new Set(),
      add: (c) => this.classList._set.add(c),
      remove: (c) => this.classList._set.delete(c),
      contains: (c) => this.classList._set.has(c),
      toggle: (c, on) => (on ? this.classList._set.add(c) : this.classList._set.delete(c)),
    };
  }

  // -- attributes --
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  get className() { return [...this.classList._set].join(" "); }
  set className(v) {
    this.classList._set = new Set(String(v).split(/\s+/).filter(Boolean));
  }

  // -- text --
  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join("");
  }
  set textContent(v) { this._text = String(v); this.children = []; }

  // -- tree --
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() { (this.listeners.click || []).forEach((fn) => fn({})); }

  set innerHTML(html) {
    this._text = "";
    this.children = parseHTML(String(html)).map((c) => { c.parent = this; return c; });
  }
  get innerHTML() { return this._html || ""; }

  // -- selectors: ".cls", ".a .b", "tag", ".cls:not([attr])" --
  querySelectorAll(sel) {
    const parts = sel.trim().split(/\s+/);
    let pool = [this];
    for (const part of parts) {
      const next = [];
      for (const el of pool) {
        for (const d of descendants(el)) if (matches(d, part)) next.push(d);
      }
      pool = next;
    }
    const out = pool;
    out.forEach = Array.prototype.forEach.bind(out);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

function descendants(el, acc = []) {
  for (const c of el.children) { acc.push(c); descendants(c, acc); }
  return acc;
}

function matches(el, sel) {
  // The widget's scan selector is `.kline-widget:not([data-kline-ready])`, which
  // is how it avoids re-initialising a node under instant navigation — so the
  // matcher has to honour :not([attr]) or nothing is ever built.
  const not = sel.match(/:not\(\[([^\]]+)\]\)/);
  if (not) {
    if (el.getAttribute(not[1]) !== null) return false;
    sel = sel.replace(not[0], "");
  }
  const attr = sel.match(/\[([^\]=]+)\]$/);
  if (attr) {
    if (el.getAttribute(attr[1]) === null) return false;
    sel = sel.replace(attr[0], "");
  }
  if (!sel) return true;
  if (sel.startsWith(".")) return sel.slice(1).split(".").every((c) => el.classList.contains(c));
  if (sel.startsWith("#")) return el.getAttribute("id") === sel.slice(1);
  return el.tagName === sel.toUpperCase();
}

const VOID_TAGS = new Set(["br", "hr", "img", "input", "meta", "link"]);
const TAG_RE = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^\s=>]+(?:=(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>/g;
const ATTR_RE = /([^\s=]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;

/** Parse a fragment into a shallow element tree. Text becomes textContent. */
function parseHTML(html) {
  const roots = [];
  const stack = [];
  let cursor = 0;
  let m;
  TAG_RE.lastIndex = 0;
  while ((m = TAG_RE.exec(html)) !== null) {
    const text = html.slice(cursor, m.index);
    if (text.trim() && stack.length) stack[stack.length - 1]._text += text;
    cursor = m.index + m[0].length;

    const [, closing, tag, attrText, selfClose] = m;
    if (closing) {
      // Unwind only if this tag is actually open. Blindly popping until a match
      // would flatten the whole tree on a stray close tag, silently detaching
      // every element the assertions then look for.
      const want = tag.toUpperCase();
      if (stack.some((e) => e.tagName === want)) {
        while (stack.length && stack[stack.length - 1].tagName !== want) stack.pop();
        stack.pop();
      }
      continue;
    }

    const el = new El(tag);
    ATTR_RE.lastIndex = 0;
    let a;
    while ((a = ATTR_RE.exec(attrText || "")) !== null) {
      const key = a[1];
      if (!key) continue;
      const val = a[2] ?? a[3] ?? a[4] ?? "";
      if (key === "class") el.className = val;
      else el.attrs[key] = val;
    }

    (stack.length ? stack[stack.length - 1] : { appendChild: (x) => roots.push(x) })
      .appendChild(el);
    if (!selfClose && !VOID_TAGS.has(tag.toLowerCase())) stack.push(el);
  }
  const tail = html.slice(cursor);
  if (tail.trim() && stack.length) stack[stack.length - 1]._text += tail;
  return roots;
}

// ── fake Lightweight Charts: record what it was asked to draw ───────────────
export function makeLC(log) {
  function series(kind) {
    const s = {
      kind,
      options: {},
      data: null,
      setData(d) { this.data = d; },
      applyOptions(o) { Object.assign(this.options, o); },
      priceScale() { return { applyOptions() {} }; },
    };
    log.series.push(s);
    return s;
  }
  return {
    CrosshairMode: { Magnet: "magnet" },
    LineStyle: { Dashed: "dashed" },
    createChart(el, opts) {
      log.chartOptions = opts;
      log.container = el;
      return {
        addCandlestickSeries(o) { const s = series("candle"); s.applyOptions(o); log.candle = s; return s; },
        addHistogramSeries(o) { const s = series("volume"); s.applyOptions(o); log.volume = s; return s; },
        addLineSeries(o) { const s = series("line"); s.applyOptions(o); log.lines.push(s); return s; },
        applyOptions(o) { log.appliedOptions.push(o); },
        subscribeCrosshairMove(fn) { log.crosshairHandler = fn; },
        timeScale() { return { setVisibleRange(r) { log.visibleRanges.push(r); } }; },
        remove() { log.removed = true; },
      };
    },
  };
}

// ── run one widget through the real widget code ─────────────────────────────
/**
 * @param attrs data-* attributes for the widget node
 * @param payload the kline.json object the fetch should resolve with
 * @param opts.zh render as a Traditional-Chinese page
 * @returns {node, log} the widget node after build, and the draw log
 */
export async function renderWidget(attrs, payload, opts = {}) {
  const log = {
    series: [], lines: [], appliedOptions: [], visibleRanges: [],
    chartOptions: null, candle: null, volume: null, removed: false,
  };

  const node = new El("div");
  node.className = "kline-widget";
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));

  const body = new El("body");
  body.setAttribute("data-md-color-scheme", opts.dark ? "slate" : "default");
  body.appendChild(node);

  const document = {
    body,
    createElement: (t) => new El(t),
    querySelectorAll: (sel) => body.querySelectorAll(sel),
    addEventListener: (type, fn) => { if (type === "DOMContentLoaded") document._ready = fn; },
  };

  let fetchCalledWith = null;
  const sandbox = {
    window: { LightweightCharts: makeLC(log) },
    document,
    location: { pathname: opts.zh ? "/finance_data/zh/reports/amd/" : "/finance_data/reports/amd/" },
    getComputedStyle: () => ({ getPropertyValue: () => "", fontFamily: "system-ui" }),
    MutationObserver: class { observe() {} },
    fetch: (src) => {
      fetchCalledWith = src;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
    },
    console,
    setTimeout,
  };
  sandbox.window.document = document;
  sandbox.globalThis = sandbox;

  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(WIDGET_JS, "utf8"), sandbox, { filename: WIDGET_JS });

  document._ready();            // the widget's DOMContentLoaded entry point
  await new Promise((r) => setImmediate(r));  // let the fetch promise settle
  return { node, log, fetchCalledWith };
}

