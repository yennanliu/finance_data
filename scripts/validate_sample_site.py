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
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = ROOT / "site"
SRC_STOCK = ROOT / "ai_gen_report" / "stock"
# On CI runners headless chromium must launch with --no-sandbox; the workflow
# writes a puppeteer config and points PUPPETEER_CONFIG at it.
_PUPPETEER = os.environ.get("PUPPETEER_CONFIG", "")
# Each mmdc call boots its own headless Chromium, so the gate was ~70s of
# serial browser startups. One render per core runs them concurrently without
# oversubscribing: a starved render that hits its 60s timeout reads as a
# failure, and a spurious failure on the sanitized side would be reported as
# a regression.
_RENDER_WORKERS = os.cpu_count() or 2


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

    # 1b. Market Data section ───────────────────────────────────────────────
    # The charts and the download links are useless if MkDocs didn't carry the
    # derived payloads and the raw CSVs through to site/ — and a missing static
    # file is exactly the kind of failure --strict does not catch.
    data_dir = SITE / "data"
    if not (data_dir / "index.html").exists():
        fail("site/data/index.html missing — the Market Data section did not build")
    ticker_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    if not ticker_dirs:
        fail("no per-ticker pages under site/data/")
    # A ticker may carry only one of the two stores (an ETF has prices and no
    # SEC filings), so each half is checked only where its page half exists.
    for d in ticker_dirs:
        if not (d / "index.html").exists():
            fail(f"site/data/{d.name}/index.html missing")
        if (d / "prices.json").exists():
            for artefact in ("analytics.json", f"{d.name}.csv"):
                if not (d / artefact).exists():
                    fail(f"site/data/{d.name}/{artefact} missing")
        if (d / "fundamentals.json").exists():
            if not (d / f"{d.name}_financials.csv").exists():
                fail(f"site/data/{d.name}/{d.name}_financials.csv missing")
        if not ((d / "prices.json").exists() or (d / "fundamentals.json").exists()):
            fail(f"site/data/{d.name}/ has neither payload — the page has no charts")
    if not (data_dir / "market_data.zip").exists():
        fail("site/data/market_data.zip missing — bulk download would 404")
    if not (data_dir / "index.json").exists():
        fail("site/data/index.json missing — the manifest would 404")
    # The pre-merge URLs were linked from outside the site, so the stubs that
    # keep them resolving are part of the contract, not a nicety.
    for legacy in ("prices", "fundamentals"):
        if not (SITE / legacy / "index.html").exists():
            fail(f"site/{legacy}/index.html missing — the pre-merge URL would 404")
    print(f"✅ market data: {len(ticker_dirs)} tickers with charts, payloads and CSVs")

    # 2. Mermaid zero-regression gate ───────────────────────────────────────
    mmdc = shutil.which("mmdc")
    if not mmdc:
        fail("mmdc not on PATH — install @mermaid-js/mermaid-cli to validate diagrams")
    # Canary. If mmdc cannot launch a browser at all, every diagram "fails"
    # raw AND sanitized, which this gate counts as LLM garbage rather than a
    # regression — so a broken renderer would pass silently.
    if not renders(mmdc, "graph TD\n  A --> B\n"):
        fail("mmdc could not render a trivial diagram — the renderer is broken, "
             "so the Mermaid gate would prove nothing")
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

    # Collect every (raw, sanitized) pair first, then render them all in one
    # concurrent pass. A diagram the sanitizer left untouched is rendered once.
    blocks: list[tuple[Path, str, str]] = []
    for doc in doc_mds:
        ticker = doc.parent.name
        src = find_source(ticker, doc.name)
        if src is None:
            continue
        # Same fence matcher the sanitizer and the docs builder use, so this
        # gate can never scan for a diagram shape they no longer recognise.
        for raw in bd._MERMAID_FENCE_RE.findall(
                src.read_text(encoding="utf-8", errors="ignore")):
            blocks.append((src, raw, bd.sanitize_mermaid(raw)))

    unique = sorted({d for _, raw, san in blocks for d in (raw, san)})
    with ThreadPoolExecutor(max_workers=_RENDER_WORKERS) as pool:
        rendered = dict(zip(unique, pool.map(lambda d: renders(mmdc, d), unique)))

    for src, raw, san in blocks:
        total += 1
        raw_ok = rendered[raw]
        san_ok = rendered[san]
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
