"""Familio справочник submission exporter.

A *справочник* is one Familio submission file (`.xlsx`) covering many years of a
parish's records, with one tab per record type (РОЖДЕНИЕ / БРАК / СМЕРТЬ). It is
built from the record sets themselves — the rows :mod:`verso.ru.exporters.csv_familio`
gives of each, no CSV read from a disk — projected onto the columns of the official
Familio **МК** template (see :mod:`verso.ru.exporters.familio_template` for the column
mapping) and written into a workbook of that template's layout
(:mod:`verso.ru.exporters.familio_layout`), or into Familio's own file.

This module is layered for testability:

* **Domain** (pure, no I/O): :func:`collect` (record sets → source rows, the unreviewed
  left out), :func:`build_sheet`, :func:`build_spravochnik` and the
  :class:`Spravochnik` / :class:`SpravochnikSheet` / :class:`YearRecords` value
  objects. Rows are concatenated in year order, projected onto the template's
  columns, and given a continuous *сквозная нумерация* (template column "А").
  :func:`referenced_places`, :func:`location_rows` and :func:`known_from` make the
  ``location`` sheet's rows of the places the rows name and a places dictionary.
* **Infrastructure**: :func:`read_location_rows`, :func:`read_about` (a village's curated
  files) and :class:`FamilioTemplateWriter` (fills the workbook — the only
  ``openpyxl``-touching code besides the layout's).
"""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

    from verso.core.places import Places

from verso.core.ratchet import unreviewed
from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.exporters.csv_familio import exporter_of
from verso.ru.exporters.familio_layout import LOCATION_HELPER_HEADERS, Layout, build_workbook, load_layout
from verso.ru.exporters.familio_template import (
    TEMPLATE_DATA_START_ROW, TEMPLATE_MAPS, TEMPLATE_SHEET_TITLES, remap_row)

# Record types in canonical справочник order.
RECORD_TYPES: tuple[str, ...] = ("births", "marriages", "deaths")

# The record sets a справочник reads — the three parts of a metric book — and the tab each fills.
RECORD_SET_TYPES: dict[type, str] = {BirthRecords: "births", MarriageRecords: "marriages", DeathRecords: "deaths"}

# Source CSV columns identifying the archival дело (Архив, Фонд, Опись, Дело),
# used to group records of the same book together.
_DELO_COLS: tuple[int, ...] = (1, 2, 3, 4)
# Same fields in the filled template (columns B/C/D/E), for дело-boundary borders.
_TEMPLATE_DELO_COLS: tuple[int, ...] = (2, 3, 4, 5)


@dataclass(frozen=True)
class YearRecords:
    """One record type's source rows for a single year, read from a per-year CSV."""

    year: int
    rows: list[list[str]]


@dataclass(frozen=True)
class SpravochnikSheet:
    """One tab of a справочник: a record type aggregated across all years and
    already projected onto the template's columns (col "А" = сквозная)."""

    record_type: str
    title: str  # the template tab title, e.g. "РОЖДЕНИЕ"
    rows: list[list[str]]


@dataclass(frozen=True)
class Spravochnik:
    """A complete Familio submission: one village, a year range, several tabs."""

    village: str
    from_year: int
    to_year: int
    sheets: list[SpravochnikSheet]
    years_label: str = ""  # human label for the year set ("1832-1840" or "1799, 1805")


@dataclass(frozen=True)
class Collected:
    """What `collect` read of the record sets it was given: the rows by tab, a year's a `YearRecords`; how many
    records they are and how many were left out as unreviewed; the parishes the rows are of, in the order met."""

    records_by_type: dict[str, list[YearRecords]]
    taken: int
    left_out: int
    parishes: tuple[str, ...]


def collect(record_sets: Iterable[object], *, parish: str | None = None, years: Collection[int] | None = None,
            reviewed_only: bool = True) -> Collected:
    """A справочник's source rows from record sets, in their order — what the per-year familio CSVs held, read
    from no file. A set that is no part of a metric book (`RECORD_SET_TYPES`) is passed over and counted
    nowhere; a set bound twice (an alias) is read once. `parish` keeps the sets of that parish (the set's
    `village`), `years` the sets of those years. With `reviewed_only` an unreviewed record
    (`verso.core.ratchet.unreviewed`) gives no row and is counted in `left_out`; a set left with no row gives
    no year."""
    records_by_type: dict[str, list[YearRecords]] = {record_type: [] for record_type in RECORD_TYPES}
    taken = left_out = 0
    parishes: list[str] = []
    seen: set[int] = set()
    for record_set in record_sets:
        record_type = RECORD_SET_TYPES.get(type(record_set))
        exporter = exporter_of(record_set)
        if record_type is None or exporter is None or id(record_set) in seen:
            continue
        seen.add(id(record_set))
        book: Any = record_set
        if parish is not None and book.village != parish:
            continue
        if years is not None and book.year not in years:
            continue
        records = [r for r in book.records if not (reviewed_only and unreviewed(r))]
        left_out += len(book.records) - len(records)
        if not records:
            continue
        taken += len(records)
        if book.village not in parishes:
            parishes.append(book.village)
        records_by_type[record_type].append(
            YearRecords(year=book.year, rows=exporter.table(book, records=records).text_rows()))
    return Collected(records_by_type, taken, left_out, tuple(parishes))


def years_label_for(years: list[int]) -> str:
    """Human label: a single year as ``1805``, a contiguous run as ``1832-1840``,
    else an explicit list ``1799, 1805``."""
    if len(years) == 1:
        return str(years[0])
    if years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}-{years[-1]}"
    return ", ".join(str(y) for y in years)


def _delo_id(row: list[str]) -> str:
    """A row's дело as ``Фонд-Опись-Дело`` (e.g. ``64-9-956``), matching how cases
    are written in archive references."""
    return "-".join(row[i] if i < len(row) else "" for i in (2, 3, 4))


def build_sheet(
    record_type: str,
    year_records: list[YearRecords],
    cases: frozenset[str] | None = None,
) -> SpravochnikSheet | None:
    """Aggregate per-year records of one type into a single template-shaped sheet.

    Records are grouped by дело, ordered by earliest year then дело identity, and
    numbered continuously in column "А". When ``cases`` is given, only rows whose
    дело (``Фонд-Опись-Дело``) is in the set are kept. Returns ``None`` when no
    rows remain, so the caller can skip the tab.
    """
    col_map = TEMPLATE_MAPS[record_type]
    # (year, original index, row) so records can be grouped by дело while keeping a
    # stable order within each book.
    indexed: list[tuple[int, int, list[str]]] = []
    for yr in sorted(year_records, key=lambda y: y.year):
        for row in yr.rows:
            if cases is None or _delo_id(row) in cases:
                indexed.append((yr.year, len(indexed), row))
    if not indexed:
        return None

    def delo_key(row: list[str]) -> tuple[str, ...]:
        return tuple(row[i] if i < len(row) else "" for i in _DELO_COLS)

    # Group records of the same дело together; order дела by their earliest year
    # (so a book spanning two years sits with the bulk of its records), then by
    # дело identity, preserving record order within a book.
    earliest: dict[tuple[str, ...], int] = {}
    for yr, _, row in indexed:
        key = delo_key(row)
        earliest[key] = min(earliest.get(key, yr), yr)
    ordered = sorted(indexed, key=lambda t: (earliest[delo_key(t[2])], delo_key(t[2]), t[1]))

    template_rows = [remap_row(row, col_map, seq) for seq, (_, _, row) in enumerate(ordered, start=1)]
    return SpravochnikSheet(
        record_type=record_type,
        title=TEMPLATE_SHEET_TITLES[record_type],
        rows=template_rows,
    )


def build_spravochnik(
    village: str,
    from_year: int,
    to_year: int,
    records_by_type: dict[str, list[YearRecords]],
    years_label: str = "",
    cases: frozenset[str] | None = None,
) -> Spravochnik:
    """Build a :class:`Spravochnik` from per-type, per-year records.

    Sheets are emitted in canonical order (РОЖДЕНИЕ, БРАК, СМЕРТЬ); a record type
    with no rows is omitted entirely. ``years_label`` is the human label for the
    year set (defaults to ``"{from_year}-{to_year}"``). ``cases`` optionally limits
    output to the given дела (``Фонд-Опись-Дело``).
    """
    sheets: list[SpravochnikSheet] = []
    for record_type in RECORD_TYPES:
        sheet = build_sheet(record_type, records_by_type.get(record_type, []), cases=cases)
        if sheet is not None:
            sheets.append(sheet)
    return Spravochnik(
        village=village,
        from_year=from_year,
        to_year=to_year,
        sheets=sheets,
        years_label=years_label or f"{from_year}-{to_year}",
    )


@dataclass(frozen=True)
class LocationRow:
    """One curated ``location`` sheet entry (the durable input columns)."""

    place: str
    type: str
    region: str
    district: str
    volost: str
    link: str


def read_location_rows(path: Path) -> list[LocationRow] | None:
    """Read a curated ``location.csv`` (header + place/type/region/district/volost/link
    columns), or ``None`` if the file is absent."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            LocationRow(
                place=(r.get("place") or "").strip(),
                type=(r.get("type") or "").strip(),
                region=(r.get("region") or "").strip(),
                district=(r.get("district") or "").strip(),
                volost=(r.get("volost") or "").strip(),
                link=(r.get("link") or "").strip(),
            )
            for r in reader
            if (r.get("place") or "").strip()
        ]


# What a place's `city` begins with → the `type` Familio's `location` sheet writes. A word that is not here
# leaves the type blank: the indexer writes it.
_PLACE_TYPES: dict[str, str] = {
    "село": "с.", "деревня": "д.", "город": "г.", "слобода": "сл.", "посёлок": "пос.", "поселок": "пос.",
    "хутор": "х.", "сельцо": "сц.", "погост": "пог.", "выселок": "выс.", "местечко": "м.", "станция": "ст.",
}
_FAMILIO_SETTLEMENT = "https://familio.org/settlements/"


def referenced_places(spravochnik: Spravochnik, layout: Layout | None = None) -> list[str]:
    """Every place a row of the справочник names — the value on the left of each location helper column —
    as it is written, once, in the order first met: what the `location` sheet must list for no lookup to miss."""
    layout = layout or load_layout()
    found: dict[str, None] = {}
    for sheet in spravochnik.sheets:
        sources = sorted(c - 2 for c in layout.sheets[sheet.record_type].helpers)     # 0-based, left of the helper
        for row in sheet.rows:
            for index in sources:
                if index < len(row) and row[index] != "":
                    found.setdefault(row[index], None)
    return list(found)


def derive_location(place: str, fields: Mapping[str, str], attributes: Mapping[str, str]) -> LocationRow:
    """The `location` row of `place` (kept as written: it is the lookup's key) from a place's fields — only
    what they say unambiguously. `city` «село X» gives the type «с.» (`_PLACE_TYPES`) — unless the place is
    written with its type already («с. X», «село X») —; `county` «A уезд, B
    волость» the district A and the volost B; `state` «A губерния» the region A, any other state whole; the
    attribute `familio` the settlement's link. Whatever is not said so stays blank."""
    kind, _, rest = fields.get("city", "").strip().partition(" ")
    place_type = _PLACE_TYPES.get(kind.lower(), "") if rest else ""
    written = place.strip().lower()
    if place_type and (written.startswith(place_type) or written.startswith(f"{kind.lower()} ")):
        place_type = ""         # «с. X», «село X»: the sheet's formula writes «type place» — no «с. с. X»
    district = volost = ""
    for part in (part.strip() for part in fields.get("county", "").split(",")):
        if part.endswith(" уезд"):
            district = part.removesuffix(" уезд").strip()
        elif part.endswith(" волость"):
            volost = part.removesuffix(" волость").strip()
    state = fields.get("state", "").strip()
    region = state.removesuffix(" губерния").strip() if state.endswith(" губерния") else state
    settlement = attributes.get("familio", "").strip()
    return LocationRow(place=place, type=place_type, region=region, district=district, volost=volost,
                       link=f"{_FAMILIO_SETTLEMENT}{settlement}" if settlement else "")


def known_from(places: Places) -> Callable[[str], LocationRow | None]:
    """What a places dictionary knows of a place, as `location_rows` asks it: the row `derive_location` makes of
    the place's fields — a spelling's (`same_as`) are its canon's —, None for a place the dictionary lacks. A
    place written with a space around it is found without the space, and kept as written."""
    from verso.core.places import parse_body

    def known(place: str) -> LocationRow | None:
        canon = places.canonicals.get(place) or places.canonicals.get(place.strip())
        body = places.bodies.get(canon) if canon is not None else None
        if canon is None or body is None:
            return None
        attributes = {name: values[canon] for name, values in places.attributes.items() if canon in values}
        return derive_location(place, parse_body(body), attributes)

    return known


def location_rows(places: Sequence[str], *, curated: Sequence[LocationRow] = (),
                  known: Callable[[str], LocationRow | None] = lambda place: None) -> list[LocationRow]:
    """The `location` sheet's rows for a справочник that names `places`: the curated rows first, as they are and
    in their order (a row no record names stays); then every other place named — what `known` says of it, a
    row of its name alone where it says nothing."""
    rows = list(curated)
    listed = {row.place for row in rows}
    for place in places:
        if place in listed:
            continue
        listed.add(place)
        rows.append(known(place) or LocationRow(place, "", "", "", "", ""))
    return rows


def _places_named(spravochnik: Spravochnik) -> list[LocationRow]:
    """The `location` rows of a справочник nobody gave any: the places its rows name, their names alone."""
    return location_rows(referenced_places(spravochnik))


def blank_places(rows: Sequence[LocationRow]) -> int:
    """How many rows say nothing but the place's name: what is left for the indexer to fill."""
    return sum(1 for row in rows if not (row.type or row.region or row.district or row.volost or row.link))


@dataclass(frozen=True)
class AboutInfo:
    """Values for the ``about`` (INFO) sheet of a Familio submission.

    Per-village/author metadata; the года rows are derived from the year range.
    String fields may contain ``{village}`` / ``{from_year}`` / ``{to_year}``
    placeholders, substituted by :func:`read_about`.
    """

    spravochnik_name: str
    description: str
    author_name: str
    author_familio_url: str
    author_telegram: str
    otchestvo_type: str  # "современный" | "старый"
    is_update: bool
    prior_catalog_url: str


def read_about(
    path: Path, village: str, from_year: int, to_year: int, years_label: str = ""
) -> AboutInfo | None:
    """Read a per-village ``about.json``, substituting village/year placeholders (:func:`about_of`).

    Returns ``None`` if the file is absent (the template's ``about`` sheet is then
    left untouched).
    """
    import json

    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)
    return about_of(data, village, from_year, to_year, years_label)


def about_of(
    data: Mapping[str, object], village: str, from_year: int, to_year: int, years_label: str = ""
) -> AboutInfo:
    """The ``about`` values a mapping holds — ``about.json``'s keys, from wherever a host keeps them — with the
    village/year placeholders substituted: ``{village}``, ``{from_year}``, ``{to_year}``, and ``{years}``, which
    expands to ``years_label`` (a contiguous range like ``1832-1840`` or an explicit list like ``1799, 1805``).
    A key the mapping lacks is empty; ``otchestvo_type`` is ``современный`` by default, ``is_update`` false."""
    label = years_label or f"{from_year}-{to_year}"

    def sub(value: str) -> str:
        return (
            value.replace("{village}", village)
            .replace("{from_year}", str(from_year))
            .replace("{to_year}", str(to_year))
            .replace("{years}", label)
        )

    def s(key: str) -> str:
        return sub(str(data.get(key, "")))

    return AboutInfo(
        spravochnik_name=s("spravochnik_name"),
        description=s("description"),
        author_name=s("author_name"),
        author_familio_url=s("author_familio_url"),
        author_telegram=s("author_telegram"),
        otchestvo_type=s("otchestvo_type") or "современный",
        is_update=bool(data.get("is_update", False)),
        prior_catalog_url=s("prior_catalog_url"),
    )


# The rows of `about` the year range alone answers, and the about of a справочник that was given none.
_YEARS_LABELS = frozenset({"Годы, охватываемые индексацией", "Наименьший год, охватываемый индексацией"})
_NO_ABOUT = AboutInfo("", "", "", "", "", "", False, "")


# A spreadsheet keeps fifteen digits of a number; a longer run of digits is a text.
_MAX_NUMBER_DIGITS = 15


def _coerce(value: str) -> str | int:
    """Write purely-numeric cells as numbers so Excel doesn't flag them as text — a plain number only: ASCII
    digits, no leading nought (a лист «007» is its text), no more of them than a spreadsheet keeps. A digit
    of another script, a superscript or a circled number stays the text it is (`str.isdigit` would take
    them, and `int` would change them or refuse)."""
    plain = (value.isascii() and value.isdigit() and len(value) <= _MAX_NUMBER_DIGITS
             and (value == "0" or not value.startswith("0")))
    return int(value) if plain else value


def _put(ws: Worksheet, row: int, column: int, value: str | int) -> None:
    """A value that came from a record or from a person's own words, written as what it is: a text beginning
    with ``=`` is a text, never a formula (openpyxl reads such a string as one). The workbook's formulas are
    the writer's own."""
    cell = ws.cell(row=row, column=column, value=value)
    if isinstance(value, str) and cell.data_type == "f":
        cell.data_type = "s"


# Template helper columns that hold a place-name lookup (`LOCATION_HELPER_HEADERS`, of the layout). Each such
# column resolves the Н.П. cell immediately to its left into a full location string via VLOOKUP against the
# ``location`` sheet. Identified by their row-2 header (works across all three record tabs and is robust to
# template column reordering).

# Column on the ``location`` sheet that VLOOKUP returns (col G, 1-based 7).
_LOCATION_RESULT_COL = 7
# The ``location`` sheet's first data row (rows 1–2 are the two header rows).
_LOCATION_DATA_START_ROW = 3


def _location_vlookup(src_col: str, row: int) -> str:
    """VLOOKUP formula resolving the Н.П. cell at ``{src_col}{row}`` to its full
    location string, blank when the source is empty (avoids ``#N/A``)."""
    cell = f"{src_col}{row}"
    return f'=IF({cell}="","",VLOOKUP({cell},location!$A:$I,{_LOCATION_RESULT_COL},FALSE))'


def _capture_row_styles(ws: Worksheet, start_row: int) -> list[dict[int, object]]:
    """Snapshot the per-column cell formatting of each template data row.

    Returns one ``{column: style}`` dict per row from ``start_row`` to the sheet's
    last row, so the formatting can be re-applied after the rows are cleared and
    repopulated. Empty when the template has no data rows.
    """
    styles: list[dict[int, object]] = []
    for r in range(start_row, ws.max_row + 1):
        styles.append(
            {c: copy(ws.cell(row=r, column=c)._style) for c in range(1, ws.max_column + 1)}
        )
    return styles


def _apply_row_styles(ws: Worksheet, excel_row: int, r_off: int, styles: list[dict[int, object]]) -> None:
    """Re-apply captured template formatting to a written data row.

    Rows beyond the template's pre-formatted range reuse the last captured row's
    style, so every generated row keeps the template's borders/fonts/number formats.
    """
    if not styles:
        return
    model = styles[min(r_off, len(styles) - 1)]
    for c, style in model.items():
        ws.cell(row=excel_row, column=c)._style = copy(style)


def _extend_sqref(sqref: str, tpl_last: int, new_last: int) -> str:
    """Extend a conditional-formatting ``sqref`` to the new last data row.

    Each space-separated sub-range whose end row equals the template's last data
    row (``tpl_last``) has that end row bumped to ``new_last``; single-cell refs
    and ranges ending elsewhere are left untouched.
    """
    out: list[str] = []
    for token in sqref.split():
        if ":" in token:
            start, end = token.split(":", 1)
            m = re.match(r"([A-Z]+)(\d+)$", end)
            if m and int(m.group(2)) == tpl_last:
                end = f"{m.group(1)}{new_last}"
            out.append(f"{start}:{end}")
        else:
            out.append(token)
    return " ".join(out)


class FamilioTemplateWriter:
    """Fill a copy of the official Familio МК template with справочник data.

    Preserves the template's helper sheets (name lists, etc.) and its two header
    rows; data rows are written from :data:`TEMPLATE_DATA_START_ROW`. The
    ``full_location`` / ``person_location`` helper columns are filled with VLOOKUP
    formulas against the ``location`` sheet, which can optionally be (re)populated
    from curated :class:`LocationRow` data.

    With no ``template_path`` the workbook is the one the library builds of the template's layout
    (:func:`verso.ru.exporters.familio_layout.build_workbook`): the same sheets, header rows and columns, none
    of Familio's helper sheets, dropdowns or formatting — and the same cells written into it.
    """

    def __init__(self, template_path: Path | None = None):
        self.template_path = template_path

    def write(
        self,
        spravochnik: Spravochnik,
        out_path: Path,
        location_rows: list[LocationRow] | None = None,
        about: AboutInfo | None = None,
    ) -> Path:
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter

        wb = load_workbook(self.template_path) if self.template_path is not None else build_workbook()
        for sheet in spravochnik.sheets:
            ws = wb[sheet.title]
            # Columns whose value is a VLOOKUP formula rather than copied data.
            helper_cols = {
                c
                for c in range(1, ws.max_column + 1)
                if ws.cell(row=2, column=c).value in LOCATION_HELPER_HEADERS
            }
            # Capture the template's per-row data-row formatting before clearing, so
            # generated rows keep the same borders/fonts/number formats.
            # The Н.П. cells the helpers look up: written as text whatever they hold — the `location` sheet's
            # names are text, and a lookup of a number among texts misses.
            looked_up = {c - 1 for c in helper_cols}
            styles = _capture_row_styles(ws, TEMPLATE_DATA_START_ROW)
            tpl_last_row = ws.max_row
            # Clear any sample/leftover data rows below the header.
            if ws.max_row >= TEMPLATE_DATA_START_ROW:
                ws.delete_rows(TEMPLATE_DATA_START_ROW, ws.max_row - TEMPLATE_DATA_START_ROW + 1)
            for r_off, row in enumerate(sheet.rows):
                excel_row = TEMPLATE_DATA_START_ROW + r_off
                for c_off, value in enumerate(row, start=1):
                    if c_off in helper_cols:
                        src_col = get_column_letter(c_off - 1)
                        ws.cell(row=excel_row, column=c_off, value=_location_vlookup(src_col, excel_row))
                    elif value != "":
                        _put(ws, excel_row, c_off, value if c_off in looked_up else _coerce(value))
                _apply_row_styles(ws, excel_row, r_off, styles)
            # Stretch the template's conditional formatting over the generated rows.
            new_last_row = TEMPLATE_DATA_START_ROW + len(sheet.rows) - 1
            self._extend_conditional_formatting(ws, tpl_last_row, new_last_row)
            # Thicken the bottom border at each дело boundary.
            self._mark_delo_boundaries(ws, TEMPLATE_DATA_START_ROW, len(sheet.rows))

        if location_rows is None and self.template_path is None:
            # The built workbook has no sample rows to keep, and a lookup against an empty sheet misses: it
            # lists at least the names of the places its rows name.
            location_rows = _places_named(spravochnik)
        if location_rows is not None:
            self._write_location_sheet(wb, location_rows)
        if about is not None:
            self._write_about_sheet(wb, about, spravochnik)
        elif self.template_path is None:
            # The built workbook has no sample to keep: it says at least the years it covers.
            self._write_about_sheet(wb, _NO_ABOUT, spravochnik, years_only=True)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
        # openpyxl drops the template's x14 (extension) data-validation dropdowns
        # on load; splice them back from the template so the dropdowns survive.
        if self.template_path is not None:
            self._preserve_data_validations(self.template_path, out_path)
        return out_path

    @staticmethod
    def _write_location_sheet(wb: Workbook, location_rows: list[LocationRow]) -> None:
        """Replace the ``location`` sheet's data with curated rows.

        Writes the durable input columns (place/type/region/district/volost in A–E,
        Familio link in H) and rebuilds the derived columns as A1-style formulas:
        ``F`` короткая сборка, ``G`` full_location (the VLOOKUP target), ``I`` URL.
        Stale sample rows below the curated data are cleared so they can't match a
        lookup.
        """
        ws = wb["location"]
        start = _LOCATION_DATA_START_ROW
        styles = _capture_row_styles(ws, start)
        if ws.max_row >= start:
            ws.delete_rows(start, ws.max_row - start + 1)
        for i, loc in enumerate(location_rows):
            r = start + i
            for column, value in ((1, loc.place), (2, loc.type), (3, loc.region), (4, loc.district),
                                  (5, loc.volost), (8, loc.link)):
                _put(ws, r, column, value)
            ws.cell(row=r, column=6, value=f'=CONCATENATE(B{r}," ",A{r})')
            ws.cell(
                row=r,
                column=7,
                value=(
                    f'=CONCATENATE(B{r}," ",A{r},'
                    f'IF(E{r}="","",", "),E{r},'
                    f'IF(D{r}="","",", "),D{r},'
                    f'IF(C{r}="","",", "),C{r})'
                ),
            )
            ws.cell(row=r, column=9, value=f"=RIGHT(H{r},36)")
            _apply_row_styles(ws, r, i, styles)

    @staticmethod
    def _write_about_sheet(wb: Workbook, about: AboutInfo, sp: Spravochnik, *, years_only: bool = False) -> None:
        """Fill the ``about`` sheet's value column (B) by matching row labels (A).

        Labels and helper text shipped in the template are preserved; only the
        per-submission values are written — with ``years_only`` the two rows of the years alone.
        """
        ws = wb["about"]
        values: dict[str, str | int] = {
            "Название справочника": about.spravochnik_name,
            "Годы, охватываемые индексацией": sp.years_label,
            "Наименьший год, охватываемый индексацией": sp.from_year,
            "Описание, которое будет под названием справочника на сайте": about.description,
            "Кем проведена индексация (авторство)": about.author_name,
            "Ссылка на профиль автора на Familio": about.author_familio_url,
            "Никнейм (имя пользователя) в мессенджере Telegram для ссылки на автора": about.author_telegram,
            "Тип написания окончания отчества у людей (рождённых, умерших детей)": about.otchestvo_type,
            "Это новый справочник или дополнительные данные к ранее начатому?": (
                "обновление начатого ранее" if about.is_update else "новый справочник"
            ),
            "Ссылка на загруженный ранее справочник на сайте familio.org": about.prior_catalog_url,
        }
        if years_only:
            values = {label: value for label, value in values.items() if label in _YEARS_LABELS}
        for r in range(1, ws.max_row + 1):
            label = ws.cell(row=r, column=1).value
            if isinstance(label, str) and label.strip() in values:
                value = values[label.strip()]
                if value != "":
                    _put(ws, r, 2, value)

    @staticmethod
    def _extend_conditional_formatting(ws: Worksheet, tpl_last: int, new_last: int) -> None:
        """Stretch the template's conditional-formatting ranges over generated rows.

        The template's CF rules cover only its sample data range (ending at
        ``tpl_last``); generated rows beyond that would otherwise be unformatted.
        Re-add every rule with its ``sqref`` extended to ``new_last``.
        """
        from openpyxl.formatting.formatting import ConditionalFormattingList

        if new_last <= tpl_last:
            return
        entries = [(str(cf.sqref), list(cf.rules)) for cf in ws.conditional_formatting]
        ws.conditional_formatting = ConditionalFormattingList()
        for sqref, rules in entries:
            new_sqref = _extend_sqref(sqref, tpl_last, new_last)
            for rule in rules:
                ws.conditional_formatting.add(new_sqref, rule)

    @staticmethod
    def _mark_delo_boundaries(ws: Worksheet, start_row: int, n_rows: int) -> None:
        """Thicken the bottom border of the last row of each дело (book) group.

        Records are grouped by дело (contiguous after :func:`build_sheet`), so a
        boundary is any row whose Архив/Фонд/Опись/Дело differs from the next row's
        (and the final data row). Marks every column of that row.
        """
        from openpyxl.styles import Border, Side

        if n_rows <= 0:
            return
        end = start_row + n_rows - 1

        def key(r: int) -> tuple[object, ...]:
            return tuple(ws.cell(row=r, column=c).value for c in _TEMPLATE_DELO_COLS)

        for r in range(start_row, end + 1):
            if r == end or key(r) != key(r + 1):
                for c in range(1, ws.max_column + 1):
                    b = ws.cell(row=r, column=c).border
                    ws.cell(row=r, column=c).border = Border(
                        left=b.left, right=b.right, top=b.top, bottom=Side(style="thick")
                    )

    @staticmethod
    def _preserve_data_validations(template_path: Path, out_path: Path) -> None:
        """Re-inject the template's x14 (extension) data-validation dropdowns.

        openpyxl cannot represent x14 list validations (cross-sheet sources) and
        silently drops them on load, so the saved workbook loses every template
        dropdown (e.g. ``about!B13`` отчество type, Пол/статус/Н.П. columns). We
        copy the ``<ext>`` blocks holding ``x14:dataValidations`` from the template
        and splice them, by sheet name, into the saved file's worksheet XML.
        """
        _MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        _REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

        def sheet_xml_by_name(zf: zipfile.ZipFile) -> dict[str, str]:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            relmap = {r.get("Id"): r.get("Target") for r in rels}
            result: dict[str, str] = {}
            sheets = wb.find(f"{{{_MAIN}}}sheets")
            if sheets is None:
                return result
            for s in sheets:
                target = relmap.get(s.get(f"{{{_REL}}}id", ""), "")
                name = s.get("name")
                if not target or not name:
                    continue
                if target.startswith("/"):
                    target = target.lstrip("/")          # package-absolute (openpyxl)
                elif not target.startswith("xl/"):
                    target = "xl/" + target               # relative to xl/ (template)
                result[name] = target
            return result

        def dv_exts(xml: str) -> str | None:
            exts = [e for e in re.findall(r"<ext\b.*?</ext>", xml, re.S) if "x14:dataValidations" in e]
            if not exts:
                return None
            return re.sub(r'\s+xr:uid="\{[^}]*\}"', "", "".join(exts))

        with zipfile.ZipFile(template_path) as tz:
            tmap = sheet_xml_by_name(tz)
            dv_by_name: dict[str, str] = {}
            for name, target in tmap.items():
                try:
                    block = dv_exts(tz.read(target).decode("utf-8"))
                except KeyError:
                    continue
                if block:
                    dv_by_name[name] = block
        if not dv_by_name:
            return

        with zipfile.ZipFile(out_path) as oz:
            omap = sheet_xml_by_name(oz)
            names = oz.namelist()
            data = {n: oz.read(n) for n in names}

        for name, block in dv_by_name.items():
            target = omap.get(name)
            if target is None or target not in data:
                continue
            xml = data[target].decode("utf-8")
            if "</extLst>" in xml:
                xml = xml.replace("</extLst>", block + "</extLst>", 1)
            else:
                xml = xml.replace("</worksheet>", f"<extLst>{block}</extLst></worksheet>", 1)
            data[target] = xml.encode("utf-8")

        tmp = out_path.with_name(out_path.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for n in names:
                zf.writestr(n, data[n])
        tmp.replace(out_path)
