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
    assert out[title_end:].lstrip().startswith("**⚠️ 程式複算更正**")
    assert "應為 **$324.23**" in out and "MOS 為 **-15.5%**" in out
    assert "若用報告所寫的 $334.34 則 MOS 為 -12.0%" in out
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


def test_title_notice_renders_apart_from_the_report_date_quote():
    """Python-Markdown merges adjacent quotes, so the notice must not be one."""
    markdown = pytest.importorskip("markdown")
    text = s88(TSLA).replace("\n\n> **現價**", "\n> **報告日期**：x ｜ **現價**")
    html = markdown.markdown(A.annotate(text, A.check(text, price=374.58)))
    quote = html[html.index("<blockquote>"):html.index("</blockquote>")]
    assert "程式複算更正" not in quote and "報告日期" in quote


# ── headline MOS and DCF premium (prompt rule 16) ────────────────────────────

def dashboard(mos: str, premium: str, dcf: str = "$576.45") -> str:
    return (f"| **DCF 內在價值（基準）** | **{dcf}** ｜ 現價溢價 **{premium}** |\n"
            f"| **安全邊際（MOS）** | **{mos}** ＝ (加權合理價值 − 現價) ÷ 加權合理價值 |\n")


def test_a_premium_with_the_wrong_sign_is_caught():
    """AMD 2026-10-21: $552.72 against a $576.45 DCF is a 4.1% discount, but
    the report printed +4.1% in three places."""
    out = A.valuation_mismatches(dashboard("+9.7%", "+4.1%"), 552.72, 612.44)
    assert out == [{"metric": "premium", "stated": 4.1, "expected": -4.1}]


def test_a_mos_that_its_own_figures_do_not_give_is_caught():
    """NVDA 2026-10-23: MOS +25% on a fair value its price puts at +38.0%."""
    out = A.valuation_mismatches(dashboard("+25%", "-35.9%", "$328.95"), 210.96, 340.23)
    assert [v["metric"] for v in out] == ["MOS"]
    assert out[0]["expected"] == 38.0


def test_consistent_figures_and_rounding_pass():
    assert A.valuation_mismatches(dashboard("+10%", "−4%"), 552.72, 612.44) == []


def test_an_unsigned_premium_is_not_guessed():
    text = "| **DCF 內在價值（基準）** | $368.55 ｜ 現價折溢價 16% |\n"
    assert A.valuation_mismatches(text, 321.68, None) == []


def test_premium_words_carry_the_sign_when_the_number_does_not():
    text = "| DCF 內在價值評估 | 基準 DCF 每股內在價值 $246.20（溢價 10.2%） |\n"
    out = A.valuation_mismatches(text, 223.55, None)
    assert out and out[0]["stated"] == 10.2 and out[0]["expected"] < 0


# ── correct(): write the recomputed total back (AMD 2026-10-23) ──────────────

AMD = """# AMD 基本面深度分析報告

| 1 | 執行摘要 | 評級 **🟡 持有** ｜ 加權合理價值 **$479.69** ｜ MOS **-7.7%** |

| **安全邊際（MOS）** | **-7.7%** ＝ ($479.69 − $516.79) ÷ $479.69 ｜ 營收年增 7.7% |

### 8.8 估值三角驗證

| **加權合理價值** | **$479.69** | **-7.2%** | **100%** |

`加權合理價值 = $403.07×40% + $520.00×30% + $480.00×20% + $560.00×10%`

- **安全邊際 MOS** ＝ (加權合理價值 $479.69 − 現價 $516.79) ÷ 加權合理價值 $479.69
  $= \\mathbf{-7.73\\%}$

### 8.9 局限
"""


def _corrected(text, price=516.79):
    r = A.check(text, price=price)
    return r, A.correct(text, r)


def test_correct_rewrites_the_total_mos_and_upside_everywhere():
    r, out = _corrected(AMD)
    total = f"${r['total']:,.2f}"                              # $469.23
    assert "479.69" not in out
    assert out.count(total) == 6
    assert "MOS **-10.1%**" in out and "**-10.1%** ＝" in out  # TOC and §1.0
    assert "| **-9.2%** |" in out                               # upside beside the value
    assert r"\mathbf{-10.14\%}" in out                          # LaTeX, a line below its label
    assert A.check(out, price=516.79)["status"] == "ok"


def test_correct_leaves_unrelated_percentages_alone():
    """The §1.0 row also carries a 7.7% growth rate; only -7.7% was the MOS."""
    _, out = _corrected(AMD)
    assert "營收年增 7.7%" in out


def test_a_total_that_is_one_of_the_terms_is_not_rewritten():
    """TSLA 2026-10-23 printed its relative-valuation term ($194.24) as the
    weighted total; replacing it everywhere would rewrite that term too."""
    text = AMD.replace("$480.00×20%", "$479.69×20%")
    r, out = _corrected(text)
    assert r["status"] == "mismatch" and out == text


def test_weights_not_summing_to_100_are_not_rewritten():
    text = AMD.replace("$560.00×10%", "$560.00×5%")
    r, out = _corrected(text)
    assert out == text


def test_a_corrected_report_says_so_and_warns_on_a_rating_band_change():
    r, out = _corrected(AMD)
    note = A.annotate(out, {**r, "status": "corrected"})
    head = note.split("### 8.8")[0]
    assert "程式複算更正" in head and "$479.69" in head          # the model's figure, named
    assert "「減碼」" in head and "「持有」" in head              # −7.7% → −10.1% crosses −10%
    assert "已改為上方複算值" in note


def test_rating_bands_follow_prompt_rule_20():
    assert [A.rating_band(m) for m in (-30, -12, 0, 12)] == ["賣出", "減碼", "持有", "買入"]
    assert A.rating_band(30).startswith("強烈買入")


# ── §8.8 product line ────────────────────────────────────────────────────────

RKLB = s88("加權合理價值 = $57.65 × 50% + $65.00 × 25% + $35.20 × 10% + $52.00 × 10% + $102.15 × 5%\n\n"
           "= $28.825 + $16.250 + $3.250 + $5.200 + $5.108 = $58.90", stated="$58.90")


def test_fix_products_rewrites_a_wrong_product_to_its_terms():
    r = A.check(RKLB)
    assert r["status"] == "ok"
    out = A.fix_products(RKLB, r)
    assert "$28.825 + $16.250 + $3.520 + $5.200 + $5.108 = $58.90" in out


def test_fix_products_leaves_a_line_whose_total_it_would_contradict():
    """The products summing to the line's own total but not to the terms means
    the run is something else (or the total is wrong): leave it."""
    text = RKLB.replace("= $58.90\n", "= $58.63\n")
    assert A.fix_products(text, A.check(text)) == text


def test_fix_products_waits_for_a_correct_total():
    text = RKLB.replace("**$58.90**", "**$60.00**")
    r = A.check(text)
    assert r["status"] == "mismatch"
    assert A.fix_products(text, r) == text


def test_fix_products_needs_the_runs_own_total():
    text = RKLB.replace(" = $58.90\n", "\n")
    assert A.fix_products(text, A.check(text)) == text


def test_fix_products_keeps_a_line_whose_rewritten_products_would_not_add_up():
    """The run's own total ($10.80) is not the terms' sum ($10.40): rewriting
    the products would leave "$5.20 + $5.20 = $10.80"."""
    text = s88("加權合理價值 = $10.40 × 50% + $10.40 × 50%\n\n= $5.00 + $5.80 = $10.80", stated="$10.40")
    r = A.check(text)
    assert r["status"] == "ok"
    assert A.fix_products(text, r) == text



# ── correct(): figures printed to a different rounding ───────────────────────

MRVL = """# MRVL 基本面深度分析報告

> **現價** $233.78

| **預期報酬（基準情境 12M）** | −30.0%（價格向加權合理價值 $163.78 收斂） |

### 8.8 估值三角驗證

| 估值方法 | 價值 | 上行空間 | 權重 |
|---|---|---|---|
| DCF | $149.63 | −36.0% | 45% |
| **加權合理價值** | **$163.78** | **−30.0%** | 100% |

`加權合理價值 = $149.63×45% + $161.24×20% + $158.40×15% + $138.50×10% + $341.44×10%`

- **隱含上行空間** = ($163.78 − $233.78) ÷ $233.78 = −$70.00 ÷ $233.78 = **−30.0%**

### 8.9 局限
"""


def test_correct_rewrites_an_upside_printed_one_unit_off_and_its_difference():
    """MRVL 2026-10-27: upside (−29.94%) printed −30.0%, beside a −$70.00
    difference; both survived the exact-match rewrite."""
    r = A.check(MRVL, price=233.78)
    out = A.correct(MRVL, r)
    assert "−30.0%" not in out and out.count("−26.7%") == 3
    assert "−$62.44 ÷ $233.78" in out


def test_correct_leaves_a_methods_own_upside_under_a_table_header():
    """The DCF row's −36.0% is near no old figure, and a whole-percent weight
    is never loosened; only the 加權合理價值 row changes."""
    out = A.correct(MRVL, A.check(MRVL, price=233.78))
    assert "| DCF | $149.63 | −36.0% | 45% |" in out
