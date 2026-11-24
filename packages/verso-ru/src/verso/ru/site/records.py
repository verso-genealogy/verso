"""One record as HTML, drawn by the interface's schema (`ui-v1`): its dates, its people in the
order of the book's columns, the members of a household as a table, and how it is cited.

What the record writes (`written`) is the text (`class="w"`); what the library derived — a modern
form of a name, a surname taken from the father, a parent's estate carried to the child — stands
beside it marked (`class="d"`). A value the book's defaults give every entry is the book's header's
to say once, not each record's. The `#` comments of the DSL (`note`) are not drawn.
"""
from __future__ import annotations

import html
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from verso.core.i18n import Message
from verso.ru.ages import format_age
from verso.ru.messages import t
from verso.ru.site import model, urls
from verso.ru.site.model import Book, Entry, Node

E = html.escape

# What a record's node holds that no page shows, and why (`tests/ru/site/test_records.py` holds every
# path of the schema to be drawn or named here).
NOT_SHOWN: Mapping[str, str] = {
    "reviewed": "the record's mark says it",
    "civil": "the book's header says it",
    "index": "a counter of the export",
    "labels": "Geni's document labels",
    "kind": "the card's page says it",
    "verb": "the factory's name",
    "scan_file": "a path to a scan, which the site does not hold",
    "context": "the codec's", "wrapper": "the codec's",
    "inventory": "the citation", "archive": "the citation", "fund": "the citation", "case": "the citation",
    "citation": "drawn as the card's source",
    "source_url": "drawn as the card's source", "original_text": "drawn as the card's source",
    "bibliography": "drawn as the card's source", "archive_location": "drawn as the card's source",
    "page": "the record's head", "number": "the record's head", "family_id": "the record's head",
    "gender": "the record's head",
}
# A persona's fields the name line and the attributes do not repeat.
PERSONA_NOT_SHOWN = frozenset({"gender", "surname.in_book", "status_defaulted", "patronymic.modern",
                               "given.original", "patronymic.original", "surname.original", "given.modern",
                               "patronymic.old", "surname.modern", "maiden_surname.modern"})
# A member's fields the table's first columns hold, and the ones no column shows.
_MEMBER_HEAD = frozenset({"number", "role", "ref_member"})
_MEMBER_NOT_SHOWN = frozenset({"hidden"})
_CARD_DATES = ("date", "birth_date", "draft_date", "casualty_date", "feat_date")
_CARD_SOURCE = ("archive", "fund", "inventory", "case", "archive_location", "original_text", "bibliography")
_DATE_KEYS = frozenset({"year", "month", "day", "year_end", "date_range"})


class Ui:
    """The interface's schema and its labels, read in the language of the moment."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        self.schema = schema
        self.package = str(schema["package"])

    def label(self, key: str | None) -> str:
        return "" if not key else str(Message(self.package, key, {}))

    def kind(self, code: str) -> Mapping[str, Any]:
        """The schema of a kind of record; a kind the vocabulary does not know is no record of it."""
        try:
            return self.schema["kinds"][code]
        except KeyError:
            raise model.NotAnExport(str(t("site.unknown_kind", kind=code))) from None

    def enum(self, name: str, code: object, form: str = "") -> str:
        for member in self.schema["enums"].get(name, ()):
            if member["code"] == code:
                return self.label((member.get("forms") or {}).get(form) or member["label"])
        return str(code)


def value(node: Node, path: str, sides: Sequence[str] = ("written", "derived")) -> tuple[Any, str] | None:
    """What `node` holds at `path` and where: `(15, "w")`, `("Иванов", "d")`; None for nothing."""
    for side in sides:
        found: Any = node.get(side) or {}
        for key in path.split("."):
            found = found.get(key) if isinstance(found, Mapping) else None
        if isinstance(found, Mapping) and "text" in found:
            found = found["text"]
        if found is None or found is False or (isinstance(found, (str, list, tuple, Mapping)) and not found):
            continue                         # nothing written — but 0 is a number the source wrote
        return found, side[0]
    return None


def _is_age(path: str) -> bool:
    return path.rsplit(".", 1)[-1].endswith("age")


def text(found: Any, field: Mapping[str, Any], ui: Ui) -> str:
    """A value as a reader's text: an enum by its label, an age in words, a flag as «yes»."""
    if found is True:
        return str(t("site.yes"))
    if isinstance(found, Mapping) and _DATE_KEYS & set(found):
        return _card_date(found, ui)                 # a date object (EventDate), wherever the vocabulary has one
    if field.get("type") == "enum" and field.get("enum"):
        return ui.enum(field["enum"], found)
    if _is_age(str(field.get("path", ""))):
        return format_age(found) or str(found)
    if isinstance(found, (list, tuple)):
        return ", ".join(str(each) for each in found)
    return str(found)


def _span(text_: str, mark: str, cls: str = "") -> str:
    return f'<span class="{(cls + " " + mark).strip()}">{E(text_)}</span>'


def date_text(day: object, month: object, year: object, ui: Ui) -> str:
    """«3 мая 1915», «май 1915», «1915»: the month in the genitive beside a day."""
    parts = [str(day)] if day else []
    if month:
        parts.append(ui.enum("month", month, "gen" if day else "nom"))
    if year:
        parts.append(str(year))
    return " ".join(parts)


def _card_date(found: Mapping[str, Any], ui: Ui) -> str:
    start = date_text(found.get("day"), found.get("month"), found.get("year"), ui)
    end = date_text(found.get("day_end"), found.get("month_end"), found.get("year_end"), ui)
    if found.get("circa"):
        start = str(t("site.date.circa", date=start))
    if found.get("circa_end") and end:
        end = str(t("site.date.circa", date=end))
    match found.get("date_range"):
        case "between" if end:
            return str(t("site.date.between", start=start, end=end))
        case "before":
            return str(t("site.date.before", date=start))
        case "after":
            return str(t("site.date.after", date=start))
        case _:
            return start


# ---------------------------------------------------------------- a person

def name_html(persona: Node) -> str:
    """The name as the source writes it, and the modern forms beside it where they differ."""
    parts = model.name_parts(persona)
    written = " ".join(_span(text_, mark) for text_, mark in parts)
    modern = " ".join(text_ for text_, _ in model.modern_parts(persona))
    as_written = " ".join(text_ for text_, _ in parts)
    out = f'<span class="name">{written}</span>'
    if modern and model.fold(modern) != model.fold(as_written):
        out += f' <span class="modern d">{E(modern)}</span>'
    return out


def _defaults(book: Book) -> Mapping[str, Any]:
    return book.written.get("defaults") or {}


def _attributes(persona: Node, book: Book, ui: Ui) -> list[str]:
    """A persona's estate, place and the rest, each `label: value` but the estate, which reads alone."""
    out: list[str] = []
    for field in ui.schema["persona"]["fields"]:
        path = field["path"]
        if path in PERSONA_NOT_SHOWN or (found := value(persona, path)) is None:
            continue
        shown, mark = found
        if mark == "d":
            # The book's default is the header's to say; a place the book gives everybody too.
            if path == "status" and persona.get("derived", {}).get("status_defaulted"):
                continue
            if path == "residence" and shown in (_defaults(book).get("residence"), book.village):
                continue
        body = _span(text(shown, field, ui), mark)
        out.append(body if path == "status" else f'<span class="k">{E(ui.label(field.get("label")))}:</span> {body}')
    return out


def persona_html(persona: Node, book: Book, ui: Ui, extra: Iterable[str] = ()) -> str:
    attrs = [*extra, *_attributes(persona, book, ui)]
    tail = f' <span class="attrs">{"; ".join(attrs)}</span>' if attrs else ""
    return name_html(persona) + tail


def _personas(node: Node, role: str) -> list[Node]:
    found = [p for p in node.get("persons", ()) if p.get("role") == role and not model.hidden(p)]
    return sorted(found, key=lambda p: p.get("slot") or 0)


def _row(label: str, body: str) -> str:
    return f'<div class="p"><div class="role">{E(label)}</div><div class="who">{body}</div></div>'


def _fields(kind: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {field["path"]: field for field in kind["fields"]}


def _labelled(node: Node, path: str, fields: Mapping[str, Mapping[str, Any]], ui: Ui, label: str = "",
              sides: Sequence[str] = ("written", "derived")) -> str | None:
    field = fields.get(path, {"path": path})
    if (found := value(node, path, sides)) is None:
        return None
    shown, mark = found
    return f'<span class="k">{E(label or ui.label(field.get("label")))}:</span> {_span(text(shown, field, ui), mark)}'


def _people(entry: Entry, book: Book, kind: Mapping[str, Any], ui: Ui) -> tuple[str, set[str]]:
    """The slots of the kind in the schema's order and its lists of relatives; the record's paths drawn
    beside a person (an age beside the groom)."""
    node, fields, used, rows = entry.node, _fields(kind), set[str](), list[str]()
    lone = len(kind["slots"]) == 1 and not kind["groups"]
    for slot in kind["slots"]:
        beside = [found for path in slot.get("row", ())
                  if (found := _labelled(node, path, fields, ui, ui.label(f"ui.row.{path}"), ("written",)))]
        personas = _personas(node, slot["role"])
        if personas:
            used.update(slot.get("row", ()))
        for persona in personas:
            numbered = "slots" in slot and len(personas) > 1
            label = ui.label(slot["label"]) + (f" {persona['slot']}" if numbered else "")
            rows.append(_row("" if lone else label, persona_html(persona, book, ui, beside)))
    for group in kind["groups"]:
        if group["name"] == "members":
            continue
        item = _fields(group["item"])
        for persona in _personas(node, group["item"]["role"]):
            link = persona.get("link") or {}
            relation = value(link, "relationship")
            label = ui.enum("relationship", relation[0]) if relation else ui.label(group["label"])
            ref = value(link, "relationship_ref")
            extra = [found for path in item if path not in ("relationship", "relationship_ref")
                     if (found := _labelled(link, path, item, ui))]
            rows.append(_row(label + (f" {ref[0]}" if ref else ""), persona_html(persona, book, ui, extra)))
    return (f'<div class="people">{"".join(rows)}</div>' if rows else ""), used


# ---------------------------------------------------------------- a household

def _columns(item: Mapping[str, Any], members: Sequence[Node]) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """The columns a household's table needs: a field's group (`arrival.*`) is one column, shown where
    some member writes it."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for field in item["fields"]:
        path = field["path"]
        if path in _MEMBER_HEAD or path in _MEMBER_NOT_SHOWN or field.get("hidden"):
            continue
        if any(value(m.get("link") or {}, path, ("written",)) for m in members):
            grouped.setdefault(path.split(".")[0], []).append(field)
    return list(grouped.items())


def _column_label(key: str, fields: Sequence[Mapping[str, Any]], ui: Ui) -> str:
    if len(fields) == 1 and "." not in fields[0]["path"]:
        return ui.label(fields[0].get("label"))
    return {"arrival": str(t("site.col.arrival")), "departure": str(t("site.col.departure")),
            "birth": str(t("site.col.birth"))}.get(key, ui.label(fields[0].get("label")))


def _cell(link: Node, fields: Sequence[Mapping[str, Any]], ui: Ui) -> str:
    parts: list[str] = []
    for field in fields:
        if (found := value(link, field["path"], ("written",))) is None:
            continue
        shown = found[0]
        if field.get("type") == "ref":
            shown = str(t("site.member_ref", number=shown))
        elif field["path"].endswith(".month"):
            shown = ui.enum("month", shown, "nom")
        else:
            shown = text(shown, field, ui)
        parts.append(_span(str(shown), "w"))
    return " ".join(parts)


def _household(entry: Entry, book: Book, kind: Mapping[str, Any], ui: Ui) -> str:
    group = next((g for g in kind["groups"] if g["name"] == "members"), None)
    if group is None:
        return ""
    item = group["item"]
    members = _personas(entry.node, item["role"])
    if not members:
        return ""
    columns = _columns(item, members)
    fields = _fields(item)
    head = "".join(f"<th>{E(label)}</th>" for label in (
        str(t("site.col.number")), str(t("site.col.relation")), str(t("site.col.name")),
        *(_column_label(key, found, ui) for key, found in columns)))
    body: list[str] = []
    for member in members:
        link = member.get("link") or {}
        number = value(link, "number")
        role = value(link, "role")
        relation = text(role[0], fields["role"], ui) if role else ""
        if (ref := value(link, "ref_member")) is not None:
            relation += " " + str(t("site.member_of", number=ref[0]))
        cells = [E(str(number[0])) if number else "", E(relation), persona_html(member, book, ui),
                 *(_cell(link, found, ui) for _, found in columns)]
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return (f'<div class="scroll"><table class="members"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# ---------------------------------------------------------------- a record

def _events(entry: Entry, book: Book, kind: Mapping[str, Any], ui: Ui) -> tuple[str, set[str]]:
    used: set[str] = set()
    out: list[str] = []
    for place, event in enumerate(kind.get("events", ())):
        paths = [event.get(part) for part in ("day", "month", "year")]
        used.update(path for path in paths if path)
        day, month, year = (value(entry.node, path) if path else None for path in paths)
        if day is None and month is None:
            continue
        own_year = year[0] if year else (value(entry.node, "year") or (book.year, "d"))[0]
        label = str(t("site.event.registration")) if book.civil and place == 1 else ui.label(event["label"])
        when = date_text(day[0] if day else None, month[0] if month else None, own_year, ui)
        out.append(f'<span class="ev"><span class="k">{E(label)}:</span> {_span(when, "w")}</span>')
    used.add("year")
    return (f'<p class="events">{" ".join(out)}</p>' if out else ""), used


def _more(entry: Entry, kind: Mapping[str, Any], ui: Ui, used: set[str]) -> str:
    """The record's other fields, in the schema's order: a comment, a note «so in the original»."""
    rows: list[str] = []
    # What a wrapper or the record set gave the record (a roll's month) is the book's header's to say.
    context = set(entry.node.get("written", {}).get("context", ()))
    for field in kind["fields"]:
        path = field["path"]
        if path in used or path in context or path.split(".")[0] in NOT_SHOWN or path in _CARD_DATES:
            continue
        if (found := value(entry.node, path, ("written",))) is None:
            continue
        label = ui.label(field.get("label")) or str(_site_label(path))
        rows.append(f"<dt>{E(label)}</dt><dd>{_span(text(found[0], field, ui), found[1])}</dd>")
    for path in _CARD_DATES:
        if (found := value(entry.node, path)) is not None and isinstance(found[0], Mapping):
            rows.append(f"<dt>{E(str(_site_label(path)))}</dt><dd>{_span(_card_date(found[0], ui), found[1])}</dd>")
    return f'<dl class="more">{"".join(rows)}</dl>' if rows else ""


def site_labels() -> dict[str, Message]:
    """The labels of what the interface's schema names no label for — a field a review page edits
    elsewhere, which a reader still reads."""
    return {"date": t("site.field.date"), "birth_date": t("site.field.birth_date"),
            "draft_date": t("site.field.draft_date"), "casualty_date": t("site.field.casualty_date"),
            "feat_date": t("site.field.feat_date"), "book": t("site.field.book"),
            "baptism.age": t("site.field.baptism_age"), "church": t("site.field.church"),
            "village": t("site.field.village"), "birth.day": t("site.field.birth_day"),
            "birth.month": t("site.field.birth_month"), "baptism.year": t("site.field.baptism_year"),
            "source_date_error": t("site.field.source_date_error"), "lag_note": t("site.field.lag_note"),
            "marriage_date": t("site.field.marriage_date")}


def _site_label(path: str) -> Message:
    return site_labels().get(path, t("site.field.other"))


def shelfmark(node: Node, book: Book) -> str:
    """«ГАРО. Ф. 627. Оп. 255. Д. 13.» — the record's own shelfmark where it states one, else the book's;
    «шифр не установлен» where a part of it is unknown."""
    of_book = book.shelf
    parts = {key: str((value(node, key, ("written",)) or (of_book[key], "w"))[0] or "") for key in of_book}
    if any(part in ("", "?") for part in parts.values()):
        known = parts["archive"] if parts["archive"] not in ("", "?") else ""
        return (known + ". " if known else "") + str(t("site.cite.unknown"))
    return str(t("site.cite.shelfmark", **parts))


def _citation(entry: Entry, book: Book) -> str:
    node = entry.node
    if book.is_cards:
        citation = (node.get("derived") or {}).get("citation") or {}
        parts = [E(str(citation.get("catalog", "")))]
        if all(citation.get(key) for key in ("archive", "fund")):
            ref = [str(citation[key]) for key in ("fund", "inventory", "case") if citation.get(key)]
            # «ЦГА 12-345678-9» where the catalog gives numbers; its own words where it gives words.
            numbers = all(" " not in part for part in ref)
            shelf = f'{citation["archive"]} {"-".join(ref)}' if numbers else ", ".join([str(citation["archive"]), *ref])
            parts.append(E(str(t("site.cite.card_archive", ref=shelf))))
        parts += [E(str(citation[key])) for key in ("archive_location", "original_text", "bibliography")
                  if citation.get(key)]
        if (url := citation.get("source_url")) and str(url).startswith(("https://", "http://")):
            parts.append(f'<a href="{E(str(url))}" rel="noopener">{E(str(t("site.cite.source")))}</a>')
        body = ". ".join(part for part in parts if part)
    else:
        body = E(shelfmark(node, book))
        if entry.leaf and entry.leaf != "?":
            body += " " + E(str(t("site.cite.leaf", leaf=entry.leaf)))
    link = (f'<a class="perma" href="#{urls.fragment(entry.anchor)}">{E(str(t("site.permalink")))}</a>'
            f' <code>{E(entry.id)}</code>')
    return f'<footer class="cite"><span class="k">{E(str(t("site.cite.label")))}:</span> {body} · {link}</footer>'


def _head(entry: Entry, book: Book, kind: Mapping[str, Any], ui: Ui) -> str:
    node = entry.node
    number = value(node, "number") or value(node, "family_id")
    if entry.node["kind"] == "household" and number:
        word = str((value({"written": book.written, "derived": book.docs[0].get("derived")}, "household_label")
                    or (ui.label(kind["label"]), "d"))[0]).capitalize()
        title = f"{word} № {number[0]}"
    elif number:
        title = f"№ {number[0]}"
    else:
        title = ui.label(kind["label"])
    gender = value(node, "gender", ("written",))
    sex = f' <span class="sex">{E(ui.enum("gender", gender[0]))}.</span>' if gender else ""
    label = f' <span class="label">{E(str(node.get("label") or ""))}</span>' if node.get("label") else ""
    leaf = (f'<span class="leaf">{E(str(t("site.leaf", leaf=entry.leaf)))}</span>'
            if entry.leaf and entry.leaf != "?" else "")
    badge = f'<span class="badge">{E(str(t("site.unreviewed")))}</span>' if entry.unreviewed else ""
    return (f'<header><h2><a href="#{urls.fragment(entry.anchor)}">{E(title)}</a>{sex}{label}</h2>'
            f'{leaf}{badge}</header>')


def render(entry: Entry, book: Book, ui: Ui) -> str:
    """The record as an `<article>` whose id is its anchor."""
    kind = ui.kind(str(entry.node.get("kind")))
    events, used = _events(entry, book, kind, ui)
    people, beside = _people(entry, book, kind, ui)
    classes = "rec" + (" held" if entry.unreviewed else "")
    return (f'<article class="{classes}" id="{E(entry.anchor)}">{_head(entry, book, kind, ui)}{events}{people}'
            f'{_household(entry, book, kind, ui)}{_more(entry, kind, ui, used | beside)}'
            f'{_citation(entry, book)}</article>')
