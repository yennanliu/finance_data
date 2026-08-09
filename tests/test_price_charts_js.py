"""Runs the price-charts.js harness (tests/js/price_charts_harness.mjs) as a test.

price-charts.js renders the Price Data section's derived charts — drawdown,
rolling volatility and the return-distribution histogram. The arithmetic behind
them is Python (tests/test_price_analytics.py), so what this covers is the part
pytest cannot reach: series selection, chart kind, the crosshair readout and the
degradation paths.

Skipped when node is unavailable, so the Python-only suite still runs anywhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "price_charts_harness.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_price_charts_widget_harness():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"price-charts.js harness failed\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert "0 failed" in proc.stdout, proc.stdout


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_price_charts_js_parses():
    """`node --check` on the shipping file: a syntax error would silently blank
    every chart in the Price Data section."""
    proc = subprocess.run(
        [NODE, "--check", str(ROOT / "docs" / "javascripts" / "price-charts.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
