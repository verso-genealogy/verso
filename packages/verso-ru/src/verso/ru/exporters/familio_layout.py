"""The layout of Familio's **МК** submission template, and a workbook built of it.

A справочник is sent to Familio as a workbook of their template's shape. The library carries that shape as
data — `familio_mk.json`: the titles of the three record sheets, their two header rows (row 1 the column
groups, row 2 the columns), the labels of the `about` sheet and the head of `location` — and
`build_workbook` makes an empty workbook of it, which :class:`verso.ru.exporters.familio_spravochnik.FamilioTemplateWriter`
fills where it is given no template file.

What the built workbook is not: Familio's file. It has no `INFO`, `spiski`, `Name_M` or `Ends` sheet, no
dropdown, no conditional formatting and no sample row; its formatting is plain. `--template FILE` of
`verso familio-spravochnik` fills Familio's own file instead.
"""
from __future__ import annotations

import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openpyxl.workbook.workbook import Workbook

# The columns of a record sheet that hold a place-name lookup, by their row-2 name: each resolves the Н.П. cell
# on its left against the `location` sheet.
LOCATION_HELPER_HEADERS: frozenset[str] = frozenset({"full_location", "person_location"})

_RECORD_TYPES = ("births", "marriages", "deaths")       # the order of the tabs
_DATA_START_ROW = 4                                     # rows 1–2 the headers, row 3 a spacer
_LOCATION_DATA_START_ROW = 3


@dataclass(frozen=True)
class SheetLayout:
    """One record sheet: its tab's title, row 1 as (first column, last column, label) — 1-based, a run of
    merged cells or a cell alone —, row 2 by column (None where the template names none), the columns that
    are location helpers, and the columns' widths (None where the template sets none)."""

    title: str
    groups: tuple[tuple[int, int, str], ...]
    columns: tuple[str | None, ...]
    helpers: frozenset[int]
    widths: tuple[float | None, ...]


@dataclass(frozen=True)
class Layout:
    """The template's layout: the record sheets by record type, the `about` sheet's header row and the
    (row, label) of each value the writer fills, the two header rows of `location`."""

    sheets: Mapping[str, SheetLayout]
    about_header: tuple[str | None, ...]
    about_labels: tuple[tuple[int, str], ...]
    about_widths: tuple[float | None, ...]
    location_titles: tuple[str | None, ...]
    location_names: tuple[str | None, ...]
    location_widths: tuple[float | None, ...]


@functools.cache
def load_layout() -> Layout:
    """The layout the library ships (`familio_mk.json`)."""
    data = json.loads(files("verso.ru.exporters").joinpath("familio_mk.json").read_text(encoding="utf-8"))
    sheets: dict[str, SheetLayout] = {}
    for record_type in _RECORD_TYPES:
        sheet = data["sheets"][record_type]
        columns = tuple(sheet["columns"])
        sheets[record_type] = SheetLayout(
            title=sheet["title"],
            groups=tuple((first, last, label) for first, last, label in sheet["groups"]),
            columns=columns,
            helpers=frozenset(c for c, name in enumerate(columns, start=1) if name in LOCATION_HELPER_HEADERS),
            widths=tuple(sheet["widths"]))
    about, location = data["about"], data["location"]
    return Layout(sheets=MappingProxyType(sheets), about_header=tuple(about["header"]),
                  about_labels=tuple((row, label) for row, label in about["labels"]),
                  about_widths=tuple(about["widths"]), location_titles=tuple(location["titles"]),
                  location_names=tuple(location["names"]), location_widths=tuple(location["widths"]))


def build_workbook(layout: Layout | None = None) -> Workbook:
    """An empty workbook of the layout: `about`, `location` and the three record sheets, their header rows
    written and nothing below them — no data row, no dropdown, no table."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    layout = layout or load_layout()
    bold, centred = Font(bold=True), Alignment(horizontal="center", vertical="center", wrap_text=True)
    wb = Workbook()
    for sheet in list(wb.worksheets):
        wb.remove(sheet)

    def widths(ws: object, values: tuple[float | None, ...]) -> None:
        for column, width in enumerate(values, start=1):
            if width is not None:
                ws.column_dimensions[get_column_letter(column)].width = width  # type: ignore[attr-defined]

    about = wb.create_sheet("about")
    for column, title in enumerate(layout.about_header, start=1):
        about.cell(1, column, title).font = bold
    for row, label in layout.about_labels:
        about.cell(row, 1, label)
    widths(about, layout.about_widths)

    location = wb.create_sheet("location")
    for column, (title, name) in enumerate(zip(layout.location_titles, layout.location_names, strict=True), start=1):
        location.cell(1, column, title).font = bold
        location.cell(2, column, name).font = bold
    location.freeze_panes = f"A{_LOCATION_DATA_START_ROW}"
    widths(location, layout.location_widths)

    for record_type in _RECORD_TYPES:
        sheet = layout.sheets[record_type]
        ws = wb.create_sheet(sheet.title)
        for first, last, label in sheet.groups:
            cell = ws.cell(1, first, label)
            cell.font, cell.alignment = bold, centred
            if last > first:
                ws.merge_cells(start_row=1, start_column=first, end_row=1, end_column=last)
        for column, name in enumerate(sheet.columns, start=1):
            if name is not None:
                ws.cell(2, column, name).font = bold
        ws.freeze_panes = f"A{_DATA_START_ROW}"
        widths(ws, sheet.widths)
    return wb
