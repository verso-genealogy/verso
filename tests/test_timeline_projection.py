"""Tests for the timeline projection: GeniProfile/GeniUnion → timeline model.

The projection's job is to decide what the drawing may claim. Each test below
pins one row of that policy, because the failure mode is not a crash — it is a
picture that quietly asserts a death nobody recorded, or a wedding date nobody
wrote down.

Domain objects are built by hand (as in `test_familio_projection.py`) rather
than by translating a village: a real translation costs ~35s and none of this
policy depends on it.
"""
from __future__ import annotations

import pytest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion
from verso.ru.timeline.history import History
from verso.ru.timeline.model import HUE_UNATTACHED, Band
from verso.ru.timeline.projection import KinResolutionError, project


def _profile(res_name, *, first="Иван", last="Кувшинников", gender="male",
             birth=None, death=None, **kw) -> GeniProfile:
    return GeniProfile(
        res_name=res_name, gender=gender, first_name=first, last_name=last,
        birth=birth, death=death, **kw,
    )


def _event(year, month=None, day=None, circa=False, date_range=None,
           end_year=None) -> GeniEvent:
    return GeniEvent(date=GeniDate(year=year, month=month, day=day, circa=circa,
                                   date_range=date_range, end_year=end_year))


def _union(res_name, a, b, *, marriage=None, children=()) -> GeniUnion:
    return GeniUnion(res_name=res_name, partner_1=a, partner_2=b,
                     children=set(children), marriage=marriage)


def _project(profiles, unions, kin, **kw):
    return project({p.res_name: p for p in profiles},
                   {u.res_name: u for u in unions}, kin,
                   village=kw.pop("village", "Тестовка"), **kw)


# --- kin resolution ----------------------------------------------------------

def test_unknown_kin_res_name_fails_loudly():
    """A stale registry entry must stop the run, not silently shrink the tree."""
    with pytest.raises(KinResolutionError) as excinfo:
        _project([_profile("a", birth=_event(1800))], [], ["a", "ghost"])
    assert excinfo.value.missing == ["ghost"]


def test_accepts_a_mapping_or_a_sequence_of_kin():
    people = [_profile("a", birth=_event(1800))]
    assert len(_project(people, [], {"a": None}).people) == 1
    assert len(_project(people, [], ["a"]).people) == 1


# --- birth / death ------------------------------------------------------------

def test_person_without_a_birth_year_is_excluded_and_reported():
    """No birth year means no place on a time axis. Dropping the person is
    right; dropping them silently is not."""
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=None)],
        [], ["a", "b"],
    )
    assert set(timeline.people) == {"a"}
    assert any("без года рождения" in note for note in timeline.notes)


def test_circa_birth_is_flagged_not_flattened():
    timeline = _project([_profile("a", birth=_event(1800, circa=True))], [], ["a"])
    assert timeline.people["a"].birth_circa is True
    assert timeline.people["a"].birth_year == 1800


def test_missing_death_year_leaves_has_death_false():
    timeline = _project([_profile("a", birth=_event(1800))], [], ["a"])
    person = timeline.people["a"]
    assert person.death_year is None
    assert person.death_at is None
    assert person.has_death is False


def test_sub_year_precision_is_kept_where_the_record_has_it():
    """A life of nine days must not be rounded to 1 January at both ends."""
    timeline = _project(
        [_profile("a", birth=_event(1853, 8, 14), death=_event(1853, 8, 23))],
        [], ["a"],
    )
    person = timeline.people["a"]
    assert person.birth_year == person.death_year == 1853
    assert person.death_at is not None
    assert person.birth_at < person.death_at
    assert 1853 < person.birth_at < 1854


def test_year_only_record_sits_at_the_start_of_its_year():
    timeline = _project([_profile("a", birth=_event(1800))], [], ["a"])
    assert timeline.people["a"].birth_at == 1800.0


# --- ranged dates: a bound is not an event ------------------------------------

def test_an_after_bound_is_not_a_death():
    """«умер после 1866» says the person was ALIVE in 1866. Reading its year as a
    death year is the single most destructive misreading available here: across
    the Горюхино tree 5763 profiles carry exactly this shape."""
    timeline = _project(
        [_profile("a", birth=_event(1841), death=_event(1866, date_range="after"))],
        [], ["a"],
    )
    person = timeline.people["a"]
    assert person.has_death is False
    assert person.death_year is None
    assert person.death_at is None
    assert person.last_seen_year == 1866


def test_a_between_death_window_is_not_a_death_either():
    timeline = _project(
        [_profile("a", birth=_event(1841),
                  death=_event(1880, date_range="between", end_year=1890))],
        [], ["a"],
    )
    assert timeline.people["a"].has_death is False
    assert timeline.people["a"].last_seen_year == 1890


def test_a_plain_death_date_is_a_death():
    timeline = _project(
        [_profile("a", birth=_event(1841), death=_event(1866))], [], ["a"])
    person = timeline.people["a"]
    assert person.has_death is True
    assert person.death_year == 1866
    assert person.last_seen_year == 1866


def test_a_between_birth_is_a_window_not_a_year():
    """`between 1855 and 1888` must not collapse to 1855 — that would put a son
    six years before his father's wedding."""
    timeline = _project(
        [_profile("a", birth=_event(1855, date_range="between", end_year=1888))],
        [], ["a"],
    )
    person = timeline.people["a"]
    assert person.birth_is_window is True
    assert person.birth_uncertain_to is not None
    assert int(person.birth_uncertain_to) == 1888
    assert person.birth_year == 1855


def test_last_seen_takes_the_latest_evidence_including_a_marriage():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802))],
        [_union("u", "a", "b", marriage=_event(1860))], ["a", "b"],
    )
    assert timeline.people["a"].last_seen_year == 1860
    assert timeline.people["a"].has_death is False


def test_notes_report_recorded_deaths_not_bounds():
    timeline = _project(
        [_profile("a", birth=_event(1800), death=_event(1850)),
         _profile("b", birth=_event(1802), death=_event(1860, date_range="after"))],
        [], ["a", "b"],
    )
    assert any("Только у 1 из 2 записана дата смерти" in n for n in timeline.notes)


# --- marriages ----------------------------------------------------------------

def test_recorded_marriage_year_is_used_verbatim():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802))],
        [_union("u", "a", "b", marriage=_event(1825))],
        ["a", "b"],
    )
    marriage = timeline.marriages["u"]
    assert (marriage.year, marriage.year_inferred) == (1825, False)
    assert marriage.joins_two_threads is True


def test_undated_marriage_is_inferred_from_the_eldest_child():
    """The couple demonstrably existed by their first child's birth, so a year
    earlier is a defensible bound — provided it is marked as inferred."""
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802)),
         _profile("c1", birth=_event(1830)), _profile("c2", birth=_event(1827))],
        [_union("u", "a", "b", children=["c1", "c2"])],
        ["a", "b", "c1", "c2"],
    )
    marriage = timeline.marriages["u"]
    assert (marriage.year, marriage.year_inferred) == (1826, True)
    assert marriage.at == 1826.0
    assert any("записанной даты" in note for note in timeline.notes)


def test_marriage_with_neither_date_nor_children_has_no_year():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802))],
        [_union("u", "a", "b")], ["a", "b"],
    )
    assert timeline.marriages["u"].year is None
    assert timeline.marriages["u"].at is None


def test_spouse_outside_the_registry_is_named_but_gets_no_thread():
    timeline = _project(
        [_profile("a", birth=_event(1800)),
         _profile("out", first="Прасковья", last="Иванова", gender="female",
                  birth=_event(1805))],
        [_union("u", "a", "out", marriage=_event(1825))],
        ["a"],
    )
    marriage = timeline.marriages["u"]
    assert marriage.kin_partners == ("a",)
    assert marriage.outside_partner == "Прасковья Иванова"
    assert marriage.joins_two_threads is False
    assert "out" not in timeline.people


def test_union_with_a_missing_partner_is_still_projected():
    timeline = _project(
        [_profile("a", birth=_event(1800))],
        [_union("u", "a", None, marriage=_event(1825))], ["a"],
    )
    assert timeline.marriages["u"].kin_partners == ("a",)
    assert timeline.marriages["u"].outside_partner is None


def test_union_touching_nobody_on_the_timeline_is_dropped():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("x", birth=_event(1800)),
         _profile("y", birth=_event(1800))],
        [_union("u", "x", "y", marriage=_event(1825))], ["a"],
    )
    assert timeline.marriages == {}


def test_links_to_an_undated_person_are_pruned_from_marriages():
    """Nothing in the model may reference someone the picture does not draw."""
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=None),
         _profile("c", birth=_event(1830))],
        [_union("u", "a", "b", marriage=_event(1825), children=["c"])],
        ["a", "b", "c"],
    )
    assert timeline.marriages["u"].kin_partners == ("a",)
    assert timeline.people["c"].parents == ("a",)


# --- parentage ----------------------------------------------------------------

def test_parents_come_from_union_membership():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802)),
         _profile("c", birth=_event(1830))],
        [_union("u", "a", "b", marriage=_event(1825), children=["c"])],
        ["a", "b", "c"],
    )
    assert timeline.people["c"].parents == ("a", "b")
    assert timeline.people["c"].parent_union == "u"


def test_parent_overrides_pin_a_link_the_records_leave_implicit():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802)),
         _profile("c", birth=_event(1830))],
        [_union("u", "a", "b", marriage=_event(1825))],
        ["a", "b", "c"],
        parent_overrides={"c": ("a", "b")},
    )
    person = timeline.people["c"]
    assert person.parents == ("a", "b")
    # The override names parents; because a union holding exactly those two
    # exists, the thread can also start on their shared lane.
    assert person.parent_union == "u"


def test_parent_override_naming_a_familio_uuid_is_ignored():
    """A parent that lives only on the familio tree cannot be drawn."""
    timeline = _project(
        [_profile("c", birth=_event(1830))], [], ["c"],
        parent_overrides={"c": ("00000000-0000-4000-8000-b76d3639bbf4",)},
    )
    assert timeline.people["c"].parents == ()
    assert timeline.people["c"].parent_union is None


def test_parent_override_without_a_matching_union_still_groups_the_child():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("c", birth=_event(1830))],
        [], ["a", "c"], parent_overrides={"c": ("a",)},
    )
    assert timeline.people["c"].parents == ("a",)
    assert timeline.people["c"].parent_union is None
    # One component, so no «unattached» band.
    assert [g.key for g in timeline.groups] == ["line-1"]


# --- grouping -----------------------------------------------------------------

def test_connected_families_become_separate_labelled_groups():
    timeline = _project(
        [_profile("a", last="Кувшинников", birth=_event(1800)),
         _profile("b", last="Кувшинникова", gender="female", birth=_event(1802)),
         _profile("x", last="Тюфякин", birth=_event(1810)),
         _profile("y", last="Тюфякина", gender="female", birth=_event(1812))],
        [_union("u1", "a", "b", marriage=_event(1825)),
         _union("u2", "x", "y", marriage=_event(1835))],
        ["a", "b", "x", "y"],
    )
    assert [g.key for g in timeline.groups] == ["line-1", "line-2"]
    assert [g.label for g in timeline.groups] == ["Кувшинниковы", "Тюфякины"]
    assert timeline.groups[0].hue != timeline.groups[1].hue


def test_group_label_folds_feminine_spellings_into_one_surname():
    """Кувшинников and Кувшинникова are one family, not two."""
    timeline = _project(
        [_profile("a", last="Кувшинников", birth=_event(1800)),
         _profile("b", last="Кувшинникова", gender="female", birth=_event(1802)),
         _profile("c", last="Кувшинникова", gender="female", birth=_event(1830))],
        [_union("u", "a", "b", marriage=_event(1825), children=["c"])],
        ["a", "b", "c"],
    )
    assert timeline.groups[0].label == "Кувшинниковы"


def test_isolated_people_share_one_unattached_band():
    """Nine singletons would make nine meaningless bands; one band says the
    useful thing — these are the kin our records connect to nobody."""
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802)),
         _profile("lone1", birth=_event(1850)), _profile("lone2", birth=_event(1860))],
        [_union("u", "a", "b", marriage=_event(1825))],
        ["a", "b", "lone1", "lone2"],
    )
    assert [g.key for g in timeline.groups] == ["line-1", "unattached"]
    unattached = timeline.groups[-1]
    assert unattached.unattached is True
    assert unattached.hue == HUE_UNATTACHED
    assert set(unattached.members) == {"lone1", "lone2"}
    assert any("не связывают" in note for note in timeline.notes)


def test_groups_are_ordered_by_size_then_earliest_birth():
    timeline = _project(
        [_profile("s1", birth=_event(1700)), _profile("s2", birth=_event(1702)),
         _profile("b1", birth=_event(1800)), _profile("b2", birth=_event(1802)),
         _profile("b3", birth=_event(1830))],
        [_union("small", "s1", "s2", marriage=_event(1725)),
         _union("big", "b1", "b2", marriage=_event(1825), children=["b3"])],
        ["s1", "s2", "b1", "b2", "b3"],
    )
    assert [len(g.members) for g in timeline.groups] == [3, 2]


# --- bands and span -----------------------------------------------------------

_ERAS = (Band("era", 1700, 1840, "первая эпоха", "до"), Band("era", 1841, 1902, "вторая эпоха", "после"),
         Band("era", 1903, 2000, "третья эпоха", ""))
_EVENTS = (Band("event", 1773, 1775, "раннее событие", ""), Band("event", 1812, 1812, "Отечественная война", "x"))


def test_bands_are_clipped_to_the_drawn_span():
    timeline = _project(
        [_profile("a", birth=_event(1800), death=_event(1850))], [], ["a"],
        history=History(eras=_ERAS, events=_EVENTS),
    )
    assert timeline.first_year == 1800
    assert timeline.last_year == 1850
    for band in timeline.bands:
        assert band.from_year >= 1800
        assert band.to_year <= 1850
    # The 1841 boundary falls inside this span, so both eras survive, eras before events.
    assert [b.label for b in timeline.bands] == ["первая эпоха", "вторая эпоха", "Отечественная война"]


def test_no_history_draws_no_bands():
    timeline = _project([_profile("a", birth=_event(1800), death=_event(1850))], [], ["a"])
    assert timeline.bands == ()


def test_the_split_note_only_when_the_kin_falls_apart():
    two = ([_profile("s1", birth=_event(1700)), _profile("s2", birth=_event(1702)),
            _profile("b1", birth=_event(1800)), _profile("b2", birth=_event(1802))],
           [_union("small", "s1", "s2", marriage=_event(1725)), _union("big", "b1", "b2", marriage=_event(1825))],
           ["s1", "s2", "b1", "b2"])
    note = "Линии сходятся в браке, которого у нас нет."
    assert note in _project(*two, history=History(split_note=note)).notes
    one = _project([_profile("a", birth=_event(1800))], [], ["a"], history=History(split_note=note))
    assert note not in one.notes


def test_last_year_counts_marriages_not_just_lives():
    timeline = _project(
        [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802))],
        [_union("u", "a", "b", marriage=_event(1860))], ["a", "b"],
    )
    assert timeline.last_year == 1860


# --- determinism --------------------------------------------------------------

def test_projection_is_deterministic():
    people = [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802)),
              _profile("c", birth=_event(1830))]
    unions = [_union("u", "a", "b", marriage=_event(1825), children=["c"])]
    first = _project(people, unions, ["a", "b", "c"])
    second = _project(people, unions, ["a", "b", "c"])
    assert first.groups == second.groups
    assert first.notes == second.notes
    assert list(first.people) == list(second.people)


def _with_lone_people(count):
    """A connected couple (so there is a line group) plus `count` isolated
    people (so there is an «unattached» band of exactly that size)."""
    people = [_profile("a", birth=_event(1800)), _profile("b", birth=_event(1802))]
    people += [_profile(f"lone{i}", birth=_event(1850 + i)) for i in range(count)]
    unions = [_union("u", "a", "b", marriage=_event(1825))]
    return _project(people, unions, [p.res_name for p in people])


def test_unattached_note_agrees_with_its_number():
    """«3 человека», not «3 человек». Russian numeral agreement is exactly the
    class of error `verso.ru.ages.agree` exists to prevent, and prose assembled by
    f-string is where it creeps back in."""
    assert any("1 человек наши записи" in n for n in _with_lone_people(1).notes)
    assert any("3 человека наши записи" in n for n in _with_lone_people(3).notes)
    assert any("5 человек наши записи" in n for n in _with_lone_people(5).notes)


def test_outside_marriage_note_agrees_with_its_number():
    timeline = _project(
        [_profile("a", birth=_event(1800)),
         _profile("out", first="Прасковья", last="Иванова", gender="female",
                  birth=_event(1805))],
        [_union("u", "a", "out", marriage=_event(1825))], ["a"],
    )
    assert any("1 брак заключён" in n for n in timeline.notes)


def test_circa_note_agrees_with_its_number():
    single = _project([_profile("a", birth=_event(1800, circa=True))], [], ["a"])
    assert any("1 дата рождения — расчётная" in n for n in single.notes)
    pair = _project(
        [_profile("a", birth=_event(1800, circa=True)),
         _profile("b", birth=_event(1802, circa=True))], [], ["a", "b"],
    )
    assert any("2 даты рождения — расчётные" in n for n in pair.notes)
