"""A burial's stated age against the birth of the same child — `death-age-check`.

The predicates the comparison is handed and the slack it allows. The comparison
itself is `verso.ru.facts.rules.stated_age`, which names none of them; the report
is `verso.ru.consolidation.death_age`, which reads the entries and draws it.
"""
from __future__ import annotations

from verso.ru.ages import age_bounds
from verso.ru.facts.identity import kin_identity, kin_matches
from verso.ru.facts.model import (
    AgedYears, AssertionSet, BornOn, KinOf, ParentOf, Relational)
from verso.ru.facts.rules.stated_age import Disagreement, disagreements

# A finding has to survive BOTH an absolute floor and a fraction of the stated
# age. The floor is three months, and it is set by the sources rather than by
# taste: «полгода» and «6 мес» are what a Горюхино clerk writes for ANY infant
# under a year — the corpus holds dozens of them at 280–300 days — so anything
# tighter reports the parish's own idiom as an error.
DEFAULT_TOLERANCE_DAYS = 90.0
DEFAULT_TOLERANCE_FRACTION = 0.20

# Beyond this ratio between elapsed time and the stated age, the two records
# describe two people rather than one badly-read number.
NAMESAKE_RATIO = 12.0


#: The kinships through which a stated age is set against a birth: the
#: deceased's PARENT, the only kin a birth record names. A spouse is not one —
#: a wife's burial names her husband, who is the father in their daughter's
#: birth — and a foster parent is by definition not one. `KinOf` stays because
#: an entry naming kin without saying which lands there too, and some of those
#: are fathers; a `KinOf` whose word the source DID write (свекор, зять,
#: мачеха) names someone who is not a parent, and `stated_age_findings` leaves
#: it out. That is `death_age.PARENT_RELATIONSHIPS` exactly.
STATED_AGE_LINKS: tuple[type[Relational], ...] = (ParentOf, KinOf)


def stated_age_findings(facts: AssertionSet, *,
                        tolerance_days: float = DEFAULT_TOLERANCE_DAYS,
                        tolerance_fraction: float = DEFAULT_TOLERANCE_FRACTION,
                        ) -> list[Disagreement]:
    """The rule, handed the predicates this check compares.

    An age its author has answered as a namesake's is left out of the
    comparison, and nowhere else: it is right, so `believed()` keeps it for
    every other reader, and it is not this christening's, so it is not handed
    to the one rule that would measure it from there. The same contract
    `death_age` keeps — the rule itself never learns the note exists.
    """
    compared = AssertionSet(
        a for a in facts.believed()
        if not (isinstance(a, AgedYears) and a.namesake)
        and not (isinstance(a, KinOf) and a.term))
    return disagreements(
        compared, origin=BornOn, quantity=AgedYears,
        links=STATED_AGE_LINKS,
        identity=kin_identity(), bounds=age_bounds, matches=kin_matches,
        tolerance_days=tolerance_days, tolerance_fraction=tolerance_fraction,
        namesake_ratio=NAMESAKE_RATIO)
