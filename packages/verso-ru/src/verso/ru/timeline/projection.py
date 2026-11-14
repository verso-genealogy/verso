"""geni domain model → timeline model.

Owns every "what does the data mean" decision the picture rests on, and none of
the "where does it go on screen" ones (that is `layout`). Free of I/O so it can
be tested by constructing `GeniProfile`/`GeniUnion` objects directly, the way
`tests/test_familio_projection.py` does.

The governing rule is that the drawing may not claim more than the records do:
a person with no death year gets a thread that fades, not a death; a union with
no marriage date gets a convergence inferred from its earliest child and says so;
a marriage to someone outside the kin registry is a node on one thread, not an
invented second thread.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from verso.ru.ages import agree
from verso.core import places
from verso.ru.naming.surnames import feminize_surname
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.targets.geni.translator.res_names import location_label
from verso.core.targets.geni.union import GeniUnion
from verso.ru.timeline.history import NO_HISTORY, History, bands_for
from verso.ru.timeline.model import (
    HUE_LINE_A, HUE_LINE_B, HUE_UNATTACHED, Group, Marriage, Person, Timeline)

# Hues handed to groups in size order. Beyond the third, groups reuse the cycle —
# the palette carries three neons and a fourth blood line has never existed.
_GROUP_HUES = (HUE_LINE_A, HUE_LINE_B, HUE_UNATTACHED)

UNATTACHED_KEY = "unattached"
UNATTACHED_LABEL = "без родственной связи в наших записях"


class KinResolutionError(ValueError):
    """A kin-registry res_name with no matching canonical profile — a typo, or a
    name left stale after re-consolidation. Mirrors the familio projection's
    error rather than silently dropping a relative from the picture."""

    def __init__(self, missing: Sequence[str]):
        self.missing = list(missing)
        super().__init__(
            "kin res_name(s) not found among canonical profiles: "
            + ", ".join(sorted(missing))
        )


def _year(event: GeniEvent | None) -> int | None:
    if event is None or event.date is None:
        return None
    return event.date.year


def _fraction(year: int, month: int | None, day: int | None) -> float:
    """A year plus its position inside itself. The month is a twelfth and the day
    a 31st of that — precise enough to place a mark, never claimed to be more."""
    return year + (((month or 1) - 1) + ((day or 1) - 1) / 31.0) / 12.0


def _at(event: GeniEvent | None) -> float | None:
    """Where an event sits on the axis, or None if it carries no year."""
    if event is None or event.date is None or event.date.year is None:
        return None
    return _fraction(event.date.year, event.date.month, event.date.day)


def _end_at(event: GeniEvent | None) -> float | None:
    """The far edge of a `between` window, or None when the date is not one."""
    if event is None or event.date is None or event.date.end_year is None:
        return None
    return _fraction(event.date.end_year, event.date.end_month, event.date.end_day)


def _is_bound(event: GeniEvent | None) -> bool:
    """True when the date is a RANGE rather than an event.

    `range="after"` on a death means «умер после 1866» — the last year somebody
    wrote the person down, not the year they died. `between` is a window. Both
    are evidence of a life, not of its end, and the drawing must not promote
    either into a death.
    """
    return bool(event is not None and event.date is not None and event.date.date_range)


def _is_circa(event: GeniEvent | None) -> bool:
    return bool(event is not None and event.date is not None and event.date.circa)


def _place(event: GeniEvent | None) -> str | None:
    """A readable place hierarchy for an event, via the structured
    entry of the corpus's places. An event whose location did not come from
    the places yields None rather than a free-text guess."""
    if event is None or not event.location:
        return None
    key = places.current().key_for_body(event.location)
    return location_label(key) if key else None


def display_name(profile: GeniProfile) -> str:
    """«Имя Отчество Фамилия», collapsing the blanks a stub profile leaves."""
    parts = [profile.first_name, profile.middle_name, profile.last_name]
    return " ".join(p for p in parts if p).strip()


def _marriage_year(
    union: GeniUnion, profiles: Mapping[str, GeniProfile],
) -> tuple[int | None, bool]:
    """`(year, inferred)` for a union's convergence point.

    A recorded marriage date wins. Otherwise the couple demonstrably existed by
    the time their eldest child was born, so the earliest child's birth year
    minus one is a defensible lower bound — flagged `inferred` so the renderer
    can draw it as provisional. A union with neither gets no year at all.
    """
    recorded = _year(union.marriage)
    if recorded is not None:
        return recorded, False
    births = [
        _year(profiles[c].birth)
        for c in sorted(union.children)
        if c in profiles and _year(profiles[c].birth) is not None
    ]
    known = [b for b in births if b is not None]
    if known:
        return min(known) - 1, True
    return None, False


def _build_marriages(
    unions: Mapping[str, GeniUnion],
    profiles: Mapping[str, GeniProfile],
    kin: frozenset[str],
) -> dict[str, Marriage]:
    """Every union touching at least one person on the timeline."""
    out: dict[str, Marriage] = {}
    for res_name in sorted(unions):
        union = unions[res_name]
        partners = [union.partner_1, union.partner_2]
        kin_partners = tuple(sorted(p for p in partners if p and p in kin))
        if not kin_partners:
            continue
        outside = [p for p in partners if p and p not in kin]
        outside_name = None
        if outside and outside[0] in profiles:
            outside_name = display_name(profiles[outside[0]]) or None
        year, inferred = _marriage_year(union, profiles)
        # An inferred year has no date behind it, so it sits at the year start.
        at = _at(union.marriage) if not inferred else None
        if at is None and year is not None:
            at = float(year)
        out[res_name] = Marriage(
            res_name=res_name,
            year=year,
            at=at,
            year_inferred=inferred,
            kin_partners=kin_partners,
            outside_partner=outside_name,
            children=tuple(sorted(c for c in union.children if c in kin)),
        )
    return out


def _parent_links(
    marriages: Mapping[str, Marriage],
    kin: frozenset[str],
    parent_overrides: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """`(parent_union_by_child, parents_by_child)`.

    Union membership is the primary source. `PARENT_OVERRIDES` — the registry's
    hand-pinned links, which exist precisely for people whose birth-union is not
    in the records — then fills in and, where a matching union does exist, wins.
    Override entries naming a bare familio UUID rather than a kin res_name are
    parents that live only on the user's familio tree; they cannot be drawn, so
    they are filtered out here.
    """
    parent_union: dict[str, str] = {}
    parents: dict[str, tuple[str, ...]] = {}
    for res_name in sorted(marriages):
        marriage = marriages[res_name]
        for child in marriage.children:
            parent_union[child] = res_name
            parents[child] = marriage.kin_partners

    # A union keyed by the kin partners it holds, so an override naming parents
    # can be resolved back to the union that draws them as a couple.
    by_partners = {
        frozenset(m.kin_partners): m.res_name
        for m in marriages.values()
        if m.kin_partners
    }
    for child in sorted(parent_overrides):
        if child not in kin:
            continue
        pinned = tuple(p for p in parent_overrides[child] if p in kin)
        if not pinned:
            continue
        parents[child] = pinned
        matched = by_partners.get(frozenset(pinned))
        if matched is not None:
            parent_union[child] = matched
    return parent_union, parents


def _components(
    people: Mapping[str, Person], marriages: Mapping[str, Marriage],
) -> list[list[str]]:
    """Connected components of the kin graph — spouses and parent/child links —
    each sorted by birth year, the list ordered by size then earliest birth.

    These are the natural top-level bands: a blood line is exactly a component.
    That the Горюхино registry does NOT resolve to two clean components is the
    point of drawing them separately rather than assuming.
    """
    adjacency: dict[str, set[str]] = {res: set() for res in people}
    for marriage in marriages.values():
        linked = list(marriage.kin_partners)
        for child in marriage.children:
            if child in adjacency:
                for partner in marriage.kin_partners:
                    adjacency[partner].add(child)
                    adjacency[child].add(partner)
        for a in linked:
            for b in linked:
                if a != b:
                    adjacency[a].add(b)
    for res, person in people.items():
        for parent in person.parents:
            if parent in adjacency:
                adjacency[res].add(parent)
                adjacency[parent].add(res)

    def by_birth(res: str) -> tuple[int, str]:
        return people[res].birth_year, res

    seen: set[str] = set()
    components: list[list[str]] = []
    for res in sorted(people, key=by_birth):
        if res in seen:
            continue
        stack, block = [res], []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            block.append(node)
            stack.extend(sorted(adjacency[node] - seen))
        components.append(sorted(block, key=by_birth))

    def by_size(block: list[str]) -> tuple[int, int, str]:
        return -len(block), people[block[0]].birth_year, block[0]

    components.sort(key=by_size)
    return components


def _pluralize_surname(name: str) -> str:
    """«Сидоров» → «Сидоровы». Regular for the -ов/-ев/-ин endings that every
    surname in these registries takes; anything else is left alone."""
    return f"{name}ы" if name.endswith(("ов", "ев", "ин")) else name


def _group_label(block: Sequence[str], people: Mapping[str, Person]) -> str:
    """Name a component after the surname its members carry.

    Men and women of one family are recorded under the same surname in
    different grammatical genders (Сидоров / Сидорова), so counting is done on the
    feminized form and the shortest spelling seen — the masculine one — is
    displayed. Several *different* surnames are also usual, because these
    families shift name across the records (Ежевикин→Ежевин, Сидоров→Сидорин→Видоплясов),
    so the two commonest are joined.
    """
    counts: dict[str, int] = {}
    spellings: dict[str, str] = {}
    for res in block:
        surname = people[res].name.split()[-1] if people[res].name else ""
        # A person with no surname leaves a patronymic in the last slot.
        if not surname or surname.endswith(("ич", "вна", "чна")):
            continue
        key = feminize_surname(surname)
        counts[key] = counts.get(key, 0) + 1
        if key not in spellings or len(surname) < len(spellings[key]):
            spellings[key] = surname
    if not counts:
        return "линия"

    def by_frequency(key: str) -> tuple[int, str]:
        return -counts[key], key

    ranked = sorted(counts, key=by_frequency)
    return " / ".join(_pluralize_surname(spellings[k]) for k in ranked[:2])


def _groups(
    people: Mapping[str, Person], marriages: Mapping[str, Marriage],
) -> tuple[Group, ...]:
    """Components sized 2+ become their own labelled band; every isolated person
    is collected into one trailing «без родственной связи» band. Splitting nine
    singletons into nine bands would say nothing; one band says exactly the
    useful thing — these are the kin our records do not connect to anyone."""
    blocks = _components(people, marriages)
    lines = [b for b in blocks if len(b) > 1]
    def by_birth(res: str) -> tuple[int, str]:
        return people[res].birth_year, res

    loners = sorted((b[0] for b in blocks if len(b) == 1), key=by_birth)
    groups: list[Group] = []
    for index, block in enumerate(lines):
        groups.append(Group(
            key=f"line-{index + 1}",
            label=_group_label(block, people),
            hue=_GROUP_HUES[index % len(_GROUP_HUES)],
            members=tuple(block),
        ))
    if loners:
        groups.append(Group(
            key=UNATTACHED_KEY,
            label=UNATTACHED_LABEL,
            hue=HUE_UNATTACHED,
            members=tuple(loners),
            unattached=True,
        ))
    return tuple(groups)


def _notes(
    split_note: str | None,
    people: Mapping[str, Person],
    marriages: Mapping[str, Marriage],
    groups: Sequence[Group],
    undated: Sequence[str],
) -> tuple[str, ...]:
    """Legend lines stating what the picture cannot show. Every one of these is a
    limit of the sources, and leaving them unsaid would make the drawing claim
    more than the records do."""
    notes: list[str] = []
    recorded = sum(1 for p in people.values() if p.has_death)
    bounded = sum(1 for p in people.values()
                  if not p.has_death and p.last_seen_at > p.birth_at)
    if bounded:
        notes.append(
            f"Только у {recorded} из {len(people)} записана дата смерти. У "
            f"остальных есть лишь нижняя граница — «умер после такого-то года», "
            "то есть последний раз, когда человека записали живым. Их линии не "
            "обрываются узлом, а угасают: кончаются записи, а не жизнь."
        )
    windows = sum(1 for p in people.values() if p.birth_is_window)
    if windows:
        notes.append(
            f"У {windows} человек год рождения — не год, а промежуток (например, "
            "«между 1855 и 1888»), выведенный из того, что в такой-то год человек "
            "уже был взрослым. Такие линии не начинаются узлом, а проявляются."
        )
    circa = sum(1 for p in people.values() if p.birth_circa and not p.birth_is_window)
    if circa:
        notes.append(
            f"{circa} {agree(circa, 'дата', 'даты', 'дат')} рождения — "
            f"{agree(circa, 'расчётная', 'расчётные', 'расчётные')} (ок.): "
            "выведены из возраста в ревизии или метрике. Такие узлы полые."
        )
    inferred = sum(1 for m in marriages.values() if m.year_inferred)
    if inferred:
        notes.append(
            f"{inferred} {agree(inferred, 'венчание', 'венчания', 'венчаний')} не "
            f"{agree(inferred, 'имеет', 'имеют', 'имеют')} записанной даты — точка "
            "схождения взята на год раньше рождения старшего ребёнка и показана "
            "пунктиром."
        )
    outside = sum(1 for m in marriages.values() if len(m.kin_partners) == 1)
    if outside:
        notes.append(
            f"{outside} {agree(outside, 'брак', 'брака', 'браков')} "
            f"{agree(outside, 'заключён', 'заключены', 'заключены')} с людьми вне "
            "круга родства — у таких венчаний одна линия, имя супруга во "
            "всплывающей подсказке."
        )
    unattached = next((g for g in groups if g.unattached), None)
    if unattached:
        count = len(unattached.members)
        notes.append(
            f"{count} {agree(count, 'человек', 'человека', 'человек')} наши записи "
            "не связывают ни с кем из остальных — они собраны в нижнюю полосу."
        )
    if len(groups) > 1 and split_note:
        notes.append(split_note)
    if undated:
        count = len(undated)
        notes.append(
            f"{count} {agree(count, 'человек', 'человека', 'человек')} без года "
            "рождения не "
            f"{agree(count, 'показан', 'показаны', 'показаны')}: поместить их на "
            "ось времени было бы догадкой."
        )
    return tuple(notes)


def unions_by_person_names(
    index: Mapping[str, list[tuple[int, str]]], res_name: str,
) -> list[str]:
    return [u for _, u in sorted(index.get(res_name, []))]


def _last_seen(
    birth_at: float,
    birth_uncertain_to: float | None,
    profile: GeniProfile,
    death_at: float | None,
    marriages: Sequence[Marriage],
) -> float:
    """The latest moment the records can show this person alive.

    A recorded death is the answer. Otherwise it is the largest of: the far edge
    of the birth window, the death BOUND's year (`умер после X` means alive at X),
    and the last marriage they appear in. Past that point the thread fades —
    the sources stop, and the drawing says so instead of running the person on
    to the edge of the canvas or killing them off at a bound.
    """
    if death_at is not None:
        return death_at
    candidates = [birth_at]
    if birth_uncertain_to is not None:
        candidates.append(birth_uncertain_to)
    bound = _at(profile.death)
    if bound is not None:
        candidates.append(bound)
    bound_end = _end_at(profile.death)
    if bound_end is not None:
        candidates.append(bound_end)
    candidates.extend(m.at for m in marriages if m.at is not None)
    return max(candidates)


def project(
    profiles: Mapping[str, GeniProfile],
    unions: Mapping[str, GeniUnion],
    kin: Mapping[str, object] | Sequence[str],
    *,
    village: str,
    parent_overrides: Mapping[str, tuple[str, ...]] | None = None,
    history: History = NO_HISTORY,
) -> Timeline:
    """Build the timeline for `village` from the consolidated domain model.

    `kin` is the curated registry — a mapping (its keys are used) or a sequence
    of canonical res_names. Raises `KinResolutionError` if any name is unknown,
    so a stale registry entry fails loudly instead of quietly shrinking the tree.
    """
    kin_names = frozenset(kin.keys() if isinstance(kin, Mapping) else kin)
    missing = sorted(name for name in kin_names if name not in profiles)
    if missing:
        raise KinResolutionError(missing)

    marriages = _build_marriages(unions, profiles, kin_names)
    parent_union, parents = _parent_links(
        marriages, kin_names, parent_overrides or {},
    )
    unions_by_person: dict[str, list[tuple[int, str]]] = {}
    for res_name in sorted(marriages):
        marriage = marriages[res_name]
        for partner in marriage.kin_partners:
            # Undated unions sort last; they cannot be placed among the dated ones.
            unions_by_person.setdefault(partner, []).append(
                (marriage.year if marriage.year is not None else 9999, res_name),
            )

    people: dict[str, Person] = {}
    undated: list[str] = []
    for res_name in sorted(kin_names):
        profile = profiles[res_name]
        birth_year = _year(profile.birth)
        if birth_year is None:
            undated.append(res_name)
            continue
        birth_at = _at(profile.birth) or float(birth_year)
        # A `between` birth is a window, not a date: the thread fades in across it.
        birth_uncertain_to = _end_at(profile.birth) if _is_bound(profile.birth) else None
        if birth_uncertain_to is not None and birth_uncertain_to <= birth_at:
            birth_uncertain_to = None

        # A ranged death is a BOUND — «умер после 1866» — so it yields no death,
        # only the last year the records can show the person alive.
        death_is_recorded = profile.death is not None and not _is_bound(profile.death)
        death_at = _at(profile.death) if death_is_recorded else None
        death_year = _year(profile.death) if death_is_recorded else None

        last_seen_at = _last_seen(
            birth_at, birth_uncertain_to, profile, death_at,
            [marriages[u] for u in unions_by_person_names(unions_by_person, res_name)
             if u in marriages],
        )
        people[res_name] = Person(
            res_name=res_name,
            name=display_name(profile),
            gender=profile.gender,
            birth_year=birth_year,
            birth_at=birth_at,
            birth_uncertain_to=birth_uncertain_to,
            birth_circa=_is_circa(profile.birth),
            death_year=death_year,
            death_at=death_at,
            last_seen_year=int(last_seen_at),
            last_seen_at=last_seen_at,
            birth_place=_place(profile.birth),
            death_place=_place(profile.death),
            parents=tuple(p for p in parents.get(res_name, ()) if p in kin_names),
            parent_union=parent_union.get(res_name),
            unions=tuple(u for _, u in sorted(unions_by_person.get(res_name, []))),
        )

    # Drop links pointing at someone excluded for want of a birth year, so no
    # part of the model references a person the picture does not contain.
    if undated:
        dropped = set(undated)
        people = {
            res: replace(
                person,
                parents=tuple(p for p in person.parents if p not in dropped),
            )
            for res, person in people.items()
        }
        marriages = {
            res: replace(
                m,
                kin_partners=tuple(p for p in m.kin_partners if p not in dropped),
                children=tuple(c for c in m.children if c not in dropped),
            )
            for res, m in marriages.items()
        }
        marriages = {res: m for res, m in marriages.items() if m.kin_partners}

    groups = _groups(people, marriages)
    timeline = Timeline(
        village=village,
        people=people,
        marriages=marriages,
        groups=groups,
        bands=(),
        notes=(),
    )
    return Timeline(
        village=village,
        people=people,
        marriages=marriages,
        groups=groups,
        bands=bands_for(
            history,
            first_year=timeline.first_year,
            last_year=timeline.last_year,
        ),
        notes=_notes(history.split_note, people, marriages, groups, undated),
    )
