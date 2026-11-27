"""The household page's rules (`verso.ru.records.household_hints`): whose a row is, a brother's patronymic, an age off
the revision gap — as pure functions of a household's `persons` in the records JSON, with the parameters read from the
schema, which is their single source. The invented household is Маниловка's."""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest

import test_linters_on_json_samples as oracle
from verso.core.records.ui import load_ui
from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR
from verso.ru.facts.checks.parent_ages import FATHER_MIN
from verso.ru.linters import on_json
from verso.ru.linters.checks.census_age import PREV_AGE_COMMENT_RE
from verso.ru.records.household_hints import AgeGap, age_gap, patronymic_hint, ref_hint


def _rules() -> dict[str, dict[str, Any]]:
    return {r["rule"]: r for r in load_ui()["kinds"]["household"]["rules"]}


def _params(rule: str, *, but: tuple[str, ...] = ()) -> dict[str, Any]:
    """A rule's parameters as the schema holds them: every key but the rule's own name and group."""
    return {k: v for k, v in _RULES[rule].items() if k not in ("rule", "group", *but)}


_RULES = _rules()
PARAMS: dict[str, Any] = _params("ref_hint")
AGE_GAP: dict[str, Any] = _params("age_gap", but=("prior_comment",))   # the pattern is CAI002's (a test holds it)
ROLES: dict[str, Any] = _params("patronymic_hint")


def m(number: int, given: str, patronymic: str | None, role: str, *, ref: int | None = None, age: Any = None,
      prev: Any = None, **link: Any) -> dict[str, Any]:
    """A member as the household node's `persons` holds it."""
    written: dict[str, Any] = {"number": number, "role": role}
    for key, value in (("ref_member", ref), ("age", age), ("previous_age", prev)):
        if value is not None:
            written[key] = value
    written.update(link)
    person: dict[str, Any] = {"given": {"original": given}}
    if patronymic is not None:
        person["patronymic"] = {"original": patronymic}
    return {"role": "member", "slot": number, "link": {"written": written, "derived": {}}, "written": person}


DVOR = [m(1, "Иванъ", "Петровъ", "head", age=45, prev=29),
        m(2, "Ѳедоръ", None, "son", age=20, prev=4),
        m(3, "Марья", "Ѳедорова", "wife", ref=2, age=19),
        m(4, "Яковъ", None, "son", age=2),
        m(5, "Степанъ", None, "brother", age=40, prev=24)]


def test_a_son_under_a_married_son_is_his():
    assert ref_hint(DVOR, 3, **PARAMS) == 2


def test_a_son_of_the_head_gets_no_hint():
    assert ref_hint(DVOR, 1, **PARAMS) is None


def test_no_hint_to_a_brother_too_young_to_be_father():
    # the son of a dead Ѳедоръ (11) under a married brother (20): nine years apart is no father and son
    dvor = [DVOR[0], m(2, "Ѳедоръ", None, "son", age=20), m(3, "Марья", None, "wife", ref=2, age=19),
            m(4, "Яковъ", None, "son", age=11)]
    assert ref_hint(dvor, 3, **PARAMS) is None


def test_the_father_may_be_exactly_min_gap_older():
    dvor = [DVOR[0], m(2, "Ѳедоръ", None, "son", age=20), m(3, "Марья", None, "wife", ref=2, age=19),
            m(4, "Яковъ", None, "son", age=20 - PARAMS["min_gap"])]
    assert ref_hint(dvor, 3, **PARAMS) == 2
    dvor[3] = m(4, "Яковъ", None, "son", age=20 - PARAMS["min_gap"] + 1)
    assert ref_hint(dvor, 3, **PARAMS) is None


def test_no_hint_without_ages():
    no_child = [*DVOR[:3], m(4, "Яковъ", None, "son")]
    no_father = [DVOR[0], m(2, "Ѳедоръ", None, "son"), DVOR[2], DVOR[3]]
    assert ref_hint(no_child, 3, **PARAMS) is None
    assert ref_hint(no_father, 3, **PARAMS) is None


def test_a_wife_goes_to_the_unmarried_man_above():
    assert ref_hint([*DVOR[:2], m(3, "Марья", None, "wife", age=19)], 2, **PARAMS) == 2


def test_a_wife_skips_a_man_who_has_one():
    dvor = [*DVOR[:3], m(4, "Яковъ", None, "son", age=22), m(5, "Анна", None, "wife", age=21)]
    assert ref_hint(dvor, 4, **PARAMS) == 4
    # Ѳедоръ above Яковъ already has Марья: Анна is not his.
    dvor[3] = m(4, "Яковъ", None, "daughter", age=22)
    assert ref_hint(dvor, 4, **PARAMS) is None


def test_a_wife_is_not_offered_a_boy():
    """The roll lays its men first: the nearest unmarried man above the head's wife is his grandson of seven."""
    dvor = [m(1, "Иванъ", "Петровъ", "head", age=45), m(2, "Ѳедоръ", None, "son", age=20),
            m(3, "Яковъ", None, "son", age=7), m(4, "Анна", None, "wife", age=42)]
    assert ref_hint(dvor, 3, **PARAMS) is None


def test_a_wife_goes_past_a_boy_to_the_man_of_age_above():
    dvor = [DVOR[0], m(2, "Ѳедоръ", None, "son", age=20), m(3, "Яковъ", None, "son", age=7),
            m(4, "Марья", None, "wife", age=19)]
    assert ref_hint(dvor, 3, **PARAMS) == 2


def test_a_wife_s_husband_is_of_marrying_age_and_not_far_her_junior():
    least, most = PARAMS["min_husband_age"], PARAMS["max_wife_older"]
    def hint(husband: int, wife: int) -> int | None:
        return ref_hint([DVOR[0], m(2, "Ѳедоръ", None, "son", age=husband), m(3, "Марья", None, "wife", age=wife)],
                        2, **PARAMS)
    assert hint(least, least) == 2
    assert hint(least - 1, least - 1) is None
    assert hint(30, 30 + most) == 2
    assert hint(30, 30 + most + 1) is None
    assert hint(40, 20) == 2                     # a husband much older is no bar


def test_no_wife_hint_without_both_ages():
    assert ref_hint([DVOR[0], m(2, "Ѳедоръ", None, "son", age=20), m(3, "Марья", None, "wife")], 2, **PARAMS) is None
    assert ref_hint([DVOR[0], m(2, "Ѳедоръ", None, "son"), m(3, "Марья", None, "wife", age=19)], 2, **PARAMS) is None


def test_the_hints_read_the_fields_the_rule_names():
    """The page reads a member only by the rule's paths: name the columns otherwise, and the hint follows them."""
    def renamed(member: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(member)
        written = out["link"]["written"]
        for old, new in (("role", "r"), ("number", "n"), ("age", "a"), ("ref_member", "whose")):
            if old in written:
                written[new] = written.pop(old)
        return out
    dvor = [renamed(x) for x in DVOR]
    names = {"role": "r", "number": "n", "age": "a", "path": "whose"}
    assert ref_hint(dvor, 3, **{**PARAMS, **names}) == 2
    assert ref_hint(dvor, 3, **PARAMS) is None
    assert patronymic_hint(dvor, 4, **{**ROLES, "role": "r", "number": "n", "ref": "whose"}) == "Петровъ"
    assert patronymic_hint(dvor, 4, **ROLES) is None
    moved = m(2, "Ѳедоръ", None, "son", age=20, prev=12)
    moved["link"]["written"]["prior"] = moved["link"]["written"].pop("previous_age")
    assert age_gap(moved, 1850, **{**AGE_GAP, "previous": "prior"}) == AgeGap(16, 8)
    assert age_gap(moved, 1850, **AGE_GAP) is None


def test_no_hint_where_written():
    assert ref_hint([*DVOR[:3], m(4, "Яковъ", None, "son", ref=1)], 3, **PARAMS) is None


def test_no_hint_where_the_household_has_no_man_above():
    assert ref_hint([DVOR[0], DVOR[3]], 1, **PARAMS) is None


def test_no_hint_to_a_man_without_a_number():
    """I13: the nearest fitting man has no number — nothing to offer, not a guess."""
    nameless = m(2, "Ѳедоръ", None, "son", age=20)
    del nameless["link"]["written"]["number"]
    wife = m(3, "Марья", None, "wife", ref=2, age=19)
    assert ref_hint([DVOR[0], nameless, wife, m(4, "Яковъ", None, "son", age=2)], 3, **PARAMS) is None


def test_a_married_man_too_young_to_be_father_does_not_stand_between():
    """The filter reading: the nearest married man (20) is too young for a child of 11; the older one above (40) is."""
    dvor = [DVOR[0], m(2, "Ѳедоръ", None, "brother", age=40), m(3, "Анна", None, "wife", ref=2, age=38),
            m(4, "Ѳома", None, "son", age=20), m(5, "Марья", None, "wife", ref=4, age=19),
            m(6, "Яковъ", None, "son", age=11)]
    assert ref_hint(dvor, 5, **PARAMS) == 2


def test_no_hint_to_a_row_that_is_neither_a_child_nor_a_wife():
    assert ref_hint(DVOR, 4, **PARAMS) is None


def test_the_head_is_never_offered_a_wife_s_ref():
    assert ref_hint([DVOR[0], m(2, "Марья", None, "wife")], 1, **PARAMS) is None


def test_brother_takes_the_heads_patronymic():
    assert patronymic_hint(DVOR, 4, **ROLES) == "Петровъ"


def test_a_brother_written_under_another_member_takes_that_member_s_patronymic():
    """A brother whose `ref_member` names a son is the son's brother: the son's patronymic, not the head's."""
    dvor = [DVOR[0], m(2, "Ѳедоръ", "Ивановъ", "son", age=20), m(3, "Ѳома", None, "brother", ref=2, age=18)]
    assert patronymic_hint(dvor, 2, **ROLES) == "Ивановъ"
    dvor[1] = m(2, "Ѳедоръ", None, "son", age=20)
    assert patronymic_hint(dvor, 2, **ROLES) is None          # the son's is not written: nothing to offer
    assert patronymic_hint([DVOR[0], m(3, "Ѳома", None, "brother", ref=9)], 1, **ROLES) is None   # nobody is № 9


def test_no_patronymic_hint_where_written_or_for_another_role():
    assert patronymic_hint([DVOR[0], m(2, "Степанъ", "Васильевъ", "brother")], 1, **ROLES) is None
    assert patronymic_hint(DVOR, 3, **ROLES) is None
    assert patronymic_hint([m(1, "Иванъ", None, "head"), m(2, "Степанъ", None, "brother")], 1, **ROLES) is None


def test_age_gap_holds_cai002():
    # 1850 counts from 1834: a gap of 16, and one year either way passes
    assert age_gap(DVOR[0], 1850, **AGE_GAP) is None
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1850, **AGE_GAP) == AgeGap(16, 8)
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=3), 1850, **AGE_GAP) is None       # 17: within a year
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=2), 1850, **AGE_GAP) == AgeGap(16, 18)


def test_age_gap_needs_both_ages():
    assert age_gap(m(4, "Яковъ", None, "son", prev=5), 1850, **AGE_GAP) is None
    assert age_gap(m(4, "Яковъ", None, "son", age=5), 1850, **AGE_GAP) is None


def test_age_gap_needs_a_year_the_table_holds():
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1900, **AGE_GAP) is None


def test_age_gap_reads_the_comment_marker_where_no_previous_age_is_written():
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, comment="прошлая РС: 12 лет"), 1850, **AGE_GAP) == AgeGap(16, 8)


@pytest.mark.parametrize("skip", ["departed", "hidden", "copied_forward", "no_previous_age"])
def test_age_gap_skips_what_cai002_skips(skip: str):
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1850, **AGE_GAP) == AgeGap(16, 8)
    skipped = {
        "departed": m(2, "Ѳедоръ", None, "son", age=20, prev=12, departure={"year": 1849, "reason": "умер"}),
        "hidden": m(2, "Ѳедоръ", None, "son", age=20, prev=12, hidden=True),
        "copied_forward": m(2, "Ѳедоръ", None, "son", age=12, prev=12),
        "no_previous_age": m(2, "Ѳедоръ", None, "son", age=20, comment="без отметки о прошлой РС"),
    }[skip]
    assert age_gap(skipped, 1850, **AGE_GAP) is None


def _households(data: dict[str, Any]) -> Iterator[tuple[str, int, list[dict[str, Any]]]]:
    for doc in data["documents"]:
        year = doc["written"].get("year")
        for page in doc.get("pages", ()):
            for record in page["records"]:
                if record["kind"] == "household" and isinstance(year, int) and doc["kind"] == "census":
                    yield record["id"], year, record["persons"]


def test_age_gap_equals_cai002_on_the_fixture_rolls():
    """Every member of the invented rolls: the page's finding is the linter's — one for one."""
    seen = 0
    for sample in oracle.samples()[0]:
        data = copy.deepcopy(sample.data)
        said: Counter[tuple[Any, ...]] = Counter()
        for f in on_json.lint_records(copy.deepcopy(data), codes=["CAI002"]):
            said[(f.record, f.params["year"], f.params["gap"], f.params["diff"])] += 1
        found: Counter[tuple[Any, ...]] = Counter()
        for record, year, persons in _households(data):
            for member in persons:
                seen += 1
                gap = age_gap(member, year, **AGE_GAP)
                if gap is not None:
                    found[(record, year, gap.expected, gap.found)] += 1
        assert found == said, sample.name
    assert seen > 10


def test_the_roll_samples_have_findings_to_compare():
    findings = [f for s in oracle.samples()[0] for f in on_json.lint_records(copy.deepcopy(s.data), codes=["CAI002"])]
    assert findings


def test_the_prior_revision_marker_is_cai002_s():
    assert _RULES["age_gap"]["prior_comment"] == PREV_AGE_COMMENT_RE.pattern


def test_schema_parameters_are_the_libraries_numbers():
    assert PARAMS["min_gap"] == FATHER_MIN
    assert {int(k): v for k, v in AGE_GAP["gaps"].items()} == dict(PREVIOUS_AGE_REVISION_YEAR)
