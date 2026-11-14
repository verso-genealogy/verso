#!/usr/bin/env python3
"""
Validates the google_sheets_importer.py pipeline end-to-end by comparing
the final Familio CSV output against the source Google Sheet data.

For each (year, record_type) with an existing DSL file, reads the corresponding
Familio CSV and compares fields between sheet and CSV, reporting discrepancies.

Usage:
  python3 validate_importer_pipeline.py [--record-type TYPE] [--year YYYY] [--regenerate]
"""
# The module-level UPPERCASE names (SPREADSHEET_ID, BIRTH_STATUS_*, ...)
# are runtime-configurable per-site defaults, rebound in main() via explicit
# `global` once --village picks the site — not immutable constants.
# pyright: reportConstantRedefinition=false

import argparse
import csv
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, field
from pathlib import Path
from typing import Any

from verso.ru.gender import Gender
from verso.ru.naming import (
    modernize_orthography, canonicalize_name, canonicalize_patronymic, find_old_patronymic_by_modern, get_gender_from_name, get_gender_from_old_patronymic, validate_old_patronymic)
from verso.core import corpus_data as core_data
from verso.core import workspace
from verso.ru import corpus_data
from verso.core.corpus_data import CorpusDataError
from verso.ru.importers.google_sheets import (
    HEADER_ROWS, _get, _get_orig, _fix_status_gender, _patr_should_be_lastname, _swap_patronymic_gender, _parse_orig_names, _TITLE_WORDS, SpreadsheetFormat, FORMAT_FAMILIO_EXTENDED, FORMATS, BirthColumns, MarriageColumns, DeathColumns)
from verso.ru.messages import t

@dataclass
class SiteConfig:
    """Village-specific configuration for the validator."""
    spreadsheet_id: str
    village_filter: str
    village: str             # the village's directory, a name of the workspace's villages
    csv_prefix: str          # e.g. "Заманиловка" for CSV filenames
    dsl_prefix: str          # e.g. "zamanilovka" for DSL filenames
    header_rows: int = 2     # Number of header rows in the source sheet/CSV
    tab_map: dict[str, str] = field(default_factory=lambda: {"births": "рождение", "marriages": "брак", "deaths": "смерть"})
    year_col_map: dict[str, int] = field(default_factory=lambda: {"births": 14, "marriages": 13, "deaths": 14})
    birth_status_male: str = "экономический крестьянин"
    birth_status_female: str = "экономическая крестьянка"
    marriage_status_male: str = "экономический крестьянин"
    marriage_status_bride: str = "девка из экономических крестьян"
    marriage_status_female: str = "девица из экономических крестьян"
    death_status_male: str = "экономический крестьянин"
    death_status_female: str = "экономическая крестьянка"
    death_cause_default: str = "натуральная"
    # Local CSV source directory (None = use Google Sheets)
    csv_source_dir: str | None = None
    # Spreadsheet format (column layout)
    fmt: SpreadsheetFormat = field(default_factory=lambda: FORMAT_FAMILIO_EXTENDED)

    def base_dir(self) -> str:
        """The village's directory in the workspace."""
        return str(workspace.current().village_dir(self.village))


# Active configuration — `select()`ed by main() from --site (a village's `[sheets]`,
# village.toml). Until then a site of no village: the dataclass's defaults.
_NO_SITE = SiteConfig(spreadsheet_id="", village_filter="", village="", csv_prefix="", dsl_prefix="")
_cfg: SiteConfig = _NO_SITE

# Legacy aliases for backward compatibility within compare functions
SPREADSHEET_ID = _cfg.spreadsheet_id
VILLAGE_FILTER = _cfg.village_filter

# Default statuses used by the importer
BIRTH_STATUS_MALE = _cfg.birth_status_male
BIRTH_STATUS_FEMALE = _cfg.birth_status_female
MARRIAGE_STATUS_MALE = _cfg.marriage_status_male
MARRIAGE_STATUS_BRIDE = _cfg.marriage_status_bride
MARRIAGE_STATUS_FEMALE = _cfg.marriage_status_female
DEATH_STATUS_MALE = _cfg.death_status_male
DEATH_STATUS_FEMALE = _cfg.death_status_female
DEATH_CAUSE_DEFAULT = _cfg.death_cause_default


# What `[sheets]` may name: every SiteConfig field but those the site is found by or
# the command line sets (`village` — the directory; `fmt` — written `format`; `csv_source_dir` — --csv).
_NOT_IN_SHEETS = ("village", "fmt", "csv_source_dir")
_SHEETS_KEYS = frozenset(f for f in SiteConfig.__dataclass_fields__ if f not in _NOT_IN_SHEETS) | {"site", "format"}
# What a sheet must name: `site`, and every field the SiteConfig has no default for.
_SHEETS_REQUIRED = frozenset({"site"} | {
    name for name, f in SiteConfig.__dataclass_fields__.items()
    if name not in _NOT_IN_SHEETS and f.default is MISSING and f.default_factory is MISSING})
# The values that are not a string, and what each must be; every other key holds a string.
_SHEETS_NOT_STR: dict[str, tuple[Callable[[Any], bool], str]] = {
    "header_rows": (lambda v: isinstance(v, int) and not isinstance(v, bool), "corpus_data.expected_integer"),
    "tab_map": (lambda v: isinstance(v, dict) and all(isinstance(x, str) for x in v.values()),  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                "importers.validation.expected_string_table"),
    "year_col_map": (lambda v: isinstance(v, dict) and all(  # pyright: ignore[reportUnknownMemberType]
        isinstance(x, int) and not isinstance(x, bool) for x in v.values()),  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                     "importers.validation.expected_integer_table"),
}


def _expected(key: str) -> str:
    """What a value of `[sheets]` must be, in the interface's words (its catalog key)."""
    words = {"corpus_data.expected_integer": t("corpus_data.expected_integer"),
             "corpus_data.expected_string": t("corpus_data.expected_string"),
             "importers.validation.expected_string_table": t("importers.validation.expected_string_table"),
             "importers.validation.expected_integer_table": t("importers.validation.expected_integer_table")}
    return str(words[key])


def _check_sheets(path: Path, sheets: Mapping[str, Any]) -> None:
    """A village's `[sheets]` as SiteConfig takes it: no unknown key, none missing, each value its type."""
    unknown = sorted(set(sheets) - _SHEETS_KEYS)
    if unknown:
        raise CorpusDataError(str(t("importers.validation.unknown_key", path=path, key=unknown[0])))
    missing = sorted(_SHEETS_REQUIRED - set(sheets))
    if missing:
        raise CorpusDataError(str(t("importers.validation.missing_key", path=path, key=missing[0])))
    for key, value in sheets.items():
        fits, expected = _SHEETS_NOT_STR.get(key, (lambda v: isinstance(v, str), "corpus_data.expected_string"))
        if not fits(value):
            raise CorpusDataError(str(t("importers.validation.wrong_type", path=path, key=key, expected=_expected(expected))))


@dataclass(frozen=True)
class _Survey:
    """Every village's sheet: site → the villages naming it, and the village files that cannot be read."""
    villages: dict[str, list[str]]
    unread: list[str]


def _survey() -> _Survey:
    ws = workspace.current()
    found: dict[str, list[str]] = {}
    unread: list[str] = []
    for village in ws.villages:
        path = ws.root / village / core_data.VILLAGE_FILE
        try:
            sheets = corpus_data.village(path.parent).sheets
            if sheets is None:
                continue
            site = sheets.get("site")
            if site is None:
                raise CorpusDataError(str(t("importers.validation.missing_key", path=path, key="site")))
            if not isinstance(site, str):
                raise CorpusDataError(str(t("importers.validation.wrong_type", path=path, key="site",
                                            expected=t("corpus_data.expected_string"))))
        except CorpusDataError as e:
            # One village's slip does not hide every other village's sheet: it is said
            # when its own site is asked for, and is not found.
            unread.append(str(e))
            continue
        found.setdefault(site, []).append(village)
    return _Survey(found, unread)


def sites() -> dict[str, str]:
    """site → village: every village of the workspace whose village.toml names a sheet,
    a site two villages name left out (`site_config` refuses it)."""
    return {site: villages[0] for site, villages in _survey().villages.items() if len(villages) == 1}


def site_config(site: str) -> SiteConfig:
    """The SiteConfig of the village whose `[sheets] site` is `site`."""
    survey = _survey()
    villages = survey.villages.get(site, [])
    if not villages:
        known = ", ".join(sorted(survey.villages)) or str(t("importers.validation.none_known"))
        unread = str(t("importers.validation.unread", unread="; ".join(survey.unread))) if survey.unread else ""
        raise CorpusDataError(str(t("importers.validation.no_sheet", site=site, known=known, unread=unread)))
    if len(villages) > 1:
        raise CorpusDataError(str(t("importers.validation.two_villages", site=site, villages=", ".join(villages))))
    village = villages[0]
    path = workspace.current().root / village / core_data.VILLAGE_FILE
    sheets = dict(corpus_data.village(path.parent).sheets or {})
    _check_sheets(path, sheets)
    fmt = sheets.pop("format", "familio-extended")
    if fmt not in FORMATS:
        raise CorpusDataError(str(t("importers.validation.format", path=path, formats=", ".join(sorted(FORMATS)))))
    sheets.pop("site")
    return SiteConfig(village=village, fmt=FORMATS[fmt], **sheets)


def select(cfg: SiteConfig) -> None:
    """Make `cfg` the active site: `_cfg` and the legacy UPPERCASE globals the compare functions read."""
    global _cfg, SPREADSHEET_ID, VILLAGE_FILTER
    global BIRTH_STATUS_MALE, BIRTH_STATUS_FEMALE, MARRIAGE_STATUS_MALE
    global MARRIAGE_STATUS_BRIDE, MARRIAGE_STATUS_FEMALE
    global DEATH_STATUS_MALE, DEATH_STATUS_FEMALE, DEATH_CAUSE_DEFAULT
    global FIELD_TO_SHEET_COL
    _cfg = cfg
    SPREADSHEET_ID = cfg.spreadsheet_id
    VILLAGE_FILTER = cfg.village_filter
    BIRTH_STATUS_MALE = cfg.birth_status_male
    BIRTH_STATUS_FEMALE = cfg.birth_status_female
    MARRIAGE_STATUS_MALE = cfg.marriage_status_male
    MARRIAGE_STATUS_BRIDE = cfg.marriage_status_bride
    MARRIAGE_STATUS_FEMALE = cfg.marriage_status_female
    DEATH_STATUS_MALE = cfg.death_status_male
    DEATH_STATUS_FEMALE = cfg.death_status_female
    DEATH_CAUSE_DEFAULT = cfg.death_cause_default
    FIELD_TO_SHEET_COL = build_field_to_sheet_col(cfg.fmt)


@dataclass
class Discrepancy:
    year: int
    record_type: str
    record_num: str
    field: str
    sheet_val: str
    csv_val: str
    sheet_row_idx: int | None = None


# ─── Field-to-column mapping for --fix ───────────────────────────────────────


def build_field_to_sheet_col(fmt: SpreadsheetFormat) -> dict[tuple[str, str], int | None]:
    """Build (record_type, field_name) → sheet column index mapping from format config.

    Maps to the SOURCE column that should be edited (orth column for "совр. орф."
    fields, canonical column for "совр." fields).
    """
    bc = fmt.birth_cols
    mc = fmt.marriage_cols
    dc = fmt.death_cols
    return {
        # Births
        ("births", "Лист"): bc.PAGE,
        ("births", "Архив"): bc.ARCHIVE,
        ("births", "Фонд"): bc.FUND,
        ("births", "Опись"): bc.INVENTORY,
        ("births", "Дело"): bc.CASE,
        ("births", "Рожд. День"): bc.B_DAY,
        ("births", "Крещ. День"): bc.K_DAY,
        ("births", "Имя реб. (совр. орф.)"): bc.CHILD_NAME,
        ("births", "Имя реб. (совр.)"): bc.CHILD_NAME_CANON,
        ("births", "Отец: Н.П."): bc.FATHER_RESIDENCE,
        ("births", "Отец: Статус"): bc.FATHER_STATUS,
        ("births", "Отец: Фамилия"): bc.FATHER_LAST_NAME,
        ("births", "Отец: Имя (совр. орф.)"): bc.FATHER_NAME,
        ("births", "Отец: Отчество (совр. орф.)"): bc.FATHER_PATR,
        ("births", "Отец: Имя (совр.)"): bc.FATHER_NAME_CANON,
        ("births", "Отец: Отчество (совр.)"): bc.FATHER_PATR_CANON,
        ("births", "Мать: Статус"): bc.MOTHER_STATUS,
        ("births", "Мать: Фамилия"): bc.MOTHER_LAST_NAME,
        ("births", "Мать: Имя (совр. орф.)"): bc.MOTHER_NAME,
        ("births", "Мать: Отчество (совр. орф.)"): bc.MOTHER_PATR,
        ("births", "Мать: Имя (совр.)"): bc.MOTHER_NAME_CANON,
        ("births", "Мать: Отчество (совр.)"): bc.MOTHER_PATR_CANON,
        ("births", "Восприемник 1: Статус"): bc.GP1_STATUS,
        ("births", "Восприемник 1: Н.П."): bc.GP1_RESIDENCE,
        ("births", "Восприемник 1: Имя (совр. орф.)"): bc.GP1_NAME,
        ("births", "Восприемник 1: Отчество (совр. орф.)"): bc.GP1_PATR,
        ("births", "Восприемник 1: ФИО (совр.)"): bc.GP1_FIO,
        ("births", "Восприемник 2: Статус"): bc.GP2_STATUS,
        ("births", "Восприемник 2: Н.П."): bc.GP2_RESIDENCE,
        ("births", "Восприемник 2: Имя (совр. орф.)"): bc.GP2_NAME,
        ("births", "Восприемник 2: Отчество (совр. орф.)"): bc.GP2_PATR,
        ("births", "Восприемник 2: Имя (совр.)"): bc.GP2_NAME,
        ("births", "Восприемник 2: ФИО (совр.)"): bc.GP2_FIO,
        ("births", "Священник: ФИО"): bc.PRIEST_FIO,
        ("births", "Дьякон: ФИО"): bc.DEACON_FIO,
        ("births", "Псаломщик: ФИО"): bc.DYACHOK_FIO,

        # Marriages
        ("marriages", "Лист"): mc.PAGE,
        ("marriages", "Архив"): mc.ARCHIVE,
        ("marriages", "Фонд"): mc.FUND,
        ("marriages", "Опись"): mc.INVENTORY,
        ("marriages", "Дело"): mc.CASE,
        ("marriages", "День"): mc.W_DAY,
        ("marriages", "Жених: Н.П."): mc.GROOM_RESIDENCE,
        ("marriages", "Жених: Статус"): mc.GROOM_STATUS,
        ("marriages", "Жених: Фамилия"): mc.GROOM_LAST_NAME,
        ("marriages", "Жених: Имя (совр. орф.)"): mc.GROOM_NAME,
        ("marriages", "Жених: Отчество (совр. орф.)"): mc.GROOM_PATR,
        ("marriages", "Жених: Имя (совр.)"): mc.GROOM_NAME_CANON,
        ("marriages", "Жених: Отчество (совр.)"): mc.GROOM_PATR_CANON,
        ("marriages", "Жених: Номер брака"): mc.GROOM_MARRIAGE_NUM,
        ("marriages", "Невеста: Н.П."): mc.BRIDE_RESIDENCE,
        ("marriages", "Невеста: Статус"): mc.BRIDE_STATUS,
        ("marriages", "Невеста: Фамилия"): mc.BRIDE_LAST_NAME,
        ("marriages", "Невеста: Имя (совр. орф.)"): mc.BRIDE_NAME,
        ("marriages", "Невеста: Отчество (совр. орф.)"): mc.BRIDE_PATR,
        ("marriages", "Невеста: Имя (совр.)"): mc.BRIDE_NAME_CANON,
        ("marriages", "Невеста: Отчество (совр.)"): mc.BRIDE_PATR_CANON,
        ("marriages", "Невеста: Номер брака"): mc.BRIDE_MARRIAGE_NUM,
        ("marriages", "Поручитель 1: Статус"): mc.W1_STATUS,
        ("marriages", "Поручитель 1: Н.П."): mc.W1_RESIDENCE,
        ("marriages", "Поручитель 1: Фамилия"): mc.W1_LAST_NAME,
        ("marriages", "Поручитель 1: Имя (совр. орф)"): mc.W1_NAME,
        ("marriages", "Поручитель 1: Отчество (совр. орф)"): mc.W1_PATR,
        ("marriages", "Поручитель 1: Имя (совр.)"): mc.W1_NAME_CANON,
        ("marriages", "Поручитель 1: Отчество (совр.)"): mc.W1_PATR_CANON,
        ("marriages", "Поручитель 1: ФИО (совр.)"): mc.W1_FIO,
        ("marriages", "Поручитель 2: Фамилия"): mc.W2_LAST_NAME,
        ("marriages", "Поручитель 2: Статус"): mc.W2_STATUS,
        ("marriages", "Поручитель 2: Н.П."): mc.W2_RESIDENCE,
        ("marriages", "Поручитель 2: Имя (совр. орф)"): mc.W2_NAME,
        ("marriages", "Поручитель 2: Отчество (совр. орф)"): mc.W2_PATR,
        ("marriages", "Поручитель 2: Имя (совр.)"): mc.W2_NAME_CANON,
        ("marriages", "Поручитель 2: Отчество (совр.)"): mc.W2_PATR_CANON,
        ("marriages", "Поручитель 2: ФИО (совр.)"): mc.W2_FIO,
        ("marriages", "Священник: ФИО"): mc.PRIEST_FIO,
        ("marriages", "Дьякон: ФИО"): mc.DEACON_FIO,
        ("marriages", "Псаломщик: ФИО"): mc.DYACHOK_FIO,

        # Deaths
        ("deaths", "Лист"): dc.PAGE,
        ("deaths", "Архив"): dc.ARCHIVE,
        ("deaths", "Фонд"): dc.FUND,
        ("deaths", "Опись"): dc.INVENTORY,
        ("deaths", "Дело"): dc.CASE,
        ("deaths", "День (смерть)"): dc.D_DAY,
        ("deaths", "День (погребение)"): dc.B_DAY,
        ("deaths", "Лет"): dc.AGE,
        ("deaths", "Причина смерти"): dc.CAUSE,
        ("deaths", "родство"): dc.RELATIONSHIP,
        ("deaths", "Умерший: Н.П."): dc.DEC_RESIDENCE,
        ("deaths", "Умерший: статус"): dc.DEC_STATUS,
        ("deaths", "Умерший: Фамилия"): dc.DEC_LAST_NAME,
        ("deaths", "Умерший: Имя (совр. орф.)"): dc.DEC_NAME,
        ("deaths", "Умерший: Отчество (совр. орф.)"): dc.DEC_PATR,
        ("deaths", "Умерший: Имя"): dc.DEC_NAME_CANON,
        ("deaths", "Умерший: Отчество"): dc.DEC_PATR_CANON,
        ("deaths", "Родственник: Н.П."): dc.REL_RESIDENCE,
        ("deaths", "Родственник: статус"): dc.REL_STATUS,
        ("deaths", "Родственник: Фамилия"): dc.REL_LAST_NAME,
        ("deaths", "Родственник: Имя (совр. орф.)"): dc.REL_NAME,
        ("deaths", "Родственник: Отчество (совр. орф.)"): dc.REL_PATR,
        ("deaths", "Родственник: Имя"): dc.REL_NAME_CANON,
        ("deaths", "Родственник: Отчество"): dc.REL_PATR_CANON,
        ("deaths", "Священник: ФИО"): dc.PRIEST_FIO,
        ("deaths", "Дьякон: ФИО"): dc.DEACON_FIO,
        ("deaths", "Псаломщик: ФИО"): dc.DYACHOK_FIO,
    }


# Module-level default (overwritten in main() based on site selection)
FIELD_TO_SHEET_COL = build_field_to_sheet_col(FORMAT_FAMILIO_EXTENDED)


@dataclass
class ValidationResult:
    record_type: str
    years_checked: int = 0
    years_ok: int = 0
    years_with_issues: int = 0
    total_fields: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)
    missing_csv: list[int] = field(default_factory=list)
    count_mismatches: list[tuple[int, int, int]] = field(default_factory=list)


# ─── Sheet fetching ───────────────────────────────────────────────────────────

def fetch_all_sheets(spreadsheet_id, tab_names=("рождение", "брак", "смерть")):
    """Fetch all sheet tabs. Returns {tab_name: all_rows}."""
    import gspread
    gc = gspread.oauth()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    result = {}
    for tab in tab_names:
        target = tab.lower()
        for ws in spreadsheet.worksheets():
            if ws.title.lower() == target:
                result[tab] = ws.get_all_values()
                break
    return result


def fetch_local_csvs(csv_dir, tab_map):
    """Read source data from local CSV files instead of Google Sheets.

    Args:
        csv_dir: Directory containing source CSV files.
        tab_map: dict mapping record types to tab names, e.g.
                 {"births": "рождение", "marriages": "брак", "deaths": "смерть"}

    Returns {tab_name: all_rows} — same format as fetch_all_sheets().
    """
    import csv as csv_mod
    # Map tab names to file suffixes
    tab_to_suffix = {}
    for rt, tab in tab_map.items():
        if rt == "births":
            tab_to_suffix[tab] = "РОЖДЕНИЕ"
        elif rt == "marriages":
            tab_to_suffix[tab] = "БРАК"
        elif rt == "deaths":
            tab_to_suffix[tab] = "СМЕРТЬ"

    result = {}
    village = _cfg.village_filter if _cfg else ""
    for tab, suffix in tab_to_suffix.items():
        # Find CSV file matching village name and record type suffix
        matched = None
        for fname in sorted(os.listdir(csv_dir)):
            if fname.endswith(".csv") and suffix in fname:
                # Prefer file matching village name
                if village and village in fname:
                    matched = os.path.join(csv_dir, fname)
                    break
                if matched is None:
                    matched = os.path.join(csv_dir, fname)
        if matched:
            with open(matched, encoding="utf-8") as f:
                result[tab] = list(csv_mod.reader(f))
    return result


def split_by_year(all_rows, year_col_idx, village=None):
    """Split rows by year, optionally filtering by village.

    Returns {year: [(global_row_idx, row), ...]} where global_row_idx is the
    0-based index into all_rows (so gspread row number = global_row_idx + 1).
    """
    # Local CSV exports always have 1 header row; Google Sheets may have more
    if _cfg and _cfg.csv_source_dir:
        header_rows = 1
    else:
        header_rows = _cfg.header_rows if _cfg else HEADER_ROWS
    by_year = {}
    for i, row in enumerate(all_rows[header_rows:], start=header_rows):
        if len(row) <= year_col_idx:
            continue
        year_str = str(row[year_col_idx]).strip()
        if not year_str:
            continue
        try:
            year = int(year_str)
        except ValueError:
            continue
        if village:
            row_village = _get(row, 6)
            if row_village.lower() != village.lower():
                continue
        by_year.setdefault(year, []).append((i, row))
    return by_year


# ─── CSV reading ──────────────────────────────────────────────────────────────

# 0-based column index for the year value in each Familio CSV type
CSV_YEAR_COL = {"births": 14, "marriages": 13, "deaths": 14}


def read_familio_csv(path):
    """Read a Familio CSV and return list of rows as dicts (by header name)."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = []
        for row in reader:
            d: dict[object, str] = {}
            for i, _h in enumerate(headers):
                d[i] = row[i] if i < len(row) else ""
            d["_headers"] = headers
            rows.append(d)
        return rows


def find_csv(year, record_type):
    """Find the Familio CSV for a given year and record type."""
    year_dir = os.path.join(_cfg.base_dir(), str(year))
    suffix = {"births": "births_familio.csv", "marriages": "marriages_familio.csv",
              "deaths": "deaths_familio.csv"}[record_type]
    csv_path = os.path.join(year_dir, f"{_cfg.csv_prefix}_{year}_{suffix}")
    if os.path.exists(csv_path):
        return csv_path
    return None


def find_dsl(year, record_type):
    """Find the DSL .py file for a given year and record type."""
    year_dir = os.path.join(_cfg.base_dir(), str(year))
    suffix = {"births": "births", "marriages": "marriages", "deaths": "deaths"}[record_type]
    py_path = os.path.join(year_dir, f"{_cfg.dsl_prefix}_{suffix}_{year}.py")
    if os.path.exists(py_path):
        return py_path
    return None


def _read_csv_rows_for_year(year, record_type, regenerate=False):
    """Read CSV rows for *year* from both year X and year X+1 CSVs.

    Carryover records (e.g. December births from 1785) live in the 1786 DSL/CSV
    with an explicit year=1785 override.  This function aggregates rows from both
    CSVs and filters to only those whose year column matches *year*.

    Returns (csv_rows, regenerated_years) or (None, regenerated_years) when no
    CSV could be found even after regeneration.  *regenerated_years* is a set of
    years whose DSL was re-run.
    """
    year_col = CSV_YEAR_COL[record_type]
    regenerated = set()

    all_rows = []
    for y in (year, year + 1):
        csv_path = find_csv(y, record_type)
        if not csv_path and regenerate:
            if find_dsl(y, record_type) and regenerate_csv(y, record_type):
                csv_path = find_csv(y, record_type)
                regenerated.add(y)
        if csv_path:
            all_rows.extend(read_familio_csv(csv_path))

    if not all_rows:
        return None, regenerated

    # Filter to rows whose year column matches the requested year
    filtered = [r for r in all_rows if r.get(year_col, "").strip() == str(year)]
    return filtered, regenerated


# ─── Name resolution (mirrors importer logic) ────────────────────────────────

def resolve_name_patr(row, name_col, patr_col, canon_name_col, canon_patr_col,
                      orig_dict=None, orig_key=None):
    """Resolve name and patronymic using the importer's priority chain.

    Priority: ORIG_NAMES → orthographic columns → canonical columns.
    Then apply _patr_should_be_lastname and validate_old_patronymic filters.

    Returns (name, patr, last_name_from_patr) where last_name_from_patr is set
    if the patronymic was reclassified as a last name.
    """
    # Fallbacks from sheet columns
    name_fb = _get(row, name_col) or _get(row, canon_name_col) if canon_name_col is not None else _get(row, name_col)
    patr_fb = _get(row, patr_col) or (_get(row, canon_patr_col) if canon_patr_col is not None else "")

    # Try orig_names first
    if orig_dict and orig_key and orig_key in orig_dict:
        orig_val = orig_dict[orig_key]
        name = orig_val[0]
        patr = orig_val[1] if len(orig_val) > 1 else ""
        name = name or name_fb
        patr = patr or patr_fb
    else:
        name, patr = name_fb, patr_fb

    last_name_from_patr = None

    if not name:
        return "", "", None

    # Title word in name field
    if name.lower() in _TITLE_WORDS:
        name = patr or "?"
        patr = ""

    # "Имена" placeholder
    if name == "Имена":
        name = "?"
        patr = ""

    # Patr should be lastname
    if patr and _patr_should_be_lastname(name, patr):
        last_name_from_patr = patr
        patr = ""

    # Drop invalid old patronymics (long-form modern ones from canonical columns)
    if patr and not validate_old_patronymic(modernize_orthography(patr)):
        patr = ""

    return name, patr, last_name_from_patr


# Words that indicate comment text, not person names, in orig_names parts.
_ORIG_NON_NAME_WORDS = frozenset([
    "возраст", "дата", "имя", "населенный", "незаконнорожденная",
    "незаконнорожденный", "отчество", "помещик", "помещица",
    "родители", "свидетели", "фамилия", "звание", "примечание",
    "восприемники",
])


def _parse_orig_parts(orig_str):
    """Parse 'Имена в МК:' string into name-only parts, filtering out comments.

    Returns a list of name parts (e.g. ["Федор Александров", "Анна Иванова"]).
    Returns [] if the string is missing, empty, or doesn't start with the
    'Имена в МК:' prefix (indicating it's a comment, not original names).
    Semicolon-separated parts whose first word is a known non-name word
    (e.g. 'Возраст', 'Отчество', 'Родители') are filtered out.
    """
    if not orig_str:
        return []
    if not orig_str.startswith("Имена в МК:"):
        return []
    text = orig_str.removeprefix("Имена в МК:").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(";")]
    result = []
    for part in parts:
        if not part:
            continue
        # Strip trailing comment after " - " (e.g. "Федор Данилов - отчествно...")
        if " - " in part:
            part = part.split(" - ", 1)[0].strip()
        if not part:
            continue
        first_token = part.split(None, 1)[0] if part else ""
        if first_token.lower() in _ORIG_NON_NAME_WORDS:
            continue
        result.append(part)
    return result


def resolve_name_patr_marriage_orig(orig_parts, orig_idx, name_col, patr_col,
                                    canon_name_col, canon_patr_col, row):
    """Marriage-specific orig resolution using positional orig_parts."""
    name_fb = _get(row, name_col) or (_get(row, canon_name_col) if canon_name_col is not None else "")
    patr_fb = _get(row, patr_col) or (_get(row, canon_patr_col) if canon_patr_col is not None else "")

    if orig_idx < len(orig_parts) and orig_parts[orig_idx]:
        tokens = orig_parts[orig_idx].split(" ", 1)
        name = tokens[0]
        patr = tokens[1] if len(tokens) > 1 else ""
        name = name or name_fb
        patr = patr or patr_fb
    else:
        name, patr = name_fb, patr_fb

    last_name_from_patr = None
    if not name:
        return "", "", None

    if name.lower() in _TITLE_WORDS:
        name = patr or "?"
        patr = ""

    if name == "Имена":
        name = "?"
        patr = ""

    if patr and _patr_should_be_lastname(name, patr):
        last_name_from_patr = patr
        patr = ""

    if patr and not validate_old_patronymic(modernize_orthography(patr)):
        patr = ""

    return name, patr, last_name_from_patr


def _extract_lastname_from_fio(fio, name):
    """Extract lastname prefix from FIO column.

    Handles both 2-part ("Амвросимов Иосиф") and 3-part ("Бобчинский Лев Петрович") FIOs.
    E.g. fio="Амвросимов Иосиф", name="Иосиф" → "Амвросимов"
         fio="Бобчинский Лев Петрович", name="Лев" → "Бобчинский"
    """
    if not fio or not name:
        return None
    parts = fio.split()

    def _name_variants(n):
        """Return list of name variants to match against."""
        variants = [n]
        n_mod = modernize_orthography(n)
        if n_mod != n:
            variants.append(n_mod)
        try:
            g = get_gender_from_name(n_mod)
            n_can = canonicalize_name(n_mod, g) if g else None
            if n_can and n_can not in variants:
                variants.append(n_can)
        except Exception:
            pass
        return variants

    name_vars = _name_variants(name)

    # 2-part: "Lastname Name" → name is last part
    if len(parts) >= 2:
        for nv in name_vars:
            if parts[-1] == nv:
                return " ".join(parts[:-1])

    # 3-part: "Lastname Name Patronymic" → name is second part
    if len(parts) >= 3:
        for nv in name_vars:
            if parts[1] == nv:
                return parts[0]

    return None


def apply_transforms(name, patr, last_name=None, gender=None):
    """Apply the same transformations as Person.__init__ + get_canonical_*.

    Returns dict with: name_modern, patr_modern, name_canon, patr_canon,
    last_name_modern, fio.
    When *gender* is provided, it is used directly for canonicalization instead
    of inferring it from the name (which can be ambiguous for names like Лука).
    """
    name_modern = modernize_orthography(name) if name else ""
    patr_modern = modernize_orthography(patr) if patr else ""
    last_name_modern = modernize_orthography(last_name) if last_name else ""

    name_canon = ""
    if name_modern and "?" not in name_modern:
        try:
            g = gender if gender is not None else get_gender_from_name(name_modern)
            if g is None and patr_modern:
                g = get_gender_from_old_patronymic(patr_modern)
            name_canon = canonicalize_name(name_modern, g)
        except Exception:
            name_canon = name_modern
    elif name_modern and "?" in name_modern:
        # Preserve uncertain names as-is (matches DSL behavior)
        name_canon = name_modern

    patr_canon = ""
    if patr_modern:
        try:
            patr_canon = canonicalize_patronymic(patr_modern)
        except ValueError:
            patr_canon = ""

    fio = " ".join(filter(None, [last_name_modern, name_canon, patr_canon]))

    return {
        "name_modern": name_modern,
        "patr_modern": patr_modern,
        "name_canon": name_canon,
        "patr_canon": patr_canon,
        "last_name_modern": last_name_modern,
        "fio": fio,
    }


# ─── Comparison helpers ───────────────────────────────────────────────────────

def _reconstruct_age(years, months, weeks, days):
    """Reconstruct age string from split CSV columns."""
    if years:
        return years
    if months:
        return f"{months} м"
    if weeks:
        return f"{weeks} н"
    if days:
        return f"{days} д"
    return ""


def _s(val):
    """Normalize a value to string for comparison."""
    if val is None:
        return ""
    s = str(val).strip()
    # "??" or "?" in the sheet means unknown — the importer converts this to None/empty
    if s in ("?", "??"):
        return ""
    return s


def _cmp(field_name, sheet_val, csv_val, year, record_type, record_num, result,
         sheet_row_idx=None):
    """Compare two values and record discrepancy if different."""
    s = _s(sheet_val)
    c = _s(csv_val)
    result.total_fields += 1
    if s != c:
        result.discrepancies.append(Discrepancy(
            year=year, record_type=record_type, record_num=record_num,
            field=field_name, sheet_val=s, csv_val=c,
            sheet_row_idx=sheet_row_idx,
        ))


def _apply_default_status(sheet_status, gender_str, record_type):
    """Apply default status based on gender, matching importer defaults."""
    if sheet_status:
        return sheet_status
    if record_type == "births":
        if gender_str in ("жен", "ж", "женский"):
            return BIRTH_STATUS_FEMALE
        return BIRTH_STATUS_MALE
    elif record_type == "deaths":
        if gender_str in ("жен", "ж", "женский"):
            return DEATH_STATUS_FEMALE
        return DEATH_STATUS_MALE
    return ""


def _apply_default_residence(sheet_residence, default_village):
    """Apply default residence."""
    if sheet_residence:
        return sheet_residence
    return default_village


# ─── Birth comparison ─────────────────────────────────────────────────────────

def _build_sequential_lookup(rows: list[Any], key_fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Build a lookup that handles duplicate keys by sequential matching.

    Returns a function that, given a key, returns the next unmatched row for that key.
    Supports '?' as a wildcard in any key position — when exact match fails and
    the key contains '?', searches all groups for partial matches.
    """
    from collections import defaultdict, deque
    groups = defaultdict(deque)
    for row in rows:
        k = key_fn(row)
        groups[k].append(row)

    def lookup(key):
        q = groups.get(key)
        if q:
            return q.popleft()
        # Wildcard fallback: if key contains '?' or '', try partial match
        if "?" in key or "" in key:
            for gk, gq in groups.items():
                if not gq:
                    continue
                if all(kv in ("?", "", gv) for kv, gv in zip(key, gk, strict=True)):
                    return gq.popleft()
        return None

    return lookup


def _make_cmp(year, record_type, rec_num, row_idx, result):
    """Bind the common _cmp() arguments for one sheet row."""
    def cmp(field_name, sheet_val, csv_val):
        _cmp(field_name, sheet_val, csv_val, year, record_type, rec_num, result,
             sheet_row_idx=row_idx)
    return cmp


def _compare_clergy(cmp, srow, cols, csv_row, priest_ix, deacon_ix, dyachok_ix):
    """Compare the clergy FIO columns (same three fields in every record type)."""
    cmp("Священник: ФИО", _get(srow, cols.PRIEST_FIO), csv_row[priest_ix])
    cmp("Дьякон: ФИО", _get(srow, cols.DEACON_FIO), csv_row[deacon_ix])
    cmp("Псаломщик: ФИО", _get(srow, cols.DYACHOK_FIO), csv_row[dyachok_ix])


def _compare_birth_parent(
        cmp, srow, orig, role, label, csv_row, csv_ix, gender,
        name_col, patr_col, name_canon_col, patr_canon_col, last_name_col,
        status_col, default_status, residence_col, default_village):
    """Compare a birth father/mother block.

    csv_ix = (residence, status, last_name, name_modern, patr_modern,
    name_canon, patr_canon) CSV indices; residence index is None for the
    mother (the sheet carries no mother residence).
    """
    n, p, ln_from_p = resolve_name_patr(
        srow, name_col, patr_col, name_canon_col, patr_canon_col, orig, role)
    sheet_ln = _get(srow, last_name_col) or (ln_from_p or "")
    tr = apply_transforms(n, p, sheet_ln, gender=gender)

    status = _get(srow, status_col) or default_status

    if csv_ix[0] is not None:
        residence = _apply_default_residence(_get(srow, residence_col), default_village)
        cmp(f"{label}: Н.П.", residence, csv_row[csv_ix[0]])
    cmp(f"{label}: Статус", status, csv_row[csv_ix[1]])
    cmp(f"{label}: Фамилия", tr["last_name_modern"], csv_row[csv_ix[2]])
    cmp(f"{label}: Имя (совр. орф.)", tr["name_modern"], csv_row[csv_ix[3]])
    cmp(f"{label}: Отчество (совр. орф.)", tr["patr_modern"], csv_row[csv_ix[4]])
    cmp(f"{label}: Имя (совр.)", tr["name_canon"], csv_row[csv_ix[5]])
    cmp(f"{label}: Отчество (совр.)", tr["patr_canon"], csv_row[csv_ix[6]])


def _compare_birth_godparent(
        cmp, srow, orig, role, label, csv_row, csv_base,
        name_col, fio_col, patr_col, last_name_col, status_col, residence_col,
        default_village, gender_based_default):
    """Compare one birth godparent (восприемник) block.

    GP1 and GP2 differ only in columns, CSV base index and the empty-status
    default: GP1 defaults to the male birth status then gender-fixes it;
    GP2 (gender_based_default=True) picks the default by the detected name
    gender.
    """
    gn_fb = _get(srow, name_col) or _get(srow, fio_col)
    gp_orig = orig.get(role, (gn_fb, _get(srow, patr_col)))
    gn, gp = gp_orig[0], gp_orig[1] if len(gp_orig) > 1 else ""
    orig_surname = gp_orig[2] if len(gp_orig) > 2 else ""
    gn = gn or gn_fb
    gp = gp or _get(srow, patr_col)
    # Apply title/patr-as-lastname/validate logic
    last_name_from_patr = orig_surname or None
    if gn and gn.lower() in _TITLE_WORDS:
        gn = gp or "?"
        gp = ""
    if gp and _patr_should_be_lastname(gn, gp):
        last_name_from_patr = gp
        gp = ""
        # Issue 1: multi-word patronymic — split out valid old patronymic
        if last_name_from_patr and " " in last_name_from_patr:
            parts = last_name_from_patr.split(" ", 1)
            if validate_old_patronymic(modernize_orthography(parts[0])):
                gp = parts[0]
                last_name_from_patr = parts[1]
        # Issue 2: fallback to sheet patronymic column
        if last_name_from_patr and not gp:
            sheet_patr = _get(srow, patr_col)
            if sheet_patr and validate_old_patronymic(modernize_orthography(sheet_patr)):
                gp = sheet_patr
    if gp and not validate_old_patronymic(modernize_orthography(gp)):
        gp = ""
    # Issue 4: swap patronymic gender if it conflicts with name gender
    if gp:
        gp_mod = modernize_orthography(gp)
        gp_gender = get_gender_from_old_patronymic(gp_mod)
        gn_gender = get_gender_from_name(gn)
        if gp_gender and gn_gender and gp_gender != gn_gender:
            swapped = _swap_patronymic_gender(gp_mod)
            if swapped and validate_old_patronymic(swapped):
                gp = swapped
    # Extract lastname from dedicated column or FIO column
    gp_last_name = _get(srow, last_name_col) if last_name_col is not None else ""
    if not last_name_from_patr:
        last_name_from_patr = gp_last_name or _extract_lastname_from_fio(
            _get(srow, fio_col), gn)
    tr = apply_transforms(gn, gp, last_name=last_name_from_patr)

    status = _get(srow, status_col)
    name_gender = get_gender_from_name(modernize_orthography(gn)) if gn else None
    if gender_based_default and not status:
        status = BIRTH_STATUS_FEMALE if name_gender == Gender.FEMALE else BIRTH_STATUS_MALE
    else:
        status = status or _apply_default_status("", "", "births")
        status = _fix_status_gender(status, name_gender)
    residence = _apply_default_residence(_get(srow, residence_col), default_village)

    cmp(f"{label}: Статус", status, csv_row[csv_base])
    cmp(f"{label}: Н.П.", residence, csv_row[csv_base + 1])
    cmp(f"{label}: Имя (совр. орф.)", tr["name_modern"], csv_row[csv_base + 3])
    cmp(f"{label}: Отчество (совр. орф.)", tr["patr_modern"], csv_row[csv_base + 4])
    cmp(f"{label}: Имя (совр.)", tr["name_canon"], csv_row[csv_base + 5])
    cmp(f"{label}: Отчество (совр.)", tr["patr_canon"], csv_row[csv_base + 6])
    cmp(f"{label}: ФИО (совр.)", tr["fio"], csv_row[csv_base + 7])


def _compare_marriage_principal(
        cmp, srow, orig_parts, orig_idx, label, csv_row, csv_ix, gender,
        name_col, patr_col, name_canon_col, patr_canon_col,
        orig_name_col, orig_patr_col, last_name_col,
        status_col, default_status, residence_col, marriage_num_col,
        default_village):
    """Compare the groom/bride block; returns the advanced orig_idx.

    csv_ix = (residence, status, last_name, name_modern, patr_modern,
    name_canon, patr_canon, marriage_num) CSV indices.
    """
    n, p, ln_from_p = resolve_name_patr_marriage_orig(
        orig_parts, orig_idx, name_col, patr_col,
        name_canon_col, patr_canon_col, srow)
    orig_idx += 1
    # Override with dedicated orig columns
    if orig_name_col is not None:
        orig_n = _get_orig(srow, orig_name_col)
        orig_p = _get_orig(srow, orig_patr_col) if orig_patr_col else ""
        if orig_n:
            n, p = orig_n, orig_p
    sheet_ln = _get(srow, last_name_col) or (ln_from_p or "")
    tr = apply_transforms(n, p, sheet_ln, gender=gender)

    residence = _apply_default_residence(_get(srow, residence_col), default_village)
    status = _get(srow, status_col) or default_status

    cmp(f"{label}: Н.П.", residence, csv_row[csv_ix[0]])
    cmp(f"{label}: Статус", status, csv_row[csv_ix[1]])
    cmp(f"{label}: Фамилия", tr["last_name_modern"], csv_row[csv_ix[2]])
    cmp(f"{label}: Имя (совр. орф.)", tr["name_modern"], csv_row[csv_ix[3]])
    cmp(f"{label}: Отчество (совр. орф.)", tr["patr_modern"], csv_row[csv_ix[4]])
    cmp(f"{label}: Имя (совр.)", tr["name_canon"], csv_row[csv_ix[5]])
    cmp(f"{label}: Отчество (совр.)", tr["patr_canon"], csv_row[csv_ix[6]])
    cmp(f"{label}: Номер брака", _get(srow, marriage_num_col), csv_row[csv_ix[7]])
    return orig_idx


def _compare_marriage_witness(
        cmp, srow, orig_parts, orig_idx, label, csv_row, csv_base,
        name_col, patr_col, name_canon_col, patr_canon_col, fio_col,
        orig_name_col, orig_patr_col, last_name_col, status_col, residence_col,
        default_village, full):
    """Compare one marriage witness (поручитель) block; returns the advanced
    orig_idx.

    W1/W2 (full=True) compare the full name breakdown and default an empty
    status to the male marriage status. W3/W4 (full=False) compare only
    status/residence/FIO, default the status to "", and treat dedicated orig
    columns as authoritative for the surname-from-patronymic heuristic.
    """
    wn, wp, ln_from_p = resolve_name_patr_marriage_orig(
        orig_parts, orig_idx, name_col, patr_col,
        name_canon_col, patr_canon_col, srow)
    orig_idx += 1
    # Override with dedicated orig columns
    if orig_name_col is not None:
        w_orig_n = _get_orig(srow, orig_name_col)
        w_orig_p = _get_orig(srow, orig_patr_col) if orig_patr_col else ""
        if w_orig_n:
            wn, wp = w_orig_n, w_orig_p
            if not full:
                ln_from_p = None  # dedicated columns are authoritative
    # Dedicated surname column takes priority over FIO-extracted one
    w_last_name = _get(srow, last_name_col) if last_name_col is not None else ""
    if not w_last_name and not ln_from_p and not wp:
        w_last_name = _extract_lastname_from_fio(
            _get(srow, fio_col), wn)
    tr = apply_transforms(wn, wp, last_name=w_last_name or ln_from_p)

    if full:
        status = _get(srow, status_col) or MARRIAGE_STATUS_MALE
        residence = _apply_default_residence(_get(srow, residence_col), default_village)
    else:
        status = _get(srow, status_col) or ""
        residence = _apply_default_residence(
            _get(srow, residence_col) if residence_col else "", default_village)

    cmp(f"{label}: Статус", status, csv_row[csv_base])
    cmp(f"{label}: Н.П.", residence, csv_row[csv_base + 1])
    if full:
        cmp(f"{label}: Фамилия", tr["last_name_modern"], csv_row[csv_base + 3])
        cmp(f"{label}: Имя (совр. орф)", tr["name_modern"], csv_row[csv_base + 4])
        cmp(f"{label}: Отчество (совр. орф)", tr["patr_modern"], csv_row[csv_base + 5])
        cmp(f"{label}: Имя (совр.)", tr["name_canon"], csv_row[csv_base + 6])
        cmp(f"{label}: Отчество (совр.)", tr["patr_canon"], csv_row[csv_base + 7])
        cmp(f"{label}: ФИО (совр.)", tr["fio"], csv_row[csv_base + 8])
    else:
        cmp(f"{label}: ФИО (совр.)", tr["fio"], csv_row[csv_base + 3])
    return orig_idx


def compare_births(sheet_rows_with_idx, csv_rows, year, result, cols=None):
    """Compare birth records between sheet and CSV."""
    if cols is None:
        cols = BirthColumns()

    csv_lookup = _build_sequential_lookup(
        csv_rows, lambda cr: (_s(cr[10]), _s(cr[11]), _s(cr[13]), _s(cr[5]), _s(cr[12])))

    for row_idx, srow in sheet_rows_with_idx:
        rec_num = _get(srow, cols.RECORD_NUM)
        gender_str = _get(srow, cols.GENDER)
        b_month = _get(srow, cols.B_MONTH) or _get(srow, cols.K_MONTH)
        b_page = _get(srow, cols.PAGE)
        b_day = _s(_get(srow, cols.B_DAY))
        key = (rec_num, gender_str, b_month, b_page, b_day)

        cr = csv_lookup(key)
        if cr is None:
            result.discrepancies.append(Discrepancy(
                year=year, record_type="births", record_num=rec_num,
                field="MISSING_IN_CSV", sheet_val=str(key), csv_val="",
                sheet_row_idx=row_idx,
            ))
            continue

        # Detect cross-source carryover (different case number = different
        # archive volume).  Skip archive-metadata comparison in that case
        # because the CSV row legitimately comes from a different source.
        case_str = _get(srow, cols.CASE)
        cross_source = _s(case_str) != _s(cr[4])

        cmp = _make_cmp(year, "births", rec_num, row_idx, result)

        # Metadata
        cmp("Лист", _get(srow, cols.PAGE), cr[5])
        cmp("№ записи", rec_num, cr[10])
        cmp("Пол", gender_str, cr[11])
        cmp("Рожд. День", _get(srow, cols.B_DAY), cr[12])
        cmp("Крещ. День", _get(srow, cols.K_DAY), cr[15])

        # Archive metadata — skip when matched row comes from a different
        # archive case (cross-source carryover from next year's CSV).
        if not cross_source:
            cmp("Архив", _get(srow, cols.ARCHIVE), cr[1])
            cmp("Фонд", _get(srow, cols.FUND), cr[2])
            cmp("Опись", _get(srow, cols.INVENTORY), cr[3])
            cmp("Дело", _get(srow, cols.CASE), cr[4])

        # Parse orig_names for name resolution
        orig_str = _get(srow, cols.ORIG_NAMES)
        has_child = bool(_get(srow, cols.CHILD_NAME) or _get(srow, cols.CHILD_NAME_CANON))
        has_father = bool(_get(srow, cols.FATHER_NAME) or _get(srow, cols.FATHER_NAME_CANON))
        has_mother = bool(_get(srow, cols.MOTHER_NAME) or _get(srow, cols.MOTHER_NAME_CANON))
        has_gp1 = bool(_get(srow, cols.GP1_NAME) or _get(srow, cols.GP1_FIO))
        has_gp2 = bool(_get(srow, cols.GP2_NAME) or _get(srow, cols.GP2_FIO))
        orig = _parse_orig_names(orig_str, has_child, has_father, has_mother, has_gp1, has_gp2)

        # Override with dedicated orig columns if available (pre-reform chars stripped)
        if cols.CHILD_ORIG_NAME is not None:
            child_orig = _get_orig(srow, cols.CHILD_ORIG_NAME)
            if child_orig:
                orig["child"] = (child_orig, "", "")

        for _role, _orig_name_col, _orig_patr_col in [
            ("father", cols.FATHER_ORIG_NAME, cols.FATHER_ORIG_PATR),
            ("mother", cols.MOTHER_ORIG_NAME, cols.MOTHER_ORIG_PATR),
            ("gp1", cols.GP1_ORIG_NAME, cols.GP1_ORIG_PATR),
            ("gp2", cols.GP2_ORIG_NAME, cols.GP2_ORIG_PATR),
        ]:
            if _orig_name_col is not None:
                _orig_n = _get_orig(srow, _orig_name_col)
                if _orig_n:
                    _orig_p = _get_orig(srow, _orig_patr_col) if _orig_patr_col else ""
                    _existing = orig.get(_role, ("", "", ""))
                    _surname = _existing[2] if len(_existing) > 2 else ""
                    orig[_role] = (_orig_n, _orig_p, _surname)

        default_village = VILLAGE_FILTER

        # ── Child ──
        child_gender = Gender.FEMALE if gender_str in ("жен", "ж", "женский") else Gender.MALE
        if has_child:
            child_name_fb = _get(srow, cols.CHILD_NAME) or _get(srow, cols.CHILD_NAME_CANON)
            child_name = orig.get("child", (child_name_fb, ""))[0]
            tr = apply_transforms(child_name, "", gender=child_gender)
            cmp("Имя реб. (совр. орф.)", tr["name_modern"], cr[18])
            cmp("Имя реб. (совр.)", tr["name_canon"], cr[19])

        # ── Father ──
        if has_father:
            _compare_birth_parent(
                cmp, srow, orig, "father", "Отец", cr,
                (20, 22, 23, 25, 26, 27, 28), Gender.MALE,
                cols.FATHER_NAME, cols.FATHER_PATR, cols.FATHER_NAME_CANON,
                cols.FATHER_PATR_CANON, cols.FATHER_LAST_NAME,
                cols.FATHER_STATUS, BIRTH_STATUS_MALE,
                cols.FATHER_RESIDENCE, default_village)

        # ── Mother ──
        if has_mother:
            _compare_birth_parent(
                cmp, srow, orig, "mother", "Мать", cr,
                (None, 29, 30, 31, 32, 33, 34), Gender.FEMALE,
                cols.MOTHER_NAME, cols.MOTHER_PATR, cols.MOTHER_NAME_CANON,
                cols.MOTHER_PATR_CANON, cols.MOTHER_LAST_NAME,
                cols.MOTHER_STATUS, BIRTH_STATUS_FEMALE,
                None, default_village)

        # ── Godparent 1 ──
        if has_gp1:
            _compare_birth_godparent(
                cmp, srow, orig, "gp1", "Восприемник 1", cr, 35,
                cols.GP1_NAME, cols.GP1_FIO, cols.GP1_PATR, cols.GP1_LAST_NAME,
                cols.GP1_STATUS, cols.GP1_RESIDENCE,
                default_village, gender_based_default=False)

        # ── Godparent 2 ──
        if has_gp2:
            _compare_birth_godparent(
                cmp, srow, orig, "gp2", "Восприемник 2", cr, 43,
                cols.GP2_NAME, cols.GP2_FIO, cols.GP2_PATR, cols.GP2_LAST_NAME,
                cols.GP2_STATUS, cols.GP2_RESIDENCE,
                default_village, gender_based_default=True)

        # ── Birth Relative 1 ──
        has_rel1 = bool(cols.REL1_FIO and _get(srow, cols.REL1_FIO))
        if has_rel1:
            rel1_whose = _get(srow, cols.REL1_WHOSE) if cols.REL1_WHOSE else ""
            rel1_relationship = _get(srow, cols.REL1_RELATIONSHIP) if cols.REL1_RELATIONSHIP else ""
            rel1_status = _get(srow, cols.REL1_STATUS) if cols.REL1_STATUS else ""
            rel1_residence = _apply_default_residence(
                _get(srow, cols.REL1_RESIDENCE) if cols.REL1_RESIDENCE else "", default_village)

            # Name resolution from split columns (appended at end of CSV)
            rel1_name = _get(srow, cols.REL1_NAME) if cols.REL1_NAME else ""
            rel1_patr = _get(srow, cols.REL1_PATR) if cols.REL1_PATR else ""
            rel1_last_name = _get(srow, cols.REL1_LAST_NAME) if cols.REL1_LAST_NAME else ""
            if rel1_name:
                tr = apply_transforms(rel1_name, rel1_patr, last_name=rel1_last_name)
            else:
                tr = {"name_modern": "", "patr_modern": "", "name_canon": "",
                     "patr_canon": "", "last_name_modern": "", "fio": ""}

            cmp("Родственник 1: Чей", rel1_whose, cr[59])
            cmp("Родственник 1: Родство", rel1_relationship, cr[60])
            cmp("Родственник 1: Статус", rel1_status, cr[61])
            cmp("Родственник 1: Н.П.", rel1_residence, cr[62])
            cmp("Родственник 1: ФИО (совр.)", tr["fio"], cr[64])

        # ── Birth Relative 2 ──
        has_rel2 = bool(cols.REL2_FIO and _get(srow, cols.REL2_FIO))
        if has_rel2:
            rel2_whose = _get(srow, cols.REL2_WHOSE) if cols.REL2_WHOSE else ""
            rel2_relationship = _get(srow, cols.REL2_RELATIONSHIP) if cols.REL2_RELATIONSHIP else ""
            rel2_status = _get(srow, cols.REL2_STATUS) if cols.REL2_STATUS else ""
            rel2_residence = _apply_default_residence(
                _get(srow, cols.REL2_RESIDENCE) if cols.REL2_RESIDENCE else "", default_village)

            cmp("Родственник 2: Чей", rel2_whose, cr[65])
            cmp("Родственник 2: Родство", rel2_relationship, cr[66])
            cmp("Родственник 2: Статус", rel2_status, cr[67])
            cmp("Родственник 2: Н.П.", rel2_residence, cr[68])
            # cr[69] = person_location (always empty)
            # For FIO, use source FIO directly (no split name columns for Rel2 yet)
            rel2_fio = _get(srow, cols.REL2_FIO)
            cmp("Родственник 2: ФИО (совр.)", rel2_fio, cr[70])

        # ── Clergy ──
        _compare_clergy(cmp, srow, cols, cr, 72, 76, 78)


# ─── Marriage comparison ──────────────────────────────────────────────────────

def compare_marriages(sheet_rows_with_idx, csv_rows, year, result, cols=None):
    """Compare marriage records between sheet and CSV."""
    if cols is None:
        cols = MarriageColumns()

    csv_lookup = _build_sequential_lookup(
        csv_rows, lambda cr: (_s(cr[10]), _s(cr[12]), _s(cr[5]), _s(cr[11])))

    for row_idx, srow in sheet_rows_with_idx:
        rec_num = _get(srow, cols.RECORD_NUM)
        w_month = _get(srow, cols.W_MONTH)
        w_page = _get(srow, cols.PAGE)
        w_day = _s(_get(srow, cols.W_DAY))
        key = (rec_num, w_month, w_page, w_day)

        cr = csv_lookup(key)
        if cr is None:
            result.discrepancies.append(Discrepancy(
                year=year, record_type="marriages", record_num=rec_num,
                field="MISSING_IN_CSV", sheet_val=str(key), csv_val="",
                sheet_row_idx=row_idx,
            ))
            continue

        case_str = _get(srow, cols.CASE)
        cross_source = _s(case_str) != _s(cr[4])

        cmp = _make_cmp(year, "marriages", rec_num, row_idx, result)

        # Metadata
        cmp("Лист", _get(srow, cols.PAGE), cr[5])
        cmp("№ записи", rec_num, cr[10])
        cmp("День", _get(srow, cols.W_DAY), cr[11])

        # Archive — skip when cross-source carryover
        if not cross_source:
            cmp("Архив", _get(srow, cols.ARCHIVE), cr[1])
            cmp("Фонд", _get(srow, cols.FUND), cr[2])
            cmp("Опись", _get(srow, cols.INVENTORY), cr[3])
            cmp("Дело", _get(srow, cols.CASE), cr[4])

        # Parse orig_names
        orig_parts = _parse_orig_parts(_get(srow, cols.ORIG_NAMES))

        default_village = VILLAGE_FILTER
        orig_idx = 0

        has_groom = bool(_get(srow, cols.GROOM_NAME) or _get(srow, cols.GROOM_NAME_CANON))
        has_bride = bool(_get(srow, cols.BRIDE_NAME) or _get(srow, cols.BRIDE_NAME_CANON))
        has_w1 = bool(_get(srow, cols.W1_NAME) or (cols.W1_NAME_CANON and _get(srow, cols.W1_NAME_CANON)) or _get(srow, cols.W1_FIO))
        has_w2 = bool(_get(srow, cols.W2_NAME) or (cols.W2_NAME_CANON and _get(srow, cols.W2_NAME_CANON)) or _get(srow, cols.W2_FIO))

        # ── Groom ──
        if has_groom:
            orig_idx = _compare_marriage_principal(
                cmp, srow, orig_parts, orig_idx, "Жених", cr,
                (14, 16, 17, 19, 20, 21, 22, 23), Gender.MALE,
                cols.GROOM_NAME, cols.GROOM_PATR,
                cols.GROOM_NAME_CANON, cols.GROOM_PATR_CANON,
                cols.GROOM_ORIG_NAME, cols.GROOM_ORIG_PATR, cols.GROOM_LAST_NAME,
                cols.GROOM_STATUS, MARRIAGE_STATUS_MALE,
                cols.GROOM_RESIDENCE, cols.GROOM_MARRIAGE_NUM,
                default_village)

        # ── Bride ──
        if has_bride:
            orig_idx = _compare_marriage_principal(
                cmp, srow, orig_parts, orig_idx, "Невеста", cr,
                (35, 37, 38, 39, 40, 41, 42, 43), Gender.FEMALE,
                cols.BRIDE_NAME, cols.BRIDE_PATR,
                cols.BRIDE_NAME_CANON, cols.BRIDE_PATR_CANON,
                cols.BRIDE_ORIG_NAME, cols.BRIDE_ORIG_PATR, cols.BRIDE_LAST_NAME,
                cols.BRIDE_STATUS, MARRIAGE_STATUS_BRIDE,
                cols.BRIDE_RESIDENCE, cols.BRIDE_MARRIAGE_NUM,
                default_village)

        # ── Witness 1 ──
        if has_w1:
            orig_idx = _compare_marriage_witness(
                cmp, srow, orig_parts, orig_idx, "Поручитель 1", cr, 55,
                cols.W1_NAME, cols.W1_PATR, cols.W1_NAME_CANON, cols.W1_PATR_CANON,
                cols.W1_FIO, cols.W1_ORIG_NAME, cols.W1_ORIG_PATR,
                cols.W1_LAST_NAME, cols.W1_STATUS, cols.W1_RESIDENCE,
                default_village, full=True)

        # ── Witness 2 ──
        if has_w2:
            orig_idx = _compare_marriage_witness(
                cmp, srow, orig_parts, orig_idx, "Поручитель 2", cr, 64,
                cols.W2_NAME, cols.W2_PATR, cols.W2_NAME_CANON, cols.W2_PATR_CANON,
                cols.W2_FIO, cols.W2_ORIG_NAME, cols.W2_ORIG_PATR,
                cols.W2_LAST_NAME, cols.W2_STATUS, cols.W2_RESIDENCE,
                default_village, full=True)

        # ── Witness 3 ──
        has_w3 = bool(
            (cols.W3_NAME and _get(srow, cols.W3_NAME))
            or (cols.W3_NAME_CANON and _get(srow, cols.W3_NAME_CANON))
            or _get(srow, cols.W3_FIO))
        if has_w3:
            orig_idx = _compare_marriage_witness(
                cmp, srow, orig_parts, orig_idx, "Поручитель 3", cr, 73,
                cols.W3_NAME, cols.W3_PATR, cols.W3_NAME_CANON, cols.W3_PATR_CANON,
                cols.W3_FIO, cols.W3_ORIG_NAME, cols.W3_ORIG_PATR,
                cols.W3_LAST_NAME, cols.W3_STATUS, cols.W3_RESIDENCE,
                default_village, full=False)

        # ── Witness 4 ──
        has_w4 = bool(
            (cols.W4_NAME and _get(srow, cols.W4_NAME))
            or (cols.W4_NAME_CANON and _get(srow, cols.W4_NAME_CANON))
            or _get(srow, cols.W4_FIO))
        if has_w4:
            orig_idx = _compare_marriage_witness(
                cmp, srow, orig_parts, orig_idx, "Поручитель 4", cr, 77,
                cols.W4_NAME, cols.W4_PATR, cols.W4_NAME_CANON, cols.W4_PATR_CANON,
                cols.W4_FIO, cols.W4_ORIG_NAME, cols.W4_ORIG_PATR,
                cols.W4_LAST_NAME, cols.W4_STATUS, cols.W4_RESIDENCE,
                default_village, full=False)

        # ── Clergy ──
        _compare_clergy(cmp, srow, cols, cr, 102, 106, 108)


# ─── Death comparison ─────────────────────────────────────────────────────────

def compare_deaths(sheet_rows_with_idx, csv_rows, year, result, cols=None):
    """Compare death records between sheet and CSV."""
    if cols is None:
        cols = DeathColumns()

    csv_lookup = _build_sequential_lookup(
        csv_rows, lambda cr: (_s(cr[10]), _s(cr[11]), _s(cr[13]), _s(cr[5]), _s(cr[12])))

    for row_idx, srow in sheet_rows_with_idx:
        rec_num = _get(srow, cols.RECORD_NUM)
        gender_str = _get(srow, cols.GENDER)
        d_month = _get(srow, cols.D_MONTH)
        d_page = _get(srow, cols.PAGE)
        d_day = _s(_get(srow, cols.D_DAY))
        key = (rec_num, gender_str, d_month, d_page, d_day)

        cr = csv_lookup(key)
        if cr is None:
            result.discrepancies.append(Discrepancy(
                year=year, record_type="deaths", record_num=rec_num,
                field="MISSING_IN_CSV", sheet_val=str(key), csv_val="",
                sheet_row_idx=row_idx,
            ))
            continue

        case_str = _get(srow, cols.CASE)
        cross_source = _s(case_str) != _s(cr[4])

        cmp = _make_cmp(year, "deaths", rec_num, row_idx, result)

        # Metadata
        cmp("Лист", _get(srow, cols.PAGE), cr[5])
        cmp("№ записи", rec_num, cr[10])
        cmp("Пол", gender_str, cr[11])
        cmp("День (смерть)", _get(srow, cols.D_DAY), cr[12])
        cmp("День (погребение)", _get(srow, cols.B_DAY), cr[15])

        # Archive — skip when cross-source carryover
        if not cross_source:
            cmp("Архив", _get(srow, cols.ARCHIVE), cr[1])
            cmp("Фонд", _get(srow, cols.FUND), cr[2])
            cmp("Опись", _get(srow, cols.INVENTORY), cr[3])
            cmp("Дело", _get(srow, cols.CASE), cr[4])

        # Age: reconstruct from split columns when AGE is None (familio-standard)
        if cols.AGE is not None:
            sheet_age = _get(srow, cols.AGE)
        else:
            sheet_age = _reconstruct_age(
                _get(srow, cols.AGE_YEARS), _get(srow, cols.AGE_MONTHS),
                _get(srow, cols.AGE_WEEKS), _get(srow, cols.AGE_DAYS))
        csv_age = _reconstruct_age(cr[27], cr[28], cr[29], cr[30])
        cmp("Лет", sheet_age, csv_age)
        cmp("Причина смерти", _get(srow, cols.CAUSE) or DEATH_CAUSE_DEFAULT, cr[41])

        relationship = _get(srow, cols.RELATIONSHIP)
        # Only compare relationship when relative is present — the importer
        # only emits relationship when has_relative is true.
        has_relative = bool(_get(srow, cols.REL_NAME) or _get(srow, cols.REL_NAME_CANON))
        if has_relative:
            cmp("родство", relationship, cr[31])

        default_village = VILLAGE_FILTER

        # Parse orig_names for deaths
        orig_parts = _parse_orig_parts(_get(srow, cols.ORIG_NAMES))

        has_deceased = bool(_get(srow, cols.DEC_NAME) or _get(srow, cols.DEC_NAME_CANON))

        orig_idx = 0

        # ── Deceased ──
        if has_deceased:
            dn_fb = _get(srow, cols.DEC_NAME) or _get(srow, cols.DEC_NAME_CANON)
            dp_fb = _get(srow, cols.DEC_PATR) or _get(srow, cols.DEC_PATR_CANON)

            if orig_idx < len(orig_parts) and orig_parts[orig_idx]:
                tokens = orig_parts[orig_idx].split()
                dn = tokens[0] if tokens else ""
                dp = tokens[1] if len(tokens) >= 2 else ""
                if dp and _patr_should_be_lastname(dn, dp):
                    dp = ""
                dn = dn or dn_fb
                dp = dp or dp_fb
            else:
                dn, dp = dn_fb, dp_fb
            orig_idx += 1

            # Override with dedicated orig columns (prefer orig over modern fallback)
            if cols.DEC_ORIG_NAME is not None:
                dec_orig_n = _get_orig(srow, cols.DEC_ORIG_NAME)
                dec_orig_p = _get_orig(srow, cols.DEC_ORIG_PATR) if cols.DEC_ORIG_PATR else ""
                if dec_orig_n:
                    dn = dec_orig_n
                    dp = dec_orig_p or dp

            # Title word handling
            dec_status = _get(srow, cols.DEC_STATUS)
            if dn and dn.lower() in _TITLE_WORDS:
                dec_status = dec_status or dn
                dn = dp or "?"
                dp = ""

            if dn and dn == "Имена":
                dn = "?"
                dp = ""

            if dp and _patr_should_be_lastname(dn, dp):
                dp = ""
            # Convert modern patronymics to old form (e.g. "Ефимович" → "Ефимов")
            if dp and not validate_old_patronymic(modernize_orthography(dp)):
                old_patr = find_old_patronymic_by_modern(modernize_orthography(dp))
                dp = old_patr if old_patr else ""

            sheet_ln = _get(srow, cols.DEC_LAST_NAME)
            dec_gender = Gender.FEMALE if gender_str in ("жен", "ж", "женский") else Gender.MALE
            tr = apply_transforms(dn, dp, sheet_ln, gender=dec_gender)

            if not dec_status:
                dec_status = _apply_default_status("", gender_str, "deaths")
            dec_residence = _apply_default_residence(_get(srow, cols.DEC_RESIDENCE), default_village)

            cmp("Умерший: Н.П.", dec_residence, cr[18])
            cmp("Умерший: статус", dec_status, cr[20])
            cmp("Умерший: Фамилия", tr["last_name_modern"], cr[21])
            cmp("Умерший: Имя (совр. орф.)", tr["name_modern"], cr[23])
            cmp("Умерший: Имя", tr["name_canon"], cr[25])
            dec_patr_canon = _get(srow, cols.DEC_PATR_CANON) or tr["patr_canon"]

            # Suppress patronymic comparison when source patr is empty and
            # the relative is the father — the Familio exporter derives the
            # deceased's patronymic from the father's name automatically.
            _dec_patr_derived = False
            relationship = _get(srow, cols.RELATIONSHIP)
            if not tr["patr_modern"] and has_relative and relationship == "отец":
                _rel_name = _get(srow, cols.REL_NAME) or _get(srow, cols.REL_NAME_CANON)
                if _rel_name:
                    _dec_patr_derived = True

            if not _dec_patr_derived:
                cmp("Умерший: Отчество (совр. орф.)", tr["patr_modern"], cr[24])
                cmp("Умерший: Отчество", dec_patr_canon, cr[26])

        # ── Relative ──
        if has_relative:
            rn_fb = _get(srow, cols.REL_NAME) or _get(srow, cols.REL_NAME_CANON)
            rp_fb = _get(srow, cols.REL_PATR) or _get(srow, cols.REL_PATR_CANON)

            if orig_idx < len(orig_parts) and orig_parts[orig_idx]:
                tokens = orig_parts[orig_idx].split()
                rn = tokens[0] if tokens else ""
                rp = tokens[1] if len(tokens) >= 2 else ""
                if rp and _patr_should_be_lastname(rn, rp):
                    rp = ""
                rn = rn or rn_fb
                rp = rp or rp_fb
            else:
                rn, rp = rn_fb, rp_fb
            orig_idx += 1

            # Override with dedicated orig columns (prefer orig over modern fallback)
            if cols.REL_ORIG_NAME is not None:
                rel_orig_n = _get_orig(srow, cols.REL_ORIG_NAME)
                rel_orig_p = _get_orig(srow, cols.REL_ORIG_PATR) if cols.REL_ORIG_PATR else ""
                if rel_orig_n:
                    rn = rel_orig_n
                    rp = rel_orig_p or rp

            # Convert modern patronymics to old form (e.g. "Ефимович" → "Ефимов")
            if rp and not validate_old_patronymic(modernize_orthography(rp)):
                old_patr = find_old_patronymic_by_modern(modernize_orthography(rp))
                rp = old_patr if old_patr else ""

            rel_status = _get(srow, cols.REL_STATUS)
            if rn and rn.lower() in _TITLE_WORDS:
                rel_status = rel_status or rn
                rn = rp or "?"
                rp = ""
            if rn == "Имена":
                rn = "?"
                rp = ""
            if rp and _patr_should_be_lastname(rn, rp):
                rp = ""
            if rp and not validate_old_patronymic(modernize_orthography(rp)):
                rp = ""

            sheet_ln = _get(srow, cols.REL_LAST_NAME)
            tr = apply_transforms(rn, rp, sheet_ln)

            if not rel_status:
                # Relative status default depends on the relative's detected gender
                detected_gender = get_gender_from_name(tr["name_modern"]) if tr["name_modern"] else None
                if detected_gender:
                    rel_status = DEATH_STATUS_FEMALE if detected_gender == Gender.FEMALE else DEATH_STATUS_MALE
                else:
                    rel_status = DEATH_STATUS_MALE
            rel_residence = _apply_default_residence(_get(srow, cols.REL_RESIDENCE), default_village)

            cmp("Родственник: Н.П.", rel_residence, cr[32])
            cmp("Родственник: статус", rel_status, cr[34])
            cmp("Родственник: Фамилия", tr["last_name_modern"], cr[35])
            cmp("Родственник: Имя (совр. орф.)", tr["name_modern"], cr[37])
            cmp("Родственник: Отчество (совр. орф.)", tr["patr_modern"], cr[38])
            cmp("Родственник: Имя", tr["name_canon"], cr[39])
            rel_patr_canon = _get(srow, cols.REL_PATR_CANON) or tr["patr_canon"]
            cmp("Родственник: Отчество", rel_patr_canon, cr[40])

        # ── Clergy ──
        _compare_clergy(cmp, srow, cols, cr, 55, 59, 61)


# ─── Main orchestration ──────────────────────────────────────────────────────

def regenerate_csv(year, record_type):
    """Run the DSL file to regenerate the CSV."""
    dsl = find_dsl(year, record_type)
    if not dsl:
        return False
    year_dir = os.path.dirname(dsl)
    base = os.path.basename(dsl)
    subprocess.run(["python3", base], cwd=year_dir, capture_output=True, timeout=30, env=workspace.child_env())
    return find_csv(year, record_type) is not None


def validate_record_type(record_type, sheet_rows_by_year, regenerate=False, year_filter=None):
    """Validate all years for a given record type."""
    result = ValidationResult(record_type=record_type)

    compare_fn = {
        "births": compare_births,
        "marriages": compare_marriages,
        "deaths": compare_deaths,
    }[record_type]

    cols_map = {
        "births": _cfg.fmt.birth_cols,
        "marriages": _cfg.fmt.marriage_cols,
        "deaths": _cfg.fmt.death_cols,
    }
    cols = cols_map[record_type]

    years = sorted(sheet_rows_by_year.keys())
    if year_filter:
        year_set = set(year_filter) if isinstance(year_filter, list) else {year_filter}
        years = [y for y in years if y in year_set]

    for year in years:
        sheet_rows = sheet_rows_by_year[year]
        if not sheet_rows:
            continue

        # Check that at least the primary DSL exists (carryover-only years
        # without their own DSL are skipped).
        dsl = find_dsl(year, record_type)
        if not dsl:
            continue  # No DSL file for this year

        # Aggregate CSV rows for this year from both year X and year X+1 CSVs
        # (carryover records from Dec of year X live in the X+1 CSV).
        csv_rows, _ = _read_csv_rows_for_year(year, record_type, regenerate=regenerate)
        if csv_rows is None:
            result.missing_csv.append(year)
            continue
        result.years_checked += 1

        # Record count check
        if len(sheet_rows) != len(csv_rows):
            result.count_mismatches.append((year, len(sheet_rows), len(csv_rows)))

        prev_disc = len(result.discrepancies)
        try:
            compare_fn(sheet_rows, csv_rows, year, result, cols=cols)
        except Exception as e:
            result.discrepancies.append(Discrepancy(
                year=year, record_type=record_type, record_num="*",
                field="ERROR", sheet_val=str(e), csv_val="",
            ))

        if len(result.discrepancies) == prev_disc:
            result.years_ok += 1
        else:
            result.years_with_issues += 1

    return result


def print_report(results):
    """Print validation summary and numbered discrepancies. Returns sorted discrepancy list."""
    print("\n=== VALIDATION SUMMARY ===")
    print(f"{'Type':<12} | {'Years':>5} | {'OK':>4} | {'Issues':>6} | {'Fields Checked':>14} | {'Discrepancies':>13} | {'Missing CSV':>11} | {'Count Mismatch':>14}")
    print("-" * 110)

    all_discrepancies: list[Discrepancy] = []
    for r in results:
        print(f"{r.record_type:<12} | {r.years_checked:>5} | {r.years_ok:>4} | {r.years_with_issues:>6} | "
              f"{r.total_fields:>14} | {len(r.discrepancies):>13} | {len(r.missing_csv):>11} | {len(r.count_mismatches):>14}")
        all_discrepancies.extend(r.discrepancies)

    # Count mismatches
    for r in results:
        if r.count_mismatches:
            print(f"\n=== RECORD COUNT MISMATCHES ({r.record_type}) ===")
            for year, sheet_ct, csv_ct in r.count_mismatches:
                print(f"  {year}: sheet={sheet_ct}, csv={csv_ct}")

    # Missing CSVs
    for r in results:
        if r.missing_csv:
            print(f"\n=== MISSING CSVs ({r.record_type}) ===")
            print(f"  Years: {', '.join(str(y) for y in r.missing_csv)}")

    sorted_disc = sorted(all_discrepancies, key=lambda x: (x.year, x.record_type, x.record_num))
    if sorted_disc:
        print(f"\n=== DISCREPANCIES ({len(sorted_disc)} total) ===")
        print(f"{'#':<5} {'Year':<6} {'Type':<12} {'Rec#':<6} {'Field':<35} {'Sheet Value':<30} {'CSV Value':<30}")
        print("-" * 130)
        for i, d in enumerate(sorted_disc, 1):
            sv = d.sheet_val[:28] if len(d.sheet_val) > 28 else d.sheet_val
            cv = d.csv_val[:28] if len(d.csv_val) > 28 else d.csv_val
            print(f"{i:<5} {d.year:<6} {d.record_type:<12} {d.record_num:<6} {d.field:<35} {sv:<30} {cv:<30}")
    else:
        print("\nNo discrepancies found!")

    return sorted_disc


# ─── Fix discrepancies ───────────────────────────────────────────────────────

def fix_discrepancies(discrepancies, fix_ids, spreadsheet_id, dry_run=False, fix_empty=False):
    """Update Google Sheet cells with CSV values for selected discrepancies.

    Args:
        discrepancies: Sorted list of Discrepancy objects (1-indexed for user display).
        fix_ids: List of 1-based discrepancy numbers, or ["all"].
        spreadsheet_id: Google Sheets spreadsheet ID.
        dry_run: If True, only print what would be changed.
        fix_empty: If True, only fix discrepancies where sheet value is empty and CSV value is non-empty.
    """
    if fix_ids == ["all"]:
        selected = list(enumerate(discrepancies, 1))
    else:
        selected = []
        for n in fix_ids:
            if 1 <= n <= len(discrepancies):
                selected.append((n, discrepancies[n - 1]))
            else:
                print(f"WARNING: discrepancy #{n} out of range (1-{len(discrepancies)})", file=sys.stderr)

    if fix_empty:
        selected = [(n, d) for n, d in selected if not d.sheet_val.strip() and d.csv_val.strip()]

    if not selected:
        print("No discrepancies selected for fixing.", file=sys.stderr)
        return

    # Filter to fixable discrepancies (have column mapping and row index)
    fixable = []
    for num, d in selected:
        col = FIELD_TO_SHEET_COL.get((d.record_type, d.field))
        if col is None:
            print(f"  #{num}: SKIP (no column mapping for field '{d.field}')")
            continue
        if d.sheet_row_idx is None:
            print(f"  #{num}: SKIP (no sheet row index)")
            continue
        fixable.append((num, d, col))

    if not fixable:
        print("No fixable discrepancies found.", file=sys.stderr)
        return

    # Group by tab for efficient worksheet access
    tab_map = _cfg.tab_map

    if dry_run:
        print(f"\n=== DRY RUN: would fix {len(fixable)} cells ===")
        for num, d, col in fixable:
            gs_row = d.sheet_row_idx + 1  # gspread is 1-based
            gs_col = col + 1              # gspread is 1-based
            print(f"  #{num}: [{tab_map[d.record_type]}] row={gs_row} col={gs_col} "
                  f"'{d.sheet_val}' → '{d.csv_val}'  ({d.field})")
        return

    import gspread
    from gspread.utils import rowcol_to_a1
    gc = gspread.oauth()
    spreadsheet = gc.open_by_key(spreadsheet_id)

    # Cache worksheets
    ws_cache = {}
    for tab_name in {tab_map[d.record_type] for _, d, _ in fixable}:
        for ws in spreadsheet.worksheets():
            if ws.title.lower() == tab_name.lower():
                ws_cache[tab_name] = ws
                break

    print(f"\n=== Fixing {len(fixable)} cells ===")

    # Group updates by worksheet tab for batch processing
    updates_by_tab = {}
    for num, d, col in fixable:
        tab = tab_map[d.record_type]
        ws = ws_cache.get(tab)
        if not ws:
            print(f"  #{num}: ERROR - worksheet '{tab}' not found")
            continue
        gs_row = d.sheet_row_idx + 1
        gs_col = col + 1
        print(f"  #{num}: [{tab}] row={gs_row} col={gs_col} "
              f"'{d.sheet_val}' → '{d.csv_val}'  ({d.field})")
        updates_by_tab.setdefault(tab, []).append({
            "range": rowcol_to_a1(gs_row, gs_col),
            "values": [[d.csv_val]],
        })

    fixed = 0
    for tab, batch in updates_by_tab.items():
        ws = ws_cache[tab]
        ws.batch_update(batch, value_input_option="RAW")
        fixed += len(batch)

    print(f"\nFixed {fixed}/{len(fixable)} cells.")
    print(
        "Note: Google Sheets may take a few seconds to propagate changes. "
        "Re-run validation after a brief pause to confirm.",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description="Validate importer pipeline end-to-end")
    parser.add_argument("--record-type", choices=["births", "marriages", "deaths"],
                        help="Only validate this record type")
    parser.add_argument("--year", type=int, nargs="+", help="Only validate these year(s)")
    parser.add_argument("--regenerate", action="store_true",
                        help="Regenerate missing CSVs by running DSL files")
    parser.add_argument("--fix", nargs="+",
                        help="Fix discrepancies by number (e.g. --fix 1 2 5) or --fix all")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview --fix changes without writing to the sheet")
    parser.add_argument("--fix-empty", action="store_true",
                        help="With --fix, only fix discrepancies where the sheet value is empty")
    parser.add_argument("--site", required=True,
                        help="the village's sheet: `[sheets] site` of its village.toml (e.g. one of `sites()`)")
    parser.add_argument("--csv", metavar="DIR",
                        help="Read source data from local CSV files in DIR (instead of Google Sheets)")
    args = parser.parse_args()

    cfg = site_config(args.site)
    if args.csv:
        cfg.csv_source_dir = args.csv
    select(cfg)

    record_types = [args.record_type] if args.record_type else ["births", "marriages", "deaths"]

    if _cfg.csv_source_dir:
        print(f"Reading source data from local CSVs in {_cfg.csv_source_dir}...", file=sys.stderr)
        sheets = fetch_local_csvs(_cfg.csv_source_dir, _cfg.tab_map)
        print(f"Loaded {len(sheets)} tabs.", file=sys.stderr)
    else:
        print("Fetching sheets from Google Sheets...", file=sys.stderr)
        sheets = fetch_all_sheets(SPREADSHEET_ID, tab_names=_cfg.tab_map.values())
        print(f"Fetched {len(sheets)} tabs.", file=sys.stderr)

    results = []
    for rt in record_types:
        tab = _cfg.tab_map[rt]
        if tab not in sheets:
            print(f"WARNING: tab '{tab}' not found in source data", file=sys.stderr)
            continue

        print(f"Splitting {rt} by year...", file=sys.stderr)
        rows_by_year = split_by_year(sheets[tab], _cfg.year_col_map[rt], VILLAGE_FILTER)
        print(f"  Found {len(rows_by_year)} years with data.", file=sys.stderr)

        print(f"Validating {rt}...", file=sys.stderr)
        result = validate_record_type(rt, rows_by_year, args.regenerate, args.year)
        results.append(result)

    sorted_disc = print_report(results)

    if args.fix:
        if _cfg.csv_source_dir:
            print("ERROR: --fix is not supported with --csv source (use Google Sheets)", file=sys.stderr)
            sys.exit(1)
        if args.fix == ["all"]:
            fix_ids = ["all"]
        else:
            fix_ids = []
            for x in args.fix:
                try:
                    fix_ids.append(int(x))
                except ValueError:
                    if x == "all":
                        fix_ids = ["all"]
                        break
                    print(f"WARNING: invalid fix id '{x}', skipping", file=sys.stderr)
        fix_discrepancies(sorted_disc, fix_ids, SPREADSHEET_ID, dry_run=args.dry_run, fix_empty=args.fix_empty)


if __name__ == "__main__":
    main()
