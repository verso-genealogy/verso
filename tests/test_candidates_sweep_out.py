"""`candidates --sweep --out`: everything the sweep writes goes where it is told.

A corpus's output check runs the sweep on the checkout under test and must write nothing into it: a
village's sweep.candidates.json and sweep_consolidation_report.md are the workspace's
own triage, not the gate's."""
from __future__ import annotations

from pathlib import Path

from verso.ru.consolidation import candidates
from tests.test_pipeline_config import _village


def test_a_sweep_given_out_writes_nothing_into_the_village(tmp_path: Path):
    village = _village(tmp_path, "А", None)
    out = tmp_path / "out" / "sweep.candidates.json"
    out.parent.mkdir()
    assert candidates.main(["--sweep", "--village", str(village), "--out", str(out)]) == 0
    assert out.is_file()
    assert (out.parent / "sweep_consolidation_report.md").is_file()
    assert sorted(p.name for p in village.iterdir()) == ["1800"]


def test_a_sweep_without_out_writes_beside_the_village_as_before(tmp_path: Path):
    village = _village(tmp_path, "А", None)
    assert candidates.main(["--sweep", "--village", str(village)]) == 0
    assert (village / "sweep.candidates.json").is_file()
    assert (village / "sweep_consolidation_report.md").is_file()
