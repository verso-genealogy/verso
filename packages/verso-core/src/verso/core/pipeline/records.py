"""A village's records as records-v1 JSON on disk.

    <root>/<village>/index.json
    <root>/<village>/<YYYY>/<stem>.json      one per DSL file

`export_village` walks the village as `discover_records` does (`village_modules`:
years, then files, the ratchet's admissions applied) and writes each file's record
sets — every kind, divorces too — through `verso.core.records.encode`, one id counter for
the village, so a repeated number takes `~2` in this order, and puts the file's `#` notes on
its nodes (`verso.core.records.notes`). `index.json` names every
DSL file with the SHA-256 of its source, and why the ones that did not import did not.

**Reading them instead of the DSL.** With `VERSO_RECORDS=<root>` (or inside
`use(root)`), `verso.core.pipeline.load.load_module` builds a DSL file's record sets
from its JSON: every reader of the corpus — translator, consolidation, facts, familio,
the timeline, the CSVs (`verso export-csv`) — reads the export unchanged. A stale export
stops the program (`StaleRecords`, a `SystemExit`: the loaders catch `Exception` and
skip, and a skipped file read from an old export is the one thing this must not do):
any DSL file of the village changed, added or removed since; another schema; a
file's JSON missing, broken or from another export; or an input the derived values
rest on changed — the names tables, the ratchet list, the library's code. `make tf-*`
refuses the variable outright. Never export it in a shell — set it per command.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import shlex
import shutil
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from importlib.resources import files as package_files
from importlib.resources.abc import Traversable
from typing import Any

from verso.core.targets.geni.held import LIST_FILE

from verso.core.pipeline.load import record_namespace, village_modules
from verso.core.records import SCHEMA_ID
from verso.core.records.decode import decode_file
from verso.core.records.encode import FormatError, encode_namespace
from verso.core.records.ids import Ids, entry_token, walk
from verso.core.records.notes import place_notes
from verso.core import plugins
from verso.core import i18n
from verso.core.i18n import Message
from verso.core.messages import t

INDEX = "index.json"
ENV = "VERSO_RECORDS"

_ROOT: ContextVar[Path | None] = ContextVar("records_root", default=None)
_CHECKED: dict[tuple[str, str], tuple[object, dict[str, Any]]] = {}
_ANNOUNCED: set[str] = set()


class StaleRecords(SystemExit):
    """An export that is not the DSL's any more: the program stops, a reader cannot skip it."""


class ExportError(RuntimeError):
    """An export that would overwrite what is not an export."""


@dataclass
class Exported:
    files: list[Path] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    records: int = 0
    notes: int = 0                  # bound to the node their anchor names
    manual_notes: int = 0           # on a file as `manual`
    # The files whose notes went on no record, and why (`verso.core.records.notes`: uncounted,
    # count, number).
    unbound: dict[str, str] = field(default_factory=dict)


def dumps(doc: Mapping[str, object]) -> str:
    """A records JSON file's text: UTF-8 as written, one-space indent, a final newline."""
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _count(doc: Mapping[str, object]) -> int:
    documents = doc["documents"]
    assert isinstance(documents, list)
    return sum(len(run["records"]) for d in documents if "pages" in d for run in d["pages"])


def export_village(village_dir: str | Path, out_root: str | Path) -> Exported:
    """Write `<out_root>/<village>/…` for one village; what was written and skipped."""
    village_dir, out_root = Path(village_dir), Path(out_root)
    reading = root()
    if reading is not None and reading.resolve() == out_root.resolve():
        raise ExportError(t("records_export.out_is_the_root", out=out_root, env=ENV))
    target = out_root / village_dir.name
    if target.exists():
        if (target / INDEX).is_file():
            shutil.rmtree(target)
        elif any(target.iterdir()):
            raise ExportError(t("records_export.not_an_export", target=target))
    target.mkdir(parents=True, exist_ok=True)
    skipped: list[tuple[Path, Exception]] = []
    ids = Ids()
    exported = Exported()
    sources: dict[str, str] = {}
    for dsl_file, module in village_modules(village_dir, skipped=skipped):
        rel = dsl_file.relative_to(village_dir).as_posix()
        sources[rel] = _sha256(dsl_file)
        namespace = record_namespace(module)
        doc = encode_namespace(namespace, village=village_dir.name, file=rel,
                               sha256=sources[rel], ids=ids)
        _notes(dsl_file, namespace, doc, rel, exported)
        out = target / dsl_file.parent.name / f"{dsl_file.stem}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dumps(doc), encoding="utf-8")
        exported.files.append(out)
        exported.records += _count(doc)
    for path, exc in skipped:
        rel = path.relative_to(village_dir).as_posix()
        sources[rel] = _sha256(path)
        with i18n.use(i18n.SOURCE):     # a derived artefact a corpus hashes follows no interface language
            exported.skipped[rel] = f"{type(exc).__name__}: {exc}"
    index = {"schema": SCHEMA_ID, "village": village_dir.name, "files": dict(sorted(sources.items())),
             "skipped": exported.skipped, "inputs": inputs(village_dir)}
    (target / INDEX).write_text(dumps(index), encoding="utf-8")
    return exported


def _notes(dsl_file: Path, namespace: Mapping[str, object], doc: dict[str, Any], rel: str,
           exported: Exported) -> None:
    """The file's `#` notes on its nodes, as the plugin reads them (`plugins.source_notes`); none
    when the plugin reads none. The notes rest on the file's text, which the index hashes, and on
    the plugin's code, which `inputs` fingerprints: an export they would change is stale already."""
    found = plugins.source_notes(dsl_file.read_text(encoding="utf-8"))
    if found is None:
        return
    numbers = [entry_token(record).number for _, record in walk(namespace)]
    placed = place_notes(doc, found, numbers)
    exported.notes += placed.bound
    exported.manual_notes += placed.manual
    if placed.refused is not None and found.notes:
        exported.unbound[rel] = placed.refused


def library() -> tuple[str, ...]:
    """The library's packages whose code derived the values an export holds: the core's and
    each enabled plugin's."""
    return ("verso.core", *(plugin.package for plugin in plugins.enabled()))


def code_fingerprint() -> str:
    """The fingerprint of the current workspace's library and of its corpus's landlords'
    statuses (`code_fingerprint_of`) — read from the workspace's corpus directory, as every
    datum of the corpus is: the core imports no `corpus` package."""
    from verso.core import workspace

    corpus = workspace.current().corpus_dir
    statuses = corpus / "statuses.py" if corpus is not None else None
    return code_fingerprint_of(library(), statuses if statuses is not None and statuses.is_file() else None)


@functools.cache
def code_fingerprint_of(packages: tuple[str, ...], statuses: Path | None = None) -> str:
    """The SHA-256 of the Python sources of `packages` — what derived the values an export
    holds — and of `statuses`, the corpus's landlords' statuses the plugin re-exports: a
    status's words and sex are values the export keeps."""
    digest = hashlib.sha256()

    def walk(node: Traversable, prefix: str) -> None:
        for child in sorted(node.iterdir(), key=lambda c: c.name):
            if child.is_dir():
                if child.name != "__pycache__":
                    walk(child, f"{prefix}{child.name}/")
            elif child.name.endswith(".py"):
                digest.update(f"{prefix}{child.name}\0".encode())
                digest.update(child.read_bytes())

    for package in packages:
        walk(package_files(package), f"{package}/")
    if statuses is not None:
        digest.update(b"corpus/statuses.py\0")
        digest.update(statuses.read_bytes())
    return digest.hexdigest()


#: The corpus's landlords' statuses as data (`verso.ru.domain.statuses`): a status's words and sex are values an
#: export keeps. Their module form, `statuses.py`, is code, fingerprinted with the library's (`code_fingerprint`).
STATUSES_DATA = "statuses.toml"


def _input_files(village_dir: Path) -> dict[str, Path]:
    """The files besides the DSL an export's derived values rest on: the ratchet list
    (which unreviewed records are on Geni), the workspace's names tables (schema 6: each layer's
    files, keyed by the layer's directory) and, where the
    corpus holds them as data, its statuses (`corpus/statuses.toml`; absent, it is no input,
    so an index of before reads as it did — and a file that appears stales the export)."""
    from verso.core.workspace import WorkspaceError, current

    found = {LIST_FILE: village_dir / LIST_FILE}
    try:
        ws = current()
    except WorkspaceError:
        ws = None
    names_dir, layers, corpus = (ws.names_dir, ws.names_layers, ws.corpus_dir) if ws is not None else (None, None, None)
    if names_dir is not None:
        found.update({f"names/{name}": names_dir / name for name in plugins.names_tables()})
    if ws is not None and layers is not None:
        files = tuple(dict.fromkeys((*plugins.names_layer_files(), *plugins.names_tables())))
        for layer in layers.layers:
            where = layer.relative_to(ws.root).as_posix() if layer.is_relative_to(ws.root) else layer.as_posix()
            found.update({f"names/{where}/{name}": layer / name for name in files})
    if corpus is not None and (corpus / STATUSES_DATA).is_file():
        found[f"corpus/{STATUSES_DATA}"] = corpus / STATUSES_DATA
    return found


def inputs(village_dir: Path) -> dict[str, str]:
    """`code` and each input file's SHA-256 ("" for one that is absent)."""
    from verso.core.workspace import WorkspaceError, current

    out = {"code": code_fingerprint()}
    for key, path in _input_files(village_dir).items():
        out[key] = _sha256(path) if path.is_file() else ""
    try:
        layers = current().names_layers
    except WorkspaceError:
        layers = None
    if layers is not None:  # schema 6: the base the layers sum over is an input too — its name and its files' bytes
        # (data, not the code `code` fingerprints), so a release that changes the base's rows stales an export
        base = layers.base
        out["names/base"] = "" if base is None else f"{base}:{plugins.names_base_digest(base) or ''}"
    return out


def _hint(village: str) -> Message:
    return t("records_export.hint", village=shlex.quote(village))


def root() -> Path | None:
    """Where records are read from instead of the DSL: the innermost `use()`, else
    `VERSO_RECORDS`; None reads the DSL."""
    inner = _ROOT.get()
    if inner is not None:
        return inner
    value = os.environ.get(ENV)
    return Path(value) if value else None


@contextmanager
def use(root_: str | Path) -> Generator[None]:
    """Read records from the export under `root_` inside this block."""
    token = _ROOT.set(Path(root_))
    try:
        yield
    finally:
        _ROOT.reset(token)


def _dsl_files(village_dir: Path) -> dict[str, Path]:
    return {p.relative_to(village_dir).as_posix(): p
            for p in sorted(village_dir.glob("[0-9][0-9][0-9][0-9]/*.py"))}


def _index(root_: Path, village_dir: Path, village: str) -> dict[str, Any]:
    """The village's index, once its export is known to be the DSL's: every DSL file
    hashed the first time and again whenever a file's size or mtime moves."""
    files = _dsl_files(village_dir)
    watched = [*files.items(), *((k, p) for k, p in _input_files(village_dir).items() if p.is_file())]
    stamp = (tuple((rel, p.stat().st_mtime_ns, p.stat().st_size) for rel, p in watched), code_fingerprint())
    key = (str(root_.resolve()), str(village_dir.resolve()))
    cached = _CHECKED.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    hint = _hint(village)
    path = root_ / village / INDEX
    if not path.is_file():
        raise StaleRecords(t("records_export.missing", village=village, root=root_, env=ENV, hint=hint))
    index: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if index.get("schema") != SCHEMA_ID:
        raise StaleRecords(t("records_export.other_schema", village=village, found=index.get('schema'), wanted=SCHEMA_ID, hint=hint))
    exported: dict[str, str] = index["files"]
    for rel in sorted(files.keys() | exported.keys()):
        if rel not in exported:
            reason = t("records_export.reason_new")
        elif rel not in files:
            reason = t("records_export.reason_gone")
        elif _sha256(files[rel]) != exported[rel]:
            reason = t("records_export.reason_changed")
        else:
            continue
        raise StaleRecords(t("records_export.stale_file", village=village, rel=rel, reason=reason, hint=hint))
    recorded: dict[str, str] = index.get("inputs", {})
    now = inputs(village_dir)
    for item in sorted(now.keys() | recorded.keys()):
        if now.get(item) != recorded.get(item):
            what = t("records_export.code_changed") if item == "code" \
                else t("records_export.input_changed", name=item.removeprefix("names/"))
            raise StaleRecords(t("records_export.stale_input", village=village, what=what, hint=hint))
    if str(root_) not in _ANNOUNCED:
        _ANNOUNCED.add(str(root_))
        print(t("records_export.reading_json", root=root_, env=ENV), file=sys.stderr)
    _CHECKED[key] = (stamp, index)
    return index


def read_namespace(dsl_path: Path, *, village_dir: Path | None = None) -> dict[str, Any]:
    """A DSL file's record sets, read from its JSON under `root()`. `village_dir` is the
    village when the file runs from a copy elsewhere (a mirror holding the year files
    only): the export is checked against the village, and the copy against the export."""
    root_ = root()
    if root_ is None:
        raise RuntimeError(str(t("records_export.reading_dsl", env=ENV)))
    real = village_dir if village_dir is not None else dsl_path.parent.parent
    name = real.name
    index = _index(root_, real, name)
    rel = f"{dsl_path.parent.name}/{dsl_path.name}"
    if village_dir is not None and _sha256(dsl_path) != index["files"].get(rel):
        raise StaleRecords(t("records_export.copy_changed", name=name, rel=rel, hint=_hint(name)))
    if rel in index["skipped"]:
        raise ImportError(index["skipped"][rel])
    path = root_ / name / dsl_path.parent.name / f"{dsl_path.stem}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StaleRecords(t("records_export.json_unreadable", name=name, rel=rel, error=type(exc).__name__, hint=_hint(name))) from exc
    if doc.get("schema") != SCHEMA_ID or doc.get("sha256") != index["files"].get(rel):
        raise StaleRecords(t("records_export.json_foreign", name=name, rel=rel, hint=_hint(name)))
    try:
        return decode_file(doc)
    except (FormatError, KeyError, TypeError, ValueError) as exc:
        raise StaleRecords(t("records_export.json_broken", name=name, rel=rel, error=type(exc).__name__, detail=exc, hint=_hint(name))) from exc
