"""Integrity check for `names.csv` itself — the table, not the DSL that reads it.

`verso.ru.linters.checks.names` validates `person()` calls AGAINST the table. This
module validates the table's own claims: that every `Имя-основа` names a form the
table actually holds, that it is a canonical one, and that no row is dead weight.

**Deliberately not checked: alphabetical order.** The file is only roughly sorted
(572 of 4049 rows sit out of order), and it cannot be sorted, because ROW ORDER IS
LOAD-BEARING: the table compiles into its layer (`verso.ru.naming.legacy`) index by
index «first row wins», so the first row carrying a key wins and later rows with the same
key are the attested variants it deliberately shadows. «Абрамов» resolving to
«Авраамович» rather than «Абрамович» is that mechanism working, not a duplicate.
Sorting the file would silently re-pick 400+ canonical forms.

Codes:

* **NCSV001** — `Имя-основа` names a form the table does not hold as an `Имя`.
  `canonicalize_name` then returns a name that is not in the dictionary.
* **NCSV002** — `Имя-основа` repeats `Имя`. A canonical row leaves it empty.
* **NCSV003** — `Имя-основа` points at a name that is itself only a variant, so
  canonicalisation stops one step short of the canonical form (it does not
  follow chains). **Advisory**, and that is not squeamishness: `canonicalize_name`
  feeds `res_names`, so flattening a chain RENAMES the Geni resources built from
  those spellings, and every applied village then needs `moved` blocks. It is a
  migration, not a cleanup, and it needs a human to schedule it.
* **NCSV004** — the row repeats an earlier row in every column.
* **NCSV005** — `Пол` is neither `М` nor `Ж`.
* **NCSV006** — `Имя` is empty.
"""

import csv
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verso.core import workspace
from verso.ru.naming import names_registry, names_table
from verso.ru.naming.orthography import modernize_orthography
from verso.ru.messages import t


def names_csv_path() -> Path:
    """The workspace's names.csv (`[names]` in verso.toml)."""
    return workspace.current().names_file('names.csv')

# names.csv line 1 is the header, so data row 0 is file line 2.
_FIRST_DATA_LINE = 2

# Codes that report but never gate — see NCSV003 above.
ADVISORY_CODES = frozenset({'NCSV003'})


@dataclass(frozen=True)
class Finding:
    code: str
    line: int
    name: str
    message: str


def _v(row: Mapping[str, str], column: str) -> str:
    value = row.get(column)
    return value.strip() if value else ''


def check_rows(rows: Sequence[Mapping[str, str]]) -> list[Finding]:
    """Report every integrity finding in `rows`, in file order."""
    names = {_v(r, 'Имя') for r in rows if _v(r, 'Имя')}  # i18n: content — names.csv's columns and values
    canonical = {_v(r, 'Имя') for r in rows  # i18n: content — names.csv's columns and values
                 if _v(r, 'Имя') and not _v(r, 'Имя-основа')}  # i18n: content — names.csv's columns and values

    findings: list[Finding] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for index, row in enumerate(rows):
        line = _FIRST_DATA_LINE + index
        name = _v(row, 'Имя')  # i18n: content — names.csv's columns and values
        base = _v(row, 'Имя-основа')  # i18n: content — names.csv's columns and values

        if not name:
            findings.append(Finding('NCSV006', line, '', str(t('NCSV006.empty'))))
            continue

        gender = _v(row, 'Пол')  # i18n: content — names.csv's columns and values
        if gender not in ('М', 'Ж'):  # i18n: content — names.csv's columns and values
            findings.append(Finding(
                'NCSV005', line, name, str(t('NCSV005.gender', gender=repr(gender)))))

        if base:
            if base == name:
                findings.append(Finding(
                    'NCSV002', line, name, str(t('NCSV002.repeats'))))
            elif base not in names:
                findings.append(Finding(
                    'NCSV001', line, name, str(t('NCSV001.unknown_base', base=repr(base)))))
            elif base not in canonical:
                findings.append(Finding(
                    'NCSV003', line, name, str(t('NCSV003.chain', base=repr(base)))))

        key = tuple(sorted(row.items()))
        if key in seen:
            findings.append(Finding(
                'NCSV004', line, name, str(t('NCSV004.duplicate'))))
        seen.add(key)

    return findings


def hard_findings(rows: Sequence[Mapping[str, str]]) -> list[Finding]:
    """Only the findings that gate — the ones whose repair changes no behaviour."""
    return [f for f in check_rows(rows) if f.code not in ADVISORY_CODES]


def read_rows(path: str | Path | None = None) -> list[dict[str, str]]:
    target = Path(path) if path is not None else names_csv_path()
    with open(target, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


# -- writing the workspace's tables (L4): the path `verso.ru.cli.names add` takes, and Verso's
# «Добавить в справочник…»

def rows() -> list[dict[str, str]]:
    """The workspace's names.csv, every row in its order."""
    return read_rows()


def add_row(row: Mapping[str, str], *, dry_run: bool = False) -> dict[str, Any]:
    """Teach the workspace's names.csv a name: the row placed where `names add` puts
    it (`names_table.place`), refused (ValueError, «CODE: message; …») when the
    table would then fail its own check, and spliced in as one line. Where it goes:
    the file, its line, the name it follows, the line itself."""
    path = names_csv_path()
    old = read_rows(path)
    new_row = names_table.build_row(
        gender=row.get("Пол", "").strip(), name=row.get("Имя", "").strip(),  # i18n: content — names.csv's columns and values
        base=row.get("Имя-основа", "").strip(), origin=row.get("От", "").strip(),  # i18n: content — names.csv's columns and values
        declension=row.get("Склонения, связи", "").strip(),  # i18n: content — names.csv's columns and values
        genitive=row.get("Родительный падеж", "").strip(),  # i18n: content — names.csv's columns and values
        patr_old_m=row.get("Отчество старое М", "").strip(),  # i18n: content — names.csv's columns and values
        patr_old_f=row.get("Отчество старое Ж", "").strip(),  # i18n: content — names.csv's columns and values
        patr_m=row.get("Отчество М", "").strip(), patr_f=row.get("Отчество Ж", "").strip(),  # i18n: content — names.csv's columns and values
        source=row.get("Источник", "").strip())  # i18n: content — names.csv's columns and values
    at = names_table.place(old, new_row)
    findings = hard_findings([*old[:at], new_row, *old[at:]])
    if findings:
        raise ValueError("; ".join(f"{f.code}: {f.message}" for f in findings))
    where = {"file": "names.csv", "line": at + 2,
             "after": old[at - 1].get("Имя", "") if at else "", "line_text": names_table.format_row(new_row)}  # i18n: content — names.csv's columns and values
    if not dry_run:
        names_table.splice(str(path), at, new_row)
        names_registry.reload()
    return where


def add_ignored(kind: str, text: str, gender: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Write a one-off spelling into its ignore list — a patronymic into
    patronymics_ignore.csv, a name (with its sex) into names_ignore.csv — refused
    (ValueError) when it is there already, or when the table holds the name."""
    value = modernize_orthography(text).strip()
    if not value:
        raise ValueError(str(t("linters.names_csv.empty_spelling")))
    if kind == "name" and any((r.get("Имя") or "").strip() == value for r in read_rows()):  # i18n: content — names.csv's columns and values
        # The ignore list is for spellings the table does not know, and it is
        # read FIRST: «Ж,Феона» there would make every man named Феона a woman.
        raise ValueError(str(t("linters.names_csv.in_the_table", value=value)))
    ws = workspace.current()
    if kind == "patronymic":
        path, line, column = ws.names_file("patronymics_ignore.csv"), value, "Patronymic"
    else:
        path, line, column = ws.names_file("names_ignore.csv"), f"{gender.strip()},{value}", "Name"
    with path.open(encoding="utf-8", newline="") as f:
        present = {(r.get(column) or "").strip() for r in csv.DictReader(f)}
    if value in present:
        raise ValueError(str(t("linters.names_csv.listed_already", value=value, file=path.name)))
    where = {"file": path.name, "line_text": line}
    if not dry_run:
        text_now = path.read_bytes().decode("utf-8")
        ending = "\r\n" if text_now.endswith("\r\n") else "\n"
        if text_now and not text_now.endswith(("\n", "\r\n")):
            text_now += ending
        path.write_bytes((text_now + line + ending).encode("utf-8"))
        names_registry.reload()
    return where


def check_file(path: str | Path | None = None) -> list[Finding]:
    return check_rows(read_rows(path))


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else names_csv_path()
    findings = check_file(path)
    for f in findings:
        mark = ' (advisory)' if f.code in ADVISORY_CODES else ''
        print(f'{path}:{f.line}: {f.code}{mark} {f.name}: {f.message}')
    hard = [f for f in findings if f.code not in ADVISORY_CODES]
    if hard:
        print(f'\n{len(hard)} finding(s) in {path}', file=sys.stderr)
        return 1
    if findings:
        print(f'\n{len(findings)} advisory finding(s) in {path}; nothing gates.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
