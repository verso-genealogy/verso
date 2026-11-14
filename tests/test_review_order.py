"""verso.ru.dsl.order — where a record stands in its book, and where it should."""
from __future__ import annotations

import unittest

from verso.ru.dsl.order import Place, Spot, describe, frame_text, month_of, placements, side, twins

JAN, DEC = "12:4", "40:4"


def spot(ordinal, number, gender="м", *, key=None, group=JAN, section=1, months=(1, 1), day=1,
         frame=None, kind="births", name=None, kin=None):
    return Spot(ordinal=ordinal, group=group, kind=kind, number=number, gender=gender,
                section_month=section, months=months, day=day, key=key, frame=frame, name=name, kin=kin)


class ByScan(unittest.TestCase):
    def test_one_stray_record_is_found_and_not_its_neighbours(self):
        # One record written in January, its window at the end of the book.
        spots = [spot(0, 4, key=(5, 0, 0.2)), spot(1, 18, key=(15, 0, 0.6), months=(12, 12)),
                 spot(2, 6, key=(6, 0, 0.3)), spot(3, 4, "ж", key=(7, 0, 0.1)),
                 spot(4, 18, "ж", key=(15, 0, 0.4), group=DEC, section=12, months=(12, 12), frame="кадр16")]
        self.assertEqual({1: Place(4, "after", "scan", None)}, placements(spots))

    def test_a_record_sharing_its_twins_windows_goes_beside_it(self):
        spots = [spot(0, 4, key=(5, 0, 0.2)), spot(1, 18, key=(15, 0, 0.6)), spot(2, 6, key=(6, 0, 0.3)),
                 spot(3, 18, "ж", key=(15, 0, 0.4), group=DEC), spot(4, 18, key=(15, 0, 0.6), group=DEC)]
        self.assertEqual({1: Place(4, "after", "scan", 4)}, placements(spots))

    def test_before_the_first_when_nothing_comes_earlier(self):
        spots = [spot(0, 4, key=(5, 0, 0.2)), spot(1, 6, key=(6, 0, 0.3)), spot(2, 1, key=(1, 0, 0.1))]
        self.assertEqual({2: Place(0, "before", "scan", None)}, placements(spots))

    def test_in_order_nothing_moves(self):
        spots = [spot(0, 1, key=(1, 0, 0.1)), spot(1, 2, key=(1, 0, 0.5)), spot(2, 3)]
        self.assertEqual({}, placements(spots))

    def test_two_records_of_one_frame_go_by_height(self):
        spots = [spot(0, 1, key=(1, 0, 0.5)), spot(1, 2, key=(1, 0, 0.2)), spot(2, 3, key=(2, 0, 0.1))]
        self.assertEqual({0: Place(1, "after", "scan", None)}, placements(spots))


    def test_on_a_spread_the_left_page_comes_first_whatever_the_height(self):
        # A spread, 43об | 44: № 11 low on the left, № 13 high on the right.
        spots = [spot(0, 11, key=(12, side((0.102, 0.683, 0.472, 0.791)), 0.683)),
                 spot(1, 13, key=(12, side((0.473, 0.127, 0.862, 0.232)), 0.127))]
        self.assertEqual({}, placements(spots))


class ByBook(unittest.TestCase):
    def test_a_record_without_a_window_goes_to_its_months_section(self):
        spots = [spot(0, 4, day=5), spot(1, 18, months=(12, 12), day=12), spot(2, 6, day=22),
                 spot(3, 27, group=DEC, section=12, months=(12, 12), day=3),
                 spot(4, 29, group=DEC, section=12, months=(12, 12), day=20)]
        self.assertEqual({1: Place(3, "after", "book", None)}, placements(spots))

    def test_a_christening_in_the_section_month_is_in_place(self):
        # Born 30 December, christened 1 January: in the January section, as the book has it.
        self.assertEqual({}, placements([spot(0, 1, months=(12, 1), day=30), spot(1, 2, day=3)]))

    def test_no_section_of_its_month_no_suggestion(self):
        self.assertEqual({}, placements([spot(0, 4), spot(1, 18, months=(12, 12))]))

    def test_its_twin_in_the_section(self):
        spots = [spot(0, 18, months=(12, 12), day=12),
                 spot(1, 18, group=DEC, section=12, months=(12, 12), day=12)]
        self.assertEqual({0: Place(1, "after", "book", 1)}, placements(spots))


class Twins(unittest.TestCase):
    def test_the_same_entry_read_twice(self):
        # One entry read twice, «Павел» and «Павелъ»: both keys are `names.match_key`'s «павел».
        spots = [spot(0, 4, name="михаил"), spot(1, 18, months=(12, 12), day=12, name="фома"),
                 spot(2, 18, months=(12, 12), day=12, name="фома")]
        self.assertEqual({1: 2, 2: 1}, twins(spots))

    def test_a_number_repeated_for_another_person_is_no_twin(self):
        # A number repeated for two children: Ефрем and Климонт, christened the same day.
        self.assertEqual({}, twins([spot(0, 2, day=28, name="ефрем"), spot(1, 2, day=28, name="климонт")]))

    def test_two_children_of_one_name_and_day_by_two_fathers_are_no_twins(self):
        # Two children of one name christened the same day: a son of Артемий and a son of Степан.
        self.assertEqual({}, twins([spot(0, 1, day=11, name="михаил", kin="артемий"),
                                    spot(1, 1, day=11, name="михаил", kin="степан")]))
        # One father unwritten: nothing to tell them apart by.
        self.assertEqual({0: 1, 1: 0}, twins([spot(0, 1, day=11, name="михаил", kin="артемий"),
                                              spot(1, 1, day=11, name="михаил")]))

    def test_another_day_or_nothing_to_compare_is_no_twin(self):
        self.assertEqual({}, twins([spot(0, 2, day=3, name="анна"), spot(1, 2, day=4, name="анна")]))
        self.assertEqual({}, twins([spot(0, 2, day=None, name="анна"), spot(1, 2, day=None, name="анна")]))
        self.assertEqual({}, twins([spot(0, None, name="анна"), spot(1, None, name="анна")]))
        self.assertEqual({}, twins([spot(0, 2), spot(1, 2)]))

    def test_of_three_the_nearest(self):
        spots = [spot(0, 5, name="анна"), spot(3, 5, name="анна"), spot(9, 5, name="анна")]
        self.assertEqual({0: 3, 3: 0, 9: 3}, twins(spots))


class Words(unittest.TestCase):
    def test_describe(self):
        spots = {4: spot(4, 18, "ж", group=DEC, section=12, frame="кадр16")}
        self.assertEqual("после № 18 ж · декабрь · кадр 16", describe(Place(4, "after", "scan", None), spots))
        self.assertEqual("перед № 18 ж · декабрь · кадр 16", describe(Place(4, "before", "scan", None), spots))

    def test_frames_and_months(self):
        self.assertEqual(("кадр 3", "л. 421об"), (frame_text("кадр3"), frame_text("421об")))
        self.assertEqual((12, None), (month_of("Month.DECEMBER"), month_of("DECEMBER")))


if __name__ == "__main__":
    unittest.main()
