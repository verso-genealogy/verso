"""A built site judged as a reader's browser meets it: every link inside it leads to a page that is
there and to an anchor that page holds, no page holds one id twice, and nothing is fetched from
another host — a stylesheet, a script, an image.

It reads the tree once and every page once: each page's start tags only (one pattern, as `html.parser` reads
them: a comment, a declaration and the text of a script or a style hold none), every address against the set of
the tree's files and directories, every anchor against a set of its page's ids. A site of thousands of pages and a
hundred thousand links is checked in a few seconds, its time the size of the site.
"""
from __future__ import annotations

import html
import os
import posixpath
import re
from dataclasses import dataclass, field
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


# A start tag, a comment or a declaration; `</script>` and `</style>` end the text a script or a style holds.
_MARKUP = re.compile(r"<!--.*?(?:-->|\Z)|<[!?][^>]*>?|<([a-zA-Z][^\s/>]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
_ATTRIBUTE = re.compile(r"""([^\s/>"'=][^\s/>=]*)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]*))?""")
_RAW = {tag: re.compile(f"</{tag}", re.I) for tag in ("script", "style")}


@dataclass
class _Page:
    ids: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    base: str | None = None

    def start(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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


def _attributes(text: str) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    for match in _ATTRIBUTE.finditer(text):
        value = match.group(2)
        if value is not None and value[:1] in ("'", '"'):
            value = value[1:-1]
        found.append((match.group(1).lower(), None if value is None else html.unescape(value)))
    return found


def _scan(text: str) -> _Page:
    """A page's start tags, read as `html.parser` reads them (names lowered, references resolved)."""
    page = _Page()
    at = 0
    while (found := _MARKUP.search(text, at)) is not None:
        at = found.end()
        if found.group(1) is None:       # a comment or a declaration
            continue
        tag = found.group(1).lower()
        page.start(tag, _attributes(found.group(2)))
        if tag in _RAW:                  # its text is no markup: on to its end tag
            end = _RAW[tag].search(text, at)
            at = len(text) if end is None else end.start()
    return page


def _read(path: Path) -> _Page:
    return _scan(path.read_text(encoding="utf-8"))


def verify(out: Path) -> list[Problem]:
    """What is wrong with the site under `out`; empty when a reader meets no dead end."""
    out = out.resolve()
    files: set[str] = set()
    directories: set[str] = {"."}
    for folder, subfolders, names in os.walk(out):
        here = Path(folder).relative_to(out).as_posix()
        directories.update(posixpath.normpath(posixpath.join(here, name)) for name in subfolders)
        files.update(posixpath.normpath(posixpath.join(here, name)) for name in names)
    pages = {rel: _read(out / rel) for rel in sorted(files) if rel.endswith(".html")}
    ids = {rel: set(page.ids) for rel, page in pages.items()}
    problems: list[Problem] = []
    for rel, page in pages.items():
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
        here = posixpath.dirname(rel)
        for link in [*page.links, *(a for a in page.fetched if not urlsplit(a).scheme)]:
            parts = urlsplit(link)
            if parts.scheme or link.startswith("//"):
                continue
            target = rel if not parts.path else posixpath.normpath(posixpath.join(here, unquote(parts.path)))
            if target in directories:
                target = posixpath.normpath(posixpath.join(target, INDEX))
            if target not in files:      # outside the tree too: `..`, or an address from the host's root
                problems.append(Problem(rel, "broken_link", link))
            elif parts.fragment and target in ids and unquote(parts.fragment) not in ids[target]:
                problems.append(Problem(rel, "broken_anchor", link))
    return problems
