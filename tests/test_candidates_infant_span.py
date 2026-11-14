"""The infant age gate compared the recorded age against a span computed in
WHOLE YEARS, with a ±1-year tolerance to absorb that coarseness. The tolerance
swallows the entire first year of life, which is where every infant record
sits: a girl born in March and dead the next May at «1 н» (one week) scored
|0.019 − 1| = 0.98 ≤ 1.0 and came out HIGH, though the fathers were two
different men of one given name — two different infants.

Both records carry full dates, so the span can be exact.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, *, role, year, parents, birth_date=None, death_date=None,
        age=None, rec_type=None, record_num=1):
    return f.Occurrence(
        key=(given, None), name=given, given=given, patr=None, surname=None,
        gender="female", rec_type=rec_type or ("birth" if role == "child" else "death"),
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents=set(parents), birth_date=birth_date, death_date=death_date, age=age,
    )


def pair(given, born, died, age, birth_parents, death_parents=None):
    child = occ(given, role="child", year=born[0], birth_date=born,
                parents=birth_parents)
    dead = occ(given, role="deceased", year=died[0], death_date=died,
               age=age, parents=death_parents or birth_parents, record_num=2)
    return child, dead


DAD = ("Иван", "Васильевич")


class TestDatePreciseSpan(unittest.TestCase):
    def test_week_old_death_a_year_after_birth_is_rejected(self):
        # 1.12 years apart, died at one week.
        c, d = pair("Мария", (1816, 3, 25), (1817, 5, 7), "1 н", [DAD])
        self.assertIsNone(f.score_infant_pair(c, d))

    def test_eight_month_span_against_a_week_old_is_rejected(self):
        # The sweep offered a burial of June («1 нед») for a boy born the
        # previous October — 255 days lived against seven stated, a
        # thirty-sixfold disagreement. It passed because the ±1-year
        # tolerance reaches across the whole first year of life.
        c, d = pair("Иоанн", (1923, 10, 6), (1924, 6, 17), "1 нед", [DAD])
        self.assertIsNone(f.score_infant_pair(c, d))

    def test_nine_days_against_a_week_old_is_kept(self):
        # The right pair for that same burial: a birth nine days before it.
        c, d = pair("Иоанн", (1924, 6, 8), (1924, 6, 17), "1 нед", [DAD])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.confidence, "high")

    def test_a_month_old_buried_three_months_on_is_kept(self):
        # 96 days lived against «1 мес». A clerk rounds, so the stated interval
        # needs slack around it — read strictly, this pair would be thrown out.
        c, d = pair("Мавра", (1847, 4, 25), (1847, 7, 30), "1 мес", [DAD])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.confidence, "high")

    def test_slack_never_grows_past_a_year(self):
        # Nine years stated against 7.46 lived. A fraction
        # of the stated age alone would allow ±1.8 years here and take the pair,
        # which is looser than the flat ±1 year this check replaced. Tightening
        # infancy must not loosen childhood.
        c, d = pair("Анна", (1827, 1, 28), (1834, 7, 14), 9, [DAD])
        self.assertIsNone(f.score_infant_pair(c, d))

    def test_age_two_years_short_of_the_span_is_rejected(self):
        # 2.30 years apart, recorded age 1.
        c, d = pair("Феофилакт", (1815, 3, 2), (1817, 6, 20), 1, [DAD])
        self.assertIsNone(f.score_infant_pair(c, d))

    def test_six_month_old_half_a_year_after_birth_is_kept(self):
        # 0.49 years apart, «6 м» — dead on with exact dates, where
        # whole-year span said 1 and only just squeaked under the tolerance.
        c, d = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м", [DAD])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.confidence, "high")

    def test_four_year_old_across_a_year_boundary_is_kept(self):
        # Whole-year span said 5 against age 4 (Δ 1.00, at the very
        # edge); exact dates give 4.11 (Δ 0.11).
        c, d = pair("Гликерия", (1824, 12, 13), (1829, 1, 23), 4, [DAD])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.confidence, "high")

    def test_year_only_dates_still_use_the_coarse_span(self):
        # No month on either side — fall back to whole years and the ±1
        # tolerance, or every year-precision record would stop matching.
        c, d = pair("Иона", (1811, None, None), (1816, None, None), 4, [DAD])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)

    def test_death_before_birth_still_rejected(self):
        c, d = pair("Мария", (1818, 5, 1), (1816, 5, 1), 1, [DAD])
        self.assertIsNone(f.score_infant_pair(c, d))


class TestParentPatronymicEvidence(unittest.TestCase):
    def test_differing_parent_patronymic_is_reported(self):
        c, d = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м",
                    [("Алексей", "Андреевич")], [("Алексей", "Александрович")])
        s = f.score_infant_pair(c, d)
        self.assertIsNotNone(s)
        assert s is not None
        hit = [e for e in s.evidence if "patronymic" in e]
        self.assertEqual(len(hit), 1, s.evidence)
        self.assertIn("Андреевич", hit[0])
        self.assertIn("Александрович", hit[0])

    def test_evidence_only_does_not_change_the_verdict(self):
        # It is evidence for a reader, not a gate: a father written «Трофимович»
        # in one record and «Иакимович» in another may be one man.
        same = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м",
                    [("Алексей", "Андреевич")])
        differ = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м",
                      [("Алексей", "Андреевич")], [("Алексей", "Александрович")])
        a, b = f.score_infant_pair(*same), f.score_infant_pair(*differ)
        assert a is not None and b is not None
        self.assertEqual(a.confidence, b.confidence)
        self.assertEqual(a.score, b.score)

    def test_matching_patronymic_reports_nothing(self):
        c, d = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м",
                    [("Алексей", "Андреевич")])
        s = f.score_infant_pair(c, d)
        assert s is not None
        self.assertFalse([e for e in s.evidence if "patronymic" in e])

    def test_missing_patronymic_on_one_side_reports_nothing(self):
        # The common shape: «Иван» in one book, «Иван Петров» in the other.
        c, d = pair("Архипп", (1826, 9, 1), (1827, 2, 26), "6 м",
                    [("Алексей", None)], [("Алексей", "Александрович")])
        s = f.score_infant_pair(c, d)
        assert s is not None
        self.assertFalse([e for e in s.evidence if "patronymic" in e])


if __name__ == "__main__":
    unittest.main()
