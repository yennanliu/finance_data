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

    # 1b. Price Data section ────────────────────────────────────────────────
    # The charts and the download links are useless if MkDocs didn't carry the
    # derived payloads and the raw CSV through to site/ — and a missing static
    # file is exactly the kind of failure --strict does not catch.
    prices_dir = SITE / "prices"
    if not (prices_dir / "index.html").exists():
        fail("site/prices/index.html missing — the Price Data section did not build")
    ticker_dirs = [d for d in prices_dir.iterdir() if d.is_dir()]
    if not ticker_dirs:
        fail("no per-ticker pages under site/prices/")
    for d in ticker_dirs:
        for artefact in ("index.html", "prices.json", "analytics.json", f"{d.name}.csv"):
            if not (d / artefact).exists():
                fail(f"site/prices/{d.name}/{artefact} missing")
    if not (prices_dir / "all_prices.zip").exists():
        fail("site/prices/all_prices.zip missing — bulk download would 404")
    print(f"✅ price data: {len(ticker_dirs)} tickers with charts, payloads and CSV")

    # 2. Mermaid zero-regression gate ───────────────────────────────────────
    mmdc = shutil.which("mmdc")
    if not mmdc:
        fail("mmdc not on PATH — install @mermaid-js/mermaid-cli to validate diagrams")
    bd = _load_build_docs()

    doc_mds = [p for p in (DOCS / "reports").rglob("*.md") if p.name != "index.md"]
    total = fixed = still_broken = ok = 0
    regressions: list[tuple[Path, str, str]] = []

    # Reports live across three roots (fundamental/technical/stock); any of them
    # may be absent. Search all existing roots for each sampled page's raw
    # source rather than assuming a single dir exists.
    roots = [r for r in bd.report_roots() if r.exists()]

    def find_source(ticker: str, name: str) -> "Path | None":
        for root in roots:
            cand = root / ticker / name          # dirs are lowercased by build_docs
            if cand.exists():
                return cand
        for root in roots:                        # case-insensitive fallback
            for d in root.iterdir():
                if d.is_dir() and d.name.lower() == ticker and (d / name).exists():
                    return d / name
        return None

    for doc in doc_mds:
        ticker = doc.parent.name
        src = find_source(ticker, doc.name)
        if src is None:
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
