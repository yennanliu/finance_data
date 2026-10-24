/*
 * lang_switch_harness.mjs — assertions over docs/javascripts/lang-switch.js
 * =========================================================================
 * Reproduces the bug the script fixes: the header (and its 文A menu) is
 * rendered once, on the home page; Material's instant navigation then swaps
 * the body and <head> but never the header. The menu must follow the page the
 * reader is on, not the one they first loaded.
 *
 * Run directly:   node tests/js/lang_switch_harness.mjs
 * Run via pytest: tests/test_lang_switch_js.py
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const SCRIPT = path.join(ROOT, "docs", "javascripts", "lang-switch.js");

let passed = 0;
const failures = [];

function check(name, cond, detail) {
  if (cond) { passed++; return; }
  failures.push(detail ? `${name}\n      ${detail}` : name);
}

class El {
  constructor(attrs) { this.attrs = { ...attrs }; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  removeAttribute(k) { delete this.attrs[k]; }
}

const SITE = "https://example.github.io/finance_data/";

/** A page whose header was rendered on the home page (stale after navigation). */
function boot() {
  const links = [
    new El({ hreflang: "en", href: "./", "aria-current": "true" }),
    new El({ hreflang: "zh-TW", href: "zh/" }),
  ];
  let metas = [];
  const subscribers = [];
  const document = {
    readyState: "complete",
    querySelectorAll(sel) {
      if (sel === 'meta[name="fp:alternate"]') {
        return metas.filter((m) => m.getAttribute("name") === "fp:alternate");
      }
      if (sel === ".md-select__link[hreflang]") return links;
      throw new Error("unexpected selector " + sel);
    },
    querySelector(sel) {
      if (sel === 'meta[name="fp:lang"]') {
        return metas.find((m) => m.getAttribute("name") === "fp:lang") || null;
      }
      throw new Error("unexpected selector " + sel);
    },
    addEventListener() {},
  };
  const ctx = {
    document,
    window: { location: { href: SITE } },
    URL,
    __md_scope: new URL(SITE),
    document$: { subscribe: (fn) => subscribers.push(fn) },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(SCRIPT, "utf8"), ctx);

  /** What Material does on an in-site click: sync <head>, emit document$. */
  function navigate(en, zh, lang) {
    metas = [
      new El({ name: "fp:alternate", "data-lang": "en", content: en }),
      new El({ name: "fp:alternate", "data-lang": "zh", content: zh }),
      new El({ name: "fp:lang", content: lang }),
    ];
    subscribers.forEach((fn) => fn());
  }
  /** A page with no targets in <head> (404.html renders without a page). */
  function navigateBare() {
    metas = [];
    subscribers.forEach((fn) => fn());
  }
  const href = (lang) => links.find((a) => a.getAttribute("hreflang") === lang)
    .getAttribute("href");
  const current = () => links.filter((a) => a.getAttribute("aria-current") !== null)
    .map((a) => a.getAttribute("hreflang"));
  return { navigate, navigateBare, href, current, subscribers };
}

// ── it subscribes to instant navigation ─────────────────────────────────────
{
  const t = boot();
  check("subscribes to document$", t.subscribers.length === 1,
    `subscribers=${t.subscribers.length}`);
}

// ── home → report: 文A goes to the report's ticker, not the ZH home ─────────
{
  const t = boot();
  t.navigate("reports/avav/", "zh/reports/avav/", "en");
  check("zh target follows the page", t.href("zh-TW") === SITE + "zh/reports/avav/",
    `got ${t.href("zh-TW")}`);
  check("en target follows the page", t.href("en") === SITE + "reports/avav/",
    `got ${t.href("en")}`);
  check("zh target is not the ZH home", t.href("zh-TW") !== SITE + "zh/");
  check("english stays selected", JSON.stringify(t.current()) === '["en"]',
    JSON.stringify(t.current()));
}

// ── switch to ZH, then keep navigating: the selection follows ───────────────
{
  const t = boot();
  t.navigate("data/2330.tw/", "zh/data/2330.tw/", "zh");
  check("en target on a zh page", t.href("en") === SITE + "data/2330.tw/",
    `got ${t.href("en")}`);
  check("chinese is now selected", JSON.stringify(t.current()) === '["zh-TW"]',
    JSON.stringify(t.current()));
  t.navigate("reports/nvda/", "zh/reports/nvda/", "zh");
  check("second navigation re-points again",
    t.href("en") === SITE + "reports/nvda/", `got ${t.href("en")}`);
}

// ── the site root maps to the site root (empty path) ────────────────────────
{
  const t = boot();
  t.navigate("reports/avav/", "zh/reports/avav/", "en");
  t.navigate("", "zh/", "en");
  check("root en", t.href("en") === SITE, `got ${t.href("en")}`);
  check("root zh", t.href("zh-TW") === SITE + "zh/", `got ${t.href("zh-TW")}`);
}

// ── a page without the metas (e.g. 404) leaves the links alone ──────────────
{
  const t = boot();
  t.navigate("reports/avav/", "zh/reports/avav/", "en");
  t.navigateBare();
  check("no metas → links untouched",
    t.href("zh-TW") === SITE + "zh/reports/avav/", `got ${t.href("zh-TW")}`);
  check("no metas → selection untouched",
    JSON.stringify(t.current()) === '["en"]', JSON.stringify(t.current()));
}

console.log(`${passed} passed, ${failures.length} failed`);
if (failures.length) {
  failures.forEach((f) => console.log("  ✗ " + f));
  process.exit(1);
}
