/*
 * price-charts.js — derived-analytics charts for the Price Data section
 * ======================================================================
 * Companion to kline-chart.js. Where that renders raw candles, this renders the
 * series scripts/analysis/data/price_analytics.py derives from the same store:
 * drawdown, rolling volatility and the daily-return histogram.
 *
 * All the maths happens in Python at build time — this file only draws. That
 * split keeps the numbers testable in pytest and keeps the payload small: each
 * page fetches one analytics.json holding pre-computed {t, v} points.
 *
 * A widget is any element with class `pchart` carrying:
 *   data-src     — URL to analytics.json, relative to the page
 *   data-series  — key inside that JSON ("drawdown" | "volatility" | "histogram")
 *   data-kind    — "area" | "line" | "histogram"
 *   data-title   — heading shown above the chart
 * and optionally:
 *   data-unit    — suffix for values in the readout (default "%")
 *   data-color   — "red" | "amber" | "blue" (default "blue")
 *
 * The markup is injected by scripts/build_docs.py. Like the K線 widget, we
 * (re)scan on every MkDocs Material `document$` emission and re-theme on a
 * palette toggle.
 */
(function () {
  "use strict";

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
      red: cssVar("--fp-red", dark ? "#ef4444" : "#dc2626"),
      green: cssVar("--fp-green", dark ? "#22c55e" : "#16a34a"),
      amber: dark ? "#fbbf24" : "#f59e0b",
      blue: dark ? "#60a5fa" : "#2563eb",
      text: cssVar("--fp-text-secondary", dark ? "#a1a1aa" : "#52525b"),
      border: cssVar("--fp-border", dark ? "#27272a" : "#e4e4e7"),
      grid: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)",
      crosshair: dark ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.35)",
    };
  }

  function seriesColor(pal, name) {
    return pal[name] || pal.blue;
  }

  // Lightweight Charts wants an opaque top and a transparent bottom for an
  // area fill; the payload colours are hex, so append 8-bit alpha.
  function alpha(hex, aa) {
    return /^#[0-9a-fA-F]{6}$/.test(hex) ? hex + aa : hex;
  }

  // ── formatting ───────────────────────────────────────────────────────────
  function fmtNum(n, unit) {
    if (n == null || isNaN(n)) return "—";
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (unit || "");
  }

  function isZh() {
    return /\/zh\//.test(location.pathname);
  }

  function labels() {
    return isZh()
      ? { loading: "載入圖表…", unavailable: "圖表暫時無法載入", latest: "最新",
          days: "天", sessions: "交易日" }
      : { loading: "Loading chart…", unavailable: "Chart unavailable", latest: "Latest",
          days: "days", sessions: "sessions" };
  }

  function readOpts(node) {
    // data-unit is read with an explicit null check, not `||`: an empty
    // data-unit means "this series has no unit", which `||` would turn into "%".
    var unit = node.getAttribute("data-unit");
    return {
      series: (node.getAttribute("data-series") || "").trim(),
      kind: (node.getAttribute("data-kind") || "line").trim(),
      title: (node.getAttribute("data-title") || "").trim(),
      unit: unit === null ? "%" : unit,
      color: (node.getAttribute("data-color") || "blue").trim(),
    };
  }

  // ── histogram: plain DOM bars ────────────────────────────────────────────
  // A distribution has no time axis, so Lightweight Charts buys nothing here —
  // a handful of divs is lighter, and stays readable without JS re-layout.
  function buildHistogram(node, buckets, opts, L) {
    var total = buckets.reduce(function (s, b) { return s + b.count; }, 0);
    var peak = buckets.reduce(function (m, b) { return Math.max(m, b.count); }, 0);
    if (!total || !peak) {
      node.classList.add("is-empty");
      node.innerHTML = '<div class="pchart__msg">' + L.unavailable + "</div>";
      return null;
    }

    var bars = buckets.map(function (b) {
        // Colour by sign of the bucket: losing sessions red, gaining green. The
        // zero-crossing bucket ("-1 to 0%") counts as a loss, which is what it is.
        var neg = b.to != null ? b.to <= 0 : false;
        var share = (b.count / total) * 100;
        // The bar is a graphic whose meaning is entirely in its height, so it
        // carries the reading as an accessible name — `title` alone is a
        // pointer-only affordance and never reaches a keyboard or screen reader.
        var desc = b.label + " · " + b.count + " " + L.sessions +
                   " (" + share.toFixed(1) + "%)";
        return (
          '<div class="pchart__hbar' + (neg ? " is-down" : " is-up") + '" ' +
          'role="img" aria-label="' + desc + '" title="' + desc + '">' +
          '<div class="pchart__hbar-fill" style="height:' +
          ((b.count / peak) * 100).toFixed(1) + '%"></div>' +
          '<span class="pchart__hbar-label">' + b.label.replace(" to ", "–") + "</span>" +
          "</div>"
        );
      }).join("");

    node.innerHTML =
      (opts.title ? '<div class="pchart__head"><span class="pchart__title">' +
        opts.title + "</span><span class=\"pchart__meta\">" + total + " " + L.sessions +
        "</span></div>" : "") +
      '<div class="pchart__hist">' + bars + "</div>";
    return null;  // nothing to re-theme: the bars are pure CSS
  }

  // ── time series: Lightweight Charts ──────────────────────────────────────
  function buildSeries(node, points, opts, L) {
    var LC = window.LightweightCharts;
    if (!LC || points.length < 2) {
      node.classList.add("is-empty");
      node.innerHTML = '<div class="pchart__msg">' + L.unavailable + "</div>";
      return null;
    }

    var pal = palette();
    var color = seriesColor(pal, opts.color);
    var last = points[points.length - 1];

    node.innerHTML =
      '<div class="pchart__head">' +
        '<span class="pchart__title">' + opts.title + "</span>" +
        '<span class="pchart__readout">' + L.latest + " " +
          '<b>' + fmtNum(last.v, opts.unit) + "</b>" +
        "</span>" +
      "</div>" +
      '<div class="pchart__canvas"></div>';

    var readout = node.querySelector(".pchart__readout b");
    var chart = LC.createChart(node.querySelector(".pchart__canvas"), {
      autoSize: true,
      layout: {
        background: { type: "solid", color: "transparent" },
        textColor: pal.text,
        fontFamily: getComputedStyle(document.body).fontFamily,
        fontSize: 11,
      },
      grid: { vertLines: { color: pal.grid }, horzLines: { color: pal.grid } },
      rightPriceScale: { borderColor: pal.border, scaleMargins: { top: 0.1, bottom: 0.08 } },
      timeScale: { borderColor: pal.border, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        mode: LC.CrosshairMode.Normal,
        vertLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
        horzLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
      },
      handleScale: { axisPressedMouseMove: false },
      localization: { priceFormatter: function (p) { return p.toFixed(0) + (opts.unit || ""); } },
    });

    var series = opts.kind === "area"
      ? chart.addAreaSeries({
          lineColor: color, lineWidth: 2,
          topColor: alpha(color, "44"), bottomColor: alpha(color, "05"),
          priceLineVisible: false, lastValueVisible: false,
        })
      : chart.addLineSeries({
          color: color, lineWidth: 2,
          priceLineVisible: false, lastValueVisible: false,
        });
    series.setData(points.map(function (p) { return { time: p.t, value: p.v }; }));
    chart.timeScale().fitContent();

    // Crosshair readout — falls back to the latest point off-chart, so the
    // header never goes blank when the pointer leaves.
    chart.subscribeCrosshairMove(function (param) {
      var v = param && param.seriesData ? param.seriesData.get(series) : null;
      readout.textContent = fmtNum(v ? v.value : last.v, opts.unit);
    });

    return {
      node: node,
      retheme: function () {
        var p = palette();
        var c = seriesColor(p, opts.color);
        chart.applyOptions({
          layout: { textColor: p.text },
          grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
          rightPriceScale: { borderColor: p.border },
          timeScale: { borderColor: p.border },
          crosshair: {
            vertLine: { color: p.crosshair, labelBackgroundColor: p.text },
            horzLine: { color: p.crosshair, labelBackgroundColor: p.text },
          },
        });
        series.applyOptions(opts.kind === "area"
          ? { lineColor: c, topColor: alpha(c, "44"), bottomColor: alpha(c, "05") }
          : { color: c });
      },
      destroy: function () { chart.remove(); },
    };
  }

  // ── scan the page ────────────────────────────────────────────────────────
  function initAll() {
    live = live.filter(function (c) {
      if (document.body.contains(c.node)) return true;
      if (c.destroy) c.destroy();
      return false;
    });

    var nodes = document.querySelectorAll(".pchart:not([data-pchart-ready])");
    nodes.forEach(function (node) {
      node.setAttribute("data-pchart-ready", "1");
      var src = node.getAttribute("data-src");
      var opts = readOpts(node);
      var L = labels();
      if (!src || !opts.series) return;
      node.innerHTML = '<div class="pchart__msg">' + L.loading + "</div>";
      fetch(src)
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) {
          var payload = (data && data[opts.series]) || [];
          var ctrl = opts.kind === "histogram"
            ? buildHistogram(node, payload, opts, L)
            : buildSeries(node, payload, opts, L);
          if (ctrl) live.push(ctrl);
        })
        .catch(function () {
          node.classList.add("is-empty");
          node.innerHTML = '<div class="pchart__msg">' + L.unavailable + "</div>";
        });
    });
  }

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
