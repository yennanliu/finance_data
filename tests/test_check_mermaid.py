"""Tests for the check_mermaid alert reporter."""

import pytest

import check_mermaid as cm

pytestmark = pytest.mark.integration

FM = "---\ntitle: x\n---\n\n"


def _write(tmp_path, ticker, name, body):
    d = tmp_path / ticker
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


BROKEN = FM + "```mermaid\ngraph TD\n    A[ADX(14) = 17.44] --> B{x}\n```\n"
CLEAN = FM + '```mermaid\ngraph TD\n    A["ADX(14) = 17.44"] --> B{"x"}\n```\n'


def test_scan_finds_broken_and_skips_clean(tmp_path):
    _write(tmp_path, "aaa", "technical_analysis_2026-01-01_gemini.md", BROKEN)
    _write(tmp_path, "bbb", "technical_analysis_2026-01-01_gemini.md", CLEAN)
    findings = cm.scan(tmp_path)
    assert len(findings) == 1
    path, locs = findings[0]
    assert path.parent.name == "aaa"
    assert any("ADX(14)" in snip for _, snip in locs)


def test_main_is_non_blocking_and_prints_failed_part(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "aaa", "technical_analysis_2026-01-01_gemini.md", BROKEN)
    monkeypatch.setattr("sys.argv", ["check_mermaid.py", "--root", str(tmp_path)])
    cm.main()  # must not raise / SystemExit
    out = capsys.readouterr().out
    assert "broken Mermaid snippet" in out
    assert "[ADX(14) = 17.44]" in out  # the failed part is printed


def test_strict_exits_nonzero_on_failure(tmp_path, monkeypatch):
    _write(tmp_path, "aaa", "technical_analysis_2026-01-01_gemini.md", BROKEN)
    monkeypatch.setattr("sys.argv",
                        ["check_mermaid.py", "--root", str(tmp_path), "--strict"])
    with pytest.raises(SystemExit) as exc:
        cm.main()
    assert exc.value.code == 1


def test_emits_github_annotations_and_summary(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "aaa", "technical_analysis_2026-01-01_gemini.md", BROKEN)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "1")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.argv", ["check_mermaid.py", "--root", str(tmp_path)])
    cm.main()
    out = capsys.readouterr().out
    assert "::warning file=" in out
    text = summary.read_text(encoding="utf-8")
    assert "Mermaid check" in text
    assert "ADX(14)" in text


def test_clean_tree_reports_success(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "bbb", "technical_analysis_2026-01-01_gemini.md", CLEAN)
    monkeypatch.setattr("sys.argv", ["check_mermaid.py", "--root", str(tmp_path)])
    cm.main()
    assert "No broken Mermaid diagrams" in capsys.readouterr().out
