"""The toy example (examples/): a workspace of its own the library runs end to end.

examples/run.py copies examples/toy/ and runs `verso` over the copy, step by step: the workspace,
the linters, the CSVs, the records JSON and its schema, Geni's Terraform, the facts, the святцы.
The copy reads nothing outside itself: the run is watched by the standalone sentinel."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
EXAMPLES = PROJECT / "examples"
LAST = "пример: 8 шагов прошли"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != "VERSO_WORKSPACE"}
    return subprocess.run([sys.executable, str(EXAMPLES / "run.py"), *args],
                          capture_output=True, text=True, env={**base, **(env or {})}, check=False)


def test_the_example_runs_end_to_end(tmp_path: Path):
    done = _run("--keep", str(tmp_path / "toy"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().splitlines()[-1] == LAST
    assert (tmp_path / "toy" / "records" / "Степанчиково" / "index.json").is_file()
    assert list((tmp_path / "toy" / "Степанчиково" / "terraform" / "geni").glob("mk_1850_*.tf"))


def test_the_example_is_its_own_workspace(tmp_path: Path):
    """A copy of toy/, run with every Python the run starts under the sentinel (a sitecustomize on
    PYTHONPATH) over the original toy/, the tests' fixtures and a corpus beside the project: none
    is read."""
    copy = tmp_path / "toy"
    shutil.copytree(EXAMPLES / "toy", copy)
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('verso_sentinel', {str(PROJECT / 'tests' / 'sentinel.py')!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "module.install_from_env()\n", encoding="utf-8")
    forbidden = [EXAMPLES / "toy", PROJECT / "tests" / "fixtures"]
    forbidden += [p for p in (PROJECT.parent / "corpus", PROJECT.parent / "names.csv") if p.exists()]
    log = tmp_path / "sentinel.log"
    pythonpath = os.pathsep.join(p for p in (str(site), os.environ.get("PYTHONPATH", "")) if p)
    done = _run("--workspace", str(copy), env={"PYTHONPATH": pythonpath,
                                               "VERSO_SENTINEL": os.pathsep.join(map(str, forbidden)),
                                               "VERSO_SENTINEL_LOG": str(log)})
    assert done.returncode == 0, done.stdout + done.stderr
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_example_uses_the_names_base():
    """The example's names are the base's (schema 6) plus a layer of its own: no old CSV tables."""
    import tomllib
    toy = EXAMPLES / "toy"
    config = tomllib.loads((toy / "verso.toml").read_text(encoding="utf-8"))
    assert config["schema"] >= 6
    assert config["names"]["base"] == "ru"
    assert not list(toy.glob("*.csv"))
    assert (toy / "names" / "names.tsv").is_file()
    assert "names.csv" not in (EXAMPLES / "README.md").read_text(encoding="utf-8")


def test_the_checks_guide_shows_what_the_example_answers(tmp_path: Path):
    """docs/checks.md (and its translation) quotes the toy example's `name-days` report: it is the report."""
    import re

    copy = tmp_path / "toy"
    shutil.copytree(EXAMPLES / "toy", copy)
    env = {k: v for k, v in os.environ.items() if k != "VERSO_WORKSPACE"} | {"VERSO_LANG": "en"}
    done = subprocess.run([sys.executable, "-m", "verso.core.cli", "--workspace", str(copy), "facts",
                           "--village", "Степанчиково", "--check", "name-days"],
                          cwd=copy, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 1, done.stdout + done.stderr   # a finding
    for guide in ("checks.md", "checks.ru.md"):
        text = (PROJECT / "docs" / guide).read_text(encoding="utf-8")
        block = re.search(r"```text\n\$ verso facts --village Степанчиково --check name-days\n(.*?)```", text, re.DOTALL)
        assert block is not None, guide
        assert block.group(1).strip() == done.stdout.strip(), guide
