"""Render a village's blood-relatives as a genealogy timeline — one HTML page.

A third publishing target alongside geni and familio, and the only read-only
one: it uploads nothing and touches no terraform state, it just draws what the
records already say. Runs the SAME DSL→domain translation as the other two
(`verso.ru.pipeline.translate.translate_village`, including consolidation), then
projects the curated kin subset onto a timeline model (`verso.ru.timeline`).

Kin come from `<village>/familio_kin.py` — the same curated registry the familio
projection uses, including its `PARENT_OVERRIDES`, which pin the parent links
that the records leave implicit.

Output (default `<village>/timeline.html`):
    timeline.html    — self-contained page: pan/zoom SVG, no build step

Usage:
    python -m verso.ru.cli.generate_timeline --village "Горюхино"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verso.ru import corpus_data
from verso.ru.cli.generate_familio_tf import load_kin
from verso.ru.pipeline.translate import translate_village
from verso.ru.timeline.history import History
from verso.ru.timeline.layout import build as build_layout
from verso.ru.timeline.model import Band
from verso.ru.timeline.projection import project
from verso.ru.timeline.render import render


def history_of(village_dir: Path) -> History:
    """The bands and note of `village_dir`'s timeline: its eras and note (village.toml),
    the corpus's events (`<corpus>/timeline.toml`)."""
    settings = corpus_data.village(village_dir)
    return History(
        eras=tuple(Band("era", e.from_year, e.to_year, e.label, e.detail) for e in settings.eras),
        events=tuple(Band("event", e.from_year, e.to_year, e.label, e.detail) for e in corpus_data.timeline_events()),
        split_note=settings.split_note,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--village", required=True)
    parser.add_argument(
        "--output",
        help="Where to write the page (default <village>/timeline.html).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any DSL file failed to import (its records — and any kin "
             "among them — would be silently missing from the timeline).",
    )
    args = parser.parse_args(argv)

    village_dir = Path(args.village)
    output = Path(args.output) if args.output else village_dir / "timeline.html"

    generator, _skipped = translate_village(village_dir, strict=args.strict)
    kin, parent_overrides, _sources = load_kin(village_dir)
    timeline = project(
        generator.canonical_profiles(),
        generator.canonical_unions(),
        kin,
        village=village_dir.name,
        parent_overrides=parent_overrides,
        history=history_of(village_dir),
    )
    layout = build_layout(timeline)
    page = render(timeline, layout)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")

    joined = sum(1 for m in timeline.marriages.values() if m.joins_two_threads)
    print(
        f"{output}: {len(timeline.people)} people, "
        f"{len(timeline.marriages)} marriages ({joined} between kin), "
        f"{timeline.first_year}–{timeline.last_year}, "
        f"{len(timeline.groups)} groups",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
