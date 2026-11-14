from __future__ import annotations

import json
import unittest
from calendar import Month

from verso.ru import ages
from verso.ru.consolidation import death_age as da
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import BirthRecords, birth
from verso.ru.dsl.records.deaths import DeathRecords, death
from verso.ru.relationship import Relationship, relative


def births(*records, year=1896):
    return [(BirthRecords("ГАВО", "690", "71", "152", "Глуповы Горы",
                          "Покровская", year, list(records)), f"{year}/births.py")]


def deaths(*records, year=1897):
    return [(DeathRecords("ГАВО", "690", "71", "152", "Глуповы Горы",
                          "Покровская", year, list(records)), f"{year}/deaths.py")]


def a_birth(name, father, *, num=1, day=4, month=Month.OCTOBER, year=None,
            gender=Gender.FEMALE):
    return birth(num, gender, day, day, b_month=month, k_month=month, year=year,
                 child=person(name), father=father, mother=person("Ксения", "Васильева"))


def a_death(name, father, age, *, num=27, day=11, month=Month.AUGUST, year=None,
            gender=Gender.FEMALE):
    return death(num, gender, day, day, d_month=month, b_month=month, year=year,
                 deceased=person(name), age=age,
                 relatives=[relative(father, Relationship.FATHER)])


FATHER = person("Никита", "Фомин", last_name_orig="Бекешев")


class AgeBounds(unittest.TestCase):
    """A stated age is a floor plus the width of its smallest written unit."""

    def test_unstated_age_is_none(self):
        for value in (None, "", "?", "-"):
            self.assertIsNone(ages.age_bounds(value))

    def test_bare_year_spans_a_whole_year(self):
        bounds = ages.age_bounds(1)
        assert bounds is not None
        low, high = bounds
        self.assertAlmostEqual(low, ages.DAYS_PER_YEAR, places=2)
        self.assertAlmostEqual(high, 2 * ages.DAYS_PER_YEAR, places=2)

    def test_months_narrow_the_interval_to_a_month(self):
        bounds = ages.age_bounds("1 г 9 мес")
        assert bounds is not None
        low, high = bounds
        self.assertAlmostEqual(high - low, ages.DAYS_PER_MONTH, places=2)

    def test_days_narrow_the_interval_to_a_day(self):
        bounds = ages.age_bounds("3 дн")
        assert bounds is not None
        low, high = bounds
        self.assertEqual((round(low), round(high)), (3, 4))

    def test_fraction_is_treated_as_exact(self):
        bounds = ages.age_bounds(0.5)
        assert bounds is not None
        low, high = bounds
        self.assertEqual(low, high)

    def test_verbatim_idiom_yields_no_numbers(self):
        # «полгода» is expanded by split_age; a token it cannot parse is skipped
        # rather than guessed at.
        self.assertIsNone(ages.age_bounds("с годом"))


class PersonMatching(unittest.TestCase):
    def test_missing_patronymic_does_not_block(self):
        child = da.PersonKey("фекла", "", "")
        self.assertTrue(child.matches(da.PersonKey("фекла", "андреевна", "")))

    def test_missing_surname_does_not_block(self):
        # The 1834 revision records no surnames; a later metric book does.
        bare = da.PersonKey("никита", "фомич", "")
        self.assertTrue(bare.matches(da.PersonKey("никита", "фомич", "бекешев")))

    def test_different_surname_blocks(self):
        a = da.PersonKey("никита", "фомич", "бекешев")
        self.assertFalse(a.matches(da.PersonKey("никита", "фомич", "бодаев")))

    def test_yo_is_folded(self):
        yo = da.person_key(person("Фёдор", "Фомин"))
        plain = da.person_key(person("Федор", "Фомин"))
        assert yo is not None and plain is not None
        self.assertTrue(yo.matches(plain))


class FindConflicts(unittest.TestCase):
    """The motivating cases, both from one book."""

    def test_misread_age_is_reported(self):
        # A girl buried ten months after her christening: «11 мѣс» on the scan,
        # first read as «1 мес».
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)),
            deaths(a_death("Фекла", FATHER, "1 мес")))
        self.assertEqual(1, len(found))
        self.assertEqual("HIGH", found[0].confidence)
        self.assertIn("МЕСЯЦ", found[0].hint.upper())

    def test_correct_age_is_silent(self):
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)),
            deaths(a_death("Фекла", FATHER, "11 мес")))
        self.assertEqual([], found)

    def test_declared_source_age_error_stands_the_check_down(self):
        # The scribe's figure is wrong and the reader has said so.
        rec = a_death("Фекла", FATHER, "1 мес")
        rec.source_age_error = "«1 мес» сверено; прожила 11 мес — описка писца"
        self.assertEqual([], da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)), deaths(rec)))

    def test_a_declared_namesake_stands_the_check_down(self):
        # The age was re-read at 12× and «1 мѣсяцъ» is right — the burial is
        # the daughter of a SECOND man of the father's name, a namesake whose
        # birth record the corpus does not hold. The finding is
        # true as a signal and false as a conclusion, so the reader declares it
        # — as a namesake, not as a wrong age (which would drop her birth).
        rec = a_death("Фекла", FATHER, "1 мес")
        rec.namesake = "возраст сверен при 12×; погребена тёзка"
        self.assertEqual([], da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)), deaths(rec)))

    def test_an_empty_source_age_error_does_not_silence_anything(self):
        rec = a_death("Фекла", FATHER, "1 мес")
        rec.source_age_error = ""
        self.assertEqual(1, len(da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)), deaths(rec))))

    def test_years_written_for_months_is_named(self):
        # A bare «4» four months after the child's own christening.
        found = da.find_death_age_conflicts(
            births(a_birth("Андрей", FATHER, month=Month.AUGUST, day=8,
                           gender=Gender.MALE)),
            deaths(a_death("Андрей", FATHER, 4, month=Month.DECEMBER, day=6,
                           year=1896, gender=Gender.MALE), year=1896))
        self.assertEqual(1, len(found))
        self.assertIn("ГОДАХ", found[0].hint)

    def test_clerk_truncation_to_whole_years_is_silent(self):
        # «1 годъ» for a child of one year three months is not an error.
        found = da.find_death_age_conflicts(
            births(a_birth("Анна", FATHER, month=Month.JANUARY, day=10, year=1806)),
            deaths(a_death("Анна", FATHER, 1, month=Month.APRIL, day=10, year=1807),
                   year=1807))
        self.assertEqual([], found)

    def test_parish_idiom_polgoda_is_silent(self):
        # Горюхино clerks write «полгода» for any infant under a year; the
        # corpus holds dozens at 280-300 days.
        found = da.find_death_age_conflicts(
            births(a_birth("Михаил", FATHER, month=Month.JANUARY, day=5, year=1806,
                           gender=Gender.MALE)),
            deaths(a_death("Михаил", FATHER, "полгода", month=Month.NOVEMBER, day=1,
                           year=1806, gender=Gender.MALE), year=1806))
        self.assertEqual([], found)

    def test_unrelated_parent_is_not_paired(self):
        other = person("Феодор", "Фомин", last_name_orig="Бекешев")
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)),
            deaths(a_death("Фекла", other, "1 мес")))
        self.assertEqual([], found)

    def test_a_wife_is_not_paired_with_her_husbands_daughter(self):
        # A burial of a woman of 50, WIFE of a man who is the father in an earlier
        # birth of a daughter of her own name. The husband is the father in the
        # birth, so pairing on every relative made mother and daughter one person
        # 23 years old at 50.
        husband = person("Савва", "Тихонов", last_name_orig="Коробочкин")
        daughter = birth(11, Gender.FEMALE, 6, 6, b_month=Month.FEBRUARY,
                         k_month=Month.FEBRUARY, year=1880, child=person("Домна"),
                         father=husband, mother=person("Домна", "Васильева"))
        wife = death(5, Gender.FEMALE, 14, 16, d_month=Month.JANUARY,
                     b_month=Month.JANUARY, year=1903,
                     deceased=person("Домна", "Васильева"), age=50,
                     relatives=[relative(husband, Relationship.HUSBAND)])
        self.assertEqual([], da.find_death_age_conflicts(
            births(daughter, year=1880), deaths(wife, year=1903)))

    def test_a_relative_of_unstated_kinship_may_still_be_the_parent(self):
        # A burial of a child aged «1» by a relative with `relationship=` left
        # unset. The entry names kin and declines to say which, and there it is
        # the father — dropping the unstated relative lost that real finding.
        father = person("Тихон", last_name_orig="Ежевикин")
        rec = death(27, Gender.FEMALE, 11, 11, d_month=Month.AUGUST, b_month=Month.AUGUST,
                    deceased=person("Фекла"), age="1 мес", relatives=[relative(father, None)])
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", father)), deaths(rec))
        self.assertEqual(1, len(found))

    def test_the_report_names_the_parent_not_the_first_relative(self):
        # No surname for him: a husband's is inherited onto the deceased and
        # would keep her from pairing with her birth at all.
        husband = person("Иван", "Петров")
        rec = death(27, Gender.FEMALE, 11, 11, d_month=Month.AUGUST, b_month=Month.AUGUST,
                    deceased=person("Фекла"), age="1 мес",
                    relatives=[relative(husband, Relationship.HUSBAND),
                               relative(FATHER, Relationship.FATHER)])
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)), deaths(rec))
        self.assertEqual(["Никита Фомич Бекешев"], [f.parent for f in found])

    def test_death_without_a_named_parent_is_skipped(self):
        rec = death(2, Gender.FEMALE, 11, 12, d_month=Month.AUGUST, b_month=Month.AUGUST,
                    deceased=person("Фекла"), age="1 мес")
        found = da.find_death_age_conflicts(births(a_birth("Фекла", FATHER)),
                                            deaths(rec))
        self.assertEqual([], found)

    def test_infant_buried_decades_later_is_a_namesake(self):
        found = da.find_death_age_conflicts(
            births(a_birth("Параскева", FATHER, year=1806)),
            deaths(a_death("Параскева", FATHER, "полгода", year=1840), year=1840))
        self.assertEqual(1, len(found))
        self.assertEqual("LOW", found[0].confidence)

    def test_reused_name_lowers_confidence(self):
        found = da.find_death_age_conflicts(
            births(a_birth("Евдокия", FATHER, num=1, year=1904),
                   a_birth("Евдокия", FATHER, num=2, year=1907)),
            deaths(a_death("Евдокия", FATHER, "3 дн", year=1911), year=1911))
        self.assertEqual(1, len(found))
        self.assertEqual("LOW", found[0].confidence)

    def test_min_gap_filters(self):
        args = (births(a_birth("Фекла", FATHER)),
                deaths(a_death("Фекла", FATHER, "1 мес")))
        self.assertEqual(1, len(da.find_death_age_conflicts(*args)))
        self.assertEqual([], da.find_death_age_conflicts(*args, min_gap_days=10_000))

    def test_findings_sort_high_first_then_widest_gap(self):
        found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER),
                   a_birth("Параскева", FATHER, year=1806)),
            deaths(a_death("Фекла", FATHER, "1 мес"),
                   a_death("Параскева", FATHER, "полгода", num=28, year=1840)))
        self.assertEqual(["HIGH", "LOW"], [f.confidence for f in found])


class Reporting(unittest.TestCase):
    def setUp(self):
        self.found = da.find_death_age_conflicts(
            births(a_birth("Фекла", FATHER)),
            deaths(a_death("Фекла", FATHER, "1 мес")))

    def test_clean_report_says_so(self):
        self.assertIn("OK — 0 findings", da.format_report([]))

    def test_report_names_both_records(self):
        text = da.format_report(self.found)
        self.assertIn("1896/births.py", text)
        self.assertIn("1897/deaths.py", text)
        self.assertIn("СИГНАЛ", text)

    def test_json_is_machine_readable(self):
        payload = json.loads(da.findings_to_json(self.found))
        self.assertEqual("stated_age_vs_birth", payload[0]["kind"])
        self.assertEqual("1 мес", payload[0]["stated_age"])

    def test_empty_json_is_an_empty_list(self):
        self.assertEqual([], json.loads(da.findings_to_json([])))


if __name__ == "__main__":
    unittest.main()
