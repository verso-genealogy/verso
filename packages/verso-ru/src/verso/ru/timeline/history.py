"""Historical bands painted behind the threads.

Two kinds, deliberately different in weight:

* **era** — a wide ground band tiling the whole axis. These are village-specific
  and come from the project's own regional rules, so they carry information you
  will not find on a general history timeline: a village's сословие sequence,
  bounded as the DSL status constants are bounded.
* **event** — a narrow strip for a national event the people on a timeline
  actually lived through.

Both are the corpus's data since 0.1.0 — a village's eras in its village.toml
(`[[timeline.era]]`), the events in `<corpus>/timeline.toml` — and reach this
module as a `History` the CLI builds; the library draws no band of its own.

The detail lines state what the sources say and stop there. Where a coincidence
is striking but unsourced — family knowledge carried as `additional_info`, not
war records — the band is drawn and the reader draws the conclusion. Do not
caption it for them.
"""
from __future__ import annotations

from dataclasses import dataclass

from verso.ru.timeline.model import Band


@dataclass(frozen=True)
class History:
    """What a timeline paints behind its threads: the village's eras, the events,
    and the note for kin that falls into more than one group."""
    eras: tuple[Band, ...] = ()
    events: tuple[Band, ...] = ()
    split_note: str | None = None


NO_HISTORY = History()


def bands_for(history: History, *, first_year: int, last_year: int) -> tuple[Band, ...]:
    """The bands to paint, eras then events, clipped to the drawn span.

    An era whose whole range falls outside the span is dropped; one that
    straddles an edge is trimmed, so the ground always tiles exactly the axis
    that is drawn. A village with no eras gets the events only — never an
    invented сословие history.
    """
    out: list[Band] = []
    for band in history.eras + history.events:
        start = max(band.from_year, first_year)
        end = min(band.to_year, last_year)
        if start > end:
            continue
        if (start, end) == (band.from_year, band.to_year):
            out.append(band)
        else:
            out.append(Band(band.kind, start, end, band.label, band.detail))
    return tuple(out)
