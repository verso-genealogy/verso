"""A death record ends a person's timeline: no later record can be the same
person — UNLESS the later record is a ревизская сказка listing them as having
died since the previous revision, which is exactly what a сказка does.

The case that motivated this: a girl born in September and dead the next
February at «полгода», paired with a LIVING girl of the same name, age 1 in a
revision years later — the parents reused a dead daughter's name (necronym).
Same father and same surname scored it HIGH.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, rec_type, role, year, stub=None, surname=None,
        gender="female", record_num=1, parents=None, departed=False):
    return f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(), given=given,
        patr=patr, surname=surname, gender=gender, rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents=set(parents or []), stub=stub, departed=departed,
    )


DAD = ("Лука", "Савельевич")


def dead(year=1843, **kw):
    return occ("Дарья", "Лукинична", rec_type="death", role="deceased",
               year=year, surname="Сидорова", parents=[DAD], **kw)


def census(year=1852, departed=False, **kw):
    return occ("Дарья", "Лукинична", rec_type="census", role="member_20",
               year=year, surname="Сидорова", parents=[DAD], record_num=38,
               departed=departed, **kw)


class TestPostDeathGate(unittest.TestCase):
    def test_living_census_member_after_death_is_rejected(self):
        self.assertIsNone(f.score_pair(dead(), census()))
        self.assertIsNone(f.score_pair(census(), dead()))  # symmetric

    def test_departed_census_member_after_death_still_pairs(self):
        # A сказка enumerates members who died since the previous revision;
        # that entry IS the dead person and must keep matching.
        s = f.score_pair(dead(), census(departed=True))
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.confidence, "high")

    def test_census_member_before_the_death_still_pairs(self):
        s = f.score_pair(dead(year=1843), census(year=1836))
        self.assertIsNotNone(s)

    def test_godparent_after_death_is_rejected(self):
        later = occ("Дарья", "Лукинична", rec_type="birth",
                    role="god_parent_1", year=1852, surname="Сидорова",
                    parents=[DAD])
        self.assertIsNone(f.score_pair(dead(), later))

    def test_relative_mention_after_death_still_pairs(self):
        # «умершего Луки дочь» — a dead person is named as a relative in
        # later records all the time. Never reject that.
        later = occ("Дарья", "Лукинична", rec_type="death",
                    role="relative", year=1852, surname="Сидорова", parents=[DAD])
        self.assertIsNotNone(f.score_pair(dead(), later))

    def test_father_after_death_still_pairs(self):
        # A posthumous child's birth record names the dead father.
        d = occ("Лука", "Савельевич", rec_type="death", role="deceased",
                year=1843, gender="male", surname="Сидоров")
        later = occ("Лука", "Савельевич", rec_type="birth", role="father",
                    year=1844, gender="male", surname="Сидоров")
        self.assertIsNotNone(f.score_pair(d, later))

    def test_normal_infant_pair_is_untouched(self):
        # birth child (1842) then death deceased (1843) — the death is LAST,
        # which is the ordinary born-and-died shape.
        child = occ("Дарья", "Лукинична", rec_type="birth", role="child",
                    year=1842, surname="Сидорова", parents=[DAD])
        self.assertIsNotNone(f.score_pair(child, dead(year=1843)))


class TestPostDeathPredicate(unittest.TestCase):
    def test_predicate_is_public_and_symmetric(self):
        d, c = dead(), census()
        self.assertTrue(f.post_death_conflict(d, c))
        self.assertTrue(f.post_death_conflict(c, d))
        self.assertFalse(f.post_death_conflict(d, census(departed=True)))


if __name__ == "__main__":
    unittest.main()
