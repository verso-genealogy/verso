"""Russian revision-census (ревизская сказка) year lookup — a LEAF module.

Deliberately dependency-free (stdlib only, no geni imports): it is shared by
the Terraform translator (`verso.ru.targets.geni.translator.census_resolvers`) AND
the DSL linters (`verso.ru.linters.checks.census_age`), and the linters must stay
importable by a bare `python3` with no venv packages — the IDE plugins
(vscode-dsllint, intellij-dsllint) shell out to `dsllint.py` that way, and a
transitive third-party import (e.g. the translator package's dateutil)
crashes the whole linter run, silently blanking every warning in
the editor.

A census member whose prev-revision age is known (either via the typed
`previous_age` kwarg or via a `прошлая РС: X лет` comment marker) has their
birth year computed as `prev_revision_year - prev_age`, matching legacy's
precomputed `Год рождения (расчётный)` CSV column. Keys cover every census
year this project uses; non-revision census years (e.g. 1815) map to the
preceding standard revision whose prev_age column they would have re-surveyed.

One table, the revision chain: which revision a roll's previous-age column
counts from — `PREVIOUS_AGE_REVISION_YEAR`, checked against the ages themselves in
every book the corpus holds; the linters, the facts layer and the translator read it.
Until 0.1.0 the translator read a second table, frozen for live Geni profiles, whose
three differences from the chain were the corpus's, not history's: 1815 → 1795 (the
legacy CSV's value, Горюхино 58-9-832), and no entry for 1721 (Горюхино) nor for
1857 (Нижняя Яичница, an applied village — 17 live circa-birth estimates would flip from
`1857 - age` to `1850 - prev_age`). They live in those villages' village.toml now
(`[census] prev_revision`), and `prev_revision_year` takes them as overrides.

None of this is `census_records(prev_revision_year=)`. That kwarg is a GATE — «this
roll has a known prior revision», read for birth-location inference and only
for whether it is set — and real files contradict each other on its value.
"""
from collections.abc import Mapping
from types import MappingProxyType

# Which revision a roll of a given year counts its previous-age column from. 1815 is
# the 7th revision as 1816 is (its file's differences all equal 4: 1811), 1857 the
# 10th as 1858 is, 1721 the 1st as 1719 is.
PREVIOUS_AGE_REVISION_YEAR: dict[int, int] = {
    1721: 1719,
    1745: 1719,
    1762: 1745,
    1795: 1782,
    1811: 1795,
    1815: 1811,
    1816: 1811,
    1834: 1816,
    1850: 1834,
    1857: 1850,
    1858: 1850,
}

_NO_OVERRIDES: Mapping[int, int | None] = MappingProxyType({})


def prev_revision_year(census_year: int, overrides: Mapping[int, int | None] = _NO_OVERRIDES) -> int | None:
    """The revision a roll of `census_year` counts its previous ages from: the
    village's override when it states one (None — date by nothing), else the chain."""
    if census_year in overrides:
        return overrides[census_year]
    return PREVIOUS_AGE_REVISION_YEAR.get(census_year)
