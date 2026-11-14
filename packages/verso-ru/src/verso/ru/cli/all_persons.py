"""
Aggregates all persons from year-record files under a village directory into village.db.
5 normalized tables: births, marriages, deaths, census_households, persons.

Usage: python3 all_persons.py <village_dir>
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.census import CensusRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.divorces import DivorceRecords
from verso.ru.dsl.records.external_sources import ExternalSourceRecords
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.dsl.records.name_lists import NameListRecords
from verso.core.records.sets import record_sets
from verso.ru.naming import derive_patronymic, derive_old_patronymic
from verso.core.pipeline.load import load_module
from verso.ru.dsl.kinds import SOURCE_PATTERNS
from verso.ru.relationship import Relationship
from verso.ru.search import build_index

RELATIONSHIP_LABEL = {
    Relationship.HUSBAND: "муж",
    Relationship.WIFE: "жена",
    Relationship.FATHER: "отец",
    Relationship.MOTHER: "мать",
    Relationship.SON: "сын",
    Relationship.DAUGHTER: "дочь",
    Relationship.FATHER_IN_LAW: "свёкор",
    Relationship.MOTHER_IN_LAW: "свекровь",
    Relationship.SON_IN_LAW: "зять",
    Relationship.DAUGHTER_IN_LAW: "сноха",
}

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS births (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    record_num INTEGER,
    b_day INTEGER,
    b_month INTEGER,
    k_day INTEGER,
    k_month INTEGER,
    page TEXT,
    comment TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS marriages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    record_num INTEGER,
    w_day INTEGER,
    w_month INTEGER,
    groom_marriage_num INTEGER,
    bride_marriage_num INTEGER,
    page TEXT,
    comment TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS deaths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    record_num INTEGER,
    d_day INTEGER,
    d_month INTEGER,
    age REAL,
    cause_of_death TEXT,
    page TEXT,
    comment TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS divorces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    record_num INTEGER,
    d_day INTEGER,
    d_month INTEGER,
    husband_age INTEGER,
    wife_age INTEGER,
    marriage_date TEXT,
    children TEXT,
    initiator TEXT,
    page TEXT,
    comment TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS census_households (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    household_idx INTEGER,
    page TEXT,
    comment TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT,
    record_id INTEGER,
    year INTEGER,
    record_num INTEGER,
    role TEXT,
    name_orig TEXT,
    patr_orig TEXT,
    last_name TEXT,
    name_modern TEXT,
    patr_old TEXT,
    patr_modern TEXT,
    last_name_modern TEXT,
    fio TEXT,
    status TEXT,
    residence TEXT,
    gender TEXT,
    birth_date TEXT,
    death_date TEXT,
    iof_orig TEXT,
    iof_modern TEXT,
    source_file TEXT
);
"""

INSERT_PERSON = """
INSERT INTO persons (
    record_type, record_id, year, record_num, role,
    name_orig, patr_orig, last_name,
    name_modern, patr_old, patr_modern, last_name_modern,
    fio, status, residence, gender,
    birth_date, death_date,
    iof_orig, iof_modern, source_file
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def create_db(conn: sqlite3.Connection) -> None:
    conn.executescript(CREATE_TABLES)
    conn.commit()


def format_date(day, month, year):
    if day and month:
        return f"{day:02d}.{month.value:02d}.{year}"
    if month:
        return f"{month.value:02d}.{year}"
    if year:
        return str(year)
    return ""


def person_values(record_type, record_id, year, record_num, role, birth_date, death_date, p, source_file):
    fio = p.get_fio() or ""
    iof_orig = " ".join(filter(None, [p.name_orig, p.patr_orig, p.last_name]))
    iof_modern = " ".join(filter(None, [p.name_modern, p.patr_old, p.last_name_modern]))
    gender = p.gender.value if p.gender else ""
    return (
        record_type,
        record_id,
        year,
        record_num,
        role,
        p.name_orig or "",
        p.patr_orig or "",
        p.last_name or "",
        p.name_modern or "",
        p.patr_old or "",
        p.patr_modern or "",
        p.last_name_modern or "",
        fio,
        p.status or "",
        p.residence or "",
        gender,
        birth_date,
        death_date,
        iof_orig,
        iof_modern,
        source_file,
    )


def insert_births(conn: sqlite3.Connection, records: BirthRecords, source_file: str) -> int:
    year = records.year
    count = 0
    for b in records.records:
        cur = conn.execute(
            "INSERT INTO births (year, record_num, b_day, b_month, k_day, k_month, page, comment, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                year,
                b.record_num,
                b.b_day,
                b.b_month.value if b.b_month else None,
                b.k_day,
                b.k_month.value if b.k_month else None,
                b.page,
                b.comment,
                source_file,
            ),
        )
        record_id = cur.lastrowid

        if b.child is not None and not b.child.patr_old and b.father is not None:
            canonical = derive_patronymic(b.father.name_modern, b.child.gender)
            b.child.patr_modern = canonical
            old_form = derive_old_patronymic(b.father.name_modern, b.child.gender)
            if old_form:
                b.child.patr_old = old_form

        birth_date = format_date(b.b_day, b.b_month, year)
        slots = [
            ("ребенок", b.child, birth_date, ""),
            ("отец", b.father, "", ""),
            ("мать", b.mother, "", ""),
            ("восприемник_1", b.god_parent1, "", ""),
            ("восприемник_2", b.god_parent2, "", ""),
        ]
        for role, p, bd, dd in slots:
            if p is not None:
                conn.execute(INSERT_PERSON, person_values("рождение", record_id, year, b.record_num, role, bd, dd, p, source_file))
                count += 1
        for rel in b.relatives:
            rel_label = ("родственник" if rel.relationship is None
                         else RELATIONSHIP_LABEL.get(rel.relationship, str(rel.relationship)))
            conn.execute(INSERT_PERSON, person_values("рождение", record_id, year, b.record_num, rel_label, "", "", rel.person, source_file))
            count += 1
    return count


def insert_marriages(conn: sqlite3.Connection, records: MarriageRecords, source_file: str) -> int:
    year = records.year
    count = 0
    for m in records.records:
        cur = conn.execute(
            "INSERT INTO marriages (year, record_num, w_day, w_month, groom_marriage_num, bride_marriage_num, page, comment, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                year,
                m.record_num,
                m.w_day,
                m.w_month.value if m.w_month else None,
                m.groom_marriage_num,
                m.bride_marriage_num,
                m.page,
                m.comment,
                source_file,
            ),
        )
        record_id = cur.lastrowid

        slots = [
            ("жених", m.groom),
            ("невеста", m.bride),
            ("свидетель_1", m.witness1),
            ("свидетель_2", m.witness2),
            ("свидетель_3", m.witness3),
            ("свидетель_4", m.witness4),
        ]
        for role, p in slots:
            if p is not None:
                conn.execute(INSERT_PERSON, person_values("брак", record_id, year, m.record_num, role, "", "", p, source_file))
                count += 1
        for rel in m.relatives:
            rel_label = ("родственник" if rel.relationship is None
                         else RELATIONSHIP_LABEL.get(rel.relationship, str(rel.relationship)))
            conn.execute(INSERT_PERSON, person_values("брак", record_id, year, m.record_num, rel_label, "", "", rel.person, source_file))
            count += 1
    return count


def insert_deaths(conn: sqlite3.Connection, records: DeathRecords, source_file: str) -> int:
    year = records.year
    count = 0
    for d in records.records:
        cur = conn.execute(
            "INSERT INTO deaths (year, record_num, d_day, d_month, age, cause_of_death, page, comment, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                year,
                d.record_num,
                d.d_day,
                d.d_month.value if d.d_month else None,
                d.age,
                d.cause_of_death,
                d.page,
                d.comment,
                source_file,
            ),
        )
        record_id = cur.lastrowid

        death_date = format_date(d.d_day, d.d_month, year)
        est_birth = ""
        if d.age is not None and isinstance(d.age, (int, float)):
            est_birth = str(year - int(d.age))

        if d.deceased is not None:
            conn.execute(INSERT_PERSON, person_values("смерть", record_id, year, d.record_num, "умерший", est_birth, death_date, d.deceased, source_file))
            count += 1

        if d.relative is not None:
            rel = d.relationship
            rel_label = "родственник" if rel is None else RELATIONSHIP_LABEL.get(rel, str(rel))
            conn.execute(INSERT_PERSON, person_values("смерть", record_id, year, d.record_num, rel_label, "", "", d.relative, source_file))
            count += 1

        for i, w in enumerate([d.witness1, d.witness2], start=1):
            if w is not None:
                conn.execute(INSERT_PERSON, person_values("смерть", record_id, year, d.record_num, f"свидетель_{i}", "", "", w, source_file))
                count += 1
    return count


def insert_divorces(conn: sqlite3.Connection, records: DivorceRecords, source_file: str) -> int:
    year = records.year
    count = 0
    for dv in records.records:
        cur = conn.execute(
            "INSERT INTO divorces (year, record_num, d_day, d_month, husband_age, wife_age, "
            "marriage_date, children, initiator, page, comment, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                year,
                dv.record_num,
                dv.d_day,
                dv.d_month.value if dv.d_month else None,
                dv.husband_age,
                dv.wife_age,
                dv.marriage_date,
                dv.children,
                dv.initiator,
                dv.page,
                dv.comment,
                source_file,
            ),
        )
        record_id = cur.lastrowid

        if dv.husband is not None:
            conn.execute(INSERT_PERSON, person_values("развод", record_id, year, dv.record_num, "муж", "", "", dv.husband, source_file))
            count += 1
        if dv.wife is not None:
            conn.execute(INSERT_PERSON, person_values("развод", record_id, year, dv.record_num, "жена", "", "", dv.wife, source_file))
            count += 1
    return count


def insert_census(conn: sqlite3.Connection, records: CensusRecords, source_file: str) -> int:
    """Insert one persons row per household-list member so `find_person`
    surfaces them. Covers both sources that share the двор → люди shape: a
    ревизская сказка and an исповедная роспись. `records.record_type` is the
    label they are stored under («ревизия» / «исповедная роспись»), so a year
    holding both stays separable."""
    year = records.year
    count = 0
    for idx, h in enumerate(records.households):
        cur = conn.execute(
            "INSERT INTO census_households (year, household_idx, page, comment, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            (year, idx, h.page, h.comment, source_file),
        )
        record_id = cur.lastrowid

        for m in h.members:
            # A role-less member is NOT skipped: `role=None` is a legitimate
            # reading — a roll lists солдатки, вдовы and lodgers by name and
            # age without ever saying how they stand to the head. Dropping
            # them would hide real people from `find_person`; the empty role
            # says what the source says.
            est_birth = ""
            if isinstance(m.age, int):
                est_birth = str(year - m.age)
            conn.execute(
                INSERT_PERSON,
                person_values(records.record_type, record_id, year,
                              h.family_id or idx,
                              m.role.value if m.role is not None else "",
                              est_birth, "", m.person, source_file),
            )
            count += 1
    return count


def insert_external(conn: sqlite3.Connection, records: ExternalSourceRecords, source_file: str) -> int:
    """Insert one persons row per external-source record (судимость / военная
    служба) so `find_person` surfaces the proof. record_type carries the kind
    label; there is no parent table, so `res_key` (the source № or positional
    index) doubles as record_id / record_num."""
    count = 0
    for r in records.records:
        birth_date = str(r.birth_year) if r.birth_year else ""
        conn.execute(
            INSERT_PERSON,
            person_values(r.kind.value, r.res_key, r.event_year, r.res_key,
                          "external", birth_date, "", r.person, source_file),
        )
        count += 1
    return count


def insert_name_lists(conn: sqlite3.Connection, records: NameListRecords, source_file: str) -> int:
    """Insert one persons row per name-list entry (e.g. 1917 voter lists) so
    `find_person` surfaces them. record_type is a fixed generic label
    ("Именной список") rather than the free-string `document_type`, since the
    CLI's `--type` filter needs a stable, enumerable value; there is no
    parent table, so the entry `number` doubles as record_id / record_num."""
    year = records.year
    count = 0
    for e in records.entries:
        by = e.birth_year(year)
        birth_date = str(by) if by else ""
        conn.execute(
            INSERT_PERSON,
            person_values("Именной список", e.number, year, e.number,
                          "listed", birth_date, "", e.person, source_file),
        )
        count += 1
    return count


def newer_than_db(village_dir: Path, db_path: Path) -> list[Path]:
    """Source DSL files modified after `db_path` was built (empty if fresh)."""
    if not db_path.exists():
        return []
    db_mtime = db_path.stat().st_mtime
    stale = [
        f for pattern in SOURCE_PATTERNS
        for f in village_dir.glob(pattern)
        if f.stat().st_mtime > db_mtime
    ]
    return sorted(stale)


def main():
    parser = argparse.ArgumentParser(description="Aggregate person records into village.db.")
    parser.add_argument("village_dir", type=Path, help="Village directory")
    args = parser.parse_args()

    village_dir = args.village_dir.resolve()
    if not village_dir.is_dir():
        print(f"Error: {village_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    db_path = village_dir / "village.db"

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    create_db(conn)

    for pattern, inserter in [
        (SOURCE_PATTERNS[0], insert_births),
        (SOURCE_PATTERNS[1], insert_marriages),
        (SOURCE_PATTERNS[2], insert_deaths),
        (SOURCE_PATTERNS[3], insert_divorces),
        (SOURCE_PATTERNS[4], insert_census),
        (SOURCE_PATTERNS[5], insert_census),
        (SOURCE_PATTERNS[6], insert_external),
        (SOURCE_PATTERNS[7], insert_name_lists),
    ]:
        for path in sorted(village_dir.glob(pattern)):
            try:
                mod, name = load_module(path), path.stem
            except Exception as e:
                print(f"WARNING: failed to load {path}: {e}")
                continue
            records_obj = getattr(mod, name, None)
            if records_obj is None:
                # Census and confession-list files both use 'census'.
                records_obj = getattr(mod, "census", None)
            if records_obj is not None:
                source_file = str(path.relative_to(village_dir))
                inserter(conn, records_obj, source_file)
            else:
                # Scan module for all matching record instances (e.g. multi-village census files)
                expected_type = {
                    insert_births: BirthRecords,
                    insert_marriages: MarriageRecords,
                    insert_deaths: DeathRecords,
                    insert_divorces: DivorceRecords,
                    insert_census: CensusRecords,
                    insert_external: ExternalSourceRecords,
                    insert_name_lists: NameListRecords,
                }[inserter]
                found = list(record_sets(vars(mod), expected_type).values())
                if not found:
                    print(f"WARNING: {path} has no {expected_type.__name__} objects, skipping")
                    continue
                source_file = str(path.relative_to(village_dir))
                for obj in found:
                    inserter(conn, obj, source_file)

    conn.commit()

    # Built last, in one pass over the finished table: village.db is dropped and
    # recreated on every run, so the index cannot drift from `persons` and needs
    # no triggers. 0 means this SQLite has no FTS5 and search falls back to the
    # scan — slower, never wrong. See verso/ru/search.py.
    n_indexed = build_index(conn)

    n_births = conn.execute("SELECT count(*) FROM births").fetchone()[0]
    n_marriages = conn.execute("SELECT count(*) FROM marriages").fetchone()[0]
    n_deaths = conn.execute("SELECT count(*) FROM deaths").fetchone()[0]
    n_divorces = conn.execute("SELECT count(*) FROM divorces").fetchone()[0]
    n_census = conn.execute("SELECT count(*) FROM census_households").fetchone()[0]
    n_persons = conn.execute("SELECT count(*) FROM persons").fetchone()[0]
    conn.close()

    print(f"Loaded {n_births} births, {n_marriages} marriages, {n_deaths} deaths, {n_divorces} divorces, {n_census} census households, {n_persons} persons")
    if n_indexed:
        print(f"Full-text index: {n_indexed} persons")
    else:
        print("Full-text index: SKIPPED (no FTS5 in this SQLite) — search falls back to a scan")
    print(f"Database: {db_path}")


if __name__ == "__main__":
    main()
