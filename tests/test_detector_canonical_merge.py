"""WS2: detector handles canonical→canonical merges (CCN008-clean output +
source-entry deletion) instead of emitting a canonical key in profile_names."""

from __future__ import annotations

import ast
from pathlib import Path

from verso.ru.consolidation.detector import (
    create_consolidated_structure, delete_canonical_entries)


def test_canonical_member_is_expanded_to_its_stubs():
    profiles = {
        "anastasija_ivanovna_rotozeeva_2": {
            "profile_names": ["_1899_bride", "_1907_mother"]},
        "anastasija_ivanovna_teljatnikova": {
            "profile_names": ["_1900_mother", "_1902_mother"]},
    }
    # a Geni merge fused the two canonicals onto one id (sorted group)
    duplicates = {"profile-123": sorted(
        ["anastasija_ivanovna_rotozeeva_2", "anastasija_ivanovna_teljatnikova"])}

    new_entries, folded = create_consolidated_structure(duplicates, profiles)

    # source canonical folded into the alphabetically-first target
    assert folded == {"anastasija_ivanovna_teljatnikova": "anastasija_ivanovna_rotozeeva_2"}
    # target gains the SOURCE's raw stubs, never a canonical key (CCN008)
    target = new_entries["anastasija_ivanovna_rotozeeva_2"]["profile_names"]
    assert set(target) == {"_1900_mother", "_1902_mother"}
    all_names = {n for e in new_entries.values() for n in e["profile_names"]}
    assert not (all_names & set(profiles)), "no canonical key may appear in profile_names"


def test_pure_stub_group_unaffected():
    profiles = {}
    duplicates = {"profile-9": sorted(["_1892_child", "_1893_deceased"])}
    new_entries, folded = create_consolidated_structure(duplicates, profiles)
    assert folded == {}
    assert new_entries  # a normal fold still produced


def test_delete_canonical_entries_removes_source_entry(tmp_path: Path):
    cfg = tmp_path / "generate_config_names.py"
    cfg.write_text(
        "profiles_to_consolidate = {\n"
        '    "keep_me": {\n'
        '        "generate_moved_block": True,\n'
        '        "profile_names": [\n'
        '            "_a_stub",\n'
        "        ],\n"
        "    },\n"
        '    "drop_me": {\n'
        '        "generate_moved_block": True,\n'
        '        "profile_names": [\n'
        '            "_b_stub",\n'
        "        ],\n"
        "    },\n"
        "}\n",
        encoding="utf-8",
    )
    n = delete_canonical_entries(str(cfg), ["drop_me"])
    assert n == 1
    text = cfg.read_text(encoding="utf-8")
    assert "drop_me" not in text
    assert "keep_me" in text
    # still valid Python with the surviving entry intact
    tree = ast.parse(text)
    assign = next(x for x in tree.body if isinstance(x, ast.Assign))
    keys = {k.value for k in assign.value.keys}  # type: ignore[attr-defined]
    assert keys == {"keep_me"}
