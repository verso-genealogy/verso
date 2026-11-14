"""What a household roll asserts, and on whose authority.

The roll is the one source that states a group — «оба во дворѣ N одной
ревизии» — and the only one whose entries are half book and half
reconstruction. Both are pinned here, because both are recovered downstream
today by parsing a res_name the translator minted.
"""
from __future__ import annotations

import re
import unittest
from calendar import Month

from verso.ru.domain import person
from verso.ru.dsl.records.census import (
    CONFESSION_LIST, CensusRole, census_records, household, member)
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.model import (
    AgedYears, ArrivedFrom, AssertionSet, BornOn, Derived, DiedOn, EnumeratedIn, FosterParentOf, KinOf, MovedTo, NameClaim, ParentOf, Persona, Retracted, SpouseOf, Stated, SurvivedUntil)



def _number(who: Persona) -> int:
    """A member's number, read off the persona's id (`…/household/5/member3`)."""
    return int(who.id.rpartition("/member")[2])

def _facts(*households, year: int = 1834, **kw) -> AssertionSet:
    recs = census_records("ГАТО", "12", "1", "1", "Тестовка", year,
                          *households, **kw)
    return AssertionSet(facts_from_census([(recs, "rs.py")], village="Тестовка"))


def _household(*members, **kw):
    return household(kw.pop("family_id", "7"), *members, **kw)


def _without_birth(outputs: dict[str, str]) -> dict[str, str]:
    """The emitted tree with every profile's `birth` block cut out."""
    return {name: re.sub(r"\n  birth = \{.*?\n  \}\n", "\n", text, flags=re.S)
            for name, text in outputs.items()}


HEAD = member(1, person("Евстафій", "Пахомовъ"), CensusRole.HEAD, age=54)


class BeingCountedIsAFact(unittest.TestCase):
    def test_every_listed_member_is_enumerated_in_the_household(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Настасья"), CensusRole.DAUGHTER, age=16),
            member(3, person("Настасья"), CensusRole.DAUGHTER, age=14)))
        listed = facts.of(EnumeratedIn)
        self.assertEqual(3, len(listed))
        self.assertEqual({("rs.py", "7", "??.??.1834")},
                         {a.payload for a in listed})

    def test_two_members_of_one_household_share_a_group(self):
        """The whole value of the predicate: the scribe enumerated them
        separately, so the source itself says there are two people."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Давыдъ"), CensusRole.SON, age=7),
            member(3, person("Давидъ"), CensusRole.SON, age=6)))
        groups = [a.payload for a in facts.of(EnumeratedIn)]
        self.assertEqual(3, len(groups))
        self.assertEqual(1, len(set(groups)))

    def test_two_households_of_one_roll_do_not(self):
        facts = _facts(_household(HEAD, family_id="7"),
                       _household(member(1, person("Сидоръ"), CensusRole.HEAD,
                                         age=40), family_id="8"))
        self.assertEqual({("rs.py", "7", "??.??.1834"),
                          ("rs.py", "8", "??.??.1834")},
                         {a.payload for a in facts.of(EnumeratedIn)})

    def test_an_unnumbered_household_is_counted(self):
        """The roll's own number when it has one, a running count otherwise —
        the same rule the generator applies, read from the roll rather than
        back out of a res_name."""
        facts = _facts(household(None, HEAD),
                       household(None, member(1, person("Сидоръ"),
                                              CensusRole.HEAD, age=40)))
        self.assertEqual({("rs.py", "1", "??.??.1834"),
                          ("rs.py", "2", "??.??.1834")},
                         {a.payload for a in facts.of(EnumeratedIn)})

    def test_a_confession_list_states_the_same_group(self):
        """A двор and a семья are one shape. Both regexes that recover a
        household from a res_name hardcode `_rs_`, so neither can see this."""
        facts = _facts(_household(HEAD), **CONFESSION_LIST)
        self.assertEqual([("rs.py", "7", "??.??.1834")],
                         [a.payload for a in facts.of(EnumeratedIn)])

    def test_an_unreviewed_household_asserts_nothing(self):
        """Transcribed, not yet checked against the scan: the rest of the
        pipeline emits nothing for it, and neither may this."""
        facts = _facts(_household(HEAD, reviewed=False))
        self.assertEqual((), facts.of(EnumeratedIn))
        self.assertEqual((), facts.of(NameClaim))


class BeingCountedIsNotBeingBorn(unittest.TestCase):
    def test_enumeration_yields_a_lower_bound_on_the_life(self):
        facts = _facts(_household(HEAD))
        alive = facts.of(SurvivedUntil)
        self.assertEqual(1, len(alive))
        self.assertEqual((1834, 1, 1), alive[0].date.earliest)

    def test_the_bound_stands_on_the_enumeration_that_supports_it(self):
        facts = _facts(_household(HEAD))
        basis = facts.of(SurvivedUntil)[0].basis
        assert isinstance(basis, Derived)
        self.assertEqual(1, len(basis.because))
        self.assertIsInstance(basis.because[0], EnumeratedIn)

    def test_the_roll_s_own_dead_were_not_alive_at_it(self):
        """A сказка lists who died since the last revision on the household's
        page, so being counted there is not being alive at the count: 497
        members were asserted alive at a roll that records their death."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Сидоръ"), CensusRole.SON, previous_age=3,
                   departure_year=1820, departure_reason="умер")))
        self.assertEqual(2, len(facts.of(EnumeratedIn)))
        self.assertEqual(1, len(facts.of(SurvivedUntil)))

    def test_the_roll_states_the_death_it_records(self):
        """«умер 1820» is a death, not a move to nowhere: it was a `MovedTo`
        with an empty place and reason «умер», which no rule may read."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Сидоръ"), CensusRole.SON, previous_age=3,
                   departure_year=1820, departure_reason="умер")))
        died = facts.of(DiedOn)
        self.assertEqual([(1820, 1, 1)], [d.date.earliest for d in died])
        self.assertTrue(died[0].date.circa, "a year told to the counter, not read")
        self.assertEqual((), facts.of(MovedTo))

    def test_an_undated_death_lies_before_the_roll(self):
        facts = _facts(_household(
            HEAD, member(2, person("Сидоръ"), CensusRole.SON, previous_age=3,
                         departure_reason="умер")))
        died = facts.of(DiedOn)
        self.assertEqual(1, len(died))
        self.assertIsNone(died[0].date.earliest)
        self.assertEqual((1834, 12, 31), died[0].date.latest)

    def test_one_who_left_alive_was_alive_when_they_left(self):
        """«отдан в рекруты» in 1783: the 1795 roll says he was alive to be
        taken, not that he was alive in 1795."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Сидоръ"), CensusRole.SON, previous_age=20,
                   departure_year=1783, departure_reason="отдан в рекруты")),
            year=1795)
        alive = [a for a in facts.of(SurvivedUntil) if a.subject.id.endswith("/member2")]
        self.assertEqual([1783], [a.date.year for a in alive])
        basis = alive[0].basis
        assert isinstance(basis, Derived)
        self.assertIsInstance(basis.because[0], MovedTo)

    def test_one_who_left_at_no_stated_date_is_bounded_by_nothing(self):
        """«в бегах», no year, no place: still a departure the roll states —
        which left no trace at all when a move needed a place or a year."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Сидоръ"), CensusRole.SON, previous_age=20,
                   departure_reason="в бегах")))
        self.assertEqual([], [a for a in facts.of(SurvivedUntil)
                              if a.subject.id.endswith("/member2")])
        self.assertEqual(["в бегах"], [m.reason for m in facts.of(MovedTo)])

    def test_a_woman_s_death_is_one_too(self):
        """«умерла» — the one spelling the translator's exact «умер» misses."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Марья"), CensusRole.DAUGHTER,
                   departure_reason="умерла")))
        self.assertEqual(1, len(facts.of(SurvivedUntil)))

    def test_a_roll_asserts_no_birth_date_of_its_own(self):
        """An age is evidence; what it implies about a birth is arithmetic."""
        self.assertEqual((), _facts(_household(HEAD)).of(BornOn))

    def test_a_reconstructed_birth_year_is_stated_as_one(self):
        facts = _facts(_household(
            member(1, person("Пахомъ"), CensusRole.HEAD, age=52, birth_year=1782)))
        born = facts.of(BornOn)
        self.assertEqual(1, len(born))
        self.assertEqual((1782, 1, 1), born[0].date.earliest)


class TwoAgesAreTwoStatements(unittest.TestCase):
    def test_current_and_previous_age_are_dated_apart(self):
        facts = _facts(_household(
            member(1, person("Власій"), CensusRole.HEAD, age=53, previous_age=37)),
            prev_revision_year=1816)
        ages = {a.age: a.as_of.year for a in facts.of(AgedYears)}
        self.assertEqual({53: 1834, 37: 1816}, ages)

    def test_an_age_not_recorded_is_not_an_age(self):
        """`age="?"` is the transcriber's «не записано», not a figure the book
        gives: 198 of them were asserted as ages the corpus holds."""
        facts = _facts(_household(
            member(1, person("Иванъ"), CensusRole.HEAD, age="?", previous_age="?")),
            prev_revision_year=1816)
        self.assertEqual((), facts.of(AgedYears))

    def test_the_scribes_own_string_survives(self):
        facts = _facts(_household(
            member(1, person("Нилъ"), CensusRole.HEAD, age="полгода")))
        self.assertEqual(["полгода"], [a.age for a in facts.of(AgedYears)])

    def test_a_prior_age_written_in_prose_is_an_age_too(self):
        """«прошлая РС: 4.5 лет» — 40 of the corpus's previous-revision ages
        live in the comment because the column was already spoken for."""
        facts = _facts(_household(
            member(1, person("Власій"), CensusRole.HEAD, age=53,
                   comment="прошлая РС: 4.5 лет; Сидоров сын Нила")),
            prev_revision_year=1816)
        ages = {a.age: a.as_of.year for a in facts.of(AgedYears)}
        self.assertEqual({53: 1834, "4.5 лет": 1816}, ages)

    def test_the_column_wins_over_the_prose(self):
        facts = _facts(_household(
            member(1, person("Власій"), CensusRole.HEAD, age=53, previous_age=37,
                   comment="прошлая РС: 4.5 лет")),
            prev_revision_year=1816)
        self.assertEqual({53, 37}, {a.age for a in facts.of(AgedYears)})


class AnAuthorCanWithdrawTheLinesAges(unittest.TestCase):
    """`member(source_age_error=)`: the scan was re-read, the transcription is
    faithful, and the scribe's figure is still wrong — a man at «51» in the
    1834 roll against a christening, a roll and a wedding that all make him 35."""

    SLIP = "в сказке «51» (скан л. 7); крещение 1799, РС 1811 — 12 лет"

    def test_every_age_and_the_birth_year_are_withdrawn(self):
        facts = _facts(_household(
            member(1, person("Прокопій", "Игнатьевъ"), CensusRole.HEAD, age=51,
                   previous_age=33, birth_year=1783, source_age_error=self.SLIP)),
            prev_revision_year=1816)
        withdrawn = [a for a in facts if isinstance(a, (AgedYears, BornOn))]
        self.assertEqual(3, len(withdrawn))
        bases = [a.basis for a in withdrawn]
        self.assertTrue(all(isinstance(b, Retracted) for b in bases))
        self.assertEqual({self.SLIP},
                         {b.reason for b in bases if isinstance(b, Retracted)})
        self.assertEqual((), facts.believed().of(AgedYears))
        self.assertEqual((), facts.believed().of(BornOn))

    def test_the_rest_of_the_line_stands(self):
        facts = _facts(_household(
            member(1, person("Прокопій", "Игнатьевъ"), CensusRole.HEAD, age=51,
                   source_age_error=self.SLIP),
            member(2, person("Лукьянъ"), CensusRole.SON, age=2)))
        believed = facts.believed()
        self.assertEqual(2, len(believed.of(EnumeratedIn)))
        self.assertEqual([2], [a.age for a in believed.of(AgedYears)])

    def test_the_translator_reads_it_for_the_birth_alone(self):
        """The document prints what the roll says; only the birth date the
        withdrawn age derived leaves the profile (tests/test_retracted_age_birth)."""
        from verso.ru.targets.geni.translator import TerraformGenerator

        def emitted(**kw):
            gen = TerraformGenerator()
            recs = census_records("ГАТО", "12", "1", "1", "Тестовка", 1834,
                                  _household(member(1, person("Прокопій", "Игнатьевъ"),
                                                    CensusRole.HEAD, age=51, **kw)))
            gen.add_census_records(recs)
            gen.finalize()
            return dict(gen.iter_outputs())

        plain, retracted = emitted(), emitted(source_age_error=self.SLIP)
        self.assertNotEqual(plain, retracted)
        self.assertEqual(_without_birth(plain), _without_birth(retracted))


class AnAuthorCanWithdrawThePreviousAgeAlone(unittest.TestCase):
    """`member(previous_age_error=)`: the roll copied an earlier tale's slip
    forward faithfully, and its own figure is sound — a man christened in
    October 1813, «15» in the 1834 roll and «15 → 37» with a birth date in 1850.
    """

    SLIP = "«15» перенесено из РС 1834 (там писарь); крещён 9.10.1813"

    def _line(self, **kw):
        return _facts(_household(
            member(1, person("Тихонъ", "Сидоровъ"), CensusRole.SON, age=37,
                   previous_age=15, birth_day=6, birth_month=Month.OCTOBER,
                   birth_year=1813, **kw)), year=1850, prev_revision_year=1834)

    def test_only_the_previous_age_is_withdrawn(self):
        facts = self._line(previous_age_error=self.SLIP)
        believed = facts.believed()
        self.assertEqual([(37, 1850)],
                         [(a.age, a.as_of.year) for a in believed.of(AgedYears)])
        self.assertEqual(1, len(believed.of(BornOn)))
        withdrawn = [(a.age, a.basis.reason) for a in facts.of(AgedYears)
                     if isinstance(a.basis, Retracted)]
        self.assertEqual([(15, self.SLIP)], withdrawn)

    def test_the_whole_line_form_still_wins(self):
        """Both kwargs: every age goes, as `source_age_error` alone would."""
        facts = self._line(source_age_error="всё", previous_age_error=self.SLIP)
        self.assertEqual((), facts.believed().of(AgedYears))
        self.assertEqual((), facts.believed().of(BornOn))

    def test_the_translator_reads_it_for_the_birth_alone(self):
        """1850 − 15 back to 1834 gave 1819; the current 37 gives 1813."""
        from verso.ru.targets.geni.translator import TerraformGenerator

        def emitted(**kw):
            gen = TerraformGenerator()
            recs = census_records("ГАТО", "12", "1", "1", "Тестовка", 1850,
                                  _household(member(1, person("Тихонъ", "Сидоровъ"),
                                                    CensusRole.HEAD, age=37,
                                                    previous_age=15, **kw)))
            gen.add_census_records(recs)
            gen.finalize()
            return dict(gen.iter_outputs())

        plain, retracted = emitted(), emitted(previous_age_error=self.SLIP)
        self.assertIn("year  = 1819", "".join(plain.values()))
        self.assertIn("year  = 1813", "".join(retracted.values()))
        self.assertEqual(_without_birth(plain), _without_birth(retracted))


class OneFigureInTwoColumnsIsOneAge(unittest.TestCase):
    """The importer's compression: when the сказка's current-age column was
    EMPTY — usually because the member had left: сдан в рекруты, продан,
    переведён, умер — it copied the previous age into both columns so the
    document had something to render. The book states one age, taken at the
    previous revision.
    """

    def _ages(self, *, year: int = 1795, **member_kw) -> list[tuple[object, int | None]]:
        """(age, year) pairs, not a dict: two readings of one figure are the
        very thing under test, and a dict keyed on the figure hides one."""
        facts = _facts(_household(
            member(1, person("Иванъ"), CensusRole.HEAD, **member_kw)), year=year)
        return sorted(((a.age, a.as_of.year) for a in facts.of(AgedYears)), key=str)

    def test_the_copy_is_not_a_reading_of_the_current_roll(self):
        """A man «отдан в рекруты» in 1783, 24 at the 1782 revision — never 24
        in 1795."""
        self.assertEqual([(24, 1782)],
                         self._ages(age=24, previous_age=24,
                                    departure_year=1783,
                                    departure_reason="отдан в рекруты"))

    def test_the_same_copy_spelled_in_prose(self):
        """The 1850 roll's infants who died between revisions: `age="0.5"`
        beside «прошлая РС: 0.5 лет» — half a year old in 1834, not in 1850."""
        self.assertEqual([("0.5 лет", 1834)],
                         self._ages(year=1850, age="0.5", departure_reason="умер",
                                    comment="прошлая РС: 0.5 лет"))

    def test_two_different_figures_are_still_two_readings(self):
        self.assertEqual([(24, 1782), (37, 1795)],
                         self._ages(age=37, previous_age=24))


class AnAgeOfSomeoneAlreadyGoneIsUndated(unittest.TestCase):
    """The current-age column is blank for a member who died or was married off
    before the revision (CAI004), so a figure that is not a copy of the previous
    one is an age the roll does not date. 1762 is the first revision to count
    women at all, so its brides have no previous column either."""

    def test_a_bride_married_off_before_the_first_count_of_women(self):
        """A bride «выдана в замужество в Захребетский уезд», 18 — at no date the
        roll gives."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Матрена"), CensusRole.DAUGHTER, age=18,
                   departure_reason="выдана замуж")),
            year=1762)
        ages = [(a.age, a.as_of.year) for a in facts.of(AgedYears)
                if a.subject.id.endswith("/member2")]
        self.assertEqual([(18, None)], ages)

    def test_the_living_are_aged_at_the_roll(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Матрена"), CensusRole.DAUGHTER, age=18)),
            year=1762)
        ages = [(a.age, a.as_of.year) for a in facts.of(AgedYears)
                if a.subject.id.endswith("/member2")]
        self.assertEqual([(18, 1762)], ages)


class ThePreviousAgeIsDatedByHistory(unittest.TestCase):
    """`prev_revision_year=` is a GATE, not a date.

    The DSL documents it as «this roll has a known prior revision» and the
    translator reads only whether it is set. Its value is whatever the author
    typed, and in four books it is not the revision the previous-age column
    counts from: a book of 1795 declares 1762 while its comparable members
    are older by 13 years, which is 1782. Dating a previous age by the flag put
    ages twenty years early.
    """

    def _prior(self, year: int, **kw) -> int | None:
        facts = _facts(_household(
            member(1, person("Иванъ"), CensusRole.HEAD, age=30, previous_age=17)),
            year=year, **kw)
        dated = {a.age: a.as_of.year for a in facts.of(AgedYears)}
        return dated[17]

    def test_a_declared_year_the_ages_contradict_is_not_read(self):
        self.assertEqual(1782, self._prior(1795, prev_revision_year=1762))

    def test_the_fifth_revision_dates_its_prior_ages_without_a_declaration(self):
        self.assertEqual(1782, self._prior(1795))

    def test_a_roll_the_table_does_not_know_keeps_its_own_word(self):
        """The roll of 1782 is the one such book, and its word is right: its
        comparable members are every one older by 19 years than at the 1763
        revision."""
        self.assertEqual(1763, self._prior(1782, prev_revision_year=1763))

    def test_one_table_serves_the_linter_and_the_facts(self):
        """CAI002 checks the two age columns against each other with this
        table; an extractor reading another would date the same ages apart."""
        from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR
        from verso.ru.linters.checks import census_age
        self.assertIs(PREVIOUS_AGE_REVISION_YEAR, census_age._PREV_REVISION_YEAR)


class StatedAndReconstructedAreOnePredicate(unittest.TestCase):
    def test_a_son_is_the_head_s_child_by_the_roll(self):
        facts = _facts(_household(
            HEAD, member(2, person("Агапъ"), CensusRole.SON, age=34)))
        links = facts.of(ParentOf)
        self.assertEqual(1, len(links))
        self.assertIsInstance(links[0].basis, Stated)

    def test_a_parent_member_is_our_reconstruction(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Ѳедоръ"), CensusRole.SON, age=30, hidden=True),
            member(3, person("Семенъ"), CensusRole.GRANDSON, age=7,
                   parent_member=2)))
        link = next(a for a in facts.of(ParentOf)
                    if (_number(a.subject), _number(a.other)) == (2, 3))
        assert isinstance(link.basis, Derived)
        self.assertEqual("census.reconstructed-parent", link.basis.rationale)

    def test_a_grandson_is_not_the_head_s_child(self):
        """«внукъ» is measured against the head, so the reference is the
        GRANDfather; reading it as a parent invents a generation."""
        facts = _facts(_household(
            HEAD, member(2, person("Семенъ"), CensusRole.GRANDSON, age=7)))
        self.assertEqual((), facts.of(ParentOf))
        self.assertEqual(1, len(facts.of(KinOf)))

    def test_a_hidden_member_asserts_nothing_as_stated(self):
        """They are not in the book at all: the roll does not name them, so
        nothing about them can be what the roll says."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Ѳедоръ"), CensusRole.SON, age="?", hidden=True)))
        hidden_claims = [a for a in facts.of(NameClaim) if a.subject.id.endswith("/member2")]
        self.assertTrue(hidden_claims)
        for a in hidden_claims:
            self.assertIsInstance(a.basis, Derived)

    def test_a_hidden_member_is_not_enumerated(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Ѳедоръ"), CensusRole.SON, age="?", hidden=True)))
        self.assertEqual(1, len(facts.of(EnumeratedIn)))
        self.assertEqual(1, len(facts.of(SurvivedUntil)))

    def test_spouse_member_states_the_marriage_the_role_cannot(self):
        """The thirteen `role=None` members: with the role cleared, the
        reference means a spouse and only `spouse_member` says so."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Аксинья"), CensusRole.WIFE, ref_member=1, age=40),
            member(3, person("Ѳедотъ"), None, ref_member=2, age="?",
                   hidden=True, spouse_member=2)))
        pairs = {(_number(a.subject), _number(a.other)) for a in facts.of(SpouseOf)}
        self.assertIn((3, 2), pairs)
        self.assertIn((2, 3), pairs)

    def test_without_spouse_member_a_role_less_reference_states_nothing(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Аксинья"), CensusRole.WIFE, ref_member=1, age=40),
            member(3, person("Ѳедотъ"), None, ref_member=2, age="?",
                   hidden=True)))
        pairs = {(_number(a.subject), _number(a.other)) for a in facts.of(SpouseOf)}
        self.assertNotIn((3, 2), pairs)

    def test_a_father_referenced_at_the_mother_is_her_husband(self):
        """A hidden «Фока» FATHER `ref_member=` the MOTHER «Агафья Лукина».
        The reference names his wife — the translator's hidden-ancestor pass
        pairs them — so he is the head's father, not hers; read the other way
        she was «Лукинична» with a father Фока."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Агафья", "Лукина"), CensusRole.MOTHER, age=68),
            member(3, person("Фока"), CensusRole.FATHER, ref_member=2,
                   age="?", hidden=True)))
        parents = {(_number(a.subject), _number(a.other)) for a in facts.of(ParentOf)}
        self.assertNotIn((3, 2), parents)
        self.assertIn((3, 1), parents)
        self.assertIn((2, 1), parents)
        spouses = {(_number(a.subject), _number(a.other)) for a in facts.of(SpouseOf)}
        self.assertEqual({(3, 2), (2, 3)}, spouses)

    def test_the_mother_he_is_referenced_at_need_not_be_the_head_s(self):
        """«Фекла» is the MOTHER of member 2, a son by her first husband,
        and «Пахомъ» — referenced at her — is the HEAD's father (the head is
        «Нилъ Пахомовъ»), not member 2's."""
        facts = _facts(_household(
            member(1, person("Нилъ", "Пахомовъ"), CensusRole.HEAD, age=41,
                   parent_member=4),
            member(2, person("Харитонъ", "Игнатьевъ"), None, ref_member=1, age=33),
            member(3, person("Фекла", "Лукина"), CensusRole.MOTHER,
                   ref_member=2, age=63),
            member(4, person("Пахомъ"), CensusRole.FATHER, ref_member=3,
                   age="?", hidden=True)))
        parents = {(_number(a.subject), _number(a.other)) for a in facts.of(ParentOf)}
        self.assertIn((4, 1), parents)
        self.assertNotIn((4, 2), parents)
        self.assertNotIn((4, 3), parents)

    def test_a_father_referenced_at_a_nephew_is_the_nephew_s_father(self):
        facts = _facts(_household(
            HEAD,
            member(2, person("Семенъ", "Ивановъ"), CensusRole.NEPHEW, age=20),
            member(3, person("Иванъ"), CensusRole.FATHER, ref_member=2, age=50)))
        parents = {(_number(a.subject), _number(a.other)) for a in facts.of(ParentOf)}
        self.assertEqual({(3, 2)}, parents)

    def test_a_foster_child_is_not_a_child(self):
        facts = _facts(_household(
            HEAD, member(2, person("Казма"), CensusRole.FOSTER_SON,
                         ref_member=1, age=10)))
        self.assertEqual((), facts.of(ParentOf))
        self.assertEqual(1, len(facts.of(FosterParentOf)))


class MovementsAndProvenance(unittest.TestCase):
    def test_an_origin_is_where_they_came_from(self):
        facts = _facts(_household(
            member(1, person("Авдотья"), CensusRole.HEAD, age=30,
                   origin="Сонливка", arrival_year=1820,
                   arrival_reason="взята замужъ")))
        came = facts.of(ArrivedFrom)
        self.assertEqual(1, len(came))
        self.assertEqual("Сонливка", came[0].place)
        self.assertEqual(1820, came[0].when.year)

    def test_a_departure_is_a_move_even_without_a_place(self):
        facts = _facts(_household(
            member(1, person("Петръ"), CensusRole.HEAD, age=30,
                   departure_year=1815, departure_reason="отдан в рекруты")))
        went = facts.of(MovedTo)
        self.assertEqual(1, len(went))
        self.assertEqual("", went[0].place)
        self.assertEqual(1815, went[0].when.year)

    def test_the_book_s_own_role_word_is_provenance(self):
        """«роль в оригинале: дядя родной» — a claim about the text, so it
        travels in the citation where no rule can reach it."""
        facts = _facts(_household(
            HEAD,
            member(2, person("Осипъ"), CensusRole.UNCLE, age=50,
                   comment="роль в оригинале: дядя родной; прочее")))
        roles = {a.cite.stated_role for a in facts.of(NameClaim)}
        self.assertIn("дядя родной", roles)

    def test_a_comment_without_a_key_states_nothing(self):
        facts = _facts(_household(
            HEAD, member(2, person("Осипъ"), CensusRole.UNCLE, age=50,
                         comment="вдовъ")))
        self.assertEqual({None}, {a.cite.stated_role for a in facts.of(NameClaim)})


if __name__ == "__main__":
    unittest.main()


class AGroupBelongsToItsRoll(unittest.TestCase):
    """Two rolls of one year each number a group 1, and they are two groups.

    The oracle's key is `(date, number)` recovered from a res_name, which has
    nowhere to put the roll — so over a whole village it fuses groups holding
    hundreds of people, some of them from different villages of the same дело. No live
    verdict rests on the fusion today; the key simply cannot express it.
    """

    def test_the_same_number_in_two_rolls_is_two_groups(self):
        recs_a = census_records("ГАТО", "66", "8", "128", "Тестовка", 1811,
                                household("1", member(1, person("Иванъ"),
                                                      CensusRole.HEAD, age=40)))
        recs_b = census_records("ГАТО", "24", "2", "140", "Тестовка", 1811,
                                household("1", member(1, person("Сидоръ"),
                                                      CensusRole.HEAD, age=30)))
        facts = AssertionSet(facts_from_census(
            [(recs_a, "d434.py"), (recs_b, "d443.py")], village="Тестовка"))
        self.assertEqual(2, len({a.payload for a in facts.of(EnumeratedIn)}))
