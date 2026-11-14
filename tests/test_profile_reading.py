"""The shared reading of a generated profile, and the guard that keeps it one.

The functions themselves are exercised where they are used
(`tests/test_age_conflicts.py`, `tests/test_union_duplicates.py`). What this
file pins is the arrangement: that every check reads through the one module,
and that the ONE renderer which is not a duplicate stays where it is.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from verso.ru.consolidation import estate_conflicts, profile_reading
from verso.core.targets.geni.profile import GeniProfile
from tests.codepaths import package_dir

_CONSOLIDATION = package_dir("verso.ru.consolidation")

#: Names that must have exactly one definition in the package. Spelled with and
#: without the underscore because the whole shape this guard exists to prevent
#: was a name that looked private and was imported by two neighbours anyway.
_SHARED = frozenset({
    "birth_year", "birth_year_latest", "birth_is_approximate", "death_year",
    "display_name", "_display_name", "partner_refs", "_partner_refs",
})

#: The one definition outside `profile_reading.py` that is allowed, because it
#: is a different function under a similar name — see the class below.
_EXEMPT = {("estate_conflicts.py", "_display_name")}


def walked() -> list[Path]:
    """The package's modules the guard reads."""
    return sorted(_CONSOLIDATION.glob("*.py"))


def _profile(res_name: str, **kw: object) -> GeniProfile:
    return GeniProfile(res_name=res_name, **kw)  # pyright: ignore[reportArgumentType]


class OneDefinitionEach(unittest.TestCase):
    def test_no_check_keeps_its_own_copy(self):
        found: set[tuple[str, str]] = set()
        self.assertGreaterEqual(len(walked()), 20, "modules of verso.ru.consolidation found")
        for path in walked():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in _SHARED:
                    found.add((path.name, node.name))
        stray = {f for f in found
                 if f[0] != "profile_reading.py" and f not in _EXEMPT}
        self.assertEqual(set(), stray,
                         "a check defined its own copy of a shared reader; "
                         "import it from verso.ru.consolidation.profile_reading "
                         "instead, or name the exemption here and say why")

    def test_the_shared_module_defines_them_all(self):
        """A guard that passes because the module is empty proves nothing."""
        for name in ("birth_year", "birth_year_latest", "birth_is_approximate",
                     "death_year", "display_name", "partner_refs"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(profile_reading, name)))


class TwoRenderersAreNotOne(unittest.TestCase):
    """`estate_conflicts._display_name` is not a duplicate of `display_name`.

    It looks like one, and the next reader's instinct will be to fold it in.
    On a man with a surname the two agree, which is why the resemblance is
    convincing; they part on exactly two shapes, and this corpus is full of
    both. Folding them would change a committed report, which is why the
    exemption above is named rather than silent.
    """

    def test_they_agree_on_a_man_with_a_surname(self):
        """Where the resemblance comes from."""
        profile = _profile("ivan_petrovich_kuzovkin", first_name="Иванъ",
                           middle_name="Петровъ", last_name="Кузовкинъ")
        self.assertEqual("Иванъ Петровъ Кузовкинъ",
                         estate_conflicts._display_name(profile))
        self.assertEqual("Иванъ Петровъ Кузовкинъ",
                         profile_reading.display_name(profile))

    def test_they_part_on_a_maiden_surname(self):
        """`full_name` reads `last_name` OR `birth_last_name`; the estate
        renderer reads only `last_name`, so an unmarried woman loses hers."""
        profile = _profile("marja_ivanovna_kuzovkina", first_name="Марья",
                           middle_name="Ивановна", birth_last_name="Кузовкина")
        self.assertEqual("Марья Ивановна",
                         estate_conflicts._display_name(profile))
        self.assertEqual("Марья Ивановна Кузовкина",
                         profile_reading.display_name(profile))

    def test_they_part_on_a_nameless_profile(self):
        """An implied-parent stub: «?» against an address a reader can find."""
        profile = _profile("head_of_family_7_1850")
        self.assertEqual("?", estate_conflicts._display_name(profile))
        self.assertEqual("head_of_family_7_1850",
                         profile_reading.display_name(profile))


class PartnerRefsReadsSlotsInOrder(unittest.TestCase):
    def test_a_single_partner_union_is_ordinary(self):
        """A mother recorded without her husband, and every implied-parent
        stub — the empty slot is skipped, not an error."""
        class _U:
            partner_1 = "mother"
            partner_2 = None
        self.assertEqual(["mother"], profile_reading.partner_refs(_U()))

    def test_both_slots_keep_their_order(self):
        class _U:
            partner_1 = "husband"
            partner_2 = "wife"
        self.assertEqual(["husband", "wife"], profile_reading.partner_refs(_U()))

    def test_a_union_with_no_partners_reads_empty(self):
        self.assertEqual([], profile_reading.partner_refs(object()))


if __name__ == "__main__":
    unittest.main()
