"""The linters on records JSON agree with `dsllint` on the library's samples.

`tests/data/linter_samples/` holds every DSL text the library's tests handed a check (bare calls and
whole files, harvested before the move); `tests/data/on_json_samples/` the texts invented for a code
no harvested sample reaches. Each sample is run as the DSL sees it — the facade's names, its three
catalogs and the fixture corpus's statuses in scope, a bare call bound to a name — and its record
sets are encoded to records v1. For every code `on_json.SUPPORTED` lists, the findings `dsllint` gives
of the text and those `lint_records` gives of the JSON are compared as multisets of (code, params,
variant, token), a positional code folded into its keyword code by `hosted.toml`'s `as`; the line
differs by design (an id there).

A sample that does not load (a syntax error, a name the fixture lacks, DSL v0 imports, an argument
the factory refuses), holds no record set, is one the export refuses, or makes `dsllint` itself crash, is skipped and counted;
`test_samples_load` prints the counts.

The oracle is parametrised over `SUPPORTED`: a code added to the registry is judged by it at once.
"""
from __future__ import annotations

import ast
import copy
import json
import shutil
import tempfile
import types
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import pytest

from thin_dictionary import thin_workspace
from verso.core import workspace
from verso.core.records import FormatError
from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru import dsl
from verso.ru.domain import causes_of_death as domain_causes
from verso.ru.domain import statuses as domain_statuses
from verso.ru.dsl import causes_of_death, marital_status, statuses
from verso.ru.linters import hosted, on_json
from verso.ru.linters.checks.reviewed_redundancy import INNER_CALLS
from verso.ru.linters.checks.single_line_calls import KNOWN_CAUSES, known_statuses
from verso.ru.linters.dsllint import check_file_json

DATA = Path(__file__).resolve().parent / "data"
SAMPLE_DIRS = (DATA / "linter_samples", DATA / "on_json_samples")

Key = tuple[str, str, str, str | None]

# A ratchet: how many samples load today. Raise it when samples are added, never lower it.
LOADED = 154
# DVC001's sample writes a divorce's marriage as text on purpose: the warning DSL v1 gives for it is expected here.
pytestmark = pytest.mark.filterwarnings(r"ignore:divorce\(marriage_date=:DeprecationWarning")


@dataclass(frozen=True)
class Sample:
    """A sample that loaded: what `dsllint` says of its text, and its records v1."""
    name: str
    text: str
    dsllint: Counter[Key]
    data: dict[str, Any]
    ids: frozenset[str]


@dataclass(frozen=True)
class Skipped:
    name: str
    why: str


def _facade() -> dict[str, Any]:
    """The names a DSL file sees: the facade, its three catalogs, the corpus's statuses."""
    import corpus.statuses as corpus_statuses

    scope: dict[str, Any] = {name: getattr(dsl, name) for name in dsl.__all__}
    for catalog in (statuses, causes_of_death, marital_status, corpus_statuses):
        scope.update({k: v for k, v in vars(catalog).items() if not k.startswith("_")})
    return scope


class _BindCalls(ast.NodeTransformer):
    """A bare call at the top of a sample becomes an assignment: a record set must be bound to a
    name to be a record set of a file."""

    def __init__(self) -> None:
        self.count = 0

    def visit_Module(self, node: ast.Module) -> ast.Module:
        body: list[ast.stmt] = []
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                self.count += 1
                stmt = ast.copy_location(ast.Assign(
                    targets=[ast.Name(id=f"sample_{self.count}", ctx=ast.Store())], value=stmt.value), stmt)
            body.append(stmt)
        node.body = body
        return ast.fix_missing_locations(node)


def _try_load(text: str) -> tuple[types.ModuleType | None, str]:
    """The sample run as a DSL module and "", or None and the name of what stopped it: a syntax
    error, a name the fixture lacks, an import of DSL v0, an argument a factory refuses."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return None, type(error).__name__
    tree = _BindCalls().visit(tree)
    module = types.ModuleType("sample")
    vars(module).update(_facade())
    try:
        exec(compile(tree, "<sample>", "exec"), vars(module))
    except Exception as error:  # NameError, ImportError, a factory's refusal: all "does not load"
        return None, type(error).__name__
    return module, ""


def load_sample(text: str) -> types.ModuleType | None:
    """The sample run as a DSL module, or None when it does not load."""
    return _try_load(text)[0]


def _key(code: str, variant: str, params: dict[str, Any], token: str | None) -> Key:
    return code, json.dumps(params, ensure_ascii=False, sort_keys=True), variant, token


@dataclass(frozen=True)
class SourceForm:
    """A variant `dsllint` says and the JSON cannot: `said` is its prefix. The JSON reads it as the variant
    `read` of the same ending, less the params in `dropped`; with `read` None the variant is absent on JSON. With
    `when` the form holds only for a finding whose line satisfies that condition of the sample (`_conditions_at`)."""
    said: str
    read: str | None
    dropped: frozenset[str] = frozenset()
    when: str | None = None
    renamed: tuple[tuple[str, str], ...] = ()
    unquoted: frozenset[str] = frozenset()


# What only the source holds, by code. SOR001's `bound_*` variants name the string a file binds (`name=`); the JSON
# holds the text and answers `literal_*` of it. RVR001's page-level variants (`page_*`: a `page()`'s flag equal to
# the set's; `inner_page_*`: a record's equal to the page's) are absent: a page that wrote the set's own value
# leaves no trace in the export, and what a page gave a record is only the record's value. The `inner_records_*` found
# inside a `page()` call are absent too: the export merges the page() calls of one label and cannot show whether the
# page wrote a flag, so the walk answers a record outside every page only, and in a run of such records only when
# one of them wrote no flag (it shows no `page(None, …)` lies over the run). Such a finding's params (value, func,
# effective, records) do not say where it was found, so the two forms are keyed on the sample's structure
# (`_conditions_at`): `in_page`, the line of the finding lies within a `page(…)` call; `flagged_run`, it lies in a
# record of a run of consecutive records outside every page that all wrote their own `reviewed=`.
# The positional forms (BRD002, BRD004, CRD003, CRD006, DRA002's `redundant_positional`) are not here: the export holds an
# argument by its parameter, so hosted.toml's `as` and `forms` fold them (`hosted.fold`), for this oracle and the corpus's.
SOURCE_ONLY: dict[str, tuple[SourceForm, ...]] = {
    "SOR001": (SourceForm("bound_", "literal_", frozenset({"name"})),),
    "RVR001": (SourceForm("inner_page_", None), SourceForm("page_", None),
               SourceForm("inner_records_", None, when="in_page"),
               SourceForm("inner_records_", None, when="flagged_run")),
}


# The param of a code that names a status or a cause-of-death constant. The JSON holds the constant as
# `{text, …}`, so of the constants that spell one value (STATE_PEASANT_MALE, GOSUDARSTVENNYJ_PEASANT_MALE) the walk
# names the one `known_statuses` / `KNOWN_CAUSES` pick, as SLC002 does; `dsllint` names the one the source wrote.
CONSTANT_PARAMS: dict[str, str] = {
    "CSR001": "status", "NAM004": "status", "SLC003": "value", "SLC005": "value", "VSR001": "status"}


# The codes whose TOKEN is the name of a status constant (ZGS004: the identifier the source wrote, or the words of a
# literal): the same alias rule applies to it.
CONSTANT_TOKENS: frozenset[str] = frozenset({"ZGS004"})


def _same_value(name: str) -> str:
    """The name the walk gives the constant `name` (itself when it is no constant)."""
    if name in (catalog := domain_statuses.catalog()):
        return known_statuses()[str(catalog[name])]
    if isinstance(text := getattr(domain_causes, name, None), str):
        return KNOWN_CAUSES[str(text)]
    return name


def _as_json_reads(code: str, variant: str, params: dict[str, Any],
                   within: frozenset[str] = frozenset()) -> tuple[str, dict[str, Any]] | None:
    """What `dsllint` says of the source, less what only the source holds (`SOURCE_ONLY`, `CONSTANT_PARAMS`);
    None for a finding the JSON does not have. `within` names the conditions of the sample that hold at the finding's line."""
    param = CONSTANT_PARAMS.get(code)
    if param is not None and isinstance(params.get(param), str):
        params = {**params, param: _same_value(params[param])}
    for form in SOURCE_ONLY.get(code, ()):
        if variant.startswith(form.said) and (form.when is None or form.when in within):
            if form.read is None:
                return None
            return form.read + variant.removeprefix(form.said), {k: v for k, v in params.items() if k not in form.dropped}
    return variant, params


def _runs(args: list[ast.expr]) -> Iterator[ast.Call | None]:
    """The records a record set's arguments write, in order, outside every `page()`; None marks a page's place, which
    ends a run. A wrapper (`death_month`, `book`) is read through."""
    for arg in args:
        node = arg.value if isinstance(arg, ast.Starred) else arg
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in INNER_CALLS:
                yield node
            elif node.func.id == "page":
                yield None
            else:
                yield from _runs(node.args)


def _conditions_at(path: Path) -> dict[int, frozenset[str]]:
    """For each line of `path`, the conditions of `SOURCE_ONLY` that hold there: `in_page` (the line lies within a
    `page()` call) and `flagged_run` (within a record of a run outside every page that all wrote `reviewed=`)."""
    spans: dict[int, set[str]] = {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return {}

    def mark(node: ast.Call, condition: str) -> None:
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            spans.setdefault(line, set()).add(condition)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "page":
                mark(node, "in_page")
            elif node.func.id.endswith("_records"):
                run: list[ast.Call] = []
                for item in [*_runs(node.args), None]:
                    if item is not None:
                        run.append(item)
                        continue
                    if run and all(any(kw.arg == "reviewed" for kw in call.keywords) for call in run):
                        for call in run:
                            mark(call, "flagged_run")
                    run = []
    return {line: frozenset(names) for line, names in spans.items()}


def _dsllint_of(path: Path, table: dict[str, hosted.Readiness]) -> tuple[Counter[Key], bool]:
    """The findings of every linter on `path`, folded by `as`; the second is True when a linter crashed."""
    out: Counter[Key] = Counter()
    crashed = False
    conditions = _conditions_at(path)
    for result in check_file_json(path):
        for found in result["issues"]:
            message = found["message"]
            code = getattr(message, "code", "")
            if code == "LNT001":
                crashed = True
            read = _as_json_reads(code, getattr(message, "variant", ""), dict(getattr(message, "params", {})),
                                  conditions.get(found.get("line") or 0, frozenset()))
            if read is not None:
                folded, variant, params = hosted.fold(code, *read, table)
                token = getattr(message, "token", None)
                out[_key(folded, variant, params, _same_value(token) if code in CONSTANT_TOKENS and token else token)] += 1
    return out, crashed


def _ids(data: Any) -> frozenset[str]:
    """The ids a finding may address: every book's and every record's the JSON holds, wherever the
    document keeps its records (pages, a list's entries, a card). A persona (it has a `role`) is
    not one."""
    out: set[str] = set()
    if isinstance(data, dict):
        if isinstance(data.get("id"), str) and "role" not in data:
            out.add(data["id"])
        for value in data.values():
            out |= _ids(value)
    elif isinstance(data, list):
        for value in data:
            out |= _ids(value)
    return frozenset(out)


@lru_cache(maxsize=1)
def samples() -> tuple[tuple[Sample, ...], tuple[Skipped, ...]]:
    table = hosted.readiness()
    loaded: list[Sample] = []
    skipped: list[Skipped] = []
    for root in SAMPLE_DIRS:
        for sample in sorted(root.rglob("*.py.sample")):
            name = sample.relative_to(DATA).with_suffix("").as_posix()
            text = sample.read_text(encoding="utf-8")
            module, error = _try_load(text)
            if module is None:
                skipped.append(Skipped(name, f"does not load: {error}"))
                continue
            sets = record_namespace(module)
            if not sets:
                skipped.append(Skipped(name, "no record set"))
                continue
            with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
                path = Path(tmp) / sample.parent.name / sample.with_suffix("").name
                path.parent.mkdir(parents=True)
                shutil.copyfile(sample, path)
                said, crashed = _dsllint_of(path, table)
            if crashed:
                skipped.append(Skipped(name, "dsllint crashes"))
                continue
            try:
                doc = encode_namespace(sets, village="Примерово", file=path.name, sha256="-", ids=Ids())
            except FormatError:                 # a sample whose records the export refuses (a wrong type)
                skipped.append(Skipped(name, "does not encode"))
                continue
            data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
            loaded.append(Sample(name, text, said, data, _ids(data)))
    return tuple(loaded), tuple(skipped)


def _walked(sample: Sample, code: str) -> Counter[Key]:
    found = on_json.lint_records(copy.deepcopy(sample.data), codes=[code])
    return Counter(_key(f.code, f.variant, f.params, f.token) for f in found)


# The names table is the linting workspace's (owner decision Д2), not always the writer's: a file read where a name is
# missing, or read as the other sex, is judged by other tables, each the tests' own less some names and with the sex of
# others turned over (`tests/thin_dictionary.py`). The codes that read a name are compared on every sample under each.
DICTIONARIES: dict[str, dict[str, frozenset[str]]] = {
    "without Лука, Фома, Анфиса": {"drop": frozenset({"Лука", "Фома", "Анфиса"})},
    "without Иван, Петр, Анна": {"drop": frozenset({"Иван", "Петр", "Анна"})},
    "Иван, Анна turned over": {"flip": frozenset({"Иван", "Анна"})},
    "Мария, Петр, Лука turned over": {"flip": frozenset({"Мария", "Петр", "Лука"})},
    "Фома, Анфиса turned over, Семен lost": {"flip": frozenset({"Фома", "Анфиса"}), "drop": frozenset({"Семен"})},
}

# The codes no sample fires in the tests' own workspace, because the constructor of a `Person` or of a record refuses
# what they find (an unknown name, a person of the other sex in a slot): they are held to a sample in a table that
# does not refuse it.
GUARDED: dict[str, str] = {
    "NAM001": "Person refuses a first name its table lacks",
    "NAM002": "Person refuses a patronymic its table lacks",
    "GND001": "Person and the records refuse a person of the other sex in a slot",
}


# A value the file holds in a name is the identifier to the check and the value to the walk (a documented class
# of difference): the one harvested sample whose status is held in a name, where a table that reads its man as a woman
# shows it. The exemption is the one finding the walk alone makes, (variant, token) of that code; every other finding of
# the sample is compared.
BOUND_NAMES: dict[tuple[str, str], tuple[tuple[str, str], str]] = {
    ("NAM004", "linter_samples/afa8910c631e/sample.py"): (("mismatch", "Петр"), "`status=MINE`, MINE = a status's words"),
}


def _names_codes() -> tuple[str, ...]:
    return tuple(c for c in on_json.SUPPORTED if "names" in hosted.readiness()[c].needs)


@pytest.fixture(scope="module")
def dictionaries(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return {name: thin_workspace(tmp_path_factory.mktemp("dictionary") / "ws", drop=kinds.get("drop", frozenset()),
                                 flip=kinds.get("flip", frozenset()))
            for name, kinds in DICTIONARIES.items()}


@cache
def dsllint_in(root: Path, name: str, text: str) -> Counter[Key] | None:
    """What `dsllint` says of a sample's text with `root` the workspace; None when a linter crashes."""
    with tempfile.TemporaryDirectory(prefix="verso-sample-") as tmp:
        parts = name.split("/")
        path = Path(tmp) / parts[-2] / parts[-1]
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        with workspace.use(root):
            said, crashed = _dsllint_of(path, hosted.readiness())
    return None if crashed else said


def _in_dictionary(root: Path, code: str) -> Iterator[tuple[Sample, Counter[Key], Counter[Key]]]:
    """(sample, what dsllint says, what the walk says) of each sample the walk can answer under `root`. One stay in
    `root` for all the samples: another workspace is another lexicon, and the base is some ten thousand names."""
    loaded = samples()[0]                       # read in the tests' own workspace, whatever the caller's turn
    with workspace.use(root):
        for sample in loaded:
            said = dsllint_in(root, sample.name, sample.text)
            if said is None:
                continue
            try:
                found = on_json.lint_records(copy.deepcopy(sample.data), codes=[code], workspace=root)
            except on_json.Unsupported:             # a file the table cannot replay: nothing to compare
                continue
            yield (sample, Counter({k: n for k, n in said.items() if k[0] == code}),
                   Counter(_key(f.code, f.variant, f.params, f.token) for f in found))


@pytest.mark.parametrize("code", _names_codes())
def test_samples_agree_in_another_dictionary(code: str, dictionaries: dict[str, Path]):
    differ: list[str] = []
    for name, root in dictionaries.items():
        for sample, source, walked in _in_dictionary(root, code):
            only_dsllint, only_json = source - walked, walked - source
            if exempt := BOUND_NAMES.get((code, sample.name)):
                only_json = Counter({k: n for k, n in only_json.items() if (k[2], k[3]) != exempt[0]})
            if only_dsllint or only_json:
                differ.append(f"[{name}] {sample.name}\n  only dsllint: {dict(only_dsllint)}"
                              f"\n  only JSON:    {dict(only_json)}")
    assert differ == [], "\n\n".join(differ)


# What each dictionary leaves uncompared, pinned: (samples a linter crashes on in `dsllint`, comparisons the walk refuses
# as `Unsupported` — the codes that replay the file, which a table that lacks a name or turns a sex over cannot build).
# A new skip fails the test below: look at it, then raise the number.
# Under the old table these were 192 / 411 / 325 / 322 / 118 with no crash. The base answers otherwise because a name
# dropped or turned over takes with it the patronymics only its own forms give: the old table held Фомин, Фомич, Иванов
# also in the rows of the name's variants (Хома, Иоанн), the base gives a variant forms of its own. So the walk refuses
# 17 comparisons more without Лука, Фома, Анфиса (seven samples of Фомин/Фомич), 23 more without Иван, Петр, Анна
# and 28 more with Иван, Анна turned over (Иванов, Иванова; one sample `census_parent_link` used to crash on, the
# CPL012 guard now answers it and the walk refuses it like its neighbours), 43 more with Фома, Анфиса turned over and
# Семен lost (Фомин, Фомич, Семенов). DVC001's sample adds one comparison each to the three that lose or turn over
# Иван or Анна (2026-11-24): its replay needs the names.
SKIPPED: dict[str, tuple[int, int]] = {
    "without Лука, Фома, Анфиса": (0, 209),
    "without Иван, Петр, Анна": (0, 435),
    "Иван, Анна turned over": (0, 354),
    "Мария, Петр, Лука turned over": (0, 323),
    "Фома, Анфиса turned over, Семен lost": (0, 161),
}


def test_the_skips_of_each_dictionary_are_pinned(dictionaries: dict[str, Path]):
    got: dict[str, tuple[int, int]] = {}
    loaded = samples()[0]                       # read in the tests' own workspace
    for name, root in dictionaries.items():
        with workspace.use(root):       # one stay in the dictionary: the base is some ten thousand names to build
            crashed = sum(dsllint_in(root, s.name, s.text) is None for s in loaded)
            refused = 0
            for code in _names_codes():
                for sample in loaded:
                    if dsllint_in(root, sample.name, sample.text) is None:
                        continue
                    try:
                        on_json.lint_records(copy.deepcopy(sample.data), codes=[code], workspace=root)
                    except on_json.Unsupported:
                        refused += 1
        got[name] = (crashed, refused)
    assert got == SKIPPED


@pytest.mark.parametrize("code", sorted(GUARDED))
def test_a_guarded_code_fires_in_another_dictionary(code: str, dictionaries: dict[str, Path]):
    """The code the constructors guard is judged by a table that lets the finding through: dsllint fires on a
    sample there, and the walk answers it alike (the test above)."""
    assert not any(_said(s, code) for s in samples()[0]), f"{code} fires in the tests' workspace: not guarded"
    firing = [f"[{name}] {sample.name}" for name, root in dictionaries.items()
              for sample, source, _ in _in_dictionary(root, code) if source]
    assert firing, f"{code}: no sample gives a finding in any dictionary"


def _said(sample: Sample, code: str) -> Counter[Key]:
    return Counter({k: n for k, n in sample.dsllint.items() if k[0] == code})


def test_samples_load():
    loaded, skipped = samples()
    by_why = Counter(s.why for s in skipped)
    print(f"\nsamples: {len(loaded)} loaded, {len(skipped)} skipped {dict(by_why)}")
    assert loaded, "no sample loaded: the facade's namespace is wrong"
    assert len(loaded) == LOADED, (
        f"{len(loaded)} samples load, {LOADED} did: a fall is a regression of the facade or a factory; "
        f"a rise (new samples) means raising LOADED")


@pytest.mark.parametrize("code", on_json.SUPPORTED)
def test_samples_agree(code: str):
    differ: list[str] = []
    for sample in samples()[0]:
        source, walked = _said(sample, code), _walked(sample, code)
        if source != walked:
            differ.append(f"{sample.name}\n{sample.text}\n  only dsllint: {dict(source - walked)}"
                          f"\n  only JSON:    {dict(walked - source)}")
    assert differ == [], "\n\n".join(differ)


@pytest.mark.parametrize("code", [c for c in on_json.SUPPORTED if c not in GUARDED])
def test_every_supported_code_has_a_positive_sample(code: str):
    """A code the registry answers is judged by a sample `dsllint` fires on: the oracle of a rule
    nothing triggers proves nothing, and a rule alone firing is no judge (the codes a constructor guards are
    judged in another dictionary, see `GUARDED`)."""
    firing = [s.name for s in samples()[0] if _said(s, code)]
    assert firing, f"{code}: no sample gives a finding — invent one in tests/data/on_json_samples/"


def test_findings_address_records():
    """A finding's `record` is the id of a record or a book of its file."""
    wrong: list[str] = []
    for sample in samples()[0]:
        for found in on_json.lint_records(copy.deepcopy(sample.data), codes=on_json.SUPPORTED):
            if found.record not in sample.ids:
                wrong.append(f"{sample.name}: {found.code} -> {found.record}")
    assert wrong == []


def test_a_held_record_is_linted_alike():
    """`reviewed=False` holds a record off Geni, not out of the linters: both readers give the
    finding of a held grandson (an invented sample)."""
    held = next(s for s in samples()[0] if s.name.endswith("CPL002_grandson_held.py"))
    assert held.data["documents"][0]["pages"][0]["records"][0]["review"] == "held"
    assert sum(_said(held, "CPL002").values()) == 1 and sum(_walked(held, "CPL002").values()) == 1


@pytest.mark.parametrize("code", ["CRD001", "CRD002", "CRD004", "DRA002"])
def test_a_load_bearing_argument_is_redundant_to_neither_reader(code: str):
    """What the generator could not have derived is no repetition: a daughter's maiden name beside a current surname of
    her own, a surname whose source names the member itself or is listed after it and derives its own, a residence
    another relative of the death contradicts (an invented sample)."""
    sample = next(s for s in samples()[0] if s.name.endswith("CRD_DRA_load_bearing.py"))
    assert (sum(_said(sample, code).values()), sum(_walked(sample, code).values())) == (0, 0)


def test_the_invented_samples_reach_every_variant_of_ulc001():
    """`dsllint` fires every variant of ULC001 on the invented samples (the oracle then holds the
    JSON walk to each)."""
    variants = {k[2] for s in samples()[0] if "on_json_samples" in s.name for k in s.dsllint if k[0] == "ULC001"}
    assert variants == {"parish_village", "default_residence", "residence", "origin", "destination"}
