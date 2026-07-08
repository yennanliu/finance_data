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
        if abs(lv - clusters[-1][-1]) / clusters[-1][-1] <= tol_pct:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    return [sum(c) / len(c) for c in clusters]


def compute_levels(hist) -> str:
    """Compute swing-pivot support/resistance and Fibonacci retracement levels.

    All numbers are derived from the OHLCV data so the LLM can cite them
    verbatim instead of inventing precise-looking price levels.
    """
    if hist is None or hist.empty:
        return "  (no OHLC data for levels)"
    try:
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
        res = [lv for lv in _cluster_levels(swing_highs) if lv >= last * 0.999]
        res = sorted(res)[:3]
        # Supports: clustered swing lows at/below current price (nearest first)
        sup = [lv for lv in _cluster_levels(swing_lows) if lv <= last * 1.001]
        sup = sorted(sup, reverse=True)[:3]

        res_lines = [
            f"  R{i+1}:  ${lv:8.2f}   ({(lv/last-1)*100:+.2f}% from price)"
            for i, lv in enumerate(res)
        ] or ["  (no swing-high resistance detected above current price)"]
        sup_lines = [
            f"  S{i+1}:  ${lv:8.2f}   ({(lv/last-1)*100:+.2f}% from price)"
            for i, lv in enumerate(sup)
        ] or ["  (no swing-low support detected below current price)"]

        # ── Fibonacci retracement over the 52-week range ──
        hi = float(high.tail(252).max())
        lo = float(low.tail(252).min())
        rng = hi - lo or 1.0
        fibs = [
            ("0.0%  (52W High)", hi),
            ("23.6%", hi - 0.236 * rng),
            ("38.2%", hi - 0.382 * rng),
            ("50.0%", hi - 0.500 * rng),
            ("61.8%", hi - 0.618 * rng),
            ("78.6%", hi - 0.786 * rng),
            ("100.0% (52W Low)", lo),
        ]
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


def compute_technicals(hist) -> str:
    """Compute technical indicators from OHLCV history DataFrame."""
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

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

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
        atr14 = tr.rolling(14).mean()

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
        if price_dir == "⬆" and rsi_dir == "⬇":
            divergence = "⚠️ 頂背離 (Bearish Divergence)"
        elif price_dir == "⬇" and rsi_dir == "⬆":
            divergence = "⚠️ 底背離 (Bullish Divergence)"
        else:
            divergence = "無明顯背離"

        # Weekly OHLCV table (last 20 weeks)
        weekly_close = close.resample("W").last().dropna().tail(20)
        weekly_volume = volume.resample("W").sum().dropna().tail(20)
        ohlcv_lines = ["  日期          收盤      RSI     MACD柱    週成交量"]
        for wdt in weekly_close.index:
            wdt_str = wdt.strftime("%Y-%m-%d")
            wc = weekly_close.get(wdt, float("nan"))
            try:
                idx_slice = rsi[rsi.index <= wdt]
                wr = float(idx_slice.iloc[-1]) if not idx_slice.empty else float("nan")
            except Exception:
                wr = float("nan")
            try:
                idx_slice = hist_m[hist_m.index <= wdt]
                wm = float(idx_slice.iloc[-1]) if not idx_slice.empty else float("nan")
            except Exception:
                wm = float("nan")
            wv = weekly_volume.get(wdt, float("nan"))
            try:
                ohlcv_lines.append(
                    f"  {wdt_str}  {wc:>8.2f}  {wr:>6.1f}  {wm:>+8.3f}  {wv:>12,.0f}"
                )
            except Exception:
                pass

        na = lambda v: f"{v:.2f}" if v == v else "N/A"
        na3 = lambda v: f"{v:.3f}" if v == v else "N/A"

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
  ATR(14):      ${na(last_atr)}  ({na(atr_pct)}% of price) — 每日波動參考

  ── 均線系統 ──
  MA20:         ${na(last_ma20)}   {'▲ 上方' if last > last_ma20 else '▼ 下方'}
  MA50:         ${na(last_ma50)}   {'▲ 上方' if last > last_ma50 else '▼ 下方'}
  MA200:        ${na(last_ma200)}  {'▲ 上方' if last_ma200 == last_ma200 and last > last_ma200 else '▼ 下方' if last_ma200 == last_ma200 else 'N/A'}
  均線排列:     {'多頭排列 MA20>MA50>MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 > last_ma50 > last_ma200 else '空頭排列 MA20<MA50<MA200' if last_ma20 == last_ma20 and last_ma50 == last_ma50 and last_ma200 == last_ma200 and last_ma20 < last_ma50 < last_ma200 else '混合排列'}

{ma_charts}

  ── 動能指標 ──
  RSI(14):      {na(last_rsi)}    {'🔴 超買 >70' if last_rsi > 70 else '🟢 超賣 <30' if last_rsi < 30 else '🟡 中性 30-70'}
  RSI 背離:     {divergence}
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
  20日均量:     {last_avg_vol:,.0f}  (量比: {na(vol_ratio)}x)
  50日均量:     {last_avg_vol50:,.0f}
  OBV趨勢:      {obv_trend}
{levels}
  ── 近20週收盤走勢 ──
{chr(10).join(ohlcv_lines)}
"""
    except Exception as exc:
        return f"  (technical indicator error: {exc})"
