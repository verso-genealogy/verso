"""The rows of `names.csv`: how one is built, where it goes, how it is written in.

Moved verbatim out of `verso.ru.cli.names` before 0.1.0: `python -m verso.ru.cli.names add` and
Verso's «Добавить в справочник…» (`verso.app_dsl.newnames`) place a row by the same
rules, and a library does not import its CLI. Where a row may go, and why it never
goes above a row it would shadow, is `verso.ru.cli.names`' docstring.
"""

import csv
import io
from collections.abc import Mapping, Sequence

from verso.ru.messages import t

COLUMNS = ['Пол', 'Имя', 'Имя-основа', 'От', 'Склонения, связи',
           'Родительный падеж', 'Отчество старое М', 'Отчество старое Ж',
           'Отчество М', 'Отчество Ж', 'Источник']


# Columns the registry indexes. A new row sharing any of these with an EARLIER
# row is harmless; sharing with a LATER row would steal the key from it.
_INDEXED = ['Имя', 'Родительный падеж', 'Отчество старое М', 'Отчество старое Ж',
            'Отчество М', 'Отчество Ж']


def _v(row: Mapping[str, str], column: str) -> str:
    value = row.get(column)
    return value.strip() if value else ''


def build_row(*, gender: str, name: str, base: str = '', origin: str = '',
              declension: str = '', genitive: str = '', patr_old_m: str = '',
              patr_old_f: str = '', patr_m: str = '', patr_f: str = '',
              source: str = '') -> dict[str, str]:
    """A complete row, every column present and in file order."""
    return {
        'Пол': gender, 'Имя': name, 'Имя-основа': base, 'От': origin,
        'Склонения, связи': declension, 'Родительный падеж': genitive,
        'Отчество старое М': patr_old_m, 'Отчество старое Ж': patr_old_f,
        'Отчество М': patr_m, 'Отчество Ж': patr_f, 'Источник': source,
    }


def insertion_index(names: Sequence[str], new_name: str) -> int:
    """Index to insert `new_name` at: after the last occurrence of the largest
    name that is `<=` it, or 0 when no name is."""
    best: str | None = None
    at = 0
    for i, name in enumerate(names):
        if name <= new_name and (best is None or name >= best):
            best, at = name, i + 1
    return at


def place(rows: Sequence[Mapping[str, str]], new_row: Mapping[str, str]) -> int:
    """Validate `new_row` against `rows` and return where it belongs.

    Raises ValueError when the row would be a duplicate, or would leave a
    finding the integrity check gates on.
    """
    name = _v(new_row, 'Имя')
    if not name:
        raise ValueError(str(t("names_table.empty_name")))

    if any(dict(r) == dict(new_row) for r in rows):
        raise ValueError(str(t("names_table.row_exists", name=repr(name))))

    base = _v(new_row, 'Имя-основа')
    if base:
        names = {_v(r, 'Имя') for r in rows if _v(r, 'Имя')}
        if base == name:
            raise ValueError(
                str(t("names_table.base_repeats_name", name=repr(name))))
        if base not in names:
            raise ValueError(str(t("names_table.base_missing", base=repr(base))))
        canonical = {_v(r, 'Имя') for r in rows
                     if _v(r, 'Имя') and not _v(r, 'Имя-основа')}
        if base not in canonical:
            ultimate = next((_v(r, 'Имя-основа') for r in rows
                             if _v(r, 'Имя') == base and _v(r, 'Имя-основа')), base)
            raise ValueError(
                str(t("names_table.base_is_variant", base=repr(base), ultimate=repr(ultimate))))

    at = insertion_index([_v(r, 'Имя') for r in rows], name)

    # Push forward past any LATER row whose indexed key this row would steal.
    keys = {(c, _v(new_row, c)) for c in _INDEXED if _v(new_row, c)}
    while at < len(rows) and keys & {(c, _v(rows[at], c)) for c in _INDEXED
                                     if _v(rows[at], c)}:
        at += 1
    return at


def format_row(row: Mapping[str, str]) -> str:
    """The row as one CSV line, quoted only where the format requires it."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator='').writerow([row.get(c, '') for c in COLUMNS])
    return buffer.getvalue()


def splice(path: str, at: int, row: Mapping[str, str]) -> None:
    """Insert ONE line after data row `at`, leaving every other byte alone.

    Rewriting the file through `csv.DictWriter` would normalise it, and
    names.csv holds six rows quoted where quoting is not required — they would
    silently lose their quotes and show up in the diff as unrelated churn.
    """
    with open(path, 'r', encoding='utf-8', newline='') as f:
        lines = f.readlines()
    ending = '\n'
    if lines and lines[-1].endswith('\r\n'):
        ending = '\r\n'
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += ending
    lines.insert(at + 1, format_row(row) + ending)   # +1 for the header line
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(lines)
