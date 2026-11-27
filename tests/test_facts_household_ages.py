"""A father's and a child's ages within one roll — `check=household-ages`.

A revision tale or a confession list states every member's age on the day of the roll (and, a revision before,
the previous column). A father asserted by the roll (`ParentOf` with the roll's own word as its basis) whose
age difference from the child lies wholly under the age of fatherhood — or a child older than its father — is
a reading to check. Fathers only: a roll asserts no mothers, and a wife is never asked. A member gone before the
roll is compared by the previous column; one without an age is not compared; the author's `source_age_error=`
withdraws the age.
"""
from __future__ import annotations

from verso.core import i18n
from verso.ru.domain import person
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.facts.checks.household_ages import HouseholdAgeFinding, household_age_findings
from verso.ru.facts.checks.parent_ages import FATHER_MIN
from verso.ru.facts.extract.census import facts_from_census
from verso.ru.facts.model import AssertionSet
from verso.ru.facts.signals import CHECKS, STAND_DOWN, signals_of

RID = "r1:Маниловка/1-1-1/1834/census/7"


def _roll(*members, family_id: str = "7"):
    return census_records("ГАТО", "12", "1", "1", "Маниловка", 1834, household(family_id, *members), reviewed=False)


def _facts(roll) -> AssertionSet:
    return AssertionSet(facts_from_census([(roll, "rs.py")], village="Маниловка", drafts=True)).believed()


def _father_son(father_age, son_age, **son):
    return _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=father_age),
                 member(2, person("Петръ"), CensusRole.SON, age=son_age, **son))


def test_father_of_eleven_is_a_finding():
    (f,) = household_age_findings(_facts(_father_son(23, 12)))
    assert isinstance(f, HouseholdAgeFinding)
    assert (f.kind, f.confidence) == ("too_young", "HIGH")
    assert (round(f.gap_low), round(f.gap_high)) == (10, 12)
    assert f.cite.locator == "member1"


def test_father_at_fifteen_is_not():
    assert FATHER_MIN == 15
    assert household_age_findings(_facts(_father_son(27, 12))) == []


def test_a_wife_is_never_asked():
    roll = _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=40),
                 member(2, person("Марія"), CensusRole.WIFE, age=21),
                 member(3, person("Петръ"), CensusRole.SON, ref_member=2, age=12))
    assert household_age_findings(_facts(roll)) == []


def test_child_older_than_father_is_high():
    (f,) = household_age_findings(_facts(_father_son(30, 31)))
    assert (f.kind, f.confidence) == ("child_older", "HIGH")


def test_a_hidden_member_without_an_age_is_silent():
    roll = _roll(member(1, person("Петръ"), CensusRole.HEAD, age=12),
                 member(2, person("Иванъ", "Петровъ"), CensusRole.FATHER, hidden=True, parent_member=None))
    assert household_age_findings(_facts(roll)) == []


def test_departed_member_compares_previous_ages():
    # the father died (1845 — before the roll): his current column is blank, his previous age 40, the son's 12
    roll = _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=None, previous_age=40,
                        departure_reason="умер", departure_year=1830),
                 member(2, person("Петръ"), CensusRole.SON, age=12, previous_age=12))
    assert household_age_findings(_facts(roll)) == []
    young = _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=None, previous_age=20,
                         departure_reason="умер", departure_year=1830),
                  member(2, person("Петръ"), CensusRole.SON, age=14, previous_age=9))
    (f,) = household_age_findings(_facts(young))
    assert f.kind == "too_young"


def test_a_member_without_an_age_is_silent():
    roll = _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=23),
                 member(2, person("Петръ"), CensusRole.SON, age=None))
    assert household_age_findings(_facts(roll)) == []


def test_source_age_error_stands_it_down():
    roll = _roll(member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=23, source_age_error="так в сказке"),
                 member(2, person("Петръ"), CensusRole.SON, age=12))
    assert household_age_findings(_facts(roll)) == []
    assert len(household_age_findings(_facts(_father_son(23, 12)))) == 1


def test_the_checks_and_the_field_that_stands_this_one_down():
    assert "household-ages" in CHECKS
    assert STAND_DOWN["household-ages"] == "source_age_error"


def _roll_and_household(roll):
    return roll, roll.households[0]


def test_signals_of_a_household_ask_household_ages_only():
    roll, dvor = _roll_and_household(_father_son(23, 12))
    s = signals_of(dvor, record_id=RID, record_set=roll)
    assert {x.check for x in s.found} == {"household-ages"}
    [one] = s.found
    assert (one.variant, one.confidence, one.stand_down, one.record) == ("too_young", "HIGH", "source_age_error", RID)
    assert one.key == "facts.signal.household_ages.too_young"
    assert one.said.params == {"low": "10", "high": "12"}
    assert i18n.render(one.said, "ru") == "Отцу при рождении ребёнка 10–12 лет — сверьте возрасты в росписи."
    with i18n.use("en"):
        assert "father" in i18n.render(one.said, "en").lower()


def test_child_older_is_said_in_its_words():
    roll, dvor = _roll_and_household(_father_son(30, 31))
    [one] = signals_of(dvor, record_id=RID, record_set=roll).found
    assert one.key == "facts.signal.household_ages.child_older"
    assert i18n.render(one.said, "ru").startswith("Ребёнок старше отца")


def test_a_household_without_its_set_answers_nothing():
    _roll, dvor = _roll_and_household(_father_son(23, 12))
    s = signals_of(dvor, record_id=RID)
    assert (s.found, s.unanswered) == ((), ())


def test_the_household_alone_yields_the_facts_the_whole_roll_yields_for_it():
    from verso.ru.facts.extract.one import extractor_of
    roll = census_records("ГАТО", "12", "1", "1", "Маниловка", 1834,
                          household("5", member(1, person("Сидоръ"), CensusRole.HEAD, age=40)),
                          household(None, member(1, person("Иванъ", "Петровъ"), CensusRole.HEAD, age=23),
                                    member(2, person("Петръ"), CensusRole.SON, age=12)),
                          household(None, member(1, person("Карпъ"), CensusRole.HEAD, age=50)), reviewed=False)
    whole = list(facts_from_census([(roll, "")], village="Маниловка", drafts=True))
    for dvor in roll.households:
        extract = extractor_of(dvor, record_set=roll)
        assert extract is not None
        alone = list(extract([(dvor, "")], village="Маниловка", drafts=True))
        mine = [a for a in whole if a.cite.entry == alone[0].cite.entry]
        assert alone == mine and alone
