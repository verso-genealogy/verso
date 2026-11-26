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
from urllib.parse import quote

import pytest

from tests.ru.site.test_build import _build
from verso.ru.site import model

_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BOOKS = [["books/manilovka/1-1-1/1900/birth/", "Рождения 1900 — Маниловка"],
         ["books/manilovka/1-1-1/1901/death/", "Смерти 1901 — Маниловка"]]
# (written, modern, book, anchor, role, unread) — the index's row, its folded text the build's own.
PEOPLE = [
    ("Насѣмовъ Ѳеодоръ", "Насемов Федор", 0, "m1", "Отец", 0),
    ("Ѳеодоръ Сѣмовъ", "Федор Семов", 0, "m2", "Младенец", 0),
    ("Іоаннъ Ѵпаркинъ", "Иоанн Ипаркин", 1, "m4а", "Умерший", 1),
    ("Подъячевъ Ёлкинъ", "", 1, "m1~2", "Отец", 0),
    ("Марья", "", 0, "f3", "Мать", 0),
]


def _chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if found := shutil.which(name):
            return found
    return _MAC if sys.platform == "darwin" and Path(_MAC).is_file() else None


def _index() -> dict[str, Any]:
    rows = [[model.fold(f"{written} {modern}"), written, modern, book, anchor, role, unread]
            for written, modern, book, anchor, role, unread in PEOPLE]
    return {"books": BOOKS, "rows": rows}


def _expected(query: str) -> list[str]:
    """What the search should list for `query`, worked out in Python: every word inside a row, those that begin a
    word of it first."""
    words = model.fold(query).split()
    first, rest = [], []
    for row in _index()["rows"]:
        if all(word in row[0] for word in words):
            (first if all(" " + word in " " + row[0] for word in words) else rest).append(row[1])
    return first + rest


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory, file_node: dict[str, Any]) -> Iterator[str]:
    """The fixture's site with the test's index, served on a port of its own; the address of its search page."""
    out = tmp_path_factory.mktemp("search") / "site"
    _build(file_node, out)
    (out / "search" / "index.json").write_text(json.dumps(_index(), ensure_ascii=False), encoding="utf-8")
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


def _search(page: str, query: str, tmp_path: Path) -> tuple[str, list[tuple[str, str]]]:
    """The search page after the browser ran `query`: its status line and each result's (link, text)."""
    chrome = _chrome()
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("no Chrome on a CI runner: the search's browser test cannot run")
        pytest.skip("no Chrome here")
    assert chrome is not None
    profile = tempfile.mkdtemp(prefix="chrome-", dir=tmp_path)     # a profile a run: no lock left by the last
    ran = subprocess.run(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={profile}", "--virtual-time-budget=10000", "--dump-dom", f"{page}?q={quote(query)}"],
        capture_output=True, text=True, timeout=120, check=False)
    assert ran.returncode == 0, f"Chrome exited {ran.returncode}: {ran.stderr[-2000:]}"
    dom = ran.stdout
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
