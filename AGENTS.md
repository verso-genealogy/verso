# AGENTS.md — verso, the library

Guidance for coding agents working in this repository: the library of Verso, two distributions
under one namespace package.

| Distribution | Import | What it is |
|---|---|---|
| `verso-core` | `verso.core` | the core: knows no language of the records |
| `verso-ru` | `verso.ru` | the plugin `ru`: records written in Russian, the Russian naming system — DSL, domain, naming, linters, facts, translator |

`verso` is a namespace package (PEP 420, no `verso/__init__.py`): each part can be its own
distribution without an import changing. A corpus — the DSL files of the books, its places,
names tables and configs — lives in a repository of its own and installs this library from a tag.
Nothing of a real corpus is in this repository: its tests read a synthetic one.

## Commands

```bash
make bootstrap        # .venv with both distributions editable and the dev tools (requirements-dev.txt)
make ci               # what CI runs, in its order: lint, tests, the core alone, the ratchets, the reference
make standalone       # the tests from `git archive HEAD` in a clean venv of the wheels, the sentinel on
make premerge         # make ci and make standalone: before every merge and release (CI runs no standalone on a PR)
make secrets-check    # gitleaks over `git archive HEAD`
make stamp v=X.Y.Z    # a version into both distributions (their `version` and the sister pin)
```

`make ci` and `.github/workflows/ci.yml` say the same thing (`tests/repo/test_kit.py` holds them
to each other). Python ≥ 3.14; CI runs 3.14 alone, the version the classifiers name and the server runs.

## Layout

```
packages/verso-core/src/verso/core/   the core: workspace, plugin registry, pipeline (load, config),
                                      records JSON codec, places, corpus data, ratchet, Geni's HCL
                                      models (targets/geni), i18n, `verso <command>` (cli.py)
packages/verso-ru/src/verso/ru/       the plugin: dsl (the facade and its catalogs), domain, naming,
                                      facts, consolidation, linters, exporters, importers, translator
                                      (targets/geni/translator), records vocabulary, cli modules
tests/                                the library's tests; tests/core — the core alone on a toy plugin;
                                      tests/repo — this repository's own tools
tools/                                layers, reference, release, standalone, secrets check, i18n codemod
docs/                                 the public guides, each with its Russian translation beside it (X.ru.md);
                                      docs/reference is written from the code and stays English
examples/                             the toy example (`examples/run.py`)
ide/                                  the VS Code and IntelliJ plugins of dsllint
```

## The rules the checks hold

- **The core imports no plugin** (LAY006, never listed). What the core needs of the plugin it asks
  the registry (`verso.core.plugins`): the DSL (record kinds, call dialect, vocabulary, citation),
  the transliterator, the content profile, the plugin's `village.toml` tables, place attributes,
  names tables, commands. `make test-core` runs `tests/core` with `verso.ru` blocked
  (`tests/core/block.py`): a test that fails on the blocker is the core calling the plugin — fix
  the core.
- **Layers** (`tools/layers.toml`, `make layering`): each package sits in a tier and imports its
  own package and lower tiers only (LAY002); nobody imports `verso.ru.cli` but the CLI, `verso <command>`
  and the plugin's command table (LAY001); no top-level import cycle (LAY003); the library never
  imports a corpus's package (LAY005). `tests/layering_allowlist.txt` only shrinks.
- **No Cyrillic in the core's code** (strings outside docstrings and comments). The interface's
  text goes through the catalogs: `t("key", name=value)` from the package's `messages`, the text in
  `locales/en.toml` (the source language) and `locales/ru.toml`. `make ui-ratchet` counts, per
  file of `verso-ru`, the lines of code holding Cyrillic: they only shrink. Content (generated prose,
  CSV headers, the sources' vocabulary) never goes through the catalogs; it is declared in
  `tests/ui_content.toml` or marked `# i18n: content`.
- **No path from `__file__` to data.** A module finds a corpus through the workspace
  (`verso.core.workspace`: `workspace.use()` → `VERSO_WORKSPACE` → `verso.toml` up from the working
  directory, never across a git boundary), never at import.

## What is public, and how it changes

`docs/compatibility.md` is the list: the DSL's facade (`verso.ru.dsl` and its three catalogs,
`packages/verso-ru/src/verso/ru/dsl/api-v1.json`, `DSL_API`), the records JSON's schema
(`records-v1.json`) and the id rule `r1`, the commands of `verso` with their flags and exit codes,
the keys of `verso.toml` and `village.toml`, `[i18n]`, `--lang`, `VERSO_LANG`, the entry point
groups `verso.plugins` and `verso.locales`, the catalogs' keys and their parameters, the linters'
codes and the format of `dsllint --json` (`code`, `params`, `token`), the advisory baseline's row,
the line of the review ratchet's list. Everything else moves without notice.

While the version is 0.x a minor version may break compatibility: a public name to be removed or
renamed lives one minor version beside its successor and warns (`DeprecationWarning`).
`make dsl-surface` refuses a facade that lost a name; `DSL_API` rises only when one goes.

## Byte neutrality is the corpus's gate

A corpus judges every release of this library by comparing its output byte for byte: every byte its producers write
(Terraform trees, CSVs, the records JSON, the facts reports, the review ratchet's fingerprints)
is compared between the pinned tag and the new one. A changed generated byte can re-create a live
Geni document; a changed record fingerprint drops a listed record off Geni. So:

- a refactor moves no byte of output — say so in the PR;
- a change that moves output is deliberate, a minor version, and its CHANGELOG entry names what
  moves and why;
- the transliteration profile `ru-v1` is frozen by its hash; a new spelling is a new profile.

## Records JSON (v1)

`verso.core.records`: the built DSL records as JSON without loss and back. Documents → page runs →
records → personas with roles; each node has `written` (the call's arguments) and `derived`
(what the object holds besides). Field names are the vocabulary's choosing (`json_names` of
`verso.ru.records.vocabulary`): an event's day, month and year are one object (`birth.day`), a
name's forms are one (`given.original`), no abbreviation (`number`). A person's slot has no key —
it is a persona named by its role — so ids (rule `r1`, a record named as it is cited) do not follow
the names. A new DSL field fails a test until the vocabulary has its row; then
`python -m verso.core.records.schema --write` (`records-v1.json`). The guide: `docs/records-json.md`.

## Ages in generated text

`verso.ru.ages` owns both age paths and keeps them apart: `split_age` is the tabular parser
(years, months, weeks, days — the CSV columns never carry prose), `format_age` the one renderer of
reader-facing text (numeral agreement, abbreviations expanded, fractions as months, idioms and
anything it cannot parse passed through verbatim). It returns None for an age not recorded, so a
call site guards on the rendered value. New age output goes through `format_age`, never by
interpolating the raw value.

## Tests

- `tests/conftest.py` sets the tests' own workspace (`tests/fixtures/workspace`: a synthetic
  corpus, the shipped names base under a layer of the names the tests write, `names-layer/`) before any module is
  imported; `VERSO_TEST_WORKSPACE` swaps it. The tests of the old tables (schema ≤ 5) read `tests/fixtures/legacy-names/`
  (the `legacy_workspace` fixture is a copy a test may write); the mini corpus's names are a layer of their own
  (`tests/fixtures/mini/names/`).
- **Fixtures are invented.** A test written from a bug found on a real record keeps only the shape
  the code reads and invents its people, numbers and days. A corpus's CI scans this tree for its
  words and its records (its `public-check`): a finding is fixed by inventing further, never
  allowlisted.
- A test takes the base's answer to what it asks of a name — when the base answers otherwise than the test was written
  for, the test's expectation changes, not the base. The fixture layer `tests/fixtures/workspace/names-layer/` holds only
  what the base lacks (the books' spellings a test writes) and the ignored names; a test that exists to exercise a layer
  builds its own over the base (`names_registry.answering(Lexicon.of([base().load(), layer]))`, or a workspace in
  `tmp_path`: the `base_workspace` fixture is the base alone). `verso names add`, `verso names check`.
- `tests/sentinel.py` (standalone) refuses any read outside the copy under test.

## Linters

`packages/verso-ru/src/verso/ru/linters/CLAUDE.md` is the guide: every finding is a structure
(`code`, variant, `params`, `token`) whose text the catalog renders (`CODE.variant`); the advisory
baseline is keyed by what a finding is, never by its message.

## Releasing

1. `CHANGELOG.md` — what changed, and whether a corpus's output moves.
2. `make premerge`, `make stamp v=X.Y.Z`, commit «Release X.Y.Z», tag `vX.Y.Z` (tags `v*` are protected: never
   moved, never deleted), push. CI runs on the commit's push to main, not on the tag. The tag runs
   `publish.yml`: it refuses a tag that does not name the stamped version, builds both distributions, publishes
   each to PyPI once the maintainer approves its `pypi-*` deployment, then installs them from PyPI and runs the
   example. The first release on PyPI also turns the README's «Install» (and its translation) to `pip install`
   from PyPI, in the release commit: until it is published, the git tag is the only way to install.
3. A corpus that pins this library moves its pin and judges the release by comparing its output byte for byte.
4. `make stamp v=X.Y.(Z+1).dev0` on `main`, commit «Open X.Y.(Z+1).dev0 [skip ci]»: a version alone, which
   the release's run has just checked, and a full CI run of the Actions quota.

## Docs

English is the source; a guide in `docs/`, the README, the example's README, CONTRIBUTING and SECURITY
each have a Russian translation beside them (`X.ru.md`). Change both in the same PR:
`tests/repo/test_public_texts.py` fails when the two differ in headings, table rows, code blocks
(comments aside) or the commands a reader types, or when a translation's link or anchor leads nowhere.

## Git

Commit messages in English. Never `--amend` a pushed commit. `.github/workflows/publish.yml` publishes a
release tag to PyPI, and by hand a dev trial to TestPyPI; nothing else uploads.
