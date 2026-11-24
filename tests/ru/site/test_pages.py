from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from tests.ru.site.conftest import BIRTHS, MARRIAGES
from verso.ru.site import model, pages
from verso.ru.site.records import Ui
from verso.ru.site.shell import Context

Change = Callable[[Callable[[dict[str, Any]], None]], model.Site]


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


def _hrefs(markup: str) -> list[str]:
    return re.findall(r'(?:href|src|action)="([^"]*)"', markup)


def test_a_book_opens_with_what_it_is_and_how_much_of_it_is_read(site: model.Site, ui: Ui, ctx: Context) -> None:
    page = pages.book(site.book(BIRTHS), ui, ctx)
    text = _text(page)
    assert "<h1>Рождения 1900 — Маниловка</h1>" in page
    assert "ЦГА. Ф. 47. Оп. 9. Д. 755." in text and "приход: Маниловка, Церковь" in text
    assert "Если в записи не сказано иначе: место — Маниловка; мужчины — крестьянин; женщины — крестьянка" in text
    assert "5 записей не вычитано: 2" in text
    assert '<a href="#m1">1</a> <a href="#m4">1об</a>' in page          # the leaves, each at its first record
    assert page.count("<article") == 5


def test_a_books_kind_is_named_as_its_source_names_it(site: model.Site, ui: Ui) -> None:
    assert [pages.kind_title(book, ui) for book in site.books] == [
        "Исповедная роспись", "Рождения", "Браки", "Смерти", "Список избирателей", "Разводы",
        "Карточки: судимость", "Карточки: военная служба", "Карточки: Великая Отечественная война"]


def test_a_civil_registers_book_says_so(changed: Change, ui: Ui, ctx: Context) -> None:
    def civil(node: dict[str, Any]) -> None:
        node["documents"][0]["written"] |= {"civil": True, "church": ""}
    site = changed(civil)
    page = pages.book(site.book(BIRTHS), ui, ctx)
    assert "Рождения (ЗАГС) 1900 — Маниловка" in page and "вторая дата — день регистрации" in page


def test_the_books_stand_by_archive_fund_and_file(changed: Change, ui: Ui, ctx: Context) -> None:
    def unknown(node: dict[str, Any]) -> None:
        node["documents"][1]["written"] |= {"fund": "?", "inventory": "?", "case": "?"}
    page = pages.books_index(changed(unknown), ui, ctx)
    assert re.findall(r"<h2>([^<]*)</h2>", page) == ["ГАПО", "ГАРО", "ГАТО", "ЦГА", "Карточки внешних каталогов"]
    assert "<h3>ф. 47, оп. 9</h3>" in page and "<h3>шифр не установлен.</h3>" in page
    assert 'href="../books/manilovka/47-9-755/1900/birth/"' in page and "не вычитано: 2" in page


def test_a_year_lists_its_books(site: model.Site, ui: Ui, ctx: Context) -> None:
    index = pages.years_index(site, ui, ctx)
    assert re.findall(r'<td><a href="(\d+)/">', index) == ["1828", "1900", "1913", "1917", "1923"]
    year = pages.year(1900, site, ui, ctx)
    assert "Рождения 1900 — Маниловка" in year and "Браки 1900 — Маниловка" in year and "Смерти" not in year
    assert 'href="../1828/"' in year and 'href="../1913/"' in year


def test_the_front_page_counts_what_the_site_holds(site: model.Site, ctx: Context) -> None:
    text = _text(pages.front(site, ctx))
    assert "9 книг" in text and "17 записей" in text and "годы 1828–1923" in text
    assert "2 записи ещё не вычитаны" in text
    assert "О селе" not in text                                      # no prose, no section of it


def test_a_page_links_within_the_site_by_relative_addresses(site: model.Site, ui: Ui, ctx: Context) -> None:
    made = [pages.front(site, ctx), pages.books_index(site, ui, ctx), pages.names_index(site, ctx),
            pages.search(ctx), pages.book(site.book(BIRTHS), ui, ctx), pages.year(1900, site, ui, ctx)]
    for page in made:
        assert '<html lang="ru">' in page
        assert not [h for h in _hrefs(page) if h.startswith(("/", "http", "//"))], page[:200]
    assert '<link rel="stylesheet" href="../../../../../assets/site.css">' in made[4]


def test_a_surname_gathers_its_mentions_and_its_feminine_form(site: model.Site, ui: Ui, ctx: Context) -> None:
    found = {page.key: page for page in pages.surname_pages(site)}
    assert list(found) == ["Сидоров"] and found["Сидоров"].title == "Сидоров, Сидорова"
    page = pages.name(found["Сидоров"], pages.NAMES, site, ui, ctx)
    rows = [_text(row) for row in re.findall(r"<tr><td>(.*?)</tr>", page)]
    assert rows[0] == "1900 Иванъ Иван Петрович Сидоров Младенец Рождения, Маниловка"
    assert rows[2] == "1900 Марья Петрова Марья Петровна Сидорова Мать Рождения, Маниловка"
    assert rows[-1] == "1917 Петръ Ивановъ Сидоровъ Петр Иванович Сидоров Человек Список избирателей, Горюхино"
    assert 'href="../../books/manilovka/47-9-755/1900/birth/#m1"' in page


def test_who_is_written_without_a_surname_is_found_by_patronymic(site: model.Site, ctx: Context) -> None:
    found = {page.key: page for page in pages.patronymic_pages(site)}
    assert list(found) == ["Иванов", "Петров"]                       # «Иванова» with «Иванов», «Петрова» with «Петров»
    assert "Анна Иванова" in [m.as_written for m in found["Иванов"].mentions]
    index = pages.patronymics_index(site, ctx)
    assert '<a href="Иванов/">Иванов, Иванова</a>' in index


def test_who_is_written_by_a_name_alone_has_a_page_too(site: model.Site, ui: Ui, ctx: Context) -> None:
    alone = pages.nameless(site)
    assert "Анна" in [m.as_written for m in alone] and all(not m.surname and not m.patronymic for m in alone)
    assert f'href="../{pages.PATRONYMICS}/{pages.NAMELESS}/"' in pages.names_index(site, ctx)
    assert "Анна" in pages.nameless_page(site, ui, ctx)


def test_an_unread_mention_is_marked_in_the_index(site: model.Site, ui: Ui, ctx: Context) -> None:
    page = pages.nameless_page(site, ui, ctx)
    held = next(row for row in re.findall(r"<tr><td>(.*?)</tr>", page) if "#f2" in row)
    assert "не вычитано" in held


def test_the_old_letters_fold_into_the_modern_ones() -> None:
    assert model.fold("Ѳеодоръ Сергѣевъ") == model.fold("Феодор Сергеев") == "феодор сергеев"
    assert model.fold("Марія") == "мария" and model.fold("объездчикъ") == "объездчик"
    assert model.fold("Семёнов") == "семенов"


def test_the_search_index_leads_each_mention_to_its_record(site: model.Site, ui: Ui) -> None:
    data = json.loads(pages.search_index(site, ui))
    assert len(data["rows"]) == len(site.mentions)
    books = [book[0] for book in data["books"]]
    assert books[1] == "books/manilovka/47-9-755/1900/birth/"
    father = next(row for row in data["rows"] if row[1] == "Петръ Ивановъ Сидоровъ" and row[5] == "Отец")
    assert father == ["петр иванович сидоров петр иванов сидоров", "Петръ Ивановъ Сидоровъ",
                      "Петр Иванович Сидоров", 1, "m1", "Отец", 0]
    unread = {row[4]: row[6] for row in data["rows"] if row[3] == 1 and row[5] == "Младенец"}
    assert unread == {"m1": 0, "f2": 1, "f3": 1, "m4": 0, "m4а": 0}        # a held and a listed record alike


def test_the_search_page_works_without_its_script(ctx: Context) -> None:
    page = pages.search(ctx)
    assert "<noscript>" in page and 'href="../names/"' in page
    assert 'data-found="Найдено: {count}."' in page and 'src="../assets/search.js"' in page
    assert 'data-unread="не вычитано"' in page


def test_a_mention_of_a_marriage_names_the_kinship(site: model.Site, ui: Ui) -> None:
    witness = next(m for m in site.mentions if m.entry.book_id == MARRIAGES and m.role == "witness")
    assert pages.role_label(witness, ui) == "Поручитель"
    relative = next(m for m in site.mentions if m.role == "relative" and m.entry.book_id == BIRTHS)
    assert pages.role_label(relative, ui) == "отец восприемника №1"


def test_the_books_of_one_file_and_year_stand_as_a_year_lists_them(changed: Change, ui: Ui, ctx: Context) -> None:
    def same_year(node: dict[str, Any]) -> None:
        deaths = node["documents"][2]
        deaths["written"] |= {"village": "Маниловка", "year": 1900}
        for run in deaths["pages"]:
            for record in run["records"]:
                record["id"] = record["id"].replace("Хлестаковка/47-9-755/1913", "Маниловка/47-9-755/1900")
    page = pages.books_index(changed(same_year), ui, ctx)
    kinds = re.findall(r'<a href="\.\./books/manilovka/47-9-755/1900/(\w+)/">', page)
    assert kinds == ["birth", "marriage", "death"]                   # not by the kinds' names


def _own_case(node: dict[str, Any]) -> None:
    """One birth that states a case of its own, as `page(case=…)` writes it: its id and its `written`."""
    record = node["documents"][0]["pages"][0]["records"][0]
    record["id"] = record["id"].replace("47-9-755", "47-9-999")
    record["written"]["case"] = "999"
    for persona in record["persons"]:
        persona["id"] = persona["id"].replace("47-9-755", "47-9-999")


def test_a_record_of_its_own_shelfmark_heads_its_book_with_it(changed: Change, ui: Ui, ctx: Context) -> None:
    site = changed(_own_case)
    own = site.book("r1:Маниловка/47-9-999/1900/birth")
    assert own.shelf == {"archive": "ЦГА", "fund": "47", "inventory": "9", "case": "999"}
    page = pages.book(own, ui, ctx)
    assert "ЦГА. Ф. 47. Оп. 9. Д. 999." in _text(page) and "Д. 755" not in page
    index = pages.books_index(site, ui, ctx)
    row = next(r for r in re.findall(r"<tr>(.*?)</tr>", index) if "47-9-999" in r)
    assert row.startswith("<td>999</td>")


def test_the_funds_of_an_archive_stand_by_their_numbers(changed: Change, ui: Ui, ctx: Context) -> None:
    def one_archive(node: dict[str, Any]) -> None:
        node["documents"][5]["written"]["archive"] = "ЦГА"           # the list of fund 1978 beside fund 47
    page = pages.books_index(changed(one_archive), ui, ctx)
    assert re.findall(r"<h3>(ф\. \d+)", page)[-2:] == ["ф. 47", "ф. 1978"]


def test_a_name_nobody_could_read_indexes_nobody(changed: Change) -> None:
    def unread_names(node: dict[str, Any]) -> None:
        groom = node["documents"][1]["pages"][0]["records"][0]["persons"][0]
        groom["written"]["patronymic"] = {"original": "?"}
        groom["derived"]["patronymic"] = {}
        groom["written"]["surname"] = {"original": "?"}
    site = changed(unread_names)
    groom = next(m for m in site.mentions if m.role == "groom")
    assert (groom.surname, groom.patronymic) == ("", "")
    assert groom in pages.nameless(site)
    assert pages.NAMELESS not in {page.key for page in pages.patronymic_pages(site)}
    assert pages.NAMELESS not in {page.key for page in pages.surname_pages(site)}


def test_a_records_heading_stands_right_under_its_books(site: model.Site, ui: Ui, ctx: Context) -> None:
    page = pages.book(site.book(BIRTHS), ui, ctx)
    assert page.count("<h1>") == 1 and page.count("<h2>") == 5 and "<h3>" not in page
    assert '<nav aria-label="Разделы сайта">' in page
