# The rules of a record

**English** · [Русский](writing-records.ru.md)

What the library itself holds a DSL file to, whoever reads the scan. A corpus adds its own rules on
top — its landlords' statuses, its estates, the surnames of its villages — and says where they are in
its AGENTS.md; an agent that finds none there writes by these. The calls and their parameters are in
[the DSL](dsl.md) and [the DSL API](reference/dsl-api.md); the examples here are invented.

## The record says what it says

- **Names as the scribe wrote them**: pre-reform orthography (ѣ, і, ѳ, ъ), nominative case. The modern
  form is derived; a name typed modern is a name the record does not hold.
- **The patronymic in the book's own form** — «Петровъ», «Ѳомина». Write «Петровичъ» only where the book
  writes it (the civil registry's books do). An entry that writes no patronymic gets `None` in its place,
  not one recovered from another record.
- **The surname is the third positional argument** of `person()`; `last_name_orig=` only when a slot
  before it is empty (`person("?", last_name_orig="Коровкина")`).
- **Kinship is what this entry states.** `father=`, `mother=`, a `relative(…, Relationship.FATHER)` name a
  person the entry names. What another record tells you — a father's patronymic, a mother's maiden name —
  goes into that person's `comment=`, with the record it came from; the people are joined later, by the
  corpus's consolidation, where it is a claim with its evidence.
- **What the record implies is not typed.** A newborn's patronymic and surname come from the father, a
  wife's surname from her husband, a status from the book's `RecordDefaults`; a value typed equal to its
  derivation is a finding (BRD, CRD, VSR).

## Doubt goes into a comment

- `"?"` is a word that does not read; `"Ва?"` keeps the letters that do.
- `"Агрипина?"` — a whole word with «?» after it — is a word settled from the context (the names
  lexicon, a lint finding, the neighbouring years), not plainly from the scan: «check on the scan».
- Two readings are both named in the record's `comment=`; the name field holds the one you would bet on,
  with its «?».
- A person whose name does not read stays in the record as `person("?")`: a person left out never
  reaches the tree, and nobody reads a comment about them.
- A lint finding on a name you have just read is first a question about the reading: crop the word again
  at 4–5×. Do not add a row to the names layer to clear it unless the scan plainly shows that form.

## Ages and dates

- **An age is a number of years or a string of units**: `age=60`, `age="2 мес"`, `age="1 г 6 мес"`,
  `age="3 нед"`, `age="4 дн"`; an idiom («полгода») passes as written. A whole number of years is an
  integer, not `"60 лет"` (AGE001); a form the parser does not know is AGE002. An age is an interval:
  «1 год» is [1, 2) years.
- **The unit of a bare number is the дело's convention**, and it can change between the years of one
  дело. A child born and buried inside one book proves it; `verso death-age` and `verso sibling-spacing`
  find an age read in the wrong unit.
- **Dates are the book's**: the day and month as written, by the calendar the book used — the Julian
  (old style) until February 1918. Never convert them: the святцы and the paschalion the checks ask are
  Julian.
- **A christening the next month**: when its day is smaller than the birth's, `birth()` takes it as the
  next month; a christening in the next year needs `k_year=`.
- **Part 1 of a metric book runs two series of numbers**, boys and girls («Мужескаго пола | Женскаго
  пола»), so «№ 4» is in a year twice: the pair `(number, Gender)` says which.

## What the source contradicts, and what only looks wrong

A record keeps what the source says. Where the source is wrong, the record declares it; where a value is
right and only looks wrong, the record notes it. Free text; never published; read by the checks it
answers.

| Field | Of | When | What it does |
|---|---|---|---|
| `source_date_error=` | `birth()`, `death()` | a christening dated before the birth, a burial before the death | withdraws that date |
| `source_age_error=` | `death()`, `member()` | a stated age the source got wrong | withdraws the age |
| `previous_age_error=` | `member()` | the previous revision's age the roll carried over wrong | withdraws that figure alone |
| `source_kin_error=` | `marriage()` | the entry's kinship contradicts itself | stands down the father check on it |
| `namesake=` | `death()` | a burial whose age is right but belongs to another child of that name | stands down `death-age` |
| `calendar_note=` | `birth()`, `christening()`, `marriage()` | a name out of the calendar, a wedding in a fast — so in the book | notes it; the value stays believed |
| `lag_note=` | `birth()`, `death()` | a christening or a burial long after — so in the book | notes it |
| `age_note=` | `marriage()` | the ages at a wedding — so in the book | notes it |

A field on a call that does not take it fails the file's build (`verso export-csv`).

## Not yet read against the scan: `reviewed=False`

Everything read from a scan and not yet read back against it by a person is `reviewed=False` — on the
record, on the `page()` around it, or on the whole record set; the innermost says. It keeps the record off
Geni and out of the facts layer until it is reviewed — and so out of the checks: of the commands, only
`verso stale-claims` reads it; the signals of one record (`signals_on_json`, [records JSON](records-json.md))
read it too. See [the review ratchet](review-ratchet.md).

## Books of the civil registry

A book of the civil registry (ЗАГС) is `civil=True` on its record set. It is a book per kind of record,
not three parts of one; its second date is the day of registration (`k_day` of a birth, `b_day` of a
death), never a christening or a burial. See [the DSL](dsl.md).

## An example

```python
from verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_month, birth_records, page, person
from verso.ru.dsl.statuses import STATE_PEASANT_FEMALE, STATE_PEASANT_LEGAL_WIFE, STATE_PEASANT_MALE

stepanchikovo_births_1852 = birth_records(
    "ГА", "1", "2", "5", "Степанчиково", "Степанчиковская", 1852,
    *page("7об",
          *birth_month(Month.MARCH,
                       birth(4, Gender.MALE, 2, 3,
                             child=person("Ѳеодоръ"),
                             father=person("Петръ", "Степановъ", "Видоплясовъ"),
                             mother=person("Анна", "Ѳомина"),
                             god_parent1=person("Николай", "Ильинъ", "Фалалеевъ"),
                             god_parent2=person("Марія", "?", "Ежевикина")),
                       birth(4, Gender.FEMALE, 5, 7,
                             child=person("Агрипина?"),
                             father=person("Иванъ", None, "Коровкинъ", comment="отчество — по записи о его венчании: Иванъ Ѳомичъ"),
                             mother=person("Ва?"),
                             comment="имя ребёнка: «Агрипина» или «Агафія» — чернила расплылись"),
                       ),
          reviewed=False),
    defaults=RecordDefaults(residence="Степанчиково", status_male=STATE_PEASANT_MALE,
                            status_female=STATE_PEASANT_FEMALE, status_mother=STATE_PEASANT_LEGAL_WIFE),
)
```

```python
from verso.ru.dsl import Gender, Month, RecordDefaults, Relationship, death, death_month, death_records, person, relative
from verso.ru.dsl.statuses import STATE_PEASANT_FEMALE, STATE_PEASANT_MALE

stepanchikovo_deaths_1852 = death_records(
    "ГА", "1", "2", "5", "Степанчиково", "Степанчиковская", 1852,
    *death_month(Month.MAY,
                 death(1, Gender.MALE, 3, 5, deceased=person("Ѳеодоръ"), age="2 мес",
                       relatives=[relative(person("Петръ", "Степановъ", "Видоплясовъ"), Relationship.FATHER)]),
                 death(2, Gender.FEMALE, 4, 6, deceased=person("Пелагея", "Иванова", "Коровкина"), age=60),
                 death(3, Gender.MALE, 9, 21, deceased=person("Сидоръ", "Ильинъ"), age="1 г 6 мес",
                       lag_note="погребён 21-го: так в подлиннике, скан сверен")),
    defaults=RecordDefaults(residence="Степанчиково", status_male=STATE_PEASANT_MALE, status_female=STATE_PEASANT_FEMALE),
    reviewed=False,
)
```

The two births are № 4 of the boys and № 4 of the girls. The second father's patronymic is not in the
entry, so it is `None`, and what his wedding says of it is his comment.

## When a file is done

A file is handed over when:

1. `verso dsllint FILE…` reports no finding of level error. It reads the file's text: it does not import it.
2. `verso export-csv --village V --year Y` exits 0. It builds every file of the year, so a file that does
   not import — a constant its statuses module lacks, a misspelt import — fails here.
3. The checks a new year answers have been asked ([the checks](checks.md)), and each finding read again on the scan.

Two things make a check say «OK — 0 findings» about records it never read:

- **A file that does not import** is skipped by every other command with a warning — `skipping …`,
  `failed to load …` — and the checks report on what is left. Their OK means something only when every
  file loaded.
- **A record that is `reviewed=False`** is not read by the checks but `verso stale-claims` (see above): a
  year just written answers them once it is reviewed.
