from __future__ import annotations

import json as _json
import unittest

from verso.ru.consolidation import profile_reading as pr
from verso.ru.consolidation import union_duplicates as ud
from verso.ru.facts.checks.lives import Baptism
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion


def _profile(res_name, given, born=None, died=None, circa=False):
    birth = GeniEvent(date=GeniDate(year=born, circa=circa)) if born is not None else None
    death = GeniEvent(date=GeniDate(year=died)) if died is not None else None
    return GeniProfile(res_name=res_name, first_name=given, birth=birth, death=death)


def _find(profiles, unions, **kw):
    return ud.find_union_duplicates(profiles, unions, lambda r: r, **kw)


def _counted(**held):
    """`households_of` for a test: canonical → the (date, number, roll) triples
    a roll counted it into, as `verso.ru.consolidation.union_duplicates.union_evidence` reads them off
    the rolls."""
    def of(canon):
        return frozenset(held.get(canon, ()))
    return of


class DeathYear(unittest.TestCase):
    def test_reads_year(self):
        self.assertEqual(pr.death_year(_profile("p", "Иван", died=1850)), 1850)

    def test_none_without_death(self):
        self.assertIsNone(pr.death_year(_profile("p", "Иван")))


class Detection(unittest.TestCase):
    def test_two_same_named_children_are_a_candidate(self):
        prof = {"a": _profile("a", "Степан", born=1841),
                "b": _profile("b", "Степан", born=1841)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", partner_2="mom",
                                 children={"a", "b"})}
        found = _find(prof, unions)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].is_candidate)
        self.assertEqual(found[0].given_name, "Степан")
        self.assertEqual([m.res_name for m in found[0].members], ["a", "b"])
        self.assertEqual(found[0].partners, ("dad", "mom"))

    def test_different_names_are_not_reported(self):
        prof = {"a": _profile("a", "Степан", born=1841),
                "b": _profile("b", "Мавра", born=1842)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertEqual(_find(prof, unions), [])

    def test_same_name_in_different_unions_is_not_reported(self):
        prof = {"a": _profile("a", "Иван", born=1841),
                "b": _profile("b", "Иван", born=1841)}
        unions = {"u1": GeniUnion(res_name="u1", partner_1="d1", children={"a"}),
                  "u2": GeniUnion(res_name="u2", partner_1="d2", children={"b"})}
        self.assertEqual(_find(prof, unions), [])

    def test_external_child_is_skipped(self):
        prof = {"a": _profile("a", "Иван", born=1841)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad",
                                 children={"a", "not_ours"})}
        self.assertEqual(_find(prof, unions), [])

    def test_child_without_given_name_is_skipped(self):
        prof = {"a": _profile("a", "", born=1841), "b": _profile("b", "", born=1841)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertEqual(_find(prof, unions), [])


class Guards(unittest.TestCase):
    def test_death_before_other_birth_is_reused_name(self):
        """A dead child's name given to the next one."""
        prof = {"a": _profile("a", "Фока", born=1835, died=1836),
                "b": _profile("b", "Фока", born=1839)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        found = _find(prof, unions)
        self.assertEqual(found[0].verdict, ud.VERDICT_REUSED_NAME)
        self.assertFalse(found[0].is_candidate)

    def test_births_far_apart_are_siblings(self):
        prof = {"a": _profile("a", "Акилина", born=1829),
                "b": _profile("b", "Акилина", born=1838)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        found = _find(prof, unions)
        self.assertEqual(found[0].verdict, ud.VERDICT_SIBLINGS)

    def test_one_year_drift_still_a_candidate(self):
        """A revision's age drift is about a year — that must not retire a pair."""
        prof = {"a": _profile("a", "Ксения", born=1839),
                "b": _profile("b", "Ксения", born=1840)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertTrue(_find(prof, unions)[0].is_candidate)

    def test_sibling_gap_is_configurable(self):
        prof = {"a": _profile("a", "Ксения", born=1839),
                "b": _profile("b", "Ксения", born=1840)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        found = _find(prof, unions, sibling_gap=1)
        self.assertEqual(found[0].verdict, ud.VERDICT_SIBLINGS)

    def test_a_derived_year_does_not_retire_a_pair(self):
        """A girl born 1881 by her metric, «14 лет» in the 1897 census ⇒ 1883.
        The gap is 2 and would retire her, but a census age is not a date —
        the same revision drift the gap is sized against IS the disagreement."""
        prof = {"a": _profile("a", "Марфа", born=1881),
                "b": _profile("b", "Марфа", born=1883, circa=True)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        found = _find(prof, unions)
        self.assertTrue(found[0].is_candidate)
        self.assertIn("приблиз", found[0].reason)

    def test_a_derived_year_is_widened_by_the_drift_not_ignored(self):
        """A child five years old in a January census ⇒ ~1894, and a birth
        recorded that November. Widening the derived year by the drift
        still leaves four years — dropping the guard outright took this pair."""
        prof = {"a": _profile("a", "Екатерина", born=1894, circa=True),
                "b": _profile("b", "Екатерина", born=1899)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertEqual(_find(prof, unions)[0].verdict, ud.VERDICT_SIBLINGS)

    def test_two_recorded_years_that_far_apart_are_still_siblings(self):
        """The mirror: with both births recorded, the guard must still fire."""
        prof = {"a": _profile("a", "Марфа", born=1882),
                "b": _profile("b", "Марфа", born=1884)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertEqual(_find(prof, unions)[0].verdict, ud.VERDICT_SIBLINGS)

    def test_two_members_of_one_household_are_two_people(self):
        """The scribe enumerated them on adjacent lines — the source says two."""
        prof = {"a": _profile("a", "Настасья", born=1834), "b": _profile("b", "Настасья", born=1835)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        seven = ("1850-10-01", "7", "rs_1850.py")
        found = _find(prof, unions, households_of=_counted(a={seven}, b={seven}))
        self.assertEqual(found[0].verdict, ud.VERDICT_SAME_HOUSEHOLD)
        self.assertIn("двора 7", found[0].reason)

    def test_different_households_still_a_candidate(self):
        prof = {"a": _profile("a", "Иван", born=1834), "b": _profile("b", "Иван", born=1834)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        held = _counted(a={("1850-10-01", "7", "rs_1850.py")},
                        b={("1850-10-01", "9", "rs_1850.py")})
        self.assertTrue(_find(prof, unions, households_of=held)[0].is_candidate)

    def test_same_household_across_two_revisions_still_a_candidate(self):
        """Household numbers are re-used between revisions — only one revision counts."""
        prof = {"a": _profile("a", "Иван", born=1834), "b": _profile("b", "Иван", born=1834)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        held = _counted(a={("1834-02-20", "7", "rs_1834.py")},
                        b={("1850-10-01", "7", "rs_1850.py")})
        self.assertTrue(_find(prof, unions, households_of=held)[0].is_candidate)

    def test_metric_beside_census_is_still_a_candidate(self):
        """The whole point of the check: a birth record next to its census entry."""
        prof = {"a": _profile("a", "Степан", born=1841), "b": _profile("b", "Степан", born=1841)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        held = _counted(b={("1850-10-01", "49", "rs_1850.py")})
        self.assertTrue(_find(prof, unions, households_of=held)[0].is_candidate)

    def test_without_the_rolls_no_household_separates_anyone(self):
        """No `households_of`, no evidence: the guard stays silent rather than
        guessing households from res_names."""
        a = "_1850_10_01_anastasija_vasilevna_rs_7_5_family_member"
        b = "_1850_10_01_anastasija_vasilevna_rs_7_6_family_member"
        prof = {a: _profile(a, "Настасья", born=1834), b: _profile(b, "Настасья", born=1835)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={a, b})}
        self.assertTrue(_find(prof, unions)[0].is_candidate)

    def test_undated_pair_stays_a_candidate(self):
        """No dates means no grounds to retire — leave it for a human."""
        prof = {"a": _profile("a", "Домна"), "b": _profile("b", "Домна")}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertTrue(_find(prof, unions)[0].is_candidate)


def _lives(**held: ud.Lives):
    """`lives_of` for a test: canonical → what its records say of its life."""
    def of(canon: str) -> ud.Lives:
        return held.get(canon, ud.Lives())
    return of


def _baptism(key: str, y: int, m: int, d: int) -> Baptism:
    return (key, (y, m, d), (y, m, d), f"{key}, р. {d:02}.{m:02}.{y}")


class RecordsSeparate(unittest.TestCase):
    """What the records say beyond the dates: two christenings, or a life
    seen after a death (`verso.ru.facts.checks.lives.lives_of_canonicals`)."""

    def _pair(self, born_a, born_b, died_a=None, died_b=None):
        prof = {"a": _profile("a", "Агриппина", born=born_a, died=died_a),
                "b": _profile("b", "Агриппина", born=born_b, died=died_b)}
        return prof, {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}

    def test_two_own_baptisms_are_two_children(self):
        """Two entries a year apart: the dates keep them a candidate; one
        entry is one christening, so they are two."""
        prof, unions = self._pair(1861, 1862)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(baptisms=frozenset({_baptism("1861#12", 1861, 3, 14)})),
            b=ud.Lives(baptisms=frozenset({_baptism("1862#34", 1862, 2, 25)}))))
        self.assertEqual(found[0].verdict, ud.VERDICT_TWO_BAPTISMS)
        self.assertIn("1861#12", found[0].reason)

    def test_one_birth_copied_twice_proves_nothing(self):
        """Two entries on one day are one birth written twice, not two."""
        prof, unions = self._pair(1861, 1861)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(baptisms=frozenset({_baptism("births#12", 1861, 3, 14)})),
            b=ud.Lives(baptisms=frozenset({_baptism("other#3", 1861, 3, 14)}))))
        self.assertTrue(found[0].is_candidate)

    def test_one_baptism_alone_separates_nobody(self):
        prof, unions = self._pair(1861, 1862)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(baptisms=frozenset({_baptism("1861#12", 1861, 3, 14)}))))
        self.assertTrue(found[0].is_candidate)

    def test_a_life_after_the_other_death_is_two_people(self):
        """A man died 14.10.1825; his namesake is counted alive in a roll of
        the next year. Same birth year, so the dates saw nothing."""
        prof, unions = self._pair(1825, 1825, died_a=1825, died_b=1844)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(died_by=frozenset({((1825, 10, 14), "умер(ла) 14.10.1825")})),
            b=ud.Lives(alive_at=frozenset({((1826, 6, 1), "жив(а) 01.06.1826")}))))
        self.assertEqual(found[0].verdict, ud.VERDICT_ALIVE_AFTER_DEATH)
        self.assertIn("14.10.1825", found[0].reason)
        self.assertIn("01.06.1826", found[0].reason)

    def test_a_life_before_the_death_separates_nobody(self):
        prof, unions = self._pair(1815, 1815)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(died_by=frozenset({((1815, 9, 7), "умер(ла)")})),
            b=ud.Lives(alive_at=frozenset({((1815, 3, 1), "жив(а)")}))))
        self.assertTrue(found[0].is_candidate)

    def test_the_older_guards_keep_their_verdict(self):
        """The records' guards come after the dates', so a pair the dates
        already retired keeps its reason."""
        prof, unions = self._pair(1850, 1856, died_a=1852)
        found = _find(prof, unions, lives_of=_lives(
            a=ud.Lives(died_by=frozenset({((1852, 1, 1), "умер(ла)")})),
            b=ud.Lives(alive_at=frozenset({((1856, 1, 1), "родился(ась)")}))))
        self.assertEqual(found[0].verdict, ud.VERDICT_REUSED_NAME)

    def test_without_the_records_nothing_is_separated(self):
        prof, unions = self._pair(1864, 1865)
        self.assertTrue(_find(prof, unions)[0].is_candidate)


class ReadableDate(unittest.TestCase):
    def test_a_full_date(self):
        self.assertEqual("01.10.1850", ud._readable("1850-10-01"))

    def test_a_roll_dated_to_the_month_or_the_year(self):
        self.assertEqual("02.1834", ud._readable("1834-02-00"))
        self.assertEqual("1719", ud._readable("1719-00-00"))

    def test_anything_else_is_left_alone(self):
        self.assertEqual("1850_10_01", ud._readable("1850_10_01"))


class Output(unittest.TestCase):
    def _found(self):
        prof = {"a": _profile("a", "Степан", born=1841),
                "b": _profile("b", "Степан", born=1841, died=1900)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        return _find(prof, unions)

    def test_report_names_the_candidate(self):
        text = ud.format_report(self._found())
        self.assertIn("Степан", text)
        self.assertIn("1 кандидат", text)

    def test_report_says_signal_not_verdict(self):
        self.assertIn("СИГНАЛ", ud.format_report(self._found()))

    def test_report_without_candidates(self):
        prof = {"a": _profile("a", "Фока", born=1835, died=1836),
                "b": _profile("b", "Фока", born=1839)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        self.assertIn("Кандидатов нет", ud.format_report(_find(prof, unions)))

    def test_all_shows_the_retired_groups_with_their_reason(self):
        """`--all` was accepted and ignored: `run` computed the groups to show
        and printed the candidates anyway, so the one question a reader asks of
        a retired pair — why was it let go — needed JSON to answer."""
        a = "_1850_10_01_anastasija_vasilevna_rs_7_5_family_member"
        b = "_1850_10_01_anastasija_vasilevna_rs_7_6_family_member"
        prof = {a: _profile(a, "Настасья", born=1834), b: _profile(b, "Настасья", born=1835)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={a, b})}
        seven = ("1850-10-01", "7", "rs_1850.py")
        held = _counted(**{a: {seven}, b: {seven}})
        plain, _ = ud.run(prof, unions, lambda r: r, sibling_gap=2,
                          as_json=False, all_groups=False, households_of=held)
        every, _ = ud.run(prof, unions, lambda r: r, sibling_gap=2,
                          as_json=False, all_groups=True, households_of=held)
        self.assertNotIn(ud.VERDICT_SAME_HOUSEHOLD, plain)
        self.assertNotIn("двора 7", plain)
        self.assertIn(f"[{ud.VERDICT_SAME_HOUSEHOLD}]", every)
        self.assertIn("двора 7", every)
        self.assertTrue(every.startswith(plain))

    def test_json_round_trips(self):
        payload = _json.loads(ud.findings_to_json(self._found()))
        self.assertEqual(payload[0]["given_name"], "Степан")
        self.assertEqual(payload[0]["verdict"], ud.VERDICT_CANDIDATE)
        self.assertEqual(payload[0]["members"][1]["death_year"], 1900)

    def test_exit_code_is_1_when_a_candidate_exists(self):
        prof = {"a": _profile("a", "Степан", born=1841),
                "b": _profile("b", "Степан", born=1841)}
        unions = {"u": GeniUnion(res_name="u", partner_1="dad", children={"a", "b"})}
        _, code = ud.run(prof, unions, lambda r: r, sibling_gap=2,
                         as_json=False, all_groups=False)
        self.assertEqual(code, 1)

    def test_exit_code_is_0_when_clean(self):
        _, code = ud.run({}, {}, lambda r: r, sibling_gap=2,
                         as_json=False, all_groups=False)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
