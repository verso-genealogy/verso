from __future__ import annotations

import re
from pathlib import Path

import pytest

from verso.ru.site import model, prose
from verso.ru.site.shell import Context

pytest.importorskip("markdown_it")

REPO = "https://example.org/owner/manilovka-records"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace with the fixture's one DSL file, a notes file outside the prose, and the prose."""
    village = tmp_path / "ws" / "Маниловка"
    (village / "1900").mkdir(parents=True)
    (village / "1900" / "all.py").write_text("", encoding="utf-8")
    (village / "village.toml").write_text("schema = 1\n", encoding="utf-8")
    docs = village / "docs"
    docs.mkdir()
    (docs / "README.md").write_text("# О Маниловке\n\n- [Места](places.md)\n- [История](history.md)\n", encoding="utf-8")
    (docs / "history.md").write_text(
        "# История\n\nСело стоит на реке *с давних пор*.\n\n## Первые книги\n\n"
        "Книга 1900 года — [здесь](../1900/all.py), настройки — [в файле](../village.toml), "
        "места — [отдельно](places.md#храмы).\n\n| год | книг |\n|---|---|\n| 1900 | 2 |\n\n<script>alert(1)</script>\n",
        encoding="utf-8")
    (docs / "places.md").write_text("# Места\n\n## Храмы\n\nЦерковь.\n", encoding="utf-8")
    (docs / "archives.md").write_text("Без заголовка.\n", encoding="utf-8")
    return tmp_path / "ws"


def _render(workspace: Path, site: model.Site, name: str, ctx: Context) -> str:
    docs = workspace / "Маниловка" / "docs"
    page = next(p for p in prose.listed(docs) if p.source.name == name)
    return prose.render(page, docs, site, ctx, workspace)


def test_the_contents_order_the_pages(workspace: Path) -> None:
    pages = prose.listed(workspace / "Маниловка" / "docs")
    assert [(p.path, p.title) for p in pages] == [
        ("about/", "О Маниловке"), ("places/", "Места"), ("history/", "История"), ("archives/", "archives")]


def test_a_village_without_prose_asks_for_no_markdown_reader(tmp_path: Path) -> None:
    assert prose.listed(tmp_path / "docs") == [] and prose.listed(None) == []
    (tmp_path / "docs").mkdir()
    assert prose.listed(tmp_path / "docs") == []


def test_a_page_is_drawn_from_its_markdown(workspace: Path, site: model.Site) -> None:
    page = _render(workspace, site, "history.md", Context("Село Маниловка", "ru", repo_url=REPO))
    assert "<title>История — Село Маниловка</title>" in page
    assert '<h2 id="первые-книги">Первые книги</h2>' in page and "<em>с давних пор</em>" in page
    assert "<table>" in page and "<td>1900</td>" in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert" not in page


def test_a_link_leads_where_the_site_has_the_thing(workspace: Path, site: model.Site) -> None:
    page = _render(workspace, site, "history.md", Context("Село Маниловка", "ru", repo_url=REPO))
    links = dict(re.findall(r'<a href="([^"]*)">([^<]*)</a>', page))
    by_text = {text: href for href, text in links.items()}
    assert by_text["здесь"] == "../books/zamanilovka/735-265-53_str-80/1828/household/"   # the file's first book
    assert by_text["отдельно"] == "../places/#%D1%85%D1%80%D0%B0%D0%BC%D1%8B"
    assert by_text["в файле"] == f"{REPO}/blob/main/%D0%9C%D0%B0%D0%BD%D0%B8%D0%BB%D0%BE%D0%B2%D0%BA%D0%B0/village.toml"
    contents = _render(workspace, site, "README.md", Context("Село Маниловка", "ru"))
    assert '<a href="../places/">Места</a>' in contents


def test_a_link_to_a_file_the_site_does_not_show_needs_the_repository(workspace: Path, site: model.Site) -> None:
    with pytest.raises(prose.ProseError, match=r"history\.md: \.\./village\.toml"):
        _render(workspace, site, "history.md", Context("Село Маниловка", "ru"))


@pytest.mark.parametrize(("link", "said"), [("../../../outside.md", "за пределы"), ("nothing.md", "в никуда")])
def test_a_link_that_leads_nowhere_is_refused(workspace: Path, site: model.Site, link: str, said: str) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text(f"# Места\n\n[туда]({link})\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match=said):
        _render(workspace, site, "places.md", Context("Село Маниловка", "ru", repo_url=REPO))


def test_an_image_is_refused(workspace: Path, site: model.Site) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text("# Места\n\n![карта](map.png)\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match="картинка"):
        _render(workspace, site, "places.md", Context("Село Маниловка", "ru"))


def test_a_page_named_as_a_directory_of_the_site_is_refused(workspace: Path) -> None:
    (workspace / "Маниловка" / "docs" / "books.md").write_text("# Книги\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match=r"books\.md"):
        prose.listed(workspace / "Маниловка" / "docs")


def test_the_settlements_summary_is_the_historys_first_paragraph(workspace: Path) -> None:
    assert prose.first_paragraph(workspace / "Маниловка" / "docs") == "Село стоит на реке с давних пор."


@pytest.mark.parametrize(("heading", "slug"), [
    ("Первые книги", "первые-книги"), ("Храмы", "храмы"), ("Церковь св. Николая (1791–1894)", "церковь-св-николая-17911894"),
    ("Что не сохранилось?", "что-не-сохранилось"), ("ГАТО, ф. 12", "гато-ф-12"), ("snake_case и дефис-слово", "snake_case-и-дефис-слово"),
])
def test_a_headings_id_is_the_one_github_gives_it(heading: str, slug: str) -> None:
    assert prose.heading_slug(heading) == slug


def test_a_heading_is_slugged_by_its_words_and_a_repeat_is_numbered(workspace: Path, site: model.Site) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text(
        "# Места\n\n## Храмы\n\n## [Храмы](history.md) и *часовни*\n\n## Храмы\n\n## Храмы\n\n"
        "[к повтору](#храмы-1), [в историю](history.md#первые-книги)\n", encoding="utf-8")
    page = _render(workspace, site, "places.md", Context("Село Маниловка", "ru"))
    assert re.findall(r'<h2 id="([^"]*)">', page) == ["храмы", "храмы-и-часовни", "храмы-1", "храмы-2"]
    assert 'href="#%D1%85%D1%80%D0%B0%D0%BC%D1%8B-1"' in page          # the same page's section, as a link spells it
    assert 'href="../history/#%D0%BF%D0%B5%D1%80%D0%B2%D1%8B%D0%B5-%D0%BA%D0%BD%D0%B8%D0%B3%D0%B8"' in page


def test_the_names_the_site_keeps_are_said_once() -> None:
    from verso.ru import site as site_package
    assert site_package.RESERVED == {"assets", "books", "cards", "years", "names", "patronymics", "search", "about"}


def test_a_page_named_as_the_sites_own_in_another_case_is_refused(workspace: Path) -> None:
    """Where a file system tells no case apart, `Books/` is `books/` and the page would replace the index."""
    (workspace / "Маниловка" / "docs" / "Books.md").write_text("# Книги\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match=r"Books\.md"):
        prose.listed(workspace / "Маниловка" / "docs")


@pytest.mark.parametrize("name", ["a#b.md", "50%.md", "что это?.md", "два слова.md"])
def test_a_page_is_named_as_an_address_spells_it(workspace: Path, name: str) -> None:
    (workspace / "Маниловка" / "docs" / name).write_text("# Страница\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match="называется"):
        prose.listed(workspace / "Маниловка" / "docs")


def test_a_page_that_is_a_link_to_another_file_is_refused(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "private.md"
    outside.write_text("# Не для сайта\n", encoding="utf-8")
    (workspace / "Маниловка" / "docs" / "leak.md").symlink_to(outside)
    with pytest.raises(prose.ProseError, match=r"leak\.md"):
        prose.listed(workspace / "Маниловка" / "docs")


def test_a_link_to_the_workspace_itself_and_a_line_of_a_file(workspace: Path, site: model.Site) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text(
        "# Места\n\n[репозиторий](../../), [строка](../village.toml#L3)\n", encoding="utf-8")
    page = _render(workspace, site, "places.md", Context("Село Маниловка", "ru", repo_url=REPO + "/"))
    by_text = {text: href for href, text in re.findall(r'<a href="([^"]*)">([^<]*)</a>', page)}
    assert by_text["репозиторий"] == REPO
    assert by_text["строка"].endswith("/village.toml#L3")


def test_a_link_no_file_system_takes_is_a_dead_link(workspace: Path, site: model.Site) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text("# Места\n\n[туда](a%00b.md)\n", encoding="utf-8")
    with pytest.raises(prose.ProseError, match="в никуда"):
        _render(workspace, site, "places.md", Context("Село Маниловка", "ru", repo_url=REPO))


def test_a_number_taken_by_a_heading_is_not_given_twice(workspace: Path, site: model.Site) -> None:
    (workspace / "Маниловка" / "docs" / "places.md").write_text(
        "# Места\n\n## B\n\n## B\n\n### b-1\n\n## ?!\n", encoding="utf-8")
    page = _render(workspace, site, "places.md", Context("Село Маниловка", "ru"))
    assert re.findall(r"<h[23]( id=\"[^\"]*\")?>", page) == [' id="b"', ' id="b-1"', ' id="b-1-1"', ""]
