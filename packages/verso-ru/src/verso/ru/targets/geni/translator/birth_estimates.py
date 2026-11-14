"""Synthetic birth-date estimates for people whose own birth is never recorded.

Metric-book records name plenty of adults — godparents, wedding witnesses,
parents — whose birth the book never states. Emitting a *bounded* circa birth
for them is what lets Geni match the per-record stub against the canonical
profile, and what lets `_pick_best_date` collapse the estimate once a real date
arrives from a census or death record.

Two shapes live here:

* `adult_birth_window()` — "this person was an adult at the record date", the
  role-based window already used for godparents, witnesses, and age-less
  marriage partners.
* `parent_birth_estimate()` — "this person was a parent of someone born in year
  A", a strictly tighter constraint anchored on the CHILD rather than on the
  record year.

The parent bounds are deliberately inside the plausibility limits enforced by
`verso.ru.consolidation.age_conflicts` (FATHER_MAX=70, MOTHER_MAX=50, MIN=12), so an
estimate can never by itself produce an age-conflict finding.
"""
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent

# Widest look-back for a role-based adult window. Every existing call site
# (godparent, witness, age-less marriage partner) used this same 60.
ADULT_WINDOW_MAX = 60

# A father was at most this old at his child's birth; a mother at most this.
FATHER_MAX_AGE_AT_BIRTH = 60
MOTHER_MAX_AGE_AT_BIRTH = 50
# ...and either parent at least this old.
PARENT_MIN_AGE_AT_BIRTH = 15


def adult_birth_window(record_year, min_age: int, *,
                       max_age: int = ADULT_WINDOW_MAX) -> GeniEvent:
    """`between [record_year - max_age, record_year - min_age]`, circa on both ends.

    The "must have been an adult at the record date" estimate. `min_age` varies
    by role: a godparent may be a child of 6, a wedding witness is 17+, a
    marrying partner 13+.

    Marked `synthetic` like `parent_birth_estimate`: this window is DERIVED from
    a role assumption, not read off a record, and it is the loosest thing we
    emit — the godparent shape spans 54 years. Leaving it unflagged made
    `_merge_event` prefer it wholesale over the far tighter parent estimate
    (which IS flagged), so folding a godparent record into a cluster of parent
    records widened the birth range instead of narrowing it. Flagged, the two
    estimates meet in `_pick_best_date`, whose branch 7 intersects overlapping
    between-ranges. A real date still wins over either: the flag only decides
    estimate-vs-estimate.
    """
    year = int(record_year)
    return GeniEvent(
        date=GeniDate(
            year=year - max_age, end_year=year - min_age,
            circa=True, end_circa=True,
            date_range="between",
            synthetic=True,
        ),
    )


def parent_birth_estimate(anchor_year, gender, *, record_year) -> GeniEvent | None:
    """Birth estimate for the parent of a person born circa `anchor_year`.

    With an anchor: `between [anchor - max, anchor - PARENT_MIN_AGE_AT_BIRTH]`,
    where `max` is 60 for a father and 50 for a mother.

    Without one (`anchor_year is None` — the record states no age for the child,
    common in early metric books): only the upper bound, `before record_year -
    PARENT_MIN_AGE_AT_BIRTH`. A flat `between` window off the record year would
    assert a LOWER bound that is simply false whenever the child was old — the
    father of an 80-year-old was born ~95 years before the record, not 60.

    Returns None when neither anchor nor record year is usable.
    """
    max_age = (MOTHER_MAX_AGE_AT_BIRTH if gender == Gender.FEMALE
               else FATHER_MAX_AGE_AT_BIRTH)
    if anchor_year is not None:
        anchor = int(anchor_year)
        return GeniEvent(
            date=GeniDate(
                year=anchor - max_age,
                end_year=anchor - PARENT_MIN_AGE_AT_BIRTH,
                circa=True, end_circa=True,
                date_range="between",
                synthetic=True,
            ),
        )
    if record_year is None:
        return None
    return GeniEvent(
        date=GeniDate(
            year=int(record_year) - PARENT_MIN_AGE_AT_BIRTH,
            circa=True, date_range="before",
            synthetic=True,
        ),
    )


# Relationships for which `parent_birth_estimate` is the right rule, mapped to
# the gender that picks the max-age bound. Spouses, children and in-laws are
# deliberately excluded: for a SON/DAUGHTER the constraint runs the other way,
# and for a spouse or in-law there is no generational offset to anchor on.
# (`verso.ru.relationship.gender_from_relationship` covers only FATHER/MOTHER of
# these six, so it can't stand in for this map.)
PARENT_RELATIONSHIP_GENDER = {
    Relationship.FATHER: Gender.MALE,
    Relationship.FOSTER_FATHER: Gender.MALE,
    Relationship.STEP_FATHER: Gender.MALE,
    Relationship.MOTHER: Gender.FEMALE,
    Relationship.FOSTER_MOTHER: Gender.FEMALE,
    Relationship.STEP_MOTHER: Gender.FEMALE,
}


def is_parent_relationship(relationship) -> bool:
    return relationship in PARENT_RELATIONSHIP_GENDER
