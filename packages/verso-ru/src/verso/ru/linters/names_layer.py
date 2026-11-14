"""What `verso names add` and `verso names remove` do to a writable layer, apart from printing it — as `names_csv` is for the old table.

A layer is written one row to a key and no row has a place: `FilesLayer.put` and `remove` keep its files sorted. What is
decided here is whether a row may be written — the layer's linter (`verso.ru.linters.checks.lexicon`) reads the new
rows over the layers under them, a hard finding refuses — and what a removal is: the layer's own row deleted, or, for a
name only a lower layer (the base) holds, a removal row (`-` in bases) that takes it out of the stack.

Only a workspace of schema 6 has layers (`verso.ru.naming.layers`); the old `names.csv` is `verso.ru.naming.names_table`'s.
"""
from __future__ import annotations

import dataclasses
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.linters.checks.lexicon import Finding, lint_layer
from verso.ru.messages import t
from verso.ru.naming import layers
from verso.ru.naming.layer_files import NO_FORM, FilesLayer, Table
from verso.ru.naming.lexicon import ABSENT, FormsEntry, Layer, NameEntry

#: The source a row written by hand carries unless one is given.
DEFAULT_SOURCE = "editor"

Key = tuple[Gender | None, str]


class EditError(Exception):
    """A request the layers cannot take: no writable layer, a layer that is none of the workspace's, a name no layer holds."""


@dataclass(frozen=True)
class Target:
    """The layer a row is written to, and the layers up to and including it, read (bottom to top)."""
    layer: FilesLayer
    below: tuple[Layer, ...]
    here: Layer


def layer_index(ws: workspace.Workspace, directory: Path) -> int:
    """The place in the sources (`layers.sources`) of the layer `directory` names among the `[names] layers` of `ws`."""
    config = ws.names_layers
    if config is None:
        raise EditError(str(t("names_edit.no_layers", config=ws.root / workspace.CONFIG)))
    held = [d.resolve() for d in config.layers]
    if directory.resolve() not in held:
        raise EditError(str(t("names_edit.not_a_layer", path=directory, config=ws.root / workspace.CONFIG)))
    return held.index(directory.resolve()) + (1 if config.base is not None else 0)


def target(ws: workspace.Workspace, directory: Path | None) -> Target:
    """The layer a row is written to: the workspace's `writable` one. `directory` (`--layer`) may name that one alone —
    the `writable` key is what protects the other layers, and a layer that is not writable is edited by changing
    `[names]` of verso.toml on purpose."""
    config = ws.names_layers
    if config is None:
        raise EditError(str(t("names_edit.no_layers", config=ws.root / workspace.CONFIG)))
    if config.writable is None:
        raise EditError(str(t("names_edit.no_writable", config=ws.root / workspace.CONFIG)))
    if directory is not None and directory.resolve() != config.writable.resolve():
        raise EditError(str(t("names_edit.not_writable", path=directory, writable=config.writable,
                              config=ws.root / workspace.CONFIG)))
    stack = layers.sources(ws)
    index = layer_index(ws, config.writable)
    source = stack[index]
    if not isinstance(source, FilesLayer):
        raise EditError(str(t("names_edit.old_format", layer=source.name)))
    layer = FilesLayer(source.directory, name=source.name, writable=True)
    return Target(layer, tuple(s.load() for s in stack[:index]), layer.load())


def summed_names(stack: Sequence[Layer]) -> dict[Key, NameEntry]:
    """The name entries of `stack` summed, a removal row taking its key out."""
    out: dict[Key, NameEntry] = {}
    for layer in stack:
        out.update(layer.names)
        for key, entry in layer.names.items():
            if entry.removes:
                del out[key]
    return out


def form_cell(value: str | None) -> str | None:
    """A forms option as the layer holds it: not given — the rule's (None); `-` — no such form ("")."""
    return None if value is None else "" if value == NO_FORM else value


def new_entries(at: Target, sex: Gender, name: str, base: str | None, forms: Mapping[str, str | None],
                source: str, *, replace: bool = False) -> list[NameEntry | FormsEntry]:
    """The entries `add` writes: the name's, unless forms are given for a name the layers hold already (and no base is
    said), and the forms'; a key the layer holds is `EditError`, unless `replace` — then its row is replaced whole."""
    entries: list[NameEntry | FormsEntry] = []
    known = (sex, name) in summed_names([*at.below, at.here])
    if base or not forms or not known:
        entries.append(NameEntry(sex, name, (base,) if base else (), None, source))
    if forms:
        genitive, modern_m, modern_f, old_m, old_f = (form_cell(forms.get(c)) for c in COLUMNS)
        entries.append(FormsEntry(sex, name, genitive, modern_m, modern_f, old_m, old_f, source))
    if not replace:
        for entry in entries:
            held = at.here.names if isinstance(entry, NameEntry) else at.here.forms
            if entry.key in held:
                raise EditError(str(t("names_edit.exists", name=name, sex=_cell(sex), layer=at.layer.name,
                                      table="names" if isinstance(entry, NameEntry) else "forms")))
    return entries


#: The forms options `add` takes, in the layer's columns' order.
COLUMNS = ("genitive", "patronymic_m", "patronymic_f", "old_patronymic_m", "old_patronymic_f")


def _cell(sex: Gender | None) -> str:
    return {Gender.MALE: "M", Gender.FEMALE: "F", None: ""}[sex]


def replaced(at: Target, entries: Sequence[NameEntry | FormsEntry]) -> list[NameEntry | FormsEntry]:
    """The entries of `entries` whose key the layer holds already: what a `replace` writes over."""
    return [e for e in entries if e.key in (at.here.names if isinstance(e, NameEntry) else at.here.forms)]


def findings_of(at: Target, entries: Sequence[NameEntry | FormsEntry], *, replace: bool = False) -> list[Finding]:
    """What the layer's linter says of `entries` written over the layers under them — only the new rows are read, so a
    layer of a thousand pins costs no more than one of none. With `replace` the rows they replace are not among the
    layers under them: the new row is compared with the layers below, not with the row it takes the place of."""
    here = at.here
    if replace:
        gone = {e.key for e in entries if isinstance(e, NameEntry)}
        gone_forms = {e.key for e in entries if isinstance(e, FormsEntry)}
        # The layer as it is but for the rows replaced: its `derives`, `derived` and the rest kept.
        here = dataclasses.replace(here, names={k: v for k, v in here.names.items() if k not in gone},
                                   forms={k: v for k, v in here.forms.items() if k not in gone_forms})
    with tempfile.TemporaryDirectory() as scratch:
        probe = FilesLayer(Path(scratch), name=at.layer.name, writable=True)
        for entry in entries:
            probe.put(entry)
        return lint_layer(FilesLayer(Path(scratch), name=at.layer.name, writable=False), below=[*at.below, here])


@dataclass(frozen=True)
class Removal:
    """What `remove` did, or would: the tables whose rows of the layer it deleted, whether it wrote a removal row, the
    layers below that still hold the key, and the names left with the removed name as a base nothing holds."""
    deleted: tuple[Table, ...]
    removal_row: bool
    still_held: bool
    dangling: tuple[str, ...]


def remove(at: Target, sex: Gender | None, name: str, *, write: bool) -> Removal:
    """The key (`sex`, `name`) taken out of the layer; `write=False` says what would be done. `EditError` when no layer
    of the stack holds it."""
    key: Key = (sex, name)
    deleted: list[Table] = []
    if key in at.here.names:
        deleted.append("names")
    if key in at.here.forms:
        deleted.append("forms")
    held_below = key in summed_names(at.below)
    if not deleted and not held_below:
        raise EditError(str(t("names_edit.no_such_name", name=name, sex=_cell(sex) or "—")))
    removal_row = not deleted
    names = {k: e for k, e in at.here.names.items() if k != key}
    if removal_row:
        names[key] = NameEntry(sex, name, (ABSENT,), None, DEFAULT_SOURCE)
    if write:
        for table in deleted:
            at.layer.remove(table, key)
        if removal_row:
            at.layer.put(names[key])
    after = Layer(at.here.name, names, at.here.forms, at.here.patronymics)
    return Removal(tuple(deleted), removal_row, held_below and not removal_row,
                   _dangling(summed_names([*at.below, after]), key))


def _dangling(names: Mapping[Key, NameEntry], gone: Key) -> tuple[str, ...]:
    """The names of the sum whose one base is `gone`'s name and no entry holds it any more."""
    sex, name = gone
    if (sex, name) in names or (None, name) in names:
        return ()
    return tuple(sorted({e.name for e in names.values() if e.bases == (name,) and e.sex == sex}))
