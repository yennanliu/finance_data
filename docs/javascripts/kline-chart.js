/*
 * kline-chart.js — TradingView-style candlestick (K線) hero chart
 * ================================================================
 * Renders an interactive candlestick + volume chart at the top of every
 * per-ticker report page, with 30D / 180D / 360D range toggles.
 *
 * Powered by TradingView's open-source Lightweight Charts™ (Apache-2.0),
 * vendored at docs/javascripts/lightweight-charts.standalone.production.js.
 *
 * A widget is any element with class `kline-widget` carrying:
 *   data-ticker  — display symbol (e.g. "TSLA")
 *   data-src     — absolute URL to the ticker's OHLCV JSON
 * The markup is injected by scripts/build_docs.py.
 *
 * MkDocs Material runs in instant-navigation (SPA) mode, so we (re)scan on
 * every `document$` emission and re-theme on palette toggles.
 */
(function () {
  "use strict";

  var RANGES = [
    { key: "30", label: "30D", days: 30 },
    { key: "180", label: "180D", days: 180 },
    { key: "360", label: "360D", days: 360 },
  ];
  var DEFAULT_RANGE = "180";

  // Live controllers, so a theme toggle can re-colour every visible chart.
  var live = [];

  // ── theme helpers ────────────────────────────────────────────────────────
  function isDark() {
    return document.body.getAttribute("data-md-color-scheme") !== "default";
  }

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.body).getPropertyValue(name);
    return v && v.trim() ? v.trim() : fallback;
  }

  function palette() {
    var dark = isDark();
    return {
      up: cssVar("--fp-green", dark ? "#22c55e" : "#16a34a"),
      down: cssVar("--fp-red", dark ? "#ef4444" : "#dc2626"),
      text: cssVar("--fp-text-secondary", dark ? "#a1a1aa" : "#52525b"),
      border: cssVar("--fp-border", dark ? "#27272a" : "#e4e4e7"),
      grid: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)",
      // Light MA(20) overlay — a soft blue that reads on both themes.
      ma: dark ? "rgba(96,165,250,0.9)" : "rgba(37,99,235,0.85)",
    };
  }

  // Simple moving average of the close, emitted only where fully defined.
  function sma(bars, period) {
    var out = [];
    var sum = 0;
    for (var i = 0; i < bars.length; i++) {
      sum += bars[i].c;
      if (i >= period) sum -= bars[i - period].c;
      if (i >= period - 1) out.push({ time: bars[i].t, value: sum / period });
    }
    return out;
  }
  var MA_PERIOD = 20;

  // ── formatting ───────────────────────────────────────────────────────────
  function fmtPrice(n) {
    var d = Math.abs(n) < 1 ? 4 : 2;
    return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function shiftDays(isoDate, days) {
    var d = new Date(isoDate + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  }

  // ── one widget ─────────────────────────────────────────────────────────────
  function build(node, data) {
    var LC = window.LightweightCharts;
    var bars = (data && data.bars) || [];
    if (!LC || bars.length < 2) {
      node.classList.add("is-empty");
      node.innerHTML = '<div class="kline__msg">K線圖暫時無法載入 · Chart unavailable</div>';
      return;
    }

    var ticker = node.getAttribute("data-ticker") || data.ticker || "";
    var currency = data.currency || "";
    var last = bars[bars.length - 1];
    var prev = bars[bars.length - 2];
    var change = last.c - prev.c;
    var pct = prev.c ? (change / prev.c) * 100 : 0;
    var up = change >= 0;
    var sign = up ? "+" : "−";

    // ---- scaffold ----
    node.classList.remove("is-empty");
    node.innerHTML =
      '<div class="kline__head">' +
        '<div class="kline__id">' +
          '<span class="kline__sym">' + ticker + '</span>' +
          (currency ? '<span class="kline__cur">' + currency + '</span>' : "") +
          '<span class="kline__price">' + fmtPrice(last.c) + '</span>' +
          '<span class="kline__chg ' + (up ? "is-up" : "is-down") + '">' +
            sign + fmtPrice(Math.abs(change)) + " (" + sign + Math.abs(pct).toFixed(2) + "%)" +
          '</span>' +
          '<span class="kline__ma"><i></i>MA' + MA_PERIOD + '</span>' +
        '</div>' +
        '<div class="kline__ranges" role="group" aria-label="Time range"></div>' +
      '</div>' +
      '<div class="kline__chart"></div>' +
      '<div class="kline__foot">' +
        '<span>更新 ' + (data.updated || "") + '</span>' +
        '<span class="kline__brand">Lightweight&nbsp;Charts™</span>' +
      '</div>';

    var chartEl = node.querySelector(".kline__chart");
    var rangesEl = node.querySelector(".kline__ranges");
    var pal = palette();

    // ---- chart ----
    var chart = LC.createChart(chartEl, {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: pal.text, fontFamily: getComputedStyle(document.body).fontFamily },
      grid: { vertLines: { color: pal.grid }, horzLines: { color: pal.grid } },
      rightPriceScale: { borderColor: pal.border, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderColor: pal.border, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: LC.CrosshairMode.Normal },
      handleScale: { axisPressedMouseMove: false },
      localization: { priceFormatter: function (p) { return fmtPrice(p); } },
    });

    var candle = chart.addCandlestickSeries({
      upColor: pal.up, downColor: pal.down,
      borderUpColor: pal.up, borderDownColor: pal.down,
      wickUpColor: pal.up, wickDownColor: pal.down,
      priceLineVisible: false, lastValueVisible: true,
    });
    candle.setData(bars.map(function (b) {
      return { time: b.t, open: b.o, high: b.h, low: b.l, close: b.c };
    }));

    var volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      lastValueVisible: false, priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(bars.map(function (b) {
      return {
        time: b.t, value: b.v,
        color: b.c >= b.o ? pal.up + "55" : pal.down + "55",
      };
    }));

    // ---- light MA(20) overlay ----
    var maLine = chart.addLineSeries({
      color: pal.ma, lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    });
    maLine.setData(sma(bars, MA_PERIOD));
    // Tint the header legend swatch to match the line.
    var swatch = node.querySelector(".kline__ma i");
    if (swatch) swatch.style.background = pal.ma;

    // ---- range toggle ----
    var firstT = bars[0].t;
    var lastT = last.t;
    function applyRange(days) {
      var from = shiftDays(lastT, days);
      if (from < firstT) from = firstT;
      chart.timeScale().setVisibleRange({ from: from, to: lastT });
    }
    RANGES.forEach(function (r) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "kline__range";
      btn.textContent = r.label;
      btn.setAttribute("data-r", r.key);
      if (r.key === DEFAULT_RANGE) btn.classList.add("is-active");
      btn.addEventListener("click", function () {
        rangesEl.querySelectorAll(".kline__range").forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");
        applyRange(r.days);
      });
      rangesEl.appendChild(btn);
    });
    applyRange(RANGES.filter(function (r) { return r.key === DEFAULT_RANGE; })[0].days);

    // ---- controller (for theme re-colour) ----
    var ctrl = {
      node: node,
      retheme: function () {
        var p = palette();
        chart.applyOptions({
          layout: { textColor: p.text },
          grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
          rightPriceScale: { borderColor: p.border },
          timeScale: { borderColor: p.border },
        });
        candle.applyOptions({
          upColor: p.up, downColor: p.down,
          borderUpColor: p.up, borderDownColor: p.down,
          wickUpColor: p.up, wickDownColor: p.down,
        });
        volume.setData(bars.map(function (b) {
          return { time: b.t, value: b.v, color: b.c >= b.o ? p.up + "55" : p.down + "55" };
        }));
        maLine.applyOptions({ color: p.ma });
        if (swatch) swatch.style.background = p.ma;
      },
    };
    live.push(ctrl);
  }

  // ── scan the page ─────────────────────────────────────────────────────────
  function initAll() {
    live = live.filter(function (c) { return document.body.contains(c.node); });
    var nodes = document.querySelectorAll(".kline-widget:not([data-kline-ready])");
    nodes.forEach(function (node) {
      node.setAttribute("data-kline-ready", "1");
      var src = node.getAttribute("data-src");
      if (!src) return;
      node.innerHTML = '<div class="kline__msg">載入 K線圖 · Loading…</div>';
      fetch(src)
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) { build(node, data); })
        .catch(function () {
          node.classList.add("is-empty");
          node.innerHTML = '<div class="kline__msg">K線圖暫時無法載入 · Chart unavailable</div>';
        });
    });
  }

  // Re-colour on light/dark toggle (Material flips body[data-md-color-scheme]).
  var themeObserver = new MutationObserver(function () {
    live.forEach(function (c) { if (document.body.contains(c.node)) c.retheme(); });
  });
  themeObserver.observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });

  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(initAll); // MkDocs Material instant navigation
  } else {
    document.addEventListener("DOMContentLoaded", initAll);
  }
})();
