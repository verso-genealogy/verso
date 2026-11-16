"""verso.core.targets.geni.fmt — `terraform fmt` over a tree, its files in parallel groups."""
from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from verso.core.targets.geni import fmt
from verso.core.tools import ToolNotFound


def _write(path: Path, text: str = "x = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_targets_are_what_terraform_fmt_reads(tmp_path: Path) -> None:
    for name in ("b.tf", "a.tf", "vars.tfvars", "t.tftest.hcl", "m.tfmock.hcl", "notes.md", "plan.json",
                 ".hidden.tf", "~lock.tf", "backup.tf~", "#auto#"):
        _write(tmp_path / name)
    _write(tmp_path / "sub" / "c.tf")
    _write(tmp_path / ".terraform" / "d.tf")
    names = [p.name for p in fmt.targets(tmp_path)]
    assert names == ["a.tf", "b.tf", "m.tfmock.hcl", "t.tftest.hcl", "vars.tfvars"]
    deep = [p.relative_to(tmp_path).as_posix() for p in fmt.targets(tmp_path, recursive=True)]
    assert deep == ["a.tf", "b.tf", "m.tfmock.hcl", "sub/c.tf", "t.tftest.hcl", "vars.tfvars"]


def test_groups_hold_every_file_once_balanced_by_bytes(tmp_path: Path) -> None:
    files = [_write(tmp_path / f"f{i}.tf", "x" * (i * 100)) for i in range(1, 11)]
    dealt = fmt.groups(files, 3)
    assert len(dealt) == 3
    assert sorted(f for g in dealt for f in g) == sorted(files)
    weights = [sum(f.stat().st_size for f in g) for g in dealt]
    assert max(weights) - min(weights) <= 1000


def test_groups_never_more_than_files_nor_too_long(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = [_write(tmp_path / f"f{i}.tf") for i in range(5)]
    assert len(fmt.groups(files, 8)) == 5
    assert len(fmt.groups(files, 1)) == 1
    monkeypatch.setattr(fmt, "_MAX_FILES", 2)
    dealt = fmt.groups(files, 1)
    assert len(dealt) == 3 and all(len(g) <= 2 for g in dealt)


def _stub_terraform(bin_dir: Path, log: Path, *, fails: bool = False) -> None:
    """A `terraform` that writes its arguments, one call a line, into `log`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "terraform"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit {1 if fails else 0}\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def test_every_file_goes_to_terraform_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = tmp_path / "tree"
    files = [_write(tree / f"f{i}.tf") for i in range(7)] + [_write(tree / "sub" / "g.tf")]
    log = tmp_path / "calls.txt"
    _stub_terraform(tmp_path / "bin", log)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    fmt.terraform_fmt(tree, recursive=True, jobs=3)
    calls = [line.split() for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 3
    assert all(call[:2] == ["fmt", "-list=false"] for call in calls)
    assert sorted(arg for call in calls for arg in call[2:]) == sorted(map(str, files))


def test_best_effort_without_terraform_and_on_its_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = tmp_path / "tree"
    _write(tree / "a.tf")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    fmt.terraform_fmt(tree)                                  # no terraform: nothing done, nothing raised
    with pytest.raises(ToolNotFound):
        fmt.terraform_fmt(tree, check=True)
    _stub_terraform(tmp_path / "bin", tmp_path / "calls.txt", fails=True)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    fmt.terraform_fmt(tree)                                  # a failing terraform, best-effort: no error
    with pytest.raises(subprocess.CalledProcessError):
        fmt.terraform_fmt(tree, check=True)


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform is not on PATH")
def test_the_same_bytes_as_one_terraform_fmt_of_the_directory(tmp_path: Path) -> None:
    unformatted = 'resource "x" "a" {\n  a = 1\n  bbbb = 2\n  nested {\n    c = "d"\n      e = 3\n  }\n}\n'
    for root in (tmp_path / "one", tmp_path / "many"):
        for i in range(6):
            _write(root / f"f{i}.tf", unformatted.replace('"a"', f'"a{i}"'))
        _write(root / "sub" / "g.tf", unformatted)
    subprocess.run(["terraform", "fmt", "-recursive", str(tmp_path / "one")], check=True, capture_output=True)
    fmt.terraform_fmt(tmp_path / "many", recursive=True, check=True, jobs=4)
    for path in sorted((tmp_path / "one").rglob("*.tf")):
        twin = tmp_path / "many" / path.relative_to(tmp_path / "one")
        assert twin.read_bytes() == path.read_bytes()
    assert (tmp_path / "many" / "f0.tf").read_text(encoding="utf-8") != unformatted
