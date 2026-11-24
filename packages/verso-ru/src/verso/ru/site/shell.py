"""The frame every page stands in: the head, the menu, the search field, the footer — and the two
files a crawler reads.

Every link is relative to the page, so the site is served the same from a project's path on a host and
from a domain of its own. Nothing is fetched from another host.
"""
from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import quote

from verso.ru.messages import t

E = html.escape
CSS = "assets/site.css"
SEARCH_JS = "assets/search.js"
# The directories the site keeps for itself: no page of prose may take one.
RESERVED = frozenset({"assets", "books", "cards", "years", "names", "patronymics", "search", "about"})


@dataclass(frozen=True)
class Context:
    title: str                        # the site's name: the settlement's
    lang: str
    repo_url: str | None = None
    site_url: str | None = None       # with its final slash
    revision: str | None = None
    summary: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    prose: Sequence[tuple[str, str]] = ()      # the pages of prose: (path, title), the contents first


def root(path: str) -> str:
    """From a page's directory (`books/x/1900/birth/`, `` for the front page) back to the site's root."""
    return "../" * path.count("/")


def address(site_url: str, path: str) -> str:
    """A page's whole address: its path percent-encoded, as a sitemap and a canonical link spell it (a page of
    names is named in Cyrillic)."""
    return site_url + quote(path)


def page(title: str, body: str, *, ctx: Context, path: str, head: str = "", scripts: Iterable[str] = ()) -> str:
    """A whole page: `body` inside the frame, `path` its directory from the root."""
    up = root(path)
    name = E(ctx.title)
    full = name if not title else f"{E(title)} — {name}"
    canonical = f'<link rel="canonical" href="{E(address(ctx.site_url, path))}">' if ctx.site_url else ""
    about = f'<a href="{up}{E(ctx.prose[0][0])}">{E(str(t("site.nav.about")))}</a>' if ctx.prose else ""
    nav = (f'<a href="{up}years/">{E(str(t("site.nav.years")))}</a>'
           f'<a href="{up}books/">{E(str(t("site.nav.books")))}</a>'
           f'<a href="{up}names/">{E(str(t("site.nav.names")))}</a>{about}')
    search = (f'<form class="search" action="{up}search/" method="get" role="search">'
              f'<input type="search" name="q" aria-label="{E(str(t("site.search.label")))}" '
              f'placeholder="{E(str(t("site.search.placeholder")))}">'
              f'<button type="submit">{E(str(t("site.search.go")))}</button></form>')
    tail = "".join(f'<script src="{up}{E(src)}" defer></script>' for src in scripts)
    return (f'<!doctype html>\n<html lang="{E(ctx.lang)}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{full}</title>\n<link rel="stylesheet" href="{up}{CSS}">\n{canonical}{head}</head>\n'
            f'<body>\n<header class="top"><a class="brand" href="{up or "./"}">{name}</a>'
            f'<nav aria-label="{E(str(t("site.nav.label")))}">{nav}</nav>{search}</header>\n<main>\n{body}\n</main>\n{_footer(ctx, up)}{tail}\n</body>\n</html>\n')


def _footer(ctx: Context, up: str) -> str:
    parts = [f'<p class="legend"><span class="w">{E(str(t("site.legend.written_word")))}</span> — '
             f'{E(str(t("site.legend.written")))}; <span class="d">{E(str(t("site.legend.derived_word")))}</span> — '
             f'{E(str(t("site.legend.derived")))}; <span class="badge">{E(str(t("site.unreviewed")))}</span> — '
             f'{E(str(t("site.legend.unreviewed")))}</p>']
    line: list[str] = []
    if ctx.license_name:
        name = E(ctx.license_name)
        line.append(str(t("site.footer.license")) + " " + (
            f'<a href="{E(ctx.license_url)}" rel="license noopener">{name}</a>' if ctx.license_url else name))
    if ctx.repo_url:
        line.append(f'<a href="{E(ctx.repo_url)}" rel="noopener">{E(str(t("site.footer.repo")))}</a>')
    if ctx.revision:
        line.append(E(str(t("site.footer.revision", revision=ctx.revision))))
    line.append(f'<a href="{up}search/">{E(str(t("site.nav.search")))}</a>')
    parts.append(f'<p>{" · ".join(line)}</p>')
    return f'<footer class="bottom">{"".join(parts)}</footer>\n'


def robots(ctx: Context) -> str:
    sitemap = f"Sitemap: {ctx.site_url}sitemap.xml\n" if ctx.site_url else ""
    return f"User-agent: *\nAllow: /\n{sitemap}"


def sitemap(ctx: Context, paths: Iterable[str]) -> str:
    """Every page's address, in the order given; asked only of a site that knows its own."""
    assert ctx.site_url is not None
    urls = "".join(f"<url><loc>{E(address(ctx.site_url, path))}</loc></url>\n" for path in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n')
