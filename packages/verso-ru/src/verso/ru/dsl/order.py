"""Where a record stands in its book — and where it should.

A record added from the page goes where the reader opened the gap, and the
gap may be in January for a child born in December: a record of the December
section written after the January ones, its windows at the end of the book.
The book's own order is read two ways.

By the scan first. A record whose window the reader drew has a place on the
album: its first window's frame, and how far down it. The file should list
those records in that order. Where it does not, the longest run that keeps
the order stands, and a record off the run belongs after the last record of
the run that comes no later than it on the scan — so one stray record is
found, and not its neighbours too.

By the book, for a record with no window: it belongs in the section of its
own month, by day and then number. A record a section holds whose dates are
in neither of the section's months is out of place; with no section of its
month there is nowhere to send it.

A record of the same number, sex and kind at the place found is its twin —
the same entry read twice, as often as not — and is named, for the reader to
replace or to keep.

Pure: the records' places in, the moves out. Reading them is
`verso.app_dsl.service`'s job.
"""
from __future__ import annotations

import calendar
import re
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from verso.ru.messages import t

# The month parameters of each record, its own date's first: the section's
# month fills each that is not written.
MONTH_PARAMS: dict[str, tuple[str, ...]] = {
    "birth": ("b_month", "k_month"), "christening": ("k_month",),
    "death": ("d_month", "b_month"), "marriage": ("w_month",),
}

def month_name(month: int) -> str:
    names = ["", t("dsl.order.month.1"), t("dsl.order.month.2"), t("dsl.order.month.3"), t("dsl.order.month.4"),
             t("dsl.order.month.5"), t("dsl.order.month.6"), t("dsl.order.month.7"), t("dsl.order.month.8"),
             t("dsl.order.month.9"), t("dsl.order.month.10"), t("dsl.order.month.11"), t("dsl.order.month.12")]
    return str(names[month])


@dataclass(frozen=True)
class Spot:
    """One record as the order is read: where it stands and what places it."""
    ordinal: int
    group: str                       # `Record.container`: the call it stands in
    kind: str                        # births / marriages / deaths
    number: int | str | None
    gender: str
    section_month: int | None        # the month of the `*_month(…)` section it stands in
    months: tuple[int, ...]          # the months its dates are in, its own first
    day: int | None
    key: tuple[int, int, float] | None    # its first window: frame index, side (`side`), top
    frame: str | None                # that frame's label, for the words
    # Whom it is about — the newborn, the deceased, the couple — orthography
    # aside (`names.match_key`): what tells a twin from a number repeated.
    name: str | None = None
    # The given name of the father (a burial's relative) it names, likewise.
    kin: str | None = None


@dataclass(frozen=True)
class Place:
    """Where a record belongs: right `after` or `before` the record at `anchor`."""
    anchor: int
    where: str                       # "after" / "before"
    by: str                          # "scan" / "book"
    twin: int | None                 # a record of its number, sex and kind there


# A window starting this far right begins on the right-hand page of a frame
# that shows a spread: a frame of 93об | 94 holds a record low on the left page
# and another high on the right one — the left page comes first, whatever the
# height.
RIGHT_PAGE = 0.45


def side(box: Sequence[float]) -> int:
    """0 for a window on the left (or only) page of its frame, 1 on the right."""
    return 1 if box[0] >= RIGHT_PAGE else 0


def month_of(code: object) -> int | None:
    """«Month.DECEMBER» → 12."""
    if isinstance(code, str) and code.startswith("Month."):
        try:
            return int(calendar.Month[code.removeprefix("Month.")])
        except KeyError:
            return None
    return None


def placements(spots: Sequence[Spot]) -> dict[int, Place]:
    """The records out of place, by ordinal, and where each belongs."""
    out: dict[int, Place] = {}
    keyed = [s for s in spots if s.key is not None]
    run = _longest_run(keyed)
    standing = [s for s in keyed if s.ordinal in run]
    for s in keyed:
        if s.ordinal in run or not standing:
            continue
        no_later = [r for r in standing if (r.key or (0, 0, 0.0)) <= (s.key or (0, 0, 0.0))]
        place = (Place(no_later[-1].ordinal, "after", "scan", None) if no_later
                 else Place(standing[0].ordinal, "before", "scan", None))
        twin = next((r for r in spots if r.ordinal != s.ordinal and r.key == s.key and _same(r, s)), None)
        if twin is not None:
            place = Place(twin.ordinal, "after", "scan", twin.ordinal)
        if not _already(spots, s, place):
            out[s.ordinal] = place
    for s in spots:
        if s.key is not None or s.section_month is None or not s.months or s.section_month in s.months:
            continue
        place = _by_book(spots, s)
        if place is not None and not _already(spots, s, place):
            out[s.ordinal] = place
    return dict(sorted(out.items()))


def twins(spots: Sequence[Spot]) -> dict[int, int]:
    """Each record that has a twin, by ordinal, and the twin's: the same kind,
    number and sex, its own date the same day of the same month, and about the
    same person, and — where both name one — by the same father. The scribe
    repeats a number often enough (in one village's books, pairs by the
    thousand, a few dozen of them on one date, a handful even of one given
    name, each a son of another father) — but for other people; the same child
    of the same day and father is the same entry read twice. With three alike,
    a record names the nearest."""
    alike: dict[tuple[str, str, str, int, int, str], list[Spot]] = {}
    for s in spots:
        if s.number is None or s.day is None or not s.months or not s.name:
            continue
        alike.setdefault((s.kind, str(s.number), s.gender, s.months[0], s.day, s.name), []).append(s)
    out: dict[int, int] = {}
    for group in alike.values():
        for s in group:
            others = [x for x in group if x is not s and (not x.kin or not s.kin or x.kin == s.kin)]
            if others:
                out[s.ordinal] = min(others, key=lambda x: abs(x.ordinal - s.ordinal)).ordinal
    return out


def describe(place: Place, spots: Mapping[int, Spot]) -> str:
    """«после № 28 м · декабрь · кадр 22»: the record it goes beside, that
    record's section, and the frame its window is on."""
    anchor = spots[place.anchor]
    number = str(t("dsl.order.no_number")) if anchor.number is None else f"№ {anchor.number}"
    parts = [str(t("dsl.order.after", number=number) if place.where == "after" else t("dsl.order.before", number=number))
             + (f" {anchor.gender}" if anchor.gender else "")]
    if anchor.section_month:
        parts.append(month_name(anchor.section_month))
    if anchor.frame:
        parts.append(frame_text(anchor.frame))
    return " · ".join(parts)


def frame_text(label: str) -> str:
    """«кадр22» → «кадр 22», «421» → «л. 421», as the page writes them."""
    m = re.match(r"^кадр(\d+)$", label)  # i18n: content — a frame's label as scans.toml keys it
    return str(t("dsl.order.frame", n=m.group(1))) if m else str(t("dsl.order.leaf", label=label))


def _same(a: Spot, b: Spot) -> bool:
    return (a.kind == b.kind and a.number is not None and str(a.number) == str(b.number)
            and a.gender == b.gender)


def _already(spots: Sequence[Spot], s: Spot, place: Place) -> bool:
    """Whether `s` stands where `place` sends it already."""
    at = next(i for i, x in enumerate(spots) if x.ordinal == s.ordinal)
    neighbour = spots[at - 1] if place.where == "after" and at > 0 else (
        spots[at + 1] if place.where == "before" and at + 1 < len(spots) else None)
    return neighbour is not None and neighbour.ordinal == place.anchor and neighbour.group == s.group


def _longest_run(keyed: Sequence[Spot]) -> set[int]:
    """The ordinals of the longest run of `keyed`, in file order, whose window
    keys never go back; of the runs that long, the one patience sorting finds."""
    tails: list[tuple[int, int, float]] = []
    tail_at: list[int] = []
    back: list[int] = [-1] * len(keyed)
    for i, s in enumerate(keyed):
        key = s.key or (0, 0, 0.0)
        k = bisect_right(tails, key)
        if k == len(tails):
            tails.append(key)
            tail_at.append(i)
        else:
            tails[k] = key
            tail_at[k] = i
        back[i] = tail_at[k - 1] if k > 0 else -1
    run: set[int] = set()
    i = tail_at[-1] if tail_at else -1
    while i >= 0:
        run.add(keyed[i].ordinal)
        i = back[i]
    return run


def _number(value: int | str | None) -> int:
    m = re.match(r"\d+", str(value or ""))
    return int(m.group(0)) if m else 0


def _by_book(spots: Sequence[Spot], s: Spot) -> Place | None:
    """The section of the record's own month, by day and then number."""
    month = s.months[0]
    group = next((x.group for x in spots if x.section_month == month and x.kind == s.kind), None)
    if group is None or group == s.group:
        return None
    members = [x for x in spots if x.group == group and x.ordinal != s.ordinal]
    if not members:
        return None
    mine = (s.day or 0, _number(s.number))
    no_later = [x for x in members if (x.day or 0, _number(x.number)) <= mine]
    twin = next((x for x in members if _same(x, s)), None)
    if twin is not None:
        return Place(twin.ordinal, "after", "book", twin.ordinal)
    if no_later:
        return Place(no_later[-1].ordinal, "after", "book", None)
    return Place(members[0].ordinal, "before", "book", None)
