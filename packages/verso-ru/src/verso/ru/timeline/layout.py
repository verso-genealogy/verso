"""Timeline model → geometry.

Turns people, marriages and bands into the paths, nodes and labels the renderer
draws. Pure and deterministic: same model in, byte-identical geometry out. That
matters because the exporter's whole guarantee is byte-stability — there is no
`terraform fmt` equivalent to normalise an HTML file — so nothing here may use
`random`, `hash()` (salted per process), or unordered iteration.

The visual grammar is that of the project's own design sketch the timeline
began as: every person is a horizontal thread drifting gently in their own lane;
a marriage pulls two threads onto one shared lane; a child's thread starts on
its parents' shared lane and swings down to its own. The `smooth()` Catmull-Rom
pass below is carried over from the sketch.
"""
from __future__ import annotations

import hashlib
import math
from itertools import pairwise
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from verso.ru.ages import format_age
from verso.ru.timeline.model import Marriage, Person, Timeline

PX_PER_YEAR = 17.0
LANE_HEIGHT = 30.0
MARGIN_LEFT = 150.0
MARGIN_RIGHT = 260.0
MARGIN_TOP = 168.0
MARGIN_BOTTOM = 104.0
GROUP_HEADER_HEIGHT = 78.0
# A name sits just above its owner's lane, clear of the thread itself.
LABEL_LANE_OFFSET = 8.0

# Years of blank axis kept either side of the data so no node sits on the edge.
PAD_YEARS_LEFT = 6
PAD_YEARS_RIGHT = 4

# How long a thread takes to dissolve once the records stop, in years.
FADE_OUT_YEARS = 14.0

NODE_BIRTH = "birth"
NODE_DEATH = "death"
NODE_MARRIAGE = "marriage"
NODE_LAST_SEEN = "last_seen"


@dataclass(frozen=True)
class Thread:
    """One person's life as a single path.

    The stroke is solid only where the records place them. `fade_in_to` is set
    when the birth is a window — the thread proves itself into existence across
    it. `fade_out_from` is set when no death was recorded — past the last year
    somebody wrote them down, the thread dissolves rather than ending on a node.
    """

    res_name: str
    d: str
    hue: str
    fades: bool
    start_x: float
    end_x: float
    fade_in_to: float | None
    fade_out_from: float | None


@dataclass(frozen=True)
class Node:
    """A drawn event. `hollow` marks a date the records do not pin down — a circa
    birth or an inferred marriage year — and is why the tooltip carries its own
    qualified year string rather than a bare number."""

    key: str
    kind: str
    x: float
    y: float
    hue: str
    hollow: bool
    title: str
    year: str
    detail: str


@dataclass(frozen=True)
class Label:
    x: float
    y: float
    text: str
    hue: str


@dataclass(frozen=True)
class BandBox:
    x: float
    width: float
    label: str
    detail: str
    years: str
    is_era: bool
    index: int
    label_x: float
    label_y: float


@dataclass(frozen=True)
class GroupBox:
    key: str
    label: str
    hue: str
    y: float
    height: float
    count: int
    unattached: bool


@dataclass(frozen=True)
class Decade:
    x: float
    label: str


@dataclass(frozen=True)
class Layout:
    width: float
    height: float
    first_year: int
    last_year: int
    threads: tuple[Thread, ...] = field(default=())
    nodes: tuple[Node, ...] = field(default=())
    labels: tuple[Label, ...] = field(default=())
    bands: tuple[BandBox, ...] = field(default=())
    groups: tuple[GroupBox, ...] = field(default=())
    decades: tuple[Decade, ...] = field(default=())


def _jitter(res_name: str) -> tuple[float, float]:
    """A stable (amplitude, phase) for a person's drift, derived from their
    res_name. sha256 rather than `hash()`: the builtin is salted per process and
    would make the output differ between runs."""
    digest = hashlib.sha256(res_name.encode("utf-8")).digest()
    amplitude = 4.0 + (digest[0] / 255.0) * 4.0
    phase = (digest[1] / 255.0) * math.tau
    return amplitude, phase


def smooth(points: Sequence[tuple[float, float]]) -> str:
    """Catmull-Rom through `points` as a cubic-bezier path — the sketch's
    `smooth()`, port for port, so the threads keep their drawn character."""
    if len(points) < 2:
        return ""
    parts = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        parts.append(
            f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f}"
            f" {p2[0]:.1f} {p2[1]:.1f}"
        )
    return "".join(parts)


def _order_group(
    members: Sequence[str],
    people: Mapping[str, Person],
    marriages: Mapping[str, Marriage],
) -> list[str]:
    """Lane order within one group: depth-first from the eldest ancestors, so a
    spouse lands next to their partner and children directly under the couple.
    Reading top to bottom is then reading down the generations."""
    inside = set(members)

    def by_birth(res: str) -> tuple[int, str]:
        return people[res].birth_year, res

    order: list[str] = []
    placed: set[str] = set()

    def visit(res: str) -> None:
        if res in placed or res not in inside:
            return
        placed.add(res)
        order.append(res)
        for union_res in people[res].unions:
            marriage = marriages.get(union_res)
            if marriage is None:
                continue
            for partner in marriage.kin_partners:
                visit(partner)
            for child in sorted(marriage.children, key=by_birth):
                visit(child)

    roots = [r for r in sorted(members, key=by_birth)
             if not any(p in inside for p in people[r].parents)]
    for root in roots:
        visit(root)
    # Anyone a cycle or a missing parent link left behind still gets a lane.
    for res in sorted(members, key=by_birth):
        visit(res)
    return order


def _year_to_x(year: float, first_year: int) -> float:
    return MARGIN_LEFT + (year - first_year) * PX_PER_YEAR


def _thread_points(
    person: Person,
    lane_y: float,
    couple_lanes: Mapping[str, float],
    marriages: Mapping[str, Marriage],
    start_y: float,
    end_at: float,
    first_year: int,
) -> list[tuple[float, float]]:
    """Sample a person's path in years, converging on each marriage in turn.

    Always returns at least two points. A life of nine days is a real life and
    needs a thread, even one too short to see at this scale — dropping it would
    silently remove a person from a picture that counts them.
    """
    amplitude, phase = _jitter(person.res_name)
    dated = sorted(
        (marriages[u].at, couple_lanes[u])
        for u in person.unions
        if u in marriages and marriages[u].at is not None and u in couple_lanes
    )

    def y_at(year: float) -> float:
        current = lane_y
        for marriage_at, couple_y in dated:
            if marriage_at is not None and year >= marriage_at:
                current = couple_y
        return current + amplitude * math.sin(year * 0.19 + phase)

    start_at = person.birth_at
    points: list[tuple[float, float]] = [(_year_to_x(start_at, first_year), start_y)]
    marriage_years = [y for y, _ in dated if y is not None]
    year = start_at + (5.0 if person.parents else 3.0)
    while year < end_at - 1:
        # Skip samples that would fight the convergence for the same stretch.
        if all(abs(year - my) > 3 for my in marriage_years):
            points.append((_year_to_x(year, first_year), y_at(year)))
        year += 6.0
    for marriage_at, couple_y in dated:
        if marriage_at is not None and start_at < marriage_at <= end_at:
            points.append((_year_to_x(marriage_at, first_year), couple_y))
    points.append((_year_to_x(max(end_at, start_at), first_year), y_at(end_at)))

    points.sort(key=lambda p: p[0])
    deduped: list[tuple[float, float]] = []
    for point in points:
        if not deduped or abs(point[0] - deduped[-1][0]) > 0.5:
            deduped.append(point)
    if len(deduped) < 2:
        deduped.append((deduped[0][0] + 1.0, deduped[0][1]))
    return deduped


def _y_at_x(points: Sequence[tuple[float, float]], x: float) -> float:
    """Linear interpolation of the sampled path at `x` — good enough to sit a
    marker on a thread whose real curve is a spline through the same points."""
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= x <= x1:
            span = x1 - x0
            return y0 if span <= 0 else y0 + (y1 - y0) * (x - x0) / span
    return points[-1][1]


def _year_text(year: int, *, approximate: bool) -> str:
    return f"ок. {year}" if approximate else str(year)


def _lifespan_detail(person: Person) -> str:
    """«Прожил 75 лет» for a completed life.

    `format_age` owns Russian numeral agreement (AGENTS.md: never interpolate a
    raw age) and returns None for an age it will not render, so the guard is on
    the rendered value, not on the number. An age of zero is dropped rather than
    rendered as «0 лет»: for the infants here the two years already say it, and
    «прожил 0 лет» reads as a formatting slip.
    """
    if person.death_year is None:
        return ""
    years = person.death_year - person.birth_year
    if years <= 0:
        return ""
    rendered = format_age(years)
    if not rendered:
        return ""
    verb = "Прожила" if person.gender == "female" else "Прожил"
    prefix = "около " if person.birth_circa else ""
    return f"{verb} {prefix}{rendered}"


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def build(timeline: Timeline) -> Layout:
    """Lay out `timeline`. The canvas grows with the data — one lane per person,
    one pixel-per-year scale across the whole span — so the caller pans and zooms
    rather than the drawing compressing to fit."""
    people, marriages = timeline.people, timeline.marriages
    if not people:
        return Layout(width=MARGIN_LEFT + MARGIN_RIGHT, height=MARGIN_TOP + MARGIN_BOTTOM,
                      first_year=0, last_year=0)

    first_year = timeline.first_year - PAD_YEARS_LEFT
    last_year = timeline.last_year + PAD_YEARS_RIGHT
    width = MARGIN_LEFT + (last_year - first_year) * PX_PER_YEAR + MARGIN_RIGHT

    lane_y: dict[str, float] = {}
    group_boxes: list[GroupBox] = []
    cursor = MARGIN_TOP
    for group in timeline.groups:
        top = cursor
        cursor += GROUP_HEADER_HEIGHT
        for res in _order_group(group.members, people, marriages):
            lane_y[res] = cursor
            cursor += LANE_HEIGHT
        group_boxes.append(GroupBox(
            key=group.key, label=group.label, hue=group.hue, y=top,
            height=cursor - top, count=len(group.members),
            unattached=group.unattached,
        ))
    height = cursor + MARGIN_BOTTOM

    hue_of = {res: g.hue for g in timeline.groups for res in g.members}

    # A marriage's shared lane sits between the partners; with one partner on the
    # timeline there is nothing to converge, so the node stays on their own lane.
    couple_lanes: dict[str, float] = {}
    for res_name in sorted(marriages):
        lanes = [lane_y[p] for p in marriages[res_name].kin_partners if p in lane_y]
        if lanes:
            couple_lanes[res_name] = sum(lanes) / len(lanes)

    threads: list[Thread] = []
    nodes: list[Node] = []
    labels: list[Label] = []

    def by_lane(res: str) -> tuple[float, str]:
        return lane_y.get(res, 0.0), res

    for res_name in sorted(people, key=by_lane):
        person = people[res_name]
        hue = hue_of.get(res_name, "v")
        own_lane = lane_y[res_name]
        # A child emerges from its parents' shared lane; everyone else simply
        # starts on their own.
        start_y = own_lane
        if person.parent_union and person.parent_union in couple_lanes:
            start_y = couple_lanes[person.parent_union]
        elif person.parents:
            parent_lanes = [lane_y[p] for p in person.parents if p in lane_y]
            if parent_lanes:
                start_y = sum(parent_lanes) / len(parent_lanes)
        # A recorded death ends the thread on its date. Otherwise it runs to the
        # last sighting and then dissolves over a fixed tail — visibly losing
        # the person rather than either killing them off at a bound or running
        # them to the edge of the canvas.
        if person.has_death and person.death_at is not None:
            end_at = person.death_at
        else:
            end_at = min(person.last_seen_at + FADE_OUT_YEARS, float(last_year))
        points = _thread_points(
            person, own_lane, couple_lanes, marriages, start_y, end_at, first_year,
        )
        fade_in_to = (
            _year_to_x(person.birth_uncertain_to, first_year)
            if person.birth_uncertain_to is not None else None
        )
        fade_out_from = (
            _year_to_x(person.last_seen_at, first_year)
            if not person.has_death else None
        )
        threads.append(Thread(
            res_name=res_name, d=smooth(points), hue=hue, fades=not person.has_death,
            start_x=points[0][0], end_x=points[-1][0],
            fade_in_to=fade_in_to, fade_out_from=fade_out_from,
        ))

        if person.birth_is_window and person.birth_uncertain_to is not None:
            year_text = f"между {person.birth_year} и {int(person.birth_uncertain_to)}"
            birth_detail = "точный год неизвестен — известно лишь, когда человек уже был взрослым"
        else:
            year_text = _year_text(person.birth_year, approximate=person.birth_circa)
            birth_detail = ("год рассчитан по возрасту в записи"
                            if person.birth_circa else "")
        nodes.append(Node(
            key=f"{res_name}:birth", kind=NODE_BIRTH,
            x=_year_to_x(person.birth_at, first_year), y=start_y, hue=hue,
            hollow=person.birth_circa or person.birth_is_window,
            title=f"Рождение — {person.name}",
            year=year_text,
            detail=_join(person.birth_place or "", birth_detail),
        ))
        if person.has_death and person.death_at is not None and person.death_year:
            nodes.append(Node(
                key=f"{res_name}:death", kind=NODE_DEATH,
                x=_year_to_x(person.death_at, first_year), y=points[-1][1], hue=hue,
                hollow=False,
                title=f"Смерть — {person.name}",
                year=str(person.death_year),
                detail=_join(_lifespan_detail(person), person.death_place or ""),
            ))
        elif person.last_seen_at > person.birth_at:
            # No death was recorded. Mark the last sighting instead — an honest
            # statement about the sources, not about the life.
            nodes.append(Node(
                key=f"{res_name}:last-seen", kind=NODE_LAST_SEEN,
                x=_year_to_x(person.last_seen_at, first_year),
                y=_y_at_x(points, _year_to_x(person.last_seen_at, first_year)),
                hue=hue, hollow=True,
                title=f"Последнее упоминание — {person.name}",
                year=str(person.last_seen_year),
                detail="даты смерти в наших записях нет — известно лишь, "
                       "что человек был жив в этом году",
            ))
        labels.append(Label(
            x=_year_to_x(person.birth_at, first_year) + 17.0,
            y=own_lane - LABEL_LANE_OFFSET, text=person.name, hue=hue,
        ))

    for res_name in sorted(marriages):
        marriage = marriages[res_name]
        if marriage.year is None or marriage.at is None or res_name not in couple_lanes:
            continue
        partners = [people[p].name for p in marriage.kin_partners if p in people]
        if marriage.outside_partner:
            partners.append(f"{marriage.outside_partner} (вне круга родства)")
        hue = hue_of.get(marriage.kin_partners[0], "v") if marriage.kin_partners else "v"
        nodes.append(Node(
            key=f"{res_name}:marriage", kind=NODE_MARRIAGE,
            x=_year_to_x(marriage.at, first_year), y=couple_lanes[res_name], hue=hue,
            hollow=marriage.year_inferred,
            title="Венчание",
            year=_year_text(marriage.year, approximate=marriage.year_inferred),
            detail=_join(
                " × ".join(partners),
                "год не записан — принят по рождению старшего ребёнка"
                if marriage.year_inferred else "",
            ),
        ))

    band_boxes: list[BandBox] = []
    era_index = 0
    for index, band in enumerate(timeline.bands):
        x = _year_to_x(band.from_year, first_year)
        # A single-year event still needs a strip wide enough to see and hover.
        span = max(_year_to_x(band.to_year + 1, first_year) - x, 14.0)
        if band.is_era:
            era_index += 1
        band_boxes.append(BandBox(
            x=x, width=span, label=band.label, detail=band.detail,
            years=band.years_label, is_era=band.is_era,
            index=(era_index - 1) if band.is_era else index,
            label_x=x + (6.0 if band.is_era else 9.0),
            label_y=44.0 if band.is_era else (78.0 + (index % 3) * 25.0),
        ))

    decades = tuple(
        Decade(x=_year_to_x(year, first_year), label=str(year))
        for year in range(_ceil_decade(first_year), last_year + 1, 10)
    )

    return Layout(
        width=width, height=height, first_year=first_year, last_year=last_year,
        threads=tuple(threads), nodes=tuple(nodes), labels=tuple(labels),
        bands=tuple(band_boxes), groups=tuple(group_boxes), decades=decades,
    )


def _ceil_decade(year: int) -> int:
    return -(-year // 10) * 10
