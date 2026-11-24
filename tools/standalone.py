"""The library tested from its own archive — `make standalone`.

`git archive HEAD` of this directory — the root of verso-genealogy/verso, or lib/ of a parent repository —
goes into a directory outside the checkout; both distributions are built there into wheels and
installed into a venv of their own, with the tests' pins from requirements-dev.txt. The tests then
run from the copy with the sentinel on (tests/sentinel.py): VERSO_SENTINEL names the checkout —
the whole repository holding this directory, and, from a worktree, the main checkout that holds it
— and a `.pth` in the venv installs it in every Python started there, pytest and the children its
tests start alike. Each refusal is also logged (VERSO_SENTINEL_LOG): a run whose log is not empty
fails, even where the code that read caught the error.

It works from HEAD: what is not committed is not checked.

    python tools/standalone.py [--keep DIR]
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The distributions, by their directory, and the extras the tests need.
DISTS: dict[str, str] = {"packages/verso-core": "schema,heic", "packages/verso-ru": "xlsx,sheets,dsl-tools,site"}
# The tests' own pins, read from requirements-dev.txt.
TEST_PINS: tuple[str, ...] = ("pytest", "pytest-xdist", "jsonschema", "pyyaml")
# What a child must not inherit: the checkout's code (make exports PYTHONPATH) or its workspace.
_DROPPED = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "VERSO_WORKSPACE", "VERSO_TEST_WORKSPACE")


class StandaloneError(SystemExit):
    """standalone refuses, in a line, in Russian."""


def pins() -> list[str]:
    """The tests' pins, as requirements-dev.txt writes them."""
    dev = [line.strip() for line in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    by_name = {re.split(r"[\[=<>!~ ;]", requirement, maxsplit=1)[0].lower(): requirement for requirement in dev}
    missing = [name for name in TEST_PINS if name not in by_name]
    if missing:
        raise StandaloneError(f"standalone: в requirements-dev.txt нет {', '.join(missing)}")
    return [by_name[name] for name in TEST_PINS]


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def forbidden() -> tuple[Path, ...]:
    """What the sentinel refuses: the repository holding this directory, and — from a worktree —
    the main checkout holding it."""
    top = Path(_git("rev-parse", "--show-toplevel")).resolve()
    main = Path(_git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent.resolve()
    return (top,) if main == top else (top, main)


def guard_children(site: Path, sentinel: Path) -> None:
    """Make every Python of the venv whose site-packages is `site` install the sentinel at start
    (when VERSO_SENTINEL is set): the project's own tests/sentinel.py, and a `.pth` importing it."""
    (site / "verso_sentinel_hook.py").write_text(sentinel.read_text(encoding="utf-8"), encoding="utf-8")
    (site / "verso_sentinel.pth").write_text("import verso_sentinel_hook; verso_sentinel_hook.install_from_env()\n",
                                             encoding="utf-8")


def check_log(log: Path) -> None:
    """A refusal logged — caught or not where it happened — fails the run, naming each path once."""
    if not log.is_file():
        return
    paths = sorted(set(log.read_text(encoding="utf-8").splitlines()))
    if paths:
        raise StandaloneError("сторож: читали вне проекта — " + ", ".join(paths))


def extract(into: Path) -> Path:
    """`git archive HEAD` of this directory unpacked into `into` — refused inside the checkout,
    which the sentinel would refuse to the copy itself."""
    into = into.resolve()
    if any(into == root or root in into.parents for root in forbidden()):
        raise StandaloneError(f"standalone: копия внутри checkout ({into}) — нужна вне его")
    prefix = _git("rev-parse", "--show-prefix")       # "lib/" in a parent repository, "" in verso
    top = _git("rev-parse", "--show-toplevel")         # git archive scopes a subdirectory's run to it
    archive = subprocess.run(["git", "-C", top, "archive", "--format=tar",
                              f"HEAD:{prefix}" if prefix else "HEAD"], capture_output=True, check=True).stdout
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(into, filter="data")
    return into


def _tool_env() -> dict[str, str]:
    """The environment without the checkout's code or workspace (make exports both): what uv and the
    venv's Python run with."""
    return {key: value for key, value in os.environ.items() if key not in _DROPPED}


def _run(command: Sequence[str | Path], **kwargs: object) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("env", _tool_env())
    return subprocess.run([str(part) for part in command], text=True, check=False, **kwargs)  # type: ignore[call-overload]


def _wheels(copy: Path, out: Path) -> list[str]:
    """Each distribution built from the copy; the requirement installing its wheel."""
    requirements = []
    for directory, extras in DISTS.items():
        before = set(out.glob("*.whl"))
        done = _run(["uv", "build", "--wheel", "--out-dir", out, copy / directory], capture_output=True)
        if done.returncode:
            raise StandaloneError(f"standalone: uv build {directory}:\n{done.stderr[-2000:]}")
        (wheel,) = set(out.glob("*.whl")) - before
        name = wheel.name.split("-")[0].replace("_", "-")
        requirements.append(f"{name}{f'[{extras}]' if extras else ''} @ {wheel.as_uri()}")
    return requirements


def _child_env(venv: Path) -> dict[str, str]:
    env = _tool_env()
    env["PATH"] = f"{venv / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["VERSO_SENTINEL"] = os.pathsep.join(map(str, forbidden()))
    env["VERSO_SENTINEL_LOG"] = str(venv.parent / "sentinel.log")
    return env


def _pytest(venv: Path, copy: Path, *args: str) -> int:
    """pytest of the copy, in its venv, with the sentinel on: the number passed, or StandaloneError."""
    done = _run([venv / "bin" / "python", "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"], cwd=copy,
                env=_child_env(venv), capture_output=True)
    tail = "\n".join(done.stdout.splitlines()[-40:])
    if done.returncode:
        raise StandaloneError(f"standalone: pytest {' '.join(args)} в {copy}:\n{tail}\n{done.stderr[-2000:]}")
    check_log(venv.parent / "sentinel.log")
    passed = re.search(r"(\d+) passed", tail)
    return int(passed.group(1)) if passed else 0


def _install(venv: Path, requirements: Sequence[str]) -> None:
    done = _run(["uv", "pip", "install", "--python", venv / "bin" / "python", *requirements], capture_output=True)
    if done.returncode:
        raise StandaloneError(f"standalone: uv pip install:\n{done.stderr[-2000:]}")


def run(*, keep: Path | None) -> int:
    """The tests from the archive, outside the checkout: the number passed."""
    if shutil.which("uv") is None:
        raise StandaloneError("standalone: нет uv — https://docs.astral.sh/uv/ (колёса строит и ставит он)")
    if keep is not None and keep.exists() and any(keep.iterdir()):
        raise StandaloneError(f"standalone: {keep} не пуст — прошлые файлы проверились бы снова; "
                              "дайте пустой или новый каталог")
    with tempfile.TemporaryDirectory(prefix="verso-standalone-") as scratch:
        work = (keep or Path(scratch)).resolve()
        copy = extract(work / "verso")
        wheels = work / "wheels"
        wheels.mkdir(exist_ok=True)
        venv = work / "venv"
        base = getattr(sys, "_base_executable", sys.executable)
        if _run(["uv", "venv", "--quiet", "--python", base, venv]).returncode:
            raise StandaloneError(f"standalone: uv venv {venv}")
        site = _run([venv / "bin" / "python", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                    capture_output=True).stdout.strip()
        guard_children(Path(site), copy / "tests" / "sentinel.py")
        _install(venv, [*_wheels(copy, wheels), *pins()])
        return _pytest(venv, copy, "tests", "--doctest-modules", "-n", "auto", "--dist", "worksteal") + _pytest(venv, copy, "-p", "tests.core.block",
                                                                         "tests/core")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/standalone.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", type=Path, help="work here (an empty or new directory) and leave it")
    args = parser.parse_args(argv)
    print(f"standalone: HEAD {_git('rev-parse', '--short', 'HEAD')} — незакоммиченное не проверяется", flush=True)
    passed = run(keep=args.keep)
    print(f"standalone: {passed} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
