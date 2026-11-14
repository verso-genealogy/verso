import tempfile
import unittest
from pathlib import Path
from typing import Any

import verso.ru.linters.checks.relative_attachment as check
from verso.ru.gender import Gender
from verso.ru.naming import names_registry
from verso.ru.naming.layer_files import base
from verso.ru.naming.lexicon import Layer, Lexicon, PatronymicEntry


def _birth(records: str) -> str:
    """Wrap `birth()` calls in a `birth_records(...)`. The checker only parses
    (never executes) the DSL, so constants need not be real imports."""
    return (
        "from verso.ru.dsl import birth, birth_records\n"
        "from verso.ru.dsl import Gender, person\n"
        "from verso.ru.dsl import Relationship, relative\n"
        "mk = birth_records(\n"
        '    "ЦГАРМ", "57", "6", "1", "Горюхино", "Николаевская", 1842,\n'
        f"{records}\n"
        ")\n"
    )


def _marriage(records: str) -> str:
    return (
        "from verso.ru.dsl import marriage, marriage_records\n"
        "from verso.ru.dsl import person\n"
        "from verso.ru.dsl import Relationship, relative\n"
        "mk = marriage_records(\n"
        '    "ЦГАРМ", "57", "6", "1", "Горюхино", "Николаевская", 1842,\n'
        f"{records}\n"
        ")\n"
    )


class _Harness(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _structured(self, src: str) -> list[dict[str, Any]]:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            return check.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()


class TestUnwiredRef(_Harness):
    def test_vospriemnica_is_flagged_with_the_numbered_form_to_use(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          child=person("Иванъ"),\n'
            '          god_parent1=person("Тарасъ", "Ивановъ"),\n'
            '          god_parent2=person("Матрена", "Степанова"),\n'
            '          relatives=[relative(person("Никита", "Ивановъ"),\n'
            '                              Relationship.HUSBAND, "восприемница")]),'
        ))
        self.assertTrue(
            any("[RLA001]" in e and "восприемница" in e and "восприемника №2" in e
                for e in errs), errs)

    def test_godparent_ref_without_that_slot_is_flagged_as_no_subject(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          god_parent1=person("Тарасъ", "Ивановъ"),\n'
            '          relatives=[relative(person("Никита", "Ивановъ"),\n'
            '                              Relationship.FATHER, "восприемника №3")]),'
        ))
        self.assertTrue(
            any("[RLA001]" in e and "names no subject" in e for e in errs), errs)

    def test_mat_ref_is_silent_now_that_it_is_wired(self):
        # «мать» attaches a relative to the mother — the shape a
        # незаконнорождённый birth takes when the entry names her father or
        # husband instead of a father for the child. The translator builds
        # that union, so the ref is not a finding.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          mother=person("Анна", "Ильина"),\n'
            '          relatives=[relative(person("Илья", "Абрамовъ"),\n'
            '                              Relationship.FATHER, "мать")]),'
        ))
        self.assertEqual(errs, [], errs)

    def test_mat_ref_without_a_mother_is_flagged(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          father=person("Тарасъ", "Ивановъ"),\n'
            '          relatives=[relative(person("Илья", "Абрамовъ"),\n'
            '                              Relationship.FATHER, "мать")]),'
        ))
        self.assertTrue(any("[RLA001]" in e and "names no subject" in e for e in errs), errs)

    def test_witness_ref_attaches_in_a_marriage(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             witness6=person("Дарья", "Григорьева"),\n'
            '             relatives=[relative(person("Григорій", "Ефимовъ"),\n'
            '                                 Relationship.HUSBAND, "поручитель №6")]),'
        ))
        self.assertEqual(errs, [], errs)

    def test_witness_ref_without_that_witness_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             witness1=person("Дарья", "Григорьева"),\n'
            '             relatives=[relative(person("Григорій", "Ефимовъ"),\n'
            '                                 Relationship.HUSBAND, "поручитель №6")]),'
        ))
        self.assertTrue(any("[RLA001]" in e and "names no subject" in e for e in errs), errs)

    def test_marriage_using_a_birth_style_ref_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ"),\n'
            '             witness6=person("Дарья", "Григорьева"),\n'
            '             relatives=[relative(person("Григорій", "Ефимовъ"),\n'
            '                                 Relationship.HUSBAND, "восприемника №6")]),'
        ))
        self.assertTrue(
            any("[RLA001]" in e and "names no subject" in e for e in errs), errs)

    def test_wired_refs_are_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ"),\n'
            '             bride=person("Мария", "Миронова"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ"),\n'
            '                                 Relationship.FATHER, "жених"),\n'
            '                        relative(person("Миронъ", "Лукинъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),'
        ))
        self.assertEqual(errs, [], errs)

    def test_numbered_godparent_ref_with_the_slot_present_is_silent(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          god_parent1=person("Тарасъ", "Ивановъ"),\n'
            '          god_parent2=person("Матрена", "Степанова"),\n'
            '          relatives=[relative(person("Никита", "Ивановъ"),\n'
            '                              Relationship.HUSBAND, "восприемника №2")]),'
        ))
        self.assertEqual(errs, [], errs)


class TestPatronymicAlignment(_Harness):
    def test_patronymic_contradicting_the_father_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Михаилъ", "Ивановъ", "Ушастиковъ"),\n'
            '             relatives=[relative(person("Михаилъ", "Семеновъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        ))
        self.assertTrue(
            any("[RLA002]" in e and "Ивановъ" in e and "Михаил" in e for e in errs), errs)

    def test_suffix_variant_of_the_same_stem_is_silent(self):
        # derive_patronymic("Иона", FEMALE) is "Ионична", but the source writes
        # "Іонова" — one stem, two suffix conventions, not a contradiction.
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Ксенія", "Іонова"),\n'
            '             relatives=[relative(person("Іона", "Тимофеевъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),'
        ))
        self.assertEqual([e for e in errs if "RLA002" in e], [], errs)

    def test_matfej_matfej_spelling_pair_is_silent(self):
        # The base keeps Матвеева and Матфеева apart; a layer says the books' Матвеева
        # is Матфей's, and then the pair is one patronymic, not a contradiction.
        pins = Layer("corpus", {}, {}, {
            (Gender.FEMALE, "Матвеева"): PatronymicEntry(Gender.FEMALE, "Матвеева", "Матфей", "Матфеевна"),
            (Gender.MALE, "Матвеев"): PatronymicEntry(Gender.MALE, "Матвеев", "Матфей", "Матфеевич")})
        with names_registry.answering(Lexicon.of([base().load(), pins])):
            errs = self._check(_marriage(
                "    marriage(1, 11,\n"
                '             bride=person("Анна", "Матвѣева"),\n'
                '             relatives=[relative(person("Матфей", "Ивановъ"),\n'
                '                                 Relationship.FATHER, "невеста")]),'
            ))
        self.assertEqual([e for e in errs if "RLA002" in e], [], errs)

    def test_step_father_is_never_compared(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Анна", "Иванова"),\n'
            '             relatives=[relative(person("Матфей", "Ивановъ"),\n'
            '                                 Relationship.STEP_FATHER, "невеста")]),'
        ))
        self.assertEqual([e for e in errs if "RLA002" in e], [], errs)

    def test_subject_without_a_patronymic_is_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Анна"),\n'
            '             relatives=[relative(person("Матфей", "Ивановъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),'
        ))
        self.assertEqual([e for e in errs if "RLA002" in e], [], errs)

    def test_matching_patronymic_is_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        ))
        self.assertEqual([e for e in errs if "RLA002" in e], [], errs)


class TestSurnameAlignment(_Harness):
    def test_male_subject_with_a_different_surname_is_flagged(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ", "Медведкинъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ", "Подколесинъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        ))
        self.assertTrue(
            any("[RLA003]" in e and "Медведкин" in e and "Подколесин" in e for e in errs), errs)

    def test_female_subject_is_compared_against_the_feminized_surname(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Агафья", "Егорова", "Егорова"),\n'
            '             relatives=[relative(person("Егоръ", "Никифоровъ", "Разиняевъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),'
        ))
        self.assertTrue(any("[RLA003]" in e for e in errs), errs)

    def test_matching_feminized_surname_is_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Агафья", "Егорова", "Разиняева"),\n'
            '             relatives=[relative(person("Егоръ", "Никифоровъ", "Разиняевъ"),\n'
            '                                 Relationship.FATHER, "невеста")]),'
        ))
        self.assertEqual([e for e in errs if "RLA003" in e], [], errs)

    def test_one_sided_surname_is_silent(self):
        # Derivation territory, not a contradiction.
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ", "Подколесинъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        ))
        self.assertEqual([e for e in errs if "RLA003" in e], [], errs)


class TestSpouseSurnameIsNotChecked(_Harness):
    """A married woman is routinely recorded under her MAIDEN surname in these
    books — a wedding names a widow by her maiden surname beside her late
    husband's, and a birth names two sisters by theirs, one of them married to a
    man of another surname. A husband/wife surname comparison cannot tell that
    convention apart from a real error, so it is deliberately not made."""

    def test_husband_with_a_different_surname_is_silent(self):
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          god_parent1=person("Тарасъ", "Ивановъ"),\n'
            '          god_parent2=person("Фекла", "Кириллова", "Ежевикина"),\n'
            '          relatives=[relative(person("Андрей", "Лукинъ", "Подушкинъ"),\n'
            '                              Relationship.HUSBAND, "восприемника №2")]),'
        ))
        self.assertEqual(errs, [], errs)


class TestHighlightSpan(_Harness):
    """Findings must pin the offending literal, not leave the IDE to paint the
    whole line (char columns — ast col_offset is in UTF-8 BYTES)."""

    def _span(self, src: str, issue: dict[str, Any]) -> str:
        line = src.splitlines()[issue["line"] - 1]
        return line[issue["col"]:issue["end_col"]]

    def test_surname_finding_pins_the_relatives_surname(self):
        src = _marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ", "Медведкинъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ", "Подколесинъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        )
        issue = next(i for i in self._structured(src) if "RLA003" in str(i["message"]))
        self.assertEqual(self._span(src, issue), '"Подколесинъ"')

    def test_patronymic_finding_pins_the_fathers_given_name(self):
        src = _marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Михаилъ", "Ивановъ", "Ушастиковъ"),\n'
            '             relatives=[relative(person("Михаилъ", "Семеновъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        )
        issue = next(i for i in self._structured(src) if "RLA002" in str(i["message"]))
        self.assertEqual(self._span(src, issue), '"Михаилъ"')

    def test_unattached_finding_pins_the_relationship_ref(self):
        src = _birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          god_parent1=person("Тарасъ", "Ивановъ"),\n'
            '          god_parent2=person("Матрена", "Степанова"),\n'
            '          relatives=[relative(person("Никита", "Ивановъ"),\n'
            '                              Relationship.HUSBAND, "восприемница")]),'
        )
        issue = next(i for i in self._structured(src) if "RLA001" in str(i["message"]))
        self.assertEqual(self._span(src, issue), '"восприемница"')


class TestSourceKinErrorDeclaration(_Harness):
    """When the SOURCE itself disagrees — a patronymic or surname that cannot
    come from the relative the same entry names — the transcription is faithful
    and there is nothing to fix. `source_kin_error=` records that verdict on the
    record, the way `source_date_error=` does for dates, so the finding stops
    being reported instead of sitting in the baseline as if it were debt."""

    def test_declared_patronymic_disagreement_is_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             bride=person("Ульяна", "Иванова"),\n'
            '             relatives=[relative(person("Іона", "Степановъ"),\n'
            '                                 Relationship.FATHER, "невеста")],\n'
            '             source_kin_error="сверено со сканом — так в подлиннике"),'
        ))
        self.assertEqual(errs, [], errs)

    def test_declared_surname_disagreement_is_silent(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ", "Медведкинъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ", "Подколесинъ"),\n'
            '                                 Relationship.FATHER, "жених")],\n'
            '             source_kin_error="сверено со сканом — так в подлиннике"),'
        ))
        self.assertEqual(errs, [], errs)

    def test_without_the_declaration_it_is_still_reported(self):
        errs = self._check(_marriage(
            "    marriage(1, 11,\n"
            '             groom=person("Семенъ", "Антиповъ", "Медведкинъ"),\n'
            '             relatives=[relative(person("Антипъ", "Кирилловъ", "Подколесинъ"),\n'
            '                                 Relationship.FATHER, "жених")]),'
        ))
        self.assertTrue(any("RLA003" in e for e in errs), errs)

    def test_the_declaration_does_not_silence_an_unattached_ref(self):
        # It speaks to the NAMES, not to whether the ref resolves.
        errs = self._check(_birth(
            "    birth(1, Gender.MALE, 3, 5,\n"
            '          father=person("Тарасъ", "Ивановъ"),\n'
            '          relatives=[relative(person("Илья", "Абрамовъ"),\n'
            '                              Relationship.FATHER, "мать")],\n'
            '          source_kin_error="так в подлиннике"),'
        ))
        self.assertTrue(any("RLA001" in e for e in errs), errs)
