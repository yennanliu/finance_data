"""Tests for the displayed-equation re-check (analysis.validate.derivation).

The chains below are the ones RKLB 2026-10-28 §8.8 printed: both ends right,
the middle invented.
"""

import pytest

from scripts.analysis.validate import derivation as D

pytestmark = pytest.mark.unit

SUM = (r"$$\text{加權合理價值} = \$28.825 + \$16.250 + \$3.520 + \$5.200 + \$5.108"
       r" = \mathbf{\$59.323} \approx \mathbf{\$58.90}$$")
MOS = (r"$$\text{MOS} = \frac{\text{加權合理價值} - \text{現價}}{\text{加權合理價值}}"
       r" = \frac{\$58.90 - \$58.60}{\$58.90} = \frac{+\$0.72}{\$58.90} = \mathbf{+0.5\%}$$")


def test_a_sum_that_does_not_add_up_is_caught():
    bad = D.check(SUM)
    assert len(bad) == 2                          # "= $59.323" and "$59.323 ≈ $58.90"
    assert bad[0]["computed"] == pytest.approx(58.903)
    assert bad[0]["stated"] == pytest.approx(59.323)


def test_a_wrong_difference_in_a_fraction_is_caught():
    bad = D.check(MOS)
    assert bad and bad[0]["right"].startswith(r"\frac{+$0.72}")


def test_fix_repairs_the_middle_of_a_chain_whose_ends_agree():
    out, n = D.fix(SUM + "\n\n" + MOS)
    assert n == 2
    assert r"\mathbf{\$58.903} \approx \mathbf{\$58.90}" in out
    assert r"\frac{+\$0.30}{\$58.90}" in out
    assert D.check(out) == []
    assert D.fix(out) == (out, 0)                 # idempotent


def test_fix_does_not_guess_when_the_ends_disagree():
    """"$25.18B ÷ 0.1371 = $1,836.72B" (AMD): nothing says which side is wrong."""
    text = r"$$\text{TV} = \$25.18\text{B} \div 0.1371 = \mathbf{\$1,836.72\text{B}}$$"
    assert len(D.check(text)) == 1
    assert D.fix(text) == (text, 0)


@pytest.mark.parametrize("chain", [
    r"$$\text{WACC} = 96.5\% \times 9.075\% + 3.5\% \times 1.853\% = 8.757\% + 0.065\% = \mathbf{8.822\%} \approx \mathbf{8.8\%}$$",
    r"$$\text{PV 合計} = \$6.06\text{B} + \$7.99\text{B} + \$9.54\text{B} = \mathbf{\$23.59\text{B}}$$",
    r"$$\frac{\$0.39}{\$6.67} = 5.92\%$$",           # 0.39 is rounded: 0.3945/6.67 = 5.91%
    r"$$\text{股數} = \frac{\$1,500}{\$32.00} = 46$$",  # a whole count, floored
    r"$$\text{Target 1} = \text{頸線 } \$190.00 + (\$190.00 - \$182.50) = \$197.50$$",
])
def test_correct_chains_and_rounding_pass(chain):
    assert D.check(chain) == []


@pytest.mark.parametrize("chain", [
    r"$$\text{目標價 T2} = 52\text{週歷史高點} = \$243.37$$",   # 52 is a label
    r"$$\text{MOS} = \frac{\text{加權合理價值} - \text{現價}}{\text{加權合理價值}}$$",
    r"$$\text{RSI} \ge 70 \implies \text{超買} = 1$$",
    r"$$\text{營收} = \$1.2\text{B} = \$1,200\text{M}$$",       # mixed units are not compared
])
def test_labels_symbols_and_mixed_units_are_not_checked(chain):
    assert D.check(chain) == []


def test_code_fences_are_ignored():
    text = "```\n$$1 + 1 = 3$$\n```\n"
    assert D.check(text) == []
    assert D.fix(text) == (text, 0)


def test_inline_dollar_math_is_checked_and_fixed():
    """RKLB 2026-10-28 writes its DCF steps as inline $ … $."""
    good = r"7. **ΔWC** = $(\$1,228.2\text{M} - \$890.0\text{M}) \times 5.0\% = \$338.2\text{M} \times 5.0\% = \mathbf{\$16.9M}$"
    assert D.check(good) == []
    bad = good.replace(r"\$338.2\text{M} \times", r"\$383.2\text{M} \times")
    assert len(D.check(bad)) == 2
    out, n = D.fix(bad)
    assert (out, n) == (good, 1)


def test_prose_prices_are_not_math():
    assert D.math_spans("現價 $58.60，目標價 $70.00，區間 $45 – $60。") == []


def test_a_span_continuing_an_expression_is_not_checked_from_its_first_figure():
    qqq = r"2. **稅前 Kd** = 利息費用 $\$0.535 \div$ 平均計息負債 $\$12.50 = \mathbf{4.28\%}$"
    meta = r"- **價格波動百分比**：$22.50 / $737.54 = \mathbf{3.05\%}$"
    assert D.check(qqq) == [] and D.check(meta) == []


def test_a_text_label_used_as_a_variable_is_not_arithmetic():
    """AMZN: "EV + 現金 $122.99B − 債務 $132.22B = $1,017.05B" — EV is a symbol."""
    text = (r"$\text{EV} + \text{現金及短投 } \$122.99\text{B} - \text{總債務 } \$132.22\text{B}"
            r" = \mathbf{\$1,017.05\text{B}}$")
    assert D.check(text) == []
    assert D.check(r"$\text{頸線 } \$190.00 + \$7.50 = \$197.50$") == []


def test_a_deduction_printed_as_negative_is_accepted():
    assert D.check(r"6. **− Capex** = $\$1,228.2\text{M} \times 12.0\% = \mathbf{-\$147.4M}$") == []
    assert len(D.check(r"$\$1,228.2\text{M} \times 12.0\% = \mathbf{-\$150.0M}$")) == 1


@pytest.mark.parametrize("segment, value", [
    (r"\$890.0\text{M} \times (1 + 38.0\%)", 1228.2),
    (r"12.0\%", 0.12),
    (r"100\%", 1.0),
    (r"5\%", 0.05),
])
def test_percentages_of_any_width_evaluate(segment, value):
    """"12.0%" once became "1(2.0/100)": every rate of 10% or more was
    silently unevaluable and its step never checked."""
    assert D.evaluate(segment) == pytest.approx(value)
