# Repository Size — Audit & Reduction Options

> 中文版:`REPO_SIZE_EVAL_ZH.md`

**Measured:** 2026-10-17, on `main` right after the 3-month prune
(`1af337af5`, which removed 1,604 reports dated before 2026-07-17).

**Question:** the repo is ~1 GB on GitHub and ~1 GB in every clone. Where does
that come from, and what can we do about it?

**Answer:** 85% of the history is two things: **PDFs (662 MB)** and **files
that are no longer in `HEAD` but stay in history (242 MB)**. Pruning old reports
shrinks the checkout but not `.git`, so on its own it can never bring the clone
size down. Getting `.git` small means rewriting history once, and keeping it
small means getting PDFs out of git and putting a cap on report growth.

---

## 1. Where the bytes are

| Metric | Value |
|---|---|
| GitHub-reported size (`gh api repos/... .size`) | 1.06 GB |
| Local `.git` (packed) | 1.02 GiB, 22 packs |
| Commits | ~17,400 (since 2025-11-16) |
| Tracked files in `HEAD` | 10,137 |
| Remote branches | 64 |

### By file type (compressed size in packs, whole history)

| Type | Size | Files | Note |
|---|---:|---:|---|
| `.pdf` | **662 MB** | 340 | Nearly all still in `HEAD`, and they never change |
| `.md` | 214 MB | 19,310 | Generated reports; zlib/deltas compress them well |
| `.png` | 178 MB | 1,750 | Technical charts. Generation **stopped after 2026-08-04** |
| `.csv` | 7 MB | 2,159 | `data/`: 186 MB raw, deltas take it to 7 MB, so it's fine |
| everything else | < 5 MB | | Code, tests, workflows |

### By directory (whole history)

| Path | In history | Of which no longer in `HEAD` |
|---|---:|---:|
| `notebook_llm/` (23 PDFs, 12–20 MB each) | 430 MB | 0 |
| `ai_gen_report/technical/` | 144 MB | 83 MB |
| `10-k/` (113 PDFs) | 140 MB | 0 |
| `ai_gen_report/stock/` (old pre-`reorg` layout) | 123 MB | **123 MB** |
| `ai_gen_report/fundamental/` | 88 MB | 14 MB |
| `10-q/` (103 PDFs) | 70 MB | 0 |
| `ai_gen_report/market_news/` | 32 MB | 13 MB |
| `investor_day/`, `6-k/` | 22 MB | 0 |
| `data/` | 6 MB | 6 MB |

### Bottom line

| Bucket | Size |
|---|---:|
| PDFs | 662 MB |
| Non-PDF blobs no longer in `HEAD` | 242 MB |
| Non-PDF blobs in `HEAD` | 161 MB |
| Trees + commits | ~30 MB |

### Growth rate

Measured as the new blobs in the last 30 days (`git rev-list --objects HEAD ^<commit from 30 days ago>`):
**~61 MB/month**, made up of 46 MB of Markdown reports, 7.5 MB of PDFs and 7.7 MB
of other files. That is roughly **+0.7 GB/year** of history even with the prune in
place, because a prune only deletes files from `HEAD`.

### Local disk (not part of the repo, but it adds up)

`.claude/worktrees/` holds 5 worktrees, each a full checkout of 1.0–1.3 GB,
**5.7 GB in total**. Most of each one is the same 430 MB of `notebook_llm/` and
230 MB of SEC PDFs.

---

## 2. Options

### A. No history rewrite (safe, can do now)

| # | Action | Effect | Cost / risk |
|---|---|---|---|
| A1 | **Done:** `maintain_ai_gen_report.py prune --before 2026-07-17` | Checkout −1,604 files (~690 k lines). `.git` unchanged | None |
| A2 | **Automate retention:** a monthly workflow that runs `prune --before <today − 90d>` | Keeps the checkout bounded at ~3 months of reports | Old reports disappear from the site (keep them in git history or an archive) |
| A3 | **Stop committing new PDFs.** Publish `notebook_llm/` and SEC PDFs as **GitHub Release assets** (no bandwidth quota, ≤ 2 GB per file) and point `NOTEBOOK_RAW_BASE` / `GITHUB_RAW_BASE` in `build_docs.py` at the release download URLs | Stops the ~7.5 MB/month of PDF growth | Changes to `download_10k.yml` / `download_10q.yml` plus a link migration. 10-K/10-Q/6-K are also re-downloadable from EDGAR |
| A4 | **Charts:** none are generated any more, and the 420 left in `HEAD` (48 MB) age out under A2 by 2026-11-04. If charts come back, save them as a 256-colour palette PNG (`quantize(256)`) | Measured **101 KB → 39 KB (−61%)** per chart | Slight colour banding on gradients |
| A5 | **Cheaper clones for people:** `git clone --filter=blob:none` (partial clone), plus `git sparse-checkout set --no-cone '/*' '!notebook_llm/' '!10-k/' '!10-q/'` | Clone downloads only the blobs it checks out, from ~1 GB down to a fraction of that | Fetches blobs lazily, which needs network for `git log -p` on old files |
| A6 | **CI is already shallow** (`fetch-depth` defaults to 1). The one exception is `daily_progress.yml` (`fetch-depth: 500`), which is fine because it reads history | Nothing to do | — |
| A7 | **Local cleanup:** `git worktree remove` on merged worktrees, or use sparse checkout in them. `git gc` consolidates the 22 packs | Frees up to 5.7 GB locally | Local only |
| A8 | Delete merged remote branches (64 remote, 15 local already merged into `main`) | Small on its own, but **a precondition for B** (an un-rewritten branch keeps the old blobs alive) | Close or merge the open PRs first |

**Status (2026-10-17), everything in A except A3:**

- A1 ✅ done (`1af337af5`).
- A2 ✅ `.github/workflows/prune_old_reports.yml`: runs on the 1st of each month at 04:30 UTC with a 90-day cutoff. It can also be dispatched with `keep_days` / `dry_run`, and won't go below 30 days.
- A4 ✅ nothing to change: charts are no longer generated, and A2 removes the remaining ones.
- A5 ✅ README "Clone (lightweight)" section.
- A6 ✅ already done, no change.
- A7 ✅ removed 4 worktrees (clean, and either pushed or merged), deleted 14 merged local branches, and ran `git gc` (22 packs → 1). The `option3-collector` worktree was kept because it has unpushed commits. `.git` is still 1.0 GB, as expected.
- A8 ✅ deleted 18 remote branches that were fully merged into `main` and had no open PR (64 → 46). The 46 remaining branches are not ancestors of `main` and were kept.
- A3 ⏸ deferred.

A1–A8 bound the **checkout** and slow **growth**. None of them makes the
existing `.git` smaller.

### B. One-time history rewrite (`git filter-repo`)

| # | Action | Expected `.git` after |
|---|---|---:|
| B1 | Strip blobs no longer in `HEAD` (old `stock/` layout, pruned reports, old charts) | ~820 MB (−242 MB) |
| B2 | B1 + remove PDF directories from history (after A3 has moved them out) | **~190 MB (−82%)** |

Sketch:

```bash
# fresh mirror clone, never the working repo
git clone --mirror git@github.com:yennanliu/finance_data.git fd.git && cd fd.git
git filter-repo --analyze                     # review .git/filter-repo/analysis/
# B2: drop PDF dirs (once they live in Releases)
git filter-repo --invert-paths \
  --path notebook_llm/ --path 10-k/ --path 10-q/ --path 6-k/ --path investor_day/
# B1: drop every blob that HEAD no longer references
git ls-tree -r HEAD | awk '{print $3}' | sort -u > keep.txt
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname)' \
  | awk '$1=="blob"{print $2}' | sort -u | comm -23 - keep.txt > strip.txt
git filter-repo --strip-blobs-with-ids strip.txt
git push --force --mirror
```

**What it costs:**

- **Pause every cron first.** CI commits to `main` about every 20 minutes, and a
  run that pushes after the rewrite either fails or re-introduces old SHAs.
  Disable the workflows, rewrite, force-push, then re-enable them.
- Every clone and worktree has to **re-clone**. Old SHAs, commit links in issues
  and PRs, and open PR branches all break. Merge or close open PRs first (A8).
- GitHub keeps unreachable objects until its own GC runs. The reported size can
  stay at 1 GB until GitHub Support runs a GC on the repo
  ([docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)).
- B1 removes the git history of deleted reports. If they matter, export them to an
  archive (a release tarball) first.

**Why not Git LFS?** The free tier is 1 GB storage and 1 GB/month of bandwidth.
The public site links straight to the PDFs, so site traffic would use up the
quota, and `raw.githubusercontent.com` serves LFS *pointer* files, so the
current links would break. Release assets have neither problem.

### C. Structural: move generated output out of `main`

Even after B, reports add ~46 MB/month to history. The only durable fix is to
**stop storing generated reports in the code branch's history**:

- **C1 Separate repo** (`finance_data-reports`): CI writes reports there, and
  `deploy.yml` checks out both repos before `build_docs.py`. Code history stays
  small forever. Report history can be rewritten or squashed on its own schedule
  without touching code PRs.
- **C2 Orphan `reports` branch, squashed periodically:** the same idea in one repo.
  Cheaper to set up but awkward (`git worktree`/`checkout` in every workflow).

Cost: `commit-and-push` composite action, `deploy.yml` and the `ai_gen_report/`
paths in `build_docs.py` / `maintain_ai_gen_report.py` / QA scripts.

---

## 3. Recommendation

1. **Now (no rewrite):** A2 (automated 90-day prune), A7 (local worktrees), A5
   (document partial clone in the README).
2. **Next:** A3 (PDFs to Release assets plus the link change in `build_docs.py`).
   This is the single biggest lever: 62% of history.
3. **Then, once, in a planned window:** A8 → B2 with crons paused. Expected
   result is **1.06 GB → ~190 MB**.
4. **If growth still matters after that:** C1. Otherwise accept ~0.55 GB/year of
   report history and repeat B1 yearly.

## 4. How these numbers were measured

```bash
git count-objects -vH
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(objectsize:disk) %(rest)'
# grouped by top-level dir / extension, compared against `git ls-files -s` of HEAD
```

`objectsize:disk` is the compressed and delta-encoded size inside the pack, so
the columns add up to the pack size. Path attribution comes from the first path
`rev-list` reports for each blob.
