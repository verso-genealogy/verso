"""The «Российская империя» plugin as the core's registry sees it.

`pyproject.toml` declares it — `[project.entry-points."verso.plugins"] ru =
"verso.ru.plugin:PLUGIN"` — and a workspace enables it (`plugins = ["ru"]`). Importing this
module costs nothing but the registry: every factory imports what it gives when the core
first asks.
"""
from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from verso.core.plugins import ContentProfile, Dsl, Plugin, SourceNotes


def _dsl() -> Dsl:
    from verso.ru.dsl.calls import CALLS
    from verso.ru.dsl.kinds import KINDS, SOURCE_PATTERNS, order
    from verso.ru.records.cite import R1
    from verso.ru.records.vocabulary import VOCABULARY
    return Dsl(kinds=KINDS, globs=SOURCE_PATTERNS, order=order, calls=CALLS, vocabulary=VOCABULARY, cite=R1,
               legacy_import=_legacy_import)


def _legacy_import(module: str, path: Path) -> str | None:
    """DSL v0 imported `geni.*`, an alias DSL v1 took away: `verso upgrade-dsl` rewrites the file."""
    if module == "geni" or module.startswith("geni."):
        return f"DSL v0 — verso upgrade-dsl {shlex.quote(str(path))}"
    return None


def _notes(source: str) -> SourceNotes:
    """The `#` notes of a DSL file and the record numbers they were counted against (`verso.ru.dsl.notes`)."""
    from verso.ru.dsl.notes import read_notes
    notes, numbers = read_notes(source)
    return SourceNotes(notes=notes, numbers=numbers)


def _transliterate() -> Callable[[str], str]:
    from verso.ru.naming.transliteration import cyrillic_to_latin
    return cyrillic_to_latin


def _display_transliterate() -> Callable[[str], str]:
    """The spelling of the names a person reads: the role `display` (`[translit] display` of verso.toml)."""
    from verso.ru.naming.transliteration import display_name
    return display_name


def _content() -> ContentProfile:
    """What the books' records generate is Russian, whatever the interface's language: a Geni
    profile's names and about under "ru", their transliteration under "en-US"."""
    return ContentProfile(native="ru", latin="en-US")


def _ui() -> Traversable:
    """The hints the review page's schema is built from (`verso.core.records.ui`): data of the package."""
    from importlib.resources import files
    return files("verso.ru.records").joinpath("ui-hints.toml")


def _village_table(name: str) -> Callable[[Path, Mapping[str, Any]], Any]:
    """The parser of one of the plugin's village.toml tables, imported when a village is read:
    importing the plugin must not import the workspace (`verso workspace` runs it as __main__)."""
    def parse(path: Path, table: Mapping[str, Any]) -> Any:
        from verso.ru.corpus_data import TABLES
        return TABLES[name](path, table)
    return parse


# Its tables of a village.toml, in `verso.ru.corpus_data.TABLES`' order.
VILLAGE_TABLES = {name: _village_table(name) for name in ("census", "timeline", "sheets", "csv")}


# `verso <команда>` — one command for each module of the plugin that runs as a program, its name
# with hyphens, but for three too general to stand alone (moved from verso.core.cli before 0.1.0).
COMMANDS: dict[str, str] = {
    "age-conflicts":                "verso.ru.consolidation.age_conflicts",
    "all-persons":                  "verso.ru.cli.all_persons",
    "apply-converge":               "verso.ru.consolidation.apply_converge",
    "audit-matches":                "verso.ru.consolidation.batches.audit_matches",
    "audit-unions":                 "verso.ru.consolidation.batches.audit_unions",
    "candidates":                   "verso.ru.consolidation.candidates",
    "canonicalize-legacy-tf":       "verso.ru.cli.canonicalize_legacy_tf",
    "conflict-capture":             "verso.ru.consolidation.conflict_capture",
    "date-order":                   "verso.ru.consolidation.date_order",
    "dead-code":                    "verso.ru.linters.dead_code",
    "death-age":                    "verso.ru.consolidation.death_age",
    "detector":                     "verso.ru.consolidation.detector",
    "dsl-surface":                  "verso.ru.dsl.surface",
    "document-sync":                "verso.ru.consolidation.document_sync",
    "drift":                        "verso.ru.consolidation.drift",
    "dsllint":                      "verso.ru.linters.dsllint",
    "echz":                         "verso.ru.cli.echz",
    "estate-conflicts":             "verso.ru.consolidation.estate_conflicts",
    "export-csv":                   "verso.ru.cli.export_csv",
    "export-records":               "verso.ru.cli.export_records",
    "facts":                        "verso.ru.cli.facts",
    "facts-snapshot":               "verso.ru.cli.facts_snapshot",
    "familio-spravochnik":          "verso.ru.cli.familio_spravochnik",
    "fetch-record":                 "verso.ru.cli.fetch_record",
    "find-person":                  "verso.ru.cli.find_person",
    "fix-combined-name-patronymic": "verso.ru.cli.fix_combined_name_patronymic",
    "fix-ich-patronymics":          "verso.ru.cli.fix_ich_patronymics",
    "generate-familio-tf":          "verso.ru.cli.generate_familio_tf",
    "generate-tf":                  "verso.ru.cli.generate_tf",
    "generate-timeline":            "verso.ru.cli.generate_timeline",
    "import-sheets":                "verso.ru.importers.google_sheets",
    "lint-config":                  "verso.ru.consolidation.lint_config",
    "lint-kin":                     "verso.ru.familio.lint_kin",
    "merge-plan":                   "verso.ru.consolidation.merge_plan",
    "migrate-statuses":             "verso.ru.cli.migrate_statuses",
    "moved-blocks":                 "verso.ru.consolidation.moved_blocks",
    "name-variants":                "verso.ru.consolidation.name_variants",
    "names":                        "verso.ru.cli.names",
    "names-csv":                    "verso.ru.linters.names_csv",
    "reconcile":                    "verso.ru.consolidation.reconcile",
    "remove-duplicates":            "verso.ru.cli.remove_duplicates",
    "review-ratchet":               "verso.ru.cli.review_ratchet",
    "show-record":                  "verso.ru.cli.show_record",
    "sibling-spacing":              "verso.ru.consolidation.sibling_spacing",
    "split-couples":                "verso.ru.consolidation.split_couples",
    "stale":                        "verso.ru.cli.stale",
    "stale-claims":                 "verso.ru.consolidation.stale_claims",
    "stale-moved":                  "verso.ru.consolidation.stale_moved",
    "stale-notes":                  "verso.ru.notes.stale_notes",
    "stale-stubs":                  "verso.ru.consolidation.stale_stubs",
    "statuses-toml":                "verso.ru.cli.statuses_toml",
    "strip-dead-overrides":         "verso.ru.consolidation.strip_dead_overrides",
    "svyatcy":                      "verso.ru.cli.svyatcy",
    "translit":                     "verso.ru.cli.translit",
    "tree-conflicts":               "verso.ru.consolidation.tree_conflicts",
    "triage-unions":                "verso.ru.consolidation.triage_unions",
    "union-duplicates":             "verso.ru.consolidation.union_duplicates",
    "upgrade-dsl":                  "verso.ru.cli.upgrade_dsl",
    "validate-import":              "verso.ru.importers.validation",
    "verify-batch":                 "verso.ru.consolidation.batches.verify",
    "verify-plan":                  "verso.ru.consolidation.verify_plan",
}

# The records files' header (records v1.x): the version of the vocabulary verso-ru's records are
# written in, and a book's language by default.
VOCABULARY_VERSION = 1
DEFAULT_LANG = "ru-Cyrl"

def _names_base_digest(name: str) -> str | None:
    from verso.ru.naming.layers import base_digest
    return base_digest(name)


PLUGIN = Plugin(name="ru", package="verso.ru", commands=COMMANDS, dsl=_dsl, transliterate=_transliterate,
                display_transliterate=_display_transliterate, content=_content, village_tables=VILLAGE_TABLES, place_attributes=("familio",),
                names_tables=("names.csv", "names_ignore.csv", "patronymics_ignore.csv"),
                names_layer_files=("names.tsv", "forms.tsv", "patronymics.tsv"), names_base_digest=_names_base_digest,
                ui=_ui,
                vocabulary=("ru", VOCABULARY_VERSION), default_lang=DEFAULT_LANG, notes=_notes)
