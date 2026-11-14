"""The names oracle's file (`verso.ru.naming.oracle`): what a row says, and a row asked again of a lexicon."""
from __future__ import annotations

from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import oracle
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, NameEntry

M = Gender.MALE

LEXICON = Lexicon.of([Layer("t", {(M, "Зюзей"): NameEntry(M, "Зюзей", source="editor"),
                                  (M, "Зюзя"): NameEntry(M, "Зюзя", ("Зюзей",), source="editor")},
                            {(M, "Зюзей"): FormsEntry(M, "Зюзей", "Зюзея", "Зюзеевич", "Зюзеевна", "Зюзеев", "Зюзеева",
                                                      "editor")}, {})])


def test_a_file_round_trips_sorted(tmp_path: Path) -> None:
    rows = [oracle.Row("matching_base", ("Зюзя", "M"), "Зюзей"),
            oracle.Row("canonicalize_patronymic", ("Зюзькин",), {"raises": "ValueError"}),
            oracle.Row("get_gender_from_name", ("Зюзя",), "M")]
    path = tmp_path / "oracle.tsv"
    oracle.write(path, rows)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("#") and lines[1:] == sorted(lines[1:])
    assert lines[1] == 'canonicalize_patronymic\t["Зюзькин"]\t{"raises":"ValueError"}'
    assert sorted(oracle.parse(path)) == sorted(rows)


def test_a_question_is_asked_of_the_lexicon_given() -> None:
    rows = [oracle.Row("matching_base", ("Зюзя", "M"), None),
            oracle.Row("get_gender_from_name", ("Зюзя",), None),
            oracle.Row("father_name_for_patronymic", ("Зюзеев",), None),
            oracle.Row("canonicalize_patronymic", ("Зюзькин",), None),
            oracle.Row("validate_first_name", ("Зюзя",), None)]
    asked = oracle.answers(rows, LEXICON)
    assert [a.answer for a in asked] == ["Зюзей", "M", "Зюзей", {"raises": "ValueError"}, True]
    assert ("name", "Зюзя") in asked[0].keys
    assert ("old_m", "Зюзеев") in asked[2].keys


def test_same_tells_true_from_one() -> None:
    assert oracle.same("M", "M") and not oracle.same(True, 1) and not oracle.same(None, "")
