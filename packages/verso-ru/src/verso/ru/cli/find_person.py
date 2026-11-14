"""Search village.db by name fragment, with optional year/type filters.

Served by the FTS5 trigram index when village.db has one and the query is at
least three characters; otherwise by a full scan with LIKE, which matches only
in the case the query was written. See verso/ru/search.py for why both exist.
"""
import argparse
import shlex
import sqlite3
import sys
from pathlib import Path

from verso.ru.cli.all_persons import newer_than_db
from verso.ru.search import FTS_TABLE, MIN_QUERY_LEN, match_expression, usable_for
from verso.ru.messages import t

def rebuild_command(village_arg: object) -> str:
    """The command that rebuilds `village.db`, the village quoted for a shell."""
    return f"verso all-persons {shlex.quote(str(village_arg))}"


def stale_warning(stale: list[Path], village_arg: object) -> str:
    """Warning text naming how many DSL files post-date the index."""
    shown = ", ".join(f.name for f in stale[:3])
    more = f" (+{len(stale) - 3} more)" if len(stale) > 3 else ""
    return (
        f"WARNING: village.db is older than {len(stale)} DSL file(s) — {shown}{more}.\n"
        f"         Results may be missing recent records; a 'not found' here is NOT\n"
        f"         proof of absence. Rebuild with: {rebuild_command(village_arg)}"
    )


def output_columns() -> list[str]:
    return [str(t("cli.find_person.column.year")), str(t("cli.find_person.column.type")),
            str(t("cli.find_person.column.number")), str(t("cli.find_person.column.role")),
            str(t("cli.find_person.column.birth")), str(t("cli.find_person.column.death")),
            str(t("cli.find_person.column.name")), str(t("cli.find_person.column.status")),
            str(t("cli.find_person.column.residence")), str(t("cli.find_person.column.file"))]

WIDTHS = [6, 10, 6, 18, 14, 14, 30, 20, 20, 36]

BASE_QUERY = """
SELECT
    p.year, p.record_type, p.record_num, p.role,
    p.birth_date, p.death_date, p.fio, p.status, p.residence, p.source_file,
    b.b_day, b.b_month, b.k_day, b.k_month,
    m.w_day, m.w_month, m.groom_marriage_num, m.bride_marriage_num,
    d.d_day, d.d_month, d.age, d.cause_of_death,
    ch.comment AS household_comment
FROM persons p
LEFT JOIN births b ON p.record_type = 'рождение' AND p.record_id = b.id
LEFT JOIN marriages m ON p.record_type = 'брак' AND p.record_id = m.id
LEFT JOIN deaths d ON p.record_type = 'смерть' AND p.record_id = d.id
LEFT JOIN divorces dv ON p.record_type = 'развод' AND p.record_id = dv.id
LEFT JOIN census_households ch ON p.record_type IN ('ревизия', 'исповедная роспись')
     AND p.record_id = ch.id
"""  # i18n: content — village.db's record types, as the query joins on them

# The two ways to ask the same question. The index is the fast one AND the
# correct one: SQLite's LIKE folds case for ASCII only, so «чичиков» typed in
# lower case finds nothing at all through the scan. Both are kept because the
# index cannot serve a query shorter than one trigram, and because an FTS5-less
# SQLite must still be able to search. See verso/ru/search.py.
FTS_PREDICATE = f"JOIN {FTS_TABLE} f ON f.rowid = p.id AND f.txt MATCH ?"

LIKE_PREDICATE = """
WHERE (p.fio LIKE ? OR p.name_modern LIKE ? OR p.patr_old LIKE ? OR p.patr_modern LIKE ?
       OR p.last_name_modern LIKE ? OR p.iof_orig LIKE ? OR p.iof_modern LIKE ?)
"""


def build_query(use_fts: bool, query: str) -> tuple[str, list[object]]:
    """The SELECT and its parameters, indexed or scanned."""
    if use_fts:
        return BASE_QUERY.replace("FROM persons p", f"FROM persons p\n{FTS_PREDICATE}") + " WHERE 1=1", [match_expression(query)]
    return BASE_QUERY + LIKE_PREDICATE, [f"%{query}%"] * 7


def print_row(values: list[str]) -> None:
    parts = [v.ljust(w) for v, w in zip(values, WIDTHS, strict=False)]
    print("  ".join(parts).rstrip()[:200])


def main() -> None:
    parser = argparse.ArgumentParser(description="Search person records in village.db.")
    parser.add_argument("village_dir", type=Path, help="Village directory")
    parser.add_argument(
        "query",
        help="Substring to search for. Case-insensitive from 3 characters up; "
             "shorter queries fall back to a scan that folds ASCII case only.",
    )
    parser.add_argument("--year", type=int, help="Filter by year")
    parser.add_argument(
        "--type",
        dest="record_type",
        choices=["рождение", "брак", "смерть", "развод", "ревизия",  # i18n: content — village.db's record types, as --type takes them
                 "исповедная роспись",  # i18n: content — village.db's record types
                 "судимость", "военная служба", "Великая Отечественная война",  # i18n: content — village.db's record types
                 "Именной список"],  # i18n: content — village.db's record types
        help="Filter by record type",
    )
    args = parser.parse_args()

    village_dir = args.village_dir.resolve()
    db_path = village_dir / "village.db"

    if not db_path.exists():
        print(
            f"Error: {db_path} not found. "
            f"Run {rebuild_command(args.village_dir)} to generate it.",
            file=sys.stderr,
        )
        sys.exit(1)

    # A stale index and a genuine absence look identical, so a "not found" from
    # an out-of-date village.db is a silent wrong answer — the reason this warns
    # rather than staying quiet. It never blocks the query.
    stale = newer_than_db(village_dir, db_path)
    if stale:
        print(stale_warning(stale, args.village_dir), file=sys.stderr)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    use_fts = usable_for(conn, args.query)
    if not use_fts and len(args.query) >= MIN_QUERY_LEN:
        print(
            "NOTE: village.db has no full-text index — falling back to a scan, and "
            "a Cyrillic query only matches in the case it was written. Rebuild with: "
            f"{rebuild_command(args.village_dir)}",
            file=sys.stderr,
        )
    sql, params = build_query(use_fts, args.query)

    if args.year is not None:
        sql += " AND p.year = ?"
        params.append(args.year)
    if args.record_type is not None:
        sql += " AND p.record_type = ?"
        params.append(args.record_type)
    sql += " ORDER BY p.year, p.record_num"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    print_row(output_columns())
    print("-" * 160)

    for row in rows:
        year, record_type, record_num, role, birth_date, death_date, fio, status, residence, source_file = row[:10]
        print_row([
            str(year),
            record_type,
            str(record_num),
            role,
            birth_date or "",
            death_date or "",
            fio or "",
            status or "",
            residence or "",
            source_file or "",
        ])

    print()
    if stale:
        print(stale_warning(stale, args.village_dir), file=sys.stderr)
    if rows:
        print(f"Found {len(rows)} rows.")
    else:
        print("No matches found.")


if __name__ == "__main__":
    main()
