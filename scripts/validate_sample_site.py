#!/usr/bin/env python3
"""Validate a SAMPLE_BUILD site (see .github/workflows/sample_build.yml).

Run after `python scripts/build_docs.py` (SAMPLE_BUILD=1) + `mkdocs build`.
It proves the build code still produces a coherent site and that the Mermaid
syntax repair in build_docs.sanitize_mermaid is SAFE on real sampled content.

Checks (exit non-zero on failure):
  1. site/ exists with an index and at least one sampled report page.
  2. Mermaid zero-regression gate: for every diagram on the sampled report
     pages, render the RAW LLM source and the SANITIZED output with mmdc. The
     sanitizer must never turn a diagram that rendered into one that fails.
     (Diagrams that are hallucinated garbage fail both ways — that is content,
     not a code regression, so it does not fail the build; the counts are
     reported for visibility.)
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = ROOT / "site"
SRC_STOCK = ROOT / "ai_gen_report" / "stock"
FENCE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
# On CI runners headless chromium must launch with --no-sandbox; the workflow
# writes a puppeteer config and points PUPPETEER_CONFIG at it.
_PUPPETEER = os.environ.get("PUPPETEER_CONFIG", "")


def _load_build_docs():
    spec = importlib.util.spec_from_file_location("build_docs", ROOT / "scripts" / "build_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def renders(mmdc: str, diagram: str) -> bool:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "x.mmd"
        dst = Path(d) / "x.svg"
        src.write_text(diagram, encoding="utf-8")
        cmd = [mmdc, "-i", str(src), "-o", str(dst)]
        if _PUPPETEER:
            cmd += ["-p", _PUPPETEER]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
        return r.returncode == 0 and dst.exists()


def main() -> None:
    # 1. Site structure ────────────────────────────────────────────────────
    if not (SITE / "index.html").exists():
        fail("site/index.html missing — mkdocs did not produce a site")
    html_pages = list(SITE.rglob("*.html"))
    report_pages = list((SITE / "reports").rglob("index.html")) if (SITE / "reports").exists() else []
    if not report_pages:
        fail("no report pages in site/reports/ — sample build produced nothing")
    print(f"✅ site built: {len(html_pages)} HTML pages, {len(report_pages)} report indexes")

    # 2. Mermaid zero-regression gate ───────────────────────────────────────
    mmdc = shutil.which("mmdc")
    if not mmdc:
        fail("mmdc not on PATH — install @mermaid-js/mermaid-cli to validate diagrams")
    bd = _load_build_docs()

    doc_mds = [p for p in (DOCS / "reports").rglob("*.md") if p.name != "index.md"]
    total = fixed = still_broken = ok = 0
    regressions: list[tuple[Path, str, str]] = []

    for doc in doc_mds:
        ticker = doc.parent.name
        src_dir = next((d for d in SRC_STOCK.iterdir()
                        if d.is_dir() and d.name.lower() == ticker), None)
        src = src_dir / doc.name if src_dir else None
        if not src or not src.exists():
            continue
        for raw in FENCE.findall(src.read_text(encoding="utf-8", errors="ignore")):
            total += 1
            san = bd.sanitize_mermaid(raw)
            raw_ok = renders(mmdc, raw)
            san_ok = renders(mmdc, san) if san != raw else raw_ok
            if raw_ok and not san_ok:
                regressions.append((src, raw, san))
            elif not raw_ok and san_ok:
                fixed += 1
            elif not raw_ok and not san_ok:
                still_broken += 1
            else:
                ok += 1

    print(f"\nMermaid on sampled pages: {total} blocks | "
          f"already-ok {ok} | fixed {fixed} | still-broken (LLM garbage) {still_broken} | "
          f"regressions {len(regressions)}")

    if regressions:
        print(f"\n❌ sanitizer REGRESSED {len(regressions)} diagram(s) "
              f"(rendered raw, broke after sanitize):")
        for src, raw, san in regressions[:5]:
            print(f"\n--- {src.relative_to(ROOT)} ---\nRAW:\n{raw[:300]}\nSANITIZED:\n{san[:300]}")
        sys.exit(1)

    if total == 0:
        print("⚠️  no Mermaid diagrams on sampled pages — consider SAMPLE_TICKERS "
              "with mermaid-heavy tickers (e.g. aapl,msft,nvda)")
    print("\n✅ sample site validation passed (no Mermaid regressions)")


if __name__ == "__main__":
    main()
