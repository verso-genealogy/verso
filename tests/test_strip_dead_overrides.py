"""Tests for the ROV001 codemod.

Removing a no-op override is output-neutral by definition, so the codemod is
purely a source rewrite: delete the named kwargs, delete the whole `override`
entry when it empties, and refuse anything it cannot edit safely.
"""
import ast
import unittest

from verso.ru.consolidation.strip_dead_overrides import strip_dead_overrides


CONFIG = '''\
from verso.core.targets.geni import GeniProfile

profiles_to_consolidate = {
    "savva_fedorovich": {
        "profile_names": [
            "_1831_04_13_savva_fedorovich_mk_births_15_child",
        ],
        "override": GeniProfile(
            first_name="Савелий",
            current_residence="село Горюхино",
        ),
    },
    "irina_kirillovna": {
        "profile_names": [
            "_1849_04_25_irina_kirillovna_mk_marriages_8_bride",
        ],
        "override": GeniProfile(
            current_residence="село Горюхино",
        ),
    },
}
'''


class StripsNamedKwargs(unittest.TestCase):
    def test_removes_only_the_named_field(self):
        out, skipped = strip_dead_overrides(
            CONFIG, {"savva_fedorovich": {"current_residence"}})

        self.assertIn('            first_name="Савелий",\n', out)
        # savva's residence line is gone; irina's identical line survives.
        self.assertEqual(out.count('current_residence="село Горюхино",'), 1)
        self.assertEqual(skipped, [])

    def test_removes_the_whole_override_when_it_empties(self):
        out, _ = strip_dead_overrides(
            CONFIG, {"irina_kirillovna": {"current_residence"}})

        # irina's override block is gone entirely...
        self.assertEqual(out.count('"override": GeniProfile('), 1)
        # ...while the cluster itself and its neighbour survive.
        self.assertIn('"irina_kirillovna": {', out)
        self.assertIn('"savva_fedorovich": {', out)
        self.assertIn(
            '"_1849_04_25_irina_kirillovna_mk_marriages_8_bride",', out)

    def test_untargeted_clusters_are_byte_identical(self):
        out, _ = strip_dead_overrides(
            CONFIG, {"irina_kirillovna": {"current_residence"}})

        self.assertIn('        "override": GeniProfile(\n'
                      '            first_name="Савелий",\n'
                      '            current_residence="село Горюхино",\n'
                      '        ),', out)

    def test_is_idempotent(self):
        once, _ = strip_dead_overrides(
            CONFIG, {"savva_fedorovich": {"current_residence"}})
        twice, _ = strip_dead_overrides(
            once, {"savva_fedorovich": {"current_residence"}})

        self.assertEqual(once, twice)

    def test_result_still_parses(self):
        out, _ = strip_dead_overrides(
            CONFIG, {"savva_fedorovich": {"current_residence"},
                     "irina_kirillovna": {"current_residence"}})

        ast.parse(out)   # raises SyntaxError if the rewrite corrupted it


class RefusesWhatItCannotEditSafely(unittest.TestCase):
    SINGLE_LINE = '''\
from verso.core.targets.geni import GeniProfile

profiles_to_consolidate = {
    "one_liner": {
        "override": GeniProfile(first_name="Иван", last_name="Марков"),
    },
}
'''

    def test_single_line_override_is_skipped_not_corrupted(self):
        out, skipped = strip_dead_overrides(
            self.SINGLE_LINE, {"one_liner": {"first_name"}})

        self.assertEqual(out, self.SINGLE_LINE)   # untouched
        self.assertEqual(len(skipped), 1)
        self.assertIn("one_liner", skipped[0])


class IgnoresNonProfileDicts(unittest.TestCase):
    """ROV001 covers profile overrides only. `unions_to_consolidate` has its
    own `override` hint with different semantics — the codemod must not reach
    into it even when a key name collides."""

    WITH_UNIONS = '''\
from verso.core.targets.geni import GeniProfile
from verso.core.targets.geni import GeniUnion

profiles_to_consolidate = {
    "collide": {
        "override": GeniProfile(
            first_name="Иван",
        ),
    },
}

unions_to_consolidate = {
    "collide": {
        "override": GeniUnion(
            first_name="Иван",
        ),
    },
}
'''

    def test_union_override_is_left_alone(self):
        out, _ = strip_dead_overrides(
            self.WITH_UNIONS, {"collide": {"first_name"}})

        self.assertNotIn("GeniProfile(", out)      # profile side stripped
        self.assertIn("GeniUnion(\n            first_name=\"Иван\",\n        ),",
                      out)                          # union side untouched


if __name__ == "__main__":
    unittest.main()
