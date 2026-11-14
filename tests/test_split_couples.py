from __future__ import annotations

import json as _json
import unittest

from verso.ru.consolidation import split_couples as sc
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion


def _person(res_name, given, patronymic, gender, born=None, circa=False):
    birth = GeniEvent(date=GeniDate(year=born, circa=circa)) if born is not None else None
    return GeniProfile(res_name=res_name, first_name=given, middle_name=patronymic,
                       gender=gender, birth=birth)


def _man(res_name, given, patronymic, born=None):
    return _person(res_name, given, patronymic, "male", born)


def _woman(res_name, given, patronymic, born=None):
    return _person(res_name, given, patronymic, "female", born)


def _child(res_name, given, born, circa=False):
    return _person(res_name, given, "", "male", born, circa)


def _union(res_name, husband, wife, children=(), married=None):
    marriage = GeniEvent(date=GeniDate(year=married)) if married else None
    return GeniUnion(res_name=res_name, partner_1=husband, partner_2=wife,
                     children=set(children), marriage=marriage)


def _find(profiles, unions, resolve=None, **kw):
    return sc.find_split_couples(profiles, unions, resolve or (lambda r: r), **kw)


def _dvor3():
    """A census household beside the same couple's metric records — the shape
    that hid a couple from every other channel."""
    profiles = {
        "aleksej_fokich": _man("aleksej_fokich", "Алексей", "Фокич"),
        "ksenija_emeljanovna": _woman("ksenija_emeljanovna", "Ксения", "Емельяновна"),
        "rs_3_1": _man("rs_3_1", "Алексей", "Фокич"),
        "rs_3_2": _woman("rs_3_2", "Ксения", "Емельяновна"),
        "sergej_1878": _child("sergej_1878", "Сергей", 1878),
        "petr_rs_3_5": _child("petr_rs_3_5", "Петр", 1886, circa=True),
    }
    unions = {
        "mk_1878": _union("mk_1878", "aleksej_fokich", "ksenija_emeljanovna",
                          {"sergej_1878"}),
        "rs_3": _union("rs_3", "rs_3_1", "rs_3_2", {"petr_rs_3_5"}),
    }
    return profiles, unions


class Detection(unittest.TestCase):
    def test_couple_split_across_census_and_metric_unions_is_reported(self):
        profiles, unions = _dvor3()
        found = _find(profiles, unions)
        self.assertEqual(len(found), 1)
        couple = found[0]
        self.assertTrue(couple.is_candidate)
        self.assertEqual(couple.shared, ())
        self.assertEqual(
            sorted(h.partners for h in couple.halves),
            [("aleksej_fokich", "ksenija_emeljanovna"), ("rs_3_1", "rs_3_2")])
        self.assertIn("нет общего профиля", couple.reason)

    def test_fully_folded_couple_is_not_reported(self):
        """Once both census stubs resolve to the canonicals, the two unions
        name ONE pair of profiles — one couple, nothing split."""
        profiles, unions = _dvor3()
        folded = {"rs_3_1": "aleksej_fokich", "rs_3_2": "ksenija_emeljanovna"}

        def resolve(ref: str) -> str:
            return folded.get(ref, ref)

        self.assertEqual(_find(profiles, unions, resolve), [])

    def test_different_patronymics_are_two_couples(self):
        profiles = {
            "ivan_p": _man("ivan_p", "Иван", "Петрович"),
            "ivan_pav": _man("ivan_pav", "Иван", "Павлович"),
            "marija_1": _woman("marija_1", "Мария", "Ивановна"),
            "marija_2": _woman("marija_2", "Мария", "Ивановна"),
        }
        unions = {"u1": _union("u1", "ivan_p", "marija_1"),
                  "u2": _union("u2", "ivan_pav", "marija_2")}
        self.assertEqual(_find(profiles, unions), [])

    def test_different_wives_are_two_couples(self):
        profiles = {
            "stepan_a": _man("stepan_a", "Степан", "Иванович"),
            "stepan_b": _man("stepan_b", "Степан", "Иванович"),
            "efimija": _woman("efimija", "Ефимия", "Игнатьевна"),
            "evdokija": _woman("evdokija", "Евдокия", "Игнатьевна"),
        }
        unions = {"u1": _union("u1", "stepan_a", "efimija"),
                  "u2": _union("u2", "stepan_b", "evdokija")}
        self.assertEqual(_find(profiles, unions), [])

    def test_half_fold_names_the_folded_side(self):
        """The wife folded on the strength of the husband, the husband left as
        per-record stubs."""
        profiles = {
            "anna": _woman("anna", "Анна", "Демьяновна"),
            "grigorij_1909": _man("grigorij_1909", "Григорий", "Алексеевич"),
            "grigorij_1913": _man("grigorij_1913", "Григорий", "Алексеевич"),
        }
        unions = {"u1909": _union("u1909", "grigorij_1909", "anna"),
                  "u1913": _union("u1913", "grigorij_1913", "anna")}
        found = _find(profiles, unions)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].is_candidate)
        self.assertEqual(found[0].shared, ("anna",))
        self.assertIn("полусвод", found[0].reason)

    def test_given_name_base_joins_egor_and_georgij(self):
        """Егоръ and Георгій are one name (names.csv «Имя-основа»)."""
        profiles = {
            "egor": _man("egor", "Егор", "Максимович"),
            "georgij": _man("georgij", "Георгий", "Максимович"),
            "nadezhda": _woman("nadezhda", "Надежда", "Дмитриевна"),
        }
        unions = {"u1": _union("u1", "egor", "nadezhda"),
                  "u2": _union("u2", "georgij", "nadezhda")}
        self.assertEqual(len(_find(profiles, unions)), 1)

    def test_partner_without_patronymic_is_not_keyed(self):
        profiles = {
            "a": _man("a", "Семен", ""),
            "b": _man("b", "Семен", ""),
            "w": _woman("w", "Степанида", "Степановна"),
        }
        unions = {"u1": _union("u1", "a", "w"), "u2": _union("u2", "b", "w")}
        self.assertEqual(_find(profiles, unions), [])

    def test_one_parent_union_names_no_couple(self):
        profiles = {"dad": _man("dad", "Алексей", "Фокич"),
                    "dad2": _man("dad2", "Алексей", "Фокич")}
        unions = {"u1": GeniUnion(res_name="u1", partner_1="dad", children=set()),
                  "u2": GeniUnion(res_name="u2", partner_1="dad2", children=set())}
        self.assertEqual(_find(profiles, unions), [])

    def test_external_partner_skips_the_union(self):
        profiles, unions = _dvor3()
        del profiles["rs_3_2"]
        self.assertEqual(_find(profiles, unions), [])


class Guards(unittest.TestCase):
    def _namesakes(self, second_married):
        profiles = {
            "father": _man("father", "Иван", "Петрович"),
            "son": _man("son", "Иван", "Петрович"),
            "w1": _woman("w1", "Мария", "Ивановна"),
            "w2": _woman("w2", "Мария", "Ивановна"),
            "k1": _child("k1", "Петр", 1822),
            "k2": _child("k2", "Петр", second_married + 1),
        }
        unions = {"u1": _union("u1", "father", "w1", {"k1"}, married=1820),
                  "u2": _union("u2", "son", "w2", {"k2"}, married=second_married)}
        return profiles, unions

    def test_halves_a_generation_apart_are_retired(self):
        found = _find(*self._namesakes(1860))
        self.assertEqual(found[0].verdict, sc.VERDICT_GENERATIONS)
        self.assertFalse(found[0].is_candidate)

    def test_halves_within_one_lifetime_stay_candidates(self):
        found = _find(*self._namesakes(1830))
        self.assertTrue(found[0].is_candidate)

    def test_generation_gap_is_configurable(self):
        found = _find(*self._namesakes(1860), generation_gap=60)
        self.assertTrue(found[0].is_candidate)

    def test_undated_half_cannot_be_retired(self):
        profiles, unions = self._namesakes(1860)
        unions["u2"] = _union("u2", "son", "w2")
        self.assertTrue(_find(profiles, unions)[0].is_candidate)


class PatronymicKey(unittest.TestCase):
    """The father a patronymic names, read off the lexicon."""

    def test_son_and_daughter_forms_agree(self):
        self.assertEqual(sc.patronymic_key("Иванович"), sc.patronymic_key("Ивановна"))
        self.assertEqual(sc.patronymic_key("Фокич"), sc.patronymic_key("Фокина"))

    def test_one_father_spelled_two_ways_agrees(self):
        self.assertEqual(sc.patronymic_key("Алексеевна"), sc.patronymic_key("Алексиевна"))
        self.assertEqual(sc.patronymic_key("Матвеевич"), sc.patronymic_key("Матфеевич"))
        self.assertEqual(sc.patronymic_key("Семенович"), sc.patronymic_key("Семёнович"))

    def test_variant_father_names_fold_to_their_base(self):
        """Егоръ and Георгій are one name, so their daughters' forms agree."""
        self.assertEqual(sc.patronymic_key("Егоровна"), sc.patronymic_key("Георгиевна"))

    def test_different_fathers_stay_apart(self):
        self.assertNotEqual(sc.patronymic_key("Алексеевна"),
                            sc.patronymic_key("Александровна"))
        self.assertNotEqual(sc.patronymic_key("Петрович"), sc.patronymic_key("Павлович"))
        self.assertNotEqual(sc.patronymic_key("Минична"), sc.patronymic_key("Минеевна"))

    def test_unknown_patronymic_is_compared_as_written(self):
        self.assertEqual(sc.patronymic_key("Нерапиевна"), "нерапиевна")

    def test_empty_patronymic_has_no_key(self):
        self.assertEqual(sc.patronymic_key(""), "")


class Output(unittest.TestCase):
    def test_report_names_both_halves(self):
        text, _ = sc.run(*_dvor3(), lambda r: r)
        self.assertIn("Алексей Фокич × Ксения Емельяновна", text)
        self.assertIn("rs_3_1", text)
        self.assertIn("aleksej_fokich", text)

    def test_report_says_signal_not_verdict(self):
        text, _ = sc.run(*_dvor3(), lambda r: r)
        self.assertIn("СИГНАЛ, не вердикт", text)

    def test_report_without_candidates(self):
        text, code = sc.run({}, {}, lambda r: r)
        self.assertIn("Кандидатов нет", text)
        self.assertEqual(code, 0)

    def test_all_shows_the_retired_groups(self):
        profiles, unions = Guards()._namesakes(1860)
        plain, code = sc.run(profiles, unions, lambda r: r)
        full, _ = sc.run(profiles, unions, lambda r: r, all_groups=True)
        self.assertEqual(code, 0)
        self.assertNotIn(sc.VERDICT_GENERATIONS, plain)
        self.assertIn(sc.VERDICT_GENERATIONS, full)

    def test_json_round_trips(self):
        text, code = sc.run(*_dvor3(), lambda r: r, as_json=True)
        payload = _json.loads(text)
        self.assertEqual(code, 1)
        self.assertEqual(payload[0]["verdict"], sc.VERDICT_CANDIDATE)
        self.assertEqual(len(payload[0]["halves"]), 2)
        kids = [c["res_name"] for h in payload[0]["halves"] for c in h["children"]]
        self.assertEqual(sorted(kids), ["petr_rs_3_5", "sergej_1878"])


if __name__ == "__main__":
    unittest.main()
