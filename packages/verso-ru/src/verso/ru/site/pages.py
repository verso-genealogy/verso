"""The site's pages: the front page, a book with its records, the indexes of books, of years and of
names, the search page and its index.

Each function returns the page whole (`shell.page`). The pages of names list mentions — a persona of
a record — never persons: the site folds nobody together.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from verso.ru.messages import t
from verso.ru.site import model, records, shell, urls
from verso.ru.site.model import Book, Mention, Site
from verso.ru.site.records import Ui
from verso.ru.site.shell import Context

E = html.escape
NAMES = "names"
PATRONYMICS = "patronymics"
NAMELESS = "-"          # the page of those written with neither a surname nor a patronymic
SEARCH_LIMIT = 200


# ---------------------------------------------------------------- titles and counts

def kind_title(book: Book, ui: Ui) -> str:
    """«Рождения», «Ревизия», «Исповедная роспись», «Список избирателей», «Карточки: судимость»."""
    if book.is_cards:
        return str(t("site.book.cards", kind=ui.enum("external_source_kind", book.kind)))
    header = {"written": book.written, "derived": book.docs[0].get("derived") or {}}
    named = records.value(header, "document_type") or (
        records.value(header, "record_type") if book.set_kind == "census" else None)
    title = str(named[0]) if named else ui.label(f"ui.set.{book.set_kind}.plural")
    title = title[:1].upper() + title[1:]
    return str(t("site.book.civil", title=title)) if book.civil else title


def book_title(book: Book, ui: Ui) -> str:
    """A book's name in a list and at its page's head: its kind, year and parish."""
    year = f" {book.year}" if book.year is not None else ""
    return f"{kind_title(book, ui)}{year} — {book.village}"


def _records(count: int) -> str:
    return str(t("counted.records", count=count))


def _unreviewed(count: int) -> str:
    return f' <span class="badge">{E(str(t("site.unreviewed_count", count=count)))}</span>' if count else ""


# ---------------------------------------------------------------- a book

def _shelf(book: Book) -> str:
    return str(t("site.book.cards_source")) if book.is_cards else records.shelfmark({}, book)


def _defaults(book: Book, ui: Ui) -> str:
    fills = {fill["field"]: fill for fill in ui.schema["books"].get(book.set_kind, {}).get("fills", ())}
    parts: list[str] = []
    for key, found in (book.written.get("defaults") or {}).items():
        shown = found.get("text") if isinstance(found, Mapping) else found
        if shown and key in fills:
            parts.append(f"{E(ui.label(fills[key]['label']))} — {E(str(shown))}")
    return "; ".join(dict.fromkeys(parts))


def book(book_: Book, ui: Ui, ctx: Context) -> str:
    up = shell.root(book_.path)
    facts = [E(_shelf(book_))]
    if not book_.is_cards:
        church = book_.church
        facts.append(E(str(t("site.book.parish", village=book_.village)) + (f", {church}" if church else "")))
        if defaults := _defaults(book_, ui):
            facts.append(E(str(t("site.book.defaults"))) + " " + defaults)
        if book_.civil:
            facts.append(E(str(t("site.book.civil_note"))))
    count = f"{E(_records(len(book_.entries)))}{_unreviewed(book_.unreviewed)}"
    leaves = list(dict.fromkeys(entry.leaf for entry in book_.entries if entry.leaf and entry.leaf != "?"))
    toc = ""
    if len(leaves) > 1:
        first = {leaf: next(e for e in book_.entries if e.leaf == leaf) for leaf in leaves}
        toc = (f'<nav class="leaves"><span class="k">{E(str(t("site.book.leaves")))}:</span> '
               + " ".join(f'<a href="#{urls.fragment(first[leaf].anchor)}">{E(leaf)}</a>' for leaf in leaves)
               + "</nav>")
    crumbs = (f'<p class="crumbs"><a href="{up}books/">{E(str(t("site.nav.books")))}</a>'
              + (f' · <a href="{up}years/{book_.year}/">{book_.year}</a>' if book_.year is not None else "")
              + "</p>")
    body = (f'{crumbs}<h1>{E(book_title(book_, ui))}</h1><ul class="facts">'
            + "".join(f"<li>{fact}</li>" for fact in facts) + f"<li>{count}</li></ul>{toc}"
            + "".join(records.render(entry, book_, ui) for entry in book_.entries))
    return shell.page(book_title(book_, ui), body, ctx=ctx, path=book_.path)


# ---------------------------------------------------------------- the indexes of books and of years

def _book_link(book_: Book, ui: Ui, up: str, text_: str | None = None) -> str:
    return f'<a href="{up}{E(book_.path)}">{E(text_ or book_title(book_, ui))}</a>'


def books_index(site: Site, ui: Ui, ctx: Context) -> str:
    """The books by archive, then fund and inventory, then case: what a researcher asks an archive for."""
    path = f"{urls.BOOKS}/"
    up = shell.root(path)
    groups: dict[tuple[str, str], list[Book]] = {}
    for book_ in site.books:
        shelf = book_.shelf
        if book_.is_cards:
            key = (str(t("site.book.cards_source")), "")
        elif any(part in ("", "?") for part in shelf.values()):
            key = (shelf["archive"].replace("?", "") or str(t("site.cite.unknown")), str(t("site.cite.unknown")))
        else:
            key = (shelf["archive"], str(t("site.book.fund", fund=shelf["fund"], inventory=shelf["inventory"])))
        groups.setdefault(key, []).append(book_)
    out = [f'<h1>{E(str(t("site.nav.books")))}</h1>']
    archive = None
    # Archive by archive, a fund's number as a number («ф. 47» before «ф. 1978»), the cards last.
    for (name, fund), found in sorted(groups.items(), key=lambda kv: (kv[1][0].is_cards, kv[0][0], _natural(kv[0][1]))):
        if name != archive:
            out.append(f"<h2>{E(name)}</h2>")
            archive = name
        rows = "".join(
            f"<tr><td>{E(book_.shelf['case']) if not book_.is_cards else ''}</td>"
            f"<td>{book_.year if book_.year is not None else ''}</td><td>{_book_link(book_, ui, up, kind_title(book_, ui))}</td>"
            f"<td>{E(book_.village)}</td><td class=\"n\">{len(book_.entries)}{_unreviewed(book_.unreviewed)}</td></tr>"
            for book_ in sorted(found, key=lambda b: (_natural(b.shelf["case"]), b.year or 0,
                                                      site.books.index(b))))
        head = "".join(f"<th>{E(str(label))}</th>" for label in (
            t("site.col.case"), t("site.col.year"), t("site.col.kind"), t("site.col.parish"), t("site.col.records")))
        out.append((f"<h3>{E(fund)}</h3>" if fund else "") +
                   f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')
    return shell.page(str(t("site.nav.books")), "".join(out), ctx=ctx, path=path)


def _natural(text_: str) -> list[Any]:
    return [(0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", text_) if part]


def years_index(site: Site, ui: Ui, ctx: Context) -> str:
    path = "years/"
    up = shell.root(path)
    rows: list[str] = []
    for year in site.years:
        found = [b for b in site.books if b.year == year]
        links = ", ".join(_book_link(b, ui, up, kind_title(b, ui)) for b in found)
        total = sum(len(b.entries) for b in found)
        rows.append(f'<tr><td><a href="{year}/">{year}</a></td><td>{links}</td><td class="n">{total}</td></tr>')
    undated = [b for b in site.books if b.year is None]
    tail = ""
    if undated:
        tail = (f'<h2>{E(str(t("site.years.undated")))}</h2><ul>'
                + "".join(f"<li>{_book_link(b, ui, up)}</li>" for b in undated) + "</ul>")
    head = "".join(f"<th>{E(str(label))}</th>" for label in (
        t("site.col.year"), t("site.nav.books"), t("site.col.records")))
    body = (f'<h1>{E(str(t("site.nav.years")))}</h1><div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>{tail}')
    return shell.page(str(t("site.nav.years")), body, ctx=ctx, path=path)


def year(year_: int, site: Site, ui: Ui, ctx: Context) -> str:
    path = f"years/{year_}/"
    up = shell.root(path)
    years = site.years
    place = years.index(year_)
    around = []
    if place:
        around.append(f'<a href="../{years[place - 1]}/">← {years[place - 1]}</a>')
    if place + 1 < len(years):
        around.append(f'<a href="../{years[place + 1]}/">{years[place + 1]} →</a>')
    items = "".join(
        f"<li>{_book_link(b, ui, up)} — {E(_shelf(b))} · {E(_records(len(b.entries)))}{_unreviewed(b.unreviewed)}</li>"
        for b in site.books if b.year == year_)
    body = (f'<p class="crumbs"><a href="../">{E(str(t("site.nav.years")))}</a></p><h1>{year_}</h1>'
            f'<ul class="books">{items}</ul><p class="around">{" · ".join(around)}</p>')
    return shell.page(str(year_), body, ctx=ctx, path=path)


# ---------------------------------------------------------------- names

@dataclass(frozen=True)
class NamePage:
    key: str                              # the directory's name
    title: str                            # «Сидоров, Сидорова»
    mentions: tuple[Mention, ...]


def _key(text_: str) -> str:
    return unicodedata.normalize("NFC", text_).lower().replace("ё", "е")  # i18n: content


def _directory(title: str) -> str:
    """A name as its page's directory: letters, digits and hyphens, no longer than a file system takes."""
    return re.sub(r"[^\w-]+", "-", title).strip("-")[:80] or NAMELESS


def _fold_feminine(keys: Iterable[str]) -> dict[str, str]:
    """Each key's page: a feminine form stands with its masculine one where the corpus has both
    («Сидорова» with «Сидоров», «Выдуманская» with «Выдуманский»)."""
    known = set(keys)
    out: dict[str, str] = {}
    for key in known:
        base = key
        if key.endswith("ая"):  # i18n: content
            base = next((key[:-2] + end for end in ("ий", "ой", "ый") if key[:-2] + end in known), key)  # i18n: content
        elif key.endswith("а") and key[:-1] in known:  # i18n: content
            base = key[:-1]
        out[key] = base
    return out


def _name_pages(mentions: Iterable[tuple[str, Mention]]) -> list[NamePage]:
    """The pages of an index of names; each lists its mentions in the site's order — by year, book, record."""
    by_key: dict[str, list[tuple[int, str, Mention]]] = {}
    for place, (name, mention) in enumerate(mentions):
        by_key.setdefault(_key(name), []).append((place, name, mention))
    base = _fold_feminine(by_key)
    grouped: dict[str, list[tuple[int, str, Mention]]] = {}
    for key in sorted(by_key):
        directory = _directory(base[key][:1].upper() + base[key][1:])
        grouped.setdefault(directory, []).extend(by_key[key])     # two names one directory holds: one page
    pages: list[NamePage] = []
    for directory in sorted(grouped, key=_key):
        found = sorted(grouped[directory], key=lambda each: each[0])
        first = _key(directory)
        spellings = sorted({_key(name) for _, name, _ in found}, key=lambda each: (each != first, each))
        title = ", ".join(each[:1].upper() + each[1:] for each in spellings)
        pages.append(NamePage(directory, title, tuple(mention for _, _, mention in found)))
    return pages


def surname_pages(site: Site) -> list[NamePage]:
    return _name_pages((m.surname, m) for m in site.mentions if m.surname)


def patronymic_pages(site: Site) -> list[NamePage]:
    """Those the source writes with no surname, by the patronymic in the book's form."""
    return _name_pages((m.patronymic, m) for m in site.mentions if not m.surname and m.patronymic)


def nameless(site: Site) -> tuple[Mention, ...]:
    found = [m for m in site.mentions if not m.surname and not m.patronymic]
    return tuple(sorted(found, key=lambda m: _key(m.given or m.as_written)))


def role_label(mention: Mention, ui: Ui) -> str:
    """Who the persona is in its record: the slot's name, a relative's kinship, a member's place."""
    kind = ui.kind(str(mention.entry.node.get("kind")))
    link = mention.persona.get("link") or {}
    if (relation := records.value(link, "relationship")) is not None:
        ref = records.value(link, "relationship_ref")
        return ui.enum("relationship", relation[0]) + (f" {ref[0]}" if ref else "")
    if (role := records.value(link, "role")) is not None:
        return ui.enum("census_role", role[0])
    for slot in kind["slots"]:
        if slot["role"] == mention.role:
            return ui.label(slot["label"])
    return mention.role


def _mention_rows(mentions: Sequence[Mention], site: Site, ui: Ui, up: str) -> str:
    books = {b.id: b for b in site.books}
    rows: list[str] = []
    for mention in mentions:
        book_ = books[mention.entry.book_id]
        href = f"{up}{E(book_.path)}#{urls.fragment(mention.entry.anchor)}"
        modern = (f' <span class="modern d">{E(mention.modern)}</span>'
                  if mention.modern and model.fold(mention.modern) != model.fold(mention.as_written) else "")
        badge = f' <span class="badge">{E(str(t("site.unreviewed")))}</span>' if mention.entry.unreviewed else ""
        rows.append(f'<tr><td>{book_.year if book_.year is not None else ""}</td>'
                    f'<td><a href="{href}">{E(mention.as_written)}</a>{modern}{badge}</td>'
                    f"<td>{E(role_label(mention, ui))}</td><td>{E(kind_title(book_, ui))}, {E(book_.village)}</td></tr>")
    head = "".join(f"<th>{E(str(label))}</th>" for label in (
        t("site.col.year"), t("site.col.name"), t("site.col.relation"), t("site.col.book")))
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def name(page_: NamePage, section: str, site: Site, ui: Ui, ctx: Context) -> str:
    path = f"{section}/{page_.key}/"
    up = shell.root(path)
    back = t("site.nav.names") if section == NAMES else t("site.names.patronymics")
    body = (f'<p class="crumbs"><a href="../">{E(str(back))}</a></p><h1>{E(page_.title)}</h1>'
            f'<p class="k">{E(str(t("site.names.mentions", count=len(page_.mentions))))}</p>'
            + _mention_rows(page_.mentions, site, ui, up))
    return shell.page(page_.title, body, ctx=ctx, path=path)


def _letters(pages_: Sequence[NamePage]) -> str:
    by_letter: dict[str, list[NamePage]] = {}
    for page_ in pages_:
        by_letter.setdefault(page_.title[:1].upper(), []).append(page_)
    jump = " ".join(f'<a href="#{E(letter)}">{E(letter)}</a>' for letter in by_letter)
    blocks = "".join(
        f'<h2 id="{E(letter)}">{E(letter)}</h2><ul class="names">' + "".join(
            f'<li><a href="{E(page_.key)}/">{E(page_.title)}</a> <span class="n">{len(page_.mentions)}</span></li>'
            for page_ in found) + "</ul>"
        for letter, found in by_letter.items())
    return f'<nav class="letters">{jump}</nav>{blocks}'


def names_index(site: Site, ctx: Context) -> str:
    path = f"{NAMES}/"
    surnames = surname_pages(site)
    others: list[str] = []
    if patronymic_pages(site):
        others.append(f'<a href="../{PATRONYMICS}/">{E(str(t("site.names.patronymics")))}</a>')
    if nameless(site):
        others.append(f'<a href="../{PATRONYMICS}/{NAMELESS}/">{E(str(t("site.names.nameless")))}</a>')
    also = f'<p>{E(str(t("site.names.also")))} {", ".join(others)}.</p>' if others else ""
    body = (f'<h1>{E(str(t("site.names.surnames")))}</h1><p class="k">{E(str(t("site.names.what")))}</p>{also}'
            + _letters(surnames))
    return shell.page(str(t("site.names.surnames")), body, ctx=ctx, path=path)


def patronymics_index(site: Site, ctx: Context) -> str:
    path = f"{PATRONYMICS}/"
    body = (f'<p class="crumbs"><a href="../{NAMES}/">{E(str(t("site.nav.names")))}</a></p>'
            f'<h1>{E(str(t("site.names.patronymics")))}</h1><p class="k">{E(str(t("site.names.patronymics_what")))}</p>'
            + _letters(patronymic_pages(site)))
    return shell.page(str(t("site.names.patronymics")), body, ctx=ctx, path=path)


def nameless_page(site: Site, ui: Ui, ctx: Context) -> str:
    path = f"{PATRONYMICS}/{NAMELESS}/"
    body = (f'<p class="crumbs"><a href="../../{NAMES}/">{E(str(t("site.nav.names")))}</a></p>'
            f'<h1>{E(str(t("site.names.nameless")))}</h1>' + _mention_rows(nameless(site), site, ui, shell.root(path)))
    return shell.page(str(t("site.names.nameless")), body, ctx=ctx, path=path)


# ---------------------------------------------------------------- search

def search_index(site: Site, ui: Ui) -> str:
    """`search/index.json`: the books and, for each mention, what a query is compared with (the modern
    and the written forms folded), what is shown, where it leads, and 1 where its record is unread."""
    place = {book_.id: n for n, book_ in enumerate(site.books)}
    rows = [[model.fold(f"{m.modern} {m.as_written}"), m.as_written,
             m.modern if model.fold(m.modern) != model.fold(m.as_written) else "",
             place[m.entry.book_id], m.entry.anchor, role_label(m, ui), int(m.entry.unreviewed)]
            for m in site.mentions]
    data = {"books": [[b.path, book_title(b, ui)] for b in site.books], "rows": rows}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def search(ctx: Context) -> str:
    path = "search/"
    body = (f'<h1>{E(str(t("site.nav.search")))}</h1>'
            f'<form id="search" class="search wide" method="get" role="search">'
            f'<input type="search" name="q" id="q" autofocus aria-label="{E(str(t("site.search.label")))}" '
            f'placeholder="{E(str(t("site.search.placeholder")))}">'
            f'<button type="submit">{E(str(t("site.search.go")))}</button></form>'
            f'<p class="k">{E(str(t("site.search.hint")))}</p>'
            f'<noscript><p>{E(str(t("site.search.noscript")))} <a href="../{NAMES}/">{E(str(t("site.nav.names")))}</a>.</p></noscript>'
            f'<p id="status" role="status" data-loading="{E(str(t("site.search.loading")))}" '
            f'data-none="{E(str(t("site.search.none")))}" data-error="{E(str(t("site.search.error")))}" '
            f'data-found="{E(str(t("site.search.found", count="{count}")))}" '
            f'data-more="{E(str(t("site.search.more", limit="{limit}")))}" '
            f'data-unread="{E(str(t("site.unreviewed")))}" data-limit="{SEARCH_LIMIT}"></p><ol id="results" class="results"></ol>')
    return shell.page(str(t("site.nav.search")), body, ctx=ctx, path=path, scripts=(shell.SEARCH_JS,))


# ---------------------------------------------------------------- the front page and the missing one

def front(site: Site, ctx: Context) -> str:
    years = site.years
    span = f"{years[0]}–{years[-1]}" if len(years) > 1 else (str(years[0]) if years else "")
    stats = [str(t("site.front.books", count=len(site.books))), _records(site.records),
             str(t("site.front.mentions", count=len(site.mentions)))]
    if span:
        stats.append(str(t("site.front.years", span=span)))
    counted = "".join(f"<li>{E(each)}</li>" for each in stats)
    if site.unreviewed:
        counted += f'<li>{E(str(t("site.front.unreviewed", count=site.unreviewed)))}</li>'
    ways = [("years/", t("site.nav.years"), t("site.front.by_years")),
            ("books/", t("site.nav.books"), t("site.front.by_books")),
            (f"{NAMES}/", t("site.nav.names"), t("site.front.by_names")),
            ("search/", t("site.nav.search"), t("site.front.by_search"))]
    cards = "".join(f'<li><a href="{href}">{E(str(title))}</a><span>{E(str(what))}</span></li>'
                    for href, title, what in ways)
    prose = ""
    if ctx.prose:
        prose = (f'<h2>{E(str(t("site.nav.about")))}</h2><ul class="prose-list">'
                 + "".join(f'<li><a href="{E(path)}">{E(title)}</a></li>' for path, title in ctx.prose) + "</ul>")
    summary = f'<p class="summary">{E(ctx.summary)}</p>' if ctx.summary else ""
    cite = f'<h2>{E(str(t("site.front.cite_title")))}</h2><p>{E(str(t("site.front.cite")))}</p>'
    body = (f'<h1>{E(ctx.title)}</h1>{summary}<ul class="stats">{counted}</ul><ul class="ways">{cards}</ul>'
            f'{prose}<h2>{E(str(t("site.front.reading_title")))}</h2><p>{E(str(t("site.front.reading")))}</p>{cite}')
    return shell.page("", body, ctx=ctx, path="")


def not_found(ctx: Context) -> str:
    """`404.html`: the host serves it at any depth, so its links need the site's address (`<base>`)."""
    head = f'<base href="{E(ctx.site_url)}">\n' if ctx.site_url else ""
    body = (f'<h1>{E(str(t("site.not_found.title")))}</h1><p>{E(str(t("site.not_found.what")))}</p>'
            f'<p><a href="./">{E(ctx.title)}</a></p>')
    return shell.page(str(t("site.not_found.title")), body, ctx=ctx, path="", head=head)
