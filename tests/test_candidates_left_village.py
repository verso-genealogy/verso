"""A ревизская сказка records where a departing member went. Once she is
«выдана замуж» into ANOTHER settlement, no later record of this parish is her.

The case that motivated this: a member whose destination names another village
(«выдана замуж в той же округе в деревню … за ясачного») was matched to a
later bride and a later census wife of this parish. Three different women.

The distinction that matters: another member of the SAME household is also
«выдана замуж», but with no destination — «в том же селе», so she stays
matchable. The field to key on is `destination`, never `departure_reason`.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(given, patr, *, rec_type, role, year, surname=None, gender="female",
        record_num=1, parents=None, spouses=None, destination=None,
        departed=False):
    return f.Occurrence(
        key=(given, patr), name=f"{given} {patr or ''}".strip(), given=given,
        patr=patr, surname=surname, gender=gender, rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file="t.py",
        parents=set(parents or []), spouses=set(spouses or []),
        destination=destination, departed=departed,
    )


DAD = ("Леонтий", "Кондратьевич")
HUSBAND = ("Григорий", "Иванович")


def departed_daughter(destination="Хлестаковка", year=1797):
    return occ("Мария", "Леонтиевна", rec_type="census", role="member_9",
               year=year, record_num=33, parents=[DAD], destination=destination,
               departed=True)


class TestLeftVillageGate(unittest.TestCase):
    def test_later_bride_after_leaving_is_rejected(self):
        bride = occ("Мария", "Леонтиевна", rec_type="marriage", role="bride",
                    year=1807, spouses=[HUSBAND], parents=[DAD])
        self.assertIsNone(f.score_pair(departed_daughter(), bride))
        self.assertIsNone(f.score_pair(bride, departed_daughter()))  # symmetric

    def test_later_census_wife_after_leaving_is_rejected(self):
        wife = occ("Мария", "Леонтиевна", rec_type="census", role="member_2",
                   year=1836, record_num=41, spouses=[HUSBAND], parents=[DAD])
        self.assertIsNone(f.score_pair(departed_daughter(), wife))

    def test_later_mother_after_leaving_is_rejected(self):
        # She would bear children in her husband's parish, not ours.
        mother = occ("Мария", "Леонтиевна", rec_type="birth", role="mother",
                     year=1812, spouses=[HUSBAND], parents=[DAD])
        self.assertIsNone(f.score_pair(departed_daughter(), mother))

    def test_married_within_the_village_still_pairs(self):
        # another member: «выдана замуж», no destination — «в том же селе».
        stayed = occ("Мария", "Леонтиевна", rec_type="census", role="member_8",
                     year=1797, record_num=33, parents=[DAD], departed=True)
        mother = occ("Мария", "Леонтиевна", rec_type="birth", role="mother",
                     year=1812, spouses=[HUSBAND], parents=[DAD])
        s = f.score_pair(stayed, mother)
        self.assertIsNotNone(s)

    def test_record_before_the_departure_still_pairs(self):
        # An EARLIER revision (own household numbering, so not the
        # same-household gate) is her too — she had not left yet.
        earlier = occ("Мария", "Леонтиевна", rec_type="census", role="member_4",
                      year=1784, record_num=27, parents=[DAD])
        self.assertIsNotNone(f.score_pair(departed_daughter(), earlier))

    def test_later_relative_mention_still_pairs(self):
        # Naming an absent woman as someone's relative implies nothing about
        # where she lives.
        rel = occ("Мария", "Леонтиевна", rec_type="death", role="relative",
                  year=1832, parents=[DAD])
        self.assertIsNotNone(f.score_pair(departed_daughter(), rel))

    def test_member_without_destination_is_untouched(self):
        plain = occ("Мария", "Леонтиевна", rec_type="census", role="member_9",
                    year=1797, record_num=33, parents=[DAD])
        mother = occ("Мария", "Леонтиевна", rec_type="birth", role="mother",
                     year=1812, spouses=[HUSBAND], parents=[DAD])
        self.assertIsNotNone(f.score_pair(plain, mother))


class TestLeftVillagePredicate(unittest.TestCase):
    def test_predicate_is_public_and_symmetric(self):
        d = departed_daughter()
        later = occ("Мария", "Леонтиевна", rec_type="marriage", role="bride",
                    year=1807, parents=[DAD])
        self.assertTrue(f.left_village_conflict(d, later))
        self.assertTrue(f.left_village_conflict(later, d))
        self.assertFalse(f.left_village_conflict(d, departed_daughter(year=1784)))


class TestAppendConflict(unittest.TestCase):
    """The scorer never sees this pair: the 1797 stub is already consolidated,
    so it is skipped as a candidate and the merge arrives through the APPEND
    path instead. The same predicates must run across the merge boundary."""

    GONE = "_1797_00_00_marija_leontievna_rs_33_9_family_member"
    BRIDE = "_1807_02_05_marija_leontievna_mk_marriages_1_bride"
    WIFE = "_1836_02_20_marija_rs_41_2_family_member"

    def _stubbed(self, o, stub):
        o.stub = stub
        return o

    def _occs(self):
        gone = self._stubbed(departed_daughter(), self.GONE)
        bride = self._stubbed(
            occ("Мария", "Леонтиевна", rec_type="marriage", role="bride",
                year=1807, spouses=[HUSBAND]), self.BRIDE)
        wife = self._stubbed(
            occ("Мария", "Леонтиевна", rec_type="census", role="member_2",
                year=1836, record_num=41, spouses=[HUSBAND]), self.WIFE)
        return {self.GONE: gone, self.BRIDE: bride, self.WIFE: wife}

    def test_append_onto_a_departed_member_is_refused(self):
        why = f.append_conflict([self.GONE], [self.BRIDE, self.WIFE], self._occs())
        self.assertIsNotNone(why)
        assert why is not None
        self.assertIn("Хлестаковка", why)

    def test_append_onto_a_death_record_is_refused(self):
        dead_stub = "_1843_02_15_daria_lukinichna_mk_deaths_1_deceased"
        later_stub = "_1852_10_01_daria_lukinichna_vishnevskaja_rs_38_20_family_member"
        by_stub = {
            dead_stub: self._stubbed(
                occ("Дарья", "Лукинична", rec_type="death",
                    role="deceased", year=1843), dead_stub),
            later_stub: self._stubbed(
                occ("Дарья", "Лукинична", rec_type="census",
                    role="member_20", year=1852, record_num=38), later_stub),
        }
        why = f.append_conflict([dead_stub], [later_stub], by_stub)
        self.assertIsNotNone(why)
        assert why is not None
        self.assertIn("death record", why)

    def test_clean_append_is_allowed(self):
        by_stub = self._occs()
        # Same two records, but the existing cluster holds an ordinary member.
        by_stub[self.GONE] = self._stubbed(
            occ("Мария", "Леонтиевна", rec_type="census", role="member_9",
                year=1797, record_num=33), self.GONE)
        self.assertIsNone(
            f.append_conflict([self.GONE], [self.BRIDE, self.WIFE], by_stub))

    def test_no_occurrence_map_degrades_quietly(self):
        # --synthesize re-reads candidates.json and has no occurrences.
        self.assertIsNone(f.append_conflict(["_1797_x"], ["_1807_y"], None))


if __name__ == "__main__":
    unittest.main()
