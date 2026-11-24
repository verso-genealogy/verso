"""What a wrapper set lives in `written` (records v1.x): a section's month, a лист's provenance, a
book's name — under the attribute's own key, named in `written.context`, never also in `derived` —
so `replay_file(..., context=False)` rebuilds the DSL's graph from `written` alone. An export of
before (the values in `derived`, no marker) still replays with `context=True`."""
from __future__ import annotations

import json
from calendar import Month
from collections.abc import Callable
from typing import Any

import pytest

from test_records_replay_ru import as_before_v1x
from verso.core.records import FormatError
from verso.core.records.decode import decode_file
from verso.core.records.encode import encode_namespace
from verso.core.records.fields import CONTEXT_KEY, split_context, vocabulary
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import replay_file
from verso.core.records.schema import build_schema
from verso.ru.domain import EventDate, Gender, book, page, person
from verso.ru.dsl.records.births import Birth, birth, birth_month_year, birth_records


def _encode(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Маниловка", file="1850/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _records(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for run in data["documents"][0]["pages"] for r in run["records"]]


def _without_derived(node: Any) -> Any:
    if isinstance(node, list):
        return [_without_derived(x) for x in node]
    if not isinstance(node, dict):
        return node
    return {k: _without_derived(v) for k, v in node.items() if k != "derived"}


def _births(*records: Birth) -> Any:
    return birth_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1850, *records)


def _section() -> dict[str, Any]:
    return {"births": _births(*page("12", *birth_month_year(
        Month.MARCH, 1850,
        birth(1, Gender.MALE, 3, 4, child=person("Иванъ"), father=person("Петръ")),
        birth(2, Gender.FEMALE, 5, 6, child=person("Анна"), father=person("Василій"), reviewed=False))))}


def test_section_month_in_written() -> None:
    first = _records(_encode(_section()))[0]
    assert first["written"]["birth"] == {"day": 3, "month": "march"}
    assert first["written"]["baptism"] == {"day": 4, "month": "march"}
    assert first["written"]["year"] == 1850
    assert {"birth.month", "baptism.month", "year"} <= set(first["written"][CONTEXT_KEY])
    assert not {"birth", "baptism", "year"} & set(first["derived"])


def test_replay_without_context_flag_keeps_section() -> None:
    ns = _section()
    data = _encode(ns)
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, replay_file(data, context=True)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_shared_page_object_stays_shared() -> None:
    ns = _section()
    replayed: Any = replay_file(_without_derived(_encode(ns)), context=False)
    one, two = replayed["births"].records
    assert one.page == "12" and one.page is two.page
    assert first_difference(ns, replayed) is None


def test_old_export_context_in_derived_still_replays() -> None:
    ns = _section()
    old, moved = as_before_v1x(_encode(ns))
    assert moved and all(CONTEXT_KEY not in r["written"] for r in _records(old))
    assert _records(old)[0]["derived"]["birth"] == {"month": "march"}
    assert first_difference(ns, replay_file(old)) is None
    assert first_difference(ns, decode_file(old)) is None
    found = first_difference(ns, replay_file(old, context=False))
    assert found is not None and "month" in found


def test_a_calls_own_value_stays_the_calls() -> None:
    """`birth(..., reviewed=False)` wrote its flag: it is no wrapper's, and replay hands it to the
    factory — the `_written` the DSL made — rather than setting it after."""
    ns = _section()
    second = _records(_encode(ns))[1]
    assert second["written"]["reviewed"] is False and "reviewed" not in second["written"][CONTEXT_KEY]
    assert second["review"] == "held"
    replayed: Any = replay_file(_without_derived(_encode(ns)), context=False)
    assert replayed["births"].records[1]._written["reviewed"] is False
    assert "reviewed" not in replayed["births"].records[0]._written


def test_a_wrapper_flag_and_the_review_state_are_two_things() -> None:
    """A `page(reviewed=False)` holds the record: `written.reviewed` is the flag the wrapper set
    (marked), `review` the node's state the encoder derives from it — the decoder holds the two
    to each other, so neither repeats the other."""
    ns = {"births": _births(*page("7", birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY,
                                             child=person("Иванъ")), reviewed=False))}
    data = _encode(ns)
    record = _records(data)[0]
    assert record["written"]["reviewed"] is False and "reviewed" in record["written"][CONTEXT_KEY]
    assert record["review"] == "held" and "reviewed" not in record["derived"]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    record["review"] = "reviewed"
    with pytest.raises(FormatError):
        decode_file(data)


def test_a_books_name_lives_in_written() -> None:
    ns = {"births": _births(*book("Книга первая", person("Иоаннъ"),
                                  birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, child=person("Иванъ"))))}
    data = _encode(ns)
    record = _records(data)[0]
    assert record["written"]["book"] == "Книга первая" and "book" in record["written"][CONTEXT_KEY]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None


def test_split_context_refuses_a_marker_it_cannot_read() -> None:
    call, context = split_context(Birth, {"number": 1, "birth": {"day": 3, "month": "march"},
                                          CONTEXT_KEY: ["birth.month"]})
    assert call == {"number": 1, "birth.day": 3} and context == {"b_month": "march"}
    assert split_context(Birth, {"number": 1, "birth": {"month": "march"}}) == (
        {"number": 1, "birth.month": "march"}, {})
    refused = {"records.fields.context_not_a_wrapper_field": (["number"], {}),
               "records.fields.context_key_missing": (["birth.month"], {}),
               "records.fields.context_not_a_list": ("birth.month", {}),
               "records.fields.context_key_twice": (["year", "year"], {"year": 1850}),
               "records.fields.context_page": (["page"], {"page": "12"})}
    for key, (marker, extra) in refused.items():
        with pytest.raises(FormatError) as err:
            split_context(Birth, {"number": 1, **extra, CONTEXT_KEY: marker})
        assert err.value.args[0].key == key, key


def test_a_wrappers_value_held_twice_is_refused() -> None:
    data = _encode(_section())
    record = _records(data)[0]
    record["derived"]["year"] = record["written"]["year"]
    with pytest.raises(FormatError) as err:
        decode_file(data)
    assert err.value.args[0].key == "records.decode.context_collides"


def test_no_factory_parameter_takes_the_markers_key() -> None:
    schema = build_schema()["$defs"]["written_birth"]["properties"]
    assert schema[CONTEXT_KEY]["items"]["enum"][:1] and "page" not in schema[CONTEXT_KEY]["items"]["enum"]
    assert "book" in schema and "year" in schema
    voc = vocabulary()
    from verso.core.records.fields import factory_params, written_key
    for cls, spec in voc.specs.items():
        for fn in spec.factories:
            assert all(written_key(cls, p) != CONTEXT_KEY for p in factory_params(fn)), cls


# --- what a wrapper would have set on a field the call wrote: `written.wrapper` (records v1.x) -----------------

def _own_leaf() -> dict[str, Any]:
    """A record writing its own лист inside `page("11", …)`, beside one taking the page's."""
    return {"births": _births(*page("11",
        birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, child=person("Иванъ"), page="12"),
        birth(2, Gender.MALE, 5, 6, Month.MAY, Month.MAY, child=person("Петръ"))))}


def _own_months() -> dict[str, Any]:
    """Records writing their own months (and one its year) inside a March 1850 section: the section is kept."""
    return {"births": _births(*birth_month_year(
        Month.MARCH, 1850,
        birth(1, Gender.MALE, 3, 4, Month.APRIL, Month.APRIL, child=person("Иванъ")),
        birth(2, Gender.MALE, 25, 1, Month.APRIL, Month.MAY, child=person("Петръ"), year=1851),
        birth(3, Gender.FEMALE, 7, 8, child=person("Анна"))))}


def test_a_pages_leaf_beside_a_records_own_is_kept() -> None:
    ns = _own_leaf()
    data = _encode(ns)
    own, plain = _records(data)
    assert own["written"]["page"] == "12" and own["written"]["wrapper"] == {"page": "11"}
    assert "wrapper" not in plain["written"] and "wrapper" not in own["derived"]
    assert [run["page"] for run in data["documents"][0]["pages"]] == ["12", "11"]   # the runs as before
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_a_sections_months_beside_a_records_own_are_kept() -> None:
    ns = _own_months()
    first, second, third = _records(_encode(ns))
    assert first["written"]["wrapper"] == {"birth": {"month": "march"}, "baptism": {"month": "march"}}
    assert "year" in first["written"][CONTEXT_KEY] and first["written"]["birth"]["month"] == "april"
    assert not {"birth.month", "baptism.month"} & set(first["written"][CONTEXT_KEY])
    # born the 25th, christened the 1st: the christening the section would have dated is in April
    assert second["written"]["wrapper"] == {"birth": {"month": "march"}, "baptism": {"month": "april"},
                                            "year": 1850}
    assert "year" not in second["written"][CONTEXT_KEY] and second["written"]["year"] == 1851
    assert "wrapper" not in third["written"]
    data = _encode(ns)
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, replay_file(data)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_the_innermost_wrappers_value_is_kept() -> None:
    ns = {"births": _births(*page("10", *page("11", birth(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY,
                                                         child=person("Иванъ"), page="12"))))}
    assert _records(_encode(ns))[0]["written"]["wrapper"] == {"page": "11"}


def test_the_view_of_v1_0_drops_the_wrappers_values() -> None:
    from verso.core.records.encode import context_in_derived
    for ns in (_own_leaf(), _own_months()):
        for record in _records(_encode(ns)):
            assert "wrapper" not in context_in_derived(record)["written"]


def test_the_schema_holds_the_wrappers_values() -> None:
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(build_schema())
    for ns in (_own_leaf(), _own_months()):
        assert [e.message for e in validator.iter_errors(_encode(ns))] == []
    schema = build_schema()["$defs"]["written_birth"]["properties"]["wrapper"]
    assert {"page", "birth", "baptism", "year"} <= set(schema["properties"])


def test_split_wrapper_refuses_what_it_cannot_read() -> None:
    from verso.core.records.fields import WRAPPER_KEY, split_wrapper
    written = {"number": 1, "page": "12", "birth": {"month": "april"}}
    assert split_wrapper(Birth, {**written, WRAPPER_KEY: {"page": "11", "birth": {"month": "march"}}}) == {
        "page": "11", "b_month": "march"}
    assert split_context(Birth, {**written, WRAPPER_KEY: {"page": "11"}})[0] == {
        "number": 1, "page": "12", "birth.month": "april"}
    refused = [("records.fields.wrapper_not_an_object", ["page"]),
               ("records.fields.wrapper_not_a_wrapper_field", {"number": 2}),
               ("records.fields.wrapper_not_a_wrapper_field", {"church": "Покровская"})]   # set, never kept
    for key, value in refused:
        with pytest.raises(FormatError) as err:
            split_wrapper(Birth, {**written, WRAPPER_KEY: value})
        assert err.value.args[0].key == key, key
    # a key the call does not write (any more) is stale: dropped, not refused
    assert split_wrapper(Birth, {**written, WRAPPER_KEY: {"year": 1850, "page": "11"}}) == {"page": "11"}
    marked = {**written, CONTEXT_KEY: ["birth.month"], WRAPPER_KEY: {"birth": {"month": "march"}}}
    assert split_wrapper(Birth, marked) == {}


def _edited(ns: dict[str, Any], number: int, edit: Callable[[dict[str, Any]], object]) -> tuple[dict[str, Any], Any]:
    """The folder's book of `ns` (`derived` cut away) with record `number`'s `written` edited by `edit`, as an
    editor that knows nothing of `written.wrapper` (verso-app 0.5.1) edits it; and the record replayed from it."""
    data = _without_derived(_encode(ns))
    record = next(r for r in _records(data) if r["written"]["number"] == number)
    edit(record["written"])
    replayed: Any = replay_file(data, context=False)
    decode_file(_encode(ns))            # the export itself reads as before
    return record, next(r for r in replayed["births"].records if r.record_num == number)


def test_deleting_a_records_own_page_drops_the_kept_leaf() -> None:
    """`changes.moved_page`'s edit: the record's own `page=` goes, the page's leaf in `written.wrapper` is stale."""
    record, rebuilt = _edited(_own_leaf(), 1, lambda w: w.pop("page"))
    assert record["written"]["wrapper"] == {"page": "11"}          # left behind by the edit
    assert "_wrapper" not in vars(rebuilt) and rebuilt.page == "12"   # the run's leaf, as replay always set it


def test_unsetting_an_own_month_drops_the_kept_month() -> None:
    record, rebuilt = _edited(_own_months(), 1, lambda w: w["birth"].pop("month"))
    assert record["written"]["wrapper"]["birth"] == {"month": "march"}
    assert rebuilt._wrapper == {"k_month": Month.MARCH} and rebuilt.b_month is None


def test_marking_an_own_month_as_contexts_drops_the_kept_month() -> None:
    """`changes.settle`'s edit after a move into a section: the month the record wrote is now the section's —
    named in `written.context` — so the old section's month kept in `written.wrapper` is stale."""
    def settle(w: dict[str, Any]) -> None:
        w["birth"]["month"] = "may"
        w[CONTEXT_KEY] = [*w[CONTEXT_KEY], "birth.month"]
    _, rebuilt = _edited(_own_months(), 1, settle)
    assert rebuilt._wrapper == {"k_month": Month.MARCH} and rebuilt.b_month is Month.MAY


def test_a_deaths_section_is_kept_beside_a_records_own_months() -> None:
    from verso.ru.dsl.records.deaths import death, death_month_year, death_records
    ns = {"deaths": death_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1850, *death_month_year(
        Month.MARCH, 1850,
        death(1, Gender.MALE, 3, 5, Month.APRIL, Month.APRIL, deceased=person("Иванъ"), year=1851),
        death(2, Gender.MALE, 6, 8, deceased=person("Петръ"))))}
    data = _encode(ns)
    own, plain = _records(data)
    assert own["written"]["wrapper"] == {"death": {"month": "march"}, "burial": {"month": "march"}, "year": 1850}
    assert "wrapper" not in plain["written"]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_a_marriages_section_is_kept_beside_a_records_own_month() -> None:
    from verso.ru.dsl.records.marriages import marriage, marriage_month, marriage_month_year, marriage_records
    ns = {"marriages": marriage_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1850,
        *marriage_month_year(Month.MAY, 1850,
                             marriage(1, 4, Month.JUNE, groom=person("Иванъ"), bride=person("Анна"), year=1851)),
        *marriage_month(Month.MAY, marriage(2, 9, Month.JULY, groom=person("Петръ"), bride=person("Анна"))),
        *marriage_month(Month.MAY, marriage(3, 11, groom=person("Петръ"), bride=person("Анна"))))}
    data = _encode(ns)
    first, second, third = _records(data)
    assert first["written"]["wrapper"] == {"marriage": {"month": "may"}, "year": 1850}
    assert second["written"]["wrapper"] == {"marriage": {"month": "may"}}
    assert "wrapper" not in third["written"]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_a_divorces_section_and_page_are_kept_beside_a_records_own() -> None:
    from verso.ru.dsl.records.divorces import divorce, divorce_month, divorce_records
    ns = {"divorces": divorce_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1850, *page("11",
        *divorce_month(Month.MAY,
                       divorce(1, 4, Month.JUNE, husband=person("Иванъ"), wife=person("Анна"), page="12"),
                       divorce(2, 6, husband=person("Петръ"), wife=person("Анна")))))}
    data = _encode(ns)
    own, plain = _records(data)
    assert own["written"]["wrapper"] == {"divorce": {"month": "may"}, "page": "11"}
    assert "wrapper" not in plain["written"]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def _divorces(*records: Any, **kw: Any) -> Any:
    from verso.ru.dsl.records.divorces import divorce_records
    return divorce_records("ГАПО", "1605", "59", "59", "Заманиловка", "", 1923, *records, **kw)


def _divorce(number: int, **kw: Any) -> Any:
    from verso.ru.dsl.records.divorces import divorce
    return divorce(number, 3, Month.JULY, husband=person("Иванъ"), wife=person("Анна"), **kw)


def test_a_divorce_with_no_flag_writes_none() -> None:
    """A divorce book that never names the flag exports as it did before divorces had one: no `reviewed`
    in a record's `written` or `derived`, nor in the book's."""
    data = _encode({"divorces": _divorces(*page("4", _divorce(1), _divorce(2)))})
    assert "reviewed" not in data["documents"][0]["written"]
    for record in _records(data):
        assert record["review"] == "reviewed"
        assert "reviewed" not in record["written"] and "reviewed" not in record["derived"]
        assert CONTEXT_KEY not in record["written"]


def test_a_divorce_is_held_by_its_own_flag_its_page_or_its_book() -> None:
    ns = {"divorces": _divorces(_divorce(1, reviewed=False), _divorce(2),
                                *page("5", _divorce(3), reviewed=False))}
    data = _encode(ns)
    own, plain, paged = _records(data)
    assert own["review"] == "held"
    assert own["written"]["reviewed"] is False and CONTEXT_KEY not in own["written"]
    assert plain["review"] == "reviewed" and "reviewed" not in plain["written"]
    assert paged["review"] == "held"
    assert paged["written"]["reviewed"] is False and "reviewed" in paged["written"][CONTEXT_KEY]
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None

    ns = {"divorces": _divorces(_divorce(1), _divorce(2, reviewed=True), reviewed=False)}
    data = _encode(ns)
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(build_schema()).iter_errors(data))
    assert data["documents"][0]["written"]["reviewed"] is False
    held, kept = _records(data)
    assert held["review"] == "held" and "reviewed" in held["written"][CONTEXT_KEY]
    assert kept["review"] == "reviewed" and kept["written"]["reviewed"] is True
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_a_divorces_notes_are_written_and_replayed() -> None:
    """`source_date_error=` and `calendar_note=` answer the checks that read the marriage the act names: a record
    that writes neither exports as before, one that writes them carries both and replays."""
    plain = _records(_encode({"divorces": _divorces(_divorce(1))}))[0]
    assert "source_date_error" not in plain["written"] and "calendar_note" not in plain["written"]

    ns = {"divorces": _divorces(_divorce(1, marriage_date=EventDate(1913, Month.NOVEMBER, 9), source_date_error="так в акте",
                                         calendar_note="суббота, так в акте"))}
    assert (ns["divorces"].records[0].source_date_error, ns["divorces"].records[0].calendar_note) == (
        "так в акте", "суббота, так в акте")
    data = _encode(ns)
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(build_schema()).iter_errors(data))
    written = _records(data)[0]["written"]
    assert (written["source_date_error"], written["calendar_note"]) == ("так в акте", "суббота, так в акте")
    assert first_difference(ns, replay_file(_without_derived(data), context=False)) is None
    assert first_difference(ns, decode_file(data)) is None


def test_a_pages_true_over_a_held_divorce_book_replays() -> None:
    ns = {"divorces": _divorces(*page("4", _divorce(1), reviewed=True), reviewed=False)}
    data = _encode(ns)
    assert ns["divorces"].records[0].reviewed is True
    assert first_difference(ns, decode_file(data)) is None
    assert first_difference(ns, replay_file(data)) is None
