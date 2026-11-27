"""One person's records naming two fathers — `facts-check check=father-claims`.

Each clause of agreement is pinned here on a made-up village, because each was
added after a false finding on the corpus: the patronymic a named father
derives («Изот»/«Изотович», whose table base is «Зотей»), the father the table
reads out of a patronymic («Егорович»/«Георгиевич»), the stem of a name the
table does not know (the 1717–1721 rolls), a father known by two names (a
roll writes one name for the man the metric books call by another), and chains of
agreement («Шумилин» and «Шумилов» through a named «Шумила»).
"""
from __future__ import annotations

import unittest
from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.ru.facts.checks.fathers import father_claims, father_findings
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import Assertion, AssertionSet, Citation, NameClaim, Persona, Record
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, relative


def _born(child: str, father: str, father_patronymic: str | None = None,
          year: int = 1830) -> Any:
    return birth_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         birth(1, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                               child=person(child),
                               father=person(father, father_patronymic)))


def _married(groom: str, patronymic: str, year: int = 1855) -> Any:
    return marriage_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                            marriage(1, 10, groom=person(groom, patronymic),
                                     bride=person("Анна", "Петрова")))


def _roll(*members: Any, year: int = 1850) -> Any:
    return census_records("ГАТО", "12", "1", "1", "Тестовка", year,
                          household("7", *members))


def _facts(*books: tuple[Any, str]) -> AssertionSet:
    out: list[Assertion] = []
    for book, name in books:
        if hasattr(book, "households"):
            out += facts_from_census([(book, name)], village="Тестовка")
            continue
        items = []
        for rec in book.records:
            if getattr(rec, "year", None) is None:
                rec.year = book.year
            items.append((rec, name))
        extract = {"b": facts_from_births, "m": facts_from_marriages,
                   "d": facts_from_deaths}[name[0]]
        out += extract(items, village="Тестовка")
    return AssertionSet(out)


def _identity(facts: AssertionSet, who_is: dict[tuple[str, str], str]
              ) -> Callable[[Record], Callable[[Persona], IdentityKey | None]]:
    """(source file, locator) → a canonical name; anyone else stands alone."""
    keys: dict[Persona, IdentityKey] = {}
    for a in facts.of(NameClaim):
        name = who_is.get((a.cite.source_file, a.cite.locator))
        keys[a.subject] = (name or f"{a.cite.source_file}:{a.cite.locator}",)

    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        return keys.get
    return identity


def _found(facts: AssertionSet, who_is: dict[tuple[str, str], str],
           acknowledged: Callable[[Citation], str | None] | None = None) -> Any:
    return father_findings(facts, _identity(facts, who_is), acknowledged)


def _claims(facts: AssertionSet, who_is: dict[tuple[str, str], str], who: str) -> int:
    return len(father_claims(facts, _identity(facts, who_is)).get(who, []))


class ClaimsAgree(unittest.TestCase):
    """Each case asserts the claims exist, so an empty answer is agreement and
    not an extractor that stopped reading."""

    def test_a_named_father_and_the_patronymic_he_derives(self):
        facts = _facts((_born("Иванъ", "Изотъ", "Петровъ"), "b1.py"),
                       (_married("Иванъ", "Изотовъ"), "m1.py"))
        who = {("b1.py", "child"): "ivan", ("m1.py", "groom"): "ivan"}
        self.assertEqual(2, _claims(facts, who, "ivan"))
        self.assertEqual([], _found(facts, who))

    def test_two_spellings_of_one_father_s_name(self):
        facts = _facts((_married("Иванъ", "Егоровъ"), "m1.py"),
                       (_married("Иванъ", "Георгіевъ", year=1860), "m2.py"))
        who = {("m1.py", "groom"): "ivan", ("m2.py", "groom"): "ivan"}
        self.assertEqual(2, _claims(facts, who, "ivan"))
        self.assertEqual([], _found(facts, who))

    def test_a_name_the_table_does_not_know_agrees_by_its_stem(self):
        facts = _facts((_born("Иванъ", "Шумила"), "b1.py"),
                       (_married("Иванъ", "Шумилинъ"), "m1.py"))
        who = {("b1.py", "child"): "ivan", ("m1.py", "groom"): "ivan"}
        self.assertEqual(2, _claims(facts, who, "ivan"))
        self.assertEqual([], _found(facts, who))

    def test_a_father_is_known_by_every_name_his_records_give_him(self):
        """The rolls write «Лаврентий» for the man the metric books call
        «Ларион» (names the lexicon does not relate); once he is one
        canonical, his son's claims agree."""
        facts = _facts(
            (_born("Мартынъ", "Ларион", "Игнатьевъ"), "b1.py"),
            (_roll(member(1, person("Лаврентій", "Игнатьевъ"), CensusRole.HEAD, age=51),
                   member(2, person("Мартынъ", "Лаврентьевъ"), CensusRole.SON, age=26)),
             "rs.py"))
        son = {("b1.py", "child"): "martyn", ("rs.py", "member2"): "martyn"}
        self.assertEqual(1, len(_found(facts, son)))
        father = {("b1.py", "father"): "larion", ("rs.py", "member1"): "larion"}
        self.assertEqual([], _found(facts, son | father))

    def test_agreement_runs_through_a_chain(self):
        """«Шумилинъ» and «Шумиловъ» share no key; each agrees with the named
        «Шумила», so all three can name one father."""
        who = {("b1.py", "child"): "ivan", ("m1.py", "groom"): "ivan",
               ("m2.py", "groom"): "ivan"}
        pair = ((_married("Иванъ", "Шумилинъ"), "m1.py"),
                (_married("Иванъ", "Шумиловъ", year=1860), "m2.py"))
        self.assertEqual(1, len(_found(_facts(*pair), who)))
        facts = _facts((_born("Иванъ", "Шумила"), "b1.py"), *pair)
        self.assertEqual([], _found(facts, who))


class ClaimsDisagree(unittest.TestCase):
    def test_two_records_two_fathers_is_a_high_finding(self):
        facts = _facts((_born("Иванъ", "Мартинъ", "Петровъ"), "b1.py"),
                       (_married("Иванъ", "Мироновъ"), "m1.py"))
        [f] = _found(facts, {("b1.py", "child"): "ivan", ("m1.py", "groom"): "ivan"})
        self.assertEqual("ivan", f.canonical)
        self.assertEqual("HIGH", f.confidence)
        self.assertEqual(1, len(f.across))
        self.assertEqual((), f.within)
        self.assertEqual(2, len(f.groups))

    def test_more_records_standing_apart_rank_first(self):
        """«Петр» holds two records against one, «Иван» two against two: a
        single deviating line is as often a slip, so «Иван» is read first."""
        facts = _facts((_married("Петръ", "Мартиновъ"), "m1.py"),
                       (_married("Петръ", "Мартиновъ", year=1860), "m2.py"),
                       (_married("Петръ", "Мироновъ", year=1865), "m3.py"),
                       (_married("Иванъ", "Сидоровъ"), "m4.py"),
                       (_married("Иванъ", "Сидоровъ", year=1860), "m5.py"),
                       (_married("Иванъ", "Карповъ", year=1865), "m6.py"),
                       (_married("Иванъ", "Карповъ", year=1870), "m7.py"))
        who = {(f"m{n}.py", "groom"): ("petr" if n <= 3 else "ivan") for n in range(1, 8)}
        found = _found(facts, who)
        self.assertEqual(["ivan", "petr"], [f.canonical for f in found])
        self.assertEqual([2, 1], [f.apart for f in found])

    def test_a_record_that_contradicts_itself_is_not_a_fold_signal(self):
        book = death_records("A", "1", "1", "1", "Тестовка", "Ц", 1803,
                             death(5, Gender.FEMALE, 12, 13, Month.APRIL, Month.APRIL,
                                   deceased=person("Фекла", "Лукина"), age=34,
                                   relatives=[relative(person("Нилъ", "Ивановъ"),
                                                       Relationship.FATHER)]))
        facts = _facts((book, "d1.py"))
        [f] = _found(facts, {("d1.py", "deceased"): "fekla"})
        self.assertEqual((), f.across)
        self.assertEqual("", f.confidence)
        self.assertEqual(1, len(f.within))

    def test_an_entry_that_says_so_stands_it_down(self):
        """A bride written «Фокина» beside a father Нилъ, checked against the
        scan — the note does not say which name is the slip, so no assertion
        is withdrawn; the within-record pair is acknowledged instead."""
        note = "невеста «Фокина» при отце Ниле — так в подлиннике"
        book = marriage_records(
            "A", "1", "1", "1", "Тестовка", "Ц", 1846,
            marriage(8, 21, groom=person("Тимонъ", "Пахомовъ"),
                     bride=person("Татьяна", "Фокина"),
                     relatives=[relative(person("Нилъ", "Ивановъ"),
                                         Relationship.FATHER, "невеста")],
                     source_kin_error=note))
        facts = _facts((book, "m1.py"))
        who = {("m1.py", "bride"): "tatiana"}
        [f] = _found(facts, who)
        self.assertEqual(1, len(f.within))
        [f] = _found(facts, who, lambda cite: note if cite.source_file == "m1.py" else None)
        self.assertEqual((), f.within)
        self.assertEqual(note, f.acknowledged[0][2])

    def test_a_father_we_reconstructed_is_low(self):
        facts = _facts(
            (_roll(member(1, person("Тихонъ", "Сидоровъ"), CensusRole.HEAD, age=62),
                   member(2, person("Нилъ"), CensusRole.SON, age="?", hidden=True),
                   member(3, person("Харитонъ"), CensusRole.GRANDSON, age=7,
                          parent_member=2)),
             "rs.py"),
            (_born("Харитонъ", "Ѳедоръ", "Тихоновъ", year=1843), "b1.py"))
        [f] = _found(facts, {("rs.py", "member3"): "khariton", ("b1.py", "child"): "khariton"})
        self.assertEqual("LOW", f.confidence)


if __name__ == "__main__":
    unittest.main()


class NewbornPatronymic(unittest.TestCase):
    """The patronymic `Birth.__init__` makes of the father (В10) is stated as derived and stands no witness
    beside that father's own edge."""

    def test_derived_not_stated_and_no_second_claim(self):
        facts = _facts((_born("Иванъ", "Изотъ", "Петровъ"), "b1.py"))
        record = next(iter(facts.records()))
        child = [a for a in record.of(NameClaim) if a.cite.locator == "child"]
        self.assertEqual([(type(a.basis).__name__, a.patronymic) for a in child],
                         [("Stated", None), ("Derived", "Изотович")])
        who = {("b1.py", "child"): "ivan"}
        self.assertEqual(1, _claims(facts, who, "ivan"))          # the father's edge alone
