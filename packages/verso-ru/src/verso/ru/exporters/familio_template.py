"""Mapping from the project's internal ``csv_familio`` columns to the official
Familio **МК** submission template (``Shablon_MK.xlsx``).

The internal CSV (see :mod:`verso.ru.exporters.csv_familio`) is an *extended* layout:
it keeps both original-orthography and canonical name forms and a few helper
columns. The official template is narrower (69 / 97 / 53 columns for births /
marriages / deaths) and stores a single name form per person. These tables remap
one source row into one template row.

Each ``SRC_*`` list has exactly one entry per template column, in template order:

* ``SEQ``  — the сквозная нумерация (template column "А"), assigned by the caller.
* ``None`` — leave the template cell blank (e.g. derived ``full_location`` /
  ``person_location`` columns, or fields we do not capture).
* ``int``  — copy from this 0-based column index of the source CSV row.

For principals (child, parents, groom/bride and their fathers, the deceased) the
template's single ``Имя`` / ``Отчество`` map to our canonical ``(совр.)`` columns.
"""
from __future__ import annotations

# Sentinel for the сквозная column (template "А"); the caller supplies its value.
SEQ = -1

# Official template sheet (tab) titles, in the canonical справочник order.
TEMPLATE_SHEET_TITLES: dict[str, str] = {
    "births": "РОЖДЕНИЕ",
    "marriages": "БРАК",
    "deaths": "СМЕРТЬ",
}

# Row where data begins in each template sheet (rows 1–2 are merged group +
# column headers, row 3 is a spacer).
TEMPLATE_DATA_START_ROW = 4

# --- births: 69 template columns ----------------------------------------------
SRC_BIRTHS: list[int | None] = [
    SEQ, 1, 2, 3, 4, 5, 6, None, 8, 9, 10, 11,   # 0–11 reквизиты + Пол
    12, 13, 14, 15, 16, 17,                       # 12–17 birth/baptism dates
    19,                                           # 18 Имя ребёнка (совр.)
    20, None,                                     # 19 родитель: Н.П. приписки (отец); 20 person_location
    22, 23, 24, 27, 28,                           # 21–25 отец: статус, фам, фам-2, имя, отч
    29, 30, None, 33, 34,                         # 26–30 мать: статус, фам, девичья, имя, отч
    35, 36, None, 42,                             # 31–34 восприемник 1
    43, 44, None, 50,                             # 35–38 восприемник 2
    51, 52, None, 54,                             # 39–42 восприемник 3
    55, 56, None, 58,                             # 43–46 восприемник 4
    59, 60, 61, 62, None, 64,                     # 47–52 родственник 1
    65, 66, 67, 68, None, 70,                     # 53–58 родственник 2
    71, 72, 73, 74, 75, 76, 77, 78,               # 59–66 clergy
    79, 80,                                       # 67–68 пометки, авторский комментарий
]

# --- marriages: 97 template columns -------------------------------------------
SRC_MARRIAGES: list[int | None] = [
    SEQ, 1, 2, 3, 4, 5, 6, None, 8, 9, 10,        # 0–10 reквизиты
    11, 12, 13,                                   # 11–13 дата венчания
    14, None, 16, 17, 18, 21, 22, 23, 24, 25, 26, 27,  # 14–25 жених + возраст
    28, None, 30, 31, 32, 33, 34,                 # 26–32 отец жениха
    35, None, 37, 38, 41, 42, 43, 44, 45, 46, 47, # 33–43 невеста + возраст
    48, None, 50, 51, 52, 53, 54,                 # 44–50 отец невесты
    55, 56, None, 63,                             # 51–54 поручитель 1 (по жениху)
    64, 65, None, 72,                             # 55–58 поручитель 2
    73, 74, None, 76,                             # 59–62 поручитель 3
    77, 78, None, 80,                             # 63–66 поручитель 4 (по невесте)
    81, 82, None, 84,                             # 67–70 поручитель 5
    85, 86, None, 88,                             # 71–74 поручитель 6
    89, 90, 91, 92, None, 94,                     # 75–80 родственник поручителя 1
    95, 96, 97, 98, None, 100,                    # 81–86 родственник поручителя 2
    101, 102, 103, 104, 105, 106, 107, 108,       # 87–94 clergy
    109, 110,                                     # 95–96 пометки, авторский комментарий
]

# --- deaths: 53 template columns ----------------------------------------------
SRC_DEATHS: list[int | None] = [
    SEQ, 1, 2, 3, 4, 5, 6, None, 8, 9, 10, 11,    # 0–11 reквизиты + Пол
    12, 13, 14, 15, 16, 17,                       # 12–17 death/burial dates
    18, None, 20, 21, 22, 25, 26,                 # 18–24 умерший
    27, 28, 29, 30,                               # 25–28 возраст
    31, 32, None, 34, 35, 36, 39, 40,             # 29–36 родственник
    41,                                           # 37 причина смерти
    50, 51, 52, 53,                               # 38–41 исповедь (clergy)
    54, 55, 56, 57,                               # 42–45 погребение (clergy)
    58, 59, 60, 61,                               # 46–49 дьякон / псаломщик
    62,                                           # 50 где погребён
    63, 64,                                       # 51–52 пометки, авторский комментарий
]

TEMPLATE_MAPS: dict[str, list[int | None]] = {
    "births": SRC_BIRTHS,
    "marriages": SRC_MARRIAGES,
    "deaths": SRC_DEATHS,
}


def remap_row(source_row: list[str], col_map: list[int | None], seq: int) -> list[str]:
    """Project one source CSV row onto the template's columns.

    ``seq`` is the сквозная number for this row (1-based).
    """
    out: list[str] = []
    for spec in col_map:
        if spec is None:
            out.append("")
        elif spec == SEQ:
            out.append(str(seq))
        else:
            out.append(source_row[spec] if spec < len(source_row) else "")
    return out
