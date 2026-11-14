"""The `#` notes of a DSL file on the nodes of its records JSON (records v1.x, additive).

A note is `{"text": …, "anchor": {…}}`: its text Markdown, its anchor what it is about. The
plugin reads them from the file's text (`Plugin.notes`, `verso.core.plugins.SourceNotes`); the
export puts each on the node it is about, under `note`, a list in the file's order:

- `file` — on the file node;
- `record` — on the record's node; `range` — on the first record of the run, `anchor.end`
  naming its last, `anchor.arg` a wrapper's name; `argument`, `field` — on the record's node,
  `anchor.arg` naming what the JSON names: a person's persona slot as its id spells it
  (`godparent1`, `member3`), else the key of the argument in the node's `written`
  (`birth.day`). The plugin names an argument as its DSL does (a factory parameter) or a person
  by its slot; the export translates the parameter through the plugin's vocabulary, and a
  note whose argument has no such name is the record's;
- `manual` — on the file node too, its anchor `{"to": "manual"}` alone: what nobody bound.

`record` and `end` are a record's place among the file's records, from nought, in the export's
order. The plugin counted them in the file's text, and the export does not take its word: a
file whose records the plugin could not count, whose count is not the export's, or whose record
written at some place carries another number than the export's record there, binds no note to
a record — each goes on the file as `manual` (`Placed.refused` says why). So does a note whose
record is not among the file's. A wrong binding is the one thing this must not make.

Like a record's `key`, `note` is a property of the stored node: `decode_file` and `replay_file`
do not read it (it is no part of the graph), the encoder never writes it — only the export from
a DSL file, which has the text — and a node rebuilt from objects does not carry it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from verso.core.messages import t
from verso.core.records import FormatError
from verso.core.records.fields import (
    CONTEXT_KEY, WRAPPER_KEY, carries_persons, role_of, ungroup, vocabulary, written_key)

if TYPE_CHECKING:
    from verso.core.plugins import SourceNotes

NOTE = "note"
#: What a note may be about. `manual`: bound to nothing — exported on the file, marked.
ANCHORS = ("file", "record", "argument", "field", "range", "manual")
_ON_A_RECORD = frozenset({"record", "argument", "field", "range"})
_ANCHOR_KEYS = ("to", "record", "end", "arg")

#: Why a file's ordinals were not trusted (`Placed.refused`).
UNCOUNTED = "uncounted"     # the plugin could not count the file's records
COUNT = "count"             # it counted another number of records than the export holds
NUMBER = "number"           # a record it counted carries another number than the export's there


@dataclass
class Placed:
    """What became of one file's notes."""
    bound: int = 0                  # on the node their anchor names
    manual: int = 0                 # on the file as `manual`: the plugin's, or the export's refusal
    refused: str | None = None      # why no note of the file went on a record, if none could
    out_of_range: int = 0           # notes made `manual` because their record is not the file's


def record_nodes(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The record nodes of a records file, in the export's order: each document's (an alias's
    none), page run by page run."""
    return [record for document in doc["documents"] if "pages" in document
            for run in document["pages"] for record in run["records"]]


def _refusal(found: SourceNotes, numbers: Sequence[str]) -> str | None:
    if found.numbers is None:
        return UNCOUNTED
    if len(found.numbers) != len(numbers):
        return COUNT
    for written, exported in zip(found.numbers, numbers, strict=True):
        if written is not None and str(written) != exported:
            return NUMBER
    return None


def _ordinal(value: object, count: int) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < count:
        return value
    return None


def _slot(persona: Mapping[str, Any]) -> str:
    """A persona's slot as its id spells it: the role and its number (`godparent1`, `child`)."""
    slot = persona.get("slot")
    return f"{persona['role']}{'' if slot is None else slot}"


def _json_arg(node: Mapping[str, Any], arg: str) -> str | None:
    """What the JSON of a record calls the argument a plugin named `arg` (a factory parameter, or
    already a persona slot): a persona's slot, else a key of the node's `written`; None for a
    name the node has none for."""
    slots = {_slot(p) for p in node.get("persons", ())}
    if arg in slots:
        return arg
    voc = vocabulary()
    cls = voc.by_code.get(str(node.get("kind")))
    if cls is None:
        return None
    if carries_persons(cls, arg):
        attr = voc.param_to_attr.get(cls, {}).get(arg, arg)
        try:
            role, number = role_of(attr)
        except AssertionError:      # not a slot's spelling
            return None
        slot = f"{role}{'' if number is None else number}"
        return slot if slot in slots else None
    written = node.get("written")
    if not isinstance(written, Mapping):
        return None
    key = written_key(cls, arg)
    try:
        keys = ungroup(cls, {k: v for k, v in written.items() if k not in (CONTEXT_KEY, WRAPPER_KEY)})  # type: ignore[union-attr]
    except FormatError:
        return None
    return key if key in keys else None


def place_notes(doc: dict[str, Any], found: SourceNotes, numbers: Sequence[str]) -> Placed:
    """Put `found`'s notes on the nodes of `doc`, the file's records JSON, in place. `numbers` are
    the numbers the export cites its records by (`verso.core.records.ids.entry_token`), one a
    record in its order: what the plugin's ordinals are held to."""
    records = record_nodes(doc)
    placed = Placed(refused=_refusal(found, numbers))
    for note in found.notes:
        anchor = note.get("anchor")
        anchor = anchor if isinstance(anchor, Mapping) else {}
        to = anchor.get("to")
        out: dict[str, object] = {k: anchor[k] for k in _ANCHOR_KEYS if anchor.get(k) is not None}
        target: dict[str, Any] = doc
        if to in _ON_A_RECORD and placed.refused is None:
            first = _ordinal(anchor.get("record"), len(records))
            if to == "range":
                last = _ordinal(anchor.get("end"), len(records))
                fits = first is not None and last is not None and last >= first
            else:
                fits = first is not None and anchor.get("end") is None
            if fits:
                assert first is not None
                target = records[first]
                if to in ("argument", "field"):
                    arg = anchor.get("arg")
                    named = _json_arg(target, arg) if isinstance(arg, str) else None
                    if named is None:
                        out = {"to": "record", "record": first}     # no JSON name for it: the record's
                    else:
                        out["arg"] = named
            else:
                placed.out_of_range += 1
                out = {"to": "manual"}
        elif to != "file":
            out = {"to": "manual"}
        if out["to"] == "manual":
            placed.manual += 1
        else:
            placed.bound += 1
        target.setdefault(NOTE, []).append({"text": str(note.get("text", "")), "anchor": out})
    return placed


def check_notes(node: Mapping[str, Any], path: str) -> None:
    """Refuse a node's `note` that is not a non-empty list of `{"text": str, "anchor": {"to": …}}`."""
    if NOTE not in node:
        return
    notes = node[NOTE]
    ok = isinstance(notes, list) and bool(notes) and all(
        isinstance(n, Mapping) and isinstance(n.get("text"), str) and isinstance(n.get("anchor"), Mapping)
        and n["anchor"].get("to") in ANCHORS for n in notes)  # type: ignore[union-attr]
    if not ok:
        raise FormatError(t("records.decode.bad_note", path=path))
