"""The reconciliation channel: a list entry or a card, and who it may be.

The rule is the one the first cards were folded by hand with (same given name
by base form, same father, a surname variant, the birth where the source gives
one). These pin each clause and each guard on a made-up
village; the channel's oracle on the corpus is `--audit-folded`, measured on
the 61 folds made by hand (Глуповы Горы 47, Нижняя Яичница 8, Маниловка 4,
Горюхино 2).
"""
from __future__ import annotations

import unittest
from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.facts.checks.reconcile import (
    RETIRED_BIRTH_APART, RETIRED_LIFE_APART, RETIRED_SAME_HOUSEHOLD, RETIRED_SAME_LIST, RETIRED_SEEN_BEFORE_BIRTH, RETIRED_TWO_BAPTISMS, VERDICT_AMBIGUOUS, VERDICT_CANDIDATE, VERDICT_NONE, AliasBook, Channel, PARENTS, Side, audit_folded, civil_parents, learned_aliases, match, reconcile)
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import Assertion, AssertionSet, NameClaim, Persona, Record
from verso.ru.gender import Gender

PETR = ("Петръ", "Ивановъ", "Сидоровъ")


def _born(num: int, year: int, child: str = "Иванъ", father=PETR,
          surname: str | None = None) -> Any:
    kid = person(child, None, surname) if surname else person(child)
    return birth_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         birth(num, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                               child=kid, father=person(*father)))


def _list(*entries: Any, year: int = 1917) -> Any:
    return name_list_records("A", "1", "1", "1", "Тестовка", year, *entries,
                             document_type="Список избирателей")


def _facts(*books: tuple[Any, str]) -> AssertionSet:
    out: list[Assertion] = []
    for book, name in books:
        for rec in getattr(book, "records", []):
            if getattr(rec, "year", None) is None:
                rec.year = book.year
        if hasattr(book, "households"):
            out += facts_from_census([(book, name)], village="Тестовка")
        elif hasattr(book, "entries"):
            out += facts_from_name_lists([(book, name)], village="Тестовка")
        elif name.startswith("d"):
            out += facts_from_deaths([(r, name) for r in book.records], village="Т")
        else:
            out += facts_from_births([(r, name) for r in book.records], village="Т")
    return AssertionSet(out)


def _identity(facts: AssertionSet,
              who_is: dict[tuple[str, str], str]) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    """(source file, locator) → a canonical name; anyone else stands alone."""
    keys: dict[Persona, IdentityKey] = {}
    for a in facts.of(NameClaim):
        name = who_is.get((a.cite.source_file, a.cite.locator))
        keys[a.subject] = (name or f"{a.cite.source_file}:{a.cite.locator}",)

    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        return keys.get
    return identity


class TheRule(unittest.TestCase):
    def test_an_age_that_fits_the_birth_is_a_high_candidate(self):
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"),
                                            age=40)), "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)
        self.assertEqual("HIGH", r.confidence)
        self.assertEqual(("b1.py:child",), r.survivors[0].person.key)

    def test_without_an_age_the_candidate_is_medium(self):
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"))),
                        "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual("MEDIUM", r.confidence)

    def test_the_father_is_read_from_the_birth_record_itself(self):
        """A newborn carries no patronymic; the record names the father, and a
        list entry by another father is not him."""
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Семеновъ", "Сидоровъ"))),
                        "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual(VERDICT_NONE, r.verdict)
        self.assertEqual((), r.matches)

    def test_a_surname_a_letter_off_is_one_family(self):
        facts = _facts((_born(1, 1877, surname="Сидоровъ"), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидаровъ"))),
                        "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)

    def test_a_spelling_one_man_s_records_carry_is_learned(self):
        """Бикешеев in one record of a man, Бекешев in another: the corpus has
        joined the two spellings, and a card spelled Бикешеев finds a Бекешев."""
        facts = _facts(
            (_born(1, 1870, child="Семенъ", father=("Андрей", "Ильинъ", "Бекешевъ")), "b1.py"),
            (_born(2, 1890, father=("Семенъ", "Андреевъ", "Бекешевъ")), "b2.py"),
            (_born(3, 1895, child="Петръ", father=("Семенъ", "Андреевъ", "Бикешеевъ")), "b3.py"),
            (_list(listed_person(1, person("Иванъ", "Семеновъ", "Бикешеевъ"))), "l.py"))
        who = {("b1.py", "child"): "semen", ("b2.py", "father"): "semen",
               ("b3.py", "father"): "semen"}
        found = {r.target.key: r for r in reconcile(facts, _identity(facts, who))}
        self.assertEqual(VERDICT_CANDIDATE, found[("l.py:listed",)].verdict)
        self.assertEqual(("b2.py:child",), found[("l.py:listed",)].survivors[0].person.key)


class TheGuards(unittest.TestCase):
    def test_an_age_too_far_from_the_birth_retires_the_match(self):
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"),
                                            age=20)), "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual(VERDICT_NONE, r.verdict)
        self.assertEqual(RETIRED_BIRTH_APART, r.matches[0].retired)

    def test_a_man_buried_before_the_list_is_not_on_it(self):
        buried = death_records("A", "1", "1", "1", "Тестовка", "Ц", 1900,
                               death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY,
                                     deceased=person("Иванъ", "Петровъ", "Сидоровъ")))
        facts = _facts((_born(1, 1877), "b1.py"), (buried, "d1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"))),
                        "l.py"))
        who = {("b1.py", "child"): "ivan", ("d1.py", "deceased"): "ivan"}
        [r] = reconcile(facts, _identity(facts, who))
        self.assertEqual(RETIRED_LIFE_APART, r.matches[0].retired)

    def test_two_entries_of_one_list_are_two_people(self):
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ")),
                              listed_person(2, person("Иванъ", "Петровъ", "Сидоровъ"))),
                        "l.py"))
        # Entry 1 is already folded into the born Иван; entry 2 stands alone.
        keys = {a.cite.record_num: a.subject for a in facts.of(NameClaim)
                if a.cite.source_file == "l.py"}
        ivan = next(a.subject for a in facts.of(NameClaim)
                    if a.cite.source_file == "b1.py" and a.cite.locator == "child")

        def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
            def key(who: Persona) -> IdentityKey | None:
                if who in (ivan, keys["1"]):
                    return ("ivan",)
                return (str(who),)
            return key
        [r] = reconcile(facts, identity)
        self.assertEqual(RETIRED_SAME_LIST, r.matches[0].retired)

    def test_two_namesakes_surviving_are_ambiguous(self):
        facts = _facts((_born(1, 1877), "b1.py"), (_born(2, 1879), "b2.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"))),
                        "l.py"))
        [r] = reconcile(facts, _identity(facts, {}))
        self.assertEqual(VERDICT_AMBIGUOUS, r.verdict)
        self.assertEqual(2, len(r.survivors))


def _godparent(year: int, num: int = 9) -> Any:
    """A birth record naming a Иван Петров Сидоров as godfather."""
    return birth_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         birth(num, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                               child=person("Семенъ"), father=person("Лука", "Ильинъ"),
                               god_parent1=person("Иванъ", "Петровъ", "Сидоровъ")))


class TheGuardsOfDates(unittest.TestCase):
    @staticmethod
    def _born_against_godfather(born: int, named: int) -> Any:
        facts = _facts((_born(1, born, surname="Сидоровъ"), "b1.py"),
                       (_godparent(named), "b9.py"))
        channel = Channel(is_target=lambda s: s.key == ("b1.py:child",),
                          in_pool=lambda s: s.key == ("b9.py:god_parent1",),
                          auditable=lambda s: False)
        [r] = match(facts, _identity(facts, {}), channel)
        return r.matches[0]

    def test_named_in_a_record_before_the_other_was_born(self):
        """A man born in 1914 and a father named in 1899 are
        two men — whoever a record names was born by its day."""
        self.assertEqual(RETIRED_SEEN_BEFORE_BIRTH,
                         self._born_against_godfather(1914, 1899).retired)

    def test_a_birth_keeps_the_slack_two_births_are_compared_with(self):
        """A year somebody wrote down may be two years out, as `birth_gap`
        allows: named in 1913, born «1914», is not yet two people."""
        self.assertIsNone(self._born_against_godfather(1914, 1913).retired)

    def test_a_godparent_after_the_other_s_death_is_someone_else(self):
        buried = death_records("A", "1", "1", "1", "Тестовка", "Ц", 1890,
                               death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY,
                                     deceased=person("Иванъ", "Петровъ", "Сидоровъ")))
        facts = _facts((buried, "d1.py"), (_godparent(1900), "b9.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"))),
                        "l.py"))
        who = {("d1.py", "deceased"): "ivan"}
        [r] = reconcile(facts, _identity(facts, who))
        retired = {m.person.key: m.retired for m in r.matches}
        self.assertEqual(RETIRED_LIFE_APART, retired[("ivan",)])


class TheMatcher(unittest.TestCase):
    def test_two_members_of_one_household_are_two_people(self):
        roll = census_records("ГАТО", "12", "1", "1", "Тестовка", 1850,
                              household("4",
                                        member(1, person("Петръ", "Ивановъ", "Сидоровъ"),
                                               CensusRole.HEAD, age=60),
                                        member(2, person("Иванъ", "Петровъ", "Сидоровъ"),
                                               CensusRole.SON, age=30),
                                        member(3, person("Иванъ", "Петровъ", "Сидоровъ"),
                                               CensusRole.SON, age=28)))
        facts = _facts((roll, "rs.py"))
        channel = Channel(is_target=lambda s: s.key == ("rs.py:member3",),
                          in_pool=lambda s: s.key == ("rs.py:member2",),
                          auditable=lambda s: False)
        [r] = match(facts, _identity(facts, {}), channel)
        self.assertEqual(RETIRED_SAME_HOUSEHOLD, r.matches[0].retired)

    def test_a_channel_may_require_the_father_on_both_sides(self):
        facts = _facts((_born(1, 1877, surname="Сидоровъ"), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", None, "Сидоровъ"))), "l.py"))

        def target(side: Side) -> bool:
            return side.key == ("l.py:listed",)

        def pool(side: Side) -> bool:
            return side.key == ("b1.py:child",)
        loose = Channel(is_target=target, in_pool=pool, auditable=target)
        strict = Channel(is_target=target, in_pool=pool, auditable=target,
                         require_father=True)
        self.assertEqual(VERDICT_CANDIDATE, match(facts, _identity(facts, {}), loose)[0].verdict)
        self.assertEqual(VERDICT_NONE, match(facts, _identity(facts, {}), strict)[0].verdict)

    def _christened(self, later: int) -> Any:
        facts = _facts((_born(1, 1915, surname="Сидоровъ"), "b1.py"),
                       (_born(2, later, surname="Сидоровъ"), "b2.py"))
        channel = Channel(is_target=lambda s: s.key == ("b2.py:child",),
                          in_pool=lambda s: s.key == ("b1.py:child",),
                          auditable=lambda s: False, require_father=True)
        [r] = match(facts, _identity(facts, {}), channel)
        return r

    def test_two_christenings_are_two_children(self):
        # Two namesakes a year apart, well inside the slack of an age — but
        # each has his own entry.
        r = self._christened(1916)
        self.assertEqual(RETIRED_TWO_BAPTISMS, r.matches[0].retired)
        self.assertEqual(VERDICT_NONE, r.verdict)

    def test_a_grown_man_the_age_of_both_boys_is_not_high(self):
        # Two namesakes christened a year apart, and one adult of the same name
        # the age of both — the birth check cannot say whose he is.
        roll = census_records("ГАТО", "12", "1", "1", "Тестовка", 1935,
                              household("4", member(1, person("Иванъ", "Петровъ", "Сидоровъ"),
                                                    CensusRole.HEAD, age=19)))
        facts = _facts((_born(1, 1915, surname="Сидоровъ"), "b1.py"),
                       (_born(2, 1916, surname="Сидоровъ"), "b2.py"), (roll, "rs.py"))
        channel = Channel(is_target=lambda s: s.key == ("b2.py:child",),
                          in_pool=lambda s: s.key in {("b1.py:child",), ("rs.py:member1",)},
                          auditable=lambda s: False, require_father=True)
        [r] = match(facts, _identity(facts, {}), channel)
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)
        self.assertEqual("MEDIUM", r.confidence)
        self.assertEqual({None, RETIRED_TWO_BAPTISMS}, {m.retired for m in r.matches})

    def test_one_birth_copied_into_two_entries_is_one_child(self):
        r = self._christened(1915)
        self.assertIsNone(r.matches[0].retired)
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)

    def test_the_alias_book_forgets_one_man_s_lesson(self):
        facts = _facts(
            (_born(1, 1870, child="Семенъ", father=("Андрей", "Ильинъ", "Бекешевъ")), "b1.py"),
            (_born(2, 1890, father=("Семенъ", "Андреевъ", "Бекешевъ")), "b2.py"),
            (_born(3, 1895, child="Петръ", father=("Семенъ", "Андреевъ", "Бикешеевъ")), "b3.py"))
        who = {("b1.py", "child"): "semen", ("b2.py", "father"): "semen",
               ("b3.py", "father"): "semen"}
        identity = _identity(facts, who)
        from verso.ru.facts.identity import conclusions
        sides = [Side.of(k, c.claims) for k, c in sorted(conclusions(facts, identity).items())]
        book = AliasBook(sides)
        self.assertEqual(learned_aliases(sides), book.aliases())
        self.assertTrue(book.aliases())
        self.assertEqual({}, book.aliases(excluding=("semen",)))
        self.assertEqual(learned_aliases(sides, excluding=("semen",)),
                         book.aliases(excluding=("semen",)))


class TheParentsChannel(unittest.TestCase):
    """«Who are the parents of a civil act?» — a parent of a ZAGS act, read
    against the people the corpus already holds."""

    SIDOROV = ("Петръ", "Ивановичъ", "Сидоровъ")

    def _act(self, father_age: int | None = 31) -> Any:
        """A 1924 act: Пётр Иванович Сидоров, father, aged `father_age`."""
        return birth_records("A", "1", "1", "1", "Тестовка", "ЗАГС", 1924,
                             birth(1, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                                   child=person("Николай"), father=person(*self.SIDOROV),
                                   father_age=father_age))

    def _wedding(self, groom_age: int, num: int = 1) -> Any:
        from verso.ru.dsl.records.marriages import marriage, marriage_records
        book = marriage_records("A", "1", "1", "1", "Тестовка", "Ц", 1915,
                                marriage(num, 7, Month.JANUARY,
                                         groom=person("Петръ", "Ивановъ", "Сидоровъ"),
                                         bride=person("Анна", "Ильина"),
                                         groom_age=groom_age))
        return book

    def _facts(self, *extra: tuple[Any, str], father_age: int | None = 31) -> AssertionSet:
        from verso.ru.facts.extract.marriages import facts_from_marriages
        out: list[Assertion] = []
        for book, name in ((self._act(father_age), "act.py"),) + extra:
            if hasattr(book, "records") and book.records and hasattr(book.records[0], "groom"):
                for rec in book.records:
                    rec.year = book.year
                out += facts_from_marriages([(r, name) for r in book.records], village="Т")
            else:
                out += _facts((book, name))
        return AssertionSet(out)

    def _run(self, facts: AssertionSet) -> list[Any]:
        return match(facts, _identity(facts, {}), PARENTS)

    def test_the_father_of_an_act_finds_the_groom_his_age_fits(self):
        facts = self._facts((self._wedding(22), "w.py"))
        [r] = self._run(facts)
        self.assertEqual(("act.py:father",), r.target.key)
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)
        self.assertEqual("HIGH", r.confidence)
        self.assertEqual(("w.py:groom",), r.survivors[0].person.key)

    def test_an_age_too_far_from_the_groom_retires_him(self):
        facts = self._facts((self._wedding(40), "w.py"))
        [r] = self._run(facts)
        self.assertEqual(VERDICT_NONE, r.verdict)
        self.assertEqual(RETIRED_BIRTH_APART, r.matches[0].retired)

    def test_two_grooms_the_age_fits_are_ambiguous(self):
        facts = self._facts((self._wedding(22), "w1.py"), (self._wedding(23), "w2.py"))
        [r] = self._run(facts)
        self.assertEqual(VERDICT_AMBIGUOUS, r.verdict)

    def test_a_birth_in_the_church_books_is_found_by_name_and_father(self):
        facts = self._facts((_born(1, 1893, child="Петръ", father=("Иванъ", "Семеновъ", "Сидоровъ"),
                                   surname="Сидоровъ"), "mk.py"))
        [r] = self._run(facts)
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)
        self.assertEqual("HIGH", r.confidence)
        self.assertEqual(("mk.py:child",), r.survivors[0].person.key)

    def test_a_target_does_not_find_itself(self):
        facts = self._facts()
        [r] = self._run(facts)
        self.assertEqual(VERDICT_NONE, r.verdict)
        self.assertEqual((), r.matches)

    def test_the_parent_of_another_act_is_not_a_candidate(self):
        """«The same father in two acts» is `parent-age-drift`'s question."""
        second = birth_records("A", "1", "1", "1", "Тестовка", "ЗАГС", 1926,
                               birth(2, Gender.FEMALE, 5, 6, Month.MAY, Month.MAY,
                                     child=person("Анна"), father=person(*self.SIDOROV),
                                     father_age=33))
        facts = self._facts((second, "act2.py"))
        results = self._run(facts)
        self.assertEqual(2, len(results))
        self.assertTrue(all(r.verdict == VERDICT_NONE and not r.matches for r in results))

    def test_who_is_a_civil_parent(self):
        facts = self._facts((self._wedding(22), "w.py"))
        from verso.ru.facts.checks.reconcile import _sides
        sides = {s.key: s for s in _sides(facts, _identity(facts, {}))}
        self.assertTrue(civil_parents(sides[("act.py:father",)]))
        self.assertFalse(civil_parents(sides[("act.py:child",)]))
        self.assertFalse(civil_parents(sides[("w.py:groom",)]))

    def test_a_parent_without_an_age_is_no_target(self):
        facts = self._facts(father_age=None)
        self.assertEqual([], self._run(facts))


class TheOracle(unittest.TestCase):
    def test_a_fold_made_by_hand_is_found_again(self):
        facts = _facts((_born(1, 1877), "b1.py"),
                       (_list(listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"),
                                            age=40)), "l.py"))
        who = {("b1.py", "child"): "ivan", ("l.py", "listed"): "ivan"}
        [a] = audit_folded(facts, _identity(facts, who))
        self.assertEqual("FOUND", a.outcome)
        self.assertEqual(("ivan",), a.canonical)


if __name__ == "__main__":
    unittest.main()
