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
