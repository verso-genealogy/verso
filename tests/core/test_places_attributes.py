"""A place's attributes beyond its fields are the plugins': the core reads `city`,
`county`, `state`, `country` and `same_as`; the toy adds `toy_id`, ru adds `familio`."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import places, plugins, workspace
from verso.core.places import PlacesError

TEXT = '["Вязовка"]\ncity = "Вязовка"\ntoy_id = "17"\n\n["Вязовка СССР"]\nsame_as = "Вязовка"\n'


@pytest.mark.usefixtures("toy_workspace")
def test_a_place_attribute_is_a_plugins():
    read = places.parse(TEXT)
    assert read.attributes == {"toy_id": {"Вязовка": "17"}}
    with pytest.raises(PlacesError, match="unknown key «familio»"):
        places.parse('["Вязовка"]\ncity = "Вязовка"\nfamilio = "u"\n')


def test_the_core_alone_reads_no_attribute(tmp_path: Path):
    (tmp_path / "verso.toml").write_text("schema = 4\n", encoding="utf-8")
    with plugins.adding(entry_points=False), workspace.use(tmp_path), \
            pytest.raises(PlacesError, match="unknown key «toy_id»"):
        places.parse(TEXT)


@pytest.mark.usefixtures("toy_workspace")
def test_verify_keeps_every_attribute():
    changed = TEXT.replace('toy_id = "17"', 'toy_id = "18"') + '\n["Дубки"]\ncity = "Дубки"\n'
    with pytest.raises(PlacesError, match="the edit changed the place «Вязовка»"):
        places.verify(TEXT, changed, "Дубки")
    kept = TEXT + '\n["Дубки"]\ncity = "Дубки"\n'
    assert places.verify(TEXT, kept, "Дубки").attributes == {"toy_id": {"Вязовка": "17"}}


@pytest.mark.usefixtures("toy_workspace")
def test_names_tables_are_the_plugins_in_order():
    assert plugins.names_tables() == ("toy_names.csv",)


def test_the_core_names_no_names_table():
    from verso.core import workspace as ws
    from verso.core.pipeline import records
    assert not hasattr(ws, "NAMES_FILES")
    assert not hasattr(records, "NAMES_TABLES")
