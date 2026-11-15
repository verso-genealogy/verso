# Plugins

**English** · [Русский](plugins.ru.md)

The core (`verso-core`) works through the plugins a workspace enables, never by importing one.
`verso-ru` is the plugin for Russian books; a corpus of another language's records would bring
its own.

## Found by entry point, enabled by name

A plugin is a `verso.core.plugins.Plugin` that a distribution declares in the entry-point group
`verso.plugins`:

```toml
[project.entry-points."verso.plugins"]
ru = "verso.ru.plugin:PLUGIN"
```

and a workspace enables it by name — `plugins = ["ru"]` in `verso.toml`. An entry point is the
environment's metadata: after installing or upgrading a distribution, reinstall it so the entry
point is current. A plugin that is enabled and not installed is refused in one line, naming what
is installed; so are a plugin named otherwise than its entry point, an entry point that does not
load, and two plugins of one name.

## What the core asks

The core asks at work, never at import. Importing the registry or a plugin reads no workspace;
each answer is kept for the workspace it was asked in and forgotten when the workspace changes.

- `transliterator()` — the spelling of Geni resource names (res_names). verso-ru's is the profile
  `ru-v1`: 66 letters and the given names it spells whole, frozen by its hash, and before it the
  corpus's own surname spellings (`transliteration.toml` of the corpus). A res_name is a
  Terraform address, so a new spelling is a new profile, never an edit.
- `display_transliterator()` — the spelling of the names a person reads: a Geni profile's Latin
  names. A plugin gives it as `Plugin.display_transliterate`; where no enabled plugin does, it is
  `transliterator()`. verso-ru's is the role `display` of its transliteration — the same as the
  res_names' until a workspace names another profile for it; `ru-v2` (BGN/PCGN without
  apostrophes) is frozen by its hash as `ru-v1` is.
- `dsl()` — one DSL per workspace: its record kinds (the record set's class, its records' classes,
  whether they are translated and ratcheted), the globs of its files and the order its books are
  read in, the call dialect the review ratchet reads, the vocabulary of the records JSON, and what
  a record is cited by (the id rule `r1`).
- the plugin's commands of `verso` — `Plugin.commands`, from the installed plugins, without a
  workspace. `verso --help` lists them grouped, the core's first; two plugins naming one command
  are refused.
- `content()` — the content profile (`ContentProfile`): the locales a generated Geni profile's
  names and about are keyed by. verso-ru's: `native = "ru"`, `latin = "en-US"`. It is content,
  frozen by the plugin, and never follows the interface's language.
- `Plugin.village_tables` — the tables of a village's `village.toml` the plugin reads, each name
  with its parser; the core reads `schema` and `[geni]`, and a table no enabled plugin reads is an
  unknown key. verso-ru reads `[census]`, `[timeline]`, `[sheets]` and `[csv]`.
- `place_attributes()` — a place's keys in `places.toml` beyond its fields and `same_as`, read into
  `Places.attributes` (verso-ru: `familio`, the place's Familio settlement).
- `names_tables()` — the tables in the workspace's `[names] dir` (verso-ru: `names.csv`,
  `names_ignore.csv`, `patronymics_ignore.csv`); the records export names them among its inputs.

- `Plugin.vocabulary` and `Plugin.default_lang` — what a records file says of itself in its header:
  the vocabulary's name and version (`("ru", 1)`) and the books' default language (`"ru-Cyrl"`).
  Optional; a plugin without them writes neither key. A file whose vocabulary version is newer than
  the enabled plugin of that name reads is refused.
- `Plugin.notes` — reads the `#` notes of a DSL file from its text: `notes(source) -> SourceNotes`,
  where `SourceNotes(notes, numbers)` holds each note as `{"text", "anchor": {"to", "record", "end",
  "arg"}}` (`record` and `end` a record's place among the file's records from nought, in the export's
  order) and each record call's number as written (`None` where unreadable), or `numbers=None` when
  the plugin could not count. The core places the notes on the nodes and checks the counts and numbers
  against its own records first; on a disagreement it binds no note to a record and reports the file
  in `Exported.unbound`. A plugin without the hook exports no notes.

What is on Geni — the review ratchet's list file, its header, the on-Geni mark — is the Geni
target's, in the core (`verso.core.targets.geni`).

## The core alone

The core's own tests run it on a toy plugin of one record kind — its DSL, dialect, vocabulary,
citation and a command — with `verso.ru` blocked. A test that fails on the blocker is the core
calling the plugin at work: fix the core, not the test.
