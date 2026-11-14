import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.residence_title as check_residence_title


def _births(default_village: str, *birth_lines: str) -> str:
    """Wrap birth() snippets in a birth_records with a RecordDefaults residence."""
    body = ",\n".join(birth_lines)
    return (
        'birth_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
        f"{body},\n"
        f'    defaults=RecordDefaults(residence="{default_village}"))\n'
    )


class TestCheckResidenceTitle(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_residence_title.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    # --- landlord vs effective residence ---

    def test_sobakevichevo_landlord_inherits_gorjuhino_default_flagged(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            "status=MANILOV_OV_PEASANT_MALE))",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("RTV001", errors[0])
        self.assertIn("Собакевичево", errors[0])

    def test_sobakevichevo_landlord_explicit_sobakevichevo_ok(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            'residence="Собакевичево", status=MANILOV_OV_PEASANT_MALE))',
        )
        self.assertEqual(self._check(src), [])

    def test_gorjuhino_landlord_default_ok(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            "status=MANILOV_PS_PEASANT_MALE))",
        )
        self.assertEqual(self._check(src), [])

    def test_gorjuhino_landlord_explicit_sobakevichevo_flagged(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            'residence="Собакевичево", status=MANILOV_PS_PEASANT_MALE))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Горюхино", errors[0])

    def test_freeform_landlord_string_flagged(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            'status="крестьянин помещицы Ольги Власьевны Маниловой"))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Собакевичево", errors[0])

    def test_yasak_in_sobakevichevo_flagged(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            'residence="Собакевичево", status=YASAK_PEASANT_MALE))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Горюхино", errors[0])

    # --- exempt roles ---

    def test_godparent_landlord_exempt(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, '
            'father=person("Бен", "Петров", status=MANILOV_PS_PEASANT_MALE), '
            'god_parent1=person("Год", "Иванов", status=MANILOV_OV_PEASANT_MALE))',
        )
        self.assertEqual(self._check(src), [])

    def test_marriage_roles_with_a_stated_residence_are_exempt(self):
        # A wedding gathers people from several villages, so a residence the
        # author wrote down is taken from the source and never second-guessed.
        # (Without a stated residence they ARE checked — see TestMarriageRoles.)
        src = (
            'marriage_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    marriage(1, groom=person("Гр", "Петров", residence="Собакевичево", '
            "status=MANILOV_OV_PEASANT_MALE), "
            'witness1=person("Ви", "Иванов", residence="Усть-Неурожайка", '
            "status=MANILOV_OV_PEASANT_MALE)),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        self.assertEqual(self._check(src), [])

    def test_death_relative_and_witness_exempt(self):
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.MALE, deceased=person("Де", "Петров", '
            "status=YASAK_PEASANT_MALE), "
            'witness1=person("Ви", "Иванов", status=MANILOV_OV_PEASANT_MALE), '
            'relatives=[relative(person("Ро", "Сидоров", status=MANILOV_OV_PEASANT_MALE), None)]),\n'
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        self.assertEqual(self._check(src), [])

    def test_death_deceased_flagged(self):
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.MALE, deceased=person("Де", "Петров", '
            "status=MANILOV_OV_PEASANT_MALE)),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[RTV001] Умерший (Де Петров)", errors[0])

    def test_deceased_inherits_relatives_explicit_residence(self):
        # Death.__init__ derives one household residence from the first relative
        # that has one, BEFORE RecordDefaults substitutes the parish village. The
        # Собакевичево serf's infant therefore lives in Собакевичево, matching her
        # status — flagging her would be a contradiction the generator never
        # produces.
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.FEMALE, deceased=person("Екатерина", '
            "status=MANILOV_KF_PEASANT_DAUGHTER), age=1, "
            'relatives=[relative(person("Ефим", "Иванов", residence="Собакевичево", '
            "status=MANILOV_KF_PEASANT_MALE), "
            "Relationship.FATHER)]),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        self.assertEqual(self._check(src), [])

    def test_deceased_inherits_from_relatives_list_form(self):
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.FEMALE, deceased=person("Екатерина", '
            "status=MANILOV_KF_PEASANT_DAUGHTER), age=1, "
            'relatives=[relative(person("Ефим", "Иванов", residence="Собакевичево", '
            "status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)]),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        self.assertEqual(self._check(src), [])

    def test_deceased_still_flagged_when_relative_has_no_residence(self):
        # Nothing to inherit -> the parish default applies and the Собакевичево
        # status really does contradict it.
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.FEMALE, deceased=person("Екатерина", '
            "status=MANILOV_KF_PEASANT_DAUGHTER), age=1, "
            'relatives=[relative(person("Ефим", "Иванов", status=MANILOV_KF_PEASANT_MALE), '
            "Relationship.FATHER)]),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("RTV001", errors[0])

    def test_deceased_own_residence_beats_the_relatives(self):
        src = (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1855,\n'
            '    death(1, Gender.FEMALE, deceased=person("Екатерина", '
            'residence="Горюхино", status=MANILOV_KF_PEASANT_DAUGHTER), age=1, '
            'relatives=[relative(person("Ефим", "Иванов", residence="Собакевичево", '
            "status=MANILOV_KF_PEASANT_MALE), "
            "Relationship.FATHER)]),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("RTV001", errors[0])

    def test_mother_inherits_fathers_explicit_residence(self):
        # Father explicitly Собакевичево; mother has no residence of her own ->
        # she inherits his, so she is NOT flagged (only would be vs the default).
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, '
            'father=person("Отец", "Петров", residence="Собакевичево", '
            "status=MANILOV_OV_PEASANT_MALE), "
            'mother=person("Мать", "Иванова", status=MANILOV_OV_PEASANT_FEMALE))',
        )
        self.assertEqual(self._check(src), [])

    def test_father_missing_residence_flags_both(self):
        # Neither parent has explicit residence -> both inherit the Горюхино
        # default and both are flagged (the father is the root error to fix).
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, '
            'father=person("Отец", "Петров", status=MANILOV_OV_PEASANT_MALE), '
            'mother=person("Мать", "Иванова", status=MANILOV_OV_PEASANT_FEMALE))',
        )
        self.assertEqual(len(self._check(src)), 2)

    # --- skip conditions ---

    def test_indeterminate_residence_skipped(self):
        # birth() with no record default and no explicit residence -> skip.
        src = (
            '_b = birth(1, Gender.MALE, father=person("Иван", "Петров", '
            "status=MANILOV_OV_PEASANT_MALE))\n"
        )
        self.assertEqual(self._check(src), [])

    def test_unclassified_statuses_skipped(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("А", "Петров", status=MAIDEN))',
            '    birth(2, Gender.MALE, father=person("Б", "Петров", status="помещик"))',
            '    birth(3, Gender.MALE, father=person("В", "Петров", '
            "status=PEASANT_MALE))",
        )
        self.assertEqual(self._check(src), [])

    def test_econ_peasant_not_village_specific_skipped(self):
        # Economic peasants are not tied to Горюхино -> never flagged.
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Эк", "Петров", '
            'residence="Ротозейск", status=ECON_PEASANT_MALE))',
            '    birth(2, Gender.MALE, father=person("Эк", "Петров", '
            'residence="Ротозейск", status="экономический крестьянин"))',
        )
        self.assertEqual(self._check(src), [])

    def test_dvorovy_serf_skipped(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Дв", "Петров", '
            'status="дворовый человек помещицы Лукерьи Кузьминичны Маниловой"))',
        )
        self.assertEqual(self._check(src), [])

    def test_unknown_landlord_key_skipped(self):
        # MANILOV_OVS (Ольга Власовна) is not in the confirmed map.
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Не", "Петров", '
            "status=MANILOV_OVS_PEASANT_MALE))",
        )
        self.assertEqual(self._check(src), [])

    # --- census ---

    def _census(self, village: str, person_src: str) -> str:
        return (
            f'census_records("a", "f", "i", "c", "{village}", 1850,\n'
            f"    household(member(1, {person_src}, CensusRole.HEAD, 60)))\n"
        )

    def test_census_member_wrong_village_flagged(self):
        src = self._census(
            "Горюхино",
            'person("Иван", "Петров", status=MANILOV_OV_PEASANT_MALE)',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[RTV001] Член двора (Иван Петров)", errors[0])

    def test_census_member_right_village_ok(self):
        src = self._census(
            "Собакевичево",
            'person("Иван", "Петров", status=MANILOV_OV_PEASANT_MALE)',
        )
        self.assertEqual(self._check(src), [])

    def test_census_member_explicit_residence_overrides_village(self):
        src = self._census(
            "Горюхино",
            'person("Иван", "Петров", residence="Собакевичево", '
            "status=MANILOV_OV_PEASANT_MALE)",
        )
        self.assertEqual(self._check(src), [])

    # --- orthography ---

    def test_kazennyj_orthography_both_flagged(self):
        for status in ('"казённый крестьянин"', '"казенный крестьянин"'):
            src = _births(
                "Горюхино",
                '    birth(1, Gender.MALE, father=person("Ка", "Петров", '
                f"residence=\"Собакевичево\", status={status}))",
            )
            errors = self._check(src)
            self.assertEqual(len(errors), 1, (status, errors))
            self.assertIn("Горюхино", errors[0])

    # --- structured API ---

    def test_structured_output_shape(self):
        src = _births(
            "Горюхино",
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            "status=MANILOV_OV_PEASANT_MALE))",
        )
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            issues = check_residence_title.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "error")
        self.assertIn("RTV001", issues[0]["message"])
        self.assertIsInstance(issues[0]["line"], int)


if __name__ == "__main__":
    unittest.main()


def _marriage_records(body: str, default_village: str = "Горюхино") -> str:
    """Wrap marriage() snippets in a marriage_records with a default residence."""
    return (
        'marriage_records("a", "f", "i", "c", "Горюхино", "Церковь", 1839,\n'
        f"{body},\n"
        f'    defaults=RecordDefaults(residence="{default_village}"))\n'
    )


class TestMarriageRoles(unittest.TestCase):
    """In a marriage the check runs ONLY on an inherited residence.

    A wedding gathers people from several villages, and when the author states
    where someone lives that statement comes from the source — an Плюшкина serf
    recorded in Усть-Неурожайка means the landlord held serfs there, not that the
    record is wrong. What the check can still catch is the silent case: nobody
    said where this person lives, so they take the parish default while their
    own status names another village.
    """

    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_residence_title.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def test_inherited_default_contradicting_the_status_is_flagged(self):
        errs = self._check(_marriage_records(
            '    marriage(17, 8,\n'
            '        bride=person("Агафія", "Константинова", status=SOBAKEVICH_TL_PEASANT_MAIDEN))'
        ))
        self.assertTrue(any("RTV001" in e and "Собакевичево" in e and "Горюхино" in e
                            for e in errs), errs)

    def test_explicit_residence_is_respected(self):
        errs = self._check(_marriage_records(
            '    marriage(17, 8,\n'
            '        groom=person("Прохоръ", "Петровъ", residence="Усть-Неурожайка",'
            ' status=SOBAKEVICH_TL_PEASANT_MALE))'
        ))
        self.assertEqual(errs, [], errs)

    def test_witnesses_and_relatives_are_covered(self):
        errs = self._check(_marriage_records(
            '    marriage(17, 8,\n'
            '        witness1=person("Кононъ", "Ивановъ", status=SOBAKEVICH_TL_PEASANT_MALE),\n'
            '        relatives=[relative(person("Константинъ", "Акимовъ",'
            ' status=SOBAKEVICH_TL_PEASANT_MALE), Relationship.FATHER, "невеста")])'
        ))
        self.assertEqual(len([e for e in errs if "RTV001" in e]), 2, errs)

    def test_matching_status_is_silent(self):
        errs = self._check(_marriage_records(
            '    marriage(17, 8,\n'
            '        groom=person("Иванъ", "Петровъ", status=MANILOV_LK_PEASANT_MALE))'
        ))
        self.assertEqual(errs, [], errs)


class TestLandlordWithSeveralVillages(unittest.TestCase):
    """A landlord's estate is usually one village, but not always. Собакевич
    held Собакевичево and also Дырявино and Усть-Неурожайка — one of his
    peasants marries out of Дырявино and buries a daughter from there years
    later. A residence the records attest for that landlord is not a
    contradiction; inheriting the PARISH default still is."""

    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_residence_title.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _deaths(self, deceased: str) -> str:
        return (
            'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1842,\n'
            f"    death(12, Gender.FEMALE, 9, 10, deceased={deceased}),\n"
            '    defaults=RecordDefaults(residence="Горюхино"))\n'
        )

    def test_secondary_village_of_the_same_landlord_is_accepted(self):
        errs = self._check(self._deaths(
            'person("Матрона", residence="Дырявино", '
            "status=SOBAKEVICH_TL_PEASANT_DAUGHTER)"))
        self.assertEqual(errs, [], errs)

    def test_primary_village_still_accepted(self):
        errs = self._check(self._deaths(
            'person("Матрона", residence="Собакевичево", '
            "status=SOBAKEVICH_TL_PEASANT_DAUGHTER)"))
        self.assertEqual(errs, [], errs)

    def test_parish_default_is_still_flagged(self):
        errs = self._check(self._deaths(
            'person("Матрона", status=SOBAKEVICH_TL_PEASANT_DAUGHTER)'))
        self.assertTrue(any("RTV001" in e and "Горюхино" in e for e in errs), errs)

    def test_an_unattested_village_is_still_flagged(self):
        errs = self._check(self._deaths(
            'person("Матрона", residence="Ротозеево", '
            "status=SOBAKEVICH_TL_PEASANT_DAUGHTER)"))
        self.assertTrue(any("RTV001" in e for e in errs), errs)


def _lint(src: str) -> list[str]:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    try:
        f.write(src)
        f.close()
        return [line.split(": ", 1)[1] for line in check_residence_title.check_file(Path(f.name))]
    finally:
        Path(f.name).unlink()


_DG_BARE = ('DEFAULTS = RecordDefaults(residence="Глуповы Горы", '
            "status_male=PEASANT_MALE, status_female=PEASANT_FEMALE)\n")


def _dg(kind: str, year: int, body: str, defaults: str = _DG_BARE) -> str:
    return (defaults
            + f'{kind}_records("ГАВО", "600", "692", "283", "Глуповы Горы", "Покровская", {year},\n'
            + f"{body},\n    defaults=DEFAULTS)\n")


class TestTheYasakRuleIsGorjuhinosParish(unittest.TestCase):
    """«Ясачные и казённые жили в Горюхино» is a fact about one parish."""

    _DECEASED = ('    death(8, Gender.FEMALE, 21, 23, deceased=person("Евпраксія", '
                 '"Игнатьева", residence="Горелово", status=KAZENNYJ_PEASANT_FEMALE))')

    def test_a_gorelovo_state_peasant_in_glupovy_gory_is_not_flagged(self):
        self.assertEqual([], _lint(_dg("death", 1826, self._DECEASED)))

    def test_the_same_record_in_a_gorjuhino_book_is(self):
        src = _dg("death", 1826, self._DECEASED).replace(
            '"Глуповы Горы", "Покровская"', '"Горюхино", "Церковь"')
        errors = _lint(src)
        self.assertEqual(1, len(errors), errors)
        self.assertEqual(
            "[RTV001] Умершая (Евпраксія Игнатьева) — «казенная крестьянка»: ясачные и "
            "казённые крестьяне прихода жили в Горюхино, а место жительства здесь — "
            "Горелово (указано в записи). Проверьте статус или укажите residence=.",
            errors[0])

    def test_a_landlord_is_checked_in_any_book(self):
        src = (
            'birth_records("a", "f", "i", "c", "Неелово", "Церковь", 1840,\n'
            '    birth(1, Gender.MALE, father=person("Иван", "Петров", '
            "status=MANILOV_OV_PEASANT_MALE)),\n"
            '    defaults=RecordDefaults(residence="Неелово"))\n'
        )
        errors = _lint(src)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("крестьяне Ольги Власьевны Маниловой жили в Собакевичево", errors[0])
        self.assertIn("Неелово (по умолчанию книги)", errors[0])


class TestGlupovyGory(unittest.TestCase):
    """Горелово was a state village, the село its owners' (RTV002)."""

    def test_an_owner_named_in_gorelovo_is_a_contradiction(self):
        src = _dg("birth", 1830, '    birth(1, Gender.MALE, father=person("Иванъ", '
                  'residence="Горелово", status=GOLOVLEV_PEASANT), '
                  'mother=person("Марія", status=GOLOVLEV_PEASANT_WIFE))')
        errors = _lint(src)
        self.assertEqual(2, len(errors), errors)
        self.assertEqual(
            "[RTV002] Отец (Иванъ) живёт в Горелово (указано в записи), а статус — "
            "«крестьянин вотчины гг. Головлевых»: в Горелово жили казённые крестьяне, "
            "вотчинные — в Глуповых Горах. Проверьте статус или место.", errors[0])
        self.assertIn("[RTV002] Мать (Марія) живёт в Горелово (как у отца)", errors[1])

    def test_a_state_peasant_in_the_selo_is_a_contradiction(self):
        src = _dg("marriage", 1842, '    marriage(1, groom=person("Петръ", '
                  'status="крестьянин Государственных имуществ"))')
        errors = _lint(src)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("[RTV002] Жених (Петръ) живёт в Глуповых Горах (по умолчанию "
                      "книги), а статус — «крестьянин Государственных имуществ»", errors[0])

    def test_the_book_default_is_what_puts_an_owner_in_gorelovo(self):
        defaults = ('DEFAULTS = RecordDefaults(residence="Глуповы Горы", '
                    "status_male=NOZDREV_PEASANT, status_female=NOZDREV_PEASANT_FEMALE)\n")
        src = _dg("birth", 1810, '    birth(1, Gender.MALE, god_parent1=person("Симеонъ", '
                  'residence="Горелово"))', defaults)
        errors = _lint(src)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("статус — «крестьянин вотчины г-на Ноздрева» (по умолчанию книги)",
                      errors[0])

    def test_a_soldier_lives_where_his_service_put_him(self):
        src = _dg("birth", 1884, '    birth(1, Gender.MALE, god_parent1=person("Аѳанасій", '
                  'status="сторож казённого бора, рядовой солдат"))')
        self.assertEqual([], _lint(src))

    def test_a_bare_peasant_is_what_the_book_says(self):
        # RTV003, retired 2026-10-09: the books write plain «крестьянин» — in the
        # село and in Горелово alike, before 1861 too (1839) — and so does the DSL.
        births = _dg("birth", 1839, '    birth(1, Gender.MALE, father=person("Иванъ"), '
                     'mother=person("Анастасія", "Васильева", status=PEASANT_LEGAL_WIFE))')
        deaths = _dg("death", 1826, '    death(8, Gender.FEMALE, 21, 23, deceased=person('
                     '"Евпраксія", "Игнатьева", residence="Горелово"), '
                     'relatives=[relative(person("Фролъ", "Савинъ"), Relationship.HUSBAND)])')
        marriages = _dg("marriage", 1820, '    marriage(1, bride=person("Анна", '
                        'status="крестьянская дочь девица"))')
        for src in (births, deaths, marriages):
            self.assertEqual([], _lint(src))

    def test_a_newborn_and_a_dead_child_are_left_to_their_parent(self):
        births = _dg("birth", 1830, '    birth(1, Gender.MALE, father=person("Иванъ", '
                     'residence="Горелово", status=GOLOVLEV_PEASANT), child=person("Петръ"))')
        deaths = _dg("death", 1830, '    death(1, Gender.MALE, 1, 2, deceased=person("Петръ"), '
                     'relatives=[relative(person("Иванъ", residence="Горелово", status=GOLOVLEV_PEASANT), '
                     "Relationship.FATHER)])")
        for src in (births, deaths):
            errors = _lint(src)
            self.assertEqual(1, len(errors), errors)
            self.assertTrue(errors[0].startswith("[RTV002] Отец (Иванъ)"), errors)

    def test_owners_named_by_the_honorific_alone_count(self):
        src = _dg("birth", 1815, '    birth(1, Gender.FEMALE, god_parent2=person("Анна", '
                  'residence="Горелово", status="крестьянская дочь девка г-на Ноздрева"))')
        errors = _lint(src)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("[RTV002] Восприемница (Анна) живёт в Горелово", errors[0])

    def test_other_parishes_are_not_asked(self):
        src = (
            'birth_records("a", "f", "i", "c", "Заманиловка", "Церковь", 1830,\n'
            '    birth(1, Gender.MALE, father=person("Иван", residence="Горелово")),\n'
            '    defaults=RecordDefaults(residence="Заманиловка", status_male=PEASANT_MALE))\n'
        )
        self.assertEqual([], _lint(src))

    def test_a_reconstructed_roll_member_is_not_in_the_book(self):
        def roll(hidden: str) -> str:
            return (
                _DG_BARE
                + 'census = census_records("ГАВО", "1", "1", "1", "Глуповы Горы", 1816,\n'
                + '    household("1", member(1, person("Иванъ", status="крестьянин Государственных '
                + f'имуществ"), CensusRole.HEAD, 60{hidden})),\n'
                + "    defaults=DEFAULTS)\n"
            )
        self.assertEqual(1, len(_lint(roll(""))))
        self.assertEqual([], _lint(roll(", hidden=True")))


class TestRulesComeFromTheCorpus(unittest.TestCase):
    """RTV001/RTV002 read their parishes, villages and landlords off corpus/estates.toml."""

    def test_rtv_rules_come_from_the_corpus(self):
        from verso.core.workspace import use
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "verso.toml").write_text('schema = 2\n[corpus]\ndir = "corpus"\n', encoding="utf-8")
            (root / "corpus").mkdir()
            (root / "corpus" / "estates.toml").write_text(
                '[[owners_and_state]]\nparish = "Ольховка"\n'
                'owners = { village = "Ольховка", in = "в Ольховке" }\n'
                'state = { village = "Дубки", in = "в Дубках" }\n', encoding="utf-8")
            src = ('birth_records("a", "f", "i", "c", "Ольховка", "Церковь", 1855,\n'
                   '    birth(1, Gender.MALE, father=person("Иванъ", "Петровъ", residence="Дубки", '
                   'status="крестьянин вотчины г-на Первова")))\n')
            path = root / "x.py"
            path.write_text(src, encoding="utf-8")
            with use(root):
                errors = check_residence_title.check_file(path)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[RTV002] Отец (Иванъ Петровъ) живёт в Дубках (указано в записи)", errors[0])
        self.assertIn("в Дубках жили казённые крестьяне, вотчинные — в Ольховке", errors[0])
