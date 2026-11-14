import ast
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.census_age as check

HOME = "Нижняя Яичница"


def _census(*members: str, year: int = 1857) -> str:
    inner = ",\n".join(members)
    return (f'census_records("a", "f", "i", "d", "{HOME}", {year},\n'
            f'  household(\n{inner},\n    family_id="1"))\n')


def _collect(*members: str, year: int = 1857):
    src = _census(*members, year=year)
    return check._collect(ast.parse(src), src.splitlines())


class TestBirthDayWithoutYear(unittest.TestCase):
    def test_lone_birth_day_on_adult_flagged(self):
        # the lone-birth-day trap: birth_day with no birth_year pins birth to the
        # census year, contradicting a 43-year age
        issues = _collect(
            'member(7, person("Евстигней", "Лукинъ"), CensusRole.BROTHER, '
            'age="41 год 10 мес", birth_day=9, ref_member=1)')
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("CAI001", msg)
        self.assertIn("birth_year", msg)
        self.assertIn("1816", msg)   # 1857 - 41

    def test_birth_month_without_year_on_adult_flagged(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age="40 лет", birth_month=Month.MAY)')
        self.assertEqual(len(issues), 1, issues)

    def test_full_birth_date_on_infant_ok(self):
        # infants carry birth_year too → consistent, no flag
        issues = _collect(
            'member(5, person("Семенъ"), CensusRole.SON, age="1 год 1 мес", '
            'birth_day=8, birth_month=Month.OCTOBER, birth_year=1856, ref_member=3)')
        self.assertEqual(issues, [])

    def test_birth_day_on_infant_without_year_not_flagged(self):
        # age < 2 yrs → could be a census-year birth, tolerated
        issues = _collect(
            'member(9, person("Тимоѳей"), CensusRole.SON, age="6 мес", birth_day=13)')
        self.assertEqual(issues, [])


class TestNoFalsePositives(unittest.TestCase):
    def test_plain_age_no_birth_fields_ok(self):
        issues = _collect(
            'member(1, person("Пахомъ", "Лукинъ"), CensusRole.HEAD, age="57 лет 2 мес")')
        self.assertEqual(issues, [])

    def test_explicit_birth_year_never_flagged(self):
        # a deceased member aged at a prior revision: birth_year disagrees with
        # census_year - age, but that is NOT cross-checked (would false-positive)
        issues = _collect(
            'member(1, person("Никон"), CensusRole.HEAD, age=52, '
            'departure_reason="умер", departure_year=1783, birth_year=1729)')
        # CAI004 does fire here (a deceased member has no current age), so assert
        # on the check under test rather than on an empty list.
        self.assertEqual([i for i in issues if "CAI001" in str(i["message"])], [])

    def test_unparseable_age_skipped(self):
        # ages.py owns malformed ages; census_age stays silent
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age="junk", birth_day=6)')
        self.assertEqual(issues, [])

    def test_missing_census_year_still_does_rule_a(self):
        # no parseable year → rule (b) can't run, but rule (a) is context-free
        src = (f'census_records("a", "f", "i", "d", "{HOME}", YEAR,\n'
               '  household(member(1, person("Икс"), CensusRole.HEAD, age="40 лет", '
               'birth_day=6), family_id="1"))\n')
        issues = check._collect(ast.parse(src))
        self.assertEqual(len(issues), 1, issues)


class TestCai002Flags(unittest.TestCase):
    def test_int_ages_off_flagged(self):
        # 1850 census, prev revision 1834 (gap 16): 40 - 12 = 28 → deviation 12
        issues = _collect(
            'member(4, person("Григорій"), CensusRole.SON, age=40, previous_age=12)',
            year=1850)
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("CAI002", msg)
        self.assertIn("28", msg)    # the observed difference
        self.assertIn("16", msg)    # the revision gap
        self.assertIn("1834", msg)  # the previous revision year

    def test_deviation_exactly_two_flagged(self):
        # boundary: 24 - 6 = 18 vs gap 16 → deviation 2, first flagged value
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=24, previous_age=6)',
            year=1850)
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI002", str(issues[0]["message"]))

    def test_string_ages_flagged(self):
        # 43 - 14 = 29 vs gap 7 (1857 → 1850) → deviation 22
        issues = _collect(
            'member(2, person("Иванъ"), CensusRole.SON, age="43 года 11 мес", '
            'previous_age="14 лет 4 мес")')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI002", str(issues[0]["message"]))

    def test_comment_marker_previous_age_flagged(self):
        # no typed kwarg; the прошлая РС comment carries the prior age
        issues = _collect(
            'member(3, person("Петръ"), CensusRole.SON, age=17, '
            'comment="прошлая РС: 30 лет")',
            year=1850)
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("CAI002", msg)
        self.assertIn("comment", msg)

    def test_check_file_round_trip(self):
        src = _census(
            'member(4, person("Григорій"), CensusRole.SON, age=40, previous_age=12)',
            year=1850)
        with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(src)
            path = Path(f.name)
        try:
            plain = check.check_file(path)
            self.assertEqual(len(plain), 1, plain)
            self.assertIn("[CAI002]", plain[0])
            structured = check.check_file_structured(path)
            self.assertEqual(len(structured), 1, structured)
            self.assertEqual(structured[0]["level"], "warn")
            self.assertIn("[CAI002]", str(structured[0]["message"]))
        finally:
            path.unlink()


class TestCai002Passes(unittest.TestCase):
    def test_exact_gap_passes(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=24)',
            year=1850)
        self.assertEqual(issues, [])

    def test_plus_one_drift_passes(self):
        # mid-year survey dates drift +1 in ~half the real 1850 records
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=41, previous_age=24)',
            year=1850)
        self.assertEqual(issues, [])

    def test_minus_one_drift_passes(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=39, previous_age=24)',
            year=1850)
        self.assertEqual(issues, [])

    def test_subyear_previous_age_passes(self):
        # a prev-revision infant: "5 нед" → 0 whole years; 17 - 0 vs gap 16 → dev 1
        issues = _collect(
            'member(3, person("Яков"), CensusRole.SON, age=17, previous_age="3 нед")',
            year=1850)
        self.assertEqual(issues, [])

    def test_bare_fractional_string_age_passes(self):
        # real Маниловка 1858 form: age="34.5" → 34; 34 - 27 = 7 vs gap 8 → dev 1
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age="34.5", previous_age=27)',
            year=1858)
        self.assertEqual(issues, [])


class TestCai002Skips(unittest.TestCase):
    def test_repeat_convention_skipped(self):
        # scribe wrote the prior age in both columns (deceased/absent members)
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=65, previous_age=65)',
            year=1850)
        self.assertEqual(issues, [])

    def test_repeat_convention_is_source_string_comparison(self):
        # mirrors the generator's str(prev) == str(age) compression check
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age="65", previous_age=65)',
            year=1850)
        self.assertEqual(issues, [])

    def test_departed_member_skipped(self):
        # departed members are aged at the revision they last appeared in
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=12, '
            'departure_year=1840)',
            year=1850)
        self.assertEqual(issues, [])

    def test_departure_reason_only_skipped(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=12, '
            'departure_reason="умер")',
            year=1850)
        # CAI004 fires on the same fixture (deceased + age=); this test owns the
        # CAI002 skip only.
        self.assertEqual([i for i in issues if "CAI002" in str(i["message"])], [])

    def test_hidden_member_skipped(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=12, '
            'hidden=True)',
            year=1850)
        self.assertEqual(issues, [])

    def test_missing_previous_age_skipped(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40)',
            year=1850)
        self.assertEqual(issues, [])

    def test_unparseable_previous_age_skipped(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age="?")',
            year=1850)
        self.assertEqual(issues, [])

    def test_unparseable_age_skipped(self):
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age="junk", previous_age=12)',
            year=1850)
        self.assertEqual(issues, [])

    def test_unknown_census_year_skipped(self):
        # 1897 is not a revision census — no prev-revision year to compare against
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=12)',
            year=1897)
        self.assertEqual(issues, [])

    def test_non_literal_census_year_skipped(self):
        src = (f'census_records("a", "f", "i", "d", "{HOME}", YEAR,\n'
               '  household(member(1, person("Икс"), CensusRole.HEAD, age=40, '
               'previous_age=12), family_id="1"))\n')
        self.assertEqual(check._collect(ast.parse(src)), [])

    def test_arrival_member_still_checked(self):
        # revisions were synchronized empire-wide, so an arrived member's
        # prior-RS age uses the same reference year — no skip
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=12, '
            'arrival_year=1848, arrival_reason="переведен")',
            year=1850)
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI002", str(issues[0]["message"]))

    def test_comment_marker_ignored_when_kwarg_present(self):
        # typed kwarg wins over the comment marker (resolver precedence)
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=40, previous_age=24, '
            'comment="прошлая РС: 90 лет")',
            year=1850)
        self.assertEqual(issues, [])

    def test_comment_marker_fractional_payload(self):
        # "0.5 лет" must parse as 0 whole years, not 5 (the translator's
        # latent \d+ mis-parse is not reproduced here)
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=16, '
            'comment="прошлая РС: 0.5 лет")',
            year=1850)
        self.assertEqual(issues, [])

    def test_comment_marker_subyear_payload(self):
        # real corpus form "прошлая РС: 2 мес лет" → 0 whole years
        issues = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=17, '
            'comment="прошлая РС: 2 мес лет")',
            year=1850)
        self.assertEqual(issues, [])


class TestCai002RevisionTable(unittest.TestCase):
    def test_overlay_1857_resolves(self):
        # Нижняя Яичница 1857 → prev 1850 (gap 7): values 21/14 pass
        issues = _collect(
            'member(14, person("Алексѣй"), CensusRole.SON, age="22 года 1 мес", '
            'previous_age="14 лет 8 мес")',
            year=1857)
        self.assertEqual(issues, [])
        flagged = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=30, previous_age=10)',
            year=1857)
        self.assertEqual(len(flagged), 1, flagged)
        msg = str(flagged[0]["message"])
        self.assertIn("1850", msg)

    def test_overlay_1815_uses_1811(self):
        # the 1815 file's column references the 1811 (6th) revision, not the
        # translator table's 1795: real values 55/51 (diff 4 = gap) pass
        issues = _collect(
            'member(1, person("Степан", "Кузьмин"), CensusRole.HEAD, '
            'age=56, previous_age=52)',
            year=1815)
        self.assertEqual(issues, [])

    def test_translator_table_year(self):
        # 1795 → 1782 (gap 13): real corpus values
        issues = _collect(
            'member(3, person("Савва"), CensusRole.SON, age=55, previous_age=42)',
            year=1795)
        self.assertEqual(issues, [])
        flagged = _collect(
            'member(1, person("Икс"), CensusRole.HEAD, age=69, previous_age=53)',
            year=1795)
        self.assertEqual(len(flagged), 1, flagged)


class TestCai002Interaction(unittest.TestCase):
    def test_cai001_and_cai002_both_fire_same_member(self):
        issues = _collect(
            'member(4, person("Григорій"), CensusRole.SON, age=40, '
            'previous_age=12, birth_day=6)',
            year=1850)
        self.assertEqual(len(issues), 2, issues)
        msgs = sorted(str(i["message"]) for i in issues)
        self.assertIn("CAI001", msgs[0])
        self.assertIn("CAI002", msgs[1])
        self.assertEqual(issues[0]["line"], issues[1]["line"])


if __name__ == "__main__":
    unittest.main()


class HighlightRange(unittest.TestCase):
    """The issue must pin the offending kwarg so IDE plugins can narrow the
    highlight. Without issue-level col/end_col the IntelliJ annotator falls
    back to highlighting the WHOLE line (DslLintAnnotator.narrowRange)."""

    def _one(self, *members: str, year: int = 1857):
        issues = _collect(*members, year=year)
        self.assertEqual(len(issues), 1, issues)
        return issues[0]

    def test_cai002_pins_the_age_kwarg(self):
        member = ('member(3, person("Михаил"), CensusRole.SON, ref_member=2, '
                  'age=26, previous_age=8)')
        issue = self._one(member, year=1850)
        self.assertIn("col", issue, "CAI002 must carry a highlight range")
        src = _census(member, year=1850).splitlines()
        line = src[int(issue["line"]) - 1]
        self.assertEqual(line[int(issue["col"]):int(issue["end_col"])], "age=26")

    def test_cai002_range_survives_cyrillic_on_the_line(self):
        # AST col_offsets are UTF-8 BYTE offsets; the Cyrillic name ahead of the
        # kwarg makes a raw byte offset overshoot the character column.
        member = ('member(9, person("Пелагея", "Никифоровна"), CensusRole.DAUGHTER, '
                  'age=40, previous_age=12)')
        issue = self._one(member, year=1850)
        src = _census(member, year=1850).splitlines()
        line = src[int(issue["line"]) - 1]
        self.assertEqual(line[int(issue["col"]):int(issue["end_col"])], "age=40")

    def test_structured_output_exposes_the_range(self):
        member = ('member(3, person("Михаил"), CensusRole.SON, age=26, previous_age=8)')
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "census_1850.py"
            f.write_text(_census(member, year=1850), encoding="utf-8")
            out = check.check_file_structured(f)
        self.assertEqual(len(out), 1, out)
        self.assertIn("col", out[0])
        self.assertIn("end_col", out[0])


class TestAgeZeroSentinel(unittest.TestCase):
    """CAI003: `age=0` is read literally by the translator, so a head whose age
    the source omitted becomes a newborn — and children referencing him end up
    older than their own father."""

    def test_age_zero_flagged(self):
        issues = _collect(
            'member(7, person("Тимофей", "Ильин"), CensusRole.COUSIN, '
            'age=0, comment="возраст не указан")', year=1719)
        cai3 = [i for i in issues if "CAI003" in str(i["message"])]
        self.assertEqual(len(cai3), 1, issues)
        self.assertIn("omit age=", str(cai3[0]["message"]))

    def test_age_zero_flagged_positionally(self):
        # `age` is the 5th positional parameter of member(); the sentinel must be
        # caught whichever way it was written.
        issues = _collect(
            'member(7, person("Тимофей"), CensusRole.SON, 1, 0)', year=1719)
        self.assertEqual(len([i for i in issues if "CAI003" in str(i["message"])]), 1, issues)

    def test_omitted_age_is_clean(self):
        # The recommended encoding: no age at all, which the translator treats as
        # unknown and emits no birth event for.
        issues = _collect(
            'member(7, person("Тимофей", "Ильин"), CensusRole.COUSIN, '
            'comment="возраст не указан")', year=1719)
        self.assertEqual([i for i in issues if "CAI003" in str(i["message"])], [])

    def test_real_age_is_clean(self):
        issues = _collect(
            'member(1, person("Фома", "Ильин"), CensusRole.HEAD, age=9)', year=1719)
        self.assertEqual([i for i in issues if "CAI003" in str(i["message"])], [])

    def test_sub_year_age_string_is_clean(self):
        # A genuine infant is spelled out rather than encoded as 0.
        issues = _collect(
            'member(5, person("Матвей"), CensusRole.SON, ref_member=1, age="полгода")',
            year=1719)
        self.assertEqual([i for i in issues if "CAI003" in str(i["message"])], [])


class TestCAI004DeceasedAge(unittest.TestCase):
    """CAI004: a member who died before the revision has no current-revision age.

    The «лета по нынешней ревизии» column is empty for them, so `age=` states
    something the source does not. The importer used to compress the prior age
    into BOTH columns (the generator documents this as
    `prev_age_compresses_current`), which is where the 405 removed occurrences
    came from. `previous_age` is the field that carries the value.

    The rule keys on DEATH, not on `age == previous_age`: alive departures
    («в острог», «выдана замуж», «уволен с должности») legitimately carry a
    current age, and a deceased member with an age but no `previous_age` — which
    the equality rule would miss — is exactly the case worth flagging.
    """

    def test_deceased_with_age_flagged(self):
        issues = _collect(
            'member(2, person("Лукьян", "Семенов"), CensusRole.BROTHER, age=33, '
            'previous_age=33, departure_year=1784, departure_reason="умер")')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI004", str(issues[0]["message"]))

    def test_deceased_with_age_but_no_previous_age_flagged(self):
        """The equality rule would miss this one; it is the worse case."""
        issues = _collect(
            'member(3, person("Егоръ"), CensusRole.SON, age=13, '
            'departure_year=1851, departure_reason="умер")')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI004", str(issues[0]["message"]))

    def test_deceased_without_age_is_clean(self):
        issues = _collect(
            'member(2, person("Лукьян", "Семенов"), CensusRole.BROTHER, '
            'previous_age=33, departure_year=1784, departure_reason="умер")')
        self.assertEqual(issues, [])

    def test_explicit_age_none_is_clean(self):
        issues = _collect(
            'member(3, person("Ѳома"), CensusRole.SON, age=None, previous_age=2, '
            'departure_year=1852, departure_reason="умер")')
        self.assertEqual(issues, [])

    def test_alive_departure_keeps_its_age(self):
        """«в острог» / «уволен» leave a person still enumerated in this
        household, whose current age the revision does record. NB «выдана
        замуж» is NOT among them — she leaves the household, so her row's
        current-age column is blank (see TestMarriedOutGirls)."""
        for reason in ("в острог", "уволен с должности диакона"):
            with self.subTest(reason=reason):
                issues = _collect(
                    f'member(12, person("Катерина"), CensusRole.DAUGHTER, age=15, '
                    f'previous_age=2, departure_reason="{reason}")')
                self.assertEqual(issues, [], f"{reason}: {issues}")

    def test_living_member_untouched(self):
        # 1795 against the 1782 revision: 22 - 9 == the 13-year gap, so CAI002
        # is silent too and any finding here would be CAI004 misfiring.
        issues = _collect(
            'member(5, person("Прохор", "Гаврилов"), CensusRole.SON, age=23, previous_age=10)',
            year=1795)
        self.assertEqual(issues, [])


class TestCAI005DeceasedBirthYear(unittest.TestCase):
    """CAI005: an explicit `birth_year=` on a member who died before the revision.

    The сказка gives no birth year — only the prior-revision age and the year of
    death. An explicit `birth_year` is therefore somebody's arithmetic presented
    as source data, and it outranks `previous_age` in the generator's birth
    estimate (step 2 vs step 3), so it also suppresses the honest two-year
    window: dropping it turned `circa 1735` into `between circa 1735 and circa
    1736` across the corpus.

    Sibling of CAI004 and deliberately a separate code: the two pin different
    kwarg ranges, so an editor can offer the right fix for each.
    """

    def test_deceased_with_birth_year_flagged(self):
        issues = _collect(
            'member(2, person("Лукьян", "Семенов"), CensusRole.BROTHER, '
            'previous_age=33, departure_year=1784, departure_reason="умер", birth_year=1748)')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("CAI005", str(issues[0]["message"]))

    def test_deceased_without_birth_year_is_clean(self):
        issues = _collect(
            'member(2, person("Лукьян", "Семенов"), CensusRole.BROTHER, '
            'previous_age=33, departure_year=1784, departure_reason="умер")')
        self.assertEqual(issues, [])

    def test_birth_year_with_explicit_day_is_kept(self):
        """A real recorded birth DATE is source data, not arithmetic."""
        issues = _collect(
            'member(2, person("Пётр"), CensusRole.SON, previous_age=3, '
            'departure_year=1849, departure_reason="умер", '
            'birth_day=6, birth_month=Month.MAY, birth_year=1846)')
        self.assertEqual([i for i in issues if "CAI005" in str(i["message"])], [])

    def test_living_member_keeps_birth_year(self):
        issues = _collect(
            'member(5, person("Прохор"), CensusRole.SON, age=23, previous_age=10, '
            'birth_year=1772)',
            year=1795)
        self.assertEqual(issues, [])

    def test_alive_departure_keeps_birth_year(self):
        issues = _collect(
            'member(12, person("Дмитрий"), CensusRole.SON, age=50, '
            'previous_age=34, departure_reason="уволен с должности диакона", '
            'birth_year=1761)')
        self.assertEqual(issues, [])

    def test_range_pins_the_birth_year_kwarg_only(self):
        """Like CAI004, the finding carries col/end_col so an IDE highlights the
        field rather than the whole line (which is what CPL003 does today)."""
        issues = _collect(
            'member(2, person("Лукьян"), CensusRole.BROTHER, previous_age=33, '
            'departure_year=1784, departure_reason="умер", birth_year=1748)')
        f = issues[0]
        self.assertIn("col", f)
        self.assertIn("end_col", f)


class TestMarriedOutGirls(unittest.TestCase):
    """CAI004/CAI005 also cover a girl «выдана замуж» into ANOTHER village.

    She left the parish before the revision, so the «лета по нынешней ревизии»
    column is as blank for her as for someone who died — same compression
    signature in the corpus (29 of 40 carry age == previous_age, and all 29 also
    carry a derived birth_year).

    The trigger is «замуж» alone. A `destination` is irrelevant: the blank
    column belongs to her NATAL row, and she left that household either way.
    """

    ULYANA = ('member(31, person("Ульяна"), CensusRole.DAUGHTER, ref_member=3, age=17, '
             'previous_age=17, destination="Пепелищи", departure_reason="выдана замуж", '
             'birth_year=1766)')

    def _of(self, issues, code):
        return [i for i in issues if code in str(i["message"])]

    def test_married_out_age_flagged(self):
        issues = _collect(self.ULYANA)
        self.assertEqual(len(self._of(issues, "CAI004")), 1, issues)

    def test_married_out_birth_year_flagged(self):
        issues = _collect(self.ULYANA)
        self.assertEqual(len(self._of(issues, "CAI005")), 1, issues)

    def test_married_out_clean_when_both_absent(self):
        issues = _collect(
            'member(31, person("Ульяна"), CensusRole.DAUGHTER, ref_member=3, '
            'previous_age=17, destination="Пепелищи", departure_reason="выдана замуж")')
        self.assertEqual(issues, [])

    def test_married_within_the_village_is_flagged_too(self):
        """`destination` is NOT the discriminator — she left the HOUSEHOLD, and
        it is her natal row's current-age column that stays blank. All 26 such
        brides in the corpus carry age == previous_age and a birth_year, without
        a single exception; the one bride whose ages DO differ has a destination,
        the opposite of what a «stayed local» rule would predict."""
        issues = _collect(
            'member(35, person("Елена"), CensusRole.DAUGHTER, ref_member=3, age=13, '
            'previous_age=13, departure_reason="выдана замуж", birth_year=1768, '
            'comment="выдана в замужество в том же селе за ясачного")')
        self.assertEqual(len(self._of(issues, "CAI004")), 1, issues)
        self.assertEqual(len(self._of(issues, "CAI005")), 1, issues)

    def test_message_names_the_departure_not_death(self):
        """The wording must not tell a living bride she «died before the revision»."""
        issues = _collect(self.ULYANA)
        msg = str(self._of(issues, "CAI004")[0]["message"])
        self.assertNotIn("died", msg)
        self.assertIn("left the parish", msg)


class TestNegativeMemberNumber(unittest.TestCase):
    """A hidden member numbered -1 parses as a negated literal; the message must
    still name it by its number, not as «member None»."""

    def test_message_names_a_negative_number(self):
        issues = _collect(
            'member(-1, person("Тимофей"), CensusRole.SON, ref_member=1, age=0, '
            'hidden=True)', year=1719)
        cai3 = [str(i["message"]) for i in issues if "CAI003" in str(i["message"])]
        self.assertEqual(len(cai3), 1, issues)
        self.assertIn("member -1 (Тимофей)", cai3[0])
