# Compatibility

**English** · [Русский](compatibility.ru.md)

## What is public

The library promises, to a corpus that is not its author's, what a corpus is written against:

| Surface | Where it is fixed |
|---|---|
| the DSL's facade — `verso.ru.dsl` and its three catalogs | `packages/verso-ru/src/verso/ru/dsl/api-v1.json`, `DSL_API` ([reference](reference/dsl-api.md)) |
| the corpus's statuses as `<the corpus directory>.statuses` | [the workspace](workspace.md) |
| the records JSON's schema and its id rule `r1` | `records-v1.json` ([records JSON](records-json.md)) |
| the review page's schema and its labels' keys (`ui.*` of `verso.ru`'s catalogs) | `ui-v1.json` ([records JSON](records-json.md#the-interfaces-schema)) |
| the commands of `verso`, their flags and exit codes | [reference](reference/commands.md) |
| the keys of `verso.toml` and `village.toml` | [reference](reference/workspace-keys.md) |
| the interface's language: `[i18n]`, `--lang`, `VERSO_LANG`, the entry point group `verso.locales`, the catalogs' keys and their parameters | [the interface's language](i18n.md) |
| the linters' codes and the format of `dsllint --json` (each finding's `code`, `params`, `token`) | [reference](reference/linters.md) |
| the advisory baseline's row (v2: `# baseline v2`, keyed by file, code, params) | [reference](reference/linters.md) |
| the line of the review ratchet's list | [the review ratchet](review-ratchet.md) |
| the addresses of a village's site: a book's page and a record's anchor, made of its id | [a village's site](site.md#the-pages-and-their-addresses) |
| the scan tools: `verso scans` and its subcommands, their flags, outputs and exit codes; the names in `__all__` of `verso.core.scans.*` and `verso.ru.scans.*` — the modules under `cli` too, a subcommand's module public in its `HELP`, `add_arguments` and `run` and in what [the table](scans.md#in-python) adds —; `Plugin.scans` | [the scan tools](scans.md) |

Everything else — the modules under the facade, the domain, the translator — is the library's own
and moves without notice.

## Versions

While the version is 0.x, **a minor version may break compatibility**. A public name to be removed
or renamed lives one minor version beside its successor and warns (`DeprecationWarning`) before it
goes. Run your corpus's checks with `PYTHONWARNINGS=error::DeprecationWarning` to learn of a
retiring name while it still works; let a third-party library's warning through only by its module
(`ignore::DeprecationWarning:<module>`), with the reason beside it.

The policy holds from **0.1.0**, the first release of this repository (2026-10-22): what 0.1.0
makes public is the baseline every later version is compared with. A release is a tag `vX.Y.Z`
naming one version of both distributions; `main` carries the next version's `.dev0` between tags,
and [CHANGELOG.md](../CHANGELOG.md) says what each one changed.

## The workspace's schema

`verso.toml` names its schema, and a file of every older schema reads exactly as it did: each schema
only adds keys (the [reference](reference/workspace-keys.md) lists them). Schema 6 changes how the
names lexicon is configured:

- **schema ≤ 5** — `[names] dir` names the old tables (`names.csv`, `names_ignore.csv`,
  `patronymics_ignore.csv`), read as one layer with nothing under it: a name the table does not know
  stays unknown, whatever the shipped base holds. A file of schema 5 keeps answering as it did;
- **schema 6** — the shipped base by default (`[names] base = "ru"`), the layers of
  `[names] layers` above it. Schema 6 refuses `[names] dir` (schema 5's key: a file moving to
  schema 6 writes its old directory as a layer), and a file of schema ≤ 5 refuses `base`, `layers`
  and `writable`.

**`names.csv` as a layer — until 0.2.** A directory of `[names] layers` that holds the old
`names.csv` instead of `names.tsv` is read as the old table, with a `DeprecationWarning`. In 0.2 a
layer is three TSV files alone; `verso names layer-diff` writes them from the old table
([the workspace](workspace.md#the-names-lexicon)).

## The DSL's version

`DSL_API` rises only when a name of the facade goes or is renamed; a new keyword argument with a
default is compatible and leaves it. A file of an older DSL says so when it loads, and
`verso upgrade-dsl` rewrites it ([the DSL](dsl.md)).

## Outputs that are addresses

Some outputs are identities on another system, and verso keeps them byte-stable across versions:

- a res_name is a Terraform address — the transliteration profile `ru-v1` is frozen by its hash, and
  a new spelling would be a new profile; `ru-v2`, the profile of the names a person reads, is frozen
  the same way;
- a record's id (`r1`) names it in the records JSON, the facts layer and links;
- a document's text on Geni is replaced when it changes, so a change of rendering is a release note.

## Judging a new version on a corpus

A corpus judges a release by what it writes. Install the pinned version and the new one in two environments,
write every output of the corpus with each into its own directory — `verso generate-tf`, `verso export-csv`,
`verso export-records`, `verso facts-snapshot`, and the checks' reports — and compare the two byte for byte. A
byte that moves is either named in the new version's CHANGELOG entry, which says what moves and why, or a
regression to report. An address above that moves is a regression whatever the entry says: a res_name that
changes makes Terraform destroy a profile and create another.
