"""Unit tests for draft_config: component clustering, key uniquification,
append form, and union block resolution."""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, stub, year=1840, surname=None, gender="male",
        rec_type="birth", record_num=1, role="father"):
    """An Occurrence.public() dict, the shape draft_config actually consumes."""
    return f.Occurrence(
        key=(given, patr), name=f"{given} {patr}", given=given, patr=patr,
        surname=surname, gender=gender, rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        stub=stub,
    ).public()


def placed(*stubs: tuple[str, int]) -> dict[str, f.Occurrence]:
    """The occurrence behind each stub, which is where a draft reads a
    record's year — never the res_name's date prefix."""
    return {stub: f.Occurrence(key=("x", None), name="x", given="x", patr=None,
                               surname=None, gender=None, rec_type="birth",
                               record_num=1, role="father", year=year,
                               source_file="t.py", stub=stub)
            for stub, year in stubs}


def entry(target, *highs, medium=()):
    """One `targets` list element: a target plus its scored local matches."""
    local = [{"confidence": "high", "score": 120, "evidence": ["shared spouse: X"],
              "cand": c} for c in highs]
    local += [{"confidence": "medium", "score": 40, "evidence": ["shared child: X"],
               "cand": c} for c in medium]
    return {"target": target, "local": local, "geni": []}


class TestComponentClustering(unittest.TestCase):
    def test_mutual_cluster_drafts_once(self):
        # Three occurrences of one man, each drafted as a target with the
        # other two as HIGH matches. Old code emitted three dict blocks with
        # the same key — the later ones silently overwrote the first.
        a = occ("Иларион", "Платонович", stub="_1849_09_03_ilarion_a", year=1849)
        b = occ("Иларион", "Платонович", stub="_1852_06_01_ilarion_b", year=1852)
        c = occ("Иларион", "Платонович", stub="_1855_01_17_ilarion_c", year=1855)
        out = f.draft_config([entry(a, b, c), entry(b, a, c), entry(c, a, b)])
        self.assertEqual(out.count('"profile_names"'), 1)
        for stub in ("_1849_09_03_ilarion_a", "_1852_06_01_ilarion_b",
                     "_1855_01_17_ilarion_c"):
            self.assertIn(stub, out)

    def test_transitive_edge_fuses_split_clusters(self):
        # a~b and b~c, no a~c edge: still ONE person, one block.
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        c = occ("Пётр", "Фомич", stub="_1850_01_01_petr_c", year=1850)
        out = f.draft_config([entry(a, b), entry(b, a, c), entry(c, b)])
        self.assertEqual(out.count('"profile_names"'), 1)

    def test_disjoint_clusters_draft_separately(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", surname="Сидоров")
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", surname="Сидоров",
                year=1845)
        x = occ("Анна", "Ивановна", stub="_1841_01_01_anna_x", gender="female",
                surname="Кулишкина", year=1841)
        y = occ("Анна", "Ивановна", stub="_1846_01_01_anna_y", gender="female",
                surname="Кулишкина", year=1846)
        out = f.draft_config([entry(a, b), entry(b, a), entry(x, y), entry(y, x)])
        self.assertEqual(out.count('"profile_names"'), 2)

    def test_medium_matches_never_drafted(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a")
        m = occ("Пётр", "Фомич", stub="_1915_01_01_petr_m", year=1915)
        out = f.draft_config([entry(a, medium=[m])])
        self.assertIn("No high-confidence local matches", out)

    def test_profile_names_are_lexicographically_sorted(self):
        # Two members in the SAME year: a year-only sort key leaves them in
        # insertion order, which CCN009 rejects.
        a = occ("Пётр", "Фомич", stub="_1840_09_01_petr_late", year=1840)
        b = occ("Пётр", "Фомич", stub="_1840_02_01_petr_early", year=1840)
        out = f.draft_config([entry(a, b), entry(b, a)])
        self.assertLess(out.index("_1840_02_01_petr_early"),
                        out.index("_1840_09_01_petr_late"))


class TestClusterGuards(unittest.TestCase):
    def test_colliding_keys_are_year_qualified(self):
        # Two components, same generated key, no edge between them.
        a1 = occ("Иларион", "Платонович", stub="_1840_02_04_ilarion_m",
                 surname="Тюлкин", year=1840, role="groom")
        a2 = occ("Иларион", "Платонович", stub="_1841_03_01_ilarion_f", year=1841)
        b1 = occ("Иларион", "Платонович", stub="_1849_09_03_ilarion_x",
                 surname="Тюлкин", year=1849)
        b2 = occ("Иларион", "Платонович", stub="_1852_06_01_ilarion_y", year=1852)
        out = f.draft_config([entry(a1, a2), entry(a2, a1),
                              entry(b1, b2), entry(b2, b1)])
        self.assertIn('"ilarion_platonovich_tjulkin_1840"', out)
        self.assertIn('"ilarion_platonovich_tjulkin_1849"', out)
        keys = [ln for ln in out.splitlines() if ln.startswith('    "')]
        self.assertEqual(len(keys), len(set(keys)), "duplicate key in draft")

    def test_chain_linked_component_is_flagged(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        c = occ("Пётр", "Фомич", stub="_1850_01_01_petr_c", year=1850)
        out = f.draft_config([entry(a, b), entry(b, a, c), entry(c, b)])
        self.assertIn("chain-linked", out)

    def test_full_clique_is_not_flagged(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        c = occ("Пётр", "Фомич", stub="_1850_01_01_petr_c", year=1850)
        out = f.draft_config([entry(a, b, c), entry(b, a, c), entry(c, a, b)])
        self.assertNotIn("chain-linked", out)

    def test_pair_is_never_chain_flagged(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        out = f.draft_config([entry(a, b), entry(b, a)])
        self.assertNotIn("chain-linked", out)


class TestAppendForm(unittest.TestCase):
    def _cluster(self):
        a = occ("Иван", "Петрович", stub="_1834_02_20_ivan_rs", year=1834,
                surname="Самоварин", rec_type="census", role="member_3")
        b = occ("Иван", "Петрович", stub="_1836_05_01_ivan_f", year=1836)
        return [entry(a, b), entry(b, a)]

    def test_existing_key_emits_merged_block(self):
        existing = {"ivan_petrovich_samovarin": [
            "_1805_03_02_ivan_child", "_1820_01_09_ivan_groom"]}
        out = f.draft_config(self._cluster(), existing)
        self.assertIn("APPEND to existing cluster (2 existing + 2 new)", out)
        # Existing members appear in the merged list, marked, and sorted first.
        self.assertIn('"_1805_03_02_ivan_child",  # existing', out)
        self.assertIn('"_1834_02_20_ivan_rs",  # NEW', out)
        self.assertLess(out.index("_1805_03_02_ivan_child"),
                        out.index("_1834_02_20_ivan_rs"))

    def test_append_emits_removed_blocks_for_new_stubs_only(self):
        existing = {"ivan_petrovich_samovarin": ["_1805_03_02_ivan_child"]}
        out = f.draft_config(self._cluster(), existing)
        self.assertIn("_moved_manual_profiles.tf", out)
        self.assertIn("removed {\n  from = geni_profile._1834_02_20_ivan_rs", out)
        self.assertNotIn("from = geni_profile._1805_03_02_ivan_child", out)

    def test_fresh_key_emits_no_append_scaffolding(self):
        out = f.draft_config(self._cluster(), {"someone_else": ["_1800_01_01_x"]})
        self.assertNotIn("APPEND to existing cluster", out)
        self.assertNotIn("_moved_manual_profiles.tf", out)

    def test_implausible_span_is_flagged(self):
        a = occ("Степан", "Петрович", stub="_1774_09_09_stepan_a", year=1774)
        b = occ("Степан", "Петрович", stub="_1915_07_02_stepan_b", year=1915)
        out = f.draft_config([entry(a, b), entry(b, a)],
                             occ_by_stub=placed(("_1774_09_09_stepan_a", 1774),
                                                ("_1915_07_02_stepan_b", 1915)))
        self.assertIn("span 1774–1915", out)
        self.assertIn("implausible for one person", out)

    def test_normal_span_is_not_flagged(self):
        a = occ("Степан", "Петрович", stub="_1834_09_09_stepan_a", year=1834)
        b = occ("Степан", "Петрович", stub="_1859_07_02_stepan_b", year=1859)
        out = f.draft_config([entry(a, b), entry(b, a)])
        self.assertNotIn("implausible for one person", out)


class TestLoadConsolidatedClusters(unittest.TestCase):
    def test_reads_profile_names_per_canonical(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            Path(d, "generate_config_names.py").write_text(
                'profiles_to_consolidate = {\n'
                '    "ivan_petrovich": {"profile_names": ["_1805_a", "_1820_b"]},\n'
                '}\n', encoding="utf-8")
            clusters = f.load_consolidated_clusters(Path(d))
        self.assertEqual(clusters, {"ivan_petrovich": ["_1805_a", "_1820_b"]})


class TestAppendGuards(unittest.TestCase):
    """The two failure modes the 2026-08-05 Горюхино review surfaced."""

    def test_span_covers_existing_members_too(self):
        # Евдокия Михайловна: existing cluster is an 1773 BRIDE; the component
        # alone spans 1850-1855, so a component-only span check sees nothing.
        a = occ("Евдокия", "Михайловна", stub="_1850_10_01_evdokija_rs", year=1850,
                rec_type="census", role="member_9")
        b = occ("Евдокия", "Михайловна", stub="_1855_02_01_evdokija_m", year=1855,
                role="mother")
        out = f.draft_config([entry(a, b), entry(b, a)],
                             {"evdokija_mihajlovna": ["_1773_04_14_evdokija_bride"]},
                             occ_by_stub=placed(("_1773_04_14_evdokija_bride", 1773),
                                                ("_1850_10_01_evdokija_rs", 1850),
                                                ("_1855_02_01_evdokija_m", 1855)))
        self.assertIn("span 1773–1855", out)
        self.assertIn("implausible for one person", out)

    def test_bare_given_name_key_never_appends(self):
        # Феофилакт: an infant with no patronymic and no surname generates the
        # bare key "feofilakt", which collides with ANY cluster of that name —
        # here an adult who fathered a child in 1778.
        a = occ("Феофилакт", None, stub="_1807_03_02_feofilakt_c", year=1807,
                role="child")
        b = occ("Феофилакт", None, stub="_1809_06_20_feofilakt_d", year=1809,
                rec_type="death", role="deceased")
        out = f.draft_config([entry(a, b), entry(b, a)],
                             {"feofilakt": ["_1778_03_27_feofilakt_filippovich_f"]})
        self.assertNotIn("APPEND to existing cluster", out)
        self.assertNotIn("_1778_03_27_feofilakt_filippovich_f", out)
        self.assertIn('"feofilakt_1807"', out)

    def test_qualified_key_still_appends(self):
        # A key carrying a patronymic/surname is specific enough to trust.
        a = occ("Антон", "Михайлович", stub="_1839_01_01_anton_g", year=1839,
                surname="Самоварин", role="groom")
        b = occ("Антон", "Михайлович", stub="_1853_01_01_anton_f", year=1853,
                surname="Самоварин")
        out = f.draft_config([entry(a, b), entry(b, a)],
                             {"anton_mihajlovich_samovarin": ["_1840_08_12_anton_f"]})
        self.assertIn("APPEND to existing cluster", out)


class TestUnionChildIndex(unittest.TestCase):
    TF = '''
resource "geni_union" "efim_ivanovich__5_1800" {
  partners = [
    geni_profile._1800_02_15_efim_ivanovich_mk_births_5_father.id,
  ]
  children = [
    geni_profile._1800_02_15_timofej_efimovich_mk_births_5_child.id,
  ]
}

resource "geni_union" "ivan_pov__2_1800" {
  partners = [
    geni_profile._1800_03_13_ivan_pov_mk_births_2_father.id,
  ]
  children = [
    geni_profile._1800_03_13_darja_ivanovna_mk_births_2_child.id,
  ]
}
'''

    def _index(self):
        from verso.core.targets.geni.union import GeniUnion
        return f.union_child_index({
            "efim_ivanovich__5_1800": GeniUnion(
                res_name="efim_ivanovich__5_1800",
                partner_1="_1800_02_15_efim_ivanovich_mk_births_5_father",
                children={"_1800_02_15_timofej_efimovich_mk_births_5_child"}),
            "ivan_pov__2_1800": GeniUnion(
                res_name="ivan_pov__2_1800",
                partner_1="_1800_03_13_ivan_pov_mk_births_2_father",
                children={"_1800_03_13_darja_ivanovna_mk_births_2_child"},
                foster_children={"_1800_03_13_marija-priemysh_mk_births_2_child"}),
        })

    def test_child_maps_to_its_union(self):
        idx = self._index()
        self.assertEqual(idx["_1800_02_15_timofej_efimovich_mk_births_5_child"],
                         "efim_ivanovich__5_1800")
        self.assertEqual(idx["_1800_03_13_darja_ivanovna_mk_births_2_child"],
                         "ivan_pov__2_1800")

    def test_a_foster_child_and_a_hyphen_are_indexed_too(self):
        self.assertEqual(self._index()["_1800_03_13_marija-priemysh_mk_births_2_child"],
                         "ivan_pov__2_1800")

    def test_partners_are_not_indexed(self):
        # The block a fold needs is the union holding it as a CHILD.
        self.assertNotIn("_1800_02_15_efim_ivanovich_mk_births_5_father",
                         self._index())


class TestUnionBlocks(unittest.TestCase):
    def test_folded_stub_emits_its_union_removed_block(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        out = f.draft_config([entry(a, b), entry(b, a)], None,
                             {"_1845_01_01_petr_b": "some_union_2_1845"})
        self.assertIn("_moved_consolidated_unions.tf", out)
        self.assertIn("UNVERIFIED", out)
        self.assertIn("removed {\n  from = geni_union.some_union_2_1845", out)

    def test_survivor_union_is_not_removed(self):
        # profile_names[0] survives; only the folded members' unions go.
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        out = f.draft_config([entry(a, b), entry(b, a)],
                             None,
                             {"_1840_01_01_petr_a": "survivor_union",
                              "_1845_01_01_petr_b": "folded_union"})
        self.assertIn("geni_union.folded_union", out)
        self.assertNotIn("geni_union.survivor_union", out)

    def test_no_union_section_without_index(self):
        a = occ("Пётр", "Фомич", stub="_1840_01_01_petr_a", year=1840)
        b = occ("Пётр", "Фомич", stub="_1845_01_01_petr_b", year=1845)
        out = f.draft_config([entry(a, b), entry(b, a)])
        self.assertNotIn("_moved_consolidated_unions.tf — UNVERIFIED", out)


if __name__ == "__main__":
    unittest.main()
