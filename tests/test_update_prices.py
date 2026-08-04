"""Tests for the price-store CLI (scripts/update_prices.py).

The store module itself is covered by test_prices.py; this pins the CLI around it
— ticker discovery, the --only-missing and --dry-run paths, the status tally, and
the exit-code policy CI depends on (fail only on a total outage, tolerate a
handful of individually-failing tickers).

Fully offline: every fetch is monkeypatched.
"""

import json

import pytest

import update_prices as up
from analysis.data import prices

pytestmark = pytest.mark.unit


# ── ticker discovery ─────────────────────────────────────────────────────────
def _fake_repo(monkeypatch, tmp_path, schedule=None, report_dirs=()):
    if schedule is not None:
        sched = tmp_path / ".ticker_schedule.json"
        sched.write_text(json.dumps(schedule), encoding="utf-8")
        monkeypatch.setattr(up, "SCHEDULE_FILE", sched)
    else:
        monkeypatch.setattr(up, "SCHEDULE_FILE", tmp_path / "absent.json")

    roots = []
    for i, names in enumerate(report_dirs):
        root = tmp_path / f"root{i}"
        for n in names:
            (root / n).mkdir(parents=True)
        roots.append(root)
    monkeypatch.setattr(up, "REPORT_ROOTS", roots)


def test_discover_unions_schedule_and_report_dirs(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path,
               schedule={"tickers": {"fundamental": ["AMD", "NVDA"],
                                     "technical": ["NVDA", "TSLA"]}},
               report_dirs=[["amd", "goog"], ["2330.tw"]])
    assert up.discover_tickers() == ["2330.tw", "amd", "goog", "nvda", "tsla"]


def test_discover_lowercases_and_deduplicates(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path,
               schedule={"tickers": {"a": ["AMD", "amd", " AMD "]}},
               report_dirs=[["AMD"]])
    assert up.discover_tickers() == ["amd"]


def test_discover_survives_a_missing_schedule(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, schedule=None, report_dirs=[["amd"]])
    assert up.discover_tickers() == ["amd"]


def test_discover_survives_a_corrupt_schedule(monkeypatch, tmp_path, capsys):
    sched = tmp_path / ".ticker_schedule.json"
    sched.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(up, "SCHEDULE_FILE", sched)
    monkeypatch.setattr(up, "REPORT_ROOTS", [])
    assert up.discover_tickers() == []
    assert "could not read" in capsys.readouterr().out


def test_discover_empty_when_nothing_exists(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, schedule=None, report_dirs=[])
    assert up.discover_tickers() == []


# ── main() ───────────────────────────────────────────────────────────────────
def _bars(dates, start=100.0):
    return [{"date": d, "open": start + i - 1, "high": start + i + 2,
             "low": start + i - 2, "close": start + i,
             "volume": 1_000_000, "div": None, "split": None}
            for i, d in enumerate(dates)]


DATES = ["2026-07-29", "2026-07-30", "2026-07-31"]


@pytest.fixture
def cli(monkeypatch, tmp_path):
    """Run main() with a temp store and a canned fetch; returns a runner."""
    state = {"bars": _bars(DATES)}

    def fetch(symbol, years=prices.KEEP_YEARS):
        got = state["bars"]
        if isinstance(got, Exception):
            raise got
        return got

    monkeypatch.setattr(prices, "fetch_history", fetch)

    def run(*argv, bars=None):
        if bars is not None:
            state["bars"] = bars
        monkeypatch.setattr("sys.argv", ["update_prices.py", "--store", str(tmp_path), *argv])
        up.main()

    run.store = tmp_path
    run.set_bars = lambda b: state.__setitem__("bars", b)
    return run


def test_main_creates_a_store_file(cli, capsys):
    cli("AMD")
    out = capsys.readouterr().out
    assert "created" in out
    assert (cli.store / "amd.csv").exists()


def test_main_second_run_reports_unchanged(cli, capsys):
    cli("AMD")
    capsys.readouterr()
    cli("AMD")
    out = capsys.readouterr().out
    assert "unchanged" in out and "created" not in out


def test_main_appends_a_new_bar(cli, capsys):
    cli("AMD")
    capsys.readouterr()
    cli("AMD", bars=_bars(DATES + ["2026-08-03"]))
    assert "appended" in capsys.readouterr().out


def test_main_reports_a_restatement(cli, capsys):
    cli("AMD", bars=_bars(DATES, start=400.0))
    capsys.readouterr()
    halved = [dict(b, open=b["open"] / 2, high=b["high"] / 2,
                   low=b["low"] / 2, close=b["close"] / 2)
              for b in _bars(DATES, start=400.0)]
    cli("AMD", bars=halved)
    out = capsys.readouterr().out
    assert "RESTATED" in out, out


def test_main_only_missing_skips_existing(cli, capsys):
    cli("AMD")
    capsys.readouterr()
    before = (cli.store / "amd.csv").read_text(encoding="utf-8")
    cli("AMD", "--only-missing", bars=_bars(DATES + ["2026-08-03"]))
    # The new bar is not fetched at all, so the file is untouched.
    assert (cli.store / "amd.csv").read_text(encoding="utf-8") == before


def test_main_dry_run_writes_nothing(cli, capsys):
    cli("AMD", "--dry-run")
    out = capsys.readouterr().out
    assert "dry run" in out and "would write" in out
    assert not (cli.store / "amd.csv").exists()


def test_main_dry_run_reports_an_append_without_writing(cli, capsys):
    cli("AMD")
    before = (cli.store / "amd.csv").read_text(encoding="utf-8")
    capsys.readouterr()
    cli("AMD", "--dry-run", bars=_bars(DATES + ["2026-08-03"]))
    out = capsys.readouterr().out
    assert "would write 1 new bars" in out, out
    assert (cli.store / "amd.csv").read_text(encoding="utf-8") == before


def test_main_dry_run_reports_a_gate_rejection(cli, capsys):
    cli("AMD")
    capsys.readouterr()
    # Nothing progressed, so the exit policy fires — a run where every ticker is
    # rejected is a signal, not a success, and a dry run reports the same verdict
    # a real run would reach.
    with pytest.raises(SystemExit):
        cli("AMD", "--dry-run", bars=_bars(DATES[:1]))  # bar-count regression
    assert "skipped" in capsys.readouterr().out


def test_main_dry_run_reports_a_fetch_error(cli, capsys):
    with pytest.raises(SystemExit):
        cli("AMD", "--dry-run", bars=RuntimeError("boom"))
    out = capsys.readouterr().out
    assert "failed" in out and "boom" in out


def test_main_exits_nonzero_when_every_ticker_fails(cli):
    # A total outage must fail the CI job…
    with pytest.raises(SystemExit) as e:
        cli("AMD", "NVDA", bars=RuntimeError("outage"))
    assert e.value.code == 1


def test_main_survives_a_partial_failure(cli, capsys, monkeypatch):
    # …but one bad ticker among several must not.
    def fetch(symbol, years=prices.KEEP_YEARS):
        if symbol == "NVDA":
            raise RuntimeError("just this one")
        return _bars(DATES)

    monkeypatch.setattr(prices, "fetch_history", fetch)
    cli("AMD", "NVDA")  # no SystemExit
    out = capsys.readouterr().out
    assert "created=1" in out and "failed=1" in out


def test_main_uses_discovery_when_no_tickers_given(cli, capsys, monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, schedule={"tickers": {"a": ["AMD"]}}, report_dirs=[])
    cli()
    assert "amd" in capsys.readouterr().out


def test_main_maps_taiwan_symbols(cli, capsys):
    cli("0050")
    assert "0050.TW" in capsys.readouterr().out
