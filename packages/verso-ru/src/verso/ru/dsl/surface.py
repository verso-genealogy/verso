"""The DSL's surface — every name the facade and its catalogs give, written down.

    verso dsl-surface --check [--base REV]   # is api-v1.json what the code gives?
    verso dsl-surface --write                # write it again (refused if it breaks v1)

`surface()` is the facade (`verso.ru.dsl`) and its three catalogs, name by name: a function or a
class by its parameters (name, kind, the default's repr — annotations are not part of it), an
enum by its members, a constant by its value (and the sex a status carries). `api-v<DSL_API>.json`
beside this module holds it, and DSL v1 may only grow: `incompatible(old, new)` says what a new
surface takes from an old one — a name, a parameter, a default, a kind, the order of the
positionals, a value. A new name, a parameter that gains a default, and a new parameter with a default
after the old positionals, are compatible; anything else is DSL v2 (`DSL_API = 2`, `api-v2.json`).
"""
from __future__ import annotations

import argparse
import enum
import importlib
import inspect
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

import verso.ru.dsl
from verso.ru.messages import t

MODULES = ("verso.ru.dsl", "verso.ru.dsl.causes_of_death", "verso.ru.dsl.marital_status", "verso.ru.dsl.statuses")
API_FILE = Path(str(files("verso.ru.dsl").joinpath(f"api-v{verso.ru.dsl.DSL_API}.json")))
# The file as a commit names it, under whichever directory the layout keeps the package in.
SURFACE_PATH = f"verso/ru/dsl/{API_FILE.name}"
_POSITIONAL = ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")


def _entry(value: object) -> dict[str, Any]:
    if isinstance(value, type) and issubclass(value, enum.Enum):
        return {"kind": "enum", "members": {m.name: repr(m.value) for m in value}}
    if inspect.isclass(value) or inspect.isroutine(value):
        params = [[p.name, p.kind.name, None if p.default is p.empty else repr(p.default)]
                  for p in inspect.signature(value).parameters.values()]
        return {"kind": "class" if inspect.isclass(value) else "function", "params": params}
    entry: dict[str, Any] = {"kind": "constant", "value": str(value)}
    gender = getattr(value, "gender", None)
    if isinstance(gender, enum.Enum):
        entry["gender"] = gender.name
    return entry


def surface() -> dict[str, Any]:
    """{"api": DSL_API, "modules": {module: {name: entry}}} — the facade and its catalogs."""
    modules = {}
    for name in MODULES:
        module = importlib.import_module(name)
        modules[name] = {n: _entry(getattr(module, n)) for n in sorted(module.__all__)}
    return {"api": verso.ru.dsl.DSL_API, "modules": modules}


def _params(where: str, old: list[list[Any]], new: list[list[Any]]) -> list[str]:
    out = []
    now = {p[0]: p for p in new}
    for name, kind, default in old:
        if name not in now:
            out.append(str(t("dsl.surface.no_param", where=where, name=name)))
        elif now[name][1] != kind:
            out.append(str(t("dsl.surface.param_kind", where=where, name=name)))
        elif default is not None and now[name][2] != default:  # a parameter may gain a default
            out.append(str(t("dsl.surface.param_default", where=where, name=name, was=default, now=now[name][2])))
    before = [p[0] for p in old if p[1] in _POSITIONAL]
    after = [p[0] for p in new if p[1] in _POSITIONAL]
    if after[:len(before)] != before and set(before) <= set(after):
        out.append(str(t("dsl.surface.positional_order", where=where)))
    was = {p[0] for p in old}
    out += [str(t("dsl.surface.new_param", where=where, name=name)) for name, kind, default in new
            if name not in was and default is None and kind not in ("VAR_POSITIONAL", "VAR_KEYWORD")]
    return out


def _value(where: str, old: str, new: str) -> list[str]:
    return [] if old == new else [str(t("dsl.surface.value", where=where, was=old, now=new))]


def incompatible(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """What `new` takes from `old`, one line each, in module and name order; [] when it only grows."""
    out = []
    for module in sorted(old["modules"]):
        names = new["modules"].get(module, {})
        for name, was in sorted(old["modules"][module].items()):
            where = f"{module}.{name}"
            now = names.get(name)
            if now is None:
                out.append(str(t("dsl.surface.no_name", where=where)))
            elif now["kind"] != was["kind"]:
                out.append(str(t("dsl.surface.kind", where=where)))
            elif was["kind"] == "enum":
                for member, value in sorted(was["members"].items()):
                    if member not in now["members"]:
                        out.append(str(t("dsl.surface.no_name", where=f"{where}.{member}")))
                    else:
                        out += _value(f"{where}.{member}", value, now["members"][member])
            elif was["kind"] == "constant":
                out += _value(where, was["value"], now["value"])
                if was.get("gender") != now.get("gender"):
                    out.append(str(t("dsl.surface.gender", where=where, was=was.get("gender"), now=now.get("gender"))))
            else:
                out += _params(where, was["params"], now["params"])
    return out


def _written() -> dict[str, Any] | None:
    return json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.is_file() else None


def _at(rev: str, repo: Path | None = None) -> dict[str, Any] | None:
    """The surface file as commit `rev` of `repo` (default: the working directory's) has it, wherever
    that commit kept it — verso/ru/dsl/ before 0.1.0, lib/packages/verso-ru/src/… after it;
    None where it has none. Two such files are refused: which is the base would be a guess. The
    whole tree, from any directory of the repository (`--full-tree`): a listing of the subdirectory
    only would read as «no surface» and the check would pass comparing nothing."""
    listed = subprocess.run(["git", "ls-tree", "-r", "-z", "--full-tree", "--name-only", rev],
                            cwd=repo or Path.cwd(), capture_output=True, text=True)
    if listed.returncode != 0:
        return None
    found = [name for name in listed.stdout.split("\0") if name == SURFACE_PATH or name.endswith("/" + SURFACE_PATH)]
    if len(found) > 1:
        raise SystemExit(t("dsl.surface.two_files", rev=rev, found=', '.join(found)))
    if not found:
        return None
    done = subprocess.run(["git", "show", f"{rev}:{found[0]}"], cwd=repo or Path.cwd(), capture_output=True,
                          text=True)
    return json.loads(done.stdout) if done.returncode == 0 else None


def _refusal(lines: list[str]) -> str:
    return str(t("dsl.surface.incompatible", changes="; ".join(lines)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--check", action="store_true", help="api-v1.json is what the code gives")
    what.add_argument("--write", action="store_true", help="write api-v1.json (refused if it breaks DSL v1)")
    ap.add_argument("--base", help="--check: and the file only grew since this commit")
    args = ap.parse_args(argv)
    now, written = surface(), _written()
    if args.write:
        lines = incompatible(written, now) if written is not None else []
        if lines:
            print(_refusal(lines))
            return 1
        API_FILE.write_text(json.dumps(now, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    if written != now:
        print(t("dsl.surface.not_written"))
        return 1
    base = _at(args.base) if args.base else None
    lines = incompatible(base, now) if base is not None else []
    if lines:
        print(_refusal(lines))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
