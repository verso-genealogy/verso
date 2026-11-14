"""Tests for Geni merge-conflict inspection and external-data preservation.

`geni conflicts resolve` keeps the surviving profile's value for every field,
silently dropping anything a merged-in (e.g. external contributor's) profile
carried. `conflict_capture` inspects each conflict, classifies the data-loss
risk, and produces append-only captures that preserve the lost value in the
canonical's config. These tests cover the pure core (no `geni`/terraform I/O).
"""
import ast
import copy
import unittest
from types import SimpleNamespace

from verso.ru.pipeline.translate import make_consolidation
from verso.ru.consolidation.conflict_capture import (
    Capture, additional_info_note, build_captures, classify_field, ensure_additional_info_note, format_report, resolve_command, resource_to_canonical, structured_suggestion, translate_field)
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.targets.geni.translator import TerraformGenerator


class TestTranslateField(unittest.TestCase):
    def test_name_fields_carry_locale(self):
        tf = translate_field("names/ru/last_name")
        self.assertEqual((tf.attr, tf.kind, tf.locale), ("last_name", "name", "ru"))
        self.assertEqual(translate_field("names/ru/maiden_name").attr, "birth_last_name")
        self.assertEqual(translate_field("names/en-US/first_name").locale, "en-US")

    def test_flat_fields(self):
        self.assertEqual(translate_field("death_date").attr, "death")
        self.assertEqual(translate_field("death_date").kind, "event")
        self.assertEqual(translate_field("current_residence").kind, "residence")
        self.assertEqual(translate_field("about_me").attr, "about")

    def test_unknown_field_is_other(self):
        tf = translate_field("public")
        self.assertIsNone(tf.attr)
        self.assertEqual(tf.kind, "other")


class TestClassifyField(unittest.TestCase):
    def test_external_added_when_primary_blank(self):
        self.assertEqual(classify_field("", ["1873"]), ("external_added", "1873"))

    def test_disagreement_when_both_present(self):
        self.assertEqual(classify_field("Сидоров", ["Сидорин"]), ("disagreement", "Сидорин"))

    def test_no_loss_when_others_echo_or_empty(self):
        self.assertEqual(classify_field("Иван", ["Иван", ""]), ("no_loss", None))
        self.assertEqual(classify_field("Иван", []), ("no_loss", None))


class TestBuildCaptures(unittest.TestCase):
    def _detail(self, fields):
        return {"has_conflict": True, "fields": fields}

    def test_skips_no_loss_and_non_ru_name_locales(self):
        detail = self._detail([
            {"field": "names/ru/first_name", "primary_value": "Иван",
             "other_values": ["Иван"]},                       # echo → no loss
            {"field": "names/en-US/last_name", "primary_value": "Markov",
             "other_values": ["Markin"]},                     # en-US → skipped
            {"field": "names/ru/last_name", "primary_value": "Сидоров",
             "other_values": ["Сидорин"]},                     # kept
            {"field": "death_date", "primary_value": "",
             "other_values": ["1873"]},                       # external-added
        ])
        caps = build_captures(detail, canonical="ivan", guid="600", manager="Ext")
        kinds = {(c.geni_field, c.classification) for c in caps}
        self.assertEqual(kinds, {
            ("names/ru/last_name", "disagreement"),
            ("death_date", "external_added"),
        })

    def test_carries_manager_and_values(self):
        detail = self._detail([
            {"field": "current_residence", "primary_value": "",
             "other_values": ["Неелово"]},
        ])
        [c] = build_captures(detail, canonical="x", guid="g", manager="Ext User")
        self.assertEqual(c.external, "Неелово")
        self.assertEqual(c.manager, "Ext User")
        self.assertEqual(c.attr, "current_residence")


class TestAdditionalInfoNote(unittest.TestCase):
    def test_note_summarises_each_external_value(self):
        caps = [
            Capture("ivan", "g", "Ext", "death_date", "death", "event",
                    "external_added", "", "1873"),
            Capture("ivan", "g", "Ext", "names/ru/last_name", "last_name",
                    "name", "disagreement", "Сидоров", "Сидорин"),
        ]
        note = additional_info_note(caps)
        self.assertTrue(note.startswith("GeniProfile(about="))
        self.assertIn("death: 1873", note)
        self.assertIn("last_name: Сидорин (выживший: Сидоров)", note)
        self.assertIn("Ext", note)

    def test_quotes_are_escaped(self):
        caps = [Capture("x", "g", "M", "about_me", "about", "about",
                        "external_added", "", 'a "quoted" note')]
        note = additional_info_note(caps)
        self.assertNotIn('""', note)
        self.assertIn('\\"quoted\\"', note)


class TestStructuredSuggestion(unittest.TestCase):
    def test_name_variant_becomes_nickname_pin(self):
        caps = [Capture("ivan", "g", "M", "names/ru/last_name", "last_name",
                        "name", "disagreement", "Сидоров", "Сидорин")]
        out = structured_suggestion("ivan", caps)
        self.assertIn('"preference": GeniProfile(last_name="Сидоров", nicknames=["Сидорин"])', out)

    def test_event_is_a_commented_override_hint(self):
        caps = [Capture("ivan", "g", "M", "death_date", "death", "event",
                        "external_added", "", "1873")]
        out = structured_suggestion("ivan", caps)
        self.assertIn("# \"override\": GeniProfile(death=GeniEvent(...))", out)


class StructuredSuggestionPastedVerbatim(unittest.TestCase):
    """The «optional structured upgrade» is printed to be pasted, so pasting it
    must leave nothing for RPF001 to reject. Geni's surviving value is, for a
    canonical we manage, what our seeding record already says — a pin of it
    writes nothing; only the external spelling, as a nickname, does work.
    """

    SEED = GeniProfile(res_name="rec_a", first_name="Иван", last_name="Сидоров")

    def _generate(self, preference=None):
        cluster: dict[str, object] = {"profile_names": [self.SEED.res_name]}
        if preference is not None:
            cluster["preference"] = preference
        gcn = SimpleNamespace(profiles_to_consolidate={"ivan": cluster},
                              profile_move_list={})
        gen = TerraformGenerator(consolidation=make_consolidation(gcn))
        gen._emit_profile("out.tf", copy.deepcopy(self.SEED))
        gen.finalize()
        return gen

    @staticmethod
    def _pasted(suggestion):
        [line] = [ln for ln in suggestion.splitlines() if '"preference":' in ln]
        source = line.split('"preference":', 1)[1].strip().rstrip(",")
        call = ast.parse(source, mode="eval").body
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name) and call.func.id == "GeniProfile"
        return GeniProfile(**{kw.arg: ast.literal_eval(kw.value)
                              for kw in call.keywords if kw.arg})

    def _round_trip(self, primary, external):
        first = self._generate()
        caps = [Capture("ivan", "g", "M", "names/ru/last_name", "last_name",
                        "name", "disagreement", primary, external)]
        pasted = self._pasted(structured_suggestion(
            "ivan", caps, pin_is_dead=first.preference_pin_is_dead))
        return pasted, self._generate(preference=pasted)

    def test_survivor_value_the_seed_already_carries_is_not_pinned(self):
        pasted, second = self._round_trip("Сидоров", "Сидорин")

        self.assertFalse(pasted.last_name)
        self.assertEqual(pasted.nicknames, ["Сидорин"])
        self.assertEqual(second.redundant_preferences, [])

    def test_survivor_value_the_seed_lacks_is_still_pinned(self):
        # Geni's survivor reads otherwise than our seed (an external edit):
        # the pin writes it onto the seed, so it is live.
        pasted, second = self._round_trip("Сидореев", "Сидорин")

        self.assertEqual(pasted.last_name, "Сидореев")
        self.assertEqual(pasted.nicknames, ["Сидорин"])
        self.assertEqual(second.redundant_preferences, [])


class TestEnsureAdditionalInfoNote(unittest.TestCase):
    BASE = (
        "profiles_to_consolidate = {\n"
        '    "ivan": {\n'
        '        "profile_names": [\n'
        '            "rec_a",\n'
        "        ],\n"
        "    },\n"
        '    "petr": {\n'
        '        "additional_info": [\n'
        "            GeniProfile(projects=[\"data.geni_project.x.id\"]),\n"
        "        ],\n"
        '        "profile_names": [\n'
        '            "rec_b",\n'
        "        ],\n"
        "    },\n"
        "}\n"
    )

    def test_creates_key_when_absent(self):
        new, status = ensure_additional_info_note(self.BASE, "ivan", "GeniProfile(about=\"note\")")
        self.assertEqual(status, "created")
        self.assertIn('"additional_info"', new)
        self.assertIn('GeniProfile(about="note")', new)
        # The new key lands inside the ivan entry, before petr.
        self.assertLess(new.index('GeniProfile(about="note")'), new.index('"petr"'))

    def test_appends_to_existing_list(self):
        new, status = ensure_additional_info_note(self.BASE, "petr", "GeniProfile(about=\"extra\")")
        self.assertEqual(status, "appended")
        self.assertIn("data.geni_project.x.id", new)   # original element kept
        self.assertIn('GeniProfile(about="extra")', new)

    def test_no_entry_for_unknown_canonical(self):
        new, status = ensure_additional_info_note(self.BASE, "missing", "GeniProfile(about=\"n\")")
        self.assertEqual(status, "no-entry")
        self.assertEqual(new, self.BASE)

    def test_duplicate_note_is_skipped(self):
        note = "GeniProfile(about=\"note\")"
        once, _ = ensure_additional_info_note(self.BASE, "ivan", note)
        twice, status = ensure_additional_info_note(once, "ivan", note)
        self.assertEqual(status, "duplicate")
        self.assertEqual(twice, once)

    def test_result_stays_loadable_python(self):
        new, _ = ensure_additional_info_note(self.BASE, "ivan", "GeniProfile(about=\"note\")")

        def _geni_profile(**kw: object) -> dict[str, object]:
            return dict(kw)

        ns: dict[str, object] = {"GeniProfile": _geni_profile}
        exec(new, ns)  # verifying the edit is valid Python
        ptc = ns["profiles_to_consolidate"]
        assert isinstance(ptc, dict)
        self.assertIn("additional_info", ptc["ivan"])


class TestResolveCommand(unittest.TestCase):
    def test_prefer_nonempty_only_when_external_added(self):
        self.assertIn("-prefer-nonempty", resolve_command("600", True, run=False))
        self.assertNotIn("-prefer-nonempty", resolve_command("600", False, run=False))
        self.assertIn("-yes", resolve_command("600", True, run=True))


class TestResourceToCanonical(unittest.TestCase):
    def test_inverts_profile_names(self):
        ptc = {"ivan": {"profile_names": ["rec_a", "rec_b"]}}
        self.assertEqual(resource_to_canonical(ptc),
                         {"rec_a": "ivan", "rec_b": "ivan"})


class TestFormatReport(unittest.TestCase):
    def test_groups_and_flags_unmapped(self):
        caps = [Capture("ivan", "600", "Ext", "death_date", "death", "event",
                        "external_added", "", "1873")]
        unmapped = [{"profile_guid": "999", "name": "X", "manager_name": "Y"}]
        out = format_report(caps, unmapped)
        self.assertIn("ivan", out)
        self.assertIn("keep on Geni: geni conflicts resolve -prefer-nonempty 600", out)
        self.assertIn("Unmapped conflicts", out)
        self.assertIn("999", out)

    def test_empty_when_nothing_found(self):
        self.assertIn("No Geni data-conflicts", format_report([], []))


if __name__ == "__main__":
    unittest.main()
