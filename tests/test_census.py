import unittest
from calendar import Month

from verso.ru.dsl.records.census import CensusMember, CensusRole, census_records, member, household, ROLE_GENDER
from verso.ru.gender import Gender
from verso.ru.domain import RecordDefaults, person


def _make_member(number, name, patr=None, role=CensusRole.SON, age=10, ref_member=None, record_number=None, hidden=False):
    p = person(name, patr) if patr else person(name)
    return member(number, p, role, ref_member=ref_member, age=age, record_number=record_number, hidden=hidden)


class TestFosterChild(unittest.TestCase):
    """A FOSTER_SON/FOSTER_DAUGHTER member (приёмыш) is recorded in the household
    but has NO biological parent among its members, so `_resolve_parent_ref`
    returns None — no biological parent-union is emitted. Without this the foster
    child is linked as the head's biological child (flagged by age-conflicts as
    "father at 9")."""

    def test_foster_member_has_no_parent_ref(self):
        from verso.ru.targets.geni.translator.census_resolvers import _resolve_parent_ref
        head = member(1, person("Нилъ", "Игнатьевъ", "Брюквинъ"), CensusRole.HEAD, age=27)
        foster = member(2, person("Фома", "Андреевъ"), CensusRole.FOSTER_SON, ref_member=1,
                        age=18, comment="приемыш Нила Игнатьева")
        members = {1: head, 2: foster}
        self.assertIsNone(_resolve_parent_ref(foster, members))

    def test_non_foster_son_still_links(self):
        from verso.ru.targets.geni.translator.census_resolvers import _resolve_parent_ref
        head = member(1, person("Нилъ", "Игнатьевъ"), CensusRole.HEAD, age=40)
        son = member(2, person("Иванъ"), CensusRole.SON, ref_member=1, age=15)
        members = {1: head, 2: son}
        self.assertEqual(_resolve_parent_ref(son, members), 1)

    def test_foster_overrides_explicit_parent_member(self):
        from verso.ru.targets.geni.translator.census_resolvers import _resolve_parent_ref
        foster = member(3, person("Сидоръ"), CensusRole.FOSTER_SON, parent_member=1, age=5)
        self.assertIsNone(_resolve_parent_ref(foster, {}))


class TestCensusHouseholdPatronymicDerivation(unittest.TestCase):

    def test_son_derives_patronymic_from_head(self):
        hh = household(None, _make_member(1, "Трофим", "Тарасов", role=CensusRole.HEAD, age=43),
                       _make_member(2, "Михаил", role=CensusRole.SON, age=10))
        son = hh.members[1]
        self.assertEqual(son.person.patr_orig, "Трофимов")
        self.assertEqual(son.person.patr_old, "Трофимов")
        self.assertEqual(son.person.patr_modern, "Трофимович")

    def test_daughter_derives_patronymic_from_head(self):
        hh = household(None, _make_member(1, "Иван", "Петров", role=CensusRole.HEAD, age=40),
                       _make_member(2, "Анна", role=CensusRole.DAUGHTER, age=8))
        daughter = hh.members[1]
        self.assertEqual(daughter.person.patr_orig, "Иванова")
        self.assertEqual(daughter.person.patr_old, "Иванова")
        self.assertEqual(daughter.person.patr_modern, "Ивановна")

    def test_grandson_derives_patronymic_from_ref_member(self):
        hh = household(None, _make_member(1, "Игнатий", "Леонтьев", role=CensusRole.HEAD, age=57),
                       _make_member(2, "Тихон", role=CensusRole.SON, age=28),
                       _make_member(3, "Дмитрий", role=CensusRole.GRANDSON, age=8, ref_member=2))
        grandson = hh.members[2]
        self.assertEqual(grandson.person.patr_orig, "Тихонов")
        self.assertEqual(grandson.person.patr_old, "Тихонов")
        self.assertEqual(grandson.person.patr_modern, "Тихонович")

    def test_granddaughter_derives_patronymic_from_ref_member(self):
        hh = household(None, _make_member(1, "Игнатий", "Леонтьев", role=CensusRole.HEAD, age=57),
                       _make_member(2, "Тихон", role=CensusRole.SON, age=28),
                       _make_member(3, "Мария", role=CensusRole.GRANDDAUGHTER, age=5, ref_member=2))
        granddaughter = hh.members[2]
        self.assertEqual(granddaughter.person.patr_orig, "Тихонова")
        self.assertEqual(granddaughter.person.patr_old, "Тихонова")
        self.assertEqual(granddaughter.person.patr_modern, "Тихоновна")

    def test_explicit_patronymic_not_overwritten(self):
        hh = household(None, _make_member(1, "Иван", "Петров", role=CensusRole.HEAD, age=40),
                       _make_member(2, "Михаил", "Максимов", role=CensusRole.SON, age=15))
        son = hh.members[1]
        self.assertEqual(son.person.patr_orig, "Максимов")

    def test_non_child_roles_not_affected(self):
        hh = household(None, _make_member(1, "Иван", "Петров", role=CensusRole.HEAD, age=40),
                       _make_member(2, "Федор", "Ипатов", role=CensusRole.SON_IN_LAW, age=20),
                       _make_member(3, "Василий", "Кузьмин", role=CensusRole.BROTHER, age=35))
        son_in_law = hh.members[1]
        brother = hh.members[2]
        self.assertEqual(son_in_law.person.patr_orig, "Ипатов")
        self.assertEqual(brother.person.patr_orig, "Кузьмин")

    def test_stepson_not_derived(self):
        hh = household(None, _make_member(1, "Иван", "Петров", role=CensusRole.HEAD, age=40),
                       _make_member(2, "Алексей", role=CensusRole.STEPSON, age=12))
        stepson = hh.members[1]
        self.assertFalse(stepson.person.patr_orig)

    def test_no_head_and_no_ref_member_skips(self):
        # Household with only sons and no HEAD — should not derive
        hh = household(None, _make_member(1, "Михаил", role=CensusRole.SON, age=10),
                       _make_member(2, "Алексей", role=CensusRole.SON, age=8))
        for m in hh.members:
            self.assertFalse(m.person.patr_orig)

    def test_female_head_does_not_yield_matronymic(self):
        """Russian historical records use patronymics derived from the
        FATHER's name, not matronymics. When the resolved parent (head
        or ref_member) is female (e.g. a widowed female head of
        household), skip patronymic derivation entirely — the child's
        father is unknown, so leaving the patronymic blank is more
        accurate than fabricating "Матрёнична" from the mother's name.

        Regression: the daughter of a widowed female head was rendered as
        "Анисья Матрёнична" by the new generator. Legacy emitted just
        "Анисья"."""
        hh = household(None, _make_member(1, "Матрена", "Лукина",
                                          role=CensusRole.HEAD, age=55), _make_member(2, "Анисья",
                                                                                      role=CensusRole.DAUGHTER, age=26))
        daughter = hh.members[1]
        self.assertFalse(daughter.person.patr_orig)
        self.assertFalse(daughter.person.patr_modern)

    def test_female_ref_member_does_not_yield_matronymic(self):
        """Same rule applies when the parent is resolved via
        `ref_member=` — if that ref points at a female member, skip
        derivation."""
        hh = household(None, _make_member(1, "Иван", "Петров",
                                          role=CensusRole.HEAD, age=60), _make_member(2, "Анисья", "Лукина",
                                                                                      role=CensusRole.DAUGHTER_IN_LAW,
                                                                                      age=38), _make_member(3, "Агафья",
                                                                                                            role=CensusRole.DAUGHTER,
                                                                                                            age=15,
                                                                                                            ref_member=2))
        granddaughter_via_dil = hh.members[2]
        self.assertFalse(granddaughter_via_dil.person.patr_orig)
        self.assertFalse(granddaughter_via_dil.person.patr_modern)

    def test_adopted_child_does_not_derive_patronymic(self):
        """A `comment="роль в оригинале: приемная дочь; ..."` (or
        `приемный сын`) marks an ADOPTED child — the listed `ref_member`
        is the foster parent, not the biological father. Russian
        patronymics derive from the biological father's name; deriving
        one from the adoptive father misrepresents lineage. Skip
        derivation when the role override carries an `приемн` marker.

        Regression: an adopted daughter of the son Харитон was rendered as
        'Мария Харитоновна' by the new generator. Legacy emitted just
        'Мария'."""
        hh = household(None, _make_member(1, "Марфа", "Прохорова",
                                          role=CensusRole.HEAD, age=62), _make_member(2, "Харитон", "Андреев",
                                                                                      role=CensusRole.SON, age=40))
        # Manually add an adopted daughter pointing at son #2
        adopted = member(4, person("Марья"), CensusRole.DAUGHTER, ref_member=2, age=7,
                         comment="роль в оригинале: приемная дочь; ФИО в документе: Марья")
        hh = household(None, *hh.members, adopted)
        adopted_resolved = hh.members[2]
        self.assertFalse(adopted_resolved.person.patr_orig)
        self.assertFalse(adopted_resolved.person.patr_modern)

    def test_caller_person_not_mutated(self):
        # Deep copy means original Person is unchanged
        p = person("Михаил")
        original_patr = p.patr_orig
        hh = household(None, _make_member(1, "Иван", "Петров", role=CensusRole.HEAD, age=40),
                       member(2, p, CensusRole.SON, age=10))
        self.assertEqual(p.patr_orig, original_patr)
        self.assertEqual(hh.members[1].person.patr_orig, "Иванов")
        self.assertEqual(hh.members[1].person.patr_old, "Иванов")
        self.assertEqual(hh.members[1].person.patr_modern, "Иванович")

    def test_hidden_member_skips_patronymic_derivation(self):
        """A hidden member (string `record_number=`, e.g. `"3-11"`) is a
        placeholder ancestor used purely for genealogy chains. Even if
        the CSV records their relationship as `сын [#]1`, the
        translator must NOT auto-derive a patronymic from HEAD's name
        — legacy emitted only `first_name` for these placeholders.

        Regression: a hidden "son" in the CSV who is really the *father*
        of another member. Legacy left him with only `first_name`; the new
        generator was emitting `middle_name = "Потапович"` (treating him
        as Потап's son)."""
        hh = household(None, _make_member(1, "Потап", "Иванов", role=CensusRole.HEAD, age=85),
                       _make_member(2, "Антон", role=CensusRole.SON, age="?",
                                    hidden=True))
        hidden = hh.members[1]
        self.assertFalse(hidden.person.patr_orig)
        self.assertFalse(hidden.person.patr_old)
        self.assertFalse(hidden.person.patr_modern)

    def test_grandson_without_ref_member_skips_patronymic(self):
        """A GRANDSON's father is one of HEAD's children, not HEAD
        himself. Without an explicit `ref_member` pointing at the
        actual parent, the patronymic is genuinely unknown — DO NOT
        fall back to HEAD's name (that would make the grandson HEAD's
        son, not grandson). Regression: legacy left a grandson's
        patronymic blank; the new generator was emitting the head's
        `Петрович`."""
        hh = household(None, _make_member(1, "Петр", "Миронов", role=CensusRole.HEAD, age=50),
                       _make_member(2, "Сергей", role=CensusRole.GRANDSON, age=5))
        grandson = hh.members[1]
        self.assertFalse(grandson.person.patr_orig)
        self.assertFalse(grandson.person.patr_old)
        self.assertFalse(grandson.person.patr_modern)


class TestCensusHouseholdSurnameDerivation(unittest.TestCase):

    def test_wife_derives_married_surname_from_head(self):
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, person("Фекла", "Сидорова"), CensusRole.WIFE, age=38))
        wife = hh.members[1]
        self.assertEqual(wife.person.last_name_modern, "Индюшева")
        self.assertIsNone(wife.person.last_name)          # as-written stays empty
        self.assertFalse(wife.person.last_name_in_book)

    def test_son_derives_surname_from_head(self):
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, person("Иван"), CensusRole.SON, age=16))
        son = hh.members[1]
        self.assertEqual(son.person.last_name_modern, "Индюшев")
        self.assertIsNone(son.person.last_name)

    def test_daughter_derives_maiden_surname_from_head(self):
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, person("Анна"), CensusRole.DAUGHTER, age=8))
        daughter = hh.members[1]
        self.assertEqual(daughter.person.birth_last_name_modern, "Индюшева")
        self.assertIsNone(daughter.person.last_name)
        self.assertIsNone(daughter.person.last_name_modern)  # maiden, not current

    def test_daughter_in_law_derives_married_surname_from_husband(self):
        hh = household(None, member(1, person("Григорий", "Иванов", "Индюшев"), CensusRole.HEAD, age=60),
                       member(2, person("Иван", last_name_orig="Индюшев"), CensusRole.SON, age=30),
                       member(3, person("Татьяна", "Фокина"), CensusRole.DAUGHTER_IN_LAW, ref_member=2, age=22))
        dil = hh.members[2]
        self.assertEqual(dil.person.last_name_modern, "Индюшева")
        self.assertFalse(dil.person.last_name_in_book)

    def test_grandson_derives_surname_from_ref_member(self):
        hh = household(None, member(1, person("Игнатий", "Леонтьев", "Индюшев"), CensusRole.HEAD, age=57),
                       member(2, person("Иван", last_name_orig="Индюшев"), CensusRole.SON, age=26),
                       member(3, person("Дмитрий"), CensusRole.GRANDSON, ref_member=2, age=8))
        grandson = hh.members[2]
        self.assertEqual(grandson.person.last_name_modern, "Индюшев")

    def test_chained_son_then_daughter_in_law(self):
        """Son inherits HEAD's surname, then a daughter-in-law referencing
        that son inherits the (now-derived) surname feminized."""
        hh = household(None, member(1, person("Григорий", "Иванов", "Индюшев"), CensusRole.HEAD, age=60),
                       member(2, person("Иван"), CensusRole.SON, age=30),
                       member(3, person("Татьяна", "Фокина"), CensusRole.DAUGHTER_IN_LAW, ref_member=2, age=22))
        son = hh.members[1]
        dil = hh.members[2]
        self.assertEqual(son.person.last_name_modern, "Индюшев")
        self.assertEqual(dil.person.last_name_modern, "Индюшева")

    def test_explicit_surname_not_overwritten(self):
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, person("Фекла", "Сидорова", "Иванова"), CensusRole.WIFE, age=38))
        wife = hh.members[1]
        self.assertEqual(wife.person.last_name, "Иванова")
        self.assertEqual(wife.person.last_name_modern, "Иванова")
        self.assertTrue(wife.person.last_name_in_book)

    def test_wife_maiden_name_coexists_with_derived_married_surname(self):
        """A wife given only her maiden name still derives the married
        surname from her husband; the two coexist (pattern #20936)."""
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, person("Фекла", "Сидорова", birth_last_name_modern_orth="Петрова"), CensusRole.WIFE,
                              age=38))
        wife = hh.members[1]
        self.assertEqual(wife.person.last_name_modern, "Индюшева")   # married, derived
        self.assertEqual(wife.person.birth_last_name_modern, "Петрова")  # maiden, kept

    def test_female_head_does_not_yield_surname(self):
        """A widowed female head can't masculinize for sons, so skip."""
        hh = household(None, member(1, person("Матрена", "Лукина", "Индюшева"), CensusRole.HEAD, age=55),
                       member(2, person("Михаил"), CensusRole.SON, age=20))
        son = hh.members[1]
        self.assertIsNone(son.person.last_name_modern)

    def test_grandson_without_ref_member_skips_surname(self):
        hh = household(None, member(1, person("Петр", "Миронов", "Индюшев"), CensusRole.HEAD, age=50),
                       member(2, person("Сергей"), CensusRole.GRANDSON, age=5))
        grandson = hh.members[1]
        self.assertIsNone(grandson.person.last_name_modern)

    def test_adopted_child_does_not_derive_surname(self):
        hh = household(None, member(1, person("Федот", "Ефимов", "Индюшев"), CensusRole.HEAD, age=50),
                       member(2, person("Марья"), CensusRole.DAUGHTER, age=7,
                              comment="роль в оригинале: приемная дочь; ФИО в документе: Марья"))
        adopted = hh.members[1]
        self.assertIsNone(adopted.person.birth_last_name_modern)

    def test_non_family_roles_not_affected(self):
        hh = household(None, member(1, person("Иван", "Петров", "Индюшев"), CensusRole.HEAD, age=40),
                       member(2, person("Василий", "Кузьмин"), CensusRole.BROTHER, age=35))
        brother = hh.members[1]
        self.assertIsNone(brother.person.last_name_modern)

    def test_caller_person_not_mutated(self):
        p = person("Фекла", "Сидорова")
        hh = household(None, member(1, person("Пахом", "Игнатьев", "Индюшев"), CensusRole.HEAD, age=47),
                       member(2, p, CensusRole.WIFE, age=38))
        self.assertIsNone(p.last_name_modern)                       # original untouched
        self.assertEqual(hh.members[1].person.last_name_modern, "Индюшева")


class TestCensusMemberGenderCheck(unittest.TestCase):

    def test_female_name_with_male_role_raises(self):
        with self.assertRaises(ValueError) as ctx:
            member(1, person("Анна"), CensusRole.SON, age=10)
        self.assertIn("Gender mismatch", str(ctx.exception))

    def test_male_name_with_female_role_raises(self):
        with self.assertRaises(ValueError) as ctx:
            member(1, person("Иван"), CensusRole.DAUGHTER, age=8)
        self.assertIn("Gender mismatch", str(ctx.exception))

    def test_male_name_with_wife_role_raises(self):
        with self.assertRaises(ValueError) as ctx:
            member(1, person("Иван"), CensusRole.WIFE, age=30)
        self.assertIn("Gender mismatch", str(ctx.exception))

    def test_female_name_with_son_in_law_role_raises(self):
        with self.assertRaises(ValueError) as ctx:
            member(1, person("Мария"), CensusRole.SON_IN_LAW, age=25)
        self.assertIn("Gender mismatch", str(ctx.exception))

    def test_correct_gender_does_not_raise(self):
        # These must all construct without error
        member(1, person("Иван"), CensusRole.SON, age=10)
        member(2, person("Мария"), CensusRole.DAUGHTER, age=8)
        member(3, person("Анна"), CensusRole.WIFE, age=30)
        member(4, person("Федор"), CensusRole.SON_IN_LAW, age=25)
        member(5, person("Иван"), CensusRole.GRANDSON, age=5)
        member(6, person("Мария"), CensusRole.GRANDDAUGHTER, age=4)

    def test_head_and_lodger_accept_any_gender(self):
        # HEAD and LODGER have no implied gender — both male and female names allowed
        member(1, person("Иван"), CensusRole.HEAD, age=45)
        member(2, person("Анна"), CensusRole.HEAD, age=45)
        member(3, person("Иван"), CensusRole.LODGER, age=30)
        member(4, person("Мария"), CensusRole.LODGER, age=30)

    def test_role_gender_mapping_is_complete(self):
        # Every role with an implied gender must map to one of the two Gender values
        for role, gender in ROLE_GENDER.items():
            self.assertIn(gender, (Gender.MALE, Gender.FEMALE),
                          f"ROLE_GENDER[{role}] has unexpected value {gender}")


class TestCensusRecordsFemalePreviousAge(unittest.TestCase):
    @staticmethod
    def _roll(wife_previous_age=None, **kwargs):
        hh = household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=45, previous_age=30),
                       member(2, person("Мария"), CensusRole.WIFE, ref_member=1, age=40,
                              previous_age=wife_previous_age))
        return census_records("A", "F", "I", "C", "V", 1795, hh, **kwargs)

    def test_unset_it_is_read_off_the_women(self):
        self.assertTrue(self._roll(wife_previous_age=25).states_female_previous_age())
        self.assertFalse(self._roll().states_female_previous_age())

    def test_a_mans_previous_age_says_nothing_of_the_womens(self):
        self.assertFalse(self._roll().states_female_previous_age())   # the head has one

    def test_written_it_wins(self):
        self.assertTrue(self._roll(female_previous_age=True).states_female_previous_age())
        self.assertFalse(self._roll(wife_previous_age=25, female_previous_age=False).states_female_previous_age())

    def test_it_changes_no_member(self):
        plain, flagged = self._roll(wife_previous_age=25), self._roll(wife_previous_age=25, female_previous_age=False)
        self.assertEqual([vars(m.person) for m in plain.households[0].members],
                         [vars(m.person) for m in flagged.households[0].members])


class TestCensusRecordsDefaults(unittest.TestCase):
    def test_defaults_populate_person_status_by_implied_gender(self):
        hh = household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=45),
                       member(2, person("Мария"), CensusRole.WIFE, age=40),
                       member(3, person("Семен"), CensusRole.SON, age=10),
                       member(4, person("Дарья"), CensusRole.DAUGHTER, age=8))
        cr = census_records(
            "A", "F", "I", "C", "V", 1834, hh,
            defaults=RecordDefaults(
                status_male="крестьянин помещицы Х",
                status_female="крестьянка помещицы Х",
            ),
        )
        members = cr.households[0].members
        # HEAD has no role-implied gender; default to male.
        self.assertEqual(members[0].person.status, "крестьянин помещицы Х")
        self.assertEqual(members[1].person.status, "крестьянка помещицы Х")
        self.assertEqual(members[2].person.status, "крестьянин помещицы Х")
        self.assertEqual(members[3].person.status, "крестьянка помещицы Х")

    def test_defaults_do_not_override_explicit_person_status(self):
        hh = household(None, member(1, person("Иван", status="дьячок"), CensusRole.HEAD, age=45))
        cr = census_records(
            "A", "F", "I", "C", "V", 1834, hh,
            defaults=RecordDefaults(
                status_male="крестьянин",
                status_female="крестьянка",
            ),
        )
        self.assertEqual(cr.households[0].members[0].person.status, "дьячок")

    def test_defaults_apply_residence_when_unset(self):
        # village always populates residence, but defaults.residence can
        # override when a DSL wants the residence to be different from village.
        hh = household(None, member(1, person("Иван"), CensusRole.HEAD, age=45))
        cr = census_records(
            "A", "F", "I", "C", "V", 1834, hh,
            defaults=RecordDefaults(residence="OtherPlace"),
        )
        # CensusRecords already set residence=village; defaults only fills
        # unset fields, so village wins.
        self.assertEqual(cr.households[0].members[0].person.residence, "V")

    def test_no_defaults_leaves_status_none(self):
        hh = household(None, member(1, person("Иван"), CensusRole.HEAD, age=45))
        cr = census_records("A", "F", "I", "C", "V", 1834, hh)
        self.assertIsNone(cr.households[0].members[0].person.status)


class TestCensusMemberStructuredFields(unittest.TestCase):
    """New typed kwargs on CensusMember / member() for first-class
    arrival/departure data. The translator will consume these in
    preference to comment-string parsing; here we just pin down the
    constructor API."""

    def test_defaults_are_none(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40)
        self.assertIsNone(m.destination)
        self.assertIsNone(m.arrival_year)
        self.assertIsNone(m.departure_year)
        self.assertIsNone(m.arrival_reason)
        self.assertIsNone(m.departure_reason)

    def test_structured_fields_are_stored_verbatim(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, destination="Дремотино",
                         arrival_year=1812, arrival_reason="вновь причисленный", departure_year=1830,
                         departure_reason="умер")
        self.assertEqual(m.destination, "Дремотино")
        self.assertEqual(m.arrival_year, 1812)
        self.assertEqual(m.departure_year, 1830)
        self.assertEqual(m.arrival_reason, "вновь причисленный")
        self.assertEqual(m.departure_reason, "умер")

    def test_member_factory_accepts_structured_fields(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, destination="Дремотино", arrival_year=1812,
                   arrival_reason="вновь причисленный", departure_year=1830, departure_reason="умер")
        self.assertEqual(m.destination, "Дремотино")
        self.assertEqual(m.arrival_year, 1812)
        self.assertEqual(m.departure_year, 1830)
        self.assertEqual(m.arrival_reason, "вновь причисленный")
        self.assertEqual(m.departure_reason, "умер")

    def test_structured_fields_do_not_affect_comment(self):
        # The caller's `comment=` string passes through untouched — no
        # auto-parse, no auto-synthesis from the structured fields.
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, destination="Дремотино", arrival_year=1812,
                   arrival_reason="вновь причисленный", departure_year=1830, departure_reason="умер",
                   comment="свободный текст")
        self.assertEqual(m.comment, "свободный текст")

        m2 = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, destination="Дремотино", arrival_year=1812,
                    arrival_reason="вновь причисленный")
        self.assertIsNone(m2.comment)

    def test_previous_age_default_is_none(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40)
        self.assertIsNone(m.previous_age)

    def test_previous_age_stored_verbatim(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, previous_age=30)
        self.assertEqual(m.previous_age, 30)

    def test_member_factory_accepts_previous_age(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, previous_age=30)
        self.assertEqual(m.previous_age, 30)

    def test_previous_age_does_not_affect_comment(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, previous_age=30, comment="свободный текст")
        self.assertEqual(m.comment, "свободный текст")

    def test_record_number_default_is_none(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40)
        self.assertIsNone(m.record_number)

    def test_record_number_stored_verbatim(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, record_number=12)
        self.assertEqual(m.record_number, 12)

    def test_member_factory_accepts_record_number(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, record_number=12)
        self.assertEqual(m.record_number, 12)

    def test_birth_date_fields_default_to_none(self):
        m = CensusMember(1, person("Иван", "Петров"), CensusRole.HEAD, age=40)
        self.assertIsNone(m.birth_day)
        self.assertIsNone(m.birth_month)
        self.assertIsNone(m.birth_year)

    def test_birth_date_fields_stored_verbatim(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=40, birth_day=10, birth_month=Month.JANUARY,
                   birth_year=1842)
        self.assertEqual((m.birth_day, m.birth_month, m.birth_year),
                         (10, Month.JANUARY, 1842))


class TestCensusRecordsAutoIncrementRecordNumber(unittest.TestCase):
    """`CensusRecords.__init__` auto-assigns `record_number` to every
    member whose DSL didn't specify one. The counter increments in
    DSL order across households, matching the legacy CSV's `№ п/п`
    sequence.

    Explicit kwargs override:
      - integer → use it AND reset the counter to that value (so
        subsequent auto-increments continue from there).
      - string  → preserve as-is (e.g. "2-7" for `#hidden` rows);
        counter does NOT advance.
    """

    def test_autoincrement_assigns_consecutive_integers(self):
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Мария"), CensusRole.WIFE, age=28),
                      member(3, person("Семен"), CensusRole.SON, age=5)),
            household(None, member(1, person("Петр", "Иванов"), CensusRole.HEAD, age=40),
                      member(2, person("Анна"), CensusRole.WIFE, age=38)),
        )
        h0, h1 = cr.households
        self.assertEqual(
            [m.record_number for m in h0.members], [1, 2, 3],
        )
        self.assertEqual(
            [m.record_number for m in h1.members], [4, 5],
        )

    def test_hidden_member_does_not_advance_counter(self):
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Мария"), CensusRole.WIFE, age=28),
                      member(3, person("Семен"), None, age="?", hidden=True)),
            household(None, member(1, person("Петр", "Иванов"), CensusRole.HEAD, age=40)),
        )
        h0, h1 = cr.households
        self.assertEqual(
            [m.record_number for m in h0.members], [1, 2, None],
        )
        # Counter did NOT advance over the hidden member;
        # h1's HEAD picks up where it would have without that row.
        self.assertEqual(h1.members[0].record_number, 3)

    def test_explicit_int_overrides_and_resets_counter(self):
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Мария"), CensusRole.WIFE, age=28, record_number=42),
                      member(3, person("Семен"), CensusRole.SON, age=5)),
        )
        h0 = cr.households[0]
        self.assertEqual(
            [m.record_number for m in h0.members], [1, 42, 43],
        )

    def test_mixed_explicit_and_implicit(self):
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Мария"), CensusRole.WIFE, age=28),
                      member(3, person("Семен"), None, age="?", hidden=True),
                      member(4, person("Дмитрий"), CensusRole.SON, age=10),
                      member(5, person("Анна"), None, age="?", hidden=True)),
        )
        h0 = cr.households[0]
        self.assertEqual(
            [m.record_number for m in h0.members],
            [1, 2, None, 3, None],
        )


class TestCensusMemberHiddenFlag(unittest.TestCase):
    """Explicit `hidden=True` flag on `member()` is the single canonical
    way to mark a member as a manually-added genealogy-chain placeholder.
    The `is_hidden()` helper returns True if and only if `hidden=True`
    was passed. Legacy sentinels (string `record_number="X-Y"` and
    comment starting with "Отсутствует в РС") are no longer supported."""

    def test_is_hidden_returns_false_by_default(self):
        m = member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30)
        self.assertFalse(m.is_hidden())

    def test_is_hidden_returns_true_when_hidden_kwarg_set(self):
        m = member(1, person("Семен"), None, age="?", hidden=True)
        self.assertTrue(m.is_hidden())

    def test_is_hidden_returns_true_with_hidden_flag(self):
        # Explicit hidden=True flag.
        m = member(1, person("Семен"), None, age="?", hidden=True)
        self.assertTrue(m.is_hidden())

    def test_is_hidden_with_hidden_flag_and_comment(self):
        # hidden=True with a comment (manual-add member): still hidden.
        m = member(1, person("Семен"), None, age="?", hidden=True,
                   comment="Отсутствует в РС 1834; персона добавлена вручную.")
        self.assertTrue(m.is_hidden())

    def test_hidden_flag_does_not_advance_record_counter(self):
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Семен"), None, age="?", hidden=True),
                      member(3, person("Дмитрий"), CensusRole.SON, age=10)),
        )
        h0 = cr.households[0]
        self.assertEqual(
            [m.record_number for m in h0.members],
            [1, None, 2],
        )

    def test_hidden_flag_keeps_explicit_int_record_number(self):
        # An explicit int `record_number=` on a hidden member is
        # preserved unchanged (no auto-increment).
        cr = census_records(
            "A", "F", "I", "C", "V", 1717,
            household(None, member(1, person("Иван", "Петров"), CensusRole.HEAD, age=30),
                      member(2, person("Семен"), None, age="?", record_number=42, hidden=True),
                      member(3, person("Дмитрий"), CensusRole.SON, age=10)),
        )
        h0 = cr.households[0]
        self.assertEqual(
            [m.record_number for m in h0.members],
            [1, 42, 2],
        )


class TestCensusBirthDateValidation(unittest.TestCase):
    """birth_month accepts only calendar.Month constants (aligning census with
    births/deaths/marriages); raw integers are no longer accepted. CensusMember
    still validates birth day/year ranges."""

    def test_birth_month_accepts_month_constant(self):
        m = member(2, person("Иван"), CensusRole.SON, age=20, birth_day=16, birth_month=Month.MAY, birth_year=1830)
        self.assertEqual(m.birth_month, Month.MAY)
        # Month is IntEnum: the stored value still compares equal to the int.
        self.assertEqual(m.birth_month, 5)

    def test_invalid_birth_day_raises(self):
        with self.assertRaises(ValueError):
            member(2, person("Иван"), CensusRole.SON, age=20, birth_day=40)

    def test_invalid_birth_year_raises(self):
        with self.assertRaises(ValueError):
            member(2, person("Иван"), CensusRole.SON, age=20, birth_year=99)

    def test_valid_birth_date_passes(self):
        m = member(2, person("Иван"), CensusRole.SON, age=20, birth_day=6, birth_month=Month.OCTOBER, birth_year=1856)
        self.assertEqual((m.birth_day, m.birth_month, m.birth_year),
                         (6, Month.OCTOBER, 1856))


if __name__ == "__main__":
    unittest.main()
