/*
 * kline_chart_harness.mjs — assertions over docs/javascripts/kline-chart.js
 * ========================================================================
 * The widget is the only part of the chart pipeline pytest cannot reach, and it
 * owns the per-widget option handling (data-as-of, data-ma, data-range,
 * data-ranges). This runs the *shipping* file — not a copy — against the DOM
 * shim and a fake Lightweight Charts, then asserts on what the chart was
 * actually asked to draw.
 *
 * Run directly:   node tests/js/kline_chart_harness.mjs
 * Run via pytest: tests/test_kline_chart_js.py
 * Exit code 0 = all assertions passed; the summary prints either way.
 */

import { renderWidget } from "./dom_shim.mjs";

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
/** `n` consecutive weekday-ish bars ending at 2026-08-03, rising by $1. */
function payload(n = 400) {
  const bars = [];
  const end = new Date(Date.UTC(2026, 7, 3));
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(end.getTime() - i * 86400000);
    const c = 100 + (n - i);
    bars.push({
      t: d.toISOString().slice(0, 10),
      o: c - 1, h: c + 2, l: c - 2, c: c, v: 1000000 + i,
    });
  }
  return { ticker: "AMD", symbol: "AMD", currency: "USD", updated: "2026-08-03", bars };
}

function periodsOf(log) {
  // MA line series are created in data-ma order after candle + volume.
  return log.lines.map((s) => s.options.color);
}

// ── tests ───────────────────────────────────────────────────────────────────
const data = payload();

// 1. index-page widget: module defaults
{
  const { node, log, fetchCalledWith } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json" }, structuredClone(data));

  eq("index: fetches the page-relative payload", fetchCalledWith, "kline.json");
  check("index: candlestick series built", !!log.candle);
  check("index: volume series built", !!log.volume);
  eq("index: three MA overlays (20/60/120)", log.lines.length, 3);
  // Assert the periods, not just the count: the default visibility pattern is
  // [on, on, off] for both the index and report presets, so visibility alone
  // cannot tell them apart.
  eq("index: legend lists MA20/60/120",
     node.querySelectorAll(".kline__legend-chips .kline__ma").map((c) => c.textContent),
     ["MA20", "MA60", "MA120"]);
  eq("index: MA20 and MA60 visible, MA120 hidden",
     log.lines.map((s) => s.options.visible), [true, true, false]);
  eq("index: three range buttons",
     node.querySelectorAll(".kline__ranges .kline__range").map((b) => b.textContent),
     ["30D", "180D", "360D"]);
  eq("index: 180D is the active range",
     node.querySelectorAll(".kline__range").filter((b) => b.classList.contains("is-active"))
         .map((b) => b.textContent), ["180D"]);
  check("index: footer reports the store's updated stamp",
        node.querySelector(".kline__foot").textContent.includes("Updated 2026-08-03"),
        node.querySelector(".kline__foot").textContent);
  check("index: no as-of label", !node.querySelector(".kline__foot").textContent.includes("As of"));
  eq("index: all bars charted", log.candle.data.length, data.bars.length);
}

// 2. report-page widget: as-of truncation is the point of the exercise
{
  const asOf = "2026-07-10";
  const { node, log } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "../kline.json",
      "data-as-of": asOf, "data-ma": "30+,60+,200" }, structuredClone(data));

  const charted = log.candle.data;
  eq("report: last charted bar is the as-of date", charted[charted.length - 1].time, asOf);
  check("report: nothing after the as-of date is charted",
        charted.every((b) => b.time <= asOf));
  check("report: bars were actually dropped", charted.length < data.bars.length,
        `charted ${charted.length} of ${data.bars.length}`);

  eq("report: MA overlays follow data-ma", log.lines.length, 3);
  eq("report: legend lists MA30/60/200 from data-ma, not the defaults",
     node.querySelectorAll(".kline__legend-chips .kline__ma").map((c) => c.textContent),
     ["MA30", "MA60", "MA200"]);
  eq("report: MA30/60 on, MA200 off by default",
     log.lines.map((s) => s.options.visible), [true, true, false]);
  check("report: MA200 got its own colour, not the neutral fallback",
        periodsOf(log)[2] && periodsOf(log)[2] !== periodsOf(log)[0],
        JSON.stringify(periodsOf(log)));

  // Volume colours and the readout must also respect as-of, which they do for
  // free because truncation happens before build().
  eq("report: volume series truncated too", log.volume.data.length, charted.length);
  const readout = node.querySelector(".kline__ohlc").textContent;
  check("report: readout shows the as-of bar", readout.includes(asOf), readout);

  const foot = node.querySelector(".kline__foot").textContent;
  check("report: footer says 'As of', not 'Updated'",
        foot.includes("As of " + asOf) && !foot.includes("Updated"), foot);

  // The header quote reflects the as-of bar, not today's price.
  const price = node.querySelector(".kline__price").textContent;
  const expected = charted[charted.length - 1].close;
  check("report: header price is the as-of close",
        price.replace(/,/g, "").startsWith(String(expected)),
        `header "${price}" vs as-of close ${expected}`);
}

// 3. option parsing edge cases
{
  const { log } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json", "data-ma": "50" },
    structuredClone(data));
  eq("data-ma without '+' builds a hidden overlay",
     log.lines.map((s) => s.options.visible), [false]);
}
{
  const { log } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json", "data-ma": "  ,,  " },
    structuredClone(data));
  eq("unparseable data-ma falls back to the defaults", log.lines.length, 3);
}
{
  const { node } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json",
      "data-ranges": "90,270", "data-range": "270" }, structuredClone(data));
  eq("data-ranges replaces the button set",
     node.querySelectorAll(".kline__range").map((b) => b.textContent), ["90D", "270D"]);
  eq("data-range selects one of them",
     node.querySelectorAll(".kline__range").filter((b) => b.classList.contains("is-active"))
         .map((b) => b.textContent), ["270D"]);
}
{
  const { node } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json",
      "data-ranges": "90,270", "data-range": "999" }, structuredClone(data));
  eq("a data-range outside data-ranges falls back rather than selecting nothing",
     node.querySelectorAll(".kline__range").filter((b) => b.classList.contains("is-active")).length,
     1);
}

// 4. degenerate data
{
  const { node } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "../kline.json", "data-as-of": "2019-01-01" },
    structuredClone(data));
  check("an as-of before all data degrades to the unavailable message",
        node.classList.contains("is-empty"), node.className);
}
{
  const { node } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json" },
    { ticker: "AMD", currency: "USD", updated: "2026-08-03", bars: [] });
  check("an empty payload degrades to the unavailable message",
        node.classList.contains("is-empty"), node.className);
}

// 5. localisation
{
  const { node } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "../kline.json", "data-as-of": "2026-07-10" },
    structuredClone(data), { zh: true });
  check("zh pages localise the as-of label",
        node.querySelector(".kline__foot").textContent.includes("資料截至"),
        node.querySelector(".kline__foot").textContent);
}

// 6. range toggling drives the chart
{
  const { node, log } = await renderWidget(
    { "data-ticker": "AMD", "data-src": "kline.json" }, structuredClone(data));
  const before = log.visibleRanges.length;
  node.querySelectorAll(".kline__range").filter((b) => b.textContent === "30D")[0].click();
  check("clicking a range sets a new visible range", log.visibleRanges.length > before);
  eq("clicking a range moves the active class",
     node.querySelectorAll(".kline__range").filter((b) => b.classList.contains("is-active"))
         .map((b) => b.textContent), ["30D"]);
}

// ── report ──────────────────────────────────────────────────────────────────
console.log(`\n  kline-chart.js harness: ${passed} passed, ${failures.length} failed`);
if (failures.length) {
  console.log("\n  FAILURES:");
  failures.forEach((f, i) => console.log(`   ${i + 1}. ${f}`));
  process.exit(1);
}
process.exit(0);
