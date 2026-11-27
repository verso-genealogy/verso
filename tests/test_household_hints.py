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
from verso.ru.records.household_hints import AgeGap, age_gap, patronymic_hint, ref_hint


def _rules() -> dict[str, dict[str, Any]]:
    return {r["rule"]: r for r in load_ui()["kinds"]["household"]["rules"]}


_RULES = _rules()
PARAMS: dict[str, Any] = {k: _RULES["ref_hint"][k] for k in ("children", "parents", "spouse", "min_gap")}
GAPS: dict[str, int] = _RULES["age_gap"]["gaps"]


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
    assert ref_hint([*DVOR[:2], m(3, "Марья", None, "wife")], 2, **PARAMS) == 2


def test_a_wife_skips_a_man_who_has_one():
    dvor = [*DVOR[:3], m(4, "Яковъ", None, "son", age=22), m(5, "Анна", None, "wife")]
    assert ref_hint(dvor, 4, **PARAMS) == 4
    # Ѳедоръ above Яковъ already has Марья: Анна is not his.
    dvor[3] = m(4, "Яковъ", None, "daughter", age=22)
    assert ref_hint(dvor, 4, **PARAMS) is None


def test_no_hint_where_written():
    assert ref_hint([*DVOR[:3], m(4, "Яковъ", None, "son", ref=1)], 3, **PARAMS) is None


def test_no_hint_to_a_number_the_household_lacks():
    assert ref_hint([DVOR[0], DVOR[3]], 1, **PARAMS) is None


def test_no_hint_to_a_row_that_is_neither_a_child_nor_a_wife():
    assert ref_hint(DVOR, 4, **PARAMS) is None


def test_the_head_is_never_offered_a_wife_s_ref():
    assert ref_hint([DVOR[0], m(2, "Марья", None, "wife")], 1, **PARAMS) is None


def test_brother_takes_the_heads_patronymic():
    assert patronymic_hint(DVOR, 4) == "Петровъ"


def test_no_patronymic_hint_where_written_or_for_another_role():
    assert patronymic_hint([DVOR[0], m(2, "Степанъ", "Васильевъ", "brother")], 1) is None
    assert patronymic_hint(DVOR, 3) is None
    assert patronymic_hint([m(1, "Иванъ", None, "head"), m(2, "Степанъ", None, "brother")], 1) is None


def test_age_gap_holds_cai002():
    # 1850 counts from 1834: a gap of 16, and one year either way passes
    assert age_gap(DVOR[0], 1850, GAPS) is None
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1850, GAPS) == AgeGap(16, 8)
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=3), 1850, GAPS) is None       # 17: within a year
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=2), 1850, GAPS) == AgeGap(16, 18)


def test_age_gap_needs_both_ages():
    assert age_gap(m(4, "Яковъ", None, "son", prev=5), 1850, GAPS) is None
    assert age_gap(m(4, "Яковъ", None, "son", age=5), 1850, GAPS) is None


def test_age_gap_needs_a_year_the_table_holds():
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1900, GAPS) is None


def test_age_gap_reads_the_comment_marker_where_no_previous_age_is_written():
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, comment="прошлая РС: 12 лет"), 1850, GAPS) == AgeGap(16, 8)


@pytest.mark.parametrize("skip", ["departed", "hidden", "copied_forward", "no_previous_age"])
def test_age_gap_skips_what_cai002_skips(skip: str):
    assert age_gap(m(2, "Ѳедоръ", None, "son", age=20, prev=12), 1850, GAPS) == AgeGap(16, 8)
    skipped = {
        "departed": m(2, "Ѳедоръ", None, "son", age=20, prev=12, departure={"year": 1849, "reason": "умер"}),
        "hidden": m(2, "Ѳедоръ", None, "son", age=20, prev=12, hidden=True),
        "copied_forward": m(2, "Ѳедоръ", None, "son", age=12, prev=12),
        "no_previous_age": m(2, "Ѳедоръ", None, "son", age=20, comment="без отметки о прошлой РС"),
    }[skip]
    assert age_gap(skipped, 1850, GAPS) is None


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
                gap = age_gap(member, year, GAPS)
                if gap is not None:
                    found[(record, year, gap.expected, gap.found)] += 1
        assert found == said, sample.name
    assert seen > 10


def test_the_roll_samples_have_findings_to_compare():
    findings = [f for s in oracle.samples()[0] for f in on_json.lint_records(copy.deepcopy(s.data), codes=["CAI002"])]
    assert findings


def test_schema_parameters_are_the_libraries_numbers():
    assert PARAMS["min_gap"] == FATHER_MIN
    assert {int(k): v for k, v in GAPS.items()} == dict(PREVIOUS_AGE_REVISION_YEAR)
