"""Unit tests for the infant born-and-died matcher in candidates.py:
age parsing, the birth-child↔death-deceased scorer (age-vs-span gate), the
necronym guard, and infant_keys bucketing."""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, *, patr=None, surname=None, gender="female", rec_type="birth",
        record_num=1, role="child", year=1912, parents=None,
        birth_date=None, death_date=None, age=None, stub=None):
    o = f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(), given=given,
        patr=patr, surname=surname, gender=gender, rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents=set(parents or []), birth_date=birth_date, death_date=death_date,
        age=age,
    )
    o.stub = stub
    return o


def birth_child(given, *, parents, year, surname=None, record_num=1, stub=None):
    return occ(given, surname=surname, rec_type="birth", role="child",
               record_num=record_num, year=year,
               birth_date=(year, None, None), parents=parents, stub=stub)


def death_deceased(given, *, parents, year, age=None, surname=None,
                   record_num=1, stub=None):
    return occ(given, surname=surname, rec_type="death", role="deceased",
               record_num=record_num, year=year, death_date=(year, None, None),
               parents=parents, age=age, stub=stub)


class TestAgeYears(unittest.TestCase):
    def _years(self, age):
        v = f._age_years(age)
        self.assertIsNotNone(v)
        assert v is not None
        return v

    def test_months(self):
        self.assertAlmostEqual(self._years("8 мес"), 8 / 12, places=3)

    def test_compound(self):
        self.assertAlmostEqual(self._years("2 года 6 мес"), 2.5, places=3)

    def test_days(self):
        self.assertAlmostEqual(self._years("21 дн"), 21 / 365, places=3)

    def test_numeric(self):
        self.assertEqual(f._age_years(1), 1.0)
        self.assertEqual(f._age_years("1.0"), 1.0)

    def test_none_and_unparseable(self):
        self.assertIsNone(f._age_years(None))
        self.assertIsNone(f._age_years("неизвестно"))


class TestScoreInfantPair(unittest.TestCase):
    DAD = ("Фёдор", "Семёнович")

    def test_consistent_age_is_high(self):
        b = birth_child("Мария", parents=[self.DAD, ("Анна", "Алексеевна")], year=1912)
        d = death_deceased("Мария", parents=[("Фёдор", None)], year=1913, age="1 год")
        s = f.score_infant_pair(b, d)
        self.assertIsNotNone(s)
        self.assertEqual(s.confidence, "high")
        self.assertTrue(any("shared parent" in e for e in s.evidence))

    def test_symmetric_death_target(self):
        b = birth_child("Мария", parents=[self.DAD], year=1912)
        d = death_deceased("Мария", parents=[self.DAD], year=1913, age="1 год")
        self.assertEqual(f.score_infant_pair(d, b).confidence, "high")

    def test_contradictory_age_rejected(self):
        # necronym: a "Мария, 8 лет" who died 1913 was born ~1905, not 1912.
        b = birth_child("Мария", parents=[self.DAD], year=1912)
        d = death_deceased("Мария", parents=[self.DAD], year=1913, age="8 лет")
        self.assertIsNone(f.score_infant_pair(b, d))

    def test_unknown_age_is_medium(self):
        b = birth_child("Мария", parents=[self.DAD], year=1919)
        d = death_deceased("Мария", parents=[self.DAD], year=1919, age=None)
        self.assertEqual(f.score_infant_pair(b, d).confidence, "medium")

    def test_no_shared_parent_skipped(self):
        b = birth_child("Мария", parents=[self.DAD], year=1912)
        d = death_deceased("Мария", parents=[("Иван", "Петрович")], year=1913, age="1 год")
        self.assertIsNone(f.score_infant_pair(b, d))

    def test_same_role_skipped(self):
        b1 = birth_child("Мария", parents=[self.DAD], year=1912, record_num=1)
        b2 = birth_child("Мария", parents=[self.DAD], year=1912, record_num=2)
        self.assertIsNone(f.score_infant_pair(b1, b2))

    def test_death_before_birth_skipped(self):
        b = birth_child("Мария", parents=[self.DAD], year=1915)
        d = death_deceased("Мария", parents=[self.DAD], year=1913, age=None)
        self.assertIsNone(f.score_infant_pair(b, d))


class TestNecronymGuard(unittest.TestCase):
    DAD = ("Фёдор", "Семёнович")

    def _pool(self, occs):
        pool = {}
        for o in occs:
            for k in f.infant_keys(o):
                pool.setdefault(k, []).append(o)
        return pool

    def test_two_birth_children_caps_at_medium(self):
        # Parent re-used a dead child's name → two "Иван" births; never auto-draft.
        b1 = birth_child("Иван", parents=[self.DAD], year=1908, record_num=1,
                         stub="_1908_01_01_ivan_b1_mk_births_1_child")
        b2 = birth_child("Иван", parents=[self.DAD], year=1912, record_num=2,
                         stub="_1912_01_01_ivan_b2_mk_births_2_child")
        d = death_deceased("Иван", parents=[self.DAD], year=1913, age="1 год",
                           stub="_1913_01_01_ivan_d_mk_deaths_1_deceased")
        pool = self._pool([b1, b2, d])
        scored = f.find_infant_candidates(d, pool, consolidated=set())
        self.assertTrue(scored)
        self.assertTrue(all(s.confidence != "high" for s in scored))

    def test_single_pair_stays_high(self):
        b = birth_child("Мария", parents=[self.DAD], year=1912,
                        stub="_1912_01_01_marija_mk_births_1_child")
        d = death_deceased("Мария", parents=[self.DAD], year=1913, age="1 год",
                           stub="_1913_01_01_marija_mk_deaths_1_deceased")
        pool = self._pool([b, d])
        scored = f.find_infant_candidates(d, pool, consolidated=set())
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0].confidence, "high")

    def test_already_consolidated_skipped(self):
        b = birth_child("Мария", parents=[self.DAD], year=1912,
                        stub="_1912_01_01_marija_mk_births_1_child")
        d = death_deceased("Мария", parents=[self.DAD], year=1913, age="1 год",
                           stub="_1913_01_01_marija_mk_deaths_1_deceased")
        pool = self._pool([b, d])
        scored = f.find_infant_candidates(
            d, pool, consolidated={"_1912_01_01_marija_mk_births_1_child"})
        self.assertEqual(scored, [])


class TestInfantKeys(unittest.TestCase):
    def test_child_and_deceased_share_key(self):
        dad = ("Фёдор", "Семёнович")
        b = birth_child("Мария", parents=[dad, ("Анна", "Алексеевна")], year=1912)
        d = death_deceased("Мария", parents=[("Фёдор", None)], year=1913)
        self.assertIn(("Мария", "Фёдор"), set(f.infant_keys(b)) & set(f.infant_keys(d)))

    def test_no_parent_disables(self):
        self.assertEqual(f.infant_keys(occ("Мария", role="deceased", parents=[])), [])

    def test_non_child_role_disabled(self):
        father = occ("Фёдор", role="father", parents=[("Дед", "Иванович")])
        self.assertEqual(f.infant_keys(father), [])


if __name__ == "__main__":
    unittest.main()
