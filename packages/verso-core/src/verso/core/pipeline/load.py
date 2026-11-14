"""A DSL file as a module, and a village's record sets in the order the translator reads them.

Moved verbatim out of `verso.ru.cli.generate_tf` (and `SOURCE_PATTERNS` out of
`verso.ru.cli.all_persons`) before 0.1.0: the consolidation checks and Verso read the corpus
through these, and a library does not import its CLI. Since 0.1.0 the record kinds, the globs
of a village's files and the order of its books are the plugin's DSL (`plugins.dsl()`;
the Russian books' are `verso.ru.dsl.kinds`): the core knows none of its own.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from verso.core import corpus_data, plugins, workspace
from verso.core import ratchet
from verso.core.records.sets import record_sets
from verso.core.records.ids import RecordIds
from verso.core.targets.geni.held import ON_GENI


def record_types(*, translated: bool = False) -> tuple[type, ...]:
    """The record sets the workspace's DSL binds: every kind — the records export reads them
    all —, or the ones the translator reads (`translated`; a divorce reaches only its CSV
    and the JSON)."""
    return tuple(kind.set_type for kind in plugins.dsl().kinds if kind.translated or not translated)


def load_module(path: Path) -> ModuleType:
    """Import a DSL file as a synthetic module (its name is not `__main__`).

    Compiled from the source, never from `__pycache__`: a .pyc is trusted while
    the file's mtime SECOND and size are unchanged, so Verso re-reading a file
    it saved within the same second — one surname for another of its length —
    got the old records back. Compiling the whole corpus costs under a second.

    With `VERSO_RECORDS` set the module holds the file's record sets read from
    the export instead, and an unreviewed record the village's ratchet lists comes
    back already marked `on_geni`: the JSON keeps the mark. From the DSL the mark is
    `admit_listed`'s, after the load, so a caller of this function alone sees it in
    JSON mode only; `village_modules` gives both modes the same records.
    """
    from verso.core.pipeline import records

    spec = importlib.util.spec_from_file_location(
        f"dsl_{path.stem}_{path.parent.name}", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load DSL spec for {path}")
    module = importlib.util.module_from_spec(spec)
    if records.root() is not None:            # The record sets from the export, not the DSL
        vars(module).update(records.read_namespace(path))
        return module
    _run(compile(path.read_bytes(), str(path), "exec"), vars(module), path)
    return module


def _run(code: Any, namespace: dict[str, Any], path: Path) -> None:
    """`exec` the DSL; a module it no longer has (ru: DSL v0's `geni.*`) is told what the
    plugin advises (`Dsl.legacy_import`) — the file whose import failed, which is the DSL file's
    own or a module it imports (`corpus/statuses.py`)."""
    try:
        exec(code, namespace)
    except ModuleNotFoundError as exc:
        advise = plugins.dsl().legacy_import
        importer = _importer(exc, path)
        hint = advise(exc.name or "", importer) if advise is not None else None
        if hint is not None:
            raise ImportError(f"{importer}: {hint}") from exc
        raise


def _importer(exc: BaseException, path: Path) -> Path:
    """The file whose import statement raised `exc`: its traceback's innermost frame outside
    the import machinery (`<frozen importlib…>`)."""
    found, tb = path, exc.__traceback__
    while tb is not None:
        name = tb.tb_frame.f_code.co_filename
        if not name.startswith("<"):
            found = Path(name)
        tb = tb.tb_next
    return found


def build_text(path: Path, text: str) -> dict[str, Any]:
    """The namespace `text` builds, run as the module at `path` would be — nothing is
    written, nothing read but the text: what a preview of an unsaved edit reads. The
    records JSON (`VERSO_RECORDS`) is not consulted: a text has no export."""
    namespace: dict[str, Any] = {"__name__": f"dsl_preview_{path.stem}", "__file__": str(path)}
    _run(compile(text, str(path), "exec"), namespace, path)
    return namespace


# The child names what its error is — an exception's `verso_code` — on a line of its own before
# the traceback, whose last line stays what the error says.
_CODE_LINE = "verso-code: "
_IMPORT_CHECK = "\n".join((
    "import sys",
    "from pathlib import Path",
    "from verso.core.pipeline.load import load_module",
    "try:",
    "    load_module(Path(sys.argv[1]))",
    "except BaseException as error:",
    "    code = getattr(error, 'verso_code', None)",
    "    if code:",
    f"        print({_CODE_LINE!r} + str(code), file=sys.stderr)",
    "    raise",
))


@dataclass(frozen=True)
class ImportProblem:
    """Why a file does not import: the exception's last line, and its `verso_code` where the
    exception carries one (what it is, for a reader that does not read the text)."""
    text: str
    code: str | None = None


def import_problem(path: Path, *, cwd: Path, timeout: float = 120) -> ImportProblem | None:
    """Whether the file at `path` imports, in a clean interpreter started in `cwd`
    (the module cache of this process holds the names tables it read): None when it
    does; else what went wrong."""
    # The child's error is read as text, not shown on a terminal: no colour, whatever forces it.
    env = {k: v for k, v in workspace.child_env().items() if k not in ("FORCE_COLOR", "PYTHON_COLORS")}
    proc = subprocess.run([sys.executable, "-c", _IMPORT_CHECK, str(path)], cwd=cwd,
                          env={**env, "PYTHON_COLORS": "0", "NO_COLOR": "1"},
                          capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode == 0:
        return None
    lines = [line for line in proc.stderr.strip().splitlines() if line.strip()]
    code = next((line[len(_CODE_LINE):].strip() for line in lines if line.startswith(_CODE_LINE)), None)
    lines = [line for line in lines if not line.startswith(_CODE_LINE)]
    return ImportProblem(lines[-1] if lines else f"exit {proc.returncode}", code or None)


def import_check(path: Path, *, cwd: Path, timeout: float = 120) -> str | None:
    """`import_problem`'s text: None when the file imports, else the exception's last line."""
    problem = import_problem(path, cwd=cwd, timeout=timeout)
    return None if problem is None else problem.text


# -- a corpus's files: <root>/<village>/<year>/*.py

_YEAR = re.compile(r"^\d{4}$")


def village_dirs(root: Path) -> list[Path]:
    """The villages under a corpus's root: each directory holding a year's directory."""
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and any(
                c.is_dir() and _YEAR.match(c.name) for c in d.iterdir()):
            out.append(d)
    return out


def book_order(path: Path) -> tuple[str, int, str]:
    """A year's files in the order of the DSL's globs (`plugins.dsl().globs` — for the
    Russian books, as the metric book holds them: births, marriages, deaths, then the rest,
    in the order village.db takes them in); a file no glob names comes last."""
    rel = f"{path.parent.name}/{path.name}"
    globs = plugins.dsl().globs
    kind = next((k for k, pattern in enumerate(globs) if fnmatch.fnmatch(rel, pattern)), len(globs))
    return path.parent.name, kind, path.name


def dsl_files(village: Path) -> list[Path]:
    """A village's DSL files, year by year, each year's in `book_order`."""
    return sorted((p for y in village.iterdir() if y.is_dir() and _YEAR.match(y.name)
                   for p in y.glob("*.py")), key=book_order)


def admit_listed(dsl_file: Path, village_dir: Path, module: Any,
                 listed: dict[str, list[ratchet.Entry]], *, admit_all: bool = False,
                 seen: list[tuple[str, Any, ratchet.RecordPrint]] | None = None) -> None:
    """Mark `on_geni` on the unreviewed records of one loaded DSL file that the
    village's ratchet lists (`verso.core.ratchet`): unreviewed, already on Geni,
    and unchanged since. Every other unreviewed record stays held.

    `admit_all` admits every unreviewed record of the file instead, and `seen`
    collects each as (file, record, print) — the seeding pass, which asks the
    translation what each would emit before terraform state says what is
    there. Raises `RatchetError` for a file whose calls cannot be paired with
    its records: guessing which line is which would admit the wrong record."""
    rel = dsl_file.relative_to(village_dir).as_posix()
    lines = listed.get(rel)
    if not lines and not admit_all:
        return
    if not any(ratchet.unreviewed(r) for r in ratchet.runtime_records(vars(module))):
        return
    pairs = ratchet.pair(dsl_file.read_text(encoding="utf-8"), module, where=rel)
    if not admit_all:
        ratchet.admit(pairs, (e.fingerprint for e in lines or ()))
        return
    for record, p in pairs:
        if ratchet.unreviewed(record):
            setattr(record, ON_GENI, True)
            if seen is not None:
                seen.append((rel, record, p))


def village_modules(village_dir: str | Path, year: int | list[int] | None = None,
                    skipped: list[tuple[Path, Exception]] | None = None, *,
                    admit_all_unreviewed: bool = False,
                    seen: list[tuple[str, Any, ratchet.RecordPrint]] | None = None,
                    ) -> Iterator[tuple[Path, ModuleType]]:
    """(dsl_path, module) for every DSL file under `village_dir/[0-9]{4}/*.py`, years
    then files in name order, each module's unreviewed records admitted by the
    village's ratchet (`admit_listed`). A file that fails to import is skipped with a
    warning on stderr and, when `skipped` is given, appended to it as `(path, exception)`.

    The walk `discover_records` sorts into the translator's order, and the one the
    records export takes as it is."""
    root = Path(village_dir)
    plugins.dsl()          # a workspace without its plugin is refused here, not file by file
    listed = ratchet.by_file(ratchet.read_list(root / ratchet.LIST_FILE))
    year_dirs = sorted(
        d for d in root.iterdir()
        if d.is_dir() and d.name.isdigit() and len(d.name) == 4
    )
    if year is not None:
        years_set = {year} if isinstance(year, int) else set(year)
        if years_set:
            year_dirs = [d for d in year_dirs if int(d.name) in years_set]

    for year_dir in year_dirs:
        for dsl_file in sorted(year_dir.glob("*.py")):
            try:
                module = load_module(dsl_file)
            except Exception as exc:
                print(f"warning: skipping {dsl_file}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                if skipped is not None:
                    skipped.append((dsl_file, exc))
                continue
            admit_listed(dsl_file, root, module, listed,
                         admit_all=admit_all_unreviewed, seen=seen)
            yield dsl_file, module


def record_namespace(module: ModuleType) -> dict[str, object]:
    """The record sets a DSL module binds, every kind (divorces too), in the module's order —
    an alias bound under each of its names."""
    kinds = record_types()
    return {name: value for name, value in vars(module).items() if isinstance(value, kinds)}


def discover_records(village_dir: str, year: int | list[int] | None = None,
                     skipped: list[tuple[Path, Exception]] | None = None, *,
                     admit_all_unreviewed: bool = False,
                     seen: list[tuple[str, Any, ratchet.RecordPrint]] | None = None,
                     ids: RecordIds | None = None,
                     ) -> Iterator[tuple[Path, str, object]]:
    """Yield (dsl_path, module_name, records_object) triples for every
    DSL-defined records container under `village_dir/[0-9]{4}/*.py`,
    in the order of the DSL (`plugins.dsl().order`) — for the Russian books the legacy
    iteration order: village MK (births → marriages → deaths) → other-parish MK (same
    triple) → census. Within each MK category records sort chronologically; census
    records follow the village's `[census] order`.

    DSL files that fail to import (e.g. `Unrecognized patronymic` errors in
    old census data) are skipped with a warning on stderr so a single broken
    file doesn't abort a full-village run. When `skipped` is provided, each
    skipped file is appended as `(path, exception)` so callers can fail the
    run loudly (see `main --strict`) — a missing import silently dropping
    every record in a file is otherwise easy to miss.

    An unreviewed record comes out held unless the village's ratchet lists it
    (`admit_listed`); `admit_all_unreviewed` and `seen` are the seeding pass's.

    `ids` counts every record of every file (`RecordIds.walk`) as the walk
    meets it — the records export's order, before the sort — so a record's id
    is the one the records JSON gives it, held records and divorces counted.
    A record set bound to several names is one book: it comes out once, under
    the first name that binds it (`record_sets`).
    """
    dsl = plugins.dsl()
    translated = record_types(translated=True)
    discovered: list[tuple[Path, str, object]] = []
    for dsl_file, module in village_modules(village_dir, year, skipped,
                                            admit_all_unreviewed=admit_all_unreviewed, seen=seen):
        if ids is not None:
            ids.walk(record_namespace(module))
        for attr_name, value in record_sets(vars(module), translated).items():
            discovered.append((dsl_file, attr_name, value))

    village = corpus_data.village(village_dir)
    discovered.sort(key=lambda t: dsl.order(t[0], t[2], village))
    yield from discovered
