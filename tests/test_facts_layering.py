"""The import budget of `verso.ru.facts`, enforced rather than documented.

A layer diagram in a docstring is a wish. This is the same statement as a test,
and it is the load-bearing one: the whole claim of the facts layer is that a
RULE cannot know what kind of document it is reading. The moment a rule can
reach `verso.ru.dsl.records` — or merely name a concrete predicate — the
per-record-kind ladder has moved rather than gone, and every parity result
above it stops meaning anything.

Modelled on `verso/ru/familio/` and `verso/ru/timeline/`, whose layering is stated in
prose (`verso/ru/timeline/__init__.py`) and has drifted only because nothing
checks it. The whole package's layers — and that nothing outside the CLI
imports it, consolidation included — are tests/test_layering.py's.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.codepaths import package_dir

_FACTS = package_dir("verso.ru.facts")
# The library's packages: an import of one is held to the budgets.
_LIBRARY = ("verso.core", "verso.ru")

_STDLIB_OK = True  # stdlib is always allowed; the budgets below list geni.* only

#: module glob → the `geni.*` prefixes it may import.
_BUDGET: dict[str, tuple[str, ...]] = {
    "model.py": ("verso.ru.gender",),
    "identity.py": ("verso.ru.facts.model", "verso.ru.naming", "verso.ru.gender"),
    # `projection.py` gained `verso.ru.facts.identity` with `consolidated_identity`:
    # the bridge's PRODUCT is an `Identity`, and the type belongs to the module
    # that owns identity policy. The direction is still one-way — `identity.py`
    # does not know `projection.py` exists, and nothing here reaches the DSL.
    "projection.py": ("verso.ru.facts.model", "verso.ru.facts.identity", "verso.core.targets.geni"),
    # `verso.ru.census_revisions` is a stdlib-only leaf: which revision a roll's
    # previous-age column counts from is a fact about the revisions, shared with
    # the CAI002 linter so the two cannot date one column two ways.
    # `verso.core.records.ids` / `.fields`: a persona is named as the records JSON
    # names it (rule r1) — the id rule and the slot's role, one definition.
    "extract/*.py": ("verso.ru.facts.model", "verso.ru.facts.extract", "verso.ru.domain",
                     "verso.ru.dsl.records", "verso.ru.relationship", "verso.ru.gender",
                     "verso.ru.ages", "verso.ru.naming", "verso.ru.census_revisions",
                     "verso.core.records.ids", "verso.core.records.fields"),
    "rules/*.py": ("verso.ru.facts.model", "verso.ru.facts.identity"),
    # A check NAMES its predicates and holds measured tolerances; it reads what
    # the domain says an age or a status means (`verso.ru.ages`,
    # `verso.ru.domain.estates`) and the slot names the extractors publish
    # (`extract.common`), and nothing that reads a file or a record.
    # `verso.ru.church_calendar` is the Church's own calendar — Julian day
    # arithmetic, the paschalion, the святцы TYPE — a stdlib-only leaf; the
    # святцы TABLE is loaded by the CLI and handed in, never read here.
    "checks/*.py": ("verso.ru.facts.model", "verso.ru.facts.identity", "verso.ru.facts.rules",
                    "verso.ru.facts.projection", "verso.ru.facts.checks",
                    "verso.ru.facts.extract.common", "verso.ru.ages", "verso.ru.domain.estates",
                    "verso.ru.naming", "verso.ru.gender", "verso.ru.church_calendar",
                    # A check's reasons and hints are words a person reads — the catalog's,
                    # rendered when read (`verso.ru.messages`, a leaf: no file, no record).
                    "verso.ru.messages"),
}

#: Nobody in the package may reach the CLI — I/O lives there, one way only.
_FORBIDDEN_EVERYWHERE = ("verso.ru.cli",)

#: A rule may not name a record's shape, nor any concrete predicate: it takes
#: its predicates as TYPE PARAMETERS.
_RULE_FORBIDDEN_NAMES = (
    "record_kind", "locator", "stated_role",
    "ParentOf", "GodparentOf", "SpouseOf", "WitnessedAt", "OfficiatedAt",
    "BornOn", "BaptizedOn", "MarriedOn", "DiedOn", "BuriedOn", "AgedYears",
    "NameClaim", "ResidedIn", "FosterParentOf", "KinOf",
    "EnumeratedIn", "MovedTo", "ArrivedFrom", "SurvivedUntil",
    # `KinOf.term` is the source's own word for kin we cannot place. A rule may
    # see that two people are related and nothing more: branching on «свекор»
    # is the per-record-kind ladder coming back through a payload field.
    ".term",
)

#: Extractors are the only layer that may touch DSL objects — and even they
#: may not touch the filesystem. I/O is the CLI's job.
_EXTRACT_FORBIDDEN_MODULES = ("pathlib", "importlib", "subprocess", "os")


def _modules(pattern: str) -> list[Path]:
    return sorted(p for p in _FACTS.glob(pattern) if p.name != "__init__.py")


def walked() -> list[Path]:
    """Every module of the package the guards read."""
    return sorted(p for p in _FACTS.rglob("*.py") if "__pycache__" not in p.parts)


def _of_library(name: str) -> bool:
    return any(name == p or name.startswith(p + ".") for p in _LIBRARY)


def _imported_geni_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


class ImportBudget(unittest.TestCase):
    def test_every_layer_stays_inside_its_budget(self):
        held = 0
        for pattern, allowed in _BUDGET.items():
            for path in _modules(pattern):
                for name in _imported_geni_modules(path):
                    if not _of_library(name):
                        continue  # stdlib and third-party are unconstrained
                    held += 1
                    with self.subTest(module=path.name, imports=name):
                        self.assertTrue(
                            any(name == a or name.startswith(a + ".") for a in allowed),
                            f"{path.relative_to(_FACTS)} may not import {name}; "
                            f"budget is {allowed}")
        # A budget no import is held to passes on nothing (an import named otherwise than the layout says).
        self.assertGreaterEqual(held, 100, "imports of the library held to the budgets")

    def test_nothing_reaches_the_cli(self):
        for path in _FACTS.rglob("*.py"):
            for name in _imported_geni_modules(path):
                for banned in _FORBIDDEN_EVERYWHERE:
                    with self.subTest(module=path.name):
                        self.assertFalse(
                            name == banned or name.startswith(banned + "."),
                            f"{path.name} imports {name}: I/O belongs in verso/ru/cli/")

    def test_the_package_is_not_empty(self):
        """A budget test that passes because nothing exists proves nothing."""
        self.assertGreaterEqual(len(_modules("extract/*.py")), 5, "extractors found")
        self.assertGreaterEqual(len(_modules("rules/*.py")), 3, "rules found")
        self.assertGreaterEqual(len(_modules("checks/*.py")), 10, "checks found")
        self.assertGreaterEqual(len(walked()), 30, "modules of the package found")


class RulesKnowNothingOfRecords(unittest.TestCase):
    def test_a_rule_names_no_predicate_and_no_record_shape(self):
        for path in _modules("rules/*.py"):
            source = path.read_text(encoding="utf-8")
            for name in _RULE_FORBIDDEN_NAMES:
                with self.subTest(rule=path.name, name=name):
                    self.assertNotIn(
                        name, source,
                        f"{path.name} names {name}; a rule takes its predicates "
                        f"as type parameters and reads no provenance")

    def test_a_rule_names_no_record_kind_in_any_language(self):
        vocabulary = ("рожден", "венчан", "восприемник", "поручител",
                      "отец", "мать", "ревизи", "исповед", "двор", "семь",
                      "birth", "marriage", "death", "census", "godparent",
                      "household")
        for path in _modules("rules/*.py"):
            source = path.read_text(encoding="utf-8").lower()
            hits = [w for w in vocabulary if w in source]
            self.assertEqual([], hits, f"{path.name} names record kinds: {hits}")


class EveryModuleHasABudget(unittest.TestCase):
    def test_no_module_escapes_the_budget(self):
        """A module no pattern covers is checked by nothing — a new subpackage
        would inherit no rule at all."""
        from fnmatch import fnmatch
        for path in _FACTS.rglob("*.py"):
            if path.name == "__init__.py" or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(_FACTS).as_posix()
            with self.subTest(module=rel):
                self.assertTrue(any(fnmatch(rel, pattern) for pattern in _BUDGET),
                                f"{rel} is covered by no import budget")


class ChecksDoNoIO(unittest.TestCase):
    def test_a_check_never_touches_the_filesystem(self):
        for path in _modules("checks/*.py"):
            for name in _imported_geni_modules(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertNotIn(name, _EXTRACT_FORBIDDEN_MODULES)


class ExtractorsDoNoIO(unittest.TestCase):
    def test_an_extractor_never_touches_the_filesystem(self):
        for path in _modules("extract/*.py"):
            for name in _imported_geni_modules(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertNotIn(name, _EXTRACT_FORBIDDEN_MODULES,
                                     f"{path.name} imports {name}; reading files "
                                     f"is the CLI's job")
