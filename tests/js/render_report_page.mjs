/*
 * render_report_page.mjs — render a *built* report page's chart widget
 * ===================================================================
 * End-to-end check: takes the real widget attributes scraped from a built report
 * page and the real kline.json derived from the price store, drives
 * docs/javascripts/kline-chart.js over them through the same shim the unit
 * harness uses, and prints what the chart was actually asked to draw.
 *
 * Usage:  node tests/js/render_report_page.mjs <page.md> <kline.json>
 *
 * Exits non-zero if the widget fails to build or the as-of contract is violated,
 * so it can gate a release rather than merely informing one.
 */

import fs from "node:fs";
import { renderWidget } from "./dom_shim.mjs";

const [pagePath, payloadPath] = process.argv.slice(2);
if (!pagePath || !payloadPath) {
  console.error("usage: node render_report_page.mjs <page.md> <kline.json>");
  process.exit(2);
}

// ── scrape the widget div out of the built page ─────────────────────────────
const page = fs.readFileSync(pagePath, "utf8");
const div = page.match(/<div class="kline-widget"[^>]*><\/div>/);
if (!div) {
  console.error(`no kline-widget found in ${pagePath}`);
  process.exit(1);
}
const attrs = {};
for (const m of div[0].matchAll(/(data-[a-z-]+)="([^"]*)"/g)) attrs[m[1]] = m[2];

const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));

// Snapshot before rendering: the widget truncates `data.bars` in place, so
// anything measured off `payload` afterwards describes the *result*, not the
// input — which would make the drop-count assertion below vacuously true.
const original = { count: payload.bars.length,
                   first: payload.bars[0].t,
                   last: payload.bars[payload.bars.length - 1].t,
                   dates: payload.bars.map((b) => b.t) };

// ── render ──────────────────────────────────────────────────────────────────
const { node, log, fetchCalledWith } = await renderWidget(attrs, structuredClone(payload));

if (node.classList.contains("is-empty")) {
  console.error("widget rendered its 'unavailable' state — chart did not build");
  process.exit(1);
}

const charted = log.candle.data;
const first = charted[0];
const last = charted[charted.length - 1];
const chips = node.querySelectorAll(".kline__legend-chips .kline__ma")
                  .map((c) => c.textContent);
const ranges = node.querySelectorAll(".kline__range").map((b) => b.textContent);
const active = node.querySelectorAll(".kline__range")
                   .filter((b) => b.classList.contains("is-active"))
                   .map((b) => b.textContent);
const foot = node.querySelector(".kline__foot").textContent
                 .replace("Lightweight&nbsp;Charts™", "").trim();
const header = [
  node.querySelector(".kline__sym").textContent,
  node.querySelector(".kline__cur").textContent,
  node.querySelector(".kline__price").textContent,
  node.querySelector(".kline__chg").textContent,
].join("  ");
const readout = node.querySelector(".kline__ohlc").textContent;

const pad = (s) => String(s).padEnd(22);
console.log(`
  ┌─ widget attributes (scraped from the built page) ─────────────────────────
${Object.entries(attrs).map(([k, v]) => `  │ ${pad(k)} ${v}`).join("\n")}
  ├─ payload (derived from data/prices/) ─────────────────────────────────────
  │ ${pad("bars in payload")} ${original.count}
  │ ${pad("payload range")} ${original.first} → ${original.last}
  │ ${pad("payload 'updated'")} ${payload.updated}
  │ ${pad("fetched from")} ${fetchCalledWith}
  ├─ what the chart drew ─────────────────────────────────────────────────────
  │ ${pad("candles")} ${charted.length}
  │ ${pad("charted range")} ${first.time} → ${last.time}
  │ ${pad("last candle OHLC")} O ${last.open}  H ${last.high}  L ${last.low}  C ${last.close}
  │ ${pad("volume bars")} ${log.volume.data.length}
  │ ${pad("MA overlays")} ${chips.join(", ")}
  │ ${pad("MA visible by default")} ${chips.filter((_, i) => log.lines[i].options.visible).join(", ")}
  │ ${pad("MA200 points")} ${log.lines[chips.indexOf("MA200")]?.data?.length ?? "n/a"}
  │ ${pad("range buttons")} ${ranges.join(", ")}   (active: ${active.join(",")})
  ├─ rendered chrome ────────────────────────────────────────────────────────
  │ header   ${header}
  │ readout  ${readout}
  │ footer   ${foot}
  └───────────────────────────────────────────────────────────────────────────`);

// ── contract checks ─────────────────────────────────────────────────────────
const problems = [];
const asOf = attrs["data-as-of"];
if (asOf) {
  if (last.time > asOf) {
    problems.push(`charted past the as-of date (${last.time} > ${asOf})`);
  }
  if (!foot.startsWith("As of") && !foot.startsWith("資料截至")) {
    problems.push(`footer should carry the as-of label, got "${foot}"`);
  }
  // Dropping bars is expected only when the payload actually reaches past the
  // as-of date. A report dated today has nothing to truncate — the newest bar is
  // yesterday's close — so "no bars dropped" is correct there, not a violation.
  const stale = original.dates.filter((t) => t > asOf).length;
  const dropped = original.count - charted.length;
  console.log(`  as-of ${asOf}: payload has ${stale} bar(s) past it, ${dropped} dropped`);
  if (dropped !== stale) {
    problems.push(`expected ${stale} bar(s) dropped by as-of, got ${dropped}`);
  }
}
if (log.volume.data.length !== charted.length) {
  problems.push("volume series length does not match the candles");
}
if (!log.lines.length) problems.push("no moving averages were built");

if (problems.length) {
  console.log("\n  ✗ contract violations:");
  problems.forEach((p) => console.log(`     • ${p}`));
  process.exit(1);
}
console.log("\n  ✓ chart built and all as-of contracts hold\n");
