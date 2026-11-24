"""`verso.ru.parent_age_text`: the parents' ages a comment says, and what stays of it."""
from __future__ import annotations

import pytest

from verso.ru.parent_age_text import FATHER, MOTHER, read_comment


@pytest.mark.parametrize(("comment", "ages", "stays"), [
    ("отцу 26, матери 22", {FATHER: 26, MOTHER: 22}, None),
    ("записан; отцу 26, матери 22; заявитель — отец", {FATHER: 26, MOTHER: 22}, "записан; заявитель — отец"),
    ("отцу 26 лет, матери 22 года", {FATHER: 26, MOTHER: 22}, None),
    ("отцу 42 (?), матери 43", {FATHER: 42, MOTHER: 43}, "отцу 42 (?)"),
    ("отцу 34 (или 31 ?)", {FATHER: 34}, "отцу 34 (или 31 ?)"),
    ("отцу 40(?)/43(?)", {FATHER: 40}, "отцу 40(?)/43(?)"),
    ("отцу 26, матери 22.", {FATHER: 26, MOTHER: 22}, None),
    ("отцу 26, матери 22;заявитель — отец", {FATHER: 26, MOTHER: 22}, "заявитель — отец"),
    ("записан;отцу 26;заявитель", {FATHER: 26}, "записан;заявитель"),
    ("родители: Иван Петров (35) и Анна Мария (?) Ивановна (35) Горюхины, занятие не указ.", {FATHER: 35, MOTHER: 35},
     "родители: Иван Петров и Анна Мария (?) Ивановна Горюхины, занятие не указ."),
    ("родители: Лука (31 л.), Дарья (27 л.) Заманиловы", {FATHER: 31, MOTHER: 27}, "родители: Лука, Дарья Заманиловы"),
    ("родители: Иван (45), Наталья (37) Горюхины / Заманиловы (?), занятие не указано", {FATHER: 45, MOTHER: 37},
     "родители: Иван, Наталья Горюхины / Заманиловы (?), занятие не указано"),
    ("родители: Иван (26) и Александра (26) Горюхины (отчества и занятие не указ.)", {FATHER: 26, MOTHER: 26},
     "родители: Иван и Александра Горюхины (отчества и занятие не указ.)"),
    ("родители: Иван Петров(?) (23?) и Анна (23?) Горюхины", {FATHER: 23, MOTHER: 23},
     "родители: Иван Петров(?) (23?) и Анна (23?) Горюхины"),
    ("родители: Иван Петров (52) и Анна (37(?)) Горюхины", {FATHER: 52, MOTHER: 37},
     "родители: Иван Петров и Анна (37(?)) Горюхины"),
    ("родители: Иван (26? л.), Мария (23 л.) Горюхины", {FATHER: 26, MOTHER: 23}, "родители: Иван (26? л.), Мария Горюхины"),
    ("родители: Федор (22) и Мария(?) (2[?](?)) Горюхины", {FATHER: 22}, "родители: Федор и Мария(?) (2[?](?)) Горюхины"),
    ("родители: Яков (возр. не указ.) и Дарья (22) Горюхины", {MOTHER: 22}, "родители: Яков (возр. не указ.) и Дарья Горюхины"),
    ("родители: Иван Петров и Елена Романовы, возраст 38 и 37, по счёту: четвёртый", {FATHER: 38, MOTHER: 37},
     "родители: Иван Петров и Елена Романовы, по счёту: четвёртый"),
    ("матери 30?", {MOTHER: 30}, "матери 30?"),
    ("отцу 26, матери 3…", {FATHER: 26}, "матери 3…"),
    ("возраст 31 и 29", {FATHER: 31, MOTHER: 29}, None),
    ("родители: Иван (35) и Феврония (35) Горюхины", {FATHER: 35, MOTHER: 35},
     "родители: Иван и Феврония Горюхины"),
    ("родители: Иван (29 л.) и Феврония (22 лет) Горюхины", {FATHER: 29, MOTHER: 22},
     "родители: Иван и Феврония Горюхины"),
    ("а; отцу 26; б; матери 22; в", {FATHER: 26, MOTHER: 22}, "а; б; в"),
])
def test_what_moves_and_what_stays(comment: str, ages: dict[str, int], stays: str | None):
    found = read_comment(comment)
    assert found is not None and found.ages == ages and found.comment == stays


@pytest.mark.parametrize("comment", ["матери 3…", "Мария(?) (2[?](?))", "отцу 1234", "отцу 34 испр. 31", "родители: Иван (35) Горюхин", "родители: мать Вера (?) (24), отец не указан", "заявитель — отец", "", None])
def test_what_no_field_takes(comment: str | None):
    assert read_comment(comment) is None


def test_a_role_not_asked_for_stays():
    found = read_comment("отцу 26, матери 22", (MOTHER,))
    assert found is not None and found.ages == {MOTHER: 22} and found.comment == "отцу 26"
    assert read_comment("возраст 31 и 29", (MOTHER,)) is None


def test_a_role_is_read_once():
    found = read_comment("отцу 26; отцу 31")
    assert found is not None and found.ages == {FATHER: 26} and found.comment == "отцу 31"


@pytest.mark.parametrize("comment", [
    "отцу 1920?", "отцу 1/2", "отцу 42 1/2", "отцу 4200 (?)",
    "родители: Иван и Феврония (35) Горюхины, дети: Петр (5)",       # one slot before the label: no pair to give
    "родители: вдова Феврония (35), муж Иван (40)",                   # by position the ages would swap
    "родители: Иван (35) Горюхины и (40) Феврония",                   # a slot after no name
    "родители: Иван (35) и Феврония (29) и Петр (5) Горюхины",        # three candidate slots
    "вдова Феврония (35), муж Иван (40)",
])
def test_what_the_position_alone_would_give_stays(comment: str):
    assert read_comment(comment) is None


def test_the_children_s_ages_after_a_label_are_not_the_parents():
    found = read_comment("родители: Иван (35) и Феврония (29) Горюхины, дети: Петр (5)")
    assert found is not None and found.ages == {FATHER: 35, MOTHER: 29}
    assert found.comment == "родители: Иван и Феврония Горюхины, дети: Петр (5)"


def test_a_slash_is_a_doubt_between_two_figures():
    assert read_comment("отцу 40/43").ages == {FATHER: 40}
    assert read_comment("отцу 40/43").comment == "отцу 40/43"


def test_a_kept_fragment_is_kept_as_written():
    found = read_comment("отцу  42 (?), матери 43.")
    assert found is not None and found.ages == {FATHER: 42, MOTHER: 43} and found.comment == "отцу  42 (?)."
    both = read_comment("отцу  42 (?),  матери 43 (?).")
    assert both is not None and both.comment == "отцу  42 (?),  матери 43 (?)."


@pytest.mark.parametrize("comment", [
    "родители: Иван [Ф.] (35) и Феврония Ф. (29 л.) Горюхины",     # restored letters and an initial are name tokens
    "родители: Иван(?) (35) и Феврония(?) (29) Горюхины",
])
def test_a_name_token_may_carry_brackets_an_initial_or_doubt_marks(comment: str):
    found = read_comment(comment)
    assert found is not None and found.ages == {FATHER: 35, MOTHER: 29}


@pytest.mark.parametrize("comment", [
    "родители: Иван и Феврония (35) Горюхины, крестный Петр (50)",
    "родители: Иван и Феврония (35) Горюхины, сын Петр (5)",
    "родители: Иван (35) и Феврония (29) Горюхины, сын Петр (5)",
    "отцу 4/45",
])
def test_a_non_parents_slot_is_no_age(comment: str):
    found = read_comment(comment)
    assert found is None or (found.ages in ({FATHER: 35, MOTHER: 29},) and "Петр (5)" in (found.comment or ""))
