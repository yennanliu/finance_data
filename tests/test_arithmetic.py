"""Tests for the §8.8 weighted-fair-value re-check (analysis.validate.arithmetic).

The term formats below are the ones the 2026-10-22 reports actually used; see
docs/FUNDAMENTAL_REPORT_REVIEW.md §12.3 for which report each comes from.
"""

import pytest

from scripts.analysis.validate import arithmetic as A

pytestmark = pytest.mark.unit


def s88(body: str, stated: "str | None" = "$334.34") -> str:
    table = (f"| 估值方法 | 價值 |\n|---|---|\n| **加權合理價值** | **{stated}** |\n"
             if stated else "")
    return (f"# TSLA 基本面深度分析報告\n\n> **現價** $374.58\n\n"
            f"## 1. 執行摘要\n\n### 8.8 估值三角驗證\n\n{table}\n{body}\n\n### 8.9 局限\n")


TSLA = "`$328.25×45% + $164.25×10% + $283.50×15% + $382.40×15% + $401.40×15%`"


def test_recomputes_the_total_from_the_reports_own_terms():
    r = A.check(s88(TSLA))
    assert r["status"] == "mismatch"
    assert (r["stated"], r["total"], r["weights_pct"]) == (334.34, 324.23, 100.0)
    assert r["diff_pct"] == pytest.approx(3.12)


def test_mos_and_upside_follow_the_corrected_total():
    r = A.check(s88(TSLA))
    assert r["price"] == 374.58
    assert (r["stated_mos"], r["mos"]) == (-12.0, -15.5)


def test_rounding_within_tolerance_is_ok():
    """PLTR: $182.13 written as ≈ $182.20 (0.04%)."""
    body = r"$$\$175.16 \times 40\% + \$182.00 \times 25\% + \$168.50 \times 15\% + \$206.43 \times 20\%$$"
    assert A.check(s88(body, stated="$182.20"))["status"] == "ok"


def test_decimal_weights_and_parentheses():
    """VST: ($181.75 × 0.40) + ($166.64 × 0.20) + …"""
    body = "($181.75 × 0.40) + ($166.64 × 0.20) + ($182.40 × 0.20) + ($173.00 × 0.10) + ($208.86 × 0.10)"
    r = A.check(s88(body, stated="$182.20"))
    assert r["total"] == pytest.approx(180.69, abs=0.01) and r["status"] == "mismatch"


def test_nt_dollar_terms():
    body = "`加權合理價值 = NT$218.70 × 50% + NT$216.60 × 25% + NT$212.80 × 15% + NT$220.50 × 10%`"
    assert A.check(s88(body, stated="NT$216.67"))["total"] == pytest.approx(217.47, abs=0.01)


def test_total_taken_from_the_derivation_when_there_is_no_table_row():
    """NBIS printed no table row, only `= **$228.00**（四捨五入至整數位）`."""
    body = ("$221.38 × 45% + $235.00 × 20% + $215.00 × 15% + $240.00 × 10% + $281.00 × 10%\n"
            "= $99.62 + $47.00 + $32.25 + $24.00 + $28.10 = **$228.00**（四捨五入至整數位）")
    r = A.check(s88(body, stated=None))
    assert (r["stated"], r["total"], r["status"]) == (228.0, 230.97, "mismatch")


def test_weights_that_do_not_sum_to_100_are_a_mismatch():
    r = A.check(s88("$100 × 50% + $100 × 40%", stated="$90.00"))
    assert r["weights_pct"] == 90.0 and r["status"] == "mismatch"


def test_a_report_without_8_8_is_unparsed():
    assert A.check("# X\n\n## 1. 摘要\n")["status"] == "unparsed"


def test_missing_chapters():
    text = "\n".join(f"## {n}. x" for n in range(1, 11))
    assert A.missing_chapters(text) == [11]


# ── annotate ─────────────────────────────────────────────────────────────────
def test_annotate_flags_a_mismatch_under_the_title_and_in_8_8():
    text = s88(TSLA)
    out = A.annotate(text, A.check(text))
    title_end = out.index("\n", out.index("# TSLA")) + 1
    assert out[title_end:].lstrip().startswith("> ⚠️ **程式複算更正**")
    assert "應為 **$324.23**" in out and "MOS 為 **-15.5%**" in out
    s = A.section(out, "8.8")
    assert "🔎 **程式複算" in s and "相差 +3.12%" in s
    assert "$334.34" in out           # the model's figure is left visible, not rewritten


def test_annotate_confirms_a_correct_total_without_a_title_notice():
    text = s88(TSLA, stated="$324.23")
    out = A.annotate(text, A.check(text))
    assert "程式複算更正" not in out and "✅ 與本節所寫數值一致" in A.section(out, "8.8")


def test_annotate_leaves_an_unparsed_report_alone():
    text = "# X\n\n## 1. 摘要\n"
    assert A.annotate(text, A.check(text)) == text
