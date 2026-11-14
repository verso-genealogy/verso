"""The ratchet: the unreviewed records already on Geni, and never one more.

`reviewed=False` holds a record off Geni (`verso.ru.dsl.records.reviewed`). Records
uploaded while `page(reviewed=False)` did nothing around births, marriages and
deaths — before that flag was honoured for them — may stay, and only
those: each village lists them in `unreviewed_on_geni.tsv`, one line per record,
seeded once from terraform state (`verso.ru.cli.review_ratchet --seed`).

**A line is a fingerprint, not a name.** It hashes what the source writes for
the record: its call without `reviewed=`, every call around it (`page`, the
month, `book`, the record set) without the records it wraps or its own
`reviewed=`, and the file's module-level assignments (`DEFAULTS`, a priest) —
the stdlib AST of each, written as 3.14's `ast.dump` writes it on any Python
(`_dump`), so formatting and comments do not count and a changed
name, number, date, лист or default does. The library is not in it: a fix to
the translator is not a change to a record. A record keeps its line only while
it is unreviewed AND unchanged; edited, it is a new record and is held.

**The list only shrinks.** A line goes when its record is reviewed (Verso's
«Вычитано» strikes it in the same write; `--prune` catches a review made by
hand), never because its record changed: an unreviewed record that no longer
matches its line would leave Geni — its profiles gone from the tree, and the
next plan destroying them — so the check fails and says so, and the fix is to
review the record or revert the edit. `--base` fails a line the base commit did
not have.

**Or rebind it, deliberately.** A maintainer may correct a listed record without
reviewing it — a misreading found on the scan, the rest of the record still
unread. `--rebind FILE` repoints each `changed` line of the file at the held
record that IS it: the same call, number, sex and лист (`RecordPrint.label`),
one line to one record, refusing anything it cannot pair so. `--base` accepts
such a line in place of the one it replaces — the same label in the base
source and in this one, the old fingerprint gone from the file — so a rebind
never grows the list, and cannot carry a line over to another record.

Pure: source text and record objects in, findings out. The loaders call
`admit` (`verso.core.pipeline.load.discover_records`, the death-age loader); I/O
is the CLI's.

**The calls are the plugin's**: which calls are a record, what numbers one, its sex,
how its лист is labelled and the words a roll says to Verso alone are the DSL's `CallDialect`
(`plugins.dsl().calls`; the Russian books' is `verso.ru.dsl.calls.CALLS`); the review flag
and the лист's name are the core's (`FLAG`, `PAGE`: the records carry them too), and which record
sets hold records the ratchet reads are its kinds (`RecordKind.ratcheted`). What is on Geni —
the list's file and header, the mark — is the Geni target's (`verso.core.targets.geni.held`).
"""
from __future__ import annotations

import ast
import hashlib
import itertools
import os
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.core import plugins
from verso.core.targets.geni.held import HEADER, LIST_FILE, ON_GENI
from verso.core.messages import t


# The review flag and the лист are the core's conventions, not a dialect's: the records carry
# them under the same names (`unreviewed`; the records JSON's review states and page runs).
FLAG = "reviewed"      # out of every print; on a record, `reviewed is False` holds it
PAGE = "page"          # the лист: a wrapper's name and a record's keyword alike


@dataclass(frozen=True)
class RecordCall:
    """A call of the DSL that is a record."""
    record_type: str                 # the class of the record it builds (`Birth`)
    number: str = "record_num"       # the parameter its number goes by, given by keyword
    sexed: bool = False              # its second argument (or `gender=`) is the record's sex


@dataclass(frozen=True)
class CallDialect:
    """How a plugin's DSL writes its records, as the ratchet reads the source."""
    calls: Mapping[str, RecordCall]
    page_label: str = "p."          # the leaf's word in a label; the plugin writes its own (ru: «л.»)
    gender: str = "gender"
    sexes: Mapping[str, str] = field(default_factory=dict[str, str])   # a sex's constant → its letter in a label
    # A record set's words on how Verso reads it: the translator reads none, so no print holds them.
    reading_flags: frozenset[str] = frozenset()


def _dialect(calls: CallDialect | None) -> CallDialect:
    return calls if calls is not None else plugins.dsl().calls



class RatchetError(Exception):
    """A listed file whose record calls cannot be paired with its records."""


@dataclass(frozen=True)
class RecordPrint:
    func: str
    line: int
    fingerprint: str
    label: str            # «birth 12 ж, л. 341об» — matched only to rebind a line (`rebind`)


@dataclass(frozen=True)
class Entry:
    file: str             # relative to the village directory, posix
    fingerprint: str
    label: str


@dataclass(frozen=True)
class Finding:
    kind: str             # changed / missing / stale / gone / added
    entry: Entry
    note: str = ""

    @property
    def prunable(self) -> bool:
        """`--prune` may take the line away: its record is reviewed (stale), or
        is gone and nothing unreviewed stands in its file that could be it."""
        return self.kind in ("stale", "gone")


# ---------------------------------------------------------------- fingerprints

def _name(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else None


def _dump(node: object) -> str:
    """`node` as 3.14's `ast.dump(node)` writes it, on any Python — the villages' lists hold
    prints taken so. 3.15's `dump` leaves `ctx=Load()` out; this writes every field the node
    has but a `None` or an empty list (a constant's `None` is written). A field a later Python
    adds is written too: the pinned prints of the tests (`test_a_print_is_the_same_on_every_python`)
    are what catch one."""
    if isinstance(node, ast.AST):
        cls = type(node)
        fields = []
        for name in node._fields:
            try:
                value = getattr(node, name)
            except AttributeError:
                continue
            if value is None and getattr(cls, name, ...) is None:
                continue
            if (value is None or value == []) and not isinstance(node, ast.Constant | ast.MatchSingleton):
                continue
            fields.append(f"{name}={_dump(value)}")
        return f"{cls.__name__}({', '.join(fields)})"
    if isinstance(node, list):
        return f"[{', '.join(_dump(item) for item in node)}]"
    return repr(node)


#: A record call and the calls around it, outermost first.
_Found = tuple[ast.Call, tuple[ast.Call, ...]]


def _walk(tree: ast.AST, dialect: CallDialect) -> tuple[list[_Found], set[int]]:
    """One walk of `tree`: every record call in source order with the calls around it, and the ids of every
    node that is a record call or holds one — what `ast.walk` would find below each node, asked once rather
    than once a wrapper and a record."""
    calls = dialect.calls
    found: list[_Found] = []
    held: set[int] = set()
    stack: list[ast.Call] = []

    def visit(node: ast.AST) -> bool:
        is_call = isinstance(node, ast.Call)
        holds = is_call and _name(node) in calls
        if holds:
            found.append((node, tuple(stack)))
        if is_call:
            stack.append(node)
        for child in ast.iter_child_nodes(node):
            if visit(child):
                holds = True
        if is_call:
            stack.pop()
        if holds:
            held.add(id(node))
        return holds

    visit(tree)
    return found, held


def _without_flag(call: ast.Call) -> ast.Call:
    return ast.Call(func=call.func, args=call.args,
                    keywords=[k for k in call.keywords if k.arg != FLAG])


def _as_context(call: ast.Call, dialect: CallDialect, held: set[int]) -> ast.Call:
    """A call around a record, as context: its own arguments, not the records
    it wraps (`held`: the ids `_walk` gives), not its `reviewed=` — releasing
    a лист changes no record — and not how Verso is to read it (`reading_flags`)."""
    return ast.Call(func=call.func,
                    args=[a for a in call.args if id(a) not in held],
                    keywords=[k for k in call.keywords
                              if k.arg != FLAG and k.arg not in dialect.reading_flags
                              and id(k.value) not in held])


def _literal(node: ast.AST | None) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _label(call: ast.Call, around: Sequence[ast.Call], dialect: CallDialect) -> str:
    func = _name(call) or "?"
    spec = dialect.calls[func]
    num = _literal(call.args[0]) if call.args else _literal(_kw(call, spec.number))
    gender = None
    if spec.sexed:
        gender = _literal(call.args[1]) if len(call.args) > 1 else _literal(_kw(call, dialect.gender))
    page = _literal(_kw(call, PAGE))
    for outer in reversed(around):
        if page is None and _name(outer) == PAGE and outer.args:
            page = _literal(outer.args[0])
    parts = [func]
    if num is not None:
        parts.append(str(num))
    if isinstance(gender, str) and gender in dialect.sexes:
        parts.append(dialect.sexes[gender])
    text = " ".join(parts)
    return f"{text}, {dialect.page_label} {page}" if page is not None else text


def record_prints(source: str, calls: CallDialect | None = None) -> list[RecordPrint]:
    """Every record call of a DSL file, in source order, with its fingerprint — read in
    `calls`, else in the workspace's DSL's dialect."""
    dialect = _dialect(calls)
    tree = ast.parse(source)
    found, held = _walk(tree, dialect)
    constants = [_dump(stmt) for stmt in tree.body
                 if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and id(stmt) not in held]
    contexts: dict[int, str] = {}  # a wrapper's context, the same for every record under it
    out = []
    for call, around in found:
        for c in around:
            if id(c) not in contexts:
                contexts[id(c)] = _dump(_as_context(c, dialect, held))
        parts = [*constants, *(contexts[id(c)] for c in around), _dump(_without_flag(call))]
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
        out.append(RecordPrint(_name(call) or "?", call.lineno, digest, _label(call, around, dialect)))
    return out


# ---------------------------------------------------------------- records

def _ratcheted() -> list[plugins.RecordKind]:
    return [kind for kind in plugins.dsl().kinds if kind.ratcheted]


def runtime_sets(namespace: Mapping[str, object]) -> list[Any]:
    """The record sets of a loaded DSL module (`vars(module)`) whose records
    `runtime_records` reads — the DSL's kinds the ratchet reads (`ratcheted`) —, in the
    module's order — a set bound to two names once (`record_sets`)."""
    from verso.core.records.sets import record_sets

    return list(record_sets(namespace, tuple(kind.set_type for kind in _ratcheted())).values())


def runtime_records(namespace: Mapping[str, object]) -> list[Any]:
    """Every record a loaded DSL module builds (`vars(module)`), in the order
    its record sets hold them — which is source order. Verso's grey defaults
    rest on the same alignment (`tests/test_review_source.py` pins it across
    the corpus)."""
    kinds = _ratcheted()
    out: list[Any] = []
    for value in runtime_sets(namespace):
        kind = next(k for k in kinds if isinstance(value, k.set_type))
        out.extend(getattr(value, kind.records))
    return out


def pair(source: str, module: Any, where: str = "", calls: CallDialect | None = None
         ) -> list[tuple[Any, RecordPrint]]:
    """Each record of a loaded module beside the print of the call that made
    it. Refuses rather than guesses: a file that builds records some other way
    than one call each cannot be held to its list line by line."""
    dialect = _dialect(calls)
    prints = record_prints(source, dialect)
    records = runtime_records(vars(module))
    if len(prints) != len(records):
        raise RatchetError(f"{where}: {len(prints)} record calls, {len(records)} records built — "
                           "the file cannot be paired with its ratchet lines")
    for record, p in zip(records, prints, strict=True):
        if type(record).__name__ != dialect.calls[p.func].record_type:
            raise RatchetError(f"{where}:{p.line}: {p.func}() paired with a {type(record).__name__}")
    return list(zip(records, prints, strict=True))


def unreviewed(record: Any) -> bool:
    """The record set has resolved the flag, so only an explicit False is it."""
    return getattr(record, FLAG, None) is False


def admit(pairs: Iterable[tuple[Any, RecordPrint]], fingerprints: Iterable[str]) -> int:
    """Mark `on_geni` on the unreviewed records the list names, one record per
    line; return how many. A record already reviewed needs no line."""
    left = Counter(fingerprints)
    n = 0
    for record, p in pairs:
        if unreviewed(record) and left[p.fingerprint] > 0:
            left[p.fingerprint] -= 1
            setattr(record, ON_GENI, True)
            n += 1
    return n


# ---------------------------------------------------------------- the list

def read_list(path: Path) -> list[Entry]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        file, fingerprint, label = (raw.split("\t") + ["", ""])[:3]
        out.append(Entry(file, fingerprint, label))
    return out


def read_header(path: Path) -> str | None:
    """The leading `#` lines of a list as written, line breaks kept; `None` for no file.
    A writer of the list passes it to `format_list`, so a list keeps the header it has."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(itertools.takewhile(lambda line: line.startswith("#"), lines))


def format_list(entries: Iterable[Entry], header: str | None = None) -> str:
    """The list's text: `header` (the file's own, `read_header`), else the core's."""
    return (HEADER if header is None else header) + "".join(f"{e.file}\t{e.fingerprint}\t{e.label}\n" for e in entries)


def listed(village_dir: Path, rel: str) -> list[str]:
    """The fingerprints the village's list holds for the DSL file `rel`
    («1900/manilovka_births_1900.py»), in the list's order."""
    return [e.fingerprint for e in read_list(village_dir / LIST_FILE) if e.file == rel]


def strike(village_dir: Path, rel: str, fingerprint: str) -> None:
    """One line of `rel` off the village's list — its record is reviewed now —
    written in place through a temporary file."""
    path = village_dir / LIST_FILE
    kept = drop(read_list(path), {(rel, fingerprint): 1})
    tmp = path.with_name(path.name + ".review-tmp")
    tmp.write_bytes(format_list(kept, read_header(path)).encode("utf-8"))
    os.replace(tmp, path)


def by_file(entries: Iterable[Entry]) -> dict[str, list[Entry]]:
    out: dict[str, list[Entry]] = {}
    for e in entries:
        out.setdefault(e.file, []).append(e)
    return out


# ---------------------------------------------------------------- the check

def _sort(entries: Sequence[Entry], records: Sequence[tuple[bool, RecordPrint]]
          ) -> tuple[list[Entry], list[Entry], list[RecordPrint]]:
    """One file's lines sorted out against its records: the lines whose record
    is reviewed (stale), the lines no record matches, and the unreviewed
    records no line took (held) — in source order."""
    open_ = Counter(p.fingerprint for u, p in records if u)
    done = Counter(p.fingerprint for u, p in records if not u)
    stale: list[Entry] = []
    unmatched: list[Entry] = []
    for e in entries:
        if open_[e.fingerprint] > 0:
            open_[e.fingerprint] -= 1
        elif done[e.fingerprint] > 0:
            done[e.fingerprint] -= 1
            stale.append(e)
        else:
            unmatched.append(e)
    held = []
    for u, p in records:
        if u and open_[p.fingerprint] > 0:
            open_[p.fingerprint] -= 1
            held.append(p)
    return stale, unmatched, held


def check_file(entries: Sequence[Entry], records: Sequence[tuple[bool, RecordPrint]]) -> list[Finding]:
    """The findings for one file's lines, given each record's (unreviewed,
    print). A line its unreviewed record still matches is silent."""
    stale, unmatched, held = _sort(entries, records)
    out = [Finding("stale", e, str(t("ratchet.stale"))) for e in stale]
    # The held records are the suspects when a line lost its record.
    for e in unmatched:
        if held:
            suspects = ", ".join(str(t("ratchet.suspect", label=p.label, line=p.line)) for p in held)
            out.append(Finding("changed", e, str(t("ratchet.changed", suspects=suspects))))
        else:
            out.append(Finding("gone", e, str(t("ratchet.gone"))))
    return out


def rebind(entries: Sequence[Entry], records: Sequence[tuple[bool, RecordPrint]]
           ) -> tuple[list[Entry], list[Finding]]:
    """One file's lines with each `changed` line repointed at the held record
    that is it, and the lines it would not repoint.

    A line goes to a held record with its own label — the call, number, sex and
    лист — and a label takes its lines and its held records in source order,
    one to one; a label whose two counts differ is refused whole, since which
    line is which record is then a guess. A line whose record changed its
    number or лист has no such record, and is refused too: that edit is a
    review's to make."""
    _, unmatched, held = _sort(entries, records)
    lines: dict[str, list[Entry]] = {}
    for e in unmatched:
        lines.setdefault(e.label, []).append(e)
    prints: dict[str, list[RecordPrint]] = {}
    for p in held:
        prints.setdefault(p.label, []).append(p)
    moved: dict[int, RecordPrint] = {}
    refused: list[Finding] = []
    for label, es in lines.items():
        ps = prints.get(label, [])
        if len(ps) != len(es):
            note = str(t("ratchet.no_label") if not ps else t("ratchet.counts_differ", lines=len(es), records=len(ps)))
            refused.extend(Finding("changed", e, note) for e in es)
            continue
        for e, p in zip(es, ps, strict=True):
            moved[id(e)] = p
    out = [Entry(e.file, moved[id(e)].fingerprint, moved[id(e)].label) if id(e) in moved else e
           for e in entries]
    return out, refused


def rebound(added_: Iterable[Entry], removed: Iterable[Entry],
            label_now: Mapping[tuple[str, str], str],
            label_base: Mapping[tuple[str, str], str]) -> list[Entry]:
    """The added lines that only repoint a removed line of the same file at the
    same record: one removed line each, whose (file, fingerprint) the base
    source labels as the current source labels the added one. `label_base`
    holds a removed line only while its fingerprint is gone from the current
    file — a record reviewed without an edit keeps its print, and its line is
    nobody's to take."""
    pool = Counter((e.file, label_base[(e.file, e.fingerprint)]) for e in removed
                   if (e.file, e.fingerprint) in label_base)
    out = []
    for e in added_:
        key = (e.file, label_now.get((e.file, e.fingerprint), ""))
        if key[1] and pool[key] > 0:
            pool[key] -= 1
            out.append(e)
    return out


def added(base: Iterable[Entry], now: Iterable[Entry]) -> list[Entry]:
    """The lines `now` has that `base` did not — by fingerprint, so a file
    renamed with `git mv` keeps its lines."""
    left = Counter(e.fingerprint for e in base)
    out = []
    for e in now:
        if left[e.fingerprint] > 0:
            left[e.fingerprint] -= 1
        else:
            out.append(e)
    return out


def drop(entries: Iterable[Entry], gone: Mapping[tuple[str, str], int]) -> list[Entry]:
    """`entries` without the (file, fingerprint) lines named in `gone`, each
    as many times as counted."""
    left = Counter(gone)
    out = []
    for e in entries:
        key = (e.file, e.fingerprint)
        if left[key] > 0:
            left[key] -= 1
        else:
            out.append(e)
    return out
