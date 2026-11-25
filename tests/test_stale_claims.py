from __future__ import annotations

import json
import unittest
from calendar import Month

from verso.ru.consolidation import stale_claims as sc
from verso.ru.domain import Gender, person
from verso.ru.dsl.records.births import BirthRecords, birth

FATHER = person("Леонтий", "Тихонов", last_name_orig="Бекешев")
MOTHER = person("Ульяна", "Лукина")


def year_of(*records, year):
    return (BirthRecords("ГАВО", "690", "71", "152", "Глуповы Горы",
                         "Покровская", year, list(records)),
            "рождение", f"{year}/births.py")


FEMALE_NAMES = {"Фекла", "Ксения", "Анна", "Мария"}


def a_birth(name, day, month, year, comment=None, *, num=1,
            father=FATHER, mother=MOTHER, gp=None):
    gender = Gender.FEMALE if name in FEMALE_NAMES else Gender.MALE
    return birth(num, gender, day, day, b_month=month, k_month=month, year=year,
                 child=person(name), father=father, mother=mother,
                 god_parent1=gp, comment=comment)


CLAIM = "🔴 **САМАЯ РАННЯЯ ДВОЙНАЯ ФАМИЛИЯ КОРПУСА.** «Леонтій Тихоновъ Бекешевъ тожъ Уездниковъ»"


class Phrases(unittest.TestCase):
    def test_superlatives_are_recognised(self):
        for text in ("это самая ранняя его запись",
                     "первая метрическая запись главы двора",
                     "старший известный ребёнок пары",
                     "прежней самой ранней была запись 1896 г."):
            self.assertTrue(sc.matched_phrases(text), text)

    def test_a_plain_note_is_not_a_claim(self):
        for text in ("двор 4 отодвигается с 1897 на 1894 год",
                     "жена та же — Мелания Игнатьева",
                     None, ""):
            self.assertEqual([], sc.matched_phrases(text))

    def test_first_in_every_case_is_a_claim(self):
        for text in ("первая запись о нём",
                     "это его первое упоминание",
                     "считать первую запись двора",
                     "стала первой метрической записью двора",
                     "стала первою записью двора",
                     "Первая метрическая запись главы двора"):
            self.assertEqual(["первая запись"], sc.matched_phrases(text), text)

    def test_an_original_entry_is_not_a_claim(self):
        # «Первоначальная запись» is the act as first written, before a
        # correction — it says nothing about which record came first.
        for text in ("Первоначальная запись ('Пётр Небывалов', отец) исправлена",
                     "первоначальное упоминание отца зачёркнуто",
                     "первородная запись"):
            self.assertEqual([], sc.matched_phrases(text), text)

    def test_retraction_marker(self):
        self.assertTrue(sc.RETRACTED.search(
            "Самой ранней в корпусе эта связка считалась лишь до 05.09.2026"))
        self.assertTrue(sc.RETRACTED.search("вывод снят 05.09.2026"))
        self.assertFalse(sc.RETRACTED.search("это самая ранняя его запись"))


class SamePerson(unittest.TestCase):
    def test_a_child_does_not_match_his_father(self):
        # The bug this rule exists for: «Иоаннъ» the newborn against «Иоаннъ
        # Михайловъ» the father.
        child = sc.PersonKey("иоанн", "", "")
        father = sc.PersonKey("иоанн", "михайлович", "кекев")
        self.assertFalse(sc.same_person(child, father))

    def test_same_name_and_patronymic_matches(self):
        a = sc.PersonKey("леонтий", "тихонович", "кекев")
        b = sc.PersonKey("леонтий", "тихонович", "")
        self.assertTrue(sc.same_person(a, b))

    def test_conflicting_surnames_do_not(self):
        a = sc.PersonKey("леонтий", "тихонович", "кекев")
        b = sc.PersonKey("леонтий", "тихонович", "козлов")
        self.assertFalse(sc.same_person(a, b))


class FindStaleClaims(unittest.TestCase):
    """The motivating case: the 1894 primacy claim that 1893 falsified."""

    def test_an_earlier_record_of_the_same_father_falsifies_the_claim(self):
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, gp=FATHER), year=1893),
        ])
        self.assertEqual(1, len(found))
        self.assertEqual("CORPUS", found[0].scope)
        self.assertEqual(1893, found[0].earlier.year)

    def test_no_earlier_record_means_no_finding(self):
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM), year=1894)])
        self.assertEqual([], found)

    def test_a_record_without_a_claim_is_ignored(self):
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, "обычный комментарий"), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, gp=FATHER), year=1893),
        ])
        self.assertEqual([], found)

    def test_a_dated_retraction_stands_the_check_down(self):
        retracted = CLAIM + " ⚠ Самой ранней в корпусе она считалась лишь до 05.09.2026."
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, retracted), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, gp=FATHER), year=1893),
        ])
        self.assertEqual([], found)

    def test_a_godparent_is_not_a_subject(self):
        # The claim sits on a record whose FATHER is new; that an earlier record
        # names the godparent is not what the superlative is about.
        other = person("Фока", "Тихонов", last_name_orig="Бекешев")
        other_wife = person("Мелания", "Игнатьева")
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM, gp=other), year=1894),
            year_of(a_birth("Ксения", 19, Month.MAY, 1893, father=other,
                            mother=other_wife), year=1893),
        ])
        self.assertEqual([], found)

    def test_one_finding_per_record(self):
        # Both parents are attested earlier; the reader re-reads the record once.
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, num=2), year=1893),
        ])
        self.assertEqual(1, len(found))

    def test_person_scope_when_the_corpus_is_not_invoked(self):
        claim = "🔴 это самая ранняя его метрическая запись"
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, claim), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, num=2), year=1893),
        ])
        self.assertEqual("PERSON", found[0].scope)

    def test_corpus_findings_sort_first(self):
        person_claim = "это самая ранняя его запись"
        other = person("Фока", "Тихонов", last_name_orig="Бекешев")
        found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM), year=1894),
            year_of(a_birth("Кузьма", 6, Month.DECEMBER, 1894, person_claim,
                            num=47, father=other,
                            mother=person("Мелания", "Игнатьева")), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, num=2), year=1893),
            year_of(a_birth("Ксения", 19, Month.MAY, 1893, num=3, father=other,
                            mother=person("Мелания", "Игнатьева")), year=1893),
        ])
        self.assertEqual(["CORPUS", "PERSON"], [f.scope for f in found])


class Reporting(unittest.TestCase):
    def setUp(self):
        self.found = sc.find_stale_claims([
            year_of(a_birth("Савва", 22, Month.AUGUST, 1894, CLAIM), year=1894),
            year_of(a_birth("Фекла", 11, Month.MARCH, 1893, gp=FATHER), year=1893),
        ])

    def test_clean_report(self):
        self.assertIn("OK — 0 findings", sc.format_report([]))

    def test_report_names_both_records(self):
        text = sc.format_report(self.found)
        self.assertIn("1894/births.py", text)
        self.assertIn("1893/births.py", text)
        self.assertIn("не приговор", text)

    def test_json(self):
        payload = json.loads(sc.findings_to_json(self.found))
        self.assertEqual("CORPUS", payload[0]["scope"])
        self.assertIn("1893", payload[0]["earlier_date"])

    def test_empty_json(self):
        self.assertEqual([], json.loads(sc.findings_to_json([])))


if __name__ == "__main__":
    unittest.main()


def test_a_record_is_named_in_the_interface_s_language():
    from datetime import date

    from verso.core import i18n
    from verso.ru.consolidation.stale_claims import RecordRef
    ref = RecordRef(kind="смерть", year=1890, record_num="5", source="v_deaths_1890", when=date(1890, 3, 1))
    with i18n.use("en"):
        assert str(ref) == "death 1890 № 5 [v_deaths_1890]"
    with i18n.use("ru"):
        assert str(ref) == "смерть 1890 № 5 [v_deaths_1890]"
