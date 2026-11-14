"""A drafted cluster may BE a person who already has a canonical.

Иларион Платонович had one built from РС 1834 and РС 1850; the sweep then
drafted a second from his six МК records. It could not notice: an
already-consolidated stub is skipped as a candidate, and the append check
compares generated key strings, where `ilarion_platonovich_tjulkin` never
collides with `ilarion_platonovich` — the key generator surname-qualifies
precisely to avoid colliding with bare given+patronymic keys.

Match on the person instead: same identity key plus a shared spouse, both
carrying a patronymic (a bare given name and a bare spouse name are far too
common to merge on).
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, stub, year, spouses=(), rec_type="birth", role="father",
        record_num=1):
    o = f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(),
        given=given, patr=patr, surname=None, gender="male", rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        spouses=set(spouses),
    )
    o.stub = stub
    return o


IRINA = ("Ирина", "Васильевна")
CENSUS_1850 = "_1850_10_01_ilarion_platonovich_rs_63_4_family_member"
BIRTH_1849 = "_1849_09_03_ilarion_platonovich_tjulkin_mk_births_31_father"
BIRTH_1855 = "_1855_01_17_ilarion_platonovich_mk_births_8_father"


def occ_map():
    return {
        CENSUS_1850: occ("Иларион", "Платонович", stub=CENSUS_1850, year=1850,
                         spouses=[IRINA], rec_type="census", role="member_4"),
        BIRTH_1849: occ("Иларион", "Платонович", stub=BIRTH_1849, year=1849,
                        spouses=[IRINA]),
        BIRTH_1855: occ("Иларион", "Платонович", stub=BIRTH_1855, year=1855,
                        spouses=[IRINA]),
    }


class TestExistingCanonicalFor(unittest.TestCase):
    def test_finds_the_cluster_holding_the_same_person(self):
        got = f.existing_canonical_for(
            [BIRTH_1849, BIRTH_1855],
            {"ilarion_platonovich": [CENSUS_1850]}, occ_map())
        self.assertEqual(got, "ilarion_platonovich")

    def test_requires_a_shared_spouse_not_just_the_name(self):
        occs = occ_map()
        occs[CENSUS_1850].spouses = {("Марфа", "Петровна")}
        self.assertIsNone(f.existing_canonical_for(
            [BIRTH_1849, BIRTH_1855],
            {"ilarion_platonovich": [CENSUS_1850]}, occs))

    def test_bare_given_name_never_matches(self):
        # ('Иван', '') sharing a spouse «Марфа» describes half the village.
        old_stub, new_stub = "_1830_01_01_ivan_f", "_1840_01_01_ivan_g"
        occs = {
            old_stub: occ("Иван", None, stub=old_stub, year=1830,
                          spouses=[("Марфа", None)]),
            new_stub: occ("Иван", None, stub=new_stub, year=1840,
                          spouses=[("Марфа", None)]),
        }
        self.assertIsNone(f.existing_canonical_for(
            [new_stub], {"ivan": [old_stub]}, occs))

    def test_no_occurrence_map_degrades_quietly(self):
        self.assertIsNone(f.existing_canonical_for(
            [BIRTH_1849], {"ilarion_platonovich": [CENSUS_1850]}, None))

    def test_ignores_the_cluster_being_drafted(self):
        # A stub cannot re-append to the cluster it already sits in.
        self.assertIsNone(f.existing_canonical_for(
            [BIRTH_1849], {"x": [BIRTH_1849]}, occ_map()))


class TestDraftRoutesToExistingCanonical(unittest.TestCase):
    def _targets(self):
        occs = occ_map()
        pub = {k: o.public() for k, o in occs.items()}

        def entry(t, c):
            return {"target": pub[t], "local": [
                {"confidence": "high", "score": 120,
                 "evidence": ["shared spouse: Ирина Васильевна"], "cand": pub[c]}],
                "geni": []}

        return [entry(BIRTH_1849, BIRTH_1855), entry(BIRTH_1855, BIRTH_1849)], occs

    def test_drafts_as_an_append_to_the_existing_cluster(self):
        targets, occs = self._targets()
        out = f.draft_config(targets, {"ilarion_platonovich": [CENSUS_1850]},
                             None, occs)
        self.assertIn('"ilarion_platonovich"', out)
        self.assertIn("APPEND to existing cluster", out)
        self.assertIn(CENSUS_1850, out)
        self.assertNotIn('"ilarion_platonovich_tjulkin"', out)

    def test_without_the_existing_cluster_it_drafts_a_new_key(self):
        targets, occs = self._targets()
        out = f.draft_config(targets, {}, None, occs)
        self.assertNotIn("APPEND to existing cluster", out)
        self.assertIn('"ilarion_platonovich"', out)


if __name__ == "__main__":
    unittest.main()
