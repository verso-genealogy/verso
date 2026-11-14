"""The infant matcher used to gate hard on the child's given name, so a death
record that mis-names the infant could never pair with its birth record.

The case: a girl born in April; the death record of July names her «Марья» —
the mother's name — and states «1 мес» instead of three. Both parents'
identities agree, and no other child of that father was alive. The pair must
surface for review, and must never auto-draft."""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, *, patr=None, surname=None, gender="female", rec_type="birth",
        record_num=1, role="child", year=1847, parents=None,
        birth_date=None, death_date=None, age=None):
    o = f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(), given=given,
        patr=patr, surname=surname, gender=gender, rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents=set(parents or []), birth_date=birth_date, death_date=death_date,
        age=age,
    )
    o.stub = None
    return o


def mavra_birth():
    return occ("Мавра", rec_type="birth", role="child", record_num=11,
               birth_date=(1847, 4, 25), parents=[("Павел", "Игнатьевич")])


def marja_death():
    return occ("Марья", rec_type="death", role="deceased", record_num=4,
               death_date=(1847, 7, 30), age="1 мес",
               parents=[("Павел", "Игнатьевич")])


class TestNameVariantPair(unittest.TestCase):
    def test_pair_surfaces_despite_the_differing_given_name(self):
        s = f.score_infant_pair(mavra_birth(), marja_death())
        self.assertIsNotNone(s)
        assert s is not None
        self.assertTrue(any("given name differs" in e for e in s.evidence),
                        s.evidence)

    def test_never_auto_drafted(self):
        s = f.score_infant_pair(mavra_birth(), marja_death())
        assert s is not None
        self.assertNotEqual(s.confidence, "high")

    def test_symmetric(self):
        self.assertIsNotNone(f.score_infant_pair(marja_death(), mavra_birth()))

    def test_parent_patronymic_disagreement_rejects_the_variant(self):
        d = occ("Марья", rec_type="death", role="deceased", record_num=4,
                death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Семёнович")])
        self.assertIsNone(f.score_infant_pair(mavra_birth(), d))

    def test_bare_parent_given_name_is_not_enough(self):
        """Without a patronymic on both sides the parent is not pinned down,
        so a differing child name stays unmatched."""
        b = occ("Мавра", rec_type="birth", role="child", record_num=11,
                birth_date=(1847, 4, 25), parents=[("Павел", None)])
        d = occ("Марья", rec_type="death", role="deceased", record_num=4,
                death_date=(1847, 7, 30), age="1 мес", parents=[("Павел", None)])
        self.assertIsNone(f.score_infant_pair(b, d))

    def test_contradicting_age_still_rejects(self):
        d = occ("Марья", rec_type="death", role="deceased", record_num=4,
                death_date=(1849, 7, 30), age="полгода",
                parents=[("Павел", "Игнатьевич")])
        self.assertIsNone(f.score_infant_pair(mavra_birth(), d))

    def test_gender_mismatch_rejects(self):
        d = occ("Мефодий", rec_type="death", role="deceased", record_num=4,
                gender="male", death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Игнатьевич")])
        self.assertIsNone(f.score_infant_pair(mavra_birth(), d))

    def test_identical_names_keep_the_original_high_confidence(self):
        d = occ("Мавра", rec_type="death", role="deceased", record_num=4,
                death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Игнатьевич")])
        s = f.score_infant_pair(mavra_birth(), d)
        assert s is not None
        self.assertEqual(s.confidence, "high")
        self.assertFalse(any("given name differs" in e for e in s.evidence))


class TestParentOnlyBucket(unittest.TestCase):
    def test_the_pair_meets_in_the_pool(self):
        b, d = mavra_birth(), marja_death()
        pool = {}
        for o in (b, d):
            for k in f.infant_keys(o) + f.infant_variant_keys(o):
                pool.setdefault(k, []).append(o)
        got = f.find_infant_candidates(b, pool, consolidated=set())
        self.assertTrue(any(s.cand is d for s in got),
                        "name-variant twin must be reachable from the pool")


class TestVariantMustBeExplicable(unittest.TestCase):
    """A differing name is only worth surfacing when the source could plausibly
    have produced it. Two unrelated names under one father are siblings."""

    def test_unrelated_names_are_dropped(self):
        b = occ("Флор", gender="male", rec_type="birth", role="child",
                birth_date=(1847, 4, 25), parents=[("Павел", "Игнатьевич")])
        d = occ("Матвей", gender="male", rec_type="death", role="deceased",
                record_num=4, death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Игнатьевич")])
        self.assertIsNone(f.score_infant_pair(b, d))

    def test_near_homograph_is_kept(self):
        b = occ("Акилина", rec_type="birth", role="child",
                birth_date=(1847, 4, 25), parents=[("Павел", "Игнатьевич")])
        d = occ("Акулина", rec_type="death", role="deceased", record_num=4,
                death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Игнатьевич")])
        s = f.score_infant_pair(b, d)
        assert s is not None
        self.assertTrue(any("near-homograph" in e for e in s.evidence), s.evidence)

    def test_parent_name_carried_into_the_child_slot_is_kept(self):
        """The death record names the girl after her mother."""
        b = occ("Мавра", rec_type="birth", role="child", birth_date=(1847, 4, 25),
                parents=[("Павел", "Игнатьевич"), ("Марья", "Родионовна")])
        d = occ("Марья", rec_type="death", role="deceased", record_num=4,
                death_date=(1847, 7, 30), age="1 мес",
                parents=[("Павел", "Игнатьевич")])
        s = f.score_infant_pair(b, d)
        assert s is not None
        self.assertTrue(any("repeats a parent" in e for e in s.evidence), s.evidence)
