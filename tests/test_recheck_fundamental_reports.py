"""Tests for the §8.8 backfill (scripts/recheck_fundamental_reports.py).

It gives a report written before the generation-time recheck what the pipeline
would give it today. The body below is TSLA 2026-10-23's §8.8: the terms sum
to $324.23, the model printed $334.34.
"""

import pytest

import recheck_fundamental_reports as R

pytestmark = pytest.mark.unit

FRONT = ('---\ntitle: "TSLA 基本面深度分析 2026-10-23"\ndate: 2026-10-23\nticker: TSLA\n'
         "analysis_type: fundamental-analysis\n")
BODY = """
# TSLA 基本面深度分析報告
> **報告日期**：2026-10-23

## 1. 執行摘要

| **安全邊際（MOS）** | **-12.0%** ＝ ($334.34 − $374.58) ÷ $334.34 |

### 8.8 估值三角驗證

| **加權合理價值** | **$334.34** |

`$328.25×45% + $164.25×10% + $283.50×15% + $382.40×15% + $401.40×15%`

### 8.9 局限
"""
OLD = FRONT + "price: 374.58\n---\n" + BODY


def test_an_old_report_is_corrected_annotated_and_recorded():
    out, fields = R.recheck(OLD)
    assert fields["arithmetic_check"] == "corrected"
    assert "arithmetic_check: corrected\nweighted_fair_value_stated: 334.34\n" in out
    assert "| **加權合理價值** | **$324.23** |" in out
    assert "**-15.5%** ＝ ($324.23 − $374.58)" in out
    assert out.count("✏️ 程式複算更正") == 1 and out.count("🔎") == 1
    assert out.startswith(FRONT)


def test_a_second_run_changes_nothing():
    once, _ = R.recheck(OLD)
    assert R.recheck(once) == (once, {})


def test_an_earlier_mismatch_notice_is_replaced_not_stacked():
    """A report the pipeline could only flag ("應為") is corrected now: its old
    notice and 「程式複算」 block go, the corrected ones come in."""
    from analysis.validate import arithmetic as A
    r = A.check(BODY, 374.58)
    flagged = FRONT + "price: 374.58\narithmetic_check: mismatch\n---\n" + A.annotate(BODY, r)
    assert "應為" in flagged
    out, fields = R.recheck(flagged)
    assert fields["arithmetic_check"] == "corrected"
    assert "應為" not in out
    assert out.count("程式複算更正") == 1 and out.count("🔎") == 1
    assert out.count("arithmetic_check:") == 1
    assert R.recheck(out) == (out, {})


def test_a_consistent_report_is_left_alone():
    ok = OLD.replace("$334.34", "$324.23").replace("-12.0%", "-15.5%")
    assert R.recheck(ok) == (ok, {})


def test_a_total_that_is_one_of_its_terms_is_flagged_not_rewritten():
    flagged_only = OLD.replace("$334.34", "$328.25")
    out, fields = R.recheck(flagged_only)
    assert fields["arithmetic_check"] == "mismatch"
    assert "| **加權合理價值** | **$328.25** |" in out and "應為" in out
