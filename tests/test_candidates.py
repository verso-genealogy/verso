"""Unit tests for find_consolidation_candidates: relative extraction, the
relative-aware scorer, surname tolerance, and stub resolution."""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, surname=None, gender="male", rec_type="birth",
        record_num=1, role="father", year=1840, spouses=None, parents=None,
        children=None, birth_date=None, death_date=None):
    return f.Occurrence(
        key=(given, patr), name=f"{given} {patr}", given=given, patr=patr,
        surname=surname, gender=gender, rec_type=rec_type, record_num=record_num,
        role=role, year=year, source_file="t.py",
        spouses=set(spouses or []), parents=set(parents or []),
        children=set(children or []), birth_date=birth_date, death_date=death_date,
    )


class TestScorer(unittest.TestCase):
    def test_shared_spouse_is_high(self):
        wife = ("Анна", "Ивановна")
        t = occ("Пётр", "Фомич", spouses=[wife], record_num=1)
        c = occ("Пётр", "Фомич", spouses=[wife], record_num=9, year=1837)
        s = f.score_pair(t, c)
        self.assertEqual(s.confidence, "high")
        self.assertGreaterEqual(s.score, 100)
        self.assertTrue(any("spouse" in e for e in s.evidence))

    def test_shared_parent_plus_surname_is_high(self):
        # A birth record's child against the same child enumerated in a сказка.
        # Two BIRTH records would be two baptisms, hence two children — see
        # two_baptisms_conflict and tests/test_candidates_two_baptisms.py.
        dad = ("Фома", "Ильич")
        t = occ("Пётр", "Фомич", surname="Сидоров", role="child",
                parents=[dad], record_num=1)
        c = occ("Пётр", "Фомич", surname="Сидоров", rec_type="census",
                role="member_4", parents=[dad], record_num=5, year=1835)
        self.assertEqual(f.score_pair(t, c).confidence, "high")

    def test_name_only_is_low_and_flagged(self):
        t = occ("Пётр", "Фомич", record_num=1)
        c = occ("Пётр", "Фомич", record_num=2, year=1700)
        s = f.score_pair(t, c)
        self.assertEqual(s.confidence, "low")
        self.assertTrue(any("name-only" in e for e in s.evidence))

    def test_name_collision_disjoint_relatives_not_high(self):
        # The classic collision: same name+patronymic, completely different families.
        t = occ("Нил", "Фокич", spouses=[("Татьяна", "Петровна")], record_num=1)
        c = occ("Нил", "Фокич", spouses=[("Анисья", "Зотовна")],
                record_num=2, year=1836)
        s = f.score_pair(t, c)
        self.assertNotEqual(s.confidence, "high")

    def test_patronymic_variant_rejected_by_default(self):
        # The per-year path must keep its exact-key gate.
        wife = ("Анна", "Ивановна")
        t = occ("Фекла", "Тимоновна", gender="female", spouses=[wife])
        c = occ("Фекла", "Пахомовна", gender="female", spouses=[wife],
                record_num=2)
        self.assertIsNone(f.score_pair(t, c))


class TestPatronymicVariant(unittest.TestCase):
    """One woman under two patronymics, wife of one man in a birth record and
    again in a burial record."""

    def test_shared_spouse_carries_the_variant(self):
        husband = ("Игнатий", "Леонтьевич")
        t = occ("Фекла", "Тимоновна", gender="female", role="mother",
                spouses=[husband], record_num=12)
        c = occ("Фекла", "Пахомовна", gender="female", role="deceased",
                spouses=[husband], record_num=7, year=1843)
        s = f.score_pair(t, c, allow_patronymic_variant=True)
        self.assertEqual(s.confidence, "high")
        self.assertTrue(any("patronymic variant" in e for e in s.evidence))

    def test_shared_parent_only_caps_at_medium(self):
        # Half-siblings look exactly like this: shared mother, different fathers,
        # hence different patronymics. Must never be auto-drafted.
        # (Two BIRTH records never reach the scorer at all — that pair is two
        # baptisms; see two_baptisms_conflict. Pair the birth with a сказка.)
        mother = ("Анна", "Ивановна")
        t = occ("Мария", "Петровна", gender="female", role="child",
                parents=[mother], record_num=1)
        c = occ("Мария", "Фомична", gender="female", rec_type="census",
                role="member_3", parents=[mother], record_num=2, year=1836)
        s = f.score_pair(t, c, allow_patronymic_variant=True)
        self.assertEqual(s.confidence, "medium")
        self.assertTrue(any("half-sibling" in e for e in s.evidence))

    def test_variant_without_family_is_rejected(self):
        t = occ("Фекла", "Тимоновна", gender="female", surname="Лясаточкина")
        c = occ("Фекла", "Пахомовна", gender="female", surname="Лясаточкина",
                record_num=2, year=1843)
        self.assertIsNone(f.score_pair(t, c, allow_patronymic_variant=True))

    def test_different_given_name_never_pairs(self):
        # Марина / «Мария» stays a human call — siblings share parents.
        husband = ("Тихон", "Андреевич")
        t = occ("Марина", "Тихоновна", gender="female", parents=[husband])
        c = occ("Мария", "Тихоновна", gender="female", parents=[husband],
                record_num=2, year=1839)
        self.assertIsNone(f.score_pair(t, c, allow_patronymic_variant=True))


class TestScorerMisc(unittest.TestCase):
    def test_gender_mismatch_skipped(self):
        t = occ("Александр", "Петрович", gender="male")
        c = occ("Александр", "Петрович", gender="female", record_num=2)
        self.assertIsNone(f.score_pair(t, c))

    def test_same_physical_resource_skipped(self):
        t = occ("Пётр", "Фомич", record_num=1, role="father")
        self.assertIsNone(f.score_pair(t, t))

    def test_different_key_skipped(self):
        t = occ("Пётр", "Фомич")
        c = occ("Иван", "Фомич", record_num=2)
        self.assertIsNone(f.score_pair(t, c))


class TestSurnames(unittest.TestCase):
    def test_feminine_matches_masculine(self):
        self.assertTrue(f.surnames_match("Петров", "Петрова"))
        self.assertTrue(f.surnames_match("Индюшев", "Индюшева"))

    def test_distinct_surnames_dont_match(self):
        self.assertFalse(f.surnames_match("Петров", "Иванов"))

    def test_empty_is_false(self):
        self.assertFalse(f.surnames_match(None, "Петров"))

    def test_soft_sign_variant_matches(self):
        # The books spell one surname both ways: «Пузыркин» and «Пузырькинъ».
        self.assertTrue(f.surnames_match("Пузыркин", "Пузырькин"))
        self.assertTrue(f.surnames_match("Пузырькина", "Пузыркин"))

    def test_soft_sign_does_not_collapse_distinct_surnames(self):
        self.assertFalse(f.surnames_match("Пузыркин", "Синкин"))


class TestFamilyGraphBlocking(unittest.TestCase):
    def test_rel_index_pool_surfaces_a_variant_pair(self):
        husband = ("Игнатий", "Леонтьевич")
        t = occ("Фекла", "Тимоновна", gender="female", role="mother",
                spouses=[husband], record_num=12)
        c = occ("Фекла", "Пахомовна", gender="female", role="deceased",
                spouses=[husband], record_num=7, year=1843)
        # Different keys, so the exact-key pool cannot see the pair …
        self.assertEqual(f.find_local_candidates(t, {t.key: [t, c]}, set()), [])
        # … but a shared relative brings it in.
        found = f.find_local_candidates(t, {t.key: [t]}, set(),
                                        rel_index={husband: [t, c]})
        self.assertEqual([s.cand for s in found], [c])
        self.assertEqual(found[0].confidence, "high")

    def test_fanout_cap_skips_and_counts_common_relatives(self):
        import collections
        common = ("Иван", "Иванович")
        t = occ("Пётр", "Фомич", spouses=[common])
        crowd = [occ("Пётр", "Фомич", spouses=[common], record_num=n)
                 for n in range(f.REL_FANOUT_MAX + 5)]
        skipped: collections.Counter[f.PersonKey] = collections.Counter()
        found = f.find_local_candidates(t, {t.key: [t]}, set(),
                                        rel_index={common: crowd},
                                        fanout_skipped=skipped)
        self.assertEqual(found, [])
        self.assertEqual(skipped[common], f.REL_FANOUT_MAX + 5)


class TestPlacement(unittest.TestCase):
    """An occurrence is placed on the profile the translator minted for its
    very DSL object — asked, never rebuilt from a record number and a name
    token (which placed a child on the namesake of another year with the same entry
    number, and could not place a res_name with a hyphen at all)."""

    def test_the_stub_is_what_the_translator_minted_for_the_object(self):
        from verso.ru.dsl.records.births import birth, birth_records
        from verso.ru.domain import person
        from verso.ru.gender import Gender
        recs = birth_records("A", "1", "1", "1", "Тестовка", "Ц", 1840,
                             birth(1, Gender.MALE, 5, 6, child=person("Иван"),
                                   father=person("Матвей", "Андреевич", "Брюхин")))
        # Keyed by the object the RECORD holds, as the translator's is.
        father = recs.records[0].father
        minted = {id(father): "_1840_01_05_matfej_andreevich_brjuhin-ov_mk_births_1_father"}
        occs = {o.role: o for o in f.extract_occurrences(
            recs, "b.py", stub_of=lambda p: minted.get(id(p)))}
        self.assertEqual("_1840_01_05_matfej_andreevich_brjuhin-ov_mk_births_1_father",
                         occs["father"].stub)
        self.assertIsNone(occs["child"].stub)

    def test_a_config_spelling_reaches_its_record(self):
        class _Consolidation:
            def config_name_for(self, res_name: str) -> str | None:
                return res_name.replace("ilarion", "illarion")
        o = occ("Иларион", "Даниилович")
        o.stub = "_1818_ilarion_daniilovich_father"
        found = f.by_stub([o], _Consolidation())
        self.assertIs(o, found["_1818_ilarion_daniilovich_father"])
        self.assertIs(o, found["_1818_illarion_daniilovich_father"])


class TestExtraction(unittest.TestCase):
    def test_birth_links_parents_and_spouses(self):
        from verso.ru.dsl.records.births import birth, birth_records
        from verso.ru.domain import person
        from verso.ru.gender import Gender
        recs = birth_records(
            "a", "f", "i", "c", "Горюхино", "церковь", 1840,
            birth(1, Gender.MALE,
                  child=person("Иван", "Фомин", "Сидоров"),
                  father=person("Фома", "Ильин", "Сидоров"),
                  mother=person("Анна", "Петрова")),
        )
        occs = f.extract_occurrences(recs, "births_1840.py")
        by_role = {o.role: o for o in occs}
        self.assertIn("father", by_role)
        self.assertIn("mother", by_role)
        self.assertIn("child", by_role)
        father, mother, child = by_role["father"], by_role["mother"], by_role["child"]
        # father's spouse == mother's key; child sits in both parents' children.
        self.assertIn(mother.key, father.spouses)
        self.assertIn(father.key, mother.spouses)
        self.assertIn(father.key, child.parents)
        self.assertIn(mother.key, child.parents)


class TestCensusExtraction(unittest.TestCase):
    def _records(self):
        from verso.ru.dsl.records.census import CensusRole, census_records, household, member
        from verso.ru.domain import person
        return census_records(
            "ГАТО", "10", "4", "4044", "Тестовка", 1858,
            household("7", member(1, person("Нил", "Пахомов", "Индюшев"), CensusRole.HEAD, age=40,
                                  parent_member=10), member(2, person("Дарья", "Семенова"), CensusRole.WIFE, age=39),
                      member(3, person("Андрей"), CensusRole.SON, age=10),
                      member(4, person("Петр", "Иванов"), CensusRole.GRANDSON, ref_member=3,
                             parent_member=3, age=1),
                      member(9, person("Фекла", "Лукина"), CensusRole.MOTHER, ref_member=1, age=63),
                      member(10, person("Пахом"), CensusRole.FATHER, ref_member=9, hidden=True)),
        )

    def _occs(self):
        return f.extract_occurrences(self._records(), "test_census_1858.py")

    def test_visible_members_emitted_hidden_skipped(self):
        occs = self._occs()
        self.assertEqual(len(occs), 5)  # 1,2,3,4,9 — hidden 10 skipped
        self.assertTrue(all(o.rec_type == "census" and o.year == 1858 for o in occs))
        self.assertEqual({o.role for o in occs},
                         {"member_1", "member_2", "member_3", "member_4", "member_9"})

    def test_head_wife_spouses_and_children(self):
        occs = {o.role: o for o in self._occs()}
        head, wife, son = occs["member_1"], occs["member_2"], occs["member_3"]
        self.assertIn(wife.key, head.spouses)
        self.assertIn(head.key, wife.spouses)
        self.assertIn(son.key, head.children)
        self.assertIn(head.key, son.parents)
        self.assertIn(wife.key, son.parents)   # co-parent via head's spouse

    def test_grandson_parent_via_parent_member(self):
        occs = {o.role: o for o in self._occs()}
        son, grandson = occs["member_3"], occs["member_4"]
        self.assertIn(son.key, grandson.parents)
        self.assertIn(grandson.key, son.children)
        self.assertNotIn(occs["member_1"].key, grandson.parents)

    def test_hidden_spouse_pairing_reaches_visible_widow(self):
        # hidden Пахом (ref_member=9) pairs with Фекла; head's parents become
        # BOTH Пахом and Фекла via parent_member=1 + the co-parent inference
        occs = {o.role: o for o in self._occs()}
        head = occs["member_1"]
        self.assertIn(("Пахомий", ""), head.parents)
        self.assertIn(("Фекла", "Лукинична"), head.parents)  # canonical form

    def test_age_gives_circa_birth_year(self):
        occs = {o.role: o for o in self._occs()}
        self.assertEqual(occs["member_1"].birth_date, (1818, None, None))

    def test_parse_tf_file_census(self):
        self.assertEqual(f.parse_tf_file("Маниловка/terraform/geni/rs_1858_1.tf"),
                         (1858, "census"))
        self.assertEqual(f.parse_tf_file("rs_1916_746-8-140_1.tf"), (1916, "census"))
        self.assertEqual(f.parse_tf_file("ir_1828_1.tf"), (1828, "census"))


if __name__ == "__main__":
    unittest.main()
