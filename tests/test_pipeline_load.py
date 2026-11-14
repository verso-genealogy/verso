"""verso.core.pipeline.load — reading one DSL file as a module, on files in tmp_path."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from verso.core.pipeline import load
from verso.core.pipeline.load import load_module


def test_load_module_reads_the_source_not_the_bytecode(tmp_path: Path):
    # A .pyc is trusted while the file's mtime second and size hold: Verso saving
    # one surname for another of its length within a second got the old records back.
    path = tmp_path / "1900" / "x_births_1900.py"
    path.parent.mkdir()
    path.write_text('x = "аа"\n', encoding="utf-8")
    stamp = path.stat()
    assert load_module(path).x == "аа"
    path.write_text('x = "бб"\n', encoding="utf-8")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert load_module(path).x == "бб"


def test_load_module_does_not_run_main(tmp_path: Path):
    path = tmp_path / "1900" / "x_births_1900.py"
    path.parent.mkdir()
    path.write_text('x = 1\nif __name__ == "__main__":\n    raise SystemExit(3)\n', encoding="utf-8")
    assert load_module(path).x == 1


def test_load_module_registers_nothing(tmp_path: Path):
    path = tmp_path / "1900" / "x_births_1900.py"
    path.parent.mkdir()
    path.write_text("import json\nx = 1\n", encoding="utf-8")
    before = set(sys.modules)
    load_module(path)
    assert set(sys.modules) - before == set()


def test_build_text_runs_the_text_not_the_file(tmp_path: Path):
    path = tmp_path / "Село" / "1900" / "selo_births_1900.py"
    path.parent.mkdir(parents=True)
    path.write_text("X = 1\n", encoding="utf-8")
    space = load.build_text(path, "X = 2\n")
    assert (space["X"], space["__name__"], space["__file__"]) == (2, "dsl_preview_selo_births_1900", str(path))


def test_import_check_names_the_last_line_of_the_error(tmp_path: Path):
    path = tmp_path / "bad.py"
    path.write_text("raise ValueError('нет такого имени')\n", encoding="utf-8")
    assert load.import_check(path, cwd=tmp_path) == "ValueError: нет такого имени"
    path.write_text("X = 1\n", encoding="utf-8")
    assert load.import_check(path, cwd=tmp_path) is None


def test_import_problem_carries_the_code(tmp_path: Path):
    """What the error is, beside what it says: an exception's `verso_code`, read in the child."""
    path = tmp_path / "bad.py"
    path.write_text("e = ValueError('нет такого имени')\ne.verso_code = 'gender.name'\nraise e\n", encoding="utf-8")
    assert load.import_problem(path, cwd=tmp_path) == load.ImportProblem("ValueError: нет такого имени", "gender.name")
    path.write_text("raise ValueError('x')\n", encoding="utf-8")
    assert load.import_problem(path, cwd=tmp_path) == load.ImportProblem("ValueError: x", None)
    path.write_text("X = 1\n", encoding="utf-8")
    assert load.import_problem(path, cwd=tmp_path) is None


def test_import_problem_is_plain_text_where_colour_is_forced(tmp_path: Path, monkeypatch):
    """The child's error is data, not a terminal's: an environment forcing colour (FORCE_COLOR, as a
    desktop app may set it) leaves no escape codes in the text."""
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("PYTHON_COLORS", "1")
    path = tmp_path / "bad.py"
    path.write_text("raise ValueError('нет такого имени')\n", encoding="utf-8")
    assert load.import_check(path, cwd=tmp_path) == "ValueError: нет такого имени"


def test_dsl_files_go_in_the_order_of_the_book(tmp_path: Path):
    """A year's files in the order its metric book holds them — births, marriages,
    deaths — then what else the year has, as village.db takes them in."""
    village = tmp_path / "Село"
    names = {"1851": ["v_census_1851_d12.py", "v_deaths_1851.py", "v_marriages_1851.py",
                      "v_births_1851.py", "other_marriages_1851.py", "v_external_sources_1851.py"],
             "1850": ["v_deaths_1850.py", "v_births_1850.py"], "notes": ["n.py"]}
    for year, files in names.items():
        (village / year).mkdir(parents=True)
        for name in files:
            (village / year / name).write_text("", encoding="utf-8")
    assert [p.relative_to(village).as_posix() for p in load.dsl_files(village)] == [
        "1850/v_births_1850.py", "1850/v_deaths_1850.py",
        "1851/v_births_1851.py", "1851/other_marriages_1851.py", "1851/v_marriages_1851.py",
        "1851/v_deaths_1851.py", "1851/v_census_1851_d12.py", "1851/v_external_sources_1851.py"]
    (tmp_path / ".hidden" / "1850").mkdir(parents=True)
    (tmp_path / "corpus").mkdir()
    assert load.village_dirs(tmp_path) == [village]
