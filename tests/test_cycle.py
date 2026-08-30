"""Tests for the generation-cycle naming used by the artifact collector."""

from datetime import datetime, timedelta, timezone

import pytest

from scripts.cycle import (
    CYCLE_START_HOUR_UTC,
    artifact_name,
    artifact_prefix,
    belongs_to_cycle,
    cycle_date,
)


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class TestCycleDate:
    def test_at_boundary_starts_new_cycle(self):
        assert cycle_date(utc(2026, 8, 30, 17, 0)) == "2026-08-30"

    def test_one_minute_before_boundary_is_previous_cycle(self):
        assert cycle_date(utc(2026, 8, 30, 16, 59)) == "2026-08-29"

    def test_evening_run_belongs_to_same_day(self):
        # daily_market_news ROBO at 23:10
        assert cycle_date(utc(2026, 8, 30, 23, 10)) == "2026-08-30"

    def test_after_midnight_belongs_to_previous_day(self):
        # daily_analysis NBIS technical at 01:30 the next calendar day
        assert cycle_date(utc(2026, 8, 31, 1, 30)) == "2026-08-30"

    def test_last_generator_of_window(self):
        # ROBO fundamental at 03:40, the final cron of the window
        assert cycle_date(utc(2026, 8, 31, 3, 40)) == "2026-08-30"

    def test_collector_run_time_matches_the_cycle_it_collects(self):
        # collect_daily.yml fires at 03:50
        assert cycle_date(utc(2026, 8, 31, 3, 50)) == "2026-08-30"

    def test_deploy_time_still_in_same_cycle(self):
        # deploy cron at 05:00 must not roll into the next cycle
        assert cycle_date(utc(2026, 8, 31, 5, 0)) == "2026-08-30"

    def test_whole_generation_window_agrees_on_one_name(self):
        """Every cron minute from 17:00 to 03:40 must yield one cycle name."""
        start = utc(2026, 8, 30, 17, 0)
        end = utc(2026, 8, 31, 3, 40)
        seen = set()
        t = start
        while t <= end:
            seen.add(cycle_date(t))
            t += timedelta(minutes=10)
        assert seen == {"2026-08-30"}, f"window split across cycles: {seen}"

    def test_month_rollover(self):
        assert cycle_date(utc(2026, 9, 1, 2, 0)) == "2026-08-31"

    def test_year_rollover(self):
        assert cycle_date(utc(2027, 1, 1, 3, 0)) == "2026-12-31"

    def test_leap_day(self):
        assert cycle_date(utc(2028, 3, 1, 1, 0)) == "2028-02-29"

    def test_non_utc_timezone_is_converted_not_truncated(self):
        """A +08:00 timestamp must be judged on its UTC hour."""
        taipei = timezone(timedelta(hours=8))
        # 2026-08-31 01:00 +08:00 == 2026-08-30 17:00 UTC -> new cycle
        assert cycle_date(datetime(2026, 8, 31, 1, 0, tzinfo=taipei)) == "2026-08-30"
        # 2026-08-31 00:59 +08:00 == 2026-08-30 16:59 UTC -> previous cycle
        assert cycle_date(datetime(2026, 8, 31, 0, 59, tzinfo=taipei)) == "2026-08-29"

    def test_naive_datetime_is_rejected(self):
        """A naive timestamp would silently shift the 17:00 boundary."""
        with pytest.raises(ValueError, match="timezone-aware"):
            cycle_date(datetime(2026, 8, 30, 17, 0))

    def test_boundary_constant_is_before_first_cron(self):
        assert CYCLE_START_HOUR_UTC == 17


class TestArtifactNaming:
    def test_prefix(self):
        assert artifact_prefix("2026-08-30") == "cycle-2026-08-30"

    def test_name_is_prefixed_so_collector_can_filter(self):
        name = artifact_name("2026-08-30", "analysis", "NVDA", "technical")
        assert name.startswith(artifact_prefix("2026-08-30"))
        assert name == "cycle-2026-08-30-analysis-NVDA-technical"

    def test_dots_in_ticker_are_preserved(self):
        name = artifact_name("2026-08-30", "analysis", "2330.TW", "fundamental")
        assert name == "cycle-2026-08-30-analysis-2330.TW-fundamental"

    @pytest.mark.parametrize("bad", ['"', ":", "<", ">", "|", "*", "?", "\\", "/"])
    def test_characters_github_rejects_are_replaced(self, bad):
        name = artifact_name("2026-08-30", "analysis", f"AA{bad}BB")
        assert bad not in name
        assert "AA_BB" in name

    def test_distinct_tickers_never_collide(self):
        names = {
            artifact_name("2026-08-30", "analysis", t, a)
            for t in ("NVDA", "AMD", "2330.TW")
            for a in ("fundamental", "technical")
        }
        assert len(names) == 6

    def test_artifact_belongs_only_to_its_own_cycle(self):
        today = artifact_name("2026-08-30", "analysis", "NVDA", "technical")
        assert belongs_to_cycle(today, "2026-08-30")
        assert not belongs_to_cycle(today, "2026-08-31")
        assert not belongs_to_cycle(today, "2026-08-29")

    def test_truncated_date_does_not_sweep_in_a_neighbouring_cycle(self):
        """"cycle-2026-08-3" is a raw string prefix of "cycle-2026-08-30-..."."""
        today = artifact_name("2026-08-30", "analysis", "NVDA", "technical")
        assert today.startswith(artifact_prefix("2026-08-3"))  # the trap
        assert not belongs_to_cycle(today, "2026-08-3")  # guarded

    def test_unrelated_artifact_names_are_excluded(self):
        for name in ("build-output", "cycle", "cycle-", "site-2026-08-30"):
            assert not belongs_to_cycle(name, "2026-08-30")
