"""A workspace's names lexicon as its sources, bottom to top — what `[names]` of verso.toml says, read.

The core reads `[names]` as data (`verso.core.workspace`): a file of schema ≤ 5 names a directory of the old
tables (`names_dir`), one of schema 6 a base and layers above it (`NamesLayers`). What that data means is
this plugin's:

  * schema ≤ 5 — one layer, the old three tables of `[names] dir` compiled (`verso.ru.naming.legacy`); no
    base under it: a name the table does not know stays unknown;
  * schema 6 — the base `[names] base` names (`ru`: the base this package ships, `verso.ru.naming.layer_files`;
    `false`: none), then each directory of `[names] layers`, a `FilesLayer` of three TSV files. A layer
    directory holding the old `names.csv` and no `names.tsv` is read as the old table, compiled — with a
    `DeprecationWarning`: the old format is read as a layer until 0.2.

`writable` marks the layer a name is added to.

A layer need not be a directory: a host that keeps its names elsewhere (a server's rows) hands the library the layer
as a `LayerSource` for the time it works in a workspace (`provided`) — `verso.toml` names the layer's directory as for
any layer, and the source stands in its place, the directory neither read nor needed.
"""
from __future__ import annotations

import hashlib
import warnings
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from verso.core import workspace
from verso.ru.messages import t
from verso.ru.naming.layer_files import FILES, FilesLayer, base
from verso.ru.naming.legacy import LegacyTables
from verso.ru.naming.lexicon import LayerSource

#: The bases a workspace of schema 6 may name in `[names] base`, by name.
BASES: dict[str, Callable[[], FilesLayer]] = {"ru": base}

#: The old tables a layer directory may hold instead of the three TSV files.
LEGACY_FILES = ("names.csv", "names_ignore.csv", "patronymics_ignore.csv")


#: The layers a host provides, by their directory as `[names] layers` resolves it (`provided`). Process-wide, as the
#: workspace is: the caller holds whatever lock it holds the workspace under.
_PROVIDED: dict[Path, LayerSource] = {}


@contextmanager
def provided(directory: Path, source: LayerSource) -> Generator[None]:
    """Until the block ends, the layer of `[names] layers` at `directory` (resolved, as `verso.core.workspace` resolves
    it) is `source` — a `LayerSource` of the host's own, in place of the directory of three files. The directory need not
    exist. `source.name` is the layer's name; to be kept between workspaces by the registry its `identity` says what it is
    (`names_registry._identity`)."""
    held = _PROVIDED.get(directory)
    _PROVIDED[directory] = source
    try:
        yield
    finally:
        if held is None:
            _PROVIDED.pop(directory, None)
        else:
            _PROVIDED[directory] = held


def base_digest(name: str) -> str | None:
    """The SHA-256 of the three files of the base `name` (`BASES`), None for a name no base has: what a records export
    fingerprints of the base (`Plugin.names_base_digest`)."""
    factory = BASES.get(name)
    if factory is None:
        return None
    directory = factory().directory
    digest = hashlib.sha256()
    for file in FILES.values():
        path = directory / file
        digest.update(f"{file}\0".encode())
        digest.update(path.read_bytes() if path.is_file() else b"")
    return digest.hexdigest()


def base_of(ws: workspace.Workspace, name: str) -> Callable[[], FilesLayer]:
    """The base `name` of `[names] base` (`BASES`): a name no plugin ships is a `WorkspaceError` naming the bases there
    are, whoever asks (a lookup, a tool that checks the workspace has names)."""
    factory = BASES.get(name)
    if factory is None:
        raise workspace.WorkspaceError(t("names_layers.unknown_base", config=ws.root / workspace.CONFIG, base=name,
                                         known=", ".join(sorted(BASES))))
    return factory


def sources(ws: workspace.Workspace) -> list[LayerSource]:
    """The lexicon's sources of `ws`, bottom to top (`LexiconNotConfigured` when a file of schema ≤ 5 keeps
    no `[names]`)."""
    config = ws.names_layers
    if config is None:
        return [LegacyTables(*(ws.names_file(name) for name in LEGACY_FILES))]
    out: list[LayerSource] = []
    if config.base is not None:
        out.append(base_of(ws, config.base)())
    for directory in config.layers:
        host = _PROVIDED.get(directory)
        if host is not None:
            out.append(host)
            continue
        out.append(layer_source(directory, name=layer_name(ws.root, directory),
                                writable=directory == config.writable))
    return out


def layer_name(root: Path, directory: Path) -> str:
    """A layer's name: its directory, from the workspace's root where it lies under it."""
    return directory.relative_to(root).as_posix() if directory.is_relative_to(root) else directory.as_posix()


def layer_source(directory: Path, *, name: str, writable: bool) -> LayerSource:
    """The source of one layer directory: its three TSV files, or — with a `DeprecationWarning` — the old
    `names.csv` it holds instead, compiled. A directory that does not exist is a `WorkspaceError`: a layer
    misnamed would otherwise answer «no such name» from nothing."""
    if not directory.is_dir():
        raise workspace.WorkspaceError(t("names_layers.no_directory", layer=name, path=directory))
    if not (directory / FILES["names"]).is_file() and (directory / LEGACY_FILES[0]).is_file():
        warnings.warn(str(t("names_layers.legacy_layer", layer=name, path=directory / LEGACY_FILES[0])),
                      DeprecationWarning, stacklevel=2)
        return LegacyTables(*(directory / file for file in LEGACY_FILES), name=name)
    return FilesLayer(directory, name=name, writable=writable)
