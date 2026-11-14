import tempfile
import unittest
from pathlib import Path

import verso.ru.linters.checks.parent_status as check_parent_status


def _births(body: str, defaults: str = "status_male=YASAK_PEASANT_MALE, "
                                       "status_female=YASAK_PEASANT_FEMALE") -> str:
    return (
        'birth_records("a", "f", "i", "c", "Горюхино", "Церковь", 1830,\n'
        f"{body},\n"
        f"    defaults=RecordDefaults({defaults}))\n"
    )


def _deaths(body: str, defaults: str = "status_male=YASAK_PEASANT_MALE, "
                                       "status_female=YASAK_PEASANT_FEMALE") -> str:
    return (
        'death_records("a", "f", "i", "c", "Горюхино", "Церковь", 1830,\n'
        f"{body},\n"
        f"    defaults=RecordDefaults({defaults}))\n"
    )


def _marriages(body: str, defaults: str = "status_male=YASAK_PEASANT_MALE, "
                                          "status_female=YASAK_PEASANT_FEMALE") -> str:
    return (
        'marriage_records("a", "f", "i", "c", "Горюхино", "Церковь", 1830,\n'
        f"{body},\n"
        f"    defaults=RecordDefaults({defaults}))\n"
    )


class TestCheckParentStatus(unittest.TestCase):
    def _check(self, src: str) -> list[str]:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        )
        try:
            f.write(src)
            f.close()
            return check_parent_status.check_file(Path(f.name))
        finally:
            Path(f.name).unlink()

    def _codes(self, src: str) -> list[str]:
        out = []
        for e in self._check(src):
            for code in ("PSA001", "PSA002", "PSA003", "PSA004"):
                if code in e:
                    out.append(code)
        return out

    # --- estate model ---

    def test_legal_wife_shares_her_husbands_landlord_estate(self):
        """MANILOV_KF_LEGAL_WIFE must resolve to MANILOV_KF_PEASANT."""
        self.assertEqual(
            check_parent_status.estates()["MANILOV_KF_LEGAL_WIFE"],
            check_parent_status.estates()["MANILOV_KF_PEASANT_MALE"],
        )

    def test_colonel_alias_folds_onto_the_landlord(self):
        self.assertEqual(
            check_parent_status.estates()["SOBAKEVICH_ZP_COL_PEASANT_MALE"],
            check_parent_status.estates()["SOBAKEVICH_ZP_PEASANT_MALE"],
        )

    def test_daughter_maiden_role_beats_maiden(self):
        """Longest-first suffix matching keeps the estate intact."""
        self.assertEqual(
            check_parent_status.estates()["YASAK_PEASANT_DAUGHTER_MAIDEN"],
            "YASAK_PEASANT",
        )

    def test_daughter_girl_role_beats_girl(self):
        """«крестьянская дочь девка»: GIRL alone would make an estate of
        GOLOVLEV_PEASANT_DAUGHTER that no relative could ever match."""
        self.assertEqual(
            check_parent_status.estates()["GOLOVLEV_PEASANT_DAUGHTER_GIRL"],
            check_parent_status.estates()["GOLOVLEV_PEASANT"],
        )

    def test_soldier_wife_keeps_her_peasant_estate(self):
        """Pins the reason military stays exempt even for a spouse pair:
        `YASAK_SOLDIER_WIFE` is «солдатка» of the ясачные — our own constants
        say a soldier's wife does NOT leave her husband's former estate."""
        self.assertEqual(
            check_parent_status.estates()["YASAK_SOLDIER_WIFE"],
            check_parent_status.estates()["YASAK_PEASANT_MALE"],
        )

    def test_popadia_shares_her_priests_estate(self):
        """«попадья» IS the wife of a «священник» — one household, one rank."""
        self.assertEqual(
            check_parent_status.estates()["POPADIA"],
            check_parent_status.estates()["PRIEST"],
        )

    def test_hiereus_is_the_same_office_as_priest(self):
        """«иерей» and «священник» are two words for one rank."""
        self.assertEqual(
            check_parent_status.estates()["HIEREUS"],
            check_parent_status.estates()["PRIEST"],
        )

    def test_dyachikha_shares_her_dyachoks_estate(self):
        self.assertEqual(
            check_parent_status.estates()["DYACHIKHA_WIDOW"],
            check_parent_status.estates()["DYACHOK"],
        )

    # --- PSA001: both sides explicit ---

    def test_death_landlord_father_yasak_child_flagged(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            "status=YASAK_PEASANT_SON), age=4, relatives=[relative(person(\"Петр\", "
            "status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])
        self.assertIn("отец (Петр) — «крестьянин помещика Кузьмы Филипповича Манилова»", errors[0])
        self.assertIn("Умерший (Иван) — «ясачный крестьянский сын»", errors[0])

    def test_matching_estates_ok(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            "status=MANILOV_KF_PEASANT_SON), age=4, relatives=[relative(person(\"Петр\", "
            "status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_legal_wife_matches_her_husband(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            "status=MANILOV_KF_PEASANT_MALE), mother=person(\"Мария\", "
            "status=MANILOV_KF_LEGAL_WIFE))",
        )
        self.assertEqual(self._check(src), [])

    def test_the_two_names_of_the_state_peasants_are_one_estate(self):
        """GOSUDARSTVENNYJ_PEASANT_* and STATE_PEASANT_* spell one estate alike;
        read by prefix, a husband of the one and a wife or child of the other
        were two estates — PSA001."""
        self.assertEqual(
            check_parent_status.estates()["GOSUDARSTVENNYJ_PEASANT_MALE"],
            check_parent_status.estates()["STATE_PEASANT_LEGAL_WIFE"],
        )
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            "status=GOSUDARSTVENNYJ_PEASANT_MALE), mother=person(\"Мария\", "
            "status=STATE_PEASANT_LEGAL_WIFE), child=person(\"Иван\", "
            "status=STATE_PEASANT_SON))",
            defaults="status_male=GOSUDARSTVENNYJ_PEASANT_MALE, "
                     "status_female=GOSUDARSTVENNYJ_PEASANT_FEMALE",
        )
        self.assertEqual(self._check(src), [])

    def test_soldier_child_exempt(self):
        """Conscription pulls a man out of his father's estate."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=SOLDIER), age=30, relatives=[relative(person("Петр", '
            "status=YASAK_PEASANT_MALE), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_clergy_pair_exempt(self):
        src = _marriages(
            '    marriage(1, 7, groom=person("Федор", status=SEXTON), '
            'bride=person("Надежда", status=MAIDEN),\n'
            '             relatives=[relative(person("Никита", status=DEACON), '
            'Relationship.FATHER, "жених")])',
        )
        self.assertEqual(self._check(src), [])

    def test_plain_string_status_resolves_like_its_constant(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status="ясачный крестьянский сын"), age=4, relatives=[relative(person("Петр", '
            'status="крестьянин помещика Кузьмы Филипповича Манилова"), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_free_text_no_constant_spells_is_compared_by_its_words(self):
        """No constant names Тентетников's serfs; the words still name an owner,
        and a ясачный son is not that owner's."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=YASAK_PEASANT_SON), age=4, relatives=[relative(person("Петр", '
            'status="крестьянин помещика Кузьмы Васильева Тентетникова"), '
            "Relationship.FATHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])
        self.assertIn("«крестьянин помещика Кузьмы Васильева Тентетникова»", errors[0])

    def test_unrecognised_constant_is_skipped(self):
        """A name the statuses module does not define says nothing we can read."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=YASAK_PEASANT_SON), age=4, relatives=[relative(person("Петр", '
            "status=NO_SUCH_STATUS), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    # --- free text: the child the book's default made ясачный ---

    def test_dvorovy_father_and_defaulted_child_flagged(self):
        """A birth where the father is «дворовый человек помещицы
        Лукерьи Кузьминичны Маниловой», which no constant spells, so the child
        was left to the parish default — ясачный — and nothing said so."""
        src = _births(
            '    birth(4, Gender.MALE, father=person("Филипп", '
            'status="дворовый человек помещицы Лукерьи Кузьминичны Маниловой"), '
            'child=person("Иван"))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA002", errors[0])
        self.assertIn("по умолчанию книги он «ясачный крестьянин»", errors[0])

    def test_meshchanka_mother_and_defaulted_child_flagged(self):
        src = _births(
            '    birth(1, Gender.MALE, mother=person("Анна", '
            'status="вдова мещанка"), child=person("Иван"))',
        )
        self.assertEqual(self._codes(src), ["PSA002"])

    def test_soldier_wife_naming_her_origin_is_compared(self):
        """«солдатская жена из крестьян помещика X» kept X's estate — the same
        reading as YASAK_SOLDIER_WIFE → YASAK_PEASANT — so her child left on
        the ясачный default contradicts her."""
        src = _births(
            '    birth(1, Gender.MALE, mother=person("Анна", '
            'status="солдатская жена из крестьян помещика Фрола Лаврентьевича '
            'Манилова"), child=person("Иван"))',
        )
        self.assertEqual(self._codes(src), ["PSA002"])

    def test_bare_soldatka_names_no_estate(self):
        src = _births(
            '    birth(1, Gender.MALE, mother=person("Анна", '
            'status="солдатская женка"), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_owner_spelled_two_ways_is_one_owner(self):
        """«Демьяна Назарова» and «Демьяна Назаровича» Манилова are one
        man; the books write both."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин помещика Демьяна Назарова Манилова"), '
            "child=person(\"Иван\", status=MANILOV_DN_PEASANT_SON))",
        )
        self.assertEqual(self._check(src), [])

    def test_two_owners_of_one_family_still_differ(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин помещика Фрола Лаврентьевича Манилова"), '
            "child=person(\"Иван\", status=MANILOV_DN_PEASANT_SON))",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_bare_dvorovy_underspecifies_a_landlord(self):
        """«дворовый человек» names no owner, so it cannot contradict one."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="дворовый человек"), '
            "child=person(\"Иван\", status=MANILOV_DN_PEASANT_SON))",
        )
        self.assertEqual(self._check(src), [])

    def test_bare_dvorovy_husband_and_defaulted_wife_flagged(self):
        """The wife of a дворовый человек is not an
        экономическая крестьянка, whatever the book's default says."""
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Петр", '
            'status="дворовый человек"), mother=person("Анна"))',
            defaults="status_male=ECON_PEASANT_MALE, "
                     "status_female=ECON_PEASANT_FEMALE",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("У жены (Анна) сословие не указано", errors[0])

    def test_free_text_clergy_parent_stays_exempt(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="сын диакона"), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_free_text_beside_a_soldier_constant_stays_exempt(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=SOLDIER), age=30, relatives=[relative(person("Петр", '
            'status="однодворец"), Relationship.FATHER)])',
        )
        self.assertEqual(self._check(src), [])

    def test_marriage_pairs_via_relationship_ref(self):
        """The bride's father must be compared to the BRIDE, not the groom."""
        src = _marriages(
            '    marriage(1, 7, groom=person("Иван", status=YASAK_PEASANT_MALE), '
            'bride=person("Дарья", status=MANILOV_KF_PEASANT_DAUGHTER),\n'
            '             relatives=[relative(person("Никита", '
            'status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER, "невеста")])',
        )
        self.assertEqual(self._check(src), [])

    def test_groom_and_bride_never_compared(self):
        """Different households by definition — that is what a marriage is."""
        src = _marriages(
            '    marriage(1, 7, groom=person("Иван", status=YASAK_PEASANT_MALE), '
            'bride=person("Дарья", status=MANILOV_KF_PEASANT_DAUGHTER))',
        )
        self.assertEqual(self._check(src), [])

    # --- spouse pairs: a wife carries her husband's estate ---

    def test_clergy_husband_and_peasant_wife_flagged(self):
        """Духовенство was a closed estate: a пономарь's wife is «жена
        пономаря», never «законная жена казённого крестьянина». Unlike a
        father and his son, the two sides of ONE marriage cannot differ."""
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Феодор", '
            'status=SEXTON), mother=person("Надежда", '
            "status=KAZENNYJ_PEASANT_LEGAL_WIFE))",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])
        self.assertIn("муж (Феодор) — «пономарь»", errors[0])

    def test_statusless_wife_of_a_clergy_husband_flagged(self):
        """The mother's omitted `status=` hands her the
        parish peasant default while her husband is a пономарь."""
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Феодор", '
            'status=SEXTON), mother=person("Надежда"))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA002", errors[0])
        self.assertIn("SEXTON", errors[0])

    def test_clergy_wife_matches_her_clergy_husband(self):
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Феодор", '
            'status=SEXTON), mother=person("Надежда", status=SEXTON_WIFE))',
        )
        self.assertEqual(self._check(src), [])

    def test_clergy_husband_of_a_peasant_deceased_wife_flagged(self):
        src = _deaths(
            '    death(1, Gender.FEMALE, 5, 6, deceased=person("Надежда", '
            'status=YASAK_PEASANT_FEMALE), age=40, relatives=[relative(person("Феодор", '
            "status=SEXTON), Relationship.HUSBAND)])",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_clergy_parent_and_child_stay_exempt(self):
        """The generational exemption survives: ranks legitimately differ
        between a father and his son — that is what a spouse pair does NOT get."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Феодор", '
            'status=SEXTON), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_soldier_husband_and_peasant_wife_stay_exempt(self):
        """A солдатка keeps her peasant estate — see
        [test_soldier_wife_keeps_her_peasant_estate]. Military stays exempt
        on BOTH axes; clergy only on the generational one."""
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Василий", '
            'status=SOLDIER), mother=person("Евдокия"))',
        )
        self.assertEqual(self._check(src), [])

    def test_vacuous_wife_status_never_compared(self):
        """«женка» names no сословие, so it cannot contradict her husband's."""
        src = _deaths(
            '    death(1, Gender.FEMALE, 5, 6, deceased=person("Гликерья", '
            'status=ZHONKA), age=40, relatives=[relative(person("Иван"), '
            "Relationship.HUSBAND)])",
        )
        self.assertEqual(self._check(src), [])

    # --- PSA002: one side inherits a different estate from RecordDefaults ---

    def test_statusless_child_of_derivable_father_is_silent(self):
        """Birth.__init__ derives the child's status from a peasant-estate
        father (statuses.child_status_for), so there is nothing to flag."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_proprietor_peasants_wife_on_the_plain_default_is_silent(self):
        """«крестьянин собственник» is the peasant estate, not one of its own:
        the book's «законная жена крестьянина» beside him is no PSA004, and his
        statusless child derives «крестьянский сын»."""
        self.assertEqual(check_parent_status.estates()["PROPRIETOR_PEASANT_MALE"],
                         check_parent_status.estates()["PEASANT_MALE"])
        self.assertEqual(check_parent_status.estates()["TEMP_OBLIGED_PEASANT_MALE"],
                         check_parent_status.estates()["PEASANT_MALE"])
        for status in ("PROPRIETOR_PEASANT_MALE", '"крестьянин собственник"'):
            src = _births(
                '    birth(1, Gender.MALE, father=person("Петр", '
                f'status={status}), mother=person("Агафья"), child=person("Иван"))',
                defaults="status_male=PEASANT_MALE, status_female=PEASANT_FEMALE, "
                         "status_mother=PEASANT_WIFE",
            )
            self.assertEqual(self._check(src), [], status)

    def test_statusless_child_of_derivable_mother_is_silent(self):
        src = _births(
            '    birth(1, Gender.MALE, mother=person("Дарья", '
            'status=MANILOV_KF_PEASANT_FEMALE), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_statusless_child_of_meshchanin_father_still_flagged(self):
        """MESHCHANIN is out of derivation scope — the child genuinely
        inherits the parish default, so PSA002 keeps firing."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MESHCHANIN), child=person("Иван"))',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA002", errors[0])
        self.assertIn("по умолчанию книги он «ясачный крестьянин»", errors[0])

    def test_dvorovy_and_peasant_of_one_owner_are_one_estate(self):
        """The books style one household «дворовый» and «крестьянин» by
        turns (the daughters of one household in a book's burials)."""
        src = _deaths(
            '    death(1, Gender.FEMALE, 5, 6, deceased=person("Анна", '
            'status=MANILOV_SP_PEASANT_DAUGHTER), age=2, relatives=[relative(person("Александр", '
            "status=MANILOV_SP_DVOROVY), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_dvorovy_husband_and_peasants_wife_of_one_owner_agree(self):
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Александр", '
            'status=MANILOV_SP_DVOROVY), mother=person("Агрипина", '
            "status=MANILOV_SP_LEGAL_WIFE), child=person(\"Агрипина\", "
            "status=MANILOV_SP_DVOROVY_DAUGHTER))",
        )
        self.assertEqual(self._check(src), [])

    def test_dvorovy_of_another_owner_still_differs(self):
        """Савва Пантелеевич's дворовый is not Прохор Савельевич's
        крестьянин — the owner has to agree."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=MANILOV_PS_PEASANT_SON), age=2, relatives=[relative(person("Александр", '
            "status=MANILOV_SP_DVOROVY), Relationship.FATHER)])",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_out_of_scope_father_blocks_mother_derivation(self):
        """Mirror of Birth.__init__: a дворовый father is consulted
        exclusively, so his wife's derivable estate does not silence the
        finding — the child really stays statusless."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_SP_DVOROVY), mother=person("Дарья", '
            'status=MANILOV_SP_LEGAL_WIFE), child=person("Иван"))',
        )
        errors = [e for e in self._check(src) if "У ребёнка" in e]
        self.assertEqual(len(errors), 2, errors)  # father~child + mother~child

    def test_statusless_deceased_of_derivable_father_is_silent(self):
        """Death.__init__ derives the deceased child's status from a
        peasant-estate parent relative — nothing to flag."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван"), age=1, '
            'relatives=[relative(person("Петр", status=MANILOV_KF_PEASANT_MALE), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_statusless_deceased_of_merchant_father_still_flagged(self):
        """MERCHANT is out of derivation scope — the deceased genuinely
        inherits the parish default, so PSA002 keeps firing."""
        src = _deaths(
            '    death(1, Gender.FEMALE, 5, 6, deceased=person("Ирина"), age=1, '
            'relatives=[relative(person("Василий", status=MERCHANT), '
            "Relationship.FATHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA002", errors[0])

    def test_statusless_father_of_explicit_deceased_still_flagged(self):
        """The REVERSE direction has no inheritance: an explicit deceased
        with a statusless father leaves the father on the parish default."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=MANILOV_KF_PEASANT_SON), age=1, relatives=[relative(person("Петр"), '
            "Relationship.FATHER)])",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA002", errors[0])

    # --- generic-PEASANT compatibility ---

    def test_plain_peasant_deceased_compatible_with_econ_default(self):
        """Bare «крестьянский сын» UNDER-specifies, it does not contradict the
        parish «экономический крестьянин» convention (a whole village's books)."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Савва", '
            'status=PEASANT_SON), age=27, relatives=[relative(person("Агафья"), '
            "Relationship.MOTHER)])",
            defaults="status_male=ECON_PEASANT_MALE, "
                     "status_female=ECON_PEASANT_FEMALE",
        )
        self.assertEqual(self._check(src), [])

    def test_plain_peasant_compatible_in_psa001_too(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Савва", '
            'status=PEASANT_SON), age=27, relatives=[relative(person("Агафья", '
            '"Ильина", status=ECON_PEASANT_WIDOW), '
            "Relationship.MOTHER)])",
        )
        self.assertEqual(self._check(src), [])

    def test_two_qualified_estates_still_contradict(self):
        """The compat rule is only for bare PEASANT — ECON vs YASAK stays red."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=YASAK_PEASANT_SON), age=4, relatives=[relative(person("Пётр", '
            'status=ECON_PEASANT_MALE), Relationship.FATHER)])',
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])

    def test_default_equal_to_the_stated_estate_ok(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=YASAK_PEASANT_MALE), child=person("Иван"))',
        )
        self.assertEqual(self._check(src), [])

    def test_no_record_defaults_means_no_psa002(self):
        src = (
            'birth_records("a", "f", "i", "c", "Горюхино", "Церковь", 1830,\n'
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван")))\n'
        )
        self.assertEqual(self._check(src), [])

    def test_status_mother_override_is_honoured(self):
        """The mother's fallback is status_mother, not status_female."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), mother=person("Мария"))',
            defaults="status_male=YASAK_PEASANT_MALE, "
                     "status_female=YASAK_PEASANT_FEMALE, "
                     "status_mother=MANILOV_KF_LEGAL_WIFE",
        )
        self.assertEqual(self._check(src), [])

    def test_status_bride_override_is_honoured(self):
        src = _marriages(
            '    marriage(1, 7, groom=person("Иван"), bride=person("Дарья"),\n'
            '             relatives=[relative(person("Никита", '
            'status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER, "невеста")])',
            defaults="status_male=YASAK_PEASANT_MALE, "
                     "status_bride=MANILOV_KF_PEASANT_DAUGHTER",
        )
        self.assertEqual(self._check(src), [])

    def test_unrecognised_status_is_not_compared_to_a_default(self):
        """`unknown` is not `none` — an unreadable status never triggers PSA002.
        (A free-text one is read by its words and compared as stated; see
        [test_free_text_no_constant_spells_is_compared_by_its_words].)"""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван", '
            "status=NO_SUCH_STATUS))",
        )
        self.assertEqual(self._check(src), [])

    # --- PSA003: newborn with an adult role ---

    def test_child_with_adult_role_flagged(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван", '
            "status=MANILOV_KF_PEASANT_MALE))",
        )
        self.assertEqual(self._codes(src), ["PSA003"])

    def test_child_with_adult_role_is_offered_the_child_form(self):
        src = _births(
            '    birth(1, Gender.FEMALE, father=person("Петр", '
            'status=YASAK_PEASANT_MALE), child=person("Анна", '
            "status=YASAK_PEASANT_FEMALE))",
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[PSA003] Новорождённой (Анна) проставлен взрослый статус "
                      "«ясачная крестьянка» — нужна детская форма, например "
                      "«ясачная крестьянская дочь» (YASAK_PEASANT_DAUGHTER).", errors[0])

    def test_child_with_child_role_ok(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван", '
            "status=MANILOV_KF_PEASANT_SON))",
        )
        self.assertEqual(self._check(src), [])

    def test_deceased_with_adult_role_not_flagged(self):
        """Births only — a deceased may legitimately be an adult."""
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=MANILOV_KF_PEASANT_MALE), age=40, relatives=[relative(person("Петр", '
            "status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)])",
        )
        self.assertEqual(self._check(src), [])

    # --- misc ---

    def test_positional_status_arg_is_read(self):
        # person(first, patr, last, first_m, patr_m, last_m, residence, status)
        positional = 'person("Иван", "", "", "", "", "", "", YASAK_PEASANT_SON)'
        src = _deaths(
            f"    death(1, Gender.MALE, 5, 6, deceased={positional}, age=4, "
            'relatives=[relative(person("Петр", status=MANILOV_KF_PEASANT_MALE), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_relatives_list_form_on_deaths(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            'status=YASAK_PEASANT_SON), age=4, '
            'relatives=[relative(person("Петр", status=MANILOV_KF_PEASANT_MALE), '
            "Relationship.FATHER)])",
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    # --- the book's own words: DEFAULTS by name, the file's constants ---

    def test_defaults_bound_by_name_are_read(self):
        """`defaults=DEFAULTS` — every Глуповы Горы book — is the book's
        default as much as one written in the call."""
        src = (
            "DEFAULTS = RecordDefaults(status_male=YASAK_PEASANT_MALE, "
            "status_female=YASAK_PEASANT_FEMALE)\n"
            'birth_records("a", "f", "i", "c", "Горюхино", "Церковь", 1830,\n'
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), mother=person("Мария")),\n'
            "    defaults=DEFAULTS)\n"
        )
        self.assertEqual(self._codes(src), ["PSA002"])

    def test_a_status_constant_the_file_defines_is_read_as_its_words(self):
        src = (
            'TENTETNIKOV_PEASANT = "крестьянин вотчины Г-на Тентетникова"\n'
            + _deaths(
                '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
                'status=YASAK_PEASANT_SON), age=4, relatives=[relative(person("Петр", '
                "status=TENTETNIKOV_PEASANT), Relationship.FATHER)])")
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])
        self.assertIn("«крестьянин вотчины Г-на Тентетникова»", errors[0])

    def test_the_catalogs_nozdrev_constants_need_no_file_definition(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", status=NOZDREV_PEASANT), '
            'mother=person("Мария"))',
            defaults="status_male=PEASANT_MALE, status_female=PEASANT_FEMALE, "
                     "status_mother=NOZDREV_PEASANT_WIFE",
        )
        self.assertEqual(self._check(src), [])

    def test_a_name_the_file_binds_shadows_the_catalogs(self):
        """As when Python runs the file: the file's own NOZDREV_PEASANT wins
        over the one `verso.ru.domain.statuses` exports."""
        src = (
            'NOZDREV_PEASANT = "крестьянин вотчины Г.Г. Головлевых"\n'
            + _births(
                '    birth(1, Gender.MALE, father=person("Петр", status=NOZDREV_PEASANT), '
                'mother=person("Мария", status=NOZDREV_PEASANT_WIFE))')
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_a_file_constant_spelling_a_statuses_constant_is_that_constant(self):
        src = (
            'MINE = "ясачный крестьянин"\n'
            + _births(
                '    birth(1, Gender.MALE, father=person("Петр", status=MINE), '
                'mother=person("Мария", status=MANILOV_KF_LEGAL_WIFE))')
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA001", errors[0])
        self.assertIn("«ясачный крестьянин»", errors[0])

    # --- «вотчины X» names an owner ---

    def test_two_owners_after_votchiny_contradict(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин вотчины Г-на Ноздрева"), mother=person("Мария", '
            'status="жена крестьянина вотчины Г.Г. Головлевых"))',
        )
        self.assertEqual(self._codes(src), ["PSA001"])

    def test_one_owner_under_two_honorifics_agrees(self):
        """«Г-на Ноздрева» and «дворянина А. Р. Ноздрева» are one owner: the
        owner is the surname closing the phrase, the rest is honorific."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин вотчины Г-на Ноздрева"), mother=person("Мария", '
            'status="жена крестьянина вотчины дворянина А. Р. Ноздрева"))',
        )
        self.assertEqual(self._check(src), [])

    def test_otchiny_names_an_owner_too(self):
        """The 1850s write «отчины Гг. Головлевых» — the same owner, one letter less."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин отчины Гг. Тентетниковых"), mother=person("Мария"))',
            defaults="status_male=PEASANT_MALE, status_female=PEASANT_FEMALE",
        )
        self.assertEqual(self._codes(src), ["PSA004"])

    def test_the_golovlev_wordings_are_one_estate(self):
        """«детей», the estate's земской, its peasant — one family."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", status=GOLOVLEV_ZEMSKOY), '
            'mother=person("Мария", status=GOLOVLEV_CHILDREN_ZEMSKOY_WIFE), '
            'child=person("Иван", status=GOLOVLEV_PEASANT))',
        )
        self.assertEqual(self._codes(src), ["PSA003"])

    def test_votchina_owner_agrees_with_the_same_pomeshchik(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status="крестьянин помещика Ивана Родионовича Ноздрева"), '
            'mother=person("Мария", status="жена крестьянина вотчины Г-на Ноздрева"))',
        )
        self.assertEqual(self._check(src), [])

    # --- PSA004: a spouse left on a default that names no estate ---

    _BARE = "status_male=PEASANT_MALE, status_female=PEASANT_FEMALE"

    def test_wife_on_a_bare_default_beside_an_owners_peasant_flagged(self):
        """The Глуповы Горы case: «крестьянка» beside «крестьянин вотчины
        Г-на Ноздрева» — nothing derives a wife's estate."""
        src = (
            'TENTETNIKOV_PEASANT = "крестьянин вотчины Г-на Тентетникова"\n'
            + _births(
                '    birth(1, Gender.MALE, father=person("Петр", '
                'status=TENTETNIKOV_PEASANT), mother=person("Мария"))',
                defaults=self._BARE)
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA004", errors[0])
        self.assertIn("просто «крестьянка»", errors[0])
        self.assertIn("«крестьянин вотчины Г-на Тентетникова»", errors[0])

    def test_status_mother_naming_the_owner_settles_it(self):
        src = (
            'TENTETNIKOV_PEASANT = "крестьянин вотчины Г-на Тентетникова"\n'
            'TENTETNIKOV_PEASANT_WIFE = "жена крестьянина вотчины Г-на Тентетникова"\n'
            + _births(
                '    birth(1, Gender.MALE, father=person("Петр", '
                'status=TENTETNIKOV_PEASANT), mother=person("Мария"))',
                defaults=self._BARE + ", status_mother=TENTETNIKOV_PEASANT_WIFE")
        )
        self.assertEqual(self._check(src), [])

    def test_wife_on_a_bare_default_beside_a_qualified_constant_flagged(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), mother=person("Мария"))',
            defaults=self._BARE,
        )
        self.assertEqual(self._codes(src), ["PSA004"])

    def test_husband_on_a_bare_default_beside_a_qualified_wife_flagged(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр"), '
            'mother=person("Мария", status=MANILOV_KF_LEGAL_WIFE))',
            defaults=self._BARE,
        )
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PSA004", errors[0])
        self.assertIn("PEASANT_MALE", errors[0])

    def test_a_burial_reads_as_a_sentence(self):
        """A burial as the review page refused it: the deceased styled
        «казенная крестьянка», her husband left on the book's bare default.
        The finding names both, in their words, and offers the fix."""
        src = _deaths(
            '    death(5, Gender.FEMALE, 9, 11, deceased=person("Авдотья", '
            '"Ильина", residence="Горелово", status=KAZENNYJ_PEASANT_FEMALE), '
            'age=31, relatives=[relative(person("Макаръ", "Лукинъ"), '
            "Relationship.HUSBAND)])",
            defaults=self._BARE)
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(
            "[PSA004] У мужа (Макаръ Лукинъ) сословие не указано — по умолчанию "
            "книги он просто «крестьянин», а умершая (Авдотья Ильина) — "
            "«казенная крестьянка». У супругов одно сословие: укажите мужу "
            "«казенный крестьянин» (KAZENNYJ_PEASANT_MALE).",
            errors[0].split(": ", 1)[1])

    def test_a_silent_mother_is_offered_her_husbands_estate_as_his_wife(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", status=NOZDREV_PEASANT), '
            'mother=person("Мария"))',
            defaults=self._BARE)
        errors = self._check(src)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("укажите жене «жена крестьянина вотчины г-на Ноздрева» "
                      "(NOZDREV_PEASANT_WIFE) — или status_mother= в DEFAULTS", errors[0])

    def test_deceased_wife_on_a_bare_default_flagged(self):
        src = (
            'TENTETNIKOV_PEASANT = "крестьянин вотчины Г-на Тентетникова"\n'
            + _deaths(
                '    death(1, Gender.FEMALE, 5, 6, deceased=person("Анфиса"), age=27, '
                'relatives=[relative(person("Тимофей", status=TENTETNIKOV_PEASANT), '
                "Relationship.HUSBAND)])",
                defaults=self._BARE)
        )
        self.assertEqual(self._codes(src), ["PSA004"])

    def test_a_child_on_a_bare_default_is_not_psa004(self):
        """Under-specification is harmless across generations — the rule is
        about one marriage."""
        src = (
            'TENTETNIKOV_PEASANT = "крестьянин вотчины Г-на Тентетникова"\n'
            + _births(
                '    birth(1, Gender.MALE, father=person("Петр", '
                'status=TENTETNIKOV_PEASANT), child=person("Иван"))',
                defaults=self._BARE)
        )
        self.assertEqual(self._check(src), [])

    def test_soldiers_wife_on_a_bare_default_is_exempt(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", status=SOLDIER), '
            'mother=person("Мария"))',
            defaults=self._BARE,
        )
        self.assertEqual(self._check(src), [])

    def test_both_spouses_on_the_default_say_nothing(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр"), mother=person("Мария"))',
            defaults="status_male=MANILOV_KF_PEASANT_MALE, status_female=PEASANT_FEMALE",
        )
        self.assertEqual(self._check(src), [])

    # --- highlight spans (IDE underlines the token, not the whole line) ---

    def _spans(self, src: str) -> list[tuple[int, str | None]]:
        """[(line, highlighted text or None)] for each structured issue."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            issues = check_parent_status.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        lines = src.splitlines()
        out: list[tuple[int, str | None]] = []
        for i in issues:
            line = int(i["line"])  # type: ignore[arg-type]
            if "col" in i:
                out.append((line, lines[line - 1][int(i["col"]):int(i["end_col"])]))  # type: ignore[arg-type]
            else:
                out.append((line, None))
        return out

    def test_psa001_highlights_the_child_status_constant(self):
        src = _deaths(
            '    death(1, Gender.MALE, 5, 6, deceased=person("Иван", '
            "status=YASAK_PEASANT_SON), age=4, relatives=[relative(person(\"Петр\", "
            "status=MANILOV_KF_PEASANT_MALE), Relationship.FATHER)])",
        )
        self.assertEqual([s for _, s in self._spans(src)], ["YASAK_PEASANT_SON"])

    def test_psa002_highlights_the_person_missing_a_status(self):
        # MESHCHANIN father: out of derivation scope, so PSA002 still fires.
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MESHCHANIN), child=person("Иван"))',
        )
        self.assertEqual([s for _, s in self._spans(src)], ['person("Иван")'])

    def test_span_survives_cyrillic_earlier_on_the_line(self):
        """AST col_offset is a UTF-8 BYTE offset; it must be converted."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Пётр Михайлович", '
            'status=MESHCHANIN), child=person("Иван"))',
        )
        self.assertEqual([s for _, s in self._spans(src)], ['person("Иван")'])

    def test_multiline_person_falls_back_to_the_name(self):
        src = _births(
            "    birth(1, Gender.MALE,\n"
            '          father=person("Петр", status=MESHCHANIN),\n'
            '          child=person(\n              "Иван",\n          ))',
        )
        self.assertEqual([s for _, s in self._spans(src)], ['"Иван"'])

    def test_psa003_highlights_the_status_constant(self):
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MANILOV_KF_PEASANT_MALE), child=person("Иван", '
            "status=MANILOV_KF_PEASANT_MALE))",
        )
        self.assertEqual([s for _, s in self._spans(src)],
                         ["MANILOV_KF_PEASANT_MALE"])

    def test_structured_issues_are_errors(self):
        """Hard since the corpus reached 0 (2026-09-26): the IDE shows red,
        matching CI, which fails on any PSA finding."""
        src = _births(
            '    birth(1, Gender.MALE, father=person("Петр", '
            'status=MESHCHANIN), child=person("Иван"))',
        )
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write(src)
            f.close()
            issues = check_parent_status.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        self.assertEqual([i["level"] for i in issues], ["error"])

    def test_syntax_error_is_left_to_single_line_calls(self):
        """A half-typed IDE buffer must not produce one duplicate per linter —
        single_line_calls reports the SyntaxError once."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            f.write("birth(1, Gender.MALE,\n")
            f.close()
            issues = check_parent_status.check_file_structured(Path(f.name))
        finally:
            Path(f.name).unlink()
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
