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
