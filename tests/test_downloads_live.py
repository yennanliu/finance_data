"""Live smoke test for the annualreports.com 10-K scraper.

This one test actually hits https://www.annualreports.com to catch the class of
breakage that motivated the scraper fix: the site changing its HTML/title
structure so that PDF links or the company name stop parsing.

It is opt-in — skipped unless ``RUN_LIVE=1`` is set — so the normal offline test
suite and CI never touch the network. The scheduled ``scraper_smoke.yml``
workflow sets ``RUN_LIVE=1`` to run it on a cadence.
"""

import os

import pytest

import download_10k_pdf as d10

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
