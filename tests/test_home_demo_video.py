"""The recorded demo on the landing page (`docs/overrides/home.html`).

The video, its poster and the chapter list are three things that have to agree:
the template names the files, `DEMO.starts` times the chapters, and each
language's `watch_ch` names them. A re-recorded video that is not re-timed, or a
chapter added in one language only, renders without error and is simply wrong.
"""
import ast
import re
import struct
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
HOME = (DOCS / "overrides" / "home.html").read_text(encoding="utf-8")

MAX_SECONDS = 90  # the demo is meant to be watched, not sat through


def jinja_set(name):
    """A `{%- set NAME = <literal> -%}` block, read as the Python literal it is."""
    m = re.search(r"\{%-? set " + name + r" = (.*?) -?%\}", HOME, re.S)
    assert m, f"home.html no longer sets {name}"
    return ast.literal_eval(m.group(1))


def mp4_seconds(path):
    """Duration from the mvhd box: no ffprobe, so the suite stays dependency-free."""
    data = path.read_bytes()
    at = data.find(b"mvhd")
    assert at != -1, f"{path.name} has no mvhd box"
    version = data[at + 4]
    if version == 1:
        timescale, duration = struct.unpack(">IQ", data[at + 24:at + 36])
    else:
        timescale, duration = struct.unpack(">II", data[at + 16:at + 24])
    return duration / timescale


DEMO = jinja_set("DEMO")
COPY = jinja_set("COPY")


def test_video_and_poster_are_committed():
    for key in ("src", "poster"):
        assert (DOCS / DEMO[key]).is_file(), f"{DEMO[key]} is missing from docs/"


def test_chapters_start_at_zero_and_ascend():
    starts = DEMO["starts"]
    assert starts[0] == 0
    assert starts == sorted(set(starts))


def test_every_chapter_starts_inside_the_video():
    seconds = mp4_seconds(DOCS / DEMO["src"])
    assert DEMO["starts"][-1] < seconds <= MAX_SECONDS


def test_both_languages_name_every_chapter():
    for lang in ("en", "zh"):
        chapters = COPY[lang]["watch_ch"]
        assert len(chapters) == len(DEMO["starts"]), lang
        assert all(len(c) == 2 and all(c) for c in chapters), lang


def test_watch_copy_exists_in_both_languages():
    keys = {k for k in COPY["en"] if k.startswith("watch_")}
    assert keys == {"watch_kick", "watch_h", "watch_p", "watch_label", "watch_ch", "watch_note"}
    assert keys <= set(COPY["zh"])


def test_media_urls_are_written_against_the_site_root():
    # The ZH landing page lives under /zh/ but assets are not mirrored there,
    # so a page-relative src would 404 on it.
    assert 'poster="{{ base_url }}/{{ DEMO.poster }}"' in HOME
    assert '<source src="{{ base_url }}/{{ DEMO.src }}"' in HOME
