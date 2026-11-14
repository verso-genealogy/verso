"""verso.ru.census_revisions: the revision chain is history; a village's frozen exceptions are its data."""
from __future__ import annotations

from pathlib import Path

from verso.ru import corpus_data
from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR, prev_revision_year


def test_the_library_table_is_the_revision_chain() -> None:
    assert [prev_revision_year(y) for y in (1721, 1815, 1857, 1858)] == [1719, 1811, 1850, 1850]
    assert prev_revision_year(1782) is None
    assert PREVIOUS_AGE_REVISION_YEAR[1816] == 1811


def test_a_village_override_wins_and_false_means_none() -> None:
    assert prev_revision_year(1815, {1815: 1795}) == 1795
    assert prev_revision_year(1857, {1857: None}) is None
    assert prev_revision_year(1816, {1815: 1795}) == 1811


def test_village_toml_states_the_overrides(tmp_path: Path) -> None:
    (tmp_path / "village.toml").write_text(
        "schema = 1\n[census]\nprev_revision = { 1721 = false, 1815 = 1795 }\n", encoding="utf-8")
    assert dict(corpus_data.village(tmp_path).prev_revision) == {1721: None, 1815: 1795}
