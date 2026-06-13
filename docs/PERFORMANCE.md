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

### Mobile-specific (slow scroll + "keeps refreshing")
| # | Issue | Detail |
|---|-------|--------|
| 11 | **`passive:false` touchmove listener on `document`** | A scroll-blocking touch handler in `clickable-rows.js` (added to stop pull-to-refresh) ran JS synchronously on every scroll frame → severe scroll lag on phones. Root cause of "page loads very slow" on mobile. |
| 12 | **Pull-to-refresh reloads the page** | iOS/Android pull-down-at-top gesture reloaded the page ("keeps refreshing"). `overscroll-behavior-y: none` was only set on `html`, missing Material's actual scroll container. |

---

## Fix List (Prioritized)

### Quick wins (< 1 hr each)
- [ ] Replace MathJax with **KaTeX** — 80 KB vs 300 KB, same output, no CDN block
- [ ] Disable unused Material features: `navigation.instant.progress`, `navigation.tracking`, `content.tooltips`
- [ ] Subset or swap **Noto Sans TC** to system CJK font stack to eliminate font blocking

### Medium effort (2–4 hrs each)
- [x] **Pre-render Mermaid to SVG** during `build_docs.py` — implemented in `build_docs.py`; activate by installing `npm install -g @mermaid-js/mermaid-cli` (renders + caches to `.mermaid_cache.json`)
- [ ] **Extract inline CSS** from HTML reports into a shared stylesheet; minify during generation (low priority — only 8 legacy HTML files)
- [x] Refactor `mathjax.js` — N/A: MathJax fully removed (zero math usage confirmed); orphan `docs/javascripts/mathjax.js` file now deleted
- [x] Switch `clickable-rows.js` to **event delegation** — done: one listener on `document`, walks up to `<tr>`

### Mobile fixes (done)
- [x] **Remove `passive:false` touchmove handler** from `clickable-rows.js` — eliminated scroll-thread blocking; mobile scrolling is smooth again (issue #11)
- [x] **Robust pull-to-refresh prevention** — `overscroll-behavior-y: none` now applied to `html, body, .md-main, .md-content, [data-md-component=container]` so it catches whichever element scrolls (issue #12)
- [x] **Disable infinite hero animations on mobile** + honor `prefers-reduced-motion` — stops continuous repaints from `fp-dot`/`fp-shimmer` on phones

### Architectural (4–8 hrs each)
- [x] **Single-source bilingual** — ZH tree now generates index-only pages; report/news/notebook files link to EN pages via absolute `SITE_BASE` paths instead of being copied (saves ~50% of `docs/` size)
- [x] **Incremental builds** in `build_docs.py` — default mode now skips unchanged files; `copy_file()` checks mtime, `write()` checks content equality; pass `--clean` to force full rebuild
- [x] **Lazy-load Chart.js** — N/A: HTML report files are wrapped in ` ```html ``` ` code fences, not actual rendered pages; Chart.js is not loaded at runtime

---

## Key Files Referenced

| File | Role |
|------|------|
| `mkdocs.yml` | Theme features, plugins, extra JS/CSS config |
| `docs/javascripts/clickable-rows.js` | Row click handler (event delegation, passive-safe) |
| `docs/stylesheets/extra.css` | Custom CSS, animations, mobile/overscroll rules |
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
