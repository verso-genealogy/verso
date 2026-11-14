"""The plugin registry: what the core takes from the plugins a workspace works with.

A plugin is a `Plugin` a distribution declares under the entry point group `verso.plugins`
(pyproject.toml: `ru = "verso.ru.plugin:PLUGIN"`), and a workspace enables it by name —
`plugins = ["ru"]` in verso.toml, schema 4; a file of an older schema reads as `["ru"]`. The
core asks at work, never at import: `transliterator()`, the res_names' spelling the Geni
models take, `content()`, the locales they key a profile's names by, `dsl()`, the one enabled plugin's DSL — its record kinds, the globs of its
files, the order its books are read in, the calls the review ratchet reads, the
vocabulary of its records JSON and what its records are cited by (rule r1), and `ui()`, the hints its review page's schema is built
from. Each answer is kept for the workspace it was asked in, and forgotten when the
workspace changes (`workspace.on_change`) or a test adds plugins (`adding`).

An entry point is loaded only when its name is asked for: `enabled()` loads the enabled
ones, `installed()` all of them (`verso --help`, the commands). A plugin named otherwise than its entry point, an entry point that is no `Plugin`, and
two plugins of one name are refused. The entry points are the venv's metadata, which `make
bootstrap` writes: a workspace naming a plugin nobody installed says so, and says `make
bootstrap`.

Importing this module reads no workspace — `verso workspace` runs `verso.core.workspace` as
`__main__`, and a copy imported here first would be a second module of it.
"""
from __future__ import annotations

from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING, Any
from verso.core.messages import t

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from verso.core.corpus_data import Village
    from verso.core.ratchet import CallDialect
    from verso.core.records.fields import Vocabulary
    from verso.core.records.ids import Citation
    from verso.core.workspace import Workspace

GROUP = "verso.plugins"


class PluginError(SystemExit):
    """A plugin cannot be found or used; the message says why, in Russian. A SystemExit, as
    `StaleRecords` is: uncaught, the program stops with the message alone, and a loader's
    broad `except Exception` (one DSL file skipped with a warning) cannot swallow it — a
    workspace without its plugin is no village of empty files."""


@dataclass(frozen=True)
class RecordKind:
    """A kind of record set a plugin's DSL binds: what the core loads, counts and exports."""
    code: str                        # "birth", "household", "card": the id's kind, the export's
    set_type: type                   # the record set's class (`BirthRecords`)
    record_types: tuple[type, ...]   # the classes of its records (`Birth`, `Christening`)
    records: str                     # the set's attribute holding them: records, households, entries
    translated: bool = True          # read by the translator (a divorce is not)
    ratcheted: bool = True           # fingerprinted by the review ratchet (a card, a divorce are not)


@dataclass(frozen=True)
class Dsl:
    """A plugin's DSL as the core reads a village through it."""
    kinds: tuple[RecordKind, ...]
    globs: tuple[str, ...]           # its files, `<year>/<name>`, in the order a year's are read
    # A record set's place among the village's: the key `discover_records` sorts by.
    order: Callable[[Path, Any, Village], tuple[Any, ...]]
    calls: CallDialect               # how its source writes a record: what the review ratchet reads
    vocabulary: Vocabulary           # every attribute of its classes: what the records JSON holds
    cite: Citation                   # what a record is cited by: rule r1's book, number, people
    # What a file is told when it imports a module the DSL no longer has (ru: DSL v0's `geni.*`):
    # the missing module and the file importing it → the advice, None for any other module.
    legacy_import: Callable[[str, Path], str | None] | None = None


@dataclass(frozen=True)
class ContentProfile:
    """The language of what a plugin's records generate: content, frozen by the plugin —
    never the interface's language. The Geni models key a profile's names by these."""
    native: str                      # the names' and the about's locale key (ru: "ru")
    latin: str                       # the transliterated names' locale key (ru: "en-US")


@dataclass(frozen=True)
class SourceNotes:
    """The `#` notes of one DSL file, as a plugin reads them from its text (records v1.x).

    Each note is `{"text": str, "anchor": {"to", "record", "end", "arg"}}` (other keys are not
    read): `to` is `file`, `record`, `argument`, `field`, `range` or `manual`; `record` and `end`
    a record's place among the file's records, from nought, in the export's order; `arg` the
    DSL's name of an argument (a factory parameter) or a person's slot (`member3`) — the export puts
    on the node what the JSON names it (`verso.core.records.notes`). `numbers` is what the ordinals were counted from — each
    record call's number as written (`None` where it wrote none the plugin can read), in source
    order — or `None` when the plugin could not count them: the export holds the two counts and
    the numbers to its own records before it binds a note to one (`verso.core.records.notes`)."""
    notes: Sequence[Mapping[str, object]]
    numbers: Sequence[int | None] | None


@dataclass(frozen=True)
class Plugin:
    """What a plugin gives the core. The factories are called when the core first asks, in
    the workspace that enables the plugin: importing a plugin's module costs nothing."""
    name: str
    package: str
    commands: Mapping[str, str] = field(default_factory=dict[str, str])
    dsl: Callable[[], Dsl] | None = None
    transliterate: Callable[[], Callable[[str], str]] | None = None
    content: Callable[[], ContentProfile] | None = None
    # The tables of a village.toml the plugin reads — a name → its parser, given the file's
    # path and the table as written (`verso.core.corpus_data.village`); a table no plugin reads
    # is an unknown key.
    village_tables: Mapping[str, Callable[[Path, Mapping[str, Any]], Any]] = field(
        default_factory=dict[str, Callable[["Path", Mapping[str, Any]], Any]])
    # A place's keys beyond its fields that the plugin reads (ru: `familio`), and the names
    # tables of the workspace's `[names] dir` it reads (ru: names.csv and its two ignore lists).
    place_attributes: tuple[str, ...] = ()
    names_tables: tuple[str, ...] = ()
    # The files of a names layer's directory the plugin reads (schema 6, `[names] layers`; ru: names.tsv,
    # forms.tsv, patronymics.tsv): what a records export fingerprints of each layer.
    names_layer_files: tuple[str, ...] = ()
    # The digest of a names base the plugin ships, by the name `[names] base` gives it (ru: "ru" → the SHA-256 of its
    # three TSV files), None for a name it ships no base under: what a records export fingerprints of the base.
    names_base_digest: Callable[[str], str | None] | None = None
    # The spelling of the names a person reads — a Geni profile's Latin names — when it is not the res_names' one
    # (`transliterate`): ru gives the role's profile `[translit] display` names. None: the res_names' spelling.
    display_transliterate: Callable[[], Callable[[str], str]] | None = None
    # The TOML of the hints the review page's schema is built from (`verso.core.records.ui`).
    ui: Callable[[], Path | Traversable] | None = None
    # What a records file says of itself (records v1.x): the plugin's name for the vocabulary its
    # records are written in and that vocabulary's version (a file of a newer one is refused), and
    # the language of a book by default, BCP 47 (ru: "ru-Cyrl"). The core hard-codes neither.
    vocabulary: tuple[str, int] | None = None
    default_lang: str | None = None
    # The `#` notes of a DSL file, read from its text (records v1.x): what the export puts on
    # the file's and the records' nodes. A plugin without it exports no notes.
    notes: Callable[[str], SourceNotes] | None = None


# adding()'s blocks, innermost last: the plugins each adds, and whether the entry points show.
_added: list[tuple[tuple[Plugin, ...], bool]] = []
# The workspace the answers below were asked in, and the answers by question.
_slot: tuple[Workspace, dict[str, Any]] | None = None
_listening = False


def _forget() -> None:
    global _slot
    _slot = None


def _cached[T](ws: Workspace, question: str, answer: Callable[[], T]) -> T:
    global _slot, _listening
    if not _listening:
        from verso.core import workspace
        workspace.on_change(_forget)
        _listening = True
    slot = _slot
    # A workspace loaded again from the same verso.toml is the same workspace (a frozen dataclass of what the file
    # says): a host that enters its workspace once a book (the hosted server's) keeps the answers.
    if slot is None or (slot[0] is not ws and slot[0] != ws):
        slot = _slot = (ws, {})
    if question not in slot[1]:
        slot[1][question] = answer()
    return slot[1][question]


def _where(entry: Plugin | metadata.EntryPoint) -> str:
    return entry.value if isinstance(entry, metadata.EntryPoint) else entry.package


def _available() -> dict[str, Plugin | metadata.EntryPoint]:
    """Every installed plugin by name, none loaded: the entry points (unless a block hides
    them), then what `adding` adds."""
    out: dict[str, Plugin | metadata.EntryPoint] = {}
    if all(shown for _, shown in _added):
        for ep in metadata.entry_points(group=GROUP):
            if ep.name in out:
                before = out[ep.name]
                dists = [e.dist.name for e in (before, ep) if isinstance(e, metadata.EntryPoint) and e.dist]
                if len(dists) == 2 and dists[0] != dists[1]:
                    # A distribution left behind — `geni` beside verso-ru after 0.1.0 — names the plugin again.
                    raise PluginError(t("plugins.declared_twice", name=ep.name, first=dists[0], second=dists[1]))
                if _where(before) != ep.value:
                    raise PluginError(t("plugins.two_entry_points", name=ep.name, first=_where(before), second=ep.value))
            out[ep.name] = ep
    for added, _ in _added:
        for plugin in added:
            if plugin.name in out and out[plugin.name] is not plugin:
                raise PluginError(t("plugins.two_added", name=plugin.name, first=_where(out[plugin.name]), second=plugin.package))
            out[plugin.name] = plugin
    return out


def _load(entry: Plugin | metadata.EntryPoint) -> Plugin:
    if isinstance(entry, Plugin):
        return entry
    try:
        plugin = entry.load()
    except Exception as error:
        raise PluginError(t("plugins.entry_point_fails", name=entry.name, value=entry.value, error=error)) from error
    if not isinstance(plugin, Plugin):
        raise PluginError(t("plugins.entry_point_no_plugin", name=entry.name, value=entry.value))
    if plugin.name != entry.name:
        raise PluginError(t("plugins.entry_point_misnamed", name=entry.name, value=entry.value, gives=plugin.name))
    return plugin


def installed() -> dict[str, Plugin]:
    """Every installed plugin, by name, each loaded (`verso --help`); it reads no workspace."""
    return {name: _load(entry) for name, entry in sorted(_available().items())}


def enabled() -> tuple[Plugin, ...]:
    """The plugins the current workspace names, in its order."""
    from verso.core import workspace
    ws = workspace.current()

    def answer() -> tuple[Plugin, ...]:
        available = _available()
        out: list[Plugin] = []
        for name in ws.plugins:
            if name not in available:
                names = ", ".join(sorted(available)) or str(t("plugins.none_installed"))
                raise PluginError(t("plugins.not_installed", config=ws.root / workspace.CONFIG, name=name, installed=names))
            out.append(_load(available[name]))
        return tuple(out)
    return _cached(ws, "enabled", answer)


def transliterator() -> Callable[[str], str]:
    """The res_names' spelling: the transliteration the one enabled plugin that gives one gives."""
    from verso.core import workspace
    ws = workspace.current()

    def answer() -> Callable[[str], str]:
        given = [p for p in enabled() if p.transliterate is not None]
        config = ws.root / workspace.CONFIG
        if not given:
            raise PluginError(t("plugins.no_transliterator", config=config))
        if len(given) > 1:
            raise PluginError(t("plugins.two_transliterators", config=config, first=given[0].name, second=given[1].name))
        factory = given[0].transliterate
        assert factory is not None
        return factory()
    return _cached(ws, "transliterator", answer)


def display_transliterator() -> Callable[[str], str]:
    """The spelling of the names a person reads: the one enabled plugin's that gives one, else the res_names'
    (`transliterator()`) — a plugin that spells both one way needs give none."""
    from verso.core import workspace
    ws = workspace.current()

    def answer() -> Callable[[str], str]:
        given = [p for p in enabled() if p.display_transliterate is not None]
        if not given:
            return transliterator()
        if len(given) > 1:
            config = ws.root / workspace.CONFIG
            raise PluginError(t("plugins.two_display_transliterators", config=config, first=given[0].name,
                                second=given[1].name))
        factory = given[0].display_transliterate
        assert factory is not None
        return factory()
    return _cached(ws, "display_transliterator", answer)


def content() -> ContentProfile:
    """The content profile of the one enabled plugin that gives one: the locales a generated
    Geni profile is keyed by."""
    from verso.core import workspace
    ws = workspace.current()

    def answer() -> ContentProfile:
        given = [p for p in enabled() if p.content is not None]
        config = ws.root / workspace.CONFIG
        if not given:
            raise PluginError(t("plugins.no_content", config=config))
        if len(given) > 1:
            raise PluginError(t("plugins.two_contents", config=config, first=given[0].name, second=given[1].name))
        factory = given[0].content
        assert factory is not None
        return factory()
    return _cached(ws, "content", answer)


def names_tables() -> tuple[str, ...]:
    """The names tables of the enabled plugins, in their order, each once."""
    return tuple(dict.fromkeys(name for p in enabled() for name in p.names_tables))


def names_base_digest(name: str) -> str | None:
    """The digest of the names base `name` the enabled plugins ship (the first that ships one), else None."""
    for p in enabled():
        if p.names_base_digest is not None:
            digest = p.names_base_digest(name)
            if digest is not None:
                return digest
    return None


def names_layer_files() -> tuple[str, ...]:
    """The files of a names layer the enabled plugins read, in their order, each once."""
    return tuple(dict.fromkeys(name for p in enabled() for name in p.names_layer_files))


def place_attributes() -> tuple[str, ...]:
    """A place's keys the enabled plugins read beyond its fields, in their order, each once."""
    return tuple(dict.fromkeys(name for p in enabled() for name in p.place_attributes))


#: `verso.core.workspace`, once `dsl()` first imported it: the import statement cost more than the rest of the kept
#: answer's path, which the records' encoder and decoder take millions of times a village.
_workspace_module: Any = None


def _workspace() -> Any:
    global _workspace_module
    # Imported here, as everywhere in this module: `python -m verso.core.workspace` (`verso workspace`) runs that module
    # as __main__, and a registry that imported it first would make runpy warn.
    from verso.core import workspace
    _workspace_module = workspace
    return workspace


def dsl() -> Dsl:
    """The DSL of the one enabled plugin that gives one: a workspace reads one DSL."""
    ws = (_workspace_module or _workspace()).current()
    # Asked of every field a book replays: the kept answer first, without building the question.
    slot = _slot
    if slot is not None and (slot[0] is ws or slot[0] == ws) and "dsl" in slot[1]:
        return slot[1]["dsl"]

    def answer() -> Dsl:
        given = [p for p in enabled() if p.dsl is not None]
        config = ws.root / _workspace_module.CONFIG
        if not given:
            raise PluginError(t("plugins.no_dsl", config=config))
        if len(given) > 1:
            raise PluginError(t("plugins.two_dsls", config=config, first=given[0].name, second=given[1].name))
        factory = given[0].dsl
        assert factory is not None
        return factory()
    return _cached(ws, "dsl", answer)


def ui() -> Mapping[str, Any]:
    """The hints of the one enabled plugin that gives them, parsed, with its package named under
    `package` — whose catalog their labels are keys of; empty when no plugin gives any."""
    from verso.core import workspace
    ws = workspace.current()

    def answer() -> Mapping[str, Any]:
        import tomllib
        given = [p for p in enabled() if p.ui is not None]
        if not given:
            return {}
        if len(given) > 1:
            raise PluginError(t("plugins.two_uis", config=ws.root / workspace.CONFIG, first=given[0].name, second=given[1].name))
        factory = given[0].ui
        assert factory is not None
        # The declared package last: the labels are its catalog's keys, whatever the hints write.
        return {**tomllib.loads(factory().read_text(encoding="utf-8")), "package": given[0].package}
    return _cached(ws, "ui", answer)


def kind_of(record_set: object) -> RecordKind | None:
    """The kind of a record set of the workspace's DSL; None for anything else."""
    return next((kind for kind in dsl().kinds if isinstance(record_set, kind.set_type)), None)


@contextmanager
def adding(*plugins: Plugin, entry_points: bool = True) -> Generator[None]:
    """The tests' seam: `plugins` are installed for the block; `entry_points=False` hides
    the venv's (tests/core, where no plugin of the venv may answer)."""
    block = (plugins, entry_points)
    _added.append(block)
    _forget()
    try:
        yield
    finally:
        del _added[next(i for i, b in enumerate(_added) if b is block)]
        _forget()


def records_header() -> dict[str, object]:
    """The optional keys a records file's header gets of the one enabled plugin that gives a DSL:
    `vocabulary` ({"plugin", "version"}) and `lang`. A core without such a plugin writes neither."""
    out: dict[str, object] = {}
    for plugin in enabled():
        if plugin.dsl is None:
            continue
        if plugin.vocabulary is not None:
            name, version = plugin.vocabulary
            out["vocabulary"] = {"plugin": name, "version": version}
        if plugin.default_lang is not None:
            out["lang"] = plugin.default_lang
        break
    return out


def known_vocabulary_version(name: str) -> int | None:
    """The newest version of the vocabulary `name` that an enabled plugin of that name reads, if any."""
    for plugin in enabled():
        if plugin.vocabulary is not None and plugin.vocabulary[0] == name:
            return plugin.vocabulary[1]
    return None


def source_notes(source: str) -> SourceNotes | None:
    """The `#` notes of a DSL file's text, as the one enabled plugin that gives a DSL reads them;
    None when it reads none (`Plugin.notes` unset)."""
    for plugin in enabled():
        if plugin.dsl is None:
            continue
        return plugin.notes(source) if plugin.notes is not None else None
    return None
