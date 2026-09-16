/*
 * price-charts.js — derived-analytics charts for the Market Data section
 * ======================================================================
 * Companion to kline-chart.js. Where that renders raw candles, this renders the
 * series scripts/analysis/data/price_analytics.py derives from the same store:
 * drawdown, rolling volatility and the daily-return histogram.
 *
 * All the maths happens in Python at build time — this file only draws. That
 * split keeps the numbers testable in pytest and keeps the payload small: each
 * page fetches one analytics.json holding pre-computed {t, v} points.
 *
 * It also draws the financial series from fundamental_analytics.py — the same
 * contract, more shapes.
 *
 * A widget is any element with class `pchart` carrying:
 *   data-src     — URL to the JSON payload, relative to the page
 *   data-series  — key inside that JSON, or a comma-separated list of keys to
 *                  draw several series on one chart
 *   data-kind    — "line" | "area" | "histogram" | "bars" | "bars+line"
 *                  | "multiline" | "stacked"
 *   data-title   — heading shown above the chart
 * and optionally:
 *   data-unit    — suffix for values on the right axis (default "%")
 *   data-unit2   — suffix for values on the left axis (default "%")
 *   data-color   — palette name, or one per series (default "blue")
 *   data-labels  — legend label per series (default: the series key)
 *   data-format  — "plain" | "percent" | "money" for the right axis
 *   data-format2 — same, for the left axis (default "percent")
 *   data-note    — one line saying what the chart means, shown under the title
 *   data-ylabel  — caption for the right axis (falls back to the unit)
 *   data-ylabel2 — caption for the left axis (falls back to unit2)
 *   data-xlabel  — caption for the time axis, e.g. "Fiscal quarter"
 *   data-ref / data-ref-label — a horizontal reference line (a historical
 *                  average, say) and the name to print against it. Python
 *                  computes the value; this file only draws it.
 *
 * "bars+line" puts the first series on the right axis as bars and the rest on
 * the left as lines — a revenue bar and its growth rate cannot share a scale.
 * "stacked" expects Python to have emitted cumulative values, because
 * Lightweight Charts does not stack.
 *
 * The markup is injected by scripts/build_docs.py. Like the K線 widget, we
 * (re)scan on every MkDocs Material `document$` emission and re-theme on a
 * palette toggle.
 *
 * Charts build lazily, as they scroll into view. A merged Market Data page
 * carries twenty-odd of them, most inside a collapsed tab — a hidden container
 * has no width, so a chart built there would lay out against zero pixels.
 */
(function () {
  "use strict";

  var live = [];
  // Observers from previous scans, disconnected on the next one: under instant
  // navigation an observer still watching detached nodes is never collected.
  var watchers = [];

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
      violet: dark ? "#a78bfa" : "#7c3aed",
      teal: dark ? "#2dd4bf" : "#0d9488",
      pink: dark ? "#f472b6" : "#db2777",
      text: cssVar("--fp-text-secondary", dark ? "#a1a1aa" : "#52525b"),
      muted: cssVar("--fp-text-muted", dark ? "#71717a" : "#71717a"),
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
          days: "天", sessions: "交易日", avg: "平均", count: "交易日數",
          bucket: "單日漲跌幅" }
      : { loading: "Loading chart…", unavailable: "Chart unavailable", latest: "Latest",
          days: "days", sessions: "sessions", avg: "Average", count: "Sessions",
          bucket: "Daily return" };
  }

  function csv(value, fallback) {
    var s = (value === null || value === undefined ? "" : value).trim();
    if (!s) return fallback ? [fallback] : [];
    return s.split(",").map(function (x) { return x.trim(); });
  }

  /** A numeric data-attribute, or null when absent or unparseable. */
  function num(value) {
    if (value === null || value === undefined || String(value).trim() === "") return null;
    var n = parseFloat(value);
    return isNaN(n) ? null : n;
  }

  function readOpts(node) {
    // data-unit is read with an explicit null check, not `||`: an empty
    // data-unit means "this series has no unit", which `||` would turn into "%".
    var unit = node.getAttribute("data-unit");
    return {
      // A comma-separated list draws several series on one chart; a bare name
      // still means one, so every existing widget reads the same as before.
      series: csv(node.getAttribute("data-series")),
      kind: (node.getAttribute("data-kind") || "line").trim(),
      title: (node.getAttribute("data-title") || "").trim(),
      unit: unit === null ? "%" : unit,
      unit2: node.getAttribute("data-unit2") || "%",
      color: csv(node.getAttribute("data-color"), "blue"),
      // How to render an axis value: money abbreviates to $1.2B, percent and
      // plain print two decimals. Financial figures run to twelve digits, so
      // the default axis labels would be unreadable.
      format: (node.getAttribute("data-format") || "plain").trim(),
      format2: (node.getAttribute("data-format2") || "percent").trim(),
      labels: csv(node.getAttribute("data-labels")),
      // What the chart means, and what each axis is counting. A P/E line is
      // only readable by someone who already knows what P/E is; these turn the
      // picture into something you can read cold.
      note: (node.getAttribute("data-note") || "").trim(),
      ylabel: (node.getAttribute("data-ylabel") || "").trim(),
      ylabel2: (node.getAttribute("data-ylabel2") || "").trim(),
      xlabel: (node.getAttribute("data-xlabel") || "").trim(),
      ref: num(node.getAttribute("data-ref")),
      refLabel: (node.getAttribute("data-ref-label") || "").trim(),
    };
  }

  // ── value formatting ─────────────────────────────────────────────────────
  function fmtMoney(n) {
    if (n == null || isNaN(n)) return "—";
    var abs = Math.abs(n), sign = n < 0 ? "-" : "";
    var units = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
    for (var i = 0; i < units.length; i++) {
      if (abs >= units[i][0]) {
        return sign + "$" + (abs / units[i][0]).toFixed(2) + units[i][1];
      }
    }
    return sign + "$" + abs.toFixed(2);
  }

  function formatter(kind, unit) {
    if (kind === "money") return fmtMoney;
    return function (n) { return fmtNum(n, unit); };
  }

  /** What an axis is counting, when the page did not say. The unit is the
   *  honest minimum: "%" or "×" reads as an axis caption on its own. */
  function axisCaption(explicit, format, unit) {
    if (explicit) return explicit;
    if (format === "money") return "USD";
    return unit || "";
  }

  /** Escape text bound for innerHTML. Every caller passes build-time strings,
   *  but these land in markup, so they get the same treatment regardless. */
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── chart chrome shared by every kind ────────────────────────────────────
  // Head (title + legend/readout), the explainer note, the plot flanked by its
  // y-axis captions, and a footer carrying the x-axis caption and the span the
  // chart covers. Kept in one place so a histogram and a P/E river are framed
  // identically.
  function frame(opts, parts) {
    return (
      '<div class="pchart__head">' +
        '<span class="pchart__title">' + esc(opts.title) + "</span>" +
        (parts.aside || "") +
      "</div>" +
      (opts.note ? '<p class="pchart__note">' + esc(opts.note) + "</p>" : "") +
      '<div class="pchart__plot">' +
        (parts.yLeft
          ? '<span class="pchart__ylab pchart__ylab--left">' + esc(parts.yLeft) + "</span>"
          : "") +
        parts.body +
        (parts.yRight
          ? '<span class="pchart__ylab pchart__ylab--right">' + esc(parts.yRight) + "</span>"
          : "") +
      "</div>" +
      ((opts.xlabel || parts.span)
        ? '<div class="pchart__foot">' +
            '<span class="pchart__xlab">' + esc(opts.xlabel || "") + "</span>" +
            '<span class="pchart__span">' + esc(parts.span || "") + "</span>" +
          "</div>"
        : "")
    );
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
          'role="img" aria-label="' + esc(desc) + '" title="' + esc(desc) + '">' +
          '<span class="pchart__hbar-count">' + b.count + "</span>" +
          '<div class="pchart__hbar-fill" style="height:' +
          ((b.count / peak) * 100).toFixed(1) + '%"></div>' +
          '<span class="pchart__hbar-label">' + esc(b.label.replace(" to ", "–")) + "</span>" +
          "</div>"
        );
      }).join("");

    // The bars carry their own counts and the tallest bucket is named in the
    // footer, so the height scale is readable without a drawn y axis.
    node.innerHTML = frame(opts, {
      aside: '<span class="pchart__meta">' + total + " " + L.sessions + "</span>",
      yLeft: opts.ylabel || L.count,
      yRight: "",
      body: '<div class="pchart__hist">' + bars + "</div>",
      span: "0 – " + peak + " " + L.sessions,
    });
    return null;  // nothing to re-theme: the bars are pure CSS
  }

  // ── time series: Lightweight Charts ──────────────────────────────────────
  // One builder for every time-based kind. `datasets` is one entry per series:
  //   {points, color, shape: "line"|"area"|"bars", axis: "right"|"left", label}
  // Which is a deliberate flattening — a bars+line combo and a three-line
  // margin chart differ only in the shapes and axes their series ask for.
  function plan(opts, payload) {
    var kind = opts.kind;
    var names = opts.series;
    var out = [];
    for (var i = 0; i < names.length; i++) {
      var points = payload[names[i]] || [];
      var shape, axis;
      if (kind === "bars" || kind === "stacked") {
        shape = "bars";
        axis = "right";
      } else if (kind === "bars+line") {
        // The bar series carries the money figure and the line its growth rate,
        // so they cannot share a scale — billions and percent on one axis makes
        // the percent a flat line at zero.
        shape = i === 0 ? "bars" : "line";
        axis = i === 0 ? "right" : "left";
      } else {
        shape = kind === "area" ? "area" : "line";
        axis = "right";
      }
      out.push({
        name: names[i],
        points: points,
        color: opts.color[i] || opts.color[opts.color.length - 1] || "blue",
        label: opts.labels[i] || names[i],
        shape: shape,
        axis: axis,
      });
    }
    // Stacked bars are drawn largest-first so the smaller series paints over
    // the larger one: Lightweight Charts has no stacking, and Python already
    // emits cumulative values for exactly this reason.
    //
    // Because the values are cumulative, the readout for the outer series is
    // the running total, not that band's own contribution — so the caller must
    // label it as the total. Labelling it after the top component would make
    // the crosshair report R&D + SG&A as SG&A.
    if (kind === "stacked") out.reverse();
    return out;
  }

  /** First and last timestamp across every drawn series, as "start → end". */
  function spanOf(datasets) {
    var first = null, last = null;
    datasets.forEach(function (d) {
      if (!d.points.length) return;
      var a = d.points[0].t, b = d.points[d.points.length - 1].t;
      if (first === null || a < first) first = a;
      if (last === null || b > last) last = b;
    });
    return first && last ? first + " → " + last : "";
  }

  function buildSeries(node, payload, opts, L) {
    var LC = window.LightweightCharts;
    var datasets = plan(opts, payload).filter(function (d) {
      return d.points && d.points.length;
    });
    var drawable = datasets.filter(function (d) { return d.points.length >= 2; });
    if (!LC || !drawable.length) {
      node.classList.add("is-empty");
      node.innerHTML = '<div class="pchart__msg">' + L.unavailable + "</div>";
      return null;
    }

    var pal = palette();
    var hasLeft = datasets.some(function (d) { return d.axis === "left"; });
    var fmtRight = formatter(opts.format, opts.unit);
    var fmtLeft = formatter(opts.format2, opts.unit2);

    // A multi-series chart names its series in the header; a single one keeps
    // the latest-value readout it has always had. Either way the header opens
    // showing numbers — the values only used to appear once you hovered, which
    // left a five-line P/E-band legend saying nothing at all.
    var legend = datasets.length > 1
      ? datasets.map(function (d) {
          // The label is carried as an attribute so the crosshair handler can
          // rebuild "Gross 65.00%" without having to re-derive it from text it
          // has already overwritten.
          // The value lives in its own <b> so the crosshair can rewrite it
          // without taking the colour swatch with it.
          var fmt = d.axis === "left" ? fmtLeft : fmtRight;
          var seed = d.points.length ? fmt(d.points[d.points.length - 1].v) : "—";
          return '<span class="pchart__key" data-series="' + esc(d.name) + '"' +
            ' data-label="' + esc(d.label) + '">' +
            '<i style="background:' + seriesColor(pal, d.color) + '"></i>' +
            "<b>" + esc(d.label) + " " + seed + "</b></span>";
        }).join("")
      : "";
    var last = datasets[0].points[datasets[0].points.length - 1];

    node.innerHTML = frame(opts, {
      aside: legend
        ? '<span class="pchart__legend">' + legend + "</span>"
        : '<span class="pchart__readout">' + L.latest + " " +
          "<b>" + fmtRight(last.v) + "</b></span>",
      yLeft: hasLeft ? axisCaption(opts.ylabel2, opts.format2, opts.unit2) : "",
      yRight: axisCaption(opts.ylabel, opts.format, opts.unit),
      body: '<div class="pchart__canvas"></div>',
      span: spanOf(datasets),
    });

    var readout = node.querySelector(".pchart__readout b");
    var spanEl = node.querySelector(".pchart__span");
    var spanText = spanEl ? spanEl.textContent : "";
    var chart = LC.createChart(node.querySelector(".pchart__canvas"), {
      autoSize: true,
      layout: {
        background: { type: "solid", color: "transparent" },
        textColor: pal.text,
        fontFamily: getComputedStyle(document.body).fontFamily,
        fontSize: 11,
      },
      grid: { vertLines: { color: pal.grid }, horzLines: { color: pal.grid } },
      rightPriceScale: {
        visible: true,
        borderColor: pal.border,
        scaleMargins: { top: 0.12, bottom: 0.1 },
      },
      leftPriceScale: {
        visible: hasLeft,
        borderColor: pal.border,
        scaleMargins: { top: 0.12, bottom: 0.1 },
      },
      // The date axis is the chart's other half of the story: without it the
      // shape floats free of when it happened.
      timeScale: {
        visible: true,
        borderColor: pal.border,
        fixLeftEdge: true,
        fixRightEdge: true,
        minBarSpacing: 0.05,
      },
      crosshair: {
        mode: LC.CrosshairMode.Normal,
        vertLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
        horzLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
      },
      handleScale: { axisPressedMouseMove: false },
    });

    var made = datasets.map(function (d) {
      var color = seriesColor(pal, d.color);
      var fmt = d.axis === "left" ? fmtLeft : fmtRight;
      var common = {
        priceScaleId: d.axis,
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: { type: "custom", formatter: fmt },
      };
      var s;
      if (d.shape === "bars") {
        s = chart.addHistogramSeries(Object.assign({ color: color }, common));
      } else if (d.shape === "area") {
        s = chart.addAreaSeries(Object.assign({
          lineColor: color, lineWidth: 2,
          topColor: alpha(color, "44"), bottomColor: alpha(color, "05"),
        }, common));
      } else {
        s = chart.addLineSeries(Object.assign({
          color: color, lineWidth: 2,
        }, common));
      }
      s.setData(d.points.map(function (p) { return { time: p.t, value: p.v }; }));
      return { series: s, def: d, fmt: fmt };
    });

    // A reference line — the historical average of the series, say. Python
    // computed the number; drawing it is what turns "P/E is 32×" into "P/E is
    // 32× against a 26× ten-year average".
    if (opts.ref !== null && made.length && made[0].series.createPriceLine) {
      made[0].series.createPriceLine({
        price: opts.ref,
        color: pal.muted,
        lineWidth: 1,
        lineStyle: LC.LineStyle.Dashed,
        axisLabelVisible: true,
        title: (opts.refLabel || L.avg) + " " + made[0].fmt(opts.ref),
      });
    }

    chart.timeScale().fitContent();

    // Crosshair readout. With one series the header shows its value; with
    // several, each legend entry picks up its own — so a margin chart reads
    // all three at the hovered quarter rather than making you guess. The footer
    // swaps the covered span for the hovered date, which is the x-axis value
    // spelled out rather than eyeballed off a tick.
    var keys = {};
    node.querySelectorAll(".pchart__key").forEach(function (el) {
      keys[el.getAttribute("data-series")] = el;
    });
    chart.subscribeCrosshairMove(function (param) {
      if (spanEl) {
        spanEl.textContent = param && param.time ? String(param.time) : spanText;
      }
      made.forEach(function (m) {
        var hit = param && param.seriesData ? param.seriesData.get(m.series) : null;
        var pts = m.def.points;
        var v = hit ? hit.value : (pts.length ? pts[pts.length - 1].v : null);
        if (readout && m === made[0]) readout.textContent = m.fmt(v);
        var key = keys[m.def.name];
        if (key) {
          key.querySelector("b").textContent =
            key.getAttribute("data-label") + " " + m.fmt(v);
        }
      });
    });

    return {
      node: node,
      retheme: function () {
        var p = palette();
        chart.applyOptions({
          layout: { textColor: p.text },
          grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
          rightPriceScale: { borderColor: p.border },
          leftPriceScale: { borderColor: p.border },
          timeScale: { borderColor: p.border },
          crosshair: {
            vertLine: { color: p.crosshair, labelBackgroundColor: p.text },
            horzLine: { color: p.crosshair, labelBackgroundColor: p.text },
          },
        });
        made.forEach(function (m) {
          var c = seriesColor(p, m.def.color);
          m.series.applyOptions(m.def.shape === "area"
            ? { lineColor: c, topColor: alpha(c, "44"), bottomColor: alpha(c, "05") }
            : { color: c });
          var key = keys[m.def.name];
          if (key) key.querySelector("i").style.background = c;
        });
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

    // Every widget on a page usually reads the same payload — twenty-odd of
    // them on a Market Data page, four on a report page — and fetch() does not
    // coalesce concurrent requests for one URL. Share the promise instead, so
    // a page makes one request per distinct src rather than one per chart.
    // Scoped to this scan: all widgets on a page are initialised in this loop,
    // and a navigation starts a fresh scan with a fresh payload.
    // Null-prototype: the keys are URLs from the page, and a plain object would
    // hand back Object.prototype.constructor for a src named "constructor".
    var pending = Object.create(null);
    function payloadFor(src) {
      if (!pending[src]) {
        pending[src] = fetch(src).then(function (r) {
          if (!r.ok) throw new Error(r.status);
          return r.json();
        });
      }
      return pending[src];
    }

    function build(node) {
      var src = node.getAttribute("data-src");
      var opts = readOpts(node);
      var L = labels();
      if (!src || !opts.series.length) return;
      payloadFor(src)
        .then(function (data) {
          // The histogram still takes one named series; every time-based kind
          // takes the whole payload and picks its own out of it, so a chart can
          // draw several.
          var ctrl = opts.kind === "histogram"
            ? buildHistogram(node, (data && data[opts.series[0]]) || [], opts, L)
            : buildSeries(node, data || {}, opts, L);
          if (ctrl) live.push(ctrl);
        })
        .catch(function () {
          node.classList.add("is-empty");
          node.innerHTML = '<div class="pchart__msg">' + L.unavailable + "</div>";
        });
    }

    watchers.forEach(function (w) { w.disconnect(); });
    watchers = [];

    var nodes = document.querySelectorAll(".pchart:not([data-pchart-ready])");
    // Lazy build. A chart inside a collapsed tab has a zero-width container, so
    // building it there lays it out against no pixels; waiting for it to be on
    // screen also keeps a twenty-chart page from doing twenty layouts at once.
    // Without IntersectionObserver every chart builds immediately, which is the
    // behaviour this file has always had.
    var io = typeof IntersectionObserver === "function"
      ? new IntersectionObserver(function (entries, obs) {
          entries.forEach(function (e) {
            if (!e.isIntersecting) return;
            obs.unobserve(e.target);
            build(e.target);
          });
        }, { rootMargin: "200px 0px" })
      : null;
    if (io) watchers.push(io);

    nodes.forEach(function (node) {
      node.setAttribute("data-pchart-ready", "1");
      // The placeholder goes in on the scan, not on the build: a card that is
      // still waiting to be scrolled to should hold its place and say so,
      // rather than sit as an empty box that jumps open later.
      node.innerHTML = '<div class="pchart__msg">' + labels().loading + "</div>";
      if (io) io.observe(node);
      else build(node);
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
