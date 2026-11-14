"""Tests for consolidation-conflict detection.

When two source records are folded into one canonical profile, a differing
field value can be silently discarded (e.g. a second `last_name` that isn't
pinned via `preference`/`override`/`ignore`). `detect_consolidation_conflicts`
is a pure query that returns exactly those silent losses so the generator can
report them.
"""
import ast
import copy
import unittest
from types import SimpleNamespace

from verso.ru.pipeline.translate import make_consolidation
from verso.core.targets.geni.consolidation_conflicts import (
    ConsolidationConflict, detect_consolidation_conflicts, exit_code_for_conflicts, format_conflict_report)
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.ru.targets.geni.translator import Consolidation, TerraformGenerator


def _ev(day=None, month=None, year=None, circa=False, date_range=None):
    return GeniEvent(date=GeniDate(day=day, month=month, year=year,
                                   circa=circa, date_range=date_range))


def _detect(existing, incoming, *, preference=None, ignore=None, override=None):
    return detect_consolidation_conflicts(
        existing, incoming,
        canonical="canon", source="src_record",
        preference=preference, ignore=ignore, override=override,
    )


class LastNameConflict(unittest.TestCase):
    def test_differing_last_name_with_no_preference_is_a_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")

        conflicts = _detect(existing, incoming)

        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c.field, "last_name")
        self.assertEqual(c.kept, "Сидоров")
        self.assertEqual(c.discarded, "Видоплясов")
        self.assertEqual(c.canonical, "canon")
        self.assertEqual(c.source, "src_record")


class LastNameResolvedIsNotConflict(unittest.TestCase):
    def test_maiden_to_married_promotion_is_not_a_conflict(self):
        # existing holds the maiden form; incoming carries the married
        # last_name with birth_last_name == the maiden form. The merge
        # legitimately adopts the married name — no loss.
        existing = GeniProfile(first_name="Анна", last_name="Иванова")
        incoming = GeniProfile(first_name="Анна", last_name="Петрова",
                               birth_last_name="Иванова")

        self.assertEqual(_detect(existing, incoming), [])

    def test_variant_declared_as_preference_alias_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")

        conflicts = _detect(existing, incoming,
                            preference={"nicknames": ["Видоплясов"]})

        self.assertEqual(conflicts, [])

    def test_ignored_variant_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")

        conflicts = _detect(existing, incoming,
                            ignore=[{"last_name": "Видоплясов"}])

        self.assertEqual(conflicts, [])

    def test_birth_last_name_preference_clears_maiden_last_name_drop(self):
        # A married-out woman pinned to her married last_name + birth_last_name
        # = maiden surname: an incoming record carrying the MAIDEN last_name is
        # not a conflict — it's preserved in the dedicated field (no redundant
        # `ignore`/`nicknames` needed). P4.
        existing = GeniProfile(first_name="Мария", last_name="Семенова",
                               birth_last_name="Ляпкина")
        incoming = GeniProfile(first_name="Мария", last_name="Ляпкина")

        conflicts = _detect(existing, incoming,
                            preference={"birth_last_name": "Ляпкина"})

        self.assertEqual(conflicts, [])


class UnknownPlaceholderName(unittest.TestCase):
    """`?` is the DSL placeholder for an unknown/unreadable name — never a real
    alternative, so it must not be reported as a conflict (either side)."""

    def test_dropped_unknown_middle_name_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Епифан", middle_name="Антонович")
        incoming = GeniProfile(first_name="Епифан", middle_name="?")

        self.assertEqual(_detect(existing, incoming), [])

    def test_kept_unknown_last_name_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="?")
        incoming = GeniProfile(first_name="Иван", last_name="Петров")

        self.assertEqual(_detect(existing, incoming), [])


class MiddleNameConflict(unittest.TestCase):
    def test_differing_middle_name_with_no_preference_is_a_conflict(self):
        existing = GeniProfile(first_name="Иван", middle_name="Петрович")
        incoming = GeniProfile(first_name="Иван", middle_name="Павлович")

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["middle_name"])
        self.assertEqual(conflicts[0].kept, "Петрович")
        self.assertEqual(conflicts[0].discarded, "Павлович")

    def test_middle_name_preference_alias_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", middle_name="Петрович")
        incoming = GeniProfile(first_name="Иван", middle_name="Павлович")

        conflicts = _detect(existing, incoming,
                            preference={"nicknames": ["Павлович"]})

        self.assertEqual(conflicts, [])


class BirthLastNameConflict(unittest.TestCase):
    def test_differing_birth_last_name_with_no_preference_is_a_conflict(self):
        existing = GeniProfile(first_name="Анна", birth_last_name="Иванова")
        incoming = GeniProfile(first_name="Анна", birth_last_name="Сидорова")

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["birth_last_name"])
        self.assertEqual(conflicts[0].kept, "Иванова")
        self.assertEqual(conflicts[0].discarded, "Сидорова")

    def test_ignored_birth_last_name_variant_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Анна", birth_last_name="Иванова")
        incoming = GeniProfile(first_name="Анна", birth_last_name="Сидорова")

        conflicts = _detect(existing, incoming,
                            ignore=[{"birth_last_name": "Сидорова"}])

        self.assertEqual(conflicts, [])


class FirstNameNeverConflicts(unittest.TestCase):
    """The merge always keeps a differing first_name as a nickname (never
    dropped), so it must never be reported — even alongside a real conflict."""

    def test_differing_first_name_alone_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иоанн", last_name="Сидоров")

        self.assertEqual(_detect(existing, incoming), [])

    def test_first_name_is_excluded_even_when_last_name_conflicts(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иоанн", last_name="Видоплясов")

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["last_name"])


class EventDateConflict(unittest.TestCase):
    def test_two_specific_differing_birth_dates_conflict(self):
        existing = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1817))
        incoming = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1819))

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["birth.date"])
        self.assertIn("1817", conflicts[0].kept)
        self.assertIn("1819", conflicts[0].discarded)

    def test_equal_dates_do_not_conflict(self):
        existing = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1817))
        incoming = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1817))

        self.assertEqual(_detect(existing, incoming), [])

    def test_specific_versus_circa_does_not_conflict(self):
        # circa is an estimate; the merge legitimately prefers the specific
        # date — no contradiction to surface.
        existing = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1817))
        incoming = GeniProfile(first_name="Иван", birth=_ev(year=1819, circa=True))

        self.assertEqual(_detect(existing, incoming), [])

    def test_year_only_refinement_of_same_year_does_not_conflict(self):
        # Same year, one carries month/day — enrichment, not contradiction.
        existing = GeniProfile(first_name="Иван", birth=_ev(year=1817))
        incoming = GeniProfile(first_name="Иван", birth=_ev(5, 3, 1817))

        self.assertEqual(_detect(existing, incoming), [])

    def test_differing_specific_death_dates_conflict(self):
        existing = GeniProfile(first_name="Иван", death=_ev(1, 10, 1850))
        incoming = GeniProfile(first_name="Иван", death=_ev(18, 1, 1853))

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["death.date"])

    def test_override_pinning_the_event_date_suppresses_conflict(self):
        existing = GeniProfile(first_name="Иван", birth=_ev(9, 8, 1801))
        incoming = GeniProfile(first_name="Иван", birth=_ev(2, 6, 1802))
        self.assertEqual(len(_detect(existing, incoming)), 1)

        # An override that pins the birth event is an explicit resolution.
        override = GeniProfile(birth=_ev(9, 8, 1801))
        conflicts = _detect(existing, incoming, override=override)

        self.assertEqual(conflicts, [])

    def test_override_pinning_a_name_field_suppresses_conflict(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")
        self.assertEqual(len(_detect(existing, incoming)), 1)

        override = GeniProfile(last_name="Сидоров")
        conflicts = _detect(existing, incoming, override=override)

        self.assertEqual(conflicts, [])

    def test_override_without_that_event_does_not_suppress(self):
        existing = GeniProfile(first_name="Иван", birth=_ev(9, 8, 1801))
        incoming = GeniProfile(first_name="Иван", birth=_ev(2, 6, 1802))

        # Override pins death, not birth — birth conflict still surfaces.
        override = GeniProfile(death=_ev(1, 1, 1860))
        conflicts = _detect(existing, incoming, override=override)

        self.assertEqual([c.field for c in conflicts], ["birth.date"])

    def test_ignored_birth_date_value_is_not_a_conflict(self):
        existing = GeniProfile(first_name="Иван", birth=_ev(9, 8, 1801))
        incoming = GeniProfile(first_name="Иван", birth=_ev(2, 6, 1802))
        # Sanity: without ignore it IS a conflict.
        self.assertEqual(len(_detect(existing, incoming)), 1)

        # Ignoring the incoming (census) date value suppresses it.
        conflicts = _detect(existing, incoming, ignore=[
            {"birth.date": GeniDate(day=2, month=6, year=1802)}])

        self.assertEqual(conflicts, [])


class CauseOfDeathConflict(unittest.TestCase):
    def test_two_differing_causes_conflict(self):
        existing = GeniProfile(first_name="Иван", cause_of_death="натуральная")
        incoming = GeniProfile(first_name="Иван", cause_of_death="холера")

        conflicts = _detect(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["cause_of_death"])
        self.assertEqual(conflicts[0].kept, "натуральная")
        self.assertEqual(conflicts[0].discarded, "холера")

    def test_one_empty_cause_does_not_conflict(self):
        existing = GeniProfile(first_name="Иван", cause_of_death="натуральная")
        incoming = GeniProfile(first_name="Иван")

        self.assertEqual(_detect(existing, incoming), [])


class GeneratorRecordsConflicts(unittest.TestCase):
    """The generator collects conflicts (with canonical + source) as it folds
    per-record profiles into a consolidated target."""

    def test_records_last_name_conflict_with_canonical_and_source(self):
        consolidation = Consolidation(
            profile_move_list={"rec_a": "canon", "rec_b": "canon"})
        gen = TerraformGenerator(consolidation=consolidation)

        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_a", first_name="Иван", last_name="Сидоров"))
        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_b", first_name="Иван", last_name="Видоплясов"))

        conflicts = gen.consolidation_conflicts
        self.assertEqual([c.field for c in conflicts], ["last_name"])
        self.assertEqual(conflicts[0].canonical, "canon")
        self.assertEqual(conflicts[0].source, "rec_b")
        self.assertEqual(conflicts[0].kept, "Сидоров")
        self.assertEqual(conflicts[0].discarded, "Видоплясов")

    def test_no_conflict_when_records_agree(self):
        consolidation = Consolidation(
            profile_move_list={"rec_a": "canon", "rec_b": "canon"})
        gen = TerraformGenerator(consolidation=consolidation)

        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_a", first_name="Иван", last_name="Сидоров"))
        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_b", first_name="Иван", last_name="Сидоров"))

        self.assertEqual(gen.consolidation_conflicts, [])


class DetectionAgreesWithMerge(unittest.TestCase):
    """Drift guard: detection is derived from the real merge's drop behavior.
    Run the actual `_merge_consolidated` and assert that a reported conflict
    means the merge truly dropped the value, and a clean result means it kept
    it. If the merge changes without updating detection, this fails."""

    def _merge(self, existing, incoming, *, preference=None, ignore=None):
        import copy
        merged = copy.copy(existing)
        merged.nicknames = list(existing.nicknames or [])
        TerraformGenerator._merge_consolidated(
            merged, incoming, preference=preference, ignore=ignore)
        return merged

    def test_conflict_means_merge_dropped_the_value(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")

        conflicts = _detect(existing, incoming)
        merged = self._merge(existing, incoming)

        self.assertEqual([c.field for c in conflicts], ["last_name"])
        self.assertEqual(merged.last_name, "Сидоров")          # kept
        self.assertNotIn("Видоплясов", merged.nicknames)          # truly dropped

    def test_preference_alias_is_conflict_free_and_kept_as_nickname(self):
        existing = GeniProfile(first_name="Иван", last_name="Сидоров")
        incoming = GeniProfile(first_name="Иван", last_name="Видоплясов")
        pref = {"nicknames": ["Видоплясов"]}

        conflicts = _detect(existing, incoming, preference=pref)
        merged = self._merge(existing, incoming, preference=pref)

        self.assertEqual(conflicts, [])
        self.assertIn("Видоплясов", merged.nicknames)             # kept, not lost

    def test_maiden_to_married_is_conflict_free_and_adopted(self):
        existing = GeniProfile(first_name="Анна", last_name="Иванова")
        incoming = GeniProfile(first_name="Анна", last_name="Петрова",
                               birth_last_name="Иванова")

        conflicts = _detect(existing, incoming)
        merged = self._merge(existing, incoming)

        self.assertEqual(conflicts, [])
        self.assertEqual(merged.last_name, "Петрова")         # adopted, not lost


class ReportFormatting(unittest.TestCase):
    def test_no_conflicts_renders_empty_report(self):
        self.assertEqual(format_conflict_report([]), "")

    def test_report_names_target_field_values_source_and_resolution(self):
        conflict = ConsolidationConflict(
            canonical="ivan_gavriilovich_lodaev", field="last_name",
            kept="Сидоров", discarded="Видоплясов", source="rec_b")

        report = format_conflict_report([conflict])

        for token in ("ivan_gavriilovich_lodaev", "last_name",
                      "Сидоров", "Видоплясов", "rec_b"):
            self.assertIn(token, report)
        # Points the reader at how to resolve it.
        self.assertIn("preference", report)

    def test_report_emits_paste_ready_preference_pin(self):
        conflicts = [
            ConsolidationConflict("mihail_egorovich", "last_name", "Мижуев", "Анучкин", "rec_a"),
            ConsolidationConflict("vasilisa_ivanovna", "last_name", "Мижуева", "Анучкина", "rec_b"),
        ]
        report = format_conflict_report(conflicts)
        # Paste-ready GeniProfile pin, kept value pinned + dropped kept as alias.
        self.assertIn(
            '"preference": GeniProfile(last_name="Мижуев", nicknames=["Анучкин"]),', report
        )
        self.assertIn(
            '"preference": GeniProfile(last_name="Мижуева", nicknames=["Анучкина"]),', report
        )

    def test_pin_groups_fields_and_aliases_per_canonical(self):
        from verso.core.targets.geni.consolidation_conflicts import suggest_preference_pins

        conflicts = [
            ConsolidationConflict("c", "last_name", "Петров", "Петровский", "a"),
            ConsolidationConflict("c", "middle_name", "Иванович", "Ивановъ", "b"),
        ]
        pin = suggest_preference_pins(conflicts)
        self.assertIn('last_name="Петров"', pin)
        self.assertIn('middle_name="Иванович"', pin)
        self.assertIn('nicknames=["Петровский", "Ивановъ"]', pin)

    def test_date_conflict_yields_no_pin(self):
        from verso.core.targets.geni.consolidation_conflicts import suggest_preference_pins

        conflicts = [ConsolidationConflict("c", "birth.date", "1840", "1841", "a")]
        self.assertEqual(suggest_preference_pins(conflicts), "")

    def test_pin_suggests_birth_last_name_for_key_surname_drop(self):
        # Canonical keyed on the maiden surname (…_ljapkina); the kept value is
        # the married name, so the dropped maiden surname (== the key's surname)
        # is suggested as birth_last_name, NOT a nicknames alias. P4.
        from verso.core.targets.geni.consolidation_conflicts import suggest_preference_pins

        conflicts = [
            ConsolidationConflict("marija_vladimirovna_ljapkina", "last_name",
                                  "Семенова", "Ляпкина", "rec_census"),
        ]
        pin = suggest_preference_pins(conflicts)
        self.assertIn('last_name="Семенова"', pin)
        self.assertIn('birth_last_name="Ляпкина"', pin)
        self.assertNotIn("nicknames", pin)

    def test_pin_emits_birth_last_name_and_nicknames_together(self):
        # A key-surname maiden drop (-> birth_last_name) and an unrelated scribal
        # variant (-> nicknames) on the same canonical coexist in one pin.
        from verso.core.targets.geni.consolidation_conflicts import suggest_preference_pins

        conflicts = [
            ConsolidationConflict("anna_petrovna_smirennikova", "last_name",
                                  "Иванова", "Смиренникова", "rec1"),
            ConsolidationConflict("anna_petrovna_smirennikova", "middle_name",
                                  "Петровна", "Петрова", "rec2"),
        ]
        pin = suggest_preference_pins(conflicts)
        self.assertIn('birth_last_name="Смиренникова"', pin)
        self.assertIn('nicknames=["Петрова"]', pin)


class ExitCodePolicy(unittest.TestCase):
    def _one(self):
        return [ConsolidationConflict("i", "last_name", "a", "b", "s")]

    def test_conflicts_without_flag_exit_zero(self):
        self.assertEqual(
            exit_code_for_conflicts(self._one(), fail_on_conflicts=False), 0)

    def test_conflicts_with_flag_exit_nonzero(self):
        self.assertNotEqual(
            exit_code_for_conflicts(self._one(), fail_on_conflicts=True), 0)

    def test_no_conflicts_with_flag_exit_zero(self):
        self.assertEqual(
            exit_code_for_conflicts([], fail_on_conflicts=True), 0)


class OverrideNicknamesDecideWhatSurvives(unittest.TestCase):
    """`override.nicknames` REPLACES the merged nicknames wholesale (see
    `_apply_profile_overrides`), so when an override carries nicknames it —
    not `preference.nicknames` — decides whether a dropped name survives as
    an alias. Detection must model that precedence, or it vouches for a value
    the renderer then throws away.
    """

    def _run(self, *, preference=None, override=None):
        consolidation = Consolidation(
            profile_move_list={"rec_a": "canon", "rec_b": "canon"},
            profile_preferences={"canon": preference} if preference else {},
            profile_overrides={"canon": override} if override else {},
        )
        gen = TerraformGenerator(consolidation=consolidation)
        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_a", first_name="Иван", last_name="Сидоров"))
        gen._emit_profile("out.tf", GeniProfile(
            res_name="rec_b", first_name="Иван", last_name="Видоплясов"))
        gen.finalize()
        canonical = gen._consolidated_profiles["canon"]
        return gen.consolidation_conflicts, list(canonical.nicknames or [])

    def test_override_discarding_the_preference_alias_is_reported(self):
        # `preference` vouches for "Видоплясов", but the override replaces
        # nicknames with ["Савва"] — the alias really is lost, so staying
        # silent here is the data-losing false negative.
        conflicts, nicknames = self._run(
            preference={"nicknames": ["Видоплясов"]},
            override=GeniProfile(nicknames=["Савва"]))

        self.assertNotIn("Видоплясов", nicknames)
        self.assertEqual([c.field for c in conflicts], ["last_name"])

    def test_override_keeping_the_alias_is_conflict_free(self):
        # The override itself keeps "Видоплясов", so nothing is lost — reporting
        # a conflict here is a false positive.
        conflicts, nicknames = self._run(
            override=GeniProfile(nicknames=["Савва", "Видоплясов"]))

        self.assertIn("Видоплясов", nicknames)
        self.assertEqual(conflicts, [])

    def test_preference_alias_still_honoured_without_an_override(self):
        # Regression guard: the existing preference path is unchanged when no
        # override carries nicknames.
        conflicts, nicknames = self._run(preference={"nicknames": ["Видоплясов"]})

        self.assertIn("Видоплясов", nicknames)
        self.assertEqual(conflicts, [])


class SuggestedPinPastedVerbatim(unittest.TestCase):
    """The suggestion is printed to be pasted, so what it prints must survive
    the next `make tf-generate`: no conflict left, and nothing RPF001 calls
    dead. A pin of the KEPT value is dead whenever the seeding record already
    carried it (Глуповы Горы, 2026-10-13: `ivan_porfirevich_1844` was
    suggested `middle_name="Порфирьевич"`, and RPF001 rejected it).
    """

    def _generate(self, records, preference=None, *, canonical):
        cluster: dict[str, object] = {
            "profile_names": [r.res_name for r in records]}
        if preference is not None:
            cluster["preference"] = preference
        gcn = SimpleNamespace(profiles_to_consolidate={canonical: cluster},
                              profile_move_list={})
        gen = TerraformGenerator(consolidation=make_consolidation(gcn))
        for rec in records:
            gen._emit_profile("out.tf", copy.deepcopy(rec))
        gen.finalize()
        return gen

    @staticmethod
    def _pasted(report):
        """The `GeniProfile(...)` of the one suggested pin, as the config
        file would hold it after a verbatim paste."""
        [line] = [ln for ln in report.splitlines() if '"preference":' in ln]
        source = line.split('"preference":', 1)[1].strip().rstrip(",")
        call = ast.parse(source, mode="eval").body
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name) and call.func.id == "GeniProfile"
        return GeniProfile(**{kw.arg: ast.literal_eval(kw.value)
                              for kw in call.keywords if kw.arg})

    def _round_trip(self, records, canonical="canon"):
        first = self._generate(records, canonical=canonical)
        report = format_conflict_report(
            first.consolidation_conflicts,
            pin_is_dead=first.preference_pin_is_dead)
        pasted = self._pasted(report)
        second = self._generate(records, preference=pasted,
                                canonical=canonical)
        return pasted, second

    def test_pin_the_seed_already_carries_is_not_suggested(self):
        pasted, second = self._round_trip([
            GeniProfile(res_name="rec_a", first_name="Иван",
                        middle_name="Порфирьевич"),
            GeniProfile(res_name="rec_b", first_name="Иван",
                        middle_name="Перфилович"),
        ])

        self.assertFalse(pasted.middle_name)
        self.assertEqual(pasted.nicknames, ["Перфилович"])
        self.assertEqual(second.consolidation_conflicts, [])
        self.assertEqual(second.redundant_preferences, [])

    def test_pin_the_seed_lacks_is_still_suggested(self):
        # The seed has no patronymic; the kept one arrives with rec_b. The pin
        # writes it onto the seed, so it is live and must stay in the paste.
        pasted, second = self._round_trip([
            GeniProfile(res_name="rec_a", first_name="Иван"),
            GeniProfile(res_name="rec_b", first_name="Иван",
                        middle_name="Порфирьевич"),
            GeniProfile(res_name="rec_c", first_name="Иван",
                        middle_name="Перфилович"),
        ])

        self.assertEqual(pasted.middle_name, "Порфирьевич")
        self.assertEqual(pasted.nicknames, ["Перфилович"])
        self.assertEqual(second.consolidation_conflicts, [])
        self.assertEqual(second.redundant_preferences, [])

    def test_maiden_name_part_survives_a_dead_field_pin(self):
        # Keyed on the maiden surname: the dropped «Ляпкина» goes to
        # `birth_last_name`, while the kept married name is the seed's own.
        pasted, second = self._round_trip([
            GeniProfile(res_name="rec_a", first_name="Мария",
                        last_name="Семенова"),
            GeniProfile(res_name="rec_b", first_name="Мария",
                        last_name="Ляпкина"),
        ], canonical="marija_vladimirovna_ljapkina")

        self.assertFalse(pasted.last_name)
        self.assertEqual(pasted.birth_last_name, "Ляпкина")
        self.assertEqual(second.consolidation_conflicts, [])
        self.assertEqual(second.redundant_preferences, [])


if __name__ == "__main__":
    unittest.main()
