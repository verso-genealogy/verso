import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import verso.ru.linters.checks.census_redundancy as check_census_redundancy
from verso.ru.dsl.records.census import CensusRole, household, member
from verso.ru.domain import person


def _census(body: str) -> str:
    """Wrap a census snippet in the minimal imports the AST checker needs to
    parse (it never executes the DSL, so names aren't validated)."""
    return (
        "from verso.ru.dsl import CensusRole, census_records, household, member\n"
        "from verso.ru.dsl import person\n"
        f"{body}\n"
    )


def _household(body: str) -> str:
    return _census(
        "rs = census_records(\n"
        '    "ГАВО", "431", "1", "100", "Нижняя Яичница", 1897,\n'
        f"    household(\n{body}\n    ),\n"
        ")"
    )


class _Harness(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check_census_redundancy.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, object]]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check_census_redundancy.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()


class TestSurnameRedundancy(_Harness):
    def test_wife_surname_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", "Индюшева"), CensusRole.WIFE, age=38),'
        ))
        self.assertTrue(any('redundant surname "Индюшева"' in e and "wife" in e for e in errs), errs)

    def test_son_surname_and_patronymic_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Леонтий", "Алексеев", "Индюшев"), CensusRole.SON, age=21),'
        ))
        self.assertTrue(any('surname "Индюшев"' in e for e in errs), errs)
        self.assertTrue(any('patronymic "Алексеев"' in e for e in errs), errs)

    def test_daughter_surname_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Ульяна", "Алексеева", "Индюшева"), CensusRole.DAUGHTER, age=9),'
        ))
        self.assertTrue(any('surname "Индюшева"' in e and "daughter" in e for e in errs), errs)

    def test_daughter_in_law_surname_flagged_via_ref(self):
        errs = self._check(_household(
            '        member(1, person("Пимен", "Савельев", "Индюшев"), CensusRole.HEAD, age=62),\n'
            '        member(2, person("Тимофей", last_name_orig="Индюшев"), CensusRole.SON, age=33),\n'
            '        member(3, person("Дарья", "Егорова", "Индюшева"), CensusRole.DAUGHTER_IN_LAW, age=26, ref_member=2),'
        ))
        self.assertTrue(any("daughter_in_law" in e and 'surname "Индюшева"' in e for e in errs), errs)

    def test_grandson_surname_flagged_via_ref(self):
        errs = self._check(_household(
            '        member(1, person("Ефим", "Корнильев", "Индюшев"), CensusRole.HEAD, age=57),\n'
            '        member(2, person("Захар", last_name_orig="Индюшев"), CensusRole.SON, age=28),\n'
            '        member(3, person("Назар", "Захаров", "Индюшев"), CensusRole.GRANDSON, age=7, ref_member=2),'
        ))
        self.assertTrue(any("grandson" in e and 'surname "Индюшев"' in e for e in errs), errs)

    def test_daughter_maiden_kwarg_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Ульяна", "Алексеева", birth_last_name_modern_orth="Индюшева"), CensusRole.DAUGHTER, age=9),'
        ))
        self.assertTrue(any("birth_last_name_modern_orth" in e for e in errs), errs)

    def test_surname_kwarg_form_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", last_name_modern_orth="Индюшева"), CensusRole.WIFE, age=38),'
        ))
        self.assertTrue(any("last_name_modern_orth" in e for e in errs), errs)


class TestNotFlagged(_Harness):
    def test_different_surname_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Домна", "Лукьянова", "Иванова"), CensusRole.WIFE, age=49),'
        ))
        self.assertFalse(any("surname" in e for e in errs), errs)

    def test_head_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),'
        ))
        self.assertEqual(errs, [])

    def test_daughter_maiden_beside_her_current_surname_not_flagged(self):
        # The generator derives no maiden name for a daughter who has a current surname: hers is load-bearing.
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Домна", "Алексеева", last_name_orig="Свиристелова", '
            'birth_last_name_modern_orth="Индюшева"), CensusRole.DAUGHTER, 1, age=25),'
        ))
        self.assertFalse(any("birth_last_name_modern_orth" in e for e in errs), errs)

    def test_member_naming_himself_not_flagged(self):
        # His own surname is his only source: the generator cannot derive it from him.
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Михаил", "Алексеев", "Индюшев"), CensusRole.SON, 2, age=22),'
        ))
        self.assertFalse(any("surname" in e for e in errs), errs)

    def test_source_listed_later_that_derives_not_flagged(self):
        # One pass in member order: the son listed after the grandson has no surname yet at the grandson's turn.
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Фома", last_name_orig="Индюшев"), CensusRole.GRANDSON, 3, age=2),\n'
            '        member(3, person("Михаил", "Алексеев"), CensusRole.SON, 1, age=22),'
        ))
        self.assertFalse(any("surname" in e for e in errs), errs)

    def test_female_head_son_not_flagged(self):
        # Widowed female head: generator can't masculinize, so no derivation.
        errs = self._check(_household(
            '        member(1, person("Ирина", "Ермолаева", "Индюшева"), CensusRole.HEAD, age=54),\n'
            '        member(2, person("Михаил", "Ирин", "Индюшев"), CensusRole.SON, age=22),'
        ))
        self.assertFalse(any("surname" in e for e in errs), errs)

    def test_grandson_without_ref_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Петр", "Миронов", "Индюшев"), CensusRole.HEAD, age=50),\n'
            '        member(2, person("Сергей", "Иванов", "Индюшев"), CensusRole.GRANDSON, age=5),'
        ))
        self.assertEqual(errs, [])

    def test_adopted_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Федот", "Ефимов", "Индюшев"), CensusRole.HEAD, age=50),\n'
            '        member(2, person("Марья", "Федотова", "Индюшева"), CensusRole.DAUGHTER, age=7,\n'
            '               comment="роль в оригинале: приемная дочь"),'
        ))
        self.assertEqual(errs, [])

    def test_hidden_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Прохор", "Иванов", "Индюшев"), CensusRole.HEAD, age=72),\n'
            '        member(2, person("Антон", "Прохоров", "Индюшев"), CensusRole.SON, age=20, hidden=True),'
        ))
        self.assertEqual(errs, [])

    def test_non_family_role_not_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Иван", "Петров", "Индюшев"), CensusRole.HEAD, age=40),\n'
            '        member(2, person("Василий", "Кузьмин", "Индюшев"), CensusRole.BROTHER, age=35),'
        ))
        self.assertFalse(any("surname" in e for e in errs), errs)

    def test_wife_patronymic_not_flagged(self):
        # Wife patronymics are never auto-derived → never redundant.
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина"), CensusRole.WIFE, age=38),'
        ))
        self.assertFalse(any("patronymic" in e for e in errs), errs)


class TestSurnameAdvisory(_Harness):
    """Surnames stay level=warn (removal changes the doc text ФИО→ИО, and renames
    daughters' res_names) but now carry a one-click `remove` fix so a genuinely
    redundant surname is quick to drop in the IDE — the author reviews before
    applying because it is a warning, not an auto-applied error."""

    def test_positional_surname_is_warn_with_remove_arg_fix(self):
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", "Индюшева"), CensusRole.WIFE, age=38),'
        ))
        surname = next(i for i in issues if "surname" in str(i["message"]))
        self.assertEqual(surname["level"], "warn")
        self.assertEqual(cast(dict[str, Any], surname["fix"])["type"], "remove_arg")

    def test_kwarg_surname_is_warn_with_remove_kwarg_fix(self):
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", last_name_modern_orth="Индюшева"), CensusRole.WIFE, age=38),'
        ))
        surname = next(i for i in issues if "last_name_modern_orth" in str(i["message"]))
        self.assertEqual(surname["level"], "warn")
        fix = cast(dict[str, Any], surname["fix"])
        self.assertEqual(fix["type"], "remove_kwarg")
        self.assertEqual(fix["kwarg"], "last_name_modern_orth")

    def test_last_name_orig_kwarg_yields_remove_kwarg_fix(self):
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", last_name_orig="Индюшева"), CensusRole.WIFE, age=38),'
        ))
        surname = next(i for i in issues if "last_name_orig" in str(i["message"]))
        self.assertEqual(cast(dict[str, Any], surname["fix"])["kwarg"], "last_name_orig")

    def test_daughter_current_surname_offers_fix(self):
        # User opted daughters in: removal renames the res_name but the fix is
        # still offered (opt-in, warning-level).
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Ульяна", "Алексеева", "Индюшева"), CensusRole.DAUGHTER, age=9),'
        ))
        surname = next(i for i in issues if "surname" in str(i["message"]) and "daughter" in str(i["message"]))
        self.assertEqual(surname["level"], "warn")
        self.assertEqual(cast(dict[str, Any], surname["fix"])["type"], "remove_arg")

    def test_daughter_maiden_kwarg_offers_remove_kwarg_fix(self):
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Ульяна", "Алексеева", birth_last_name_modern_orth="Индюшева"), CensusRole.DAUGHTER, age=9),'
        ))
        maiden = next(i for i in issues if "birth_last_name_modern_orth" in str(i["message"]))
        self.assertEqual(maiden["level"], "warn")
        self.assertEqual(cast(dict[str, Any], maiden["fix"])["kwarg"], "birth_last_name_modern_orth")

    def test_positional_surname_not_last_has_no_fix(self):
        # Surname positional with a name_modern_orth positional after it → not the
        # last positional, so removing it would shift args: no fix offered (chained
        # on re-lint, like the patronymic case).
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", "Индюшева", "Параскева"), CensusRole.WIFE, age=38),'
        ))
        surname = next(i for i in issues if "surname" in str(i["message"]))
        self.assertNotIn("fix", surname)


class TestPatronymicTiers(_Harness):
    """Two tiers by how neutral removal is: an EXACT old-form match re-derives
    byte-identically (Tier 1, level=error + fix); a MODERNIZE-only match (e.g. a
    pre-reform "Степановъ") is redundant but drops the ъ/ѣ/і from the doc line on
    removal (Tier 2, level=warn + opt-in fix)."""

    def test_exact_patronymic_is_warn_with_fix(self):
        # "Тихонов" == derive_old_patronymic("Тихон") exactly → byte-neutral Tier 1.
        # Demoted to warn 2026-07-21: still byte-neutral, but advisory rather
        # than an error, because no auto-remedy exists once a positional surname
        # follows the patronymic (the fix can only target the LAST positional).
        issues = self._structured(_household(
            '        member(1, person("Тихон", "Петров", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Петр", "Тихонов"), CensusRole.SON, age=21),'
        ))
        patr = next(i for i in issues if "patronymic" in str(i["message"]))
        self.assertEqual(patr["level"], "warn")
        self.assertIn("fix", patr)
        self.assertNotIn("advisory", str(patr["message"]))

    def test_old_orthography_patronymic_is_warn_with_fix(self):
        # "Тихоновъ" modernizes to the derived "Тихонов" but is not identical; it is
        # now a Tier-2 advisory warn (removal drops the ъ from the doc line) that
        # carries an opt-in remove fix — not "unflagged" as before.
        issues = self._structured(_household(
            '        member(1, person("Тихон", "Петров", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Петр", "Тихоновъ"), CensusRole.SON, age=21),'
        ))
        patr = next(i for i in issues if "patronymic" in str(i["message"]))
        self.assertEqual(patr["level"], "warn")
        self.assertIn("advisory", str(patr["message"]))
        self.assertEqual(cast(dict[str, Any], patr["fix"])["type"], "remove_arg")

    def test_tier2_kwarg_patronymic_is_warn_with_remove_kwarg_fix(self):
        issues = self._structured(_household(
            '        member(1, person("Степан", "Иванов", "Индюшев"), CensusRole.HEAD, age=45),\n'
            '        member(2, person("Григорий", patr_orig="Степановъ"), CensusRole.SON, age=1),'
        ))
        patr = next(i for i in issues if "patr_orig" in str(i["message"]))
        self.assertEqual(patr["level"], "warn")
        self.assertEqual(cast(dict[str, Any], patr["fix"])["kwarg"], "patr_orig")

    def test_old_form_matches_but_modern_differs_not_flagged(self):
        # "Нуштанзов" == derive_old_patronymic("Нуштанза"), but
        # canonicalize("Нуштанзов")="Нуштанзович" != derive_patronymic="Нуштанзич".
        # Removing it would change middle_name + rename the res_name → must NOT flag
        # in EITHER tier (the canonicalize guard rejects it).
        errs = self._check(_household(
            '        member(1, person("Нуштанза", "Петров"), CensusRole.HEAD, age=50),\n'
            '        member(2, person("Иван", "Нуштанзов"), CensusRole.SON, age=19),'
        ))
        self.assertFalse(any("patronymic" in e for e in errs), errs)

    def test_old_form_modern_differs_with_pre_reform_orth_not_flagged(self):
        # Same as above but the explicit form carries a terminal ъ ("Нуштанзовъ"):
        # it would take the Tier-2 (modernize) path, but the canonicalize guard
        # ("Нуштанзович" != "Нуштанзич") still rejects it — Tier 2 does not widen
        # the hole.
        errs = self._check(_household(
            '        member(1, person("Нуштанза", "Петров"), CensusRole.HEAD, age=50),\n'
            '        member(2, person("Иван", "Нуштанзовъ"), CensusRole.SON, age=19),'
        ))
        self.assertFalse(any("patronymic" in e for e in errs), errs)


class TestFixMetadata(_Harness):
    def test_patronymic_before_surname_has_no_autofix(self):
        # patr is positional idx1 with a surname positional after it → not last,
        # so no fix until the surname is removed (chained on re-lint).
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Леонтий", "Алексеев", "Индюшев"), CensusRole.SON, age=21),'
        ))
        patr = next(i for i in issues if "patronymic" in str(i["message"]))
        self.assertNotIn("fix", patr)

    def test_patronymic_as_last_positional_yields_remove_arg(self):
        issues = self._structured(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Леонтий", "Алексеев"), CensusRole.SON, age=21),'
        ))
        patr = next(i for i in issues if "patronymic" in str(i["message"]))
        self.assertEqual(cast(dict[str, Any], patr["fix"])["type"], "remove_arg")


class TestGeneratorParity(_Harness):
    """The linter must flag a name only when removing it lets the generator
    re-derive the SAME value — otherwise it would suggest dropping load-bearing
    data (#14113). Builds each household through the real generator with and
    without the explicit names and asserts the equivalence the linter relies on."""

    def test_flagged_names_are_truly_derivable(self):
        # Full household with explicit (redundant) names.
        full = household(None, member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),
                         member(2, person("Параскева", "Фомина", "Индюшева"), CensusRole.WIFE, age=38),
                         member(3, person("Леонтий", "Алексеев", "Индюшев"), CensusRole.SON, age=21),
                         member(4, person("Ульяна", "Алексеева", "Индюшева"), CensusRole.DAUGHTER, age=9))
        # Same household with the redundant names stripped → generator derives.
        stripped = household(None, member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),
                             member(2, person("Параскева"), CensusRole.WIFE, age=38),
                             member(3, person("Леонтий"), CensusRole.SON, age=21),
                             member(4, person("Ульяна"), CensusRole.DAUGHTER, age=9))
        # Wife: married surname identical (profile last_name unchanged).
        self.assertEqual(stripped.members[1].person.last_name_modern,
                         full.members[1].person.last_name_modern)
        # Son: surname + patronymic identical.
        self.assertEqual(stripped.members[2].person.last_name_modern,
                         full.members[2].person.last_name_modern)
        self.assertEqual(stripped.members[2].person.patr_orig,
                         full.members[2].person.patr_orig)
        # Daughter: maiden surname (stripped) equals the explicit current surname.
        self.assertEqual(stripped.members[3].person.birth_last_name_modern,
                         full.members[3].person.last_name_modern)
        self.assertEqual(stripped.members[3].person.patr_orig,
                         full.members[3].person.patr_orig)

        # And the linter flags exactly those redundant names on the full source.
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Параскева", "Фомина", "Индюшева"), CensusRole.WIFE, age=38),\n'
            '        member(3, person("Леонтий", "Алексеев", "Индюшев"), CensusRole.SON, age=21),\n'
            '        member(4, person("Ульяна", "Алексеева", "Индюшева"), CensusRole.DAUGHTER, age=9),'
        ))
        # 1 wife surname + (son surname + patr) + (daughter surname + patr) = 5
        self.assertEqual(len(errs), 5, errs)


if __name__ == "__main__":
    unittest.main()


class TestPatronymicIsAdvisory(_Harness):
    """Tier-1 patronymics are demoted from error to warn (2026-07-21).

    Removal is still byte-neutral, but it is not auto-applied: in the common
    `person("Прохор", "Ильин", "Пупырев")` shape the patronymic is NOT the last
    positional, so no removal fix can be offered until the surname goes first —
    which is itself a reviewed, non-neutral change. Reporting it as an error
    implied an automatic remedy that does not exist.
    """

    def test_exact_match_patronymic_is_warn(self):
        issues = self._structured(_household(
            '        member(1, person("Тимофей", "Ильин"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Прохор", "Тимофеев"), CensusRole.SON, age=22),'
        ))
        patr = next(i for i in issues if "patronymic" in str(i["message"]))
        self.assertEqual(patr["level"], "warn")

    def test_no_census_redundancy_errors_remain(self):
        issues = self._structured(_household(
            '        member(1, person("Тимофей", "Ильин", "Пупырев"), CensusRole.HEAD, age=47),\n'
            '        member(2, person("Прохор", "Тимофеев", "Пупырев"), CensusRole.SON, age=22),'
        ))
        self.assertEqual([i for i in issues if i.get("level") == "error"], [])


class TestNegativeMemberNumber(_Harness):
    """A hidden member numbered -1 parses as a negated literal. A reference to it
    must reach it, not fall back to the head."""

    def test_patronymic_derived_from_a_negative_hidden_father_flagged(self):
        errs = self._check(_household(
            '        member(1, person("Алексей", "Матвеев", "Индюшев"), CensusRole.HEAD, age=47),\n'
            '        member(5, person("Иван", "Петров"), CensusRole.GRANDSON, ref_member=-1),\n'
            '        member(-1, person("Петр"), CensusRole.SON, ref_member=1, hidden=True),'
        ))
        self.assertTrue(any('patronymic "Петров"' in e for e in errs), errs)


class TestPositionalRefMember(_Harness):
    """member(number, person, role, ref_member, age, …): a reference written in
    place is ref_member, not age, and reaches the member it names."""

    def test_positional_ref_member_reaches_its_member(self):
        errs = self._check(_household(
            '        member(1, person("Ефим", "Корнильев", "Индюшев"), CensusRole.HEAD, age=57),\n'
            '        member(2, person("Захар", last_name_orig="Индюшев"), CensusRole.SON, 1, age=28),\n'
            '        member(3, person("Назар", "Захаров"), CensusRole.GRANDSON, 2, age=7),'
        ))
        self.assertTrue(any("grandson" in e and 'patronymic "Захаров"' in e for e in errs), errs)

    def test_positional_ref_member_is_not_the_head_fallback(self):
        # A daughter-in-law requires her ref_member; read in place it names the
        # son, whose surname she carries — read as an age it named nobody.
        errs = self._check(_household(
            '        member(1, person("Пимен", "Савельев", "Индюшев"), CensusRole.HEAD, age=62),\n'
            '        member(2, person("Тимофей", last_name_orig="Индюшев"), CensusRole.SON, 1, age=33),\n'
            '        member(3, person("Дарья", "Егорова", "Индюшева"), CensusRole.DAUGHTER_IN_LAW, 2, age=26),'
        ))
        self.assertTrue(any("daughter_in_law" in e and 'surname "Индюшева"' in e for e in errs), errs)
