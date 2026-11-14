"""Tests for the FTS5 name index behind `find_person`.

The index replaces a `LIKE '%q%'` scan, so the property that matters is not
speed but that it answers the SAME question: «эта подстрока встречается хотя бы
в одном из семи столбцов имени». Every test here is a statement about the
result SET; none of them time anything.
"""

import sqlite3
import unittest

from verso.ru.cli.find_person import build_query
from verso.ru.search import (
    FTS_TABLE, MIN_QUERY_LEN, SEARCH_COLUMNS, build_index, fts5_available, has_index, index_text, match_expression, usable_for)

# fio, name_modern, patr_old, patr_modern, last_name_modern, iof_orig, iof_modern
PEOPLE = [
    (1, "Чичиков Иван Петрович", "Иван", "Петров", "Петрович", "Чичиков",
     "Иванъ Петровъ Чичиковъ", "Иван Петрович Чичиков"),
    (2, "Чичикова Прасковья Ивановна", "Прасковья", "Иванов", "Ивановна", "Чичикова",
     "Параскева Иванова Чичикова", "Прасковья Ивановна Чичикова"),
    (3, "Лодырев Фёдор Кузьмич", "Фёдор", "Кузьмин", "Кузьмич", "Лодырев",
     "Ѳеодоръ Косьминъ Лодыревъ", "Фёдор Кузьмич Лодырев"),
    (4, "Жевакин Пётр Сергеевич", "Пётр", "Сергеев", "Сергеевич", "Жевакин",
     "Петръ Сергіевъ Жевакинъ", "Пётр Сергеевич Жевакин"),
]


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE persons (id INTEGER PRIMARY KEY, record_type TEXT, record_id INTEGER, "
        "year INTEGER, record_num INTEGER, role TEXT, "
        + ", ".join(f"{c} TEXT" for c in SEARCH_COLUMNS)
        + ", status TEXT, residence TEXT, birth_date TEXT, death_date TEXT, source_file TEXT)"
    )
    for table in ("births", "marriages", "deaths", "divorces"):
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE census_households (id INTEGER PRIMARY KEY, comment TEXT)")
    conn.executemany(
        f"INSERT INTO persons (id, {', '.join(SEARCH_COLUMNS)}) VALUES "
        f"({', '.join('?' * (len(SEARCH_COLUMNS) + 1))})",
        PEOPLE,
    )
    conn.commit()
    return conn


def ground_truth(query: str) -> set[int]:
    """What a case-insensitive substring search must return, computed in Python."""
    q = query.lower()
    return {
        row[0] for row in PEOPLE if any(v and q in v.lower() for v in row[1:])
    }


def ids_via_index(conn: sqlite3.Connection, query: str) -> set[int]:
    return {
        row[0]
        for row in conn.execute(
            f"SELECT p.id FROM persons p JOIN {FTS_TABLE} f "
            f"ON f.rowid = p.id AND f.txt MATCH ?",
            (match_expression(query),),
        )
    }


@unittest.skipUnless(fts5_available(sqlite3.connect(":memory:")), "SQLite without FTS5")
class TestIndexAnswersTheSameQuestion(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()
        build_index(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_index_is_built_over_every_person(self):
        self.assertTrue(has_index(self.conn))
        n = self.conn.execute(f"SELECT count(*) FROM {FTS_TABLE}").fetchone()[0]
        self.assertEqual(n, len(PEOPLE))

    def test_matches_the_python_ground_truth(self):
        for query in ("Чичиков", "Прасковья", "Лодырев", "Жевакин", "Ѳеодоръ",
                      "Иванов", "Петр", "овъ", "Иван Петрович", "нет такого"):
            with self.subTest(query=query):
                self.assertEqual(ids_via_index(self.conn, query), ground_truth(query))

    def test_case_is_ignored_for_cyrillic(self):
        """The reason the index exists: LIKE folds case for ASCII only, so a
        lower-case Cyrillic query used to return nothing at all."""
        expected = ground_truth("Чичиков")
        self.assertEqual(expected, {1, 2})
        for spelling in ("чичиков", "ЧИЧИКОВ", "Чичиков"):
            with self.subTest(spelling=spelling):
                self.assertEqual(ids_via_index(self.conn, spelling), expected)

    def test_a_match_never_straddles_two_columns(self):
        """Columns are joined by \\n precisely so that a query cannot match
        across the seam — «Чичиков Прасковья» is not a person."""
        self.assertEqual(ids_via_index(self.conn, "Чичиков Прасковья"), set())
        # ...while the same words inside one column do match.
        self.assertEqual(ids_via_index(self.conn, "Чичикова Прасковья"), {2})

    def test_like_wildcards_are_literal(self):
        """The query is a substring, not a LIKE pattern: through the scan
        «Чичиков%» silently matched everything, which the help never promised."""
        self.assertEqual(ids_via_index(self.conn, "Чичиков%"), set())
        self.assertEqual(ids_via_index(self.conn, "_ван"), set())

    def test_quotes_in_a_query_do_not_break_the_phrase(self):
        self.assertEqual(ids_via_index(self.conn, 'Чичиков"'), set())


class TestIndexText(unittest.TestCase):

    def test_lowercases_and_joins_with_newline(self):
        self.assertEqual(index_text(("Аб", "Вг")), "аб\nвг")

    def test_drops_empty_columns(self):
        self.assertEqual(index_text(("Аб", None, "", "Вг")), "аб\nвг")


class TestQuerySelection(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_short_query_falls_back_to_the_scan(self):
        build_index(self.conn)
        self.assertFalse(usable_for(self.conn, "ин"))
        self.assertEqual(len("ин") + 1, MIN_QUERY_LEN)

    def test_missing_index_falls_back_to_the_scan(self):
        """An FTS5-less SQLite must still search — slower, never wrong."""
        self.assertFalse(has_index(self.conn))
        self.assertFalse(usable_for(self.conn, "Чичиков"))

    def test_scan_query_carries_one_pattern_per_searched_column(self):
        sql, params = build_query(False, "Лодырев")
        self.assertEqual(params, ["%Лодырев%"] * len(SEARCH_COLUMNS))
        self.assertNotIn(FTS_TABLE, sql)

    def test_index_query_carries_a_single_phrase(self):
        sql, params = build_query(True, "Лодырев")
        self.assertEqual(params, ['"лодырев"'])
        self.assertIn(FTS_TABLE, sql)


if __name__ == "__main__":
    unittest.main()


def test_the_query_runs_against_a_village_db():
    """The SQL itself runs, both ways — a test of the parameters alone let a stray comment into it
    once (a `# …` marker inside BASE_QUERY, which SQLite does not read as a comment)."""
    import sqlite3

    from verso.ru.cli.all_persons import create_db

    conn = sqlite3.connect(":memory:")
    create_db(conn)
    for use_fts in (False, True):
        sql, params = build_query(use_fts, "Лодырев")
        try:
            assert conn.execute(sql, params).fetchall() == []
        except sqlite3.OperationalError as e:
            assert use_fts and "no such table" in str(e), e   # an FTS-less db: the index is built elsewhere
