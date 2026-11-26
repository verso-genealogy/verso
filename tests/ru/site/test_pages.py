from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import replace
from collections.abc import Callable
from typing import Any

import pytest

from tests.ru.site.conftest import BIRTHS, DEATHS, HOUSEHOLDS, LISTED, MARRIAGES, WWI
from verso.ru.messages import t
from verso.ru.site import model, pages, prose
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


def _cells(index: str, year_: int) -> str:
    return re.search(rf'<tr><td><a href="{year_}/">.*?</tr>', index).group(0)


def _row(index: str, year_: int) -> str:
    return re.sub(r"<[^>]+>", "", re.search(rf'<tr><td><a href="{year_}/">.*?</tr>', index).group(0))


def _twin(node: dict[str, Any], **written: str) -> None:
    """A second book of births of 1900 in the same village, its record set's header rewritten by `written`."""
    births = next(d for d in node["documents"] if d.get("kind") == "births")
    case = written.get("case", "755")
    suffix = written.get("archive_suffix")
    book = "47-9-" + case + (f";{suffix.removeprefix('47-9-' + case + '-')}" if suffix else "")
    twin = {**births, "id": births["id"].replace("47-9-755", book), "variable": "twin",
            "written": {**births["written"], **written},
            "pages": [{**run, "records": [{**r, "id": r["id"].replace("47-9-755", book)} for r in run["records"]]}
                      for run in births["pages"]]}
    node["documents"].append(twin)


def test_the_years_name_a_book_of_another_village_and_tell_two_of_one_kind_apart(
        site: model.Site, changed: Any, ui: Ui, ctx: Context) -> None:
    """«Ревизия, Ревизия, Ревизия» said nothing of whose: a book of another village than the site's own parish
    is named with it, and two books of one kind, year and village by their shelfmarks and parts."""
    index = pages.years_index(site, ui, ctx)
    assert "Исповедная роспись — Заманиловка" in _row(index, 1828) and "— Хлестаковка" in _row(index, 1913)
    assert "Рождения, Браки" in _row(index, 1900)                       # the site's own parish: as it was
    def other_case(node: dict[str, Any]) -> None:
        _twin(node, case="756")

    def other_part(node: dict[str, Any]) -> None:
        _twin(node, archive_suffix="47-9-755-стр-9")
    row = _row(pages.years_index(changed(other_case), ui, ctx), 1900)
    assert "Рождения — 47-9-755" in row and "Рождения — 47-9-756" in row and "Браки —" not in row
    links = re.findall(r'<a href="[^"]*">([^<]*)</a>', _cells(pages.years_index(changed(other_part), ui, ctx), 1900))
    assert sorted(links[1:]) == ["Браки", "Рождения — 47-9-755", "Рождения — 47-9-755, стр-9"]   # [0]: the year


def test_a_site_whose_directory_is_not_its_parish_names_no_village(file_node: dict[str, Any], ui: Ui,
                                                                     ctx: Context) -> None:
    """A village kept under another directory than its parish (a village of its church's village's books): the
    parish most of its records name is its own, and so is the village itself where a book names it."""
    site = model.load([file_node], village="Другое")
    assert "Рождения, Браки" in _row(pages.years_index(site, ui, ctx), 1900)
    site = model.load([file_node], village="Заманиловка")             # a book of its own, its parish another's
    assert "Исповедная роспись" in _row(pages.years_index(site, ui, ctx), 1828)
    assert "— Заманиловка" not in _row(pages.years_index(site, ui, ctx), 1828)


def test_a_year_page_tells_two_parts_of_one_case_apart(changed: Any, ui: Ui, ctx: Context) -> None:
    def other_part(node: dict[str, Any]) -> None:
        _twin(node, archive_suffix="47-9-755-стр-9")
    page = pages.year(1900, changed(other_part), ui, ctx)
    lines = re.findall(r"<li>(.*?)</li>", page)
    assert len(lines) == len(set(lines)) and any("стр-9" in line for line in lines)



def test_a_part_of_a_case_names_its_book_wherever_the_book_is_named(changed: Any, ui: Ui, ctx: Context) -> None:
    """Two books of one case, year and kind — the case and a leaf of it filed apart — read apart at their heads,
    in a year's list, in the search's list of books and in the case column of the books' index."""
    def other_part(node: dict[str, Any]) -> None:
        _twin(node, archive_suffix="47-9-755-стр-9")
    site = changed(other_part)
    part = next(b for b in site.books if b.part and b.year == 1900)
    assert f"<h1>Рождения 1900 — Маниловка, {part.part}</h1>" in pages.book(part, ui, ctx)
    titles = re.findall(r'<li><a href="[^"]*">([^<]*)</a>', pages.year(1900, site, ui, ctx))
    assert "Рождения 1900 — Маниловка" in titles and f"Рождения 1900 — Маниловка, {part.part}" in titles
    books = [book[1] for book in json.loads(pages.search_index(site, ui))["books"]]
    assert len(books) == len(set(books))
    assert re.findall(r"<tr><td>(755[^<]*)</td><td>1900</td><td><a[^>]*>Рождения</a>", pages.books_index(site, ui, ctx)) \
        == ["755", f"755, {part.part}"]


def test_a_year_of_two_villages_names_each_books_village(changed: Any, ui: Ui, ctx: Context) -> None:
    """Where a year holds a book of another village, its own parish's books are named too: «Рождения» beside
    «Рождения — Тестовка» would read as nobody's."""
    def neighbour(node: dict[str, Any]) -> None:
        births = next(d for d in node["documents"] if d.get("kind") == "births")
        moved = "r1:Тестовка/47-9-755/"
        node["documents"].append({
            **births, "id": births["id"].replace("r1:Маниловка/47-9-755/", moved), "variable": "neighbour",
            "pages": [{**run, "records": [{**r, "id": r["id"].replace("r1:Маниловка/47-9-755/", moved)}
                                          for r in run["records"]]} for run in births["pages"]]})
    row = _row(pages.years_index(changed(neighbour), ui, ctx), 1900)
    assert "Рождения — Маниловка" in row and "Рождения — Тестовка" in row and "Браки — Маниловка" in row



@pytest.mark.parametrize(("part", "shown"), [
    ("part-2", "часть 2"),
    ("zamanilovka", ""), ("novaja-manilovka", ""),               # a file's slug for the village the book names already
    ("стр-34-35", "стр-34-35"), ("Заманиловка", "Заманиловка"), ("1-2-345", "1-2-345"),
    (None, ""),
])
def test_a_part_reads_as_a_reader_reads_it(site: model.Site, part: str | None, shown: str) -> None:
    assert pages.part_label(replace(site.book(BIRTHS), part=part)) == shown


def test_a_slug_for_a_part_stays_off_the_page(site: model.Site, ui: Ui, ctx: Context) -> None:
    book = replace(site.book(BIRTHS), part="zamanilovka")
    assert pages.book_title(book, ui) == "Рождения 1900 — Маниловка" and "zamanilovka" not in pages.book(book, ui, ctx)


def test_two_books_of_one_year_and_kind_in_two_cases_are_told_apart_by_case(changed: Any, ui: Ui) -> None:
    """«Браки 1783 — Маниловка» twice said nothing of which: a book whose twin stands in another case names its."""
    def other_case(node: dict[str, Any]) -> None:
        _twin(node, case="756")
    site = changed(other_case)
    births = [pages.book_title(b, ui) for b in site.books if b.year == 1900 and b.kind == "birth"]
    assert sorted(births) == ["Рождения 1900 — Маниловка, Д. 755", "Рождения 1900 — Маниловка, Д. 756"]
    assert pages.book_title(site.book(MARRIAGES), ui) == "Браки 1900 — Маниловка"     # no twin, no case
    books = [book[1] for book in json.loads(pages.search_index(site, ui))["books"]]
    assert len(books) == len(set(books))


def test_two_villages_of_the_sites_own_are_named_too(site: model.Site, ui: Ui) -> None:
    """A site kept under one village and its parish's name (two «own» villages): a year holding a book of each
    names both, or «Ревизия — 1-2-3, Ревизия — 1-2-4» would say nothing of whose."""
    births = site.book(BIRTHS)
    other = replace(births, id=births.id + "x", village="Тестовка", shelfmark="47-9-756")
    labels = pages._year_labels([births, other], {"Маниловка", "Тестовка"}, ui)
    assert labels == ["Рождения — Маниловка", "Рождения — Тестовка"]

def test_a_books_leaves_run_by_number_not_as_its_records_do(changed: Any, ui: Ui, ctx: Context) -> None:
    """A civil register lists its boys, then its girls: its leaves stand by number («3об» before «12»)."""
    def leaves(node: dict[str, Any]) -> None:
        records_ = [record for run in node["documents"][0]["pages"] for record in run["records"]]
        for record, leaf in zip(records_, ["12", "3об", "12об", "3", "1"], strict=True):
            record["written"]["page"] = leaf
    toc = re.search(r'<nav class="leaves">(.*?)</nav>', pages.book(changed(leaves).book(BIRTHS), ui, ctx))
    assert toc and re.findall(r">([^<]+)</a>", toc.group(1)) == ["1", "3", "3об", "12", "12об"]

def test_every_page_but_the_one_of_no_address_leads_back_to_its_top(site: model.Site, ui: Ui, ctx: Context) -> None:
    """The head's id is no heading's: GitHub's slug drops the dot (a prose page's «Top» is `top`)."""
    year = pages.year(1900, site, ui, ctx)
    assert 'id="page.top"' in year and 'href="#page.top"' in year
    assert prose.heading_slug("page.top") != "page.top"
    assert 'href="#page.top"' not in pages.not_found(ctx)             # its <base> would lead to the front page



def test_every_page_draws_in_the_chosen_theme_from_its_first_frame(site: model.Site, ui: Ui, ctx: Context) -> None:
    """The theme script is read in the head, before the body is drawn (no flash of the other theme); the bar's
    button is hidden until the script wires it, its three labels from the catalog — the 404's, under its
    `<base>`, too."""
    first = pages.year(1900, site, ui, ctx)
    for page in (first, pages.not_found(replace(ctx, site_url="https://example.org/s/"))):
        head, body = page.split("</head>")
        script = re.search(r'<script src="(\.\./)*assets/theme\.js"></script>', head)   # neither defer nor async
        assert script and head.find("<base ") < head.index('rel="stylesheet"') < script.start()   # resolved by <base>
        assert ("<base " in head) == (page is not first)
        button = re.search(r'<button type="button" class="theme" id="page.theme" hidden[^>]*>', body)
        assert button and body.index(button.group(0)) < body.index("</header>")
        assert 'data-light="Тема: светлая"' in button.group(0) and 'data-dark="Тема: тёмная"' in button.group(0)
        assert 'aria-label="Тема: как в системе"' in button.group(0)
        assert [m for m in re.findall(r'class="i-(\w+)"', body)] == ["auto", "light", "dark"]
    assert prose.heading_slug("page.theme") != "page.theme"                   # no heading takes the button's id


def test_the_front_page_counts_what_the_site_holds(site: model.Site, ctx: Context) -> None:
    text = _text(pages.front(site, ctx))
    assert "9 книг" in text and "17 записей" in text and "годы 1828–1923" in text
    assert "2 записи ещё не вычитаны" in text
    assert "О селе" not in text                                      # no prose, no section of it



def test_a_number_of_five_figures_has_its_thousands_set_apart() -> None:
    assert [pages.grouped(n) for n in (0, 1924, 9999, 12257, 1_000_000)] == [
        "0", "1924", "9999", "12\u00a0257", "1\u00a0000\u00a0000"]
    assert pages.counted(t("counted.records", count=12257), 12257) == "12\u00a0257 записей"


def test_the_front_page_groups_every_number_it_counts(site: model.Site, ctx: Context,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    def marked(count: int) -> str:
        return f"<{count}>"
    monkeypatch.setattr(pages, "grouped", marked)
    text = _text(pages.front(site, ctx)).replace("&lt;", "<").replace("&gt;", ">")
    assert "<9> книг" in text and "<17> записей" in text and "<2> записи ещё не вычитаны" in text
    assert re.search(r"<\d+> упоминан", text)



def test_every_count_of_the_indexes_is_grouped(site: model.Site, ui: Ui, ctx: Context,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    def marked(count: int) -> str:
        return f"[{count}]"
    monkeypatch.setattr(pages, "grouped", marked)
    assert re.search(r'<td class="n">\[\d+\]</td></tr>', pages.years_index(site, ui, ctx))
    assert re.search(r'<td class="n">\[\d+\]', pages.books_index(site, ui, ctx))
    assert re.search(r'<span class="n">\[\d+\]</span>', pages.names_index(site, ctx))
    page = next(p for p in pages.surname_pages(site))
    assert re.search(r'<p class="k">\[\d+\] ', pages.name(page, pages.NAMES, site, ui, ctx))


def test_a_mention_with_no_name_written_says_so(changed: Any, ui: Ui) -> None:
    """A link must say where it leads: a mention whose name was not written (a child the act leaves unnamed) is
    shown as such in the indexes and in the search, not as an empty link."""
    def unnamed(node: dict[str, Any]) -> None:
        record = node["documents"][0]["pages"][0]["records"][0]
        record["written"].pop("gender", None)          # no patronymic derived for a child of no stated sex
        child = record["persons"][0]
        child["written"], child["derived"] = {}, {}
    site = changed(unnamed)
    nobody = [m for m in site.mentions if not m.as_written]
    assert nobody
    rows = pages._mention_rows(nobody, site, ui, "")
    assert "(имя не записано)" in rows and not re.search(r"<a [^>]*>\s*</a>", rows)
    shown = {row[1] for row in json.loads(pages.search_index(site, ui))["rows"]}
    assert "" not in shown and "(имя не записано)" in shown


def test_a_page_links_within_the_site_by_relative_addresses(site: model.Site, ui: Ui, ctx: Context) -> None:
    made = [pages.front(site, ctx), pages.books_index(site, ui, ctx), pages.names_index(site, ctx),
            pages.search(site, ctx), pages.book(site.book(BIRTHS), ui, ctx), pages.year(1900, site, ui, ctx)]
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


def test_the_search_page_works_without_its_script(site: model.Site, ctx: Context) -> None:
    page = pages.search(site, ctx)
    assert "<noscript>" in page and 'href="../names/"' in page
    assert 'data-found="Найдено: {count}."' in page and 'src="../assets/search.js"' in page
    assert 'data-unread="не вычитано"' in page


def test_the_search_index_tells_each_book_what_its_filters_ask(changed: Change, ui: Ui) -> None:
    """A book's year (none for the cards), its source and its parish, which the search's filters compare."""
    def civil(node: dict[str, Any]) -> None:
        node["documents"][0]["written"]["civil"] = True
    site = changed(civil)
    asked = {book[0]: book[2:] for book in json.loads(pages.search_index(site, ui))["books"]}
    path = {book_.id: book_.path for book_ in site.books}
    assert asked[path[BIRTHS]] == [1900, "civil", "Маниловка"]
    assert asked[path[MARRIAGES]] == [1900, "metric", "Маниловка"]
    assert asked[path[DEATHS]] == [1913, "metric", "Хлестаковка"]
    assert asked[path[HOUSEHOLDS]] == [1828, "census", "Заманиловка"]
    assert asked[path[LISTED]] == [1917, "list", "Горюхино"]
    assert asked[path[WWI]] == [None, "cards", "Маниловка"]
    assert asked[path["r1:Заманиловка/1605-59-59/1923/divorce"]] == [1923, "civil", "Заманиловка"]   # no flag needed


def _filters(page: str) -> str:
    found = re.search(r'<fieldset id="filters"[^>]*>.*?</fieldset>', page)
    return found.group(0) if found else ""


def _options(page: str, name: str) -> list[tuple[str, str]]:
    select = re.search(rf'<select name="{name}" id="{name}">(.*?)</select>', page)
    assert select, name
    return re.findall(r'<option value="([^"]*)">([^<]*)</option>', select.group(1))


def test_the_search_page_draws_its_filters_in_the_form_hidden_until_its_script(site: model.Site, ctx: Context) -> None:
    """The filters stand in the search's form (Enter in a year searches), hidden — the script shows them; the years
    bounded by the site's, the sources and the parishes those of its books, in order, a choice of any first."""
    page = pages.search(site, ctx)
    form = re.search(r'<form id="search".*?</form>', page)
    assert form and _filters(page) and _filters(page) in form.group(0)
    assert re.match(r'<form id="search"[^>]* novalidate>', form.group(0))     # a year out of the bounds is no stop
    assert re.match(r'<fieldset id="filters" class="filters" aria-label="Отбор" hidden>', _filters(page))
    for name in ("from", "to"):
        assert re.search(rf'<input type="number" name="{name}" id="{name}" [^>]*min="1828" max="1923" step="1"', page)
    assert 'placeholder="1828"' in page and 'placeholder="1923"' in page
    assert re.search(r'id="to" aria-label="годы по"', page)                     # «по» alone says nothing
    assert _options(page, "source") == [("", "любой"), ("metric", "метрические книги"), ("civil", "книги ЗАГС"),
                                        ("census", "ревизии, росписи, переписи"), ("list", "другие списки"),
                                        ("cards", "карточки внешних каталогов")]
    assert _options(page, "village") == [("", "любой"), ("Горюхино", "Горюхино"), ("Заманиловка", "Заманиловка"),
                                         ("Маниловка", "Маниловка"), ("Хлестаковка", "Хлестаковка")]
    assert '<input type="checkbox" name="reviewed" id="reviewed" value="1"> только вычитанные' in page
    assert 'data-found-of="Найдено: {count} из {total}."' in page
    assert 'data-none-of="С этим отбором ничего не найдено, без него — {total}."' in page


@pytest.mark.parametrize(("books", "drawn"), [
    ((MARRIAGES,), set()),                                      # one year, source, parish; read through: none
    ((MARRIAGES, BIRTHS), {"reviewed"}),                        # two records of the births unread
    ((MARRIAGES, DEATHS), {"from", "to", "village"}),           # 1900 and 1913, two parishes
    ((MARRIAGES, WWI), {"source"}),                             # a metric book and cards without a year
    ((BIRTHS + "~unread",), set()),                             # all unread: «read only» would find nothing
])
def test_the_search_page_draws_only_the_filters_its_site_has_a_use_for(
        site: model.Site, ctx: Context, books: tuple[str, ...], drawn: set[str]) -> None:
    def book(each: str) -> model.Book:
        if each.endswith("~unread"):
            whole = site.book(each.removesuffix("~unread"))
            return replace(whole, entries=tuple(entry for entry in whole.entries if entry.unreviewed))
        return site.book(each)
    page = pages.search(replace(site, books=tuple(book(each) for each in books)), ctx)
    assert set(re.findall(r'id="(from|to|source|village|reviewed)"', page)) == drawn
    assert bool(_filters(page)) == bool(drawn) and ('id="filters"' in page) == bool(drawn)


def test_a_civil_register_is_a_source_of_its_own(changed: Change, ctx: Context) -> None:
    def civil(node: dict[str, Any]) -> None:
        node["documents"][0]["written"]["civil"] = True
    site = changed(civil)
    page = pages.search(replace(site, books=(site.book(BIRTHS), site.book(MARRIAGES))), ctx)
    assert _options(page, "source") == [("", "любой"), ("metric", "метрические книги"), ("civil", "книги ЗАГС")]


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



def _surnames(node: dict[str, Any], names: tuple[str, ...]) -> None:
    """The 1828 household's members (the site's first book) written with `names` as their surnames."""
    household = next(d for d in node["documents"] if "/1828/" in d["id"])
    members = household["pages"][0]["records"][0]["persons"]
    for member, surname in zip(members, names, strict=False):
        member["written"]["surname"] = {"original": surname}
        member.setdefault("derived", {}).pop("surname", None)


def test_a_reading_in_doubt_stands_on_its_sure_page_marked(changed: Any, ui: Ui, ctx: Context) -> None:
    """«Сидоровъ?» beside a surely read «Сидоров» (folded as the search folds: the hard sign, the old letters) is
    on the page of «Сидоров», marked — even read before any sure one (the household of 1828 comes first)."""
    site = changed(functools.partial(_surnames, names=("Сидоровъ?", "Ѳедоровъ", "Федоров?")))
    page = next(p for p in pages.surname_pages(site) if p.key == "Сидоров")
    assert not page.unread and page.title == "Сидоров, Сидорова" and len(page.doubtful) == 1
    old_letters = next(p for p in pages.surname_pages(site) if p.title == "Ѳедоровъ")      # sure in the old spelling
    assert not old_letters.unread and len(old_letters.mentions) == 2 and len(old_letters.doubtful) == 1
    doubtful = page.mentions[min(page.doubtful)]
    assert doubtful.entry.book_id.endswith("/1828/household")
    html_ = pages.name(page, pages.NAMES, site, ui, ctx)
    assert html_.count('class="doubt"') == 1 and 'title="прочтение под вопросом"' in html_


def test_a_reading_not_made_out_has_the_indexs_last_section(changed: Any, ctx: Context) -> None:
    """A part of a name, a letter not made out, a name read surely nowhere: each its own page, in a last section
    of the index — no «?» among the letters. One whose page's name a sure one takes keeps a directory of its own."""
    site = changed(functools.partial(_surnames, names=("Сид?ров", "?Сидоров", "Выдуманъ?")))
    found = pages.surname_pages(site)
    unread = [p for p in found if p.unread]
    assert sorted(p.title for p in unread) == ["?Сидоров", "Выдуманъ?", "Сид?ров"]
    assert all("?" not in p.title for p in found if not p.unread)
    assert len({p.key for p in found}) == len(found) and "Сидоров-" in {p.key for p in unread}
    index = pages.names_index(site, ctx)
    heads = re.findall(r'<h2 id="([^"]*)">([^<]*)</h2>', index)
    assert heads[-1] == ("unread", "Неразобранные") and "?" not in [head for _, head in heads]
    assert re.search(r'<a href="#unread">Неразобранные</a></nav>', index)
    last = index[index.index('<h2 id="unread">'):]
    assert all(title in last for title in ("Сид?ров", "Выдуманъ?"))


def test_a_reading_in_doubt_prefers_its_very_spelling_then_its_kin(changed: Any) -> None:
    """Of two sure spellings one folds to, the very one is its page («Фимкинъ?» on «Фимкинъ», not on
    «Фимкин»); a masculine in doubt stands with a sure feminine («Выдуманов?» on «Выдуманова»)."""
    site = changed(functools.partial(_surnames, names=("Фимкин", "Фимкинъ?", "Фимкинъ")))
    found = {p.title: p for p in pages.surname_pages(site)}
    assert len(found["Фимкинъ"].doubtful) == 1 and not found["Фимкин"].doubtful
    site = changed(functools.partial(_surnames, names=("Выдуманова", "Выдуманов?")))
    page = next(p for p in pages.surname_pages(site) if p.title == "Выдуманова")
    assert len(page.mentions) == 2 and len(page.doubtful) == 1



@pytest.mark.parametrize(("stem", "sure", "page"), [
    ("Выдуманов", "выдуманова", "выдуманова"), ("Выдуманова", "выдуманов", "выдуманов"),
    ("Выдуманская", "выдуманский", "выдуманский"), ("Выдуманский", "выдуманская", "выдуманская"),
    ("Выдуманъ", "выдуман", "выдуман"), ("Сидоров", "петров", None),
])
def test_a_stem_in_doubt_finds_its_sure_kin(stem: str, sure: str, page: str | None) -> None:
    assert pages._sure_page(stem, {sure}, {model.fold(sure): sure}) == page

def test_an_unread_pages_address_is_its_own(site: model.Site) -> None:
    """Whatever order its records come in, an unread reading keeps one address; never the page of the nameless
    («-»); a name written in decomposed letters is addressed as composed."""
    one, two = site.mentions[:2]
    forward = {p.title: p.key for p in pages._name_pages([("Ев?", one), ("?ев", two)])}
    backward = {p.title: p.key for p in pages._name_pages([("?ев", two), ("Ев?", one)])}
    assert forward == backward and len(set(forward.values())) == 2
    assert pages._name_pages([("?", one)])[0].key != pages.NAMELESS
    decomposed = unicodedata.normalize("NFD", "Чуйкинъ?")
    page = pages._name_pages([(decomposed, one)])[0]
    assert page.title == unicodedata.normalize("NFC", decomposed) and page.key == "Чуйкинъ"

def test_a_records_heading_stands_right_under_its_books(site: model.Site, ui: Ui, ctx: Context) -> None:
    page = pages.book(site.book(BIRTHS), ui, ctx)
    assert page.count("<h1>") == 1 and page.count("<h2>") == 5 and "<h3>" not in page
    assert '<nav aria-label="Разделы сайта">' in page
