<!-- Written by tools/reference.py from the code — do not edit; `make reference`. -->

# Checks

`verso facts --village V --check CHECK` asks one check of a village's reviewed records and exits 1 on a finding (`identity`, on a broken invariant); a finding a record's note stands down is counted apart and is none. A check one record answers alone is also asked of one record by `verso.ru.pipeline.signals.signals_on_json` (see records JSON); the field named stands a finding down. The guide is [the checks](../checks.md).


## `verso facts --check`

| Check | One record | Stood down by |
|---|---|---|
| `identity` | — | — |
| `date-order` | inside one entry | `source_date_error=` |
| `birth-claims` | — | — |
| `father-claims` | — | — |
| `death-claims` | — | — |
| `name-days` | yes | `calendar_note=` |
| `wedding-calendar` | yes | `calendar_note=` |
| `baptism-lag` | yes | `lag_note=` |
| `burial-lag` | yes | `lag_note=` |
| `posthumous-birth` | — | — |
| `children-span` | — | — |
| `wedding-ages` | yes | `age_note=` |
| `parent-ages` | yes | `source_age_error=` |
| `parent-age-drift` | — | — |
| `household-ages` | a household, with its roll | `source_age_error=` |

## Thresholds

Each a number a check holds, as Python prints it, with the first sentence of its comment in the code.

| Module | Name | Value | What it is |
|---|---|---|---|
| `verso.ru.facts.checks.births` | `BIRTH_SLACK_YEARS` | `2.0` | How far two birth claims of one person may sit apart before they cannot both be true: two years, or a fifth of the older stated age, whichever is wider. |
| `verso.ru.facts.checks.dates` | `CIRCA_SLACK_YEARS` | `2` | How far a circa year may sit from the truth, in years. |
| `verso.ru.facts.checks.deaths` | `NEAR_SLACK_DAYS` | `365` | How far past the told-year slack a gap stays LOW — see the module docstring. |
| `verso.ru.facts.checks.lags` | `BURIAL_DAYS` | `3` | A burial more than this many days after the death is a finding … |
| `verso.ru.facts.checks.lags` | `BURIAL_HIGH_DAYS` | `9` | … and HIGH past this many. |
| `verso.ru.facts.checks.lags` | `BAPTISM_DAYS` | `11` | A christening more than this many days after the birth is a finding. |
| `verso.ru.facts.checks.name_days` | `BEFORE` | `3` | Days before the birth a saint may be kept and still have named the child. |
| `verso.ru.facts.checks.name_days` | `AFTER` | `3` | Days past the later of the christening and the eighth day. |
| `verso.ru.facts.checks.name_days` | `NAMING_DAY` | `7` | The eighth day: a child born on day 0 was named on day 7. |
| `verso.ru.facts.checks.name_days` | `FAR_DAYS` | `30` | A finding lies more than this many days outside the window — where the real misses run at a tenth of what random days produce. |
| `verso.ru.facts.checks.name_days` | `LOOKALIKE_RATIO` | `0.7` | How alike a name kept in the window must look to be offered as a reading. |
| `verso.ru.facts.checks.neighbours` | `NEIGHBOUR_SPAN` | `4` | How far apart two entries of one list may be numbered and still be read as one household. |
| `verso.ru.facts.checks.neighbours` | `SPOUSE_MAX_GAP` | `20` | The most years apart the ages of two entries of one household may be and still be spouses. |
| `verso.ru.facts.checks.neighbours` | `PARENT_MIN_GAP` | `14` | The least years a parent among the entries of one household is older than a child. |
| `verso.ru.facts.checks.parent_ages` | `DRIFT_SLACK_YEARS` | `2.0` | Two acts of one couple state ages whose birth intervals lie further apart than this: the same pair of lives cannot have both. |
| `verso.ru.facts.checks.parenthood` | `FATHER_DAYS` | `294` | How long after the father's death a child may still be his: 294 days, the posthumous-birth limit Gramps uses. |
| `verso.ru.facts.checks.parenthood` | `MOTHER_SPAN_YEARS` | `28.0` | A mother's children born further apart than this are two mothers. |
| `verso.ru.facts.checks.parenthood` | `MOTHER_SPAN_HIGH_YEARS` | `30.0` | … and past this, no reading of the dates saves the fold. |
| `verso.ru.facts.checks.stated_age` | `DEFAULT_TOLERANCE_DAYS` | `90.0` | A burial's age may miss the birth by this many days and be no finding: the floor is three months, set by the sources rather than by taste — «полгода» and «6 мес» are what a Горюхино clerk writes for ANY infant under a year, and the corpus holds dozens of them at 280–300 days, so anything tighter reports the parish's own idiom as an error. |
| `verso.ru.facts.checks.stated_age` | `DEFAULT_TOLERANCE_FRACTION` | `0.2` | … nor by this share of the stated age: a finding has to survive both. |
| `verso.ru.facts.checks.stated_age` | `NAMESAKE_RATIO` | `12.0` | Beyond this ratio between elapsed time and the stated age, the two records describe two people rather than one badly-read number. |
| `verso.ru.facts.checks.wedding_ages` | `MINIMUM_AGES` | `(((1830, 7, 19), 18, 16), ((1774, 12, 17), 15, 13))` | (from this date, groom, bride) — the minimum age of marriage in force. |
| `verso.ru.facts.checks.wedding_ages` | `DISPENSATION_YEARS` | `0.5` | How far short of the minimum the books go by custom. |
| `verso.ru.facts.checks.wedding_ages` | `GAP_YEARS` | `20.0` | Spouses further apart than this are a finding. |
| `verso.ru.facts.checks.wedding_calendar` | `LAST_YEAR` | `1917` | The last year of the Julian church books this check reads. |
| `verso.ru.consolidation.age_conflicts` | `MOTHER_MAX_DEFAULT` | `50` | A mother older than this at a child's birth is flagged as implausibly old (`--mother-max`). |
| `verso.ru.consolidation.age_conflicts` | `FATHER_MAX_DEFAULT` | `70` | A father older than this at a child's birth is flagged as implausibly old (`--father-max`). |
| `verso.ru.consolidation.age_conflicts` | `MOTHER_MIN_DEFAULT` | `12` | A mother younger than this at a child's birth is flagged as implausibly young (Geni's «Ребёнок родился в слишком раннем возрасте»). |
| `verso.ru.consolidation.age_conflicts` | `FATHER_MIN_DEFAULT` | `12` | A father younger than this at a child's birth is flagged as implausibly young (`--father-min`). |
| `verso.ru.consolidation.death_age` | `UNIT_RATIO_TOLERANCE` | `0.25` | How near the ratio of the time lived to the stated age must come to twelve (or to a twelfth), as a share of it, for a finding to be called an age read in the wrong unit. |
| `verso.ru.consolidation.sibling_spacing` | `DEFAULT_MIN_GAP_DAYS` | `270` | Shortest interval between two live births to one mother that the records can mean literally. |
| `verso.ru.consolidation.sibling_spacing` | `TWIN_DAYS` | `2` | Two children entered on the same day (or a day apart) are twins — the books record them as consecutive numbers, and the corpus holds several pairs. |
