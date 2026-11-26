"""The site's search (`assets/search.js`) in a real browser: a headless Chrome opens the built search page, served
over HTTP as a host would serve it, and the test reads the page it leaves. The index is the test's own — invented
names that hold every pre-reform letter the search folds — so the script's folding of a query is compared with
Python's folding of the index (`model.fold`), which the build writes.

Chrome is found on the PATH (`google-chrome`, `chromium`…) or where macOS keeps it; where there is none the test is
skipped, but not on CI (`CI` set), whose runners have one.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import pytest

from tests.ru.site.test_build import _build
from verso.ru.site import model

_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# (path, title, year, source, parish): the sources and the parishes are those the fixture's site draws as choices.
BOOKS = [["books/manilovka/1-1-1/1900/birth/", "Рождения 1900 — Маниловка", 1900, "metric", "Маниловка"],
         ["books/manilovka/1-1-1/1901/death/", "Смерти 1901 — Маниловка", 1901, "metric", "Маниловка"],
         ["books/zamanilovka/2-2-2/1828/household/", "Ревизия 1828 — Заманиловка", 1828, "census", "Заманиловка"],
         ["books/manilovka/card/wwi/", "Карточки: ПМВ", None, "cards", "Маниловка"]]
# (written, modern, book, anchor, role, unread) — the index's row, its folded text the build's own.
PEOPLE = [
    ("Насѣмовъ Ѳеодоръ", "Насемов Федор", 0, "m1", "Отец", 0),
    ("Ѳеодоръ Сѣмовъ", "Федор Семов", 0, "m2", "Младенец", 0),
    ("Іоаннъ Ѵпаркинъ", "Иоанн Ипаркин", 1, "m4а", "Умерший", 1),
    ("Подъячевъ Ёлкинъ", "", 1, "m1~2", "Отец", 0),
    ("Марья", "", 0, "f3", "Мать", 0),
    ("Ѳеодоръ Шкатулкинъ", "Федор Шкатулкин", 2, "h1", "Глава семьи", 0),
    ("Шкатулкинъ Ѳеодоръ", "Шкатулкин Федор", 3, "c1", "Солдат", 1),
]


def _chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if found := shutil.which(name):
            return found
    return _MAC if sys.platform == "darwin" and Path(_MAC).is_file() else None


# Enough of one invented name for a count of five figures, which the status sets apart as the pages do.
MANY = 10_234


def _index() -> dict[str, Any]:
    rows = [[model.fold(f"{written} {modern}"), written, modern, book, anchor, role, unread]
            for written, modern, book, anchor, role, unread in PEOPLE]
    rows += [["многоимъ", "Многоимъ", "", 0, f"m{n}", "Отец", 0] for n in range(MANY)]
    return {"books": BOOKS, "rows": rows}


def _year(text: str) -> int | None:
    """A bound as the page takes it: a whole year, as a field of numbers holds it («1e3» is 1000), else none."""
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() else None


def _kept(book: list[Any], row: list[Any], narrow: dict[str, str]) -> bool:
    """What the filters keep, worked out in Python: years either way round, a book without one out of any bound."""
    low, high = (_year(narrow.get(key, "")) for key in ("from", "to"))
    if low is not None and high is not None and low > high:
        low, high = high, low
    if (low is not None or high is not None) and book[2] is None:
        return False
    sources = {"metric", "civil", "census", "list", "cards"}                    # the choices the fixture's page draws
    villages = {"Горюхино", "Заманиловка", "Маниловка", "Хлестаковка"}
    return ((low is None or book[2] >= low) and (high is None or book[2] <= high)
            and (narrow.get("source") not in sources or book[3] == narrow["source"])
            and (narrow.get("village") not in villages or book[4] == narrow["village"])
            and not (narrow.get("reviewed") == "1" and row[6]))


def _matched(query: str) -> list[list[Any]]:
    """The rows the search should list for `query`, worked out in Python: every word inside a row, those that begin
    a word of it first."""
    words = model.fold(query).split()
    first, rest = [], []
    for row in _index()["rows"]:
        if all(word in row[0] for word in words):
            (first if all(" " + word in " " + row[0] for word in words) else rest).append(row)
    return first + rest


def _expected(query: str, narrow: dict[str, str] | None = None) -> list[str]:
    return [row[1] for row in _matched(query) if _kept(BOOKS[row[3]], row, narrow or {})]


# A page of the same site that opens the search for «федор» (its source one the page does not offer) in a frame,
# sets the source to the revisions there as a reader would, then a year before the site's, a parish, the read
# records only and a new query, submitted; and writes down what the search said at each step, and its address.
_DRIVER = """<!doctype html><meta charset="utf-8"><title>driver</title><pre id="out"></pre>
<iframe id="page" src="search/?q=%D1%84%D0%B5%D0%B4%D0%BE%D1%80&source=no-such"></iframe>
<script>
var frame = document.getElementById("page");
function later(then) { setTimeout(then, 400); }
frame.addEventListener("load", function () {
  var page = frame.contentDocument, seen = {};
  function look(step) {
    seen[step] = { status: page.getElementById("status").textContent,
                   address: decodeURIComponent(frame.contentWindow.location.search),
                   results: page.querySelectorAll("#results li").length };
  }
  later(function () {
    look("loaded");
    seen.loaded.source = page.getElementById("source").selectedIndex;
    var source = page.getElementById("source");
    source.value = "census";
    source.dispatchEvent(new Event("change", { bubbles: true }));
    later(function () {
      look("changed");
      page.getElementById("from").value = "1800";
      page.getElementById("village").value = "Заманиловка";
      page.getElementById("reviewed").checked = true;
      page.getElementById("q").value = "шкатулкин";
      page.getElementById("search").requestSubmit();
      later(function () {
        look("submitted");
        document.getElementById("out").textContent = JSON.stringify(seen);
      });
    });
  });
});
</script>
"""


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory, file_node: dict[str, Any]) -> Iterator[str]:
    """The fixture's site with the test's index, served on a port of its own; the address of its search page."""
    out = tmp_path_factory.mktemp("search") / "site"
    _build(file_node, out)
    (out / "search" / "index.json").write_text(json.dumps(_index(), ensure_ascii=False), encoding="utf-8")
    (out / "driver.html").write_text(_DRIVER, encoding="utf-8")       # a page that sets a filter on the search's
    handler = functools.partial(_Quiet, directory=str(out))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/search/"
    finally:
        server.shutdown()
        server.server_close()


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def _dom(address: str, tmp_path: Path) -> str:
    """The page at `address` as the browser leaves it once its scripts ran."""
    chrome = _chrome()
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("no Chrome on a CI runner: the search's browser test cannot run")
        pytest.skip("no Chrome here")
    assert chrome is not None
    profile = tempfile.mkdtemp(prefix="chrome-", dir=tmp_path)     # a profile a run: no lock left by the last
    ran = subprocess.run(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={profile}", "--virtual-time-budget=10000", "--dump-dom", address],
        capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 0, f"Chrome exited {ran.returncode}: {ran.stderr[-2000:]}"
    return ran.stdout


def _search(page: str, query: str, tmp_path: Path, narrow: dict[str, str] | None = None,
            ) -> tuple[str, list[tuple[str, str]]]:
    """The search page after the browser ran `query`, narrowed as the address asks: its status line and each
    result's (link, text)."""
    dom = _dom(f"{page}?{urlencode({'q': query, **(narrow or {})}, quote_via=quote)}", tmp_path)
    status = re.search(r'<p id="status"[^>]*>(.*?)</p>', dom, re.S)
    found = re.search(r'<ol id="results"[^>]*>(.*?)</ol>', dom, re.S)
    assert status and found, dom[-2000:]
    items = [(unescape(href), re.sub(r"<[^>]+>", "", unescape(text)))
             for href, text in re.findall(r'<li><a href="([^"]*)">(.*?)</li>', found.group(1), re.S)]
    return unescape(status.group(1)), items


@pytest.mark.parametrize("query", [
    "Федор", "ФЕОДОРЪ", "ѳеодор сѣмов", "семов", "Иоанн Ипаркин", "Ѵпаркинъ", "елкин", "Ёлкин", "Подъячев", "подячев",
    "Марья", "нет такого",
])
def test_the_search_finds_in_a_browser_what_python_folds_alike(served: str, query: str, tmp_path: Path) -> None:
    """The script folds a query as Python folded the index (the old letters as the new, ё as е, a hard sign gone
    only at a word's end) and lists a word that begins a name before one found inside another."""
    status, items = _search(served, query, tmp_path)
    expected = _expected(query)
    assert [next(row[1] for row in _index()["rows"] if text.startswith(row[1])) for _, text in items] == expected
    assert status == ("Ничего не найдено." if not expected else f"Найдено: {len(expected)}.")


def test_a_result_leads_to_its_record_and_says_what_it_is(served: str, tmp_path: Path) -> None:
    """A result links to its book's page and the record's anchor (encoded, «~» kept), shows the modern name, marks
    a record not yet read against its scan, and names the role and the book."""
    _, items = _search(served, "семов", tmp_path)
    assert items[0] == ("../books/manilovka/1-1-1/1900/birth/#m2",
                        "Ѳеодоръ Сѣмовъ Федор Семов — Младенец, Рождения 1900 — Маниловка")
    assert items[1][0] == "../books/manilovka/1-1-1/1900/birth/#m1"           # «Насѣмовъ»: found inside a word
    _, items = _search(served, "ипаркин", tmp_path)
    assert items == [("../books/manilovka/1-1-1/1901/death/#m4%D0%B0",
                      "Іоаннъ Ѵпаркинъ Иоанн Ипаркин не вычитано — Умерший, Смерти 1901 — Маниловка")]
    _, items = _search(served, "елкин", tmp_path)
    assert items[0][0] == "../books/manilovka/1-1-1/1901/death/#m1~2"


def test_a_count_of_five_figures_is_grouped_as_the_pages_group_it(served: str, tmp_path: Path) -> None:
    status, items = _search(served, "многоим", tmp_path)
    assert status.startswith("Найдено: 10\u00a0234.") and len(items) == 200


def _shown(items: list[tuple[str, str]]) -> list[str]:
    return [next(row[1] for row in _index()["rows"] if text.startswith(row[1])) for _, text in items]


@pytest.mark.parametrize("narrow", [
    {"from": "1850"}, {"to": "1900"}, {"from": "1901", "to": "1828"}, {"from": "1900", "to": "1900"},
    {"source": "census"}, {"source": "cards"}, {"source": "civil"}, {"source": "no-such"},
    {"village": "Заманиловка"}, {"village": "Хлестаковка"}, {"reviewed": "1"}, {"reviewed": "0"},
    {"from": "1828", "village": "Маниловка", "reviewed": "1"}, {"from": "год"}, {"from": "1e3"}, {"from": "1850.5"},
    {"from": "1800"},
])
def test_the_filters_the_address_sets_narrow_what_is_found(served: str, narrow: dict[str, str], tmp_path: Path) -> None:
    """The address's filters, set on the page, narrow the found as Python would: a year's bound leaves out the
    cards, which have none; bounds either way round are one span; a choice the page does not offer and a year that
    is no number narrow nothing. The status says how many of the found are kept."""
    status, items = _search(served, "федор", tmp_path, narrow)
    expected, total = _expected("федор", narrow), len(_matched("федор"))
    assert total == 4 and _shown(items) == expected
    if not expected:
        assert status == f"С этим отбором ничего не найдено, без него — {total}."
    elif len(expected) < total:
        assert status == f"Найдено: {len(expected)} из {total}."
    else:
        assert status == f"Найдено: {total}."


def test_the_filters_are_shown_by_the_script(served: str, tmp_path: Path) -> None:
    dom = _dom(served, tmp_path)
    fieldset = re.search(r'<fieldset id="filters"[^>]*>', dom)
    assert fieldset and "hidden" not in fieldset.group(0)


def test_a_filter_changed_searches_again_and_the_address_keeps_it(served: str, tmp_path: Path) -> None:
    """A choice the page does not offer reads «any»; a filter set on the page searches again at once; a year outside
    the site's does not stop the form; and the address names the query and every filter set: a search is a link to
    send."""
    dom = _dom(served.removesuffix("search/") + "driver.html", tmp_path)
    out = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    assert out and out.group(1), dom[-2000:]
    seen = json.loads(unescape(out.group(1)))
    assert seen["loaded"]["source"] == 0 and seen["loaded"]["status"] == "Найдено: 4."
    assert seen["changed"]["status"] == "Найдено: 1 из 4." and seen["changed"]["results"] == 1
    assert dict(parse_qsl(seen["changed"]["address"].removeprefix("?"))) == {"q": "федор", "source": "census"}
    assert seen["submitted"]["status"] == "Найдено: 1 из 2." and seen["submitted"]["results"] == 1
    assert dict(parse_qsl(seen["submitted"]["address"].removeprefix("?"))) == {
        "q": "шкатулкин", "from": "1800", "source": "census", "village": "Заманиловка", "reviewed": "1"}
