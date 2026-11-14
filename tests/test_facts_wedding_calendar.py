"""A wedding dated on a day the Church did not marry — `check=wedding-calendar`.

1850: Pascha 23 April, Clean Monday 6 March, Cheesefare week 27 Feb–5 March.
"""
from __future__ import annotations

import unittest
from calendar import Month

from verso.ru.cli.facts import format_wedding_calendar
from verso.ru.domain import person
from verso.ru.dsl.records.marriages import marriage
from verso.ru.facts.checks.wedding_calendar import wedding_calendar_findings
from verso.ru.facts.extract.marriages import facts_from_marriages
from verso.ru.facts.model import AssertionSet


def _facts(*weddings: tuple[int, int, Month], note: str | None = None) -> AssertionSet:
    recs = []
    for i, (year, day, month) in enumerate(weddings, start=1):
        rec = marriage(i, day, month, person("Иван", "Петров"), person("Анна", "Ильина"),
                       calendar_note=note)
        rec.year = year
        recs.append((rec, "m.py"))
    return AssertionSet(facts_from_marriages(recs, village="Тестовка")).believed()


class WeddingCalendar(unittest.TestCase):
    def test_a_wedding_in_lent_is_high_and_offers_the_month_before(self):
        result = wedding_calendar_findings(_facts((1850, 8, Month.MARCH)))
        [f] = result.findings
        self.assertEqual("great_lent", f.ban.kind)
        self.assertEqual("HIGH", f.confidence)
        # 8 February is the мясоед; 8 April is still Lent.
        self.assertEqual(((1850, 2, 8),), f.other_months)
        self.assertEqual(1, result.strict)

    def test_groom_and_bride_are_one_wedding(self):
        result = wedding_calendar_findings(_facts((1850, 8, Month.MARCH)))
        self.assertEqual(1, result.checked)
        self.assertEqual(1, len(result.findings))

    def test_an_ordinary_sunday_in_october_is_fine(self):
        result = wedding_calendar_findings(_facts((1850, 15, Month.OCTOBER)))
        self.assertEqual([], result.findings)
        self.assertEqual(1, result.checked)

    def test_a_tuesday_is_low_and_offers_the_days_beside_it(self):
        """17 October 1850 O.S. is a Tuesday: Monday and Wednesday are open."""
        [f] = wedding_calendar_findings(_facts((1850, 17, Month.OCTOBER))).findings
        self.assertEqual("fast_day_eve", f.ban.kind)
        self.assertEqual("LOW", f.confidence)
        self.assertEqual(((1850, 10, 16), (1850, 10, 18)), f.other_days)

    def test_strict_findings_come_first(self):
        found = wedding_calendar_findings(_facts((1850, 17, Month.OCTOBER),
                                                 (1850, 8, Month.MARCH))).findings
        self.assertEqual(["HIGH", "LOW"], [f.confidence for f in found])

    def test_calendar_note_stands_it_down(self):
        result = wedding_calendar_findings(_facts((1850, 8, Month.MARCH),
                                                  note="так в подлиннике, переснято"))
        self.assertEqual([], result.findings)
        self.assertEqual(1, result.noted)

    def test_after_the_julian_books_nothing_is_asked(self):
        result = wedding_calendar_findings(_facts((1920, 8, Month.MARCH)))
        self.assertEqual(0, result.checked)

    def test_the_report_gives_pascha_for_a_movable_ban(self):
        text = format_wedding_calendar(wedding_calendar_findings(
            _facts((1850, 8, Month.MARCH))))
        self.assertIn("[HIGH] 08.03.1850 (ср) — Великий пост (Пасха 23.04)", text)
        self.assertIn("тот же день в соседнем месяце разрешён: 08.02.1850", text)


if __name__ == "__main__":
    unittest.main()
