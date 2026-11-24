from __future__ import annotations

import pytest

from verso.ru.site import urls


@pytest.mark.parametrize(("record_id", "path", "anchor"), [
    ("r1:Маниловка/47-9-755/1900/birth/f4", "books/manilovka/47-9-755/1900/birth/", "f4"),
    ("r1:Маниловка/47-9-755/1900/birth/m12~2", "books/manilovka/47-9-755/1900/birth/", "m12~2"),
    ("r1:Маниловка/47-9-755/1900/birth/m_1", "books/manilovka/47-9-755/1900/birth/", "m_1"),
    ("r1:Маниловка/47-9-755/1900/marriage/12", "books/manilovka/47-9-755/1900/marriage/", "12"),
    ("r1:Маниловка/47-9-12а/1900/birth/m4а", "books/manilovka/47-9-12a/1900/birth/", "m4а"),
    ("r1:Заманиловка/735-265-53;стр-80/1828/household/94",
     "books/zamanilovka/735-265-53_str-80/1828/household/", "94"),
    ("r1:Маниловка/5-1-7/household/3", "books/manilovka/5-1-7/household/", "3"),
    ("r1:Маниловка/card/wwi/chelovek_plen1", "cards/manilovka/wwi/", "chelovek_plen1"),
])
def test_a_record_id_is_its_page_and_anchor(record_id: str, path: str, anchor: str) -> None:
    assert urls.book_path(urls.book_of(record_id)) == path
    assert urls.anchor(record_id) == anchor


def test_a_persona_is_addressed_by_its_record() -> None:
    record = "r1:Маниловка/47-9-755/1900/birth/f4"
    assert urls.book_of(record) == "r1:Маниловка/47-9-755/1900/birth"
    assert urls.record_href(record) == "books/manilovka/47-9-755/1900/birth/#f4"


def test_an_anchor_is_one_token_whatever_the_number_holds() -> None:
    assert urls.anchor("r1:Маниловка/5-1-7/1850/household/12 а") == "12_а"
    assert urls.anchor("r1:Маниловка/5-1-7/1850/household/1%2F2") == "1%2F2"
    assert urls.record_href("r1:Маниловка/5-1-7/1850/household/1%2F2").endswith("#1%252F2")


def test_a_segment_no_letter_survives_is_refused() -> None:
    with pytest.raises(ValueError, match="—"):
        urls.slug("—")
