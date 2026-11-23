"""The library's reference, written from the code: docs/reference/.

Four pages, each what one part of the code declares, so the reference cannot drift from it:
the commands of `verso` (the core's and each installed plugin's), the keys of `verso.toml`,
`village.toml` and the corpus's files, the DSL linters and their codes, the DSL's facade v1.
`tests/test_reference.py` and CI (`make reference check=1`) fail when a page is stale.

    python -m tools.reference           # make reference: write the pages
    python -m tools.reference --check   # make reference check=1: what is stale; exit 1
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reference"
CHECKS = ROOT / "packages" / "verso-ru" / "src" / "verso" / "ru" / "linters" / "checks"
API = ROOT / "packages" / "verso-ru" / "src" / "verso" / "ru" / "dsl" / "api-v1.json"
HEAD = "<!-- Written by tools/reference.py from the code — do not edit; `make reference`. -->\n\n"


def _docline(source: str) -> str:
    """The first sentence of a module's docstring (its first paragraph, on one line), read without
    importing it. A sentence ends at a full stop: a colon introduces what follows it («The святцы: import
    the table, …»), and a summary cut there says nothing."""
    doc = (ast.get_docstring(ast.parse(source)) or "").strip()
    paragraph = " ".join(line.strip() for line in doc.split("\n\n")[0].splitlines())
    end = re.search(r"(?<=\.)\s", paragraph)
    return (paragraph[:end.start()] if end else paragraph).replace("|", "\\|")


def _module_source(module: str) -> str:
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        raise SystemExit(f"reference: нет модуля {module}")
    return Path(spec.origin).read_text(encoding="utf-8")


def render_commands() -> str:
    """Every command of `verso`: the core's, then each installed plugin's, with its module."""
    from verso.core import cli, plugins

    groups: list[tuple[str, Mapping[str, str]]] = [("The core", cli.COMMANDS)]
    groups += [(f"Plugin `{name}`", plugin.commands) for name, plugin in sorted(plugins.installed().items())]
    lines = [HEAD + "# Commands\n", "`verso <command> [args]` runs the command's module as a program; "
             "`verso --help` lists them. `--workspace DIR` names the workspace for that command.\n"]
    for title, commands in groups:
        lines += [f"\n## {title}\n", "| Command | Module | What it does |", "|---|---|---|"]
        for name in sorted(commands):
            module = commands[name]
            lines.append(f"| `verso {name}` | `{module}` | {_docline(_module_source(module))} |")
    return "\n".join(lines) + "\n"


def _key_table(title: str, keys: Mapping[str, frozenset[str]]) -> list[str]:
    lines = [f"\n## `{title}`\n", "| Table | Keys |", "|---|---|"]
    for table in sorted(keys):
        lines.append(f"| `{table or '(top level)'}` | {', '.join(f'`{k}`' for k in sorted(keys[table]))} |")
    return lines


def render_workspace_keys() -> str:
    """The keys of verso.toml, village.toml and the corpus's files — what their readers accept."""
    from verso.core import corpus_data, places, workspace
    from verso.ru import corpus_data as ru_data
    from verso.ru.plugin import PLUGIN

    lines = [HEAD + "# Workspace keys\n",
             f"An unknown key or table is refused, naming the file and the key. `verso.toml` is of "
             f"schema {workspace.SCHEMA} (a newer schema than the code's is refused).\n"]
    lines += _key_table("verso.toml", workspace._KEYS)  # pyright: ignore[reportPrivateUsage]
    # village.toml: the core's `[geni]` and the tables the ru plugin reads, as one file.
    village = {**corpus_data.VILLAGE_KEYS, **ru_data.VILLAGE_KEYS,
               "": corpus_data.VILLAGE_KEYS[""] | frozenset(ru_data.TABLES)}
    lines += _key_table("<village>/village.toml", village)
    lines += _key_table("<corpus>/estates.toml", ru_data._ESTATES_KEYS)  # pyright: ignore[reportPrivateUsage]
    lines += _key_table("<corpus>/timeline.toml", ru_data._TIMELINE_KEYS)  # pyright: ignore[reportPrivateUsage]
    lines += _key_table("<corpus>/places.toml",  # the core's keys and ru's attributes
                        {"[\"<place>\"]": places._PLACE_KEYS | frozenset(PLUGIN.place_attributes)})  # pyright: ignore[reportPrivateUsage]
    return "\n".join(lines) + "\n"


def render_linters() -> str:
    """Each DSL check: its module's first sentence and its codes — `verso.ru.linters.codes.LINTER_CODES`,
    each linter's under the module it runs from."""
    from verso.ru.linters.codes import COMMON_CODES, LINTER_CODES
    from verso.ru.linters.dsllint import LINTERS
    checks = {path.stem: path.read_text(encoding="utf-8") for path in sorted(CHECKS.glob("*.py"))
              if path.name != "__init__.py"}
    owned: dict[str, set[str]] = {}
    for linter in LINTERS:
        module = linter.plain.__module__.rsplit(".", 1)[-1]
        owned.setdefault(module, set()).update(LINTER_CODES[linter.name])
    for name in checks:  # a check dsllint does not run (the names layers' own) owns the codes of its name
        if name not in owned and name in LINTER_CODES:
            owned[name] = set(LINTER_CODES[name])
    lines = [HEAD + "# Linters\n", "`dsllint` runs every check over DSL files (`--json` for tools). "
             "A code is hard (fails at once) or advisory (held by the baseline ratchet).\n",
             "`dsllint --json` prints, per file and linter, its findings: `level`, `line`, `message`, "
             "then `code`, `params` (what the DSL wrote; a part said in words is `{key, params}`) and "
             "`token` (what the finding is about, or `null`), then `col`/`end_col` and `fix` where the "
             "check has them. A finding is its code and params, in no language; its message is the "
             "catalog's text in the interface's language.\n",
             "The baseline ratchet (`dsllint --baseline FILE`) keeps a row per advisory finding: "
             "`CODE <tab> KEY <tab> FILE <tab> excerpt`, `KEY = sha256(file, code, params as JSON with "
             "sorted keys, nth)[:16]` — `nth` its occurrence among identical ones — under the line "
             "`# baseline v2`; only CODE and KEY are matched. A file without that line (v1, keyed by "
             "the message) is refused, and `--update-baseline` writes it anew.\n",
             "| Module | Codes | What it checks |", "|---|---|---|"]
    for name, source in checks.items():
        lines.append(f"| `{name}` | {', '.join(sorted(owned.get(name, ()))) or '—'} | {_docline(source)} |")
    lines += ["", f"Any linter: {', '.join(COMMON_CODES)} — a file that does not parse (`SyntaxError`, "
              "`parse error`), a check that crashed."]
    return "\n".join(lines) + "\n"


def _params(params: Sequence[Sequence[object]]) -> str:
    out: list[str] = []
    starred = False
    for name, kind, default in params:
        if kind == "KEYWORD_ONLY" and not starred:
            out.append("*")
        starred = starred or kind in ("VAR_POSITIONAL", "KEYWORD_ONLY")
        star = "*" if kind == "VAR_POSITIONAL" else "**" if kind == "VAR_KEYWORD" else ""
        out.append(f"{star}{name}" + (f"={default}" if default is not None else ""))
    return ", ".join(out)


def render_dsl_api() -> str:
    """The DSL's facade v1 (`verso.ru.dsl` and its catalogs), from api-v1.json."""
    api = json.loads(API.read_text(encoding="utf-8"))
    lines = [HEAD + f"# DSL API v{api['api']}\n",
             "What a DSL file may import (IMP001 refuses anything else). `DSL_API` rises only when a "
             "name goes or is renamed; a new keyword with a default is compatible.\n"]
    for module, names in api["modules"].items():
        lines.append(f"\n## `{module}`\n")
        for name, entry in names.items():
            kind = entry["kind"]
            if kind == "function":
                lines.append(f"- `{name}({_params(entry['params'])})`")
            elif kind == "enum":
                lines.append(f"- `{name}` (enum): {', '.join(f'`{m}`' for m in entry['members'])}")
            elif kind == "class":
                lines.append(f"- `{name}` (class)")
            else:
                lines.append(f"- `{name}` = `{entry['value'] or '\"\"'}`")
    return "\n".join(lines) + "\n"


PAGES = {"commands.md": render_commands, "workspace-keys.md": render_workspace_keys,
         "linters.md": render_linters, "dsl-api.md": render_dsl_api}


def write(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, render in PAGES.items():
        (out / name).write_text(render(), encoding="utf-8")
        written.append(out / name)
    return written


def check(out: Path = OUT) -> list[str]:
    """A page missing or not what the code says now."""
    stale = []
    for name, render in PAGES.items():
        path = out / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render():
            stale.append(f"{path.relative_to(ROOT).as_posix()}: устарела — make reference")
    return stale


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.reference", description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="say which page is stale and write nothing")
    args = parser.parse_args(argv)
    if args.check:
        stale = check()
        print("\n".join(stale) or "reference: страницы совпадают с кодом")
        return 1 if stale else 0
    for path in write():
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
