"""The library's statuses, and the catalog a workspace adds its corpus's own to.

`catalog()` is every status constant the library and the workspace's corpus define, in the
catalog's order — the corpus's (`<[corpus] dir>/statuses.py`, or the same as data in
`statuses.toml`) where its block stood, before `LANDLORD`: what Verso offers, the linters read
and the newborn's-status index is built from. It is read at work time, and kept for the
workspace it was asked in. The TOML form is read without executing any Python.
"""
import functools
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, ModuleType, SimpleNamespace
from typing import cast

from verso.core import corpus_data, workspace
from verso.ru.gender import Gender
from verso.core.workspace import WorkspaceError
from verso.ru.domain import Status
from verso.ru.messages import t

# Economic peasants — base statuses (used in RecordDefaults)
ECON_PEASANT_MALE = Status("экономический крестьянин", Gender.MALE)
ECON_PEASANT_FEMALE = Status("экономическая крестьянка", Gender.FEMALE)

# State peasants — base statuses (used in RecordDefaults)
STATE_PEASANT_MALE = Status("государственный крестьянин", Gender.MALE)
STATE_PEASANT_FEMALE = Status("государственная крестьянка", Gender.FEMALE)
# State peasants — specific roles. The child forms are what `child_status_for`
# derives a newborn's or a dead child's status from, as for the казённые and
# экономические below; GOSUDARSTVENNYJ_PEASANT_* is the same estate.
STATE_PEASANT_WIFE = Status("жена из государственных крестьян", Gender.FEMALE)
STATE_PEASANT_LEGAL_WIFE = Status("законная жена государственного крестьянина", Gender.FEMALE)
STATE_PEASANT_SON = Status("государственный крестьянский сын", Gender.MALE)
STATE_PEASANT_DAUGHTER = Status("государственная крестьянская дочь", Gender.FEMALE)

# Economic peasants — specific roles in birth/marriage/death records
ECON_PEASANT_GIRL = Status("девка из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_MAIDEN = Status("девица из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_DEVA = Status("дева из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_WIFE = Status("жена из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_ZHONKA = Status("женка из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_WIDOW = Status("вдова из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_SON = Status("экономический крестьянский сын", Gender.MALE)
ECON_PEASANT_WIDOWER = Status("экономический крестьянин вдовец", Gender.MALE)
ECON_PEASANT_DAUGHTER_MAIDEN = Status("дочь девица из экономических крестьян", Gender.FEMALE)
ECON_PEASANT_DAUGHTER = Status("экономическая крестьянская дочь", Gender.FEMALE)
ECON_PEASANT_BOY = Status("отрок из экономических крестьян", Gender.MALE)
ECON_PEASANT_WIFE_OF = Status("жена экономического крестьянина", Gender.FEMALE)
ECON_PEASANT_LEGAL_WIFE = Status("законная жена экономического крестьянина", Gender.FEMALE)

# Generic statuses (no estate specified)
MAIDEN = Status("девица", Gender.FEMALE)
GIRL = Status("девка", Gender.FEMALE)
ZHONKA = Status("женка", Gender.FEMALE)
WIDOW = Status("вдова", Gender.FEMALE)
ODNODVORETS_DAUGHTER = Status("однодворческая дочь", Gender.FEMALE)
ODNODVORETS = Status("однодворец", Gender.MALE)
ODNODVORETS_SON = Status("однодворческий сын", Gender.MALE)
ODNODVORETS_LEGAL_WIFE = Status("законная жена однодворца", Gender.FEMALE)
PRIVATE_SOLDIER = Status("рядовой", Gender.MALE)
MESHCHANIN = Status("мещанин", Gender.MALE)
MESHCHANIN_DAUGHTER = Status("мещанская дочь", Gender.FEMALE)
MESHCHANIN_SON = Status("мещанский сын", Gender.MALE)
MESHCHANIN_FEMALE = Status("мещанка", Gender.FEMALE)
MESHCHANIN_WIFE = Status("мещанская жена", Gender.FEMALE)
MESHCHANIN_WIDOW = Status("вдова мещанка", Gender.FEMALE)
PRIEST_DAUGHTER = Status("дочь священника", Gender.FEMALE)
POPADIA = Status("попадья", Gender.FEMALE)
DYACHIKHA_WIDOW = Status("вдова дьячиха", Gender.FEMALE)
YASAK_SOLDIER_WIFE = Status("ясачная солдатская жена", Gender.FEMALE)

# Yasak peasants — base statuses (used in RecordDefaults for Горюхино)
YASAK_PEASANT_MALE = Status("ясачный крестьянин", Gender.MALE)
YASAK_PEASANT_FEMALE = Status("ясачная крестьянка", Gender.FEMALE)

# Yasak peasants — specific roles
YASAK_PEASANT_GIRL = Status("девка из ясачных крестьян", Gender.FEMALE)
YASAK_PEASANT_BOY = Status("отрок из ясачных крестьян", Gender.MALE)
YASAK_PEASANT_SON = Status("ясачный крестьянский сын", Gender.MALE)
YASAK_PEASANT_NEWCONVERT = Status("новокрещёный ясачный крестьянин", Gender.MALE)

# Yasak peasants — additional roles
YASAK_PEASANT_WIFE = Status("ясачная крестьянская жена", Gender.FEMALE)
YASAK_PEASANT_WIDOW = Status("вдова из ясачных крестьян", Gender.FEMALE)
YASAK_PEASANT_DAUGHTER_MAIDEN = Status("дочь девица из ясачных крестьян", Gender.FEMALE)
YASAK_PEASANT_MAIDEN = Status("девица из ясачных крестьян", Gender.FEMALE)
YASAK_PEASANT_DAUGHTER = Status("ясачная крестьянская дочь", Gender.FEMALE)
YASAK_PEASANT_LEGAL_WIFE = Status("законная жена ясачного крестьянина", Gender.FEMALE)

# Kazennyj (state) peasants — 1841+ replacement for yasak (Горюхино)
# Starting in 1841 the population of Горюхино was reclassified from ясачные
# to казенные крестьяне. Use these for DSL records dated 1841 and later.
KAZENNYJ_PEASANT_MALE = Status("казенный крестьянин", Gender.MALE)
KAZENNYJ_PEASANT_FEMALE = Status("казенная крестьянка", Gender.FEMALE)
KAZENNYJ_PEASANT_GIRL = Status("девка из казенных крестьян", Gender.FEMALE)
KAZENNYJ_PEASANT_BOY = Status("отрок из казенных крестьян", Gender.MALE)
KAZENNYJ_PEASANT_SON = Status("казенный крестьянский сын", Gender.MALE)
KAZENNYJ_PEASANT_NEWCONVERT = Status("новокрещёный казенный крестьянин", Gender.MALE)
KAZENNYJ_PEASANT_WIFE = Status("казенная крестьянская жена", Gender.FEMALE)
KAZENNYJ_PEASANT_WIDOW = Status("вдова из казенных крестьян", Gender.FEMALE)
KAZENNYJ_PEASANT_DAUGHTER_MAIDEN = Status("дочь девица из казенных крестьян", Gender.FEMALE)
KAZENNYJ_PEASANT_MAIDEN = Status("девица из казенных крестьян", Gender.FEMALE)
KAZENNYJ_PEASANT_DAUGHTER = Status("казенная крестьянская дочь", Gender.FEMALE)
KAZENNYJ_PEASANT_LEGAL_WIFE = Status("законная жена казенного крестьянина", Gender.FEMALE)

# Gosudarstvennye (state) peasants — official wording used in Нижняя Яичница.
# Same fiscal-administrative category as the казённые крестьяне above, but the
# Нижняя Яичница revision skazki (e.g. 1857) record it as "государственный".
GOSUDARSTVENNYJ_PEASANT_MALE = Status("государственный крестьянин", Gender.MALE)
GOSUDARSTVENNYJ_PEASANT_FEMALE = Status("государственная крестьянка", Gender.FEMALE)

# Временнообязанные — former landlord peasants between the 1861 emancipation and the
# redemption of their allotment (Маниловка from 1863, Глуповы Горы 1874–1881). The
# books write «временно-обязанный»; the catalog spells it as modern Russian does.
TEMP_OBLIGED_PEASANT_MALE = Status("временнообязанный крестьянин", Gender.MALE)
# Крестьяне-собственники — former landlord peasants who have redeemed their allotment,
# the stage after временнообязанные (Маниловка 1870–1879, «крестьянинъ собственникъ»);
# the catalog spells it as modern Russian does. Still the peasant estate.
PROPRIETOR_PEASANT_MALE = Status("крестьянин собственник", Gender.MALE)

# Plain peasants — 1903+ (Горюхино)
# By the early 20th century the fiscal-administrative qualifiers (ясачный /
# казенный) were dropped from records and peasants are listed as just
# "крестьянин" / "крестьянка". Use these for DSL records dated 1903 and later.
# (Earlier transition possible but not yet attested in surviving records.)
PEASANT_MALE = Status("крестьянин", Gender.MALE)
PEASANT_FEMALE = Status("крестьянка", Gender.FEMALE)
PEASANT_BOY = Status("отрок из крестьян", Gender.MALE)
PEASANT_GIRL = Status("девка из крестьян", Gender.FEMALE)
PEASANT_MAIDEN = Status("крестьянская девица", Gender.FEMALE)
PEASANT_WIDOW = Status("вдова из крестьян", Gender.FEMALE)
PEASANT_WIFE = Status("законная жена крестьянина", Gender.FEMALE)
# The short form, as SOLDIER_SPOUSE is to SOLDIER_WIFE: «крестьянская жена»
# without the husband — how Маниловка and Глуповы Горы style a godmother.
PEASANT_SPOUSE = Status("крестьянская жена", Gender.FEMALE)
PEASANT_SON = Status("крестьянский сын", Gender.MALE)
PEASANT_DAUGHTER = Status("крестьянская дочь", Gender.FEMALE)
PEASANT_DAUGHTER_MAIDEN = Status("крестьянская дочь девица", Gender.FEMALE)
PEASANT_DAUGHTER_GIRL = Status("крестьянская дочь девка", Gender.FEMALE)
# «женка» is how the Глуповы Горы books style a peasant wife; see ZHONKA and
# ECON_PEASANT_ZHONKA for the same word in the other estates.
PEASANT_ZHONKA = Status("крестьянская женка", Gender.FEMALE)

BUDNY_PEASANT = Status("будный крестьянин", Gender.MALE)

# Landlord peasants are the corpus's own (corpus/statuses.py): the DSL imports them from
# `corpus.statuses`, and the library reads them through `catalog()`, from the workspace,
# in the place their block stood here — before LANDLORD.

# Nobility (дворянство)
LANDLORD = Status("помещик", Gender.MALE)
LANDLORD_FEMALE = Status("помещица", Gender.FEMALE)
LANDLORD_SON = Status("сын помещика", Gender.MALE)
LANDLORD_DAUGHTER = Status("дочь помещика", Gender.FEMALE)

# Soldiers (военные)
SOLDIER = Status("солдат", Gender.MALE)
RETIRED_SOLDIER = Status("отставной солдат", Gender.MALE)
SOLDIER_WIFE = Status("солдатка", Gender.FEMALE)
SOLDIER_SPOUSE = Status("солдатская жена", Gender.FEMALE)
SOLDIER_LEGAL_WIFE = Status("законная жена солдата", Gender.FEMALE)
# «женка», as ZHONKA and PEASANT_ZHONKA: how the books style a wife.
SOLDIER_ZHONKA = Status("солдатская женка", Gender.FEMALE)
SOLDIER_WIDOW = Status("солдатская вдова", Gender.FEMALE)
SOLDIER_SON = Status("солдатский сын", Gender.MALE)
SOLDIER_DAUGHTER = Status("солдатская дочь", Gender.FEMALE)
SOLDIER_GIRL = Status("солдатская девка", Gender.FEMALE)
# A rank, not a сословие: no child forms, so `child_status_for` leaves it alone.
UNTER_OFFICER = Status("унтер-офицер", Gender.MALE)

# Merchants (купечество)
MERCHANT = Status("купец", Gender.MALE)
MERCHANT_SON = Status("купеческий сын", Gender.MALE)
MERCHANT_DAUGHTER = Status("купеческая дочь", Gender.FEMALE)

# Clergy (духовенство)
HIEREUS = Status("иерей", Gender.MALE)
PRIEST = Status("священник", Gender.MALE)
DEACON = Status("диакон", Gender.MALE)
DYACHOK = Status("дьячок", Gender.MALE)
SEXTON = Status("пономарь", Gender.MALE)
SEXTON_WIFE = Status("жена пономаря", Gender.FEMALE)
SEXTON_SON = Status("сын пономаря", Gender.MALE)
DYACHOK_SON = Status("сын дьячка", Gender.MALE)
DYACHOK_WIFE = Status("жена дьячка", Gender.FEMALE)
DEACON_DAUGHTER = Status("дочь диакона", Gender.FEMALE)
PRIEST_DAUGHTER_MAIDEN = Status("дочь девица священника", Gender.FEMALE)


# --- Child-status derivation --------------------------------------------------
# Сословие is inherited within the household: a newborn of SOBAKEVICH_UK_PEASANT_MALE
# is SOBAKEVICH_UK_PEASANT_SON / _DAUGHTER. `Birth.__init__` (dsl/records/births.py)
# uses `child_status_for` to derive a statusless child's status from the consulted
# parent (father with a status, else mother) BEFORE RecordDefaults substitutes the
# parish estate; PSA002 (linters/checks/parent_status.py) imports the same function
# to model the inheritance.
#
# The index is built from the catalog, per workspace, by the constant-name convention `<ESTATE>_<ROLE>`
# (role suffixes matched longest-first; a bare landlord key from `*_LEGAL_WIFE`
# promotes to `<KEY>_PEASANT`; полковник == помещик Захар Порфирьевич Собакевич).
# Scope: peasant estates + SOLDIER (with RETIRED_SOLDIER: an отставной солдат's
# child is a солдатский сын/дочь, a ruling of the maintainers). Clergy (a
# rank, not a сословие), дворовые, merchants/мещане/помещики/однодворцы and
# PRIVATE_SOLDIER are deliberately absent — `child_status_for` returns None and
# the caller leaves the child statusless, so the book's RecordDefaults (a peasant
# estate) fills it. Their child forms (MESHCHANIN_SON, LANDLORD_DAUGHTER,
# *_DVOROVY_SON, …) exist, but are stated per record: PSA002 flags a child left
# to the default beside such a parent.
#
# SOLDIER_WIFE-role override: «ясачная солдатская жена» / «солдатская жена из
# крестьян помещицы …» name-split to peasant estates, but a soldier's wife's child
# is a солдатский сын/дочь.

_ROLE_SUFFIXES: tuple[str, ...] = (
    "DAUGHTER_MAIDEN", "DAUGHTER_GIRL", "LEGAL_WIFE", "SOLDIER_WIFE", "WIFE_OF", "NEWCONVERT",
    "DAUGHTER", "WIDOWER", "MAIDEN", "FEMALE", "ZHONKA", "SPOUSE", "WIDOW",
    "MALE", "WIFE", "GIRL", "BOY", "SON",
)
# A временнообязанный's newborn, and a крестьянин собственник's, is styled as any
# peasant's: «крестьянский сын».
# A земской is the peasants' own elected head, a serf of the estate he speaks for,
# so his child is that estate's крестьянский сын/дочь.
# An отставной солдат stays of the military estate his service gave him, and the
# books style his child «солдатский сын», «солдатская дочь».
# The corpus adds its own (`CHILD_ESTATE_ALIASES` of its statuses, `corpus_aliases()`).
_ESTATE_ALIASES = {"RETIRED_SOLDIER": "SOLDIER",
                   "GOSUDARSTVENNYJ_PEASANT": "STATE_PEASANT",
                   "TEMP_OBLIGED_PEASANT": "PEASANT",
                   "PROPRIETOR_PEASANT": "PEASANT"}


def _split_role(const_name: str) -> tuple[str, str]:
    for suffix in _ROLE_SUFFIXES:
        if const_name.endswith("_" + suffix):
            return const_name[: -len(suffix) - 1], suffix
    return const_name, ""


# --- The catalog: the library's statuses and the workspace's corpus's -----------------

# The corpus's statuses stand where their block stood in this module, before this one.
_CORPUS_BEFORE = "LANDLORD"
CORPUS_STATUSES = "statuses.py"
CORPUS_STATUSES_TOML = "statuses.toml"

# What `corpus_statuses()` returns: the corpus's module, or — for the TOML form — a namespace
# with the same names, `__all__` and `__name__`.
CorpusStatuses = ModuleType | SimpleNamespace

_ALIAS_TABLES = {"child_estate_aliases": "CHILD_ESTATE_ALIASES", "estate_aliases": "ESTATE_ALIASES"}
_GENDERS = {"male": Gender.MALE, "female": Gender.FEMALE}
_CONSTANT_KEYS = frozenset({"text", "gender"})


def _corpus_files() -> tuple[Path | None, Path | None]:
    return corpus_data.corpus_file(CORPUS_STATUSES), corpus_data.corpus_file(CORPUS_STATUSES_TOML)


def corpus_module_name() -> str | None:
    """The name the DSL imports the corpus's statuses by — `<the corpus directory's name>.statuses`,
    `corpus.statuses` here; None without a corpus or its `statuses.py`. A corpus holding its statuses
    as `statuses.toml` alone has no module to import them from — the DSL cannot name them, so IMP001
    refuses the import and `verso upgrade-dsl` knows none of their names."""
    py, _ = _corpus_files()
    return None if py is None else f"{py.parent.name}.statuses"


_UNSET = object()
# The stamp (path, mtime, size) of the `statuses.toml` the caches below were built from; `_UNSET` before any.
_seen: object = _UNSET
# How many `held()` blocks are open: inside one the stamp is not asked again.
_held = 0
_listeners: list[Callable[[], None]] = []


def on_change(listener: Callable[[], None]) -> None:
    """Call `listener` whenever the workspace's statuses may have changed: the workspace becoming another
    one, or its `statuses.toml` changing (its stamp: mtime and size) while the process runs."""
    _listeners.append(listener)
    workspace.on_change(listener)


def _stamp(path: Path | None) -> tuple[Path, int, int] | None:
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return path, st.st_mtime_ns, st.st_size


def _refresh() -> None:
    """Forget what was built from `statuses.toml` when the file is another than the one read — added,
    changed or removed — as the corpus's other files are read again on the next question. The module
    form is not re-read: Python does not unload a module the DSL has imported. Inside `held()` the
    stamp was asked as the block began, and is not asked again."""
    global _seen
    if _held:
        return
    stamp = _stamp(corpus_data.corpus_file(CORPUS_STATUSES_TOML))
    if _seen is not _UNSET and stamp != _seen:
        for listener in list(_listeners):
            listener()
    _seen = stamp


def _forget() -> None:
    global _seen
    _seen = _UNSET


def follow() -> None:
    """Ask the stamp of `statuses.toml` now, as every kept function does before it answers (`Kept`): a change
    forgets what was built from the file."""
    _refresh()


@contextmanager
def held() -> Generator[None]:
    """Ask the stamp of `statuses.toml` once, as the block begins, and not again until it ends: one request —
    a lint call (`verso.ru.linters.on_json`) — reads the file as it stood when the request began, and the next
    request sees an edit. A change of workspace inside the block still forgets what was built from the file (`on_change`).
    Not thread-safe: the count of open blocks is the process's, as the caches are."""
    global _held
    _refresh()
    _held += 1
    try:
        yield
    finally:
        _held -= 1


def _forget_genders() -> None:
    Status._data_genders = {}


workspace.on_change(_forget)
on_change(_forget_genders)


class Kept[**P, R]:
    """A function's answers kept per workspace, as `functools.cache` keeps them, and forgotten as the workspace's
    statuses may have changed (`on_change`) — the stamp of `statuses.toml` is asked before each call. What is built
    from the catalog is kept so (`@kept`), or it would outlive a change of the file."""

    def __init__(self, function: Callable[P, R]) -> None:
        self._cached = functools.cache(function)
        functools.update_wrapper(self, function)
        on_change(self._cached.cache_clear)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        _refresh()
        return self._cached(*args, **kwargs)

    def cache_clear(self) -> None:
        self._cached.cache_clear()


def kept[**P, R](function: Callable[P, R]) -> Kept[P, R]:
    return Kept(function)


@kept
def corpus_statuses() -> CorpusStatuses | None:
    """The corpus's statuses of the workspace: the module `<[corpus] dir>/statuses.py`, registered
    in `sys.modules` as `<the corpus directory's name>.statuses` — the name the DSL imports it
    by — or, when the corpus holds `statuses.toml` instead, a namespace of the same names read
    from the data, with no Python executed; None without a corpus or either file. A module
    already there under that name is the one, if it is that file. Both files are refused."""
    py, toml = _corpus_files()
    if py is not None and toml is not None:
        raise WorkspaceError(t("statuses.both_forms", toml=toml, py=py))
    if toml is not None:
        module = _read_toml(toml)
        Status._data_genders = {str(s): s.gender for n in _corpus_names(module)
                                if (s := getattr(module, n)).gender is not None}
        return module
    path = py
    if path is None:
        return None
    name = f"{path.parent.name}.statuses"
    module = sys.modules.get(name)
    if module is not None:
        found = getattr(module, "__file__", None)
        if found is None or Path(found).resolve() != path.resolve():
            raise WorkspaceError(t("statuses.imported_elsewhere", name=name, found=found, path=path))
        return module
    if _is_the_package(path.parent):      # imported as the import system would: bound on its package
        return importlib.import_module(name)
    # Loaded from the file a link names, so a workspace whose link is gone (a temporary
    # directory) leaves no module the next one cannot recognise.
    spec = importlib.util.spec_from_file_location(name, path.resolve())
    if spec is None or spec.loader is None:
        raise WorkspaceError(t("statuses.not_a_module", path=path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _read_toml(path: Path) -> SimpleNamespace:
    """The statuses of `statuses.toml`: a table a constant (`text`, `gender`), in the file's order,
    and the two alias tables. Refuses what it does not know, naming the file and the key."""
    data = corpus_data.read_toml(path)
    consts: dict[str, Status] = {}
    aliases: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if key in _ALIAS_TABLES:
            table = cast(dict[object, object], value) if isinstance(value, dict) else None
            if table is None or not all(isinstance(k, str) and isinstance(v, str) for k, v in table.items()):
                raise corpus_data.wrong(path, key, t("statuses.expected_aliases"))
            aliases[_ALIAS_TABLES[key]] = cast(dict[str, str], table)
            continue
        if not (key.isidentifier() and key.isupper()) or not isinstance(value, dict):
            raise corpus_data.wrong(path, key, t("statuses.expected_constant"))
        fields = cast(dict[str, object], value)
        corpus_data.check_keys(path, key, fields, {key: _CONSTANT_KEYS})
        text = fields.get("text")
        if not isinstance(text, str) or not text:
            raise corpus_data.wrong(path, f"{key}.text", t("corpus_data.expected_string"))
        gender = fields.get("gender")
        if gender is not None and (not isinstance(gender, str) or gender not in _GENDERS):
            raise corpus_data.wrong(path, f"{key}.gender", t("statuses.expected_gender"))
        # Not registered by text (`Status._gender_registry`): `corpus_statuses` gives the file's sexes to
        # `Status._data_genders`, which is replaced whenever the file is read again.
        status = Status(text)
        status.gender = _GENDERS[gender] if gender is not None else None
        consts[key] = status
    module = SimpleNamespace(**consts, __all__=list(consts),
                             CHILD_ESTATE_ALIASES=aliases.get("CHILD_ESTATE_ALIASES", {}),
                             ESTATE_ALIASES=aliases.get("ESTATE_ALIASES", {}))
    module.__name__ = f"{path.parent.name}.statuses"
    return module


def _is_the_package(directory: Path) -> bool:
    """Whether `import <directory's name>` finds this very directory — asked of the finders,
    nothing imported."""
    try:
        spec = importlib.util.find_spec(directory.name)
    except (ImportError, ValueError):
        return False
    return spec is not None and any(Path(p).resolve() == directory.resolve()
                                    for p in (spec.submodule_search_locations or ()))


def _corpus_names(module: CorpusStatuses) -> list[str]:
    names = getattr(module, "__all__", None)
    if names is None:
        names = [k for k in vars(module) if k.isupper()]
    return [n for n in names if isinstance(getattr(module, n, None), Status)]


def _basic(text: str) -> str:
    """A TOML basic string. JSON's escapes are TOML's, but for DEL (U+007F), which a TOML string may not hold."""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def _key(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else _basic(name)


def statuses_toml(module: CorpusStatuses) -> str:
    """The TOML form of a corpus's statuses (`statuses.toml`): a table a constant of `module`, in
    the order `_corpus_names` reads them — `text`, and `gender` where the status has one — then
    its estate aliases as the tables `child_estate_aliases` and `estate_aliases`, where it has any."""
    out: list[str] = []
    for name in _corpus_names(module):
        status: Status = getattr(module, name)
        lines = [f"[{_key(name)}]", f"text = {_basic(str(status))}"]
        if status.gender is not None:
            lines.append(f'gender = "{status.gender.name.lower()}"')
        out.append("\n".join(lines))
    for table, attribute in _ALIAS_TABLES.items():
        aliases: Mapping[str, str] = getattr(module, attribute, {})
        if aliases:
            rows = [f"{_key(k)} = {_basic(v)}" for k, v in aliases.items()]
            out.append("\n".join([f"[{table}]", *rows]))
    return "\n\n".join(out) + "\n"


@kept
def catalog() -> Mapping[str, Status]:
    """Every status constant, by name, in the catalog's order: the library's, and the
    workspace's corpus's (in its `__all__`'s order) before `LANDLORD`."""
    own = [(k, v) for k, v in globals().items() if k.isupper() and isinstance(v, Status)]
    module = corpus_statuses()
    theirs = [(k, getattr(module, k)) for k in _corpus_names(module)] if module is not None else []
    at = next(i for i, (k, _) in enumerate(own) if k == _CORPUS_BEFORE)
    return MappingProxyType(dict(own[:at] + theirs + own[at:]))


@dataclass(frozen=True)
class CorpusAliases:
    """The corpus's own estate aliases: a newborn's (`child`, the index below) and PSA's."""
    child: Mapping[str, str]
    estate: Mapping[str, str]


@kept
def corpus_aliases() -> CorpusAliases:
    module = corpus_statuses()
    return CorpusAliases(dict(getattr(module, "CHILD_ESTATE_ALIASES", {})),
                         dict(getattr(module, "ESTATE_ALIASES", {})))


@kept
def _child_index() -> dict[tuple[str, Gender], Status]:
    consts = dict(catalog())
    aliases = {**_ESTATE_ALIASES, **corpus_aliases().child}
    bases = {_split_role(name)[0] for name in consts}
    index: dict[tuple[str, Gender], Status] = {}
    for name, status in consts.items():
        base, role = _split_role(name)
        if base + "_PEASANT" in bases:
            base += "_PEASANT"
        estate = aliases.get(base, base)
        if role == "SOLDIER_WIFE":
            estate = "SOLDIER"  # her husband is a soldier, whatever her own estate
        if not (estate == "SOLDIER" or estate == "PEASANT"
                or estate.endswith("_PEASANT")):
            continue
        for child_gender, child_role in ((Gender.MALE, "SON"),
                                         (Gender.FEMALE, "DAUGHTER")):
            child = consts.get(f"{estate}_{child_role}")
            if child is not None:
                index[(str(status), child_gender)] = child
    return index


def child_status_for(parent_status: str | None,
                     child_gender: Gender | None) -> Status | None:
    """The Status a newborn inherits from `parent_status`, or None when the
    parent's estate is unknown / out of scope. Keyed by the status TEXT, so a
    free-text `status="ясачный крестьянин"` resolves like its constant; an
    unrecognised string is never guessed."""
    if parent_status is None or child_gender is None:
        return None
    return _child_index().get((str(parent_status), child_gender))
