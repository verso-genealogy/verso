"""The full-text index behind `find_person`, and the one place its rules live.

`village.db` is a search index for a human or an agent, not an analytical store:
one substring query per process, over a table that is at most a few tens of
thousands of rows. The query it has to answer is «дай всё, где встречается вот
эта подстрока», across seven name columns at once.

Done with `LIKE '%q%'` that is a full scan of every column — cheap in absolute
terms but linear in the corpus, and **ASCII-only case-insensitive**, so a
Cyrillic query typed in the wrong case silently returns nothing. In a project
where a "not found" is routinely read as proof of absence (see
`find_person.stale_warning`), that is a wrong answer wearing the clothes of an
answer.

An FTS5 **trigram** index fixes both. Trigram is the tokenizer that gives
substring semantics — `unicode61` would only match whole words, which is not
what this search is — and because the indexed text is lower-cased here, the
match is case-insensitive for Cyrillic as well, whatever the local SQLite does
about Unicode case folding.

Two decisions worth keeping:

- **Contentless** (`content=''`). The text is already in `persons`; storing it
  twice doubles the index for nothing. Measured on Заманиловка (30k persons):
  contentless 4.1 MB and 0.7 ms per match, stored 8.7 MB and 2.8 ms.
- **Columns joined by `\\n`, not by a space.** A trigram that spans the join
  contains `\\n`, and no query typed by a person ever does — so a match can never
  straddle two columns, and the index answers exactly what seven separate
  `LIKE`s would have. Joining with a space would quietly invent hits like
  «ов Иван» spanning `last_name_modern` → `name_modern`.

The index is built once, at the end of a full rebuild, and `village.db` is
dropped and recreated every time (`all_persons.main`), so there are no triggers
to keep it in sync and no way for it to drift from `persons` — the failure mode
that makes hand-maintained FTS tables a liability. Staleness against the DSL is
a separate question, and the one `find_person` already warns about.
"""
from __future__ import annotations

import sqlite3

#: Columns of `persons` that a name search looks at, in the order they are
#: indexed. Kept here so the writer and the reader cannot disagree.
SEARCH_COLUMNS: tuple[str, ...] = (
    "fio",
    "name_modern",
    "patr_old",
    "patr_modern",
    "last_name_modern",
    "iof_orig",
    "iof_modern",
)

FTS_TABLE = "persons_fts"

#: A trigram index cannot answer a query shorter than one trigram. Such a query
#: falls back to the scan; it matches thousands of rows anyway and is not a
#: search in any useful sense.
MIN_QUERY_LEN = 3

#: Column separator — see the module docstring. Never appears in a user query.
_JOIN = "\n"


def index_text(values: tuple[str | None, ...]) -> str:
    """The searchable blob for one person row, lower-cased and `\\n`-joined."""
    return _JOIN.join(v for v in values if v).lower()


def fts5_available(conn: sqlite3.Connection) -> bool:
    """True when this SQLite can create an FTS5 trigram table.

    FTS5 is compiled into every build we have met, but it is an option, not a
    guarantee — so the index is built when possible and simply absent when not,
    and `find_person` falls back to the scan. A missing index must degrade
    performance, never correctness.
    """
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE temp._fts5_probe USING fts5(x, tokenize='trigram')"
        )
    except sqlite3.Error:
        return False
    conn.execute("DROP TABLE temp._fts5_probe")
    return True


def has_index(conn: sqlite3.Connection) -> bool:
    """True when `village.db` carries a usable full-text index."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (FTS_TABLE,)
    ).fetchone()
    return row is not None


def build_index(conn: sqlite3.Connection) -> int:
    """(Re)build the full-text index over `persons`. Returns rows indexed.

    A no-op returning 0 when the local SQLite has no FTS5.
    """
    if not fts5_available(conn):
        return 0
    conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")
    conn.execute(
        f"CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5("
        f"    txt, tokenize = 'trigram', content = ''"
        f")"
    )
    rows = conn.execute(
        f"SELECT id, {', '.join(SEARCH_COLUMNS)} FROM persons"
    ).fetchall()
    conn.executemany(
        f"INSERT INTO {FTS_TABLE}(rowid, txt) VALUES (?, ?)",
        ((row[0], index_text(row[1:])) for row in rows),
    )
    conn.commit()
    return len(rows)


def match_expression(query: str) -> str:
    """`query` as an FTS5 phrase: lower-cased, quoted, inner quotes doubled.

    Quoting is what makes the whole query one phrase rather than a bag of
    tokens, so «Анна Ивановна» keeps its word order and its space.
    """
    return '"' + query.lower().replace('"', '""') + '"'


def usable_for(conn: sqlite3.Connection, query: str) -> bool:
    """True when this query should go through the index rather than the scan."""
    return len(query) >= MIN_QUERY_LEN and has_index(conn)
