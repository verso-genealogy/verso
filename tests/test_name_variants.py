"""The fourth channel: a loose record whose surname the canonical already carries.

Since 2026-09-28 `name-variants` is the second caller of the matcher
`reconcile` runs on (`verso.ru.facts.checks.reconcile`), so these build DSL
records on a made-up village and read them through the extractors, as
`tests/test_facts_reconcile.py` does — never a res_name. The surname helpers
it shares with `reconcile` are pinned here too.
"""
from __future__ import annotations

import unittest
from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.consolidation.name_variants import auditable, name_variants_channel
from verso.ru.domain import person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.facts.checks.reconcile import (
    RETIRED_LIFE_APART, VERDICT_AMBIGUOUS, VERDICT_CANDIDATE, Side, audit_folded, match)
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.name_lists import facts_from_name_lists
from verso.ru.facts.identity import IdentityKey
from verso.ru.facts.model import Assertion, AssertionSet, NameClaim, Persona, Record
from verso.ru.gender import Gender
from verso.ru.naming.surnames import normalise_surname, within_one_letter

Identity = Callable[[Record], Callable[[Persona], IdentityKey | None]]


class NormaliseSurname(unittest.TestCase):
    def test_strips_feminine_ending(self):
        self.assertEqual(normalise_surname("Оляпкина"), normalise_surname("Оляпкин"))

    def test_folds_yat_and_hard_sign(self):
        self.assertEqual(normalise_surname("Мижуевъ"), normalise_surname("Мижуев"))

    def test_leading_a_becomes_o(self):
        """Аляпкин and Оляпкин are one family."""
        self.assertEqual(normalise_surname("Аляпкин"), normalise_surname("Оляпкин"))

    def test_different_surnames_stay_different(self):
        self.assertNotEqual(normalise_surname("Медвежатников"), normalise_surname("Тихоходов"))


class WithinOneLetter(unittest.TestCase):
    def test_identical(self):
        self.assertTrue(within_one_letter("тюфяев", "тюфяев"))

    def test_one_substitution(self):
        self.assertTrue(within_one_letter("тюфяев", "тяфяев"))

    def test_one_insertion(self):
        self.assertTrue(within_one_letter("лапшев", "лапшеев"))

    def test_two_differences_rejected(self):
        self.assertFalse(within_one_letter("тюфяев", "бубнов"))

    def test_length_gap_rejected(self):
        self.assertFalse(within_one_letter("ов", "тюфяев"))


def _godfather(num: int, year: int, surname: str | None,
               patronymic: str | None = "Ѳедоровъ") -> Any:
    """A baptism naming Потап Ѳедоровъ <surname> as godfather."""
    return birth_records("A", "1", "1", "1", "Тестовка", "Ц", year,
                         birth(num, Gender.MALE, 5, 6, Month.MAY, Month.MAY,
                               child=person("Семенъ"),
                               father=person("Лука", "Ильинъ", "Хмуринъ"),
                               god_parent1=person("Потапъ", patronymic, surname)))


def _facts(*books: tuple[Any, str]) -> AssertionSet:
    out: list[Assertion] = []
    for book, name in books:
        if hasattr(book, "entries"):
            out += facts_from_name_lists([(book, name)], village="Тестовка")
            continue
        for rec in book.records:
            if rec.year is None:
                rec.year = book.year
        extract = facts_from_deaths if name.startswith("d") else facts_from_births
        out += extract([(r, name) for r in book.records], village="Тестовка")
    return AssertionSet(out)


def _identity(facts: AssertionSet, who_is: dict[str, str]) -> Identity:
    """Source file → the canonical its godfather (or deceased, or listed man)
    is folded into; anyone unnamed stands alone under a key of their own."""
    keys: dict[Persona, IdentityKey] = {}
    for a in facts.of(NameClaim):
        name = who_is.get(a.cite.source_file) if a.cite.locator in (
            "god_parent1", "deceased", "listed") else None
        keys[a.subject] = (name or f"{a.cite.source_file}:{a.cite.locator}",)

    def identity(_record: Record) -> Callable[[Persona], IdentityKey | None]:
        return keys.get
    return identity


#: The Петушков canonical: two baptisms folded into one godfather.
PETUSHKOV = {"b1.py": "potap", "b2.py": "potap"}


def _run(facts: AssertionSet, who_is: dict[str, str]) -> list[Any]:
    identity = _identity(facts, who_is)
    folded = set(who_is.values())

    def loose(key: IdentityKey) -> bool:
        return key[0] not in folded
    return match(facts, identity, name_variants_channel(loose))


def _for(found: list[Any], source: str) -> Any:
    return next(r for r in found if r.target.key == (f"{source}:god_parent1",))


class Detection(unittest.TestCase):
    def test_a_surname_the_canonical_carries_a_letter_off_is_a_candidate(self):
        """Горюхино 1845: «Потап Несторович Патушков» beside the Петушковы."""
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"),
                       (_godfather(3, 1845, "Патушковъ"), "b3.py"))
        r = _for(_run(facts, PETUSHKOV), "b3.py")
        self.assertEqual(VERDICT_CANDIDATE, r.verdict)
        self.assertEqual(("potap",), r.survivors[0].person.key)

    def test_an_unattested_surname_is_not_a_match(self):
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"),
                       (_godfather(3, 1845, "Тихоходовъ"), "b3.py"))
        self.assertEqual((), _for(_run(facts, PETUSHKOV), "b3.py").matches)

    def test_a_canonical_without_any_surname_is_never_a_match(self):
        """The larger half of the class, out of scope by design: nothing to
        compare the loose record's surname with."""
        facts = _facts((_godfather(1, 1840, None), "b1.py"),
                       (_godfather(2, 1842, None), "b2.py"),
                       (_godfather(3, 1845, "Петушковъ"), "b3.py"))
        self.assertEqual((), _for(_run(facts, PETUSHKOV), "b3.py").matches)

    def test_the_father_must_be_written_on_both_sides(self):
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"),
                       (_godfather(3, 1845, "Петушковъ", patronymic=None), "b3.py"))
        found = _run(facts, PETUSHKOV)
        self.assertFalse(any(r.target.key == ("b3.py:god_parent1",) for r in found))

    def test_two_canonicals_of_one_name_are_ambiguous(self):
        """The old channel said nothing at all here; now a human reads both."""
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"),
                       (_godfather(4, 1841, "Петушковъ"), "b4.py"),
                       (_godfather(5, 1843, "Петушковъ"), "b5.py"),
                       (_godfather(3, 1845, "Патушковъ"), "b3.py"))
        who = {**PETUSHKOV, "b4.py": "potap_2", "b5.py": "potap_2"}
        self.assertEqual(VERDICT_AMBIGUOUS, _for(_run(facts, who), "b3.py").verdict)

    def test_a_list_entry_is_reconcile_s(self):
        roster = name_list_records("A", "1", "1", "1", "Тестовка", 1917,
                                   listed_person(1, person("Потапъ", "Ѳедоровъ",
                                                           "Петушковъ")),
                                   document_type="Список избирателей")
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"), (roster, "l.py"))
        found = _run(facts, PETUSHKOV)
        self.assertFalse(any(r.target.key == ("l.py:listed",) for r in found))


class Guards(unittest.TestCase):
    def test_a_godfather_after_the_canonical_s_burial_is_a_name_given_again(self):
        buried = death_records("A", "1", "1", "1", "Тестовка", "Ц", 1843,
                               death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY,
                                     deceased=person("Потапъ", "Ѳедоровъ", "Петушковъ")))
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"), (buried, "d1.py"),
                       (_godfather(3, 1845, "Петушковъ"), "b3.py"))
        r = _for(_run(facts, {"b1.py": "potap", "d1.py": "potap"}), "b3.py")
        self.assertEqual(RETIRED_LIFE_APART, r.matches[0].retired)


class TheOracle(unittest.TestCase):
    def test_a_fold_made_by_hand_is_found_again(self):
        facts = _facts((_godfather(1, 1840, "Петушковъ"), "b1.py"),
                       (_godfather(2, 1842, "Петушковъ"), "b2.py"),
                       (_godfather(3, 1845, "Патушковъ"), "b3.py"))
        who = {**PETUSHKOV, "b3.py": "potap"}
        identity = _identity(facts, who)
        audits = audit_folded(facts, identity, name_variants_channel(lambda key: False))
        self.assertEqual({"FOUND"}, {a.outcome for a in audits})
        self.assertEqual(3, len(audits))

    def test_only_what_the_channel_could_propose_is_audited(self):
        """A godfather written without a surname, or without a father, is not
        an appearance this channel could ever have proposed."""
        def godfather(surname: str | None, patronymic: str | None) -> Side:
            facts = _facts((_godfather(1, 1840, surname, patronymic), "b1.py"))
            return Side.of(("x",), (a for a in facts
                                    if a.cite.locator == "god_parent1"))
        self.assertTrue(auditable(godfather("Петушковъ", "Ѳедоровъ")))
        self.assertFalse(auditable(godfather(None, "Ѳедоровъ")))
        self.assertFalse(auditable(godfather("Петушковъ", None)))

if __name__ == "__main__":
    unittest.main()
