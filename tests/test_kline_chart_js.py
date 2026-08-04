"""Runs the kline-chart.js harness (tests/js/kline_chart_harness.mjs) as a test.

The widget is the one piece of the chart pipeline pytest cannot reach directly,
and it owns the per-widget option handling — as-of truncation above all, which is
what keeps a dated report from showing today's prices. The harness executes the
shipping JS against a minimal DOM and a fake Lightweight Charts, then asserts on
what the chart was actually asked to draw.

Skipped when node is unavailable, so the Python-only suite still runs anywhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "kline_chart_harness.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_kline_chart_widget_harness():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    # The harness prints "N passed, M failed" either way; surface it on failure
    # so CI shows which assertion broke without re-running anything.
    assert proc.returncode == 0, (
        f"kline-chart.js harness failed\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert "0 failed" in proc.stdout, proc.stdout


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_widget_js_parses():
    """`node --check` on the shipping file: a syntax error would break every
    chart on the site, and the harness alone wouldn't localise it."""
    proc = subprocess.run(
        [NODE, "--check", str(ROOT / "docs" / "javascripts" / "kline-chart.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
