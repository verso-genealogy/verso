"""Where the corpus is: the one place the library finds its data.

A workspace is a directory holding `verso.toml`: the villages, the names
tables, the notes stale-notes reads, (schema 2) where the corpus's own
data lives (`[corpus] dir`: places, estates, the timeline's events) and where else
to look for terraform and geni (`[tools] path`), and (schema 4) the plugins it
works with (`plugins`, read by `verso.core.plugins`), and (schema 6) the names lexicon as layers over
a plugin's shipped base (`[names] base`, `layers`, `writable` — `NamesLayers`, which the plugin
reads). It is found, in this order:

1. the innermost `use(root)` — a test, or a caller holding a root of its own;
2. `VERSO_WORKSPACE`, a path to the directory;
3. `verso.toml` from the working directory up — never across a git boundary:
   a directory holding `.git` (a checkout, or a worktree's `.git` file) and no
   `verso.toml` ends the search with an error, so a worktree nested in another
   checkout never quietly reads that checkout's data.

The answer is kept for the life of the process, from the first question on: a
caller that will `chdir` somewhere outside (a mirror of a village in a
temporary directory) asks first, and a Python child is started with
`child_env()`, which names the workspace the parent found.

Importing a module never asks: no module looks for its workspace at import or
in a default argument — `--help`, an IDE's linter run and an import from
anywhere work without one, and a test's `use()` is not pre-empted by a cache.
"""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any
from verso.core import i18n
from verso.core.messages import t

SCHEMA = 7
CONFIG = "verso.toml"
ENV = "VERSO_WORKSPACE"

# The keys a verso.toml may hold, by table ("" is the top level). Schema 2 added
# [corpus] and [tools]; a schema-1 file holds neither and reads as it always did.
# Schema 3 lets [app] stand: the App's settings (verso.app.settings), which the
# library takes as it is and never reads. Schema 4 names the plugins: a file of an
# older schema reads as `plugins = ["ru"]` — the library was the Russian books' — and one of
# schema 4 without the key is the core alone. Schema 5 says the interface's language,
# `[i18n] locale` and the language packs it enables (`packs`); a file of an older schema reads as
# `locale = "ru"` — the interface was Russian —, one of schema 5 without it is English. Schema 6 sums the
# names lexicon of layers: `[names] base` (a plugin's shipped base, by its name; `false` — none), `layers`
# (directories above it, bottom to top) and `writable` (the one a name is added to); `dir` is schema ≤ 5's. A
# file of schema 6 without `[names]` has the base alone. What the base's name means and how a layer is read is
# the plugins': the core reads the keys as data (`NamesLayers`). Schema 7 says which transliteration profile each role
# spells by: `[translit] address` (the res_names', a Terraform address) and `display` (the names a person reads); a key
# not written is the plugin's default. What a profile's name means is the plugins' (`TranslitRoles`); a file of schema
# 6 or older has no roles (`Workspace.translit` is None) and spells as it always did.
_KEYS: dict[str, frozenset[str]] = {
    "": frozenset({"schema", "villages", "names", "notes", "corpus", "tools", "app", "plugins", "i18n", "translit"}),
    "i18n": frozenset({"locale", "packs"}),
    "names": frozenset({"dir", "base", "layers", "writable"}),
    "notes": frozenset({"globs"}),
    "corpus": frozenset({"dir"}),
    "tools": frozenset({"path"}),
    "translit": frozenset({"address", "display"}),
}


class WorkspaceError(Exception):
    """No workspace, or one this code cannot read."""


class LexiconNotConfigured(WorkspaceError):
    """The workspace names no names tables."""


#: The base a file of schema 6 sums its layers over when `[names] base` is not written.
DEFAULT_NAMES_BASE = "ru"


@dataclass(frozen=True)
class NamesLayers:
    """`[names]` of schema 6: the names lexicon as a sum of layers. `base` — the name of a plugin's shipped
    base (None: `base = false`, no base); `layers` — the layers' directories above it, bottom to top;
    `writable` — the one of them a name is added to (the top one by default; None with no layers)."""
    base: str | None
    layers: tuple[Path, ...] = ()
    writable: Path | None = None


@dataclass(frozen=True)
class TranslitRoles:
    """`[translit]` of schema 7: the transliteration profile of each role, by the name its plugin gives it — `address`
    (the res_names') and `display` (the names a person reads). None: not written, the plugin's default."""
    address: str | None = None
    display: str | None = None


@dataclass(frozen=True)
class Workspace:
    root: Path
    villages: tuple[str, ...]
    names_dir: Path | None                   # [names] dir, schema ≤ 5: the old tables' directory
    notes: tuple[str, ...]
    corpus_dir: Path | None = None           # [corpus] dir; None: no corpus data
    tool_path: tuple[Path, ...] = ()         # [tools] path, searched after PATH
    plugins: tuple[str, ...] = ()            # plugins, in order (verso.core.plugins)
    locale: str = "en"                       # [i18n] locale: the interface's language (verso.core.i18n)
    packs: tuple[str, ...] = ()              # [i18n] packs: the language packs enabled
    names_layers: NamesLayers | None = None  # [names] of schema 6; None: schema ≤ 5 (`names_dir`)
    translit: TranslitRoles | None = None    # [translit] of schema 7; None: schema ≤ 6 (no roles)

    def village_dir(self, name: str) -> Path:
        if name not in self.villages:
            raise WorkspaceError(t("workspace.no_village", name=name, config=self.root / CONFIG))
        return self.root / name

    def names_file(self, name: str) -> Path:
        # Which tables there are is the plugins' (`plugins.names_tables()`): the core
        # asks only that it is a file of the directory.
        if not name or Path(name).name != name:
            raise ValueError(f"not a names table: {name}")
        if self.names_dir is None:
            if self.names_layers is not None:
                raise LexiconNotConfigured(t("workspace.names_file_schema_6", config=self.root / CONFIG))
            raise LexiconNotConfigured(t("workspace.no_lexicon", config=self.root / CONFIG))
        return self.names_dir / name


def _strings(path: Path, key: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):  # pyright: ignore[reportUnknownVariableType]
        raise WorkspaceError(t("workspace.expected_strings", path=path, key=key))
    return tuple(value)  # pyright: ignore[reportUnknownArgumentType]


def _table(path: Path, data: dict[str, Any], name: str) -> dict[str, Any] | None:
    table = data.get(name)
    if table is None:
        return None
    if not isinstance(table, dict):
        raise WorkspaceError(t("workspace.expected_table", path=path, key=name))
    return table  # pyright: ignore[reportUnknownVariableType]


def load(root: Path) -> Workspace:
    """The workspace `root/verso.toml` describes. The villages and tables it names
    need not exist yet: a checkout with its data moved aside is still a workspace."""
    root = root.resolve()
    path = root / CONFIG
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WorkspaceError(t("workspace.no_file", path=path)) from None
    except tomllib.TOMLDecodeError as e:
        raise WorkspaceError(f"{path}: {e}") from None
    schema = data.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise WorkspaceError(t("workspace.schema_not_int", path=path))
    if schema > SCHEMA:
        raise WorkspaceError(t("workspace.schema_newer", path=path, schema=schema, code=SCHEMA))
    names, notes = _table(path, data, "names"), _table(path, data, "notes")
    corpus, tools = _table(path, data, "corpus"), _table(path, data, "tools")
    i18n_table = _table(path, data, "i18n")
    if i18n_table is not None and schema < 5:
        raise WorkspaceError(t("workspace.i18n_needs_schema_5", path=path))
    translit_table = _table(path, data, "translit")
    if translit_table is not None and schema < 7:
        raise WorkspaceError(t("workspace.translit_needs_schema_7", path=path))
    for table, keys in (("", data), ("names", names or {}), ("notes", notes or {}),
                        ("corpus", corpus or {}), ("tools", tools or {}), ("i18n", i18n_table or {}),
                        ("translit", translit_table or {})):
        unknown = sorted(set(keys) - _KEYS[table])
        if unknown:
            raise WorkspaceError(t("workspace.unknown_key", path=path, table=table + '.' if table else '', unknown=unknown[0]))
    names_dir, names_layers = None, None
    if schema >= 6:
        names_layers = _names_layers(path, root, names or {})
    elif names is not None:
        later = sorted(set(names) - {"dir"})
        if later:
            raise WorkspaceError(t("workspace.names_key_needs_schema_6", path=path, key=later[0]))
        d = names.get("dir", ".")
        if not isinstance(d, str):
            raise WorkspaceError(t("workspace.names_dir_not_string", path=path))
        names_dir = (root / d).resolve()
    corpus_dir = None
    if corpus is not None:
        d = corpus.get("dir")
        if not isinstance(d, str):
            raise WorkspaceError(t("workspace.corpus_dir_not_string", path=path))
        corpus_dir = (root / d).resolve()
    tool_path = tuple(p if p.is_absolute() else (root / p).resolve()
                      for p in (Path(s).expanduser() for s in _strings(path, "tools.path",
                                                                     (tools or {}).get("path", []))))
    locale, packs = _locale(path, i18n_table, schema), _strings(path, "i18n.packs", (i18n_table or {}).get("packs", []))
    try:                      # a pack misnamed or a language nobody speaks, said once and loudly here:
        i18n.check_settings(locale, packs)   # rendering forgives them in silence
    except i18n.CatalogError as error:
        raise WorkspaceError(t("workspace.i18n_refused", path=path, why=str(error))) from None
    return Workspace(root=root, villages=_strings(path, "villages", data.get("villages", [])),
                     names_dir=names_dir,
                     notes=_strings(path, "notes.globs", (notes or {}).get("globs", [])),
                     corpus_dir=corpus_dir, tool_path=tool_path,
                     plugins=_strings(path, "plugins", data["plugins"]) if "plugins" in data
                     else ("ru",) if schema < 4 else (),
                     locale=locale, packs=packs, names_layers=names_layers,
                     translit=_translit(path, translit_table or {}) if schema >= 7 else None)


def _translit(path: Path, table: dict[str, Any]) -> TranslitRoles:
    """`[translit]` of schema 7, as data: a profile's name for each role written, None for one left to the plugin."""
    roles: dict[str, str | None] = {}
    for role in ("address", "display"):
        value = table.get(role)
        if value is not None and (not isinstance(value, str) or not value):
            raise WorkspaceError(t("workspace.translit_profile_not_string", path=path, key=f"translit.{role}"))
        roles[role] = value
    return TranslitRoles(address=roles["address"], display=roles["display"])


def _names_layers(path: Path, root: Path, names: dict[str, Any]) -> NamesLayers:
    """`[names]` of schema 6, as data: which base is the plugins' to resolve, a layer's directory theirs to read."""
    if "dir" in names:
        raise WorkspaceError(t("workspace.names_dir_schema_6", path=path))
    base = names.get("base", DEFAULT_NAMES_BASE)
    if base is not False and (not isinstance(base, str) or not base):
        raise WorkspaceError(t("workspace.names_base_type", path=path))
    layers = tuple((root / d).resolve() for d in _strings(path, "names.layers", names.get("layers", [])))
    seen: set[Path] = set()
    for layer in layers:
        if layer in seen:
            raise WorkspaceError(t("workspace.names_layer_twice", path=path, layer=layer))
        seen.add(layer)
    writable = names.get("writable")
    if writable is None:
        chosen = layers[-1] if layers else None
    elif not isinstance(writable, str):
        raise WorkspaceError(t("workspace.names_writable_not_string", path=path))
    else:
        chosen = (root / writable).resolve()
        if chosen not in seen:
            raise WorkspaceError(t("workspace.names_writable_not_a_layer", path=path, writable=writable))
    return NamesLayers(base=base or None, layers=layers, writable=chosen)


def _locale(path: Path, i18n: dict[str, Any] | None, schema: int) -> str:
    """`[i18n] locale`; a file of schema 4 or older speaks Russian, a newer one without it English."""
    if schema < 5:
        return "ru"
    locale = (i18n or {}).get("locale", "en")
    if not isinstance(locale, str) or not locale:
        raise WorkspaceError(t("workspace.locale_not_string", path=path))
    return locale


def find(start: Path) -> Path:
    """The nearest directory from `start` up that holds `verso.toml`."""
    here = start.resolve()
    while True:
        if (here / CONFIG).is_file():
            return here
        if (here / ".git").exists():
            raise WorkspaceError(t("workspace.not_found_git", here=here, config=CONFIG, env=ENV))
        if here.parent == here:
            raise WorkspaceError(t("workspace.not_found", start=start, env=ENV))
        here = here.parent


def _excepthook(kind: type[BaseException], error: BaseException, tb: TracebackType | None) -> None:
    """A command that finds no workspace says why in a line: the traceback adds
    nothing to «run it from a checkout or set VERSO_WORKSPACE». Anything else
    goes to the hook that was there."""
    if isinstance(error, WorkspaceError):
        print(error, file=sys.stderr)
    else:
        _previous_excepthook(kind, error, tb)


# Installed at import: whatever command reaches the workspace imports this module.
# Only the message of an uncaught WorkspaceError changes; the exit code stays 1.
_previous_excepthook = sys.excepthook
sys.excepthook = _excepthook


_stack: list[Workspace] = []
_found: Workspace | None = None
_listeners: list[Callable[[], None]] = []


def _peek() -> Path | None:
    """The current root, if one is known, without looking for it."""
    if _stack:
        return _stack[-1].root
    return _found.root if _found is not None else None


def _notify_if_moved(before: Path | None) -> None:
    if _peek() != before:
        for listener in list(_listeners):
            listener()


def _discover() -> Workspace:
    named = os.environ.get(ENV)
    if named:
        if not (Path(named) / CONFIG).is_file():
            raise WorkspaceError(t("workspace.env_no_config", env=ENV, named=named, config=CONFIG))
        return load(Path(named))
    return load(find(Path.cwd()))


def current() -> Workspace:
    """The workspace this process works in (see the module's docstring)."""
    global _found
    if _stack:
        return _stack[-1]
    if _found is None:
        _found = _discover()
    return _found


@contextmanager
def use(root: Path) -> Generator[Workspace]:
    """Work in the workspace at `root` until the block ends."""
    ws = load(root)
    before = _peek()
    _stack.append(ws)
    _notify_if_moved(before)
    try:
        yield ws
    finally:
        _stack.pop()
        _notify_if_moved(ws.root)


def pin(root: Path | None) -> None:
    """Make `root` the process's workspace; None forgets it, and the next question
    looks again. A `use()` block in force stays in force."""
    global _found
    before = _peek()
    _found = load(root) if root is not None else None
    _notify_if_moved(before)


def on_change(listener: Callable[[], None]) -> None:
    """Call `listener` whenever the current workspace becomes another one."""
    _listeners.append(listener)


def child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment for a Python child: `base` (else this one's), naming the
    workspace this process found — the child's working directory may be anywhere."""
    return {**(os.environ if base is None else base), ENV: str(current().root)}


def _current_locale() -> str | None:
    try:
        return current().locale
    except WorkspaceError:
        return None


def _current_packs() -> tuple[str, ...]:
    try:
        return current().packs
    except WorkspaceError:
        return ()


# The interface speaks the workspace's language — asked when a message is read, never here.
i18n.configure(configured=_current_locale, packs=_current_packs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="verso workspace", description="Print the workspace's root or villages.")
    ap.add_argument("what", choices=("root", "villages"))
    args = ap.parse_args(argv)
    try:
        ws = current()
    except WorkspaceError as e:
        print(e, file=sys.stderr)
        return 2
    for line in ((str(ws.root),) if args.what == "root" else ws.villages):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
