#!/usr/bin/env python3
"""Unit tests for check_consolidation_config.py.

Each test feeds a synthetic generate_config_names.py-shaped source through
the linter and asserts which CCN codes fire. Fixtures are derived from real
defects (CCN001 from a duplicated cluster, CCN006 from the maiden_name=
regression, etc.).
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


from verso.ru.consolidation.lint_config import Finding, lint_file


def _write_and_lint(src: str) -> list[Finding]:
    src = textwrap.dedent(src).lstrip("\n")
    with TemporaryDirectory() as d:
        path = Path(d) / "fixture.py"
        path.write_text(src, encoding="utf-8")
        return lint_file(path)


def _codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


CLEAN_PRELUDE = """
    from geni_profile import GeniProfile
    from geni_event import GeniEvent
    from geni_date import GeniDate

    profiles_to_consolidate = {
"""


class CCN001DuplicateCanonicalKey(unittest.TestCase):
    def test_two_clusters_share_a_key(self):
        src = CLEAN_PRELUDE + """
            "pelageja_mihajlovna": {
                "profile_names": ["_1850_05_01_pelageja_mihajlovna_mk_births_1_mother"],
            },
            "pelageja_mihajlovna": {
                "profile_names": ["_1853_05_01_pelageja_mihajlovna_mk_births_2_mother"],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN001"])
        self.assertIn("pelageja_mihajlovna", findings[0].message)

    def test_no_duplicates_passes(self):
        src = CLEAN_PRELUDE + """
            "pelageja_mihajlovna": {"profile_names": ["_a_b_c"]},
            "pelageja_mihajlovna_2": {"profile_names": ["_a_b_d"]},
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])


class CCN002CrossClusterDuplicateStub(unittest.TestCase):
    def test_same_stub_in_two_clusters(self):
        src = CLEAN_PRELUDE + """
            "anna": {"profile_names": ["_1800_01_01_anna_mk_births_1_child"]},
            "anna_2": {"profile_names": ["_1800_01_01_anna_mk_births_1_child"]},
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN002"])

    def test_stub_as_own_key_also_in_another_cluster(self):
        # Regression: a stub used as its own canonical key (legacy solo entry)
        # while also listed in a proper named canonical.
        # CCN008 fires first (self-reference canonical key in profile_names),
        # then CCN002 fires (same stub reused across clusters).
        src = CLEAN_PRELUDE + """
            "_1800_01_01_anna_mk_births_1_child": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
            },
            "anna": {"profile_names": ["_1800_01_01_anna_mk_births_1_child"]},
        }
        """
        findings = _write_and_lint(src)
        self.assertIn("CCN002", _codes(findings))
        self.assertIn("CCN008", _codes(findings))


class CCN003WithinClusterDuplicateStub(unittest.TestCase):
    def test_same_stub_listed_twice(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": [
                    "_1800_01_01_anna_mk_births_1_child",
                    "_1800_01_01_anna_mk_births_1_child",
                ],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN003"])


class CCN004ProfileNamesMissingOrMalformed(unittest.TestCase):
    def test_missing_profile_names_key(self):
        src = CLEAN_PRELUDE + """
            "anna": {"override": GeniProfile()},
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN004"])

    def test_empty_profile_names_list(self):
        src = CLEAN_PRELUDE + """
            "anna": {"profile_names": []},
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN004"])

    def test_non_string_in_profile_names(self):
        src = CLEAN_PRELUDE + """
            "anna": {"profile_names": [123]},
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN004"])

    def test_cluster_value_not_a_dict(self):
        src = CLEAN_PRELUDE + """
            "anna": [],
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN004"])


class CCN005UnknownSchemaKey(unittest.TestCase):
    def test_typo_key_in_profile_cluster(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "additionall_info": [GeniProfile()],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN005"])
        self.assertIn("additionall_info", findings[0].message)

    def test_known_keys_pass(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "additional_info": [GeniProfile(birth_last_name="Кувшинникова")],
                "override": GeniProfile(),
                "preference": GeniProfile(first_name="Анна"),
                "ignore": ["foo"],
                "generate_moved_block": True,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])

    def test_union_schema_typo(self):
        src = """
            from geni_profile import GeniProfile

            profiles_to_consolidate = {}

            unions_to_consolidate = {
                "u1": {
                    "union_names": ["x"],
                    "undocumented_kid": "foo",
                },
            }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN005"])
        self.assertIn("undocumented_kid", findings[0].message)


class CCN006InvalidGeniProfileKwarg(unittest.TestCase):
    def test_maiden_name_is_flagged_with_fix(self):
        # Direct regression case.
        src = CLEAN_PRELUDE + """
            "evdokija": {
                "profile_names": ["_1900_01_01_evdokija_mk_births_1_mother"],
                "additional_info": [GeniProfile(maiden_name="Пузырькина")],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN006"])
        self.assertIn("birth_last_name", findings[0].message)

    def test_unknown_kwarg_without_fix(self):
        src = CLEAN_PRELUDE + """
            "evdokija": {
                "profile_names": ["_1900_01_01_evdokija_mk_births_1_mother"],
                "override": GeniProfile(unknown_field="x"),
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN006"])

    def test_positional_arg_to_geni_profile(self):
        src = CLEAN_PRELUDE + """
            "evdokija": {
                "profile_names": ["_1900_01_01_evdokija_mk_births_1_mother"],
                "override": GeniProfile("res_name_value"),
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN006"])
        self.assertIn("positional", findings[0].message)

    def test_nested_geni_profile_inside_additional_info_list(self):
        # Ensure ast.walk finds GeniProfile nested in [GeniProfile(...)].
        src = CLEAN_PRELUDE + """
            "evdokija": {
                "profile_names": ["_1900_01_01_evdokija_mk_births_1_mother"],
                "additional_info": [
                    GeniProfile(birth_last_name="ok"),
                    GeniProfile(maiden_name="bad"),
                ],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN006"])


class CCN007GenerateMovedBlockType(unittest.TestCase):
    def test_string_not_allowed(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "generate_moved_block": "yes",
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN007"])

    def test_true_passes(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "generate_moved_block": True,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])


class TopLevelMissingProfilesVar(unittest.TestCase):
    def test_file_without_profiles_to_consolidate(self):
        src = """
            x = 1
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN000"])


class CCN008CanonicalKeyInNamesList(unittest.TestCase):
    """A names-list entry must never equal another canonical key; a cluster's
    OWN key is exempt only in a single-element passthrough list."""

    def test_ccn008_single_element_self_reference_is_clean(self):
        """A single-element passthrough (key is its own sole stub) is exempt —
        CSV-only villages (e.g. Заманиловка) may use a raw stub as the canonical key."""
        src = CLEAN_PRELUDE + """
            "ivan_ivanovich_petrov": {
                "profile_names": ["ivan_ivanovich_petrov"],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual([f for f in findings if f.code == "CCN008"], [])

    def test_ccn008_multi_element_self_reference_flagged(self):
        """A cluster merging 2+ stubs must use a new synthetic key, not its own raw stub."""
        src = CLEAN_PRELUDE + """
            "ivan_ivanovich_petrov": {
                "profile_names": [
                    "_1850_births_ivan_mk_1_child",
                    "ivan_ivanovich_petrov",
                ],
            },
        }
        """
        findings = _write_and_lint(src)
        ccn008 = [f for f in findings if f.code == "CCN008"]
        self.assertGreaterEqual(len(ccn008), 1, f"Expected CCN008, got: {findings}")
        self.assertIn("ivan_ivanovich_petrov", ccn008[0].message)

    def test_ccn008_profile_cross_reference(self):
        """profile_names that lists another cluster's canonical key is an error (forward ref too)."""
        src = CLEAN_PRELUDE + """
            "nikolaj_epifanovich_tjufjakin": {
                "profile_names": ["_some_real_stub"],
            },
            "nikolaj_epifanovich_tjufjakin_and_anisja_ivanovna_tjufjakina": {
                "profile_names": ["nikolaj_epifanovich_tjufjakin"],
            },
        }
        """
        findings = _write_and_lint(src)
        ccn008 = [f for f in findings if f.code == "CCN008"]
        self.assertGreaterEqual(len(ccn008), 1, f"Expected CCN008, got: {findings}")
        self.assertIn("nikolaj_epifanovich_tjufjakin", ccn008[0].message)
        # cluster key should appear in the message too
        self.assertIn("nikolaj_epifanovich_tjufjakin_and_anisja_ivanovna_tjufjakina", ccn008[0].message)

    def test_ccn008_single_element_union_self_reference_is_clean(self):
        """A single-element union passthrough (key is its own sole stub) is exempt."""
        src = """
            from geni_profile import GeniProfile

            profiles_to_consolidate = {}

            unions_to_consolidate = {
                "trofim_nikitich_sundukin_and_marija_galaktionovna_sundukina": {
                    "union_names": ["trofim_nikitich_sundukin_and_marija_galaktionovna_sundukina"],
                },
            }
        """
        findings = _write_and_lint(src)
        self.assertEqual([f for f in findings if f.code == "CCN008"], [])

    def test_ccn008_multi_element_union_self_reference_flagged(self):
        """A union merging 2+ stubs must use a new synthetic key, not its own raw stub."""
        src = """
            from geni_profile import GeniProfile

            profiles_to_consolidate = {}

            unions_to_consolidate = {
                "trofim_nikitich_sundukin_and_marija_galaktionovna_sundukina": {
                    "union_names": [
                        "_raw_union_stub",
                        "trofim_nikitich_sundukin_and_marija_galaktionovna_sundukina",
                    ],
                },
            }
        """
        findings = _write_and_lint(src)
        ccn008 = [f for f in findings if f.code == "CCN008"]
        self.assertGreaterEqual(len(ccn008), 1, f"Expected CCN008, got: {findings}")
        self.assertIn("trofim_nikitich_sundukin_and_marija_galaktionovna_sundukina", ccn008[0].message)

    def test_ccn008_clean_does_not_flag(self):
        """Raw source stubs (not matching any canonical key) produce no CCN008."""
        src = """
            from geni_profile import GeniProfile

            profiles_to_consolidate = {
                "ivan_ivanovich_petrov": {
                    "profile_names": ["_1850_births_ivan_mk_1_child"],
                },
                "petr_sidorovich_ivanov": {
                    "profile_names": ["_1851_births_petr_mk_2_child"],
                },
            }

            unions_to_consolidate = {
                "ivan_and_anna": {
                    "union_names": ["_union_stub_1"],
                },
            }
        """
        findings = _write_and_lint(src)
        ccn008 = [f for f in findings if f.code == "CCN008"]
        self.assertEqual(ccn008, [], f"Expected no CCN008, got: {ccn008}")


class CCN009ProfileNamesNotSorted(unittest.TestCase):
    def test_unsorted_list_is_flagged(self):
        src = CLEAN_PRELUDE + """
            "ivan_petrovich": {
                "profile_names": [
                    "_1840_05_01_ivan_petrovich_mk_births_2_father",
                    "_1838_01_01_ivan_petrovich_mk_births_1_child",
                ],
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN009"])

    def test_sorted_list_passes(self):
        src = CLEAN_PRELUDE + """
            "ivan_petrovich": {
                "profile_names": [
                    "_1838_01_01_ivan_petrovich_mk_births_1_child",
                    "_1840_05_01_ivan_petrovich_mk_births_2_father",
                ],
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])

    def test_single_element_passes(self):
        src = CLEAN_PRELUDE + """
            "ivan_petrovich": {"profile_names": ["_1838_01_01_ivan_petrovich_mk_births_1_child"]},
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])


if __name__ == "__main__":
    unittest.main()


class TestCcn010NicknameDuplicatesSurname(unittest.TestCase):
    """CCN010: a nickname must not repeat last_name / birth_last_name.

    `preference` pins the KEPT value per field; a dropped variant becomes a
    `nicknames` alias. A value carried by BOTH is a contradiction — Geni then
    renders the surname twice, e.g.
        last_name = "Ахинеева"; birth_last_name = "Нюхина"
        nicknames = ["Ахинеева", "Нюхина"]
    When the dropped value is already represented by another name field, the
    right tool is `ignore`, not a nickname.
    """

    def _codes(self, src: str) -> list[str]:
        return [f.code for f in _write_and_lint(src)]

    def test_nickname_equal_to_last_name_flagged(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "feodosija_sergeevna_ahineeva": {
                    "profile_names": ["_1836_05_25_a_mk_births_15_child"],
                    "preference": GeniProfile(last_name="Ахинеева", nicknames=["Ахинеева"]),
                },
            }
        ''')
        self.assertIn("CCN010", codes)

    def test_nickname_equal_to_birth_last_name_flagged(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "natalja_kuvshinnikova": {
                    "profile_names": ["_1842_01_01_a_mk_marriages_1_bride"],
                    "preference": GeniProfile(
                        last_name="Кувшинникова",
                        birth_last_name="Неумехина",
                        nicknames=["Кувшиникова", "Неумехина"],
                    ),
                },
            }
        ''')
        self.assertIn("CCN010", codes)

    def test_genuine_aliases_are_clean(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "natalja_kuvshinnikova": {
                    "profile_names": ["_1842_01_01_a_mk_marriages_1_bride"],
                    "preference": GeniProfile(
                        last_name="Кувшинникова",
                        birth_last_name="Неумехина",
                        nicknames=["Кувшиникова", "Анастасия"],
                    ),
                },
            }
        ''')
        self.assertNotIn("CCN010", codes)

    def test_no_nicknames_is_clean(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "feodosija_sergeevna_ahineeva": {
                    "profile_names": ["_1836_05_25_a_mk_births_15_child"],
                    "preference": GeniProfile(last_name="Ахинеева", birth_last_name="Нюхина"),
                },
            }
        ''')
        self.assertNotIn("CCN010", codes)


class TestCcn011PreferenceIgnoreCollision(unittest.TestCase):
    """CCN011: `ignore` must not list the value its own `preference` pins.

    The two keys pull in opposite directions on the same field. `preference`
    says "keep THIS value"; `ignore` says "drop this value wherever it is
    seen" — and the generator's seed scrub runs AFTER `_apply_preference`, so
    an `ignore` naming the pinned value blanks it on the seed record. The next
    record carrying the *rejected* variant then fills the blank and sticks,
    which is the exact inverse of what the config asks for.

    Observed live: `andrej_ignatievich_groshikov` carried
    `preference(middle_name="Игнатиевич", nicknames=["Гордеевич"])` alongside
    `ignore=[GeniProfile(middle_name="Игнатиевич")]` and generated
    `middle_name = "Гордеевич"` with `nicknames = ["Гордеевич"]`.
    """

    def _codes(self, src: str) -> list[str]:
        return [f.code for f in _write_and_lint(src)]

    def test_ignore_of_pinned_middle_name_flagged(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "andrej_ignatievich_groshikov": {
                    "profile_names": ["_1834_02_20_a_rs_26_14_family_member"],
                    "preference": GeniProfile(
                        middle_name="Игнатиевич",
                        nicknames=["Гордеевич"],
                    ),
                    "ignore": [
                        GeniProfile(middle_name="Игнатиевич"),
                    ],
                },
            }
        ''')
        self.assertIn("CCN011", codes)

    def test_ignore_of_pinned_last_name_flagged(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "terentij_mefodievich_mjamlin": {
                    "profile_names": ["_1834_02_20_a_rs_61_5_family_member"],
                    "preference": GeniProfile(last_name="Мямлин"),
                    "ignore": [
                        GeniProfile(first_name="Терентий"),
                        GeniProfile(last_name="Мямлин"),
                    ],
                },
            }
        ''')
        self.assertIn("CCN011", codes)

    def test_ignore_of_a_rejected_variant_is_clean(self):
        """The correct shape: pin the keeper, ignore the value you DON'T want."""
        codes = self._codes('''
            profiles_to_consolidate = {
                "andrej_ignatievich_groshikov": {
                    "profile_names": ["_1834_02_20_a_rs_26_14_family_member"],
                    "preference": GeniProfile(middle_name="Игнатиевич"),
                    "ignore": [
                        GeniProfile(middle_name="Гордеевич"),
                    ],
                },
            }
        ''')
        self.assertNotIn("CCN011", codes)

    def test_ignore_on_a_different_field_is_clean(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "natalja_kuvshinnikova": {
                    "profile_names": ["_1842_01_01_a_mk_marriages_1_bride"],
                    "preference": GeniProfile(last_name="Кувшинникова"),
                    "ignore": [
                        GeniProfile(middle_name="Кувшинникова"),
                    ],
                },
            }
        ''')
        self.assertNotIn("CCN011", codes)

    def test_ignore_without_preference_is_clean(self):
        codes = self._codes('''
            profiles_to_consolidate = {
                "matvej_vasilevich": {
                    "profile_names": ["_1804_01_01_a_mk_births_1_child"],
                    "ignore": [
                        GeniProfile(last_name="Черпаков"),
                    ],
                },
            }
        ''')
        self.assertNotIn("CCN011", codes)


class CCN012KeeperNeverRead(unittest.TestCase):
    """`keeper` is read in exactly one place — `build_moved_consolidated_profiles`,
    gated on `generate_moved_block`. Without the flag the pin is dead text, and
    the author's intent (which record's Geni id survives) is silently unrealised.
    Both real findings were exactly that: `praskovja_petrovna_kochergina` carries a
    six-line comment justifying its keeper, and the flag was never added."""

    def test_keeper_without_generate_moved_block(self):
        src = CLEAN_PRELUDE + """
            "praskovja_petrovna_kochergina": {
                "keeper": "_1839_01_24_praskovja_petrovna_kochergina_mk_births_6_mother",
                "profile_names": [
                    "_1835_11_03_praskovja_petrovna_kochergina_mk_marriages_7_bride",
                    "_1839_01_24_praskovja_petrovna_kochergina_mk_births_6_mother",
                ],
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN012"])
        self.assertIn("generate_moved_block", findings[0].message)

    def test_keeper_with_generate_moved_block_false(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "keeper": "_1800_01_01_anna_mk_births_1_child",
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "generate_moved_block": False,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN012"])

    def test_keeper_with_adopt_external_is_never_read(self):
        """`adopt_external` takes the removed-only branch before the keeper is
        consulted, so the pin is dead there too."""
        src = CLEAN_PRELUDE + """
            "anna": {
                "keeper": "_1800_01_01_anna_mk_births_1_child",
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
                "generate_moved_block": True,
                "adopt_external": True,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN012"])

    def test_keeper_with_generate_moved_block_passes(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "keeper": "_1800_01_01_anna_mk_births_1_child",
                "profile_names": [
                    "_1800_01_01_anna_mk_births_1_child",
                    "_1810_01_01_anna_mk_deaths_2_deceased",
                ],
                "generate_moved_block": True,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])

    def test_no_keeper_passes(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "profile_names": ["_1800_01_01_anna_mk_births_1_child"],
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])


class CCN013KeeperNotInProfileNames(unittest.TestCase):
    """A keeper that names no declared record makes the generated
    `moved { from = geni_profile.<keeper> }` point at an address the cluster
    never manages, and every declared record gets a `removed{destroy=false}` —
    so nothing carries the surviving Geni id onto the canonical. The real
    finding was `salmanida_onufrievna`, whose pin used the `salmanida` spelling
    while every declared stub reads `solomonida`."""

    def test_keeper_spelled_differently_from_every_stub(self):
        src = CLEAN_PRELUDE + """
            "salmanida_onufrievna": {
                "keeper": "_1817_01_07_salmanida_onufrievna_mk_marriages_1_bride",
                "profile_names": [
                    "_1817_01_07_solomonida_onufrievna_mk_marriages_1_bride",
                    "_1833_09_09_solomonida_onufrievna_mk_births_27_mother",
                ],
                "generate_moved_block": True,
            },
        }
        """
        findings = _write_and_lint(src)
        self.assertEqual(_codes(findings), ["CCN013"])
        self.assertIn("profile_names", findings[0].message)

    def test_unused_dangling_keeper_reports_only_ccn012(self):
        """No flag ⇒ the pin is dead text; one finding with one fix, not two."""
        src = CLEAN_PRELUDE + """
            "salmanida_onufrievna": {
                "keeper": "_1817_01_07_salmanida_onufrievna_mk_marriages_1_bride",
                "profile_names": [
                    "_1817_01_07_solomonida_onufrievna_mk_marriages_1_bride",
                ],
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), ["CCN012"])

    def test_keeper_in_profile_names_passes(self):
        src = CLEAN_PRELUDE + """
            "anna": {
                "keeper": "_1810_01_01_anna_mk_deaths_2_deceased",
                "profile_names": [
                    "_1800_01_01_anna_mk_births_1_child",
                    "_1810_01_01_anna_mk_deaths_2_deceased",
                ],
                "generate_moved_block": True,
            },
        }
        """
        self.assertEqual(_codes(_write_and_lint(src)), [])


class AnnotatedTopLevelAssignments(unittest.TestCase):
    """`_find_assign` used to match only `ast.Assign`, so a config that spelled
    its top-level dicts with a type annotation was invisible to the linter.

    That is not hypothetical: a village's config can write
    `unions_to_consolidate: dict[str, object] = {`, and because the unions
    branch skips silently when the lookup returns None, every union entry in
    that village went unchecked. `profiles_to_consolidate` failed louder — it
    reported CCN000 "could not find top-level assignment" — which is what
    surfaced the bug.
    """

    def test_annotated_profiles_dict_is_found(self):
        src = """
            profiles_to_consolidate: dict[str, object] = {
                "ivan_petrovich": {
                    "profile_names": ["_1850_05_01_ivan_petrovich_mk_births_1_child"],
                },
            }
        """
        self.assertNotIn("CCN000", _codes(_write_and_lint(src)))

    def test_annotated_profiles_dict_is_actually_checked(self):
        # A duplicate canonical key must still be caught through the annotation.
        src = """
            profiles_to_consolidate: dict[str, object] = {
                "ivan_petrovich": {
                    "profile_names": ["_1850_05_01_ivan_petrovich_mk_births_1_child"],
                },
                "ivan_petrovich": {
                    "profile_names": ["_1852_05_01_ivan_petrovich_mk_births_2_child"],
                },
            }
        """
        self.assertIn("CCN001", _codes(_write_and_lint(src)))

    def test_annotated_unions_dict_is_checked(self):
        # The Маниловка shape: annotated unions dict with an unknown schema key.
        src = """
            profiles_to_consolidate = {}

            unions_to_consolidate: dict[str, object] = {
                "ivan_and_marja": {
                    "not_a_real_key": ["union_1"],
                },
            }
        """
        codes = _codes(_write_and_lint(src))
        self.assertNotIn("CCN000", codes)
        self.assertTrue(codes, "annotated unions dict was not checked at all")

    def test_empty_annotated_dicts_are_clean(self):
        # The shape a freshly-onboarded village starts from.
        src = """
            profile_move_list: dict[str, str] = {}
            profiles_to_consolidate: dict[str, object] = {}
            union_move_list_v2: dict[str, str] = {}
            unions_to_consolidate: dict[str, object] = {}
        """
        self.assertEqual([], _codes(_write_and_lint(src)))


class CCN014DuplicateKeyInsideOneCluster(unittest.TestCase):
    """Two `"preference"` entries in one cluster: Python keeps the LAST.

    A pin was pasted into a cluster that already had one, and the earlier entry
    (the one carrying the new nickname) vanished at parse time. The generator
    went on reporting the conflict the pin was supposed to resolve, and nothing
    pointed at the config.
    """

    def test_two_preference_keys(self):
        src = CLEAN_PRELUDE + """
            "avksentij_makarovich_mazjukin": {
                "profile_names": ["_1841_03_01_avksentij_makarovich_motylev_mk_births_10_father"],
                "preference": GeniProfile(last_name="Растеряшкин", nicknames=["Мотылев"]),
                "preference": GeniProfile(last_name="Растеряшкин", nicknames=["Мазюкин"]),
            },
        }
        """
        findings = [f for f in _write_and_lint(src) if f.code == "CCN014"]
        self.assertEqual(1, len(findings))
        self.assertIn("preference", findings[0].message)
        self.assertIn("avksentij_makarovich_mazjukin", findings[0].message)

    def test_the_line_of_the_first_occurrence_is_named(self):
        src = CLEAN_PRELUDE + """
            "x": {
                "profile_names": ["_a_b_c"],
                "preference": GeniProfile(last_name="A"),
                "preference": GeniProfile(last_name="B"),
            },
        }
        """
        [finding] = [f for f in _write_and_lint(src) if f.code == "CCN014"]
        # The duplicate is reported at the SECOND key, pointing back at the first.
        self.assertIn("line 9", finding.message)

    def test_distinct_keys_pass(self):
        src = CLEAN_PRELUDE + """
            "x": {
                "profile_names": ["_a_b_c"],
                "preference": GeniProfile(last_name="A"),
                "override": GeniProfile(last_name="B"),
            },
        }
        """
        self.assertNotIn("CCN014", _codes(_write_and_lint(src)))


class UpdateBlocks(unittest.TestCase):
    """`profiles_to_consolidate.update({...})` blocks are part of the config:
    Заманиловка keeps 149 clusters in them. Until 2026-09-29 the linter read only
    the dict literal, so a stub folded twice or a key overwritten there went
    unnoticed. The style rules the Заманиловка block predates — CCN008 (a key that
    is one of its own records) and CCN009 (sorted names) — stay exempt inside
    `.update()`: 88 and 32 findings when measured, none of them an error of
    consolidation."""

    LITERAL = (
        "profiles_to_consolidate = {\n"
        '    "ivan_petrovich": {"profile_names": ["_1850_a_mk_births_1_child", "_1870_a_mk_births_2_father"]},\n'
        "}\n"
    )

    def _lint(self, update_entry: str) -> list[str]:
        src = (self.LITERAL + "profiles_to_consolidate.update({\n"
               f"    {update_entry}\n" + "})\n")
        return _codes(_write_and_lint(src))

    def test_a_stub_folded_in_the_literal_and_in_an_update_is_ccn002(self):
        self.assertIn("CCN002", self._lint(
            '"_1890_b_mk_births_3_father": {"profile_names": '
            '["_1890_b_mk_births_3_father", "_1870_a_mk_births_2_father"]},'))

    def test_an_update_overwriting_a_literal_key_is_ccn001(self):
        self.assertIn("CCN001", self._lint(
            '"ivan_petrovich": {"profile_names": ["_1890_b_mk_births_3_father"]},'))

    def test_the_style_rules_are_exempt_inside_an_update(self):
        self.assertEqual([], self._lint(
            '"_1890_b_mk_births_3_father": {"profile_names": '
            '["_1890_b_mk_births_3_father", "_1880_c_mk_births_4_father"]},'))

    def test_the_style_rules_still_hold_in_the_literal(self):
        src = ("profiles_to_consolidate = {\n"
               '    "_1890_b_mk_births_3_father": {"profile_names": '
               '["_1890_b_mk_births_3_father", "_1880_c_mk_births_4_father"]},\n'
               "}\n")
        self.assertEqual({"CCN008", "CCN009"}, set(_codes(_write_and_lint(src))))
