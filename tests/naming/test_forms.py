"""The rules of the forms of a name (`verso.ru.naming.forms`): one example a branch. The rules are held to the
shipped base by `test_base.py` (`test_rule_equals_forms`: an entry of the base's `forms.tsv` is never what the rule
gives).
"""
from __future__ import annotations

import pytest

from verso.ru.gender import Gender
from verso.ru.naming import derive_old_patronymic
from verso.ru.naming.forms import genitive, modern_from_old, modern_patronymic, old_patronymic

M, F = Gender.MALE, Gender.FEMALE


@pytest.mark.parametrize(("father", "son", "daughter"), [
    ("Иван", "Иванович", "Ивановна"),          # a hard consonant
    ("Никита", "Никитич", "Никитична"),        # -а
    ("Илья", "Ильич", "Ильична"),              # -я
    ("Андрей", "Андреевич", "Андреевна"),      # -й
    ("Авель", "Авелевич", "Авелевна"),         # -ь, was «Авельович»
    ("Игорь", "Игоревич", "Игоревна"),         # -ь, was «Игорьович»
    ("Азария", "Азариевич", "Азариевна"),      # -ия, was «Азариич»
    ("Гаврила", "Гаврилович", "Гавриловна"),    # -ила, was «Гаврилич»
    ("Самойла", "Самойлович", "Самойловна"),    # -йла, was «Самойлич»
    ("Семён", "Семёнович", "Семёновна"),       # ё stays the name's own
])
def test_rule_examples(father: str, son: str, daughter: str) -> None:
    assert (modern_patronymic(father, M), modern_patronymic(father, F)) == (son, daughter)


@pytest.mark.parametrize(("father", "son", "daughter"), [
    ("Иван", "Иванов", "Иванова"),
    ("Никита", "Никитин", "Никитина"),
    ("Илья", "Ильин", "Ильина"),
    ("Осия", "Осин", "Осина"),                 # -ия drops its «и»: the table's every one
    ("Андрей", "Андреев", "Андреева"),
    ("Игорь", "Игорев", "Игорева"),
    ("Семён", "Семёнов", "Семёнова"),
])
def test_old_rule_examples(father: str, son: str, daughter: str) -> None:
    assert (old_patronymic(father, M), old_patronymic(father, F)) == (son, daughter)


@pytest.mark.parametrize(("name", "sex", "gen"), [
    ("Иван", M, "Ивана"),
    ("Семён", M, "Семёна"),
    ("Марфа", F, "Марфы"),
    ("Микишка", M, "Микишки"),                 # -а after a velar
    ("Илья", M, "Ильи"),
    ("Андрей", M, "Андрея"),
    ("Игорь", M, "Игоря"),
    ("Любовь", F, "Любови"),
    ("Игорь", None, "Игоря"),                  # no sex: a man's -ь
    ("Василько", M, "Василько"),               # a vowel the rule leaves alone
    ("Эстер", F, "Эстер"),                     # a woman's name on a hard consonant does not decline
    ("Эстер", None, "Эстера"),                 # without a sex: a man's
])
def test_genitive_examples(name: str, sex: Gender | None, gen: str) -> None:
    assert genitive(name, sex) == gen


@pytest.mark.parametrize(("old", "modern"), [
    ("Иванов", "Иванович"),
    ("Андреев", "Андреевич"),
    ("Иванова", "Ивановна"),
    ("Андреева", "Андреевна"),
    ("Кузьмин", None),                          # «-ин» has no rule: Кузьмич, Ильинична
    ("Бурмяй", None),
])
def test_modern_from_old_examples(old: str, modern: str | None) -> None:
    assert modern_from_old(old) == modern


def test_old_patronymic_of_a_father_the_lexicon_does_not_know() -> None:
    """The lexicon's short form first, then the short form of the modern one — then the rule."""
    assert derive_old_patronymic("Зюзяк", M) == "Зюзяков"


def test_empty_is_empty() -> None:
    assert modern_patronymic("", M) == old_patronymic("", F) == genitive("", None) == ""
    assert modern_from_old("") is None
