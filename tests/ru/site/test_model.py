from __future__ import annotations

import copy
from typing import Any

import pytest

from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.domain import page, person
from verso.ru.dsl.records.name_lists import listed_person, name_list_records
from verso.ru.site import model


def test_a_book_is_what_its_records_are_cited_from(site: model.Site) -> None:
    paths = [book.path for book in site.books]
    assert paths == [
        "books/zamanilovka/735-265-53_str-80/1828/household/",
        "books/manilovka/47-9-755/1900/birth/",
        "books/manilovka/47-9-755/1900/marriage/",
        "books/hlestakovka/47-9-755/1913/death/",
        "books/gorjuhino/1978-5-9700/1917/listed/",
        "books/zamanilovka/1605-59-59/1923/divorce/",
        "cards/manilovka/criminal/",
        "cards/manilovka/wwi/",
        "cards/manilovka/wwii/",
    ]


def test_an_alias_of_a_record_set_is_no_second_book(site: model.Site) -> None:
    deaths = [book for book in site.books if book.kind == "death"]
    assert len(deaths) == 1 and len(deaths[0].entries) == 4


def test_a_book_under_its_own_parish(site: model.Site) -> None:
    by_path = {book.path: book for book in site.books}
    assert by_path["books/hlestakovka/47-9-755/1913/death/"].village == "Хлестаковка"


def test_entries_keep_the_books_order_and_their_leaves(site: model.Site) -> None:
    births = site.book("r1:Маниловка/47-9-755/1900/birth")
    assert [(e.anchor, e.leaf, e.review) for e in births.entries] == [
        ("m1", "1", "reviewed"), ("f2", "1", "held"), ("f3", "1", "on_geni"), ("m4", "1об", "reviewed"),
        ("m4а", "1", "reviewed")]
    assert births.unreviewed == 2


def test_the_order_of_the_files_does_not_order_the_books(file_node: dict[str, Any]) -> None:
    first = {**file_node, "documents": file_node["documents"][:3], "file": "1900/a.py"}
    second = {**file_node, "documents": file_node["documents"][3:], "file": "1900/b.py"}
    one = model.load([first, second], village="Маниловка")
    other = model.load([second, first], village="Маниловка")
    assert [b.path for b in one.books] == [b.path for b in other.books]


def test_two_books_of_one_path_are_refused(file_node: dict[str, Any]) -> None:
    doc = file_node["documents"][1]

    def renamed(shelf: str) -> dict[str, Any]:
        run = doc["pages"][0]
        record = {**run["records"][0], "id": f"r1:Маниловка/{shelf}/1900/marriage/1"}
        return {**doc, "id": f"r1:Маниловка/{shelf}/1900/marriage", "pages": [{**run, "records": [record]}]}

    twins = {**file_node, "documents": [renamed("47-9-12а"), renamed("47-9-12a")]}
    with pytest.raises(model.DuplicatePath) as refused:
        model.load([twins], village="Маниловка")
    assert "47-9-12а" in str(refused.value) and "47-9-12a" in str(refused.value)


def test_mentions_name_every_person_but_a_hidden_member(site: model.Site) -> None:
    household = site.book("r1:Заманиловка/735-265-53;стр-80/1828/household")
    mentions = [m for m in site.mentions if m.entry.book_id == household.id]
    assert [m.as_written for m in mentions] == ["Иванъ Петровъ", "Марья", "Петръ Иванов"]


def test_a_mention_is_keyed_by_surname_else_by_patronymic(site: model.Site) -> None:
    births = site.book("r1:Маниловка/47-9-755/1900/birth")
    first = [m for m in site.mentions if m.entry.id == births.entries[0].id]
    assert [(m.role, m.surname, m.patronymic) for m in first] == [
        ("child", "Сидоров", "Петров"), ("father", "Сидоров", "Иванов"), ("mother", "Сидорова", "Петрова"),
        ("godparent", "Сидоров", "Петров"), ("relative", "Сидоров", "Петров")]


def test_a_leaf_released_in_a_held_list_is_read_and_the_rest_is_not() -> None:
    """The export says it of the built record (`review`); no key of `written` alone does — an entry under
    `page(…, reviewed=True)` writes the flag, its neighbour off the page inherits the set's."""
    names = name_list_records(
        "ЦГА", "7", "3", "41", "Примерово", 1917,
        *page("5", listed_person(1, person("Иванъ")), listed_person(2, person("Петръ"), reviewed=False), reviewed=True),
        listed_person(3, person("Сидоръ")), document_type="Список", reviewed=False)
    node = encode_namespace({"names": names}, village="Примерово", file="1917/names.py", sha256="", ids=Ids())
    site = model.load([node], village="Примерово")
    assert [(e.anchor, e.unreviewed) for e in site.books[0].entries] == [("1", False), ("2", True), ("3", True)]
    assert site.unreviewed == 2


def test_a_record_that_does_not_say_whether_it_was_read_is_no_export(file_node: dict[str, Any]) -> None:
    doc = file_node["documents"][1]
    run = doc["pages"][0]
    silent = {key: value for key, value in run["records"][0].items() if key != "review"}
    stored = {**file_node, "documents": [{**doc, "pages": [{**run, "records": [silent]}]}]}
    with pytest.raises(model.NotAnExport, match="r1:Маниловка/47-9-755/1900/marriage/1"):
        model.load([stored], village="Маниловка")


def test_a_persona_without_a_role_is_no_export(file_node: dict[str, Any]) -> None:
    doc = file_node["documents"][1]
    run = doc["pages"][0]
    record = run["records"][0]
    nobody = {key: value for key, value in record["persons"][0].items() if key != "role"}
    stored = {**file_node, "documents": [{**doc, "pages": [{**run, "records": [{**record, "persons": [nobody]}]}]}]}
    with pytest.raises(model.NotAnExport):
        model.load([stored], village="Маниловка")


def test_a_village_no_address_can_be_made_of_is_refused(file_node: dict[str, Any]) -> None:
    from verso.ru.site.errors import SiteError
    doc = file_node["documents"][1]
    run = doc["pages"][0]
    record = {**run["records"][0], "id": "r1:?/47-9-755/1900/marriage/1"}
    stored = {**file_node, "documents": [{**doc, "pages": [{**run, "records": [record]}]}]}
    with pytest.raises(SiteError, match="адрес не из чего"):
        model.load([stored], village="Маниловка")


# --- an infant's patronymic ---------------------------------------------------------------------------------

CHILD = "r1:Маниловка/47-9-755/1900/birth/m1/child"


def _persons(node: dict[str, Any], record: str) -> list[dict[str, Any]]:
    return next(r for d in node["documents"] if "pages" in d for p in d["pages"] for r in p["records"]
                if r["id"] == record)["persons"]


def _child(site: model.Site) -> model.Mention:
    return next(m for m in site.mentions if m.persona["id"] == CHILD)


def _before_v10(node: dict[str, Any]) -> None:
    """The node as an export made before the library derived a newborn's patronymic (В10): the child's derived
    patronymic taken out, as `infant_patronymic` finds it in such an export."""
    for doc in node["documents"]:
        for run in doc.get("pages", []):
            for record in run["records"]:
                for persona in record.get("persons", []):
                    if persona.get("role") == "child":
                        (persona.get("derived") or {}).pop("patronymic", None)


def test_an_infant_takes_its_fathers_patronymic_as_the_library_derives_it(site: model.Site) -> None:
    """A birth writes no patronymic of the child; the site says the father's, as derived — as it says the
    father's surname (`Birth`), and as the Geni translator and the CSV derive it."""
    child = _child(site)
    assert child.modern == "Иван Петрович Сидоров"
    assert model.form(child.persona, "patronymic", "modern") == ("Петрович", "d")


def test_the_export_carries_the_infants_patronymic_and_the_site_reads_it_from_there(file_node: dict[str, Any]) -> None:
    """Since В10 the library derives it (`Birth.__init__`), both forms, into the export's `derived`; the site's
    own derivation is for an export made before."""
    child = next(p for p in _persons(file_node, CHILD.rsplit("/", 1)[0]) if p["role"] == "child")
    assert child["derived"]["patronymic"] == {"old": "Петров", "modern": "Петрович"}
    record = next(r for d in file_node["documents"] if "pages" in d for p in d["pages"] for r in p["records"]
                  if r["id"] == CHILD.rsplit("/", 1)[0])
    assert model.infant_patronymic(record) is record


def test_a_daughter_takes_the_feminine_and_the_file_node_is_left_as_it_was(file_node: dict[str, Any]) -> None:
    node = copy.deepcopy(file_node)
    record = next(r for d in node["documents"] if "pages" in d for p in d["pages"] for r in p["records"]
                  if r["id"] == CHILD.rsplit("/", 1)[0])
    record["written"]["gender"] = "female"
    _before_v10(node)
    before = copy.deepcopy(node)
    site = model.load([node], village="Маниловка")
    assert model.form(_child(site).persona, "patronymic", "modern") == ("Петровна", "d")
    assert node == before                                        # the export read, not rewritten


def test_a_christening_names_its_child_as_a_birth_does_and_a_null_form_is_no_patronymic(
        changed: Any) -> None:
    """A christening is a birth (`Christening(Birth)`); `person("Иван", None)` exports a patronymic of no form,
    which writes none."""
    def rewrite(node: dict[str, Any]) -> None:
        record = next(r for d in node["documents"] if "pages" in d for p in d["pages"] for r in p["records"]
                      if r["id"] == CHILD.rsplit("/", 1)[0])
        record["kind"] = "christening"
        next(p for p in record["persons"] if p["role"] == "child")["written"]["patronymic"] = {"original": None}
        _before_v10(node)
    assert model.form(_child(changed(rewrite)).persona, "patronymic", "modern") == ("Петрович", "d")


@pytest.mark.parametrize("change", ["written", "no father", "unread father", "no gender"])
def test_no_patronymic_is_made_where_the_record_gives_one_or_none_can_be_made(
        changed: Any, change: str) -> None:
    def rewrite(node: dict[str, Any]) -> None:
        _before_v10(node)
        persons = _persons(node, CHILD.rsplit("/", 1)[0])
        child = next(p for p in persons if p["role"] == "child")
        if change == "written":
            child["written"]["patronymic"] = {"original": "Сергѣевъ"}
        elif change == "no father":
            persons[:] = [p for p in persons if p["role"] != "father"]
        elif change == "unread father":
            father = next(p for p in persons if p["role"] == "father")
            father["written"]["given"] = {"original": "?"}
            father["derived"]["given"] = {"modern": "?"}
        else:
            next(r for d in node["documents"] if "pages" in d for p in d["pages"] for r in p["records"]
                 if r["id"] == CHILD.rsplit("/", 1)[0])["written"].pop("gender")
    child = _child(changed(rewrite))
    assert model.form(child.persona, "patronymic", "modern") is None
    if change == "written":
        assert model.form(child.persona, "patronymic", "original") == ("Сергѣевъ", "w")
