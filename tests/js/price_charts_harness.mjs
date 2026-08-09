/*
 * price_charts_harness.mjs — assertions over docs/javascripts/price-charts.js
 * ==========================================================================
 * The renderer for the Price Data section's derived charts. All the arithmetic
 * lives in Python (tests/test_price_analytics.py covers it), so what is left to
 * verify here is the wiring: that each widget fetches its payload, picks the
 * right series out of it, draws the right *kind* of chart, and degrades to a
 * message instead of a broken box when the data isn't there.
 *
 * Runs the shipping file — not a copy — against the DOM shim and a fake
 * Lightweight Charts.
 *
 * Run directly:   node tests/js/price_charts_harness.mjs
 * Run via pytest: tests/test_price_charts_js.py
 * Exit code 0 = all assertions passed; the summary prints either way.
 */

import { renderPriceChart } from "./dom_shim.mjs";

// ── assertions ───────────────────────────────────────────────────────────────
let passed = 0;
const failures = [];

function check(name, cond, detail) {
  if (cond) { passed++; return; }
  failures.push(detail ? `${name}\n      ${detail}` : name);
}

function eq(name, got, want) {
  check(name, JSON.stringify(got) === JSON.stringify(want),
        `expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`);
}

// ── fixtures ────────────────────────────────────────────────────────────────
/** The shape scripts/build_docs.py::analytics_payload writes. */
function payload() {
  const drawdown = [];
  const volatility = [];
  for (let i = 0; i < 40; i++) {
    const d = `2026-01-${String(i + 1).padStart(2, "0")}`;
    drawdown.push({ t: d, v: -(i % 10) });
    volatility.push({ t: d, v: 30 + (i % 5) });
  }
  return {
    ticker: "AMD",
    updated: "2026-02-09",
    summary: { bars: 40 },
    drawdown,
    volatility,
    histogram: [
      { label: "< -10%", from: null, to: -10, count: 2 },
      { label: "-1 to 0%", from: -1, to: 0, count: 9 },
      { label: "0 to 1%", from: 0, to: 1, count: 11 },
      { label: "> 10%", from: 10, to: null, count: 3 },
    ],
  };
}

// ── tests ───────────────────────────────────────────────────────────────────
const data = payload();

// 1. drawdown: an area series over the drawdown key
{
  const { node, log, fetchCalledWith } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "drawdown",
      "data-kind": "area", "data-title": "Drawdown", "data-color": "red" },
    structuredClone(data));

  eq("drawdown: fetches the page-relative payload", fetchCalledWith, "analytics.json");
  eq("drawdown: one area series, no line series", [log.areas.length, log.lines.length], [1, 0]);
  eq("drawdown: draws every point", log.areas[0].data.length, data.drawdown.length);
  eq("drawdown: maps {t,v} to Lightweight Charts {time,value}",
     log.areas[0].data[0], { time: "2026-01-01", value: 0 });
  check("drawdown: fits the whole series into view", log.fitContent);
  check("drawdown: title rendered",
        node.querySelector(".pchart__title").textContent === "Drawdown");
  check("drawdown: readout seeded with the latest point",
        node.querySelector(".pchart__readout").textContent.includes("-9.00%"),
        node.querySelector(".pchart__readout").textContent);
}

// 2. volatility: a line series over a different key of the *same* payload
{
  const { log } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "volatility",
      "data-kind": "line", "data-title": "Volatility", "data-color": "amber" },
    structuredClone(data));

  eq("volatility: one line series, no area series", [log.lines.length, log.areas.length], [1, 0]);
  eq("volatility: reads the volatility key, not drawdown",
     log.lines[0].data[0], { time: "2026-01-01", value: 30 });
}

// 3. crosshair readout follows the pointer and falls back off-chart
{
  const { node, log } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "volatility",
      "data-kind": "line", "data-title": "Volatility" },
    structuredClone(data));

  const series = log.lines[0];
  log.crosshairHandler({ seriesData: new Map([[series, { value: 42.5 }]]) });
  eq("crosshair: readout shows the hovered value",
     node.querySelector(".pchart__readout b").textContent, "42.50%");

  // Leaving the chart must restore the latest value, not blank the header.
  log.crosshairHandler({ seriesData: new Map() });
  eq("crosshair: readout falls back to the latest point",
     node.querySelector(".pchart__readout b").textContent, "34.00%");
}

// 4. histogram: pure DOM bars, no charting library involved
{
  const { node, log } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "histogram",
      "data-kind": "histogram", "data-title": "Distribution" },
    structuredClone(data));

  eq("histogram: draws no chart series at all", log.series.length, 0);
  const bars = node.querySelectorAll(".pchart__hbar");
  eq("histogram: one bar per bucket", bars.length, data.histogram.length);
  // Losing buckets red, gaining buckets green — the "-1 to 0%" bucket is a loss.
  eq("histogram: buckets coloured by sign",
     bars.map((b) => (b.classList.contains("is-down") ? "down" : "up")),
     ["down", "down", "up", "up"]);
  // The tallest bucket sets the scale, so it must reach the full height.
  const fills = node.querySelectorAll(".pchart__hbar-fill");
  check("histogram: the modal bucket is full height",
        fills[2].getAttribute("style") === "height:100.0%",
        fills[2].getAttribute("style"));
  // The bar's meaning lives entirely in its height, so the reading has to be an
  // accessible name — `title` is a pointer-only affordance.
  eq("histogram: each bar is an image with an accessible name",
     bars.map((b) => [b.getAttribute("role"), b.getAttribute("aria-label")])[0],
     ["img", "< -10% · 2 sessions (8.0%)"]);
  check("histogram: total session count in the header",
        node.querySelector(".pchart__meta").textContent.includes("25"),
        node.querySelector(".pchart__meta").textContent);
}

// 5. degradation — a missing key, an empty series, and a failed fetch
{
  const { node } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "nope", "data-kind": "line",
      "data-title": "Missing" },
    structuredClone(data));
  check("missing series: renders a message, not a broken box",
        node.classList.contains("is-empty") && !!node.querySelector(".pchart__msg"));
}

{
  const empty = structuredClone(data);
  empty.volatility = [];
  const { node } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "volatility",
      "data-kind": "line", "data-title": "Volatility" }, empty);
  check("empty series: renders a message",
        node.classList.contains("is-empty"), node.className);
}

{
  const zeroed = structuredClone(data);
  zeroed.histogram = zeroed.histogram.map((b) => ({ ...b, count: 0 }));
  const { node } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "histogram",
      "data-kind": "histogram", "data-title": "Distribution" }, zeroed);
  check("all-zero histogram: renders a message instead of dividing by zero",
        node.classList.contains("is-empty"), node.className);
}

// 6. localisation follows the /zh/ URL, same rule as the K線 widget
{
  const empty = structuredClone(data);
  empty.drawdown = [];
  const { node } = await renderPriceChart(
    { "data-src": "analytics.json", "data-series": "drawdown",
      "data-kind": "area", "data-title": "回撤" }, empty, { zh: true });
  check("zh: the unavailable message is localised",
        node.querySelector(".pchart__msg").textContent.includes("圖表暫時無法載入"),
        node.querySelector(".pchart__msg").textContent);
}

// ── summary ─────────────────────────────────────────────────────────────────
console.log(`${passed} passed, ${failures.length} failed`);
failures.forEach((f) => console.log(`  ✗ ${f}`));
process.exit(failures.length ? 1 : 0);
