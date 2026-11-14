"""0.1.0 moved what the CLI did for everyone else into the library (verso.core.pipeline,
verso.ru.naming.names_table); its CLI modules re-exported the moved names for callers outside
the repo until 0.1.0. A CLI module now answers only for the names it uses itself."""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(("module", "name"), [
    ("verso.ru.cli.generate_tf", "discover_records"), ("verso.ru.cli.generate_tf", "admit_listed"),
    ("verso.ru.cli.generate_tf", "RECORD_TYPES"), ("verso.ru.cli.generate_tf", "_load_module"),
    ("verso.ru.cli.generate_tf", "_categorize"), ("verso.ru.cli.generate_tf", "ConsolidationBlock"),
    ("verso.ru.cli.generate_tf", "translate_village"),
    ("verso.ru.cli.facts", "assertions_of"), ("verso.ru.cli.facts", "_dated"),
    ("verso.ru.cli.names", "format_row"), ("verso.ru.cli.names", "insertion_index"), ("verso.ru.cli.names", "_INDEXED"),
])
def test_a_cli_module_answers_only_for_its_own_names(module: str, name: str):
    assert not hasattr(importlib.import_module(module), name), f"{module}.{name}"
