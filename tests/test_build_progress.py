"""Tests for the daily progress summary builder."""

from scripts.build_progress import build


class TestBuild:
    def test_analysis_report_becomes_a_site_link(self):
        out = build(["ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md"])
        assert (
            "- [NVDA technical-analysis_2026-08-30]"
            "(https://yennanliu.github.io/finance_data/reports/NVDA/"
            "technical-analysis_2026-08-30/)" in out
        )

    def test_news_goes_under_its_own_heading_and_base_url(self):
        out = build(["ai_gen_report/market_news/AMD/market_news_2026-08-30_gemini.md"])
        assert "### Market News" in out
        assert "finance_data/market_news/AMD/" in out

    def test_all_three_analysis_roots_are_recognised(self):
        out = build(
            [
                "ai_gen_report/stock/A/dcf-valuation_2026-08-30.md",
                "ai_gen_report/fundamental/B/fundamental-analysis_2026-08-30.md",
                "ai_gen_report/technical/C/technical-analysis_2026-08-30.md",
            ]
        )
        for t in ("A", "B", "C"):
            assert f"[{t} " in out

    def test_ticker_is_uppercased_in_the_label_but_not_the_url(self):
        out = build(["ai_gen_report/technical/2330.tw/technical-analysis_2026-08-30.md"])
        assert "[2330.TW " in out
        assert "/reports/2330.tw/" in out

    def test_news_section_omitted_when_there_is_no_news(self):
        out = build(["ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md"])
        assert "### Stock Analysis" in out
        assert "### Market News" not in out

    def test_non_markdown_is_ignored(self):
        out = build(["data/prices/NVDA.csv", "ai_gen_report/technical/NVDA/chart.png"])
        assert out.strip() == "### Stock Analysis"

    def test_paths_outside_report_roots_are_ignored(self):
        out = build(["ws/2026_08_30_open.txt", "qa/README.md", "progress/p.txt"])
        assert out.strip() == "### Stock Analysis"

    def test_duplicates_are_collapsed(self):
        p = "ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md"
        # Count entry lines, not occurrences of the ticker — it appears twice
        # in a single line (once in the label, once in the URL).
        lines = [ln for ln in build([p, p]).splitlines() if ln.startswith("- ")]
        assert len(lines) == 1

    def test_output_is_sorted_for_a_stable_diff(self):
        out = build(
            [
                "ai_gen_report/technical/TSLA/technical-analysis_2026-08-30.md",
                "ai_gen_report/technical/AMD/technical-analysis_2026-08-30.md",
            ]
        )
        assert out.index("AMD") < out.index("TSLA")

    def test_empty_input_still_produces_a_valid_file(self):
        assert build([]).strip() == "### Stock Analysis"

    def test_blank_lines_are_tolerated(self):
        out = build(["", "  ", "ai_gen_report/technical/NVDA/t_2026-08-30.md"])
        assert "NVDA" in out

    def test_bare_file_directly_under_a_root_is_skipped(self):
        """A path with no ticker directory must not produce a broken link."""
        assert build(["ai_gen_report/technical/stray.md"]).strip() == "### Stock Analysis"

    def test_ends_with_newline(self):
        assert build(["ai_gen_report/technical/NVDA/t.md"]).endswith("\n")
