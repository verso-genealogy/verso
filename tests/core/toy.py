"""A plugin of one record kind, for the core's tests: what the core asks of a plugin, and
nothing of the Russian books'.

Its DSL: a book of notes (`notes(village, fund, inventory, case, year, *records)`), each
note numbered and naming one person (`note(number, who(name))`). Its files are
`<year>/*_notes_<year>.py`; its books go by year, then file name.
"""
from __future__ import annotations

from enum import StrEnum
from importlib.resources import files
from importlib.resources.abc import Traversable
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from verso.core.plugins import ContentProfile, Dsl, Plugin, RecordKind
from verso.core.ratchet import CallDialect, RecordCall
from verso.core.records.fields import ClassSpec, ListOf, TypeSpec, Vocabulary, parse_fields
from verso.core.records.ids import BookKey, Token
from verso.core.written import captures_written


class Sex(StrEnum):
    """The toy's own sex: the core knows none."""
    MALE = "m"
    FEMALE = "f"


class Who:
    def __init__(self, name: str, gender: Sex | None = None) -> None:
        self.name = name
        self.gender = gender


class Note:
    def __init__(self, number: int, who: Who, *, page: str | None = None, reviewed: bool | None = None) -> None:
        self.number = number
        self.who = who
        self.page = page
        self.reviewed = reviewed


class Notes:
    def __init__(self, village: str, fund: str, inventory: str, case: str, year: int, *records: Note,
                 reviewed: bool = True) -> None:
        self.village = village
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.year = year
        self.records = list(records)
        self.reviewed = reviewed


@captures_written
def who(name: str, gender: Sex | None = None) -> Who:
    return Who(name, gender)


@captures_written
def note(number: int, person: Who, *, page: str | None = None, reviewed: bool | None = None) -> Note:
    return Note(number, person, page=page, reviewed=reviewed)


@captures_written
def notes(village: str, fund: str, inventory: str, case: str, year: int, *records: Note,
          reviewed: bool = True) -> Notes:
    return Notes(village, fund, inventory, case, year, *records, reviewed=reviewed)


TOY_KIND = RecordKind("note", Notes, (Note,), "records")


def _order(path: Path, record_set: Any, village: Any) -> tuple[Any, ...]:  # noqa: ARG001 — Dsl.order's signature
    return (record_set.year, path.name)


# The call that is a record — `note(...)` — numbered by `number`, and no sex in its label.
TOY_CALLS = CallDialect(calls={"note": RecordCall("Note", number="number")}, sexes={}, reading_flags=frozenset())

# Its records JSON's vocabulary: every attribute of the three classes, in `vars()` order.
_TYPES: dict[str, TypeSpec] = {"Sex": Sex, "Notes": ListOf(Note)}


def _f(spec: str) -> tuple:  # type: ignore[type-arg]
    return parse_fields(spec, _TYPES)


TOY_VOCABULARY = Vocabulary(
    specs={s.cls: s for s in (
        ClassSpec(Who, "who", _f("name:str gender:Sex"), (who,)),
        ClassSpec(Note, "note", _f("number:intstr who:person page:str reviewed:bool"), (note,)),
        ClassSpec(Notes, "notes", _f("village:str fund:str inventory:str case:str year:int records:Notes "
                                     "reviewed:bool=True"), (notes,), "records"),
    )},
    value_classes=(), param_to_attr={Note: {"person": "who"}}, written_only={}, item_roles={},
    person=Who, scalars={}, schema_package="tests.core",
    # Records v1: a field renamed, and a group of two fields that do not stand side by side.
    json_names={Who: {"name": "full_name"}, Notes: {"fund": "shelfmark.fund", "case": "shelfmark.case"}})

class _ToyCitation:
    """Rule r1 for the toy: a note cited by its book's shelfmark and year, and its number."""

    def book_key(self, record_set: Any, record: Any | None) -> BookKey:  # noqa: ARG002 — Citation's signature
        return BookKey(record_set.village, f"{record_set.fund}-{record_set.inventory}-{record_set.case}", None,
                       record_set.year, "note")

    def entry_token(self, record: Any) -> Token:
        return Token("", str(record.number))

    def principals(self, record: Any) -> list[Any]:
        return [record.who]

    def person_label(self, person: Any) -> str:
        return person.name


TOY_CITE = _ToyCitation()

def _legacy_import(module: str, path: Path) -> str | None:
    return f"toy v0 — перепишите {path}" if module.split(".")[0] == "toy_v0" else None


def _toy_table(path: Path, table: Mapping[str, Any]) -> tuple[str, Any]:  # noqa: ARG001 — the hook's signature
    """The toy's own table of a village.toml, `[toy]`: read as written."""
    return ("toy", table.get("shelf"))


TOY_DSL = Dsl(kinds=(TOY_KIND,), globs=("*/*_notes_*.py",), order=_order, calls=TOY_CALLS,
              vocabulary=TOY_VOCABULARY, cite=TOY_CITE, legacy_import=_legacy_import)

def _ui() -> Traversable:
    return files("tests.core").joinpath("ui-hints.toml")


TOY = Plugin(name="toy", package="tests.core", commands={"toy-hello": "tests.core.hello"},
             dsl=lambda: TOY_DSL, transliterate=lambda: str.upper,
             content=lambda: ContentProfile(native="xx", latin="en-US"),
             village_tables={"toy": _toy_table}, place_attributes=("toy_id",), names_tables=("toy_names.csv",),
             ui=_ui)
