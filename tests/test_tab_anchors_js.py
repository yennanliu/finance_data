"""Runs the tab-anchors.js harness (tests/js/tab_anchors_harness.mjs) as a test.

The Market Data pages put ~22 charts into five content tabs. The table of
contents still lists every heading on the page, so a TOC entry pointing into a
tab that is not open scrolls to a `display: none` panel and looks broken.
tab-anchors.js opens the owning tab first; this is the only place that behaviour
is checked, since it is pure DOM work that pytest cannot reach.

Skipped when node is unavailable, so the Python-only suite still runs anywhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "tab_anchors_harness.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_tab_anchors_harness():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"tab-anchors.js harness failed\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert "0 failed" in proc.stdout, proc.stdout


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_tab_anchors_js_parses():
    """`node --check` on the shipping file: a syntax error here would leave
    every in-page link on a tabbed page silently dead."""
    proc = subprocess.run(
        [NODE, "--check", str(ROOT / "docs" / "javascripts" / "tab-anchors.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
