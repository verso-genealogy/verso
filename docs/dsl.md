# The DSL

**English** · [Русский](dsl.ru.md)

A DSL file is a Python module that builds record sets by calling the DSL's functions. It imports
one facade — **DSL v1** — and nothing else.

## What a file may import

- `verso.ru.dsl` — the record functions and their sets (`birth_records`, `birth`, `birth_month`,
  `marriage_records`, `death_records`, `census_records`, `household`, `member`,
  `name_list_records`, `criminal_record`, `wwi_record`, …), `person`, `page`, `book`, `relative`,
  the enums (`Gender`, `Month`, `CensusRole`, `Relationship`, `Side`, …), `NOT_IN_DOCUMENT`,
  `RecordDefaults`, and `DSL_API = 1`;
- its catalogs of constants — `verso.ru.dsl.statuses`, `verso.ru.dsl.causes_of_death`,
  `verso.ru.dsl.marital_status`;
- the corpus's own landlords' statuses, `corpus.statuses` (by the name of the workspace's corpus
  directory).

IMP001 (hard) refuses any other import — `calendar`, `os`, a module of the library. A file has
no `__main__`: `verso export-csv` writes its CSVs. The full surface, with every parameter, is
[the DSL API reference](reference/dsl-api.md).

## Writing a record

- **Names are written as the scribe wrote them** — pre-reform orthography, the patronymic in the
  book's form («Петровъ»). The modern form and the derivations are the library's.
- **What a record implies is derived**: a newborn's patronymic and surname from the father, a
  mother's surname from her husband, a child's сословие from a parent's status, an unstated
  status from the book's `RecordDefaults`. A value typed equal to its derivation is flagged by
  the linters as redundant.
- **Ages, dates and places are the record's**: a burial age is an interval («1 год» is [1, 2)
  years), a place is a key of the corpus's places, looked up verbatim.
- **A record the source contradicts is declared, not corrected**: `source_date_error=` (a
  christening dated before the birth), `source_age_error=`, `source_kin_error=`,
  `calendar_note=` — free text, never emitted, read by the checks they stand down.
- **`reviewed=False`** holds a record off Geni and out of the facts layer until read against the
  scan (see [the review ratchet](review-ratchet.md)).
- **A book of the civil registry is `civil=True`** on its record set — `birth_records`,
  `death_records`, `marriage_records` of a ZAGS book. Its entries are the same kinds with the
  same people; what differs is the second date. A birth's `k_day`/`k_month`/`k_year` and a
  death's `b_day`/`b_month` are the day of **registration**, never a christening or a burial,
  and a marriage is its registration. So the translator emits no baptism or burial event and
  titles the documents «Книга ЗАГС …» (about sections «ЗАГС …», the date «Дата регистрации»,
  printed only where a day is written); the Familio CSVs leave the christening and burial
  columns empty and put «зарегистрировано Д.М.Г» in the comment; the facts layer asserts no
  baptism or burial. Each record carries the flag as `civil` too. A parish book omits it.

`verso dsllint FILE…` runs every DSL check in one process (`--json` for tools);
`verso dsllint --fix` repairs the one mechanical finding — a `person()` call wrapped across lines —
and rewrites only when the file re-parses to an identical AST.

## What the facade promises

`packages/verso-ru/src/verso/ru/dsl/api-v1.json` is the facade's surface; `verso dsl-surface` checks it and
`verso dsl-surface --write` records a deliberate change. `DSL_API` rises only when a name goes or
is renamed: a new keyword with a default is compatible. Every writer of the DSL — the review page,
`verso migrate-statuses`, the importers — writes v1, each import sorted and wrapped at 100 columns.

## Files of an older DSL

A file written against an older DSL (DSL v0 imported the library's modules directly) says so when
it loads: «DSL v0 — verso upgrade-dsl FILE». `verso upgrade-dsl FILE…` (or `--village V`) rewrites
its imports and drops its `__main__`, and nothing else; `--check` writes nothing and fails when a
file would change. It refuses rather than guesses — a comment inside the imports, an import with
`as`, a name no catalog holds — and checks itself: every record's review fingerprint and the
module's AST outside its head stay as they were.
