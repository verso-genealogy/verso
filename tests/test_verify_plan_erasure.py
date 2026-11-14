#!/usr/bin/env python3
"""The gate's value check: an in-place update that EMPTIES a field Geni holds.

The four structural checks never compare values, so a plan they call clean can
still blank what a co-author filled in, or what the generator stopped carrying.
Both happen: a clean plan can be about to detach two wives and drop wedding
dates, surnames and baptisms; a fold can lose the occupation a WWII card had
given the canonical («чернорабочий»). Each case below is one of those, or one
of the reshapings a plan shows that are NOT a loss.
"""
from __future__ import annotations

import unittest

from verso.ru.consolidation import verify_plan as vp


def _update(rtype, name, before, after, after_unknown=None):
    return {
        "address": f"{rtype}.{name}",
        "type": rtype,
        "change": {"actions": ["update"], "before": before, "after": after,
                   "after_unknown": after_unknown or {}},
    }


def _plan(*changes, drift=()):
    return {"resource_changes": list(changes), "resource_drift": list(drift)}


def _drift(rtype, name, stored, refreshed):
    return {"address": f"{rtype}.{name}", "type": rtype,
            "change": {"actions": ["update"], "before": stored, "after": refreshed}}


def _erasures(plan, **kw):
    return [v for v in vp.check_plan(plan, **kw) if v.kind == "field_erasure"]


class ErasedScalars(unittest.TestCase):
    def test_an_emptied_occupation_is_an_error(self):
        """A fold dropped the occupation a WWII card gave the canonical."""
        plan = _plan(_update(
            "geni_profile", "ivan_petrovich_sidorov",
            {"id": "p1", "occupation": "чернорабочий"}, {"id": "p1", "occupation": None}))
        [v] = _erasures(plan)
        self.assertEqual("error", v.severity)
        self.assertEqual("geni_profile.ivan_petrovich_sidorov", v.address)
        self.assertIn("occupation", v.detail)
        self.assertIn("чернорабочий", v.detail)

    def test_a_changed_value_is_not_an_erasure(self):
        plan = _plan(_update("geni_profile", "x", {"occupation": "пахарь"},
                             {"occupation": "чернорабочий"}))
        self.assertEqual([], _erasures(plan))

    def test_an_erased_surname_inside_a_locale(self):
        plan = _plan(_update(
            "geni_profile", "x",
            {"names": {"ru": {"first_name": "Ирина", "last_name": "Стужева"}}},
            {"names": {"ru": {"first_name": "Ирина", "last_name": None}}}))
        [v] = _erasures(plan)
        self.assertIn("names.ru.last_name", v.detail)
        self.assertIn("Стужева", v.detail)

    def test_computed_fields_are_never_erasures(self):
        """Read back from Geni, never sent: the event name Geni derives from the
        profile name, a geocode, the profile's own union list."""
        plan = _plan(_update(
            "geni_profile", "x",
            {"unions": ["u1"], "birth": {"name": "Birth of X",
                                         "date": {"year": 1850},
                                         "location": {"city": "Горюхино",
                                                      "latitude": 53.1}}},
            {"unions": [], "birth": {"name": None, "date": {"year": 1850},
                                     "location": {"city": "Горюхино",
                                                  "latitude": None}}}))
        self.assertEqual([], _erasures(plan))

    def test_an_unknown_sibling_does_not_hide_the_erasure(self):
        """Every refreshed profile update marks `unions` known-after-apply. The
        first cut of this check skipped a node with ANY unknown descendant, so it
        skipped every profile — and passed the real plan."""
        plan = _plan(_update(
            "geni_profile", "ivan_petrovich_sidorov",
            {"id": "p1", "unions": ["u1"], "occupation": "чернорабочий"},
            {"id": "p1", "unions": None, "occupation": None},
            after_unknown={"unions": True}))
        [v] = _erasures(plan)
        self.assertIn("чернорабочий", v.detail)

    def test_a_value_known_only_after_apply_is_not_erased(self):
        plan = _plan(_update("geni_profile", "x", {"occupation": "пахарь"},
                             {"occupation": None}, after_unknown={"occupation": True}))
        self.assertEqual([], _erasures(plan))


class ErasedEvents(unittest.TestCase):
    def test_a_whole_event_is_reported_once(self):
        """A baptism a co-author added, which the config does not carry."""
        plan = _plan(_update(
            "geni_profile", "x",
            {"baptism": {"name": "Baptism", "date": {"year": 1841, "month": 3},
                         "location": {"city": "Горюхино"}}},
            {"baptism": None}))
        [v] = _erasures(plan)
        self.assertIn("baptism", v.detail)
        self.assertNotIn("baptism.date", v.detail)

    def test_an_emptied_wedding_date(self):
        plan = _plan(_update(
            "geni_union", "ivan_and_anna",
            {"marriage": {"date": {"year": 1842, "month": 1, "day": 20},
                          "location": {"city": "Горюхино"}}},
            {"marriage": {"date": None, "location": {"city": "Горюхино"}}}))
        [v] = _erasures(plan)
        self.assertIn("marriage.date", v.detail)
        self.assertIn("1842", v.detail)

    def test_a_death_bound_is_a_date(self):
        """«alive after 1850», a co-author's death bound from the 1850 roll."""
        plan = _plan(_update(
            "geni_profile", "x",
            {"death": {"date": {"year": 1850, "range": "after"}}}, {"death": None}))
        [v] = _erasures(plan)
        self.assertIn("death", v.detail)

    def test_a_range_narrowed_to_a_point_is_not_an_erasure(self):
        """«between 1885 and 1886» replaced by the record's year — the range
        fields empty, the date does not."""
        plan = _plan(_update(
            "geni_profile", "petr_ivanovich_vidopljasov",
            {"birth": {"date": {"year": 1885, "circa": True, "range": "between",
                                "end_year": 1886, "end_circa": True}}},
            {"birth": {"date": {"year": 1886, "circa": False, "range": None,
                                "end_year": None, "end_circa": None}}}))
        self.assertEqual([], _erasures(plan))

    def test_a_place_name_giving_way_to_an_address_is_not_an_erasure(self):
        plan = _plan(_update(
            "geni_profile", "x",
            {"birth": {"location": {"place_name": "Горюхино"}}},
            {"birth": {"location": {"place_name": None, "city": "Горюхино",
                                    "county": "Ротозейский уезд"}}}))
        self.assertEqual([], _erasures(plan))

    def test_an_emptied_location_is_an_erasure(self):
        plan = _plan(_update(
            "geni_profile", "x",
            {"current_residence": {"city": "Горюхино", "latitude": 53.1}},
            {"current_residence": None}))
        [v] = _erasures(plan)
        self.assertIn("current_residence", v.detail)


class LostMembers(unittest.TestCase):
    def test_a_detached_wife_is_an_error(self):
        plan = _plan(_update(
            "geni_union", "ivan_and_anna",
            {"partners": ["profile-ivan", "profile-anna"]},
            {"partners": ["profile-ivan"]}))
        [v] = _erasures(plan)
        self.assertIn("partners", v.detail)
        self.assertIn("profile-anna", v.detail)

    def test_a_swap_is_not_a_loss(self):
        """A fold: the stub's id gives way to its canonical's. Real plans do this
        to union children and to a document's tagged profiles."""
        plan = _plan(
            _update("geni_union", "u", {"children": ["profile-a", "profile-stub"]},
                    {"children": ["profile-a", "profile-canon"]}),
            _update("geni_document", "d", {"profiles": ["profile-stub"]},
                    {"profiles": ["profile-canon", "profile-other"]}))
        self.assertEqual([], _erasures(plan))

    def test_a_member_not_yet_created_counts_as_gained(self):
        """A child being created has no id at plan time: terraform writes null."""
        plan = _plan(_update("geni_union", "u", {"children": ["profile-stub"]},
                             {"children": [None]}))
        self.assertEqual([], _erasures(plan))

    def test_a_transliterated_nickname_is_not_a_loss(self):
        plan = _plan(_update(
            "geni_profile", "x", {"names": {"en-US": {"nicknames": ["Иван"]}}},
            {"names": {"en-US": {"nicknames": ["Ivan"]}}}))
        self.assertEqual([], _erasures(plan))


class WhichActions(unittest.TestCase):
    def test_forget_is_releasing_not_erasing(self):
        """removed{destroy=false}: `after` is null wholesale."""
        plan = {"resource_changes": [{
            "address": "geni_profile.stub", "type": "geni_profile",
            "change": {"actions": ["forget"], "before": {"occupation": "пахарь"},
                       "after": None}}]}
        self.assertEqual([], _erasures(plan))


class WhoseValue(unittest.TestCase):
    def test_a_value_added_on_geni_since_the_last_apply(self):
        """The refresh brought it in: someone edited the profile on Geni."""
        plan = _plan(
            _update("geni_profile", "x", {"cause_of_death": "от старости"},
                    {"cause_of_death": None}),
            drift=[_drift("geni_profile", "x", {"cause_of_death": None},
                          {"cause_of_death": "от старости"})])
        [v] = _erasures(plan)
        self.assertIn("edited on Geni", v.detail)

    def test_a_value_this_config_applied_before(self):
        plan = _plan(_update("geni_profile", "x", {"cause_of_death": "от старости"},
                             {"cause_of_death": None}))
        [v] = _erasures(plan)
        self.assertIn("applied from this config", v.detail)


class Acknowledged(unittest.TestCase):
    def test_allow_erasure_keeps_the_report_and_lets_the_plan_through(self):
        plan = _plan(_update("geni_profile", "x", {"occupation": "пахарь"},
                             {"occupation": None}))
        [v] = _erasures(plan, allow_erasure=True)
        self.assertEqual("warning", v.severity)

    def test_allow_erasure_touches_nothing_else(self):
        plan = {"resource_changes": [{
            "address": "geni_profile.x", "type": "geni_profile",
            "change": {"actions": ["delete"], "before": {"id": "p1"}, "after": None}}]}
        [v] = vp.check_plan(plan, allow_erasure=True)
        self.assertEqual(("error", "profile_delete"), (v.severity, v.kind))


if __name__ == "__main__":
    unittest.main()
