# Records JSON

The built records, written out as JSON without loss and read back in their place — the way to
the records without running Python (`verso.core.records`, schema v1).

```sh
verso export-records --village V [--out DIR]   # records/<village>/<YYYY>/<file>.json + index.json
verso records-schema --check | --write | --validate DIR
```

## What is written

One JSON per DSL file: documents (record sets) → page runs → records → personas with roles
(`child`, `godparent2`, `member4`, …). Every node has `written` — the arguments its DSL call
passed, evaluated (a constant is its text) — and `derived`, every attribute the built object holds
besides: a surname inherited, the book's default status, the section's month. Enum values are
English codes (`male`, `daughter_in_law`).

Field names are neutral (schema v1): a field keeps its DSL attribute's name unless the vocabulary
names its JSON key otherwise (`json_names`). Three rules make those names:

1. an event's day, month and year are one object — `birth`, `baptism`, `marriage`, `death`,
   `burial`, `divorce`, `record`, a roll member's `arrival` and `departure`: `{"birth": {"day": 3,
   "month": "january"}}`; a record's and a book's `year` stays `year`;
2. a name's forms are one object — `given`, `patronymic` (with `old`), `surname`,
   `maiden_surname`: `{"given": {"original": "Петръ", "modern": "Петр"}}`;
3. no abbreviation is left — `record_num` is `number`, `groom_marriage_num` is
   `groom_marriage_number`.

A group is one level deep. A person's slot has no key: it is a persona, named by its role, so the
ids do not follow the names. In `written` a field stands under its key when its attribute is renamed,
else under the parameter's own name. Schema v0 — the DSL's names — is read no more: an export
written before v1 is stale (`verso export-records` writes it again). The schema carries no interface
text; a field's or an enum's label is a key of the catalogs.

One table — the plugin's vocabulary — names every attribute of every DSL class; the encoder refuses
an attribute it lacks, so a new DSL field fails a test until it has a row, and then
`verso records-schema --write` writes `records-v1.json` again.

## Additions to v1 (all optional; `SCHEMA_ID` stays `records-v1`)

Every item below is additive: a reader that ignores unknown keys reads the new files, and the new
reader reads old files.

- **`verb` on an external-source card.** A card from `criminal_record`, `wwi_record` or `wwii_record`
  writes `written.verb`, because the three take the same keys. Replay builds the card with the named
  factory (`Vocabulary.verbs`); an old export without it replays when its keys fit one factory.
- **Wrapper values in `written`, and `written.context`.** What a wrapper set on a record — a section's
  month and year, a `page()`'s provenance and flag, a `book()`'s name — stands in `written` under the
  attribute's own key. `written.context` lists those keys (flat, as they stand in `written`); a value
  the call wrote itself is the call's and is not listed. `derived` no longer holds them. Replay hands
  the factory the call's keys and sets the listed ones on the record it built, so a file replays from
  `written` alone. A consumer that edits a wrapper-set field edits it where the wrapper or the set holds it: the marker's
  entry stays. Only a key that a factory takes as a parameter can move to the call's side (drop it from
  `written.context`); a key no factory takes would be refused by decode and replay (`no_factory`,
  `param_spec`). Those are `book` and `inventory` on every metric kind; `archive` and `fund` on a marriage
  and a death; `church` on a death; `birth.month` and `baptism.year` on a christening; `case` on a
  census household.
  The review page's record (`record_view`) keeps the old shape — the wrapper values back in `derived`,
  `written` the call's alone — so the page is unchanged.
- **`written.wrapper`: a wrapper's value beside the call's own** (0.1.20). Where a record's call writes a
  field a wrapper around it also gives — `page="12"` inside `page("11", …)`, a record writing its months
  (or its year) inside a `*_month(…)` / `*_month_year(…)` section — the call's value stands, as in the DSL,
  and the wrapper's is kept under `written.wrapper`, grouped as `written` is: `{"page": "11"}`,
  `{"birth": {"month": "march"}, "baptism": {"month": "march"}}`. It says where the record stands: the
  `page()` around it, the section it is in (a christening's month is the one the section would have dated,
  a day before the birth's rolling it into the next month). Only the leaf of a `page()` and the month and
  year of a section are kept — not a `page()`'s provenance or flag, nor a `book()`'s name. The innermost
  wrapper's value is the one kept; a key the call did not write, or one no wrapper sets, is refused
  (`split_wrapper`). Replay and decode change no value by it and keep it on the record (`_wrapper`); the
  page run is the record's own leaf, as before. `record_view` drops it, as it does `written.context`.
- **`key` on a record node.** Optional, a non-empty string without `/`: the record's own key that
  outlives a corrected number or sex. It is a property of the stored node: the encoder never writes it,
  decode and replay ignore it, ids (`r1`) do not read it, and rebuilding a node from objects drops it —
  code that does so (a backend that stores nodes) copies it from the node it replaces.
  `verso.core.records.schema.check_keys(doc)` names the paths of two records sharing a key; decode
  refuses a malformed one.
- **`vocabulary` and `lang` in the file header.** `vocabulary` is `{"plugin": "ru", "version": 1}` — the
  plugin whose vocabulary the records are written in and its version — and `lang` the book's default
  language (BCP 47, `"ru-Cyrl"`). The plugin declares them (`Plugin.vocabulary`, `Plugin.default_lang`);
  a core without such a plugin writes neither. Decode refuses a vocabulary version newer than the
  enabled plugin of that name reads, naming both. The header is informational until a second plugin
  exists: a file naming a plugin that is not enabled is read with the enabled plugin's rules.
- **`note` on the file node and on record nodes.** The `#` comments of the DSL file, a list of
  `{"text": …, "anchor": {…}}` (the text is Markdown). `anchor.to` is one of: `file` (on the file node);
  `record` (the record below the comment); `argument` (an argument of a record's call or a person, `anchor.arg`); `field` (a comment at
  the end of an argument's line, `anchor.arg`); the `arg` of both is what the JSON names the argument:
  a person's persona slot as its id spells it (`godparent1`, `relative2`, `member4`), else the key of the
  argument in the record node's `written` (`birth.day`, a group's key dotted as `written.context` writes
  it) — a note whose argument the node has no such name for is the record's (`record`); `range` (on the
  first record of a run, `anchor.end` its last, `anchor.arg` the wrapper's name — `page`, `book`, `…_month` — for a wrapper's lead);
  `manual` (a note nobody bound, on the file node). A record is its place among the file's record calls in
  source order, the export's order. Binding, in short: a block directly above a record call, in its
  column and container, is the record's; the lead above a set's first wrapper is the file's; a block
  above a later `page()`, a `*_month()` or a `book()` is a range with that wrapper's name; a group heading
  (a range of numbers or in brackets) is a range over the run, never past the last record of the record set
  (the `*_records(…)` call) of its first record. Commented-out code is no note: a block that parses as Python
  and calls a function by an ASCII name (`birth(…)`) or imports or defines (`import`, `def`, `class`) is
  left out; prose that merely parses («Восприемник: Петровъ», «TODO: recheck», «Иван = Пётр») is a note. A `#` at the end of a line that two records' calls share is `manual`, not guessed. Where the text cannot promise the order
  (a record call in a loop, a comprehension or a `def`, a factory under another name) every note of the
  file is `manual`. The core also checks the plugin's counts: if the plugin's record count, or the number
  of a record at some place, is not the export's, no note goes on a record — each goes on the file as
  `manual` and `Exported.unbound` names the file and why. Notes are invisible to replay and to the
  graph; the encoder never writes them, and editing a comment makes the export stale like any DSL change.

## Compatibility and reading an old export

A consumer that validates against the **previous** closed `records-v1.json` rejects a file carrying
`note`, `key`, `vocabulary`, `lang`, `written.context` or `written.wrapper` (the schema is closed on those
nodes), and
every external-source card node, since it carries `verb` (the 0.1.15 schema says «'verb' was
unexpected»): take the schema from the release that writes them (`verso records-schema --write`).

An export written before these additions reads as it always did: no `vocabulary`/`lang` means none is
checked; wrapper values found in `derived` with no `written.context` are read as the wrapper's
(`context=True`, the default of `replay_file`, which also handles a value the call wrote and a wrapper
later changed; `context=False` rebuilds from `written` alone and is for files whose context is in `written`); a card without `verb` replays when its keys fit one factory, else `ReplayGap`. To get the new
keys into an old export, export again (`verso export-records`).

## A book without a DSL source

A book started where no DSL file exists — on a review page — is a records JSON from its first day.
`verso.ru.records.blank.blank_book(BookSpec(...))` writes it: one document and no pages, made by the record set's own
factory (`birth_records`, `marriage_records`, `death_records`) without any record and without `reviewed`, so what is
typed into it is read as it is typed. Replayed, it is the object the factory builds.

- `sha256` is `""`: «there is no DSL source». It is the sign of such a book, and no reader compares it with a file.
- `file` is the path the DSL file would have had, `<year>/<kind>_<fund>-<inventory>-<case>[_<part>].py`; nothing is
  there. The schema does not change.
- The book lies at `book_path(spec)`, `<locality>/<year>/<kind>_<fund>-<inventory>-<case>[_<part>].json`, the variable
  being `<kind>_<fund>_<inventory>_<case>[_<part>]`. A metric book's id has no part (rule `r1` takes one from a roll's
  `archive_suffix` alone), so `part` only tells two books of one shelfmark apart in the path.
- `BlankError` refuses a year outside 1700–1930, an empty fund, inventory or case, an empty parish, a `/`, `\` or `..` in
  a field of the path or in the parish (which the id writes between its `/`s), a path field (fund, inventory, case, part, locality) or the parish with spaces at its ends or a
  control character, a locality that is empty, `.` or `..`, defaults the record set does not accept, and a kind that is not
  births, marriages or deaths. It is a `ValueError`: `str(exc)` is the message in the library's language, `exc.key` the
  catalog key and `exc.params` its parameters, for a caller that says it in its own language (`BlankError(key, message)`
  with a ready message still works, `params` then empty):

  | `key` | `params` |
  |---|---|
  | `records.blank.kind` | `kind` |
  | `records.blank.year` | `year` |
  | `records.blank.shelfmark` | `fund`, `inventory`, `case` |
  | `records.blank.parish` | none |
  | `records.blank.path` | `value` — the offending field |
  | `records.blank.defaults` | `error` — the record set's own refusal |

## Ids — the rule `r1`

A record is named as it is cited:

```
r1:<village of the book>/<fund>-<inventory>-<case>[;<part>][/<year of the book>]/<kind>/<m12|f23|12>
```

a persona as the record's id with its slot (`…/godparent2`), a repeated number with `~2` in export
order, a record with no number `_1`, a card `r1:<village>/card/wwi/<key of its catalog address>`.
A corrected name moves no id; a corrected number, sex or shelfmark does. `~k` and `_k` are counted
in export order (years, files by name, records in file order). `r1` versions the rule, not the
schema. The facts layer names its personas by the same ids, and the review page takes one as a
link.

## Reading the export in the DSL's place

`VERSO_RECORDS=<root>` makes the pipeline read each file's record sets from its JSON: every reader
of the corpus reads the export unchanged. A stale export stops the program — a DSL file changed,
added or removed since; a JSON missing, broken or from another export; another schema; or a changed
input of the derived values (the names tables, the review list, the corpus's statuses — `statuses.toml`, or
`statuses.py` with the library's code). Set it per
command, never `export` it; Terraform generation refuses it outright and is built from the DSL only.

### The index (`index.json`)

Each village's export has an `index.json` beside its years: `schema`, `village`, `files` (each DSL file's
path in the village → its SHA-256), `skipped` (a file that did not load → why) and `inputs`, what the derived
values rest on besides the DSL, each key → its file's SHA-256 (`""` for a file that is absent):

- `code` — the library's code (the core's and each enabled plugin's packages) and, where the corpus holds its
  statuses as a module, its `statuses.py`;
- `unreviewed_on_geni.tsv` — the village's review list, in the village's directory;
- `names/<table>` — each names table, in the workspace's `[names] dir`;
- `corpus/statuses.toml` (0.1.20) — the corpus's statuses as data, in the workspace's `[corpus] dir`; the key
  stands only where the file does, so an index of a corpus without it reads as before.

A reader that checks an export against its source resolves each key by that list. `corpus/statuses.toml` lies
under the corpus directory, not under the village: verso-app 0.5.1's importer read every key but `code` and
`names/…` as `<source>/<village>/<key>`, so an import with a source root from a corpus holding `statuses.toml`
read as stale (fixed in verso-app 0.5.2).

## A single record

`verso.core.records.encode.encode_record(record, record_id)` writes one record as the export writes it
under its record set — the export writes each record through it. The review page's view of a record
(`verso.ru.dsl.view.record_view`) is that record and three things the JSON does not say: `consts`, the
paths the source writes as a constant of a catalog (`{"mother/status": "PEASANT_WIFE"}`); `opaque`, the
paths it writes as an expression (`relatives=ROWS`, `age=2 + 3`), which no edit reaches; and
`version`, the hash of the record's call. `value_at(record, path)` reads one path of a record:
`written` where the source writes it, else `derived`.

A record that has no source — only its JSON node, as a folder of records JSON keeps it (`written` alone,
no `derived`) — is viewed by `verso.ru.dsl.view.node_view(built, node, record_id)`, with `built` the object
`replay_file` made of the node. It gives the same `record` and `consts`, read off `written` by the catalogs
(a status or a cause is a constant when the JSON holds it as an object; of constants that spell one text the
one that sorts last, as the linters on JSON name it), an empty `opaque` (there is no expression in JSON) and no
`version`: a store keeps its own. A constant the file defines itself, or a marital status written as text,
is not told from a literal. A file-level alias of a catalog constant (`GM = GOSUDARSTVENNYJ_PEASANT_MALE`, then
`status=GM`) is not told from the constant either, and the JSON keeps only its text: `consts` names
the constant that sorts last of those that spell that text (`STATE_PEASANT_MALE` here), which is not always the one
the alias names, and never a literal.

## A record on its own

A store that keeps one record per row rebuilds and checks ONE record per edit, not its book. A record is a
function of three things: its `written`, its record set's header (the set's node without its `pages` — its `written`
holds the book's defaults, the parish, `civil`, `reviewed`) and two counters its place in the set gives it. So the
store needs to know, for each record, the header, the leaf the record stands on (`page`) and its `Position`.

```python
from verso.core.records.replay import Position, position_values, replay_record

record = replay_record(node, header=header, page="12об", position=Position(ordinal=4, members_before=17))
position_values(node, position=Position(5, 21))     # {"index": 6}, or {"members[0].record_number": 22, …}
```

`replay_record` builds the record through its set's own factory, so the book's defaults, the clergy's parish and the
`on_geni` mark apply as in the book, and then sets the counters. The result equals the record `replay_file` makes of the
same node inside its book, once the position is given.

The counters are the whole of a position. `Position.ordinal` is the record's 0-based place among the records of its set,
in the order of the export; it gives a list entry's and a card's `index` (`ordinal + 1`). `Position.members_before` is the
running number a roll has reached before this двор — a household's members are numbered across the roll (№ п/п): a
hidden member takes no number, a member that writes a whole `record_number` of its own keeps it and the count goes on
from it. `position_values` gives the same numbers as paths in the record's `derived` (`"index"`,
`"members[3].record_number"`, a member's place counted from 0) without building anything, and gives nothing for a
member that wrote its own.

A position changes only by a structural act — inserting, removing or moving a record, or editing a member's whole
number: an edit that changes no record's place changes no other record's counters. After the act the store rewrites the
counters of the records after the one acted on, which is what `position_values` is for. Nothing else a record holds
depends on its neighbours.

## The interface's schema

`ui-v1.json`, beside `records-v1.json`, says how a page draws and edits a record: for each kind
of record its fields in order, each with its `path` (its JSON key), its `type` (the vocabulary's:
`text`, `integer`, `boolean`, `age`, `enum`, `catalog`, `ref`) and its `label`; its people's slots
(`godparent` 1–4), the slot a record's field is drawn beside (`row`), the one-click adder a slot or a
record's own field offers while the record has none (`quick`, its words a label: «+ восприемник»,
«+ причина смерти»), its lists of entities as groups
(`relatives`, `members`) with their items' fields, its dates (`events`), and what a new record opens
with (`draft`); a person's fields; each enumeration's members with their labels; a book's fields, its
defaults and its flags. A label is a key of the plugin's catalogs (`ui.*` of `verso.ru`), never a text:
the page renders it in its language.

It is built, not written — from the vocabulary and the plugin's hints, `verso/ru/records/ui-hints.toml`
(`Plugin.ui`), which give the order, the labels and what the vocabulary does not say — and checked
against them: `python -m verso.core.records.ui --check` (`--write` after a change). A field the
vocabulary gains fails the build until the hints place it or hide it.

A path addresses one value of a record: a record's field is its key (`birth.day`), a person's field
`<role>/<field>` (`groom/given.original`) or, in a numbered slot, `<role>/<slot>/<field>`
(`godparent/2/surname.original`), and an item of a group `<group>/<n>/<field>`, `n` its place in the
source from 1 (`members/3/age`; its person's fields `members/3/person/given.original`).

## Linters on records JSON

`verso.ru.linters.on_json.lint_records(data, codes=…, workspace=…)` lints a records-v1 file node as
`dsllint` lints its DSL source, code by code: the same code, variant and params and the same token, a
finding addressed by the id (rule `r1`) of its record — or of its book, for what the book writes —
instead of a line. A held record (`reviewed=False`) is linted like any other. It is for a reader that
has the JSON and no file; `dsllint` stays the check of the source.

```python
from verso.ru.linters import on_json
found = on_json.lint_records(data, codes=on_json.SUPPORTED, workspace=root)
# [Finding(code, variant, record, params, token, level), …]
```

`codes` is a collection of codes, not a `str` (`TypeError`: «NAM001» would ask for six codes). When it asks for
any, the input is checked first, as `replay_file` checks it: anything but a mapping of schema `records-v1`
with a list of documents (each a mapping), or with a header vocabulary newer than the plugin's, is a
`FormatError`, for a code that reads no replay too. A v0 export, `{}` or a list never reaches a rule.

It answers every code of `hosted.toml` (93) except the four that are the form of the source text.
`on_json.SUPPORTED` lists the 85 codes that have a rule: the 89 that are not `source`, less the four
positional ones that fold into a keyword code (below). `hosted.toml` gives each code a class, a level
and what it needs, and marks the 19 whose finding is a redundant argument — a written value equal to the one
the record inherits — with `redundant = true` (`hosted.readiness()[code].redundant`; every one is `derived`,
the positional codes folding into one included).

### One record, one set

`lint_record(node, header=…, page=…, position=…, codes=…, workspace=…, file_in_scope=…, run_levels=…)` runs the same
rules over one record and its set's header (the record built alone, see «A record on its own»), and
`lint_header(header, codes=…, workspace=…, file_in_scope=…)` over a set's header. Every finding of a file is addressed to
a record or to a set, so the findings of `lint_record` over a file's records and of `lint_header` over its sets are
those of `lint_records` — by code, variant, params, token, level and id. `hosted.toml` gives each code a `scope`
(`hosted.readiness()[code].scope`): `record` (87 codes — one record, or one двор, with its set's header; the findings the
same rule addresses to the book, like a default status written in the old orthography, are `lint_header`'s), `set` (ZGS003,
a finding about the header alone: `lint_record` refuses it by name), `file` (ULC001, which fires only in a file where some
set names a parish the corpus's places know: `lint_record` and `lint_header` take that one fact as `file_in_scope`, which
`places.file_in_scope(headers)` computes from the file's set nodes) and `source` (the four codes about the text).
RVR001 is the one code whose finding on a record reads other records: a record's own `reviewed=` is redundant only
if its page run holds an unflagged record built with the set's level, so it reads the review levels of the record's page
run. A store passes them as `run_levels` (the `reviewed` the run's other unflagged records are built with; an empty
collection when the run holds none), and `lint_record` refuses RVR001 asked without it (`Unsupported`,
`on_json.needs_run_levels`) rather than answer from a run it cannot see. So "a record is the unit" holds for linting
except here: when one record's review level changes (its `reviewed=` written or removed, a `page()` flag), re-lint the
records of its page run for RVR001 only — the findings of every other code stay with the record.

### Four classes

- **`written`** (42) — what one record's calls wrote, read from the node's `written` by the factory's
  parameter (`FileView.written`: v1's grouped, renamed keys back to the parameters), and the library's
  own tables.
- **`derived`** (21) — what the factories and the wrappers derive: a death's days from its section, an
  argument written equal to what the book's defaults or the family give (the redundant-kwarg codes), a
  record's `reviewed=` equal to its record set's. The rule reads the objects `replay_file` builds from
  `written` alone (`FileView.replayed`), once per file. An export without `written.context` (from before
  0.1.16) is refused (`Unsupported`, `on_json.no_context`), and so is a file no factory can rebuild
  (`on_json.not_replayable`). The refusal does not discard what the call could answer: the `Unsupported` carries
  `findings`, those of every requested rule that reads no replay, leveled as a call that succeeded levels
  them, and `unanswered`, the sorted requested codes whose rules asked for the replay and were refused. A code is
  in `unanswered` exactly when asked alone it is refused; a derived code whose rule has no record to read in this
  file is answered (with nothing). A returned list is therefore whole, and a refusal is the only report of what
  is missing.
- **`context`** (26) — data outside the record: the book (a record set's `written`: its village, year,
  `civil`, defaults), the corpus's estates and places, the names tables. The
  row's `needs` says which of `names`, `places`, `estates`, `book`, `file` the code reads. A code of another class
  that asks the names table all the same — it reads a name, or replays the file, which builds its
  persons from the table — says `names` too.
- **`source`** (4: SLC001, SLC002, CML001, IMP001) — the form of the source text, which a file has and
  the JSON does not. `lint_records` refuses them by name (`Unsupported`, `on_json.source_code`); so it
  does a code of no row or no rule, that is, no such linter code (`on_json.unsupported`). A code is never skipped
  quietly.

### Levels

A finding's level is its code's severity in `hosted.toml`: `refuse` (a hard check of `dsllint`) is
`"error"`, `warn` (an advisory one) is `"warn"`. Two cases lower an `"error"` to `"warn"`, because
what the rule found rests on a partial reading:

- **No names table (H7).** A workspace that configures no names lexicon (no `[names] layers`, and no `names.csv` in a file of schema ≤ 5) gives a code whose `needs` holds `names` a
  warning, never a raise. A name the rule cannot look up is taken as valid, a sex as not known, a
  patronymic as agreeing, so the finding that rests on it is not made — and a rule that needs the
  replay finds nothing more (`NoReplay`: the persons it builds are validated against the table). Any
  other workspace error — no workspace at all — still raises.
- **No estates.** The same for a code that needs `estates` in a workspace without the corpus's
  `estates.toml`: it has no landlord, owner alias or parish rule to read.

### Positional codes fold into their keyword code

The export keeps a call's arguments by parameter, so it cannot say whether an argument was written by
position or by keyword. A code that tells the two forms apart answers as one on JSON: `hosted.toml`'s
`as` names the keyword code a positional one folds into — BRD002 into BRD001, BRD004 into BRD003, CRD003
into CRD002, CRD006 into CRD005 — and `forms` the variants of the source that the JSON speaks as the
keyword's (`said` → `read`, params renamed or unquoted; DRA002's `redundant_positional` is its
`redundant`). `hosted.fold(code, variant, params)` applies them to a finding of the source: the one
place where the two forms are one. `lint_records` and the oracles read the same table: the oracles fold the
source's findings through `fold`, `lint_records` asks the keyword code through each row's `as_code`. A folded code asked
for answers its `as` code's findings, spoken as that code: `codes=["BRD002"]` returns BRD001 findings,
never a silent empty list.

### The workspace is an argument

The tables a rule reads — the names, the estates, the places, the landlords' statuses — are those of
`workspace=`, entered for the call; `None` is the current workspace. A name is unknown to the table of the
workspace the file is linted in, which is not always the one that wrote it. A hosted caller passes its workspace explicitly, so
a finding never depends on an ambient one.

**Calls are not thread-safe.** Entering a workspace pushes it on a process-global stack
(`verso.core.workspace.use`), and the tables of status constants are cleared through a process-global hook
(`workspace.on_change`): two calls at once, in threads of one process, can read each other's workspace. Serialise
the calls, or run one per process.

### Where the JSON and the source differ

Same codes and params, not always the same count or the same name in a fix. Each class below is spelled
out, with its reasons, in the docstring of the module that holds it (`verso/ru/linters/on_json/`), and
none is in a real corpus today:

- *Argument form.* A keyword and a positional argument are one in `written`; a few checks read some keywords
  alone (`birth_year`, `departure_reason`, `secondary_role` of a member), and the JSON is the stricter reader
  (`census`, `names`; the folded codes in `redundancy`). PM001, PM002, AGE001, AGE002, MRA001 and DRA001 read
  a positional argument as the keyword since 0.1.18, and agree.
- *A value held in a name.* `AGE = 5`, `YEAR = 1858`, a `person()` bound once and used twice: an identifier or
  nothing to a check, a value to the JSON — one finding there, one per record here (`common`, `events`,
  `names`, `estates`, `redundancy`).
- *`RecordDefaults` is written whole.* `status_groom` is derived from `status_male` and the export cannot
  say if the author wrote it: one finding fewer for SOR001, ZGS004, VSR001 (`common`, `estates`,
  `redundancy`).
- *Merged `page()` calls.* The export joins consecutive records of one page, so RVR001 answers what the
  export shows, and only where it cannot be wrong; the `page_*`, `inner_page_*` and part of the
  `inner_records_*` variants are the source's alone (`redundancy`).
- *Aliases of one constant.* Several status or cause constants of one text: the JSON names the one that
  sorts last, `dsllint` the one the author wrote — only the name a fix offers differs (`estates`,
  `redundancy`, `names`).
- *No table.* H7 and the estates level above (`names`, `estates`, `redundancy`).

### How agreement is held

The rules are not asserted equal to the checks; two oracles compare them, both over the multiset of
(code, params, variant, token) per file, the positional codes folded by `hosted.fold`, the line left out
(an id stands in its place):

- **The samples** (the library, `tests/test_linters_on_json_samples.py`): every DSL text the library's tests
  handed a check (`tests/data/linter_samples/`) and the texts invented for a code none reaches
  (`tests/data/on_json_samples/`) is run through `dsllint` and, encoded to records v1, through
  `lint_records`. The test is parametrised over `SUPPORTED`, so a code added to the registry is judged at once; a
  sample that does not load is counted, and the count of those that do is a ratchet. The few forms the JSON cannot
  show are declared in the test, by code and variant.
- **The corpus** (the corpus oracle, kept with the corpus): every DSL file of a real corpus's
  villages, `check_file_json` against `lint_records` over `SUPPORTED`. On 0.1.17: 85 distinct codes, 0
  differences over its files, 278 findings from 14 advisory codes (the other 71 are
  silent on the corpus, so the samples are what judges them), no linter crash. `lint_records` over all 85
  codes takes about 42 s for the whole corpus (median 16 ms a file, 36 % of the time is replay), against about 52 s
  for `dsllint` — which also reads the source and the four `source` codes, so the figure is context, not a target.
