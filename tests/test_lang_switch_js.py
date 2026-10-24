"""Runs the lang-switch.js harness (tests/js/lang_switch_harness.mjs) as a test.

Material's instant navigation swaps the page body and <head> but never the
header, so the 文A language menu kept the links of the first page loaded —
switching language from a report sent the reader to the other tree's home
page. lang-switch.js re-points the menu from the <head> targets main.html
publishes; this is the only place that DOM behaviour is checked.

Skipped when node is unavailable, so the Python-only suite still runs anywhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "lang_switch_harness.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_lang_switch_harness():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"lang-switch.js harness failed\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert "0 failed" in proc.stdout, proc.stdout


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_lang_switch_js_parses():
    """`node --check` on the shipping file: a syntax error would leave the
    menu pointing at whatever page was loaded first."""
    proc = subprocess.run(
        [NODE, "--check", str(ROOT / "docs" / "javascripts" / "lang-switch.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
