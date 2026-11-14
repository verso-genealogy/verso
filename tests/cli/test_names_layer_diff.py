"""`verso names layer-diff`: the smallest layer over the base that answers an oracle as the old tables do.

The oracle is written here from the fixture's own table, by asking it a fixed set of questions; no corpus's
oracle is read.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from verso.ru.cli import names as names_cli
from verso.ru.gender import Gender
from verso.ru.naming import layer_diff, oracle
from verso.ru.naming.layer_files import FILES, FilesLayer, base, read_rows
from verso.ru.naming.layers import LEGACY_FILES
from verso.ru.naming.legacy import compile_legacy
from verso.ru.naming.lexicon import IGNORE_LIST, Layer, Lexicon

HEADER = ("Пол,Имя,Имя-основа,От,\"Склонения, связи\",Родительный падеж,Отчество старое М,Отчество старое Ж,"
          "Отчество М,Отчество Ж,Источник\n")


def _questions(legacy: Layer) -> list[oracle.Row]:
    """A fixed set of questions about every name (a father's patronymic of a man's name), short and modern patronymic
    of `legacy`."""
    names = sorted({n for _, n in legacy.names})
    old = sorted({f for fe in legacy.forms.values() for f in (fe.old_patronymic_m, fe.old_patronymic_f) if f})
    modern = sorted({f for fe in legacy.forms.values() for f in (fe.patronymic_m, fe.patronymic_f) if f})
    asked: list[tuple[str, tuple[object, ...]]] = []
    for n in names:
        for g in ("M", "F", None):
            asked += [("canonicalize_name", (n, g)), ("matching_base", (n, g)), ("genitive_given_name", (n, g))]
        if (Gender.MALE, n) in legacy.names:  # a father's patronymic is asked of a man's name
            for g in ("M", "F"):
                asked += [("derive_patronymic", (n, g)), ("derive_old_patronymic", (n, g))]
        asked += [(f, (n,)) for f in ("get_gender_from_name", "validate_first_name", "is_ignored_name",
                                      "ignored_name_gender", "genitive_from_name")]
    for p in old:
        asked += [(f, (p,)) for f in ("canonicalize_patronymic", "father_name_for_patronymic",
                                      "get_gender_from_old_patronymic", "is_ignored_patronymic")]
        asked.append(("validate_old_patronymic", (p, False)))
    asked += [("find_old_patronymic_by_modern", (m,)) for m in modern]
    genitives = sorted({fe.genitive for fe in legacy.forms.values() if fe.genitive})
    asked += [("name_from_genitive", (g,)) for g in genitives]      # looked up by a genitive: kind «genitive»
    rows = [oracle.Row(f, args, None) for f, args in asked]
    answers = oracle.answers(rows, Lexicon.of([legacy]).complete())
    return [row._replace(answer=a.answer) for row, a in zip(rows, answers, strict=True)]


def _digest(directory: Path) -> dict[str, str]:
    return {file: hashlib.sha256((directory / file).read_bytes()).hexdigest() for file in FILES.values()}


def _run(legacy_dir: Path, oracle_file: Path, out: Path) -> int:
    return names_cli.main(["layer-diff", "--from-legacy", str(legacy_dir), "--base", "ru", "--oracle",
                           str(oracle_file), "--out", str(out)])


def test_layer_diff_reproduces_oracle(legacy_workspace: Path, tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    legacy = compile_legacy(*(legacy_workspace / name for name in LEGACY_FILES))
    below = base().load()
    rows = _questions(legacy)
    assert len(rows) > 500
    oracle_file = tmp_path / "oracle.tsv"
    oracle.write(oracle_file, rows)

    assert _run(legacy_workspace, oracle_file, tmp_path / "layer") == 0
    said = capsys.readouterr().out
    assert "вопросов" in said

    layer = FilesLayer(tmp_path / "layer", name="corpus", writable=True).load()
    got = oracle.answers(rows, Lexicon.of([below, layer]).complete())
    assert [(r.function, r.args, a.answer) for r, a in zip(rows, got, strict=True)
            if not oracle.same(a.answer, r.answer)] == []
    # Smaller than the table it stands for, and every entry the old table's.
    assert 0 < len(layer.names) < len(legacy.names)
    assert any(e.removes for e in layer.names.values())  # a sex the base holds and the fixture's table does not
    sources = {row["source"] for rows_ in read_rows(tmp_path / "layer").values() for _, row in rows_}
    assert sources <= {"legacy", IGNORE_LIST}
    # The fold a consolidation check compares patronymics by answers as the old table's, though no oracle asks it.
    folds = layer_diff.derived_questions(rows)
    assert [a.answer for a in oracle.answers(folds, Lexicon.of([below, layer]))] == \
        [a.answer for a in oracle.answers(folds, Lexicon.of([legacy]))]

    # The same inputs write the same bytes: over the first run's, in a process of its own with another hash seed.
    first = _digest(tmp_path / "layer")
    seed = "1" if os.environ.get("PYTHONHASHSEED") != "1" else "2"
    subprocess.run([sys.executable, "-m", "verso.ru.cli.names", "layer-diff", "--from-legacy", str(legacy_workspace),
                    "--base", "ru", "--oracle", str(oracle_file), "--out", str(tmp_path / "layer")],
                   check=True, capture_output=True, env={**os.environ, "PYTHONHASHSEED": seed})
    assert _digest(tmp_path / "layer") == first


def test_a_sex_the_old_table_does_not_hold_is_removed(tmp_path: Path) -> None:
    """The base holds «Кирилла» as a woman's name (the святцы) and a man's (the books); an old table that knows the
    man's alone: the layer removes the woman's (`-` in bases), and the sum answers «M» as the table did."""
    old = tmp_path / "old"
    old.mkdir()
    (old / "names.csv").write_text(HEADER + "М,Кирилла,Кирилл,,,Кириллы,Кириллов,Кириллова,Кириллович,Кирилловна,\n",
                                   encoding="utf-8")
    rows = [oracle.Row("get_gender_from_name", ("Кирилла",), "M")]
    oracle_file = tmp_path / "oracle.tsv"
    oracle.write(oracle_file, rows)
    assert _run(old, oracle_file, tmp_path / "layer") == 0
    assert "F\tКирилла\t-\t\tlegacy\t\n" in (tmp_path / "layer" / "names.tsv").read_text(encoding="utf-8")


def test_what_no_entry_settles_is_listed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An old table that knows «Мария» as a woman's name alone answers a son's short patronymic of her with nothing;
    the base gives «Мариев» through a man's name of its own the table never held — no entry of the table settles it:
    it is listed, the exit is 1, and the layer is written all the same."""
    old = tmp_path / "old"
    old.mkdir()
    (old / "names.csv").write_text(HEADER + "Ж,Мария,,,,Марии,,,,,\n", encoding="utf-8")
    rows = [oracle.Row("derive_old_patronymic", ("Мария", "M"), "")]
    oracle_file = tmp_path / "oracle.tsv"
    oracle.write(oracle_file, rows)
    assert _run(old, oracle_file, tmp_path / "layer") == 1
    assert 'derive_old_patronymic ["Мария","M"]: "" ≠ ' in capsys.readouterr().err
    assert (tmp_path / "layer" / "names.tsv").is_file()


def test_a_stale_oracle_is_said(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An answer recorded otherwise than the old tables give today: the layer follows the tables, and says so."""
    old = tmp_path / "old"
    old.mkdir()
    (old / "names.csv").write_text(HEADER + "М,Зюзей,,,,Зюзея,Зюзеев,Зюзеева,Зюзеевич,Зюзеевна,\n", encoding="utf-8")
    oracle_file = tmp_path / "oracle.tsv"
    oracle.write(oracle_file, [oracle.Row("validate_first_name", ("Зюзей",), False)])
    assert _run(old, oracle_file, tmp_path / "layer") == 0
    assert "слой следует" in capsys.readouterr().err


def test_a_conflict_no_answer_of_the_old_table_pins_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Two names of the old table whose rules give one short patronymic the old table knows nothing of: no pin can say
    which holds — the catalogued error and exit 1, no traceback, no layer."""
    old = tmp_path / "old"
    old.mkdir()
    (old / "names.csv").write_text(HEADER + "М,Зюзя,,,,Зюзи,,,,,\nМ,Зюзия,,,,Зюзии,,,,,\n", encoding="utf-8")
    oracle_file = tmp_path / "oracle.tsv"
    oracle.write(oracle_file, [oracle.Row("validate_first_name", ("Зюзя",), True),
                               oracle.Row("validate_first_name", ("Зюзия",), True)])
    assert _run(old, oracle_file, tmp_path / "layer") == 1
    err = capsys.readouterr().err
    assert "Зюзин" in err and "Traceback" not in err
    assert not (tmp_path / "layer").exists()


def test_an_answer_the_notation_cannot_hold_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from verso.ru.naming import names_registry
    def answers_a_number(name: str, gender: Gender | None = None) -> object:  # noqa: ARG001 — the function's signature
        return 1

    monkeypatch.setattr(names_registry, "matching_base", answers_a_number)
    with pytest.raises(oracle.OracleError):
        oracle.ask("matching_base", ("Зюзя", "M"))
