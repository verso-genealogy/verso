import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import verso.ru.linters.checks.census_status_redundancy as check


def _census(members: str, *, defaults: str | None = None) -> str:
    """Wrap census members in a `census_records(...)` with an optional
    `defaults=RecordDefaults(...)` block. The checker only parses (never
    executes) the DSL, so status/name constants need not be real imports."""
    defaults_line = f"    defaults=RecordDefaults({defaults}),\n" if defaults else ""
    return (
        "from verso.ru.dsl import CensusRole, census_records, household, member\n"
        "from verso.ru.dsl import RecordDefaults, person\n"
        "rs = census_records(\n"
        '    "ГАВО", "431", "1", "100", "Нижняя Яичница", 1897,\n'
        "    household(\n"
        f"{members}\n"
        "    ),\n"
        f"{defaults_line}"
        ")\n"
    )


_MF = "status_male=KAZ_MALE, status_female=KAZ_FEMALE"


class _Harness(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, Any]]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()


class TestFlagged(_Harness):
    def test_male_status_matches_default_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("redundant status=KAZ_MALE" in e and "status_male" in e for e in errs), errs)

    def test_female_status_matches_default_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),\n'
            '        member(2, person("Марья", status=KAZ_FEMALE), CensusRole.WIFE, age=40),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("redundant status=KAZ_FEMALE" in e and "status_female" in e for e in errs), errs)

    def test_female_falls_back_to_status_male_when_no_status_female(self):
        # apply_to_person: FEMALE with status_female unset → gets status_male.
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),\n'
            '        member(2, person("Марья", status=KAZ_MALE), CensusRole.WIFE, age=40),',
            defaults="status_male=KAZ_MALE",
        ))
        self.assertTrue(
            any("redundant status=KAZ_MALE" in e and "status_female" not in e
                and ".py:" in e for e in errs), errs)
        # Both the head and the wife repeat status_male → two findings.
        self.assertEqual(sum("redundant status=KAZ_MALE" in e for e in errs), 2, errs)

    def test_status_via_alias_constant_flagged(self):
        # Same token used in defaults and on the member — byte-neutral removal.
        errs = self._check(_census(
            '        member(1, person("Иван", status=M), CensusRole.HEAD, age=45),',
            defaults="status_male=M, status_female=F",
        ))
        self.assertTrue(any("redundant status=M" in e for e in errs), errs)


class TestNotFlagged(_Harness):
    def test_divergent_status_not_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван", status=SOLDIER_MALE), CensusRole.HEAD, age=45),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_no_explicit_status_not_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван"), CensusRole.HEAD, age=45),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_no_defaults_block_not_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),',
        ))
        self.assertEqual(errs, [], errs)

    def test_hidden_member_not_flagged(self):
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),\n'
            '        member(7, person("Бурмяй", status=KAZ_MALE), None, age="?", hidden=True),',
            defaults=_MF,
        ))
        # Head is still flagged; the hidden member is not.
        self.assertEqual(sum("redundant status=KAZ_MALE" in e for e in errs), 1, errs)

    def test_ambiguous_gender_not_flagged(self):
        # role=None + a name the gender heuristic can't resolve → status could be
        # load-bearing for gender inference, so removal isn't provably neutral.
        errs = self._check(_census(
            '        member(1, person("Бурмяй", status=KAZ_MALE), None, age="?"),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_alias_mismatch_not_flagged(self):
        # Member uses the underlying constant, default uses an alias name — we
        # can't prove they're the same object statically, so we don't flag.
        errs = self._check(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),',
            defaults="status_male=M, status_female=F",
        ))
        self.assertEqual(errs, [], errs)


class TestFix(_Harness):
    def test_kwarg_status_remove_fix(self):
        issues = self._structured(_census(
            '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),',
            defaults=_MF,
        ))
        flagged = [i for i in issues if "redundant status" in cast(str, i["message"])]
        self.assertEqual(len(flagged), 1, issues)
        fix = cast(dict[str, Any], flagged[0]["fix"])
        self.assertEqual(fix["type"], "remove_kwarg")
        self.assertEqual(fix["kwarg"], "status")
        self.assertIn("col", fix)
        self.assertEqual(flagged[0]["level"], "error")

    def test_fix_col_points_at_status_kwarg(self):
        line = '        member(1, person("Иван", status=KAZ_MALE), CensusRole.HEAD, age=45),'
        issues = self._structured(_census(line, defaults=_MF))
        flagged = [i for i in issues if "redundant status" in cast(str, i["message"])]
        fix = cast(dict[str, Any], flagged[0]["fix"])
        self.assertEqual(line[fix["col"]:fix["col"] + len("status=")], "status=")


if __name__ == "__main__":
    unittest.main()
