# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[compatibility](docs/compatibility.md) — while 0.x, a minor version may break compatibility.

## Unreleased

### Changed

- verso-ru, the site (`verso site`): a newborn is named with a patronymic — its father's, as the library
  derives it (`verso.ru.naming.patronymics.derive_patronymic`, what the Geni translator and the CSV give the
  child), marked derived as the surname the child takes from the father — where the record of the birth or the
  christening writes none and the export derived none. A son of Петр Сидоров was «Иван Сидоров»; he is
  «Иван Петрович Сидоров». The site derives it on its own: the records JSON, the facts
  and every other output of a corpus stay as they were.
- The guide to writing records (and its translation) and the toy example: their invented surname is now
  «Обноскин» in every form — a corpus turned out to hold the old one. No output of a corpus moves.
- The plugin `verso-reading`: what a reading benchmark's error analysis found, in the agents' prompts and two
  skills. `scan-reader` and `dsl-writer` count a record's people against the scan (a strong reader's blanks are
  people and patronymics it did not see, and asking for «?» does not bring them back — measured through the API); name where
  the errors sit (sureties', fathers' and godparents' surnames, the end of a long household) and the given names
  taken for one another; `dsl-writer` checks every unflagged surname against the village's records
  (`verso find-person`, by its modern stem, never a hit in the year being written) and flags one they do not hold
  instead of replacing it; `scan-reader` takes a list of the parish's people in its brief as a reading aid, not an
  answer. `metric-books` says what a list of the village's people of the nearest years is worth to a reader and that
  two readers of one model agreeing is not a check; `census` asks a reader to count each двор against the page;
  both say that a stronger model reads better than Opus at high and how to ask for it. The sizes the skills and
  the plugin's README state are the texts' sizes again. No code, no output of a corpus moves.

### Fixed

- verso-ru: every report names an entry its book left unnumbered «без номера» — the lines of `union-dups` (households,
  baptisms, deaths, signs of life), `reconcile` (`verso reconcile`, the check under it and `verso name-variants`,
  which describes a record by it) and `estate-conflicts`,
  the noted pairs of `father-claims` and `verso facts --why` (its header, and every evidence line: `str(Citation)`
  wrote «рек. none»), which 0.1.47 left printing «№none» (or a bare «none»). A citation says its number itself,
  `Citation.number` (`verso.ru.facts.labels.record_number`), and a test holds the reports' modules and the catalogs
  to it. **A corpus's reports move** where they name an unnumbered entry: «№none» becomes «без номера».
  The catalog's `cli.facts.father.noted_pair` writes the number it is handed as it is (`{number}`, with its sign).
- verso-core: a field of several types (`OneOf`) refused a value naming no cause: the refusal now says why each type
  did not take it (`records.encode.none_of`, `records.decode.none_of`) — an `EventDate` whose month is no month's
  code is said so. A code no member of an enum has is a reason there, and the next type is tried, where it stopped
  the decoder with a `ValueError`. The decoder names a field's type as the encoder does («EventDate | str»), not by
  its `repr`. The order the vocabulary writes is the order tried, and a test holds it.
- verso-ru: DVC001 reads a text bound once to a name at the head of the file (`MARRIED = "…"`,
  `marriage_date=MARRIED`, by keyword or in its place) and says it at the act, with no quick fix; a file that
  defines, binds or imports from elsewhere than `verso.ru.dsl` its own `divorce` has no act to read.

## 0.1.47 — 2026-11-24

A corpus's CSVs and Terraform do not move. What does, and only where a corpus holds it: the records JSON of a
name-list entry or a divorce under `page(…, reviewed=True)` in a held book (see **Fixed**), and of a divorce whose
`marriage_date=` moves to an `EventDate`; dsllint's report of a divorce that writes it as text (DVC001, advisory); a
facts report's line of an unnumbered entry («без номера»); and, for a corpus with divorces, its facts reports and
`facts_findings.tsv` (see **Added**). A DSL file that still writes `marriage_date=` as text warns, and does not load
where a `DeprecationWarning` is an error (see **Deprecated**). `verso site` is new.

### Added

- verso-ru: **an act of divorce is read by the facts layer.** `verso facts` reads the divorce record sets of a
  village — from the DSL and from the records JSON, in the one walk that reads the rest — and a divorce alone
  (`signals_of`, `signals_on_json`); `verso facts --kind divorce` dumps, explains (`--why`) and counts the bases of
  its assertions. A divorce asserts that the two were spouses (`SpouseOf`), the day the marriage
  was dissolved (the new `DivorcedOn`, of each of them), each one's age that day and, where `marriage_date=` is an
  `EventDate` (see below), the wedding the act names (`MarriedOn`, cited by the divorce); a text there asserts
  nothing. Two checks read it: `date-order`
  gains «a divorce before the marriage its own act names», asked inside one entry only and said once of it, and
  `wedding-calendar` asks the church wedding an act names (1917 and before). The translator still mints no profile
  for a divorce's people: the checks that compare records do not see them, `--check identity` counts them on a
  line of their own («вид без профилей») and the snapshot's `identity-refused-beyond-clergy` leaves them out; a
  finding of theirs inside one entry is in the village's `date-order` report and in `date-order-within`.
  The people index (`verso.ru.persons.people.sightings_of`) reads no divorce, as before.
  **A corpus that holds divorces moves**: its `identity` report and, where an act names its marriage as an
  `EventDate`, its `wedding-calendar` report, its `date-order` report and
  `facts_findings.tsv` (`date-order-within`, `wedding-calendar-strict`) where an act contradicts itself or names a
  church wedding on a strict ban; the dump of each other kind does not move (`--kind divorce --dump` is new). A day
  or a month the DSL holds as words is not recorded, as an empty column is: a divorce never stops a village's reading.
  An older release, or a reader validating against an older `records-v1.json`, refuses a divorce that writes
  `source_date_error` or `calendar_note` ([records JSON](docs/records-json.md), «Compatibility»).
- verso-ru: **the marriage an act of divorce names is an `EventDate`** — `divorce(marriage_date=EventDate(1927,
  Month.FEBRUARY, 24))`, the library's one structure of a date (a point, a month, a year, `circa`, a range), as an
  external card's dates are; the facts layer reads it as it reads a card's. The familio CSV («Дата заключения брака»)
  and `village.db` write it as the corpus wrote the text — «24 февраля 1927», «февраль 1927», «1927», «около мая 1915»,
  «до 1915», «1914–1915»
  (`verso.ru.domain.event_date.written_date`, `date_text`) — so a text already in one of those forms, moved to the
  structure, writes the same CSV. `read_written_date` reads a text in those forms back, and in a few more
  («24.02.1927», «1927 г.», the months in the old spelling): DVC001's fix for such a text writes the CSV's form, so
  its row moves. An older release, or a reader validating against an older `records-v1.json`, refuses an `EventDate`
  in `marriage_date`. The interface's schema hides the field, as a card's dates —
  the review page neither shows nor edits it (it has no card for a divorce); `verso site` draws it, either form.
  `wedding-calendar` asks a single day only: a wedding named «около», «до», «после» or as a range is not asked of
  the calendar.
- verso-ru: **DVC001** (advisory): a divorce's `marriage_date=` written as text, with its `EventDate` offered as the
  quick fix where the text is a date in a known form; answered on records JSON too.
- verso-core: a field of the vocabulary may hold **one of several types** — `OneOf`, written `a|b`
  (`marriage_date:EventDate|str`): encoded by the first type that takes the value, decoded by the first that reads
  it, `anyOf` in `records-v1.json`. An export of before (a text) reads as it was written.
- verso-ru: the reports `verso facts` writes say «без номера» for an entry its book left unnumbered, where they
  printed «№none» (the header of `--why`, the noted pairs of `father-claims` and the lines of the checks `lives`
  and `reconcile` still print the bare number);
  `verso facts --kind divorce` without `--dump`, `--why` or `--basis-census` is refused, saying why (an act of
  divorce names no godparents, witnesses or parents to pair).
- DSL v1: `divorce(source_date_error=)` withdraws the date of the marriage an act of divorce names (the divorce's
  own day stays), `divorce(calendar_note=)` notes that the wedding's day is right although the Church did not marry
  on it. Both are fields of the records JSON and of the interface's schema (marked `checks`).
- verso-core: `discover_records(untranslated=)` hands out the record sets the translator does not read, from the
  same walk; `translate_village(untranslated=)` passes them on. What is yielded and fed is unchanged.
- verso-ru: `verso site --village V --out DIR` — a village's records as a static site ([a village's
  site](docs/site.md)): every book as the document it was read from, drawn record by record by the interface's
  schema (`ui-v1.json`), what the record writes told apart from what the library derived, an unread record marked;
  an index of the names that needs no JavaScript and a search that reads its own index; the settlement's prose
  (`<village>/docs/*.md`, the new extra `verso-ru[site]`: markdown-it-py) as pages. A record's address is its id
  (rule `r1`): the page of its book and its token as the anchor, the same at every build. Every link is relative
  and nothing is fetched from another host, so the site serves from GitHub Pages or a domain of its own. A new
  product: no output a corpus compares moves.
- verso-core: a `late` rule of the interface's schema may name the fields that stand it down — `stand_down` (an
  event late past its days) and `stand_down_before` (one before the first); the build refuses a path the kind lacks.
  verso-ru names them for the christening and the burial: `lag_note` and `source_date_error`, the fields the signals
  of `baptism-lag`, `burial-lag` and `date-order` name (`STAND_DOWN`). The review page says no «проверьте» where the
  record writes one (verso-app's rule `late`).
- Docs: [the rules of a record](docs/writing-records.md) — what goes into each field (names as written, the
  patronymic in the book's form or `None`, kinship only as the entry states it), where a doubt goes, ages and dates
  (Julian until 1918), what declares or notes a value the source contradicts, and when a file is done (`dsllint`
  reads the text and imports nothing; `verso export-csv` builds every file). Its examples are tested.
- Docs: [the checks](docs/checks.md) — every check over the records: the six one record answers alone, with what
  each asks and the field that answers it; those that compare records before consolidation (`death-age`,
  `sibling-spacing`, `stale-claims`, `father-claims` inside one record) and after it; what they do not read (a file
  that does not import, a record that is `reviewed=False`), their exit codes, the names their reports print, and
  a corpus's CI. The reference gains [checks](docs/reference/checks.md), written from the code: the checks of
  `verso facts --check`, which one record answers and what stands each down, and every threshold a check holds
  with its comment (`#:`). Comments only in the code: no output moves.
- verso-reading: the skills say what they cost in context (the plugin's README, «What it costs»; `metric-books` and
  `census` their own size, which a test holds to the text) and that the two tiers of reading are two scales of crop,
  not two passes of readers. «After the reading» of `metric-books` lists the checks a written year answers and the
  field that answers each, says that `dsllint` imports nothing — `verso export-csv` is the build — and that the checks
  read reviewed records only. `metric-books` gains the books of the civil registry and the two series of numbers of
  part 1; `dsl-writer` writes by the library's rules of a record when the project has none, and checks the build.
- The toy example carries a sample of a project's map, `examples/toy/AGENTS.md`: what a corpus tells the reading
  skills — its rules, statuses and places, the checks after a year. The plugin's README points a new project at it.
- Docs: [compatibility](docs/compatibility.md) says how a corpus judges a new version — every output written with
  both, compared byte for byte. [Records JSON](docs/records-json.md) says that its days are the book's (Julian until
  1918) and that `verso death-age`, `verso sibling-spacing` and `verso stale-claims` load the DSL themselves and do
  not read the export under `VERSO_RECORDS`.
- The docstrings and comments of the checks name the library's commands (`verso facts --check name-days`,
  `verso death-age`, `verso candidates --sweep`) where they named a corpus's Makefile targets (`facts-check
  check=…`, `death-age-check`, `consolidation-sweep`). The reports' own first words are unchanged: no output moves.
- verso-ru: a divorce takes the review flag. `divorce(…, reviewed=None)` and
  `divorce_records(…, reviewed=True)`: resolved innermost-first — the record, its `page(…, reviewed=)` (which
  refused a divorce until now), the book — so an unproofread divorce can be held. `Divorce.reviewed` and
  `DivorceRecords.reviewed`; the records JSON writes the flag as it writes a name list's entry's, not a birth's
  (`reviewed` on the `divorce` and `divorces` nodes of `records-v1.json`, default `True`, written nowhere when it is
  the default; a `False` where a birth's stands), and a held divorce's `review` is `held`. A divorce reaches no Geni document, so the review ratchet lists
  none; `tables(…, reviewed_only=True)` leaves a held one out, and RVR001 reads `divorce` and `divorce_records`. The
  interface's schema hides the flag on the divorce and its book, as on the other kinds.

  **The flag moves no output.** A divorce file that does not name it gives the same bytes as on 0.1.46 — its familio
  CSV, its records JSON, the Terraform (a divorce writes none), dsllint; a held divorce moves its records
  JSON alone (its `review`, its `reviewed`), its CSV row stays. A corpus that writes `reviewed=` on a divorce needs
  this version: an older one refuses the keyword, and an older decoder, or a reader validating against an older
  `records-v1.json`, refuses a divorce that writes `reviewed` (the vocabulary's version stays 1) — so the library
  and its readers move before a corpus writes the flag. Writing it as a name list's entry's (default `True`, written
  nowhere), not a birth's (always written), is what keeps an unflagged book's bytes; a `page(…, reviewed=True)` inside
  `divorce_records(…, reviewed=False)` is written as the entry's is (see **Fixed**). RVR001 on the records JSON reads
  a run's levels as the export shows them, `on_json.review_level(node, built)` — a store's `run_levels` too.
- Docs: [records JSON](docs/records-json.md#compatibility-and-reading-an-old-export) names a known limit, until
  0.2: a wrapper's field a call writes as `None` in so many words (`year=None` in a section, `reviewed=None` in a
  `page()`; not a record's leaf) is filled by the wrapper, and only `derived` holds its value, so a rebuild from
  `written` alone leaves it unset or gives it the set's value: `replay_file(…, context=False)`, `replay_record` with its
  default `context=False`, a store that keeps `written` alone, and `on_json.lint_record` and the signals of one record,
  which replay so, silently. A `book()`'s priest written as `None` loses the call's `null` in every replay. The guide's
  claims that `lint_record` gives `lint_records`'s findings, that a card agrees with `verso facts --check`, and that
  `replay_record` equals `replay_file` now name the exception. No corpus file writes the shape, nor any verso-app
  path seen; no output moves.

### Changed

- The reference: a command's or a linter's summary ends at a full stop, not at a colon — fifteen rows of
  `commands.md` and `linters.md` said only «The святцы:», «Fix:» and the like. No output moves.

### Deprecated

- verso-ru: `divorce(marriage_date=)` written as **text**. It is taken, kept and exported as written, and warns
  (`DeprecationWarning`, at the line that wrote it — or, replaying an export that holds the text, in the library;
  shown where Python shows one — a test run, `-W default`); no
  reader parses it, so the facts layer does not see the wedding it names. DVC001 says so and offers the
  `EventDate`. Refused from 0.2. A corpus that wrote the text moves its records to `EventDate`: its CSV does not
  move where the text was in the form the CSV writes, its records JSON and its facts do. **Where a `DeprecationWarning` is an error** — as
  [compatibility](docs/compatibility.md) advises a corpus's checks to run, `PYTHONWARNINGS=error::DeprecationWarning`
  — a DSL file that writes the text no longer loads, and the loader skips it with every record in it, and a replay of
  an export that holds the text (`replay_file`, the linters on JSON, a store's views) raises: move the records, and
  write the export again, in the same commit that takes this release. An empty text (`""`) is no date and does not warn.
- verso-core: `encode_record` without `record_set=`. Left out, it is `None` and warns (`DeprecationWarning`, at the
  caller's line; `warnings.deprecated` on its overload, so a type checker that reports deprecations names the call), so
  a caller written before the keyword — verso-app's rebuild of a record — keeps working and keeps the gap in the node it
  stores until it passes its set. Python shows the warning where it shows a `DeprecationWarning` (a test run,
  `-W default`), not in a server's log. Required from 0.2.

### Fixed

- Records JSON: a wrapper's value equal to its field's default is written under `written.context` when the record
  set holds another value of the field, which the set's factory would give the record otherwise. A name-list entry
  under `page(…, reviewed=True)` in a `name_list_records(…, reviewed=False)`, and a divorce under it in a
  `divorce_records(…, reviewed=False)`, left no trace of the page's flag (`true` is the default of `reviewed`):
  `decode_file` read it right, but `replay_file`, `replay_record` and so the linters on JSON and a store's views
  rebuilt it held. `on_json.review_level` worked around it for RVR001 (for a divorce and a name list's entry, the
  kind's default `True` where `written` says nothing) and is unchanged: on a node the export writes it now agrees with the replayed record, on one written without
  its set (`record_set=None`, an export of before) it still answers the default where the replay answers the set's.
  The fields a set gives its records are the vocabulary's (`Vocabulary.inherited`, verso-ru's `INHERITED`: the flag of
  every kind whose set gives one — not a card, whose set gives none), never inferred from a field's name. `encode_record` takes the set (`record_set=`): `record_set=None`
  says there is none, and the node then leaves the flag out as before (see **Deprecated**).
  An export written before keeps the gap until `verso export-records` writes it again: the bump alone fixes nothing
  a store already holds.
  **A corpus's records JSON moves** for those records alone: each gains `"reviewed": true` in its `written` and
  `"reviewed"` in its `written.context` (the kinds `listed_person` and `divorce`). Its `review` stays `reviewed`; this fix moves
  no schema, Terraform, CSV, facts report or print of the review ratchet (read from the source).

## 0.1.46 — 2026-11-20

A corpus's CSVs do not move: `verso export-csv` writes the bytes it wrote. `verso familio-spravochnik` changes
on purpose — see **Changed**; the workbook it writes is no output a corpus commits.

### Added

- verso-ru: a familio CSV as a table in memory. `verso.ru.exporters.base` gains `CsvTable` (`name`, `headers`,
  `rows`, `text_rows()` — the rows as the csv module writes and reads them back) and `write_table`;
  `verso.ru.exporters.csv_familio` gains `FamilioCsvExporter` (the four exporters' base: `table(record_set,
  records=None)`, and `export()` writing it), `exporter_of`, `tables(record_sets, parish=, years=,
  reviewed_only=)` and `merge_tables`.
- verso-ru: `verso.ru.exporters.familio_spravochnik.collect(record_sets, parish=, years=, reviewed_only=True)`
  → `Collected` (`records_by_type`, `taken`, `left_out`, `parishes`): a справочник's source rows from record
  sets, the unreviewed left out and counted. `RECORD_SET_TYPES`; `years_label_for` (moved from the command).
- verso-ru: `verso.ru.exporters.familio_layout` — the layout of Familio's МК template as data
  (`familio_mk.json`: the record sheets' titles and two header rows, the labels of `about`, the head of
  `location`; no sample value, no list and no text of Familio's file) and `build_workbook()`, an empty workbook
  of it. `FamilioTemplateWriter()` with no template path fills that workbook — and, given no `about`, still
  writes the years it covers (a template's `about` is left as it came).
- verso-ru: the `location` sheet from the records and the places — `referenced_places`, `derive_location`,
  `known_from(places)`, `location_rows(places, curated=, known=)`, `blank_places`: every place a row names
  gets a line; its type, region, district, volost and Familio link are filled where the places dictionary
  says them unambiguously, and left blank where it does not.
- verso-ru: `familio_spravochnik.about_of(data, village, from_year, to_year, years_label)` — the `about` values of a
  mapping (`read_about` is it over a JSON file), for a host that keeps them elsewhere.
- `verso familio-spravochnik --with-unreviewed`. New catalog keys `cli.familio_spravochnik.left_out`,
  `only_unreviewed`, `blank_places`, `not_imported`, `help_with_unreviewed`, `help_no_regenerate`.

### Changed

- `verso familio-spravochnik` reads the village's **records** (the DSL files, or the records export with
  `VERSO_RECORDS`), no `*_familio.csv` from the disk: the workbook no longer depends on the CSVs being fresh.
  A file of `[csv] skip` stays out; a file that does not import is refused, not skipped.
- `verso familio-spravochnik` puts in **only proofread records**: a record held back as `reviewed=False` is
  left out and counted («пропущено невычитанных: N»). `--with-unreviewed` gives the former workbook.
- `verso familio-spravochnik` needs **no template**: without `--template` it writes a workbook the library
  builds — `about`, `location` and the three record sheets, with the template's header rows and columns and
  none of its helper sheets (`INFO`, `spiski`, `Name_M`, `Ends`), dropdowns or formatting. `--template FILE`
  fills Familio's own file as before; `<corpus>/familio/Shablon_MK.xlsx` is no longer read by default.
- The `location` sheet lists every place the rows name: the curated `location.csv` first, as it is, then the
  places it lacks, from the workspace's places. A lookup no longer answers `#N/A` for a place the CSV forgot.
- A value of a record, of `about.json` or of `location.csv` that begins with `=` is written as text, never as
  a formula.
- Two record sets of one parish, year and kind — two дела of a year — both go in; read from the CSVs, the
  second file's CSV had overwritten the first's.
- With `--template` and no curated `location.csv` the template's sample `location` rows are replaced by the
  places the rows name (they were left as they came). The built workbook given no `location` rows lists the
  places by name.
- A cell is written as a number only when it is a plain one — ASCII digits, no leading nought, fifteen digits
  at most: a лист «007», a long run of digits and a digit of another script stay the text they are (the last
  two raised or changed the value). A place name the `location` sheet is asked for is always text.
- A place written with its type («с. X», «село X») gets no type on the `location` sheet: the sheet's formula
  writes «type place».
- The command's `location:` line says how many places are listed and how many of them the curated file gave.
- `--no-regenerate` is accepted and does nothing.

### Removed

- `verso.ru.exporters.familio_spravochnik.read_year_records`; `verso.ru.cli.familio_spravochnik`'s
  `regenerate_year_csvs`, `collect_records`, `default_template`, `TEMPLATE_IN_CORPUS`; the catalog key
  `cli.familio_spravochnik.no_template`.

## 0.1.45 — 2026-11-20

A corpus's output does not move — its Terraform, CSVs, records export and the counts of `facts_findings.tsv` are the
same bytes. What moves is the TEXT of six reports of `verso facts --check` (`name-days`, `wedding-calendar`,
`baptism-lag`, `burial-lag`, `wedding-ages` and the class «inside one entry» of `date-order`): they name the same
records at the same level in new words — the words a record's card says.

### Added

- verso-ru: `verso.ru.facts.signals` — the six checks one record answers alone, asked of ONE record:
  `signals_of(record, record_id=…)` reads a built birth, wedding or death (reviewed or not) and gives its `Signals` —
  each `Signal` a message of the catalog with plain params (`said`), why it is worth a second look (`why`), the lines
  that help the re-reading (`details`), the finding's own confidence, the slot, and `stand_down`, the key of the
  record's `written` that answers it. `signal_of(finding)` is the one translation of a check's finding; `CHECKS`,
  `STAND_DOWN`. `verso.ru.pipeline.signals.signals_on_json(node, header=…, page=…, position=…)` asks the same of one
  record of a records-v1 file, built alone as `lint_record` builds it; a record that cannot be built, or a workspace
  with no names table, leaves the checks `unanswered` and raises nothing. `svyatcy_cached()` is the святцы of the
  current workspace, built once per names lexicon (the rows are the package's; the index is read through the lexicon).
- verso-ru: `verso.ru.facts.checks.dates.within_entry(facts)` — `date-order`'s class «inside one entry» without a
  consolidation, on `verso.ru.facts.identity.self_identity()` (every appearance its own person).
- DSL v1: `birth(lag_note=)`, `death(lag_note=)`, `marriage(age_note=)` — the author's note that a late christening,
  a late burial, the ages at a wedding are RIGHT (re-read on the scan). Each stands its check's findings down for
  the record (`baptism-lag`, `burial-lag`, `wedding-ages`) and nothing else: no retraction, both dates and both ages
  stay believed; never emitted. In the vocabulary (`records-v1.json`), in the interface's schema with `checks = true`
  (`ui.field.lag_note_birth`, `ui.field.lag_note_death`, `ui.field.age_note`). `baptism_lags`, `burial_lags` and
  `wedding_age_findings` now return their findings with the count the notes stood down (`Lags`, `WeddingAges`:
  `.findings`, `.noted`).
- verso-ru: `hosted.toml` rows may name `stand_down`, the key of `written` that stands the code down once the scan
  confirms the source (`hosted.readiness()[code].stand_down`): `source_date_error` for DBD001 and DBD002.

### Changed

- verso-ru: the six reports above are printed by one function, `verso.ru.cli.facts.format_signals`, from the signals
  (`signal_report(check, result)`); `format_name_days`, `format_wedding_calendar`, `format_lags` and
  `format_wedding_ages` are gone. A finding is one line in the signal's words, the helping lines under it, then the
  file, the number and the leaf; why a kind of finding is worth a look is said once, under the report's first line
  and with its level, and so is the field that answers a finding the scan confirms (`cli.facts.stand_down`).

### Deprecated

- verso-ru: the catalog lines those reports printed from — `cli.facts.name_days.{finding,lookalikes,note}`,
  `cli.facts.wedding_calendar.{note,pascha,other_months,other_days}`, `cli.facts.lags.{finding,baptism_note,burial_note}`,
  `cli.facts.wedding_ages.{under_age,gap,note,groom,bride}`, `cli.facts.abbr.{born,christened,died,buried}` — are
  called by nothing; they stay in the catalogs until 0.2.

## 0.1.44 — 2026-11-18

A corpus's output does not move: the list is new, and nothing the DSL produces reads it.

### Added

- verso-ru: `verso.ru.reading.people` — the people of a village's neighbouring years, as a reading vocabulary: the
  proofread (`review == "reviewed"`) records-v1 people of the years ±N around a record's year, never that year,
  never the clergy (`CLERGY`), the nearest pair always in and the next pairs only whole under `MAX_PEOPLE_CHARS`.
  `mentions(docs, places)` reads the documents (`places` maps a place as written to its canonical name), `people_list`
  builds the list, `render` and `people_text` write it. Standard library only, like the rest of `verso.ru.reading`, so
  every caller builds the list with one code.

## 0.1.43 — 2026-11-18

A corpus's output does not move: without `--angle` the scan tools cut what they cut, and nothing the DSL produces
reads them; the statuses are new, and no record names them yet.

### Added

- verso-ru: `verso scans rows|zoom --angle DEG|auto` turn a slanted leaf level before it is read (degrees
  counter-clockwise, within ±45; `auto` measures the lines — `rows` the leaf's, `zoom` the writing inside the
  window). The leaf, `--count` and a zoom's window, measured on the page as it lies, are carried to the turned page
  around their middle; `rows` draws its ruler on the turned page and still writes no window, and `zoom`'s line says
  the turn. verso-core: `verso.core.scans.level` gains `carry`, `slant`, `STRAIGHT` (a slant under 0.1° is none) and
  `MAX_ANGLE`; `verso.ru.scans.cli` gains `add_angle_flag`. New catalog keys `scans.angle.*`.
- verso-ru: the statuses `SOLDIER_LEGAL_WIFE` («законная жена солдата») and `SOLDIER_ZHONKA` («солдатская женка») in
  `verso.ru.dsl.statuses`. Their child, as any soldier's wife's, is a `SOLDIER_SON` / `SOLDIER_DAUGHTER`
  (`child_status_for`).
- The plugin `verso-reading`: the skills `metric-books` and `census` cut a slanted leaf level with `--angle`, and
  their install floors and the plugin README's rise to 0.1.43, the release that brings it.

## 0.1.42 — 2026-11-17

A corpus's output does not move: the reading task changes, and nothing the DSL produces reads it.

### Added

- verso-ru: the reading schema (`verso.ru.reading.task`) lets a model read a relative's relationship. In the groups
  `births`, `marriages` and `deaths` a person gains `relationship` (the records-v1 relationship codes; null for any
  slot but `relative`, and where no code fits). In `births` and `marriages` also `relationship_of`, whose relative it
  is, one closed choice with the party's number in it: `mother`, `godparent 1`…`godparent 4`; `groom`, `bride`,
  `witness 1`…`witness 6`. Null is the child in `births` (or an unsaid party), an unsaid party in `marriages`. New
  public names: `RELATIONSHIPS`, `RELATIONSHIP_OF`, `NUMBERED_PARTIES` (the counts are records-v1's, held by a test) and
  `relationship_of_choices`. The prompts name the fields, so their hash moves: a bench needs re-measuring.

### Changed

- verso-ru: **breaking, the shape of a reading's answer.** A person of `births`, `marriages` and `deaths` no longer
  carries `role` (it was always null outside a census), so that each group stays within Gemini's sixteen nullable
  fields; `census` keeps its `role`.

## 0.1.41 — 2026-11-16

A corpus's output does not move: the scan tools are new, and nothing the DSL produces reads them.

### Added

- verso-core: `verso scans` and `verso.core.scans` (`[scans]`, `[heic]`); verso-ru: `verso.ru.scans` — from
  verso-app, Apache-2.0 by its author. The tools work on the frames of a book already on disk: the core's `strips`,
  `quadrants`, `descreen` (were the reading plugin's scripts; its skills now name `verso scans`) and `jpeg`
  (a directory's HEIC frames as JPEG); verso-ru's `check`, `headers`, `crops`, `spread`, `zoom`, `rows` (verso-app's
  `verso-scans` subcommands of those names, the same files, bytes and output — held by `tests/golden/scans`, captured
  from verso-app on macOS; off macOS, where Pillow's JPEG coder and resampling differ, an image is held to a 32×32
  thumbnail within a tolerance) and `cards` (the 1917 census cards). They read an album's stanza of `scans.toml` and write none:
  the windows stay Verso's. The guide: [the scan tools](docs/scans.md).
  Their public names are what the guide's table lists — each module's `__all__` is exactly that, a subcommand's
  module public in `HELP`, `add_arguments` and `run` (`tests/ru/scans/test_surface.py`).
- `verso.ru.scans.cli.zoom.locate` and `cut` (`Target`): `zoom`'s run in two steps — the page `--folio` names, then
  the window cut from it, enlarged, written and said — so a caller with a window of its own (verso-app's
  `verso-scans zoom --record`, a window remembered in `scans.toml` at the turn it was drawn) hands `cut` that window
  and angle and its output is `zoom`'s. `zoom` itself writes what it wrote.
- `Plugin.scans`: a plugin's subcommands of `verso scans`, as `Plugin.commands` are its commands.
- `frames = "spread"` in an album's stanza is read by `check`, `headers`, `crops` and `spread` too, not only by
  `zoom` and `rows`: a frame named by its left leaf is the two pages it holds, each cut from its half, unless it
  stands up as one page (`verso.ru.scans.album.album_of`, `spread_frames`; `check_album(spreads=)`). `check`
  expects such an album's sides from its first to its last — the recto before its first spread and the verso after
  its last are the neighbouring albums' — and counts «N page(s) on M frame(s)». An album with no such stanza reads
  as before; `tests/golden/scans-spread` holds the six subcommands on an album of spreads.
- A `scans.toml` that is no TOML is refused by every subcommand that reads it, in a line, exit 2
  (`verso.core.scans.stanza.StanzaError`), not a traceback.
- A frame of every suffix the tools open (`IMAGE_SUFFIXES`, HEIC included) is read by its лист when its name carries
  one; `cards` and `strips` take the same suffixes, and `quadrants` and `descreen` stand a frame up by its EXIF tag,
  as the other subcommands do.
- `rows` ends by naming no subcommand of the App's: «check them before a window is cut by them» — the one line of
  `tests/golden/scans` that differs from the capture.

## 0.1.40 — 2026-11-16

A corpus's output does not move: a pin teaches a spelling and changes no answer the lexicon gave, and
`terraform fmt` is run otherwise over a generated tree.

### Added

- `verso names pin | unpin` (`linters.names_layer.new_pin`, `remove_pin`): a row of `patronymics.tsv` written into and taken
  out of the writable layer — a short patronymic read back to its father and modern form, a modern form's short one
  (`--old`), or a form tied to nothing — read first by the layers' linter, whose LEX001, LEX003 and LEX007 refuse it. A pin
  of a form the sum already reads otherwise is written with a warning naming both readings (`names_layer.reading_change`).
  `findings_of(replace=True)` reads a replaced pin against the layers below, as it does a names or forms row.
- LEX003 also at a pin: a father no layer holds as a man's name (`unknown_father`).

### Fixed

- `terraform fmt` formats one file after another in a single thread: over a village's tree of 30 MB it was two thirds
  of the Terraform translation, and `verso stale --tf` paid it twice. `verso generate-tf` and both checks of
  `verso stale` now hand it the tree's files in up to eight groups of about equal bytes, one `terraform fmt` a group,
  at once (`verso.core.targets.geni.fmt.terraform_fmt`); the files formatted are those `terraform fmt DIR` reads, and
  the bytes are the same. A village's translation went from about 14 s to 7, `verso stale --tf` from 23–29 s to 9.

## 0.1.39 — 2026-11-15

A corpus's output does not move: the change is in how often the transliteration's rules are read.

### Fixed

- A word's spelling (`naming.transliteration.spelling`, asked once a name) gathered the layers' rule sources and
  `stat`-ed their files on every call — about a fifth of a village's Terraform translation. The rules summed are now
  kept per workspace (`naming.translit_layers.rules`), their sources' stamps looked at again at most every
  `RECHECK_SECONDS` (1 s, as the names lexicon's), and forgotten at once by a rule written through a source or
  `linters.translit_layer`, a host's source provided or taken back, and another workspace (`translit_layers.reload`).
  The refusal of a `transliteration.toml` left in a corpus of schema 7 is looked at as often.

## 0.1.38 — 2026-11-14

The first release from this repository, imported as one commit. A corpus's output does not move: texts and the
example reworded.

### Changed

- README, CONTRIBUTING and AGENTS.md: installing from a git tag, the names base `verso-ru` ships, the `ru` plugin by
  its record tradition.
- `examples/toy` is a workspace of schema 6: a `names/` layer over the shipped base in place of `names.csv`; with an
  empty layer it takes the base's pre-reform forms (Иоанн, Параскева, Феодор …).
- Tests and docs: archaic single-name ancestors are invented names; neutral wording in comments, docs and tests.

## 0.1.37 — 2026-11-13

A corpus's output does not move: the change is in what `verso translit add|remove` refuses.

### Fixed

- `verso translit add|remove` (`linters.translit_layer`) refuses a rule of the addresses' profile only when the address
  spelling of its word would change: a rule giving what the profile gives — a redundant one, LEX009 — is written or
  taken away over a tree that spells the word (`minted_labels(…, after=)`). With one profile for both roles the refusal
  no longer offers `--profile` of the same profile; it names `[translit] display` (`translit_edit.minted_same`).

## 0.1.36 — 2026-11-13

A corpus's output does not move: docstrings, a guide and tests reworded.

## 0.1.35 — 2026-11-13

A corpus's output does not move: a workspace of schema 6 or older keeps `ru-v1` for both roles and reads its
`transliteration.toml` as before, so every Terraform tree, CSV and records JSON comes out the same byte for byte; only
`verso --help` gains a command. A workspace moves its Geni latin names only by naming `display = "ru-v2"` (schema 7).

### Added

- Transliteration has two roles: `address` (res_names and Terraform addresses) and `display` (Geni's latin names).
  `verso.ru.naming.transliteration`: `address()`, `display()`, `display_name(name)`, `profile_of(role)`;
  `cyrillic_to_latin` stays the address spelling.
- Profiles are data (`TranslitProfile`, `load_profile`, `PROFILES`): a table of letters with word contexts — a word's
  first letter, after ь/ъ, after a hushing consonant, a word's ending — and whole names. `ru-v1` keeps its
  `str.translate` path and its hash. **`ru-v2`** (`naming/data/translit/ru-v2.toml`), frozen by its hash: BGN/PCGN
  without apostrophes — е → e everywhere, -ий/-ый → -y, -ия → -ia after a letter, ё → yo (o after ж ч ш щ), ь/ъ
  dropped and ye/yo/yi/yu/ya after them; the pre-reform letters (ѣ, і, ѳ, ѵ); eight whole names (Alexey, Artyom,
  Yeremey, Yemelyan, Maxim, Pyotr, Semyon, Fyodor). The default profile of a new workspace.
- Workspace schema 7 (`verso.core.workspace`): `[translit] address`, `display` name each role's profile
  (`TranslitRoles`, `Workspace.translit`). Schema 6 and older read as before: `ru-v1` for both, and the corpus's
  `transliteration.toml`; schema 7 refuses that file and names `verso translit migrate`.
- The transliteration's rules are rows of the names layers: `translit.tsv` (profile, word, latin, source, note) beside
  the three tables, summed as the names are — an upper layer's row replaces the lower one, `-` takes it away
  (`verso.ru.naming.translit_layers`: `rules`, `explain`, `sources`, `writable`, `provided` for a host's own source).
- Plugins: `Plugin.display_transliterate` and `plugins.display_transliterator()` (the address one when a plugin gives
  none); Geni's latin names (`targets.geni.profile`) ask it.
- `verso translit show|add|remove|check|migrate` (`verso.ru.linters.translit_layer`): `add` refuses a rule of the
  address profile that would rename a label a generated Terraform tree has minted, and names the display profile
  instead; `remove` writes a `-` row over a lower layer's rule; `migrate` moves `transliteration.toml` into `ru-v1` rows.
- Linters LEX008 (a rule's profile or word missing or unknown), LEX009 (a redundant rule, a removal of nothing),
  LEX010 (latin outside `[A-Za-z' -]`; hard but for `ru-v1`).

## 0.1.34 — 2026-11-13

A corpus's output does not move: dsllint's findings (`--json` and the text), the records JSON and the review ratchet's
prints come out the same byte for byte on every file of the corpus; only how often the same work is done changes.

### Added

- `verso.ru.records.blank` — `BookSpec`, `blank_book`, `book_path`, `BlankError`: an empty metric book (births,
  marriages or deaths) as a records-v1 file, built from the record set's own factory, with no `reviewed` flag and an
  empty `sha256` («no DSL source»); see «A book without a DSL source» in `docs/records-json.md`.
- `verso names add --replace`: replaces the row of a key the writable layer holds already, whole, instead of refusing
  it; the layers under it are not touched (`names_layer.new_entries(…, replace=True)`).
- `BlankError.key` and `.params` (the catalog key and its parameters; `BlankError(key, message)` still works), listed in
  `docs/records-json.md`.
- `blank_book` refuses more: padded or control characters in a path field or the parish, a locality that is empty, `.` or
  `..`, an empty parish (`records.blank.path`, `records.blank.parish`), and defaults the record set does not accept
  (`records.blank.defaults`) — as `BlankError`, no longer a bare `TypeError`.
- `verso names add --replace` on a workspace of schema 5 or older is refused (`cli.names.replace_needs_schema_6`) instead of
  writing a shadowed row; the replaced row is linted against the layers below it, not the row it replaces, and the command
  prints a «replaced» line for it.

### Changed

- dsllint parses a DSL file once for all its checks and walks each node once between them
  (`verso.ru.linters.checks.shared_ast`): each of the 35 checks parsed the file itself, and walked its tree again from
  the root. `shared_ast.parse` keeps the trees of the last texts parsed, `shared_ast.walk` a node's `ast.walk`, and
  `shared_ast.Visitor` is `ast.NodeVisitor` with its handlers looked up once per class and a node's children listed once
  for every visitor. Every finding of one village's 358 files: `--json` 42 s → 9 s, both modes 88 s → 18 s.
- The records' encoder and decoder look the vocabulary up once where they looked it up per field (`written_key_in`,
  `param_of_key_in` beside `param_spec_in`), and `plugins.dsl()` keeps the workspace module it imports. A village's
  decode and re-encode: about 30 % faster.

## 0.1.33 — 2026-11-11

A corpus's output does not move: the change is in the people index's build, which no producer runs.

### Changed

- The people index (`verso.ru.persons.people.PeopleIndex`) builds about three times faster, with every answer the
  same: a name's keys (`match_key` of its written and modern forms) are computed once per distinct pair in a build and
  shared, a person's counts are plain dicts, a life (`verso.ru.persons.lives`) keeps the bounds its questions ask for
  instead of scanning its days for every clue of its name, and the cyclic collector is held off during the build
  (`gc.disable`, let run again when the last build under way ends). On a large synthetic corpus the build fell from 1.1–1.2 s to 0.45 s; on a real corpus, in a process holding its
  records, from 1.1–1.4 s to 0.42 s. `python tests/people_synthetic.py` times it.

## 0.1.32 — 2026-11-11

A corpus's output does not move: the change is in `ui-v1.json`, its build and two labels of the page; no record, records
JSON, translator or CSV byte changes.

### Added

- ui-v1: a field's flag `checks` — a field that only answers the corpus's checks, offered in no «+ поле» of a page and
  shown where it is written. verso-ru marks its seven: «ошибка даты в подлиннике» (`source_date_error`), «имя не по
  святцам — верно» and «венчание в запретный день — верно» (`calendar_note`), «ошибка родства в подлиннике»
  (`source_kin_error`), «ошибка возраста в подлиннике» (`source_age_error`, a burial's and a roll member's), «тёзка
  (возраст чужой)» (`namesake`) and a roll member's «ошибка прошл. возраста» (`previous_age_error`). A page that does
  not read the flag offers them as before.
- ui-v1: a field's flag `auto` — what the plugin sets itself where it can, offered in no «+ поле» and shown where written;
  verso-ru marks «фамилия в книге» (`surname.in_book`), unticked for every surname it derives.
- ui-v1: a person's field may say whom a page's «+» offers it — `offer = {gender, not_in}`: a person of that sex, not one
  standing in those roles; shown, all the same, where written (a hint the build checks: `records.ui.bad_offer`). verso-ru
  offers `maiden_surname.modern` to a woman who is not the child of a birth or a christening: a newborn girl's is derived
  from her parents, a man's is his surname.

### Changed

- `maiden_surname.modern` is labelled «фамилия при рождении» / «birth surname» (it was «девичья фамилия» / «maiden
  surname»): what Geni and Familio keep under it, a word that fits whoever carries it.

## 0.1.31 — 2026-11-10

### Changed

- The review ratchet's prints and the names layers' linter run faster. No output moves: every record's print and label,
  and every finding of `lint_layer`, is what 0.1.30 gives. `record_prints` walks a file once, marking every node that
  holds a record call, and dumps each wrapper's context once for all the records under it — it rebuilt it for each, so
  a record set of N records cost N² (`ast.walk` once a wrapper and a record); LEX005 builds the sum's derivations once
  and asks each pin of the sum's pins without it (`Lexicon.unpinned`, `verso.ru.naming.derived.Unpinned`) rather than
  building a lexicon without each pin. On a large corpus (one machine, wall time): the prints of its
  files 6.8 s → 2.8 s, its `test_every_corpus_file_upgrades` 45.9 s → 37.2 s (the rest is the
  codemod's own libcst), and `lint_layer` of a names layer over the base 16.7 s → 0.1 s.

## 0.1.30 — 2026-11-10

### Changed

- The linters on records JSON and the replay run faster — the path a hosted store runs on every edit, and a corpus's
  tests on every record. No output moves: every finding, every record built and every byte a corpus writes is what
  0.1.29 gives. What changed is what is asked again: a lint call (`lint_records`, `lint_record`, `lint_header`) reads
  what each node wrote once for all its rules (`walk.keeping_written`) and looks at the corpus's `statuses.toml` once,
  as it begins (`statuses.held()` — the next call still sees an edit); a JSON key's factory parameter is a table the
  vocabulary keeps (`Vocabulary.params_of_keys`) rather than a scan per key; the replay asks the workspace's
  vocabulary once a book; `modernize_orthography` keeps its answers. On a large corpus (one machine, wall time) the tests that lint
  every record alone fell from 123 s to 54 s, and those that hold the JSON walk to `dsllint` from 124 s to 92 s (the
  rest is `dsllint` itself).

## 0.1.29 — 2026-11-10

### Fixed

- The святцы's `ALSO_KEPT` holds names, not keys: a `Svyatcy` files them under the lexicon it files the book's names
  under (`Svyatcy.keys`, in place of the module's `name_keys`). 0.1.28 kept the base's key «иулиания», which a layer
  folding Иулиания onto Юлиания never asks, so the people's forms of Юлиания (Ульяна, Улиана, Ульяния, Иулиана) found
  no saint. A corpus's output moves only in `facts-check check=name-days`: those births are read against the book again,
  as before 0.1.28.

## 0.1.28 — 2026-11-09

The names lexicon gets a base of its own and a workspace that needs no table. A corpus of schema ≤ 5 reads as it
did — its `names.csv` compiled into one layer, no base under it —, and its output does not move.

### Added

- **The names base** (`verso.ru.naming.data.base`): 9 667 given names, each row with its source — the 1906
  svyatcy (`trebnik1906:<row>`), Wikidata (`wikidata:Q…`, CC0), the spellings metric books write (`mk`, no record
  in them), a form the rules give (`rule`) or a maintainer's (`editor`). It follows the svyatcy's direction (Иван →
  Иоанн) and their sex for a name they hold; a label outside the Russian alphabet, a patronymic or a surname is left
  out. `tools/names_build/` builds it byte for byte from its inputs (`SOURCES.md` beside it); a check against
  Wiktionary is a comparison only and writes nothing.
- **Workspace schema 6** — `[names] base` (default `"ru"`, or `false`), `layers` (directories above the base,
  lowest first) and `writable` (where `verso names add` writes; the top layer by default). A workspace of schema 6
  without `[names]` reads the base alone. `[names] dir` is schema ≤ 5's and is refused in schema 6
  ([the workspace](docs/workspace.md)).
- **A layer is three TSV files** (`names.tsv`, `forms.tsv`, `patronymics.tsv`, sorted by key; `FilesLayer`). A
  `-` forms or patronymic cell means «no such form» (the rules do not fill it); a names row whose bases are `-`
  removes the lower layers' entry of that key. A layer that derives takes a form it leaves empty from the rules.
- `verso names layer-diff --from-legacy DIR --base ru --oracle FILE --out DIR` — the minimal layer above the base
  that answers every question of an oracle (the recorded answers of the naming functions) as a `names.csv` does.
- `verso names add | remove | check | explain` over the names layers of a workspace of schema 6 ([the workspace](docs/workspace.md#adding-removing-checking-and-explaining-a-name)):
  a name is written to the writable layer after the layers' linter has read it (a hard finding refuses it, LEX005 warns),
  removed — a name only the base holds by a removal row — with a warning when records of the corpus still write it, the layers
  checked (exit 1 on a hard finding), and an answer of each naming function explained by the layer and the entry it came from,
  or by the rule. In a workspace of schema ≤ 5 `add` still writes `names.csv`.
- The layers' linter, `LEX001`–`LEX007`: a key that is not a name (another alphabet, an accent, a space), a key twice,
  a base no layer holds, a base that is itself a variant, a row the sum answers alike without, a base row whose
  source is not one of the base's, two names deriving one form with no pin.
- `verso.ru.naming.layers.provided(directory, source)`: a host hands the library a names layer as a `LayerSource` of its own —
  a server's rows — in place of the directory `[names] layers` names, for the block it works in a workspace; a source
  with an `identity` is kept between workspaces by the registry as a directory is. `IdentifiedSource` (`verso.ru.naming.lexicon`) is the
  typed form of such a source — a `LayerSource` with an `identity` — and its `stamp()` must change with every write, by any process.
- `names_registry.invalidate(identity)`: a host that wrote its own layer drops the lexicon held and the kept lexicons built from that
  layer, and no others (`reload()` drops all of them).

### Changed

- A father in «-ила/-йла» takes «-ович/-овна» (Гаврила → Гаврилович, Самойла → Самойлович), the church name's form.
  The names of the svyatcy whose «-а» is their own — Акила, Арпила, Вавила, Папила, Сила — keep «-ич/-ична» as
  `editor` rows of the base (Сила → Силич); Михаила takes Михаил's forms.
- `derive_old_patronymic` gives the rule's short patronymic for a father the lexicon does not know (Зюзяк →
  Зюзяков), where it gave "". A name it holds — a «no such form» cell, a layer that does not derive, a name of the
  ignore list — keeps its answer.
- A records export names the base's bytes among its inputs: a release that changes only the base makes an older
  export stale.
- The lexicon built from a stack of sources is kept (eight of them, one for a set of sources — an edit makes a new stamp
  and drops the older lexicon —, by each source's identity and stamp): a switch of workspace, or a workspace entered
  again, no longer builds the base's ten thousand names anew (13 ms cold, 0.07 ms from the kept sum). `reload()`
  keeps none: it rebuilds whatever the stamps say (a rewrite of the same size within one tick of a coarse clock shows
  in none).
- `hosted.readiness()` reads `hosted.toml` once; each call still returns a table of its own.
- The church calendar's `ALSO_KEPT` follows the base: `юлиана` is kept with `иулиания` (the key the book files the saint
  under, which the base folds Юлиания onto), not `юлиания`; with the base alone `Ульяна` finds the book. A test holds
  every kept key to the book's keys. A corpus of schema ≤ 5 whose table folds Иулиания onto Юлиания loses that one
  extra key.
- The lexicon trace — `VERSO_LEXICON_TRACE`, `VERSO_LEXICON_TRACE_ROOT`, `names_registry.TRACE_ENV`, `TRACE_ROOT_ENV`,
  `TRACED_KINDS`, `traced_root`, `traced_table`, and `names_csv.read_rows`' refusal under it — is gone: it cut the
  tests' slices of a names table, which the tests no longer need. `names_registry.asked()` stays.

### Fixed

- A name of the ignore list (source `ignore`) in a layer gets no forms from the rules, as it never did from the old tables.
- A name whose one base no layer holds answers as written instead of folding onto a name the lexicon does not know.
- `census_parent_link` (CPL012) no longer fails on a patronymic the lexicon lacks (`ValueError: Cannot canonicalize
  patronymic …`, reported by `dsllint` as a failed linter): such a patronymic says nothing of the father, as in the
  records JSON's CPL012.
- The tests' names slice (`tests/fixtures/workspace/names.csv`, named by the entries below) is gone: the tests read the
  base under a layer of what it lacks.
- `verso names layer-diff` no longer fails with `KeyError: 'genitive'` on an oracle that asks `genitive_from_name` or
  `name_from_genitive` of a name the base answers otherwise.
- `lint_records` refuses a `[names] base` no plugin ships, naming the bases there are, where it read it as a workspace
  with no names.

### Deprecated

- A `names.csv` read as a layer of schema 6 warns (`DeprecationWarning`); it goes in 0.2.

## 0.1.27 — 2026-11-08

A corpus's output does not move: every answer of the naming functions a corpus's producers ask is the same,
and a corpus's byte-for-byte comparison says so.

### Changed

- The names table is read as a lexicon of layers (`verso.ru.naming.lexicon`): each layer holds three tables with a
  unique key — names (sex, name → bases, the form a res_name takes), forms (the exceptions to the rules) and
  patronymics (a form the rules do not tie to a name, an old form of a modern one, a patronymic known without a
  father) —, and an upper layer replaces a lower one's entry of the same key. A `names.csv` with its two ignore lists
  is compiled into one such layer (`verso.ru.naming.legacy`): «the first row wins» is settled there, once, and every
  answer that hung on the order of the rows is written out. The public functions keep their names and signatures.
- The forms the table does not hold — modern and old patronymics, the genitive, a modern patronymic from an old
  one — are derived by one rules module, `verso.ru.naming.forms`, pure and without the table. A father in «-ь» takes
  «-евич/-евна» (Игорь → Игоревич), one in «-ия» takes «-иевич» (Азария → Азариевич).
- `name_from_genitive` answers from the lexicon where the table gave one genitive to several names and the order of
  its rows chose: no corpus asks it.

### Deprecated

- `names_registry.reload()`, `names_registry._names_table_loaded` and `names_registry._find_name_in_table` stay for
  the App and a corpus's tests, and go in 0.2.

## 0.1.26 — 2026-11-07

A corpus's output does not move: only the tests' fixtures change.

### Fixed

- The tests' names slice keeps Сергий's two rows as a real names table holds them («Сергиев» in both old-patronymic
  columns): 0.1.25 took them corrected, which made one of them repeat its neighbour, and a real table keeps them
  as they were.

## 0.1.25 — 2026-11-07

A corpus's output does not move: only the tests' fixtures change.

### Changed

- The tests' names slice (`tests/fixtures/workspace/names.csv`) takes seven rows as a real names table now holds them:
  Анимаиса's genitive is «Анимаисы», Василько's «Василька» (and its old patronymics «Васильков», «Василькова»), the
  patronymics of Аэтий and Гостомысл lose a stray accent and capital, Сергий's old feminine patronymic is «Сергиева»,
  and the two rows that filed Викторий's and Викторин's forms under «Виктор» are gone.

## 0.1.24 — 2026-11-05

A corpus's output does not move: a corpus's byte-for-byte comparison at the bump says so.

### Fixed

- `verso workspace` (and `python -m verso.core.workspace`) no longer warns «'verso.core.workspace' found in sys.modules
  … prior to execution» (0.1.23): the registry imported the module at its top, and runpy ran it as __main__ after. It
  imports it where it asks it again, as before 0.1.23; the plugins' answers stay kept.

## 0.1.23 — 2026-11-05

A corpus's output does not move: the change caches pure functions of a factory and keeps answers that are the same;
a corpus's byte-for-byte comparison at the bump says so.

### Changed

- Rebuilding records from `written` (`replay_file`, `replay_record`) costs about half as much: a factory's signature is
  read once (`factory_params`, `param_names`, `required_params`, `takes_records` are cached — `factory_params` returns a
  tuple now), a record's entity lists are found once rather than once a persona, and `plugins.dsl()` answers a kept DSL
  without building the question. A workspace entered again inside itself from the same verso.toml keeps the plugins'
  answers (it compared by identity, and a host entering its workspace once a book — the hosted server — read the
  entry points and built the DSL anew each time). The first queue of a village on the hosted server: 12 s → 6 s (M1).
  A corpus's output does not move.

## 0.1.22 — 2026-11-04

A corpus's output does not move: a corpus's byte-for-byte comparison of this tree against v0.1.21 is 0 changed, 0 vanished,
0 new — python-dateutil 4.0 included.

### Changed

- verso-ru pins `python-dateutil==4.0.0` (it was 2.9.0.post0), a dependency whose bytes reach the output: see the comparison above.
- The dev tools: `ruff==0.17.3`, `pytest==9.2.0` (`requirements-dev.txt`); a corpus's dev pins follow this tag's.
- verso-core and verso-ru name Python 3.14 alone among their classifiers (3.15 is gone), and CI tests 3.14 alone: the
  hosted server's image runs 3.14, as every venv does. `requires-python` stays `>=3.14`. A corpus's output does not move.

## 0.1.21 — 2026-11-04

A corpus's output does not move: this release adds entry points and a column of `hosted.toml`; no Terraform, CSV,
records JSON, facts report or ratchet fingerprint changes.

### Added

- **`replay_record`: a record rebuilt alone** (`verso.core.records.replay`). A hosted store keeps one record per row and
  rebuilds one per edit. `replay_record(node, header=, page=, position=)` builds a record through its set's own factory,
  given the set's header (the node without its `pages`), the leaf and a `Position` — `ordinal` (0-based place in the set)
  and `members_before` (the roll's running number reached before the двор) — and sets the counters the place gives:
  a list entry's and a card's `index`, a household's `record_number` (a hidden member takes none, a whole number a member
  wrote is kept). It equals the record `replay_file` makes in the book. `position_values(node, position=)` names those
  values as paths in `derived` without building. The vocabulary says which classes hold a place
  (`Vocabulary.positional`: `Positional`, `Numbering`; ru's `POSITIONAL`). `replay_alone` also returns the set built
  around the record. The guide: «A record on its own» in `docs/records-json.md`.
- **`lint_record` and `lint_header`: the checks of one record** (`verso.ru.linters.on_json`). The same rules over a view
  of one record and its set's header (`RecordView`), and over a header alone: the findings of `lint_record` over a
  file's records and of `lint_header` over its sets are those of `lint_records`. `file_in_scope` carries ULC001's one
  fact of the whole file (`places.file_in_scope(headers)`), `run_levels` what RVR001 reads of the rest of a page run:
  RVR001 is refused without it (`on_json.needs_run_levels`), and a change of one record's review level means re-linting
  its page run's records for RVR001 only.
- **`scope` in `hosted.toml`**: every code says where it is answered — `record`, `set` (ZGS003), `file` (ULC001) or
  `source` — read as `hosted.readiness()[code].scope`. Three messages: `on_json.set_scope`, `on_json.needs_file_scope`, `on_json.needs_run_levels`.

## 0.1.20 — 2026-11-01

A corpus's output moves in its records JSON alone (the `records` producer of a corpus's comparison): a record that writes its own
лист inside a `page()`, or its own months or year inside a month section, gains `written.wrapper`. No Terraform,
CSV, facts report or ratchet fingerprint moves.

### Added

- **`written.wrapper`: a wrapper's value beside a record's own** (records v1.x; `SCHEMA_ID` stays `records-v1`,
  `records-v1.json` gains the key). A record writing `page="12"` inside `page("11", …)`, or writing its months
  (or year) inside a `*_month(…)` / `*_month_year(…)` section, kept no trace of the wrapper: its call's value stood
  and the wrapper's was gone, so a reader of the JSON could not say which `page()` or section held it (the App's
  folder admitted both as KNOWN, its R17 and R33). The DSL's wrappers now keep the value they would have set on
  a field the call wrote (`verso.core.written.shadow`, the record's `_wrapper`); the export writes it as
  `written.wrapper`, grouped as `written` is (`{"page": "11"}`, `{"birth": {"month": "march"}, …}`); decode and
  replay keep it on the record and change no value by it; `split_wrapper` reads it and `split_context` leaves it
  out of the call's keys; `record_view` (`context_in_derived`) drops it. Only the leaf of a `page()` and the month
  and year of a section are kept, the innermost wrapper's (`Vocabulary.shadowed` names them; the schema holds
  `written.wrapper` to those keys, never null). Reading is lenient where an editor of the JSON that knows nothing
  of the key left an entry behind: decode and replay drop an entry whose key the call no longer writes — its own
  `page` deleted, an own month unset — or that `written.context` now marks as a wrapper's (a record moved into a
  section); the encoder never writes one.
- **`redundant` in `hosted.toml`.** The 19 codes whose finding is a redundant argument (a written value equal to the
  one the record inherits) — the `derived` codes whose note says «(redundant…», and the positional `BRD002`,
  `BRD004` that fold into one — carry `redundant = true`, read as `hosted.readiness()[code].redundant`
  (`Readiness.redundant`, default False), so a caller no longer searches the note for «(redundant». A test holds
  the field and the notes to one set; a `redundant` on a code that is not `derived` is refused.

### Changed

- **A corpus's `statuses.toml` is an input of its records export.** The index's `inputs` hashed the statuses only
  as `statuses.py`, with the library's code; a corpus holding them as data could change a status's words or sex
  and keep its export. `corpus/statuses.toml` is now an input where the file stands (an index of a corpus without
  it reads as before), resolved in the workspace's `[corpus] dir` (docs/records-json.md, «The index»).
  verso-app 0.5.1's importer resolves every key but `code` and `names/…` under the village, so an import with
  `source_root` from a corpus holding `statuses.toml` reads as stale there; verso-app 0.5.2 resolves it.
- **`corpus_module_name()` is None for a corpus whose statuses are `statuses.toml` alone**: there is no module the
  DSL could import them from, so IMP001 refuses `from <corpus>.statuses import …` there and `verso upgrade-dsl`
  knows none of their names (a v0 file naming one is refused).
- **The statuses of `statuses.toml` register no sex in `Status._gender_registry`.** Their sexes go to
  `Status._data_genders`, replaced whenever the file is read and asked first by `Status.gender_of` (which follows
  the file's stamp while it holds anything), so a constant the file drops gives no sex to a plain-string status of
  its words once the file has changed, and a corpus's constant wins over a library's of the same words and another
  sex — as a corpus's `statuses.py`, imported after the library, always did.
- **An unrecognized name is named as it was checked.** `Person`'s refusal said «Unrecognized first name 'None'
  (original: 'Хщъ')» for a name written in the original alone; it now names the modern form it looked up
  («Unrecognized first name 'Хщ' (original: 'Хщъ')»), and the patronymic's refusal likewise. verso-app's DSL
  backend passes this text through as a refusal: its golden `tests/golden/api_v2/15-edit-refused.json` changes
  from `'None'` to `ValueError: Unrecognized first name 'Васьлиск' (original: 'Васьлискъ')`.

### Deprecated

- The catalog key `statuses.unknown_key` (0.1.19) is no longer called: an unknown key of a constant in
  `statuses.toml` is refused by `corpus_data.check_keys`, with the core's `corpus_data.unknown_key` — the same
  text. The key stays in both catalogs until 0.2, a catalog key being public.

## 0.1.19 — 2026-10-31

### Added

- **A corpus's landlord statuses can be data.** `<[corpus] dir>/statuses.toml` — a table a constant (`text`,
  `gender`), and the alias tables `child_estate_aliases` and `estate_aliases` — is read by `catalog()` without
  executing any Python; with `statuses.py` beside it the workspace is refused (`statuses.both_forms`).
  `verso statuses-toml [--out FILE]` prints the TOML of the module, or writes it to FILE: the migration is
  `--out <corpus dir>/statuses.toml`, then `statuses.py` removed by hand (there is no flag that writes the file
  beside the module and leaves both). `statuses.toml` is read again when its stamp (mtime, size) changes while
  a process runs, as the corpus's other files are, and a TOML text with DEL (U+007F) is written escaped.
- **A record's view from its JSON node.** `verso.ru.dsl.view.node_view(built, node, record_id)` is `record_view`
  for a record that has only its records-v1 node (`written` alone): the same `record`, `consts` read off `written`
  by the catalogs, an empty `opaque` and no `version`.

## 0.1.18 — 2026-10-31

### Changed

- **The checks read an argument written in its place as they read the keyword.** PM001 and PM002 read
  `member()`'s `ref_member` (and `role`, `parent_member`) positionally too, AGE001 and AGE002 a `death()`'s `age`
  and a `marriage()`'s `groom_age`/`bride_age`, MRA001 a marriage's `groom`, `bride` and `relatives`, DRA001,
  DRA002 and DRL001 a death's `deceased` and `relatives`. A positional value was not judged before: the source was
  silent where the records JSON (`lint_records`) found it. Those divergences of 0.1.17 are agreements now
  (`tests/test_linters_on_json_written.py`), and each check's positions are held to its factory's signature.

### Fixed

- **Three redundancy findings no longer name an argument the generator needs.** Each told the author to remove a
  value that `CensusHousehold.__init__` or `Death.__init__` would not give back; `dsllint` and `lint_records` now both
  stay silent there:
  - **CRD004** — a daughter's maiden name (`birth_last_name_modern_orth`) beside a current surname of her own: the
    generator derives no maiden name for a daughter who has a current surname, so hers is the only one.
  - **CRD001-CRD004** — a surname whose source is the member himself, or a member listed after him that derives
    its own, or a chain that leads back to him: the generator makes one pass in member order and would give him
    none. `census_redundancy` now reads the source as `lint_records` already did (`_family_surname`); the two
    findings `dsllint` gave there and the JSON did not are gone.
  - **DRA002** — a relative's residence equal to the deceased's in a death where another relative states a
    different one (DRA001): the household's residence is the FIRST relative's that states one, so the removed
    copy could take the other relative's village.

  Findings only vanish; none is added. A corpus held none of these, so its output and baseline do not
  move (a corpus's comparison against 0.1.17: 0 changed).

## 0.1.17 — 2026-10-31

### Added

- **`lint_records` answers every code that is not the form of the source text.** `verso.ru.linters.on_json`
  was a pilot of two codes (CPL002, ULC001, 0.1.11); it is now a package, a registry of rules by family —
  `census`, `common`, `events`, `names`, `places`, `estates`, `redundancy` — and `on_json.SUPPORTED` lists the
  85 codes it answers: the 42 `written` codes (what one record's calls wrote), the 21 `derived` ones (what the
  factories and the wrappers derive, read off the records `replay_file` rebuilds from `written` alone) and the 26
  `context` ones (the book, the corpus's estates and places, the names tables), less the four positional codes
  folded into their keyword codes. The four `source` codes (SLC001, SLC002, CML001, IMP001) are refused by name
  (`on_json.source_code`), as is a code that is no linter code (`on_json.unsupported`). A finding is the code, variant,
  params and token `dsllint` gives, addressed by the id (rule `r1`) of its record or of its book; its level is
  its code's severity in `hosted.toml` (`refuse` an error, `warn` a warning). `lint_records(data, codes=…,
  workspace=…)` reads the tables of the workspace it is given. The classes of difference between the JSON and the
  source (a positional and a keyword argument are one in `written`, for one) are described in the modules' docstrings and
  in `docs/records-json.md` («Linters on records JSON»). Agreement with `dsllint` is held by the samples oracle
  (`tests/test_linters_on_json_samples.py`, over every code of `SUPPORTED`) and, in a corpus, by a test over the
  corpus.
- **`lint_records` checks its input and keeps what a refusal could answer.** With a non-empty `codes`, before any
  rule, anything but a mapping of schema `records-v1` with a list of documents (and a header vocabulary no newer
  than the plugin's) is a `FormatError`, as `replay_file` refuses it — `{}`, a list, a v0 export, for a code
  that reads no replay too; `codes` as a `str` is a `TypeError`. A file that cannot be replayed (no wrapper
  context, a record no factory rebuilds, a names table that lacks a name the file writes) still refuses with
  `Unsupported`, which now carries `findings` — those of every requested rule that reads no replay, leveled as
  usual — and `unanswered`, the sorted codes that went unanswered. Calls are not thread-safe (the workspace is
  a process-global stack): serialise them or run one per process. Public names of `on_json`: `lint_records`,
  `SUPPORTED`, `RULES`, `Finding`, `FileView`, `Rule`, `Unsupported`, `names_table_present`, `estates_present`.
- **A code that needs the names table warns without one (H7); a code that needs the estates, without them.**
  In a workspace with no `names.csv`, the findings of a code whose `needs` in `hosted.toml` holds `names`
  are warnings, never a raise, and a rule that needs the replay (which builds its persons from the table)
  finds nothing more. The same for a code that needs `estates` in a workspace with no `estates.toml`.
  `names_table_present()` and `estates_present()` ask. `needs = ["names"]` is now on the 19 codes
  of the other classes that read a name or replay the file, not only on the `context` ones.
- **`forms` and `as`: the positional fold has one home, `hosted.toml`.** BRD002 folds into BRD001, BRD004
  into BRD003, CRD003 into CRD002, CRD006 into CRD005 (`as`), and `forms` gives, per code, the variants of the
  source that the JSON speaks as the keyword's (`said`, `read`, `rename`, `unquote`; DRA002's
  `redundant_positional` is its `redundant`). `hosted.Form`, `hosted.Readiness.as_code` and `.forms`, and
  `hosted.fold(code, variant, params)` apply them; `lint_records` and the oracles read the same table. A
  folded code asked of `lint_records` answers its `as` code's findings, spoken as that code.

Internals of the walk, not API (`on_json.walk`): `status_constant` / `status_name` (the constants of the
workspace's catalogs that spell a status the JSON holds as `{text, gender}`, and the one name the rules give it —
the one that sorts last, as the checks' tables are built), `NoReplay` (raised when the file cannot be replayed for
want of a names table; `lint_records` answers what the rule found before) and `ReplayRefused` (the replay's refusal,
which `lint_records` turns into the `Unsupported` that carries the answered findings).

### Changed

- **The checks' tables, patterns and helpers the rules on JSON share are public.** Renames only, with no
  change of behaviour: across `linters/checks/` the module-level names a rule on JSON imports lose their
  leading underscore (`CIVIL_LIKELY_FROM`, `OLD_ESTATE`, `NAME_KWARGS`, `FULL_SUFFIXES`, `is_full_form`,
  `as_peasant`, `estates_compatible`, `landlord_expected`, `Expected`, `Lives`, `relative_label`, the role
  sets of the census checks and the like). A corpus's comparison holds the output of `dsllint` to the byte.
- **One extraction in `census_redundancy`: `patronymic_tier`.** The nested `_tier` closure of the CRD
  check moves, unchanged, to module level as `patronymic_tier(explicit, gen_orig, gen_modern)`, which the check
  and the rule on JSON both call. The same findings.

## 0.1.16 — 2026-10-29

### Added

- **Records v1.x: the `#` notes of a DSL file on its nodes.** The export (`verso export-records`) puts each
  note of a DSL file under `note` — a list of `{"text", "anchor"}`, the text Markdown — on the node it is
  about: a `file` note on the file node, a `record`, `argument` or `field` note on its record's node
  (`anchor.arg` naming the argument as the JSON does, below), a `range` on the first record of the run (`anchor.end`
  its last), and a note nobody bound on the file node as `{"to": "manual"}`. The plugin reads the notes
  (`Plugin.notes` → `SourceNotes`; ru: `verso.ru.dsl.notes.read_notes`), the core places them
  (`verso.core.records.notes`) and holds the plugin's record ordinals to its own records: a file whose
  record count, or the number of a record at some place, is not the export's binds no note to a record —
  each goes on the file as `manual` (`Exported.unbound` names the file and why). Like `key`, `note` is a
  property of the stored node: `decode_file` checks it and `replay_file` ignores it, no part of the graph;
  the encoder never writes it, so the review page's view of a record and `ui-v1.json` are unchanged.
  Additive: `SCHEMA_ID` stays `records-v1`; the JSON Schema gains the optional property on the file and
  record nodes. A plugin without the hook exports no notes.
- **Records v1.x: the vocabulary and the default language in the file header.** A records file may carry
  `vocabulary` (`{"plugin": "ru", "version": 1}`: the plugin whose vocabulary the records are written in and
  that vocabulary's version) and `lang` (the book's language by default, BCP 47: `"ru-Cyrl"`). The core asks
  the registry — `Plugin.vocabulary: tuple[str, int] | None` and `Plugin.default_lang: str | None`
  (verso-ru declares `VOCABULARY_VERSION = 1`, `DEFAULT_LANG = "ru-Cyrl"`) — and names neither itself: a core
  without such a plugin writes neither key. An old file without them reads as before; `decode` refuses a file
  whose vocabulary version is newer than its enabled plugin reads, naming plugin and version, and `replay_file`
  refuses it alike; the graph does not read them. Additive: `SCHEMA_ID` stays `records-v1`, the JSON Schema gains the two optional
  properties, the review page's view of a record is unchanged.
- **Records v1.x: an optional immutable `key` on a record.** A record node may carry `key` (a non-empty
  string without `/`), the record's own key that outlives a corrected number or sex. It is a property of the
  stored node: the DSL never writes one (the export from the DSL has none), decode and replay ignore it (it
  is no part of the graph) and ids (rule `r1`) do not read it. Code that rebuilds a node from objects does
  not carry it — only the folder backend, which sets it on first load, may do that and must copy
  `key` from the node it replaces. `check_keys(doc)` (`verso.core.records.schema`) names the paths of two
  records sharing a key; `decode` refuses a malformed one. Additive: `SCHEMA_ID` stays `records-v1`, the JSON
  Schema gains the optional property, the review page's view of a record (built from the object) is unchanged.
- **Records v1.x: an external-source card writes its verb.** A card from `criminal_record`, `wwi_record` or
  `wwii_record` carries `written.verb` (`"criminal_record"` …), because the three take the same keys and
  `written` alone cannot say which was called. `Vocabulary.verbs` (verso-ru's `VERBS`) names a class's verbs;
  replay builds the card with the named factory. Additive: `SCHEMA_ID` stays `records-v1`, an export without
  `verb` still reads and replays when its keys fit one factory (else `ReplayGap`, as before), and no
  generated byte of the corpus moves — only the records export gains the key (and the review page's
  `record_view` of a card, which also carries `written.verb`; harmless to App 0.4.3).
- **Records v1.x: what a wrapper set lives in `written`.** A section's month and year
  (`birth_month_year()` and its kin), a `page()`'s provenance and flag, a `book()`'s name — the
  vocabulary's `context` — stand in the record's `written` under the attribute's own key (`birth.month`,
  `year`, `book`, `reviewed` …), and `written.context` lists the keys a wrapper set rather than the call;
  `derived` no longer holds them. A value the call wrote itself stays the call's (no marker): `birth(…,
  reviewed=False)` keeps its flag in `_written`. `split_context()` (`verso.core.records.fields`) splits the
  two; replay hands the factory the call's keys and sets the wrappers' values on the record it built, so
  `replay_file(…, context=False)` rebuilds the DSL's graph from `written` alone. Additive: `SCHEMA_ID` stays
  `records-v1`; an export of before (the values in `derived`, no marker) reads and replays as before
  (`context=True`). A consumer that edits a wrapper-set field edits it where the wrapper or the set holds it: the marker's
  entry stays. Only a key that a factory takes as a parameter can move to the call's side (drop it from
  `written.context`); a key no factory takes would be refused by decode and replay (`no_factory`,
  `param_spec`). Those are `book` and `inventory` on every metric kind; `archive` and `fund` on a marriage
  and a death; `church` on a death; `birth.month` and `baptism.year` on a christening; `case` on a
  census household. The review
  page's record (`verso.ru.dsl.view.record_view`) keeps v1.0's shape: `context_in_derived()`
  (`verso.core.records.encode`) moves those values back into `derived`, so the App reads `written` as the call's
  alone, as before; the JSON linters (`verso.ru.linters.on_json`) read the call's keys only.
- **Records v1.x: compatibility note.** A consumer validating against the closed `records-v1.json` of
  0.1.15 or earlier rejects the files this release writes when they carry `note`, `key`, `vocabulary`,
  `lang` or `written.context`, and every external-source card node, since it carries `verb`
  («'verb' was unexpected»); it takes the schema of this release. Old exports still read and replay
  (`docs/records-json.md`, «Compatibility and reading an old export»).
- **Records v1.x: `anchor.arg` names what the JSON names.** On the exported `note` of a record, `argument` and
  `field` anchors carry a person's persona slot as its id spells it (`godparent1`, `member3`) or the key of the
  argument in the node's `written` (`birth.day`), never the DSL's parameter name; an argument the node has no
  such name for makes the note the record's. A `range` keeps the wrapper's name.
- **The `#` notes of a DSL file, each with an anchor** (`verso.ru.dsl.notes.extract_notes`, internal — the
  facade is unchanged). A pure function of the file's text (`tokenize` and `ast`; the file is never run): every
  block of whole `#` lines (a blank line ends one) and every `#` at the end of a line, as `{text, anchor, lines}`.
  The anchor is `file` (outside the sets, above a set's first wrapper, beside a set's own arguments, any block
  not right above a record), `record` (the block on the line above a record's call, in its column and wrapper),
  `argument` (a block inside the call: the argument below, `member3` / `relative2` for a census person), `field` (a `#`
  ending an argument's line), or `range` — a group heading («№ 970–971», «(970–971)», or a range ending on the
  run's last number, within the record set of its first record; never «лл. 12–13») or a block above a later `page()` / `*_month()` or a `book()`, its
  `arg` the wrapper's name. A record is its place among the file's record calls in source order — the records
  export's order (`verso.core.records.ids.walk`); where the text cannot promise that (a record call outside a
  set's call, in a loop, comprehension or `def`, a factory under another name) every note is `manual` rather
  than bound to a wrong record, as is a trailing `#` on a line two records' calls share. Commented-out code (a block that parses and calls a function by an ASCII name, or imports or defines; prose that merely
  parses, «Восприемник: Петровъ», is a note), tool directives, a BOM, `#!` and the coding cookie are no
  notes; the text keeps its Markdown (only `# ` is taken off). The records export places them (above).

## 0.1.15 — 2026-10-28

### Changed

- **Counted nouns agree with their number**, in English («1 birth», «2 births») and in Russian («1 запись»,
  «2 записи», «5 записей»; «2 сословия в 2 записях» where it said «2 сословий»): a message that counts one
  thing is a table of plural forms on its `count`, one that counts two takes each as a phrase of its own
  (`counted.*` of verso-ru's catalogs). The facts checks' heads and spans, `export-records`, `svyatcy`,
  `echz`, `review-ratchet`, `estate-conflicts` and `facts-why`. A linter's message is left as it is: its
  params are its baseline key.
- **`claim-check` names a record's kind in the interface's language** — the English report said «смерть
  1890 № 5».
- **Plan hints run as printed**: `terraform show -json .plan > _plan.json` worked from no folder (`.plan`
  lies in `<village>/terraform/geni/`, `_plan.json` is read from `<village>/`). The detector, `verify-plan`,
  `merge-plan`, `moved-blocks`, `triage-unions` and the sweep's draft now print
  `terraform -chdir=<village>/terraform/geni show -json .plan > <village>/_plan.json`, and `merge-plan`
  without a plan says how to save one (`plan -refresh=false -out=.plan-fast`, where it said
  `terraform plan -refresh=false`, which saves nothing). `consolidation.plan` gives both lines
  (`plan_command`, `export_command`). The sweep's draft comments move.
- **A village or a path is quoted for a shell** in the hints of a stale records export
  (`verso export-records --village 'Две Тестовки'`), of a DSL v0 file and IMP001 (`verso upgrade-dsl`)
  and of `find-person` (`verso all-persons`), as `facts-snapshot`'s already was. IMP001's `path` param is
  the quoted path.
- The consolidation guide's section numbers that 0.1.13 left behind («§5», «§7», «§8», «§11.x» in `drift`,
  `tree-conflicts` and `merge-plan`) are gone; a test keeps shipped code free of them.

## 0.1.14 — 2026-10-28

### Added

- **CPL012** (advisory): a census member's written patronymic that the linked father's name cannot give —
  `parent_member=`, else a SON's or DAUGHTER's `ref_member=`. Only a contradiction: the names agree by the keys
  `father-claims` compares with, now `verso.ru.naming.fathers` for both, so a spelling the names table folds or a
  stem it lacks is silent; a mother as the reference and a `patr_old` that agrees stand it down. A corpus baselines
  what it keeps (`dsllint --update-baseline`).

### Changed

- **The review page labels the `status` field «звание» in Russian**, the word of the metric book's own column
  («Званіе, имя, отчество и фамилія…»), where it said «статус» (`ui.field.status`). The DSL's `status=`, the
  records JSON's field and every generated byte stay as they were.
- Hints that would not run as written now do: the baseline-v1 refusal and a baseline's header say
  `verso dsllint --baseline FILE --update-baseline --villages` (were `verso dsllint --update-baseline`,
  which asks for both); the keeper-pin refusal and `tree-conflicts --write` say that `verso verify-plan`
  reads a fresh plan exported to the village's `_plan.json`.
- `merge-plan`'s apply step is gated again: it printed a bare `terraform plan` / `terraform apply`, which
  typed from the workspace root reach no village's module and skip `verify-plan`; it prints the plan saved
  and exported in the village's module, `verso verify-plan --village …` and `terraform apply .plan`.
- `facts-snapshot` quotes a village of two words for a shell, in its hint and in the header of
  `facts_findings.tsv` (`--village 'Две Тестовки'`): the header of such a village's snapshot moves.
- Texts the label removal of 0.1.13 left broken are mended: `name-variants`' description (a line that
  began «. Read-only»), `find-person`'s hint that named one command twice, a double space in the
  keeper-pin refusal.

## 0.1.13 — 2026-10-28

### Changed

- **Messages name the library's commands, not a corpus's Makefile**: a hint that said `make tf-generate
  village=X`, `make review-ratchet-prune`, `make facts-snapshot`, `make db`, `make export-records`,
  `make tf-consolidate-verify` … says `verso generate-tf --village X`, `verso review-ratchet --prune`,
  `verso facts-snapshot`, `verso all-persons`, `verso export-records`, `verso verify-plan`; a terraform step
  says the `terraform` command; «make bootstrap» says «reinstall the environment's packages». In Russian too, so
  under `locale = "ru"` these lines read otherwise than in 0.1.12: `stale`'s and `moved-blocks`' regeneration
  hints, the review ratchet's «the list lags behind», `merge-plan`'s plan and apply lines, the facts
  snapshot's header (`facts_findings.tsv` — regenerate it), `find-person`'s village.db hints, the plugins'
  refusals, the records export's stale hint and the lexicon trace's refusal.
- The consolidation channels' «a SIGNAL, not a verdict» lines (`reconcile`, `union-duplicates`,
  `split-couples`) no longer point at a section of a corpus's guide.
- The labels of the plan that split the library out are gone from the code, the tests, the tools and the docs: a label that
  dated a change names the release, one that gave a reason gives it. `tests/repo/test_public_texts.py` holds
  that no label, no pointer into a corpus's guides and no Makefile target in the shipped code comes back.

## 0.1.12 — 2026-10-27

### Changed

- **verso-ru speaks through its catalogs alone**: the commands' errors and help, the facts reports, the
  consolidation channels' reports and the reasons their guards give, the importers' refusals, the linters'
  own messages, `dsl-surface`, `upgrade-dsl`, `stale-notes` and the archives' client — 417 keys added to
  `verso.ru`'s catalogs, the Russian moved verbatim, so under `locale = "ru"` every command says what it said.
  Its interface ratchet (`tests/ui_text.tsv`) is at zero: what Cyrillic is left in the code is the sources'
  own — the words a record is matched against, the sheets' columns, what a command writes into a corpus's
  files — declared in `tests/ui_content.toml` or marked `# i18n: content`. Two tests hold it: the linters
  find the same under English, and no message is told by its text.
- A list neighbour's kinship (`verso.ru.facts.checks.neighbours`: `SPOUSE`, `PARENT`, `CHILD`) is a code
  now — `spouse`, `parent`, `child` — worded by the report; `reconcile --json` writes the code.
- `verso.ru.facts.model`'s text — a date's, a citation's, `why()` — is what `facts.jsonl` writes, and stays
  Russian under any interface language.

## 0.1.11 — 2026-10-27

### Added

- **Records rebuilt from `written` alone** (L10, part 1): `verso.core.records.replay.replay_file(data)` builds a
  records-v1 file's record sets by calling the DSL's own factories with what each node wrote, bottom up — no
  source read, nothing `exec`'d — so every value a constructor or a set's factory derives is derived again;
  `decode_file` keeps taking them from `derived`. What a wrapper sets and no call writes (a section's month,
  a sheet's provenance, a book's name) v1 keeps in `derived` alone: the vocabulary names those attributes
  (`Vocabulary.context`, the plugin ru's `CONTEXT`), and replay reads them, or nothing with `context=False`.
  A node that fits no factory, or several, raises `ReplayGap` (`records.replay.no_factory`,
  `records.replay.ambiguous_factory`; a list the chosen factory has no place for, `records.replay.no_list`): a
  card's three verbs (`criminal_record`, `wwi_record`, `wwii_record`) take overlapping keys, and v1 does not
  write which one built it. A node the schema would refuse is a `FormatError` (`records.replay.malformed`). `ClassSpec.factory_for(keys)` and `factories_for(keys)` name the factory. Nothing
  reads replay yet: the output of every command is the same as 0.1.10's.
- **The linters' readiness for records JSON** (L10, part 2): `verso.ru.linters.hosted.readiness()` reads
  `hosted.toml`, a row for each of the 92 codes — its class (`written` 42, `derived` 21 — among them the 19
  redundant-kwarg codes, a written value equal to the one it inherits —, `context` 25, `source` 4: what it needs
  once there is no DSL source), its severity, what a `context` code needs (the
  names tables, the places, the estates, the book) and a line of what it reads. `verso.ru.linters.on_json.
  lint_records(data, codes=…)` lints a records-v1 file node as `dsllint` lints its source — the same codes
  and params, a finding addressed by its record's id — for the pilot, CPL002 and ULC001; any other code is
  refused by name (`on_json.unsupported`). The count can differ where a `person()` is bound once and used in
  several records (one call there, one persona per record here).

## 0.1.10 — 2026-10-27

### Fixed

- The tests of a civil registry book (0.1.9) used a surname that a corpus's books hold. A corpus's
  public-tree scan refused the release, so the surname is now an invented one. Only tests change: the
  output of every command is the same as 0.1.9's.

## 0.1.9 — 2026-10-27

### Added

- **A book of the civil registry:** `birth_records(…, civil=True)`, and `death_records`, `marriage_records`
  alike (`DSL_API` stays 1: a new keyword with a default). A ZAGS book records the same events with the
  same people; its second date is the registration. With the flag the translator emits no baptism or burial
  event from it, titles the documents «Книга ЗАГС …» and the about sections «ЗАГС …», and prints «Дата
  регистрации» (only for a day written) where a parish book prints «Дата крещения» / «Дата венчания»; the
  Familio CSVs leave the christening and burial columns empty and write «зарегистрировано Д.М.Г» into the
  comment (the burial's «пометки»); the facts layer asserts no `BaptizedOn` or `BuriedOn`, and the sweep
  reads no burial. Each record carries the flag as `civil`.
- records-v1: `civil` on births, marriages, deaths and their record sets (default `false`, so a parish
  book's JSON is unchanged); ui-v1: a book flag `civil` (`ui.book.civil`) of the three books, hidden on
  their records.
- **Linters for a civil registry book** — `civil_register` (hard: ZGS001 a godparent, surety, clergy or
  `christening()` in a civil book; ZGS002 a civil birth registered before it was born) and
  `civil_register_advisory` (ZGS003 a book of 1918 on with no church and no `civil=True`; ZGS004 an estate
  of the old order in a civil book; ZGS005 a name in the old orthography in a civil book). `civil=True`
  before 1917 is no finding: the Old Believers' police books (1874) and the Kingdom of Poland's acts are
  civil registrations too. DBD001 says «registration … precedes death» in a civil book
  (`DBD001.registration_precedes`).

Without `civil=True` in a corpus the output of every command is unchanged. dsllint is not: a corpus's
churchless books of 1918 on are ZGS003 (advisory) until they say `civil=True`; the hard checks fire only
inside a civil book.

## 0.1.8 — 2026-10-26

### Fixed

- `stale-notes` hid a note that writes the old reading as «already corrected» when the part of the name the
  proofread kept stood in it: «Фома Фомичъ Опискинъ» → «… Ростаневъ» took the note's own «Фома Фомичъ»
  for the new reading beside the old. Only a pair the new name writes and the old did not counts.
- A surname added to a person is written as its file writes surnames: by `last_name_orig=` in a file that
  names them more often than it writes them third in place, where it always took the next positional
  place; a person created in such a file names its surname too.

The output of every command is unchanged.

## 0.1.7 — 2026-10-26

### Added

- `ui-v1`: a record's own field may name its one-click adder, `quick`, as a slot does — the label of the
  button a page offers while the record neither writes the field nor takes it from its book's defaults.
  The ru plugin's burial offers «+ причина смерти» (`ui.quick.cause_of_death`). A person's, an item's or a
  book's field naming one is refused (`records.ui.quick_not_here`). The key is optional: a page that does
  not read it draws what it drew.

The output of every command is unchanged.

## 0.1.6 — 2026-10-26

### Fixed

- An age a page's edit sets to a whole number of years — «4», «5 лет» — is written as the integer AGE001
  asks for (`age=4`), where it was written as text and the edit was rolled back on the new finding. The
  rule is one, `verso.ru.ages.whole_years`, which AGE001 reads too; «4 мес», «полгода» and a compound age
  stay text, and a roll's ages, which AGE001 does not read, are written as typed.

The output of every command is unchanged.

## 0.1.5 — 2026-10-26

### Fixed

- `verso.ru.dsl.view.value_at` answers None for a path that names no item — a slot or a group without its
  number, or with a word in its place — as for a slot nobody fills, where it raised.
- `verso.core.i18n.categories` looks a pack's language up once, not for each of the 200 numbers it asks.
- A plugin's hints cannot rename the package its labels are keys of: the declared package wins over a
  `package` written in `ui-hints.toml`.
- `ui-v1.json` is read once per schema package, as the workspace's vocabulary names it, where
  `verso.ru.dsl.paths` kept the first one a process met and `view.value_at` read it on every call.
- Two `CallView`s that differ only in `splat` are not equal; `paths`' unreachable `number` type is gone.

The output of every command is unchanged.

## 0.1.4 — 2026-10-25

### Added

- `verso ui-schema` (`--check | --write`), the command of `verso.core.records.ui`, as `records-schema` is of
  the records JSON's schema: every module of the core that runs as a program is a command.

The output of every command is unchanged; `verso --help` lists the new one.

## 0.1.3 — 2026-10-25

### Added

- `ui-v1.json`, the review page's schema, built from the vocabulary and the plugin's hints
  (`verso.core.records.ui`, `Plugin.ui`, `plugins.ui()`); verso-ru's hints as data
  (`verso/ru/records/ui-hints.toml`) and their labels, `ui.*`, in both languages. A field's place
  in a person's row is a flag of the hints: `column` (the people's table), `line` (shown on every
  person), `suggest` (suggested as typed).
- `verso.ru.dsl.paths`: an edit addressed by the records' own names (`birth.day`,
  `godparent/2/given.original`, `members/3/age`) and a typed value, turned into the edits
  `source.apply` writes (`translate`, `path_of`, `opaque`, and `field_of` — the schema's field at a path,
  what its value is typed by); a refusal is a `PathError` with its key (`paths.*`). `source` moves an item
  of `relatives=[…]` (`#k`) as it moves a member.
- `verso.ru.dsl.view`: one record as the review page reads it — the export's record
  (`verso.core.records.encode.encode_record`), the constants its source names, the paths no schema
  can edit, its version — and `value_at`, a path's value.

### Changed

- The first read of a catalog (`verso.core.i18n`) is under a lock: threads asking at once read it once.
- `verso.core.i18n.use()` keeps its language per context (a `ContextVar`): two threads, or two tasks,
  each in a `use()` of their own speak their own.
- A refusal of `verso.ru.dsl.source` (`EditError`, `Stale`) carries its message's `key` and `params`
  (`source.*` of verso.ru's catalogs) and is said through the catalog; the Russian text is the one it
  said before.

### Fixed

- `relatives=[…]` keeps each note with its person: a move is refused when the last relative carries a
  note after its trailing comma (libcst keeps it before `]`, where a move would hand it to whoever comes
  last), and a relative added after it leaves the note on its line; an added relative no longer copies
  the comment line of the list's first separator.
- `ui-v1`'s build refuses a rule naming a path, a group or an event the kind lacks
  (`records.ui.unknown_path`), as it refuses a field: the page writes by the rules.
- `verso.core.pipeline.load.import_problem` ran its child with the caller's environment, and one that
  forces colour (`FORCE_COLOR`, as a desktop app may set it) put escape codes in the error's text; the
  child runs with colour off.

The output of every command is unchanged.

## 0.1.2 — 2026-10-24

### Fixed

- An invented surname in the tests (the patronymic-form tests and two frozen linter samples) came to
  be written by a real corpus; it now spells another invented one of the same length, so a corpus's
  public-tree scan finds nothing in the library.

The output of every command is unchanged.

## 0.1.1 — 2026-10-23

### Added

- `py.typed` (PEP 561) in verso-core and verso-ru: a strict type checker reads the installed library's
  annotations instead of asking for stubs.

### Fixed

- `verso.ru.dsl.describe` re-exports `RECORD_FUNCS` explicitly, as a typed package must for a name it
  hands on.
- A frozen linter sample spelled a name a real names table may come to hold; it now spells an
  invented one, so the sample's finding does not depend on whose table the tests run on.

The output of every command is unchanged.

## 0.1.0 — 2026-10-22

### Added

- The DSL's facade v1 (`verso.ru.dsl`, `DSL_API = 1`) for metric books, revision lists,
  confession lists, name lists and external-source cards, with its catalogs of statuses, causes of
  death and marital statuses.
- The workspace (`verso.toml`, `village.toml`, the corpus's data files) and the plugin registry
  (`verso.plugins` entry points); the plugin `ru`.
- The `verso` command: generating Geni's Terraform and Familio's, CSVs, the records JSON (v1:
  neutral field names — events with dates, names `{original, modern}`; ids by rule `r1`), the timeline; the DSL linters (`verso dsllint`); the facts layer and the
  consolidation checks; the review ratchet.

### Notes

- Python 3.14 and 3.15.
