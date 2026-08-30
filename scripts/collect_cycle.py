#!/usr/bin/env python3
"""Download every artifact belonging to one generation cycle and unpack it.

Background
----------
The ~100 daily generator jobs used to each commit and push their own report,
which produced ~100 commits a day and a permanent push race (36 of 38
market-news runs share a cron minute with an analysis run). They now upload
their output as a workflow artifact instead, and this script — run once per
cycle by collect_daily.yml — gathers them into a single commit.

Artifacts are scoped to the run that produced them, so `actions/download-artifact`
cannot reach across runs. The repo-wide Actions artifacts API can, which is what
this walks.

Safety
------
Artifact zips carry repo-relative paths and are extracted over a real checkout,
so extraction is guarded twice: entries that escape the destination (zip slip)
are rejected, and entries outside the known content roots are skipped.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.cycle import belongs_to_cycle, cycle_date  # noqa: E402

API_ROOT = "https://api.github.com"
PER_PAGE = 100

# Hard cap on pagination so a malformed response cannot spin forever.
MAX_PAGES = 100

# Only these top-level directories may be written by a collected artifact.
# A generator that starts writing somewhere else must be added here
# deliberately, rather than silently gaining write access to the whole repo.
ALLOWED_ROOTS = ("ai_gen_report", "data", "ws", "progress")


class CollectError(RuntimeError):
    pass


def _request(url: str, token: str, *, accept: str = "application/vnd.github+json"):
    """Issue a GET and return (status, headers, body-bytes).

    Redirects are NOT followed automatically. The artifact download endpoint
    answers 302 to a signed storage URL that rejects requests carrying an
    Authorization header, so the caller re-issues that hop without the token.
    """
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            return exc.code, dict(exc.headers), b""
        raise


def list_artifacts(repo: str, token: str) -> list[dict[str, Any]]:
    """Return every non-expired artifact in the repository, newest first."""
    artifacts: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{API_ROOT}/repos/{repo}/actions/artifacts?per_page={PER_PAGE}&page={page}"
        status, _headers, body = _request(url, token)
        if status != 200:
            raise CollectError(f"listing artifacts failed: HTTP {status}")
        payload = json.loads(body)
        batch = payload.get("artifacts", [])
        if not batch:
            break
        artifacts.extend(a for a in batch if not a.get("expired"))
        if len(batch) < PER_PAGE:
            break
    return artifacts


def select_for_cycle(
    artifacts: Iterable[dict[str, Any]], date: str
) -> list[dict[str, Any]]:
    """Pick this cycle's artifacts, keeping only the newest of each name.

    A re-run of a single ticker uploads a second artifact under the same name;
    collecting both would extract the stale one over the fresh one depending on
    ordering, so the newest wins.
    """
    newest: dict[str, dict[str, Any]] = {}
    for art in artifacts:
        name = art.get("name", "")
        if not belongs_to_cycle(name, date):
            continue
        seen = newest.get(name)
        if seen is None or str(art.get("created_at", "")) > str(seen.get("created_at", "")):
            newest[name] = art
    return sorted(newest.values(), key=lambda a: a["name"])


def download_artifact(repo: str, token: str, artifact_id: int) -> bytes:
    """Fetch one artifact's zip, following the signed-URL redirect by hand."""
    url = f"{API_ROOT}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    status, headers, body = _request(url, token)

    if status in (301, 302, 303, 307, 308):
        location = headers.get("Location") or headers.get("location")
        if not location:
            raise CollectError(f"artifact {artifact_id}: redirect without Location")
        # Storage rejects the Authorization header -> re-issue with no token.
        status, _headers, body = _request(location, token="")

    if status != 200:
        raise CollectError(f"artifact {artifact_id}: download failed HTTP {status}")
    return body


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def safe_extract(zip_bytes: bytes, dest: Path) -> list[str]:
    """Extract an artifact zip into ``dest``, rejecting unsafe entries.

    Returns the repo-relative paths actually written.
    """
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename

            if name.startswith("/") or ".." in Path(name).parts:
                print(f"  ! skipping unsafe path: {name}", file=sys.stderr)
                continue

            root = Path(name).parts[0] if Path(name).parts else ""
            if root not in ALLOWED_ROOTS:
                print(f"  ! skipping path outside content roots: {name}", file=sys.stderr)
                continue

            out = dest / name
            if not _is_within(dest, out):
                print(f"  ! skipping escaping path: {name}", file=sys.stderr)
                continue

            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                dst.write(src.read())
            written.append(name)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument(
        "--cycle-date",
        help="cycle to collect (YYYY-MM-DD); defaults to the current cycle",
    )
    parser.add_argument("--dest", default=".", help="repo root to unpack into")
    parser.add_argument(
        "--token", default=os.environ.get("GITHUB_TOKEN", ""), help="API token"
    )
    parser.add_argument(
        "--summary-out", help="write the collected artifact names here, one per line"
    )
    args = parser.parse_args()

    if not args.repo:
        print("error: --repo or GITHUB_REPOSITORY required", file=sys.stderr)
        return 2
    if not args.token:
        print("error: --token or GITHUB_TOKEN required", file=sys.stderr)
        return 2

    from datetime import datetime, timezone

    date = args.cycle_date or cycle_date(datetime.now(timezone.utc))
    dest = Path(args.dest).resolve()

    print(f"Collecting cycle {date} from {args.repo}")
    artifacts = list_artifacts(args.repo, args.token)
    selected = select_for_cycle(artifacts, date)
    print(f"  {len(artifacts)} live artifacts in repo, {len(selected)} in this cycle")

    if not selected:
        # Not an error: a cycle where every generator failed, or a re-run after
        # the artifacts expired. The workflow decides what to do with 0 files.
        print("No artifacts for this cycle — nothing to collect.")
        if args.summary_out:
            Path(args.summary_out).write_text("", encoding="utf-8")
        return 0

    all_written: list[str] = []
    failed: list[str] = []
    for art in selected:
        name = art["name"]
        try:
            blob = download_artifact(args.repo, args.token, art["id"])
            written = safe_extract(blob, dest)
            all_written.extend(written)
            print(f"  ✓ {name} ({len(written)} files)")
        except (CollectError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            # One bad artifact must not cost the whole cycle.
            failed.append(name)
            print(f"  ✗ {name}: {exc}", file=sys.stderr)

    print(f"\nCollected {len(all_written)} files from {len(selected) - len(failed)} artifacts.")
    if failed:
        print(f"WARNING: {len(failed)} artifact(s) failed: {', '.join(failed)}", file=sys.stderr)

    if args.summary_out:
        Path(args.summary_out).write_text(
            "\n".join(sorted(all_written)), encoding="utf-8"
        )

    # Fail only if every artifact failed; a partial cycle is still worth committing.
    return 1 if failed and not all_written else 0


if __name__ == "__main__":
    raise SystemExit(main())
