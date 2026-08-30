#!/usr/bin/env python3
"""Naming for a daily generation cycle.

The generation window does not line up with a calendar day. Reports start at
17:00 UTC and the last cron fires at 03:40 UTC the *next* calendar day:

    daily_market_news           17:00 - 23:10
    daily_analysis fundamental  17:00 - 21:00
    daily_analysis technical    21:30 - 01:30  (next day)
    daily_analysis fundamental  02:00 - 03:40  (next day, additional block)

So a run at 22:00 and a run at 02:00 belong to the same batch. Every job in a
batch must agree on one name for it, or the collector will split one cycle
across two commits (or merge two cycles into one).

The rule: a cycle is named for the UTC date on which it *started*. Anything at
or after 17:00 UTC belongs to that day's cycle; anything before belongs to the
previous day's.

Used by the generators to name their artifacts and by collect_daily.yml to
build the prefix it collects.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

# First cron of the window (daily_market_news / daily_analysis fundamental).
CYCLE_START_HOUR_UTC = 17

# Every artifact belonging to a cycle is named "<PREFIX>-<cycle date>-...".
ARTIFACT_PREFIX = "cycle"


def cycle_date(now: datetime) -> str:
    """Return the YYYY-MM-DD name of the cycle that ``now`` belongs to.

    ``now`` must be timezone-aware; it is converted to UTC first, because the
    17:00 boundary is defined in UTC and a naive local timestamp would shift it.
    """
    if now.tzinfo is None:
        raise ValueError("cycle_date() requires a timezone-aware datetime")

    now = now.astimezone(timezone.utc)
    if now.hour < CYCLE_START_HOUR_UTC:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def artifact_prefix(date: str) -> str:
    """Prefix shared by every artifact in a cycle, e.g. ``cycle-2026-08-30``."""
    return f"{ARTIFACT_PREFIX}-{date}"


def belongs_to_cycle(name: str, date: str) -> bool:
    """Whether artifact ``name`` belongs to the cycle named ``date``.

    Matches on ``<prefix>-`` rather than the bare prefix: "cycle-2026-08-3" is
    a string prefix of "cycle-2026-08-30-analysis-NVDA-technical", so a plain
    startswith() would let a malformed date sweep in a neighbouring cycle's
    artifacts. Requiring the trailing separator makes the boundary exact.
    """
    return name.startswith(artifact_prefix(date) + "-")


def artifact_name(date: str, source: str, *parts: str) -> str:
    """Build a full artifact name.

    ``source`` identifies the producing workflow (``analysis``, ``news``, ...)
    and ``parts`` disambiguates within it (ticker, analysis type, ...).

    GitHub rejects artifact names containing " : < > | * ? \\ /, so those are
    replaced. Ticker symbols legitimately contain dots (2330.TW), which are
    allowed and left alone.
    """
    raw = "-".join([artifact_prefix(date), source, *parts])
    for bad in '":<>|*?\\/':
        raw = raw.replace(bad, "_")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--at",
        help="ISO-8601 UTC timestamp to evaluate instead of now (for testing)",
    )
    parser.add_argument(
        "--prefix",
        action="store_true",
        help="print the artifact prefix instead of the bare date",
    )
    args = parser.parse_args()

    now = (
        datetime.fromisoformat(args.at).replace(tzinfo=timezone.utc)
        if args.at
        else datetime.now(timezone.utc)
    )
    date = cycle_date(now)
    print(artifact_prefix(date) if args.prefix else date)


if __name__ == "__main__":
    main()
