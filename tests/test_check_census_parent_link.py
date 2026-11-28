import ast
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.census_parent_link as check


def _census(*members: str, year: int = 1858) -> str:
    body = ",\n        ".join(members)
    return (
        f'census = census_records("ГАТО", "1", "1", "1", "Маниловка", {year},\n'
        f'    household(\n        {body},\n    family_id="1"),\n)\n'
    )


def _collect(*members: str, year: int = 1858):
    return check._collect(ast.parse(_census(*members, year=year)))


class TestCpl001Flagged(unittest.TestCase):
    def test_mislabel_no_patronymic_flagged(self):
        # A GRANDSON with no patronymic, ref → non-head SON.
        issues = _collect(
            'member(1, person("Савелій", "Пахомовъ"), CensusRole.HEAD, age=66)',
            'member(2, person("Леонтій"), CensusRole.SON, ref_member=1, age=44)',
            'member(3, person("Прокофій"), CensusRole.GRANDSON, ref_member=2, age=11)',
        )
        self.assertEqual(len(issues), 1)
        msg = issues[0]["message"]
        self.assertIn("CPL001", msg)
        self.assertIn("member 3 (Прокофій)", msg)
        self.assertIn("parent_member=2", msg)
        self.assertIn("SON/DAUGHTER", msg)
        self.assertIn("auto-derived", msg)

    def test_role_faithful_patronymic_match_flagged(self):
        # A role-faithful GRANDSON whose patronymic matches the ref.
        issues = _collect(
            'member(1, person("Тихонъ", "Мироновъ"), CensusRole.HEAD, age=52)',
            'member(2, person("Фаддей", "Кирилловъ"), CensusRole.SON, age=27)',
            'member(5, person("Ермолай", "Фаддеевъ"), CensusRole.GRANDSON, ref_member=2, age=5)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("«Фаддеевъ»", issues[0]["message"])
        self.assertIn("«Фаддей»", issues[0]["message"])

    def test_old_orthography_match_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрѣй"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Иванъ", "Андрѣевъ"), CensusRole.GRANDSON, ref_member=2, age=5)',
        )
        self.assertEqual(len(issues), 1)

    def test_granddaughter_female_form_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Марья", "Андреева"), CensusRole.GRANDDAUGHTER, ref_member=2, age=5)',
        )
        self.assertEqual(len(issues), 1)

    def test_comment_signal_on_bare_nephew_flagged(self):
        issues = _collect(
            'member(1, person("Герасимъ", "Лукинъ"), CensusRole.HEAD, age=46)',
            'member(3, person("Мартынъ", "Лукинъ"), CensusRole.BROTHER, ref_member=1, age=38)',
            'member(4, person("Евграфъ"), CensusRole.NEPHEW, ref_member=3, age=1, '
            'comment="сын Мартына Лукина")',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("«сын/дочь»", issues[0]["message"])


class TestCpl001Silent(unittest.TestCase):
    def _no_cpl001(self, issues):
        self.assertFalse([i for i in issues if "CPL001" in str(i["message"])], issues)

    def test_anchor_patronymic_contradiction_not_flagged(self):
        # A NEPHEW whose patronymic contradicts the ref.
        issues = _collect(
            'member(1, person("Тимофей", "Семеновъ"), CensusRole.HEAD, age=50)',
            'member(7, person("Лука", "Тимофеевъ"), CensusRole.NEPHEW, ref_member=1, age=20)',
            'member(11, person("Макаръ", "Борисовъ"), CensusRole.NEPHEW, ref_member=7, age=7)',
        )
        self._no_cpl001(issues)

    def test_contradiction_vetoes_comment_signal(self):
        issues = _collect(
            'member(1, person("Тимофей", "Семеновъ"), CensusRole.HEAD, age=50)',
            'member(7, person("Лука", "Тимофеевъ"), CensusRole.NEPHEW, ref_member=1, age=20)',
            'member(11, person("Макаръ", "Борисовъ"), CensusRole.NEPHEW, ref_member=7, age=7, '
            'comment="сын отставного солдата")',
        )
        self._no_cpl001(issues)

    def test_ref_to_head_not_cpl001(self):
        # ref→HEAD is CPL002 territory (father absent), never CPL001.
        issues = _collect(
            'member(1, person("Елисей", "Назаровъ"), CensusRole.HEAD, age=80)',
            'member(2, person("Афанасій", "Прохоровъ"), CensusRole.GRANDSON, ref_member=1, age=36)',
        )
        self._no_cpl001(issues)
        self.assertTrue(any("CPL002" in str(i["message"]) for i in issues))

    def test_ref_to_head_with_nonstandard_number_not_cpl001(self):
        issues = _collect(
            'member(2, person("Елисей", "Назаровъ"), CensusRole.HEAD, age=80)',
            'member(3, person("Афанасій"), CensusRole.GRANDSON, ref_member=2, age=36)',
        )
        self._no_cpl001(issues)

    def test_parent_member_present_not_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Иванъ"), CensusRole.GRANDSON, ref_member=2, age=5, parent_member=2)',
        )
        self.assertEqual(issues, [])

    def test_nephew_sibling_inheritance_not_flagged(self):
        # Translator precedence 4: ref target itself carries parent_member.
        issues = _collect(
            'member(1, person("Корнилій", "Мироновъ"), CensusRole.HEAD, age=59)',
            'member(6, person("Никонъ", "Корнильевъ"), CensusRole.SON, hidden=True)',
            'member(4, person("Савватій", "Никоновъ"), CensusRole.NEPHEW, ref_member=5, age=14)',
            'member(5, person("Ѳедотъ", "Никоновъ"), CensusRole.NEPHEW, ref_member=1, age=9, '
            'parent_member=6)',
        )
        self.assertEqual(issues, [])

    def test_hidden_ref_target_not_flagged(self):
        # A hidden ref IS the parent (translator legacy path) — union emitted.
        # Scoped to CPL001, this class's subject, like its siblings: CPL006
        # DOES have something to say about a recorded member pointing
        # `ref_member` at a reconstruction, and says it advisorily.
        issues = _collect(
            'member(1, person("Корнилій", "Мироновъ"), CensusRole.HEAD, age=59)',
            'member(6, person("Никонъ", "Корнильевъ"), CensusRole.SON, hidden=True)',
            'member(4, person("Савватій", "Никоновъ"), CensusRole.NEPHEW, ref_member=6, age=14)',
        )
        self._no_cpl001(issues)

    def test_son_with_ref_member_not_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Иванъ"), CensusRole.SON, ref_member=2, age=5)',
        )
        self.assertEqual(issues, [])

    def test_bare_nephew_without_patronymic_not_flagged(self):
        # NEPHEW gets no patronymic derivation from ref — no evidence.
        issues = _collect(
            'member(1, person("Герасимъ", "Лукинъ"), CensusRole.HEAD, age=46)',
            'member(3, person("Мартынъ", "Лукинъ"), CensusRole.BROTHER, ref_member=1, age=38)',
            'member(4, person("Евграфъ"), CensusRole.NEPHEW, ref_member=3, age=1)',
        )
        self.assertEqual(issues, [])

    def test_female_ref_target_not_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Дарья", "Петрова"), CensusRole.DAUGHTER, ref_member=1, age=30)',
            'member(3, person("Иванъ"), CensusRole.GRANDSON, ref_member=2, age=5)',
        )
        self.assertEqual(issues, [])

    def test_adopted_line_not_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Иванъ"), CensusRole.GRANDSON, ref_member=2, age=5, '
            'comment="приемный внук")',
        )
        self.assertEqual(issues, [])

    def test_dangling_ref_not_flagged(self):
        # Scoped to CPL001, this class's subject: CPL001 reads the resolved ref
        # TARGET and a dangling number has none, so it has nothing to say.
        # CPL009 is the one that owns a number missing from the household.
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(3, person("Иванъ"), CensusRole.GRANDSON, ref_member=9, age=5)',
        )
        self._no_cpl001(issues)
        self.assertTrue(any("CPL009" in str(i["message"]) for i in issues), issues)

    def test_non_census_file_yields_nothing(self):
        tree = ast.parse('births = birth_records(person("Иванъ"))\n')
        self.assertEqual(check._collect(tree), [])


class TestCpl002(unittest.TestCase):
    def test_orphaned_nephew_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(6, person("Карпъ", "Захаровъ"), CensusRole.NEPHEW, ref_member=1, age=22)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("CPL002", issues[0]["message"])
        self.assertIn("«Захаровъ»", issues[0]["message"])

    def test_orphaned_grandson_without_ref_flagged(self):
        issues = _collect(
            'member(1, person("Елисей", "Назаровъ"), CensusRole.HEAD, age=80)',
            'member(2, person("Афанасій", "Прохоровъ"), CensusRole.GRANDSON, age=36)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("CPL002", issues[0]["message"])

    def test_hidden_father_with_parent_member_not_flagged(self):
        issues = _collect(
            'member(1, person("Елисей", "Назаровъ"), CensusRole.HEAD, age=80)',
            'member(2, person("Афанасій", "Прохоровъ"), CensusRole.GRANDSON, ref_member=1, age=36, '
            'parent_member=9)',
            'member(9, person("Прохоръ"), None, ref_member=6, parent_member=1, hidden=True, spouse_member=6)',
            'member(6, person("Мелания", "Гавриилова"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=62)',
        )
        self.assertEqual(issues, [])

    def test_visible_father_ref_is_cpl001_not_cpl002(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Иванъ", "Андреевъ"), CensusRole.GRANDSON, ref_member=2, age=5)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("CPL001", issues[0]["message"])

    def test_hidden_member_itself_not_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(6, person("Захаръ"), CensusRole.NEPHEW, ref_member=1, hidden=True)',
        )
        self.assertEqual(issues, [])

    def test_adopted_nephew_not_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(6, person("Карпъ", "Захаровъ"), CensusRole.NEPHEW, ref_member=1, age=22, '
            'comment="приемныш")',
        )
        self.assertEqual(issues, [])


class TestCpl003(unittest.TestCase):
    def test_unpairable_snokha_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(12, person("Матрена", "Лукьянова"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=44)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("CPL003", issues[0]["message"])
        self.assertIn("ref_member=12", issues[0]["message"])

    def test_rule_a_single_dead_son_not_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(2, person("Тарасъ"), CensusRole.SON, ref_member=1, previous_age=21, '
            'departure_year=1854, departure_reason="умер")',
            'member(12, person("Матрена", "Лукьянова"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=44)',
        )
        self.assertEqual(issues, [])

    def test_hidden_husband_not_flagged(self):
        issues = _collect(
            'member(1, person("Фаддей", "Ивановъ"), CensusRole.HEAD, age=41)',
            'member(8, person("Ульяна", "Михеева"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=52)',
            'member(9, person("Гаврила"), CensusRole.BROTHER, ref_member=8, hidden=True)',
        )
        self.assertEqual(issues, [])

    def test_ref_to_husband_not_flagged(self):
        issues = _collect(
            'member(1, person("Петръ", "Ивановъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=30)',
            'member(3, person("Дарья", "Семенова"), CensusRole.DAUGHTER_IN_LAW, ref_member=2, age=28)',
        )
        self.assertEqual(issues, [])

    def test_two_dead_sons_flagged(self):
        issues = _collect(
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(2, person("Тарасъ"), CensusRole.SON, ref_member=1, previous_age=21, '
            'departure_year=1854, departure_reason="умер")',
            'member(3, person("Власъ"), CensusRole.SON, ref_member=1, previous_age=23, '
            'departure_year=1856, departure_reason="умер")',
            'member(12, person("Матрена", "Лукьянова"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=44)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("found 2", issues[0]["message"])


class TestEntryPoints(unittest.TestCase):
    def test_check_file_string_format(self):
        src = _census(
            'member(1, person("Савелій", "Пахомовъ"), CensusRole.HEAD, age=66)',
            'member(2, person("Леонтій"), CensusRole.SON, ref_member=1, age=44)',
            'member(3, person("Прокофій"), CensusRole.GRANDSON, ref_member=2, age=11)',
        )
        with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(src)
            p = Path(f.name)
        try:
            lines = check.check_file(p)
            self.assertEqual(len(lines), 1)
            self.assertRegex(lines[0], rf"^{p}:\d+: \[CPL001\] ")
            structured = check.check_file_structured(p)
            self.assertEqual(len(structured), 1)
            self.assertEqual(structured[0]["level"], "warn")
        finally:
            p.unlink()


if __name__ == "__main__":
    unittest.main()


class TestCpl004MarriedInSpouseStrayParent(unittest.TestCase):
    """A married-in wife whose `parent_member` points into her HUSBAND's
    lineage — she would become her own husband's sister/niece."""

    @staticmethod
    def _cpl004(*members: str):
        return [i for i in _collect(*members) if "CPL004" in str(i["message"])]

    def test_parent_is_husbands_brother_flagged(self):
        # A сноха whose parent_member pointed at her husband's BROTHER. Her patronymic even matches his first name,
        # which is exactly why the mistake was made.
        issues = self._cpl004(
            'member(1, person("Пахомъ", "Игнатьевъ"), CensusRole.HEAD, age=47)',
            'member(8, person("Агафья", "Потапова"), CensusRole.WIFE, ref_member=1, age=48, parent_member=24)',
            'member(24, person("Потапъ", "Игнатьевъ"), CensusRole.BROTHER, age="?", hidden=True)',
        )
        self.assertEqual(len(issues), 1)
        msg = str(issues[0]["message"])
        self.assertIn("member 8 (Агафья)", msg)
        self.assertIn("parent_member=24", msg)

    def test_parent_is_husbands_grandfather_flagged(self):
        # A wife whose parent_member pointed at her husband's grandfather, two
        # links up the chain.
        issues = self._cpl004(
            'member(1, person("Кондратій", "Яковлевъ"), CensusRole.HEAD, age=68)',
            'member(2, person("Ермилъ", "Зотовъ"), CensusRole.NEPHEW, age=57, parent_member=19)',
            'member(7, person("Ипполитъ"), CensusRole.SON, ref_member=2, age=30)',
            'member(17, person("Ефимія", "Зотова"), CensusRole.WIFE, ref_member=7, age=24, parent_member=19)',
            'member(19, person("Зотъ", "Яковлевъ"), CensusRole.BROTHER, age="?", hidden=True)',
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("member 17 (Ефимія)", str(issues[0]["message"]))

    def test_snokha_role_also_flagged(self):
        issues = self._cpl004(
            'member(1, person("Пахомъ", "Игнатьевъ"), CensusRole.HEAD, age=47)',
            'member(3, person("Аксинья"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=32, parent_member=4)',
            'member(4, person("Потапъ", "Игнатьевъ"), CensusRole.BROTHER, age=52)',
        )
        self.assertEqual(len(issues), 1)

    # --- legitimate shapes that must stay silent -------------------------

    def test_her_own_father_in_household_not_flagged(self):
        # The documented legitimate pattern: the head is HER father and her
        # husband married in, so the head is NOT in the husband's lineage.
        self.assertEqual(self._cpl004(
            'member(1, person("Алексѣй", "Петровъ"), CensusRole.HEAD, age=58)',
            'member(2, person("Прохоръ", "Ѳедоровъ"), CensusRole.SON_IN_LAW, ref_member=1, age=29)',
            'member(3, person("Марья", "Алексѣева"), CensusRole.WIFE, ref_member=2, age=26, parent_member=1)',
        ), [])

    def test_wife_without_parent_member_not_flagged(self):
        self.assertEqual(self._cpl004(
            'member(1, person("Пахомъ", "Игнатьевъ"), CensusRole.HEAD, age=47)',
            'member(8, person("Агафья", "Потапова"), CensusRole.WIFE, ref_member=1, age=48)',
        ), [])

    def test_hidden_wife_not_flagged(self):
        self.assertEqual(self._cpl004(
            'member(1, person("Егоръ", "Степановъ"), CensusRole.HEAD, age=47)',
            'member(2, person("Февронья"), CensusRole.WIFE, ref_member=1, age="?", hidden=True, parent_member=3)',
            'member(3, person("Степанъ", "Егоровъ"), CensusRole.BROTHER, age=60)',
        ), [])


class TestCpl005DeadHiddenMember(unittest.TestCase):
    """A hidden=True member that connects nobody — a fabricated leaf."""

    @staticmethod
    def _cpl005(*members: str):
        return [i for i in _collect(*members) if "CPL005" in str(i["message"])]

    def test_fabricated_leaf_flagged(self):
        # The fabricated-brother shape: a hidden member invented purely to father
        # a nephew; once that parent_member was corrected he linked to
        # nobody, and his only remaining tie was an external father_ref.
        issues = self._cpl005(
            'member(1, person("Евдокимъ", "Ермолаевъ"), CensusRole.HEAD, age=55)',
            'member(3, person("Ипполитъ", "Сидоровъ"), CensusRole.NEPHEW, age=24)',
            'member(7, person("Сидоръ", "Ермолаевъ"), CensusRole.BROTHER, age="?", father_ref="ermolaj_tarasovich", hidden=True)',
        )
        self.assertEqual(len(issues), 1)
        msg = str(issues[0]["message"])
        self.assertIn("member 7 (Сидоръ)", msg)
        self.assertIn("hidden", msg)

    # --- connectors doing real work must stay silent ---------------------

    def test_hidden_father_referenced_by_parent_member_not_flagged(self):
        self.assertEqual(self._cpl005(
            'member(1, person("Кондратій", "Яковлевъ"), CensusRole.HEAD, age=68)',
            'member(2, person("Ермилъ", "Зотовъ"), CensusRole.NEPHEW, age=57, parent_member=19)',
            'member(19, person("Зотъ", "Яковлевъ"), CensusRole.BROTHER, age="?", hidden=True)',
        ), [])

    def test_hidden_father_referenced_by_ref_member_not_flagged(self):
        self.assertEqual(self._cpl005(
            'member(1, person("Пахомъ", "Игнатьевъ"), CensusRole.HEAD, age=47)',
            'member(24, person("Потапъ", "Игнатьевъ"), CensusRole.BROTHER, age="?", hidden=True)',
            'member(25, person("Ипатъ", "Потаповъ"), CensusRole.SON, ref_member=24, age="?")',
        ), [])

    def test_hidden_first_wife_referenced_by_secondary_ref_not_flagged(self):
        # The Option-A deceased-1st-wife pattern: children route to her via
        # secondary_ref_member.
        self.assertEqual(self._cpl005(
            'member(2, person("Ермилъ"), CensusRole.HEAD, age=49)',
            'member(5, person("Назаръ"), CensusRole.SON, ref_member=2, age=25, secondary_role=CensusRole.SON, secondary_ref_member=18)',
            'member(18, person("Ненила"), CensusRole.WIFE, ref_member=2, age="?", hidden=True)',
        ), [])

    def test_hidden_husband_with_outbound_ref_not_flagged(self):
        # The CPL003 fix shape: he points at his wife, so he wires the marriage.
        self.assertEqual(self._cpl005(
            'member(1, person("Алексѣй", "Петровъ"), CensusRole.HEAD, age=58)',
            'member(6, person("Дарья"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=30)',
            'member(9, person("Макаръ"), None, ref_member=6, parent_member=1, hidden=True)',
        ), [])

    def test_visible_unreferenced_member_not_flagged(self):
        # Visible people are attested by the source — absence of links is fine.
        self.assertEqual(self._cpl005(
            'member(1, person("Евдокимъ", "Ермолаевъ"), CensusRole.HEAD, age=55)',
            'member(2, person("Марфа"), CensusRole.WIFE, ref_member=1, age=54)',
        ), [])


class Cpl005FalsePositives(unittest.TestCase):
    """Real corpus shapes CPL005 wrongly flagged when first shipped.

    A hidden member can be connected WITHOUT an explicit ref_member: most roles
    resolve head-relatively (a DAUGHTER with no ref is the head's daughter), and
    `secondary_ref_member` is an outbound link too. Missed because the
    validating sweep was silently broken by an unquoted path.
    """

    @staticmethod
    def _cpl005(*members: str):
        return [i for i in _collect(*members) if "CPL005" in str(i["message"])]

    def test_hidden_daughter_defaulting_to_head_not_flagged(self):
        # A DAUGHTER with no ref_member is the HEAD's daughter by the
        # translator's default.
        self.assertEqual(self._cpl005(
            'member(1, person("Ермолай", "Лукьяновъ"), CensusRole.HEAD, age=61)',
            'member(15, person("Параскева", "Ермолаева"), CensusRole.DAUGHTER, age="?", hidden=True)',
        ), [])

    def test_hidden_wife_defaulting_to_head_not_flagged(self):
        # A WIFE with no ref_member is the HEAD's wife.
        self.assertEqual(self._cpl005(
            'member(1, person("Яковъ", "Васильевъ"), CensusRole.HEAD, age=55)',
            'member(10, person("Акилина", "Фомина"), CensusRole.WIFE, age="?", hidden=True)',
        ), [])

    def test_secondary_ref_member_is_an_outbound_link(self):
        # A BROTHER, but secondary_ref_member wires him as HUSBAND of m2, so he
        # carries a real union.
        self.assertEqual(self._cpl005(
            'member(1, person("Никифоръ"), CensusRole.HEAD, age=68)',
            'member(2, person("Ненила"), CensusRole.WIFE, ref_member=1, age=58)',
            'member(12, person("Мартынъ", "Никифоровъ"), CensusRole.BROTHER, age="?", '
            'secondary_role=CensusRole.HUSBAND, secondary_ref_member=2, hidden=True)',
        ), [])

    def test_the_fabricated_leaf_is_still_flagged(self):
        # Regression guard: the fabricated-brother shape must keep firing —
        # BROTHER creates no union, and father_ref alone does not rescue him.
        issues = self._cpl005(
            'member(1, person("Евдокимъ", "Ермолаевъ"), CensusRole.HEAD, age=55)',
            'member(7, person("Сидоръ", "Ермолаевъ"), CensusRole.BROTHER, age="?", '
            'father_ref="ermolaj_tarasovich", hidden=True)',
        )
        self.assertEqual(len(issues), 1)


class TestCpl003Range(unittest.TestCase):
    """CPL003 must pin the role argument, not just the line.

    Without col/end_col the IntelliJ annotator has nothing to narrow to and
    highlights the WHOLE member() line (DslLintAnnotator.narrowRange) — the same
    reason census_age's CAI checks carry `_kwarg_range`. The finding is about the
    role, so `CensusRole.DAUGHTER_IN_LAW` is what should light up.
    """

    SRC_MEMBERS = (
        'member(1, person("Савелій", "Пахомовъ"), CensusRole.HEAD, age=66)',
        'member(2, person("Парасковья", "Лукьянова"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=28)',
    )

    def _one(self):
        src = _census(*self.SRC_MEMBERS)
        issues = check._collect(ast.parse(src), src.splitlines())
        found = [i for i in issues if "CPL003" in str(i["message"])]
        self.assertEqual(len(found), 1, issues)
        return found[0], src.splitlines()

    def test_range_present(self):
        f, _ = self._one()
        self.assertIn("col", f)
        self.assertIn("end_col", f)

    def test_range_slices_to_the_role_argument(self):
        f, lines = self._one()
        line = lines[int(f["line"]) - 1]
        self.assertEqual(line[int(f["col"]):int(f["end_col"])],
                         "CensusRole.DAUGHTER_IN_LAW")

    def test_structured_output_carries_the_range(self):
        """check_file_structured used to rebuild the dict and drop everything
        but level/line/message, so the range has to survive that too."""
        src = _census(*self.SRC_MEMBERS)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manilovka_census_1858.py"
            p.write_text(src, encoding="utf-8")
            rows = [r for r in check.check_file_structured(p)
                    if "CPL003" in str(r["message"])]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("col", rows[0])
        self.assertIn("end_col", rows[0])


class TestCplRangesForTheRest(unittest.TestCase):
    """CPL001/002/004/005 pin the argument their fix actually targets.

    Same reason as CPL003: without col/end_col the IntelliJ annotator highlights
    the whole member() line. The pin differs per check because the actionable
    field does — the role for the two lineage checks, the offending kwarg for
    the other two.
    """

    def _one(self, code, *members):
        src = _census(*members)
        issues = [i for i in check._collect(ast.parse(src), src.splitlines())
                  if code in str(i["message"])]
        self.assertEqual(len(issues), 1, issues)
        f = issues[0]
        line = src.splitlines()[int(f["line"]) - 1]
        self.assertIn("col", f)
        return line[int(f["col"]):int(f["end_col"])]

    def test_cpl001_pins_the_role(self):
        """«the role should be SON/DAUGHTER» — the role is what misroutes ref_member."""
        got = self._one(
            "CPL001",
            'member(1, person("Савелій", "Пахомовъ"), CensusRole.HEAD, age=66)',
            'member(2, person("Леонтій"), CensusRole.SON, ref_member=1, age=44)',
            'member(3, person("Прокофій"), CensusRole.GRANDSON, ref_member=2, age=11)')
        self.assertEqual(got, "CensusRole.GRANDSON")

    def test_cpl002_pins_the_role(self):
        got = self._one(
            "CPL002",
            'member(1, person("Ермолай", "Игнатьевъ"), CensusRole.HEAD, age=52)',
            'member(6, person("Карпъ", "Захаровъ"), CensusRole.NEPHEW, ref_member=1, age=22)')
        self.assertEqual(got, "CensusRole.NEPHEW")

    def test_cpl004_pins_parent_member(self):
        """«Drop parent_member unless he is genuinely her own» — pin what to drop."""
        got = self._one(
            "CPL004",
            'member(1, person("Гордѣй", "Кирилловъ"), CensusRole.HEAD, age=62)',
            'member(2, person("Домна"), CensusRole.WIFE, ref_member=1, age="?", parent_member=3)',
            'member(3, person("Родіонъ", "Кирилловъ"), CensusRole.BROTHER, age=58)')
        self.assertEqual(got, "parent_member=3")

    def test_cpl005_pins_hidden(self):
        """The finding is that the hidden member is unjustified — pin hidden=True."""
        got = self._one(
            "CPL005",
            'member(1, person("Евдокимъ", "Ермолаевъ"), CensusRole.HEAD, age=55)',
            'member(3, person("Ипполитъ", "Сидоровъ"), CensusRole.NEPHEW, age=24)',
            'member(7, person("Сидоръ", "Ермолаевъ"), CensusRole.BROTHER, age="?", '
            'father_ref="ermolaj_tarasovich", hidden=True)')
        self.assertEqual(got, "hidden=True")

    def test_cpl006_pins_ref_member(self):
        """A recorded member's ref_member may only name someone the source wrote
        down; the reconstruction goes on parent_member. Pin what to change."""
        got = self._one(
            "CPL006",
            'member(1, person("Артемій", "Исаевъ"), CensusRole.HEAD, age=74)',
            'member(30, person("Лазарь"), CensusRole.SON, ref_member=32, age=17)',
            'member(32, person("Прохоръ", "Артемьевъ"), CensusRole.SON, ref_member=1, '
            'hidden=True)')
        self.assertEqual(got, "ref_member=32")


class TestCpl006Scope(unittest.TestCase):
    """CPL006 fires on the source's own wording, not on the reconstruction."""

    @staticmethod
    def _codes(*members):
        src = _census(*members)
        return [str(i["message"]) for i in
                check._collect(ast.parse(src), src.splitlines())
                if "CPL006" in str(i["message"])]

    def test_parent_member_at_a_hidden_member_is_fine(self):
        """The reconstructed lineage axis — this is the prescribed fix."""
        self.assertEqual(self._codes(
            'member(1, person("Артемій", "Исаевъ"), CensusRole.HEAD, age=74)',
            'member(29, person("Ирина", "Матвѣева"), CensusRole.DAUGHTER_IN_LAW, '
            'ref_member=1, age=38)',
            'member(30, person("Лазарь"), CensusRole.SON, ref_member=29, '
            'parent_member=32, age=17)',
            'member(32, person("Прохоръ", "Артемьевъ"), CensusRole.SON, ref_member=1, '
            'hidden=True)'), [])

    def test_a_hidden_member_may_point_anywhere(self):
        """Hidden→visible is the reconstruction's own wiring, not a source claim."""
        self.assertEqual(self._codes(
            'member(1, person("Артемій", "Исаевъ"), CensusRole.HEAD, age=74)',
            'member(3, person("Ирина", "Матвѣева"), CensusRole.DAUGHTER_IN_LAW, '
            'ref_member=1, age=38)',
            'member(5, person("Прохоръ"), None, ref_member=3, hidden=True)'), [])


class TestCpl007(unittest.TestCase):
    """A `role=None` member's `ref_member` must say what it encodes.

    The shape is real and the corpus holds thirteen of it: with the role
    cleared, the same number is read as a spouse by one generator pass and as a
    parent by another, and the only statement of which is a prose comment.
    """

    @staticmethod
    def _codes(*members):
        src = _census(*members)
        return [str(i["message"]) for i in
                check._collect(ast.parse(src), src.splitlines())
                if "CPL007" in str(i["message"])]

    # A hidden first husband whose ref names the widow, and whose comment is
    # the only place that is written down.
    _HUSBAND = ('member(17, person("Герасим"), None, ref_member=3, age="?", '
                'hidden=True, comment="первый муж Меланьи")')
    _HOUSEHOLD = ('member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
                  'member(2, person("Макаръ"), CensusRole.SON, ref_member=1, age=45)',
                  'member(3, person("Мелания"), CensusRole.WIFE, ref_member=2, age=38)')

    def test_undeclared_ref_is_flagged(self):
        found = self._codes(*self._HOUSEHOLD, self._HUSBAND)
        self.assertEqual(len(found), 1, found)
        self.assertIn("member 17 (Герасим)", found[0])
        self.assertIn("spouse_member=3", found[0])
        self.assertIn("parent_member=3", found[0])

    def test_spouse_member_settles_it(self):
        self.assertEqual(self._codes(
            *self._HOUSEHOLD,
            self._HUSBAND[:-1] + ', spouse_member=3)'), [])

    def test_parent_member_settles_it(self):
        """The one of the thirteen where N is the father."""
        self.assertEqual(self._codes(
            'member(1, person("Ермил", "Терентьев"), CensusRole.HEAD, age=58)',
            'member(2, person("Мелетий", "Стратонов"), None, ref_member=7, age=47, '
            'parent_member=7)',
            'member(7, person("Стратон"), None, age="?", hidden=True)'), [])

    def test_the_secondary_axis_settles_it_too(self):
        """It names the relation to N just as precisely, and the extractor
        reads it on the same footing. The difference is that it also MINTS the
        union — which is a reason to choose it, not a reason to reject it."""
        self.assertEqual(self._codes(
            *self._HOUSEHOLD,
            self._HUSBAND[:-1] + ', secondary_role=CensusRole.HUSBAND, '
                                 'secondary_ref_member=3)'), [])

    def test_a_secondary_reference_without_a_role_settles_nothing(self):
        """The number alone states nothing; the role word is what names the
        relation to N. (The DSL itself rejects the pair half-set, so this can
        only ever arrive in a buffer an IDE is linting mid-edit.)"""
        found = self._codes(*self._HOUSEHOLD,
                            self._HUSBAND[:-1] + ', secondary_ref_member=3)')
        self.assertEqual(len(found), 1, found)

    def test_a_secondary_reference_to_somebody_else_settles_nothing(self):
        found = self._codes(
            *self._HOUSEHOLD,
            self._HUSBAND[:-1] + ', secondary_role=CensusRole.SON, '
                                 'secondary_ref_member=1)')
        self.assertEqual(len(found), 1, found)

    def test_a_different_number_does_not_settle_it(self):
        """`spouse_member` naming somebody else leaves `ref_member` unexplained —
        it is the REFERENCE that has to be given a meaning, not the member."""
        found = self._codes(*self._HOUSEHOLD,
                            self._HUSBAND[:-1] + ', spouse_member=1)')
        self.assertEqual(len(found), 1, found)

    def test_a_role_is_itself_the_declaration(self):
        """With a role, `ref_member` is measured against it — nothing to state."""
        self.assertEqual(self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Макаръ"), CensusRole.SON, ref_member=1, age=45)'), [])

    def test_a_left_out_role_is_none(self):
        """`member(n, person(...), ref_member=N)` builds the same member as `role=None`: the same finding."""
        left_out = 'member(17, person("Герасим"), ref_member=3, age="?", hidden=True)'
        found = self._codes(*self._HOUSEHOLD, left_out)
        self.assertEqual(len(found), 1, found)
        self.assertIn("member 17 (Герасим)", found[0])
        self.assertEqual(self._codes(*self._HOUSEHOLD, left_out[:-1] + ', spouse_member=3)'), [])

    def test_a_role_left_out_without_a_ref_is_silent(self):
        self.assertEqual(self._codes(
            'member(1, person("Лука", "Шумилов"), CensusRole.HEAD, age=41)',
            'member(9, person("Мирон"), age="?", hidden=True)'), [])

    def test_role_none_without_a_ref_is_silent(self):
        """A member with no reference has nothing to disambiguate — the
        «связь не указана» shape, and the bare hidden ancestors."""
        self.assertEqual(self._codes(
            'member(1, person("Лука", "Шумилов"), CensusRole.HEAD, age=41)',
            'member(9, person("Мирон"), None, age="?", hidden=True)'), [])


class TestCpl008(unittest.TestCase):
    """The secondary axis is for a relationship the role does NOT describe.

    Aimed at the member `ref_member` already names, it restates one — and does
    it the expensive way, since the translator mints a union from that axis.
    The corpus holds 36 secondary references and none of them equal, so the
    check gates at zero.
    """

    @staticmethod
    def _codes(*members):
        src = _census(*members)
        return [str(i["message"]) for i in
                check._collect(ast.parse(src), src.splitlines())
                if "CPL008" in str(i["message"])]

    def test_the_same_member_on_both_axes_is_flagged(self):
        found = self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Мелания"), CensusRole.WIFE, ref_member=1, age=38)',
            'member(3, person("Герасимъ"), None, ref_member=2, age="?", hidden=True, '
            'secondary_role=CensusRole.HUSBAND, secondary_ref_member=2)')
        self.assertEqual(len(found), 1, found)
        self.assertIn("member 3 (Герасимъ)", found[0])
        self.assertIn("spouse_member=2", found[0])

    def test_it_names_parent_member_when_the_role_is_not_marital(self):
        found = self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Макаръ"), CensusRole.SON, ref_member=1, age=45, '
            'secondary_role=CensusRole.SON, secondary_ref_member=1)')
        self.assertEqual(len(found), 1, found)
        self.assertIn("parent_member=1", found[0])

    def test_a_genuinely_additional_relationship_is_silent(self):
        """The shape the axis was built for: SON of the head per
        the roll, and SON of a hidden second wife per other materials."""
        self.assertEqual(self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Макаръ"), CensusRole.SON, ref_member=1, age=45, '
            'secondary_role=CensusRole.SON, secondary_ref_member=18)',
            'member(18, person("Ульяна"), CensusRole.WIFE, ref_member=1, '
            'age="?", hidden=True)'), [])

    def test_a_secondary_reference_with_no_ref_member_is_silent(self):
        """Twelve of the corpus's 36 carry no `ref_member` at all — there is
        nothing for the secondary reference to restate."""
        self.assertEqual(self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Макаръ"), CensusRole.SON, age=45, '
            'secondary_role=CensusRole.SON, secondary_ref_member=18)',
            'member(18, person("Ульяна"), CensusRole.WIFE, ref_member=1, '
            'age="?", hidden=True)'), [])

    def test_the_annotation_axes_are_never_flagged_by_it(self):
        """`spouse_member=N` beside `ref_member=N` is the PRESCRIBED shape."""
        self.assertEqual(self._codes(
            'member(1, person("Лукьянъ", "Макаровъ"), CensusRole.HEAD, age=78)',
            'member(2, person("Мелания"), CensusRole.WIFE, ref_member=1, age=38)',
            'member(3, person("Герасимъ"), None, ref_member=2, age="?", '
            'hidden=True, spouse_member=2)'), [])
def _census_two(first: list[str], second: list[str], year: int = 1816) -> str:
    """Two households in one census — the shape CPL009 exists for."""
    def hh(members: list[str], fam: str) -> str:
        body = ",\n        ".join(members)
        return f'    household(\n        {body},\n    family_id="{fam}"),\n'
    return (
        f'census = census_records("ГАТО", "1", "1", "2", "Горюхино", {year},\n'
        + hh(first, "1") + hh(second, "1в") + ")\n"
    )


class TestCpl009DanglingMemberRef(unittest.TestCase):
    """A member number that does not exist in its own household.

    Numbering is per household, so a household split, a renumbering or a
    copy-paste from the household next door leaves a reference pointing at
    nothing. The translator resolves it, fails to find the member and emits no
    union — a silent no-op the other six checks cannot see, because each of
    them reads the resolved TARGET.
    """

    @staticmethod
    def _codes(*members: str) -> list[str]:
        return [str(i["message"]) for i in _collect(*members)
                if "CPL009" in str(i["message"])]

    def test_parent_member_in_another_household_flagged(self):
        """A head of household «1» whose parent_member=16 names a member of
        household «1в»."""
        msgs = self._codes(
            'member(1, person("Прохор", "Леонтьев"), CensusRole.HEAD, age=66, parent_member=16)',
            'member(2, person("Ипат"), CensusRole.SON, ref_member=1, age=36)',
        )
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("member 1 (Прохор)", msgs[0])
        self.assertIn("parent_member=16", msgs[0])
        self.assertIn("it has 1-2", msgs[0])
        self.assertIn("father_ref", msgs[0])

    def test_dangling_ref_member_flagged(self):
        msgs = self._codes(
            'member(1, person("Евстигней", "Денисов"), CensusRole.HEAD, ref_member=16, age=71)',
        )
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("ref_member=16", msgs[0])

    def test_dangling_secondary_ref_member_flagged(self):
        msgs = self._codes(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Марья"), CensusRole.WIFE, ref_member=1, age=55, '
            'secondary_role=CensusRole.DAUGHTER, secondary_ref_member=9)',
        )
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("secondary_ref_member=9", msgs[0])

    def test_both_dangling_refs_are_reported_separately(self):
        msgs = self._codes(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Петръ"), CensusRole.SON, ref_member=8, age=30, parent_member=9)',
        )
        self.assertEqual(len(msgs), 2, msgs)
        self.assertTrue(any("ref_member=8" in m for m in msgs), msgs)
        self.assertTrue(any("parent_member=9" in m for m in msgs), msgs)

    def test_a_number_from_the_NEXT_household_is_still_dangling(self):
        """Member 16 exists in the file — in another household. That is the
        whole failure mode, so the check must not look past its own."""
        src = _census_two(
            ['member(1, person("Прохор", "Леонтьев"), CensusRole.HEAD, age=66, parent_member=16)'],
            ['member(1, person("Евстигней", "Денисов"), CensusRole.HEAD, ref_member=16, age=71)',
             'member(16, person("Денис"), None, age="?", hidden=True)'],
        )
        msgs = [str(i["message"]) for i in check._collect(ast.parse(src))
                if "CPL009" in str(i["message"])]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("parent_member=16", msgs[0])

    def test_in_household_references_are_silent(self):
        self.assertEqual(self._codes(
            'member(1, person("Прохоръ", "Леонтьевъ"), CensusRole.HEAD, age=66)',
            'member(2, person("Ипатъ"), CensusRole.SON, ref_member=1, age=36)',
            'member(3, person("Тарасъ"), CensusRole.SON, ref_member=2, age=6)'), [])

    def test_a_gap_in_the_numbering_is_not_a_dangling_ref(self):
        """Household numbering skips (a member dropped in an earlier edit); a
        reference to a number that IS present must stay silent, and the report
        shows the gap rather than a range."""
        msgs = self._codes(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=60)',
            'member(3, person("Петръ"), CensusRole.SON, ref_member=1, age=30, parent_member=2)')
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("it has 1, 3", msgs[0])

    def test_hidden_members_are_checked_too(self):
        """A reconstruction may be wired wrong like anything else."""
        msgs = self._codes(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Максимъ"), None, parent_member=7, hidden=True)')
        self.assertTrue(any("parent_member=7" in m for m in msgs), msgs)

    def test_pins_the_offending_kwarg(self):
        src = _census(
            'member(1, person("Прохор", "Леонтьев"), CensusRole.HEAD, age=66, parent_member=16)')
        issues = [i for i in check._collect(ast.parse(src), src.splitlines())
                  if "CPL009" in str(i["message"])]
        self.assertEqual(len(issues), 1, issues)
        line = src.splitlines()[int(issues[0]["line"]) - 1]
        self.assertEqual(line[int(issues[0]["col"]):int(issues[0]["end_col"])],
                         "parent_member=16")


class TestCpl010RepeatedMemberNumber(unittest.TestCase):
    """A number used twice in one household: the map keeps the last member, so
    the earlier one vanishes from every reference and every check."""

    @staticmethod
    def _msgs(*members: str) -> list[str]:
        return [str(i["message"]) for i in _collect(*members)
                if "CPL010" in str(i["message"])]

    def test_repeated_member_number_flagged(self):
        """A wife and a daughter are both № 18, another daughter is 19."""
        msgs = self._msgs(
            'member(5, person("Тихонъ"), CensusRole.SON, previous_age=9)',
            'member(18, person("Анна"), CensusRole.WIFE, ref_member=5, age=28)',
            'member(18, person("Аграфена"), CensusRole.DAUGHTER, ref_member=5, age=4)',
            'member(19, person("Ирина"), CensusRole.DAUGHTER, ref_member=5, age=2)',
        )
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("member 18 (Аграфена)", msgs[0])
        self.assertIn("member 18 (Анна)", msgs[0])

    def test_distinct_numbers_are_silent(self):
        self.assertEqual([], self._msgs(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=40)',
            'member(2, person("Марья"), CensusRole.WIFE, age=30)',
        ))

    def test_a_number_used_three_times_is_flagged_twice(self):
        self.assertEqual(2, len(self._msgs(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=40)',
            'member(1, person("Петръ"), CensusRole.SON, age=10)',
            'member(1, person("Павелъ"), CensusRole.SON, age=8)',
        )))

    def test_the_same_number_in_two_households_is_silent(self):
        """Numbering is per household — CPL009's premise, and this one's."""
        src = _census_two(
            ['member(1, person("Иванъ"), CensusRole.HEAD, age=40)'],
            ['member(1, person("Петръ"), CensusRole.HEAD, age=50)'])
        self.assertEqual([], [i for i in check._collect(ast.parse(src))
                              if "CPL010" in str(i["message"])])

    def test_pins_the_repeated_number(self):
        src = _census(
            'member(1, person("Иванъ"), CensusRole.HEAD, age=40)',
            'member(1, person("Петръ"), CensusRole.SON, age=10)')
        issues = [i for i in check._collect(ast.parse(src), src.splitlines())
                  if "CPL010" in str(i["message"])]
        self.assertEqual(len(issues), 1, issues)
        line = src.splitlines()[int(issues[0]["line"]) - 1]
        self.assertEqual("1", line[int(issues[0]["col"]):int(issues[0]["end_col"])])
        self.assertIn("Петр", line)


class TestCpl011HiddenParentPairedWithNoSpouse(unittest.TestCase):
    """The hidden-ancestor pass takes a hidden parent's ref_member as the second
    partner of his children's union — wrong wherever it names no spouse."""

    def _codes(self, *members: str) -> list[str]:
        return [str(i["message"]).split("]")[0] + "]" for i in _collect(*members)
                if "CPL011" in str(i["message"])]

    def test_absent_brother_pointing_at_the_head_flagged(self):
        """An absent brother pointing at the head makes the head the co-parent of the nephew."""
        issues = [i for i in _collect(
            'member(1, person("Гордѣй", "Лазаревъ"), CensusRole.HEAD, age=39)',
            'member(4, person("Мелетій", "Тарасовъ"), CensusRole.NEPHEW, ref_member=1, parent_member=9)',
            'member(9, person("Тарасъ"), CensusRole.BROTHER, ref_member=1, hidden=True)',
        ) if "CPL011" in str(i["message"])]
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("member 9 (Тарасъ)", msg)
        self.assertIn("member 1 (Гордѣй) the CO-PARENT", msg)
        self.assertIn("one sex", msg)

    def test_brother_with_a_widow_typed_as_brother_flagged(self):
        """A hidden member typed BROTHER with ref_member at the head: he marries
        his brother and takes the nephews along."""
        self.assertEqual(self._codes(
            'member(1, person("Аѳанасій", "Макаровъ"), CensusRole.HEAD, previous_age=48)',
            'member(2, person("Евграфъ", "Макаровъ"), CensusRole.BROTHER, ref_member=1, hidden=True, spouse_member=7)',
            'member(3, person("Ермолай", "Евграфовъ"), CensusRole.NEPHEW, ref_member=1, parent_member=2, age=22)',
            'member(7, person("Агафья", "Прохорова"), CensusRole.MOTHER, ref_member=3, age=52)',
        ), ["[CPL011]"])

    def test_dead_husband_wired_to_his_widow_is_silent(self):
        """The rule's own shape: role=None, ref_member and spouse_member at the widow."""
        self.assertEqual(self._codes(
            'member(1, person("Аѳанасій", "Макаровъ"), CensusRole.HEAD, previous_age=48)',
            'member(2, person("Евграфъ", "Макаровъ"), None, ref_member=7, hidden=True, spouse_member=7)',
            'member(3, person("Ермолай", "Евграфовъ"), CensusRole.NEPHEW, ref_member=1, parent_member=2, age=22)',
            'member(7, person("Агафья", "Прохорова"), CensusRole.MOTHER, ref_member=3, age=52)',
        ), [])

    def test_absent_brother_without_a_reference_is_silent(self):
        self.assertEqual(self._codes(
            'member(1, person("Пахомъ", "Ефремовъ"), CensusRole.HEAD, age=64)',
            'member(7, person("Ксенофонтъ", "Дорофеевъ"), CensusRole.NEPHEW, ref_member=1, parent_member=14, age=38)',
            'member(14, person("Дорофей"), CensusRole.BROTHER, hidden=True)',
        ), [])

    def test_hidden_father_pointing_at_the_mother_is_silent(self):
        """The corpus convention: the reference is his wife, the head's mother."""
        self.assertEqual(self._codes(
            'member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, parent_member=12, age=30)',
            'member(9, person("Марья"), CensusRole.MOTHER, ref_member=1, age=55)',
            'member(12, person("Петръ"), CensusRole.FATHER, ref_member=9, hidden=True)',
        ), [])

    def test_absent_brother_pointing_at_his_widow_is_silent(self):
        """A hidden BROTHER whose ref_member is the MOTHER of his children."""
        self.assertEqual(self._codes(
            'member(1, person("Тихонъ", "Ивановъ"), CensusRole.HEAD, age=41)',
            'member(2, person("Ермилъ", "Петровъ"), CensusRole.NEPHEW, ref_member=1, parent_member=9, age=13)',
            'member(8, person("Анна", "Лаврентьева"), CensusRole.MOTHER, ref_member=2, age=37)',
            'member(9, person("Петръ"), CensusRole.BROTHER, ref_member=8, hidden=True)',
        ), [])

    def test_sister_pointing_at_the_head_flagged_though_of_two_sexes(self):
        self.assertEqual(self._codes(
            'member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=30)',
            'member(3, person("Ѳедоръ"), CensusRole.NEPHEW, ref_member=1, parent_member=5, age=4)',
            'member(5, person("Марья", "Петрова"), CensusRole.SISTER, ref_member=1, hidden=True)',
        ), ["[CPL011]"])

    def test_declared_spouse_member_stands_it_down(self):
        self.assertEqual(self._codes(
            'member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=30)',
            'member(3, person("Ѳедоръ"), CensusRole.NEPHEW, ref_member=1, parent_member=5, age=4)',
            'member(5, person("Марья", "Петрова"), CensusRole.SISTER, ref_member=1, hidden=True, spouse_member=1)',
        ), [])


class TestNegativeMemberNumbers(unittest.TestCase):
    """A hidden member numbered -1, -2… parses as `UnaryOp(USub, Constant)`, not
    a Constant. Until 2026-10-12 such a member and every reference to it were
    invisible to all eleven checks: a household once married two hidden men
    to the head, and nothing reported it."""

    @staticmethod
    def _issues(code: str, *members: str) -> list[dict[str, object]]:
        src = _census(*members)
        return [i for i in check._collect(ast.parse(src), src.splitlines())
                if code in str(i["message"])]

    def test_hidden_men_paired_with_the_head_flagged(self):
        issues = self._issues(
            "CPL011",
            'member(1, person("Терентій", "Андреевъ"), CensusRole.HEAD, previous_age=52)',
            'member(29, person("Ермолай", "Карповъ"), CensusRole.NEPHEW, ref_member=1, age=23, parent_member=-1)',
            'member(30, person("Ксенія", "Онуфріева"), CensusRole.MOTHER, ref_member=29, age=56)',
            'member(34, person("Лукьянъ", "Леонтьевъ"), CensusRole.GRANDSON, ref_member=1, age=19, parent_member=-2)',
            'member(-1, person("Карпъ"), CensusRole.BROTHER, ref_member=1, hidden=True)',
            'member(-2, person("Леонтій"), CensusRole.LODGER, ref_member=1, hidden=True)')
        messages = sorted(str(i["message"]) for i in issues)
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("member -1 (Карпъ)", messages[0])
        self.assertIn("member -2 (Леонтій)", messages[1])

    def test_as_fixed_is_silent(self):
        """The shape of the fix: Карпъ at his widow, Леонтій a son, Андрей the
        hidden father of the brothers — negative numbers raise nothing."""
        self.assertEqual(self._issues(
            "CPL",
            'member(1, person("Терентій", "Андреевъ"), CensusRole.HEAD, previous_age=52, parent_member=-3)',
            'member(18, person("Авдей", "Андреевъ"), CensusRole.BROTHER, ref_member=1, age=57, parent_member=-3)',
            'member(29, person("Ермолай", "Карповъ"), CensusRole.NEPHEW, ref_member=1, age=23, parent_member=-1)',
            'member(30, person("Ксенія", "Онуфріева"), CensusRole.MOTHER, ref_member=29, age=56)',
            'member(34, person("Лукьянъ", "Леонтьевъ"), CensusRole.GRANDSON, ref_member=1, age=19, parent_member=-2)',
            'member(-1, person("Карпъ"), CensusRole.BROTHER, ref_member=30, parent_member=-3, hidden=True)',
            'member(-2, person("Леонтій"), CensusRole.SON, ref_member=1, hidden=True)',
            'member(-3, person("Андрей"), CensusRole.FATHER, hidden=True)'), [])

    def test_recorded_member_ref_at_a_negative_hidden_one_flagged(self):
        members = (
            'member(1, person("Артемій", "Исаевъ"), CensusRole.HEAD, age=74)',
            'member(30, person("Лазарь"), CensusRole.SON, ref_member=-1, age=17)',
            'member(-1, person("Прохоръ", "Артемьевъ"), CensusRole.SON, ref_member=1, hidden=True)')
        issues = self._issues("CPL006", *members)
        self.assertEqual(len(issues), 1, issues)
        line = _census(*members).splitlines()[int(issues[0]["line"]) - 1]
        self.assertEqual(line[int(issues[0]["col"]):int(issues[0]["end_col"])], "ref_member=-1")

    def test_dangling_negative_reference_flagged(self):
        issues = self._issues(
            "CPL009",
            'member(1, person("Иванъ"), CensusRole.HEAD, age=40)',
            'member(2, person("Петръ"), CensusRole.NEPHEW, ref_member=1, parent_member=-5, age=10)',
            'member(-1, person("Семенъ"), CensusRole.BROTHER, hidden=True)')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("parent_member=-5", str(issues[0]["message"]))
        self.assertIn("it has -1, 1-2)", str(issues[0]["message"]))

    def test_repeated_negative_number_flagged(self):
        self.assertEqual(len(self._issues(
            "CPL010",
            'member(1, person("Иванъ"), CensusRole.HEAD, age=40)',
            'member(2, person("Петръ"), CensusRole.SON, ref_member=-1, age=10)',
            'member(-1, person("Семенъ"), CensusRole.SON, ref_member=1, hidden=True)',
            'member(-1, person("Леонтій"), CensusRole.SON, ref_member=1, hidden=True)')), 1)


class TestCpl012PatronymicAgainstParent(unittest.TestCase):
    """A written patronymic that cannot come from the linked father."""

    @staticmethod
    def _issues(*members: str, lines: bool = False) -> list[dict[str, object]]:
        src = _census(*members)
        found = check._collect(ast.parse(src), src.splitlines() if lines else None)
        return [i for i in found if "CPL012" in str(i["message"])]

    def test_son_patronymic_against_ref_member_flagged(self):
        issues = self._issues(
            'member(1, person("Степанъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=35)',
            'member(3, person("Иванъ", "Петровъ"), CensusRole.SON, ref_member=2, age=8)')
        self.assertEqual(len(issues), 1, issues)
        msg = str(issues[0]["message"])
        self.assertIn("Член двора 3 (Иванъ)", msg)
        self.assertIn("«Петровъ»", msg)
        self.assertIn("«Андрей»", msg)
        self.assertIn("ref_member=2", msg)

    def test_parent_member_against_any_role_flagged(self):
        issues = self._issues(
            'member(1, person("Степанъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.SON, ref_member=1, age=35)',
            'member(3, person("Марья", "Тимофеева"), CensusRole.GRANDDAUGHTER, ref_member=1,'
            ' parent_member=2, age=8)')
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("parent_member=2", str(issues[0]["message"]))

    def test_parent_member_wins_over_ref_member(self):
        # The SON's ref_member is the head, his parent_member the father.
        self.assertEqual(self._issues(
            'member(1, person("Степанъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Андрей"), CensusRole.BROTHER, ref_member=1, age=35)',
            'member(3, person("Иванъ", "Андреевъ"), CensusRole.SON, ref_member=1,'
            ' parent_member=2, age=8)'), [])

    def test_agreeing_patronymic_silent(self):
        self.assertEqual(self._issues(
            'member(1, person("Андрѣй"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Андрѣевъ"), CensusRole.SON, ref_member=1, age=8)',
            'member(3, person("Марья", "Андреевна"), CensusRole.DAUGHTER, ref_member=1, age=6)'), [])

    def test_one_father_written_two_ways_silent(self):
        # «Егоръ» and «Георгій» are one name to the names table.
        self.assertEqual(self._issues(
            'member(1, person("Егоръ"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Георгіевъ"), CensusRole.SON, ref_member=1, age=8)'), [])

    def test_name_the_table_lacks_agrees_by_stem(self):
        self.assertEqual(self._issues(
            'member(1, person("Будила"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Будиловъ"), CensusRole.SON, ref_member=1, age=8)'), [])

    def test_mother_names_no_patronymic(self):
        # «дѣти ея»: the widow is the reference, the patronymic her husband's.
        self.assertEqual(self._issues(
            'member(1, person("Степанъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Марья"), CensusRole.DAUGHTER_IN_LAW, ref_member=1, age=35)',
            'member(3, person("Иванъ", "Петровъ"), CensusRole.SON, ref_member=2, age=8)'), [])

    def test_head_by_default_and_other_roles_by_ref_silent(self):
        # No reference: the head's son by default — out of the rule; a stepson's
        # reference is his stepfather, a nephew's an anchor.
        self.assertEqual(self._issues(
            'member(1, person("Степанъ"), CensusRole.HEAD, age=60)',
            'member(2, person("Иванъ", "Петровъ"), CensusRole.SON, age=30)',
            'member(3, person("Федоръ", "Петровъ"), CensusRole.STEPSON, ref_member=1, age=10)',
            'member(4, person("Андрей", "Петровъ"), CensusRole.NEPHEW, ref_member=2, age=5)'), [])

    def test_patr_old_reading_silences(self):
        self.assertEqual(self._issues(
            'member(1, person("Андрей"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Петровъ", patr_old="Андреев"), CensusRole.SON,'
            ' ref_member=1, age=8)'), [])

    def test_illegible_and_missing_silent(self):
        self.assertEqual(self._issues(
            'member(1, person("Андрей"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Пет?овъ"), CensusRole.SON, ref_member=1, age=8)',
            'member(3, person("Федоръ", "Петровъ"), CensusRole.SON, ref_member=9, age=6)',
            'member(4, person("Степанъ"), CensusRole.SON, ref_member=1, age=4)'), [])

    def test_pinned_on_the_reference(self):
        issues = self._issues(
            'member(1, person("Андрей"), CensusRole.HEAD, age=40)',
            'member(2, person("Иванъ", "Петровъ"), CensusRole.SON, ref_member=1, age=8)',
            lines=True)
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("col", issues[0])
        self.assertEqual(issues[0]["message"].token, "Петровъ")  # type: ignore[attr-defined]


class TestFormatNumbers(unittest.TestCase):
    def test_spans(self):
        self.assertEqual(check.format_numbers([1, 2, 3, 4, 5, 6, 7]), "1-7")
        self.assertEqual(check.format_numbers([1, 3]), "1, 3")
        self.assertEqual(check.format_numbers([1, 2, 3, 5, 7, 8]), "1-3, 5, 7-8")
        self.assertEqual(check.format_numbers([4]), "4")
        self.assertEqual(check.format_numbers([]), "none")

    def test_negative_numbers_are_listed_one_by_one(self):
        """«-3--1» would read as nonsense; a hidden member's number stands alone."""
        self.assertEqual(check.format_numbers([-3, -2, -1, 1, 2]), "-3, -2, -1, 1-2")


class TestCpl012UnknownPatronymic(unittest.TestCase):
    def test_a_patronymic_the_lexicon_lacks_is_no_crash_and_no_finding(self):
        """The lexicon cannot canonicalize a patronymic it does not hold, and asking raises: the linter says nothing of
        the patronymic's agreement with the father (the names linter says the patronymic is unknown), never fails on it."""
        issues = _collect(
            'member(1, person("Иванъ", "Нетакоговъ"), CensusRole.HEAD, age=66)',
            'member(2, person("Петръ", "Неведомовъ"), CensusRole.SON, ref_member=1, age=44)',
        )
        self.assertEqual([i for i in issues if "CPL012" in str(i["message"])], [])
