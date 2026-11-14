#!/usr/bin/env python3
"""Unit tests for the rename -> moved{} block generator.

Plan-driven and network-free, like verify_plan: the pairing and tiering rules are
what stand between a res_name rename and a destroyed live Geni profile, so they
are pinned here rather than discovered during an apply.
"""
from __future__ import annotations

import unittest

from verso.ru.consolidation import moved_blocks as mb


class ParseTest(unittest.TestCase):
    def test_simple_role(self):
        r = mb.parse_profile(
            "_1862_01_11_prokopij_andreevich_oladushkin_mk_births_1_god_parent_1")
        assert r is not None
        self.assertEqual(r.date, "1862_01_11")
        self.assertEqual(r.name, "prokopij_andreevich_oladushkin")
        self.assertEqual(r.kind, "births")
        self.assertEqual(r.num, "1")
        self.assertEqual(r.role, "god_parent_1")
        self.assertIsNone(r.uniq)

    def test_non_numeric_record_number(self):
        """Twin registers use a suffixed record № (6 / 6zh)."""
        r = mb.parse_profile(
            "_1862_02_27_mihail_kirillovich_famusov_mk_births_6zh_father")
        assert r is not None
        self.assertEqual(r.num, "6zh")
        self.assertEqual(r.role, "father")

    def test_uniquifier_suffix(self):
        r = mb.parse_profile(
            "_1862_02_27_mihail_kirillovich_famusov_mk_births_6_father_2")
        assert r is not None
        self.assertEqual(r.role, "father")
        self.assertEqual(r.uniq, "2")

    def test_numbered_role_with_uniquifier(self):
        r = mb.parse_profile("_1865_10_28_x_y_mk_births_18_witness_4_2")
        assert r is not None
        self.assertEqual(r.role, "witness_4")
        self.assertEqual(r.uniq, "2")

    def test_deceased_role(self):
        r = mb.parse_profile(
            "_1894_10_30_leontij_dmitrievich_zhevakin_mk_deaths_21_deceased")
        assert r is not None
        self.assertEqual(r.role, "deceased")
        self.assertEqual(r.kind, "deaths")

    def test_compound_roles(self):
        """Roles seen in the real trees: bride_relative, groom_father, rel_N."""
        for res, role in [
            ("_1878_04_23_a_b_mk_marriages_12_bride_relative", "bride_relative"),
            ("_1878_04_23_a_b_mk_marriages_12_bride_relative_1", "bride_relative_1"),
            ("_1880_01_01_a_b_mk_marriages_3_groom_father", "groom_father"),
            ("_1880_01_01_a_b_mk_deaths_3_rel_2", "rel_2"),
        ]:
            r = mb.parse_profile(res)
            assert r is not None, res
            self.assertEqual(r.role, role, res)

    def test_partial_date(self):
        """Real trees carry year+month dates with no day."""
        r = mb.parse_profile("_1799_11_isaija_fedorovich_mk_births_12_father")
        assert r is not None
        self.assertEqual(r.date, "1799_11")
        self.assertEqual(r.name, "isaija_fedorovich")
        self.assertEqual(r.record, ("1799", "births", "12"))

    def test_empty_name(self):
        """An unnamed deceased has no name segment at all."""
        r = mb.parse_profile("_1784_06_06_mk_deaths_4_deceased")
        assert r is not None
        self.assertEqual(r.date, "1784_06_06")
        self.assertEqual(r.name, "")
        self.assertEqual(r.role, "deceased")

    def test_external_profile_is_unparseable(self):
        """ext_ cards have no record slot — never guess at them."""
        self.assertIsNone(mb.parse_profile(
            "_1915_02_17_vasilij_ivanovich_teljatnikov_ext_gwar_1_external"))

    def test_record_key_ignores_the_date(self):
        """A record's date can be CORRECTED (1896 №26 moved 06-05 -> 11-05), so the
        record identity must be (year, kind, №) — not the full date."""
        a = mb.parse_profile("_1896_06_05_ivan_teljatnikov_mk_births_26_father")
        b = mb.parse_profile("_1896_11_05_ivan_teljatnikov_mk_births_26_father")
        assert a is not None and b is not None
        self.assertEqual(a.record, b.record)
        self.assertEqual(a.record, ("1896", "births", "26"))


def _rc(rtype, name, actions, before=None):
    return {"address": f"{rtype}.{name}", "type": rtype,
            "change": {"actions": actions, "before": before, "after": None}}


def _plan(*changes):
    return {"resource_changes": list(changes)}


def _delete(name, gid):
    return _rc("geni_profile", name, ["delete"], before={"id": gid})


def _create(name):
    return _rc("geni_profile", name, ["create"])


class PairTest(unittest.TestCase):
    def test_surname_spelling_change_is_auto(self):
        plan = _plan(
            _delete("_1862_01_11_prokopij_andreevich_oladushkin_mk_births_1_god_parent_1",
                    "profile-1"),
            _create("_1862_01_11_prokopij_andreevich_aladushkin_mk_births_1_god_parent_1"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(unpaired, [])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].tier, "auto")
        self.assertEqual(pairs[0].geni_id, "profile-1")

    def test_role_change_same_person_is_review(self):
        """1891 №29: the mis-read 'father' was actually the godparent. Same man —
        but a human confirms before we move a live profile."""
        plan = _plan(
            _delete("_1891_11_01_nikolaj_izotovich_chirikin_mk_births_29_father",
                    "profile-2"),
            _create("_1891_11_01_nikolaj_izotovich_chirikin_mk_births_29_god_parent_1"),
        )
        pairs, _ = mb.pair_profiles(plan)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].tier, "review")
        self.assertIn("role", pairs[0].why)

    def test_identity_swap_in_same_role_is_review(self):
        """1891 №29: the father SLOT came to hold a different man. Auto-writing this
        would rebrand a live Geni profile onto another human."""
        plan = _plan(
            _delete("_1891_11_01_nikolaj_izotovich_chirikin_mk_births_29_father",
                    "profile-3"),
            _create("_1891_11_01_ivan_dmitrievich_teljatnikov_mk_births_29_father"),
        )
        pairs, _ = mb.pair_profiles(plan)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].tier, "review")

    def test_given_name_typo_is_review_not_auto(self):
        """zaha -> zahar is almost certainly a typo fix, but pairing cannot prove it
        is not a different person. Print, do not write."""
        plan = _plan(
            _delete("_1865_10_28_zaha_ivanovich_ladankin_mk_births_18_god_parent_1",
                    "profile-4"),
            _create("_1865_10_28_zahar_ivanovich_ladankin_mk_births_18_god_parent_1"),
        )
        pairs, _ = mb.pair_profiles(plan)
        self.assertEqual(pairs[0].tier, "review")

    def test_delete_with_no_create_is_unpaired(self):
        plan = _plan(_delete("_1894_10_30_x_y_mk_deaths_21_deceased", "profile-5"))
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(pairs, [])
        self.assertEqual(unpaired,
                         [("_1894_10_30_x_y_mk_deaths_21_deceased", "profile-5")])

    def test_date_correction_still_pairs(self):
        """1896 №26 had its date corrected 06-05 -> 11-05. Same record, same person."""
        plan = _plan(
            _delete("_1896_06_05_ivan_dmitrievich_teljatnikov_mk_births_26_father",
                    "profile-6"),
            _create("_1896_11_05_ivan_dmitrievich_teljatnikov_mk_births_26_father"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(unpaired, [])
        self.assertEqual(pairs[0].tier, "auto")

    def test_external_delete_is_unpaired_never_guessed(self):
        plan = _plan(
            _delete("_1915_02_17_x_y_ext_gwar_1_external", "profile-7"),
            _create("_1915_02_17_x_z_ext_gwar_1_external"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(pairs, [])
        self.assertEqual(len(unpaired), 1)

    def test_replace_is_not_a_rename(self):
        """delete+create on the SAME address is a force-replace, not a rename."""
        plan = _plan(_rc("geni_profile", "_1862_01_11_a_b_mk_births_1_father",
                         ["delete", "create"], before={"id": "profile-8"}))
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(pairs, [])
        self.assertEqual(unpaired, [])


class RenderTest(unittest.TestCase):
    def test_renders_only_auto_pairs_with_geni_id_comment(self):
        pairs = [
            mb.Pair("geni_profile", "old_a", "new_a", "profile-1", "auto",
                    "surname spelling"),
            mb.Pair("geni_profile", "old_b", "new_b", "profile-2", "review",
                    "role change"),
        ]
        out = mb.render(pairs)
        self.assertIn("# profile-1", out)
        self.assertIn("from = geni_profile.old_a", out)
        self.assertIn("to   = geni_profile.new_a", out)
        self.assertNotIn("old_b", out)      # review pairs are NEVER written
        self.assertIn("DO NOT EDIT", out)

    def test_owns_only_the_auto_file(self):
        """_moved_renames.tf is a HAND-MAINTAINED audit trail in Горюхино and
        _moved_manual_profiles.tf is hand-written too. The tool must own neither."""
        self.assertEqual(mb.AUTO_FILE, "_moved_auto_renames.tf")


if __name__ == "__main__":
    unittest.main()


class CensusResNames(unittest.TestCase):
    """`moved_blocks` must parse census (`_rs_`) res_names, not only MK (`_mk_`).

    Making a census daughter's res_name carry her derived maiden surname renamed
    46 live profiles across Нижняя Яичница and Маниловка. Every pair was an
    unambiguous surname-only change in the same family slot, yet the tool
    reported AUTO(0) and listed them all as real destroys — parse_profile()
    partitioned on "_mk_" only, so census names returned None and never paired.
    """

    def test_census_family_member_parses(self):
        r = mb.parse_profile("_1857_11_06_anna_grigorevna_rs_17_7_family_member")
        self.assertIsNotNone(r)
        assert r is not None
        self.assertEqual(r.name, "anna_grigorevna")
        self.assertEqual(r.role, "family_member")

    def test_rename_pairs_in_the_same_family_slot(self):
        old = mb.parse_profile("_1857_11_06_anna_grigorevna_rs_17_7_family_member")
        new = mb.parse_profile("_1857_11_06_anna_grigorevna_indjushova_rs_17_7_family_member")
        assert old is not None and new is not None
        self.assertEqual(old.record, new.record)   # same slot → pairable
        self.assertEqual(old.role, new.role)

    def test_different_slots_do_not_pair(self):
        a = mb.parse_profile("_1857_11_06_anna_grigorevna_rs_17_7_family_member")
        b = mb.parse_profile("_1857_11_06_anna_grigorevna_rs_18_7_family_member")
        assert a is not None and b is not None
        self.assertNotEqual(a.record, b.record)

    def test_mk_names_still_parse(self):
        r = mb.parse_profile("_1832_07_01_marfa_ignatievna_uhvatova_mk_births_11_child")
        self.assertIsNotNone(r)
        assert r is not None
        self.assertEqual(r.kind, "births")
        self.assertEqual(r.role, "child")


class NameListResNames(unittest.TestCase):
    """`moved_blocks` must parse name-list (`_list_`) res_names too.

    A voter list was read against the scan after it had been applied, and three
    entries changed surname (a doubled letter dropped). The tool could not parse
    a list name, so it reported all three as REAL destroys of live Geni profiles
    and their moved blocks had to be written by hand.
    """

    def test_list_entry_parses(self):
        r = mb.parse_profile("_1917_ivan_kapitonovich_kuvshinnikov_list_41_listed")
        assert r is not None
        self.assertEqual(r.date, "1917")
        self.assertEqual(r.name, "ivan_kapitonovich_kuvshinnikov")
        self.assertEqual(r.kind, "list")
        self.assertEqual(r.num, "41")
        self.assertEqual(r.role, "listed")
        self.assertIsNone(r.uniq)
        self.assertEqual(r.record, ("1917", "list", "41"))

    def test_surname_correction_is_auto(self):
        plan = _plan(
            _delete("_1917_ivan_kapitonovich_kuvshinnikov_list_41_listed", "profile-41"),
            _delete("_1917_agafja_egorovna_kuvshinnikova_list_42_listed", "profile-42"),
            _create("_1917_ivan_kapitonovich_kuvshinikov_list_41_listed"),
            _create("_1917_agafja_egorovna_kuvshinikova_list_42_listed"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(unpaired, [])
        self.assertEqual(
            sorted((p.old, p.new, p.geni_id, p.tier) for p in pairs),
            [("_1917_agafja_egorovna_kuvshinnikova_list_42_listed",
              "_1917_agafja_egorovna_kuvshinikova_list_42_listed", "profile-42", "auto"),
             ("_1917_ivan_kapitonovich_kuvshinnikov_list_41_listed",
              "_1917_ivan_kapitonovich_kuvshinikov_list_41_listed", "profile-41", "auto")])

    def test_given_name_correction_is_review(self):
        """An entry was read «Степанида» and corrected to «Степанъ»: the same line of
        the list, but pairing alone cannot tell a misreading from another person."""
        plan = _plan(
            _delete("_1917_stepanida_vasilevna_ezhevikina_list_71_listed", "profile-71"),
            _create("_1917_stepan_vasilevich_ezhevikin_list_71_listed"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(unpaired, [])
        self.assertEqual([p.tier for p in pairs], ["review"])

    def test_different_entries_do_not_pair(self):
        plan = _plan(
            _delete("_1917_ivan_kapitonovich_kuvshinnikov_list_41_listed", "profile-41"),
            _create("_1917_ivan_kapitonovich_kuvshinikov_list_43_listed"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(pairs, [])
        self.assertEqual(unpaired,
                         [("_1917_ivan_kapitonovich_kuvshinnikov_list_41_listed", "profile-41")])

    def test_a_list_entry_never_pairs_with_a_metric_record(self):
        plan = _plan(
            _delete("_1917_ivan_kapitonovich_kuvshinnikov_list_12_listed", "profile-12"),
            _create("_1917_03_01_ivan_kapitonovich_kuvshinikov_mk_births_12_father"),
        )
        pairs, unpaired = mb.pair_profiles(plan)
        self.assertEqual(pairs, [])
        self.assertEqual(len(unpaired), 1)
