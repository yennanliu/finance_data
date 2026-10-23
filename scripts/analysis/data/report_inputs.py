"""Extra inputs for the fundamental report's fact block (network layer).

:func:`gather` collects what ``fetch_data`` does not: the committed fundamentals
and price stores (refreshed in memory from SEC so a quarter filed since the last
weekly store update is not missed), a risk-free rate for the cost of equity, and
the configured peers' multiples. Each step is best-effort and records whether it
worked, so a failure narrows the fact block instead of aborting the report.

The arithmetic over these inputs lives in :mod:`analysis.context.fundamental_facts`,
which is pure and tested offline.
"""

from __future__ import annotations

from ..config.valuation import PEERS, RISK_FREE_SYMBOL
from . import fundamentals, prices
from .sources import _get_yf, last_completed_close

# Peer fields copied from Yahoo, each with the period it covers.
PEER_FIELDS = (
    "currency", "financialCurrency", "trailingPE", "forwardPE",
    "priceToSalesTrailing12Months", "enterpriseToEbitda",
    "revenueGrowth", "grossMargins", "profitMargins",
)


def store_rows(ticker: str) -> "tuple[list[dict], dict]":
    """Committed fundamentals rows, upserted with a live SEC fetch.

    Returns ``(rows, status)``. The live rows are not written back — the weekly
    ``update_fundamentals`` workflow owns the store and its gate.
    """
    key = prices.report_key(ticker)
    rows = fundamentals.load_store(key)
    status = {"fundamentals_store": bool(rows), "sec_live": False}
    try:
        cik = fundamentals.cik_map().get(key.split(".")[0].upper())
        facts = fundamentals.fetch_facts(cik) if cik else None
        live = fundamentals.trim(fundamentals.resolve(facts)) if facts else []
    except Exception as exc:  # noqa: BLE001 — NoFacts (ETF), HTTP, parse: all non-fatal
        print(f"  ⚠ SEC companyfacts unavailable for {ticker}: {exc}")
        live = []
    if live and fundamentals.gate(live, []) is None:
        rows = fundamentals.upsert(rows, live)
        status["sec_live"] = True
    return rows, status


def risk_free_rate() -> "float | None":
    """The 10-year Treasury yield as a decimal (^TNX quotes 4.25 for 4.25%)."""
    try:
        hist = _get_yf().Ticker(RISK_FREE_SYMBOL).history(period="10d")
        close, _ = last_completed_close(hist)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ risk-free rate unavailable: {exc}")
        return None
    return close / 100.0 if close else None


def peer_multiples(ticker: str) -> "list[dict]":
    """Yahoo multiples for the configured peers; a peer that fails is skipped."""
    out = []
    yf = None
    for peer in PEERS.get(prices.report_key(ticker), []):
        try:
            yf = yf or _get_yf()
            info = yf.Ticker(prices.to_yf_symbol(peer)).info or {}
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠ peer {peer} unavailable: {exc}")
            continue
        if not info:
            continue
        entry = {"ticker": peer}
        entry.update({k: info.get(k) for k in PEER_FIELDS})
        out.append(entry)
    return out


def fx_rate(statement_ccy: "str | None", quote_ccy: "str | None") -> "dict | None":
    """Quote-currency units per statement-currency unit, for an ADR whose
    statements are in another currency (SKHY: KRW → USD).

    Without it the model picked its own rate (1,350 KRW/USD on 2026-10-23,
    vs 1,322 that day). Returns ``{"pair", "rate", "date"}`` or None.
    """
    if not statement_ccy or not quote_ccy or statement_ccy == quote_ccy:
        return None
    pair = f"{statement_ccy}{quote_ccy}=X"
    try:
        hist = _get_yf().Ticker(pair).history(period="10d")
        rate, day = last_completed_close(hist)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ FX rate {pair} unavailable: {exc}")
        return None
    return {"pair": pair, "rate": rate, "date": day} if rate else None


def prefer_newer_close(data: dict, bars: "list[dict]") -> bool:
    """Use the price store's last close when it is newer than Yahoo's.

    Yahoo sometimes returns an empty (NaN) bar for the latest session, and
    returns nothing at all for a symbol it does not know; the committed store
    then holds the more recent close. Returns True if the price was replaced.
    """
    if not bars:
        return False
    last = bars[-1]
    if data.get("price_now") is None or (data.get("price_date") or "") < last["date"]:
        data["price_now"], data["price_date"] = float(last["close"]), last["date"]
        return True
    return False


def gather(ticker: str, info: "dict | None" = None) -> dict:
    """Everything :func:`fundamental_facts.compute_facts` needs beyond ``fetch_data``.

    ``info`` is ``fetch_data``'s Yahoo info; its currencies decide whether an
    FX rate is needed.
    """
    info = info or {}
    rows, status = store_rows(ticker)
    bars = prices.load_store(prices.report_key(ticker))
    rf = risk_free_rate()
    peers = peer_multiples(ticker)
    fx = fx_rate(info.get("financialCurrency"), info.get("currency"))
    status.update({
        "price_store": bool(bars),
        "risk_free_rate": rf is not None,
        "peers": bool(peers),
    })
    if info.get("financialCurrency") and info.get("financialCurrency") != info.get("currency"):
        status["fx_rate"] = fx is not None
    return {"store_rows": rows, "bars": bars, "risk_free": rf,
            "peers": peers, "fx": fx, "status": status}


__all__ = ["gather", "store_rows", "risk_free_rate", "peer_multiples",
           "prefer_newer_close", "fx_rate", "PEER_FIELDS"]
