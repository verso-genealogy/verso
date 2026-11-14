import inspect
import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.parent_member as check_parent_member
from verso.ru.dsl.records import census


class TestCheckParentMember(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_parent_member.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def test_parent_member_equal_to_ref_member_flagged(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(6, person("Иван"), CensusRole.SON, 4, '
            "ref_member=5, parent_member=5)\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1)
        self.assertIn("redundant", errors[0])
        self.assertIn("parent_member=5", errors[0])

    def test_parent_member_differs_from_ref_member_ok(self):
        # parent_member pointing at a DIFFERENT member is meaningful
        # (e.g. a step-child whose ref_member is the step-parent).
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(4, person("Агафья"), CensusRole.STEPDAUGHTER, 9, '
            "ref_member=2, parent_member=17)\n"
        )
        self.assertEqual(self._check(src), [])

    def test_ref_member_only_ok(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(6, person("Иван"), CensusRole.SON, 4, ref_member=5)\n'
        )
        self.assertEqual(self._check(src), [])

    def test_parent_member_only_ok(self):
        # parent_member alone (no ref_member) is the only parent link —
        # not redundant.
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(6, person("Иван"), CensusRole.SON, 4, '
            "parent_member=5)\n"
        )
        self.assertEqual(self._check(src), [])

    def test_no_parent_member_ok(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(1, person("Пётр"), CensusRole.HEAD, 50)\n'
        )
        self.assertEqual(self._check(src), [])

    def test_censusmember_call_also_checked(self):
        src = (
            "from census import CensusRole, CensusMember\n"
            "from genealogy import person\n"
            'm = CensusMember(7, person("Николай"), CensusRole.SON, 1, '
            "ref_member=3, parent_member=3)\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1)
        self.assertIn("redundant", errors[0])

    def test_grandson_parent_member_equal_to_ref_member_ok(self):
        # For non-child roles ref_member is NOT the parent (translator's
        # _resolve_parent_ref), so an equal parent_member is load-bearing —
        # the 1897 посемейные списки shape (GRANDSON whose ref IS the father).
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(10, person("Александр", "Иванов"), CensusRole.GRANDSON, 7, '
            "ref_member=3, parent_member=3)\n"
        )
        self.assertEqual(self._check(src), [])

    def test_nephew_parent_member_equal_to_ref_member_ok(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(4, person("Григорий"), CensusRole.NEPHEW, 2, '
            "ref_member=3, parent_member=3)\n"
        )
        self.assertEqual(self._check(src), [])

    # --- PM002: married-in spouse sharing the partner's parent ---

    def test_wife_sharing_husbands_explicit_parent_flagged(self):
        # Husband is a GRANDSON with explicit parent_member=19; the wife was
        # mistakenly given the same parent, making her a child of her own
        # father-in-law (the real Пелагея/Самоварина bug).
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "household(\n"
            '  member(11, person("Яков"), CensusRole.GRANDSON, 23, '
            "ref_member=2, parent_member=19),\n"
            '  member(17, person("Пелагея"), CensusRole.WIFE, 25, '
            "ref_member=11, parent_member=19),\n"
            '  member(19, person("Михаил"), CensusRole.SON, 50, ref_member=2),\n'
            ")\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PM002", errors[0])
        self.assertIn("parent_member=19", errors[0])

    def test_wife_sharing_husbands_ref_member_parent_flagged(self):
        # Husband is a SON (ref_member IS the parent); wife points at that same
        # head — she'd become her father-in-law's child.
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "household(\n"
            '  member(1, person("Иван"), CensusRole.HEAD, 60),\n'
            '  member(2, person("Пётр"), CensusRole.SON, 30, ref_member=1),\n'
            '  member(3, person("Анна"), CensusRole.WIFE, 28, '
            "ref_member=2, parent_member=1),\n"
            ")\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PM002", errors[0])

    def test_uxorilocal_wife_points_at_own_father_ok(self):
        # Husband married in (SON_IN_LAW), so he has no parent in this
        # household; the wife correctly points at her own father, the head.
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "household(\n"
            '  member(1, person("Тимофей"), CensusRole.HEAD, 61),\n'
            '  member(2, person("Перфил"), CensusRole.SON_IN_LAW, 46),\n'
            '  member(3, person("Татьяна"), CensusRole.WIFE, 46, '
            "ref_member=2, parent_member=1),\n"
            ")\n"
        )
        self.assertEqual(self._check(src), [])

    def test_wife_with_distinct_parent_member_ok(self):
        # Wife's parent (member 19) differs from her husband's parent (member
        # 2) — a normal cross-household parent link, not the bug.
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "household(\n"
            '  member(7, person("Сергей"), CensusRole.SON, 30, '
            "ref_member=1, parent_member=2),\n"
            '  member(17, person("Ульяна"), CensusRole.WIFE, 22, '
            "ref_member=7, parent_member=19),\n"
            ")\n"
        )
        self.assertEqual(self._check(src), [])

    # --- a hidden member numbered -1, -2… (parses as a negated literal) ---

    def test_negative_parent_member_equal_to_ref_member_flagged(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(6, person("Иван"), CensusRole.SON, '
            "ref_member=-1, parent_member=-1)\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("parent_member=-1", errors[0])

    def test_wife_sharing_husbands_negative_parent_flagged(self):
        # The husband's parent is a hidden member numbered -1.
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "household(\n"
            '  member(1, person("Иван"), CensusRole.HEAD, 60),\n'
            '  member(2, person("Пётр"), CensusRole.GRANDSON, 30, '
            "ref_member=1, parent_member=-1),\n"
            '  member(3, person("Анна"), CensusRole.WIFE, 28, '
            "ref_member=2, parent_member=-1),\n"
            '  member(-1, person("Михаил"), CensusRole.SON, ref_member=1, hidden=True),\n'
            ")\n"
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PM002", errors[0])
        self.assertIn("parent_member=-1", errors[0])



def test_the_positions_read_are_the_factories():
    """`ROLE_AT`, `REF_MEMBER_AT` and `PARENT_MEMBER_AT` are the places of those parameters in `member()` and
    `CensusMember`: a reordered signature fails here, not as a silent misreading."""
    for factory in (census.member, census.CensusMember):
        names = list(inspect.signature(factory).parameters)
        assert (names.index("role"), names.index("ref_member"), names.index("parent_member")) == (
            check_parent_member.ROLE_AT, check_parent_member.REF_MEMBER_AT, check_parent_member.PARENT_MEMBER_AT)


class TestPositionalReference(TestCheckParentMember):
    def test_positional_ref_member_equal_to_parent_member_flagged(self):
        src = (
            "from census import CensusRole, member\n"
            "from genealogy import person\n"
            'm = member(6, person("Иван"), CensusRole.SON, 5, parent_member=5)\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("parent_member=5", errors[0])

    def test_positional_ref_member_of_a_wife_sharing_her_husbands_parent_flagged(self):
        src = (
            "from census import CensusRole, household, member\n"
            "from genealogy import person\n"
            "h = household(\"1\",\n"
            '    member(1, person("Лука"), CensusRole.HEAD),\n'
            '    member(2, person("Иван"), CensusRole.SON, 1),\n'
            '    member(3, person("Анна"), CensusRole.WIFE, 2, parent_member=1))\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PM002", errors[0])


if __name__ == "__main__":
    unittest.main()
