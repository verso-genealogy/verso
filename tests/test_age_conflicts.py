from __future__ import annotations
import json as _json
from verso.core.targets.geni.union import GeniUnion

import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.consolidation import age_conflicts as ac
from verso.ru.consolidation import profile_reading as pr


def _profile(res_name, gender="", year=None, circa=False, end_year=None):
    birth = None
    if year is not None:
        birth = GeniEvent(date=GeniDate(year=year, circa=circa, end_year=end_year))
    return GeniProfile(res_name=res_name, gender=gender, first_name=res_name, birth=birth)


class Helpers(unittest.TestCase):
    def test_birth_year_reads_year(self):
        self.assertEqual(pr.birth_year(_profile("p", year=1840)), 1840)

    def test_birth_year_none_when_no_birth(self):
        self.assertIsNone(pr.birth_year(_profile("p")))

    def test_approximate_true_for_circa(self):
        self.assertTrue(pr.birth_is_approximate(_profile("p", year=1840, circa=True)))

    def test_approximate_true_for_range(self):
        self.assertTrue(pr.birth_is_approximate(_profile("p", year=1840, end_year=1850)))

    def test_approximate_false_for_exact(self):
        self.assertFalse(pr.birth_is_approximate(_profile("p", year=1840)))

    def test_ageconflict_span(self):
        c1 = ac.ChildAge(res_name="a", name="A", birth_year=1900, age=62)
        c2 = ac.ChildAge(res_name="b", name="B", birth_year=1913, age=77)
        f = ac.AgeConflict(parent="m", parent_name="M", parent_birth_year=1836,
                           approximate=True, role="mother", children=(c1, c2))
        self.assertEqual(f.max_age, 77)
        self.assertEqual(f.min_age, 62)



def _identity(x):
    return x


def _find(profiles, unions, **kw):
    return ac.find_age_conflicts(profiles, unions, _identity, **kw)


class Detection(unittest.TestCase):
    def test_mother_boundary(self):
        # age 49 clean, age 51 flagged (default mother_max=50)
        prof = {
            "mom": _profile("mom", gender="female", year=1800),
            "ok": _profile("ok", gender="male", year=1849),      # age 49
            "bad": _profile("bad", gender="male", year=1851),    # age 51
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"ok", "bad"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].parent, "mom")
        self.assertEqual(found[0].role, "mother")
        self.assertEqual([c.res_name for c in found[0].children], ["bad"])

    def test_father_boundary(self):
        prof = {
            "dad": _profile("dad", gender="male", year=1800),
            "ok": _profile("ok", gender="male", year=1870),      # age 70 clean
            "bad": _profile("bad", gender="male", year=1872),    # age 72 flagged
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"ok", "bad"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual([c.res_name for c in found[0].children], ["bad"])
        self.assertEqual(found[0].role, "father")

    def test_unknown_gender_uses_father_rule(self):
        prof = {
            "p": _profile("p", gender="", year=1800),
            "c60": _profile("c60", year=1860),   # age 60 clean under father rule
            "c72": _profile("c72", year=1872),   # age 72 flagged
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="p",
                                 children={"c60", "c72"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual([c.res_name for c in found[0].children], ["c72"])
        self.assertEqual(found[0].role, "parent")

    def test_missing_birth_year_skipped(self):
        # Two separate skip conditions, isolated in their own unions so they
        # don't cross-attribute: a parent with no birth year (u1), and a child
        # with no birth year (u2). Neither yields a finding.
        prof = {
            "mom": _profile("mom", gender="female"),        # no birth year
            "child": _profile("child", year=1900),
            "mom2": _profile("mom2", gender="female", year=1800),
            "child2": _profile("child2"),                   # no birth year
        }
        unions = {
            "u1": GeniUnion(res_name="u1", partner_1="mom", children={"child"}),
            "u2": GeniUnion(res_name="u2", partner_1="mom2", children={"child2"}),
        }
        self.assertEqual(_find(prof, unions), [])

    def test_approximate_flag_carried(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1836, circa=True),
            "child": _profile("child", year=1913),          # age 77
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"child"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].approximate)

    def test_external_partner_skipped(self):
        # partner is a raw profile-id not in `profiles` → skip, no crash
        prof = {"child": _profile("child", year=1900)}
        unions = {"u": GeniUnion(res_name="u", partner_1="profile-999",
                                 children={"child"})}
        self.assertEqual(_find(prof, unions), [])

    def test_multi_union_aggregation_and_span(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1836),
            "a": _profile("a", year=1898),   # age 62
            "b": _profile("b", year=1913),   # age 77
        }
        unions = {
            "u1": GeniUnion(res_name="u1", partner_1="mom", children={"a"}),
            "u2": GeniUnion(res_name="u2", partner_1="mom", children={"b"}),
        }
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(sorted(c.res_name for c in found[0].children),
                         ["a", "b"])
        self.assertEqual(found[0].max_age, 77)
        self.assertEqual(found[0].min_age, 62)

    def test_threshold_override(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1800),
            "child": _profile("child", year=1848),   # age 48
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"child"})}
        self.assertEqual(_find(prof, unions), [])                 # 48 <= 50
        self.assertEqual(len(_find(prof, unions, mother_max=45)), 1)  # 48 > 45

    def test_sorted_worst_first(self):
        prof = {
            "m1": _profile("m1", gender="female", year=1800),
            "c1": _profile("c1", year=1855),   # age 55
            "m2": _profile("m2", gender="female", year=1800),
            "c2": _profile("c2", year=1870),   # age 70
        }
        unions = {
            "u1": GeniUnion(res_name="u1", partner_1="m1", children={"c1"}),
            "u2": GeniUnion(res_name="u2", partner_1="m2", children={"c2"}),
        }
        found = _find(prof, unions)
        self.assertEqual([f.parent for f in found], ["m2", "m1"])  # 70 before 55



class TooYoung(unittest.TestCase):
    def test_young_parent_flagged(self):
        prof = {
            "dad": _profile("dad", gender="male", year=1900),
            "kid": _profile("kid", gender="male", year=1909),   # age 9
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"kid"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_young")
        self.assertEqual([c.res_name for c in found[0].children], ["kid"])

    def test_min_boundary(self):
        # age 12 clean (default min 12 → flag age < 12), age 11 flagged
        prof = {
            "p": _profile("p", gender="female", year=1900),
            "ok": _profile("ok", year=1912),    # age 12
            "bad": _profile("bad", year=1911),   # age 11
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="p",
                                 children={"ok", "bad"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_young")
        self.assertEqual([c.res_name for c in found[0].children], ["bad"])

    def test_default_old_finding_has_direction(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1800),
            "bad": _profile("bad", year=1852),   # age 52
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom", children={"bad"})}
        found = _find(prof, unions)
        self.assertEqual(found[0].direction, "too_old")

    def test_both_directions_two_findings(self):
        # one parent, a too-young child and a too-old child (60-year span)
        prof = {
            "p": _profile("p", gender="male", year=1850),
            "early": _profile("early", year=1861),   # age 11 → too_young
            "late": _profile("late", year=1921),      # age 71 → too_old
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="p",
                                 children={"early", "late"})}
        found = _find(prof, unions)
        dirs = sorted(f.direction for f in found)
        self.assertEqual(dirs, ["too_old", "too_young"])

    def test_min_override(self):
        prof = {
            "p": _profile("p", gender="female", year=1900),
            "c": _profile("c", year=1914),   # age 14
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="p", children={"c"})}
        self.assertEqual(_find(prof, unions), [])                  # 14 >= 12
        self.assertEqual(len(_find(prof, unions, mother_min=15)), 1)  # 14 < 15


class RangeHandling(unittest.TestCase):
    """A wide 'birth unknown' circa range must not fabricate an extreme age.
    too_old uses the parent's LATEST possible birth (charitable); too_young the
    EARLIEST — flag only when the parent is out of range at BOTH ends."""

    def test_wide_range_not_too_old(self):
        # Стефанида/Клавдия shape: unknown birth 1836–1890, child 1913.
        # At the latest birth (1890) the mother is only 23 → not flagged.
        prof = {
            "mom": _profile("mom", gender="female", year=1836, end_year=1890, circa=True),
            "child": _profile("child", year=1913),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom", children={"child"})}
        self.assertEqual(_find(prof, unions), [])

    def test_range_still_flags_when_latest_too_old(self):
        # Born between 1800–1810, child 1870 → age at latest birth = 60 > 50.
        prof = {
            "mom": _profile("mom", gender="female", year=1800, end_year=1810, circa=True),
            "child": _profile("child", year=1870),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom", children={"child"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_old")
        self.assertEqual(found[0].children[0].age, 60)   # conservative (latest) age

    def test_range_too_young_uses_earliest(self):
        # Born between 1895–1905, child 1904 → age at earliest birth = 9 < 12.
        prof = {
            "p": _profile("p", gender="female", year=1895, end_year=1905, circa=True),
            "c": _profile("c", year=1904),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="p", children={"c"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_young")
        self.assertEqual(found[0].children[0].age, 9)    # conservative (earliest) age


class Reporting(unittest.TestCase):
    def _one(self):
        c1 = ac.ChildAge(res_name="a", name="Ребёнок A", birth_year=1898, age=62)
        c2 = ac.ChildAge(res_name="b", name="Ребёнок B", birth_year=1913, age=77)
        return ac.AgeConflict(parent="mom", parent_name="Стефанида",
                              parent_birth_year=1836, approximate=True,
                              role="mother", children=(c1, c2))

    def test_text_report_mentions_span_name_and_hint(self):
        out = ac.format_report([self._one()])
        self.assertIn("Стефанида", out)
        self.assertIn("62", out)
        self.assertIn("77", out)
        self.assertIn("over-merge", out.lower())        # two-ended hint present
        self.assertIn("~", out)                          # approximate marker

    def test_text_report_clean(self):
        self.assertIn("0", ac.format_report([]))         # a clean message with a count

    def test_json_shape(self):
        data = _json.loads(ac.findings_to_json([self._one()]))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parent_name"], "Стефанида")
        self.assertEqual(data[0]["max_age"], 77)
        self.assertEqual(data[0]["min_age"], 62)
        self.assertTrue(data[0]["approximate"])
        self.assertEqual(data[0]["direction"], "too_old")
        self.assertEqual(len(data[0]["children"]), 2)
        self.assertEqual(data[0]["children"][0]["res_name"], "a")

    def test_young_report_and_json(self):
        c = ac.ChildAge(res_name="k", name="Ребёнок", birth_year=1909, age=9)
        f = ac.AgeConflict(parent="d", parent_name="Филипп",
                           parent_birth_year=1900, approximate=False,
                           role="father", children=(c,), direction="too_young")
        out = ac.format_report([f])
        self.assertIn("Филипп", out)
        self.assertIn("ранн", out.lower())          # young-specific wording
        data = _json.loads(ac.findings_to_json([f]))
        self.assertEqual(data[0]["direction"], "too_young")


class Run(unittest.TestCase):
    def test_run_exit_and_text(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1836),
            "child": _profile("child", year=1913),   # age 77
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"child"})}
        text, code = ac.run(prof, unions, _identity,
                            mother_max=50, father_max=70, as_json=False)
        self.assertEqual(code, 1)
        self.assertIn("77", text)

    def test_run_clean_exit_zero(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1870),
            "child": _profile("child", year=1900),   # age 30
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"child"})}
        _text, code = ac.run(prof, unions, _identity,
                            mother_max=50, father_max=70, as_json=False)
        self.assertEqual(code, 0)

    def test_run_json_mode(self):
        prof = {
            "mom": _profile("mom", gender="female", year=1836),
            "child": _profile("child", year=1913),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="mom",
                                 children={"child"})}
        text, code = ac.run(prof, unions, _identity,
                            mother_max=50, father_max=70, as_json=True)
        self.assertEqual(code, 1)
        _json.loads(text)  # valid JSON


if __name__ == "__main__":
    unittest.main()


class BeforeBoundBirth(unittest.TestCase):
    """A `range="before"` birth (the anchor-less parent estimate) carries an
    UPPER bound in `year`, not a lower one — reading it as a range start would
    understate the parent's age and fabricate findings."""

    @staticmethod
    def _before(res_name, gender, year):
        return GeniProfile(
            res_name=res_name, gender=gender, first_name=res_name,
            birth=GeniEvent(date=GeniDate(year=year, circa=True,
                                          date_range="before")),
        )

    def test_birth_year_is_none_for_before_range(self):
        self.assertIsNone(pr.birth_year(self._before("dad", "male", 1805)))

    def test_birth_year_latest_still_reads_the_bound(self):
        self.assertEqual(
            pr.birth_year_latest(self._before("dad", "male", 1805)), 1805)

    def test_before_bounded_parent_produces_no_finding(self):
        prof = {
            "dad": self._before("dad", "male", 1805),
            "kid": _profile("kid", gender="male", year=1700),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"kid"})}
        self.assertEqual(_find(prof, unions), [])


class CharitableChildRange(unittest.TestCase):
    """Both profiles must be read in the direction that makes the age
    plausible. Reading the CHILD at its range start for the too-young test
    made every child with a wide estimate look older than the data shows."""

    def test_wide_child_range_does_not_fabricate_a_negative_age(self):
        """Горюхино «Пётр Романович» shape: a precisely-dated parent against a
        child estimated at [1771..1825]. The old code took 1771 and reported an
        age of -25; 1825 is equally consistent and gives a plausible 29."""
        prof = {
            "dad": _profile("dad", gender="male", year=1796),
            "kid": _profile("kid", gender="female", year=1771, circa=True,
                            end_year=1825),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"kid"})}
        self.assertEqual(_find(prof, unions), [])

    def test_still_flags_when_even_the_latest_child_birth_is_too_early(self):
        """The charitable read must not disarm the check: a child whose whole
        range predates the parent is still a conflict."""
        prof = {
            "dad": _profile("dad", gender="male", year=1796),
            "kid": _profile("kid", gender="female", year=1750, circa=True,
                            end_year=1760),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"kid"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_young")
        self.assertEqual(found[0].children[0].birth_year, 1760)
        self.assertEqual(found[0].min_age, -36)

    def test_too_old_still_reads_the_child_at_its_earliest(self):
        """The too-old direction keeps the opposite (also charitable) pairing:
        earliest child, latest parent."""
        prof = {
            "dad": _profile("dad", gender="male", year=1700),
            "kid": _profile("kid", gender="male", year=1790, circa=True,
                            end_year=1800),
        }
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"kid"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "too_old")
        self.assertEqual(found[0].children[0].birth_year, 1790)
        self.assertEqual(found[0].max_age, 90)
