"""What every rule of the linters on records JSON shares: the finding, the view of a file, the rule's type.

A rule is a function of a `FileView` that yields `Finding`s of its code (`RULES` of each family's
module); the registry (`verso.ru.linters.on_json`) runs them and sets each finding's level.
"""
from __future__ import annotations

import functools
from collections.abc import Callable, Collection, Generator, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, cast

from verso.core import workspace
from verso.core.i18n import Message
from verso.core.records import SCHEMA_ID, FormatError
from verso.core.records.decode import check_vocabulary
from verso.core.records.fields import CONTEXT_KEY, WRAPPER_KEY, attr_of, split_context_in, ungroup, vocabulary
from verso.core.records.replay import Position, replay_alone, replay_file
from verso.core.workspace import LexiconNotConfigured, WorkspaceError
from verso.ru import corpus_data
from verso.ru.domain import marital_status, statuses
from verso.ru.linters.checks.census_redundancy import ROLE_GENDER_BY_NAME
from verso.ru.linters.issue import Param, Text, neutral
from verso.ru.messages import t
from verso.ru.naming import get_gender_from_name, modernize_orthography

__all__ = [
    "ADOPTED", "FileView", "Finding", "NoReplay", "RecordView", "ReplayRefused", "Rule", "Unsupported", "as_int", "as_text",
    "check_input", "estates_present", "finding", "finding_of", "gender_from_name", "keeping_written", "member_gender",
    "member_name", "names_table_present", "only", "personas", "slot_of", "status_constant", "status_name",
    "status_name_or_none", "without_names",
]


ADOPTED = "приемн"  # i18n: content — the word of a member's comment that marks an adopted line


@dataclass(frozen=True)
class Finding:
    """A finding of the JSON walk: what `dsllint` says of the source, addressed by an id."""
    code: str
    variant: str
    record: str
    params: dict[str, Any] = field(default_factory=dict[str, Any])
    token: str | None = None
    level: str = "warn"


class NoReplay(Exception):
    """The file cannot be replayed because the workspace has no names table (the persons it builds are validated against
    it). `lint_records` answers a rule that needs the replay with what it found before (H7); any other
    `WorkspaceError` is not this."""


class Unsupported(ValueError):
    """A code, or a file, the JSON walk cannot answer.

    When `lint_records` could answer part of what was asked and the rest needs the file replayed, which it cannot be,
    the refusal carries what was answered: `findings` — those of every requested rule that reads no replay, leveled as
    a call that succeeded levels them — and `unanswered`, the sorted requested codes that went unanswered because
    they need the replay. Any other refusal carries neither."""

    def __init__(self, message: Message, *, findings: Collection[Finding] = (), unanswered: Collection[str] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.findings: list[Finding] = list(findings)
        self.unanswered: list[str] = sorted(unanswered)


class ReplayRefused(Unsupported):
    """The replay's refusal: the file has no wrapper context (an export before 0.1.16), or no factory can rebuild it.
    `lint_records` catches this and nothing broader, to answer the rules that read no replay."""


def finding(code: str, variant: str, record: str, token: str | None = None, **params: Param) -> Finding:
    """A finding of `code`; the registry gives it its level."""
    return Finding(code, variant, record, neutral(params), token)


def finding_of(message: Text, record: str) -> Finding:
    """The finding a check's own message builder (`says`, a `…said…` function) made, addressed by an id:
    its code, variant, params and token are the message's."""
    return Finding(message.code, message.variant, record, dict(message.params), message.token)


# What a node wrote (`FileView.written`), kept for the length of one lint call (`keeping_written`): every rule of the call
# asks it of the same nodes. Keyed by the node's id and the code it is read as, the node kept beside its answer so
# that its id names no other object while the call runs; nothing of it outlives the call.
_kept_written: ContextVar[dict[tuple[int, str], tuple[Mapping[str, Any], dict[str, Any]]] | None] = ContextVar(
    "kept_written", default=None)


@contextmanager
def keeping_written() -> Generator[None]:
    """Keep what each node wrote while the block runs — one lint call, whose input is not changed while it runs. A
    block inside another keeps the outer one's."""
    if _kept_written.get() is not None:
        yield
        return
    token = _kept_written.set({})
    try:
        yield
    finally:
        _kept_written.reset(token)


class FileView:
    """A records-v1 file node, read the ways the rules ask: its documents, its records, what a node
    wrote."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data = data
        self._replayed: dict[str, object] | None = None
        self._refusal: ReplayRefused | None = None
        self._objects: dict[str, object] | None = None
        # Whether some set of the file names a place the corpus knows (ULC001's gate): a view of less than the file
        # is told it (`lint_record`, `lint_header`); None is the file's own answer, asked of its documents.
        self.file_scope: bool | None = None

    def run_mates(self, run: Mapping[str, Any]) -> frozenset[bool]:  # noqa: ARG002 — the hook of RecordView
        """The `reviewed` of the unflagged records of a page run that the run's own records do not show: none for a
        file, which holds the whole run (RVR001)."""
        return frozenset()

    def documents(self) -> list[Mapping[str, Any]]:
        return list(self.data["documents"])

    def records(self, kinds: Collection[str] | None = None) -> Iterator[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        """Each record with its document, in file order; `kinds` keeps the documents of those kinds."""
        for doc in self.data["documents"]:
            if kinds is not None and doc.get("kind") not in kinds:
                continue
            for run in doc.get("pages", ()):
                for record in run["records"]:
                    yield doc, record

    @staticmethod
    def written(code_or_person: str, node: Mapping[str, Any]) -> dict[str, Any]:
        """What a node wrote, by its factory's parameter — v1 groups and renames keys (`arrival.place`
        is `origin`, `given.original` is `name_orig`). `code_or_person` is `"person"` or the node's
        class code (`"member"`)."""
        kept = _kept_written.get()
        if kept is not None and (found := kept.get((id(node), code_or_person))) is not None:
            return dict(found[1])
        voc = vocabulary()
        cls = voc.person if code_or_person == "person" else voc.by_code[code_or_person]
        call, _ = split_context_in(voc, cls, node.get("written", {}))      # a wrapper's value is no parameter
        params = voc.params_of_keys.get(cls, {})
        out = {params.get(k, k): v for k, v in call.items()}
        if kept is not None:
            kept[(id(node), code_or_person)] = (node, out)
        return dict(out)

    def require_context(self) -> None:
        """Refuse an export that keeps a wrapper's value (a section's month, a `page()`'s flag, a `book()`'s
        name) in `derived` where `written.context` now names it: a record whose `derived` holds an attribute of
        a wrapper that neither its `written` nor the marker mentions is from before 0.1.16. The codes that
        read what a record inherits ask the file to be exported again, rather than read the old shape as the
        new one (`Unsupported`, `on_json.no_context`)."""
        voc = vocabulary()
        for _, record in self.records():
            cls = voc.by_code.get(record["kind"])
            if cls is None or not (wanted := voc.context.get(cls, frozenset())):
                continue
            attrs = voc.json_attrs[cls]
            written = ungroup(cls, {k: v for k, v in record.get("written", {}).items()
                                    if k not in (CONTEXT_KEY, WRAPPER_KEY)})
            for key in ungroup(cls, record.get("derived", {})):
                if attrs.get(key) in wanted and key not in written:
                    raise ReplayRefused(t("on_json.no_context", record=record["id"]))

    def replayed(self) -> dict[str, object]:
        """The file's record sets rebuilt by the DSL's own factories from `written` alone
        (`verso.core.records.replay.replay_file`), by variable: what a constructor or a set derives (a status
        a book's defaults give, a running number) is derived again, and a wrapper's value is what
        `written.context` names. Built once per view. An export without that context, or a file no factory can
        rebuild, is `Unsupported`."""
        if self._refusal is not None:                  # a file that cannot be replayed is not replayed again per rule
            raise self._refusal
        if self._replayed is None:
            self._replayed = self._guarded(lambda: replay_file(self.data))
        return self._replayed

    def _guarded[R](self, build: Callable[[], R]) -> R:
        """`build()` after the context check, a refusal remembered: a file no factory can rebuild is `ReplayRefused`,
        a workspace without a names table `NoReplay`."""
        if self._refusal is not None:
            raise self._refusal
        try:
            self.require_context()
            return build()
        except ReplayRefused as error:
            self._refusal = error
            raise
        except FormatError as error:
            self._refusal = ReplayRefused(t("on_json.not_replayable", error=str(error)))
            raise self._refusal from error
        except WorkspaceError as error:
            if names_table_present():
                raise
            raise NoReplay from error

    def object_of(self, record: Mapping[str, Any]) -> Any:
        """The record `replayed()` built for a record node, found by the node's id — the id (rule r1) is unique
        in a file and survives the walk's order, where a position would shift with an aliased set (`alias_of`)
        that holds the very records of another."""
        if self._objects is None:
            voc = vocabulary()
            found: dict[str, object] = {}
            for doc in self.data["documents"]:
                if "alias_of" in doc:
                    continue
                built = self.replayed()[doc["variable"]]
                spec = voc.specs[type(built)]
                assert spec.records_attr is not None
                nodes = [r for run in doc.get("pages", ()) for r in run["records"]]
                for node, obj in zip(nodes, getattr(built, spec.records_attr), strict=True):
                    found[node["id"]] = obj
            self._objects = found
        return self._objects[record["id"]]

    def set_of(self, doc: Mapping[str, Any]) -> Any:
        """The record set `replayed()` built for a document node (an aliased one: the set it names)."""
        return self.replayed()[doc.get("alias_of") or doc["variable"]]


class RecordView(FileView):
    """One record of a file read as the file's rules read a file: a node of one set — its header, one page run holding
    this record — so a rule that walks the documents and their records sees this record and its set's header and
    nothing else. The objects a rule reads of it are built alone (`replay_alone`), with the record's `position`.

    `file_scope` is the one fact of the whole file ULC001 asks, `run_levels` what the rest of the record's page run
    shows RVR001 (`run_mates`)."""

    def __init__(self, node: Mapping[str, Any], *, header: Mapping[str, Any], page: str | None, position: Position,
                 file_scope: bool | None = None, run_levels: Collection[bool] | None = None) -> None:
        document = {**{k: v for k, v in header.items() if k != "pages"}, "pages": [{"page": page, "records": [node]}]}
        super().__init__({"schema": SCHEMA_ID, "documents": [document]})
        self.node, self.header, self.page, self.position = node, header, page, position
        self.file_scope = file_scope
        self.run_levels = frozenset(run_levels or ())
        self._alone: tuple[Any, Any] | None = None

    def run_mates(self, run: Mapping[str, Any]) -> frozenset[bool]:  # noqa: ARG002 — a record has one run
        return self.run_levels

    def alone(self) -> tuple[Any, Any]:
        """The record set around the record and the record, built alone (once)."""
        if self._alone is None:
            self._alone = self._guarded(lambda: replay_alone(
                self.node, header=self.header, page=self.page, position=self.position, context=False))
        return self._alone

    def replayed(self) -> dict[str, object]:
        document = self.data["documents"][0]
        return {document.get("variable", "set"): self.alone()[0]}

    def object_of(self, record: Mapping[str, Any]) -> Any:  # noqa: ARG002 — the one record of the view
        return self.alone()[1]

    def set_of(self, doc: Mapping[str, Any]) -> Any:  # noqa: ARG002 — the one set of the view
        return self.alone()[0]


def check_input(data: object) -> None:
    """Refuse what is not a records-v1 file node as `replay_file` refuses it — the same `FormatError`, before any rule
    reads it: a mapping of the schema `records-v1` with a list of documents (each a mapping), and a header vocabulary
    no newer than the plugin's."""
    if not isinstance(data, Mapping):
        raise FormatError(t("on_json.not_a_file", found=type(data).__name__))
    data = cast(Mapping[str, Any], data)
    if data.get("schema") != SCHEMA_ID:
        raise FormatError(t("on_json.other_schema", wanted=SCHEMA_ID, found=repr(data.get("schema"))))
    documents = data.get("documents")
    if not isinstance(documents, list) or not all(isinstance(doc, Mapping) for doc in cast(list[object], documents)):
        raise FormatError(t("on_json.no_documents", found=type(documents).__name__))
    check_vocabulary(data)


Rule = Callable[[FileView], Iterator[Finding]]


def only(code: str, found: Iterator[Finding]) -> Iterator[Finding]:
    """One code of a walk that makes several: the registry runs a rule per code it was asked for."""
    return (item for item in found if item.code == code)


def personas(record: Mapping[str, Any], role: str | None = None) -> list[Mapping[str, Any]]:
    """The personas of a record, in order; `role` keeps those of that role."""
    return [p for p in record["persons"] if role is None or p.get("role") == role]


def as_int(value: object) -> int | None:
    """The value if it is an integer that is no bool, else none: what a rule reads of a written number (the checks'
    `_int_literal`)."""
    return value if type(value) is int else None


def as_text(value: object) -> str | None:
    """The value if it is a string, else none: what a rule reads of a written value that may be any type."""
    return value if isinstance(value, str) else None


# --- the names table (H7): what a rule answers in a workspace that has none -----------------------------

def names_table_present() -> bool:
    """Whether the current workspace has a names lexicon — `names.csv` (schema ≤ 5), a base or a layer (schema 6): a
    rule that reads one answers as far as it can without it, and `lint_records` gives what it finds the level of a
    warning. A base no plugin ships is no workspace without names but a mistake in `[names]`: the `WorkspaceError`
    naming the bases there are."""
    try:
        ws = workspace.current()
        if ws.names_layers is not None:
            from verso.ru.naming.layers import base_of
            base = ws.names_layers.base
            if base is not None:
                base_of(ws, base)
            return base is not None or bool(ws.names_layers.layers)
        return ws.names_file("names.csv").is_file()
    except LexiconNotConfigured:
        return False


def estates_present() -> bool:
    """Whether the current workspace has the corpus's estates (`estates.toml`): a rule that reads them answers as far as
    it can without (no landlord, no owner's alias, no parish rule), and `lint_records` gives what it finds the level of
    a warning."""
    return corpus_data.corpus_file(corpus_data.ESTATES_FILE) is not None


def without_names[**P, R](lookup: Callable[P, R], absent: R) -> Callable[P, R]:
    """A lookup of the names table that answers `absent` where the workspace has no table, and is the lookup itself
    where it has one (a `WorkspaceError` of another kind — no workspace at all — still raises). One mechanism for
    every rule that reads a name: the finding that rests on a name no table can read is not made."""
    @functools.wraps(lookup)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return lookup(*args, **kwargs)
        except WorkspaceError:
            if names_table_present():
                raise
            return absent
    return wrapper


gender_from_name = without_names(get_gender_from_name, None)


def member_name(person: Mapping[str, Any]) -> str | None:
    """`census_redundancy._name_modern`: the modern first name WRITTEN (a keyword holding nothing is the keyword: it names
    nobody and does not fall back), else the old one modernized."""
    modern = as_text(person.get("name_modern_orth"))
    if modern is not None:
        return modern
    orig = as_text(person.get("name_orig"))
    return modernize_orthography(orig) if orig else None


def member_gender(person: Mapping[str, Any], role: str | None) -> str | None:
    """`census_redundancy._gender` of a roll member (what CSR001, CRD and RTV read): the gender written, else the role's, else
    the first name's (none without a names table). The one reading of the three readers of a member's sex."""
    written = as_text(person.get("gender"))
    if written:
        return written.upper()
    if role in ROLE_GENDER_BY_NAME:
        return ROLE_GENDER_BY_NAME[role].name
    name = member_name(person)
    inferred = gender_from_name(name) if name else None
    return inferred.name if inferred is not None else None


def slot_of(record: Mapping[str, Any], persona: Mapping[str, Any]) -> str:
    """The keyword a person stands at in its record: `god_parent2`, `witness1`, `father`."""
    voc = vocabulary()
    return attr_of(voc.specs[voc.by_code[record["kind"]]], persona["role"], persona.get("slot"))


# --- a status constant, from what the JSON holds of it -----------------------------------------------------

@statuses.kept
def _constants() -> dict[tuple[str, str | None], tuple[str, ...]]:
    """{(text, gender): the names of the constants that spell it}, each in alphabetical order. A catalog `Status`
    keeps its gender (`male`, `female`); a marital status is plain text and stands under none."""
    found: dict[tuple[str, str | None], list[str]] = {}
    for name, value in sorted(statuses.catalog().items()):
        gender = None if value.gender is None else value.gender.name.lower()
        found.setdefault((str(value), gender), []).append(name)
    for name in sorted(vars(marital_status)):
        if not name.startswith("_") and isinstance(text := getattr(marital_status, name), str) and name.isupper() \
                and name != "MARITAL_STATUSES":
            found.setdefault((text, None), []).append(name)
    return {key: tuple(names) for key, names in found.items()}



def status_constant(text: str, gender: str | None) -> tuple[str, ...]:
    """The constants of the workspace's catalogs (`statuses`, the corpus's own, `marital_status`) that spell
    `text` for `gender` (`male`, `female`, none), in alphabetical order — the names a source could have written
    where the JSON holds `{text, gender}`. Empty for a constant the file defines itself."""
    return _constants().get((text, gender), ())


def status_name_or_none(text: str, gender: str | None) -> str | None:
    """The name the checks give a status of the JSON: of the constants that spell it, the one that sorts LAST
    (`known_statuses` and `status_words.tables` are built over sorted names and the later overwrites), so
    `STATE_PEASANT_MALE` of `GOSUDARSTVENNYJ_PEASANT_MALE`; none where no constant spells it. The one place the
    choice is made."""
    names = status_constant(text, gender)
    return names[-1] if names else None


def status_name(text: str, gender: str | None) -> str:
    """`status_name_or_none`, or the text itself where no constant spells it (a constant the file defines)."""
    return status_name_or_none(text, gender) or text
