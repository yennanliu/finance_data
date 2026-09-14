"""Tests for the committed fundamentals store (scripts/analysis/data/fundamentals.py).

Two layers are asserted here. The store invariants (I1-I6) mirror the price
store's, because a silent regression in any of them degrades this store the same
way. Above those sit the XBRL extraction rules, which exist because SEC's
companyfacts payload is shaped for filers rather than for readers — each rule
here was written against a real payload that broke an earlier version of the
code, and the docstrings name the company and period so the next person can go
look at the same filing.

Fully offline: every fetch is monkeypatched and the read path is stdlib-only.
"""

import pytest

from analysis.data import fundamentals as F

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────
def row(period_end, fy, fp, **metrics):
    """A well-formed store row; unnamed metrics are absent, not zero."""
    r = {"period_end": period_end, "fy": fy, "fp": fp,
         "form": "10-Q", "filed": "2026-01-31"}
    for m in F.METRICS:
        r[m] = metrics.get(m)
    return r


def quarters(*values, fy=2026, start_end="2025-03-31"):
    """Four consecutive quarter rows carrying `revenue`."""
    ends = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    return [row(e, fy, f"Q{i}", revenue=v)
            for i, (e, v) in enumerate(zip(ends, values), start=1)]


def fact(start, end, val, form="10-Q", filed="2026-01-31", accn="x"):
    return {"start": start, "end": end, "val": val,
            "form": form, "filed": filed, "accn": accn}


def duration_facts(*facts):
    """The {(start, end): point} shape `discrete_quarters` consumes."""
    return {(f["start"], f["end"]): f for f in facts}


# ── I1: byte-stable serialisation ────────────────────────────────────────────
def test_serialise_parse_round_trip_is_byte_stable():
    text = F.serialise(quarters(1e9, 2e9, 3e9, 4e9))
    assert F.serialise(F.parse(text)) == text


def test_round_trip_stable_for_fractional_and_absent_values():
    rows = [row("2025-12-31", 2026, "Q4", revenue=1.234e11, eps_diluted=2.46)]
    text = F.serialise(rows)
    assert F.serialise(F.parse(text)) == text
    assert "123400000000" in text  # whole dollars stay integral
    assert "2.46" in text


def test_absent_metric_serialises_empty_not_zero():
    """An untagged concept must never read as a reported zero.

    AMZN does not tag GrossProfit quarterly; rendering that as 0 would put a
    company with no gross margin on the chart.
    """
    text = F.serialise([row("2025-12-31", 2026, "Q4", revenue=1e9)])
    assert ",," in text
    assert F.parse(text)[0]["gross_profit"] is None


def test_fmt_value_never_emits_scientific_notation():
    assert F.fmt_value(1.23e11) == "123000000000"
    assert F.fmt_value(0.00005) == "0.0001"


def test_fmt_value_is_idempotent():
    for v in (0, -0.0, 1e9, 2.46, -1.5, 123456789.1234):
        once = F.fmt_value(v)
        assert F.fmt_value(float(once)) == once


def test_parse_skips_malformed_lines_without_losing_good_ones():
    text = F.serialise(quarters(1e9, 2e9, 3e9, 4e9))
    broken = text.replace("2025-06-30,2026,Q2", "not-a-row")
    assert len(F.parse(broken)) == 3


# ── I2 / I5: writes ──────────────────────────────────────────────────────────
def test_write_store_is_idempotent(tmp_path):
    rows = quarters(1e9, 2e9, 3e9, 4e9)
    assert F.write_store("nvda", rows, tmp_path) is True
    assert F.write_store("nvda", rows, tmp_path) is False


def test_write_store_leaves_no_temp_file(tmp_path):
    F.write_store("nvda", quarters(1e9, 2e9, 3e9, 4e9), tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_load_store_of_missing_ticker_is_empty(tmp_path):
    assert F.load_store("nope", tmp_path) == []


def test_store_path_lowercases_the_key(tmp_path):
    assert F.store_path("NVDA", tmp_path).name == "nvda.csv"


# ── I3: merge ────────────────────────────────────────────────────────────────
def test_upsert_sorts_and_deduplicates():
    merged = F.upsert(quarters(1e9, 2e9, 3e9, 4e9)[:2],
                      quarters(1e9, 2e9, 3e9, 4e9)[1:])
    ends = [r["period_end"] for r in merged]
    assert ends == sorted(set(ends)) and len(ends) == 4


def test_upsert_fetched_period_wins_on_collision():
    """A restatement overwrites the stored figure — the whole restatement story."""
    old = [row("2025-12-31", 2026, "Q4", revenue=1e9)]
    new = [row("2025-12-31", 2026, "Q4", revenue=2e9)]
    assert F.upsert(old, new)[0]["revenue"] == 2e9


# ── I4: trim ─────────────────────────────────────────────────────────────────
def test_trim_drops_periods_older_than_keep_years_from_newest():
    rows = ([row("2010-12-31", 2011, "Q4")] + quarters(1e9, 2e9, 3e9, 4e9))
    assert len(F.trim(rows, years=10)) == 4


def test_trim_is_independent_of_today():
    """Measured from the newest row, so the same input gives the same bytes."""
    rows = quarters(1e9, 2e9, 3e9, 4e9)
    assert F.trim(rows, years=10) == F.trim(rows, years=10)


def test_trim_of_empty_is_empty():
    assert F.trim([], years=10) == []


# ── The fy/fp trap ───────────────────────────────────────────────────────────
def test_fiscal_years_come_from_period_dates_not_fy_fp_labels():
    """fy/fp label the *filing*, not the period.

    One NVDA 10-Q filed 2024-11-20 emits four Revenues facts all tagged
    fy=2025/fp=Q3: the current quarter, the current year-to-date, and both
    prior-year comparatives. Keying on those labels silently mixes periods.
    """
    gaap = {"Revenues": {"units": {"USD": [
        # All four carry the same (wrong) fy/fp; only the dates distinguish them.
        dict(fact("2023-01-30", "2023-10-29", 38.82e9), fy=2025, fp="Q3"),
        dict(fact("2023-07-31", "2023-10-29", 18.12e9), fy=2025, fp="Q3"),
        dict(fact("2024-01-29", "2024-10-27", 91.17e9), fy=2025, fp="Q3"),
        dict(fact("2024-07-29", "2024-10-27", 35.08e9), fy=2025, fp="Q3"),
        dict(fact("2024-01-29", "2025-01-26", 130.50e9, form="10-K"), fy=2025, fp="FY"),
    ]}}}
    assert F.fiscal_years(gaap) == [("2024-01-29", "2025-01-26")]


# ── Year-to-date reconstruction ──────────────────────────────────────────────
def test_cumulative_metrics_are_recovered_by_differencing():
    """Cash flow is only ever reported year-to-date, never as a discrete quarter.

    NVDA FY2026 OCF is tagged 27.41 / 42.78 / 66.53 / 102.72 at 90/181/272/363
    days; the quarters are the differences and must sum back to the annual.
    """
    facts = duration_facts(
        fact("2025-01-27", "2025-04-27", 27.41e9),
        fact("2025-01-27", "2025-07-27", 42.78e9),
        fact("2025-01-27", "2025-10-26", 66.53e9),
        fact("2025-01-27", "2026-01-25", 102.72e9, form="10-K"),
    )
    q = F.discrete_quarters(facts, "2025-01-27", "2026-01-25")
    assert len(q) == 4
    assert q["2025-04-27"] == pytest.approx(27.41e9)
    assert q["2025-07-27"] == pytest.approx(15.37e9)
    assert q["2026-01-25"] == pytest.approx(36.19e9)
    assert sum(q.values()) == pytest.approx(102.72e9)


def test_a_reported_quarter_beats_a_differenced_one():
    facts = duration_facts(
        fact("2025-01-27", "2025-04-27", 100.0),
        fact("2025-01-27", "2025-07-27", 250.0),
        fact("2025-04-28", "2025-07-27", 149.0),  # reported, differs by 1
    )
    q = F.discrete_quarters(facts, "2025-01-27", "2025-07-27")
    assert q["2025-07-27"] == 149.0


def test_a_lone_annual_fact_is_never_emitted_as_a_quarter():
    """MSFT's 2008 operating income is tagged only as a 365-day fact.

    Treating that lone point as the first link of a chain would publish a whole
    year's profit as one quarter — and did, until the chain had to start at a
    quarter.
    """
    facts = duration_facts(
        fact("2007-07-01", "2008-06-30", 22.27e9, form="10-K"))
    assert F.discrete_quarters(facts, "2007-07-01", "2008-06-30") == {}


def test_a_gap_in_the_chain_does_not_fold_two_quarters_into_one():
    facts = duration_facts(
        fact("2025-01-27", "2025-04-27", 100.0),
        fact("2025-01-27", "2026-01-25", 500.0, form="10-K"),  # jumps 9 months
    )
    q = F.discrete_quarters(facts, "2025-01-27", "2026-01-25")
    assert "2026-01-25" not in q


# ── Non-cumulative metrics ───────────────────────────────────────────────────
def test_weighted_average_share_counts_are_never_differenced():
    """A weighted average is not a flow.

    NVDA reports diluted shares year-to-date as 24.61 / 24.57 / 24.54 / 24.51B;
    differencing those yields -0.03B, which is an artefact, not a share count.
    """
    facts = duration_facts(
        fact("2025-01-27", "2025-04-27", 24.611e9),
        fact("2025-01-27", "2025-07-27", 24.571e9),
        fact("2025-01-27", "2026-01-25", 24.514e9, form="10-K"),
    )
    q = F.discrete_quarters(facts, "2025-01-27", "2026-01-25", cumulative=False)
    assert all(v > 20e9 for v in q.values()), q
    assert q["2026-01-25"] == pytest.approx(24.514e9)


# ── The inconsistent-chain trap ──────────────────────────────────────────────
def test_a_shrinking_revenue_chain_yields_no_quarter_rather_than_a_negative_one():
    """WDC FY2023 runs 3.74 → 6.84 → 9.65 → 6.26B on one concept.

    The 10-K tags that concept more narrowly than the 10-Qs did, so the annual
    figure is smaller than the nine-month one. Differencing gave -3.39B of
    revenue; refusing the value lets the next concept claim the period.
    """
    facts = duration_facts(
        fact("2022-07-02", "2022-09-30", 3.736e9),
        fact("2022-07-02", "2022-12-30", 6.843e9),
        fact("2022-07-02", "2023-03-31", 9.646e9),
        fact("2022-07-02", "2023-06-30", 6.255e9, form="10-K"),
    )
    q = F.discrete_quarters(facts, "2022-07-02", "2023-06-30", non_negative=True)
    assert "2023-06-30" not in q
    assert q["2023-03-31"] == pytest.approx(2.803e9)


def test_a_later_concept_supplies_a_period_the_first_one_could_not():
    """KTOS FY2011: `Revenues` gives a bad Q4, `SalesRevenueNet` a clean one."""
    gaap = {
        "Revenues": {"units": {"USD": [
            fact("2010-12-27", "2011-09-25", 0.500e9),
            fact("2010-12-27", "2011-12-25", 0.054e9, form="10-K"),
        ]}},
        "SalesRevenueNet": {"units": {"USD": [
            fact("2010-12-27", "2011-03-27", 0.123e9, form="10-K"),
            fact("2010-12-27", "2011-12-25", 0.714e9, form="10-K"),
            fact("2011-03-28", "2011-06-26", 0.171e9, form="10-K"),
            fact("2011-06-27", "2011-09-25", 0.207e9, form="10-K"),
            fact("2011-09-26", "2011-12-25", 0.213e9, form="10-K"),
        ]}},
    }
    rows = F.resolve({"facts": {"us-gaap": gaap}})
    q4 = next(r for r in rows if r["period_end"] == "2011-12-25")
    assert q4["revenue"] == pytest.approx(0.213e9)


# ── Provenance / dedupe ──────────────────────────────────────────────────────
def test_the_latest_filing_wins_for_a_restated_period():
    points = [fact("2025-01-01", "2025-03-31", 100.0, filed="2025-05-01"),
              fact("2025-01-01", "2025-03-31", 110.0, filed="2026-04-30")]
    assert F._latest(points)["val"] == 110.0


def test_a_periodic_report_beats_a_later_proxy_statement():
    """AMZN's FY2025 net income appears in both a 10-K and a later DEF 14A.

    Same figure, but the filing that *is* the financial statement is the one the
    `form` column should name.
    """
    points = [fact("2025-01-01", "2025-12-31", 77.67e9, form="10-K", filed="2026-02-06"),
              fact("2025-01-01", "2025-12-31", 77.67e9, form="DEF 14A", filed="2026-04-09")]
    assert F._latest(points)["form"] == "10-K"


# ── I6: the gate ─────────────────────────────────────────────────────────────
def test_gate_accepts_a_clean_fetch():
    assert F.gate(quarters(1e9, 2e9, 3e9, 4e9), []) is None


def test_gate_rejects_an_empty_fetch():
    assert F.gate([], []) == "empty result"


def test_gate_rejects_unsorted_or_duplicated_periods():
    rows = quarters(1e9, 2e9, 3e9, 4e9)
    assert "ascending" in F.gate(list(reversed(rows)), [])
    assert "ascending" in F.gate(rows + rows[-1:], [])


def test_gate_rejects_negative_revenue():
    assert "negative revenue" in F.gate(quarters(1e9, -2e9, 3e9, 4e9), [])


def test_gate_rejects_gross_profit_above_revenue():
    rows = [row("2025-12-31", 2026, "Q4", revenue=1e9, gross_profit=2e9)]
    assert "gross profit exceeds revenue" in F.gate(rows, [])


def test_gate_allows_operating_income_above_gross_profit():
    """AMD's 2009 Q4 booked the GlobalFoundries settlement gain above the
    operating line. Comparing those two would reject a decade of correct data
    over a real figure."""
    rows = [row("2009-12-26", 2009, "Q4",
                revenue=1.646e9, gross_profit=0.735e9, operating_income=1.288e9)]
    assert F.gate(rows, []) is None


def test_gate_rejects_a_period_count_regression():
    old = quarters(1e9, 2e9, 3e9, 4e9) * 3
    assert "regression" in F.gate(quarters(1e9, 2e9, 3e9, 4e9)[:1], old)


def test_gate_ignores_stored_periods_newer_than_the_fetch():
    old = quarters(1e9, 2e9, 3e9, 4e9) + [row("2030-12-31", 2031, "Q4")]
    assert F.gate(quarters(1e9, 2e9, 3e9, 4e9), old) is None


# ── update() plumbing ────────────────────────────────────────────────────────
@pytest.fixture
def facts_payload():
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        fact("2025-01-01", "2025-03-31", 1e9),
        fact("2025-01-01", "2025-06-30", 2.1e9),
        fact("2025-01-01", "2025-09-30", 3.3e9),
        fact("2025-01-01", "2025-12-31", 4.6e9, form="10-K"),
    ]}}}}}


def test_update_creates_then_reports_unchanged(tmp_path, monkeypatch, facts_payload):
    monkeypatch.setattr(F, "fetch_facts", lambda cik: facts_payload)
    assert F.update("nvda", "1", store_dir=tmp_path)[0] == "created"
    assert F.update("nvda", "1", store_dir=tmp_path)[0] == "unchanged"


def test_update_skips_a_filer_with_no_us_gaap_facts(tmp_path, monkeypatch):
    """TSM, GRAB and NU return zero us-gaap concepts — they file IFRS."""
    monkeypatch.setattr(F, "fetch_facts",
                        lambda cik: {"facts": {"ifrs-full": {"Revenue": {}}}})
    status, detail = F.update("tsm", "1", store_dir=tmp_path)
    assert status == "skipped" and "IFRS" in detail


def test_update_skips_an_etf_with_no_facts_at_all(tmp_path, monkeypatch):
    def raise_no_facts(cik):
        raise F.NoFacts(cik)
    monkeypatch.setattr(F, "fetch_facts", raise_no_facts)
    assert F.update("qqq", "1", store_dir=tmp_path)[0] == "skipped"


def test_update_reports_failure_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "fetch_facts", lambda cik: None)
    assert F.update("nvda", "1", store_dir=tmp_path)[0] == "failed"
    assert not F.store_path("nvda", tmp_path).exists()


def test_update_dry_run_writes_nothing(tmp_path, monkeypatch, facts_payload):
    monkeypatch.setattr(F, "fetch_facts", lambda cik: facts_payload)
    F.update("nvda", "1", store_dir=tmp_path, dry_run=True)
    assert not F.store_path("nvda", tmp_path).exists()


def test_update_leaves_the_store_untouched_when_the_gate_trips(tmp_path, monkeypatch):
    good = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        fact("2025-01-01", "2025-03-31", 1e9),
        fact("2025-01-01", "2025-12-31", 4.6e9, form="10-K"),
    ]}}}}}
    monkeypatch.setattr(F, "fetch_facts", lambda cik: good)
    F.update("nvda", "1", store_dir=tmp_path)
    before = F.store_path("nvda", tmp_path).read_bytes()

    monkeypatch.setattr(F, "fetch_facts",
                        lambda cik: {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
                            fact("2025-01-01", "2025-03-31", -1e9)]}}}}})
    assert F.update("nvda", "1", store_dir=tmp_path)[0] == "skipped"
    assert F.store_path("nvda", tmp_path).read_bytes() == before


# ── the committed store itself ───────────────────────────────────────────────
def test_committed_store_round_trips_byte_for_byte():
    """I1 against real data, not fixtures — the check that catches drift."""
    if not F.STORE_DIR.exists():
        pytest.skip("no committed fundamentals store")
    for path in sorted(F.STORE_DIR.glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        assert F.serialise(F.parse(text)) == text, path.name


def test_committed_store_passes_its_own_gate():
    if not F.STORE_DIR.exists():
        pytest.skip("no committed fundamentals store")
    for path in sorted(F.STORE_DIR.glob("*.csv")):
        rows = F.parse(path.read_text(encoding="utf-8"))
        assert F.gate(rows, []) is None, f"{path.name}: {F.gate(rows, [])}"
