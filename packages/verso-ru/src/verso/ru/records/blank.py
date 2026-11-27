"""An empty metric book, revision list or confession list, built from the record set's own factory.

A book started on the review page has no DSL file: its records JSON is the source. `blank_book` is that file at its
birth — one document, no pages — made by the factory a DSL file would call (`birth_records` …), so the set holds every
value the factory derives and replays to the very object the factory builds. The set carries no `reviewed` flag: what is
typed into it is read as it is typed (decision Р7). `sha256` is empty — «no DSL source» (Р6) — and `file` is the path
the DSL file would have, `<year>/<stem>.py`.

A metric book has no part in its citation (`verso.ru.records.cite` takes a part from a roll's `archive_suffix` alone), so
`part` tells two books of one shelfmark apart in the path, not in the id. A roll (a revision list, a confession list)
is the other way round: its part is the `archive_suffix` the citation reads, so it is in the id too, and `part` is
refused. A roll's own fields (`ROLL_FIELDS`) mean nothing to a metric book and are refused there; the confession list is
a preset, the vocabulary `CONFESSION_LIST` carries on the same `census_records`.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.domain.record_defaults import RecordDefaults
from verso.ru.dsl.records.births import birth_records
from verso.ru.dsl.records.census import CONFESSION_LIST, census_records
from verso.ru.dsl.records.deaths import death_records
from verso.ru.dsl.records.marriages import marriage_records
from verso.ru.messages import t

Kind = Literal["births", "marriages", "deaths", "census"]

FACTORIES: dict[str, Callable[..., Any]] = {
    "births": birth_records, "marriages": marriage_records, "deaths": death_records, "census": census_records}

#: The fields only a roll reads (`BookSpec`), in the order a refusal names them.
ROLL_FIELDS = ("preset", "prev_revision_year", "female_previous_age", "district", "volost", "archive_suffix")

YEARS = (1700, 1930)


@dataclass(frozen=True)
class BookSpec:
    """What a new metric book is called by. `parish` is the village of the parish (the set's `village`), `locality` the
    project's settlement (the file's `village`); a user's default is the same word for both."""
    kind: Kind
    locality: str
    year: int
    archive: str
    fund: str
    inventory: str
    case: str
    part: str | None
    church: str
    parish: str
    defaults: Mapping[str, object] | None
    preset: Literal["confessions"] | None = None
    prev_revision_year: int | None = None
    female_previous_age: bool | None = None
    district: str | None = None
    volost: str | None = None
    archive_suffix: str | None = None


class BlankError(ValueError):
    """A spec no book can be made of. `key` is the message's catalog key and `params` its parameters, so a caller says it
    in its own language; `str(exc)` is the message in the library's. The second argument may still be a ready message
    (the old form), then `params` is empty."""

    def __init__(self, key: str, params: Mapping[str, object] | object = None, message: object = None) -> None:
        if isinstance(params, Mapping):
            self.params: dict[str, object] = dict(params)
            text: object = message if message is not None else f"{key}: {self.params}"
        else:  # the old form: `BlankError(key, message)`
            self.params = {}
            text = params if params is not None else message if message is not None else key
        super().__init__(str(text))
        self.key = key


def _bad_path_part(value: str) -> bool:
    return (value != value.strip() or any(not c.isprintable() or unicodedata.category(c) == "Cc" for c in value)
            or "/" in value or "\\" in value or ".." in value)


def _refuse_roll_field(field: str) -> BlankError:
    return BlankError("records.blank.roll_field", {"field": field}, t("records.blank.roll_field", field=field))


def _check_roll_fields(spec: BookSpec) -> None:
    if spec.kind != "census":
        for field in ROLL_FIELDS:
            if getattr(spec, field) is not None:
                raise _refuse_roll_field(field)
        return
    if spec.part is not None:
        raise _refuse_roll_field("part")
    if spec.preset not in (None, "confessions"):
        raise _refuse_roll_field("preset")
    if spec.preset == "confessions":
        for field in ("prev_revision_year", "female_previous_age"):
            if getattr(spec, field) is not None:
                raise _refuse_roll_field(field)


def _check(spec: BookSpec) -> None:
    if spec.kind not in FACTORIES:
        raise BlankError("records.blank.kind", {"kind": spec.kind}, t("records.blank.kind", kind=spec.kind))
    if not YEARS[0] <= spec.year <= YEARS[1]:
        raise BlankError("records.blank.year", {"year": spec.year}, t("records.blank.year", year=spec.year))
    if not all(x.strip() for x in (spec.fund, spec.inventory, spec.case)):
        raise BlankError("records.blank.shelfmark", {"fund": spec.fund, "inventory": spec.inventory, "case": spec.case},
                         t("records.blank.shelfmark", fund=spec.fund, inventory=spec.inventory, case=spec.case))
    if not spec.parish.strip():
        raise BlankError("records.blank.parish", {}, t("records.blank.parish"))
    _check_roll_fields(spec)
    for value in (spec.locality, spec.fund, spec.inventory, spec.case, spec.part or "", spec.parish,
                  spec.archive_suffix or ""):
        if _bad_path_part(value):
            raise BlankError("records.blank.path", {"value": value}, t("records.blank.path", value=value))
    if spec.locality in ("", ".", ".."):
        raise BlankError("records.blank.path", {"value": spec.locality}, t("records.blank.path", value=spec.locality))


def _kind_word(spec: BookSpec) -> str:
    return "confessions" if spec.preset == "confessions" else spec.kind


def _part(spec: BookSpec) -> str | None:
    return (spec.archive_suffix if spec.kind == "census" else spec.part) or None


def _stem(spec: BookSpec) -> str:
    part = _part(spec)
    return f"{_kind_word(spec)}_{spec.fund}-{spec.inventory}-{spec.case}" + (f"_{part}" if part else "")


def book_path(spec: BookSpec) -> str:
    """`<locality>/<year>/<stem>.json` — where the book lies in a folder of books (decision Р5)."""
    _check(spec)
    return f"{spec.locality}/{spec.year}/{_stem(spec)}.json"


def _variable(spec: BookSpec) -> str:
    part = _part(spec)
    parts = [_kind_word(spec), spec.fund, spec.inventory, spec.case] + ([part] if part else [])
    return re.sub(r"\W", "_", "_".join(parts))


def blank_book(spec: BookSpec) -> dict[str, Any]:
    """The records-v1 file of an empty book: one document, `pages: []`."""
    _check(spec)
    extra: dict[str, Any] = {}
    if spec.defaults is not None:
        try:
            extra["defaults"] = RecordDefaults(**spec.defaults)
        except (TypeError, ValueError) as error:
            raise BlankError("records.blank.defaults", {"error": str(error)},
                         t("records.blank.defaults", error=str(error))) from error
    if spec.kind == "census":
        # Only what is set: a set records which arguments were written, and a replay compares them.
        roll: dict[str, Any] = {field: getattr(spec, field) for field in ROLL_FIELDS[1:]
                                if getattr(spec, field) is not None}
        if spec.preset == "confessions":
            roll.update(CONFESSION_LIST)
        record_set = census_records(spec.archive, spec.fund, spec.inventory, spec.case, spec.parish, spec.year,
                                    **roll, **extra)
    else:
        record_set = FACTORIES[spec.kind](spec.archive, spec.fund, spec.inventory, spec.case, spec.parish,
                                          spec.church, spec.year, **extra)
    return encode_namespace({_variable(spec): record_set}, village=spec.locality,
                            file=f"{spec.year}/{_stem(spec)}.py", sha256="", ids=Ids())
