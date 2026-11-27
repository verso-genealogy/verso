"""`task.of_targets`: an `of` under the head told apart from oneself and nobody."""
from __future__ import annotations

from verso.ru.reading import task
from verso.ru.reading.task import OfTarget


def test_numbered_of_the_heads_number():
    persons = [{"number": "5", "role": "head"}, {"number": "6", "role": "wife", "of": "5"}]
    assert task.of_targets(persons)[1] == OfTarget(None, False, True)


def test_unnumbered_of_the_heads_place():
    persons = [{"role": "head"}, {"role": "son", "of": "1"}]
    assert task.of_targets(persons)[1] == OfTarget(None, False, True)


def test_doubtful_head():
    persons = [{"role": "head"}, {"role": "son", "of": "1?"}]
    assert task.of_targets(persons)[1] == OfTarget(None, True, True)


def test_oneself_and_nobody_are_not_under_head():
    persons = [{"role": "head"}, {"role": "son", "of": "2"}, {"role": "son", "of": "9"}]
    got = task.of_targets(persons)
    assert got[1] == OfTarget(None, False, False)
    assert got[2] == OfTarget(None, False, False)


def test_empty_of_and_a_real_link():
    persons = [{"role": "head"}, {"role": "son"}, {"role": "wife", "of": "2"}]
    got = task.of_targets(persons)
    assert got[1].under_head is False
    assert got[2] == OfTarget(1, False, False)
