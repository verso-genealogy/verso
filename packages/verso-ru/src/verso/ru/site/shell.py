"""The frame every page stands in: the head, the menu, the search field, the theme button, the footer — and the two
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
THEME_JS = "assets/theme.js"
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


# The head's id: no heading's, as GitHub's slug drops the dot (a prose page's «Top» is `top`).
TOP = "page.top"


def page(title: str, body: str, *, ctx: Context, path: str, head: str = "", scripts: Iterable[str] = (),
         top: bool = True) -> str:
    """A whole page: `body` inside the frame, `path` its directory from the root; `top=False` leaves out the
    footer's way back to the head (a page with a `<base>`, where «#…» leads to the base)."""
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
    theme = _theme_button()
    return (f'<!doctype html>\n<html lang="{E(ctx.lang)}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{full}</title>\n<link rel="stylesheet" href="{up}{CSS}">\n'
            f'<script src="{up}{THEME_JS}"></script>\n{canonical}{head}</head>\n'
            f'<body>\n<header class="top" id="{TOP}"><a class="brand" href="{up or "./"}">{name}</a>'
            f'<nav aria-label="{E(str(t("site.nav.label")))}">{nav}</nav>{search}{theme}</header>\n<main>\n{body}\n</main>\n{_footer(ctx, up, top)}{tail}\n</body>\n</html>\n')


# The three marks of the theme button: the system's (half a disc), light (a sun), dark (a crescent).
_THEME_MARKS = (
    ("auto", '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>'),
    ("light", '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8'
              'M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>'),
    ("dark", '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>'),
)


def _theme_button() -> str:
    """The bar's theme button: hidden until `theme.js` wires it, so a page without scripts shows no dead control.
    Each mode's label rides in a `data-` attribute; the script shows the one in force."""
    said = {"auto": t("site.theme.auto"), "light": t("site.theme.light"), "dark": t("site.theme.dark")}
    labels = "".join(f' data-{mode}="{E(str(said[mode]))}"' for mode, _ in _THEME_MARKS)
    marks = "".join(f'<svg class="i-{mode}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{body}</svg>'
                    for mode, body in _THEME_MARKS)
    return (f'<button type="button" class="theme" id="theme" hidden data-mode="auto"{labels} '
            f'aria-label="{E(str(said["auto"]))}">{marks}</button>')


def _footer(ctx: Context, up: str, top: bool) -> str:
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
    if top:                                                          # a long book's foot, back to its head
        line.append(f'<a href="#{TOP}">{E(str(t("site.footer.top")))}</a>')
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
