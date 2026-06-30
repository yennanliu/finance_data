# Finance Data Hub — Performance & System Analysis

**Target:** https://yennj12.js.org/finance_data/ (Cloudflare → GitHub Pages, MkDocs Material)
**First analysed:** 2026-06-30 · all numbers are real measurements.
**Status:** Fixes #1–#6 + #2b implemented & verified (see [Changelog](#changelog)).

---

## Executive summary

The site is **functionally healthy but structurally over-weight**. Static delivery is fast
(warm TTFB ~70 ms), but the architecture inlined a ~5,000-page navigation tree into *every*
page and shipped a **195 MB search index**. These don't hurt a single cold page-load much,
but they cripple in-site navigation and search, and make every deploy slow and fragile.
The site scaled ~50× in page count without the build/delivery model scaling with it.

---

## 1. Live measurements (baseline, 2026-06-30)

| Resource | Wire (gzip) | Uncompressed | TTFB (warm) | Total |
|---|---|---|---|---|
| Homepage | 60.7 KB | **1.07 MB** | 0.07 s | 0.12 s |
| Report page (`/reports/sofi/`) | 55 KB | **1.057 MB** | 0.27 s | 0.27 s |
| `reports/` index | 82 KB | — | 0.28 s | 0.28 s |
| **`search/search_index.json`** | **29.7 MB** | **195 MB** | — | **1.06–1.3 s** |

**Delivery headers:** `cache-control: max-age=600` (10 min), `cf-cache-status: DYNAMIC`
→ Cloudflare is **not edge-caching**; every hit reaches the GitHub Pages origin. That is why
cold TTFB (0.31 s) is ~4× the warm one and varies run-to-run.

---

## 2. Bottlenecks, ranked

### 🔴 #1 — 195 MB search index (29.7 MB on the wire)
`search_index.json` is **195 MB uncompressed** / 29.7 MB gzipped. MkDocs Material's client
search downloads **and parses the whole thing** into memory on first search. On mobile/slow
links this is a multi-second freeze and can OOM the tab. Worst issue.
- **Cause:** all ~5,000 pages (full report bodies) are indexed.

### 🔴 #2 — Full nav inlined into every page (~1 MB DOM each)
Every page's HTML carried **5,309 `<a>` links / 5,507 `md-nav__link` nodes** — the entire site
tree. The actual report content is a few KB; **~95% of every page was navigation.** With
`navigation.instant`, each in-site click re-fetches a fresh ~1 MB document.
- **Cause:** `navigation.expand` + `navigation.sections` + `navigation.tabs` force the whole
  tree to render expanded on every page.

### 🟠 #3 — No edge caching (`DYNAMIC`, 10-min TTL)
js.org's Cloudflare returns `cf-cache-status: DYNAMIC`, so static HTML/JSON is fetched from
origin every time. Largely controlled by js.org's CNAME setup; mitigated by shrinking the
payloads above and fingerprinted assets.

### 🟠 #4 — 752 MB deploy payload / 2.3 GB git history → slow, fragile CI
- `docs/` = **752 MB**: 296 MB report markdown, **155 MB PNGs (1,295 files)**, **33 PDFs up to 19 MB**.
- `deploy.yml` used **`fetch-depth: 0`** "for git-revision-date plugin" — but that plugin is
  **not installed**, so it cloned 2.3 GB of binary history for nothing.
- `mkdocs build --strict` + `minify` over ~5,000 × 2 pages is the slow tail.
- **GitHub Pages risk:** trending toward the 1 GB published-site soft limit.

### 🟡 #5 — Unoptimized binary assets
- `docs/pic/demo_1..3.png` were 428–464 KB each (full-res screenshots).
- 33 notebook PDFs (14–19 MB) shipped as-is.

### 🟡 #6 — Deploy storm
`deploy.yml` triggered on push to `ai_gen_report/**`; ~42 analysis jobs/day each pushed,
queuing dozens of full 752 MB deploys daily (`concurrency: cancel-in-progress: false`).

---

## 3. QA / code findings
- ✅ gzip active on HTML & JSON; HTTPS + HTTP/2 via Cloudflare.
- ✅ Markdown content pages themselves are lean (2–10 KB).
- ⚠️ `fetch-depth: 0` was dead weight (no git-date plugin uses it).
- ⚠️ zh is a partial mirror (136 zh md vs 5,028 en) — intended; links to EN pages.
- ⚠️ No page-count / index-size guardrail; both grew unbounded with daily generation.

---

## 4. Recommended fixes (impact × effort)

| # | Action | Impact | Effort | Status |
|---|---|---|---|---|
| 1 | Scope/shrink the search index (exclude report bodies) | 195 MB → <5 MB | Low | ✅ Done |
| 2 | Remove `navigation.expand`; add `navigation.prune` | shallow pages 1 MB → 53 KB | Low | ✅ Done |
| 2b | Drop individual reports from global nav (per-ticker `.pages`) | deep pages 590 → 195 KB; built HTML 3.1 GB → 503 MB | Med | ✅ Done |
| 3 | Remove `fetch-depth: 0` from `deploy.yml` | Faster CI | Trivial | ✅ Done |
| 4 | Retention window: only publish recent reports | Smaller index, build, payload | Med | ✅ Done |
| 5 | Move large PDFs off Pages; WebP the screenshots | −200+ MB deploy | Med | ✅ Done |
| 6 | Debounce deploys to nightly only | Fewer 752 MB deploys | Low | ✅ Done |

---

## 5. Results (after fixes — verified by a full local `mkdocs build`)

| Metric | Before | After | Δ |
|---|---|---|---|
| **`search_index.json`** (uncompressed) | **195 MB** | **0.86 MB** | **−99.6%** |
| `search_index.json` (gzip wire) | 29.7 MB | **0.04 MB** | −99.9% |
| **Homepage HTML** | 1.07 MB (5,309 links) | **53 KB (8 nav links)** | **−95%** |
| **Deep report page** (raw / nav links) | 1.057 MB / 3,605 | **195 KB / 112** *(after #2b)* | **−82%** |
| Deep report page (gzip wire) | 55 KB | **12 KB** *(after #2b)* | −78% |
| **Total built HTML** | ~3.1 GB (avg 590 KB) | **503 MB (avg 94 KB)** *(after #2b)* | **−84%** |
| Built `site/` total | ~3.3 GB | **713 MB** *(after #2b)* | −78% |
| `mkdocs build` (strict) | ~15 min | **~6.5 min** *(after #2b)* | −56% |
| `docs/` deploy payload | 752 MB | **387 MB** | −49% |
| Notebook PDFs in deploy | ~200 MB | **60 KB** (linked from GitHub) | −99.9% |
| Published report md files | 5,028 | **3,486** (120-day window) | −31% |
| Pages excluded from search | 0 | **5,208 / 5,486** | bodies dropped |
| Demo screenshots | 1.33 MB (PNG) | **0.26 MB (WebP)** | −80% |
| `build_docs.py` (clean) | — | **~3 s** | — |

**Headline:** the unusable 195 MB search index is now **0.86 MB** — the single biggest
user-facing win. Search now works on mobile. The homepage dropped from 1.07 MB to 53 KB.

### ✅ Deep pages — resolved by Fix #2b
Initially, `navigation.prune` fixed only the **top of the tree** (homepage: 8 nav links,
53 KB) while a deep report page still rendered ~3,605 nav links / 590 KB, because all ~3,500
dated report pages lived in the global nav. **Fix #2b** (per-ticker `.pages` listing only
`index.md`) removed them from the nav tree — reports stay built and reachable via the
per-ticker index tables. Result: deep page **3,605 → 112 nav links, 590 KB → 195 KB raw
(12 KB gzip)**, total built HTML **3.1 GB → 503 MB**, strict build **15 → 6.5 min**.
Verified with `mkdocs build --strict` (exit 0).

---

## 6. Follow-ups (not yet done)

### Other
- **Report chart PNGs (160 MB, 1,378 files):** convert to WebP + lazy-load. Requires touching
  the analysis chart-generation pipeline and report templates.
- **Edge caching:** raise `cache-control` where possible; depends on js.org Cloudflare config.
- **Retention window tuning:** currently 120 days (`REPORT_RETENTION_DAYS`); revisit as the
  archive grows. Set `REPORT_RETENTION_DAYS=0` to publish everything.
- **Local builds need Python 3.11/3.12.** Python 3.9's stdlib `html.parser` hits an
  `AssertionError: we should not get here!` on some report HTML (a CPython 3.9 bug). CI uses
  3.11, so this is local-only.

---

## 7. Related prior analysis & newly-surfaced gaps

A prior page, [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md), already tracks render-side issues
this network-level pass did not measure — worth folding into the same backlog:
- **MathJax loaded from `unpkg.com` CDN on every page** (200–300 KB, render-blocking; re-runs
  on each SPA navigation).
- **Mermaid rendered client-side** (reports have 14+ blocks each).
- **`clickable-rows.js`** `passive:false` touch handler causing mobile scroll lag.

**New concrete finding (this pass):** `scripts/build_docs.py` has a Mermaid→SVG pre-render
path gated on `mmdc` being installed (`_MMDC = shutil.which("mmdc")`), but
`.github/workflows/deploy.yml` **never installs `@mermaid-js/mermaid-cli` (or Node)** — so in
CI `_MMDC` is `None` and **every Mermaid diagram ships unrendered and is drawn client-side in
production.** Installing mermaid-cli in the deploy workflow would activate the existing
pre-render code and remove that client-side cost for free.

---

## Changelog
- **2026-06-30** — Fix #2b: per-ticker `.pages` (only `index.md`) removes ~3,500 dated report
  pages from the global nav; added `validation.nav.omitted_files: info` so `--strict` tolerates
  the orphaned-from-nav (still-built) pages. Deep page 590 KB → 195 KB, built HTML 3.1 GB →
  503 MB. Verified with `mkdocs build --strict`.
- **2026-06-30** — Implemented fixes #1–#6.
  - `scripts/build_docs.py`: retention window (`REPORT_RETENTION_DAYS`, default 120d),
    `search.exclude` front-matter on report/news/notebook bodies, notebook PDFs linked from
    GitHub raw instead of copied into the deploy.
  - `mkdocs.yml`: `navigation.expand` → `navigation.prune`.
  - `.github/workflows/deploy.yml`: dropped `fetch-depth: 0`; narrowed push trigger to
    config/site-asset paths (content now published by the nightly cron).
  - `README.md` + `docs/pic/`: demo screenshots converted PNG → WebP.
