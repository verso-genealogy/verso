"""Records v1 ids: a record named as it is cited (`verso.core.records.ids`, rule r1)."""
from __future__ import annotations

import pytest

from verso.ru.domain import Gender, page, person
from verso.ru.dsl.records.births import birth, birth_records
from verso.ru.dsl.records.census import CensusRole, census_records, household, member
from verso.ru.dsl.records.external_sources import external_source_records, wwi_record
from verso.ru.dsl.records.marriages import marriage, marriage_records
from verso.core.records import FormatError
from verso.core.records.ids import (
    ID_SCHEME, BookKey, Ids, book_key, entry_token, escape, parse, person_label, persona_id, record_label)
from verso.ru.records.cite import url_key


def _births(*records):
    return birth_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1842, *records)


def _ids(records) -> list[str]:
    ids = Ids()
    return [ids.record_id(book_key(records, r), entry_token(r)) for r in records.records]


def test_a_record_is_named_as_it_is_cited():
    rs = _births(birth(1, Gender.MALE, 3, 4, child=person("Иванъ")))
    assert ID_SCHEME == "r1"
    assert _ids(rs) == ["r1:Маниловка/47-9-755/1842/birth/m1"]
    assert persona_id("r1:Маниловка/47-9-755/1842/birth/m1", "godparent", 2) == \
        "r1:Маниловка/47-9-755/1842/birth/m1/godparent2"
    assert persona_id("r1:Маниловка/47-9-755/1842/birth/m1", "child", None) == \
        "r1:Маниловка/47-9-755/1842/birth/m1/child"


def test_a_marriage_has_no_sex_in_its_number():
    rs = marriage_records("ЦГА", "47", "9", "755", "Маниловка", "Церковь", 1842,
                          marriage(12, 3, groom=person("Иванъ"), bride=person("Марья")))
    ids = Ids()
    assert ids.record_id(book_key(rs, rs.records[0]), entry_token(rs.records[0])) == \
        "r1:Маниловка/47-9-755/1842/marriage/12"


def test_an_id_does_not_move_when_a_name_is_corrected():
    before = _ids(_births(birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))))
    assert _ids(_births(birth(1, Gender.MALE, 3, 4, child=person("Петръ")))) == before


def test_an_id_does_not_move_when_a_record_is_inserted_above():
    alone = _ids(_births(birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))))
    below = _ids(_births(birth(1, Gender.FEMALE, 1, 2, child=person("Марья")),
                         birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))))
    assert below[-1] == alone[-1] == "r1:Маниловка/47-9-755/1842/birth/m1"


def test_a_repeated_number_takes_a_tilde_in_order():
    ids, k = Ids(), BookKey("Маниловка", "47-9-755", None, 1842, "birth")
    assert [ids.record_id(k, ("m", "1")), ids.record_id(k, ("m", "1"))] == [f"{k}/m1", f"{k}/m1~2"]
    assert [ids.record_id(k, ("m", "")), ids.record_id(k, ("m", ""))] == [f"{k}/m_1", f"{k}/m_2"]
    assert [ids.document_id(k), ids.document_id(k)] == [str(k), f"{k}~2"]


CARDS = BookKey("Маниловка", "card", None, None, "cards")


def test_a_set_of_cards_is_counted_among_the_sets_of_its_year():
    """A village's sets of cards state no year: each takes its file's, so an export of some of the years (a tree
    that leaves the young ones out) numbers a set as the export of the whole village does."""
    whole, some = Ids(), Ids()
    assert [whole.document_id(CARDS, "1932/a.py"), whole.document_id(CARDS, "1941/b.py"),
            whole.document_id(CARDS, "1941/c.py")] == [
        "r1:Маниловка/card/1932/cards", "r1:Маниловка/card/1941/cards", "r1:Маниловка/card/1941/cards~2"]
    assert [some.document_id(CARDS, "1941/b.py"), some.document_id(CARDS, "1941/c.py")] == [
        "r1:Маниловка/card/1941/cards", "r1:Маниловка/card/1941/cards~2"]


def test_a_book_keeps_its_own_year_and_a_file_out_of_a_year_gives_none():
    k = BookKey("Маниловка", "47-9-755", None, 1842, "birth")
    assert Ids().document_id(k, "1900/fixture.py") == str(k)            # the book's year, not the file's
    assert Ids().document_id(CARDS, "cards.py") == "r1:Маниловка/card/cards"
    assert Ids().document_id(CARDS) == "r1:Маниловка/card/cards"        # a caller that names no file


def test_the_id_of_a_set_of_cards_parses_with_its_year():
    p = parse("r1:Маниловка/card/1941/cards")
    assert (p.shelfmark, p.year, p.kind) == ("card", 1941, "cards")


def test_a_numberless_record_inserted_above_shifts_the_ones_below():
    # What r1 does not promise: a record without a number is counted, not cited.
    alone = _ids(_births(birth(None, Gender.MALE, 3, 4, child=person("Иванъ"))))
    below = _ids(_births(birth(None, Gender.MALE, 1, 2, child=person("Петръ")),
                         birth(None, Gender.MALE, 3, 4, child=person("Иванъ"))))
    assert alone == ["r1:Маниловка/47-9-755/1842/birth/m_1"]
    assert below[-1] == "r1:Маниловка/47-9-755/1842/birth/m_2"


def test_a_repeat_moved_inside_its_file_swaps_its_tilde():
    # Nor this: `~k` follows the export's order, and a move inside the file is a new order.
    ivan = birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))
    petr = birth(1, Gender.MALE, 5, 6, child=person("Петръ"))
    assert _ids(_births(ivan, petr)) == ["r1:Маниловка/47-9-755/1842/birth/m1", "r1:Маниловка/47-9-755/1842/birth/m1~2"]
    ivan = birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))
    petr = birth(1, Gender.MALE, 5, 6, child=person("Петръ"))
    assert _ids(_births(petr, ivan))[1] == "r1:Маниловка/47-9-755/1842/birth/m1~2"


def test_a_household_numbered_by_an_int_is_cited_by_it():
    rs = census_records("ГА", "43", "6", "587", "Собакевичево", 1816,
                        household(3, member(1, person("Иванъ"), CensusRole.HEAD)))  # type: ignore[arg-type]
    h = rs.households[0]
    assert Ids().record_id(book_key(rs, h), entry_token(h)) == "r1:Собакевичево/43-6-587/1816/household/3"


def test_a_birth_without_a_sex_is_refused_by_its_number():
    rs = _births(*page("5", birth(7, None, 3, 4)))  # type: ignore[arg-type]
    with pytest.raises(FormatError, match=r"Birth № 7, л\. 5: пол не указан"):
        entry_token(rs.records[0])


def test_parts_of_one_case_are_told_apart():
    def roll(suffix):
        return census_records("ГА", "43", "6", "587", "Собакевичево", 1816,
                              household("3", member(1, person("Иванъ"), CensusRole.HEAD)),
                              archive_suffix=suffix)
    assert str(book_key(roll("43-6-587-part-2"))) == "r1:Собакевичево/43-6-587;part-2/1816/household"
    assert str(book_key(roll("стр-34-35"))) == "r1:Собакевичево/43-6-587;стр-34-35/1816/household"
    assert str(book_key(roll(None))) == "r1:Собакевичево/43-6-587/1816/household"
    rs = roll(None)
    assert Ids().record_id(book_key(rs, rs.households[0]), entry_token(rs.households[0])) == \
        "r1:Собакевичево/43-6-587/1816/household/3"


def test_a_record_keeps_its_own_case_and_takes_the_books_year():
    rs = _births(*page("5", birth(2, Gender.FEMALE, 1, 2, child=person("Марья"), year=1843), case="410"))
    assert _ids(rs) == ["r1:Маниловка/47-9-410/1842/birth/f2"]


def test_a_card_is_named_by_its_catalog_address():
    assert url_key("https://gwar.mil.ru/heroes/chelovek_plen10000001/") == "chelovek_plen10000001"
    assert url_key("https://viewer.rsl.ru/ru/rsl01000000001?page=1") == "rsl01000000001-page-1"
    assert url_key("https://pamyat-naroda.ru/heroes/memorial-chelovek_dopolnitelnoe_donesenie10000002/") == \
        "memorial-chelovek_dopolnitelnoe_donesenie10000002"
    cards = external_source_records(
        "Маниловка", wwi_record(person("Иванъ"), source_url="https://gwar.mil.ru/heroes/chelovek_plen10000001/"))
    card = cards.records[0]
    assert Ids().record_id(book_key(cards, card), entry_token(card)) == \
        "r1:Маниловка/card/wwi/chelovek_plen10000001"


def test_ids_round_trip_through_parse():
    p = parse("r1:Маниловка/12%2F3;part-2/1900/household/1а~2/member-1")
    assert (p.scheme, p.village, p.shelfmark, p.part, p.year, p.kind) == \
        ("r1", "Маниловка", "12/3", "part-2", 1900, "household")
    assert (p.token, p.repeat, p.persona) == ("1а", 2, "member-1")
    card = parse("r1:Маниловка/card/wwi/chelovek_plen10000001")
    assert (card.shelfmark, card.year, card.kind, card.token) == ("card", None, "wwi", "chelovek_plen10000001")
    assert escape("12/3;a~b%") == "12%2F3%3Ba%7Eb%25"


def test_an_id_without_a_year_parses():
    key = BookKey("Маниловка", "47-9-755", None, None, "household")
    assert str(key) == "r1:Маниловка/47-9-755/household"
    p = parse(f"{key}/3~2/member1")
    assert (p.shelfmark, p.part, p.year, p.kind, p.token, p.repeat, p.persona) == \
        ("47-9-755", None, None, "household", "3", 2, "member1")
    assert parse(str(key)).kind == "household"


def test_another_scheme_is_refused():
    with pytest.raises(ValueError, match="понимаю только r1"):
        parse("r2:Маниловка/47-9-755/1842/birth/m1")


def test_labels():
    assert person_label(person("Иванъ", "Петровъ")) == "Иванъ Петровъ"
    m = marriage(12, 3, groom=person("Иванъ"), bride=person("Марья", "Петрова"))
    assert record_label(m) == "Иванъ + Марья Петрова"
    assert record_label(birth(1, Gender.MALE, 3, 4, child=person("Иванъ"))) == "Иванъ"


def test_the_citation_takes_its_kinds_from_the_dsls_kinds():
    """A record's kind in its id is its RecordKind's code (verso.ru.dsl.kinds), spelled once."""
    import ast
    from pathlib import Path

    from verso.ru.dsl.kinds import KINDS
    from verso.ru.records import cite
    codes = {kind.code for kind in KINDS} - {"card"}
    tree = ast.parse(Path(cite.__file__).read_text(encoding="utf-8"))
    assert not {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)} & codes
