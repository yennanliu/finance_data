"""Tests for the cycle artifact collector.

The HTTP boundary is mocked; no network access.
"""

import io
import json
import urllib.parse
import zipfile

import pytest

from scripts import collect_cycle
from scripts.collect_cycle import (
    CollectError,
    download_artifact,
    list_artifacts,
    safe_extract,
    select_for_cycle,
)


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def artifact(name, aid=1, created="2026-08-30T18:00:00Z", expired=False):
    return {"id": aid, "name": name, "created_at": created, "expired": expired}


class TestSelectForCycle:
    def test_picks_only_the_named_cycle(self):
        arts = [
            artifact("cycle-2026-08-30-analysis-NVDA-technical", 1),
            artifact("cycle-2026-08-29-analysis-NVDA-technical", 2),
            artifact("cycle-2026-08-31-analysis-NVDA-technical", 3),
        ]
        got = select_for_cycle(arts, "2026-08-30")
        assert [a["id"] for a in got] == [1]

    def test_ignores_unrelated_artifacts(self):
        arts = [artifact("build-site", 1), artifact("coverage", 2)]
        assert select_for_cycle(arts, "2026-08-30") == []

    def test_rerun_keeps_newest_of_duplicate_name(self):
        name = "cycle-2026-08-30-analysis-NVDA-technical"
        arts = [
            artifact(name, 1, created="2026-08-30T18:00:00Z"),
            artifact(name, 2, created="2026-08-30T21:30:00Z"),  # the re-run
        ]
        got = select_for_cycle(arts, "2026-08-30")
        assert len(got) == 1
        assert got[0]["id"] == 2

    def test_result_is_deterministically_ordered(self):
        arts = [
            artifact("cycle-2026-08-30-analysis-TSLA-technical", 3),
            artifact("cycle-2026-08-30-analysis-AMD-technical", 1),
            artifact("cycle-2026-08-30-news-NVDA", 2),
        ]
        got = select_for_cycle(arts, "2026-08-30")
        assert [a["name"] for a in got] == sorted(a["name"] for a in arts)


class TestListArtifacts:
    def test_paginates_and_drops_expired(self, monkeypatch):
        page1 = {"artifacts": [artifact(f"a{i}", i) for i in range(100)]}
        page1["artifacts"][0]["expired"] = True
        page2 = {"artifacts": [artifact("b0", 500)]}
        calls = []

        def fake(url, token, accept="application/vnd.github+json"):
            calls.append(url)
            # Parse the param properly: "per_page=100" contains "page=1", so a
            # substring check here silently matches every page.
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            page = int(query["page"][0])
            return 200, {}, json.dumps(page1 if page == 1 else page2).encode()

        monkeypatch.setattr(collect_cycle, "_request", fake)
        got = list_artifacts("o/r", "tok")

        assert len(got) == 100  # 100 + 1 - 1 expired
        assert not any(a["expired"] for a in got)
        assert len(calls) == 2

    def test_stops_on_empty_page(self, monkeypatch):
        monkeypatch.setattr(
            collect_cycle,
            "_request",
            lambda *a, **k: (200, {}, json.dumps({"artifacts": []}).encode()),
        )
        assert list_artifacts("o/r", "tok") == []

    def test_raises_on_http_error(self, monkeypatch):
        monkeypatch.setattr(collect_cycle, "_request", lambda *a, **k: (403, {}, b""))
        with pytest.raises(CollectError, match="HTTP 403"):
            list_artifacts("o/r", "tok")


class TestDownloadArtifact:
    def test_follows_redirect_without_forwarding_the_token(self, monkeypatch):
        """Storage rejects a forwarded Authorization header."""
        seen = []

        def fake(url, token, accept="application/vnd.github+json"):
            seen.append((url, token))
            if "api.github.com" in url:
                return 302, {"Location": "https://storage.example/blob"}, b""
            return 200, {}, b"ZIPBYTES"

        monkeypatch.setattr(collect_cycle, "_request", fake)
        assert download_artifact("o/r", "secret", 42) == b"ZIPBYTES"

        assert seen[0][1] == "secret"  # API hop is authenticated
        assert seen[1][1] == ""  # storage hop is not

    def test_direct_200_needs_no_redirect(self, monkeypatch):
        monkeypatch.setattr(
            collect_cycle, "_request", lambda *a, **k: (200, {}, b"ZIP")
        )
        assert download_artifact("o/r", "t", 1) == b"ZIP"

    def test_redirect_without_location_is_an_error(self, monkeypatch):
        monkeypatch.setattr(collect_cycle, "_request", lambda *a, **k: (302, {}, b""))
        with pytest.raises(CollectError, match="redirect without Location"):
            download_artifact("o/r", "t", 1)

    def test_failure_status_raises(self, monkeypatch):
        monkeypatch.setattr(collect_cycle, "_request", lambda *a, **k: (500, {}, b""))
        with pytest.raises(CollectError, match="HTTP 500"):
            download_artifact("o/r", "t", 1)


class TestSafeExtract:
    def test_writes_files_preserving_repo_relative_paths(self, tmp_path):
        blob = make_zip(
            {
                "ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md": b"# r",
                "data/prices/NVDA.csv": b"d,o\n",
            }
        )
        written = safe_extract(blob, tmp_path)

        assert sorted(written) == [
            "ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md",
            "data/prices/NVDA.csv",
        ]
        assert (
            tmp_path / "ai_gen_report/technical/NVDA/technical-analysis_2026-08-30.md"
        ).read_bytes() == b"# r"

    def test_rejects_parent_traversal(self, tmp_path):
        blob = make_zip({"../../etc/passwd": b"pwned"})
        assert safe_extract(blob, tmp_path) == []
        assert not (tmp_path.parent.parent / "etc/passwd").exists()

    def test_rejects_absolute_path(self, tmp_path):
        blob = make_zip({"/etc/passwd": b"pwned"})
        assert safe_extract(blob, tmp_path) == []

    def test_rejects_path_outside_content_roots(self, tmp_path):
        """An artifact must not be able to rewrite workflows or scripts."""
        blob = make_zip({".github/workflows/deploy.yml": b"evil"})
        assert safe_extract(blob, tmp_path) == []
        assert not (tmp_path / ".github").exists()

        blob = make_zip({"scripts/generate_analysis.py": b"evil"})
        assert safe_extract(blob, tmp_path) == []

    def test_allows_each_declared_content_root(self, tmp_path):
        blob = make_zip(
            {
                "ai_gen_report/x.md": b"1",
                "data/prices/y.csv": b"2",
                "ws/z.txt": b"3",
                "progress/p.txt": b"4",
            }
        )
        assert len(safe_extract(blob, tmp_path)) == 4

    def test_overwrites_an_existing_file(self, tmp_path):
        target = tmp_path / "ai_gen_report/a.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")

        safe_extract(make_zip({"ai_gen_report/a.md": b"new"}), tmp_path)
        assert target.read_bytes() == b"new"

    def test_directory_entries_are_skipped(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("ai_gen_report/", b"")
            zf.writestr("ai_gen_report/a.md", b"x")
        assert safe_extract(buf.getvalue(), tmp_path) == ["ai_gen_report/a.md"]


class TestMainEndToEnd:
    """Exercise the whole path: list -> select -> download -> extract -> summary."""

    def _wire(self, monkeypatch, artifacts, zips):
        def fake(url, token, accept="application/vnd.github+json"):
            if url.endswith("/zip"):
                aid = int(url.rsplit("/", 2)[-2])
                return 200, {}, zips[aid]
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            page = int(query["page"][0])
            body = {"artifacts": artifacts if page == 1 else []}
            return 200, {}, json.dumps(body).encode()

        monkeypatch.setattr(collect_cycle, "_request", fake)

    def _argv(self, monkeypatch, tmp_path, summary, date="2026-08-30"):
        monkeypatch.setattr(
            "sys.argv",
            [
                "collect_cycle.py",
                "--repo", "o/r",
                "--token", "t",
                "--cycle-date", date,
                "--dest", str(tmp_path),
                "--summary-out", str(summary),
            ],
        )

    def test_collects_a_cycle_and_writes_the_summary(self, monkeypatch, tmp_path):
        arts = [
            artifact("cycle-2026-08-30-analysis-NVDA-technical", 1),
            artifact("cycle-2026-08-30-news-AMD", 2),
            artifact("cycle-2026-08-29-analysis-OLD-technical", 3),  # other cycle
        ]
        zips = {
            1: make_zip({"ai_gen_report/technical/NVDA/t_2026-08-30.md": b"r"}),
            2: make_zip({"ai_gen_report/market_news/AMD/n_2026-08-30.md": b"n"}),
            3: make_zip({"ai_gen_report/technical/OLD/t_2026-08-29.md": b"stale"}),
        }
        self._wire(monkeypatch, arts, zips)
        summary = tmp_path / "collected.txt"
        self._argv(monkeypatch, tmp_path, summary)

        assert collect_cycle.main() == 0
        assert (tmp_path / "ai_gen_report/technical/NVDA/t_2026-08-30.md").exists()
        assert (tmp_path / "ai_gen_report/market_news/AMD/n_2026-08-30.md").exists()
        # A neighbouring cycle must not leak in.
        assert not (tmp_path / "ai_gen_report/technical/OLD").exists()
        assert summary.read_text().splitlines() == [
            "ai_gen_report/market_news/AMD/n_2026-08-30.md",
            "ai_gen_report/technical/NVDA/t_2026-08-30.md",
        ]

    def test_empty_cycle_is_success_with_empty_summary(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, [], {})
        summary = tmp_path / "collected.txt"
        self._argv(monkeypatch, tmp_path, summary)

        # Not a failure: the workflow decides what an empty cycle means.
        assert collect_cycle.main() == 0
        assert summary.read_text() == ""

    def test_one_corrupt_artifact_does_not_lose_the_cycle(self, monkeypatch, tmp_path):
        arts = [
            artifact("cycle-2026-08-30-analysis-NVDA-technical", 1),
            artifact("cycle-2026-08-30-analysis-BAD-technical", 2),
        ]
        zips = {
            1: make_zip({"ai_gen_report/technical/NVDA/t.md": b"good"}),
            2: b"not a zip at all",
        }
        self._wire(monkeypatch, arts, zips)
        summary = tmp_path / "collected.txt"
        self._argv(monkeypatch, tmp_path, summary)

        assert collect_cycle.main() == 0
        assert (tmp_path / "ai_gen_report/technical/NVDA/t.md").read_bytes() == b"good"

    def test_missing_token_is_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "sys.argv",
            ["collect_cycle.py", "--repo", "o/r", "--token", "",
             "--dest", str(tmp_path)],
        )
        assert collect_cycle.main() == 2
