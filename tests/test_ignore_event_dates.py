"""An `ignore`d event date is dropped from the consolidation, as an ignored name is.

Before, a date `ignore` only kept a conflict out of the report: the value itself
still reached `_pick_best_date` and widened the canonical's range, so the only
way to keep a wrong date off a profile was an `override` — which pins the whole
event and silences every later conflict on it. An overstated burial age was
the case: it widened a canonical's birth into a range nothing else supported.
"""
import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _ignore(**fields):
    entry = {"first_name": "", "middle_name": "", "last_name": "",
             "birth_last_name": "", "title": "",
             "birth.date": None, "death.date": None,
             "baptism.date": None, "burial.date": None}
    entry.update(fields)
    return entry


def _canonical(ignore_entries, records):
    consolidation = Consolidation(
        profile_move_list={r.res_name: "canon" for r in records},
        profile_ignores={"canon": ignore_entries},
    )
    gen = TerraformGenerator(consolidation=consolidation)
    for rec in records:
        gen._emit_profile("out.tf", rec)
    gen.finalize()
    return gen._consolidated_profiles["canon"], gen.redundant_ignores


OVERSTATED = GeniDate(month=7, year=1740, circa=True)
FROM_ROLL = GeniDate(year=1762, circa=True)


class AnIgnoredDateIsDropped(unittest.TestCase):
    def test_on_a_merged_record(self):
        canon, dead = _canonical(
            [_ignore(**{"birth.date": OVERSTATED})],
            [GeniProfile(res_name="roll", first_name="Прасковья",
                         birth=GeniEvent(date=FROM_ROLL)),
             GeniProfile(res_name="burial", first_name="Прасковья",
                         birth=GeniEvent(date=OVERSTATED))])
        self.assertEqual(FROM_ROLL, canon.birth.date)
        self.assertEqual([], dead)

    def test_on_the_seed(self):
        canon, dead = _canonical(
            [_ignore(**{"birth.date": OVERSTATED})],
            [GeniProfile(res_name="burial", first_name="Прасковья",
                         birth=GeniEvent(date=OVERSTATED)),
             GeniProfile(res_name="roll", first_name="Прасковья",
                         birth=GeniEvent(date=FROM_ROLL))])
        self.assertEqual(FROM_ROLL, canon.birth.date)
        self.assertEqual([], dead)

    def test_its_place_survives(self):
        canon, _ = _canonical(
            [_ignore(**{"birth.date": OVERSTATED})],
            [GeniProfile(res_name="burial", first_name="Прасковья",
                         birth=GeniEvent(date=OVERSTATED, location="Простофилино")),
             GeniProfile(res_name="roll", first_name="Прасковья",
                         birth=GeniEvent(date=FROM_ROLL))])
        self.assertEqual("Простофилино", canon.birth.location)
        self.assertEqual(FROM_ROLL, canon.birth.date)

    def test_a_date_nobody_ignored_still_merges(self):
        canon, _ = _canonical(
            [],
            [GeniProfile(res_name="roll", first_name="Прасковья",
                         birth=GeniEvent(date=FROM_ROLL)),
             GeniProfile(res_name="burial", first_name="Прасковья",
                         birth=GeniEvent(date=OVERSTATED))])
        self.assertNotEqual(FROM_ROLL, canon.birth.date)


if __name__ == "__main__":
    unittest.main()
