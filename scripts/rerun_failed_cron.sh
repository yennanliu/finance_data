#!/usr/bin/env bash
# rerun_failed_cron.sh — re-run daily cron jobs that FAILED in a recent window
# by dispatching FRESH workflow_dispatch runs on the current default branch.
#
# WHY NOT `gh run rerun`?
#   `gh run rerun` replays a run at its ORIGINAL commit SHA. When a failure was
#   caused by a bug/config that has since been fixed on main (e.g. a model the
#   project can't access, an expired setting), a rerun re-executes the OLD broken
#   code and fails again. Dispatching a fresh run picks up current `main`, so the
#   fix applies. This script therefore *re-dispatches*, it does not `rerun`.
#
# HOW IT WORKS
#   1. Lists failed `schedule`-event runs for each daily workflow in the window.
#   2. Extracts each run's cron expression from its run title.
#   3. Decodes cron → ticker (+ analysis_type) using the case-maps embedded in
#      the workflow YAML itself, so the mapping never drifts out of sync.
#   4. Re-dispatches one fresh workflow_dispatch run per unique failed job.
#
# USAGE
#   ./scripts/rerun_failed_cron.sh [--since DAYS] [--workflow FILE]
#                                  [--wait] [--dry-run] [--delay N] [--repo o/r]
#
# EXAMPLES
#   ./scripts/rerun_failed_cron.sh --dry-run              # preview last 1 day
#   ./scripts/rerun_failed_cron.sh --since 2 --wait       # last 2 days, sequential
#   ./scripts/rerun_failed_cron.sh --workflow daily_analysis.yml
#
# Requires: gh (authenticated). Portable to macOS bash 3.2 and Linux CI.
set -euo pipefail

GH="${GH_BIN:-gh}"
REPO="${GH_REPO:-yennanliu/finance_data}"
SINCE_DAYS="${SINCE_DAYS:-1}"
DELAY="${TRIGGER_DELAY:-20}"    # seconds between dispatches when not --wait
WAIT=0
DRY_RUN=0
ONLY_WF=""

# Workflows that run on a daily schedule. Format: "file.yml"
WORKFLOWS=("daily_analysis.yml" "daily_market_news.yml")

die() { echo "Error: $*" >&2; exit 1; }
# Ensure a value-taking flag actually received a (non-empty) value under `set -u`,
# instead of failing later with a cryptic unbound-variable error.
require_val() { [[ -n "${2:-}" ]] || die "$1 requires a value"; }

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)    require_val --since "${2:-}";    SINCE_DAYS="$2"; shift 2 ;;
    --workflow) require_val --workflow "${2:-}"; ONLY_WF="$2";    shift 2 ;;
    --repo)     require_val --repo "${2:-}";     REPO="$2";       shift 2 ;;
    --delay)    require_val --delay "${2:-}";    DELAY="$2";      shift 2 ;;
    --wait)     WAIT=1;          shift ;;
    --dry-run)  DRY_RUN=1;       shift ;;
    -h|--help)
      sed -n '2,32p' "$0"; exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

# Validate numerics (also covers values supplied via SINCE_DAYS / TRIGGER_DELAY env).
[[ "$SINCE_DAYS" =~ ^[1-9][0-9]*$ ]] || die "--since must be a positive integer (got '$SINCE_DAYS')"
[[ "$DELAY"      =~ ^[0-9]+$      ]] || die "--delay must be a non-negative integer (got '$DELAY')"

[[ -n "$ONLY_WF" ]] && WORKFLOWS=("$ONLY_WF")

# ── Compute UTC cutoff (portable: macOS `date -v` vs GNU `date -d`) ────────────
if date -u -v-1d '+%Y' >/dev/null 2>&1; then
  CUTOFF=$(date -u -v-"${SINCE_DAYS}"d '+%Y-%m-%dT%H:%M:%SZ')
else
  CUTOFF=$(date -u -d "${SINCE_DAYS} days ago" '+%Y-%m-%dT%H:%M:%SZ')
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo "Re-dispatch failed cron jobs"
echo "  Repo    : $REPO"
echo "  Since   : ${SINCE_DAYS}d ago  (cutoff ${CUTOFF})"
echo "  Mode    : $([[ $DRY_RUN -eq 1 ]] && echo DRY-RUN || echo LIVE)$([[ $WAIT -eq 1 ]] && echo ' + wait-each')"
echo ""

TOTAL=0; PASS=0; FAIL=0; SKIP=0

# Look up "TICKER|ANALYSIS_TYPE" for a cron in a workflow YAML case-map.
# Uses fixed-string match on the `"CRON")` label so the `*` in the cron is literal.
lookup_job() {
  local file="$1" cron="$2" line ticker atype
  line=$(grep -F "\"${cron}\")" "$file" | head -1 || true)
  [[ -z "$line" ]] && { echo ""; return; }
  ticker=$(printf '%s' "$line" | sed -E 's/.*TICKER="([^"]+)".*/\1/')
  if printf '%s' "$line" | grep -q 'ANALYSIS_TYPE='; then
    atype=$(printf '%s' "$line" | sed -E 's/.*ANALYSIS_TYPE="([^"]+)".*/\1/')
  else
    atype=""
  fi
  echo "${ticker}|${atype}"
}

# Find the run WE just dispatched and wait for it to finish. Echoes "conclusion|runid".
# Correlates on (run id greater than the pre-dispatch max) AND (title contains the
# ticker), so a concurrent dispatch of a *different* ticker isn't mistaken for ours.
# gh returns no dispatched-run id, so two simultaneous dispatches of the SAME ticker
# still can't be distinguished — acceptable for this manual backfill helper.
wait_for_run() {
  local wf="$1" boundary="$2" ticker="$3" newid="" line status concl i
  [[ "$boundary" == "none" || -z "$boundary" ]] && boundary=0
  for i in $(seq 1 30); do
    sleep 4
    newid=$("$GH" run list --workflow "$wf" --repo "$REPO" --event workflow_dispatch --limit 20 \
      --json databaseId,displayTitle \
      --jq "[.[] | select((.databaseId > ${boundary}) and ((.displayTitle // \"\") | contains(\"${ticker}\")))] | .[0].databaseId // \"\"" \
      2>/dev/null || echo "")
    [[ -n "$newid" ]] && break
  done
  [[ -z "$newid" ]] && { echo "unknown|?"; return; }
  for i in $(seq 1 180); do
    line=$("$GH" run view "$newid" --repo "$REPO" --json status,conclusion \
             --jq '"\(.status)|\(.conclusion)"' 2>/dev/null || echo "|")
    status="${line%%|*}"; concl="${line##*|}"
    [[ "$status" == "completed" ]] && break
    sleep 10
  done
  echo "${concl}|${newid}"
}

for WF in "${WORKFLOWS[@]}"; do
  FILE="${REPO_ROOT}/.github/workflows/${WF}"
  if [[ ! -f "$FILE" ]]; then
    echo "!! workflow file not found: $FILE — skipping" >&2; continue
  fi

  echo "── ${WF} ──────────────────────────────────────────────"

  # Query failed scheduled runs; abort on a gh/API failure rather than silently
  # treating an auth/network error as "no failures in window".
  if ! TITLES=$("$GH" run list --workflow "$WF" --repo "$REPO" --event schedule --limit 200 \
        --json conclusion,createdAt,displayTitle \
        --jq "[.[] | select(.conclusion==\"failure\" and .createdAt >= \"${CUTOFF}\")] | .[].displayTitle"); then
    die "gh run list failed for ${WF} (authentication/API error?)"
  fi

  # Unique cron expressions among those failed runs.
  CRONS=()
  while IFS= read -r c; do [[ -n "$c" ]] && CRONS+=("$c"); done < <(
    printf '%s\n' "$TITLES" | grep -oE '[0-9]+ [0-9]+ \* \* \*' | sort -u
  )

  if [[ ${#CRONS[@]} -eq 0 ]]; then
    echo "  (no failed scheduled runs in window)"; echo ""; continue
  fi

  for CRON in "${CRONS[@]}"; do
    JOB=$(lookup_job "$FILE" "$CRON")
    if [[ -z "$JOB" ]]; then
      printf "  %-14s → (cron not in workflow case-map) SKIP\n" "$CRON"
      SKIP=$((SKIP+1)); continue
    fi
    TICKER="${JOB%%|*}"; ATYPE="${JOB##*|}"
    TOTAL=$((TOTAL+1))
    label="$TICKER ${ATYPE:-news}"

    if [[ $DRY_RUN -eq 1 ]]; then
      printf "  %-14s → would dispatch: %s\n" "$CRON" "$label"
      continue
    fi

    printf "  %-14s → dispatching %-28s ... " "$CRON" "$label"
    before=$("$GH" run list --workflow "$WF" --repo "$REPO" --event workflow_dispatch \
               --limit 1 --json databaseId --jq '.[0].databaseId // "none"' 2>/dev/null || echo none)

    if [[ -n "$ATYPE" ]]; then
      DISP=$("$GH" workflow run "$WF" --repo "$REPO" -f ticker="$TICKER" -f analysis_type="$ATYPE" 2>&1) || {
        echo "DISPATCH FAILED: $DISP"; FAIL=$((FAIL+1)); continue; }
    else
      DISP=$("$GH" workflow run "$WF" --repo "$REPO" -f ticker="$TICKER" 2>&1) || {
        echo "DISPATCH FAILED: $DISP"; FAIL=$((FAIL+1)); continue; }
    fi

    if [[ $WAIT -eq 1 ]]; then
      RES=$(wait_for_run "$WF" "$before" "$TICKER")
      concl="${RES%%|*}"; rid="${RES##*|}"
      if [[ "$concl" == "success" ]]; then
        echo "OK (run $rid)"; PASS=$((PASS+1))
      else
        echo "FAILED: ${concl} (run $rid)"; FAIL=$((FAIL+1))
      fi
    else
      echo "dispatched"; PASS=$((PASS+1))
      sleep "$DELAY"
    fi
  done
  echo ""
done

echo "════════════════════════════════════════════════════════"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "DRY-RUN: ${TOTAL} job(s) would be dispatched, ${SKIP} skipped."
else
  echo "Done: ${TOTAL} dispatched — ${PASS} ok, ${FAIL} failed, ${SKIP} skipped."
fi
[[ $FAIL -eq 0 ]]
