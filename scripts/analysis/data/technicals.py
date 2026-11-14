"""Technical-analysis layer: ASCII price & moving-average charts and the
text technical-indicator report. Pure computation, no network.
"""

from __future__ import annotations


def price_ascii_chart(price_series: dict) -> str:
    """Generate ASCII chart from price series."""
    if not price_series:
        return "  (no price history)"
    lines = [f"  {'月份':>7}  {'收盤價':>8}  走勢"]
    min_p = min(price_series.values())
    max_p = max(price_series.values())
    rng = max_p - min_p or 1
    for month, price in price_series.items():
        bars = int((price - min_p) / rng * 30)
        lines.append(f"  {month}  {price:>8.2f}  {'█' * bars}")
    return "\n".join(lines)


def _cluster_levels(levels, tol_pct=0.015):
    """Merge levels within tol_pct of each other into a single averaged level."""
    if not levels:
        return []
    levels = sorted(levels)
    clusters = [[levels[0]]]
    for lv in levels[1:]:
        prev = clusters[-1][-1]
        denom = abs(prev) or 1.0  # guard against zero / negative reference
        if abs(lv - prev) / denom <= tol_pct:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    return [sum(c) / len(c) for c in clusters]


def complete(hist):
    """``hist`` without bars that have no close. Yahoo publishes a new session's
    bar with volume but NaN prices for a while after the close; reading it as
    the latest bar turned every rolling indicator and level into NaN."""
    if hist is None or hist.empty:
        return hist
    return hist[hist["Close"].notna()]


def key_levels(hist) -> dict:
    """Swing-pivot resistances/supports and the 52-week Fibonacci grid.

    ``{"last", "resistance": [R1, R2, R3], "support": [S1, S2, S3],
    "fib": [(label, price), …], "low", "high"}``, or ``{}`` without data.
    The validator compares a report's R1–S3 with these (via front matter).
    """
    hist = complete(hist)
    if hist is None or hist.empty:
        return {}
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]

    last = float(close.iloc[-1])

    # ── Swing pivots (fractal highs/lows over last ~1y of daily bars) ──
    window = 5
    h = high.tail(252).reset_index(drop=True)
    l = low.tail(252).reset_index(drop=True)
    n = len(h)
    swing_highs, swing_lows = [], []
    for i in range(window, n - window):
        seg_h = h.iloc[i - window:i + window + 1]
        seg_l = l.iloc[i - window:i + window + 1]
        if h.iloc[i] == seg_h.max():
            swing_highs.append(float(h.iloc[i]))
        if l.iloc[i] == seg_l.min():
            swing_lows.append(float(l.iloc[i]))

    # Resistances: clustered swing highs at/above current price (nearest first)
    res = [lv for lv in _cluster_levels(swing_highs) if lv >= last]
    res = sorted(res)[:3]
    # Supports: clustered swing lows at/below current price (nearest first)
    sup = [lv for lv in _cluster_levels(swing_lows) if lv <= last]
    sup = sorted(sup, reverse=True)[:3]

    # ── Fibonacci retracement over the 52-week range ──
    hi = float(high.tail(252).max())
    lo = float(low.tail(252).min())
    rng = hi - lo
    fibs = [
        ("0.0%  (52W High)", hi),
        ("23.6%", hi - 0.236 * rng),
        ("38.2%", hi - 0.382 * rng),
        ("50.0%", hi - 0.500 * rng),
        ("61.8%", hi - 0.618 * rng),
        ("78.6%", hi - 0.786 * rng),
        ("100.0% (52W Low)", lo),
    ]

    return {"last": last, "resistance": res, "support": sup, "fib": fibs,
            "low": lo, "high": hi}


def levels_summary(levels: dict) -> str:
    """``"R1 562.23; R2 574.20; S1 496.75"`` for the report's front matter."""
    parts = [f"R{i+1} {v:.2f}" for i, v in enumerate(levels.get("resistance", []))]
    parts += [f"S{i+1} {v:.2f}" for i, v in enumerate(levels.get("support", []))]
    return "; ".join(parts)


def compute_levels(hist) -> str:
    """Compute swing-pivot support/resistance and Fibonacci retracement levels.

    All numbers are derived from the OHLCV data so the LLM can cite them
    verbatim instead of inventing precise-looking price levels.
    """
    try:
        levels = key_levels(hist)
        if not levels:
            return "  (no OHLC data for levels)"
        last, res, sup, fibs = (levels[k] for k in ("last", "resistance", "support", "fib"))
        lo, hi = levels["low"], levels["high"]
        res_lines = [
            f"  R{i+1}:  ${lv:8.2f}   ({(lv/last-1)*100:+.2f}% from price)"
            for i, lv in enumerate(res)
        ] or ["  (no swing-high resistance detected above current price)"]
        sup_lines = [
            f"  S{i+1}:  ${lv:8.2f}   ({(lv/last-1)*100:+.2f}% from price)"
            for i, lv in enumerate(sup)
        ] or ["  (no swing-low support detected below current price)"]

        fib_lines = [
            f"  {label:<18} ${price:8.2f}"
            + ("  ◄ 現價附近" if abs(price - last) / last <= 0.01 else "")
            for label, price in fibs
        ]

        return f"""
  ── 關鍵價位（由 OHLCV 計算，非估算）──
  當前價格:  ${last:.2f}

  阻力位 (Resistance) — 近一年波段高點聚類：
{chr(10).join(res_lines)}

  支撐位 (Support) — 近一年波段低點聚類：
{chr(10).join(sup_lines)}

  ── 斐波那契回調（52週區間 ${lo:.2f} → ${hi:.2f}）──
{chr(10).join(fib_lines)}
"""
    except Exception as exc:
        return f"  (levels computation error: {exc})"


def compute_moving_average_charts(hist) -> str:
    """Generate ASCII charts for moving averages (5, 10, 20, 60, 120, 240 days)."""
    if hist is None or hist.empty:
        return ""

    try:
        import pandas as pd

        close = hist["Close"]
        ma_periods = [5, 10, 20, 60, 120, 240]

        ma_lines = ["  ── 移動平均線 (MA) 走勢 ──"]

        for period in ma_periods:
            if len(close) < period:
                ma_lines.append(f"  MA{period:3d}: (資料不足，需要{period}筆數據)")
                continue

            ma = close.rolling(period).mean()
            last_ma = ma.iloc[-1]

            # Get last 30 values for sparkline
            ma_tail = ma.tail(30)
            if ma_tail.isna().all():
                ma_lines.append(f"  MA{period:3d}: N/A")
                continue

            # Create sparkline
            ma_valid = ma_tail.dropna()
            if len(ma_valid) > 0:
                min_val = ma_valid.min()
                max_val = ma_valid.max()
                rng = max_val - min_val if max_val != min_val else 1

                sparkline = ""
                chars = "▁▂▃▄▅▆▇█"
                for val in ma_valid:
                    pos = int((val - min_val) / rng * 8)
                    pos = max(0, min(pos, len(chars) - 1))  # Clamp to valid range
                    sparkline += chars[pos]

                # Current price vs MA
                current = close.iloc[-1]
                diff = current - last_ma
                pct_diff = (diff / last_ma * 100) if last_ma != 0 else 0
                arrow = "▲" if diff > 0 else "▼" if diff < 0 else "="

                ma_lines.append(
                    f"  MA{period:3d}: ${last_ma:8.2f}  {arrow} {diff:+7.2f} ({pct_diff:+6.2f}%)  {sparkline}"
                )
            else:
                ma_lines.append(f"  MA{period:3d}: N/A")

        return "\n".join(ma_lines)
    except Exception as e:
        return f"  (MA chart error: {e})"


def period_bars(hist, freq: str):
    """OHLCV resampled to ``freq`` ("W" or "ME"), each bar labelled by its
    **last trading day**.

    ``resample`` labels a week by its Sunday and a month by its last calendar
    day, so a report generated on a Thursday cited the week in progress as
    "2026-10-25" — a date in the future. The last bar is the period in progress.
    """
    import pandas as pd

    g = hist.assign(Date=hist.index).groupby(pd.Grouper(freq=freq))
    out = pd.DataFrame({
        "Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(),
        "Close": g["Close"].last(), "Volume": g["Volume"].sum(), "Date": g["Date"].last(),
    }).dropna(subset=["Close", "Date"])
    return out.set_index("Date")


def weekly_bars(hist):
    """Weekly OHLCV, each week labelled by its last trading day."""
    return period_bars(hist, "W")


def monthly_bars(hist):
    """Monthly OHLCV, each month labelled by its last trading day."""
    return period_bars(hist, "ME")


def wilder_rsi(close, n: int = 14):
    """RSI with Wilder smoothing (α = 1/n), NaN until ``n`` changes exist.

    A window with gains and no loss at all is RSI 100, not a division by zero:
    fourteen rising months is the strongest reading there is, and reporting it
    as N/A would also blank that timeframe's direction. A window with no move
    in either direction has no RSI.
    """
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rsi = 100 - (100 / (1 + gain / loss.where(loss > 0)))
    return rsi.mask((loss == 0) & (gain > 0), 100.0)


# 26 bars for the slow EMA plus 9 for the signal line. An EMA will return a
# number from the first bar on; before this many it is mostly its seed value.
MACD_MIN_BARS = 35


def macd_histogram(close):
    """MACD(12/26/9) histogram, all-NaN on fewer than ``MACD_MIN_BARS`` bars.

    Two years of history is ~24 monthly bars, so a monthly MACD is honestly
    N/A rather than a figure the model would quote as a signal.
    """
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist_m = macd - macd.ewm(span=9, adjust=False).mean()
    return hist_m if len(close) >= MACD_MIN_BARS else hist_m * float("nan")


# Each timeframe's trend average, chosen to span a similar stretch of calendar:
# 50 days ≈ 10 weeks, 20 weeks ≈ 100 days, 10 months ≈ 200 days.
TIMEFRAMES = (("日線", "D", 50), ("週線", "W", 20), ("月線", "ME", 10))


def timeframe_snapshot(hist) -> "list[dict]":
    """RSI, MACD histogram, trend average and direction per timeframe, each
    computed on **that timeframe's own bars**.

    The weekly table used to carry the daily RSI and MACD sampled on each
    Friday. Reports then quoted them as weekly: NVDA's "週 RSI 24.9" was its
    daily RSI, while the RSI of its weekly closes was 33 — not oversold.

    Direction: 偏多 when the close is above the average and RSI > 50, 偏空 when
    below and RSI < 50, 中性 otherwise, N/A when either input is missing.
    """
    hist = complete(hist)
    if hist is None or hist.empty:
        return []
    nan = float("nan")
    out = []
    for label, freq, ma_n in TIMEFRAMES:
        close = (hist if freq == "D" else period_bars(hist, freq))["Close"]
        last = float(close.iloc[-1])
        ma = float(close.rolling(ma_n).mean().iloc[-1]) if len(close) >= ma_n else nan
        rsi = float(wilder_rsi(close).iloc[-1])
        macd = float(macd_histogram(close).iloc[-1])
        if ma != ma or rsi != rsi:
            direction = "N/A"
        elif last > ma and rsi > 50:
            direction = "偏多"
        elif last < ma and rsi < 50:
            direction = "偏空"
        else:
            direction = "中性"
        out.append({"label": label, "close": last, "ma_n": ma_n, "ma": ma,
                    "rsi": rsi, "macd_hist": macd, "direction": direction})
    return out


def alignment(snapshot: "list[dict]") -> str:
    """``"2/3 偏空"``: how many timeframes share the leading direction."""
    bull = sum(1 for t in snapshot if t["direction"] == "偏多")
    bear = sum(1 for t in snapshot if t["direction"] == "偏空")
    total = len(snapshot)
    if bull == bear:
        return f"0/{total}（無一致方向）" if bull == 0 else f"{bull}/{total}（多空分歧）"
    return f"{max(bull, bear)}/{total} {'偏多' if bull > bear else '偏空'}"


def timeframe_block(hist) -> str:
    """The multi-timeframe table of the technical context."""
    snap = timeframe_snapshot(hist)
    if not snap:
        return ""
    f2 = lambda v: f"{v:.2f}" if v == v else "N/A"
    f3 = lambda v: f"{v:+.3f}" if v == v else "N/A"
    rows = ["  ── 多時框指標（每個時框皆以該時框自己的 K 棒計算）──",
            "  時框    收盤        趨勢均線            RSI(14)   MACD柱     方向"]
    for t in snap:
        side = "N/A" if t["ma"] != t["ma"] else "▲ 上方" if t["close"] > t["ma"] else "▼ 下方"
        ma = f"MA{t['ma_n']} {f2(t['ma'])} {side}"
        rows.append(f"  {t['label']}  {t['close']:>9.2f}   {ma:<22}{f2(t['rsi']):>7}  "
                    f"{f3(t['macd_hist']):>9}   {t['direction']}")
    rows += [f"  多時框一致性: {alignment(snap)}",
             "  方向規則: 收盤 > 趨勢均線 且 RSI > 50 → 偏多；收盤 < 趨勢均線 且 RSI < 50 → 偏空；"
             "其餘 → 中性；任一數值缺漏 → N/A",
             "  註: 週線、月線的最後一根是進行中的 K 棒（截至最新交易日）。"
             f"MACD 柱需至少 {MACD_MIN_BARS} 根 K 棒，不足則為 N/A。"]
    return "\n".join(rows)


# ── market context: relative strength, gaps, the next earnings date ──────────
# The 2026-11-14 review found no technical report that measured the stock
# against a benchmark or named a dated event, and NVDA's 13% opening gap of
# 2026-11-12 was described as a "long bullish candle". All three are facts
# about the bars and the calendar, so they are computed here.
RS_WINDOWS = (("1 個月", 21), ("3 個月", 63), ("6 個月", 126))
RS_TREND_BARS = 50
GAP_LOOKBACK = 60       # sessions searched for gaps
GAP_MIN_PCT = 1.0       # smaller gaps are noise
GAP_MAX_LISTED = 5


def relative_strength(hist, bench_bars: "list[dict]") -> "dict | None":
    """Return of the stock against a benchmark over ``RS_WINDOWS``, on the
    sessions both have, and whether the price ratio is above its own
    ``RS_TREND_BARS``-session average (the stock is gaining on the benchmark).

    ``bench_bars`` are price-store rows. None when fewer than a month of
    common sessions exists.
    """
    hist = complete(hist)
    if hist is None or hist.empty or not bench_bars:
        return None
    mine = {str(ts)[:10]: float(c) for ts, c in hist["Close"].items()}
    theirs = {b["date"]: float(b["close"]) for b in bench_bars}
    dates = sorted(set(mine) & set(theirs))
    if len(dates) <= RS_WINDOWS[0][1]:
        return None
    rows = []
    for label, n in RS_WINDOWS:
        if len(dates) <= n:
            rows.append({"label": label, "stock": None, "benchmark": None, "excess": None})
            continue
        a, b = dates[-1 - n], dates[-1]
        stock = (mine[b] / mine[a] - 1) * 100
        bench = (theirs[b] / theirs[a] - 1) * 100
        rows.append({"label": label, "stock": stock, "benchmark": bench, "excess": stock - bench})
    ratio = [mine[d] / theirs[d] for d in dates]
    trend = None
    if len(ratio) >= RS_TREND_BARS:
        avg = sum(ratio[-RS_TREND_BARS:]) / RS_TREND_BARS
        trend = "相對走強（比值高於其 50 日均值）" if ratio[-1] > avg else "相對走弱（比值低於其 50 日均值）"
    return {"as_of": dates[-1], "rows": rows, "trend": trend}


def price_gaps(hist, lookback: int = GAP_LOOKBACK, min_pct: float = GAP_MIN_PCT) -> "list[dict]":
    """Gaps in the last ``lookback`` sessions, newest first.

    A gap up is a session whose low is above the previous session's high; a
    gap down, a high below the previous low. Its size is the empty range as a
    percent of the previous close. It is filled once a later session trades
    back through the far edge.
    """
    hist = complete(hist)
    if hist is None or len(hist) < 2:
        return []
    h = hist.tail(lookback + 1)
    highs, lows, closes = h["High"].tolist(), h["Low"].tolist(), h["Close"].tolist()
    out = []
    for i in range(1, len(h)):
        if lows[i] > highs[i - 1]:
            direction, lo, hi = "up", highs[i - 1], lows[i]
            filled = any(low <= lo for low in lows[i + 1:])
        elif highs[i] < lows[i - 1]:
            direction, lo, hi = "down", highs[i], lows[i - 1]
            filled = any(high >= hi for high in highs[i + 1:])
        else:
            continue
        size = (hi - lo) / closes[i - 1] * 100
        if size >= min_pct:
            out.append({"date": str(h.index[i])[:10], "direction": direction,
                        "low": lo, "high": hi, "size_pct": size, "filled": filled})
    return out[::-1]


def market_context(hist, key: "str | None" = None, earnings_date: "str | None" = None) -> str:
    """The 市場脈絡 block: relative strength against the market and sector
    benchmarks from the price store, recent gaps, and the next earnings date."""
    from ..config.benchmarks import BENCHMARK_NAMES, market_benchmark, sector_benchmark
    from . import prices

    hist = complete(hist)
    if hist is None or hist.empty:
        return ""
    rows = ["  ── 市場脈絡（相對強度、缺口、財報日；皆由程式計算）──"]
    benches = []
    for bench in (market_benchmark(key), sector_benchmark(key)) if key else ():
        if bench and bench != (key or "").lower() and bench not in benches:
            benches.append(bench)
    found = False
    for bench in benches:
        rs = relative_strength(hist, prices.load_store(bench))
        if not rs:
            continue
        found = True
        rows.append(f"  相對強度 vs {BENCHMARK_NAMES.get(bench, bench.upper())}（至 {rs['as_of']}，價格報酬）:")
        rows.append("    期間       本股     基準     超額")
        f = lambda v: "N/A" if v is None else f"{v:+.1f}%"
        for r in rs["rows"]:
            rows.append(f"    {r['label']:<8} {f(r['stock']):>7}  {f(r['benchmark']):>7}  {f(r['excess']):>7}")
        rows.append(f"    比值趨勢: {rs['trend'] or 'N/A（共同交易日不足 50 日）'}")
    if not found:
        rows.append("  相對強度: N/A（無可用的基準資料）")

    gaps = price_gaps(hist)
    if gaps:
        rows.append(f"  近 {GAP_LOOKBACK} 個交易日的跳空缺口（≥ {GAP_MIN_PCT:.0f}%，新到舊，最多列 {GAP_MAX_LISTED} 個）:")
        for g in gaps[:GAP_MAX_LISTED]:
            name = "向上跳空" if g["direction"] == "up" else "向下跳空"
            rows.append(f"    {g['date']}  {name}  缺口區間 ${g['low']:.2f}–${g['high']:.2f}"
                        f"（{g['size_pct']:.1f}%）  {'已回補' if g['filled'] else '未回補'}")
    else:
        rows.append(f"  近 {GAP_LOOKBACK} 個交易日的跳空缺口: 無（≥ {GAP_MIN_PCT:.0f}%）")

    last = str(hist.index[-1])[:10]
    if earnings_date:
        from datetime import date
        days = (date.fromisoformat(earnings_date) - date.fromisoformat(last)).days
        rows.append(f"  下次財報日: {earnings_date}（距最新收盤日 {days} 個日曆天；Yahoo Finance，日期可能調整）")
    else:
        rows.append("  下次財報日: N/A（數據未提供）")
    return "\n".join(rows)


def indicator_table(bars, n: int, title: str, prefix: str, date_label: str) -> str:
    """Close, RSI(14), MACD histogram and volume of the last ``n`` bars, the
    indicators computed on these bars and named for their timeframe."""
    rsi, macd = wilder_rsi(bars["Close"]), macd_histogram(bars["Close"])
    rows = [f"  ── {title} ──",
            f"  {date_label}    收盤   {prefix}RSI(14)  {prefix}MACD柱    {prefix}成交量"]
    for ts, b in bars.tail(n).iterrows():
        r, m = rsi.get(ts, float("nan")), macd.get(ts, float("nan"))
        rows.append(f"  {str(ts)[:10]}  {b['Close']:>8.2f}  "
                    + (f"{r:>8.1f}" if r == r else f"{'N/A':>8}") + "  "
                    + (f"{m:>+9.3f}" if m == m else f"{'N/A':>9}")
                    + f"  {b['Volume']:>14,.0f}")
    return "\n".join(rows)


def ohlc_table(bars, title: str) -> str:
    """Plain OHLCV rows, so candlestick claims can be checked against real bars."""
    rows = [f"  ── {title} ──",
            "  日期            開        高        低        收         成交量"]
    for ts, b in bars.iterrows():
        rows.append(f"  {str(ts)[:10]}  {b['Open']:>8.2f}  {b['High']:>8.2f}  "
                    f"{b['Low']:>8.2f}  {b['Close']:>8.2f}  {b['Volume']:>13,.0f}")
    return "\n".join(rows)


def compute_technicals(hist, key: "str | None" = None,
                       earnings_date: "str | None" = None) -> str:
    """Compute technical indicators from OHLCV history DataFrame.

    ``key`` (the report key) and ``earnings_date`` add the 市場脈絡 block; the
    technical report passes them, other callers get the indicators alone.
    """
    hist = complete(hist)
    if hist is None or hist.empty:
        return "  (no OHLC data)"
    try:
        import pandas as pd
        import numpy as np

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        # Moving averages
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        # RSI-14, Wilder smoothing (α = 1/14) as every charting site uses. The
        # 14-day simple mean used before (Cutler's RSI) read INTC at 14.5 where
        # the standard RSI was 36.4, and called 7 of 24 tickers oversold that
        # were not.
        rsi = wilder_rsi(close)

        # MACD (12/26/9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_m = macd - signal

        # Bollinger Bands (20, 2σ)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_up = bb_mid + 2 * bb_std
        bb_lo = bb_mid - 2 * bb_std
        bb_pct = (close - bb_lo) / (bb_up - bb_lo).replace(0, float("nan"))

        # ATR-14
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14 = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()  # Wilder

        # Stochastic %K/%D (14,3,3)
        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        stoch_k = 100 * (close - low14) / (high14 - low14).replace(0, float("nan"))
        stoch_d = stoch_k.rolling(3).mean()

        # ADX-14 (trend strength)
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr14_adx = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14_adx.replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
        adx = dx.ewm(alpha=1/14, adjust=False).mean()

        # OBV (On-Balance Volume)
        obv_direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * obv_direction).cumsum()
        obv_ma20 = obv.rolling(20).mean()

        # Volume
        avg_vol_20 = volume.rolling(20).mean()
        avg_vol_50 = volume.rolling(50).mean()

        # Last values
        last = close.iloc[-1]
        last_ma20 = ma20.iloc[-1]
        last_ma50 = ma50.iloc[-1]
        last_ma200 = ma200.iloc[-1] if len(close) >= 200 else float("nan")
        last_rsi = rsi.iloc[-1]
        last_macd = macd.iloc[-1]
        last_signal = signal.iloc[-1]
        last_hist_m = hist_m.iloc[-1]
        last_bb_up = bb_up.iloc[-1]
        last_bb_lo = bb_lo.iloc[-1]
        last_bb_pct = bb_pct.iloc[-1]
        last_atr = atr14.iloc[-1]
        last_stoch_k = stoch_k.iloc[-1]
        last_stoch_d = stoch_d.iloc[-1]
        last_adx = adx.iloc[-1]
        last_plus_di = plus_di.iloc[-1]
        last_minus_di = minus_di.iloc[-1]
        last_obv = obv.iloc[-1]
        last_obv_ma = obv_ma20.iloc[-1]
        last_vol = volume.iloc[-1]
        last_avg_vol = avg_vol_20.iloc[-1]
        last_avg_vol50 = avg_vol_50.iloc[-1]

        # 52-week position
        w52_high = float(high.tail(252).max())
        w52_low = float(low.tail(252).min())
        w52_pct = (last - w52_low) / (w52_high - w52_low) * 100 if w52_high != w52_low else 50

        # RSI divergence hint (last 20 bars)
        price_20 = close.tail(20)
        rsi_20 = rsi.tail(20)
        price_dir = "⬆" if price_20.iloc[-1] > price_20.iloc[0] else "⬇"
        rsi_dir = "⬆" if rsi_20.iloc[-1] > rsi_20.iloc[0] else "⬇"
        divergence = ""
        if rsi_20.iloc[0] != rsi_20.iloc[0] or rsi_20.iloc[-1] != rsi_20.iloc[-1]:
            # A NaN end compares false and would read as a falling RSI.
            divergence = "N/A（RSI 數據不足）"
        elif price_dir == "⬆" and rsi_dir == "⬇":
            divergence = "⚠️ 頂背離 (Bearish Divergence)"
        elif price_dir == "⬇" and rsi_dir == "⬆":
            divergence = "⚠️ 底背離 (Bullish Divergence)"
        else:
            divergence = "無明顯背離"

        # Weekly and monthly tables carry indicators computed on their own
        # bars; the daily ones sampled on a Friday are not weekly indicators.
        weekly = weekly_bars(hist)
        monthly = monthly_bars(hist)

        na = lambda v: f"{v:.2f}" if v == v else "N/A"
        na3 = lambda v: f"{v:.3f}" if v == v else "N/A"
        vol = lambda v: f"{v:,.0f}" if v == v else "N/A"

        vol_ratio = last_vol / last_avg_vol if last_avg_vol > 0 else float("nan")
        obv_trend = "OBV > MA → 量能支撐上漲" if last_obv > last_obv_ma else "OBV < MA → 量能疲弱"

        atr_pct = last_atr / last * 100 if last > 0 else float("nan")

        # Get MA charts
        ma_charts = compute_moving_average_charts(hist)

        # Computed support/resistance + Fibonacci levels
        levels = compute_levels(hist)

        return f"""
  ── 當前技術指標快照 ──
  收盤價:       ${last:.2f}
  52W 高/低:    ${w52_high:.2f} / ${w52_low:.2f}  (目前位於52W區間 {w52_pct:.1f}%)
  ATR(14):      ${na(last_atr)}  ({na(atr_pct)}% of price, Wilder) — 每日波動參考

  ── 均線系統 ──
  MA20:         ${na(last_ma20)}   {'▲ 上方' if last > last_ma20 else '▼ 下方'}
  MA50:         ${na(last_ma50)}   {'▲ 上方' if last > last_ma50 else '▼ 下方'}
  MA200:        ${na(last_ma200)}  {'▲ 上方' if last_ma200 == last_ma200 and last > last_ma200 else '▼ 下方' if last_ma200 == last_ma200 else 'N/A'}
  均線排列:     {'多頭排列 MA20>MA50>MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 > last_ma50 > last_ma200 else '空頭排列 MA20<MA50<MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 < last_ma50 < last_ma200 else '混合排列'}

{ma_charts}

  ── 動能指標 ──
  RSI(14):      {na(last_rsi)}  (Wilder)  {'N/A' if last_rsi != last_rsi else '🔴 超買 >70' if last_rsi > 70 else '🟢 超賣 <30' if last_rsi < 30 else '🟡 中性 30-70'}
  RSI 背離:     {divergence}  (僅比較近20根K棒首尾的價格與RSI方向)
  MACD:         {na3(last_macd)}
  MACD Signal:  {na3(last_signal)}
  MACD Hist:    {last_hist_m:+.3f}  {'🟢 看多' if last_hist_m > 0 else '🔴 看空'}
  Stoch %K:     {na(last_stoch_k)}  Stoch %D: {na(last_stoch_d)}  {'超買' if last_stoch_k > 80 else '超賣' if last_stoch_k < 20 else '中性'}

  ── 趨勢強度 (ADX) ──
  ADX(14):      {na(last_adx)}  {'強趨勢 >25' if last_adx > 25 else '弱趨勢/盤整 <25'}
  +DI:          {na(last_plus_di)}  -DI: {na(last_minus_di)}  {'多頭主導' if last_plus_di > last_minus_di else '空頭主導'}

  ── 布林通道 ──
  BB上軌:       ${na(last_bb_up)}
  BB中軌(MA20): ${na(last_ma20)}
  BB下軌:       ${na(last_bb_lo)}
  BB %B:        {na(last_bb_pct)}  (0=下軌, 0.5=中軌, 1=上軌)

  ── 成交量 ──
  最新成交量:   {last_vol:,.0f}
  20日均量:     {vol(last_avg_vol)}  (量比: {na(vol_ratio)}x)
  50日均量:     {vol(last_avg_vol50)}
  OBV趨勢:      {obv_trend}
{levels}

{timeframe_block(hist)}

{market_context(hist, key, earnings_date) if key else ""}

{indicator_table(weekly, 20, "近20週收盤走勢（RSI、MACD 柱皆以週K計算）", "週", "週末交易日")}

{indicator_table(monthly, 12, "近12個月收盤走勢（RSI、MACD 柱皆以月K計算）", "月", "月末交易日")}

{ohlc_table(hist.tail(10), "近10根日K (開高低收)")}

{ohlc_table(weekly.tail(8), "近8根週K (開高低收，以該週最後交易日標示)")}
"""
    except Exception as exc:
        return f"  (technical indicator error: {exc})"
