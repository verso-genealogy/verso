from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from tests.ru.site.conftest import BIRTHS, DEATHS, HOUSEHOLDS, LISTED, MARRIAGES, WWI
from verso.ru.site import model, records
from verso.ru.site.records import Ui

Change = Callable[[Callable[[dict[str, Any]], None]], model.Site]


def _drawn(site: model.Site, ui: Ui, book_id: str, anchor: str) -> str:
    book = site.book(book_id)
    return records.render(next(e for e in book.entries if e.anchor == anchor), book, ui)


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


def test_a_birth_reads_as_its_entry(site: model.Site, ui: Ui) -> None:
    drawn = _drawn(site, ui, BIRTHS, "m1")
    assert 'id="m1"' in drawn
    assert "рождение: 3 января 1900" in _text(drawn) and "крещение: 4 января 1900" in _text(drawn)
    roles = re.findall(r'<div class="role">([^<]*)</div>', drawn)
    assert roles == ["Младенец", "Отец", "Мать", "Восприемник", "отец восприемника №1"]


def test_what_is_written_and_what_is_derived_are_told_apart(site: model.Site, ui: Ui) -> None:
    drawn = _drawn(site, ui, BIRTHS, "m1")
    assert '<span class="w">Петръ</span> <span class="w">Ивановъ</span> <span class="w">Сидоровъ</span>' in drawn
    assert '<span class="modern d">Петр Иванович Сидоров</span>' in drawn
    assert '<span class="d">крестьянский сын</span>' in drawn      # the child's estate, from the father's
    assert '<span class="w">крестьянин</span>' in drawn            # the father's, which the entry writes


def test_a_modern_form_that_only_drops_old_letters_is_not_repeated(site: model.Site, ui: Ui) -> None:
    assert "modern" not in _drawn(site, ui, DEATHS, "m1")           # «Иванъ» and «Иван»


def test_what_the_book_gives_every_entry_is_not_said_in_each(site: model.Site, ui: Ui) -> None:
    held = _drawn(site, ui, BIRTHS, "f2")                # the father: a peasant of Маниловка by the book's defaults
    assert "крестьянин" not in held and "Маниловка" not in _text(held).replace("r1:Маниловка", "")
    assert "натуральная" not in _drawn(site, ui, DEATHS, "m3")      # the book's default cause of death
    assert "причина смерти: натуральная" in _text(_drawn(site, ui, DEATHS, "f2"))   # the entry writes it


@pytest.mark.parametrize("anchor", ["f2", "f3"])
def test_an_unread_record_is_marked_whatever_holds_it(site: model.Site, ui: Ui, anchor: str) -> None:
    drawn = _drawn(site, ui, BIRTHS, anchor)
    assert 'class="rec held"' in drawn and '<span class="badge">не вычитано</span>' in drawn
    assert "geni" not in drawn.lower()


def test_a_read_record_carries_no_mark(site: model.Site, ui: Ui) -> None:
    assert "badge" not in _drawn(site, ui, BIRTHS, "m1")


def test_a_marriage_puts_an_age_beside_its_person(site: model.Site, ui: Ui) -> None:
    text = _text(_drawn(site, ui, MARRIAGES, "1"))
    assert "венчание: 9 января 1900" in text
    assert "Жених Иванъ Петровъ Иван Петрович возраст: 17 лет 2 месяца" in text
    assert "Поручитель 2 Василій Петровъ Василий Петрович сторона: по невесте" in text


def test_a_death_says_the_age_in_words(site: model.Site, ui: Ui) -> None:
    assert "возраст: полгода" in _text(_drawn(site, ui, DEATHS, "f2"))
    assert "возраст: 15 лет 6 месяцев" in _text(_drawn(site, ui, DEATHS, "m3"))


def test_a_household_is_a_table_of_those_the_roll_lists(site: model.Site, ui: Ui) -> None:
    drawn = _drawn(site, ui, HOUSEHOLDS, "94")
    assert "Двор № 94" in drawn
    rows = re.findall(r"<tr><td>(.*?)</tr>", drawn)
    assert len(rows) == 3                                           # the member written for the kinship is not listed
    assert [_text(row).split(" ")[0] for row in rows] == ["1", "2", "3"]
    assert "сын к № 1" in _text(rows[2]) and "6 месяцев" in _text(rows[2])
    assert '<span class="d">Иванов</span>' in rows[2]               # the son's patronymic, from the head's name


def test_a_line_of_a_list_names_its_person_without_a_role(site: model.Site, ui: Ui) -> None:
    drawn = _drawn(site, ui, LISTED, "1")
    assert '<div class="role"></div>' in drawn and "возраст 40 лет" in _text(drawn)


def test_a_card_leads_to_its_catalog_and_shows_no_scan(changed: Change, ui: Ui) -> None:
    def with_scan(node: dict[str, Any]) -> None:
        card = node["documents"][6]["pages"][0]["records"][0]
        card["written"]["scan_file"] = "scans/card.jpg"
        card["derived"]["citation"] |= {"scan_file": "scans/card.jpg", "scan_files": ["scans/card.jpg"]}
    drawn = _drawn(changed(with_scan), ui, WWI, "chelovek_plen1")
    assert '<a href="https://gwar.mil.ru/heroes/chelovek_plen1/" rel="noopener">' in drawn
    assert "дата 3 мая 1915" in _text(drawn) and "Карточки военнопленных" in drawn
    assert "scan" not in drawn and "card.jpg" not in drawn


def test_a_civil_registers_second_date_is_a_registration(changed: Change, ui: Ui) -> None:
    def civil(node: dict[str, Any]) -> None:
        node["documents"][0]["written"]["civil"] = True
    text = _text(_drawn(changed(civil), ui, BIRTHS, "m1"))
    assert "регистрация: 4 января 1900" in text and "крещение" not in text



def test_an_event_with_a_day_and_no_month_draws_no_date(changed: Change, ui: Ui) -> None:
    """A day alone is no date (the library writes a day only beside its month), and the year would be only the
    book's: the birth's line is left out, the baptism's stays."""
    def no_month(node: dict[str, Any]) -> None:
        del node["documents"][0]["pages"][0]["records"][0]["written"]["birth"]["month"]
    text = _text(_drawn(changed(no_month), ui, BIRTHS, "m1"))
    assert "рождение:" not in text and "крещение: 4 января 1900" in text

def test_the_text_of_a_record_is_escaped(changed: Change, ui: Ui) -> None:
    def hostile(node: dict[str, Any]) -> None:
        record = node["documents"][0]["pages"][0]["records"][0]
        record["persons"][0]["written"]["given"]["original"] = '<b>&"</script>'
        record["written"]["comment"] = "<img src=x onerror=alert(1)>"
    drawn = _drawn(changed(hostile), ui, BIRTHS, "m1")
    assert "&lt;b&gt;&amp;&quot;&lt;/script&gt;" in drawn and "<b>&" not in drawn
    assert "&lt;img src=x onerror=alert(1)&gt;" in drawn and "<img" not in drawn


def test_a_comment_of_the_entry_is_drawn_and_a_note_of_the_file_is_not(changed: Change, ui: Ui) -> None:
    def noted(node: dict[str, Any]) -> None:
        record = node["documents"][0]["pages"][0]["records"][0]
        record["note"] = [{"text": "the compiler's own remark", "anchor": {"to": "record", "record": 0}}]
        record["written"]["comment"] = "приписка на полѣ"
    drawn = _drawn(changed(noted), ui, BIRTHS, "m1")
    assert "приписка на полѣ" in drawn and "the compiler's own remark" not in drawn


def test_a_record_says_how_it_is_cited(site: model.Site, ui: Ui) -> None:
    drawn = _drawn(site, ui, BIRTHS, "m4")
    assert "Источник: ЦГА. Ф. 47. Оп. 9. Д. 755. Л. 1об." in _text(drawn)
    assert "<code>r1:Маниловка/47-9-755/1900/birth/m4</code>" in drawn and 'href="#m4"' in drawn


def test_an_unknown_shelfmark_is_said_so(changed: Change, ui: Ui) -> None:
    def unknown(node: dict[str, Any]) -> None:
        node["documents"][1]["written"] |= {"fund": "?", "inventory": "?", "case": "?"}
    assert "Источник: ЦГА. шифр не установлен." in _text(_drawn(changed(unknown), ui, MARRIAGES, "1"))


def test_every_field_of_the_schema_is_drawn_or_named_as_not_shown(ui: Ui) -> None:
    """A field the vocabulary gains reaches the page by itself; one without a label fails here until the
    site gives it one or says why it shows none."""
    labelled = set(records.site_labels())
    for code, kind in ui.schema["kinds"].items():
        for field in kind["fields"]:
            path = field["path"]
            assert (path.split(".")[0] in records.NOT_SHOWN or field.get("label") or path in labelled), (code, path)
        for group in kind["groups"]:
            for field in group["item"]["fields"]:
                assert field.get("label") or field.get("hidden"), (code, group["name"], field["path"])
    for field in ui.schema["persona"]["fields"]:
        assert field.get("label") or field["path"] in records.PERSONA_NOT_SHOWN, field["path"]


def test_a_cards_document_is_cited_as_its_catalog_gives_it(changed: Change, ui: Ui) -> None:
    def archived(node: dict[str, Any]) -> None:
        cards = node["documents"][6]["pages"][0]["records"]
        cards[0]["derived"]["citation"] |= {"archive": "ЦГВА", "fund": "58", "inventory": "977", "case": "92"}
        cards[1]["derived"]["citation"] |= {"archive": "ЦГВА", "fund": "Ф. 970, Канцелярія", "inventory": "Оп. 3"}
    site = changed(archived)
    assert "документ: ЦГВА 58-977-92." in _text(_drawn(site, ui, WWI, "chelovek_plen1"))
    wwii = "r1:Маниловка/card/wwii"
    assert "документ: ЦГВА, Ф. 970, Канцелярія, Оп. 3." in _text(_drawn(site, ui, wwii, "memorial-chelovek_donesenie2"))


def test_a_zero_the_source_wrote_is_a_value() -> None:
    assert records.value({"written": {"age": 0}}, "age") == (0, "w")
    assert records.value({"written": {"age": "", "flag": False, "list": []}, "derived": {"age": 3}}, "age") == (3, "d")
    assert records.value({"written": {"flag": False, "list": []}}, "flag") is None


def test_a_kind_the_vocabulary_does_not_know_is_refused(changed: Change, ui: Ui) -> None:
    def strange(node: dict[str, Any]) -> None:
        node["documents"][1]["pages"][0]["records"][0]["kind"] = "betrothal"
    site = changed(strange)
    with pytest.raises(model.NotAnExport, match="betrothal"):
        _drawn(site, ui, MARRIAGES, "1")


@pytest.mark.parametrize(("written", "shown"), [
    ("14 марта 1926", "дата брака 14 марта 1926"),                               # the text DSL v1 writes
    ({"year": 1926, "month": "march", "day": 14}, "дата брака 14 марта 1926"),   # a date, as a card's
    ({"year": 1926, "year_end": 1927, "date_range": "between"}, "дата брака 1926 — 1927"),
    ({"year": 1926, "circa": True}, "дата брака около 1926"),
])
def test_the_marriage_a_divorce_names_reads_in_either_form(changed: Change, ui: Ui, written: Any, shown: str) -> None:
    """The marriage an act of divorce names: a text in DSL v1, a date object where the vocabulary makes it one
    (a field the interface's schema may hide from its editor — the site draws it all the same)."""
    def named(node: dict[str, Any]) -> None:
        node["documents"][3]["pages"][0]["records"][0]["written"]["marriage_date"] = written
    text = _text(_drawn(changed(named), ui, "r1:Заманиловка/1605-59-59/1923/divorce", "1"))
    assert shown in text and "{" not in text


@pytest.mark.parametrize(("written", "shown"), [
    ({"date_range": "after"}, ""),                                   # no part of a date: nothing written
    ({"year": None, "circa": True}, ""),
    ({"year_end": 1927}, "1927"),                                    # an end alone is what is written
    ({"year_end": 1927, "date_range": "before"}, "до 1927"),
    ({"year_end": 1927, "circa_end": True}, "около 1927"),
    ({"circa": True}, ""),
    # as the library writes a date (written_date): a day only beside its month, the month governed after a word
    ({"year": 1915, "day": 5}, "1915"),
    ({"day": 5}, ""),                                                # a day alone: no date to draw
    ({"day": 5, "day_end": 9}, ""),
    ({"year": 1915, "month": "may"}, "май 1915"),
    ({"month": "may", "day": 3}, "3 мая"),
    ({"year": 1915, "month": "may", "date_range": "before"}, "до мая 1915"),
    ({"year": 1915, "month": "may", "date_range": "after"}, "после мая 1915"),
    ({"year": 1915, "month": "may", "circa": True}, "около мая 1915"),
    ({"year_end": 1915, "month_end": "may", "date_range": "before"}, "до мая 1915"),
    ({"year": 1914, "year_end": 1915, "month_end": "may", "circa_end": True, "date_range": "between"},
     "1914 — около мая 1915"),
    ({"year": 1914, "month": "june", "year_end": 1915, "month_end": "may", "date_range": "between"},
     "июнь 1914 — май 1915"),
    ({"day": 5, "year": 1915, "circa": True}, "около 1915"),
    ({"year_end": 1927, "circa": True}, "1927"),                     # «около» of a start not written
])
def test_a_date_with_parts_missing_says_what_it_has(ui: Ui, written: dict[str, Any], shown: str) -> None:
    found = records.value({"written": {"when": written}}, "when")
    if not shown:
        assert found is None
    else:
        assert found is not None and records.text(found[0], {}, ui) == shown


@pytest.mark.parametrize("written", [
    {"year": 1900, "reason": "умер"},                                # a year beside what is no date's
    {"status": "крестьянин"},
])
def test_an_object_no_field_of_the_schema_draws_is_refused(ui: Ui, written: dict[str, Any]) -> None:
    """A value the site cannot draw would be lost from the page without a word — a refusal says it."""
    with pytest.raises(model.NotAnExport):
        records.text(written, {"path": "departure"}, ui)


def test_a_hidden_date_without_a_label_still_has_the_sites() -> None:
    assert str(records.site_labels()["marriage_date"]) == "дата брака"


def test_a_birth_puts_each_parents_age_beside_them(ui: Ui) -> None:
    from tests.records_fixture import aged
    from verso.core.records.encode import encode_namespace
    from verso.core.records.ids import Ids
    node = encode_namespace(aged(), village="Маниловка", file="1900/all.py", sha256="", ids=Ids())
    site = model.load([node], village="Маниловка")
    book = site.book(BIRTHS)
    text = _text(records.render(book.entries[0], book, ui))
    assert re.search(r"Отец Петръ .*? возраст: 31 год", text), text
    assert re.search(r"Мать Марья .*? возраст: 30\?", text), text
