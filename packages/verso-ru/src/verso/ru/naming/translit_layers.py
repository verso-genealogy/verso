"""The transliteration's rules: a word a profile is to spell whole, as rows of the names layers.

A rule is (profile, word) → Latin: `Чубарев` under `ru-v1` is `Tchoubarev`. Rules live where the names do — a layer of
`[names] layers` (schema 6 and later) keeps them in a fourth file beside its three, `translit.tsv`, sorted by its key —
and are summed as the names are: bottom to top (the base, then each layer), an upper layer's rule replacing the lower
one of its key whole, a `-` in `latin` taking a lower rule away. A rule is bound to its profile: a rule of `ru-v1` says
nothing of `ru-v2`. A workspace of schema 6 or older reads no rules here — its rules are the corpus's
`transliteration.toml` (`verso.ru.naming.transliteration.corpus_spellings`).

The rules are not part of the names lexicon (`verso.ru.naming.lexicon`): they spell, they do not answer a name's forms,
and no records export fingerprints them. A host that keeps a layer elsewhere (a server's rows) hands its rules over as a
`RuleSource` for the time it works in a workspace (`provided`), as it hands its names (`verso.ru.naming.layers.provided`).
"""
from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from time import monotonic
from importlib.resources.abc import Traversable
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, Protocol

from verso.core import workspace
from verso.ru.messages import t
from verso.ru.naming.layer_files import BASE, LayerFileError
from verso.ru.naming.layers import layer_name

#: A layer's file of rules, beside its three names files.
FILE = "translit.tsv"
COLUMNS = ("profile", "word", "latin", "source", "note")
#: A `latin` cell that takes a lower layer's rule of the key away.
REMOVED = "-"

type Key = tuple[str, str]


class TranslitRule(NamedTuple):
    """A row of `translit.tsv`: `profile` spells `word` (a whole word, as the record writes it) as `latin`; `latin` None — the
    row takes a lower layer's rule of the key away (`-`)."""
    profile: str
    word: str
    latin: str | None
    source: str = "editor"
    note: str = ""

    @property
    def key(self) -> Key:
        return (self.profile, self.word)


class RuleSource(Protocol):
    """Where a layer's rules come from: its file, or a host's rows. `stamp()` changes whenever `load()` would read something
    else; `put` and `remove` are for a writable source."""
    name: str
    writable: bool

    def load(self) -> Mapping[Key, TranslitRule]: ...

    def stamp(self) -> str: ...

    def put(self, rule: TranslitRule) -> None: ...

    def remove(self, key: Key) -> None: ...


def read_rows(path: Path | Traversable) -> list[tuple[int, TranslitRule]]:
    """Every row of a `translit.tsv` as written — (line, rule) — duplicates included (the layers' linter); none without the
    file. A header other than `COLUMNS`, or a row of another width, is a `LayerFileError`."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or tuple(lines[0].split("\t")) != COLUMNS:
        raise LayerFileError(str(t("layer_files.header", file=FILE, columns="\t".join(COLUMNS))))
    out: list[tuple[int, TranslitRule]] = []
    for number, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(COLUMNS):
            raise LayerFileError(str(t("layer_files.width", file=FILE, line=number)))
        profile, word, latin, source, note = cells
        out.append((number, TranslitRule(profile, word, None if latin == REMOVED else latin, source, note)))
    return out


def _read(path: Path | Traversable) -> dict[Key, TranslitRule]:
    out: dict[Key, TranslitRule] = {}
    for number, rule in read_rows(path):
        if rule.key in out:
            raise LayerFileError(str(t("layer_files.duplicate", file=FILE, line=number,
                                       key=f"{rule.profile} {rule.word}")))
        out[rule.key] = rule
    return out


def write(path: Path, rules: Mapping[Key, TranslitRule]) -> None:
    """Write `rules` as a layer's `translit.tsv`, sorted by key, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\t".join(COLUMNS) + "\n" + "".join(
        "\t".join((r.profile, r.word, REMOVED if r.latin is None else r.latin, r.source, r.note)) + "\n"
        for _, r in sorted(rules.items()))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


class FileRules:
    """The rules of one layer directory: its `translit.tsv` (none without the file)."""

    def __init__(self, directory: Path | Traversable, *, name: str, writable: bool) -> None:
        self.directory, self.name, self.writable = directory, name, writable

    @property
    def path(self) -> Path | Traversable:
        return self.directory / FILE

    def stamp(self) -> str:
        path = self.path
        if not isinstance(path, Path):
            return "package"
        try:
            st = path.stat()
        except FileNotFoundError:
            return "absent"
        return f"{st.st_mtime_ns}:{st.st_size}"

    def load(self) -> Mapping[Key, TranslitRule]:
        return MappingProxyType(_read(self.path))

    def put(self, rule: TranslitRule) -> None:
        """Write `rule` in its key's place, replacing the row of that key (its note kept when the rule brings none)."""
        path = self._writable()
        rules = _read(path)
        held = rules.get(rule.key)
        rules[rule.key] = rule._replace(note=held.note) if held is not None and not rule.note else rule
        write(path, rules)
        reload()

    def remove(self, key: Key) -> None:
        """Drop the row of `key`; a KeyError when the layer has none."""
        path = self._writable()
        rules = _read(path)
        del rules[key]
        write(path, rules)
        reload()

    def _writable(self) -> Path:
        if not self.writable or not isinstance(self.path, Path):
            raise TypeError(str(t("lexicon.read_only", layer=self.name)))
        return self.path


#: The rule sources a host provides, by the layer directory `[names] layers` resolves (`provided`).
_PROVIDED: dict[Path, RuleSource] = {}


@contextmanager
def provided(directory: Path, source: RuleSource) -> Generator[None]:
    """Until the block ends, the rules of the layer at `directory` are `source`'s, in place of its `translit.tsv`."""
    held = _PROVIDED.get(directory)
    _PROVIDED[directory] = source
    reload()
    try:
        yield
    finally:
        if held is None:
            _PROVIDED.pop(directory, None)
        else:
            _PROVIDED[directory] = held
        reload()


def sources(ws: workspace.Workspace) -> list[RuleSource]:
    """The rule sources of `ws`, bottom to top: the base's (the package's `data/base/`) when `[names] base` is `ru`, then each
    layer of `[names] layers`. None for a workspace of schema 6 or older: its rules are not here."""
    config = ws.names_layers
    if ws.translit is None or config is None:
        return []
    out: list[RuleSource] = []
    if config.base == "ru":
        out.append(FileRules(BASE, name="base", writable=False))
    for directory in config.layers:
        host = _PROVIDED.get(directory)
        out.append(host if host is not None else
                   FileRules(directory, name=layer_name(ws.root, directory), writable=directory == config.writable))
    return out


def writable(ws: workspace.Workspace) -> RuleSource:
    """The source a rule is written to: the layer `[names] writable` names; a `WorkspaceError` without one."""
    for source in sources(ws):
        if source.writable:
            return source
    raise workspace.WorkspaceError(t("transliteration.no_writable_layer", config=ws.root / workspace.CONFIG))


#: How long the rules summed are answered from before their sources' stamps are looked at again: a word's spelling is
#: asked ~10⁵ times a village (`verso.ru.naming.transliteration.spelling`), and a stamp costs a `stat` a file — as the
#: names lexicon's (`verso.ru.naming.names_registry.RECHECK_SECONDS`).
RECHECK_SECONDS = 1.0


class _Held(NamedTuple):
    """The rules summed for one workspace: its sources, their stamps then, and when to look at the stamps again."""
    ws: workspace.Workspace
    sources: tuple[RuleSource, ...]
    stamps: tuple[str, ...]
    rules: Mapping[Key, TranslitRule]
    next_check: float


_held: _Held | None = None


def rules(ws: workspace.Workspace) -> Mapping[Key, TranslitRule]:
    """Every rule of `ws`, the layers summed: an upper layer's row replaces the lower one of its key, a `-` takes it away.
    Kept for the workspace; its sources' stamps are looked at again at most every `RECHECK_SECONDS`, and the rules read
    again when one changed. A rule written through a source (`put`, `remove`, `verso.ru.linters.translit_layer`), a
    host's source provided or taken back (`provided`) and another workspace forget them at once (`reload`)."""
    global _held
    held = _held  # a local: another thread's `reload()` may forget the global meanwhile
    if held is not None and held.ws is ws and monotonic() < held.next_check:
        return held.rules
    stack = held.sources if held is not None and held.ws is ws else tuple(sources(ws))
    stamps = tuple(s.stamp() for s in stack)
    if held is not None and held.ws is ws and held.stamps == stamps:
        summed = held.rules
    else:
        out: dict[Key, TranslitRule] = {}
        for source in stack:
            for key, rule in source.load().items():
                if rule.latin is None:
                    out.pop(key, None)
                else:
                    out[key] = rule
        summed = MappingProxyType(out)
    _held = _Held(ws, stack, stamps, summed, monotonic() + RECHECK_SECONDS)
    return summed


def reload() -> None:
    """Forget the rules summed, so the next `rules` reads every source again — after a write that may leave a stamp as it
    was, or from a host whose rows changed under it."""
    global _held
    _held = None


# Another workspace is other rules.
workspace.on_change(reload)


def explain(ws: workspace.Workspace, profile: str, word: str) -> list[tuple[str, TranslitRule]]:
    """Which layers hold a row of (profile, word), bottom to top, each with its row (a `-` row too)."""
    return [(source.name, row) for source in sources(ws)
            if (row := source.load().get((profile, word))) is not None]
