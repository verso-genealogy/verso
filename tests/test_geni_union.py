"""Unit tests for `geni_union._ref` and `GeniUnion.to_terraform`.

Covers the three reference forms recognised by `_ref`:
- ``data.geni_profile.X`` → data-source reference (emit as-is + ``.id,``)
- ``profile-NNNNN`` → raw Geni id (emit as a quoted string literal)
- everything else → local managed-resource reference (``geni_profile.<name>.id,``)
"""

import unittest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.union import GeniUnion, _ref


class TestRef(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(_ref(None), "")

    def test_empty_string_returns_empty(self):
        self.assertEqual(_ref(""), "")

    def test_local_resource_name(self):
        self.assertEqual(_ref("ivan_petrovich"), "geni_profile.ivan_petrovich.id,")

    def test_local_resource_name_with_underscore_prefix(self):
        # Names generated from MK records start with `_<year>_<month>_...`.
        self.assertEqual(
            _ref("_1909_05_15_darja_ivanovna_mk_births_38_mother"),
            "geni_profile._1909_05_15_darja_ivanovna_mk_births_38_mother.id,",
        )

    def test_raw_profile_id(self):
        self.assertEqual(_ref("profile-12345"), '"profile-12345",')

    def test_raw_profile_id_long(self):
        self.assertEqual(_ref("profile-91234567890"), '"profile-91234567890",')

    def test_data_source_ref(self):
        self.assertEqual(
            _ref("data.geni_profile.ivan_gavrilovich_sidorov"),
            "data.geni_profile.ivan_gavrilovich_sidorov.id,",
        )

    def test_data_source_ref_with_p_suffix_naming(self):
        # `p_<id>` fallback names used when the underlying Geni profile is
        # nameless.
        self.assertEqual(
            _ref("data.geni_profile.p_38662140"),
            "data.geni_profile.p_38662140.id,",
        )

    def test_data_prefix_takes_precedence_over_profile_substring(self):
        # A data-source name that happens to contain the substring
        # `profile-` (e.g. a sloppy name) must still be routed to the
        # data-source branch because the prefix check runs first.
        self.assertEqual(
            _ref("data.geni_profile.weird_profile-name"),
            "data.geni_profile.weird_profile-name.id,",
        )


class TestGeniUnionToTerraform(unittest.TestCase):
    def test_two_local_partners_no_children(self):
        u = GeniUnion(res_name="test_union", partner_1="father", partner_2="mother")
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "test_union" {\n'
            "  partners = [\n"
            "    geni_profile.father.id,\n"
            "    geni_profile.mother.id,\n"
            "  ]\n"
            "}\n\n",
        )

    def test_single_partner_with_one_local_child(self):
        u = GeniUnion(res_name="single_parent", partner_1="widow", children={"kid_a"})
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "single_parent" {\n'
            "  partners = [\n"
            "    geni_profile.widow.id,\n"
            "  ]\n"
            "  children = [\n"
            "    geni_profile.kid_a.id,\n"
            "  ]\n"
            "}\n\n",
        )

    def test_children_mix_all_three_ref_types(self):
        # Children list mixes a local resource, a data source, and a raw id.
        # The block sorts entries by string, so the data-source ref
        # ("data....") comes first, then the local name, then the raw id.
        u = GeniUnion(
            res_name="mixed_kids",
            partner_1="father",
            partner_2="mother",
            children={"local_kid", "profile-99999", "data.geni_profile.external_kid"},
        )
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "mixed_kids" {\n'
            "  partners = [\n"
            "    geni_profile.father.id,\n"
            "    geni_profile.mother.id,\n"
            "  ]\n"
            "  children = [\n"
            "    data.geni_profile.external_kid.id,\n"
            "    geni_profile.local_kid.id,\n"
            '    "profile-99999",\n'
            "  ]\n"
            "}\n\n",
        )

    def test_raw_profile_id_partners(self):
        u = GeniUnion(
            res_name="raw_id_partners",
            partner_1="profile-12345",
            partner_2="profile-67890",
        )
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "raw_id_partners" {\n'
            "  partners = [\n"
            '    "profile-12345",\n'
            '    "profile-67890",\n'
            "  ]\n"
            "}\n\n",
        )

    def test_data_source_partner_mixed_with_local(self):
        u = GeniUnion(
            res_name="mixed_partners",
            partner_1="data.geni_profile.external_father",
            partner_2="local_mother",
        )
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "mixed_partners" {\n'
            "  partners = [\n"
            "    data.geni_profile.external_father.id,\n"
            "    geni_profile.local_mother.id,\n"
            "  ]\n"
            "}\n\n",
        )

    def test_marriage_event_emitted(self):
        u = GeniUnion(
            res_name="with_marriage",
            partner_1="father",
            partner_2="mother",
            marriage=GeniEvent(date=GeniDate(year=1900, month=5, day=12)),
        )
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "with_marriage" {\n'
            "  partners = [\n"
            "    geni_profile.father.id,\n"
            "    geni_profile.mother.id,\n"
            "  ]\n"
            "  marriage = {\n"
            "    date = {\n"
            "      day   = 12\n"
            "      month = 5\n"
            "      year  = 1900\n"
            "    }\n"
            "  }\n"
            "}\n\n",
        )

    def test_empty_partner_2_only_emits_partner_1(self):
        u = GeniUnion(res_name="solo", partner_1="lone_widow")
        # Only one partner appears in the `partners` list.
        self.assertEqual(
            u.to_terraform(),
            'resource "geni_union" "solo" {\n'
            "  partners = [\n"
            "    geni_profile.lone_widow.id,\n"
            "  ]\n"
            "}\n\n",
        )

    def test_no_children_attribute_when_set_is_empty(self):
        u = GeniUnion(res_name="childless", partner_1="father", partner_2="mother")
        # Asserts the rendered text does NOT contain `children =`.
        self.assertNotIn("children", u.to_terraform())


if __name__ == "__main__":
    unittest.main()
