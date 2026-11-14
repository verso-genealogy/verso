"""Tests for the timeline geometry.

Two things matter here beyond "does it draw". First, determinism: the exporter's
only guarantee against a stale file is that identical input yields an identical
byte stream, and there is no formatter to normalise HTML afterwards. Second,
that nobody falls off the picture — a nine-day life still needs a thread.
"""
from __future__ import annotations

import subprocess
import sys
from itertools import pairwise

from verso.ru.timeline.layout import (
    LABEL_LANE_OFFSET, LANE_HEIGHT, MARGIN_RIGHT, NODE_BIRTH, NODE_DEATH, NODE_LAST_SEEN, NODE_MARRIAGE, PX_PER_YEAR, _jitter, build, smooth)
from verso.ru.timeline.model import Band, Group, Marriage, Person, Timeline


def _person(res_name, birth, death=None, *, gender="male", parents=(),
            parent_union=None, unions=(), circa=False, name=None,
            birth_at=None, death_at=None, birth_window_to=None,
            last_seen=None) -> Person:
    """`death` means a RECORDED death. `last_seen` is the weaker thing — the last
    year the person can be shown alive — and defaults to the death, or to the
    birth when nothing else is known."""
    b_at = birth_at if birth_at is not None else float(birth)
    d_at = death_at if death_at is not None else (
        float(death) if death is not None else None)
    if last_seen is not None:
        seen_at = float(last_seen)
    elif d_at is not None:
        seen_at = d_at
    elif birth_window_to is not None:
        seen_at = float(birth_window_to)
    else:
        seen_at = b_at
    return Person(
        res_name=res_name, name=name or res_name.title(), gender=gender,
        birth_year=birth, birth_at=b_at,
        birth_uncertain_to=float(birth_window_to) if birth_window_to else None,
        birth_circa=circa, death_year=death, death_at=d_at,
        last_seen_year=int(seen_at), last_seen_at=seen_at,
        birth_place=None, death_place=None, parents=tuple(parents),
        parent_union=parent_union, unions=tuple(unions),
    )


def _marriage(res_name, partners, year=None, *, children=(), inferred=False,
              outside=None) -> Marriage:
    return Marriage(
        res_name=res_name, year=year, at=float(year) if year is not None else None,
        year_inferred=inferred, kin_partners=tuple(partners),
        outside_partner=outside, children=tuple(children),
    )


def _lanes(layout) -> dict[str, float]:
    """Lane y per person, recovered from their name label (which is drawn one
    fixed offset above the lane)."""
    return {label.text.lower(): label.y + LABEL_LANE_OFFSET for label in layout.labels}


def _timeline(people, marriages=(), groups=None, bands=()) -> Timeline:
    by_res = {p.res_name: p for p in people}
    by_union = {m.res_name: m for m in marriages}
    if groups is None:
        groups = (Group(key="line-1", label="Тест", hue="v",
                        members=tuple(by_res)),)
    return Timeline(village="Тестовка", people=by_res, marriages=by_union,
                    groups=tuple(groups), bands=tuple(bands))


# --- smooth ------------------------------------------------------------------

def test_smooth_needs_two_points():
    assert smooth([]) == ""
    assert smooth([(0.0, 0.0)]) == ""


def test_smooth_starts_with_a_moveto_and_emits_a_curve_per_segment():
    d = smooth([(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)])
    assert d.startswith("M0.0 0.0")
    assert d.count(" C") == 2


# --- jitter determinism -------------------------------------------------------

def test_jitter_is_stable_across_processes():
    """`hash()` is salted per process; the drift must not be. If this ever
    regresses, the generated file changes on every run for no reason."""
    code = (
        "from verso.ru.timeline.layout import _jitter; "
        "print(repr(_jitter('semen_savelievich')))"
    )
    runs = {
        subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, check=True).stdout.strip()
        for _ in range(2)
    }
    assert len(runs) == 1
    assert runs.pop() == repr(_jitter("semen_savelievich"))


# --- lanes --------------------------------------------------------------------

def test_every_person_gets_their_own_lane():
    people = [_person(f"p{i}", 1800 + i) for i in range(6)]
    layout = build(_timeline(people))
    ys = sorted(_lanes(layout).values())
    assert len(ys) == len(people)
    assert all(round(b - a, 6) == LANE_HEIGHT for a, b in pairwise(ys))


def test_spouse_and_children_are_laid_out_under_the_couple():
    """Reading top to bottom should read down the generations."""
    people = [
        _person("father", 1800, unions=("u",)),
        _person("mother", 1802, unions=("u",)),
        _person("child", 1830, parents=("father", "mother"), parent_union="u"),
        _person("stranger", 1805),
    ]
    layout = build(_timeline(people, [_marriage("u", ("father", "mother"), 1825,
                                                children=("child",))]))
    lanes = _lanes(layout)
    assert lanes["father"] < lanes["mother"] < lanes["child"] < lanes["stranger"]
    assert len(layout.threads) == 4


def test_group_bands_stack_and_the_canvas_grows_to_fit():
    people = [_person("a", 1800), _person("b", 1810)]
    groups = (
        Group(key="line-1", label="A", hue="v", members=("a",)),
        Group(key="unattached", label="B", hue="p", members=("b",), unattached=True),
    )
    layout = build(_timeline(people, groups=groups))
    assert [g.key for g in layout.groups] == ["line-1", "unattached"]
    assert layout.groups[0].y < layout.groups[1].y
    assert layout.groups[1].unattached is True
    assert layout.height > layout.groups[1].y + layout.groups[1].height


# --- threads ------------------------------------------------------------------

def test_a_life_shorter_than_a_year_still_gets_a_thread():
    """A child who lived nine days still gets a thread."""
    person = _person("andrej", 1853, 1853, birth_at=1853.62, death_at=1853.64)
    layout = build(_timeline([person]))
    assert layout.threads[0].d != ""


def test_thread_without_a_recorded_death_fades_past_the_last_sighting():
    people = [_person("alive", 1900, last_seen=1930), _person("dead", 1900, 1950)]
    layout = build(_timeline(people))
    threads = {t.res_name: t for t in layout.threads}
    assert threads["alive"].fades is True
    assert threads["dead"].fades is False
    assert threads["dead"].fade_out_from is None
    # The fade starts at the last sighting and the thread stops shortly after —
    # it must not run on to the edge of the canvas.
    assert threads["alive"].fade_out_from is not None
    assert threads["alive"].fade_out_from < threads["alive"].end_x
    assert threads["alive"].end_x < layout.width - MARGIN_RIGHT


def test_a_death_BOUND_is_not_a_death():
    """«умер после 1866» is the last time somebody wrote the person down. It must
    never become a death node — that is the error the whole exporter guards."""
    layout = build(_timeline([_person("bounded", 1841, last_seen=1866)]))
    assert [n for n in layout.nodes if n.kind == NODE_DEATH] == []
    marker = next(n for n in layout.nodes if n.kind == NODE_LAST_SEEN)
    assert marker.year == "1866"
    assert "даты смерти" in marker.detail


def test_a_windowed_birth_fades_in_instead_of_starting_on_a_node():
    layout = build(_timeline([_person("win", 1855, birth_window_to=1888)]))
    thread = layout.threads[0]
    assert thread.fade_in_to is not None
    assert thread.fade_in_to > thread.start_x
    birth = next(n for n in layout.nodes if n.kind == NODE_BIRTH)
    assert birth.hollow is True
    assert birth.year == "между 1855 и 1888"


def test_child_thread_starts_on_the_parents_shared_lane():
    people = [
        _person("father", 1800, unions=("u",)),
        _person("mother", 1802, unions=("u",)),
        _person("child", 1830, parents=("father", "mother"), parent_union="u"),
    ]
    layout = build(_timeline(people, [_marriage("u", ("father", "mother"), 1825,
                                                children=("child",))]))
    lanes = _lanes(layout)
    couple_lane = (lanes["father"] + lanes["mother"]) / 2
    birth = next(n for n in layout.nodes
                 if n.kind == NODE_BIRTH and "Child" in n.title)
    assert abs(birth.y - couple_lane) < 0.01
    assert abs(birth.y - lanes["child"]) > LANE_HEIGHT / 2


# --- nodes --------------------------------------------------------------------

def test_x_is_linear_in_years():
    people = [_person("a", 1800, 1900)]
    layout = build(_timeline(people))
    birth = next(n for n in layout.nodes if n.kind == NODE_BIRTH)
    death = next(n for n in layout.nodes if n.kind == NODE_DEATH)
    assert abs((death.x - birth.x) - 100 * PX_PER_YEAR) < 0.01


def test_same_year_birth_and_death_are_placed_apart_by_their_dates():
    person = _person("andrej", 1853, 1853, birth_at=1853.62, death_at=1853.64)
    layout = build(_timeline([person]))
    birth = next(n for n in layout.nodes if n.kind == NODE_BIRTH)
    death = next(n for n in layout.nodes if n.kind == NODE_DEATH)
    assert death.x > birth.x


def test_circa_birth_and_inferred_marriage_are_hollow():
    people = [_person("a", 1800, circa=True, unions=("u",)),
              _person("b", 1802, unions=("u",))]
    layout = build(_timeline(people, [_marriage("u", ("a", "b"), 1825, inferred=True)]))
    birth = next(n for n in layout.nodes
                 if n.kind == NODE_BIRTH and n.key.startswith("a:"))
    marriage = next(n for n in layout.nodes if n.kind == NODE_MARRIAGE)
    assert birth.hollow is True
    assert birth.year == "ок. 1800"
    assert marriage.hollow is True
    assert "не записан" in marriage.detail


def test_marriage_without_a_year_draws_no_node():
    people = [_person("a", 1800, unions=("u",)), _person("b", 1802, unions=("u",))]
    layout = build(_timeline(people, [_marriage("u", ("a", "b"), None)]))
    assert [n for n in layout.nodes if n.kind == NODE_MARRIAGE] == []


def test_marriage_node_sits_between_the_two_partners():
    people = [_person("a", 1800, unions=("u",)), _person("b", 1802, unions=("u",))]
    layout = build(_timeline(people, [_marriage("u", ("a", "b"), 1825)]))
    lanes = sorted(_lanes(layout).values())
    marriage = next(n for n in layout.nodes if n.kind == NODE_MARRIAGE)
    assert lanes[0] < marriage.y < lanes[1]


def test_marriage_to_an_outsider_names_them_in_the_tooltip():
    people = [_person("a", 1800, name="Иван Марков", unions=("u",))]
    layout = build(_timeline(
        people, [_marriage("u", ("a",), 1825, outside="Прасковья Иванова")]))
    marriage = next(n for n in layout.nodes if n.kind == NODE_MARRIAGE)
    assert "Прасковья Иванова (вне круга родства)" in marriage.detail


def test_death_tooltip_renders_the_age_with_russian_agreement():
    layout = build(_timeline([
        _person("m", 1800, 1875, gender="male", name="Иван"),
        _person("f", 1800, 1801, gender="female", name="Мария"),
    ]))
    deaths = {n.key: n for n in layout.nodes if n.kind == NODE_DEATH}
    assert "Прожил 75 лет" in deaths["m:death"].detail
    assert "Прожила 1 год" in deaths["f:death"].detail


def test_age_of_zero_is_omitted_rather_than_rendered_as_zero_years():
    layout = build(_timeline([_person("baby", 1866, 1866)]))
    death = next(n for n in layout.nodes if n.kind == NODE_DEATH)
    assert "Прожил" not in death.detail


# --- bands and decades --------------------------------------------------------

def test_era_bands_span_their_years_and_events_keep_a_minimum_width():
    bands = (
        Band("era", 1800, 1840, "ясачные крестьяне", ""),
        Band("event", 1812, 1812, "Отечественная война", ""),
    )
    layout = build(_timeline([_person("a", 1800, 1840)], bands=bands))
    era = next(b for b in layout.bands if b.is_era)
    event = next(b for b in layout.bands if not b.is_era)
    assert abs(era.width - 41 * PX_PER_YEAR) < 0.01
    assert event.width >= 14.0


def test_decades_are_labelled_on_round_years():
    layout = build(_timeline([_person("a", 1798, 1832)]))
    assert [d.label for d in layout.decades] == ["1800", "1810", "1820", "1830"]


# --- determinism --------------------------------------------------------------

def test_layout_is_deterministic():
    people = [_person("a", 1800, 1870, unions=("u",)),
              _person("b", 1802, 1880, unions=("u",)),
              _person("c", 1830, parents=("a", "b"), parent_union="u")]
    marriages = [_marriage("u", ("a", "b"), 1825, children=("c",))]
    first = build(_timeline(people, marriages))
    second = build(_timeline(people, marriages))
    assert first == second


def test_empty_timeline_does_not_crash():
    layout = build(_timeline([], groups=()))
    assert layout.threads == ()
    assert layout.width > 0
