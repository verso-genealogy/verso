"""The DSL's public facade — `verso.ru.dsl` and its three catalogs of constants (DSL v1)."""
from __future__ import annotations

import ast
import calendar
import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path


import verso.ru.dsl
import verso.ru.dsl.causes_of_death
import verso.ru.dsl.marital_status
import verso.ru.dsl.statuses
import verso.ru.domain.marital_status
from verso.ru.domain.status import Status
from tests.codepaths import child_env, code_files, module_name, package_dir


FACADE = {
    "birth", "christening", "birth_month", "birth_month_year", "birth_records",
    "marriage", "marriage_month", "marriage_month_year", "marriage_records",
    "death", "death_month", "death_month_year", "death_records",
    "divorce", "divorce_month", "divorce_records",
    "census_records", "household", "member", "CONFESSION_LIST", "CensusRole",
    "external_source_records", "criminal_record", "wwi_record", "wwii_record", "WwiDocumentType",
    "WwiiDocumentType",
    "name_list_records", "listed_person",
    "person", "page", "book", "relative", "Relationship", "RecordDefaults", "EventDate", "Side", "Gender",
    "Status", "Month", "NOT_IN_DOCUMENT",
}
CATALOGS = {"geni.domain.statuses": verso.ru.dsl.statuses,  # verso-rename: keep
            "geni.domain.causes_of_death": verso.ru.dsl.causes_of_death,  # verso-rename: keep
            "geni.domain.marital_status": verso.ru.dsl.marital_status}  # verso-rename: keep


def test_the_facade_is_41_names():
    assert len(verso.ru.dsl.__all__) == len(set(verso.ru.dsl.__all__)) == 41
    assert set(verso.ru.dsl.__all__) == FACADE
    assert verso.ru.dsl.DSL_API == 1 and "DSL_API" not in verso.ru.dsl.__all__
    assert verso.ru.dsl.Month is calendar.Month


def test_widow_is_two_constants():
    assert "WIDOW" not in verso.ru.dsl.__all__
    assert isinstance(verso.ru.dsl.statuses.WIDOW, Status)
    assert verso.ru.dsl.marital_status.WIDOW is verso.ru.domain.marital_status.WIDOW


def test_the_catalogs_are_their_sizes():
    assert len(verso.ru.dsl.causes_of_death.__all__) == 57
    assert len(verso.ru.dsl.marital_status.__all__) == 8
    assert "MARITAL_STATUSES" not in verso.ru.dsl.marital_status.__all__
    for module in CATALOGS.values():
        assert all(hasattr(module, name) for name in module.__all__)


def test_every_dsl_module_imports_first(tmp_path: Path):
    # A module of the DSL's package imported first, in a fresh interpreter, imports: the
    # facade it runs first imports the record modules, which must not want the facade back.
    names = ["verso.ru.dsl", *(m.name for m in pkgutil.walk_packages(verso.ru.dsl.__path__, "verso.ru.dsl."))]
    assert "verso.ru.dsl.records.births" in names
    env = child_env()
    for name in names:
        done = subprocess.run([sys.executable, "-c", f"import {name}"], cwd=tmp_path, env=env,
                              capture_output=True, text=True)
        assert done.returncode == 0, f"{name}: {done.stderr.strip().splitlines()[-1:]}"


def test_the_library_does_not_import_the_facade():
    # The facade is for the data: the library takes a name from the module that defines it.
    found = []
    for path in code_files("verso.core", "verso.ru"):
        if path == package_dir("verso.ru.dsl") / "__init__.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "verso.ru.dsl":
                found += [f"{module_name(path)}:{node.lineno} {a.name}" for a in node.names
                          if a.name in verso.ru.dsl.__all__]
    assert found == []


def test_the_config_types_are_public():
    import verso.core.targets.geni as models
    from verso.core.targets.geni import date, event, profile, union
    assert models.__all__ == ["GeniDate", "GeniEvent", "GeniProfile", "GeniUnion"]
    assert (models.GeniDate, models.GeniEvent, models.GeniProfile, models.GeniUnion) == (
        date.GeniDate, event.GeniEvent, profile.GeniProfile, union.GeniUnion)


def test_every_constant_verso_offers_is_importable_from_its_module():
    # describe names the module a constant is written from; the facade's catalogs must hold it.
    from verso.ru.dsl import describe
    missing = [(c.module, c.import_name) for consts in describe.catalogs().values() for c in consts
               if not hasattr(importlib.import_module(c.module), c.import_name)]
    assert missing == []
