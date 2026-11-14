"""A list's neighbours as evidence: the household the list runs, read against
the kin the metric books state.

A 1917 list in household order writes a family in one stretch; an entry whose
candidate is the spouse, parent or child of the canonical its neighbour is has
the list and the books agreeing. These pin the rule on a made-up village —
including what it must NOT do: back anything on a list in another order, reach
past the span or across a surname, or change a channel that did not ask.
"""
from __future__ import annotations

import unittest
from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.consolidation.reconcile import findings_to_json, format_report
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.facts.checks.neighbours import CHILD, PARENT, SPOUSE
from verso.ru.facts.checks.reconcile import (
    LISTS_AND_CARDS, VERDICT_AMBIGUOUS, VERDICT_CANDIDATE, VERDICT_NONE, Channel, Reconciliation, audit_folded, match, reconcile)
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import Assertion, AssertionSet, NameClaim, Persona, Record
from verso.ru.gender import Gender

IVAN = ("Иванъ", "Петровъ", "Сидоровъ")
ORDERED = frozenset({"l.py"})


def _born(num: int, year: int, *, child: str = "Семенъ", father=IVAN,
          mother=("Марія", "Семенова", "Сидорова"), child_surname=None) -> Any:
    kid = person(child, None, child_surname) if child_surname else person(child)
    return birth_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         birth(num, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                               child=kid, father=person(*father),
                               mother=person(*mother) if mother else None))


def _list(*entries: Any, household_order: bool = True) -> Any:
    return name_list_records("A", "1", "1", "1", "Тестовка", 1917, *entries,
                             document_type="Список избирателей",
                             household_order=household_order)


def _facts(births: list[tuple[Any, str]], roster: Any) -> AssertionSet:
    out: list[Assertion] = []
    for book, name in births:
        for rec in book.records:
            rec.year = book.year
        out += facts_from_births([(r, name) for r in book.records], village="Т")
    out += facts_from_name_lists([(roster, "l.py")], village="Тестовка")
    return AssertionSet(out)


def _identity(facts: AssertionSet, who: dict[tuple[str, str], str]
              ) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    """(birth file, slot) or ("l.py", list №) → a canonical; the rest alone."""
    keys: dict[Persona, IdentityKey] = {}
    for a in facts.of(NameClaim):
        c = a.cite
        slot = c.record_num if c.source_file == "l.py" else c.locator
        keys[a.subject] = (who.get((c.source_file, slot))
                           or f"{c.source_file}:{c.record_num}:{c.locator}",)

    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        return keys.get
    return identity


COUPLE = {("b1.py", "father"): "ivan", ("b1.py", "mother"): "marija"}


def _of(found: list[Reconciliation], number: int) -> Reconciliation:
    [r] = [r for r in found if r.target.key == (f"l.py:{number}:listed",)]
    return r


class Backing(unittest.TestCase):
    def test_a_wife_beside_backs_her_husband_and_he_her(self):
        facts = _facts([(_born(1, 1895), "b1.py")], _list(
            listed_person(5, person(*IVAN)),
            listed_person(6, person("Марія", "Семенова", "Сидорова"))))
        found = reconcile(facts, _identity(facts, COUPLE), ORDERED)
        husband, wife = _of(found, 5), _of(found, 6)
        self.assertEqual((VERDICT_CANDIDATE, "HIGH"), (husband.verdict, husband.confidence))
        [b] = husband.proposed[0].backed
        self.assertEqual((6, ("marija",), SPOUSE), (b.neighbour.number, b.canonical, b.relation))
        self.assertEqual("HIGH", wife.confidence)

    def test_a_list_not_in_household_order_backs_nothing(self):
        """Маниловка's list runs by given name within the surname: a neighbour
        there is a namesake by surname, not a household."""
        facts = _facts([(_born(1, 1895), "b1.py")], _list(
            listed_person(5, person(*IVAN)),
            listed_person(6, person("Марія", "Семенова", "Сидорова")),
            household_order=False))
        found = reconcile(facts, _identity(facts, COUPLE), frozenset())
        self.assertEqual("MEDIUM", _of(found, 5).confidence)
        self.assertEqual((), _of(found, 5).proposed[0].backed)

    def test_a_channel_that_did_not_ask_is_unchanged(self):
        """`name-variants` is the matcher's second caller, and has no list."""
        facts = _facts([(_born(1, 1895), "b1.py")], _list(
            listed_person(5, person(*IVAN)),
            listed_person(6, person("Марія", "Семенова", "Сидорова"))))
        plain = Channel(LISTS_AND_CARDS.is_target, LISTS_AND_CARDS.in_pool,
                        LISTS_AND_CARDS.auditable)
        found = match(facts, _identity(facts, COUPLE), plain, ORDERED)
        self.assertEqual("MEDIUM", _of(found, 5).confidence)

    def test_a_parent_and_a_child(self):
        facts = _facts(
            [(_born(1, 1880, child="Иванъ", father=("Петръ", "Ивановъ", "Сидоровъ"),
                    mother=None, child_surname="Сидоровъ"), "b1.py")],
            _list(listed_person(5, person("Петръ", "Ивановъ", "Сидоровъ")),
                  listed_person(6, person(*IVAN))))
        who = {("b1.py", "father"): "petr", ("b1.py", "child"): "ivan"}
        found = reconcile(facts, _identity(facts, who), ORDERED)
        self.assertEqual(CHILD, _of(found, 5).proposed[0].backed[0].relation)
        self.assertEqual(PARENT, _of(found, 6).proposed[0].backed[0].relation)


class Namesakes(unittest.TestCase):
    def _two_ivans(self, *entries: Any) -> list[Reconciliation]:
        facts = _facts([(_born(1, 1895), "b1.py"),
                        (_born(2, 1896, mother=("Анна", "Ильина", "Сидорова")), "b2.py")],
                       _list(*entries))
        who = {**COUPLE, ("b2.py", "father"): "ivan_2", ("b2.py", "mother"): "anna"}
        return reconcile(facts, _identity(facts, who), ORDERED)

    def test_the_wife_beside_chooses_between_two_namesakes(self):
        found = self._two_ivans(listed_person(5, person(*IVAN)),
                                listed_person(6, person("Марія", "Семенова", "Сидорова")))
        r = _of(found, 5)
        self.assertEqual((VERDICT_CANDIDATE, "HIGH", True),
                         (r.verdict, r.confidence, r.by_neighbours))
        self.assertEqual([("ivan",)], [m.person.key for m in r.proposed])
        # the namesake is not retired — nothing says he is someone else
        self.assertEqual({("ivan",), ("ivan_2",)}, {m.person.key for m in r.survivors})

    def test_both_namesakes_backed_stay_ambiguous(self):
        found = self._two_ivans(listed_person(5, person(*IVAN)),
                                listed_person(6, person("Марія", "Семенова", "Сидорова")),
                                listed_person(7, person("Анна", "Ильина", "Сидорова")))
        self.assertEqual(VERDICT_AMBIGUOUS, _of(found, 5).verdict)

    def test_no_wife_beside_leaves_them_ambiguous(self):
        found = self._two_ivans(listed_person(5, person(*IVAN)))
        self.assertEqual(VERDICT_AMBIGUOUS, _of(found, 5).verdict)


class WhoIsANeighbour(unittest.TestCase):
    def _husband(self, *entries: Any, who: dict[tuple[str, str], str] | None = None
                 ) -> Reconciliation:
        facts = _facts([(_born(1, 1895), "b1.py")], _list(*entries))
        return _of(reconcile(facts, _identity(facts, {**COUPLE, **(who or {})}), ORDERED), 5)

    def test_past_the_span_is_not_a_neighbour(self):
        r = self._husband(listed_person(5, person(*IVAN)),
                          listed_person(10, person("Марія", "Семенова", "Сидорова")))
        self.assertEqual("MEDIUM", r.confidence)

    def test_the_number_decides_not_the_line_of_the_file(self):
        """Заманиловка's list is a selection: № 1127 is followed in the file by
        № 1138, and the two are not neighbours in the book."""
        r = self._husband(listed_person(5, person(*IVAN)),
                          listed_person(16, person("Марія", "Семенова", "Сидорова")))
        self.assertEqual("MEDIUM", r.confidence)

    def test_another_surname_is_another_family(self):
        """A wife written under her maiden name is not read as a neighbour —
        absent backing is no reason against, and this is why."""
        r = self._husband(listed_person(5, person(*IVAN)),
                          listed_person(6, person("Марія", "Семенова", "Бодаева")),
                          who={("l.py", "6"): "marija"})
        self.assertEqual("MEDIUM", r.confidence)

    def test_a_neighbour_already_folded_is_its_canonical(self):
        r = self._husband(listed_person(5, person(*IVAN)),
                          listed_person(6, person("Марья", "", "Сидорова")),
                          who={("l.py", "6"): "marija"})
        self.assertEqual("HIGH", r.confidence)
        self.assertEqual(("marija",), r.proposed[0].backed[0].canonical)


class TheListsOwnAges(unittest.TestCase):
    """A grandmother and her grandson's wife of one name, a few numbers apart
    around the grandson."""

    def _household(self) -> list[Reconciliation]:
        facts = _facts(
            [(_born(1, 1887, child="Тихонъ", father=("Лука", "Ѳоминъ", "Сидоровъ"),
                    mother=("Марѳа", "Петрова", "Сидорова")), "b1.py"),
             (_born(2, 1920, child="Савва", father=("Нилъ", "Пахомовъ", "Сидоровъ"),
                    mother=("Марѳа", "Петрова", "Сидорова")), "b2.py")],
            _list(listed_person(351, person("Марѳа", "Петрова", "Сидорова"), age=66),
                  listed_person(355, person("Нилъ", "Пахомовъ", "Сидоровъ"), age=26),
                  listed_person(356, person("Марѳа", "Петрова", "Сидорова"), age=22),
                  listed_person(360, person("Тихонъ", "Лукинъ", "Сидоровъ"), age=30)))
        who = {("b1.py", "mother"): "grandmother", ("b1.py", "child"): "pavel",
               ("b2.py", "father"): "jakov", ("b2.py", "mother"): "wife",
               ("l.py", "355"): "jakov", ("l.py", "360"): "pavel"}
        return reconcile(facts, _identity(facts, who), ORDERED)

    def test_a_woman_of_66_is_not_the_wife_of_a_man_of_26(self):
        r = _of(self._household(), 351)
        self.assertEqual(VERDICT_AMBIGUOUS, r.verdict)
        self.assertTrue(all(not m.backed for m in r.survivors))

    def test_a_woman_of_22_is_not_the_mother_of_a_man_of_30(self):
        r = _of(self._household(), 356)
        self.assertEqual((VERDICT_CANDIDATE, "HIGH"), (r.verdict, r.confidence))
        self.assertEqual([("wife",)], [m.person.key for m in r.proposed])
        [b] = r.proposed[0].backed
        self.assertEqual((355, SPOUSE), (b.neighbour.number, b.relation))


class OneCanonicalPerList(unittest.TestCase):
    def test_one_person_proposed_for_two_entries_is_proposed_for_neither(self):
        facts = _facts([(_born(1, 1895), "b1.py")], _list(
            listed_person(5, person(*IVAN)), listed_person(40, person(*IVAN))))
        found = reconcile(facts, _identity(facts, COUPLE), ORDERED)
        first, second = _of(found, 5), _of(found, 40)
        self.assertEqual((VERDICT_AMBIGUOUS, ("№40",)), (first.verdict, first.contested))
        self.assertEqual((VERDICT_AMBIGUOUS, ("№5",)), (second.verdict, second.contested))
        self.assertIn("предложен и строке №40", format_report(found, {}))


class TheWifeWithoutASurname(unittest.TestCase):
    """The records give the wife another surname than the list does — a bride
    is written with her maiden name, and so is this mother («Бодаева») — so no
    list entry of hers can match by name. Her husband beside her on the list
    can: his candidate's wife, named like her, is her."""

    def _found(self, wife: tuple[str, ...], *, wife_age=None, husband_age=None
               ) -> list[Reconciliation]:
        facts = _facts([(_born(1, 1895, mother=("Марія", "Семенова", "Бодаева")), "b1.py")], _list(
            listed_person(5, person(*IVAN), age=husband_age),
            listed_person(6, person(*wife), age=wife_age)))
        return reconcile(facts, _identity(facts, COUPLE), ORDERED)

    def test_the_husband_is_backed_by_the_name_of_his_wife(self):
        r = _of(self._found(("Марія", "Семенова", "Сидорова")), 5)
        self.assertEqual((VERDICT_CANDIDATE, "HIGH"), (r.verdict, r.confidence))
        [b] = r.proposed[0].backed
        self.assertEqual((6, ("marija",), SPOUSE, True),
                         (b.neighbour.number, b.canonical, b.relation, b.by_name))

    def test_the_wife_is_found_through_her_husband(self):
        r = _of(self._found(("Марія", "Семенова", "Сидорова")), 6)
        self.assertEqual((VERDICT_CANDIDATE, "HIGH", True),
                         (r.verdict, r.confidence, r.through_neighbour))
        self.assertEqual([("marija",)], [m.person.key for m in r.proposed])
        self.assertIn("найден(а) через соседа по списку",
                      format_report(self._found(("Марія", "Семенова", "Сидорова")), {}))

    def test_another_woman_beside_him_is_not_his_wife(self):
        found = self._found(("Анна", "Ильина", "Сидорова"))
        self.assertEqual("MEDIUM", _of(found, 5).confidence)
        self.assertEqual(VERDICT_NONE, _of(found, 6).verdict)

    def test_the_ages_must_fit_a_marriage(self):
        found = self._found(("Марія", "Семенова", "Сидорова"), wife_age=64, husband_age=24)
        self.assertEqual("MEDIUM", _of(found, 5).confidence)
        self.assertEqual(VERDICT_NONE, _of(found, 6).verdict)


class TheOracle(unittest.TestCase):
    def test_a_fold_made_by_hand_among_namesakes_is_found_by_the_wife(self):
        facts = _facts([(_born(1, 1895), "b1.py"),
                        (_born(2, 1896, mother=("Анна", "Ильина", "Сидорова")), "b2.py")],
                       _list(listed_person(5, person(*IVAN)),
                             listed_person(6, person("Марія", "Семенова", "Сидорова"))))
        who = {**COUPLE, ("b2.py", "father"): "ivan_2", ("b2.py", "mother"): "anna",
               ("l.py", "5"): "ivan", ("l.py", "6"): "marija"}
        identity = _identity(facts, who)
        without = {a.canonical: a.outcome for a in audit_folded(facts, identity)}
        with_list = {a.canonical: a.outcome
                     for a in audit_folded(facts, identity, ordered_lists=ORDERED)}
        self.assertEqual("AMONG", without[("ivan",)])
        self.assertEqual("FOUND", with_list[("ivan",)])


class TheReport(unittest.TestCase):
    def test_the_report_names_the_neighbour_and_the_namesake(self):
        facts = _facts([(_born(1, 1895), "b1.py"),
                        (_born(2, 1896, mother=("Анна", "Ильина", "Сидорова")), "b2.py")],
                       _list(listed_person(5, person(*IVAN)),
                             listed_person(6, person("Марія", "Семенова", "Сидорова"))))
        who = {**COUPLE, ("b2.py", "father"): "ivan_2", ("b2.py", "mother"): "anna"}
        found = reconcile(facts, _identity(facts, who), ORDERED)
        text = format_report(found, {})
        self.assertIn("выбран соседями по списку", text)
        self.assertIn("сосед по списку №6 Сидорова Мария Семеновна → marija — "
                      "супруг(а) кандидата", text)
        self.assertIn("· тоже по имени (тёзка или несведённый дубль), соседи не подтверждают:",
                      text)
        self.assertIn("по соседям", text.splitlines()[0])
        self.assertIn('"relation": "spouse"', findings_to_json(found))

    def test_the_flag_is_kept_on_the_records(self):
        self.assertTrue(_list().household_order)
        self.assertFalse(name_list_records("A", "1", "1", "1", "Т", 1917,
                                           document_type="С").household_order)


if __name__ == "__main__":
    unittest.main()
