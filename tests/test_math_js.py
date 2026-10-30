"""Runs the math.js harness (tests/js/math_harness.mjs) as a test.

Report equations reach the page as `<span class="arithmatex">\\( … \\)</span>`;
math.js fetches KaTeX and renders them. Without it the page shows raw TeX, as
every report with `$$ … $$` or `$ … $` did until 2026-10-30.

Skipped when node is unavailable, so the Python-only suite still runs anywhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "math_harness.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_math_harness():
    proc = subprocess.run([NODE, str(HARNESS)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    assert "0 failed" in proc.stdout, proc.stdout


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_math_js_parses():
    proc = subprocess.run([NODE, "--check", str(ROOT / "docs" / "javascripts" / "math.js")],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
