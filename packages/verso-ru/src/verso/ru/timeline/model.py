"""The timeline domain model — what the picture is *about*, with no geometry.

Deliberately narrower than `GeniProfile`/`GeniUnion`: a timeline needs a name, a
span, and the events that punctuate it. Everything here is frozen and free of
I/O so `projection` and `layout` can be tested by construction.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# Hue keys shared by the model and the renderer's palettes. The design sketch
# carried three (`v`/`c`/`p`); here they mean something: one per blood line, plus
# a third for people the records leave unattached.
HUE_LINE_A = "v"
HUE_LINE_B = "c"
HUE_UNATTACHED = "p"


@dataclass(frozen=True)
class Marriage:
    """A union touching at least one person on the timeline.

    `year` is None only when the union carries no marriage date AND has no dated
    children to infer one from — in that case there is nothing to draw a
    convergence at. `year_inferred` marks a year derived from the earliest
    child's birth rather than read off a marriage record.
    """

    res_name: str
    year: int | None
    at: float | None
    year_inferred: bool
    kin_partners: tuple[str, ...]
    outside_partner: str | None
    children: tuple[str, ...]

    @property
    def joins_two_threads(self) -> bool:
        """True when both partners are on the timeline, so the marriage is drawn
        as two threads converging rather than a node on a single thread."""
        return len(self.kin_partners) == 2


@dataclass(frozen=True)
class Person:
    """One thread. `birth_year` is required — a person with no birth year has no
    place on a time axis, and the projection refuses to invent one.

    The date fields encode **how much the records actually pin down**, because
    most of them pin down very little. Across the Горюхино tree 3626 births are
    a `between` window and 5763 deaths are an open `after` bound — so treating a
    bound's year as an event would make most of the picture a fabrication.

    * `birth_at` is where the evidence starts. `birth_uncertain_to` is set when
      the birth is a window («между 1855 и 1888»), and the thread fades IN across
      it rather than beginning on a node.
    * `death_at` / `death_year` are set **only for a recorded death**. A person
      known merely to have outlived some year has neither.
    * `last_seen_at` is the latest moment the records can show them alive. Past
      it the thread fades OUT — we lost sight of them, which is not dying.
    """

    res_name: str
    name: str
    gender: str
    birth_year: int
    birth_at: float
    birth_uncertain_to: float | None
    birth_circa: bool
    death_year: int | None
    death_at: float | None
    last_seen_year: int
    last_seen_at: float
    birth_place: str | None
    death_place: str | None
    parents: tuple[str, ...]
    parent_union: str | None
    unions: tuple[str, ...]

    @property
    def has_death(self) -> bool:
        """True only when a death was actually recorded. An `after 1866` bound is
        not a death — it is the last time somebody wrote the person down."""
        return self.death_at is not None

    @property
    def birth_is_window(self) -> bool:
        return self.birth_uncertain_to is not None


@dataclass(frozen=True)
class Group:
    """A band of related threads — one connected component of the kin graph,
    or the catch-all for people the records leave unattached."""

    key: str
    label: str
    hue: str
    members: tuple[str, ...]
    unattached: bool = False


@dataclass(frozen=True)
class Band:
    """A historical span painted behind the threads. `era` bands are wide
    grounds that tile the whole axis; `event` bands are narrow strips."""

    kind: str
    from_year: int
    to_year: int
    label: str
    detail: str

    @property
    def is_era(self) -> bool:
        return self.kind == "era"

    @property
    def years_label(self) -> str:
        if self.from_year == self.to_year:
            return str(self.from_year)
        return f"{self.from_year} — {self.to_year}"


@dataclass(frozen=True)
class Timeline:
    """Everything the renderer needs about the data, before any geometry."""

    village: str
    people: Mapping[str, Person]
    marriages: Mapping[str, Marriage]
    groups: tuple[Group, ...]
    bands: tuple[Band, ...]
    notes: tuple[str, ...] = field(default=())

    @property
    def first_year(self) -> int:
        return min(p.birth_year for p in self.people.values())

    @property
    def last_year(self) -> int:
        """The last year anything is known to happen — a recorded death, or
        failing that the last year a person can be shown alive. Never an assumed
        lifespan: nobody is run on past their evidence."""
        years = [p.last_seen_year for p in self.people.values()]
        years.extend(m.year for m in self.marriages.values() if m.year is not None)
        return max(years)
