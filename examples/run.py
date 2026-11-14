"""Run the toy example end to end: copy toy/ and run the installed `verso` over the copy.

    python examples/run.py [--workspace DIR] [--keep DIR]

`--keep DIR` copies the toy workspace into DIR and leaves it there (else a temporary directory
that goes); `--workspace DIR` runs over DIR as it is, copying nothing. Each step is a command, its
exit code and what it must write; the first that fails is said — «пример: шаг N (<команда>) —
<что не так>» — and the run exits 1. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

TOY = Path(__file__).resolve().parent / "toy"
VILLAGE = "Степанчиково"


class StepFailed(Exception):
    pass


def _verso(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The installed `verso` (its module, as the console script runs it) over the workspace `root`."""
    env = {k: v for k, v in os.environ.items() if k != "VERSO_WORKSPACE"}
    return subprocess.run([sys.executable, "-m", "verso.core.cli", "--workspace", str(root), *args],
                          cwd=root, capture_output=True, text=True, env=env, check=False)


def _dsl_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in (root / VILLAGE).glob("[0-9][0-9][0-9][0-9]/*.py"))


def _ok(done: subprocess.CompletedProcess[str]) -> None:
    if done.returncode != 0:
        raise StepFailed(f"выход {done.returncode}: {(done.stderr or done.stdout or '').strip().splitlines()[-1:]}")


def step_villages(root: Path) -> None:
    done = _verso(root, "workspace", "villages")
    _ok(done)
    if VILLAGE not in done.stdout.split():
        raise StepFailed(f"нет села {VILLAGE} в выводе: {done.stdout.strip()!r}")


def step_lint(root: Path) -> None:
    done = _verso(root, "dsllint", "--json", *_dsl_files(root))
    _ok(done)
    errors = [f"{entry['file']}: {issue.get('code', '')} {issue.get('message', '')}"
              for entry in json.loads(done.stdout) for issue in entry.get("issues", [])
              if issue.get("level") == "error"]
    if errors:
        raise StepFailed(f"находки уровня error: {errors[:3]}")


def step_csv(root: Path) -> None:
    _ok(_verso(root, "export-csv", "--village", VILLAGE, "--out", str(root / "csv")))
    written = list((root / "csv").rglob("*.csv"))
    if len(written) < len(_dsl_files(root)):
        raise StepFailed(f"CSV {len(written)}, а DSL-файлов {len(_dsl_files(root))}")


def step_records(root: Path) -> None:
    _ok(_verso(root, "export-records", "--village", VILLAGE, "--out", str(root / "records")))
    exported = [p for p in (root / "records").rglob("*.json") if p.name != "index.json"]
    if not any((root / "records").rglob("index.json")) or len(exported) < len(_dsl_files(root)):
        raise StepFailed(f"нет index.json или JSON на каждый файл: {len(exported)}")


def step_schema(root: Path) -> None:
    _ok(_verso(root, "records-schema", "--validate", str(root / "records")))


def step_terraform(root: Path) -> None:
    _ok(_verso(root, "generate-tf", "--village", VILLAGE))
    if not list((root / VILLAGE / "terraform" / "geni").glob("mk_1850_*.tf")):
        raise StepFailed("нет mk_1850_*.tf")


def step_facts(root: Path) -> None:
    _ok(_verso(root, "facts", "--village", VILLAGE))


def step_svyatcy(root: Path) -> None:
    done = _verso(root, "svyatcy", "near", "1850-04-16", "--gender", "M")
    _ok(done)
    if not done.stdout.strip():
        raise StepFailed("пустой вывод")


STEPS: list[tuple[str, Callable[[Path], None]]] = [
    ("workspace villages", step_villages),
    ("dsllint --json", step_lint),
    ("export-csv", step_csv),
    ("export-records", step_records),
    ("records-schema --validate", step_schema),
    ("generate-tf", step_terraform),
    ("facts", step_facts),
    ("svyatcy near 1850-04-16", step_svyatcy),
]


def run(root: Path) -> int:
    for n, (name, step) in enumerate(STEPS, start=1):
        try:
            step(root)
        except StepFailed as failed:
            print(f"пример: шаг {n} ({name}) — {failed}")
            return 1
        print(f"пример: шаг {n} ({name}) — ok")
    print(f"пример: {len(STEPS)} шагов прошли")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--workspace", type=Path, help="run over this workspace as it is")
    where.add_argument("--keep", type=Path, help="copy toy/ here and leave it")
    args = parser.parse_args(argv)
    if args.workspace:
        return run(args.workspace.resolve())
    if args.keep:
        shutil.copytree(TOY, args.keep)
        return run(args.keep.resolve())
    with tempfile.TemporaryDirectory(prefix="verso-example-") as tmp:
        copy = Path(tmp) / "toy"
        shutil.copytree(TOY, copy)
        return run(copy)


if __name__ == "__main__":
    sys.exit(main())
