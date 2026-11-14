"""A DSL file is v1 (the facade); whoever adds an import writes v1 — Verso's edits, a book's
defaults, `migrate-statuses` — and a new file is v1. A v0 file (`geni.*`) is refused with the
command that rewrites it."""
from __future__ import annotations

import ast
from pathlib import Path

import libcst as cst
import pytest

from verso.ru.cli import migrate_statuses
from verso.ru.cli.export_csv import export_file
from verso.ru.dsl import describe, signatures
from verso.ru.dsl.source import (EditError, Imports, add_import, bound_names, drop_imports, dsl_form,
                                 format_import)
from verso.ru.importers.google_sheets.births import generate_births
from test_google_sheets_importer import _make_row

V0 = """\
from calendar import Month

from geni.domain import Gender, person
from geni.domain.statuses import PEASANT_MALE
from geni.dsl.records.births import birth, birth_records

x = 1
"""
V1 = """\
from verso.ru.dsl import Gender, Month, birth, birth_records, person
from verso.ru.dsl.statuses import PEASANT_MALE

x = 1
"""
REFUSED = "DSL v0: verso upgrade-dsl <файл>"


def _add(text: str, code: str) -> str:
    module = cst.parse_module(text)
    imports = Imports(bound_names(module))
    imports.need(code)
    for mod, name in sorted(imports.needed):
        module = add_import(module, mod, name)
    return module.code


def test_the_form_of_a_file():
    assert dsl_form(cst.parse_module(V1)) == "v1"
    assert dsl_form(cst.parse_module("x = 1\n")) == "v1"
    assert dsl_form(cst.parse_module("from corpus.statuses import A\n")) == "v1"
    with pytest.raises(EditError) as refused:
        dsl_form(cst.parse_module(V0))
    assert str(refused.value) == REFUSED


def test_a_constant_goes_into_the_facade_s_import():
    assert describe.constant_by_code()["MESHCHANIN"].module == "verso.ru.dsl.statuses"
    assert "from verso.ru.dsl.statuses import MESHCHANIN, PEASANT_MALE\n" in _add(V1, "MESHCHANIN")
    assert "from verso.ru.dsl.causes_of_death import FEVER\n" in _add(V1, "FEVER")
    assert "from verso.ru.dsl import Gender, Month, Relationship, birth" in _add(V1, "Relationship.FATHER")


def test_a_v0_file_is_refused_with_the_hint():
    for code in ("MESHCHANIN", "Relationship.FATHER"):
        with pytest.raises(EditError) as refused:
            _add(V0, code)
        assert str(refused.value) == REFUSED
    with pytest.raises(EditError):
        migrate_statuses.add_import(V0, {"MESHCHANIN"})


def test_a_corpus_constant_comes_from_corpus():
    # The tests' workspace reads a corpus's corpus/: its statuses are corpus.statuses'.
    assert describe.constant_by_code()["MANILOV_LK_PEASANT_MALE"].module == "corpus.statuses"
    assert "from corpus.statuses import MANILOV_LK_PEASANT_MALE\n" in _add(V1, "MANILOV_LK_PEASANT_MALE")


def _need_function(text: str, func: str) -> str:
    module = cst.parse_module(text)
    imports = Imports(bound_names(module))
    imports.need_function(func)
    for mod, name in sorted(imports.needed):
        module = add_import(module, mod, name)
    return module.code


def test_relative_and_recorddefaults_come_from_the_facade():
    assert signatures.IMPORT_OF == {"relative": "verso.ru.dsl", "RecordDefaults": "verso.ru.dsl"}
    assert "from verso.ru.dsl import Gender, Month, birth, birth_records, person, relative\n" in _need_function(
        V1, "relative")
    assert "from verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_records, person\n" in _need_function(
        V1, "RecordDefaults")


def test_an_import_is_wrapped_as_the_corpus_wraps_it():
    assert format_import("verso.ru.dsl", ["person", "Gender"]) == "from verso.ru.dsl import Gender, person"
    long = format_import("verso.ru.dsl", ["Gender", "Month", "RecordDefaults", "birth", "birth_month",
                                          "birth_records", "page", "person"])
    assert long == ("from verso.ru.dsl import (Gender, Month, RecordDefaults, birth, birth_month, birth_records, page,\n"
                    "                          person)")
    assert all(len(line) <= 100 for line in long.splitlines())


def test_a_name_added_to_a_v1_import_is_wrapped_again():
    text = ("# шапка\nfrom verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_month, birth_records, person\n"
            "from verso.ru.dsl.statuses import PEASANT_MALE\n\nx = 1\n")
    module = cst.parse_module(text)
    for name in ("relative", "Relationship"):
        module = add_import(module, "verso.ru.dsl", name)
    assert module.code == (
        "# шапка\n"
        "from verso.ru.dsl import (Gender, Month, RecordDefaults, Relationship, birth, birth_month,\n"
        "                          birth_records, person, relative)\n"
        "from verso.ru.dsl.statuses import PEASANT_MALE\n\nx = 1\n")


def test_a_new_import_line_stands_where_the_codemod_puts_it():
    # corpus.statuses, the facade, its catalogs — so `verso upgrade-dsl --check` finds nothing to do.
    from verso.ru.dsl.upgrade import upgrade
    code = _add(V1, "GOLOVLEV_PEASANT_FEMALE")
    assert code.startswith("from corpus.statuses import GOLOVLEV_PEASANT_FEMALE\nfrom verso.ru.dsl import ")
    code = _add(code, "FEVER")
    assert "from verso.ru.dsl.causes_of_death import FEVER\nfrom verso.ru.dsl.statuses import" in code
    assert upgrade(code, ("GOLOVLEV_PEASANT_FEMALE",)) == code


def test_a_name_dropped_from_a_v1_import_is_wrapped_again():
    # What the writer adds and then drops comes back as it was.
    text = ("from verso.ru.dsl import (Month, RecordDefaults, marriage, marriage_month, marriage_records, page,\n"
            "                          person)\n\nx = 1\n")
    added = add_import(cst.parse_module(text), "verso.ru.dsl", "Side")
    assert added.code.startswith("from verso.ru.dsl import (Month, RecordDefaults, Side, marriage,")
    assert drop_imports(added, {"Side"}).code == text


def test_an_import_with_a_comment_is_not_wrapped_again():
    text = "from verso.ru.dsl import (Gender,  # пол\n                          person)\n\nx = 1\n"
    code = add_import(cst.parse_module(text), "verso.ru.dsl", "page").code
    assert "# пол" in code and "page," in code and code.count("\n") == text.count("\n") + 1


def test_an_import_with_a_comment_above_it_is_wrapped_again():
    text = ("from corpus.statuses import GOLOVLEV_PEASANT_FEMALE\n# фасад\n"
            "from verso.ru.dsl import Gender, Month, RecordDefaults, birth, birth_month, birth_records, person\n\nx = 1\n")
    code = add_import(cst.parse_module(text), "verso.ru.dsl", "relative").code
    assert "\n# фасад\nfrom verso.ru.dsl import (Gender," in code
    assert all(len(line) <= 100 for line in code.splitlines())


def test_a_first_import_goes_under_the_docstring():
    code = add_import(cst.parse_module('"""Док."""\n\nx = 1\n'), "verso.ru.dsl", "person").code
    assert code == '"""Док."""\nfrom verso.ru.dsl import person\n\nx = 1\n'


def test_migrate_statuses_writes_dsl_v1():
    assert "from verso.ru.dsl.statuses import MESHCHANIN, PEASANT_MALE\n" in migrate_statuses.add_import(
        V1, {"MESHCHANIN"})


def test_the_importer_writes_dsl_v1(tmp_path: Path):
    row = _make_row(B_CHILD_NAME="Алексей", B_GENDER="муж", B_B_MONTH="4", B_B_DAY="3", B_RECORD_NUM="1",
                    B_PAGE="12")
    text = generate_births([row], "ГАТО", "1", "1", "1", "Заманиловка", "Церковь", 1804)
    tree = ast.parse(text)
    header = [n for n in tree.body if isinstance(n, ast.ImportFrom | ast.Import)]
    assert header and all(isinstance(n, ast.ImportFrom) and n.module is not None
                          and n.module.startswith("verso.ru.dsl") for n in header)
    assert "import os" not in text and "__main__" not in text
    path = tmp_path / "Заманиловка" / "1804" / "zamanilovka_births_1804.py"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    assert [p.name for p in export_file(path, tmp_path / "out")] == ["Заманиловка_1804_births_familio.csv"]
