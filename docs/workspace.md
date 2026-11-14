# The workspace

verso finds a corpus through one module, `verso.core.workspace`, never from where its own code
lies. A workspace is a directory holding `verso.toml`; everything the library reads of a corpus —
its villages, its names layer (over the base lexicon the library ships, `[names] base = "ru"`), its places and owners — is named there or beside it.

## Finding it

In this order:

1. the innermost `workspace.use(root)` (a context manager, for code and tests);
2. `VERSO_WORKSPACE`, a path to the directory;
3. `verso.toml` from the working directory up — never across a git boundary: a directory holding
   `.git` and no `verso.toml` is an error, so a checkout nested in another never reads the outer
   one's data.

`verso <command> --workspace DIR` sets the variable for that command. Set `VERSO_WORKSPACE` per
command, never `export` it: it wins over the working directory. `verso workspace root` and
`verso workspace villages` print what was found.

The answer is kept per process from the first question on. Importing a module never asks: `--help`
and an import from anywhere work without a workspace. Every Python child verso starts is given
the workspace in its environment.

## `verso.toml`

```toml
schema = 6
plugins = ["ru"]
villages = ["Степанчиково"]

[names]
layers = ["names"]       # the corpus's names layers over the shipped base; below

[corpus]
dir = "corpus"           # the corpus's own data, below

[notes]
globs = ["**/*.md"]      # the notes `verso stale-notes` reads

[tools]
path = ["/opt/terraform/bin"]   # where else to look for terraform and geni after PATH

[i18n]
locale = "en"            # the interface's language; see the guide to the language
```

- `villages` — the corpus's village directories, by name, in order.
- `plugins` — the plugins the workspace works with (see [plugins](plugins.md)); a file of
  schema 1–3 reads as `["ru"]`, one of schema 4 without the key is the core alone.
- `[names]` — the names lexicon: schema 6 sums layers over the base the library ships (see
  [the names lexicon](#the-names-lexicon)); a file of schema 5 or older names its old table with
  `dir`, and without `[names]` the first name lookup fails rather than answering «no such name» from
  an empty table.
- `[i18n]` — the interface's language (`locale`) and the language packs enabled (`packs`), see
  [the interface's language](i18n.md); a file of schema 4 or older speaks Russian, one of schema
  5 without the table English.
- `[translit]` (schema 7) — the transliteration profile of each role: `address` spells the res_names
  (a Terraform address), `display` the names a person reads (a Geni profile's Latin names). A key not
  written is `ru-v2`; a name no profile has is refused. A file of schema 6 or older spells both roles
  by `ru-v1` and the corpus's `transliteration.toml`, as it always did. See
  [the transliteration's rules](#the-transliterations-rules).
- `[app]` — the review page's own settings (`cache`, `photos_library`, `port`), which the
  library never reads.

An unknown key is refused naming the file and the key; the full list is in
[the reference](reference/workspace-keys.md).

## The names lexicon

What a name is — its base, its forms, the patronymics it gives — is answered by the sum of the
names layers, bottom to top: an entry of an upper layer replaces the lower layer's entry of its key
(the sex and the name, or the form) whole, and nothing depends on the order of the rows. `[names]`
of schema 6:

```toml
[names]
base = "ru"                       # the base the layers stand on; false — none (default "ru")
layers = ["corpus/names"]         # directories above it, bottom to top (default: none)
writable = "corpus/names"         # the layer a name is added to (default: the top layer)
```

- `base` — `"ru"` is the base verso-ru ships (built from the 1906 Требник's alphabet, Wikidata
  and the metric books' spellings, a source on every row); another name is refused at the first
  lookup, `false` sums the layers alone.
- `layers` — each a directory of three TSV files, `names.tsv`, `forms.tsv` and `patronymics.tsv`,
  sorted by their key; a table a directory lacks is empty, a directory that does not exist is
  refused at the first lookup. A layer leaves empty the forms the rules give (a genitive, a
  patronymic); a forms cell `-` says the name has no such form — the rules do not fill it in, and
  no reverse lookup (a short patronymic → its father) finds it. A names row whose `bases` is `-`
  says the (sex, name) does not exist: it removes the lower layers' entry of that key alone, its
  forms with it, and the name answers as if no layer held it in that sex (the base, with nothing
  below it, may not write one). A name whose source is `ignore`
  is one the lexicon knows and leaves out on purpose. A directory holding the old `names.csv`
  instead of `names.tsv` is read as the old table, with a `DeprecationWarning` — until 0.2.
- `writable` — one of `layers`; a name that is no layer is refused.
- `dir` is schema 5's and is refused in schema 6. A file of schema 6 without `[names]` has the base
  alone.

A host that keeps its names elsewhere than in files — a server's rows — hands the library a layer as a source for the
time it works in a workspace: `verso.ru.naming.layers.provided(directory, source)` makes `source` (a `LayerSource`) the layer
`[names] layers` names at `directory`, which then need not exist. A source that names its `identity` is kept between
workspaces like a directory is (`IdentifiedSource`); its `stamp()` must change with every write, by any process, and a host that has
written the layer calls `names_registry.invalidate(identity)` to have the next lookup read it at once without dropping the lexicons of
other layers.

A file of schema 5 or older reads as it always did: its `[names] dir` is one layer, the old tables
compiled, and **no base under it** — a name the old table does not know stays unknown.

Loading the lexicon reads the layers and sums them, nothing more: a reverse index (a short or a
modern patronymic, a genitive) is built when it is first asked, and two names the rules give one
key answer there by a fixed order. Refusing them is the check — `Lexicon.complete()`, which the
base's build, the layers' linter (LEX007) and `verso names layer-diff` run — and a pin in a layer's
`patronymics.tsv` settles which one holds.

### Adding, removing, checking and explaining a name

```
verso names add --gender Ж --name Евфрасиния --base Ефросиния --genitive Евфрасинии --source "МК 1917" [--dry-run]
verso names remove --gender Ж --name Евфрасиния [--dry-run]
verso names check [--layer DIR | --all]
verso names explain Евфрасиния [--gender Ж]
```

`add` writes a row to the writable layer — the one `[names] writable` names; `--layer DIR` may name that layer and
no other, a layer that is not writable is refused (change `[names]` to edit it on purpose): the name's row in
`names.tsv` and, when a form is given, its row in `forms.tsv`, the two files written together or neither. A row has no place and no order, a key has one row, and a
key the layer holds is refused. `--gender` is `М` or `Ж`; the forms are `--genitive`, `--patr-m`, `--patr-f`,
`--patr-old-m` and `--patr-old-f` (also `--patronymic-m` and so on): a form left out is the rules', one set to `-` is «no
such form»; `--source` defaults to `editor`. The new rows are read first by the layers' linter over the layers under
them: a hard finding — LEX001 (a key no lookup can ask by), LEX003 (a base no layer holds), LEX007 (two derivations of
one patronymic) — refuses them, exit 1 and nothing written; a row the sum already answers alike (LEX005) is written, with
the warning saying so. When forms are given for a name the layers hold already and no `--base`, only the forms row is
written. `--origin` and `--declension` are the old `names.csv`'s columns and refused here.

`add --replace` replaces the row of a key the writable layer holds already, instead of refusing it. Each table the command
writes — `names.tsv`, and `forms.tsv` when forms are given — has that key's row replaced whole; a table it does not write is
left as it is, so `--replace --base X` without forms keeps the old `forms.tsv` row. The new row is read by the linter over the
layers under it, not against the row it replaces (a replacement that makes the row equal to the base is LEX005), and the
command prints «replaced» for each. A workspace of schema 5 or older, which has no layer rows to replace, refuses it (exit 1).

`remove` deletes the layer's rows of the key (its `names.tsv` and `forms.tsv` rows). A name only a layer below holds —
the base — is taken out of the stack by a removal row (`-` in bases) written into the layer, and removing it once more
deletes that row. Either way it says so, and says when a layer below still holds the key, when other names still have the
removed one as their base (they answer as written; LEX003 in `check`), and — a warning, never a refusal — how many
records of the workspace's villages still write the name (`written` as a `person(…)`'s given name, the files read as
syntax). `--gender -` is the entry of a name with no sex. Exit 1: no layer holds the key.

`check` reads the writable layer with the linter (LEX001–LEX007), or the layer `--layer` names, or with `--all` every layer,
the base included, and their sum. Each finding is printed as `layer/file:line: message`; exit 1 when one is hard
(advice, LEX004 and LEX005, passes).

`explain` prints, for one name, the answer of `canonicalize_name`, `matching_base`, `genitive_given_name`,
`get_gender_from_name`, and `derive_patronymic` and `derive_old_patronymic` for a son and a daughter, and under each the
entries it was read from, each with its layer; a function that reads a form shows the cell it reads, marked with its layer or with `rule` (`verso.ru.naming.forms`) where no layer writes it. Without
`--gender` it asks for the sexes the lexicon holds the name in.

In a workspace of schema ≤ 5 `add` writes its row into the old `names.csv` as it always did (`--path` another file, a
note says so); `explain` reads the old tables as one layer; `remove` and `check` are for layers, exit 1.

A name an ignore-list entry (source `ignore`) holds gets no form from the rules: it is known and not validated, and no
patronymic or genitive of it is given until a forms row says one. A name whose one base no layer holds — a layer written
over a base a later release dropped — still loads and answers as a name with no base (as written); `check` says LEX003.

### From the old table to a layer

```
verso names layer-diff --from-legacy DIR --base ru --oracle FILE --out DIR
```

writes the smallest layer over the base that answers every question of an oracle as the old
tables of `--from-legacy` do. The oracle is the record of what a corpus asked its naming functions,
a TSV file of one row a question:

```
function<TAB>args_json<TAB>answer_json
```

- a line starting with `#` is a comment; the rows are sorted as lines;
- `function` is the bare name of a naming function (`canonicalize_name`, `matching_base`,
  `derive_patronymic` …);
- `args_json` is the JSON list of all its parameters in order, defaults applied, a sex written
  `"M"`, `"F"` or `null`;
- `answer_json` is the answer in the same notation, or `{"raises": "<the exception's class>"}`;
- JSON is written compact, keys sorted, non-ASCII as it is.

For each question the base alone answers otherwise, it takes the old table's entries of the keys the
question was looked up by — a name with its forms, the names whose forms give a patronymic, a pin —
and repeats until every question agrees. Where a name and a pin would both do, the name is taken (it
answers the name's other questions too); a question its keys do not settle gets the old table's
answer written down as a pin, a forms cell, or `-` where the old table knows no form the rules
would give; and where the base holds a name in a sex the old table does not, and nothing else
settles a question asked of it, a names row with `-` for bases removes that (sex, name). Beside
the oracle's questions it asks the woman's fold of every patronymic the oracle names
(`feminine_patronymic`, the form a consolidation check compares two patronymics by).

Then it leaves out what the base answers alike. Every entry that may answer as the base does — a
name entry the base holds alike, a forms entry whose forms the base gives alike, any pin — is left
out at once; for each question then answered otherwise, the entries it reads are put back. The
entries put back as a group are then tried one at a time: each one whose own questions still
answer as the old table without it goes, and a last full replay puts back whatever a question
still needs. Every entry is written with the source `legacy` — but a
name of the old ignore list, which keeps the source `ignore`, the mark it is answered by. The same
inputs write the same bytes.

Exit 1 lists the questions no entry settles — the layer is written all the same. Two names whose
rules give one patronymic, which the old tables answer with nothing a pin could write, are the
other exit 1: the conflict is said and no layer is written. An answer the oracle's notation cannot
hold is a third.

## The transliteration's rules

verso-ru ships two profiles, each frozen by its hash: `ru-v1`, the res_names' spelling of old
(`Jakov`, `Hohrjakov`), and `ru-v2`, BGN/PCGN without apostrophes (`Yakov`, `Khokhryakov`, `Yury`,
`Darya`, `Maria`, `Semyon`). A word a profile is to spell whole is a **rule**, and from schema 7 the
rules are rows of the names layers — a fourth file beside a layer's three, `translit.tsv`:

```
profile	word	latin	source	note
ru-v1	Чубарев	Tchoubarev	editor
ru-v2	Сорокоплехин	Sorokoplekhine	editor	as the family writes it
```

A rule is bound to its profile: a rule of `ru-v1` says nothing of `ru-v2`. The layers are summed as
the names are — an upper layer's row replaces the lower one of its key (profile, word), a `-` in
`latin` takes a lower rule away — and a rule is added to the layer `[names] writable` names. A file
of schema 7 whose corpus still holds `transliteration.toml` is refused until its rules are moved
into the layer (`verso translit migrate`).

`verso translit show WORD` says what each role spells a word as and by which rule; `add WORD LATIN`
and `remove WORD` write the writable layer (a rule of the profile of display unless `--profile`
says another), after the layers' linter has read the row: LEX008 (a rule of no profile, of a word
that is not one Cyrillic word, of nothing) and LEX010 (a Latin spelling with a character outside
the Latin letters, the apostrophe, the space and the hyphen; advice for `ru-v1`) refuse it, LEX009
says a rule is redundant. A rule of the profile that spells the **addresses** is refused while a
generated tree of the workspace (`<village>/terraform/geni/*.tf`) holds a resource label carrying
the word as that profile spells it now: the rule would rename a Terraform address. The refusal
names the profile of display instead. `verso translit check` lints every layer's rules.


A village is a directory of DSL files by year — `<village>/<YYYY>/<village>_<kind>_<YYYY>.py` —
and its settings, `<village>/village.toml`, read from the village's own directory:

- `[geni]` — the Geni projects every profile joins, and `project_rules`: a project for a profile
  whose place (its name or its expanded location) contains a substring — the core's; every other
  table is a plugin's (verso-ru's below), and one no enabled plugin reads is an unknown key;
- `[census]` — the legacy order of the census rolls, and exceptions to the revision chain;
- `[timeline]` — the village's eras on its timeline;
- `[sheets]` — the Google sheet its records are imported from;
- `[csv]` — files that write no CSV.

## The corpus's data

What the library knows of a corpus is data, read at call time through the workspace — never
code, never at import. Under `[corpus] dir`:

| File | What | Read by |
|---|---|---|
| `places.toml` | a table a place: `city`, `county`, `state`, `country`, and the plugins' attributes (verso-ru's `familio`, its Familio settlement); another spelling is a table with `same_as` alone | `verso.core.places` → the translator, ULC001, Familio, the timeline |
| `estates.toml` | owners and parishes: aliases, maiden families, landlords' villages, state peasants | `verso.ru.corpus_data.estates` → estate-conflicts, RTV001/RTV002 |
| `timeline.toml` | the timeline's events | `verso.ru.corpus_data.timeline_events` |
| `transliteration.toml` | the corpus's surnames the res_name profile spells whole | `verso.ru.naming.transliteration` |
| `statuses.py` | the corpus's landlords' statuses, as `Status` constants | the DSL (`from corpus.statuses import …`); the library through `verso.ru.domain.statuses.catalog()` |
| `statuses.toml` | the same statuses as data, instead of the module: a table a constant (`text`, and `gender` — `male` or `female` — where it has one), in the catalog's order, and the optional alias tables `child_estate_aliases` and `estate_aliases` | the library through `verso.ru.domain.statuses.catalog()`, without executing any Python |

The corpus directory is a package because the DSL imports its statuses; a workspace whose corpus
directory is named otherwise imports them by that name. A corpus file changed while a process runs
is read again on the next question. Without `[corpus]` there is no corpus data — no places, owners
or events — which is not an error.

A corpus holds its statuses as `statuses.py` or as `statuses.toml`, not both: a workspace with both
is refused. `verso statuses-toml` prints the TOML of the module, or writes it with `--out FILE`; to move a
corpus to the data form, `verso statuses-toml --out <corpus dir>/statuses.toml` and then remove
`statuses.py` by hand (the workspace is refused while both stand). The DSL imports
`<the corpus directory>.statuses` only from the module. A change to `statuses.toml` is read
again on the next question.

`transliteration.toml` holds one table, `[names]`: a surname as the books write it and its Latin
spelling (`"Сорокоплехин" = "Sorokoplekhin"`). The res_name profile (ru-v1) spells a name it does
not know letter by letter; a surname listed here is spelled whole, as the corpus's res_names have
always spelled it. A name the profile's own table already spells is refused there, as is any other
key. So `cyrillic_to_latin` and `generate_res_name` read the workspace: called outside one, they
raise `WorkspaceError` rather than spell a corpus's surname otherwise than its tree does.
