import tempfile
import unittest
from pathlib import Path
from typing import Any

import verso.ru.linters.checks.status_redundancy as check


def _marriage(records: str, *, defaults: str | None = None) -> str:
    """Wrap `marriage()` calls in a `marriage_records(...)` with an optional
    `defaults=RecordDefaults(...)`. The checker only parses (never executes) the
    DSL, so status constants need not be real imports."""
    defaults_line = f"    defaults=RecordDefaults({defaults}),\n" if defaults else ""
    return (
        "from verso.ru.dsl import marriage, marriage_records\n"
        "from verso.ru.dsl import RecordDefaults, person\n"
        "from verso.ru.dsl import Relationship, relative\n"
        "mk = marriage_records(\n"
        '    "ЦГАРМ", "57", "6", "1", "Горюхино", "Николаевская", 1842,\n'
        f"{records}\n"
        f"{defaults_line}"
        ")\n"
    )


def _birth(records: str, *, defaults: str | None = None) -> str:
    defaults_line = f"    defaults=RecordDefaults({defaults}),\n" if defaults else ""
    return (
        "from verso.ru.dsl import birth, birth_month, birth_records\n"
        "from verso.ru.dsl import Gender, RecordDefaults, person\n"
        "from verso.ru.dsl import Relationship, relative\n"
        "mk = birth_records(\n"
        '    "ЦГАРМ", "57", "6", "1", "Горюхино", "Николаевская", 1842,\n'
        f"{records}\n"
        f"{defaults_line}"
        ")\n"
    )


def _death(records: str, *, defaults: str | None = None) -> str:
    defaults_line = f"    defaults=RecordDefaults({defaults}),\n" if defaults else ""
    return (
        "from verso.ru.dsl import death, death_records\n"
        "from verso.ru.dsl import Gender, RecordDefaults, person\n"
        "from verso.ru.dsl import Relationship, relative\n"
        "mk = death_records(\n"
        '    "ЦГАРМ", "57", "6", "1", "Горюхино", "Николаевская", 1842,\n'
        f"{records}\n"
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


class TestMarriageRelative(_Harness):
    def test_relative_status_matching_status_male_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             groom=person("Романъ", "Леонтьевъ"),\n'
            '             bride=person("Агафья", "Мартынова"),\n'
            '             relatives=[relative(person("Мартынъ", "Фоминъ", status=KAZ_MALE),\n'
            '                                 Relationship.FATHER, "невеста")]),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("[VSR001]" in e and "redundant status=KAZ_MALE" in e and "status_male" in e
                for e in errs), errs)


class TestBirthAndDeathVerbs(_Harness):
    def test_birth_relative_status_matching_status_male_is_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Тарасъ", "Ивановъ"),\n'
            '          relatives=[relative(person("Илья", "Абрамовъ", status=KAZ_MALE),\n'
            '                              Relationship.FATHER, "восприемника №2")]),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("[VSR001]" in e and "redundant status=KAZ_MALE" in e and "birth" in e
                for e in errs), errs)

    def test_death_relative_status_matching_status_male_is_flagged(self):
        errs = self._check(_death(
            "    death(1, Gender.FEMALE, 3, 5,\n"
            '          deceased=person("Марья", "Иванова"),\n'
            '          relatives=[relative(person("Тарасъ", "Ивановъ", status=KAZ_MALE),\n'
            '                              Relationship.HUSBAND, "умершая")]),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("[VSR001]" in e and "redundant status=KAZ_MALE" in e and "death" in e
                for e in errs), errs)


class TestSilent(_Harness):
    def test_divergent_status_is_not_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             relatives=[relative(person("Мартынъ", "Фоминъ", status=SOLDIER_MALE),\n'
            '                                 Relationship.FATHER, "невеста")]),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_no_explicit_status_is_not_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             relatives=[relative(person("Мартынъ", "Фоминъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_no_defaults_block_is_not_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             relatives=[relative(person("Мартынъ", "Фоминъ", status=KAZ_MALE),\n'
            '                                 Relationship.FATHER, "невеста")]),',
        ))
        self.assertEqual(errs, [], errs)

    def test_defaults_bound_by_name_are_read(self):
        """`defaults=DEFAULTS`, as every Глуповы Горы book writes it, hid 16
        redundant statuses until 2026-10-01."""
        src = _birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          father=person("Ѳедоръ", "Харитоновъ", status=TENTETNIKOV_M)),\n'
            "    defaults=DEFAULTS,",
        ).replace("mk = birth_records(",
                  "DEFAULTS = RecordDefaults(status_male=TENTETNIKOV_M, status_female=TENTETNIKOV_F)\n"
                  "mk = birth_records(")
        errs = self._check(src)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("redundant status=TENTETNIKOV_M", errs[0])


class TestMarriageSlots(_Harness):
    def test_groom_falls_back_to_status_male_when_no_status_groom(self):
        # RecordDefaults.__init__: status_groom defaults to status_male.
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             groom=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertTrue(any("redundant status=KAZ_MALE" in e for e in errs), errs)

    def test_groom_matching_status_groom_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             groom=person("Мартынъ", "Фоминъ", status=KAZ_GROOM)),',
            defaults=_MF + ", status_groom=KAZ_GROOM",
        ))
        self.assertTrue(
            any("redundant status=KAZ_GROOM" in e and "status_groom" in e for e in errs), errs)

    def test_groom_matching_status_male_is_silent_when_status_groom_differs(self):
        # apply_to_marriage assigns status_groom first, so status_male never
        # reaches the groom — an explicit status_male is NOT redundant.
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             groom=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF + ", status_groom=KAZ_GROOM",
        ))
        self.assertEqual(errs, [], errs)

    def test_bride_matching_status_bride_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             bride=person("Агафья", "Мартынова", status=KAZ_MAIDEN)),',
            defaults=_MF + ", status_bride=KAZ_MAIDEN",
        ))
        self.assertTrue(
            any("redundant status=KAZ_MAIDEN" in e and "status_bride" in e for e in errs), errs)

    def test_bride_falls_back_to_status_female_when_no_status_bride(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             bride=person("Агафья", "Мартынова", status=KAZ_FEMALE)),',
            defaults=_MF,
        ))
        self.assertTrue(
            any("redundant status=KAZ_FEMALE" in e and "status_female" in e for e in errs), errs)

    def test_witness_matching_status_male_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertTrue(any("redundant status=KAZ_MALE" in e for e in errs), errs)


class TestBirthSlots(_Harness):
    def test_father_and_godparents_are_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          father=person("Мартынъ", "Фоминъ", status=KAZ_MALE),\n'
            '          god_parent1=person("Бурмяй", status=KAZ_MALE),\n'
            '          god_parent2=person("Бурмяй", status=KAZ_FEMALE),\n'
            '          god_parent3=person("Матрена", "Степанова", status=KAZ_FEMALE)),',
            defaults=_MF,
        ))
        # god_parent1 falls back to MALE and god_parent2 to FEMALE in
        # Birth.__init__ even when the name resolves nothing.
        self.assertEqual(len(errs), 4, errs)

    def test_mother_matching_status_mother_is_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          mother=person("Агафья", "Мартынова", status=KAZ_WIFE)),',
            defaults=_MF + ", status_mother=KAZ_WIFE",
        ))
        self.assertTrue(
            any("redundant status=KAZ_WIFE" in e and "status_mother" in e for e in errs), errs)

    def test_child_is_never_flagged(self):
        # Birth.__init__ derives the child's сословие from the parent via
        # child_status_for BEFORE defaults run, so removal is not byte-neutral.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ", status=KAZ_MALE),\n'
            '          father=person("Мартынъ", "Фоминъ", status=SOLDIER_MALE)),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)



_KAZ = ("status_male=KAZENNYJ_PEASANT_MALE, status_female=KAZENNYJ_PEASANT_FEMALE, "
        "status_mother=KAZENNYJ_PEASANT_LEGAL_WIFE")


class TestNewbornStatusSource(_Harness):
    """Birth.__init__ derives the newborn's status from a parent's WRITTEN
    status (child_status_for) before the defaults run, so the written status
    the newborn's rests on is not redundant even when it repeats the default:
    without it the newborn takes status_male/status_female instead."""

    def test_mother_the_newborn_derives_from_is_not_flagged(self):
        # The father's status is the default, the mother's is written and is
        # what makes the girl «казенная крестьянская дочь» rather than
        # «казенная крестьянка».
        errs = self._check(_birth(
            "    birth(9, Gender.FEMALE, 14, 15,\n"
            '          child=person("Агафья"),\n'
            '          father=person("Тимофей", "Лукинъ"),\n'
            '          mother=person("Домна", "Лукина", status=KAZENNYJ_PEASANT_LEGAL_WIFE)),',
            defaults=_KAZ,
        ))
        self.assertEqual(errs, [], errs)

    def test_father_the_newborn_derives_from_is_not_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Мартынъ", "Фоминъ", status=KAZENNYJ_PEASANT_MALE),\n'
            '          mother=person("Агафья", "Мартынова")),',
            defaults=_KAZ,
        ))
        self.assertEqual(errs, [], errs)

    def test_mother_beside_a_father_with_a_status_is_flagged(self):
        # The father's status is consulted exclusively: the mother's feeds nothing.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Мартынъ", "Фоминъ", status=SOLDIER),\n'
            '          mother=person("Агафья", "Мартынова", status=KAZENNYJ_PEASANT_LEGAL_WIFE)),',
            defaults=_KAZ,
        ))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("mother status", errs[0])

    def test_of_two_redundant_parents_the_father_is_kept(self):
        # Removing both would hand the child the default; removing the
        # mother's alone changes nothing — the father is the one consulted.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Мартынъ", "Фоминъ", status=KAZENNYJ_PEASANT_MALE),\n'
            '          mother=person("Агафья", "Мартынова", status=KAZENNYJ_PEASANT_LEGAL_WIFE)),',
            defaults=_KAZ,
        ))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("mother status", errs[0])

    def test_father_whose_status_the_mother_would_give_too_is_flagged(self):
        # Without the father's status the child derives from the mother's,
        # and gets the same «казенный крестьянский сын».
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Мартынъ", "Фоминъ", status=KAZENNYJ_PEASANT_MALE),\n'
            '          mother=person("Агафья", "Мартынова", status=KAZENNYJ_PEASANT_LEGAL_WIFE)),',
            defaults="status_male=KAZENNYJ_PEASANT_MALE, status_female=KAZENNYJ_PEASANT_FEMALE",
        ))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("father status", errs[0])

    def test_parent_of_a_newborn_with_a_written_status_is_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ", status=SOLDIER_SON),\n'
            '          father=person("Мартынъ", "Фоминъ", status=KAZENNYJ_PEASANT_MALE)),',
            defaults=_KAZ,
        ))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("father status", errs[0])

    def test_parent_with_a_status_the_file_cannot_resolve_is_not_flagged(self):
        # An unknown constant may derive anything: keep it rather than guess.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          father=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)

    def test_death_father_the_deceased_derives_from_is_not_flagged(self):
        errs = self._check(_death(
            "    death(1, Gender.MALE, 3, 5,\n"
            '          deceased=person("Иванъ"),\n'
            "          relatives=[relative(person(\"Мартынъ\", \"Фоминъ\", status=KAZENNYJ_PEASANT_MALE), "
            "Relationship.FATHER)]),",
            defaults=_KAZ,
        ))
        self.assertEqual(errs, [], errs)

    def test_death_husband_is_flagged(self):
        # A wife's status is never derived from her husband's.
        errs = self._check(_death(
            "    death(1, Gender.FEMALE, 3, 5,\n"
            '          deceased=person("Марья"),\n'
            "          relatives=[relative(person(\"Мартынъ\", \"Фоминъ\", status=KAZENNYJ_PEASANT_MALE), "
            "Relationship.HUSBAND)]),",
            defaults=_KAZ,
        ))
        self.assertEqual(len(errs), 1, errs)


class TestDeathSlots(_Harness):
    def test_witness_is_flagged(self):
        errs = self._check(_death(
            "    death(1, Gender.FEMALE, 3, 5,\n"
            '          witness1=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertTrue(any("redundant status=KAZ_MALE" in e for e in errs), errs)

    def test_deceased_is_never_flagged(self):
        # Death.__init__ derives a deceased child's сословие from the parent.
        errs = self._check(_death(
            "    death(1, Gender.MALE, 3, 5,\n"
            '          deceased=person("Иванъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)


class TestGenderResolution(_Harness):
    def test_unresolvable_name_takes_the_status_male_branch(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Бурмяй", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertTrue(any("redundant status=KAZ_MALE" in e for e in errs), errs)

    def test_unresolvable_name_never_matches_status_female(self):
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Бурмяй", status=KAZ_FEMALE)),',
            defaults=_MF,
        ))
        self.assertEqual(errs, [], errs)


class TestFixPayload(_Harness):
    def test_status_kwarg_gets_a_remove_kwarg_fix(self):
        issues = self._structured(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Мартынъ", "Фоминъ", status=KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertEqual(len(issues), 1, issues)
        fix = issues[0].get("fix")
        self.assertIsNotNone(fix, issues)
        assert fix is not None
        self.assertEqual(fix["type"], "remove_kwarg")
        self.assertEqual(fix["kwarg"], "status")

    def test_trailing_positional_status_gets_a_remove_arg_fix(self):
        issues = self._structured(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Мартынъ", None, None, None, None, None, None, KAZ_MALE)),',
            defaults=_MF,
        ))
        self.assertEqual(len(issues), 1, issues)
        fix = issues[0].get("fix")
        self.assertIsNotNone(fix, issues)
        assert fix is not None
        self.assertEqual(fix["type"], "remove_arg")

    def test_positional_status_followed_by_gender_is_flagged_without_a_fix(self):
        # Removing it would shift `gender` into the status slot — flag, no fix.
        issues = self._structured(_marriage(
            "    marriage(4, 23,\n"
            '             witness1=person("Мартынъ", None, None, None, None, None, None,'
            " KAZ_MALE, Gender.MALE)),",
            defaults=_MF,
        ))
        self.assertEqual(len(issues), 1, issues)
        self.assertNotIn("fix", issues[0])


class TestPositionalRecordDefaults(_Harness):
    def test_positional_status_groom_is_resolved(self):
        # RecordDefaults(residence, status_male, status_female, status_bride,
        #                status_groom, ...) — CSR001 only mapped male/female.
        errs = self._check(_marriage(
            "    marriage(4, 23,\n"
            '             groom=person("Мартынъ", "Фоминъ", status=KAZ_GROOM)),',
            defaults='"Горюхино", KAZ_MALE, KAZ_FEMALE, KAZ_MAIDEN, KAZ_GROOM',
        ))
        self.assertTrue(
            any("redundant status=KAZ_GROOM" in e and "status_groom" in e for e in errs), errs)

    def test_positional_status_mother_is_resolved(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          mother=person("Агафья", "Мартынова", status=KAZ_WIFE)),',
            defaults='"Горюхино", KAZ_MALE, KAZ_FEMALE, KAZ_MAIDEN, KAZ_GROOM, KAZ_WIFE',
        ))
        self.assertTrue(
            any("redundant status=KAZ_WIFE" in e and "status_mother" in e for e in errs), errs)
