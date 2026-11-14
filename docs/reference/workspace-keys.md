<!-- Written by tools/reference.py from the code — do not edit; `make reference`. -->

# Workspace keys

An unknown key or table is refused, naming the file and the key. `verso.toml` is of schema 7 (a newer schema than the code's is refused).


## `verso.toml`

| Table | Keys |
|---|---|
| `(top level)` | `app`, `corpus`, `i18n`, `names`, `notes`, `plugins`, `schema`, `tools`, `translit`, `villages` |
| `corpus` | `dir` |
| `i18n` | `locale`, `packs` |
| `names` | `base`, `dir`, `layers`, `writable` |
| `notes` | `globs` |
| `tools` | `path` |
| `translit` | `address`, `display` |

## `<village>/village.toml`

| Table | Keys |
|---|---|
| `(top level)` | `census`, `csv`, `geni`, `schema`, `sheets`, `timeline` |
| `census` | `order`, `prev_revision` |
| `census.order` | `suffix`, `year` |
| `csv` | `skip` |
| `geni` | `project_rules`, `projects` |
| `timeline` | `era`, `split_note` |
| `timeline.era` | `detail`, `from`, `label`, `to` |

## `<corpus>/estates.toml`

| Table | Keys |
|---|---|
| `(top level)` | `landlords`, `maiden_families`, `owner_aliases`, `owners_and_state`, `state_peasants`, `village_aliases` |
| `landlords` | `token`, `villages` |
| `owners_and_state` | `owners`, `parish`, `state` |
| `owners_and_state.side` | `in`, `village` |
| `state_peasants` | `books`, `village`, `who` |

## `<corpus>/timeline.toml`

| Table | Keys |
|---|---|
| `(top level)` | `event` |
| `event` | `detail`, `from`, `label`, `to` |

## `<corpus>/places.toml`

| Table | Keys |
|---|---|
| `["<place>"]` | `city`, `country`, `county`, `familio`, `same_as`, `state` |
