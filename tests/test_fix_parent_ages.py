"""`verso fix-parent-ages`: the parents' ages a civil birth's comment says, moved into `father_age=` / `mother_age=`.

Invented fixtures, written to a tmp dir as DSL files. The reader is `verso.ru.parent_age_text`; the codemod edits the
`comment=` keyword's span and writes a file only when its Records JSON differs by `father_age`, `mother_age` and
`comment` of births alone.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.ru import parent_age_text
from verso.ru.cli import fix_parent_ages
from verso.ru.linters import findings

HEAD = '''from verso.ru.dsl import Gender, Month, birth, birth_records, person

'''


def _birth(number: int, comment: str, extra: str = "") -> str:
    return (f'    birth({number}, Gender.MALE, 4, 6, Month.MARCH, Month.MARCH, child=person("Лука"),\n'
            f'          comment={comment!r}{extra}),\n')


def _book(*records: str, civil: bool = True, church: str = "") -> str:
    flag = "    civil=True,\n" if civil else ""
    return (HEAD + f'births = birth_records(\n    "Госархив", "21", "3", "114", "Горюхино", {church!r}, 1924,\n'
            + "".join(records) + flag + ")\n")


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "Горюхино" / "1924" / "goryukhino_births_1924.py"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fixed(tmp_path: Path, comment: str, extra: str = "") -> tuple[str, fix_parent_ages.Outcome]:
    path = _file(tmp_path, _book(_birth(1, comment, extra)))
    outcome = fix_parent_ages.fix_file(path)
    return path.read_text(encoding="utf-8"), outcome


def test_both_ages_move_and_the_rest_of_the_comment_stays(tmp_path: Path):
    text, outcome = _fixed(tmp_path, "записан; отцу 26, матери 22; заявитель — отец", ", reviewed=False")
    assert "father_age=26, mother_age=22, comment='записан; заявитель — отец', reviewed=False" in text
    assert outcome.refused is None and outcome.changed
    assert dict(outcome.forms) == {"father_and_mother": 1}


def test_a_comment_said_whole_goes_with_its_keyword(tmp_path: Path):
    text, _ = _fixed(tmp_path, "отцу 26, матери 22")
    assert "father_age=26, mother_age=22)" in text and "comment" not in text


def test_a_doubt_gives_its_figure_and_stays(tmp_path: Path):
    text, _ = _fixed(tmp_path, "отцу 42 (?), матери 43")
    assert "father_age=42, mother_age=43, comment='отцу 42 (?)'" in text


@pytest.mark.parametrize("comment", ["матери 3…", "Мария(?) (2[?](?))", "что-то другое"])
def test_a_figure_no_field_can_take_leaves_the_file_alone(tmp_path: Path, comment: str):
    path = _file(tmp_path, _book(_birth(1, comment)))
    before = path.read_text(encoding="utf-8")
    outcome = fix_parent_ages.fix_file(path)
    assert path.read_text(encoding="utf-8") == before and not outcome.changed and outcome.refused is None


@pytest.mark.parametrize(("comment", "kept", "fields"), [
    ("отцу 34 (или 31 ?), матери 30", "comment='отцу 34 (или 31 ?)'", "father_age=34, mother_age=30"),
    ("отцу 40(?)/43(?)", "comment='отцу 40(?)/43(?)'", "father_age=40"),
    ("матери 30?", "comment='матери 30?'", "mother_age=30"),
    ("отцу 26", "", "father_age=26"),
    ("матери 22", "", "mother_age=22"),
    ("возраст 31 и 29", "", "father_age=31, mother_age=29"),
    ("отцу 26, матери 3…", "comment='матери 3…'", "father_age=26"),
])
def test_forms(tmp_path: Path, comment: str, kept: str, fields: str):
    text, _ = _fixed(tmp_path, comment)
    assert fields in text and (kept in text if kept else "comment" not in text)


@pytest.mark.parametrize(("comment", "kept"), [
    ("родители: Иван (35) и Феврония (35) Горюхины", "comment='родители: Иван и Феврония Горюхины'"),
    ("родители: Иван (29 л.) и Феврония (22 лет) Горюхины", "comment='родители: Иван и Феврония Горюхины'"),
])
def test_the_1920_form(tmp_path: Path, comment: str, kept: str):
    text, outcome = _fixed(tmp_path, comment)
    assert kept in text and "father_age=" in text and "mother_age=" in text
    assert dict(outcome.forms) == {"parents_1920": 1}


def test_a_second_run_changes_nothing(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "записан; отцу 42 (?), матери 43; ещё")))
    fix_parent_ages.fix_file(path)
    once = path.read_text(encoding="utf-8")
    outcome = fix_parent_ages.fix_file(path)
    assert path.read_text(encoding="utf-8") == once and not outcome.changed


def test_a_written_field_is_not_overwritten(tmp_path: Path):
    text, _ = _fixed(tmp_path, "отцу 26, матери 22", ", father_age=27")
    assert "father_age=27" in text and "father_age=26" not in text and "mother_age=22" in text
    assert "comment='отцу 26'" in text


def test_a_church_book_is_left_alone(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22"), civil=False, church="Церковь"))
    before = path.read_text(encoding="utf-8")
    assert not fix_parent_ages.fix_file(path).changed and path.read_text(encoding="utf-8") == before


def test_check_reports_without_writing(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    before = path.read_text(encoding="utf-8")
    outcome = fix_parent_ages.fix_file(path, check=True)
    assert outcome.changed and path.read_text(encoding="utf-8") == before


def test_the_codemod_moves_what_the_linter_finds_and_no_more(tmp_path: Path):
    comments = ["записан; отцу 26, матери 22", "отцу 42 (?), матери 43", "матери 3…", "возраст 31 и 29",
                "родители: Иван (35) и Феврония (35) Горюхины", "Мария(?) (2[?](?))", "отцу 40(?)/43(?)", "пусто"]
    path = _file(tmp_path, _book(*(_birth(n, c) for n, c in enumerate(comments, 1))))
    before = path.read_text(encoding="utf-8")
    zgs006 = [f for f in findings.lint_text(before, path) if f.code == "ZGS006"]
    outcome = fix_parent_ages.fix_file(path)
    assert not [f for f in findings.lint_text(path.read_text(encoding="utf-8"), path) if f.code == "ZGS006"]
    assert len(zgs006) == sum(1 for c in comments if parent_age_text.read_comment(c) for _ in parent_age_text.read_comment(c).ages)
    assert outcome.births == sum(1 for c in comments if parent_age_text.read_comment(c))


def test_the_guard_refuses_a_change_of_another_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(fix_parent_ages, "FIELDS", {"father": "father_age", "mother": "year"})
    outcome = fix_parent_ages.fix_file(path)
    assert path.read_text(encoding="utf-8") == before
    assert outcome.refused and not outcome.changed


def test_main_prints_counts_per_form_and_exits_by_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22"), _birth(2, "матери 30"), _birth(3, "возраст 31 и 29")))
    assert fix_parent_ages.main([str(path), "--check"]) == 1
    out = capsys.readouterr().out
    assert "«отцу N, матери M»: 1" in out and "«матери M»: 1" in out and "«возраст N и M»: 1" in out
    assert fix_parent_ages.main([str(path)]) == 0
    capsys.readouterr()
    assert fix_parent_ages.main([str(path), "--check"]) == 0


def test_births_that_already_hold_ages_do_not_stop_the_file(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 30", ", father_age=30"), _birth(2, "матери 22")))
    outcome = fix_parent_ages.fix_file(path)
    assert outcome.changed and outcome.refused is None and outcome.births == 1
    assert "father_age=30" in path.read_text(encoding="utf-8") and "mother_age=22" in path.read_text(encoding="utf-8")


def test_the_guard_names_the_record_it_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    monkeypatch.setattr(fix_parent_ages, "FIELDS", {"father": "father_age", "mother": "year"})
    assert "birth/m1" in (fix_parent_ages.fix_file(path).refused or "")


def test_a_none_field_is_empty_and_takes_its_figure_where_it_stands(tmp_path: Path):
    text, outcome = _fixed(tmp_path, "отцу 26, матери 22", ", father_age=None")
    assert "father_age=26" in text and "father_age=None" not in text and "mother_age=22" in text
    assert text.count("father_age") == 1 and outcome.changed and outcome.refused is None


def test_a_comment_said_whole_with_a_none_field_leaves_no_stray_comma(tmp_path: Path):
    text, _ = _fixed(tmp_path, "отцу 26", ", father_age=None")
    assert "father_age=26)" in text and ", ," not in text and "comment" not in text


def test_the_guard_says_which_side_did_not_build(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 26")))
    broken = path.read_text(encoding="utf-8") + "\nraise ValueError('x')\n"
    assert "до правки" in (fix_parent_ages.guard(path, broken, broken) or "")
    assert "после правки" in (fix_parent_ages.guard(path, path.read_text(encoding="utf-8"), broken) or "")


def test_a_1920_fragment_is_cut_to_the_clause_and_no_more(tmp_path: Path):
    text, outcome = _fixed(tmp_path, "родители: Иван Петров (35) и Анна (?) (29 л.) Горюхины, занятие не указ.")
    assert "father_age=35, mother_age=29, comment='родители: Иван Петров и Анна (?) Горюхины, занятие не указ.'" in text
    assert dict(outcome.forms) == {"parents_1920": 1}


def test_the_guard_refuses_digits_that_do_not_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A move whose fields say another figure than the one that left the comment is refused, the record named."""
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    before = path.read_text(encoding="utf-8")
    real = fix_parent_ages.plan
    def wrong(source: str):
        text, births, forms = real(source)
        return text.replace("father_age=26", "father_age=62"), births, forms

    monkeypatch.setattr(fix_parent_ages, "plan", wrong)
    outcome = fix_parent_ages.fix_file(path)
    assert path.read_text(encoding="utf-8") == before and outcome.refused and "62" in outcome.refused


def test_a_doubt_s_figure_in_both_places_is_conserved(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 42 (?), матери 43")))
    assert fix_parent_ages.fix_file(path).refused is None


def test_a_directory_stands_for_its_py_files(tmp_path: Path, capsys):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (path.parent / "broken.py").write_text("def (:\n", encoding="utf-8")
    code = fix_parent_ages.main([str(tmp_path), str(tmp_path / "notes.txt"), str(tmp_path / "gone.py"), "--check"])
    err = capsys.readouterr().err
    assert code == 2
    assert "notes.txt" in err and "gone.py" in err and "broken.py" in err and err.count("пропущен") == 3


def test_line_endings_are_kept(tmp_path: Path):
    path = _file(tmp_path, "")
    text = _book(_birth(1, "отцу 26, матери 22; записан")).replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    assert fix_parent_ages.fix_file(path).changed
    raw = path.read_bytes()
    assert b"father_age=26" in raw and raw.count(b"\r\n") == raw.count(b"\n") > 3


def test_hidden_directories_and_venv_are_not_walked(tmp_path: Path):
    path = _file(tmp_path, _book(_birth(1, "отцу 26, матери 22")))
    for hidden in (".venv", ".git"):
        (tmp_path / hidden).mkdir()
        (tmp_path / hidden / "x.py").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    files, skipped = fix_parent_ages.expand([tmp_path])
    assert files == [path] and not skipped
