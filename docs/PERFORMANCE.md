# Website Performance Analysis

## Root Causes of Slow Loading

### Critical
| # | Issue | Detail |
|---|-------|--------|
| 1 | **MathJax CDN (200–300 KB)** | Loaded from `unpkg.com` on every page, blocks render. Re-renders all equations on every SPA navigation via `document$.subscribe()` in `docs/javascripts/mathjax.js` |
| 2 | **Mermaid diagrams rendered client-side** | Reports have 14+ Mermaid blocks each, all rendered in-browser — no pre-rendering at build time |
| 3 | **Large report files (50–60 KB each)** | 900–1,400 lines per report with heavy tables, ASCII art, inline styles |

### High Priority
| # | Issue | Detail |
|---|-------|--------|
| 4 | **13 Material theme features enabled** | `navigation.instant`, `navigation.instant.progress`, `navigation.tracking`, etc. — each adds JS event listeners and overhead |
| 5 | **HTML reports have 1,000+ lines of inline CSS** | No extraction or minification; Chart.js (40 KB) also loaded per-report |
| 6 | **CJK font loading** | Noto Sans TC (full character set) loaded globally, likely blocking render |
| 7 | **Bilingual duplication doubles build size** | `docs/` + `docs/zh/` = 752 MB total; same PDFs and reports copied twice |

### Medium Priority
| # | Issue | Detail |
|---|-------|--------|
| 8 | **Bilingual search indexes 1,600+ docs** | No index size cap configured |
| 9 | **`clickable-rows.js` uses `querySelectorAll` on full DOM** | Runs on every page load instead of event delegation |
| 10 | **No image compression** | Technical chart PNGs unoptimized |

---

## Fix List (Prioritized)

### Quick wins (< 1 hr each)
- [ ] Replace MathJax with **KaTeX** — 80 KB vs 300 KB, same output, no CDN block
- [ ] Disable unused Material features: `navigation.instant.progress`, `navigation.tracking`, `content.tooltips`
- [ ] Subset or swap **Noto Sans TC** to system CJK font stack to eliminate font blocking

### Medium effort (2–4 hrs each)
- [x] **Pre-render Mermaid to SVG** during `build_docs.py` — implemented in `build_docs.py`; activate by installing `npm install -g @mermaid-js/mermaid-cli` (renders + caches to `.mermaid_cache.json`)
- [ ] **Extract inline CSS** from HTML reports into a shared stylesheet; minify during generation (low priority — only 8 legacy HTML files)
- [x] Refactor `mathjax.js` — N/A: MathJax fully removed (zero math usage confirmed)
- [x] Switch `clickable-rows.js` to **event delegation** — done: one listener on `document`, walks up to `<tr>`

### Architectural (4–8 hrs each)
- [ ] **Single-source bilingual** — one `docs/` dir with language routing instead of duplicating all content into `docs/zh/`
- [ ] **Incremental builds** in `build_docs.py` — skip unchanged files (currently rebuilds everything)
- [ ] **Lazy-load Chart.js** in HTML reports — defer until chart container is in viewport

---

## Key Files Referenced

| File | Role |
|------|------|
| `mkdocs.yml` | Theme features, plugins, extra JS/CSS config |
| `docs/javascripts/mathjax.js` | MathJax re-render hook — primary JS bottleneck |
| `docs/javascripts/clickable-rows.js` | Row click handler — minor inefficiency |
| `docs/stylesheets/extra.css` | 811-line custom CSS with animations |
| `docs/overrides/home.html` | Heavy inline CSS/animations on landing page |
| `scripts/build_docs.py` | Generates all docs; duplicates content for bilingual |
| `scripts/analysis/utils/llm.py` | Report generation — controls report structure/size |

---

## Size Reference

| Component | Size | Notes |
|-----------|------|-------|
| MathJax CDN | 200–300 KB | External, render-blocking |
| Chart.js | 40 KB | Loaded per HTML report |
| Custom CSS (`extra.css`) | 27 KB | GPU-accelerated animations |
| Markdown reports (avg) | 50–60 KB | 900–1,400 lines each |
| HTML reports (avg) | 50–60 KB | Includes 1,000+ lines inline CSS |
| `docs/` total | 752 MB | Includes bilingual duplication |
| `10-k/` PDFs | 1.3 GB | 381 files, not served via Pages |
