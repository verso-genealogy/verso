"""How a check reads what a generated profile or union ASSERTS.

Six functions, all pure, and the only place in `verso.ru.consolidation` that knows
how a `GeniProfile`'s dates are to be read. That matters most for the birth:
a birth event here is usually an interval, not a day, and the two ends answer
different questions — `birth_year` is the earliest the person can have been
born and `birth_year_latest` the latest. A check that reaches for `.year`
instead picks one of them by accident, and a `range="before"` bound picks the
wrong one, which is how an age test fabricates findings.

It exists as a module because the alternative was worse. `age_conflicts.py`
had grown into the shared one — `birth_year`, `birth_year_latest`,
`birth_is_approximate`, `_display_name` and `_partner_refs` all lived there
while `union_duplicates.py` and `name_variants.py` imported them, and
`death_year` lived in `union_duplicates.py` while `name_variants.py` imported
THAT. Two neighbours importing a check's private helpers is a check that has
become a library without saying so, and it means moving either one breaks the
other two. Naming the shared part makes the next move a move rather than a
rescue.

`display_name` and `partner_refs` lose the leading underscore they carried
while pretending to be private: a name imported by two other modules is public,
and spelling it so is the point of this file.

Deliberately NOT here: `estate_conflicts._display_name`. It looks like a
duplicate and is not one. On a man with a surname the two agree, which is what
makes the resemblance convincing, and they part on two shapes this corpus is
full of: an unmarried woman, because `full_name` reads `last_name` OR
`birth_last_name` while that one reads only `last_name` and drops her maiden
surname; and a nameless stub, which it renders «?» where this one gives the
res_name a reader can find in the tree. Folding them would change a committed
report, and this module is a move with no behaviour in it.
`tests/test_profile_reading.py` pins both divergences and guards, by AST, that
no other check grows its own copy back.
"""
from __future__ import annotations

from verso.core.targets.geni.profile import GeniProfile


def birth_year(profile: GeniProfile) -> int | None:
    """The profile's EARLIEST possible birth year (range start), or None when no
    dated birth event exists.

    A `range="before"` bound has no lower end at all — its `year` is the LATEST
    possible birth, not the earliest (see the parent-birth estimate in
    `verso.ru.targets.geni.translator.birth_estimates`). Reading it as a range start
    would understate the parent's age and fabricate findings, so return None and
    let the caller skip the profile."""
    birth = getattr(profile, "birth", None)
    if birth is None or getattr(birth, "date", None) is None:
        return None
    if birth.date.date_range == "before":
        return None
    return birth.date.year


def birth_year_latest(profile: GeniProfile) -> int | None:
    """The profile's LATEST possible birth year: a circa RANGE's `end_year`,
    else the single year. Used for the charitable end of the age test so a wide
    'birth unknown' range (e.g. 1836–1890) does not fabricate an extreme age."""
    birth = getattr(profile, "birth", None)
    if birth is None or getattr(birth, "date", None) is None:
        return None
    return birth.date.end_year or birth.date.year


def birth_is_approximate(profile: GeniProfile) -> bool:
    """True when the birth date is circa or a range (soft year)."""
    birth = getattr(profile, "birth", None)
    if birth is None or getattr(birth, "date", None) is None:
        return False
    d = birth.date
    return bool(d.circa or d.end_year or d.date_range)


def death_year(profile: GeniProfile) -> int | None:
    """The profile's death year, or None when no dated death event exists."""
    death = getattr(profile, "death", None)
    if death is None or getattr(death, "date", None) is None:
        return None
    return death.date.year


def display_name(profile: GeniProfile) -> str:
    """What a report calls this profile: the rendered name, else the res_name.

    The res_name fallback is deliberate — a finding a reader cannot locate in
    the tree is a finding they cannot act on.
    """
    return getattr(profile, "full_name", "") or profile.res_name


def partner_refs(union: object) -> list[str]:
    """The union's partner refs, in slot order, skipping the empty slot.

    A single-partner union is ordinary here rather than malformed: a mother
    recorded without her husband is one, and so is every implied-parent stub.
    """
    refs: list[str] = []
    for attr in ("partner_1", "partner_2"):
        ref = getattr(union, attr, None)
        if ref:
            refs.append(ref)
    return refs
