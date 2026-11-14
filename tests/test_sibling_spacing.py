from __future__ import annotations

import json
import unittest
from calendar import Month
from datetime import date

from verso.ru.consolidation import sibling_spacing as ss
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import BirthRecords, birth
from verso.ru.dsl.records.deaths import DeathRecords, death
from verso.ru.relationship import Relationship, relative

FATHER = person("Лука", "Петров", last_name_orig="Бекешев")
MOTHER = person("Агафья", "Ильина")


def births(*records, year=1895):
    return [(BirthRecords("ГАВО", "690", "71", "152", "Глуповы Горы",
                          "Покровская", year, list(records)), f"{year}/births.py")]


def deaths(*records, year=1895):
    return [(DeathRecords("ГАВО", "690", "71", "152", "Глуповы Горы",
                          "Покровская", year, list(records)), f"{year}/deaths.py")]


def a_birth(name, day, month, year, *, num=1, gender=Gender.FEMALE,
            father=FATHER, mother=MOTHER):
    return birth(num, gender, day, day, b_month=month, k_month=month, year=year,
                 child=person(name), father=father, mother=mother)


def a_death(name, day, month, year, age, *, num=5, gender=Gender.MALE, father=FATHER):
    return death(num, gender, day, day, d_month=month, b_month=month, year=year,
                 deceased=person(name), age=age,
                 relatives=[relative(father, Relationship.FATHER)])


def sib(name, low, high=None, *, derived=False):
    # Built directly rather than through person(): these separation tests use
    # placeholder names like "а", which the name table rightly rejects.
    key = ss.PersonKey(name=name, patronymic="", surname="", written=name)
    return ss.Sibling(name=name, key=key,
                      low=low, high=high or low, derived=derived,
                      year=low.year, record_num="1", source="x.py")


class Separation(unittest.TestCase):
    """The placement that matters is the one most favourable to the records."""

    def test_two_exact_dates(self):
        a, b = sib("а", date(1895, 5, 14)), sib("б", date(1895, 9, 8))
        self.assertEqual(117, ss.max_separation(a, b))

    def test_an_interval_is_measured_at_its_furthest(self):
        a = sib("а", date(1894, 10, 1), date(1894, 11, 1), derived=True)
        b = sib("б", date(1895, 5, 14))
        # 1894-10-01 → 1895-05-14 is the furthest the two can be placed apart.
        self.assertEqual((date(1895, 5, 14) - date(1894, 10, 1)).days,
                         ss.max_separation(a, b))

    def test_order_does_not_matter(self):
        a = sib("а", date(1894, 10, 1), date(1894, 11, 1), derived=True)
        b = sib("б", date(1895, 5, 14))
        self.assertEqual(ss.max_separation(a, b), ss.max_separation(b, a))


class HouseholdKey(unittest.TestCase):
    def test_two_parents_identify_a_household(self):
        self.assertTrue(ss.identifies_a_household(
            (ss.PersonKey("лука", "петрович", ""), ss.PersonKey("агафья", "", ""))))

    def test_a_lone_father_with_a_surname_does(self):
        self.assertTrue(ss.identifies_a_household((ss.PersonKey("василий", "григорьевич", "тюфяев"),)))

    def test_a_lone_father_without_a_surname_does_not(self):
        # Early books hold several men of one name and patronymic.
        self.assertFalse(ss.identifies_a_household((ss.PersonKey("василий", "григорьевич", ""),)))

    def test_no_parents_at_all(self):
        self.assertFalse(ss.identifies_a_household(()))


class FindConflicts(unittest.TestCase):
    """The motivating case: a child's bare «4½» at burial, months or years."""

    def test_months_reading_collides_with_a_sister(self):
        # Read as months, Тихон is born ~Oct 1894 — about six months before Ксения.
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)),
            deaths(a_death("Тихон", 9, Month.MARCH, 1895, "4 мес 15 дн")))
        self.assertEqual(1, len(found))
        self.assertIn("выведен из погребения", found[0].hint)

    def test_years_reading_is_silent(self):
        # Read as years he is born ~Sep 1890, and nothing collides.
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)),
            deaths(a_death("Тихон", 9, Month.MARCH, 1895, "4 г 6 мес")))
        self.assertEqual([], found)

    def test_one_child_spelled_two_ways_is_not_two_siblings(self):
        # «Иванъ» in his birth record and «Иоаннъ» in his burial («2 г 3 мес»
        # deriving the same day). Comparing the scribe's spellings made him two
        # boys born together; identity has to go through the folded base name.
        found = ss.find_spacing_conflicts(
            births(a_birth("Иванъ", 14, Month.SEPTEMBER, 1892, gender=Gender.MALE)),
            deaths(a_death("Иоанн", 14, Month.DECEMBER, 1894, "2 г 3 мес"), year=1894))
        self.assertEqual([], found)

    def test_two_genuinely_different_names_still_collide(self):
        # The guard must not swallow the real case: Стефанида and Марья are
        # two children, and 23 days apart they cannot both be born.
        found = ss.find_spacing_conflicts(
            births(a_birth("Марья", 19, Month.NOVEMBER, 1893)),
            deaths(a_death("Стефанида", 12, Month.DECEMBER, 1893, "1 мес",
                           gender=Gender.FEMALE), year=1893))
        self.assertEqual(1, len(found))

    def test_a_burial_naming_one_parent_picks_no_household_when_two_fit(self):
        # A father with two wives, and a burial naming only him. Which household the child belongs to is not in the
        # record, and taking whichever couple came first made the answer
        # arbitrary — so with nothing to tell them apart, attach to neither.
        WIFE2 = person("Евдокия", "Николаева")
        found = ss.find_spacing_conflicts(
            births(a_birth("Марья", 19, Month.NOVEMBER, 1893),
                   a_birth("Анна", 3, Month.MARCH, 1894, num=2, mother=WIFE2)),
            deaths(a_death("Стефанида", 12, Month.DECEMBER, 1893, "1 мес",
                           gender=Gender.FEMALE), year=1893))
        self.assertEqual([], found)

    def test_childbearing_dates_break_the_tie(self):
        # Same shape, but now the two wives bore children a generation apart,
        # so only one couple can own a birth in 1893 and the finding stands.
        WIFE2 = person("Евдокия", "Николаева")
        found = ss.find_spacing_conflicts(
            births(a_birth("Марья", 19, Month.NOVEMBER, 1893),
                   a_birth("Анна", 3, Month.MARCH, 1860, num=2, mother=WIFE2)),
            deaths(a_death("Стефанида", 12, Month.DECEMBER, 1893, "1 мес",
                           gender=Gender.FEMALE), year=1893))
        self.assertEqual(1, len(found))
        # the 1893 couple, not the one whose only child was born in 1860
        self.assertIn("Ильинична", found[0].parents)
        self.assertNotIn("Николаевна", found[0].parents)

    def test_a_couple_a_generation_off_does_not_claim_the_burial(self):
        # A burial matched a couple of an earlier generation because PersonKey
        # compares a surname only when both sides carry one, and the earlier
        # father was written without his. Forty-six years apart.
        OLD_WIFE = person("Феодосия", "Фалалеева")
        found = ss.find_spacing_conflicts(
            births(a_birth("Анна", 1, Month.JUNE, 1859, mother=OLD_WIFE)),
            deaths(a_death("Феодор", 13, Month.DECEMBER, 1905, "10 мес 15 дн",
                           gender=Gender.MALE), year=1905))
        self.assertEqual([], found)

    def test_declared_source_age_error_withdraws_the_derived_birth(self):
        # The check exists to question a birth DERIVED from a burial age. Once
        # the reader has re-read that age and argued the burial belongs to a
        # namesake, the corpus no longer claims that sibling at all.
        rec = a_death("Тихон", 9, Month.MARCH, 1895, "4 мес 15 дн")
        rec.source_age_error = "возраст сверен при 12×; погребена тёзка"
        self.assertEqual([], ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)), deaths(rec)))

    def test_a_wife_is_not_filed_among_her_husbands_children(self):
        # A burial of a wife names her husband, who is the father in his
        # children's births. Filing her as one of those children set a second
        # wife, born the spring her stepdaughter was, beside that stepdaughter.
        rec = death(5, Gender.FEMALE, 3, 5, d_month=Month.JUNE, b_month=Month.JUNE,
                    year=1910, deceased=person("Мария", "Петрова"),
                    age="17 лет 2 мес",
                    relatives=[relative(FATHER, Relationship.HUSBAND)])
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)), deaths(rec, year=1910))
        self.assertEqual([], found)

    def test_ordinary_siblings_are_silent(self):
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895, num=1),
                   a_birth("Ирина", 20, Month.JUNE, 1897, num=2)), deaths())
        self.assertEqual([], found)

    def test_twins_entered_separately_are_not_a_finding(self):
        found = ss.find_spacing_conflicts(
            births(a_birth("Анна", 28, Month.AUGUST, 1899, num=51),
                   a_birth("Любовь", 28, Month.AUGUST, 1899, num=52)), deaths())
        self.assertEqual([], found)

    def test_a_derived_date_never_competes_with_its_own_birth_record(self):
        # Анна has a birth record; her burial age must not be re-derived and
        # set against her twin Любовь.
        found = ss.find_spacing_conflicts(
            births(a_birth("Анна", 28, Month.AUGUST, 1899, num=51),
                   a_birth("Любовь", 28, Month.AUGUST, 1899, num=52)),
            deaths(a_death("Анна", 5, Month.OCTOBER, 1901, 2, gender=Gender.FEMALE),
                   year=1901))
        self.assertEqual([], found)

    def test_the_same_child_twice_is_not_this_check(self):
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)),
            deaths(a_death("Ксения", 28, Month.SEPTEMBER, 1895, "4 мес 15 дн",
                           gender=Gender.FEMALE)))
        self.assertEqual([], found)

    def test_a_burial_naming_no_parent_is_skipped(self):
        rec = death(1, Gender.MALE, 9, 10, d_month=Month.MARCH, b_month=Month.MARCH,
                    deceased=person("Тихон"), age="4 мес")
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)), deaths(rec))
        self.assertEqual([], found)

    def test_another_couple_is_not_folded_in(self):
        other = person("Михаил", "Феодоров", last_name_orig="Бекешев")
        found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)),
            deaths(a_death("Тихон", 9, Month.MARCH, 1895, "4 мес", father=other)))
        self.assertEqual([], found)

    def test_min_gap_is_configurable(self):
        args = (births(a_birth("Ксения", 14, Month.MAY, 1895)),
                deaths(a_death("Тихон", 9, Month.MARCH, 1895, "4 мес 15 дн")))
        self.assertEqual(1, len(ss.find_spacing_conflicts(*args)))
        self.assertEqual([], ss.find_spacing_conflicts(*args, min_gap_days=30))


class Reporting(unittest.TestCase):
    def setUp(self):
        self.found = ss.find_spacing_conflicts(
            births(a_birth("Ксения", 14, Month.MAY, 1895)),
            deaths(a_death("Тихон", 9, Month.MARCH, 1895, "4 мес 15 дн")))

    def test_clean_report(self):
        self.assertIn("OK — 0 findings",
                      ss.format_report([], min_gap_days=ss.DEFAULT_MIN_GAP_DAYS))

    def test_report_names_both_children_and_their_provenance(self):
        text = ss.format_report(self.found, min_gap_days=ss.DEFAULT_MIN_GAP_DAYS)
        self.assertIn("ксения", text)
        self.assertIn("тихон", text)
        self.assertIn("метрика о рождении", text)
        self.assertIn("выведено из погребения", text)

    def test_json(self):
        payload = json.loads(ss.findings_to_json(self.found))
        self.assertEqual(2, len(payload[0]["children"]))
        self.assertTrue(any(c["derived"] for c in payload[0]["children"]))

    def test_empty_json(self):
        self.assertEqual([], json.loads(ss.findings_to_json([])))


if __name__ == "__main__":
    unittest.main()
