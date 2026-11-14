from __future__ import annotations
import unittest
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.consolidation import date_order as do
import json as _json


def _prof(res_name, *, birth=None, baptism=None, death=None, burial=None):
    def ev(t):
        if t is None:
            return None
        y, m, d = t
        return GeniEvent(date=GeniDate(year=y, month=m, day=d))
    return GeniProfile(res_name=res_name, first_name=res_name,
                       birth=ev(birth), baptism=ev(baptism),
                       death=ev(death), burial=ev(burial))


def _d(y, m=None, d=None):
    return GeniDate(year=y, month=m, day=d)


class DefinitelyBefore(unittest.TestCase):
    def test_year_before(self):
        self.assertTrue(do.definitely_before(_d(1912), _d(1913)))

    def test_same_year_jan_before_dec(self):
        self.assertTrue(do.definitely_before(_d(1913, 1), _d(1913, 12)))

    def test_same_month_earlier_day(self):
        self.assertTrue(do.definitely_before(_d(1827, 10, 11), _d(1827, 10, 18)))

    def test_same_month_later_day_not_before(self):
        self.assertFalse(do.definitely_before(_d(1913, 1, 5), _d(1913, 1, 3)))

    def test_year_only_same_year_not_before(self):
        self.assertFalse(do.definitely_before(_d(1913), _d(1913)))

    def test_missing_year_not_before(self):
        self.assertFalse(do.definitely_before(_d(None, 1), _d(1913, 12)))
        self.assertFalse(do.definitely_before(None, _d(1913)))

    def test_dataclasses(self):
        v = do.OrderViolation(kind="baptism_before_birth", event="крещение",
                              event_date=(1913, 1, 1), reference="рождение",
                              reference_date=(1913, 12, 31))
        f = do.DateOrderConflict(res_name="p", name="P", violations=(v,))
        self.assertEqual(f.violations[0].kind, "baptism_before_birth")


class Detect(unittest.TestCase):
    def _find(self, profiles):
        return do.find_date_order_conflicts(profiles)

    def test_baptism_before_birth(self):
        p = _prof("indjushev", birth=(1913, 12, 31), baptism=(1913, 1, 1))
        found = self._find({"indjushev": p})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].violations[0].kind, "baptism_before_birth")
        self.assertEqual(found[0].violations[0].event_date, (1913, 1, 1))
        self.assertEqual(found[0].violations[0].reference_date, (1913, 12, 31))

    def test_baptism_after_birth_clean(self):
        p = _prof("ok", birth=(1913, 1, 3), baptism=(1913, 1, 5))
        self.assertEqual(self._find({"ok": p}), [])

    def test_death_before_birth(self):
        p = _prof("d", birth=(1850, 6, 1), death=(1849, 1, 1))
        found = self._find({"d": p})
        self.assertEqual(found[0].violations[0].kind, "death_before_birth")

    def test_burial_before_death_not_also_birth(self):
        p = _prof("b", birth=(1850, 1, 1), death=(1900, 6, 1), burial=(1900, 5, 1))
        found = self._find({"b": p})
        kinds = [v.kind for v in found[0].violations]
        self.assertEqual(kinds, ["burial_before_death"])

    def test_burial_before_birth_when_no_death(self):
        p = _prof("b", birth=(1900, 6, 1), burial=(1900, 1, 1))
        found = self._find({"b": p})
        self.assertEqual([v.kind for v in found[0].violations], ["burial_before_birth"])

    def test_year_only_same_year_clean(self):
        p = _prof("y", birth=(1913, None, None), baptism=(1913, None, None))
        self.assertEqual(self._find({"y": p}), [])

    def test_sorted_by_res_name(self):
        pa = _prof("bbb", birth=(1913, 12, 1), baptism=(1913, 1, 1))
        pb = _prof("aaa", birth=(1913, 12, 1), baptism=(1913, 1, 1))
        found = self._find({"bbb": pa, "aaa": pb})
        self.assertEqual([f.res_name for f in found], ["aaa", "bbb"])



class ReportAndRun(unittest.TestCase):
    def _one(self):
        return {"g": _prof("g", birth=(1913, 12, 31), baptism=(1913, 1, 1))}

    def test_report_mentions_dates_and_hint(self):
        out = do.format_report(do.find_date_order_conflicts(self._one()))
        self.assertIn("крещение", out)
        self.assertIn("1913", out)
        self.assertIn("k_year", out)

    def test_report_clean(self):
        self.assertIn("0", do.format_report([]))

    def test_json_shape(self):
        data = _json.loads(do.findings_to_json(do.find_date_order_conflicts(self._one())))
        self.assertEqual(data[0]["violations"][0]["kind"], "baptism_before_birth")
        self.assertEqual(data[0]["violations"][0]["event_date"], [1913, 1, 1])

    def test_run_exit(self):
        _text, code = do.run(self._one(), as_json=False)
        self.assertEqual(code, 1)
        _text2, code2 = do.run({"ok": _prof("ok", birth=(1913, 1, 1),
                                           baptism=(1913, 2, 1))}, as_json=False)
        self.assertEqual(code2, 0)


if __name__ == "__main__":
    unittest.main()


class SourceDateError(unittest.TestCase):
    """A record may declare that the SOURCE's own dates are inconsistent — a
    christening the scribe dated before the birth. The transcription is
    faithful, so the check acknowledges it instead of reporting it forever."""

    @staticmethod
    def _pelageja(reason=None):
        # Born 18 Oct, christened 11 Oct — as written.
        p = _prof("pelageja", birth=(1827, 10, 18), baptism=(1827, 10, 11))
        p.source_date_error = reason
        return p

    def test_flagged_profile_is_not_reported(self):
        self.assertEqual(
            do.find_date_order_conflicts({"pelageja": self._pelageja(
                "крещение записано раньше рождения — так в подлиннике")}),
            [])

    def test_same_profile_without_the_flag_is_reported(self):
        found = do.find_date_order_conflicts({"pelageja": self._pelageja()})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].violations[0].kind, "baptism_before_birth")

    def test_empty_reason_does_not_suppress(self):
        # An empty string is not an explanation; only a real reason silences it.
        found = do.find_date_order_conflicts({"pelageja": self._pelageja("")})
        self.assertEqual(len(found), 1)

    def test_flag_does_not_leak_into_terraform(self):
        block = self._pelageja("так в подлиннике").to_terraform()
        self.assertNotIn("source_date_error", block)


class SourceDateErrorSurvivesConsolidation(unittest.TestCase):
    """Folding the record into a canonical must not resurrect the finding."""

    def test_merge_carries_the_reason_over(self):
        from verso.ru.targets.geni.translator import TerraformGenerator

        canonical = _prof("canonical", birth=(1827, 10, 18))
        record = _prof("record", birth=(1827, 10, 18), baptism=(1827, 10, 11))
        record.source_date_error = "так в подлиннике"

        TerraformGenerator._merge_consolidated(canonical, record)
        self.assertEqual(canonical.source_date_error, "так в подлиннике")
        self.assertEqual(
            do.find_date_order_conflicts({"canonical": canonical}), [])

    def test_merge_does_not_invent_a_reason(self):
        from verso.ru.targets.geni.translator import TerraformGenerator

        canonical = _prof("canonical", birth=(1827, 10, 18))
        record = _prof("record", birth=(1827, 10, 18), baptism=(1827, 10, 11))

        TerraformGenerator._merge_consolidated(canonical, record)
        self.assertIsNone(canonical.source_date_error)
