"""Surname variants the RULES cannot derive, learned from the config instead.

Сундукин and Тюфякин are not spellings of one name — they are two family names for
one household, and no registry can connect them. But the consolidated clusters
already record it: a cluster holding both surnames is a curator's statement
that they co-refer. The same goes for Мижуев ~ Анучкин and Тарабаев ~ Тарабуев.

Deliberately limited to SURNAMES. The given name is the blocking key, so
teaching it variants would invent new candidate pairs; the surname only ever
corroborates a pair the family graph already found. And the learned pairs are
family-specific — «Михайлович ~ Онисимович» holds in one family and nowhere
else — so they must not gate anything.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, stub, surname=None, year=1840, spouses=(), rec_type="birth",
        role="father", record_num=1):
    o = f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(), given=given,
        patr=patr, surname=surname, gender="male", rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        spouses=set(spouses),
    )
    o.stub = stub
    return o


WIFE = ("Анна", "Ивановна")


class TestLearnSurnameVariants(unittest.TestCase):
    def _occs(self):
        return {
            "_1849_a": occ("Антон", "Семенович", stub="_1849_a", surname="Сундукин"),
            "_1855_b": occ("Антон", "Семенович", stub="_1855_b", surname="Тюфякин"),
            "_1860_c": occ("Иван", "Петрович", stub="_1860_c", surname="Мижуев"),
            "_1862_d": occ("Иван", "Петрович", stub="_1862_d", surname="Анучкин"),
        }

    def test_learns_a_pair_held_by_one_cluster(self):
        aliases = f.learn_surname_variants(
            {"anton": ["_1849_a", "_1855_b"]}, self._occs())
        self.assertIn(("Сундукин", "Тюфякин"), aliases)
        self.assertEqual(aliases[("Сундукин", "Тюфякин")], 1)

    def test_counts_distinct_clusters(self):
        occs = self._occs()
        occs["_1870_e"] = occ("Пётр", "Ильич", stub="_1870_e", surname="Сундукин")
        occs["_1872_f"] = occ("Пётр", "Ильич", stub="_1872_f", surname="Тюфякин")
        aliases = f.learn_surname_variants(
            {"anton": ["_1849_a", "_1855_b"], "petr": ["_1870_e", "_1872_f"]}, occs)
        self.assertEqual(aliases[("Сундукин", "Тюфякин")], 2)

    def test_pair_is_stored_orientation_independently(self):
        aliases = f.learn_surname_variants({"c": ["_1862_d", "_1860_c"]}, self._occs())
        self.assertIn(("Анучкин", "Мижуев"), aliases)

    def test_single_surname_cluster_teaches_nothing(self):
        self.assertEqual(f.learn_surname_variants({"c": ["_1849_a"]}, self._occs()), {})

    def test_no_occurrence_map_degrades_quietly(self):
        self.assertEqual(f.learn_surname_variants({"c": ["_1849_a"]}, None), {})


class TestScoringWithLearnedSurnames(unittest.TestCase):
    def _pair(self):
        t = occ("Антон", "Семенович", stub="_1849_x", surname="Сундукин",
                spouses=[WIFE], record_num=1)
        c = occ("Антон", "Семенович", stub="_1855_y", surname="Тюфякин",
                spouses=[WIFE], record_num=2, year=1855)
        return t, c

    def test_learned_variant_is_reported_as_evidence(self):
        t, c = self._pair()
        s = f.score_pair(t, c, surname_aliases={("Сундукин", "Тюфякин"): 3})
        assert s is not None
        hit = [e for e in s.evidence if "learned surname" in e]
        self.assertEqual(len(hit), 1, s.evidence)
        self.assertIn("Сундукин", hit[0])
        self.assertIn("Тюфякин", hit[0])

    def test_learned_variant_adds_score(self):
        t, c = self._pair()
        plain = f.score_pair(t, c)
        learned = f.score_pair(t, c, surname_aliases={("Сундукин", "Тюфякин"): 3})
        assert plain is not None and learned is not None
        self.assertGreater(learned.score, plain.score)

    def test_it_never_creates_a_pair_on_its_own(self):
        # No shared relative, no date proximity: a learned surname must not
        # lift a name-only pair into being draftable.
        t = occ("Антон", "Семенович", stub="_1700_x", surname="Сундукин", year=1700)
        c = occ("Антон", "Семенович", stub="_1855_y", surname="Тюфякин",
                year=1855, record_num=2)
        s = f.score_pair(t, c, surname_aliases={("Сундукин", "Тюфякин"): 3})
        assert s is not None
        self.assertNotEqual(s.confidence, "high")

    def test_unknown_pair_changes_nothing(self):
        t, c = self._pair()
        a = f.score_pair(t, c)
        b = f.score_pair(t, c, surname_aliases={("Ахинеев", "Нюхин"): 4})
        assert a is not None and b is not None
        self.assertEqual(a.score, b.score)
        self.assertEqual(a.evidence, b.evidence)


if __name__ == "__main__":
    unittest.main()
