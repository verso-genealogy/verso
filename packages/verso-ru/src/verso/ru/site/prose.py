"""The settlement's prose — `<village>/docs/*.md` — as pages of the site.

`README.md` is the contents (`about/`); every other file is a page under its own name
(`history.md` → `history/`), in the order the contents links them, the rest by name. A link to
another page of the prose leads to that page; a link to a DSL file leads to its book on the site;
any other link into the workspace leads to the repository, and is refused where the site knows no
repository. A link out of the workspace is refused. Raw HTML in the text is shown as text.
Markdown is read by markdown-it-py — the extra `verso-ru[site]`, imported only when there is prose.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from verso.ru.messages import t
from verso.ru.site import shell
from verso.ru.site.errors import SiteError
from verso.ru.site.model import Site
from verso.ru.site.shell import Context

CONTENTS = "README.md"
ABOUT = "about/"
BRANCH = "main"


class ProseError(SiteError):
    """Prose the site cannot show: a link that leads nowhere it may, a page named as a directory of
    the site, Markdown with no reader installed."""


class MissingExtra(ProseError):
    """There is prose and no markdown-it-py: install `verso-ru[site]`."""


@dataclass(frozen=True)
class Page:
    path: str            # its directory on the site, with the final slash
    title: str
    source: Path


def _path(source: Path) -> str:
    return ABOUT if source.name == CONTENTS else f"{source.stem}/"


def _linked(text: str) -> list[str]:
    return [unquote(urlsplit(target).path) for target in re.findall(r"\]\(([^)\s]+)", text)]


_STEM = re.compile(r"[\w-]+")


def order(docs: Path) -> list[Path]:
    """The pages of `docs`: the contents first, then as the contents links them, then by name. A file that is
    a link to another, and a name that is not letters, digits, `_` and `-`, are refused: a page is a file of
    the prose itself, named as an address spells it."""
    files = {path.name: path for path in sorted(docs.glob("*.md"))}
    for name, path in files.items():
        if path.is_symlink():
            raise ProseError(str(t("site.prose.symlink", file=name)))
        if not _STEM.fullmatch(path.stem):
            raise ProseError(str(t("site.prose.name", file=name)))
    out: list[Path] = []
    if CONTENTS in files:
        out.append(files[CONTENTS])
        for name in _linked(files[CONTENTS].read_text(encoding="utf-8")):
            if name in files and files[name] not in out:
                out.append(files[name])
    return out + [path for path in files.values() if path not in out]


def heading_slug(text: str) -> str:
    """A heading's id as GitHub makes it of the heading's text: lower case, everything but letters, digits,
    `_`, `-` and spaces dropped, each space a hyphen — so a link to a section reads the same in the repository
    and on the site. A heading met again on its page is numbered there (`-1`, `-2`: `_number`)."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _plain(inline: Any) -> str:
    """The text a heading shows: its words without the markup, a link by its words."""
    return "".join(child.content for child in inline.children or () if child.type in ("text", "code_inline"))


def _number(tokens: list[Any]) -> None:
    """An id on every heading, GitHub's: the slug of its text, a repeat numbered from 1 — and numbered on, where
    that number is a heading's own slug already («B», «B», «b-1» are `b`, `b-1`, `b-1-1`). A heading with no
    letter or digit gets none."""
    seen: dict[str, int] = {}
    for place, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        slug = heading_slug(_plain(tokens[place + 1]))
        if not slug:
            continue
        unique = slug
        while unique in seen:
            seen[slug] += 1
            unique = f"{slug}-{seen[slug]}"
        seen[unique] = 0
        token.attrSet("id", unique)


def _title(tokens: list[Any], fallback: str) -> str:
    for place, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h1":
            return _plain(tokens[place + 1]) or fallback
    return fallback


def _reader() -> Any:
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise MissingExtra(str(t("site.prose.missing_extra"))) from exc
    return MarkdownIt("commonmark", {"html": False}).enable("table")


class _Links:
    """Where a relative link of a page of prose leads on the site."""

    def __init__(self, docs: Path, site: Site, ctx: Context, workspace: Path) -> None:
        self.docs = docs.resolve()
        self.ctx = ctx
        self.workspace = workspace.resolve()
        self.pages = {path.resolve(): _path(path) for path in docs.glob("*.md")}
        village = self.docs.parent
        self.books: dict[Path, str] = {}
        for book in site.books:              # a file of several books leads to its first
            for file in book.files:
                self.books.setdefault((village / file).resolve(), book.path)

    def rewrite(self, href: str, source: Path, up: str) -> str:
        parts = urlsplit(href)
        if parts.scheme or href.startswith(("//", "#")):
            return href
        where = f"{source.name}: {href}"
        try:
            target = (source.parent / unquote(parts.path)).resolve()
        except (ValueError, OSError):            # a path no file system takes (a NUL in it)
            raise ProseError(str(t("site.prose.link_dead", link=where))) from None
        fragment = f"#{quote(unquote(parts.fragment))}" if parts.fragment else ""
        if target in self.pages:
            return up + self.pages[target] + fragment
        if target in self.books:
            return up + self.books[target]
        if not target.is_relative_to(self.workspace):
            raise ProseError(str(t("site.prose.link_outside", link=where)))
        if not target.exists():
            raise ProseError(str(t("site.prose.link_dead", link=where)))
        if not self.ctx.repo_url:
            raise ProseError(str(t("site.prose.link_needs_repo", link=where)))
        repo = self.ctx.repo_url.rstrip("/")
        parts_ = target.relative_to(self.workspace).parts
        if not parts_:                           # the workspace itself: the repository's front page
            return repo + fragment
        kind = "tree" if target.is_dir() else "blob"
        return f"{repo}/{kind}/{BRANCH}/{quote(posixpath.join(*parts_))}{fragment}"


def listed(docs: Path | None) -> list[Page]:
    """The pages the prose makes, with their titles: what the menu and the front page name."""
    if docs is None or not docs.is_dir():
        return []
    found = order(docs)
    if not found:
        return []
    reader = _reader()
    pages: list[Page] = []
    for source in found:
        path = _path(source)
        # By the name a file system that tells no case apart would give the page («Books.md» is `books/`).
        stem = path.rstrip("/").casefold()
        if stem in shell.RESERVED - {"about"} or (stem == "about" and source.name != CONTENTS):
            raise ProseError(str(t("site.prose.reserved", file=source.name)))
        tokens = reader.parse(source.read_text(encoding="utf-8"))
        fallback = str(t("site.nav.about")) if source.name == CONTENTS else source.stem
        pages.append(Page(path, _title(tokens, fallback), source))
    return pages


def render(page: Page, docs: Path, site: Site, ctx: Context, workspace: Path) -> str:
    """One page of prose, whole."""
    reader = _reader()
    links = _Links(docs, site, ctx, workspace)
    up = shell.root(page.path)
    tokens = reader.parse(page.source.read_text(encoding="utf-8"))
    _number(tokens)
    for token in tokens:
        for child in token.children or ():
            if child.type == "link_open":
                child.attrSet("href", links.rewrite(str(child.attrGet("href") or ""), page.source, up))
            elif child.type == "image":
                raise ProseError(str(t("site.prose.image", file=page.source.name)))
    body = f'<article class="prose">{reader.renderer.render(tokens, reader.options, {})}</article>'
    return shell.page(page.title, body, ctx=ctx, path=page.path)


def first_paragraph(docs: Path | None) -> str | None:
    """The opening paragraph of `history.md`, plain: the settlement's summary where none is given."""
    if docs is None or not (docs / "history.md").is_file():
        return None
    reader = _reader()
    tokens = reader.parse((docs / "history.md").read_text(encoding="utf-8"))
    for place, token in enumerate(tokens):
        if token.type == "paragraph_open":
            inline = tokens[place + 1]
            return "".join(child.content for child in inline.children or ()
                           if child.type in ("text", "code_inline", "softbreak")).strip() or None
    return None
