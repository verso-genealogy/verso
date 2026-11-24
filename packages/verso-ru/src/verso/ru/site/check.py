"""A built site judged as a reader's browser meets it: every link inside it leads to a page that is
there and to an anchor that page holds, no page holds one id twice, and nothing is fetched from
another host — a stylesheet, a script, an image.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

INDEX = "index.html"
# The attributes whose address a browser fetches without being asked.
_FETCHED = {("link", "href"), ("script", "src"), ("img", "src"), ("iframe", "src"), ("source", "src"),
            ("video", "src"), ("audio", "src"), ("object", "data"), ("embed", "src")}


@dataclass(frozen=True)
class Problem:
    page: str
    what: str            # `broken_link`, `broken_anchor`, `duplicate_id`, `fetched`
    detail: str

    def __str__(self) -> str:
        return f"{self.page}: {self.what}: {self.detail}"


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[str] = []
        self.fetched: list[str] = []
        self.base: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        given = dict(attrs)
        if given.get("id"):
            self.ids.append(str(given["id"]))
        if tag == "base" and given.get("href"):
            self.base = str(given["href"])
        if tag in ("a", "form") and (target := given.get("href" if tag == "a" else "action")) is not None:
            self.links.append(target)
        if tag == "link" and "canonical" in str(given.get("rel") or "").split():
            return                       # an address the page states, which no browser fetches
        for (element, attribute) in _FETCHED:
            if tag == element and given.get(attribute):
                self.fetched.append(str(given[attribute]))


def _read(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def verify(out: Path) -> list[Problem]:
    """What is wrong with the site under `out`; empty when a reader meets no dead end."""
    out = out.resolve()
    pages = {path: _read(path) for path in sorted(out.rglob("*.html"))}
    problems: list[Problem] = []
    for path, page in pages.items():
        rel = path.relative_to(out).as_posix()
        seen: set[str] = set()
        for id_ in page.ids:
            if id_ in seen:
                problems.append(Problem(rel, "duplicate_id", id_))
            seen.add(id_)
        for address in page.fetched:
            if urlsplit(address).scheme or address.startswith("//"):
                problems.append(Problem(rel, "fetched", address))
        if page.base is not None:        # the page the host serves at any depth: its links are the host's
            continue
        for link in [*page.links, *(a for a in page.fetched if not urlsplit(a).scheme)]:
            parts = urlsplit(link)
            if parts.scheme or link.startswith("//"):
                continue
            target = path if not parts.path else (path.parent / unquote(parts.path)).resolve()
            if target.is_dir():
                target = target / INDEX
            if not target.is_file() or not target.is_relative_to(out):
                problems.append(Problem(rel, "broken_link", link))
            elif parts.fragment and target in pages and unquote(parts.fragment) not in pages[target].ids:
                problems.append(Problem(rel, "broken_anchor", link))
    return problems
