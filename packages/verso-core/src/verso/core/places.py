"""The corpus's places, read through the workspace.

A place is a key the DSL writes (`residence=`, a roll member's `origin=` and
`destination=`) with its body: the HCL fragment the translator emits as a
`location` block (`city`, `county`, `state`, `country`, `render_body`). Until 0.1.0
they were code, `geni/locations.py`; now they are the corpus's — `<corpus>/places.toml`,
a table a place, or `same_as` for another spelling of one — and every reader asks
`current()` at call time, never at import:

* the translator (`res_names._location`, `location_label`, the project rules);
* ULC001, which refuses a place the corpus does not hold;
* the plugins' readers of a place's attributes (ru's familio projection, a place's
  settlement UUID) and the timeline (its label);
* Verso, which adds a place (`add_place`, `add_spelling` — text in, text out, the
  result read back and refused if an old place moved) and then `reload()`s, so all
  of the above see it.

A workspace without a corpus holds no places: every place is then unknown, and the
translator emits no location block.
"""
from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from verso.core import plugins, workspace
from verso.core.workspace import WorkspaceError
from verso.core.i18n import Message
from verso.core.messages import t

PLACES_FILE = "places.toml"


FIELDS = ("city", "county", "state", "country")
_FIELD_RE = re.compile(r'\s*(city|county|state|country)\s*=\s*"(.*)"\s*$')


class PlacesError(ValueError):
    """A places file or an edit of it this code refuses; the message says why, in Russian."""


def parse_body(body: str) -> dict[str, str]:
    """The four fields of a body; a field the body lacks is ""."""
    fields: dict[str, str] = dict.fromkeys(FIELDS, "")
    for line in body.split("\n"):
        m = _FIELD_RE.match(line)
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def render_body(fields: Mapping[str, str]) -> str:
    """The HCL a place emits: a line a field, in FIELDS order, `=` aligned, continuation
    lines at 18 columns (the translator strips them; `terraform fmt` aligns the rest)."""
    lines = [f'{name:<7} = "{fields[name].strip()}"' for name in FIELDS if fields.get(name, "").strip()]
    return ("\n" + " " * 18).join(lines)


class Places:
    """Every place of a corpus: key → body, the plugins' attributes (attribute → key → value: ru's
    `familio`, a place's settlement UUID), key → its canonical key."""

    def __init__(self, bodies: dict[str, str] | None = None, attributes: dict[str, dict[str, str]] | None = None,
                 path: Path | None = None, canonicals: dict[str, str] | None = None) -> None:
        self.bodies: dict[str, str] = bodies if bodies is not None else {}
        self.attributes: dict[str, dict[str, str]] = attributes if attributes is not None else {}
        self.path = path
        # A spelling's place is its canonical key's (`same_as`); a key given none is its own.
        self.canonicals: dict[str, str] = canonicals if canonicals is not None else {k: k for k in self.bodies}
        self._body_to_key: dict[str, str] = {}
        self._index()

    def _index(self) -> None:
        self._body_to_key = {self.bodies[c]: c for c in dict.fromkeys(self.canonicals.values()) if self.bodies.get(c)}

    def key_for_body(self, body: str | None) -> str | None:
        """The key whose body is `body`; None for a blank body or one no place has."""
        if not body:
            return None
        return self._body_to_key.get(body)

    def refill(self, other: Places) -> None:
        """Take `other`'s places into this object: whoever holds `bodies` sees them."""
        self.bodies.clear()
        self.bodies.update(other.bodies)
        self.attributes.clear()
        self.attributes.update(other.attributes)
        self.path = other.path
        self.canonicals = other.canonicals
        self._index()


# A place's keys the core reads; the enabled plugins add their attributes (`_place_keys`).
_PLACE_KEYS = frozenset({*FIELDS, "same_as"})
def _unsafe_names() -> tuple[tuple[str, Message], ...]:
    """What a field cannot hold — the body is HCL, written between quotes as it stands — and its
    words (the catalog's, asked at work)."""
    return (('"', t("places.unsafe_quote")), ("\\", t("places.unsafe_backslash")),
            ("\n", t("places.unsafe_newline")), ("\r", t("places.unsafe_return")),
            ("${", t("places.unsafe_interpolation")), ("%{", t("places.unsafe_directive")))


def unsafe(value: str) -> list[str]:
    """What of `value` the HCL body cannot carry, in words; [] when nothing."""
    return [str(words) for needle, words in _unsafe_names() if needle in value]


def _unsafe_message(name: str, found: list[str]) -> Message:
    return t("places.unsafe", name=name, found=", ".join(found))


def _header(line: str) -> str | None:
    """The table a `["key"]` line opens; None for any other line."""
    stripped = line.strip()
    if not stripped.startswith("[") or stripped.startswith("[["):
        return None
    try:
        names = list(tomllib.loads(stripped + "\n"))
    except tomllib.TOMLDecodeError:
        return None
    return names[0] if len(names) == 1 else None


def _table_line(key: str) -> str:
    return f"[{json.dumps(key, ensure_ascii=False)}]"


def _canonical_of(data: Mapping[str, Any], key: str) -> str:
    """Where a chain of same_as from `key` ends (or stops, at a loop or a missing key)."""
    seen: set[str] = set()
    while key not in seen and isinstance(data.get(key), dict) and "same_as" in data[key]:
        seen.add(key)
        key = data[key]["same_as"]
    return key


def _attributes() -> tuple[str, ...]:
    """The enabled plugins' place attributes; none outside a workspace."""
    try:
        return plugins.place_attributes()
    except WorkspaceError:
        return ()


def parse(text: str, *, path: Path | None = None) -> Places:
    """Places written as TOML: a table a place — its fields (and the plugins' attributes of it),
    or `same_as = "<key>"` for another spelling of that place."""
    names = _attributes()
    allowed = _PLACE_KEYS | frozenset(names)
    where = f"{path}: " if path is not None else ""
    try:
        data: dict[str, Any] = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise PlacesError(t("places.not_toml", where=where, e=e)) from None
    bodies: dict[str, str] = {}
    attributes: dict[str, dict[str, str]] = {}
    canonicals: dict[str, str] = {}
    fields_of: dict[str, tuple[str, ...]] = {}
    for key, table in data.items():
        if not isinstance(table, dict):
            raise PlacesError(t("places.not_a_table", where=where, key=key))
        unknown = sorted(set(table) - allowed)  # pyright: ignore[reportUnknownArgumentType]
        if unknown:
            raise PlacesError(t("places.unknown_key", where=where, key=key, unknown=unknown[0]))
        for name, value in table.items():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(value, str):
                raise PlacesError(t("places.expected_string", where=where, key=key, name=name))
        if "same_as" in table:
            if set(table) != {"same_as"}:
                raise PlacesError(t("places.same_as_with_fields", where=where, key=key))
            continue
        fields = {name: table[name].strip() for name in FIELDS if table.get(name, "").strip()}
        if not fields:
            raise PlacesError(t("places.no_field", where=where, key=key))
        for name, value in fields.items():
            found = unsafe(value)
            if found:
                raise PlacesError(t("places.unsafe_at", where=where, key=key, problem=_unsafe_message(name, found)))
        bodies[key] = render_body(fields)
        canonicals[key] = key
        fields_of[key] = tuple(fields.get(name, "") for name in FIELDS)
        for name in names:
            if name in table:
                attributes.setdefault(name, {})[key] = table[name]
    seen: dict[tuple[str, ...], str] = {}
    for key, fields in fields_of.items():
        if fields in seen:
            raise PlacesError(t("places.same_fields", where=where, seen=seen[fields], key=key))
        seen[fields] = key
    ordered: dict[str, str] = {}
    for key, table in data.items():
        if "same_as" in table:
            target = table["same_as"]
            if target not in data:
                raise PlacesError(t("places.same_as_nowhere", where=where, key=key, target=target))
            if target not in fields_of:
                hint = _canonical_of(data, target)
                tail = t("places.same_as_hint", hint=hint) if hint in fields_of else ""
                raise PlacesError(t("places.same_as_a_spelling", where=where, key=key, target=target, tail=tail))
            canonicals[key] = target
            ordered[key] = bodies[target]
        else:
            ordered[key] = bodies[key]
    return Places(ordered, attributes, path, {k: canonicals[k] for k in ordered})


def verify(old: str, new: str, key: str, *, canonical: str | None = None,
           path: Path | None = None) -> Places:
    """`new` read back: every place of `old` keeps its body, its canonical and every attribute
    of it, and `key` is there, reading as `canonical` (itself, for a new place)."""
    before, after = parse(old, path=path), parse(new, path=path)
    names = set(before.attributes) | set(after.attributes)

    def kept(places: Places, k: str) -> tuple[str | None, ...]:
        return tuple(places.attributes.get(name, {}).get(k) for name in sorted(names))
    for k, body in before.bodies.items():
        if (after.bodies.get(k), after.canonicals.get(k), kept(after, k)) != \
                (body, before.canonicals[k], kept(before, k)):
            raise PlacesError(t("places.edit_moved", key=k))
    if key not in after.bodies:
        raise PlacesError(t("places.edit_lost", key=key))
    reads_as = after.canonicals[key]
    if reads_as != (canonical or key):
        raise PlacesError(t("places.edit_reads_as", key=key, reads_as=reads_as))
    return after


def _check_new(places: Places, key: str) -> None:
    if not key.strip() or key != key.strip():
        raise PlacesError(t("places.key_blank"))
    if key in places.bodies:
        raise PlacesError(t("places.key_taken", key=key))


def _comment(comment: str) -> list[str]:
    return [f"# {line}".rstrip() for line in comment.splitlines() if line.strip()]


def add_place(text: str, key: str, fields: Mapping[str, str], comment: str, *,
              path: Path | None = None) -> str:
    """`text` with a new place `key` at its end, under `comment`; `path` — the file
    `text` is, for a refusal to name."""
    places = parse(text, path=path)
    _check_new(places, key)
    wanted = {name: fields.get(name, "").strip() for name in FIELDS if fields.get(name, "").strip()}
    if not wanted:
        raise PlacesError(t("places.new_no_field"))
    for name, value in wanted.items():
        found = unsafe(value)
        if found:
            raise PlacesError(_unsafe_message(name, found))
    same = places.key_for_body(render_body(wanted))
    if same is not None:
        raise PlacesError(t("places.same_place", same=same))
    entry = [*_comment(comment), _table_line(key),
             *(f"{name} = {json.dumps(value, ensure_ascii=False)}" for name, value in wanted.items())]
    head = text.rstrip("\n") + "\n\n" if text.strip() else ""
    new = head + "\n".join(entry) + "\n"
    verify(text, new, key, path=path)
    return new


def add_spelling(text: str, key: str, of: str, comment: str, *, path: Path | None = None) -> str:
    """`text` with `key` as another spelling of the place `of` names, written just before
    that place's canonical table and the comment above it; `path` as for `add_place`."""
    places = parse(text, path=path)
    _check_new(places, key)
    if of not in places.bodies:
        raise PlacesError(t("places.no_place", of=of))
    canonical = places.canonicals[of]
    lines = text.split("\n")
    at = next((i for i, line in enumerate(lines) if _header(line) == canonical), None)
    if at is None:
        raise PlacesError(t("places.no_table", canonical=canonical))
    while at > 0 and lines[at - 1].lstrip().startswith("#"):
        at -= 1
    lines[at:at] = [*_comment(comment), _table_line(key), f"same_as = {json.dumps(canonical, ensure_ascii=False)}", ""]
    new = "\n".join(lines)
    verify(text, new, key, canonical=canonical, path=path)
    return new


def load(path: Path) -> Places:
    """The places of the TOML file at `path` (`parse`)."""
    resolved = Path(path).resolve()
    return parse(resolved.read_text(encoding="utf-8"), path=resolved)


def places_file() -> Path | None:
    """Where the workspace keeps its places — `<corpus>/places.toml`, written yet or not;
    None for a workspace without a corpus."""
    corpus = workspace.current().corpus_dir
    return corpus / PLACES_FILE if corpus is not None else None     # corpus_dir is resolved


# The places each workspace has read, with the stamp of the file they were read from:
# a changed file is read again on the next question (`current()`), as the estates are.
_current: dict[Path, tuple[tuple[int, int] | None, Places]] = {}


# Each workspace's places file, found once: the translator asks for a place per person.
_files: dict[Path, Path | None] = {}


def _located() -> tuple[Path | None, tuple[int, int] | None]:
    """The workspace's places file and its stamp (mtime, size); (None, None) without one."""
    ws = workspace.current()
    if ws.root not in _files:
        _files[ws.root] = places_file()
    path = _files[ws.root]
    if path is None:
        return None, None
    try:
        st = path.stat()
    except FileNotFoundError:
        old = path.with_name("places.py")
        if old.is_file():
            # A worktree of a branch older than places.toml, running this code: its places
            # would read as none, and every location block would go without a word.
            raise PlacesError(t("places.old_places_py", old=old, places=PLACES_FILE)) from None
        return None, None
    return path, (st.st_mtime_ns, st.st_size)


def current() -> Places:
    """The workspace's places: read once, and again whenever their file changes."""
    root = workspace.current().root
    path, stamp = _located()
    held = _current.get(root)
    if held is None:
        found = load(path) if path is not None else Places()
    elif held[0] != stamp:
        found = held[1]
        found.refill(load(path) if path is not None else Places())
    else:
        return held[1]
    _current[root] = (stamp, found)
    return found


def reload() -> Places:
    """Re-read the workspace's places into the object `current()` gave out."""
    root = workspace.current().root
    held = current()
    path, stamp = _located()
    held.refill(load(path) if path is not None else Places())
    _current[root] = (stamp, held)
    return held
