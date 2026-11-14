"""A record rebuilt alone, given its set's header and its place in the set (`replay_record`, 0.1.21).

A hosted store keeps one record per row and rebuilds ONE record per edit. A record is a function of its
`written`, its set's header (the book's defaults, its parish, `civil`, `reviewed`) and two counters its place in
the set gives it: the 1-based `index` of a list's entry or a card, and the roll's running number over a
household's members. The books here are invented: a births book with defaults and a priest, a roll of three
дворы (one with a hidden member, one that writes a whole number of its own), a list of three entries and
three cards.
"""
from __future__ import annotations

import json
from calendar import Month
from collections.abc import Iterator
from typing import Any, cast

import pytest

from records_alone import located
from verso.core.records import FormatError
from verso.core.records.encode import encode_namespace
from verso.core.records.graph import first_difference
from verso.core.records.ids import Ids
from verso.core.records.replay import Position, position_values, replay_file
from verso.core.records.replay import replay_record as _replay_record
from verso.ru.domain import Gender, RecordDefaults, page, person
from verso.ru.domain.status import Status
from verso.ru.dsl.records.births import birth, birth_month, birth_records
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.external_sources import external_source_records, wwi_record
from verso.ru.dsl.records.name_lists import listed_person, name_list_records

def replay_record(node: dict[str, Any], *, header: dict[str, Any], page: str | None, position: Position) -> Any:
    """`verso.core.records.replay.replay_record`, its record typed as the object it is for these tests."""
    return _replay_record(node, header=header, page=page, position=position)


PEASANT = Status("крестьянин", Gender.MALE)
PEASANT_WIFE = Status("крестьянская жена", Gender.FEMALE)


def _namespace() -> dict[str, Any]:
    books = birth_records(
        "ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1900,
        *page("1", *birth_month(
            Month.JANUARY,
            birth(1, Gender.MALE, 3, 4, child=person("Иванъ"),
                  father=person("Петръ", "Ивановъ", "Сидоровъ", status=PEASANT), mother=person("Марья", "Петрова"),
                  priest=person("Василій", "Петровъ")),
            birth(2, Gender.FEMALE, 5, 6, child=person("Анна"), father=person("Петръ"), reviewed=False))),
        *page("1об", *birth_month(
            Month.FEBRUARY,
            birth(3, Gender.FEMALE, 7, 8, child=person("Марья"), father=person("Иванъ")))),
        defaults=RecordDefaults(residence="Маниловка", status_male=PEASANT, status_female="крестьянка",
                                status_mother=PEASANT_WIFE),
    )
    vars(books.records[1])["on_geni"] = True            # a listed record, as `ratchet.admit` marks it
    roll = census_records(
        "ГАРО", "735", "265", "53", "Заманиловка", 1858,
        *page("80",
              household("1",
                        member(1, person("Иванъ", "Петровъ", status=PEASANT), CensusRole.HEAD, age=40),
                        member(2, person("Марья", status=Status("крестьянка", Gender.FEMALE)), CensusRole.WIFE, age=35),
                        member(-1, person("Петръ"), CensusRole.FATHER, hidden=True),
                        member(3, person("Петръ"), CensusRole.SON, ref_member=1, age=6)),
              household("2",
                        member(1, person("Василій", "Петровъ"), CensusRole.HEAD, age=50),
                        member(2, person("Анна"), CensusRole.WIFE, age=45))),
        *page("81",
              household("3",
                        member(1, person("Иванъ", "Сидоровъ"), CensusRole.HEAD, age=30),
                        member(2, person("Марья"), CensusRole.WIFE, age=28),
                        member(3, person("Анна"), CensusRole.DAUGHTER, ref_member=1, age=5))),
        reviewed=False,
    )
    voters = name_list_records(
        "ГАТО", "1978", "5", "9700", "Горюхино", 1917,
        *page("5", listed_person(1, person("Иванъ", "Петровъ", "Сидоровъ"), age=40),
              listed_person(2, person("Петръ", "Ивановъ", "Сидоровъ"))),
        *page("6", listed_person(3, person("Анна", "Петрова"), age=33)),
        document_type="Список избирателей", labels=["Other"],
    )
    cards = external_source_records(
        "Маниловка",
        wwi_record(person("Иванъ", "Петровъ"), source_url="https://gwar.mil.ru/heroes/a1/"),
        wwi_record(person("Петръ", "Ивановъ"), source_url="https://gwar.mil.ru/heroes/a2/"),
        wwi_record(person("Василій", "Сидоровъ"), source_url="https://gwar.mil.ru/heroes/a3/"),
    )
    return {"births": books, "roll": roll, "voters": voters, "cards": cards}


def _export(ns: dict[str, Any]) -> dict[str, Any]:
    doc = encode_namespace(ns, village="Маниловка", file="1900/f.py", sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


@pytest.fixture(scope="module")
def book() -> tuple[dict[str, Any], dict[str, object]]:
    data = _export(_namespace())
    return data, replay_file(data, context=False)


def _records(data: dict[str, Any], whole: dict[str, object]) -> Iterator[tuple[dict[str, Any], str | None, dict[str, Any], Position, Any]]:
    for item in located(data, whole):
        yield item.header, item.page, item.node, item.position, item.built


def _ids(book: tuple[dict[str, Any], dict[str, object]]) -> list[str]:
    return [record["id"] for _, _, record, _, _ in _records(*book)]


def test_the_fixture_has_every_positional_kind(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    kinds = {record["kind"] for _, _, record, _, _ in _records(*book)}
    assert {"birth", "household", "listed_person", "external_record"} <= kinds
    assert len(_ids(book)) == 3 + 3 + 3 + 3


@pytest.mark.parametrize("which", range(12))
def test_record_alone_equals_record_in_book(book: tuple[dict[str, Any], dict[str, object]], which: int) -> None:
    header, leaf, node, position, in_book = list(_records(*book))[which]
    alone = replay_record(node, header=header, page=leaf, position=position)
    assert first_difference(in_book, alone) is None, node["id"]


def test_without_its_position_a_roll_member_is_numbered_from_one(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    """What `Position` is for: the third двор alone, numbered as a roll of its own, is not the third двор of the roll."""
    located = [item for item in _records(*book) if item[2]["kind"] == "household"]
    header, leaf, node, position, in_book = located[2]
    assert position.members_before == 5            # the book's two earlier дворы: 3 + 2 numbered members
    wrong = replay_record(node, header=header, page=leaf, position=Position(position.ordinal))
    assert [m.record_number for m in wrong.members] == [1, 2, 3]
    assert [m.record_number for m in in_book.members] == [6, 7, 8]


def test_a_hidden_member_takes_no_number(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    header, leaf, node, position, _ = next(item for item in _records(*book) if item[2]["kind"] == "household")
    alone = replay_record(node, header=header, page=leaf, position=position)
    assert [m.record_number for m in alone.members] == [1, 2, None, 3]
    assert position_values(node, position=position) == {
        "members[0].record_number": 1, "members[1].record_number": 2, "members[3].record_number": 3}


def test_position_values_match_replay(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    for header, leaf, node, position, _ in _records(*book):
        values = position_values(node, position=position)
        alone = replay_record(node, header=header, page=leaf, position=position)
        for path, number in values.items():
            if path == "index":
                assert alone.index == number, node["id"]
            else:
                place, attr = path.removesuffix("]").replace("members[", "").split("].")
                assert getattr(alone.members[int(place)], attr) == number, (node["id"], path)
        if node["kind"] in ("birth",):
            assert values == {}
        if node["kind"] in ("listed_person", "external_record"):
            assert values == {"index": position.ordinal + 1}


def test_position_values_follow_the_position(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    """A structural act moves only the records after it: the same node at another place gives the other values."""
    _, _, node, position, _ = next(item for item in _records(*book) if item[2]["kind"] == "listed_person")
    assert position_values(node, position=Position(position.ordinal + 4)) == {"index": position.ordinal + 5}
    roll = next(item for item in _records(*book) if item[2]["kind"] == "household")[2]
    assert position_values(roll, position=Position(0, 10)) == {
        "members[0].record_number": 11, "members[1].record_number": 12, "members[3].record_number": 13}


def test_explicit_record_number_is_kept() -> None:
    """A member that writes a whole number keeps it, takes no value from the position, and the count goes on from it."""
    ns = {"roll": census_records(
        "ГАРО", "735", "265", "53", "Заманиловка", 1858,
        *page("80", household("1",
                              member(1, person("Иванъ", "Петровъ", status=PEASANT), CensusRole.HEAD, age=40),
                              member(2, person("Марья"), CensusRole.WIFE, age=35, record_number=40),
                              member(3, person("Петръ"), CensusRole.SON, ref_member=1, age=6))),
        reviewed=False)}
    data = _export(ns)
    node, header = data["documents"][0]["pages"][0]["records"][0], {k: v for k, v in data["documents"][0].items()
                                                                     if k != "pages"}
    in_book = cast(Any, replay_file(data, context=False)["roll"]).households[0]
    assert [m.record_number for m in in_book.members] == [1, 40, 41]
    alone = replay_record(node, header=header, page="80", position=Position(0))
    assert first_difference(in_book, alone) is None
    assert position_values(node, position=Position(0)) == {
        "members[0].record_number": 1, "members[2].record_number": 41}
    shifted = replay_record(node, header=header, page="80", position=Position(1, 7))
    assert [m.record_number for m in shifted.members] == [8, 40, 41]


def test_a_node_no_factory_builds_is_a_format_error(book: tuple[dict[str, Any], dict[str, object]]) -> None:
    header, leaf, node, position, _ = next(iter(_records(*book)))
    with pytest.raises(FormatError):
        replay_record({**node, "kind": "nothing"}, header=header, page=leaf, position=position)
    with pytest.raises(FormatError):
        replay_record({k: v for k, v in node.items() if k != "kind"}, header=header, page=leaf, position=position)
