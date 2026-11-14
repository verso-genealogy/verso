"""What the Russian books read of the corpus's data files (out of the core, which
reads `[geni]` of a village.toml and nothing else):

* `<village>/village.toml` — the tables the plugin parses through the core's
  `village_tables` hook (`TABLES`): `[census]`, `[timeline]`, `[sheets]`, `[csv]`; `village()`
  gives them with the core's `[geni]` as one `RuVillage`;
* `<corpus>/timeline.toml` — the events every village's timeline draws
  (`timeline_events()`), from the workspace's `[corpus] dir`;
* `<corpus>/estates.toml` — the corpus's owners and parishes (`estates()`): one
  landlady under two surnames, the family she was born into, each landlord's
  village, the parishes RTV001/RTV002 check.

A file that is not there is no settings; one that says something this code does not know is
an error naming the file and the key (`CorpusDataError`).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from verso.core import corpus_data
from verso.core.corpus_data import (CorpusDataError, check_keys, corpus_file, read_toml, string, string_map,
                                    strings, table, wrong)
from verso.ru.messages import t

_EMPTY: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class Era:
    """A span of years with a label — a village's сословие era, or an event."""
    from_year: int
    to_year: int
    label: str
    detail: str = ""


# The keys of the plugin's tables of a village.toml, by table.
VILLAGE_KEYS: dict[str, frozenset[str]] = {
    "csv": frozenset({"skip"}),
    "census": frozenset({"order", "prev_revision"}),
    "census.order": frozenset({"year", "suffix"}),
    "timeline": frozenset({"split_note", "era"}),
    "timeline.era": frozenset({"from", "to", "label", "detail"}),
}

TIMELINE_FILE = "timeline.toml"
_TIMELINE_KEYS: dict[str, frozenset[str]] = {
    "": frozenset({"event"}),
    "event": frozenset({"from", "to", "label", "detail"}),
}


@dataclass(frozen=True)
class Census:
    """`[census]`: the legacy order of the rolls, and the village's exceptions to the revision chain."""
    order: tuple[tuple[int, str | None], ...] = ()
    prev_revision: Mapping[int, int | None] = field(default=MappingProxyType({}))


@dataclass(frozen=True)
class Timeline:
    """`[timeline]`: the village's eras and the note on lines left apart."""
    eras: tuple[Era, ...] = ()
    split_note: str | None = None


@dataclass(frozen=True)
class RuVillage:
    """A village's settings as the Russian books read them: the core's `[geni]` and the plugin's tables."""
    projects: tuple[str, ...] = ()                                  # [geni] projects
    project_rules: Mapping[str, str] = field(default=_EMPTY)        # [geni.project_rules]
    census_order: tuple[tuple[int, str | None], ...] = ()           # [census] order
    prev_revision: Mapping[int, int | None] = field(default=MappingProxyType({}))  # [census] prev_revision
    eras: tuple[Era, ...] = ()                                      # [[timeline.era]]
    split_note: str | None = None                                   # [timeline] split_note
    sheets: Mapping[str, Any] | None = None                         # [sheets], as written: its reader checks it
    csv_skip: tuple[str, ...] = ()                                  # [csv] skip: files writing no CSV


def _census_order(path: Path, value: Any) -> tuple[tuple[int, str | None], ...]:
    if not isinstance(value, list):
        raise wrong(path, "census.order", t("corpus_data.expected_list"))
    order: list[tuple[int, str | None]] = []
    for entry in value:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            raise wrong(path, "census.order", t("corpus_data.expected_order_tables"))
        check_keys(path, "census.order", entry, VILLAGE_KEYS)  # pyright: ignore[reportUnknownArgumentType]
        year, suffix = entry.get("year"), entry.get("suffix")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if not isinstance(year, int) or isinstance(year, bool):
            raise wrong(path, "census.order.year", t("corpus_data.expected_integer"))
        if suffix is not None and not isinstance(suffix, str):
            raise wrong(path, "census.order.suffix", t("corpus_data.expected_string"))
        order.append((year, suffix))
    return tuple(order)


def _prev_revision(path: Path, value: Any) -> Mapping[int, int | None]:
    """`{ 1815 = 1795, 1721 = false }` → {1815: 1795, 1721: None}: a year, or false for none."""
    if not isinstance(value, dict):
        raise wrong(path, "census.prev_revision", t("corpus_data.expected_prev_revision"))
    out: dict[int, int | None] = {}
    for key, year in value.items():  # pyright: ignore[reportUnknownVariableType]
        if not str(key).isdigit():  # pyright: ignore[reportUnknownArgumentType]
            raise wrong(path, f"census.prev_revision.{key}", t("corpus_data.expected_year"))
        if year is False:
            out[int(key)] = None  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(year, int) and not isinstance(year, bool):
            out[int(key)] = year  # pyright: ignore[reportUnknownArgumentType]
        else:
            raise wrong(path, f"census.prev_revision.{key}", t("corpus_data.expected_year_or_false"))
    return MappingProxyType(out)


def _spans(path: Path, name: str, value: Any, keys: Mapping[str, frozenset[str]]) -> tuple[Era, ...]:
    """`[[name]]` entries (`from`, `to`, `label`, `detail`) in their order."""
    if not isinstance(value, list):
        raise wrong(path, name, t("corpus_data.expected_entries", table=name))
    spans: list[Era] = []
    for entry in value:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            raise wrong(path, name, t("corpus_data.expected_entries", table=name))
        check_keys(path, name, entry, keys)  # pyright: ignore[reportUnknownArgumentType]
        for key in ("from", "to"):
            year = entry.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if not isinstance(year, int) or isinstance(year, bool):
                raise wrong(path, f"{name}.{key}", t("corpus_data.expected_integer"))
        for key in ("label", "detail"):
            text = entry.get(key, "" if key == "detail" else None)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if not isinstance(text, str):
                raise wrong(path, f"{name}.{key}", t("corpus_data.expected_string"))
        spans.append(Era(entry["from"], entry["to"], entry["label"], entry.get("detail", "")))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    return tuple(spans)


def _census(path: Path, census: Mapping[str, Any]) -> Census:
    check_keys(path, "census", census, VILLAGE_KEYS)
    return Census(_census_order(path, census.get("order", [])), _prev_revision(path, census.get("prev_revision", {})))


def _timeline(path: Path, timeline: Mapping[str, Any]) -> Timeline:
    check_keys(path, "timeline", timeline, VILLAGE_KEYS)
    note = timeline.get("split_note")
    if note is not None and not isinstance(note, str):
        raise wrong(path, "timeline.split_note", t("corpus_data.expected_string"))
    return Timeline(_spans(path, "timeline.era", timeline.get("era", []), VILLAGE_KEYS), note)


def _sheets(path: Path, sheets: Mapping[str, Any]) -> Mapping[str, Any]:  # noqa: ARG001 — the hook's signature
    return MappingProxyType(dict(sheets))


def _csv(path: Path, csv: Mapping[str, Any]) -> tuple[str, ...]:
    check_keys(path, "csv", csv, VILLAGE_KEYS)
    skip = strings(path, "csv.skip", csv.get("skip", []))
    for name in skip:
        if not (path.parent / name).is_file():
            raise CorpusDataError(t("corpus_data.csv_skip_missing", path=path, name=name))
    return skip


# The plugin's tables of a village.toml, for `Plugin.village_tables`: the core parses each
# through these, in this order, once it has read `[geni]`.
TABLES = MappingProxyType({"census": _census, "timeline": _timeline, "sheets": _sheets, "csv": _csv})


def village(village_dir: str | Path) -> RuVillage:
    """The settings of the village at `village_dir` (its `village.toml`); `RuVillage()` without one."""
    v = corpus_data.village(village_dir)
    census: Census = v.table("census") or Census()
    timeline: Timeline = v.table("timeline") or Timeline()
    return RuVillage(projects=v.projects, project_rules=v.project_rules, census_order=census.order,
                     prev_revision=census.prev_revision, eras=timeline.eras, split_note=timeline.split_note,
                     sheets=v.table("sheets"), csv_skip=v.table("csv") or ())


def timeline_events() -> tuple[Era, ...]:
    """The events the timelines draw (`<corpus>/timeline.toml`, `[[event]]`), in order; none without it."""
    path = corpus_file(TIMELINE_FILE)
    if path is None:
        return ()
    data = read_toml(path)
    check_keys(path, "", data, _TIMELINE_KEYS)
    return _spans(path, "event", data.get("event", []), _TIMELINE_KEYS)


ESTATES_FILE = "estates.toml"


@dataclass(frozen=True)
class Landlord:
    """A landlord's village(s) — None: never flagged — and his name in the genitive, as a status writes it."""
    villages: tuple[str, ...] | None
    token: str


@dataclass(frozen=True)
class StatePeasants:
    """RTV001: in books of `books`, the state peasants (ясачные, казённые) lived in `village`."""
    books: frozenset[str]
    village: str
    who: str


@dataclass(frozen=True)
class Side:
    """A village and how a message says «in it»."""
    village: str
    in_: str


@dataclass(frozen=True)
class OwnersAndState:
    """RTV002: in books of `parish`, the owners' village and the state village beside it."""
    parish: str
    owners: Side
    state: Side


@dataclass(frozen=True)
class Estates:
    """What the corpus knows of its owners and parishes (`<corpus>/estates.toml`)."""
    owner_aliases: Mapping[str, str] = field(default=_EMPTY)
    maiden_families: Mapping[str, str] = field(default=_EMPTY)
    landlords: Mapping[str, Landlord] = field(default=MappingProxyType({}))
    state_peasants: tuple[StatePeasants, ...] = ()
    owners_and_state: tuple[OwnersAndState, ...] = ()
    village_aliases: Mapping[str, str] = field(default=_EMPTY)


_ESTATES_KEYS: dict[str, frozenset[str]] = {
    "": frozenset({"owner_aliases", "maiden_families", "landlords", "state_peasants", "owners_and_state",
                   "village_aliases"}),
    "landlords": frozenset({"villages", "token"}),
    "state_peasants": frozenset({"books", "village", "who"}),
    "owners_and_state": frozenset({"parish", "owners", "state"}),
    "owners_and_state.side": frozenset({"village", "in"}),
}
# Read once per file and its stamp: estate_of asks for every status it reads.
_estates_read: dict[Path, tuple[int, Estates]] = {}


def _landlords(path: Path, value: Any) -> Mapping[str, Landlord]:
    if not isinstance(value, dict):
        raise wrong(path, "landlords", t("corpus_data.expected_table"))
    out: dict[str, Landlord] = {}
    for key, entry in value.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            raise wrong(path, f"landlords.{key}", t("corpus_data.expected_landlord"))
        unknown = sorted(set(entry) - _ESTATES_KEYS["landlords"])  # pyright: ignore[reportUnknownArgumentType]
        if unknown:
            raise CorpusDataError(t("corpus_data.unknown_landlord_key", path=path, key=key, unknown=unknown[0]))
        villages = entry.get("villages")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        out[str(key)] = Landlord(  # pyright: ignore[reportUnknownArgumentType]
            strings(path, f"landlords.{key}.villages", villages) if villages is not None else None,
            string(path, f"landlords.{key}.token", entry.get("token")))  # pyright: ignore[reportUnknownMemberType]
    return MappingProxyType(out)


def _entries(path: Path, table: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):  # pyright: ignore[reportUnknownVariableType]
        raise wrong(path, table, t("corpus_data.expected_entries", table=table))
    for entry in value:  # pyright: ignore[reportUnknownVariableType]
        check_keys(path, table, entry, _ESTATES_KEYS)  # pyright: ignore[reportUnknownArgumentType]
    return value  # pyright: ignore[reportUnknownVariableType]


def _side(path: Path, key: str, value: Any) -> Side:
    if not isinstance(value, dict):
        raise wrong(path, key, t("corpus_data.expected_side"))
    check_keys(path, "owners_and_state.side", value, _ESTATES_KEYS)  # pyright: ignore[reportUnknownArgumentType]
    return Side(string(path, f"{key}.village", value.get("village")),  # pyright: ignore[reportUnknownMemberType]
                string(path, f"{key}.in", value.get("in")))  # pyright: ignore[reportUnknownMemberType]


def _parse_estates(path: Path) -> Estates:
    data = read_toml(path)
    check_keys(path, "", data, _ESTATES_KEYS)
    return Estates(
        owner_aliases=string_map(path, "owner_aliases", table(path, data, "owner_aliases")),
        maiden_families=string_map(path, "maiden_families", table(path, data, "maiden_families")),
        landlords=_landlords(path, data.get("landlords", {})),
        state_peasants=tuple(
            StatePeasants(frozenset(strings(path, "state_peasants.books", e.get("books"))),
                          string(path, "state_peasants.village", e.get("village")),
                          string(path, "state_peasants.who", e.get("who")))
            for e in _entries(path, "state_peasants", data.get("state_peasants", []))),
        owners_and_state=tuple(
            OwnersAndState(string(path, "owners_and_state.parish", e.get("parish")),
                           _side(path, "owners_and_state.owners", e.get("owners")),
                           _side(path, "owners_and_state.state", e.get("state")))
            for e in _entries(path, "owners_and_state", data.get("owners_and_state", []))),
        village_aliases=string_map(path, "village_aliases", table(path, data, "village_aliases")),
    )


def estates() -> Estates:
    """The corpus's owners and parishes (`<corpus>/estates.toml`); `Estates()` without them."""
    path = corpus_file(ESTATES_FILE)
    if path is None:
        return Estates()
    stamp = path.stat().st_mtime_ns
    read = _estates_read.get(path)
    if read is None or read[0] != stamp:
        read = (stamp, _parse_estates(path))
        _estates_read[path] = read
    return read[1]
