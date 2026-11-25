"""A village's records as a static site (`verso site`): the books as the documents they are read
from, record by record, an index of the names and a search — plain files any host of static pages
serves, at any path.

`build` draws records v1 (`verso.core.records`), by the interface's schema (`ui-v1`); it knows no
DSL. The guide: `docs/site.md`.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.resources import files as resources
from pathlib import Path
from typing import Any

from verso.core import i18n
from verso.core.records import ui as ui_schema
from verso.ru.messages import t
from verso.ru.site import check, model, pages, prose, shell
from verso.ru.site.errors import SiteError
from verso.ru.site.records import Ui
from verso.ru.site.shell import RESERVED, Context

# The library's own files, under assets/: the stylesheet, the search, the theme, and the fonts the stylesheet draws with,
# each beside its licence (SIL OFL 1.1; NOTICE names them).
FONTS = ("onest.woff2", "cormorant-garamond-italic.woff2", "jetbrains-mono.woff2", "noto-sans-old.woff2",
         "OFL-Onest.txt", "OFL-CormorantGaramond.txt", "OFL-JetBrainsMono.txt", "OFL-NotoSans.txt")
ASSETS = ("site.css", "search.js", "theme.js", *(f"fonts/{name}" for name in FONTS))
__all__ = ["RESERVED", "BuildError", "Built", "SiteError", "build"]


class BuildError(SiteError):
    """A site that cannot be built where it was asked."""


@dataclass(frozen=True)
class Built:
    out: Path
    pages: int
    bytes: int
    books: int
    records: int
    unreviewed: int
    problems: tuple[check.Problem, ...]


def build(files: Iterable[Mapping[str, Any]], *, out: Path, village: str, title: str | None = None,
          lang: str | None = None, docs: Path | None = None, workspace: Path | None = None,
          repo_url: str | None = None, site_url: str | None = None, revision: str | None = None,
          summary: str | None = None, license_name: str | None = None, license_url: str | None = None) -> Built:
    """The site of `files` — records-v1 file nodes of one village — written under `out`, which is new
    or empty. The same input makes the same bytes: nothing of the hour or the machine is written."""
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise BuildError(str(t("site.build.out_not_empty", out=out)))
    for address in (repo_url, site_url, license_url):
        if address and not address.startswith(("https://", "http://")):
            raise BuildError(str(t("site.build.bad_url", url=address)))
    if site_url and not site_url.endswith("/"):
        site_url += "/"
    with i18n.use(lang) if lang else nullcontext():
        return _build(model.load(files, village=village), out, Context(
            title=title or village, lang=lang or i18n.language(), repo_url=repo_url, site_url=site_url,
            revision=revision, summary=summary, license_name=license_name, license_url=license_url), docs,
            workspace)


def _build(site: model.Site, out: Path, ctx: Context, docs: Path | None, workspace: Path | None) -> Built:
    ui = Ui(ui_schema.load_ui())
    prose_pages = prose.listed(docs)
    ctx = Context(**{**ctx.__dict__, "prose": tuple((page.path, page.title) for page in prose_pages),
                     "summary": ctx.summary or (prose.first_paragraph(docs) if prose_pages else None)})
    written: dict[str, str] = {}
    taken: dict[str, str] = {}

    def page(path: str, text: str) -> None:
        """One page, at a path no other page has — nor would have where a file system tells no case apart."""
        key = path.casefold()
        if key in taken:
            raise BuildError(str(t("site.build.two_pages", first=taken[key] or "/", second=path or "/")))
        taken[key] = path
        written[path + check.INDEX] = text

    page("", pages.front(site, ctx))
    page("books/", pages.books_index(site, ui, ctx))
    page("years/", pages.years_index(site, ui, ctx))
    for year in site.years:
        page(f"years/{year}/", pages.year(year, site, ui, ctx))
    for book in site.books:
        page(book.path, pages.book(book, ui, ctx))
    page(f"{pages.NAMES}/", pages.names_index(site, ctx))
    for found in pages.surname_pages(site):
        page(f"{pages.NAMES}/{found.key}/", pages.name(found, pages.NAMES, site, ui, ctx))
    patronymics = pages.patronymic_pages(site)
    if patronymics:
        page(f"{pages.PATRONYMICS}/", pages.patronymics_index(site, ctx))
        for found in patronymics:
            page(f"{pages.PATRONYMICS}/{found.key}/", pages.name(found, pages.PATRONYMICS, site, ui, ctx))
    if pages.nameless(site):
        page(f"{pages.PATRONYMICS}/{pages.NAMELESS}/", pages.nameless_page(site, ui, ctx))
    page("search/", pages.search(ctx))
    for prose_page in prose_pages:
        assert docs is not None
        page(prose_page.path, prose.render(prose_page, docs, site, ctx, workspace or docs.parent.parent))
    listed = sorted(path.removesuffix(check.INDEX) for path in written)
    written["404.html"] = pages.not_found(ctx)
    written["search/index.json"] = pages.search_index(site, ui)
    written["robots.txt"] = shell.robots(ctx)
    if ctx.site_url:
        written["sitemap.xml"] = shell.sitemap(ctx, listed)
    total = 0
    for rel, text in written.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        target.write_bytes(data)
        total += len(data)
    assets = resources("verso.ru.site").joinpath("assets")
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        data = assets.joinpath(*name.split("/")).read_bytes()
        (out / "assets" / name).parent.mkdir(parents=True, exist_ok=True)
        (out / "assets" / name).write_bytes(data)
        total += len(data)
    return Built(out, len(listed), total, len(site.books), site.records, site.unreviewed, tuple(check.verify(out)))
