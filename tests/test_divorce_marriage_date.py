"""The marriage an act of divorce names is an `EventDate`, the library's one structure of a date; the text an older
file writes is still read, and warns.

`divorce(marriage_date=EventDate(1924, Month.MARCH, 18))` — a point, a month, a year, `circa`, a range, as an
external card's dates are. A text (`marriage_date="18 марта 1924"`) is what DSL v1 wrote until now: it is
accepted, kept as it is and exported as it is, with a `DeprecationWarning` at the line that wrote it; no reader
parses it. The CSV and the people's database write an `EventDate` the way the corpus wrote the text.
"""
from __future__ import annotations

import json
import warnings
from calendar import Month
from typing import Any

import pytest

from verso.core.records.decode import decode_file
from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import replay_file
from verso.core.records.schema import build_schema
from verso.ru.domain import EventDate, person
from verso.ru.domain.event_date import read_written_date, written_date
from verso.ru.dsl.records.divorces import divorce, divorce_records


def _divorces(*records: Any) -> Any:
    return divorce_records("ГА Глуповской области", "10", "4", "4071", "Маниловка", "", 1925, *records)


def _act(**more: Any) -> Any:
    return divorce(1, 3, Month.JULY, husband=person("Иванъ"), wife=person("Анна"), **more)


def _export(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Маниловка", file="1925/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _written(data: dict[str, Any]) -> dict[str, Any]:
    return data["documents"][0]["pages"][0]["records"][0]["written"]


def test_an_event_date_is_written_whole_and_replays():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ns = {"divorces": _divorces(_act(marriage_date=EventDate(1924, Month.MARCH, 18)))}
    data = _export(ns)
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(build_schema()).iter_errors(data))
    assert isinstance(_written(data)["marriage_date"], dict)
    assert first_difference(ns, decode_file(data)) is None
    assert first_difference(ns, replay_file(data)) is None


def test_a_text_is_still_taken_and_warns_at_the_line_that_wrote_it():
    with pytest.warns(DeprecationWarning, match="marriage_date") as warned:
        record = _act(marriage_date="18 марта 1924")
    assert record.marriage_date == "18 марта 1924"
    assert warned[0].filename == __file__


def test_a_text_exports_as_text_and_an_older_export_reads():
    with pytest.warns(DeprecationWarning):
        ns = {"divorces": _divorces(_act(marriage_date="18 марта 1924"))}
    data = _export(ns)
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(build_schema()).iter_errors(data))
    assert _written(data)["marriage_date"] == "18 марта 1924"
    # An export is read as it was written, with no call made: an older file's text reads quietly …
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert first_difference(ns, decode_file(data)) is None
    # … and replaying it calls the factory, which says so.
    with pytest.warns(DeprecationWarning):
        assert first_difference(ns, replay_file(data)) is None


def test_an_empty_text_is_no_date_and_warns_nothing():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _act(marriage_date="").marriage_date == ""


def test_no_date_warns_nothing_and_writes_nothing():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        data = _export({"divorces": _divorces(_act())})
    assert "marriage_date" not in _written(data)


@pytest.mark.parametrize("date, text", [
    (EventDate(1924, Month.MARCH, 18), "18 марта 1924"),
    (EventDate(1922, Month.APRIL, 21), "21 апреля 1922"),
    (EventDate(1924, Month.MARCH), "март 1924"),
    (EventDate(1927), "1927"),
    (EventDate(1915, circa=True), "около 1915"),
    (EventDate(1915, date_range="before"), "до 1915"),
    (EventDate(1915, Month.MAY, date_range="after"), "после мая 1915"),
    (EventDate(1914, year_end=1915), "1914–1915"),
    (EventDate(1914, Month.MAY, 3, year_end=1914, month_end=Month.JUNE, day_end=1), "3 мая 1914 – 1 июня 1914"),
    # a month after «до», «около», «после» is in the genitive, as beside a day
    (EventDate(1915, Month.MAY, date_range="before"), "до мая 1915"),
    (EventDate(1915, Month.MAY, circa=True), "около мая 1915"),
    (EventDate(1915, Month.MAY, 3, circa=True), "около 3 мая 1915"),
    (EventDate(1915, circa=True, date_range="after"), "после 1915"),
    # an end that names a day but no month of its own takes the start's
    (EventDate(1914, Month.MAY, 3, year_end=1914, day_end=9), "3 мая 1914 – 9 мая 1914"),
    # no year, nothing to write
    (EventDate(None, Month.MAY, date_range="after"), ""),
    (EventDate(), ""),
])
def test_an_event_date_is_written_as_the_corpus_writes_a_date(date: EventDate, text: str):
    assert written_date(date) == text


@pytest.mark.parametrize("text", ["18 марта 1924", "21 апреля 1922", "9 ноября 1913", "март 1924", "1927"])
def test_the_text_of_a_date_reads_back_to_the_same_text(text: str):
    date = read_written_date(text)
    assert date is not None and written_date(date) == text


@pytest.mark.parametrize("text, date", [
    ("18.03.1924", EventDate(1924, Month.MARCH, 18)),
    ("9 ноября 1913 г.", EventDate(1913, Month.NOVEMBER, 9)),
    ("9 Ноября 1913 года", EventDate(1913, Month.NOVEMBER, 9)),
    ("  1915 г. ", EventDate(1915)),
    ("марта 1924", EventDate(1924, Month.MARCH)),
    # the old spelling of the months an act of 1918–1919 may still write
    ("12 іюня 1915", EventDate(1915, Month.JUNE, 12)),
    ("7 іюля 1913", EventDate(1913, Month.JULY, 7)),
    ("3 Апрѣля 1914 г.", EventDate(1914, Month.APRIL, 3)),
    ("5 генваря 1916", EventDate(1916, Month.JANUARY, 5)),
    # the books' calendar is Julian: 1900 has its 29 February
    ("29 февраля 1900", EventDate(1900, Month.FEBRUARY, 29)),
    ("29.02.1900", EventDate(1900, Month.FEBRUARY, 29)),
])
def test_the_forms_a_date_is_written_in_are_read(text: str, date: EventDate):
    got = read_written_date(text)
    assert got is not None and (got.year, got.month, got.day) == (date.year, date.month, date.day)


@pytest.mark.parametrize("text", [None, "", "в феврале 1927 г.", "1915?", "24/II-1927", "31 февраля 1927",
                                  "24 фебруария 1927", "32.01.1927", "24 февраля", "около 1915", "29 февраля 1901",
                                  "0000", "0 мая 1925", "12 мая 1925 и 3 июня", "١٢ мая 1925", "１２ мая 1925",
                                  "12.13.1925", "12 1927", "5 1915 г.", "24.02.0000", "1 января 0000",
                                  1927, 1927.0, ["1927"], True])
def test_anything_else_reads_as_no_date(text: object):
    assert read_written_date(text) is None
