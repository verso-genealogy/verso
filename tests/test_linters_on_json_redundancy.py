"""The rules on what a record inherits (`on_json.redundancy`): the export they refuse, the objects they read,
and the places where the walk answers on the value where `dsllint` answers on the text of the source.

The samples oracle (`test_linters_on_json_samples`) holds each rule to `dsllint`; this module holds what it
cannot: an old export, the replayed objects, and every divergence the module's docstring accepts, so a change
that closes one (or opens another) is seen.
"""
from __future__ import annotations

import copy
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import context_in_derived, encode_namespace
from verso.core.records.ids import Ids
from verso.ru.linters import hosted, on_json
from verso.ru.linters.dsllint import check_file_json
from verso.ru.linters.on_json.walk import FileView, Unsupported
from tests.test_linters_on_json_samples import Key, _dsllint_of, _key, _try_load

HEAD = '"ГА Глуповской области", "10", "4", "4071", "Маниловка", "Церковь"'
DERIVED = ("DBD001", "DBD002", "RVR001", "SLC003", "SLC004", "SLC005", "VSR001")


def _encode(text: str) -> dict[str, Any]:
    module, error = _try_load(text)
    assert module is not None, error
    doc = encode_namespace(record_namespace(module), village="Примерово", file="sample.py", sha256="-", ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _sides(text: str, code: str) -> tuple[Counter[Key], Counter[Key]]:
    """What `dsllint` says of `text` and what the walk says of its records, of one code."""
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        path = Path(tmp) / "Примерово" / "sample.py"
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
        said, _ = _dsllint_of(path, hosted.readiness())
    found = on_json.lint_records(_encode(text), codes=[code])
    return (Counter({k: n for k, n in said.items() if k[0] == code}),
            Counter(_key(f.code, f.variant, f.params, f.token) for f in found))


def _agree(text: str, code: str) -> int:
    said, walked = _sides(text, code)
    assert said == walked
    return sum(said.values())


# --- the export ---------------------------------------------------------------------------------------------

DEATH = f'deaths = death_records({HEAD}, 1857, *death_month(Month.MAY, death(1, Gender.MALE, 9, 8)))'


def _old(data: dict[str, Any]) -> dict[str, Any]:
    """The export as it was before 0.1.16: a wrapper's value back in `derived`, no `written.context`."""
    out = copy.deepcopy(data)
    for doc in out["documents"]:
        for run in doc.get("pages", ()):
            run["records"] = [context_in_derived(r) for r in run["records"]]
    return out


def test_old_export_refuses_derived():
    """A file whose records keep a section's month in `derived`, where `written.context` now names it, is from
    before 0.1.16: every code that reads what a record inherits asks for the export again."""
    data = _encode(DEATH)
    assert on_json.lint_records(data, codes=["DBD001"])          # the new export answers
    old = _old(data)
    assert "context" not in old["documents"][0]["pages"][0]["records"][0]["written"]
    for code in DERIVED:
        with pytest.raises(Unsupported) as refused:
            on_json.lint_records(copy.deepcopy(old), codes=[code])
        assert refused.value.message.key == "on_json.no_context"
        assert str(refused.value.message.params["record"]).endswith("/death/m1")
    with pytest.raises(Unsupported):
        FileView(old).replayed()


def test_a_call_that_wrote_none_is_not_an_old_export():
    """`d_month=None` is written and the section gave the month: the value is in `derived` beside the call's
    key, which the export of today writes too — `replay` reads it, and the rules answer."""
    data = _encode(f'deaths = death_records({HEAD}, 1857, *death_month(Month.MAY, death(1, Gender.MALE, 9, 8, d_month=None)))')
    record = data["documents"][0]["pages"][0]["records"][0]
    assert record["written"]["death"] == {"day": 9, "month": None} and record["derived"]["death"]["month"] == "may"
    assert [f.code for f in on_json.lint_records(data, codes=["DBD001"])] == ["DBD001"]


def test_a_file_no_factory_rebuilds_is_unsupported():
    data = _encode(DEATH)
    data["documents"][0]["pages"][0]["records"][0]["written"]["no_such_argument"] = 1
    with pytest.raises(Unsupported) as refused:
        on_json.lint_records(data, codes=["DBD001"])
    assert refused.value.message.key == "on_json.not_replayable"


def test_the_objects_are_built_once_and_found_by_the_id():
    view = FileView(_encode(f'{DEATH}\nmore = death_records({HEAD}, 1858, death(1, Gender.FEMALE, 3, 4))'))
    assert view.replayed() is view.replayed()
    (doc, record), *_ = view.records({"deaths"})
    built = view.object_of(record)
    assert (built.d_month.name, built.b_month.name, built.d_day) == ("MAY", "MAY", 9)    # the section's, derived again
    assert view.set_of(doc).year == 1857
    assert view.object_of(record) is built
    other = [r for _, r in view.records({"deaths"})][1]
    assert view.object_of(other).d_month is None and view.object_of(other).b_month is None


def test_an_aliased_set_has_no_records_of_its_own():
    data = _encode(f'{DEATH}\nagain = deaths')
    assert any("alias_of" in d for d in data["documents"])
    view = FileView(data)
    assert len(view.replayed()) == 2
    assert len([f for f in on_json.lint_records(data, codes=["DBD001"])]) == 1


# --- the inherited value --------------------------------------------------------------------------------

def test_the_year_comes_from_the_record_then_the_section_then_the_book():
    """February 29 is Julian-leap in 1804 and 1860, no day in 1861, and any year between: the record's `year=`
    wins over the section's, the section's over the book's."""
    text = (f'deaths = death_records({HEAD}, 1861,\n'
            '    *death_month_year(Month.FEBRUARY, 1860, death(1, Gender.MALE, 29, 28), death(2, Gender.MALE, 29, 28, year=1861)),\n'
            '    *death_month(Month.FEBRUARY, death(3, Gender.MALE, 29, 28)))')
    assert _agree(text, "DBD002") == 2                  # the second and the third: 1861 is not a leap year


@pytest.mark.parametrize("code, text, count", [
    ("DBD001", f'deaths = death_records({HEAD}, 1925, death(1, Gender.MALE, 11, 2, d_month=Month.APRIL, b_month=Month.APRIL), '
              'civil=True)', 1),
    ("DBD001", f'deaths = death_records({HEAD}, 1857, death(1, Gender.MALE, 11, 2, d_month=Month.APRIL, b_month=Month.APRIL, '
              'source_date_error="так в подлиннике"))', 0),
    ("DBD001", f'deaths = death_records({HEAD}, 1857, *death_month(None, death(1, Gender.MALE, 11, 2)))', 0),
    ("DBD002", f'deaths = death_records({HEAD}, 1857, death(1, Gender.MALE, 0, 0, d_month=Month.JUNE, b_month=Month.MAY))', 0),
    ("DBD002", f'deaths = death_records({HEAD}, 1857, death(1, Gender.MALE, 31, 32))', 1),
], ids=["civil", "declared", "no-month", "empty-column", "day-32"])
def test_the_dates_of_a_death(code: str, text: str, count: int):
    assert _agree(text, code) == count


# --- the book's defaults ------------------------------------------------------------------------------

DEFAULTS = 'defaults=RecordDefaults(residence="Ротозеево", status_male=YASAK_PEASANT_MALE, cause_of_death=CONSUMPTION)'


def test_a_book_without_defaults_repeats_nothing():
    for text in (f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=person("Петр", residence="Ротозеево")))',
                 f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=person("Петр", residence="Ротозеево")), '
                 'defaults=RecordDefaults())'):
        assert [_agree(text, c) for c in DERIVED] == [0] * 7


def test_a_christening_is_no_birth_to_these_checks():
    text = (f'b = birth_records({HEAD}, 1857, christening(1, Gender.MALE, 9, '
            f'father=person("Петр", residence="Ротозеево", status=YASAK_PEASANT_MALE)), {DEFAULTS})')
    assert [_agree(text, c) for c in DERIVED] == [0] * 7


def test_the_newborns_parent_keeps_the_status_the_child_rests_on():
    base = (f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, child=person("Иван"), '
            'father=person("Петр", status=YASAK_PEASANT_MALE)), {})')
    assert _agree(base.format(DEFAULTS), "VSR001") == 0              # the son's «крестьянский сын» derives from it
    assert _agree(base.format(DEFAULTS), "SLC005") == 0
    grown = base.replace('child=person("Иван")', 'child=person("Иван", status=YASAK_PEASANT_SON)')
    assert _agree(grown.format(DEFAULTS), "VSR001") == 1             # the child wrote its own: the parent's repeats
    assert _agree(grown.format(DEFAULTS), "SLC005") == 1


def test_no_names_table_is_no_crash(tmp_path: Path):
    """The gender of a witness comes from the names table; a workspace without one reads it as unknown, as the
    check does when it cannot read the table."""
    (tmp_path / "verso.toml").write_text('schema = 5\nplugins = ["ru"]\n')
    text = (f'b = marriage_records({HEAD}, 1857, marriage(1, 3, witness1=person("Петр", status=YASAK_PEASANT_MALE)), '
            f'{DEFAULTS})')
    data = _encode(text)
    found = on_json.lint_records(data, codes=["SLC005", "VSR001"], workspace=tmp_path)
    assert sorted(f.code for f in found) == ["SLC005", "VSR001"]       # the male default, as for a name nobody knows


# --- the divergences the module's docstring accepts ------------------------------------------------------

def _only_walk(text: str, code: str) -> int:
    said, walked = _sides(text, code)
    assert not said - walked
    return sum((walked - said).values())


def test_two_names_of_one_status_are_one_value():
    text = (f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=person("Петр", '
            'status=GOSUDARSTVENNYJ_PEASANT_MALE)), defaults=RecordDefaults(status_male=STATE_PEASANT_MALE))')
    said, walked = _sides(text, "SLC005")
    assert not said and sum(walked.values()) == 1
    assert _only_walk(text, "VSR001") == 1


def test_a_literal_is_not_the_constant_of_its_text():
    text = (f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=person("Петр", status="ясачный крестьянин")), '
            'defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE))')
    assert _agree(text, "SLC005") == 0 and _agree(text, "VSR001") == 0


def test_a_person_bound_to_a_name_is_read_here_and_not_there():
    text = (f'F = person("Петр", residence="Ротозеево")\n'
            f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=F), defaults=RecordDefaults(residence="Ротозеево"))')
    assert _only_walk(text, "SLC004") == 1


def test_a_books_priest_is_one_finding_per_record():
    text = (f'P = person("Лука", residence="Ротозеево")\n'
            f'b = birth_records({HEAD}, 1857, *book("к1", P, birth(1, Gender.MALE, 3, 4), birth(2, Gender.MALE, 3, 4)), '
            'defaults=RecordDefaults(residence="Ротозеево"))')
    assert _only_walk(text, "SLC004") == 2


def test_a_name_is_read_by_parameter():
    text = (f'd = death_records({HEAD}, 1857, death(1, Gender.FEMALE, 9, 8, d_month=Month.MAY, b_month=Month.MAY, '
            'witness1=person(name_orig="Мария", status=YASAK_PEASANT_FEMALE)), '
            'defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE))')
    assert _only_walk(text, "SLC005") == 1       # the check reads a positional name; a keyword one is unknown there


def test_a_residence_given_positionally_is_read():
    text = (f'd = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, '
            'father=person("Петр", None, None, None, None, None, "Ротозеево")), defaults=RecordDefaults(residence="Ротозеево"))')
    assert _only_walk(text, "SLC004") == 1


def test_a_section_around_a_page_is_seen_by_the_walk_alone():
    text = f'd = death_records({HEAD}, 1857, *death_month(Month.MAY, *page("1", death(1, Gender.MALE, 9, 8))))'
    assert _only_walk(text, "DBD001") == 1


def test_a_status_the_file_defines_is_shown_by_its_text():
    text = (f'S = Status("мещанин особый", Gender.MALE)\n'
            f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father=person("Петр", status=S)), '
            'defaults=RecordDefaults(status_male=S))')
    said, walked = _sides(text, "SLC005")
    assert [k[1] for k in said] == ['{"value": "S"}'] and [k[1] for k in walked] == ['{"value": "мещанин особый"}']


def test_a_groom_status_equal_to_the_males_is_the_one_derived():
    """`RecordDefaults` derives `status_groom` from `status_male`: written equal to it, the field is the male's."""
    text = (f'm = marriage_records({HEAD}, 1857, marriage(1, 3, groom=person("Иван", status=YASAK_PEASANT_MALE)), '
            'defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_groom=YASAK_PEASANT_MALE))')
    said, walked = _sides(text, "VSR001")
    assert [json.loads(k[1])["field"] for k in said] == ["status_groom"]
    assert [json.loads(k[1])["field"] for k in walked] == ["status_male"]


# --- RVR001: what the export represents ----------------------------------------------------------------

PAGES = f'd = death_records({HEAD}, 1857, {{}})'


def _rvr(body: str, records: str = "death_records") -> tuple[set[str], set[str]]:
    """The RVR001 variants `dsllint` gives of `death_records(…, body)` — or of another set's call, `records` — (all of
    them, the page's too), and the walk."""
    text = PAGES.replace("death_records", records).format(body)
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        path = Path(tmp) / "Примерово" / "sample.py"
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
        said = {m.variant for r in check_file_json(path) for i in r["issues"]
                if getattr(m := i["message"], "code", "") == "RVR001"}
    return said, {f.variant for f in on_json.lint_records(_encode(text), codes=["RVR001"])}


def test_a_pages_flag_equal_to_the_default_leaves_no_trace():
    """`page(reviewed=True)` over the default `True` and no flag at all give the same JSON, so a page's own variants
    (`page_*`, `inner_page_*`) cannot be told from the record set's: the walk abstains on every labelled run and
    the oracle declares what `dsllint` finds there absent on JSON (`SOURCE_ONLY`). Likewise `False` over `False`."""
    flagged = PAGES.format('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True), reviewed=True)')
    plain = PAGES.format('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True))')
    assert _encode(flagged) == _encode(plain)
    said, walked = _rvr('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True), reviewed=True)')
    assert said == {"page_labelled_default", "inner_page_labelled"} and walked == set()
    said, walked = _rvr('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True))')
    assert said == {"inner_records_default"} and walked == set()
    held = 'death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=False)'
    assert _encode(PAGES.format(f'*page("1", {held}, reviewed=False), reviewed=False')) == _encode(
        PAGES.format(f'*page("1", {held}), reviewed=False'))


def test_a_record_outside_every_page_is_answered_beside_an_unflagged_one():
    said, walked = _rvr('death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True)')
    assert said == walked == {"inner_records_default"}
    said, walked = _rvr('death(1, Gender.MALE, 5, reviewed=False), death(2, Gender.MALE, 5), reviewed=False')
    assert said == walked == {"inner_records_set"}


def test_a_divorces_flag_is_answered_as_a_deaths():
    """A divorce has its `reviewed=` as the other kinds do: the walk finds the flag its book repeats — and not the
    `False` a `page(None, reviewed=True)` makes load-bearing, which its default `True` would hide from the replay."""
    def rvr(body: str) -> tuple[set[str], set[str]]:
        return _rvr(body, "divorce_records")

    assert rvr('divorce(1, 5), divorce(2, 5, reviewed=True)') == ({"inner_records_default"},) * 2
    assert rvr('divorce(1, 5, reviewed=False), divorce(2, 5), reviewed=False') == ({"inner_records_set"},) * 2
    assert rvr('divorce(1, 5), divorce(2, 5, reviewed=False)') == (set(), set())
    assert rvr('*page(None, divorce(1, 5), divorce(2, 5, reviewed=False), reviewed=True), reviewed=False') == (
        set(), set())


def test_a_run_of_explicit_flags_alone_is_not_answered():
    """Nothing in the run shows that no `page(None, …)` lies over it: dsllint finds what the set repeats, the
    walk (whose false finding would invite removing a flag) says nothing."""
    said, walked = _rvr('death(1, Gender.MALE, 5, reviewed=True)')
    assert said == {"inner_records_default"} and walked == set()
    said, walked = _rvr('death(1, Gender.MALE, 5, reviewed=False), reviewed=False')
    assert said == {"inner_records_set"} and walked == set()


def test_a_labelled_run_is_not_answered():
    """A page of explicit flags alone, a page that wrote another flag, a page that wrote the set's own: the walk
    says nothing in each, where `dsllint` finds what the page leaves redundant."""
    said, walked = _rvr('*page("1", death(1, Gender.MALE, 5, reviewed=True))')
    assert said == {"inner_records_default"} and walked == set()
    said, walked = _rvr('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=True), reviewed=False)')
    assert said == walked == set()
    said, walked = _rvr('*page("1", death(1, Gender.MALE, 5), death(2, Gender.MALE, 5, reviewed=False), reviewed=False)')
    assert said == {"inner_page_labelled"} and walked == set()


def test_a_label_repeated_by_two_pages_is_one_run_and_proves_nothing():
    """The encoder merges consecutive records of one label: death 1 inherits `False` from its page and is not
    redundant, yet the run holds death 2's `True` from the set. The walk must not call death 1's flag the set's."""
    body = '*page("5", death(1, Gender.MALE, 5, reviewed=True), reviewed=False), *page("5", death(2, Gender.MALE, 5))'
    assert len(_encode(PAGES.format(body))["documents"][0]["pages"]) == 1
    assert _rvr(body) == (set(), set())
    sections = ('*page("5", *death_month(Month.MAY, death(1, Gender.MALE, 5, reviewed=True)), reviewed=False), '
                '*page("5", *death_month(Month.JUNE, death(2, Gender.MALE, 5)))')
    assert _rvr(sections) == (set(), set())


def test_a_page_with_no_number_cannot_hide_behind_a_run():
    """`page(None, …)` leaves the records with no leaf: a run that looks page-less. A record of it that wrote no flag
    shows the page's, and the walk abstains when that differs from the set's; over records that all wrote their own
    it shows nothing, and the walk abstains on that too — dsllint finds nothing there, the walk no false finding."""
    body = 'page(None, death(1, Gender.MALE, 5, reviewed=True), death(2, Gender.MALE, 5), reviewed=False)'
    assert len(_encode(PAGES.format(f'*{body}'))["documents"][0]["pages"]) == 1
    assert _rvr(f'*{body}') == (set(), set())
    assert _rvr('*page(None, death(1, Gender.MALE, 5, reviewed=True), reviewed=False)') == (set(), set())


def test_the_residue_a_page_with_no_number_beside_page_less_records():
    """Pinned, not wanted: the run of a `page(None, …)` of explicit flags and the page-less record after it is one
    run, and the record shows the set's value. The call is outside the DSL's contract (a leaf is a `str`)."""
    said, walked = _rvr('*page(None, death(1, Gender.MALE, 5, reviewed=True), reviewed=False), death(2, Gender.MALE, 5)')
    assert said == set() and walked == {"inner_records_default"}


def test_a_record_set_that_wrote_the_flag_is_named_so():
    said, walked = _rvr('death(1, Gender.MALE, 5, reviewed=False), death(2, Gender.MALE, 5), reviewed=False')
    assert said == walked == {"inner_records_set"}


# --- the positional codes: the form of an argument is not in the export (Д3) -----------------------------------

def _raw_codes(text: str) -> Counter[str]:
    """The codes `dsllint` gives of `text`, as the checks name them (a positional code NOT folded into its keyword one)."""
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        path = Path(tmp) / "Примерово" / "sample.py"
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
        codes = (getattr(i["message"], "code", "") for r in check_file_json(path) for i in r["issues"])
        return Counter(code for code in codes if code.startswith(("BRD", "CRD")))


def _birth_of(father: str, mother: str) -> str:
    return f'b = birth_records({HEAD}, 1857, birth(1, Gender.MALE, 3, 4, father={father}, mother={mother}))'


def _household_of(son: str) -> str:
    return (f'c = census_records({HEAD.rsplit(",", 1)[0]}, 1858, household("1", member(1, person("Петр", "Лукин", "Образцов"), '
            f'CensusRole.HEAD, age=40), member(2, {son}, CensusRole.SON, 1, age=10)))')


@pytest.mark.parametrize("keyword, positional, codes", [
    (_birth_of('person("Петр", residence="Ротозеево")', 'person("Мария", None, None, None, None, None, residence="Ротозеево")'),
     _birth_of('person("Петр", residence="Ротозеево")', 'person("Мария", None, None, None, None, None, "Ротозеево")'),
     ("BRD001", "BRD002")),
    (_birth_of('person("Петр", "Лукин", "Образцов")', 'person("Мария", None, last_name_orig="Образцова", last_name_in_book=False)'),
     _birth_of('person("Петр", "Лукин", "Образцов")', 'person("Мария", None, "Образцова", last_name_in_book=False)'),
     ("BRD003", "BRD004")),
    (_household_of('person("Иван", "Лукин", last_name_orig="Образцов")'),
     _household_of('person("Иван", "Лукин", "Образцов")'), ("CRD002", "CRD003")),
    (_household_of('person("Иван", patr_orig="Петров")'), _household_of('person("Иван", "Петров")'), ("CRD005", "CRD006")),
], ids=["residence", "surname", "census-surname", "patronymic"])
def test_written_hides_the_form(keyword: str, positional: str, codes: tuple[str, str]):
    """A redundant argument written by keyword (BRD001, BRD003, CRD002, CRD005) and the same argument written by
    position (the next code) leave the same `written`: the export holds an argument by its parameter, so the pair
    answers as one code (`hosted.toml`'s `as`) and the walk speaks the keyword form. `dsllint` tells the two apart;
    the exports of the two texts are equal (the positional call writes its skipped parameters as Nones, so the
    keyword text here does too: whether a call skipped them by position is not something a keyword call can show)."""
    by_keyword, by_position = codes
    assert by_keyword in _raw_codes(keyword) and by_position not in _raw_codes(keyword)
    assert by_position in _raw_codes(positional) and by_keyword not in _raw_codes(positional)
    assert _encode(keyword) == _encode(positional)
    table = hosted.readiness()
    assert table[by_position].as_code == by_keyword and table[by_keyword].as_code is None


# --- the rules of a birth, a death and a roll ------------------------------------------------------------------

FATHER = 'father=person("Петр", "Лукин", "Образцов", residence="Ротозеево")'


def _births_of(*records: str, defaults: str = "") -> str:
    return f'b = birth_records({HEAD}, 1857, {", ".join(records)}{defaults})'


def _roll_of(*members: str, defaults: str = "") -> str:
    return (f'c = census_records({HEAD.rsplit(",", 1)[0]}, 1858, household("1", '
            f'member(1, person("Петр", "Лукин", "Образцов"), CensusRole.HEAD, age=40), {", ".join(members)}){defaults})')


def test_old_export_refuses_the_rules_that_read_the_objects():
    """BRD00n and CRD00n read the family's surname off the replayed objects, CSR001 the book's defaults: an export
    from before 0.1.16 is asked for again. DRA002 reads what the call wrote and has no use for the context."""
    for code, text in (("BRD001", _births_of(f'birth(1, Gender.MALE, 3, 4, {FATHER})')),
                       ("CRD001", _roll_of('member(2, person("Иван"), CensusRole.SON, 1, age=3)')),
                       ("CSR001", _roll_of('member(2, person("Иван"), CensusRole.SON, 1, age=3)',
                                           defaults=', defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE)'))):
        old = _old(_encode(text))
        with pytest.raises(Unsupported) as refused:
            on_json.lint_records(old, codes=[code])
        assert refused.value.message.key == "on_json.no_context"
    old = _old(_encode(DEATH))
    assert on_json.lint_records(old, codes=["DRA002"]) == []


def test_a_residence_the_family_does_not_state_is_not_the_books_default():
    """The replayed child and mother hold the book's residence and the father's; the check compares what each call
    wrote. A child written at the book's village with no father and mother residence says nothing of the family."""
    text = _births_of('birth(1, Gender.MALE, 3, 4, child=person("Иван", residence="Ротозеево"), '
                      'father=person("Петр"), mother=person("Мария"))',
                      'birth(2, Gender.MALE, 3, 4, child=person("Иван", residence="Ротозеево"), '
                      'father=person("Петр", residence="Ротозеево"), mother=person("Мария"))',
                      defaults=', defaults=RecordDefaults(residence="Ротозеево")')
    assert _agree(text, "BRD001") == 1                      # the second: the father's village is the child's


def test_a_daughters_surname_is_her_mothers_written_not_the_one_inherited():
    """A mother who wrote none is given the father's feminized by `Birth.__init__`; the daughter's derived surname
    is then that, whether it is read off the mother's object or off the father's."""
    text = _births_of('birth(1, Gender.FEMALE, 3, 4, child=person("Анна", last_name_orig="Образцова", last_name_in_book=False), '
                      f'{FATHER}, mother=person("Мария"))')
    assert _agree(text, "BRD003") == 1


def test_a_surname_written_with_none_is_none():
    """`last_name_modern_orth=None` written by keyword is a kwarg the check reads as the father's surname being
    unreadable (no surname rule runs); the export holds none, and the father's surname is the one `last_name_orig`
    gave: the walk answers where the check is silent."""
    text = _births_of('birth(1, Gender.MALE, 3, 4, child=person("Иван", last_name_orig="Образцов", last_name_in_book=False), '
                      'father=person("Петр", "Лукин", "Образцов", last_name_modern_orth=None))')
    assert _only_walk(text, "BRD003") == 1


def test_a_gender_given_by_keyword_is_read_here_and_not_there():
    """`_record_gender` reads the record's second positional argument; `birth(1, gender=Gender.MALE)` is silent in the
    source for a child's surname, and the same record in the JSON is a son."""
    text = _births_of(f'birth(1, gender=Gender.MALE, b_day=3, child=person("Иван", last_name_orig="Образцов", '
                      f'last_name_in_book=False), {FATHER})')
    assert _only_walk(text, "BRD003") == 1


def test_a_modern_surname_given_by_position_is_read():
    """The check reads a person's surname by position at index 2 and its residence at 6, and the modern one by keyword
    alone: a positional `last_name_modern_orth` (index 5) is no kwarg there, and a value to the walk."""
    text = _births_of(f'birth(1, Gender.MALE, 3, 4, child=person("Иван", None, "Образцов", None, None, "Лукин", '
                      f'last_name_in_book=False), {FATHER})')
    said, walked = _sides(text, "BRD003")
    assert sum(said.values()) == 1 and not walked


def test_a_gender_given_by_keyword_in_a_roll_is_the_same_gender():
    """`person(gender=Gender.FEMALE)` is the key the check reads, the roll's sons and daughters being the roles."""
    text = _roll_of('member(2, person("Анна", "Петрова", gender=Gender.FEMALE, birth_last_name_modern_orth="Образцова"), '
                    'CensusRole.DAUGHTER, 1, age=3)')
    assert _agree(text, "CRD004") == 1 and _agree(text, "CRD005") == 1


def test_a_grandsons_surname_chains_through_the_son_the_generator_gave_one():
    """A son with no surname gets the head's; the grandson naming him derives it (the object holds the son's)."""
    text = _roll_of('member(2, person("Иван"), CensusRole.SON, 1, age=30)',
                    'member(3, person("Лука", last_name_orig="Образцов"), CensusRole.GRANDSON, 2, age=5)')
    assert _agree(text, "CRD002") == 1


def _said_and_walked(text: str, code: str) -> tuple[int, int]:
    said, walked = _sides(text, code)
    return sum(said.values()), sum(walked.values())


def test_a_circular_pair_is_load_bearing_for_both():
    """A grandson (no surname) naming a son who writes «Образцов» and names him back: the generator makes one pass, the
    grandson reads the son's surname and derives it, and the son's own is what the grandson derived from. Removing it
    leaves both with none, so neither the walk nor the check calls it redundant."""
    text = _roll_of('member(2, person("Никифор"), CensusRole.GRANDSON, 3, age=6)',
                    'member(3, person("Семен", "Иванович", "Образцов"), CensusRole.SON, 2, age=16)')
    assert _said_and_walked(text, "CRD002") == (0, 0)


def test_a_source_the_generator_had_not_reached_is_not_read():
    """The generator makes ONE pass in member order: a source that derives its surname has it only for the members listed
    after it. A grandson who wrote «Образцов» and names a son listed LATER who derives his from the head: at the
    grandson's turn the son has none, so the grandson's is not what he would have been given, and neither reader calls
    it redundant."""
    text = _roll_of('member(2, person("Никифор", last_name_orig="Образцов"), CensusRole.GRANDSON, 3, age=6)',
                    'member(3, person("Семен", "Иванович"), CensusRole.SON, 1, age=16)')
    assert _said_and_walked(text, "CRD002") == (0, 0)
    ahead = _roll_of('member(2, person("Семен", "Иванович"), CensusRole.SON, 1, age=16)',
                     'member(3, person("Никифор", last_name_orig="Образцов"), CensusRole.GRANDSON, 2, age=6)')
    assert _agree(ahead, "CRD002") == 1                      # listed after: the chain is read


def test_a_member_naming_itself_is_not_its_own_source():
    """A member who names himself has his own surname for a source; the generator cannot derive it from himself, so it
    is load-bearing, and neither reader calls it redundant."""
    text = _roll_of('member(2, person("Никифор", last_name_modern_orth="Образцов"), CensusRole.GRANDSON, 2, age=6)')
    assert _said_and_walked(text, "CRD001") == (0, 0)


def test_a_daughters_maiden_name_beside_her_own_surname_is_load_bearing():
    """A daughter who writes a current surname is given no maiden name by the generator: the one she writes is hers."""
    text = _roll_of('member(2, person("Анна", "Петрова", last_name_orig="Другова", '
                    'birth_last_name_modern_orth="Образцова"), CensusRole.DAUGHTER, 1, age=30)')
    assert _said_and_walked(text, "CRD004") == (0, 0)
    alone = _roll_of('member(2, person("Анна", "Петрова", birth_last_name_modern_orth="Образцова"), '
                     'CensusRole.DAUGHTER, 1, age=15)')
    assert _agree(alone, "CRD004") == 1


def test_a_source_who_wrote_a_surname_is_read_wherever_it_is_listed():
    """A source that wrote its surname has it at the grandson's turn, listed before or after."""
    text = _roll_of('member(2, person("Никифор", last_name_orig="Образцов"), CensusRole.GRANDSON, 3, age=6)',
                    'member(3, person("Семен", "Иванович", "Образцов"), CensusRole.SON, 1, age=16)')
    assert _agree(text, "CRD002") == 2                       # the grandson's and the son's, both from the head


@pytest.mark.parametrize("folded, kept", [("BRD002", "BRD001"), ("BRD004", "BRD003"), ("CRD003", "CRD002"),
                                           ("CRD006", "CRD005")])
def test_a_positional_code_asks_its_keyword_codes_findings(folded: str, kept: str):
    """The export holds no form, so `codes=["BRD002"]` is the findings of BRD001, spoken as BRD001."""
    text = {"BRD": _births_of(f'birth(1, Gender.MALE, 3, 4, {FATHER}, mother=person("Мария", None, None, None, None, None, '
                              '"Ротозеево"))', 'birth(2, Gender.MALE, 3, 4, father=person("Петр", "Лукин", "Образцов"), '
                              'mother=person("Мария", None, "Образцова", last_name_in_book=False))'),
            "CRD": _roll_of('member(2, person("Иван", "Петров", "Образцов"), CensusRole.SON, 1, age=3)')}[folded[:3]]
    data = _encode(text)
    asked = on_json.lint_records(data, codes=[folded])
    assert asked and {f.code for f in asked} == {kept}
    assert asked == on_json.lint_records(data, codes=[kept])
    assert {f.code for f in on_json.lint_records(data, codes=[folded, kept])} == {kept}


def test_a_gender_given_by_position_is_read_here_and_not_there():
    """The check's `_gender` reads the `gender=` keyword; `Лука` is a name the table gives no sex, and the sex the head
    wrote at index 8 is the walk's alone."""
    text = (f'c = census_records({HEAD.rsplit(",", 1)[0]}, 1858, household("1", member(1, person("Лука", None, None, None, '
            'None, None, None, YASAK_PEASANT_FEMALE, Gender.FEMALE), CensusRole.HEAD, age=40)), '
            'defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE, status_female=YASAK_PEASANT_FEMALE))')
    assert _said_and_walked(text, "CSR001") == (0, 1)


def test_relatives_passed_as_a_tuple_are_read_here_and_not_there():
    text = (f'd = death_records({HEAD}, 1857, death(1, Gender.MALE, 9, 8, d_month=Month.MAY, b_month=Month.MAY, '
            'deceased=person("Лука", residence="Ротозеево"), '
            'relatives=(relative(person("Петр", residence="Ротозеево"), Relationship.FATHER),)))')
    assert _said_and_walked(text, "DRA002") == (0, 1)


def test_a_contradicted_death_repeats_nothing():
    """A relative's residence equal to the deceased's, beside one that differs: the generator's anchor is the first
    relative stating a residence, so neither reader calls the copy redundant (DRA001 says the contradiction)."""
    text = (f'd = death_records({HEAD}, 1857, death(1, Gender.MALE, 9, 8, d_month=Month.MAY, b_month=Month.MAY, '
            'deceased=person("Лука", residence="Ротозеево"), '
            'relatives=[relative(person("Петр", residence="Ротозеево"), Relationship.FATHER), '
            'relative(person("Мария", residence="Заманиловка"), Relationship.MOTHER)]))')
    assert _said_and_walked(text, "DRA002") == (0, 0)
    assert _agree(text, "DRA001") == 1


def test_a_roll_member_built_outside_the_household_call_is_read():
    text = ('def son(): return member(2, person("Иван", last_name_orig="Образцов"), CensusRole.SON, 1, age=3)\n'
            + _roll_of("son()"))
    assert _only_walk(text, "CRD002") == 1


def test_two_names_of_one_status_in_a_roll_are_one_value():
    text = _roll_of('member(2, person("Иван", status=GOSUDARSTVENNYJ_PEASANT_MALE), CensusRole.SON, 1, age=3)',
                    defaults=', defaults=RecordDefaults(status_male=STATE_PEASANT_MALE)')
    said, walked = _sides(text, "CSR001")
    assert not said and [json.loads(k[1])["status"] for k in walked] == ["STATE_PEASANT_MALE"]


def test_a_hidden_member_is_not_in_the_book():
    text = _roll_of('member(2, person("Иван", status=YASAK_PEASANT_MALE), CensusRole.SON, 1, age=3, hidden=True)',
                    'member(3, person("Иван", status=YASAK_PEASANT_MALE), CensusRole.SON, 1, age=3)',
                    defaults=', defaults=RecordDefaults(status_male=YASAK_PEASANT_MALE)')
    assert _agree(text, "CSR001") == 1                      # the third


def test_a_relatives_residence_is_the_deceaseds_by_position_too():
    text = (f'd = death_records({HEAD}, 1857, death(1, Gender.MALE, 9, 8, d_month=Month.MAY, b_month=Month.MAY, '
            'deceased=person("Лука", residence="Ротозеево"), '
            'relatives=[relative(person("Петр", None, None, None, None, None, "Ротозеево"), Relationship.FATHER)]))')
    said, walked = _sides(text, "DRA002")
    assert said == walked and sum(walked.values()) == 1
    assert [k[2] for k in walked] == ["redundant"] and json.loads(next(iter(walked))[1]) == {"val": "Ротозеево"}
