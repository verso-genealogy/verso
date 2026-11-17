# verso

**English** · [Русский](README.ru.md)

verso is a library for genealogical records written in Russian — from the Russian Empire to the Soviet
period: parish metric books (births, marriages, deaths), revision lists (ревизские сказки), confession
lists (исповедные росписи), and the cards of later catalogs.
A corpus writes each record as a call of a small Python DSL, one file per book and year; verso
reads those files and turns them into Geni profiles (as Terraform), Familio справочники, a records
JSON, CSVs, a timeline, and a set of checks that find what the records contradict.

It is two distributions:

- **verso-core** — what knows no language of the records: the workspace, the plugin registry, the
  pipeline's loading, the records JSON's codec, the places and the corpus's data, the review
  ratchet, Geni's HCL models and the `verso` command.
- **verso-ru** — the plugin for records written in Russian: the DSL (`verso.ru.dsl`), the domain and naming,
  the facts layer, the consolidation checks, the DSL linters, the translator to Geni's Terraform,
  the exporters and importers.

## Install

From PyPI, since 0.1.39:

```sh
pip install "verso-ru[xlsx,dsl-tools,sheets]"
```

`verso-ru` brings the `verso-core` of its own version. A version before 0.1.39 installs from its git tag (`<tag>` is
one of [the tags](https://github.com/verso-genealogy/verso/tags)):

```sh
pip install "verso-core @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-core"
pip install "verso-ru[xlsx,dsl-tools,sheets] @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-ru"
```

Python 3.14+. The extras: `xlsx` — the Familio справочник (openpyxl); `dsl-tools` — rewriting DSL files,
`verso upgrade-dsl` (libcst); `sheets` — the Google Sheets importer.

The library ships no corpus, but it ships a base names lexicon (`[names] base = "ru"`: given names,
patronymics and their old spellings). A corpus is a directory with a `verso.toml` that names its
villages, its own names layer over that base, and its own data — places, owners, the timeline's
events, the landlords' statuses. See [the workspace](docs/workspace.md).

## Quick start

`examples/` holds a whole toy workspace — one invented village, its names layer over the shipped base, its places and
landlord, four books — and a script that runs the library over a copy of it:

```sh
python examples/run.py --keep /tmp/toy     # then look at /tmp/toy: CSVs, records/, terraform/
```

See [the example](examples/README.md).

## A record

```python
from verso.ru.dsl import Gender, Month, birth, birth_month, birth_records, person

births = birth_records(
    "ГА", "1", "2", "3", "Степанчиково", "Троицкая", 1850,
    *birth_month(Month.JANUARY,
                 birth(1, Gender.MALE, 3, 4,
                       child=person("Иванъ"),
                       father=person("Петръ", "Сидоровъ", "Ежевикинъ"),
                       mother=person("Анна", "Ѳомина"))),
)
```

The record states the book's shelfmark (archive, fund, inventory, case), the village and the
church, then each entry as the scribe wrote it — names in the original orthography. What the
record implies (the child's patronymic and surname, the mother's surname, a status from the
book's defaults) is derived; what it says is kept verbatim. Then:

- `verso dsllint FILE…` — the DSL linters (see [the reference](docs/reference/linters.md));
- `verso export-csv --village V` — a CSV per record set, beside its file;
- `verso generate-tf --village V` — Geni profiles, unions and documents as Terraform;
- `verso export-records --village V` — the records JSON ([records JSON](docs/records-json.md));
- `verso facts`, `verso date-order`, `verso reconcile`, … — checks over the records
  ([all commands](docs/reference/commands.md)).

## Reading the scans: a Claude Code plugin

The repository is also a Claude Code marketplace, `verso`, with one plugin, **verso-reading**: skills and
agents that read handwritten scans — metric books, revision and confession lists, the 1917 farm-census
cards — and write what they say into the DSL.

```text
/plugin marketplace add verso-genealogy/verso
/plugin install verso-reading@verso
```

| Skill | What for |
|---|---|
| `verso-reading:metric-books` | a year of a metric book: is the дело whole, where the parts begin, legible crops, reading in two tiers |
| `verso-reading:census` | a family in a revision or confession list by its age fingerprint, then its households |
| `verso-reading:agri-census-1917` | the 1917 household cards |
| `verso-reading:transcription` | the transcribe-first route: a reviewable `.txt` of a page |
| `verso-reading:names` | the names lexicon and its lint findings |

Its agents are `verso-reading:dsl-writer` (a scan straight to the DSL) and `verso-reading:scan-reader`
(reading that writes no DSL). The plugin names no corpus: the project's AGENTS.md says where its rules,
regional notes and frames are. The skills work in other agents too, through skills.sh. See
[the plugin](plugins/verso-reading/README.md).

## What is public

The library promises, to a corpus that is not its author's, what a corpus is written against:

- the DSL's facade — `verso.ru.dsl` and its three catalogs (`DSL_API`, [the DSL](docs/dsl.md));
- the corpus's statuses as `<the corpus directory>.statuses`;
- the records JSON's schema (`records-v1.json`) and its id rule `r1`;
- the commands of `verso`, their flags and exit codes;
- the keys of `verso.toml` and `village.toml`;
- the linters' codes and the format of `dsllint --json`;
- the line of the review ratchet's list (`unreviewed_on_geni.tsv`).

Everything else — the modules under the facade, the domain, the translator — is the library's own
and moves without notice. While the version is 0.x a minor version may break compatibility: a
public name to be removed or renamed lives one minor version beside its successor and warns
(`DeprecationWarning`) before it goes. See [compatibility](docs/compatibility.md).

## Documentation

- Guides: [the workspace](docs/workspace.md) · [the DSL](docs/dsl.md) · [plugins](docs/plugins.md) · [the interface's language](docs/i18n.md)
  · [records JSON](docs/records-json.md) · [the review ratchet](docs/review-ratchet.md)
  · [compatibility](docs/compatibility.md)
- Reference, written from the code: [commands](docs/reference/commands.md) ·
  [workspace keys](docs/reference/workspace-keys.md) · [linters](docs/reference/linters.md) ·
  [DSL API](docs/reference/dsl-api.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changes](CHANGELOG.md)

## Licence

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
