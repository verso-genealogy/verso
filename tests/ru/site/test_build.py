from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path
from typing import Any

import pytest

from tests.ru.site.conftest import VILLAGE
from verso.ru import site as site_package
from verso.ru.site import check, model

URL = "https://example.org/manilovka-records/"


def _build(file_node: dict[str, Any], out: Path, **settings: Any) -> site_package.Built:
    return site_package.build([file_node], out=out, village=VILLAGE, title="Село Маниловка", lang="ru", **settings)


def _digest(out: Path) -> dict[str, str]:
    return {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(out.rglob("*")) if path.is_file()}


def test_a_built_site_holds_no_dead_end(file_node: dict[str, Any], tmp_path: Path) -> None:
    built = _build(file_node, tmp_path / "site", site_url=URL, repo_url="https://example.org/repo")
    assert built.problems == ()
    assert (built.books, built.records, built.unreviewed) == (9, 17, 2)
    made = set(_digest(tmp_path / "site"))
    assert {"index.html", "404.html", "robots.txt", "sitemap.xml", "assets/site.css", "assets/search.js", "assets/theme.js",
            "search/index.html", "search/index.json", "books/index.html", "years/1900/index.html",
            "books/manilovka/47-9-755/1900/birth/index.html", "cards/manilovka/wwi/index.html",
            "names/Сидоров/index.html", "patronymics/Иванов/index.html", "patronymics/-/index.html"} <= made
    assert built.pages == sum(1 for name in made if name.endswith("index.html"))


def test_the_site_draws_with_its_own_fonts_and_names_their_licences(file_node: dict[str, Any], tmp_path: Path) -> None:
    """The fonts are the site's own files (nothing fetched from another host), each beside its licence: every
    `url(…)` of the stylesheet is a file the build wrote, and none leaves the site."""
    _build(file_node, tmp_path / "site")
    css = (tmp_path / "site" / "assets" / "site.css").read_text(encoding="utf-8")
    named = re.findall(r'url\("?([^")]+)"?\)', css)
    assert named and all(not re.match(r"[a-z]+:|//", url) for url in named)
    for url in named:
        assert (tmp_path / "site" / "assets" / url).is_file(), url
    fonts = sorted(p.name for p in (tmp_path / "site" / "assets" / "fonts").iterdir())
    assert [n for n in fonts if n.endswith(".woff2")] == [
        "cormorant-garamond-italic.woff2", "jetbrains-mono.woff2", "noto-sans-old.woff2", "onest.woff2"]
    assert [n for n in fonts if n.startswith("OFL-")] == [
        "OFL-CormorantGaramond.txt", "OFL-JetBrainsMono.txt", "OFL-NotoSans.txt", "OFL-Onest.txt"]
    assert "@import" not in css


def test_the_package_ships_every_asset_the_build_copies() -> None:
    """The build copies `ASSETS` out of the installed package: a wheel holds only what `package-data` names, and a
    test run from the source would not see a font a glob left out."""
    import fnmatch
    import tomllib
    data = tomllib.loads((Path(__file__).parents[3] / "packages" / "verso-ru" / "pyproject.toml").read_text(
        encoding="utf-8"))["tool"]["setuptools"]["package-data"]["verso.ru.site"]
    for name in site_package.ASSETS:
        assert any(fnmatch.fnmatch(f"assets/{name}", glob) and glob.count("/") == f"assets/{name}".count("/")
                   for glob in data), name


def test_the_same_records_make_the_same_bytes(file_node: dict[str, Any], tmp_path: Path) -> None:
    _build(file_node, tmp_path / "one", site_url=URL, revision="abc1234")
    _build(file_node, tmp_path / "two", site_url=URL, revision="abc1234")
    assert _digest(tmp_path / "one") == _digest(tmp_path / "two")


def test_a_site_is_built_into_nothing_but_an_empty_directory(file_node: dict[str, Any], tmp_path: Path) -> None:
    out = tmp_path / "site"
    out.mkdir()
    (out / "mine.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(site_package.BuildError, match="не пуст"):
        _build(file_node, out)
    assert [path.name for path in out.iterdir()] == ["mine.txt"]


def test_a_site_that_knows_its_address_lists_its_pages(file_node: dict[str, Any], tmp_path: Path) -> None:
    _build(file_node, tmp_path / "with", site_url=URL.rstrip("/"))
    sitemap = (tmp_path / "with" / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{URL}</loc>" in sitemap and f"<loc>{URL}books/manilovka/47-9-755/1900/birth/</loc>" in sitemap
    encoded = "names/%D0%A1%D0%B8%D0%B4%D0%BE%D1%80%D0%BE%D0%B2/"        # a page named in Cyrillic, as an address
    assert f"<loc>{URL}{encoded}</loc>" in sitemap
    name = (tmp_path / "with" / "names" / "Сидоров" / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{URL}{encoded}">' in name
    assert f"Sitemap: {URL}sitemap.xml" in (tmp_path / "with" / "robots.txt").read_text(encoding="utf-8")
    assert f'<base href="{URL}">' in (tmp_path / "with" / "404.html").read_text(encoding="utf-8")
    page = (tmp_path / "with" / "books" / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{URL}books/">' in page
    _build(file_node, tmp_path / "without")
    assert not (tmp_path / "without" / "sitemap.xml").exists()
    assert "Sitemap" not in (tmp_path / "without" / "robots.txt").read_text(encoding="utf-8")


def test_one_unread_book_alone_makes_a_whole_site(file_node: dict[str, Any], tmp_path: Path) -> None:
    doc = {**file_node["documents"][0]}
    held = [{**record, "review": "held"} for run in doc["pages"] for record in run["records"]]
    doc["pages"] = [{"page": "1", "records": held}]
    built = _build({**file_node, "documents": [doc]}, tmp_path / "site")
    assert built.problems == () and (built.books, built.records, built.unreviewed) == (1, 5, 5)
    front = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "5 записей ещё не вычитано" in front and "О селе" not in front


def test_the_site_speaks_the_language_it_is_built_in(file_node: dict[str, Any], tmp_path: Path) -> None:
    site_package.build([file_node], out=tmp_path / "en", village=VILLAGE, lang="en")
    page = (tmp_path / "en" / "books" / "manilovka" / "47-9-755" / "1900" / "birth" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in page and "not proofread" in page and "не вычитано" not in page
    assert "Иванъ" in page                                         # the record stays as it is written


def test_the_search_index_is_the_sites_own_file(file_node: dict[str, Any], tmp_path: Path) -> None:
    _build(file_node, tmp_path / "site")
    data = json.loads((tmp_path / "site" / "search" / "index.json").read_text(encoding="utf-8"))
    assert {tuple(book) for book in data["books"]} >= {("books/manilovka/47-9-755/1900/marriage/", "Браки 1900 — Маниловка")}


def test_the_check_names_what_a_reader_would_meet(tmp_path: Path) -> None:
    out = tmp_path / "site"
    (out / "a").mkdir(parents=True)
    (out / "index.html").write_text(
        '<a href="a/">there</a> <a href="a/#x">an anchor</a> <a href="a/#gone">no anchor</a> <a href="b/">gone</a>'
        '<a href="https://example.org/">abroad</a> <p id="twice"></p><p id="twice"></p>'
        '<script src="https://cdn.example.org/x.js"></script><img src="//cdn.example.org/x.png">'
        '<link rel="canonical" href="https://example.org/">', encoding="utf-8")
    (out / "a" / "index.html").write_text('<p id="x"></p><a href="../">home</a>', encoding="utf-8")
    found = {(p.page, p.what, p.detail) for p in check.verify(out)}
    assert found == {("index.html", "broken_anchor", "a/#gone"), ("index.html", "broken_link", "b/"),
                     ("index.html", "duplicate_id", "twice"),
                     ("index.html", "fetched", "https://cdn.example.org/x.js"),
                     ("index.html", "fetched", "//cdn.example.org/x.png")}



def test_the_check_reads_start_tags_as_the_html_parser_does() -> None:
    """The check's one pattern finds what `html.parser` finds: names lowered, references resolved, an attribute
    with no value told from an empty one, and nothing inside a comment, a declaration, a script or a style."""
    from html.parser import HTMLParser

    class Reference(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.page = check._Page()

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.page.start(tag, attrs)

    text = ('<!DOCTYPE html><!-- <a href="in-a-comment/"> --><A HREF="up/" ID="One">x</A>'
            "<a href='single/?q=1&amp;r=2' id=bare>y</a><a href=unquoted/>z</a><form action=\"go/\" id=\"\">"
            '<p id="a&quot;b" hidden data-x="1 > 0"></p><a href>no address</a><img src="i.png"/><link rel="canonical" href="//c/">'
            '<script src="s.js">document.write(\'<a href="in-a-script/">\')</script>'
            '<style>a[href="in-a-style/"] {}</style><SCRIPT>"<a href=\'shout/\'>"</SCRIPT><a href="after/">')
    reference = Reference()
    reference.feed(text)
    reference.close()
    found = check._scan(text)
    assert found == reference.page
    assert found.links == ["up/", "single/?q=1&r=2", "unquoted/", "go/", "after/"]
    assert found.ids == ["One", "bare", 'a"b'] and found.fetched == ["i.png", "s.js"]


def test_the_check_reads_the_tree_once_not_a_file_a_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every address is looked up in the set of the tree's files, not asked of the file system: a hundred thousand
    links cost no more than reading their pages. A name in another case is another address (Pages tells them
    apart), and so is one outside the tree."""
    out = tmp_path / "site"
    (out / "a").mkdir(parents=True)
    (out / "a" / "index.html").write_text('<p id="x"></p>', encoding="utf-8")
    (out / "index.html").write_text('<a href="a/#x">1</a><a href="a">2</a><a href="A/">3</a><a href="../site/">4</a>'
                                    '<a href="/a/">5</a><a href="#top">6</a><p id="top"></p>', encoding="utf-8")

    def asked(*_: object, **__: object) -> None:
        raise AssertionError("a link asked of the file system")
    with monkeypatch.context() as patched:
        for name in ("is_file", "is_dir", "exists"):
            patched.setattr(Path, name, asked)
        found = {(p.what, p.detail) for p in check.verify(out)}
    assert found == {("broken_link", "A/"), ("broken_link", "../site/"), ("broken_link", "/a/")}

def test_two_books_of_one_address_stop_the_build(file_node: dict[str, Any], tmp_path: Path) -> None:
    doc = file_node["documents"][1]
    twins = []
    for shelf in ("47-9-12а", "47-9-12a"):
        run = doc["pages"][0]
        record = {**run["records"][0], "id": f"r1:Маниловка/{shelf}/1900/marriage/1"}
        twins.append({**doc, "id": f"r1:Маниловка/{shelf}/1900/marriage", "pages": [{**run, "records": [record]}]})
    with pytest.raises(model.DuplicatePath):
        _build({**file_node, "documents": twins}, tmp_path / "site")
    assert not (tmp_path / "site").exists()


@pytest.mark.parametrize("flag", ["repo_url", "site_url", "license_url"])
def test_an_address_is_an_address(file_node: dict[str, Any], tmp_path: Path, flag: str) -> None:
    with pytest.raises(site_package.BuildError, match="javascript"):
        _build(file_node, tmp_path / "site", **{flag: "javascript:alert(1)"})
    assert not (tmp_path / "site").exists()


def test_every_refusal_is_one_family() -> None:
    from verso.ru.site import prose, urls
    for refusal in (site_package.BuildError, model.DuplicatePath, model.NotAnExport, prose.ProseError, urls.BadAddress):
        assert issubclass(refusal, site_package.SiteError)


def test_the_dark_theme_is_one_set_of_colours_whether_the_system_or_the_reader_chose_it() -> None:
    """The stylesheet spells the dark tokens twice — under the system's dark (unless the reader chose light) and
    under the reader's dark — as CSS has no one selector for both; the two must not drift apart."""
    css = (Path(site_package.__file__).parent / "assets" / "site.css").read_text(encoding="utf-8")
    def tokens(selector: str) -> list[str]:
        block = css[css.index(selector + " {"):]
        return sorted(re.findall(r"--[\w-]+:[^;]+;", block[:block.index("}")]))
    system, chosen = tokens(':root:not([data-theme="light"])'), tokens(':root[data-theme="dark"]')
    assert system and system == chosen
