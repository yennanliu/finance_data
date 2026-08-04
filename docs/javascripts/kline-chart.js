/*
 * kline-chart.js — TradingView-style candlestick (K線) hero chart
 * ================================================================
 * Renders an interactive candlestick + volume chart at the top of every
 * per-ticker report page, with 30D / 180D / 360D range toggles, several
 * toggleable moving-average overlays, and a live OHLC / volume readout.
 *
 * Powered by TradingView's open-source Lightweight Charts™ (Apache-2.0),
 * vendored at docs/javascripts/lightweight-charts.standalone.production.js.
 *
 * A widget is any element with class `kline-widget` carrying:
 *   data-ticker  — display symbol (e.g. "TSLA")
 *   data-src     — URL to the ticker's OHLCV JSON, relative to the page
 * and optionally, so one renderer serves both the live ticker index and dated
 * report bodies:
 *   data-as-of   — "YYYY-MM-DD"; drop bars after this date. Dated reports must
 *                  show the prices they were written about, not today's.
 *   data-ma      — overlays to build, e.g. "30+,60+,200" ("+" = on by default)
 *   data-range   — initially selected range key (e.g. "180")
 *   data-ranges  — range buttons to offer, e.g. "30,180,360"
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

  // Moving-average overlays. `on` is the default visibility; every line can be
  // toggled independently from the header legend, so users can show them all
  // together or narrow down to a single average.
  var MA_LINES = [
    { period: 20, on: true },
    { period: 60, on: true },
    { period: 120, on: false },
  ];

  // ── per-widget option parsing ────────────────────────────────────────────
  // Each widget may override the module defaults through data-* attributes, so
  // the ticker index and a dated technical report can share one renderer.
  function parseMa(spec) {
    if (!spec) return MA_LINES;
    var out = [];
    spec.split(",").forEach(function (tok) {
      tok = tok.trim();
      if (!tok) return;
      var on = /\+$/.test(tok);           // "60+" → visible by default
      var period = parseInt(tok, 10);
      if (period > 0) out.push({ period: period, on: on });
    });
    return out.length ? out : MA_LINES;
  }

  function parseRanges(spec) {
    if (!spec) return RANGES;
    var out = [];
    spec.split(",").forEach(function (tok) {
      var days = parseInt(String(tok).trim(), 10);
      if (days > 0) out.push({ key: String(days), label: days + "D", days: days });
    });
    return out.length ? out : RANGES;
  }

  function readOpts(node) {
    var ranges = parseRanges(node.getAttribute("data-ranges"));
    var wanted = (node.getAttribute("data-range") || "").trim();
    var pick = ranges.filter(function (r) { return r.key === wanted; })[0];
    if (!pick) {
      pick = ranges.filter(function (r) { return r.key === DEFAULT_RANGE; })[0] ||
             ranges[ranges.length - 1];
    }
    return {
      asOf: (node.getAttribute("data-as-of") || "").trim(),
      maLines: parseMa(node.getAttribute("data-ma")),
      ranges: ranges,
      defaultRange: pick.key,
    };
  }

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
      crosshair: dark ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.35)",
      watermark: dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.035)",
      // Distinct, theme-aware colours for each moving-average line. Periods a
      // widget may request via data-ma but that aren't listed here fall back to
      // the neutral colour, so an unrecognised period still draws.
      ma: {
        20: dark ? "#60a5fa" : "#2563eb", // blue
        30: dark ? "#60a5fa" : "#2563eb", // blue  (technical reports use MA30)
        50: dark ? "#34d399" : "#059669", // green
        60: dark ? "#fbbf24" : "#f59e0b", // amber
        120: dark ? "#c084fc" : "#9333ea", // violet
        200: dark ? "#fb923c" : "#ea580c", // orange
      },
    };
  }

  // Colour for a moving-average period, with a neutral fallback.
  function maColor(pal, period) {
    return pal.ma[period] || pal.text;
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

  // ── formatting ───────────────────────────────────────────────────────────
  function fmtPrice(n) {
    var d = Math.abs(n) < 1 ? 4 : 2;
    return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function fmtVol(n) {
    if (!n && n !== 0) return "—";
    var abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (abs >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(2) + "K";
    return String(n);
  }

  function shiftDays(isoDate, days) {
    var d = new Date(isoDate + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  }

  // Normalise a Lightweight-Charts time (string or {year,month,day}) to ISO.
  function timeToIso(t) {
    if (t == null) return null;
    if (typeof t === "string") return t;
    if (typeof t === "object" && t.year) {
      var mm = ("0" + t.month).slice(-2);
      var dd = ("0" + t.day).slice(-2);
      return t.year + "-" + mm + "-" + dd;
    }
    return String(t);
  }

  // ── i18n ─────────────────────────────────────────────────────────────────
  // The site is one MkDocs build (theme.language=en), so <html lang> is "en"
  // on every page; the Traditional-Chinese pages are only distinguished by a
  // "/zh/" URL path. Detect that to localise the widget's own strings.
  function isZh() {
    return /\/zh\//.test(location.pathname);
  }
  function labels() {
    return isZh()
      ? { o: "開", h: "高", l: "低", c: "收", v: "量",
          updated: "更新", asOf: "資料截至", loading: "載入 K線圖…",
          unavailable: "K線圖暫時無法載入" }
      : { o: "O", h: "H", l: "L", c: "C", v: "Vol",
          updated: "Updated", asOf: "As of", loading: "Loading chart…",
          unavailable: "Chart unavailable" };
  }

  // ── one widget ─────────────────────────────────────────────────────────────
  function build(node, data, opts) {
    var LC = window.LightweightCharts;
    var bars = (data && data.bars) || [];
    var L = labels();
    opts = opts || { maLines: MA_LINES, ranges: RANGES, defaultRange: DEFAULT_RANGE };
    if (!LC || bars.length < 2) {
      node.classList.add("is-empty");
      node.innerHTML = '<div class="kline__msg">' + L.unavailable + '</div>';
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

    // Index bars by date for the crosshair readout (bar + previous close).
    var byTime = {};
    for (var i = 0; i < bars.length; i++) {
      byTime[bars[i].t] = { bar: bars[i], prevClose: i > 0 ? bars[i - 1].c : bars[i].o };
    }

    // ---- scaffold ----
    node.classList.remove("is-empty");
    var maChips = opts.maLines.map(function (m) {
      return (
        '<button type="button" class="kline__ma' + (m.on ? " is-on" : "") + '" ' +
        'data-p="' + m.period + '" aria-pressed="' + m.on + '">' +
        '<i></i>MA' + m.period + "</button>"
      );
    }).join("");

    node.innerHTML =
      '<div class="kline__head">' +
        '<div class="kline__id">' +
          '<span class="kline__sym">' + ticker + '</span>' +
          (currency ? '<span class="kline__cur">' + currency + '</span>' : "") +
          '<span class="kline__price">' + fmtPrice(last.c) + '</span>' +
          '<span class="kline__chg ' + (up ? "is-up" : "is-down") + '">' +
            sign + fmtPrice(Math.abs(change)) + " (" + sign + Math.abs(pct).toFixed(2) + "%)" +
          '</span>' +
        '</div>' +
        '<div class="kline__legend-chips">' + maChips + '</div>' +
        '<div class="kline__ranges" role="group" aria-label="Time range"></div>' +
      '</div>' +
      '<div class="kline__chart">' +
        '<div class="kline__ohlc" aria-hidden="true"></div>' +
      '</div>' +
      '<div class="kline__foot">' +
        // An as-of chart is pinned to a past date, so reporting the store's own
        // "updated" stamp would claim a freshness the chart does not have.
        '<span>' + (opts.asOf ? L.asOf + ' ' + last.t
                              : L.updated + ' ' + (data.updated || "")) + '</span>' +
        '<span class="kline__brand">Lightweight&nbsp;Charts™</span>' +
      '</div>';

    var chartEl = node.querySelector(".kline__chart");
    var ohlcEl = node.querySelector(".kline__ohlc");
    var rangesEl = node.querySelector(".kline__ranges");
    var pal = palette();

    // ---- chart ----
    var chart = LC.createChart(chartEl, {
      autoSize: true,
      layout: {
        background: { type: "solid", color: "transparent" },
        textColor: pal.text,
        fontFamily: getComputedStyle(document.body).fontFamily,
        fontSize: 12,
      },
      grid: { vertLines: { color: pal.grid }, horzLines: { color: pal.grid } },
      rightPriceScale: { borderColor: pal.border, scaleMargins: { top: 0.12, bottom: 0.26 } },
      timeScale: { borderColor: pal.border, fixLeftEdge: true, fixRightEdge: true, rightOffset: 2 },
      crosshair: {
        mode: LC.CrosshairMode.Magnet,
        vertLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
        horzLine: { color: pal.crosshair, width: 1, style: LC.LineStyle.Dashed, labelBackgroundColor: pal.text },
      },
      handleScale: { axisPressedMouseMove: false },
      watermark: {
        visible: !!ticker,
        text: ticker,
        color: pal.watermark,
        fontSize: 64,
        fontStyle: "bold",
        horzAlign: "center",
        vertAlign: "center",
      },
      localization: { priceFormatter: function (p) { return fmtPrice(p); } },
    });

    var candle = chart.addCandlestickSeries({
      upColor: pal.up, downColor: pal.down,
      borderUpColor: pal.up, borderDownColor: pal.down,
      wickUpColor: pal.up, wickDownColor: pal.down,
      priceLineVisible: true, priceLineStyle: LC.LineStyle.Dashed, priceLineWidth: 1,
      lastValueVisible: true,
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

    // ---- moving-average overlays ----
    var maSeries = opts.maLines.map(function (m) {
      var line = chart.addLineSeries({
        color: maColor(pal, m.period), lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        visible: m.on,
      });
      line.setData(sma(bars, m.period));
      return { period: m.period, on: m.on, series: line };
    });

    // Colour the legend swatches to match their lines; wire up toggling.
    var chipEls = node.querySelectorAll(".kline__legend-chips .kline__ma");
    function paintChips() {
      var p = palette();
      chipEls.forEach(function (chip) {
        var period = +chip.getAttribute("data-p");
        var sw = chip.querySelector("i");
        if (sw) sw.style.background = maColor(p, period);
      });
    }
    paintChips();
    chipEls.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var period = +chip.getAttribute("data-p");
        var rec = maSeries.filter(function (s) { return s.period === period; })[0];
        if (!rec) return;
        rec.on = !rec.on;
        rec.series.applyOptions({ visible: rec.on });
        chip.classList.toggle("is-on", rec.on);
        chip.setAttribute("aria-pressed", String(rec.on));
      });
    });

    // ---- live OHLC / volume readout ----
    function renderReadout(rec) {
      if (!rec) { ohlcEl.innerHTML = ""; return; }
      var b = rec.bar;
      var ch = b.c - rec.prevClose;
      var cp = rec.prevClose ? (ch / rec.prevClose) * 100 : 0;
      var cls = ch >= 0 ? "is-up" : "is-down";
      var s = ch >= 0 ? "+" : "−";
      ohlcEl.innerHTML =
        '<span class="kline__ohlc-date">' + b.t + '</span>' +
        '<span>' + L.o + ' <b>' + fmtPrice(b.o) + '</b></span>' +
        '<span>' + L.h + ' <b class="is-up">' + fmtPrice(b.h) + '</b></span>' +
        '<span>' + L.l + ' <b class="is-down">' + fmtPrice(b.l) + '</b></span>' +
        '<span>' + L.c + ' <b>' + fmtPrice(b.c) + '</b></span>' +
        '<span class="' + cls + '">' + s + fmtPrice(Math.abs(ch)) + " (" + s + Math.abs(cp).toFixed(2) + "%)</span>" +
        '<span>' + L.v + ' <b>' + fmtVol(b.v) + '</b></span>';
    }
    renderReadout(byTime[last.t]);
    chart.subscribeCrosshairMove(function (param) {
      var iso = param && param.time ? timeToIso(param.time) : null;
      renderReadout((iso && byTime[iso]) || byTime[last.t]);
    });

    // ---- range toggle ----
    var firstT = bars[0].t;
    var lastT = last.t;
    function applyRange(days) {
      var from = shiftDays(lastT, days);
      if (from < firstT) from = firstT;
      chart.timeScale().setVisibleRange({ from: from, to: lastT });
    }
    opts.ranges.forEach(function (r) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "kline__range";
      btn.textContent = r.label;
      btn.setAttribute("data-r", r.key);
      if (r.key === opts.defaultRange) btn.classList.add("is-active");
      btn.addEventListener("click", function () {
        rangesEl.querySelectorAll(".kline__range").forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");
        applyRange(r.days);
      });
      rangesEl.appendChild(btn);
    });
    var initial = opts.ranges.filter(function (r) { return r.key === opts.defaultRange; })[0]
                  || opts.ranges[opts.ranges.length - 1];
    applyRange(initial.days);

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
          crosshair: {
            vertLine: { color: p.crosshair, labelBackgroundColor: p.text },
            horzLine: { color: p.crosshair, labelBackgroundColor: p.text },
          },
          watermark: { color: p.watermark },
        });
        candle.applyOptions({
          upColor: p.up, downColor: p.down,
          borderUpColor: p.up, borderDownColor: p.down,
          wickUpColor: p.up, wickDownColor: p.down,
        });
        volume.setData(bars.map(function (b) {
          return { time: b.t, value: b.v, color: b.c >= b.o ? p.up + "55" : p.down + "55" };
        }));
        maSeries.forEach(function (s) { s.series.applyOptions({ color: maColor(p, s.period) }); });
        paintChips();
      },
      // Free the Lightweight Charts instance (and its resize observer /
      // listeners) when the widget's node leaves the DOM under MkDocs
      // Material's instant navigation, so we don't leak a chart per page view.
      destroy: function () { chart.remove(); },
    };
    live.push(ctrl);
  }

  // ── scan the page ─────────────────────────────────────────────────────────
  function initAll() {
    // Drop controllers whose node has left the DOM, disposing each chart so
    // instant navigation doesn't leak a Lightweight Charts instance per view.
    live = live.filter(function (c) {
      if (document.body.contains(c.node)) return true;
      if (c.destroy) c.destroy();
      return false;
    });
    var nodes = document.querySelectorAll(".kline-widget:not([data-kline-ready])");
    nodes.forEach(function (node) {
      node.setAttribute("data-kline-ready", "1");
      var src = node.getAttribute("data-src");
      if (!src) return;
      var L = labels();
      var opts = readOpts(node);
      node.innerHTML = '<div class="kline__msg">' + L.loading + '</div>';
      fetch(src)
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) {
          // Truncate before build() so every downstream computation — moving
          // averages, volume colours, the readout, range clamping — is as-of
          // correct without needing to know about as-of at all.
          if (opts.asOf && data && data.bars) {
            data.bars = data.bars.filter(function (b) { return b.t <= opts.asOf; });
          }
          build(node, data, opts);
        })
        .catch(function () {
          node.classList.add("is-empty");
          node.innerHTML = '<div class="kline__msg">' + L.unavailable + '</div>';
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
