"""The checks: which predicates a question compares, and how far apart is too far.

Between `rules/` and the reports. A rule takes its predicates as TYPE
PARAMETERS and may not name one; a check names them — `BornOn` against
`AgedYears`, `Titled` against `Titled` — and holds the measured tolerances that
say what «cannot both be true» means for one kind of claim: a circa year read
±2, a birth gap wider than max(2 years, 20 %), an old age made older by up to
30 %. No I/O and no translation: identity arrives as a parameter, and what a
report prints is the CLI's or the consolidation module's.

    dates        records of one person dated out of order   (`date-order`)
    births       two birth claims one life cannot hold       (`birth-claims`)
    stated_age   a burial's age against the birth            (`verso death-age`)
    lives        households, baptisms, deaths, signs of life  (`union-dups`)
    estates      two сословия held by one canonical          (`estate-conflicts`)
    reach        how far the appearance→canonical bridge reaches (`identity`)
    reconcile    who a list entry or an external card is      (`reconcile`)
    name_days    a newborn's name no saint near the birth supports (`name-days`)
    wedding_calendar  a wedding on a day the Church did not marry (`wedding-calendar`)
    lags         too long from birth to christening, death to burial (`baptism-lag`, `burial-lag`)
    parenthood   a child after the parent's death; a mother's children too far apart
                 (`posthumous-birth`, `children-span`)
    wedding_ages under the age of marriage; spouses far apart     (`wedding-ages`)

A check may also ask the Church's calendar (`verso.ru.church_calendar`): Julian
day arithmetic and the paschalion directly, the святцы as a table the CLI
loads and hands in — a check still reads no file.

`tests/test_facts_layering.py` holds the budget.
"""

#: Every check `verso facts --check` asks, in the order its help lists them.
FACTS_CHECKS: tuple[str, ...] = (
    "identity", "date-order", "birth-claims", "father-claims", "death-claims", "name-days", "wedding-calendar",
    "baptism-lag", "burial-lag", "posthumous-birth", "children-span", "wedding-ages")
