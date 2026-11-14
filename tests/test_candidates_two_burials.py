"""Two burial entries are two namesakes, never one person recorded twice.

A person is buried once. A metric book's часть 3 enumerates one burial per
entry, exactly as часть 1 enumerates one baptism (see
`test_candidates_two_baptisms`) and a сказка one member per line — so two
death records dated differently are two people, however well the name, the
patronymic, the surname and the parents agree. And they do agree: a family
buried an Иван Фёдорович in one year and another seven years later, and the
shared-parent bonus alone scored the pair HIGH.

Rejecting such pairs by hand in the consolidation config was not enough; the
sweep re-proposed them on every run.

Same-date pairs stay eligible: two death records of one day may be one
burial transcribed twice, which IS a duplicate.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(*, rec_type, role, year, record_num=1, parents=None, age=None,
        source_file="t.py"):
    return f.Occurrence(
        key=("Иван", "Фёдорович"), name="Иван Фёдорович Ежевикин", given="Иван",
        patr="Фёдорович", surname="Ежевикин", gender="male", rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file=source_file,
        parents=set(parents or []), age=age,
    )


DAD = ("Фёдор", "Иванович")
MUM = ("Пелагея", "Фёдоровна")


def buried(year, month, day, record_num, **kw):
    o = occ(rec_type="death", role="deceased", year=year, record_num=record_num,
            parents=[DAD, MUM], source_file=f"{year}.py", **kw)
    o.death_date = (year, month, day)
    return o


class TestTwoBurialsGate(unittest.TestCase):
    def test_two_death_records_never_pair(self):
        # The same name, parents and surname, buried seven years apart.
        a, b = buried(1897, 1, 11, 6), buried(1904, 7, 3, 23)
        self.assertIsNone(f.score_pair(a, b))
        self.assertIsNone(f.score_pair(b, a))  # symmetric

    def test_gate_holds_within_one_year(self):
        # Two burials of one year are still two burials.
        self.assertIsNone(f.score_pair(buried(1912, 6, 18, 17),
                                       buried(1912, 11, 2, 42)))

    def test_undated_burials_of_different_years_are_two_people(self):
        # No month/day recorded: the years alone already separate them.
        a, b = buried(1891, None, None, 12), buried(1898, None, None, 21)
        self.assertIsNone(f.score_pair(a, b))

    def test_same_date_still_pairs(self):
        # One burial entered under two numbers — a real duplicate, and the
        # only death+death pair the gate leaves eligible. A scribe may enter
        # one girl's burial more than once on one day: those entries still
        # pair, while an entry of another day does not.
        a, b = buried(1905, 6, 24, 20), buried(1905, 6, 24, 46)
        self.assertIsNotNone(f.score_pair(a, b))

    def test_partially_dated_pair_still_pairs(self):
        # Nothing positively contradicts: do not silently retire the pair.
        self.assertIsNotNone(f.score_pair(buried(1905, 6, 24, 20),
                                          buried(1905, 6, None, 21)))

    def test_born_and_died_infant_still_pairs(self):
        # The legitimate infant fold: birth record's child + death record's
        # deceased. One baptism, one burial — untouched by the gate.
        birth = occ(rec_type="birth", role="child", year=1904, record_num=20,
                    parents=[DAD, MUM], source_file="1904.py")
        birth.birth_date = (1904, 6, 11)
        self.assertIsNotNone(f.score_pair(birth, buried(1907, 12, 21, 43, age=3)))

    def test_deceased_and_census_member_still_pair(self):
        member = occ(rec_type="census", role="member_7", year=1900,
                     record_num=7, parents=[DAD, MUM], source_file="1900.py")
        self.assertIsNotNone(f.score_pair(member, buried(1904, 7, 3, 23)))

    def test_predicate_is_false_for_mixed_roles(self):
        # A death record's `relative` (the bereaved father) is a living person
        # named by the entry, not a second burial.
        relative = occ(rec_type="death", role="relative", year=1904,
                       record_num=23, source_file="1904.py")
        self.assertFalse(f.two_burials_conflict(buried(1897, 1, 11, 6), relative))


if __name__ == "__main__":
    unittest.main()
