"""`Titled`: how a record styles someone, and on whose authority.

«Титул/звание» is what `estate-conflicts` compares, so which appearances carry
one — and which only look as if they do — is pinned here: the newborn, whose
status the record never states; the reconstructed revision member, whom the
roll never names; and the status a book's defaults filled in place.
"""
from __future__ import annotations

import unittest

from corpus.statuses import SOBAKEVICH_UK_PEASANT_MALE
from verso.ru.domain import Gender, RecordDefaults, person
from verso.ru.domain.statuses import SOLDIER_WIFE, YASAK_PEASANT_FEMALE, YASAK_PEASANT_MALE
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.ru.facts.extract.births import facts_from_births
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.extract.deaths import facts_from_deaths
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet, Derived, Stated, Titled


def _titled(facts: AssertionSet) -> dict[str, Titled]:
    return {a.cite.locator: a for a in facts.of(Titled)}


class WhatTheRecordStyles(unittest.TestCase):
    def test_a_parent_is_styled_verbatim(self):
        r = birth_records("a", "f", "i", "c", "Тестовка", "Ц", 1830,
                          birth(1, Gender.MALE, child=person("Иванъ"),
                                father=person("Пётръ", status=SOBAKEVICH_UK_PEASANT_MALE)))
        found = _titled(AssertionSet(facts_from_births(
            [(r.records[0], "b.py")], village="Тестовка")))
        self.assertEqual(str(SOBAKEVICH_UK_PEASANT_MALE), found["father"].status)
        self.assertEqual(Stated(), found["father"].basis)

    def test_the_newborn_is_not_styled_by_its_record(self):
        """`Birth.__init__` derives the child's сословие from the father's; the
        record states the father's alone, and the translator never prints the
        child's."""
        r = birth_records("a", "f", "i", "c", "Тестовка", "Ц", 1830,
                          birth(1, Gender.MALE, child=person("Иванъ"),
                                father=person("Пётръ", status=SOBAKEVICH_UK_PEASANT_MALE)))
        child = r.records[0].child
        assert child is not None
        self.assertIsNotNone(child.status)
        found = _titled(AssertionSet(facts_from_births(
            [(r.records[0], "b.py")], village="Тестовка")))
        self.assertNotIn("child", found)

    def test_a_book_default_is_stated_on_an_unknown_basis(self):
        r = birth_records("a", "f", "i", "c", "Тестовка", "Ц", 1830,
                          birth(1, Gender.MALE, child=person("Иванъ"),
                                father=person("Пётръ", status=YASAK_PEASANT_MALE),
                                mother=person("Анна")),
                          defaults=RecordDefaults(status_mother=YASAK_PEASANT_FEMALE))
        found = _titled(AssertionSet(facts_from_births(
            [(r.records[0], "b.py")], village="Тестовка")))
        self.assertEqual(Stated(basis_unknown=True), found["mother"].basis)
        self.assertEqual(Stated(), found["father"].basis)

    def test_a_role_status_is_a_status_too(self):
        """Classification is the caller's: «солдатка» names no сословие, but it
        is still how the record styles her, so it is still asserted."""
        r = marriage_records("a", "f", "i", "c", "Тестовка", "Ц", 1830,
                             marriage(1, groom=person("Иванъ", status=YASAK_PEASANT_MALE),
                                      bride=person("Анна", status=SOLDIER_WIFE)))
        found = _titled(AssertionSet(facts_from_marriages(
            [(r.records[0], "m.py")], village="Тестовка")))
        self.assertEqual(str(SOLDIER_WIFE), found["bride"].status)
        self.assertEqual(str(YASAK_PEASANT_MALE), found["groom"].status)

    def test_the_deceased_is_styled(self):
        r = death_records("a", "f", "i", "c", "Тестовка", "Ц", 1830,
                          death(1, Gender.MALE,
                                deceased=person("Иванъ", status=YASAK_PEASANT_MALE)))
        found = _titled(AssertionSet(facts_from_deaths(
            [(r.records[0], "d.py")], village="Тестовка")))
        self.assertEqual(str(YASAK_PEASANT_MALE), found["deceased"].status)


class TheRoll(unittest.TestCase):
    def _facts(self, *members) -> dict[str, Titled]:
        recs = census_records("ГАТО", "12", "1", "1", "Тестовка", 1834,
                              household("7", *members),
                              defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE,
                                                      status_female=YASAK_PEASANT_FEMALE))
        return _titled(AssertionSet(facts_from_census([(recs, "rs.py")],
                                                      village="Тестовка")))

    def test_a_listed_member_carries_the_roll_default_on_an_unknown_basis(self):
        found = self._facts(member(1, person("Тихонъ", "Сидоровъ"), CensusRole.HEAD, age=54))
        self.assertEqual(str(YASAK_PEASANT_MALE), found["member1"].status)
        self.assertEqual(Stated(basis_unknown=True), found["member1"].basis)

    def test_a_reconstructed_member_is_styled_by_us(self):
        """The roll never names a hidden member, so their status — like every
        other claim about them — is ours: `estate-conflicts` still reads it,
        and marks the line."""
        found = self._facts(
            member(1, person("Тихонъ", "Сидоровъ"), CensusRole.HEAD, age=54),
            member(2, person("Сидоръ"), CensusRole.FATHER, hidden=True))
        basis = found["member2"].basis
        assert isinstance(basis, Derived)
        self.assertEqual("census.reconstructed-member", basis.rationale)


if __name__ == "__main__":
    unittest.main()
