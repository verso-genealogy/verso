"""Tests for the familio projection: GeniProfile/GeniUnion → familio resources.

The familio provider is a much narrower model than geni (single Russian name
fields, a `parents` set instead of unions-with-children, a separate
`familio_marriage`, no documents/projects). These tests pin the mapping policy
in `verso.ru.familio.projection` and the HCL rendering in `verso.ru.familio.model`.

Event comments cite RECORDS (`verso.ru.familio.sources.Appearance`): which record
names the person, of what kind and in which slot, is the facts layer's answer,
and the section is the one the translator minted for it. The fixtures state
both; nothing is cut out of the `about` string.
"""
from __future__ import annotations

import pytest

from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.union import GeniUnion
from verso.ru.familio.model import (
    FamilioDate, FamilioMarriage, FamilioPerson, FamilioSource)
from verso.ru.familio.projection import (
    KinResolutionError, _full_modern_name, _shared_marriage_comment, parse_sources, project_kin)
from verso.ru.familio.sources import Appearance, in_about_order


def _profile(res_name, gender="male", **kw) -> GeniProfile:
    return GeniProfile(res_name=res_name, gender=gender, **kw)


def _birth(year, month=None, day=None) -> GeniEvent:
    return GeniEvent(date=GeniDate(year=year, month=month, day=day))


def _cite(kind, slot, year, text, *, title="", age="", record=(), spouse=None,
          children=(), died=False) -> Appearance:
    """One record naming the person — its kind, slot and year, the section the
    translator minted for it, whom the record marries them to and names them
    the parent of, and whether it states their death."""
    return Appearance(kind=kind, slot=slot, year=year, text=text, title=title, age=age,
                      record=record or (kind, year, text), spouse=spouse,
                      children=frozenset(children), died=died)


def _about_of(*sections: Appearance, appendix: str = "") -> str:
    """The about a canonical folds these sections into, as the translator does."""
    return "\n\n        ".join([a.text for a in sections] + ([appendix] if appendix else [])) + "\n"


# --- FamilioDate / rendering -------------------------------------------------

def test_date_renders_only_present_fields():
    assert FamilioDate(1850).to_hcl() == "{ year = 1850 }"
    assert FamilioDate(1850, 3).to_hcl() == "{ year = 1850, month = 3 }"
    assert FamilioDate(1850, 3, 14).to_hcl() == "{ year = 1850, month = 3, day = 14 }"


def test_person_hcl_maps_names_and_required_gender():
    p = FamilioPerson(
        res_name="efim", gender="male", first_name="Ефим",
        last_name="Индюшев", patronymic="Максимович",
        birth_date=FamilioDate(1850),
    )
    tf = p.to_terraform()
    # Raw output is single-space `key = value`; `terraform fmt` (run by the
    # CLI) handles column alignment.
    assert 'resource "familio_person" "efim"' in tf
    assert 'gender = "male"' in tf
    assert 'first_name = "Ефим"' in tf
    assert 'last_name = "Индюшев"' in tf
    assert 'patronymic = "Максимович"' in tf
    # provider ≥ 0.8.0: date nests under a birth block
    assert "birth = {" in tf
    assert "date = { year = 1850 }" in tf
    # no maiden name, no death/christening → those blocks absent
    assert "birth_last_name" not in tf
    assert "death" not in tf
    assert "christening" not in tf


def test_person_import_block_only_when_uuid():
    no_uuid = FamilioPerson(res_name="x", gender="female")
    assert no_uuid.import_block() == ""
    imported = FamilioPerson(res_name="x", gender="female", uuid="abc-123")
    blk = imported.import_block()
    assert "import {" in blk
    assert "to = familio_person.x" in blk
    assert 'id = "abc-123"' in blk


def test_person_parents_render_as_uuid_refs():
    p = FamilioPerson(res_name="child", gender="male", parents=("dad", "mom"))
    tf = p.to_terraform()
    assert "parents = [familio_person.dad.uuid, familio_person.mom.uuid]" in tf


def test_birth_block_groups_date_comment_parents():
    p = FamilioPerson(res_name="kid", gender="male",
                      birth_date=FamilioDate(1910, 1, 9),
                      birth_comment="рождение", parents=("dad", "mom"))
    birth = p.to_terraform().split("birth = {", 1)[1].split("\n  }", 1)[0]
    assert "date = { year = 1910, month = 1, day = 9 }" in birth
    assert "comment = trimspace(<<-EOT" in birth
    assert "parents = [familio_person.dad.uuid, familio_person.mom.uuid]" in birth


def test_marriage_hcl():
    m = FamilioMarriage(res_name="a_and_b", partner_1="a", partner_2="b",
                        marriage_date=FamilioDate(1875, 5, 12))
    tf = m.to_terraform()
    assert 'resource "familio_marriage" "a_and_b"' in tf
    assert "partners = [familio_person.a.uuid, familio_person.b.uuid]" in tf
    assert "marriage_date = { year = 1875, month = 5, day = 12 }" in tf


# --- projection --------------------------------------------------------------

def test_project_maps_profile_fields():
    profiles = {
        "efim": _profile("efim", first_name="Ефим", middle_name="Максимович",
                         last_name="Индюшев", birth=_birth(1850),
                         death=GeniEvent(date=GeniDate(year=1911))),
    }
    persons, marriages = project_kin(profiles, {}, {"efim": None})
    assert len(persons) == 1
    p = persons[0]
    assert p.patronymic == "Максимович"   # from middle_name
    assert p.first_name == "Ефим"
    assert p.birth_date == FamilioDate(1850, calendar="julian")
    assert p.death_date == FamilioDate(1911, calendar="julian")
    assert p.uuid is None
    assert marriages == []


def test_project_carries_uuid_for_import():
    profiles = {"efim": _profile("efim", first_name="Ефим")}
    persons, _ = project_kin(profiles, {}, {"efim": "uuid-1"})
    assert persons[0].uuid == "uuid-1"


def test_maiden_name_only_when_distinct_from_last_name():
    # married woman: last_name (married) differs from birth_last_name (maiden)
    profiles = {
        "anna": _profile("anna", gender="female", first_name="Анна",
                         last_name="Индюшева", birth_last_name="Ляпкина"),
        "klava": _profile("klava", gender="female", first_name="Клава",
                          last_name="Индюшева", birth_last_name="Индюшева"),
    }
    persons, _ = project_kin(profiles, {}, {"anna": None, "klava": None})
    by = {p.res_name: p for p in persons}
    assert by["anna"].birth_last_name == "Ляпкина"
    assert by["klava"].birth_last_name == ""   # same as last_name → dropped


def test_missing_gender_raises():
    profiles = {"x": _profile("x", gender="")}
    with pytest.raises(ValueError):
        project_kin(profiles, {}, {"x": None})


def test_unknown_kin_res_name_raises():
    profiles = {"efim": _profile("efim")}
    with pytest.raises(KinResolutionError):
        project_kin(profiles, {}, {"efim": None, "ghost": None})


def test_range_bound_death_becomes_a_range():
    # a census "alive after 1897" bound is published as range="after" (an honest
    # death bound), NOT a false exact death and NOT dropped
    after = GeniEvent(date=GeniDate(year=1897, date_range="after"))
    profiles = {"x": _profile("x", first_name="Икс", death=after)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].death_date == FamilioDate(1897, date_range="after", calendar="julian")


def test_circa_year_is_marked_circa():
    circa = GeniEvent(date=GeniDate(year=1846, circa=True))
    profiles = {"x": _profile("x", first_name="Икс", birth=circa)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date == FamilioDate(1846, circa=True, calendar="julian")


def test_between_range_carries_endpoint():
    span = GeniEvent(date=GeniDate(year=1846, date_range="between", end_year=1850))
    profiles = {"x": _profile("x", first_name="Икс", birth=span)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date == FamilioDate(
        1846, date_range="between", end_year=1850, calendar="julian")


def test_between_range_drops_approximate_endpoint():
    # the provider rejects an *approximate* range (range + circa endpoint:
    # "Approximate range not supported"), so end_circa is dropped — the span
    # stays a definite "between" bound
    span = GeniEvent(date=GeniDate(year=1843, month=7, date_range="between",
                                   end_year=1844, end_circa=True))
    profiles = {"x": _profile("x", first_name="Икс", birth=span)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date == FamilioDate(
        1843, month=7, date_range="between", end_year=1844, calendar="julian")


def test_between_without_endpoint_degrades_to_plain_date():
    # a malformed "between" with no end_year can't be a valid familio range
    span = GeniEvent(date=GeniDate(year=1846, date_range="between"))
    profiles = {"x": _profile("x", first_name="Икс", birth=span)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date == FamilioDate(1846, calendar="julian")


def test_pre_reform_date_is_julian():
    # ≤1917 dates are Old Style → calendar="julian"
    profiles = {"x": _profile("x", first_name="Икс", birth=_birth(1917, 12, 31))}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date is not None
    assert persons[0].birth_date.calendar == "julian"


def test_post_reform_date_is_gregorian():
    # 1918-onward dates are New Style → gregorian default (no calendar stamp)
    profiles = {"x": _profile("x", first_name="Икс", birth=_birth(1918, 5, 20))}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date is not None
    assert persons[0].birth_date.calendar is None


def test_date_renders_circa_and_range_hcl():
    assert FamilioDate(1846, circa=True).to_hcl() == "{ year = 1846, circa = true }"
    assert FamilioDate(1897, date_range="after").to_hcl() == '{ year = 1897, range = "after" }'
    assert (
        FamilioDate(1846, date_range="between", end_year=1850).to_hcl()
        == '{ year = 1846, range = "between", end_year = 1850 }'
    )
    assert (
        FamilioDate(1850, calendar="julian").to_hcl()
        == '{ year = 1850, calendar = "julian" }'
    )


def test_no_date_means_no_date_block():
    profiles = {"x": _profile("x", first_name="Икс")}  # no birth event
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].birth_date is None


# --- event comments (per-event records of the person) -----------------------

_BIRTH = _cite("birth", "child", 1910,
               "<strong>МК Нижняя Яичница 1910:</strong> рождение\n"
               "        Титул/звание отца: крестьянин\n"
               "        Комментарий из МК:\n"
               "        >Имена в МК: Татьяна")
# The translator heads a burial «умерший»/«умершая»; the role-word regex this
# replaced looked for «смерт» and never found one (61 kin without a death comment).
_DEATH = _cite("death", "deceased", 1941,
               "<strong>МК Нижняя Яичница 1941:</strong> умерший\n"
               "        >Комментарий: умер")


def test_event_comments_route_birth_death_and_strip_html():
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([_BIRTH, _DEATH])
    assert c["birth"].startswith("МК Нижняя Яичница 1910: рождение")   # direct record first
    assert "Имена в МК: Татьяна" in c["birth"]
    assert "<strong>" not in c["birth"] and not c["birth"].lstrip().startswith(">")
    # death (age at death) is an INDIRECT birth source → also in the birth comment
    assert "МК Нижняя Яичница 1941: умерший" in c["birth"]
    # christening shares only the birth RECORD, not the indirect death source
    assert c["christening"].startswith("МК Нижняя Яичница 1910: рождение")
    assert "умерший" not in c["christening"]
    assert c["death"].startswith("МК Нижняя Яичница 1941: умерший")
    assert "marriage" not in c                 # the union's, which knows the spouse


def test_event_comments_birth_gains_census_and_marriage_drop_parent_role():
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([
        _cite("census", "member13", 1897,
              "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 13\n"
              "        >ФИО: Василий"),
        _cite("birth", "father", 1910,
              "<strong>МК Нижняя Яичница 1910:</strong> отец ребенка\n"
              "        >Имена в МК: Татьяна; Василий"),
        _cite("marriage", "groom", 1908,
              "<strong>МК Нижняя Яичница 1908:</strong> жених\n"
              "        >Невеста: Параскева"),
    ])
    # census enumeration + own marriage record the person's age ⇒ INDIRECT birth sources
    assert "1-я всеобщая перепись Нижняя Яичница 1897: семья 13" in c["birth"]
    assert "1908: жених" in c["birth"]
    # a parent role in someone else's birth carries no age of this person → dropped
    assert "отец ребенка" not in c["birth"] and "Татьяна" not in c["birth"]
    assert c["christening"] == ""              # no own birth record → no christening


def test_census_age_line_flows_into_birth_comment_and_biography():
    # The census about block carries a "Возраст: N" line right under the
    # header; it must pass through UNCHANGED into both the census-derived
    # birth comment and the biography (no marriage-style relabeling).
    from verso.ru.familio.projection import _about_biography, _event_comments
    roll = _cite("census", "member5", 1858,
                 "<strong>РС Маниловка 1858:</strong> семья 17\n"
                 "        Возраст: 33\n"
                 "        Титул/звание: крестьянка помещика Тентетникова\n"
                 "        Комментарий из РС 1858 года:\n"
                 "        >ИО в документе: Екатерина Иванова")
    c = _event_comments([roll])
    assert "РС Маниловка 1858: семья 17" in c["birth"]
    assert "Возраст: 33" in c["birth"]
    bio = _about_biography(_about_of(roll))
    assert "Возраст: 33" in bio
    # census age is NOT rewritten the way marriage ages are
    assert "Возраст жениха" not in c["birth"] and "Возраст жениха" not in bio


def test_a_confession_list_dvor_is_a_birth_source_too():
    """An ИР counts its people by «двор», not «семья»; the old role-word test
    matched «семья» only, so a confession list's age never reached the birth."""
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([_cite("census", "member3", 1828,
                               "<strong>Исповедная роспись Заманиловка 1828:</strong> двор 94\n"
                               "        Возраст: 20")])
    assert "двор 94" in c["birth"] and "Возраст: 20" in c["birth"]


def test_a_roll_listing_the_member_dead_is_the_death_source():
    """A roll's «умер (1846)» is where the circa death comes from, so with no
    burial it is the death's comment — Заманиловка's 1850 roll folded onto the
    1834 members left their deaths dated and uncited."""
    from verso.ru.familio.projection import _event_comments
    roll_1834 = _cite("census", "member1", 1834,
                      "<strong>РС Заманиловка 1834:</strong> семья 523\n        Возраст: 61")
    roll_1850 = _cite("census", "member1", 1850,
                      "<strong>РС Заманиловка 1850:</strong> семья 411\n"
                      "        Причина, основание убытия: умер (1846)", died=True)
    c = _event_comments([roll_1834, roll_1850])
    assert "семья 411" in c["death"] and "семья 523" not in c["death"]
    assert "семья 523" in c["birth"] and "семья 411" in c["birth"]


def test_a_burial_outranks_the_roll_that_lists_the_death():
    from verso.ru.familio.projection import _event_comments
    roll = _cite("census", "member1", 1850,
                 "<strong>РС Заманиловка 1850:</strong> семья 411\n"
                 "        Причина, основание убытия: умер (1846)", died=True)
    burial = _cite("death", "deceased", 1846,
                   "<strong>МК Заманиловка 1846:</strong> умерший")
    c = _event_comments([roll, burial])
    assert "умерший" in c["death"] and "семья 411" not in c["death"]


def test_birth_comment_collects_direct_then_all_indirect_sources():
    # own birth (direct) + census + marriage + death (all age-bearing → indirect),
    # in that order; christening keeps only the direct birth record.
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([
        _cite("birth", "child", 1890,
              "<strong>МК Нижняя Яичница 1890:</strong> рождение\n        >Имена в МК: Василий"),
        _cite("census", "member4", 1897,
              "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 13\n"
              "        >ФИО: Василий Андреев"),
        _cite("marriage", "groom", 1908,
              "<strong>МК Нижняя Яичница 1908:</strong> жених\n        >Невеста: Параскева"),
        _DEATH,
    ])
    b = c["birth"]
    assert b.startswith("МК Нижняя Яичница 1890: рождение")        # direct record first
    assert "1897: семья 13" in b and "1908: жених" in b and "1941: умерший" in b
    assert b.index("семья 13") < b.index("1908: жених") < b.index("1941: умерший")
    assert c["christening"] == "МК Нижняя Яичница 1890: рождение\nИмена в МК: Василий"
    assert c["death"].startswith("МК Нижняя Яичница 1941: умерший")


def test_birth_comment_for_census_only_person():
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([_cite("census", "member7", 1897,
                               "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 7\n"
                               "        >ФИО в документе: Петр Иосифов Ляпкин")])
    assert c["birth"].startswith("1-я всеобщая перепись Нижняя Яичница 1897: семья 7")
    assert "Петр Иосифов Ляпкин" in c["birth"]
    assert c["christening"] == ""              # no own birth record


def test_birth_comment_excludes_godparent_witness_parent_and_relative_roles():
    # roles in OTHER people's records carry no event of this person. «отец
    # невесты» contains «невест»: the role-word regex took it for the person's
    # own wedding (Заманиловка: a daughter's 1839 wedding on her father).
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([
        _cite("birth", "god_parent1", 1900,
              "<strong>МК Нижняя Яичница 1900:</strong> восприемник на крещении\n        >x"),
        _cite("marriage", "witness1", 1905,
              "<strong>МК Нижняя Яичница 1905:</strong> поручитель на свадьбе\n        >y"),
        _cite("birth", "father", 1907,
              "<strong>МК Нижняя Яичница 1907:</strong> отец ребенка\n        >z"),
        _cite("marriage", "relative1", 1839,
              "<strong>МК Заманиловка 1839:</strong> отец невесты\n        >w"),
    ])
    assert c["birth"] == "" and c["death"] == ""


def test_a_christening_record_is_the_persons_own_birth():
    """A `christening()` entry is headed «крещение»; the role-word regex looked
    for «рожден» and gave such a person no birth comment and no birth place."""
    from verso.ru.familio.projection import _event_comments
    c = _event_comments([_cite("birth", "child", 1893,
                               "<strong>МК Нижняя Яичница 1893:</strong> крещение\n        >x")])
    assert c["birth"].startswith("МК Нижняя Яичница 1893: крещение")
    assert c["christening"].startswith("МК Нижняя Яичница 1893: крещение")


def test_an_appendix_is_no_record():
    born = _cite("birth", "child", 1910,
                 "<strong>МК Нижняя Яичница 1910:</strong> рождение\n        >Имена в МК: Татьяна")
    about = _about_of(born, appendix="\'\'\'Memorial\'\'\' Родился в 1889 г. Умер 03.02.41")
    profiles = {"p": _profile("p", first_name="П", about=about)}
    persons, _ = project_kin(profiles, {}, {"p": None}, appearances={"p": [born]})
    assert persons[0].birth_comment == "МК Нижняя Яичница 1910: рождение\nИмена в МК: Татьяна"
    assert "Memorial" in persons[0].biography


def test_sections_stand_in_about_order_and_only_if_they_stand_there():
    """Where a record's section lies is found by its known text; one the fold
    dropped (contained in another) and one absent from the about are dropped."""
    a = _cite("census", "member1", 1897, "<strong>РС Т 1897:</strong> семья 1\n        >a")
    b = _cite("birth", "child", 1890, "<strong>МК Т 1890:</strong> рождение\n        >b")
    inner = _cite("birth", "father", 1890, "<strong>МК Т 1890:</strong> рождение")
    stray = _cite("death", "deceased", 1950, "<strong>МК Т 1950:</strong> умерший")
    about = _about_of(b, a)
    assert in_about_order([a, inner, stray, b], about) == [b, a]


# --- biography (the whole combined all-sources narrative) --------------------

def test_about_biography_keeps_all_sections_and_appendix_strips_markup():
    from verso.ru.familio.projection import _about_biography
    about = (
        "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 13\n"
        "        >ФИО: Василий Андреев\n"
        "\n"
        "        <strong>МК Нижняя Яичница 1908:</strong> жених\n"
        "        >Невеста: Параскева\n"
        "\n"
        "        '''Memorial''' Арестован 18.11.1937. Умер 03.02.1941.\n"
    )
    bio = _about_biography(about)
    # every section is present, in document order
    assert bio.index("1897: семья 13") < bio.index("1908: жених") < bio.index("Memorial")
    # markup stripped: no <strong> tags, no leading > quote markers
    assert "<strong>" not in bio
    assert not any(ln.startswith(">") for ln in bio.split("\n"))
    # the trailing memorial appendix is kept (unlike _event_comments)
    assert "Арестован 18.11.1937" in bio
    # sections separated by a single blank line, no double blanks
    assert "\n\n\n" not in bio


def test_about_biography_empty_for_no_about():
    from verso.ru.familio.projection import _about_biography
    assert _about_biography(None) == ""
    assert _about_biography("") == ""
    assert _about_biography("   \n  \n") == ""


def test_project_sets_biography_to_full_about():
    roll = _cite("census", "member7", 1897,
                 "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 7\n        >ФИО: Петр")
    father = _cite("birth", "father", 1908,
                   "<strong>МК Нижняя Яичница 1908:</strong> отец ребенка\n        >Имена в МК: дочь Анна")
    profiles = {"p": _profile("p", first_name="Петр", about=_about_of(roll, father))}
    persons, _ = project_kin(profiles, {}, {"p": None}, appearances={"p": [roll, father]})
    bio = persons[0].biography
    # biography is the WHOLE about — even the parent-role section that the
    # filtered birth comment deliberately drops
    assert "1897: семья 7" in bio
    assert "отец ребенка" in bio and "дочь Анна" in bio
    # the per-event birth comment still excludes that parent-role section
    assert "отец ребенка" not in persons[0].birth_comment


def test_person_renders_biography_heredoc():
    p = FamilioPerson(res_name="x", gender="male", biography="строка1\nстрока2")
    tf = p.to_terraform()
    assert "biography = trimspace(<<-EOT" in tf
    assert "строка1" in tf and "строка2" in tf
    # omitted when empty
    assert "biography" not in FamilioPerson(res_name="y", gender="male").to_terraform()


def test_person_renders_uuid_parent_as_literal():
    from verso.ru.familio.model import is_uuid
    u = "00000000-0000-4000-8000-0deb39eeaf25"
    assert is_uuid(u) and not is_uuid("gavrila_petrovich_sidorov")
    p = FamilioPerson(res_name="x", gender="male", birth_date=FamilioDate(year=1846),
                      parents=("gavrila_petrovich_sidorov", u))
    tf = p.to_terraform()
    # kin parent → resource ref; familio-only parent → bare UUID literal
    assert "familio_person.gavrila_petrovich_sidorov.uuid" in tf
    assert f'"{u}"' in tf


def test_parent_override_accepts_uuid_for_unmanaged_parent():
    profiles = {
        "kid": _profile("kid", first_name="Васса", birth=_birth(1846)),
        "dad": _profile("dad", first_name="Гавриил", birth=_birth(1819)),
    }
    persons, _ = project_kin(
        profiles, {}, {"kid": None, "dad": None},
        parent_overrides={"kid": ("dad", "00000000-0000-4000-8000-0deb39eeaf25")},
    )
    kid = {p.res_name: p for p in persons}["kid"]
    # both the managed res_name and the bare familio UUID survive the filter
    assert kid.parents == ("dad", "00000000-0000-4000-8000-0deb39eeaf25")


def test_project_sets_event_comments_gated_on_baptism():
    anc_born = _cite("birth", "child", 1850, "<strong>МК Нижняя Яичница 1850:</strong> рождение\n        >x")
    profiles = {
        "kid": _profile("kid", first_name="Икс", birth=_birth(1910),
                        baptism=_birth(1910), about=_about_of(_BIRTH, _DEATH)),
        "anc": _profile("anc", first_name="Дед", birth=_birth(1850), about=_about_of(anc_born)),
    }
    persons, _ = project_kin(profiles, {}, {"kid": None, "anc": None},
                             appearances={"kid": [_BIRTH, _DEATH], "anc": [anc_born]})
    by = {p.res_name: p for p in persons}
    assert "рождение" in by["kid"].birth_comment
    assert "рождение" in by["kid"].christening_comment   # has a baptism event
    assert by["anc"].christening_comment == ""           # no baptism → dropped
    assert by["kid"].death_comment.startswith("МК Нижняя Яичница 1941: умерший")


def test_marriage_comment_filtered_to_this_wedding_year():
    # a twice-married groom: the 1850 marriage must NOT carry the 1839 section
    first = _cite("marriage", "groom", 1839,
                  "<strong>МК Заманиловка 1839:</strong> жених\n        >Невеста: Ирина Григорьева")
    second = _cite("marriage", "groom", 1850,
                   "<strong>МК Заманиловка 1850:</strong> жених\n        >Невеста: Феодора Иванова")
    profiles = {
        "h": _profile("h", first_name="Емельян", about=_about_of(first, second)),
        "w": _profile("w", gender="female", first_name="Феодора"),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="h", partner_2="w",
                             marriage=_birth(1850))}
    _, marriages = project_kin(profiles, unions, {"h": None, "w": None},
                               appearances={"h": [first, second]})
    assert len(marriages) == 1
    c = marriages[0].comment
    assert "1850: жених" in c and "Феодора Иванова" in c
    assert "1839" not in c and "Ирина Григорьева" not in c   # other wedding excluded


def test_marriage_comment_from_partner_about():
    """An undated union finds its wedding by the spouse the record names."""
    wed = _cite("marriage", "groom", 1908, "<strong>МК Нижняя Яичница 1908:</strong> жених\n        >Невеста: W",
                spouse="w")
    profiles = {
        "h": _profile("h", first_name="H", about=_about_of(wed)),
        "w": _profile("w", gender="female", first_name="W"),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="h", partner_2="w")}
    _, marriages = project_kin(profiles, unions, {"h": None, "w": None},
                               appearances={"h": [wed]})
    assert len(marriages) == 1
    assert "жених" in marriages[0].comment


def _couple(h_cites, w_cites=(), *, children=(), marriage=None):
    profiles = {
        "h": _profile("h", first_name="Фома", about=_about_of(*h_cites)),
        "w": _profile("w", gender="female", first_name="Дарья", about=_about_of(*w_cites)),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="h", partner_2="w",
                             children=set(children), marriage=marriage)}
    _, marriages = project_kin(profiles, unions, {"h": None, "w": None},
                               appearances={"h": list(h_cites), "w": list(w_cites)})
    assert len(marriages) == 1
    return marriages[0].comment


_SON_WED = _cite("marriage", "relative7", 1851,
                 "<strong>МК Горюхино 1851:</strong> отец жениха\n"
                 "        Титул/звание: казенный крестьянин\n"
                 "        >Имена в МК: Михаилъ Фоминъ Видоплясовъ; Фома Петровъ Видоплясовъ",
                 record=("1851", 3), children={"son"})


def test_a_relatives_wedding_is_not_the_couples():
    """A wedding at which the record names him the parent of someone who is
    not this union's child says nothing of this marriage."""
    assert _couple([_SON_WED], children={"other"}) == ""


def test_a_childs_wedding_attests_a_couple_without_their_own():
    """A couple married before the books begin has no wedding in the corpus;
    their son's, naming the father «отец жениха», is the record that attests
    the family. The role-word regex put it there by accident, and the first
    reading of the records dropped it."""
    c = _couple([_SON_WED], children={"son"})
    assert c.startswith("МК Горюхино 1851: отец жениха")
    assert "Михаилъ Фоминъ" in c


def test_another_spouses_wedding_is_not_this_marriage():
    """The husband's earlier wedding married him to Параскева Ивановна, his first
    wife: it is no source of his undated marriage to Дарья."""
    first = _cite("marriage", "groom", 1818,
                  "<strong>МК Горюхино 1818:</strong> жених\n        >Имена в МК: Фома Петров; Параскева Иванова",
                  spouse="praskovja")
    c = _couple([first, _SON_WED], children={"son"})
    assert "1818" not in c and "Параскева" not in c
    assert c.startswith("МК Горюхино 1851: отец жениха")


def test_a_couples_own_wedding_leaves_out_the_childrens():
    own = _cite("marriage", "groom", 1830,
                "<strong>МК Горюхино 1830:</strong> жених\n        >Невеста: Дарья", spouse="w")
    c = _couple([own, _SON_WED], children={"son"})
    assert "1830: жених" in c and "1851" not in c


def test_a_childs_wedding_naming_both_parents_is_cited_once():
    mother = _cite("marriage", "relative8", 1851,
                   "<strong>МК Горюхино 1851:</strong> мать жениха\n        >Имена в МК: Михаилъ",
                   record=("1851", 3), children={"son"})
    c = _couple([_SON_WED], [mother], children={"son"})
    assert "отец жениха" in c and "мать жениха" not in c


def test_death_place_from_real_death_record_location():
    from verso.core import places
    locations = places.current().bodies
    nv = locations["Нижняя Яичница"]
    profiles = {
        # real death record → death event carries the location
        "dead": _profile("dead", first_name="Покойник",
                         death=GeniEvent(date=GeniDate(year=1910), location=nv)),
        # derived "after"-bound death → date only, no location
        "bound": _profile("bound", first_name="Живой",
                          death=GeniEvent(date=GeniDate(year=1910,
                                                        date_range="after"))),
    }
    persons, _ = project_kin(profiles, {}, {"dead": None, "bound": None})
    by = {p.res_name: p for p in persons}
    assert by["dead"].death_place == "local.settlement_nizhnjaja_jaichnitsa"
    assert by["bound"].death_place == ""
    hcl = by["dead"].to_terraform()
    assert "place = local.settlement_nizhnjaja_jaichnitsa" in hcl


def test_marriage_place_from_union_marriage_location():
    from verso.core import places
    locations = places.current().bodies
    profiles = {
        "h": _profile("h", first_name="H"),
        "w": _profile("w", gender="female", first_name="W"),
    }
    unions = {"u": GeniUnion(
        res_name="u", partner_1="h", partner_2="w",
        marriage=GeniEvent(date=GeniDate(year=1908),
                           location=locations["Нижняя Яичница"]))}
    _, marriages = project_kin(profiles, unions, {"h": None, "w": None})
    assert len(marriages) == 1
    assert marriages[0].place == "local.settlement_nizhnjaja_jaichnitsa"
    hcl = marriages[0].to_terraform()
    assert "place = local.settlement_nizhnjaja_jaichnitsa" in hcl  # unquoted ref


def test_marriage_place_empty_when_location_unmapped():
    profiles = {
        "h": _profile("h", first_name="H"),
        "w": _profile("w", gender="female", first_name="W"),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="h", partner_2="w",
                             marriage=_birth(1908))}   # no location
    _, marriages = project_kin(profiles, unions, {"h": None, "w": None})
    assert marriages[0].place == ""
    assert "place" not in marriages[0].to_terraform().replace(
        "marriage_date", "")   # no place line emitted


# --- shared (both-spouse) marriage comment ----------------------------------

_NAMES = ">Имена в МК: Емельян Емельянов Чичиков; Ирина Григорьева"


def _wed(slot, *, title="", age=""):
    role = {"groom": "жених", "bride": "невеста"}[slot]
    lines = [f"<strong>МК Заманиловка 1839:</strong> {role}"]
    if age:
        lines.append(f"Возраст: {age}")
    if title:
        lines.append(f"Титул/звание: {title}")
    lines += ["Комментарий из МК:", _NAMES]
    return _cite("marriage", slot, 1839, "\n        ".join(lines), title=title, age=age)


_GROOM = _wed("groom", title="экономический крестьянин")
_BRIDE = _wed("bride", title="экономическая крестьянка")


def test_shared_marriage_comment_merges_both_names_and_titles():
    out = _shared_marriage_comment(
        [_GROOM], [_BRIDE],
        groom_name="Емельян Емельянович Чичиков",
        bride_name="Ирина Григорьевна Чичикова",
    )
    assert "Жених: Емельян Емельянович Чичиков, экономический крестьянин" in out
    assert "Невеста: Ирина Григорьевна Чичикова, экономическая крестьянка" in out
    assert out.count("Имена в МК:") == 1                 # shared tail not duplicated
    assert out.splitlines()[0] == "МК Заманиловка 1839"    # header, role suffix stripped
    assert "жених" not in out and "невеста" not in out   # lowercase role tags gone
    assert "Комментарий из МК:" in out
    assert "Титул/звание:" not in out                    # moved onto the role lines


def test_shared_marriage_comment_labels_groom_age():
    out = _shared_marriage_comment(
        [_wed("groom", title="экономический крестьянин", age="18 лет")], [_BRIDE],
        groom_name="Емельян Емельянович Чичиков",
        bride_name="Ирина Григорьевна Чичикова",
    )
    # The groom's age must be attributed to him, not float unlabeled after
    # the Невеста line (where it reads as the bride's).
    assert "Возраст жениха: 18 лет" in out
    assert "\nВозраст: 18" not in out
    assert out.count("Имена в МК:") == 1


def test_shared_marriage_comment_keeps_both_ages():
    out = _shared_marriage_comment(
        [_wed("groom", age="18 лет")], [_wed("bride", age="17 лет")],
        groom_name="Емельян Емельянович Чичиков",
        bride_name="Ирина Григорьевна Чичикова",
    )
    assert "Возраст жениха: 18 лет" in out
    assert "Возраст невесты: 17 лет" in out    # bride's age must not be dropped


def test_shared_marriage_comment_falls_back_to_single_partner():
    out = _shared_marriage_comment(
        [_GROOM], [],
        groom_name="Емельян Емельянович Чичиков", bride_name="",
    )
    assert out == ("МК Заманиловка 1839: жених\nТитул/звание: экономический крестьянин\n"
                   "Комментарий из МК:\nИмена в МК: Емельян Емельянов Чичиков; Ирина Григорьева")


def test_shared_marriage_comment_omits_missing_title():
    out = _shared_marriage_comment(
        [_wed("groom")], [_BRIDE],
        groom_name="Емельян Емельянович Чичиков",
        bride_name="Ирина Григорьевна Чичикова",
    )
    assert "Жених: Емельян Емельянович Чичиков\n" in out       # no ", <title>"
    assert "Жених: Емельян Емельянович Чичиков," not in out    # no dangling comma
    assert "Невеста: Ирина Григорьевна Чичикова, экономическая крестьянка" in out


def test_full_modern_name_uses_maiden_for_bride():
    bride = FamilioPerson(res_name="b", gender="female", first_name="Ирина",
                          patronymic="Григорьевна", last_name="Иванова",
                          birth_last_name="Чичикова")
    assert _full_modern_name(bride, maiden=True) == "Ирина Григорьевна Чичикова"
    assert _full_modern_name(bride, maiden=False) == "Ирина Григорьевна Иванова"
    # empty parts skipped — a person with no patronymic yields no double space
    no_patr = FamilioPerson(res_name="x", gender="male",
                            first_name="Иван", last_name="Петров")
    assert _full_modern_name(no_patr) == "Иван Петров"


def test_marriage_comment_merges_both_spouses():
    profiles = {
        "g": _profile("g", first_name="Емельян", middle_name="Емельянович",
                      last_name="Чичиков", about=_about_of(_GROOM)),
        "b": _profile("b", gender="female", first_name="Ирина",
                      middle_name="Григорьевна", last_name="Чичикова",
                      about=_about_of(_BRIDE)),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="g", partner_2="b",
                             marriage=_birth(1839))}
    _, marriages = project_kin(profiles, unions, {"g": None, "b": None},
                               appearances={"g": [_GROOM], "b": [_BRIDE]})
    assert len(marriages) == 1
    c = marriages[0].comment
    assert "Жених: Емельян Емельянович Чичиков, экономический крестьянин" in c
    assert "Невеста: Ирина Григорьевна Чичикова, экономическая крестьянка" in c
    assert c.count("Имена в МК:") == 1


def test_person_and_marriage_render_comment_heredoc():
    p = FamilioPerson(res_name="x", gender="male", birth_comment="line1\nline2")
    tf = p.to_terraform()
    assert "birth = {" in tf                         # comment nests under birth
    assert "comment = trimspace(<<-EOT" in tf
    assert "line1" in tf and "line2" in tf
    m = FamilioMarriage(res_name="a_and_b", partner_1="a", partner_2="b",
                        comment="венчание")
    assert "comment = trimspace(<<-EOT" in m.to_terraform()


# --- "after"-bounded death cites its latest source --------------------------

def _father_in(year, *body):
    return _cite("birth", "father", year,
                 "\n        ".join([f"<strong>МК Нижняя Яичница {year}:</strong> отец ребенка", *body]))


def test_after_death_comment_cites_latest_parent_role_source():
    # Андрей case: died "after 20.11.1908" because last seen as a father in 1908.
    from verso.ru.familio.projection import _latest_source_comment
    cited = [_father_in(1900, ">Имена в МК: Алексей; Андрей"),
             _father_in(1908, ">Титул/звание: крестьянин",
                        ">Имена в МК: Екатерина; Андрей Иосифов Ляпкин")]
    after = GeniEvent(date=GeniDate(year=1908, month=11, day=20, date_range="after"))
    profiles = {"andrej": _profile("andrej", first_name="Андрей", death=after,
                                   about=_about_of(*cited))}
    persons, _ = project_kin(profiles, {}, {"andrej": None}, appearances={"andrej": cited})
    dc = persons[0].death_comment
    # the latest (1908) parent-role section — one `_event_comments` normally drops
    assert dc.startswith("МК Нижняя Яичница 1908: отец ребенка")
    assert "Имена в МК: Екатерина" in dc
    assert "1900" not in dc
    assert _latest_source_comment(cited).startswith("МК Нижняя Яичница 1908: отец ребенка")


def test_after_death_comment_from_census_source():
    roll = _cite("census", "member7", 1897,
                 "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 7\n"
                 "        >ФИО в документе: Петр Иосифов Ляпкин")
    after = GeniEvent(date=GeniDate(year=1897, date_range="after"))
    profiles = {"petr": _profile("petr", first_name="Петр", death=after, about=_about_of(roll))}
    persons, _ = project_kin(profiles, {}, {"petr": None}, appearances={"petr": [roll]})
    dc = persons[0].death_comment
    assert dc.startswith("1-я всеобщая перепись Нижняя Яичница 1897: семья 7")
    assert "Петр Иосифов Ляпкин" in dc


def test_after_death_comment_uses_latest_section_not_death_year():
    # death bound is a manual "after 1916", but the latest real record is 1910 →
    # cite the latest known source, not the (sourceless) bound year.
    cited = [_father_in(1908, ">x"), _father_in(1910, ">Имена в МК: Иван")]
    after = GeniEvent(date=GeniDate(year=1916, date_range="after"))
    profiles = {"p": _profile("p", first_name="П", death=after, about=_about_of(*cited))}
    persons, _ = project_kin(profiles, {}, {"p": None}, appearances={"p": cited})
    dc = persons[0].death_comment
    assert dc.startswith("МК Нижняя Яичница 1910: отец ребенка")
    assert "Имена в МК: Иван" in dc


def test_real_death_section_not_overridden():
    # an exact death documented by its burial record keeps that comment; the
    # "after" fallback does not fire (death is not range-bounded).
    roll = _cite("census", "member7", 1897,
                 "<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 7\n        >ФИО: Икс")
    buried = _cite("death", "deceased", 1905,
                   "<strong>МК Нижняя Яичница 1905:</strong> умерший\n        >Комментарий: умер")
    profiles = {"x": _profile("x", first_name="Икс",
                              death=GeniEvent(date=GeniDate(year=1905)),
                              about=_about_of(roll, buried))}
    persons, _ = project_kin(profiles, {}, {"x": None}, appearances={"x": [roll, buried]})
    dc = persons[0].death_comment
    assert dc.startswith("МК Нижняя Яичница 1905: умерший")
    assert "семья 7" not in dc


def test_exact_death_no_range_gets_no_fallback_comment():
    about = ("<strong>1-я всеобщая перепись Нижняя Яичница 1897:</strong> семья 7\n"
             "        >ФИО: Икс\n")
    profiles = {"x": _profile("x", first_name="Икс",
                              death=GeniEvent(date=GeniDate(year=1897)), about=about)}
    persons, _ = project_kin(profiles, {}, {"x": None})
    assert persons[0].death_comment == ""   # not range="after" → no source fallback


# --- parents + marriage derivation from unions -------------------------------

def test_parents_derived_and_filtered_to_kin():
    profiles = {
        "dad": _profile("dad", first_name="Папа"),
        "mom": _profile("mom", gender="female", first_name="Мама"),
        "kid": _profile("kid", first_name="Сын"),
        "neighbor": _profile("neighbor", first_name="Сосед"),
    }
    unions = {
        "u1": GeniUnion(res_name="u1", partner_1="dad", partner_2="mom",
                        children={"kid"}),
        # a union where one partner (neighbor) is NOT kin → dropped, not dangling
        "u2": GeniUnion(res_name="u2", partner_1="dad", partner_2="neighbor",
                        children={"kid"}),
    }
    kin = {"dad": None, "mom": None, "kid": None}  # neighbor NOT kin
    persons, _ = project_kin(profiles, unions, kin)
    kid = next(p for p in persons if p.res_name == "kid")
    assert set(kid.parents) == {"dad", "mom"}   # neighbor never appears


def test_marriage_only_when_both_partners_kin():
    profiles = {
        "h": _profile("h", first_name="Муж"),
        "w": _profile("w", gender="female", first_name="Жена"),
        "outsider": _profile("outsider", gender="female", first_name="Чужая"),
    }
    unions = {
        "u1": GeniUnion(res_name="u1", partner_1="h", partner_2="w",
                        marriage=GeniEvent(date=GeniDate(year=1875))),
        "u2": GeniUnion(res_name="u2", partner_1="h", partner_2="outsider"),
    }
    kin = {"h": None, "w": None}  # outsider NOT kin
    _, marriages = project_kin(profiles, unions, kin)
    assert len(marriages) == 1
    assert {marriages[0].partner_1, marriages[0].partner_2} == {"h", "w"}
    assert marriages[0].marriage_date == FamilioDate(1875, calendar="julian")


def test_union_refs_normalised_via_resolve():
    # union still references a per-record name; resolve() maps it to canonical
    profiles = {
        "dad_canon": _profile("dad_canon", first_name="Папа"),
        "kid": _profile("kid", first_name="Сын"),
    }
    unions = {
        "u1": GeniUnion(res_name="u1", partner_1="dad_1892_record",
                        children={"kid"}),
    }
    mapping: dict[str, str] = {"dad_1892_record": "dad_canon"}

    def resolve(n: str) -> str:
        return mapping.get(n, n)

    persons, _ = project_kin(profiles, unions, {"dad_canon": None, "kid": None},
                             resolve=resolve)
    kid = next(p for p in persons if p.res_name == "kid")
    assert kid.parents == ("dad_canon",)


# --- birth place (familio settlement UUID, gated on a real birth record) ------

def test_settlement_place_maps_known_location_to_local_ref_else_empty():
    from verso.ru.familio.projection import _settlement_place
    from verso.core import places
    locations = places.current().bodies
    nv = GeniEvent(location=locations["Нижняя Яичница"])
    assert _settlement_place(nv) == "local.settlement_nizhnjaja_jaichnitsa"
    assert _settlement_place(None) == ""
    assert _settlement_place(GeniEvent(location='city = "Неизвестно"')) == ""
    assert _settlement_place(GeniEvent(date=GeniDate(year=1900))) == ""  # no location


def test_settlement_locals_block_lists_every_settlement():
    from verso.ru.familio.projection import settlement_locals_hcl
    from verso.core import places
    familio_settlements = places.current().attributes["familio"]
    hcl = settlement_locals_hcl()
    assert hcl.startswith("locals {")
    for key, uuid in familio_settlements.items():
        assert f'= "{uuid}"' in hcl
        assert f"# {key}" in hcl
    assert "settlement_nizhnjaja_jaichnitsa" in hcl


def test_birth_place_only_for_real_birth_record():
    from verso.core import places
    locations = places.current().bodies
    nv = locations["Нижняя Яичница"]
    born = _cite("birth", "child", 1910, "<strong>МК Нижняя Яичница 1910:</strong> рождение\n        >x")
    roll = _cite("census", "member1", 1857, "<strong>РС Нижняя Яичница 1857:</strong> семья 1\n        >x")
    profiles = {
        "kid": _profile("kid", first_name="Дитя",
                        birth=GeniEvent(date=GeniDate(year=1910), location=nv),
                        baptism=GeniEvent(date=GeniDate(year=1910), location=nv),
                        about=_about_of(born)),
        "anc": _profile("anc", first_name="Дед",
                        birth=GeniEvent(date=GeniDate(year=1850), location=nv),
                        about=_about_of(roll)),
    }
    persons, _ = project_kin(profiles, {}, {"kid": None, "anc": None},
                             appearances={"kid": [born], "anc": [roll]})
    by = {p.res_name: p for p in persons}
    assert by["kid"].birth_place == "local.settlement_nizhnjaja_jaichnitsa"
    assert by["kid"].christening_place == "local.settlement_nizhnjaja_jaichnitsa"
    assert by["anc"].birth_place == ""          # census only → no birthplace asserted
    assert by["anc"].christening_place == ""


def test_person_renders_place_as_unquoted_local_ref():
    p = FamilioPerson(res_name="x", gender="male", birth_date=FamilioDate(1910),
                      birth_place="local.settlement_nizhnjaja_jaichnitsa")
    birth = p.to_terraform().split("birth = {", 1)[1].split("\n  }", 1)[0]
    assert "place = local.settlement_nizhnjaja_jaichnitsa" in birth
    assert 'place = "' not in birth   # a reference, never a quoted literal


def test_parent_overrides_pin_parentage():
    # a first-marriage child the census groups under the head's 2nd wife: the
    # override drops the stepmother, linking him to the father alone
    profiles = {
        "dad": _profile("dad", first_name="Папа"),
        "stepmom": _profile("stepmom", gender="female", first_name="Мачеха"),
        "kid": _profile("kid", first_name="Сын"),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="dad", partner_2="stepmom",
                             children={"kid"})}
    kin = {"dad": None, "stepmom": None, "kid": None}
    persons, _ = project_kin(profiles, unions, kin,
                             parent_overrides={"kid": ("dad",)})
    kid = next(p for p in persons if p.res_name == "kid")
    assert kid.parents == ("dad",)


def test_person_renders_sources_block():
    p = FamilioPerson(res_name="x", gender="male", sources=(
        FamilioSource(reference_uuid="u-1", type="catalog_person", catalog_key="vss"),
        FamilioSource(reference_uuid="u-2", type="case"),
    ))
    tf = p.to_terraform()
    assert "sources = [" in tf
    assert 'reference_uuid = "u-1"' in tf
    assert 'type           = "catalog_person"' in tf
    assert 'catalog_key    = "vss"' in tf
    assert 'reference_uuid = "u-2"' in tf
    # a case source carries no catalog_key
    case_block = tf.split('"u-2"', 1)[1]
    assert "catalog_key" not in case_block


def test_person_without_sources_omits_block():
    assert "sources" not in FamilioPerson(res_name="x", gender="male").to_terraform()


def test_parse_sources_builds_and_validates():
    out = parse_sources({"p": [
        {"type": "catalog_person", "reference_uuid": "u", "catalog_key": "vss"},
        {"type": "case", "reference_uuid": "d"},
    ]})
    assert out["p"] == (
        FamilioSource(reference_uuid="u", type="catalog_person", catalog_key="vss"),
        FamilioSource(reference_uuid="d", type="case"),
    )


def test_parse_sources_rejects_bad_shapes():
    with pytest.raises(ValueError):
        parse_sources({"p": [{"type": "catalog_person", "reference_uuid": "u"}]})  # no key
    with pytest.raises(ValueError):
        parse_sources({"p": [{"type": "case", "reference_uuid": "d", "catalog_key": "vss"}]})
    with pytest.raises(ValueError):
        parse_sources({"p": [{"type": "bogus", "reference_uuid": "u"}]})
    with pytest.raises(ValueError):
        parse_sources({"p": [{"type": "case"}]})  # no reference_uuid


def test_project_kin_attaches_sources():
    profiles = {"iosif": _profile("iosif", first_name="Иосиф")}
    src = FamilioSource(reference_uuid="26eb603e", type="catalog_person", catalog_key="vss")
    persons, _ = project_kin(profiles, {}, {"iosif": None},
                             sources_by_res={"iosif": (src,)})
    assert persons[0].sources == (src,)


# --- About sort-markers must never reach familio ------------------------------
#
# `inject_section_date_marker` appends an invisible `<!--sd:YYYY-MM-DD-->` to a
# section header so same-year About sections sort by full date. The geni
# renderer strips it on the way out. The biography prints the about, so it has
# to strip it too; and a record's section — handed over by the translator
# without the marker — must still be found in an about that carries one. When
# the projection cut the about apart with a `$`-anchored header regex, a marker
# at the end of the header line silently stopped two spouses' sections merging.

_MARKED_GROOM_ABOUT = (
    "<strong>МК Заманиловка 1839:</strong> жених<!--sd:1839-04-30-->\n"
    "        Титул/звание: экономический крестьянин\n"
    "        >Имена в МК: Емельян Емельянов Чичиков; Ирина Григорьева\n"
)
_MARKED_BRIDE_ABOUT = (
    "<strong>МК Заманиловка 1839:</strong> невеста<!--sd:1839-04-30-->\n"
    "        Титул/звание: экономическая крестьянка\n"
    "        >Имена в МК: Емельян Емельянов Чичиков; Ирина Григорьева\n"
)


def _marked_couple():
    # The translator hands over a section without its marker; the about keeps it.
    groom = _cite("marriage", "groom", 1839,
                  _MARKED_GROOM_ABOUT.replace("<!--sd:1839-04-30-->", "").rstrip("\n"),
                  title="экономический крестьянин")
    bride = _cite("marriage", "bride", 1839,
                  _MARKED_BRIDE_ABOUT.replace("<!--sd:1839-04-30-->", "").rstrip("\n"),
                  title="экономическая крестьянка")
    profiles = {
        "h": _profile("h", first_name="Емельян", last_name="Чичиков",
                      middle_name="Емельянович", about=_MARKED_GROOM_ABOUT),
        "w": _profile("w", gender="female", first_name="Ирина",
                      last_name="Чичикова", middle_name="Григорьевна",
                      about=_MARKED_BRIDE_ABOUT),
    }
    unions = {"u": GeniUnion(res_name="u", partner_1="h", partner_2="w",
                             marriage=_birth(1839, 4, 30))}
    return project_kin(profiles, unions, {"h": None, "w": None},
                       appearances={"h": [groom], "w": [bride]})


def test_marriage_comment_merges_both_spouses_despite_sort_markers():
    _, marriages = _marked_couple()
    assert len(marriages) == 1
    c = marriages[0].comment
    assert "Жених: Емельян Емельянович Чичиков, экономический крестьянин" in c
    assert "Невеста: Ирина Григорьевна Чичикова, экономическая крестьянка" in c
    assert c.splitlines()[0] == "МК Заманиловка 1839"   # role suffix + marker stripped


def test_sort_markers_reach_neither_comments_nor_biography():
    persons, marriages = _marked_couple()
    for text in [p.biography for p in persons] + [m.comment for m in marriages]:
        assert "<!--sd:" not in text
    for p in persons:
        for attr in ("birth_comment", "death_comment", "christening_comment"):
            assert "<!--sd:" not in (getattr(p, attr, "") or "")
