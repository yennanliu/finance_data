"""Live smoke test for the annualreports.com 10-K scraper.

This one test actually hits https://www.annualreports.com to catch the class of
breakage that motivated the scraper fix: the site changing its HTML/title
structure so that PDF links or the company name stop parsing.

It is opt-in — skipped unless ``RUN_LIVE=1`` is set — so the normal offline test
suite and CI never touch the network. The scheduled ``scraper_smoke.yml``
workflow sets ``RUN_LIVE=1`` to run it on a cadence.
"""

import os
from datetime import date

import pytest

import download_10k_pdf as d10
import edgar_common as ec

pytestmark = pytest.mark.live

RUN_LIVE = os.environ.get("RUN_LIVE") == "1"
skip_unless_live = pytest.mark.skipif(
    not RUN_LIVE, reason="live network test; set RUN_LIVE=1 to run"
)


@skip_unless_live
def test_annualreports_apple_page_still_parses():
    soup = d10.fetch_page("apple-inc")
    assert soup is not None, "annualreports.com returned no page for apple-inc"

    # Company name must parse cleanly (no trailing "_-" from a changed title).
    name = d10.parse_company_name(soup, "fallback")
    assert name == "Apple_Inc", f"unexpected company name: {name!r}"

    # PDF archive links must still be discoverable, newest first.
    links = d10.extract_pdf_links(soup)
    years = [y for y, _ in links]
    assert years, "no annual-report PDF links found — site structure may have changed"
    assert years == sorted(years, reverse=True)
    assert max(years) >= 2023, f"latest report year {max(years)} looks stale"
    assert all(u.startswith("https://www.annualreports.com") for _, u in links)


# ── EDGAR rolling window ─────────────────────────────────────────────────────
# The offline tests pin the arithmetic against a frozen clock. This one runs
# against the real calendar and the real EDGAR, which is what actually caught
# the class of bug these guard: a query that silently matches nothing makes the
# download job go green having fetched zero filings, and nobody notices until
# someone wonders why a ticker looks stale.

@skip_unless_live
def test_one_year_window_still_returns_quarterlies_today():
    """Whatever today's date is, a --years 1 10-Q query for a large quarterly
    filer must return filings. Under the old calendar-year cutoff this returned
    nothing from 1 January until the first filing of the new year."""
    cik = ec.get_cik("NVDA")
    assert cik, "NVDA not found in EDGAR — ticker→CIK lookup may have changed"

    filings = ec.get_filings(cik, "10-Q", years=1)
    assert filings, (
        "a one-year 10-Q window returned no filings for NVDA; the window is "
        "almost certainly broken rather than the company having stopped filing"
    )
    # A quarterly filer produces ~3 10-Qs a year (the fourth quarter is folded
    # into the 10-K), so a correct rolling year sees at least two.
    assert len(filings) >= 2, f"only {len(filings)} 10-Q(s) in a rolling year: {filings}"

    newest = max(f["date"] for f in filings)
    cutoff = ec._cutoff_date(1)
    assert newest >= cutoff, f"newest filing {newest} predates the cutoff {cutoff}"


@skip_unless_live
def test_cutoff_is_a_full_year_behind_today():
    """Catches the window collapsing without needing EDGAR to have new data."""
    cutoff = date.fromisoformat(ec._cutoff_date(1))
    days = (date.today() - cutoff).days
    assert 364 <= days <= 367, f"one-year window spans {days} days, not ~365"
