import unittest

import corpus.statuses as cs
import verso.ru.domain.statuses as st
from verso.ru.domain.statuses import _child_index, child_status_for  # pyright: ignore[reportPrivateUsage]
from verso.ru.gender import Gender


class TestChildStatusFor(unittest.TestCase):
    # --- landlord estates ---

    def test_landlord_father_derives_son_and_daughter(self):
        self.assertEqual(
            child_status_for(str(cs.SOBAKEVICH_UK_PEASANT_MALE), Gender.MALE),
            cs.SOBAKEVICH_UK_PEASANT_SON)
        self.assertEqual(
            child_status_for(str(cs.SOBAKEVICH_UK_PEASANT_MALE), Gender.FEMALE),
            cs.SOBAKEVICH_UK_PEASANT_DAUGHTER)

    def test_colonel_variant_folds_onto_the_landlord(self):
        self.assertEqual(
            child_status_for(str(cs.SOBAKEVICH_ZP_COL_PEASANT_MALE), Gender.MALE),
            cs.SOBAKEVICH_ZP_PEASANT_SON)

    def test_any_adult_role_derives_including_legal_wife_and_girl(self):
        self.assertEqual(
            child_status_for(str(cs.MANILOV_KF_LEGAL_WIFE), Gender.FEMALE),
            cs.MANILOV_KF_PEASANT_DAUGHTER)
        self.assertEqual(
            child_status_for(str(st.YASAK_PEASANT_GIRL), Gender.MALE),
            st.YASAK_PEASANT_SON)

    def test_glupovy_gory_owners_derive_their_serfs_children(self):
        """Until 2026-10-03 the catalog held no child of a «вотчины …» estate, so
        a Головлев serf's newborn or buried child fell to the book's bare
        «крестьянин» — 77 children, 17 of them burials on Geni."""
        for parent, son, daughter in (
                (cs.NOZDREV_PEASANT, cs.NOZDREV_PEASANT_SON, cs.NOZDREV_PEASANT_DAUGHTER),
                (cs.NOZDREV_PEASANT_WIFE, cs.NOZDREV_PEASANT_SON, cs.NOZDREV_PEASANT_DAUGHTER),
                (cs.GOLOVLEV_PEASANT, cs.GOLOVLEV_PEASANT_SON, cs.GOLOVLEV_PEASANT_DAUGHTER),
                (cs.GOLOVLEV_PEASANT_WIFE, cs.GOLOVLEV_PEASANT_SON, cs.GOLOVLEV_PEASANT_DAUGHTER),
                (cs.GOLOVLEV_PEASANT_LEGAL_WIFE, cs.GOLOVLEV_PEASANT_SON, cs.GOLOVLEV_PEASANT_DAUGHTER),
                (cs.GOLOVLEV_PEASANT_SPOUSE, cs.GOLOVLEV_PEASANT_SON, cs.GOLOVLEV_PEASANT_DAUGHTER)):
            self.assertEqual(son, child_status_for(str(parent), Gender.MALE), parent)
            self.assertEqual(daughter, child_status_for(str(parent), Gender.FEMALE), parent)

    def test_a_zemskoys_child_is_his_estates_peasant_child(self):
        """The земской is the serfs' own elected head; a приказчик is not
        presumed one, and his child derives nothing."""
        for zemskoy in (cs.GOLOVLEV_ZEMSKOY, cs.GOLOVLEV_ZEMSKOY_WIFE,
                        cs.GOLOVLEV_CHILDREN_ZEMSKOY, cs.GOLOVLEV_CHILDREN_ZEMSKOY_WIFE):
            self.assertEqual(cs.GOLOVLEV_PEASANT_SON,
                             child_status_for(str(zemskoy), Gender.MALE), zemskoy)
        self.assertIsNone(child_status_for(str(cs.GOLOVLEV_STEWARD), Gender.MALE))

    # --- generic peasant families ---

    def test_generic_peasant_estates(self):
        self.assertEqual(child_status_for(str(st.YASAK_PEASANT_MALE), Gender.FEMALE),
                         st.YASAK_PEASANT_DAUGHTER)
        self.assertEqual(child_status_for(str(st.KAZENNYJ_PEASANT_MALE), Gender.MALE),
                         st.KAZENNYJ_PEASANT_SON)
        self.assertEqual(child_status_for(str(st.ECON_PEASANT_MALE), Gender.MALE),
                         st.ECON_PEASANT_SON)
        self.assertEqual(child_status_for(str(st.PEASANT_MALE), Gender.FEMALE),
                         st.PEASANT_DAUGHTER)

    def test_state_peasants_derive_a_state_peasant_child(self):
        """As the казённые and экономические do: «государственный крестьянский
        сын» / «государственная крестьянская дочь», from either name the catalog
        gives the estate, from a wife's status, and from the words written as
        free text."""
        for parent in (st.STATE_PEASANT_MALE, st.STATE_PEASANT_FEMALE,
                       st.GOSUDARSTVENNYJ_PEASANT_MALE, st.GOSUDARSTVENNYJ_PEASANT_FEMALE,
                       st.STATE_PEASANT_WIFE, st.STATE_PEASANT_LEGAL_WIFE):
            for words in (parent, str(parent)):
                self.assertEqual(st.STATE_PEASANT_SON,
                                 child_status_for(words, Gender.MALE), parent)
                self.assertEqual(st.STATE_PEASANT_DAUGHTER,
                                 child_status_for(words, Gender.FEMALE), parent)
        self.assertEqual("жена из государственных крестьян", str(st.STATE_PEASANT_WIFE))
        self.assertEqual("законная жена государственного крестьянина",
                         str(st.STATE_PEASANT_LEGAL_WIFE))

    def test_post_reform_peasants_derive_a_peasant_child(self):
        """A временнообязанный and a крестьянин собственник are stages of land
        tenure, not estates: the child is a plain крестьянский сын/дочь — as
        the catalog constant and as the string the DSL may still write."""
        for parent in (st.TEMP_OBLIGED_PEASANT_MALE, st.PROPRIETOR_PEASANT_MALE):
            for words in (parent, str(parent)):
                self.assertEqual(st.PEASANT_SON, child_status_for(words, Gender.MALE), parent)
                self.assertEqual(st.PEASANT_DAUGHTER,
                                 child_status_for(words, Gender.FEMALE), parent)

    # --- soldiers ---

    def test_soldier_father_derives_soldier_child(self):
        self.assertEqual(child_status_for(str(st.SOLDIER), Gender.MALE),
                         st.SOLDIER_SON)
        self.assertEqual(child_status_for(str(st.SOLDIER), Gender.FEMALE),
                         st.SOLDIER_DAUGHTER)

    def test_retired_soldier_father_derives_soldier_child(self):
        """An отставной солдат's child is a солдатский сын / солдатская дочь,
        by the constant and by its words alike."""
        for words in (st.RETIRED_SOLDIER, str(st.RETIRED_SOLDIER)):
            self.assertEqual(child_status_for(words, Gender.MALE), st.SOLDIER_SON)
            self.assertEqual(child_status_for(words, Gender.FEMALE),
                             st.SOLDIER_DAUGHTER)

    def test_soldier_wife_mothers_derive_soldier_children(self):
        """A soldier's wife's child is a солдатский сын whatever HER estate —
        the SOLDIER_WIFE-role override, incl. «ясачная солдатская жена» and
        «солдатская жена из крестьян помещицы …» that name-split to peasant
        estates."""
        for mother in (st.SOLDIER_WIFE, st.SOLDIER_SPOUSE, st.SOLDIER_WIDOW,
                       st.YASAK_SOLDIER_WIFE, cs.MANILOV_LK_SOLDIER_WIFE):
            self.assertEqual(child_status_for(str(mother), Gender.MALE),
                             st.SOLDIER_SON, mother)

    # --- out of scope ---

    def test_non_derivable_estates_return_none(self):
        for parent in (st.DYACHOK, st.PRIEST, st.MERCHANT, st.MESHCHANIN,
                       st.LANDLORD, cs.MANILOV_SP_DVOROVY,
                       st.PRIVATE_SOLDIER, st.BUDNY_PEASANT, st.MAIDEN, st.WIDOW):
            self.assertIsNone(child_status_for(str(parent), Gender.MALE), parent)

    def test_unknown_text_and_none_inputs(self):
        self.assertIsNone(child_status_for("крестьянин помещика Кузьмы Тентетникова",
                                           Gender.MALE))
        self.assertIsNone(child_status_for(None, Gender.MALE))
        self.assertIsNone(child_status_for(str(st.YASAK_PEASANT_MALE), None))

    # --- index consistency ---

    def test_every_indexed_estate_has_both_child_forms(self):
        """Derivation must never be gender-lopsided: if an estate derives a
        son it must also derive a daughter, and vice versa."""
        male_texts = {t for (t, g) in _child_index() if g == Gender.MALE}
        female_texts = {t for (t, g) in _child_index() if g == Gender.FEMALE}
        self.assertEqual(male_texts, female_texts)

    def test_new_child_constants_follow_the_male_form_wording(self):
        """Each landlord child form is the mechanical transform of its estate's
        _MALE text: «крестьянин X» → «крестьянский сын/крестьянская дочь X»."""
        consts = dict(st.catalog())      # the library's and the corpus's
        checked = 0
        for name, male in consts.items():
            if not name.endswith("_PEASANT_MALE") or not str(male).startswith("крестьянин "):
                continue
            owner = str(male)[len("крестьянин "):]
            son = consts.get(name[:-len("MALE")] + "SON")
            daughter = consts.get(name[:-len("MALE")] + "DAUGHTER")
            if son is not None:
                self.assertEqual(str(son), f"крестьянский сын {owner}", name)
                checked += 1
            if daughter is not None:
                self.assertEqual(str(daughter), f"крестьянская дочь {owner}", name)
                checked += 1
        self.assertGreaterEqual(checked, 12)  # every pair the synthetic corpus holds


if __name__ == "__main__":
    unittest.main()
