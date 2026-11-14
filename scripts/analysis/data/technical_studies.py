"""Studies the technical report quotes beyond the classic indicator snapshot:
Ichimoku, volume profile, anchored VWAP, accumulation/distribution, and the
historical base rates that stand behind a probability.

The 2026-11-14 review (``docs/REPORT_REVIEW.md`` T3, T7) found that the
reports' scenario probabilities, win rates and pattern confidences were the
model's estimates printed as percentages, and that five studies the reference
rubric lists were absent though the bars to compute them were already fetched.
Everything here is computed from those bars and handed over to be quoted.

Pure computation, no network. Every function returns None (or an "N/A" block)
when its inputs are too short, never a number built on a seed value.
"""

from __future__ import annotations

from .technicals import complete, wilder_rsi

ICHIMOKU = (9, 26, 52)          # conversion, base, leading span B (and the 26-bar shift)
PROFILE_BARS = 252
PROFILE_BINS = 24
VALUE_AREA = 0.70
AD_TREND_BARS = 20

# Base rates: forward returns after sessions in the same state as today.
BASE_RATE_HORIZONS = (5, 20, 60)
BASE_RATE_MIN_SAMPLES = 30      # fewer matching sessions than this is not a rate
RSI_BUCKETS = ((30, "RSI(14) < 30"), (50, "RSI(14) 30–50"), (70, "RSI(14) 50–70"),
               (float("inf"), "RSI(14) ≥ 70"))
TREND_MA = 200


def _mid(high, low, n: int):
    return (high.rolling(n).max() + low.rolling(n).min()) / 2


def ichimoku(hist) -> "dict | None":
    """Ichimoku (9/26/52) as it stands on the last bar.

    ``span_a`` / ``span_b`` are the cloud **at the last bar**: the values
    computed 26 bars earlier and plotted forward. ``lead_a`` / ``lead_b`` are
    the cloud being plotted 26 bars ahead. None on fewer than 52 + 26 bars.
    """
    hist = complete(hist)
    conv_n, base_n, span_n = ICHIMOKU
    if hist is None or len(hist) < span_n + base_n:
        return None
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    tenkan, kijun = _mid(high, low, conv_n), _mid(high, low, base_n)
    lead_a, lead_b = (tenkan + kijun) / 2, _mid(high, low, span_n)
    span_a, span_b = float(lead_a.shift(base_n).iloc[-1]), float(lead_b.shift(base_n).iloc[-1])
    last = float(close.iloc[-1])
    top, bottom = max(span_a, span_b), min(span_a, span_b)
    position = "雲層上方" if last > top else "雲層下方" if last < bottom else "雲層內"
    return {"close": last, "tenkan": float(tenkan.iloc[-1]), "kijun": float(kijun.iloc[-1]),
            "span_a": span_a, "span_b": span_b, "position": position,
            "lead_a": float(lead_a.iloc[-1]), "lead_b": float(lead_b.iloc[-1]),
            "tk": "轉換線在基準線上方" if tenkan.iloc[-1] > kijun.iloc[-1]
            else "轉換線在基準線下方" if tenkan.iloc[-1] < kijun.iloc[-1] else "轉換線等於基準線"}


def volume_profile(hist, bars: int = PROFILE_BARS, bins: int = PROFILE_BINS) -> "dict | None":
    """Volume by price over the last ``bars`` sessions.

    Each session's volume is booked at its typical price ``(H + L + C) / 3``,
    since daily bars do not say where inside the range the volume traded. The
    point of control is the middle of the busiest bin; the value area grows
    outward from it, taking the busier neighbour each time, until it holds
    ``VALUE_AREA`` of the volume. None when the range or the volume is zero.
    """
    hist = complete(hist)
    if hist is None or len(hist) < 20:
        return None
    h = hist.tail(bars)
    lo, hi = float(h["Low"].min()), float(h["High"].max())
    total = float(h["Volume"].sum())
    if hi <= lo or total <= 0:
        return None
    width = (hi - lo) / bins
    book = [0.0] * bins
    for tp, vol in zip(((h["High"] + h["Low"] + h["Close"]) / 3).tolist(), h["Volume"].tolist()):
        if vol == vol:
            book[min(int((tp - lo) / width), bins - 1)] += float(vol)
    poc = max(range(bins), key=lambda i: book[i])
    left = right = poc
    held = book[poc]
    while held < VALUE_AREA * total and (left > 0 or right < bins - 1):
        below = book[left - 1] if left > 0 else -1.0
        above = book[right + 1] if right < bins - 1 else -1.0
        if above >= below:
            right += 1
            held += above
        else:
            left -= 1
            held += below
    last = float(h["Close"].iloc[-1])
    val, vah = lo + left * width, lo + (right + 1) * width
    return {"bars": len(h), "bins": bins, "poc": lo + (poc + 0.5) * width,
            "val": val, "vah": vah, "share": held / total,
            "position": "價值區上方" if last > vah else "價值區下方" if last < val else "價值區內"}


def anchored_vwap(hist, anchor) -> "float | None":
    """Volume-weighted average of the typical price from ``anchor`` (an index
    label of ``hist``) to the last bar. None when no volume traded."""
    h = hist.loc[anchor:]
    vol = h["Volume"].sum()
    if not vol or vol != vol:
        return None
    return float((((h["High"] + h["Low"] + h["Close"]) / 3) * h["Volume"]).sum() / vol)


def vwap_anchors(hist) -> "list[dict]":
    """VWAP anchored at the 52-week high and at the 52-week low: the average
    price paid since each, and whether the close is above or below it."""
    hist = complete(hist)
    if hist is None or len(hist) < 2:
        return []
    year = hist.tail(252)
    last = float(hist["Close"].iloc[-1])
    out = []
    for name, anchor in (("52 週高點", year["High"].idxmax()), ("52 週低點", year["Low"].idxmin())):
        value = anchored_vwap(hist, anchor)
        if value is not None:
            out.append({"name": name, "date": str(anchor)[:10], "vwap": value,
                        "side": "上方" if last > value else "下方" if last < value else "相同"})
    return out


def accumulation_distribution(hist, n: int = AD_TREND_BARS) -> "dict | None":
    """Accumulation/distribution line against its own ``n``-bar average, and
    whether it and the price moved the same way over those ``n`` bars.

    ``A/D = Σ volume × ((C − L) − (H − C)) ÷ (H − L)``; a bar with no range
    adds nothing. Its level is arbitrary (it depends on where the sum starts),
    so only its direction is reported.
    """
    hist = complete(hist)
    if hist is None or len(hist) <= n:
        return None
    rng = (hist["High"] - hist["Low"])
    clv = (((hist["Close"] - hist["Low"]) - (hist["High"] - hist["Close"])) / rng.where(rng > 0)).fillna(0.0)
    line = (clv * hist["Volume"]).cumsum()
    above = bool(line.iloc[-1] > line.rolling(n).mean().iloc[-1])
    ad_up = bool(line.iloc[-1] > line.iloc[-1 - n])
    price_up = bool(hist["Close"].iloc[-1] > hist["Close"].iloc[-1 - n])
    if ad_up == price_up:
        relation = "與價格同向（確認）"
    else:
        relation = "價跌而 A/D 上升（吸籌跡象）" if ad_up else "價漲而 A/D 下降（派發跡象）"
    return {"bars": n, "above_average": above, "ad_up": ad_up, "price_up": price_up,
            "relation": relation}


def studies_block(hist) -> str:
    """The 進階指標 block of the technical context."""
    try:
        return _studies_block(hist)
    except Exception as exc:  # one study failing must not cost the report its indicators
        return f"  ── 進階指標 ──\n  N/A（計算錯誤: {exc}）"


def _studies_block(hist) -> str:
    rows = ["  ── 進階指標（一目均衡表、成交量分布、錨定 VWAP、A/D；皆由日線計算）──"]
    ich = ichimoku(hist)
    if ich:
        rows += [
            f"  一目均衡表 ({'/'.join(map(str, ICHIMOKU))}): 轉換線 ${ich['tenkan']:.2f}   基準線 ${ich['kijun']:.2f}   "
            f"先行帶 A ${ich['span_a']:.2f}   先行帶 B ${ich['span_b']:.2f}（此為最新 K 棒所在位置的雲層）",
            f"    收盤位於{ich['position']}；{ich['tk']}；"
            f"前方 26 根的雲層: 先行帶 A ${ich['lead_a']:.2f} / B ${ich['lead_b']:.2f}"
            f"（{'A 在 B 上方，偏多' if ich['lead_a'] > ich['lead_b'] else 'A 在 B 下方，偏空' if ich['lead_a'] < ich['lead_b'] else 'A 等於 B'}）",
        ]
    else:
        rows.append(f"  一目均衡表: N/A（需至少 {ICHIMOKU[2] + ICHIMOKU[1]} 根日K）")
    vp = volume_profile(hist)
    if vp:
        rows += [
            f"  成交量分布（近 {vp['bars']} 個交易日，{vp['bins']} 個價格區間，每日成交量記在典型價 (高+低+收)÷3）:",
            f"    控制點 POC ${vp['poc']:.2f}   價值區 ${vp['val']:.2f}–${vp['vah']:.2f}"
            f"（含 {vp['share'] * 100:.0f}% 成交量）   收盤位於{vp['position']}",
        ]
    else:
        rows.append("  成交量分布: N/A（數據不足）")
    anchors = vwap_anchors(hist)
    if anchors:
        rows.append("  錨定 VWAP（自錨定日起的成交量加權平均價）:")
        rows += [f"    自{a['name']}（{a['date']}）起: ${a['vwap']:.2f}   收盤在其{a['side']}" for a in anchors]
    else:
        rows.append("  錨定 VWAP: N/A（數據不足）")
    ad = accumulation_distribution(hist)
    if ad:
        rows.append(f"  A/D 線（近 {ad['bars']} 根）: {'高於' if ad['above_average'] else '不高於'}其 {ad['bars']} 日均值；"
                    f"A/D {'上升' if ad['ad_up'] else '下降'}、價格{'上漲' if ad['price_up'] else '下跌'} → {ad['relation']}")
    else:
        rows.append("  A/D 線: N/A（數據不足）")
    return "\n".join(rows)


# ── base rates ───────────────────────────────────────────────────────────────
def _quantile(values: list, q: float) -> float:
    """Linear-interpolated quantile of a sorted list."""
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _bucket(rsi: float) -> "int | None":
    if rsi != rsi:
        return None
    return next(i for i, (upper, _) in enumerate(RSI_BUCKETS) if rsi < upper)


def _stats(returns: list) -> dict:
    ordered = sorted(returns)
    return {"n": len(ordered), "up": sum(1 for r in ordered if r > 0) / len(ordered),
            "median": _quantile(ordered, 0.5), "p25": _quantile(ordered, 0.25),
            "p75": _quantile(ordered, 0.75)}


def base_rates(close, horizons=BASE_RATE_HORIZONS) -> "dict | None":
    """What this ticker did after past sessions that looked like today.

    Today's state is its RSI(14) bucket and which side of the 200-day average
    the close is on. For each horizon the forward return of every earlier
    session in the same state is collected: how many, the share that rose, the
    median and the quartiles — beside the same figures for all sessions, so a
    reader can see whether the state changes anything.

    Matching sessions come in runs, and their forward windows overlap, so
    ``episodes`` (the number of separate runs) is the honest sample size.
    A horizon with fewer than ``BASE_RATE_MIN_SAMPLES`` matching sessions has
    no statistics. None when the state itself cannot be computed.
    """
    close = close.dropna()
    if len(close) < TREND_MA + 1:
        return None
    rsi = wilder_rsi(close)
    ma = close.rolling(TREND_MA).mean()
    now_bucket = _bucket(float(rsi.iloc[-1]))
    if now_bucket is None or ma.iloc[-1] != ma.iloc[-1]:
        return None
    now_above = bool(close.iloc[-1] > ma.iloc[-1])
    values, rsis, mas = close.tolist(), rsi.tolist(), ma.tolist()
    match = [m == m and _bucket(r) == now_bucket and (c > m) == now_above
             for c, r, m in zip(values, rsis, mas)]
    valid = [m == m and r == r for r, m in zip(rsis, mas)]
    rows = []
    for h in horizons:
        last = len(values) - h              # sessions with a full forward window
        same = [values[i + h] / values[i] - 1 for i in range(last) if match[i]]
        every = [values[i + h] / values[i] - 1 for i in range(last) if valid[i]]
        episodes = sum(1 for i in range(last) if match[i] and (i == 0 or not match[i - 1]))
        rows.append({"horizon": h, "episodes": episodes,
                     "same": _stats(same) if len(same) >= BASE_RATE_MIN_SAMPLES else None,
                     "matched": len(same),
                     "all": _stats(every) if len(every) >= BASE_RATE_MIN_SAMPLES else None})
    return {"state": f"{RSI_BUCKETS[now_bucket][1]} 且收盤在 MA{TREND_MA} {'上方' if now_above else '下方'}",
            "from": str(close.index[0])[:10], "to": str(close.index[-1])[:10],
            "sessions": len(values), "rows": rows}


def base_rate_block(hist, long_bars=None) -> str:
    """The 歷史基準機率 block. Uses ``long_bars`` (the price store) when it is
    the longer history, else the fetched bars."""
    title = "  ── 歷史基準機率（本股過去處於與今日相同狀態後的實際報酬；由程式計算）──"
    try:
        hist = complete(hist)
        src = long_bars if long_bars is not None and hist is not None and len(long_bars) > len(hist) else hist
        if src is None or src.empty:
            return ""
        br = base_rates(src["Close"])
    except Exception as exc:
        return f"{title}\n  N/A（計算錯誤: {exc}）"
    if not br:
        return f"{title}\n  N/A（需至少 {TREND_MA + 1} 個交易日的收盤價）"
    pct = lambda v: f"{v * 100:+.1f}%"
    rows = [title,
            f"  今日狀態: {br['state']}",
            f"  樣本: {br['from']} 至 {br['to']}，共 {br['sessions']} 個交易日（價格報酬，不含股息）",
            "  持有期     相同狀態的交易日（段數）   上漲比例   中位數    25%–75% 分位        全部交易日: 上漲比例 / 中位數"]
    for r in br["rows"]:
        s, a = r["same"], r["all"]
        base = f"{a['up'] * 100:.0f}% / {pct(a['median'])}" if a else "N/A"
        if s:
            rows.append(f"  {r['horizon']:>3} 日     {s['n']:>5}（{r['episodes']} 段）            "
                        f"{s['up'] * 100:>5.0f}%   {pct(s['median']):>7}   {pct(s['p25'])} – {pct(s['p75'])}        {base}")
        else:
            rows.append(f"  {r['horizon']:>3} 日     {r['matched']:>5}（{r['episodes']} 段）            "
                        f"N/A（相同狀態的交易日少於 {BASE_RATE_MIN_SAMPLES} 個）        {base}")
    rows += [
        "  註: 相同狀態的交易日連續出現、持有期互相重疊，並非獨立樣本；「段數」才接近獨立事件的個數。",
        "  註: 這是歷史頻率，不是預測。報告中的機率只能引用本表的「上漲比例」，或改用 高／中／低 並說明依據。",
    ]
    return "\n".join(rows)


__all__ = ["ichimoku", "volume_profile", "anchored_vwap", "vwap_anchors",
           "accumulation_distribution", "studies_block", "base_rates", "base_rate_block"]
