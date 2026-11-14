"""Two baptismal entries are two children, never one person recorded twice.

A metric book enumerates one baptism per entry, exactly as a сказка enumerates
one member per line. Parents reuse a dead child's given name, so given name,
surname and both parents can agree while the pair is still two people — and
the shared-parent bonus alone scores that HIGH.

The case that motivated the gate: a boy born in July and again the next June to
the same couple.
"""
import unittest

from verso.ru.consolidation import candidates as f


def occ(*, rec_type, role, year, record_num=1, parents=None, age=None,
        source_file="t.py"):
    return f.Occurrence(
        key=("Владимир", "Петрович"), name="Владимир Петрович", given="Владимир",
        patr="Петрович", surname="Ежевикин", gender="male", rec_type=rec_type,
        record_num=record_num, role=role, year=year, source_file=source_file,
        parents=set(parents or []), age=age,
    )


DAD = ("Пётр", "Семёнович")
MUM = ("Агафья", "Матвеевна")


def born(year, record_num, **kw):
    return occ(rec_type="birth", role="child", year=year,
               record_num=record_num, parents=[DAD, MUM],
               source_file=f"{year}.py", **kw)


class TestTwoBaptismsGate(unittest.TestCase):
    def test_two_birth_records_never_pair(self):
        self.assertIsNone(f.score_pair(born(1894, 5), born(1895, 6)))
        self.assertIsNone(f.score_pair(born(1895, 6), born(1894, 5)))  # symmetric

    def test_gate_holds_across_a_long_gap(self):
        # A girl born in 1892 and again in 1905 to the same couple.
        self.assertIsNone(f.score_pair(born(1892, 6), born(1905, 9)))

    def test_born_and_died_infant_still_pairs(self):
        # The legitimate fold: a birth record's child + a death record's
        # deceased. Unaffected by the gate.
        birth = born(1905, 7)
        birth.birth_date = (1905, 6, 20)
        death = occ(rec_type="death", role="deceased", year=1910, record_num=8,
                    parents=[DAD], age=5, source_file="1910.py")
        death.death_date = (1910, 9, 24)
        self.assertIsNotNone(f.score_pair(birth, death))

    def test_child_and_census_member_still_pairs(self):
        member = occ(rec_type="census", role="member_7", year=1893,
                     record_num=13, parents=[DAD, MUM], source_file="1893.py")
        self.assertIsNotNone(f.score_pair(born(1892, 6), member))

    def test_predicate_is_false_for_mixed_roles(self):
        self.assertFalse(f.two_baptisms_conflict(
            born(1892, 6),
            occ(rec_type="birth", role="father", year=1920, parents=[]),
        ))


if __name__ == "__main__":
    unittest.main()
