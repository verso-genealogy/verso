"""What the library's repository runs: its Makefile and its CI say one thing, its tools are its own."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent.parent
CI = LIB / ".github" / "workflows" / "ci.yml"


def _prerequisites(target: str) -> list[str]:
    text = (LIB / "Makefile").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(target)}:(.*)$", text, re.M)
    assert match, f"Makefile: нет цели {target}"
    return match.group(1).split()


def test_lib_makefile_ci_mirrors_ci_yml():
    made = set(re.findall(r"\bmake ([a-z-]+)", CI.read_text(encoding="utf-8")))
    assert set(_prerequisites("ci")) <= made, set(_prerequisites("ci")) - made
    assert made - {"bootstrap", "ci"} <= set(_prerequisites("ci")), made - {"bootstrap", "ci"} - set(_prerequisites("ci"))


def test_lib_tools_resolve_to_lib():
    import tools.layers

    assert Path(tools.layers.__file__).resolve().parent == LIB / "tools"


def test_ci_tests_every_python_the_classifiers_name():
    # Every Python a step of CI sets up: a matrix's list (`python:` or `python-version:`), or one version written out.
    text = CI.read_text(encoding="utf-8")
    versions = {v for listed in re.findall(r"\bpython(?:-version)?: \[([^\]]*)\]", text)
                for v in listed.replace("'", "").replace(" ", "").split(",")}
    versions |= set(re.findall(r"python-version: '(3\.\d+)'", text))
    assert versions, "ci.yml sets up no Python"
    for package in ("verso-core", "verso-ru"):
        project = tomllib.loads((LIB / "packages" / package / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        named = {c.rsplit(" :: ", 1)[1] for c in project["classifiers"] if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)}
        assert named == versions, (package, named, versions)
        assert project["requires-python"] == ">=3.14"


def test_a_workflow_filtered_by_paths_watches_its_own_file():
    for path in sorted(CI.parent.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        named = set(re.findall(r"'(\.github/workflows/[^']+)'", text))
        if "paths:" in text:
            assert named == {f".github/workflows/{path.name}"}, path.name


def test_each_distribution_marks_itself_typed():
    """PEP 561: a py.typed beside each distribution's package, shipped by its package-data — or a
    strict type checker reading the installed library asks for stubs (a corpus's pyright did)."""
    for dist, package in (("verso-core", "verso.core"), ("verso-ru", "verso.ru")):
        project = LIB / "packages" / dist
        data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
        assert "py.typed" in data["package-data"][package], dist
        assert (project / "src" / Path(*package.split(".")) / "py.typed").is_file(), dist
