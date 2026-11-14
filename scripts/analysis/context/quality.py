"""Quality figures for the fundamental report: Piotroski F-Score, DuPont,
working-capital days, and the lender's own metrics.

The 2026-11-14 review (``docs/REPORT_REVIEW.md`` F8, F9) found none of the 38
reports carried an F-Score, one carried working-capital days, every DuPont
diagram was ``N/A`` though its three factors were in the data, and the two
lenders (SOFI, NU) were described with an operating company's ratios. All of
it is arithmetic on figures already fetched, so it is done here and quoted.

Pure: plain data in, plain data out; ``render`` turns it into context lines.
A missing input gives None for that figure, never a zero.
"""

from __future__ import annotations

from datetime import date

from ..data import fundamental_analytics as fa

DAYS = 365
# Yahoo's balance-sheet column must be this close to the period the flows end
# on, or the two describe different quarters and no ratio is formed.
PERIOD_MATCH_DAYS = 10

F_SCORE_LABELS = {
    "roa_positive": "ROA > 0",
    "ocf_positive": "營業現金流 > 0",
    "roa_improving": "ROA 高於一年前",
    "accruals": "營業現金流 > 淨利（應計品質）",
    "leverage_falling": "長期負債 ÷ 總資產 低於一年前",
    "liquidity_improving": "流動比率高於一年前",
    "no_dilution": "稀釋股數未增加",
    "gross_margin_improving": "毛利率高於一年前",
    "asset_turnover_improving": "資產週轉率高於一年前",
}


def _f(v) -> "float | None":
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _gap_days(a: str, b: str) -> int:
    return abs((date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days)


def f_score(cur: "dict | None", prev: "dict | None") -> "dict | None":
    """Piotroski F-Score of the latest TTM against the TTM a year earlier."""
    if not cur or not prev:
        return None
    out = fa.piotroski(cur, prev)
    tests = dict(out["tests"])
    if _f(cur.get("long_term_debt")) is None or _f(prev.get("long_term_debt")) is None:
        # fa.piotroski reads a missing debt figure as no debt, which passes the
        # leverage test for a company that simply did not tag it this year.
        # A reported zero still counts; an absent figure is not a result.
        tests["leverage_falling"] = None
    tested = [v for v in tests.values() if v is not None]
    if not tested:
        return None
    return {"score": sum(1 for v in tested if v), "tested": len(tested), "tests": tests,
            "period_end": cur.get("period_end"), "prior_period_end": prev.get("period_end")}


def dupont(row: "dict | None") -> "dict | None":
    """ROE = net margin × asset turnover × equity multiplier, on TTM flows and
    closing balances (the basis ``fa.returns_on_capital`` uses, so this ROE is
    the ROE quoted elsewhere). None when a factor is missing or equity is not
    positive — a multiplier on negative equity has no reading."""
    if not row:
        return None
    net, rev = _f(row.get("net_income")), _f(row.get("revenue"))
    assets, equity = _f(row.get("total_assets")), _f(row.get("total_equity"))
    if net is None or not rev or not assets or equity is None or equity <= 0:
        return None
    return {"net_margin": net / rev, "asset_turnover": rev / assets,
            "equity_multiplier": assets / equity, "roe": net / equity}


def _column(frame, when: str, tolerance: int = PERIOD_MATCH_DAYS):
    """The column of a newest-first yfinance frame dated within ``tolerance``
    days of ``when``, or None."""
    if frame is None or not when:
        return None
    for col in getattr(frame, "columns", []):
        try:
            if _gap_days(str(col), when) <= tolerance:
                return col
        except ValueError:
            continue
    return None


def _cell(frame, row: str, col) -> "float | None":
    try:
        if frame is None or col is None or row not in frame.index:
            return None
        return _f(frame.loc[row, col])
    except (KeyError, IndexError):
        return None


def _ttm(frame, row: str, start: int = 0) -> "float | None":
    """Sum of four consecutive quarters of ``row`` from column ``start``."""
    try:
        if frame is None or row not in frame.index:
            return None
        cells = [_f(v) for v in frame.loc[row].iloc[start:start + 4]]
    except (KeyError, IndexError):
        return None
    return sum(cells) if len(cells) == 4 and None not in cells else None


def _days(balance: "float | None", flow: "float | None") -> "float | None":
    return balance / flow * DAYS if balance is not None and flow and flow > 0 else None


def _cycle(revenue, cogs, receivables, inventory, payables) -> dict:
    dso, dio, dpo = _days(receivables, revenue), _days(inventory, cogs), _days(payables, cogs)
    return {"dso": dso, "dio": dio, "dpo": dpo,
            "ccc": dso + dio - dpo if None not in (dso, dio, dpo) else None}


def working_capital(data: dict, cur: "dict | None", prev: "dict | None") -> "dict | None":
    """DSO, DIO, DPO and the cash conversion cycle, now and a year earlier.

    Flows (revenue; cost of revenue = revenue − gross profit) are the TTM rows
    of the SEC store when given, else Yahoo's last four quarters. Receivables,
    inventory and payables are closing balances from Yahoo's quarterly balance
    sheet — the store does not carry them — taken from the column dated the
    same quarter-end as the flows. None when no balance column matches.
    """
    bal, inc = data.get("balance_q"), data.get("income_q")

    def flows(row):
        rev, gp = _f(row.get("revenue")), _f(row.get("gross_profit"))
        return row.get("period_end"), rev, (rev - gp if rev is not None and gp is not None else None)

    periods = []
    if cur:
        end, revenue, cogs = flows(cur)
        source = "SEC"
        if cogs is None and inc is not None and _column(inc, end) is not None \
                and _column(inc, end) == inc.columns[0]:
            # A filer that tags no gross profit (AMZN): Yahoo's cost of revenue
            # for the same four quarters.
            cogs = _ttm(inc, "Cost Of Revenue")
            source = "SEC revenue, Yahoo cost of revenue" if cogs is not None else source
        periods.append((source, end, revenue, cogs))
        if prev:
            periods.append(("SEC", *flows(prev)))
    elif inc is not None and len(getattr(inc, "columns", [])):
        periods.append(("Yahoo", str(inc.columns[0])[:10],
                        _ttm(inc, "Total Revenue"), _ttm(inc, "Cost Of Revenue")))
    out = []
    for source, end, revenue, cogs in periods:
        col = _column(bal, end)
        if col is None:
            out.append(None)
            continue
        cycle = _cycle(revenue, cogs, _cell(bal, "Accounts Receivable", col),
                       _cell(bal, "Inventory", col), _cell(bal, "Accounts Payable", col))
        out.append({"period_end": end, "flow_source": source, **cycle})
    if not out or out[0] is None or all(out[0][k] is None for k in ("dso", "dio", "dpo")):
        return None
    return {"now": out[0], "prior": out[1] if len(out) > 1 else None}


def bank_metrics(data: dict, info: dict, rate: "float | None" = 1.0) -> "dict | None":
    """A lender's metrics from Yahoo's quarterly statements, each labelled with
    what it is — two of them are proxies, because Yahoo carries neither
    earning assets nor credit provisions.

    ``rate`` converts statement currency to quote currency for P/TBV. None
    when there is no net interest income to speak of.
    """
    inc, bal = data.get("income_q"), data.get("balance_q")
    nii, revenue = _ttm(inc, "Net Interest Income"), _ttm(inc, "Total Revenue")
    if nii is None or bal is None or not len(getattr(bal, "columns", [])):
        return None
    # Balances of the quarter the four quarters of income end on. Yahoo can
    # publish a newer balance sheet before the matching income statement; with
    # no column for the income period the balance-based ratios are left out
    # rather than formed across two periods.
    end = str(inc.columns[0])[:10]
    latest = _column(bal, end)
    assets_now = _cell(bal, "Total Assets", latest)
    lo, hi = fa.YEAR_APART_DAYS
    assets_then = next((_cell(bal, "Total Assets", c) for c in bal.columns
                        if latest is not None and str(c) < str(latest)
                        and lo <= _gap_days(str(c), end) <= hi), None)
    avg_assets = (assets_now + assets_then) / 2 if assets_now and assets_then else None
    pretax, net = _ttm(inc, "Pretax Income"), _ttm(inc, "Net Income")
    tbv = _cell(bal, "Tangible Book Value", latest)
    mcap = _f(info.get("marketCap"))
    loans = _cell(bal, "Net Loan", latest)
    return {
        "period_end": end,
        "balance_matched": latest is not None,
        "nii_ttm": nii,
        "nii_share": nii / revenue if revenue else None,
        "nim_proxy": nii / avg_assets if avg_assets else None,
        "cost_to_income": (revenue - pretax) / revenue if revenue and pretax is not None else None,
        "rotce": net / tbv if net is not None and tbv and tbv > 0 else None,
        "tangible_book": tbv,
        "p_tbv": mcap / (tbv * rate) if mcap and tbv and tbv > 0 and rate else None,
        "loans_to_assets": loans / assets_now if loans is not None and assets_now else None,
    }


def build(data: dict, info: dict, stmt: "dict | None", lender: bool,
          rate: "float | None" = 1.0) -> dict:
    """Every quality figure for one company."""
    cur = stmt.get("_ttm_row") if stmt else None
    prev = stmt.get("_ttm_prior_row") if stmt else None
    return {
        "lender": lender,
        # Piotroski's tests read a lender backwards: lending more is an
        # operating cash outflow and a falling asset turnover.
        "f_score": None if lender else f_score(cur, prev),
        "dupont": dupont(cur),
        "working_capital": None if lender else working_capital(data, cur, prev),
        "bank": bank_metrics(data, info, rate) if lender else None,
    }


# ── rendering ────────────────────────────────────────────────────────────────
def _p(v, digits: int = 1) -> str:
    return "N/A" if v is None else f"{v * 100:.{digits}f}%"


def _d(v) -> str:
    return "N/A" if v is None else f"{v:.0f} 天"


def render(q: "dict | None") -> "list[str]":
    """The QUALITY FIGURES lines of the VERIFIED FIGURES block."""
    if not q:
        return []
    lines = ["", "QUALITY FIGURES (computed in Python — copy, do not recompute):"]
    fs = q.get("f_score")
    if fs:
        lines.append(f"  Piotroski F-Score: {fs['score']} / {fs['tested']}   "
                     f"(TTM to {fs['period_end']} vs TTM to {fs['prior_period_end']}; "
                     "a test with a missing input is left out, so the denominator may be below 9)")
        mark = {True: "✅ 通過", False: "❌ 未通過", None: "— 無法判定（缺資料）"}
        lines += [f"    {F_SCORE_LABELS[k]:<28} {mark[v]}" for k, v in fs["tests"].items()]
    elif q.get("lender"):
        lines.append("  Piotroski F-Score: N/A — not applied to a lender (loan growth is an operating cash "
                     "outflow, so its cash-flow tests misread a bank).")
    else:
        lines.append("  Piotroski F-Score: N/A — needs two TTM periods a year apart from SEC filing data.")
    dp = q.get("dupont")
    if dp:
        lines.append(f"  DuPont (TTM, closing balances): 淨利率 {_p(dp['net_margin'])} × 資產週轉率 "
                     f"{dp['asset_turnover']:.2f} × 權益乘數 {dp['equity_multiplier']:.2f} = ROE {_p(dp['roe'])}")
    else:
        lines.append("  DuPont: N/A — net income, revenue, total assets or positive equity is missing.")
    wc = q.get("working_capital")
    if wc:
        def row(tag, c):
            return (f"    {tag} (to {c['period_end']}):  DSO {_d(c['dso'])}   DIO {_d(c['dio'])}   "
                    f"DPO {_d(c['dpo'])}   現金轉換週期 CCC {_d(c['ccc'])}")
        lines.append(f"  Working-capital days (closing balance ÷ TTM flow × {DAYS}; flows: "
                     f"{wc['now']['flow_source']}, balances: Yahoo quarterly balance sheet):")
        lines.append(row("最新 TTM", wc["now"]))
        if wc.get("prior"):
            lines.append(row("一年前 TTM", wc["prior"]))
        lines.append("    DSO = 應收帳款 ÷ 營收；DIO = 存貨 ÷ 營業成本；DPO = 應付帳款 ÷ 營業成本；CCC = DSO + DIO − DPO。"
                     "N/A = the company reports no such balance; do not fill it in.")
    elif q.get("bank") is None:
        lines.append("  Working-capital days: N/A — no quarterly balance sheet for the statement period.")
    b = q.get("bank")
    if b:
        lines += [
            f"  LENDER METRICS (Yahoo quarterly statements, TTM to {b['period_end']}) — use these in §6 instead of "
            "ROIC / working-capital analysis:",
            f"    淨利息收入 NII (TTM) ÷ 總營收:                {_p(b['nii_share'])}",
            f"    淨利差代理值 = NII (TTM) ÷ 平均總資產:         {_p(b['nim_proxy'], 2)}"
            "   ← a proxy: earning assets are not in the data, so the reported NIM is higher",
            f"    成本收入比代理值 = (營收 − 稅前淨利) ÷ 營收:    {_p(b['cost_to_income'])}"
            "   ← includes credit provisions, so it is above the reported efficiency ratio",
            f"    有形權益報酬率 ROTCE = 淨利 (TTM) ÷ 有形帳面價值: {_p(b['rotce'])}",
            f"    股價 ÷ 有形帳面價值 P/TBV:                    "
            + ("N/A" if b["p_tbv"] is None else f"{b['p_tbv']:.2f}x"),
            f"    放款淨額 ÷ 總資產:                            {_p(b['loans_to_assets'])}",
            "    淨沖銷率、逾放比、CET1: N/A — not in the data. Say so; do not quote them from memory.",
        ]
        if not b.get("balance_matched", True):
            lines.append(f"    Balance-based ratios are N/A: Yahoo has no balance sheet dated {b['period_end']}, "
                         "the quarter the income figures end on.")
    return lines


__all__ = ["f_score", "dupont", "working_capital", "bank_metrics", "build", "render",
           "F_SCORE_LABELS"]
