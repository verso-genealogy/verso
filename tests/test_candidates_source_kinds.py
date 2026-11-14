"""The sweep must not decide what a record is by pattern-matching a res_name.

Two defects of one shape, both found while planning the facts layer:

1. `_RS_TAIL_RE` hardcoded `_rs_`, so an исповедная роспись — which emits
   `ir`-keyed member profiles because `CONFESSION_LIST` pins `file_prefix="ir"`
   — was invisible to the regex resolver. Since 2026-09-28 there is no
   resolver: an occurrence is placed on the profile minted for its object.

2. A death record's `b_day`/`b_month` are the BURIAL date (see
   the extraction rules), but a birth record's fields of the same name
   are the BIRTH date. The occurrence builder copied the birth branch and wrote
   a burial into `birth_date` — the same attribute name meaning two things in
   two record kinds, which is exactly the disease the facts layer is meant to
   cure.
"""
from __future__ import annotations

import unittest

from calendar import Month

from verso.ru.consolidation import candidates as f
from verso.ru.domain import person
from verso.ru.dsl.records.deaths import death, death_records
from verso.ru.gender import Gender


class ConfessionListStubs(unittest.TestCase):
    """An ИР member is placed like a revision member: on the profile minted for
    it, whatever prefix its res_name carries."""

    def test_confession_member_is_placed(self):
        from verso.ru.dsl.records.census import (
            CONFESSION_LIST, CensusRole, census_records, household, member)
        roll = census_records("ГАРО", "735", "265", "53", "Заманиловка", 1828,
                              household("94", member(1, person("Максимъ"), CensusRole.HEAD,
                                                     age=50),
                                        member(5, person("Яковъ", "Максимовъ"),
                                               CensusRole.SON, age=20)),
                              **CONFESSION_LIST, record_month=Month.MARCH)
        # Keyed by the object the ROLL holds, as the translator's is.
        jakov = next(m.person for m in roll.households[0].members if m.number == 5)
        name = "_1828_03_00_jakov_maksimovich_ir_94_5_family_member"
        occs = {o.role: o for o in f.extract_occurrences(
            roll, "ir.py", stub_of=lambda p: name if p is jakov else None)}
        self.assertEqual(name, occs["member_5"].stub)


class DeathRecordBurialDate(unittest.TestCase):
    def _records(self):
        return death_records(
            "ГАТО", "2041", "94", "8", "Горюхино", "Николая Чудотворца", 1875,
            death(1, Gender.MALE, deceased=person("Иван", "Петров"), age=40,
                  d_day=3, d_month=Month.MARCH, b_day=5, b_month=Month.MARCH),
        )

    def _deceased(self) -> f.Occurrence:
        occs = f.extract_occurrences(self._records(), "d.py")
        dec = [o for o in occs if o.role == "deceased"]
        self.assertEqual(1, len(dec))
        return dec[0]

    def test_death_date_is_recorded(self):
        self.assertEqual((1875, 3, 3), self._deceased().death_date)

    def test_burial_is_not_filed_as_a_birth(self):
        """A burial is not a birth, however alike the DSL field names look."""
        self.assertIsNone(self._deceased().birth_date)

    def test_burial_is_kept_under_its_own_name(self):
        self.assertEqual((1875, 3, 5), self._deceased().burial_date)
