"""What the core reads of a village's own data file, and the helpers a plugin reads its
corpus data with (the rest of it is the plugins').

`<village>/village.toml` holds one village's settings (`village()`), read from the village's
directory itself: the translator is handed a path, and a test's village in a temporary
directory is no village of verso.toml. The core reads `schema` and `[geni]`, the Geni
projects its models take; every other table is an enabled plugin's, parsed by the plugin's
`village_tables` hook (ru: `[census]`, `[timeline]`, `[sheets]`, `[csv]`), and a table no
enabled plugin reads is an unknown key. The corpus's own files (ru: `estates.toml`,
`timeline.toml`) are the plugins' to read, through `corpus_file()`.

A file that is not there is no settings (a new user's library, a test's village);
a file that is there and says something this code does not know is an error naming
the file and the key — a default quietly taken instead would be worse than a stop.
"""
from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from verso.core import plugins, workspace
from verso.core.workspace import WorkspaceError
from verso.core.messages import t

VILLAGE_FILE = "village.toml"
VILLAGE_SCHEMA = 1

_EMPTY: Mapping[str, str] = MappingProxyType({})


class CorpusDataError(WorkspaceError):
    """A corpus data file this code cannot read; the message starts with its path."""


@dataclass(frozen=True)
class Village:
    """A village's settings (`village.toml`); every part optional."""
    projects: tuple[str, ...] = ()                                  # [geni] projects
    project_rules: Mapping[str, str] = field(default=_EMPTY)        # [geni.project_rules]
    # The enabled plugins' tables, parsed by their hooks, by name; a table not written is absent.
    tables: Mapping[str, Any] = field(default=MappingProxyType({}))

    def table(self, name: str) -> Any:
        """A plugin's table as its hook parsed it; None where the file does not write it."""
        return self.tables.get(name)


# The keys of the core's part of a village.toml, by table ("" is the top level).
VILLAGE_KEYS: dict[str, frozenset[str]] = {
    "": frozenset({"schema", "geni"}),
    "geni": frozenset({"projects", "project_rules"}),
}


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise CorpusDataError(t("corpus_data.not_toml", path=path, e=e)) from None


def check_keys(path: Path, table: str, data: Mapping[str, Any], allowed: Mapping[str, frozenset[str]]) -> None:
    unknown = sorted(set(data) - allowed[table])
    if unknown:
        raise CorpusDataError(t("corpus_data.unknown_key", path=path, table=table + '.' if table else '', unknown=unknown[0]))


def wrong(path: Path, key: str, expected: object) -> CorpusDataError:
    return CorpusDataError(t("corpus_data.wrong", path=path, key=key, expected=expected))


def table(path: Path, data: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise wrong(path, key, t("corpus_data.expected_table"))
    return value  # pyright: ignore[reportUnknownVariableType]


def strings(path: Path, key: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):  # pyright: ignore[reportUnknownVariableType]
        raise wrong(path, key, t("corpus_data.expected_strings"))
    return tuple(value)  # pyright: ignore[reportUnknownArgumentType]


def string(path: Path, key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise wrong(path, key, t("corpus_data.expected_string"))
    return value


def string_map(path: Path, key: str, value: Mapping[str, Any]) -> Mapping[str, str]:
    if not all(isinstance(v, str) for v in value.values()):
        raise wrong(path, key, t("corpus_data.expected_string_values"))
    return MappingProxyType(dict(value))


def check_schema(path: Path, data: Mapping[str, Any], newest: int) -> None:
    schema = data.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise wrong(path, "schema", t("corpus_data.expected_integer"))
    if schema > newest:
        raise CorpusDataError(t("corpus_data.schema_newer", path=path, schema=schema, newest=newest))


def corpus_file(name: str) -> Path | None:
    """`name` in the workspace's `[corpus] dir`; None without a corpus or the file."""
    corpus = workspace.current().corpus_dir
    path = corpus / name if corpus is not None else None
    return path if path is not None and path.is_file() else None


def _plugin_tables() -> tuple[dict[str, Callable[[Path, Mapping[str, Any]], Any]], WorkspaceError | None]:
    """The village.toml tables the enabled plugins read, in the plugins' order; none without a
    workspace — a village read outside one has only the core's part —, and then why."""
    try:
        enabled = plugins.enabled()
    except WorkspaceError as error:
        return {}, error
    out: dict[str, Callable[[Path, Mapping[str, Any]], Any]] = {}
    for plugin in enabled:
        for name, parse in plugin.village_tables.items():
            out.setdefault(name, parse)
    return out, None


def village(village_dir: str | Path) -> Village:
    """The settings of the village at `village_dir` (its `village.toml`); `Village()` without one."""
    path = Path(village_dir) / VILLAGE_FILE
    if not path.is_file():
        return Village()
    data = read_toml(path)
    check_schema(path, data, VILLAGE_SCHEMA)
    hooks, nowhere = _plugin_tables()
    if nowhere is not None and (others := sorted(set(data) - VILLAGE_KEYS[""])):
        raise CorpusDataError(t("corpus_data.no_workspace", path=path, key=others[0], why=nowhere))
    check_keys(path, "", data, {"": VILLAGE_KEYS[""] | frozenset(hooks)})
    geni = table(path, data, "geni")
    check_keys(path, "geni", geni, VILLAGE_KEYS)
    rules = geni.get("project_rules", {})
    if not isinstance(rules, dict):
        raise wrong(path, "geni.project_rules", t("corpus_data.expected_table"))
    projects = strings(path, "geni.projects", geni.get("projects", []))
    project_rules = string_map(path, "geni.project_rules", rules)  # pyright: ignore[reportUnknownArgumentType]
    tables = {name: parse(path, table(path, data, name)) for name, parse in hooks.items() if name in data}
    return Village(projects=projects, project_rules=project_rules, tables=MappingProxyType(tables))
