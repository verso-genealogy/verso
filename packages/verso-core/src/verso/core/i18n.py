"""The interface's language and its catalogs: a message is a key and its parameters, and its
text is the catalog's, in the language of the moment it is read.

A package that speaks to a person keeps its catalogs as package data, `<package>/locales/<lang>.toml`
— English (`en`) is the source language, every other is a translation —, and calls `t("key",
name=value)` from its own `messages` module, which gives a `Message`. The text is put together when
the message is read (`str()`), so an exception raised in one language and printed after the
language changed (a test, Verso switching workspaces) speaks the language of the print.

* **The language** (`language()`): the innermost `use(lang)`, else `VERSO_LANG`, else the host's
  answer (`configure(configured=…)`: the workspace's `[i18n] locale`), else `en`. The system's
  `LANG`/`LC_*` say nothing. A host that fails to answer gives `en`; an unknown language named by
  `use`/`VERSO_LANG` is refused with the list of languages — the one path that raises.
* **A catalog** is TOML: `schema = 1`, in a translation `untranslated = [keys]` (those the
  language still prints in English), and tables whose dotted path is the key (`[workspace]
  not_found = "…{here}…"`). A table of plural categories (`one`, `few`, `many`, `other`) is one
  message, chosen by its `count` parameter (CLDR's rules for en and ru, `plural()`). Parameters
  are `{name}`; a literal brace is `{{` `}}`.
* **Rendering never raises**: a key missing in the language falls back to English, and missing in
  English, or a catalog that does not read, or a parameter missing, prints `key {params}` — the
  error a message was raised for is never hidden by the rendering of its message.
* **Language packs** add a language without touching a distribution: an entry point of the group
  `verso.locales` gives a `LocalePack`, and a workspace enables it by name (`[i18n] packs`). A pack
  for a language a package ships is refused: the shipped catalogs are not overridden.

This module imports nothing of verso: the App keeps a byte-for-byte copy (`verso.app.i18n`),
and each host tells it where its language comes from.
"""
from __future__ import annotations

import ast
import os
import re
import string
import threading
import tomllib
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib import metadata, resources
from typing import Any

ENV = "VERSO_LANG"
GROUP = "verso.locales"
SOURCE = "en"
_SHIPPED_RULES = ("en", "ru")
_CATEGORIES = frozenset({"zero", "one", "two", "few", "many", "other"})

type Template = str | Mapping[str, str]


class CatalogError(ValueError):
    """A catalog that does not read, a language nobody ships, a pack that would override one."""


@dataclass(frozen=True)
class Message:
    """A message of `package`'s catalogs: its key and parameters, rendered when read."""
    package: str
    key: str
    params: Mapping[str, object] = field(default_factory=dict[str, object])

    def __str__(self) -> str:
        return render(self)

    def __hash__(self) -> int:
        """Equal messages hash alike — a parameter may be a list, so by its repr."""
        return hash((self.package, self.key, tuple(sorted((k, repr(v)) for k, v in self.params.items()))))


@dataclass(frozen=True)
class LocalePack:
    """A language added by an entry point of `verso.locales`: its catalogs, by package, each a
    resource `"<import package>:<path in it>"`, and its plural rule (None: English's)."""
    name: str
    language: str
    catalogs: Mapping[str, str]
    plural: Callable[[int], str] | None = None


# ---------------------------------------------------------------- where the language comes from

def _none() -> str | None:
    return None


def _no_packs() -> tuple[str, ...]:
    return ()


_configured: Callable[[], str | None] = _none
_packs: Callable[[], tuple[str, ...]] = _no_packs
# The languages `use()` speaks, innermost last — per context: two threads, or two tasks, each speak
# their own.
_using: ContextVar[tuple[str, ...]] = ContextVar("i18n_using", default=())
_added: list[tuple[LocalePack, ...]] = []
# Read catalogs by (package, language): the templates by key, and the keys left untranslated.
_catalogs: dict[tuple[str, str], tuple[dict[str, Template], frozenset[str]]] = {}
# A server answers in threads: a catalog is read once, whole, under this lock.
_reading = threading.RLock()


def configure(*, configured: Callable[[], str | None], packs: Callable[[], tuple[str, ...]] = _no_packs) -> None:
    """Where the language and the enabled packs come from when nothing overrides them (the host's
    workspace); asked at each question, so a host's answer may change between two."""
    global _configured, _packs
    _configured, _packs = configured, packs
    forget()


def forget() -> None:
    """Drop the catalogs read so far: they are read again at the next question."""
    with _reading:
        _catalogs.clear()


@contextmanager
def use(lang: str) -> Generator[None]:
    """Speak `lang` until the block ends."""
    token = _using.set((*_using.get(), lang))
    try:
        yield
    finally:
        _using.reset(token)


@contextmanager
def adding(*packs: LocalePack) -> Generator[None]:
    """Enable `packs` beside the configured ones until the block ends (tests)."""
    _added.append(packs)
    forget()
    try:
        yield
    finally:
        _added.pop()
        forget()


def _found(names: tuple[str, ...]) -> Iterator[LocalePack]:
    """The packs `names` enables, by entry point; refused when one is not installed or no pack."""
    if not names:
        return
    found = {ep.name: ep for ep in metadata.entry_points(group=GROUP)}
    for name in names:
        if name not in found:
            raise CatalogError(f"language pack «{name}» is not installed")
        pack = found[name].load()
        if not isinstance(pack, LocalePack):
            raise CatalogError(f"entry point «{name}» of {GROUP} is no LocalePack")
        yield pack


def _host_packs() -> tuple[str, ...]:
    try:
        return tuple(_packs())
    except Exception:  # a host that cannot answer enables no pack
        return ()


def _enabled_packs() -> Iterator[LocalePack]:
    for added in _added:
        yield from added
    try:
        packs = list(_found(_host_packs()))
    except CatalogError:  # rendering forgives a pack that does not load; `check` says why
        packs = []
    yield from packs


def _known() -> tuple[str, ...]:
    return tuple(dict.fromkeys((*_SHIPPED_RULES, *(p.language for p in _enabled_packs()))))


def _unknown(lang: str, known: Iterable[str]) -> CatalogError:
    return CatalogError(f"unknown language «{lang}» — languages: {', '.join(known)}")


def language() -> str:
    """The language of the moment: `use()`, `VERSO_LANG`, the host's, else English."""
    using = _using.get()
    named = using[-1] if using else os.environ.get(ENV) or None
    if named is not None:
        if named not in _SHIPPED_RULES and named not in _known():
            raise _unknown(named, _known())
        return named
    try:
        return _configured() or SOURCE
    except Exception:  # a workspace that does not read speaks English
        return SOURCE


def check_settings(locale: str | None, packs: Iterable[str]) -> None:
    """Refuse a host's settings that rendering would forgive in silence: a pack not installed, one
    that is no LocalePack or would override a catalog a package ships, and a `locale` nobody speaks.
    A host asks it when it reads its settings (the workspace, at `verso.toml`'s load)."""
    enabled = [*(p for added in _added for p in added), *_found(tuple(packs))]
    for pack in enabled:
        for package in pack.catalogs:
            if _shipped(package, pack.language) is not None:
                raise CatalogError(f"language pack «{pack.name}»: {package} ships «{pack.language}» "
                                   "— a pack cannot override it")
    known = tuple(dict.fromkeys((*_SHIPPED_RULES, *(p.language for p in enabled))))
    if locale and locale not in known:
        raise _unknown(locale, known)


def check() -> None:
    """`check_settings` of the host's settings, and the language named for the moment — `use()`,
    `VERSO_LANG` — refused when nobody speaks it (`verso.core.cli` asks at start, `--lang` included)."""
    try:
        locale = _configured()
    except Exception:  # a host that does not read says so itself
        locale = None
    check_settings(locale, _host_packs())
    language()


# ---------------------------------------------------------------- catalogs

def _flatten(table: Mapping[str, Any], prefix: str, out: dict[str, Template], where: str) -> None:
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, str):
            out[key] = value
        elif isinstance(value, dict) and value and set(value) <= _CATEGORIES and "other" in value \
                and all(isinstance(v, str) for v in value.values()):  # pyright: ignore[reportUnknownVariableType]
            out[key] = dict(value)  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(value, dict):
            _flatten(value, f"{key}.", out, where)  # pyright: ignore[reportUnknownArgumentType]
        else:
            raise CatalogError(f"{where}: «{key}» — expected a string or a table")


def _read(where: str, text: str) -> tuple[dict[str, Template], frozenset[str]]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise CatalogError(f"{where}: does not read as TOML: {e}") from None
    if data.pop("schema", None) != 1:
        raise CatalogError(f"{where}: «schema» — expected 1")
    untranslated = data.pop("untranslated", [])
    if not isinstance(untranslated, list) or not all(isinstance(k, str) for k in untranslated):  # pyright: ignore[reportUnknownVariableType]
        raise CatalogError(f"{where}: «untranslated» — expected a list of keys")
    out: dict[str, Template] = {}
    _flatten(data, "", out, where)
    return out, frozenset(untranslated)  # pyright: ignore[reportUnknownArgumentType]


def _shipped(package: str, lang: str) -> str | None:
    try:
        path = resources.files(package).joinpath("locales", f"{lang}.toml")
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        return None


def _load(package: str, lang: str) -> tuple[dict[str, Template], frozenset[str]]:
    """`package`'s catalog of `lang`, shipped or a pack's, and its untranslated keys. A shipped
    catalog never asks the packs: a pack cannot override it (`check_settings` refuses one that
    would), and one that does not load blanks no message of a language a package ships."""
    shipped = _shipped(package, lang)
    if shipped is not None:
        return _read(f"{package}/locales/{lang}.toml", shipped)
    if lang == SOURCE:
        return {}, frozenset()
    packs = [p for p in _enabled_packs() if p.language == lang and package in p.catalogs]
    if not packs:
        return {}, frozenset()
    resource = packs[0].catalogs[package]
    module, _, path = resource.partition(":")
    return _read(resource, resources.files(module).joinpath(path).read_text(encoding="utf-8"))


def _cached(package: str, lang: str) -> tuple[dict[str, Template], frozenset[str]]:
    key = (package, lang)
    found = _catalogs.get(key)
    if found is None:
        with _reading:
            found = _catalogs.get(key)
            if found is None:
                found = _catalogs[key] = _load(package, lang)
    return found


def catalog(package: str, lang: str) -> Mapping[str, Template]:
    """`package`'s catalog of `lang`: its keys, flat, each a template or a table of plural forms;
    empty when nobody gives one."""
    return dict(_cached(package, lang)[0])


def untranslated(package: str, lang: str) -> frozenset[str]:
    """The keys `lang` still prints in English (its catalog's `untranslated`)."""
    return _cached(package, lang)[1]


def languages(package: str) -> tuple[str, ...]:
    """The languages `package` speaks: the catalogs it ships, then the enabled packs'."""
    shipped = [lang for lang in _SHIPPED_RULES if _shipped(package, lang) is not None]
    try:
        root = resources.files(package).joinpath("locales")
        shipped += sorted(p.name[:-5] for p in root.iterdir()
                          if p.name.endswith(".toml") and p.name[:-5] not in shipped)
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    return tuple(dict.fromkeys((*shipped, *(p.language for p in _enabled_packs() if package in p.catalogs))))


# ---------------------------------------------------------------- plurals and rendering

def _ru_plural(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def _en_plural(n: int) -> str:
    return "one" if n == 1 else "other"


def _plural_rule(lang: str) -> Callable[[int], str]:
    """`lang`'s plural rule: en and ru are ours, a pack's language its pack's, any other English's."""
    if lang == "ru":
        return _ru_plural
    if lang != "en":
        for pack in _enabled_packs():
            if pack.language == lang and pack.plural is not None:
                return pack.plural
    return _en_plural


def plural(lang: str, n: int) -> str:
    """CLDR's plural category of the integer `n` in `lang`: en and ru are ours, a pack's language
    its pack's, any other English's."""
    return _plural_rule(lang)(n)


_FORM = re.compile(r"^(forms\.[^.]+\.[^.]+)\.[a-z]+?(_capital)?$")


def _template(package: str, lang: str, key: str) -> Template | None:
    """`key`'s template in `lang`, else English's; a word's form (`forms.<kind>.<id>.<case>`) a
    language does not keep is its nominative."""
    found = _lookup(package, lang, key)
    if found is None and (form := _FORM.match(key)) is not None:
        found = _lookup(package, lang, f"{form[1]}.nom{form[2] or ''}")
    return found


def _lookup(package: str, lang: str, key: str) -> Template | None:
    for each in dict.fromkeys((lang, SOURCE)):
        try:
            found, left = _cached(package, each)
        except Exception:  # a catalog that does not read hides no message
            continue
        if key in found and key not in left:
            return found[key]
    return None


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


def render(message: Message, lang: str | None = None) -> str:
    """The message's text in `lang` (else the language of the moment); never raises."""
    fallback = f"{message.key} {dict(message.params)}"
    try:
        lang = lang or language()
    except Exception:  # an unknown language speaks English here; language() says why
        lang = SOURCE
    try:
        template = _template(message.package, lang, message.key)
        if template is None:
            return fallback
        if not isinstance(template, str):
            count = message.params.get("count")
            category = plural(lang, count) if isinstance(count, int) else "other"
            template = template.get(category) or template["other"]
        if not _fields(template) <= set(message.params):
            return fallback
        return template.format(**message.params)
    except Exception:  # the rendering of a message never hides its error
        return fallback


# ---------------------------------------------------------------- the catalogs against the code

def categories(lang: str) -> frozenset[str]:
    """The plural categories `lang`'s catalogs write: its rule's, and `other`, the fallback — what a
    page that renders a catalog's plural forms itself is told (`Intl.PluralRules`' names)."""
    rule = _plural_rule(lang)
    return frozenset({rule(n) for n in range(200)} | {"other"})


_categories = categories


def _template_fields(template: Template) -> frozenset[str]:
    forms = [template] if isinstance(template, str) else list(template.values())
    return frozenset(name for form in forms for _, name, _, _ in string.Formatter().parse(form) if name)


def _calls(package: str, sources: Path) -> list[tuple[str, int, str | None, frozenset[str] | None]]:
    """Every `t(…)` of `<package>.messages` under `sources`: where, its key (None: not a literal) and
    its parameters (None: a `**` the check cannot read)."""

    out: list[tuple[str, int, str | None, frozenset[str] | None]] = []
    for path in sorted(sources.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        local = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                 and n.module == f"{package}.messages" for a in n.names if a.name == "t"}
        if not local:
            continue
        rel = path.relative_to(sources).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in local:
                first = node.args[0] if node.args else None
                key = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
                params = None if any(k.arg is None for k in node.keywords) \
                    else frozenset(k.arg for k in node.keywords if k.arg is not None)
                out.append((rel, node.lineno, key, params))
    return out


def _set(names: Iterable[str]) -> str:
    return "{" + ", ".join(sorted(names)) + "}"


def problems(package: str, sources: Path, *, computed: Callable[[str], bool] | None = None) -> list[str]:
    """What of `package`'s catalogs disagrees with its code under `sources` and with English: a
    key no literal, a key or a parameter English lacks, an English key nobody calls, a translation
    missing (and not marked untranslated), its parameters not English's, a key marked untranslated
    that is translated, plural forms not the language's. A key the code builds (`computed`: a linter's
    `CODE.variant`) is never called by name, so nobody calling it is no problem."""
    out: list[str] = []
    try:
        english, _ = _load(package, SOURCE)
    except CatalogError as e:
        return [str(e)]
    called: set[str] = set()
    for rel, line, key, params in _calls(package, sources):
        if key is None:
            out.append(f"{rel}:{line}: the key is no literal")
            continue
        called.add(key)
        if key not in english:
            out.append(f"{rel}:{line}: «{key}» — no such key in en")
        elif params is not None and params != _template_fields(english[key]):
            out.append(f"{rel}:{line}: «{key}» — params {_set(params)}, the template's {_set(_template_fields(english[key]))}")
    out += [f"en: «{key}» — no call" for key in english
            if key not in called and not key.startswith("forms.") and not (computed and computed(key))]
    for lang in languages(package):
        try:
            found, left = _load(package, lang)
        except CatalogError as e:
            out.append(str(e))
            continue
        for key, template in found.items():
            if not isinstance(template, str) and frozenset(template) != _categories(lang):
                out.append(f"{lang}: «{key}» — plural forms {', '.join(sorted(template))}, "
                           f"the language's {', '.join(sorted(_categories(lang)))}")
        if lang == SOURCE:
            continue
        for key, template in english.items():
            if key in left:
                if key in found:
                    out.append(f"{lang}: «{key}» — untranslated, yet translated")
            elif key not in found:
                out.append(f"{lang}: «{key}» — missing, and not untranslated")
            elif _template_fields(found[key]) != _template_fields(template):
                out.append(f"{lang}: «{key}» — params {_set(_template_fields(found[key]))}, "
                           f"English's {_set(_template_fields(template))}")
    return out
