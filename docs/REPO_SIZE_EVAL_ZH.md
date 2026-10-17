# 儲存庫大小 — 盤點與瘦身方案

> English version: `REPO_SIZE_EVAL.md`

**量測時間:** 2026-10-17,於 `main` 剛完成三個月清理之後
(`1af337af5`,刪除 2026-07-17 以前的 1,604 份報告)。

**問題:** 這個 repo 在 GitHub 上約 1 GB,每次 clone 也約 1 GB。這些空間從哪來?能怎麼減?

**結論:** 歷史中 85% 來自兩類:**PDF(662 MB)**,以及**已不在 `HEAD`、但仍留在歷史裡的檔案(242 MB)**。
清理舊報告只會縮小工作目錄,不會縮小 `.git`,所以單靠它永遠降不了 clone 大小。
要讓 `.git` 變小,必須改寫一次歷史;要讓它維持小,必須把 PDF 移出 git,並限制報告的成長。

---

## 1. 空間分布

| 指標 | 數值 |
|---|---|
| GitHub 回報大小(`gh api repos/... .size`) | 1.06 GB |
| 本機 `.git`(已打包) | 1.02 GiB,22 個 pack |
| Commit 數 | 約 17,400(自 2025-11-16) |
| `HEAD` 追蹤檔案數 | 10,137 |
| 遠端分支 | 64 |

### 依檔案類型(整段歷史,pack 內壓縮後大小)

| 類型 | 大小 | 檔案數 | 說明 |
|---|---:|---:|---|
| `.pdf` | **662 MB** | 340 | 幾乎全部仍在 `HEAD`,且從不變動 |
| `.md` | 214 MB | 19,310 | 生成的報告;zlib/delta 壓縮效果好 |
| `.png` | 178 MB | 1,750 | 技術分析圖。**2026-08-04 後已停止產生** |
| `.csv` | 7 MB | 2,159 | `data/`:原始 186 MB,delta 後僅 7 MB,沒問題 |
| 其他 | < 5 MB | | 程式碼、測試、workflow |

### 依目錄(整段歷史)

| 路徑 | 歷史中大小 | 其中已不在 `HEAD` |
|---|---:|---:|
| `notebook_llm/`(23 個 PDF,每個 12–20 MB) | 430 MB | 0 |
| `ai_gen_report/technical/` | 144 MB | 83 MB |
| `10-k/`(113 個 PDF) | 140 MB | 0 |
| `ai_gen_report/stock/`(`reorg` 前的舊目錄結構) | 123 MB | **123 MB** |
| `ai_gen_report/fundamental/` | 88 MB | 14 MB |
| `10-q/`(103 個 PDF) | 70 MB | 0 |
| `ai_gen_report/market_news/` | 32 MB | 13 MB |
| `investor_day/`、`6-k/` | 22 MB | 0 |
| `data/` | 6 MB | 6 MB |

### 總結

| 類別 | 大小 |
|---|---:|
| PDF | 662 MB |
| 已不在 `HEAD` 的非 PDF blob | 242 MB |
| 仍在 `HEAD` 的非 PDF blob | 161 MB |
| Tree + commit | 約 30 MB |

### 成長速度

以近 30 天新增的 blob 計算(`git rev-list --objects HEAD ^<30 天前的 commit>`):
**約 61 MB/月**,其中 Markdown 報告 46 MB、PDF 7.5 MB、其他 7.7 MB。
也就是說,即使持續清理,歷史仍會**每年增加約 0.7 GB**,因為清理只會從 `HEAD` 刪檔。

### 本機磁碟(不屬於 repo,但累積可觀)

`.claude/worktrees/` 有 5 個 worktree,每個都是 1.0–1.3 GB 的完整 checkout,
**合計 5.7 GB**。每個 worktree 的大部分空間都是同一份 430 MB 的 `notebook_llm/` 和 230 MB 的 SEC PDF。

---

## 2. 可行方案

### A. 不改寫歷史(安全,可立即執行)

| # | 動作 | 效果 | 成本/風險 |
|---|---|---|---|
| A1 | **已完成:** `maintain_ai_gen_report.py prune --before 2026-07-17` | 工作目錄減少 1,604 個檔案(約 69 萬行)。`.git` 不變 | 無 |
| A2 | **自動化保留政策:** 每月一次的 workflow 執行 `prune --before <今天 − 90 天>` | 工作目錄維持在約三個月份量的報告 | 舊報告會從網站消失(仍保留在 git 歷史或封存檔) |
| A3 | **停止提交新的 PDF。** 把 `notebook_llm/` 與 SEC PDF 改放 **GitHub Release 附件**(無流量配額,單檔 ≤ 2 GB),並把 `build_docs.py` 的 `NOTEBOOK_RAW_BASE` / `GITHUB_RAW_BASE` 改指向 release 下載網址 | 止住每月約 7.5 MB 的 PDF 成長 | 需修改 `download_10k.yml` / `download_10q.yml` 並遷移連結。10-K/10-Q/6-K 也可隨時從 EDGAR 重新下載 |
| A4 | **圖表:** 目前已不再產生,`HEAD` 剩下的 420 張(48 MB)在 A2 下會於 2026-11-04 前自然清除。若日後恢復產圖,改存 256 色調色盤 PNG(`quantize(256)`) | 實測每張 **101 KB → 39 KB(−61%)** | 漸層處有輕微色階 |
| A5 | **讓開發者的 clone 更省:** `git clone --filter=blob:none`(partial clone),再加上 `git sparse-checkout set --no-cone '/*' '!notebook_llm/' '!10-k/' '!10-q/'` | Clone 只下載實際 checkout 的 blob,從約 1 GB 降到其中一小部分 | Blob 按需下載,對舊檔案執行 `git log -p` 時需要網路 |
| A6 | **CI 已經是淺層 clone**(`fetch-depth` 預設為 1)。唯一例外是 `daily_progress.yml`(`fetch-depth: 500`),它需要讀歷史,沒問題 | 不需處理 | — |
| A7 | **本機清理:** 對已合併的 worktree 執行 `git worktree remove`,或在 worktree 內使用 sparse checkout。`git gc` 合併 22 個 pack | 本機最多可釋放 5.7 GB | 只影響本機 |
| A8 | 刪除已合併的遠端分支(遠端 64 個,本機 15 個已合併進 `main`) | 單獨效果小,但**是 B 的前置條件**(未改寫的分支會讓舊 blob 繼續存在) | 先關閉或合併進行中的 PR |

A1–A8 能限制**工作目錄**大小並減緩**成長**,但都無法讓現有的 `.git` 變小。

### B. 一次性改寫歷史(`git filter-repo`)

| # | 動作 | 預估改寫後 `.git` |
|---|---|---:|
| B1 | 移除已不在 `HEAD` 的 blob(舊 `stock/` 結構、已清理的報告、舊圖表) | 約 820 MB(−242 MB) |
| B2 | B1 + 從歷史中移除 PDF 目錄(需先完成 A3 把 PDF 移走) | **約 190 MB(−82%)** |

步驟草稿:

```bash
# 使用全新的 mirror clone,絕不在工作中的 repo 上操作
git clone --mirror git@github.com:yennanliu/finance_data.git fd.git && cd fd.git
git filter-repo --analyze                     # 檢視 .git/filter-repo/analysis/
# B2:移除 PDF 目錄(PDF 已改放 Release 之後)
git filter-repo --invert-paths \
  --path notebook_llm/ --path 10-k/ --path 10-q/ --path 6-k/ --path investor_day/
# B1:移除 HEAD 已不再引用的所有 blob
git ls-tree -r HEAD | awk '{print $3}' | sort -u > keep.txt
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname)' \
  | awk '$1=="blob"{print $2}' | sort -u | comm -23 - keep.txt > strip.txt
git filter-repo --strip-blobs-with-ids strip.txt
git push --force --mirror
```

**代價:**

- **必須先暫停所有排程。** CI 大約每 20 分鐘就 commit 一次到 `main`,改寫後才推送的 run
  會失敗,或把舊 SHA 帶回來。先停用 workflow,改寫、force-push,再重新啟用。
- 所有 clone 與 worktree 都必須**重新 clone**。舊 SHA、issue/PR 中的 commit 連結、
  進行中的 PR 分支都會失效。請先合併或關閉進行中的 PR(A8)。
- GitHub 會保留不可達的物件,直到它自己的 GC 執行。顯示的大小可能維持在 1 GB,
  直到 GitHub Support 對 repo 執行 GC
  ([文件](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository))。
- B1 會刪除已刪報告的 git 歷史。若這些報告仍有價值,請先匯出封存(例如 release 壓縮檔)。

**為何不用 Git LFS?** 免費額度是 1 GB 儲存空間和每月 1 GB 流量。
公開網站直接連結 PDF,網站流量會用光配額;而且 `raw.githubusercontent.com` 回傳的是
LFS *指標檔*,現有連結會失效。Release 附件沒有這兩個問題。

### C. 架構調整:把生成內容移出 `main`

即使完成 B,報告仍會讓歷史每月增加約 46 MB。唯一長久的解法是
**不把生成的報告存進程式碼分支的歷史**:

- **C1 獨立 repo**(`finance_data-reports`):CI 把報告寫到那裡,
  `deploy.yml` 在執行 `build_docs.py` 前同時 checkout 兩個 repo。程式碼歷史可永久保持精簡。
  報告的歷史可以依自己的週期改寫或壓縮,不影響程式碼的 PR。
- **C2 孤立的 `reports` 分支並定期壓縮:** 同樣概念但在同一個 repo。
  建置成本較低,但較不便(每個 workflow 都要 `git worktree`/`checkout`)。

成本:需修改 `commit-and-push` composite action、`deploy.yml`,以及
`build_docs.py` / `maintain_ai_gen_report.py` / QA 腳本中的 `ai_gen_report/` 路徑。

---

## 3. 建議

1. **現在(不改寫歷史):** A2(自動 90 天清理)、A7(本機 worktree)、A5
   (在 README 說明 partial clone)。
2. **接著:** A3(PDF 改放 Release 附件,並修改 `build_docs.py` 的連結)。
   這是影響最大的一項:占歷史的 62%。
3. **然後,在規劃好的時段做一次:** A8 → B2,期間暫停排程。預估結果是 **1.06 GB → 約 190 MB**。
4. **若之後成長仍是問題:** 採用 C1。否則接受報告歷史每年約 0.55 GB 的成長,並每年重做一次 B1。

## 4. 量測方式

```bash
git count-objects -vH
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(objectsize:disk) %(rest)'
# 依頂層目錄/副檔名分組,並與 HEAD 的 `git ls-files -s` 比對
```

`objectsize:disk` 是 pack 內經壓縮與 delta 編碼後的大小,所以各欄加總等於 pack 大小。
路徑歸屬取自 `rev-list` 為每個 blob 回報的第一個路徑。
