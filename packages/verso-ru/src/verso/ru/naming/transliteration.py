"""The res_names' transliteration: the profile `ru-v1`, our own table.

A res_name is a terraform address, so a changed letter moves every resource it names.
`ru-v1` is what the `transliterate` package (1.10.2, `translit(…, 'ru', reversed=True)`)
spelled until 0.1.0 — the 66 letters it changes, one character at a time — behind the
given names `names_map` spells whole; `tests/test_transliteration.py` holds it frozen by
its hash. A new spelling is a new profile (`ru-v2`) and switching to it is a decision of
its own, with `moved` blocks — never an edit of this table.

A corpus's own surnames the profile spells whole (they were the table's until then)
are the corpus's data — `[names]` of `<corpus>/transliteration.toml` — read before the
table (`corpus_spellings`); a name the table already spells is refused there.
"""
from __future__ import annotations

import functools
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from time import monotonic
from types import MappingProxyType
from typing import Literal, cast

from verso.core import workspace
from verso.core.corpus_data import CorpusDataError
from verso.ru.messages import t


_EMPTY: Mapping[str, str] = MappingProxyType({})

#: The soft and the hard sign: the letter after one of them is read in `after_sign`.
SIGNS = frozenset("ъь")
#: The hushing consonants: the letter after one of them is read in `after_hushing`.
HUSHING = frozenset("жчшщ")


def _is_cyrillic(char: str) -> bool:
    return "Ѐ" <= char <= "ӿ"


def _cased(latin: str, source: str, prev: str | None, nxt: str | None) -> str:
    """`latin` in the case of the letter `source` it spells: as is under a small letter; under a capital
    capitalized, or all capitals when a neighbouring letter of the word is a capital too (ЩЕГЛОВ → SHCHEGLOV)."""
    if not source.isupper():
        return latin
    if (nxt is not None and nxt.isupper()) or (prev is not None and prev.isupper()):
        return latin.upper()
    return latin[:1].upper() + latin[1:]


@dataclass(frozen=True)
class TranslitProfile:
    """A whole text first (`names`), else letter by letter.

    Without context tables (`ru-v1`) a letter is `chars` or itself, one at a time (`str.translate`).
    With them the text is read word by word — a word a run of Cyrillic letters, everything else passes as
    is and parts words — and a letter of a word takes the first that fits: an ending of the word (`final`,
    the longest, when a letter stands before it), the first letter (`initial`), a letter after ь/ъ
    (`after_sign`), after ж ч ш щ (`after_hushing`), `chars`, else itself. Context tables are keyed by small
    letters; the case of the source letter carries over (`_cased`). `strip` — characters dropped first
    (the combining acute)."""
    name: str
    names: Mapping[str, str]
    chars: Mapping[str, str]
    initial: Mapping[str, str] = _EMPTY
    after_sign: Mapping[str, str] = _EMPTY
    after_hushing: Mapping[str, str] = _EMPTY
    final: Mapping[str, str] = _EMPTY
    strip: str = ""
    _table: dict[int, str] = field(init=False, repr=False, compare=False)
    _endings: tuple[str, ...] = field(init=False, repr=False, compare=False)
    _contextual: bool = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_table", {ord(c): latin for c, latin in self.chars.items()})
        object.__setattr__(self, "_endings", tuple(sorted(self.final, key=len, reverse=True)))
        object.__setattr__(self, "_contextual",
                           bool(self.initial or self.after_sign or self.after_hushing or self.final or self.strip))

    def __call__(self, text: str) -> str:
        if text in self.names:
            return self.names[text]
        if not self._contextual:
            return text.translate(self._table)
        if self.strip:
            text = "".join(c for c in text if c not in self.strip)
            if text in self.names:
                return self.names[text]
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            if not _is_cyrillic(text[i]):
                out.append(text[i])
                i += 1
                continue
            j = i
            while j < n and _is_cyrillic(text[j]):
                j += 1
            out.append(self._word(text[i:j]))
            i = j
        return "".join(out)

    def _word(self, word: str) -> str:
        if word in self.names:
            return self.names[word]
        low = word.lower()
        n = len(word)
        out: list[str] = []
        i = 0
        while i < n:
            ending = next((e for e in self._endings if i > 0 and i == n - len(e) and low.endswith(e)), None)
            if ending is not None:
                out.append(_cased(self.final[ending], word[i], word[i - 1], None))
                break
            c, prev = low[i], low[i - 1] if i else None
            if i == 0 and c in self.initial:
                latin = self.initial[c]
            elif prev in SIGNS and c in self.after_sign:
                latin = self.after_sign[c]
            elif prev in HUSHING and c in self.after_hushing:
                latin = self.after_hushing[c]
            elif c in self.chars:
                latin = self.chars[c]
            else:
                out.append(word[i])
                i += 1
                continue
            out.append(_cased(latin, word[i], word[i - 1] if i else None, word[i + 1] if i + 1 < n else None))
            i += 1
        return "".join(out)


_PROFILE_KEYS = frozenset({"name", "names", "chars", "initial", "after_sign", "after_hushing", "final", "strip"})


def profile_data(resource: Traversable | Path) -> dict[str, object]:
    """A profile's TOML as data: its tables and `strip`; an unknown key is refused."""
    data = tomllib.loads(resource.read_text(encoding="utf-8"))
    unknown = sorted(set(data) - _PROFILE_KEYS)
    if unknown:
        raise ValueError(str(t("transliteration.unknown_key", path=resource, unknown=unknown[0])))
    return data


def load_profile(resource: Traversable | Path) -> TranslitProfile:
    """A transliteration profile from its TOML (`profile_data`)."""
    data = profile_data(resource)

    def table(key: str) -> Mapping[str, str]:
        raw = cast(Mapping[str, object], data.get(key, {}))
        return MappingProxyType({str(k): str(v) for k, v in raw.items()})

    return TranslitProfile(str(data["name"]), table("names"), table("chars"), initial=table("initial"),
                           after_sign=table("after_sign"), after_hushing=table("after_hushing"), final=table("final"),
                           strip=str(data.get("strip", "")))


# The 66 letters `transliterate` changed, in code point order.
_RU_V1_CHARS: dict[str, str] = {
    'Ё': 'E',
    'А': 'A',
    'Б': 'B',
    'В': 'V',
    'Г': 'G',
    'Д': 'D',
    'Е': 'E',
    'Ж': 'Zh',
    'З': 'Z',
    'И': 'I',
    'Й': 'J',
    'К': 'K',
    'Л': 'L',
    'М': 'M',
    'Н': 'N',
    'О': 'O',
    'П': 'P',
    'Р': 'R',
    'С': 'S',
    'Т': 'T',
    'У': 'U',
    'Ф': 'F',
    'Х': 'H',
    'Ц': 'Ts',
    'Ч': 'Ch',
    'Ш': 'Sh',
    'Щ': 'Sch',
    'Ъ': "'",
    'Ы': 'Y',
    'Ь': "'",
    'Э': 'E',
    'Ю': 'Ju',
    'Я': 'Ja',
    'а': 'a',
    'б': 'b',
    'в': 'v',
    'г': 'g',
    'д': 'd',
    'е': 'e',
    'ж': 'zh',
    'з': 'z',
    'и': 'i',
    'й': 'j',
    'к': 'k',
    'л': 'l',
    'м': 'm',
    'н': 'n',
    'о': 'o',
    'п': 'p',
    'р': 'r',
    'с': 's',
    'т': 't',
    'у': 'u',
    'ф': 'f',
    'х': 'h',
    'ц': 'ts',
    'ч': 'ch',
    'ш': 'sh',
    'щ': 'sch',
    'ъ': "'",
    'ы': 'y',
    'ь': "'",
    'э': 'e',
    'ю': 'ju',
    'я': 'ja',
    'ё': 'e',
}

names_map: dict[str, str] = {
    'Аверкий': 'Averkiy',
    'Авдей': 'Avdey',
    'Агафья': 'Agafya',
    'Ананий': 'Ananiy',
    'Анастасия': 'Anastasia',
    'Андрей': 'Andrey',
    'Анисья': 'Anisya',
    'Алексей': 'Alexey',
    'Артемий': 'Artemiy',
    'Афанасий': 'Afanasy',
    'Василий': 'Vasily',
    'Георгий': 'Georgy',
    'Гликерия': 'Glikeria',
    'Гордей': 'Gordey',
    'Григорий': 'Grigory',
    'Дарья': 'Darya',
    'Дементий': 'Dementiy',
    'Дмитрий': 'Dmitry',
    'Евдокия': 'Evdokiya',
    'Евлампий': 'Evlampiy',
    'Евтихий': 'Evtihiy',
    'Евтропий': 'Evtropiy',
    'Елисей': 'Elisey',
    'Емельян': 'Yemelyan',
    'Еремей': 'Yeremey',
    'Ермолай': 'Ermolay',
    'Ефимия': 'Efimiya',
    'Ефросиния': 'Efrosiniya',
    'Зиновий': 'Zinovy',
    'Игнатий': 'Ignatiy',
    'Исаакий': 'Isaakiy',
    'Илья': 'Ilya',
    'Кондратий': 'Kondratiy',
    'Лаврентий': 'Lavrentiy',
    'Лазарь': 'Lazar',
    'Леонтий': 'Leontiy',
    'Лукьян': 'Lukyan',
    'Лукерья': 'Lukerya',
    'Любовь': 'Lyubov',
    'Кузьма': 'Kuzma',
    'Ксения': 'Ksenia',
    'Максим': 'Maxim',
    'Матвей': 'Matvey',
    'Мария': 'Maria',
    'Мелания': 'Melania',
    'Мефодий': 'Mefodiy',
    'Михаил': 'Mikhail',
    'Моисей': 'Moisey',
    'Наталия': 'Natalia',
    'Наталья': 'Natalya',
    'Николай': 'Nikolay',
    'Ольга': 'Olga',
    'Пелагея': 'Pelageya',
    'Порфирий': 'Porfiry',
    'Прасковья': 'Praskovya',
    'Прокопий': 'Prokopy',
    'Савелий': 'Savely',
    'Семен': 'Semyon',
    'Сергей': 'Sergey',
    'Сисой': 'Sisoy',
    'Софья': 'Sofya',
    'Татьяна': 'Tatyana',
    'Терентий': 'Terenty',
    'Тимофей': 'Timofey',
    'Ульяна': 'Ulyana',
    'Феврония': 'Fevroniya',
    'Феодосий': 'Feodosiy',
    'Феодосия': 'Feodosiya',
    'Юлий': 'Yuliy',
    'Яков': 'Yakov',
}


RU_V1 = TranslitProfile("ru-v1", MappingProxyType(dict(names_map)), MappingProxyType(_RU_V1_CHARS))

#: The profile of the names a person reads: BGN/PCGN without apostrophes, data of the package.
RU_V2_FILE: Traversable = files("verso.ru.naming") / "data" / "translit" / "ru-v2.toml"
RU_V2 = load_profile(RU_V2_FILE)

PROFILES: Mapping[str, TranslitProfile] = MappingProxyType({RU_V1.name: RU_V1, RU_V2.name: RU_V2})


TRANSLITERATION_FILE = "transliteration.toml"


@functools.cache
def _spellings_path() -> Path | None:
    """Where the workspace's corpus keeps its spellings (asked once per workspace)."""
    corpus = workspace.current().corpus_dir
    return None if corpus is None else corpus / TRANSLITERATION_FILE


# The spellings read, with the stamp (mtime, size) of the file they were read from.
_spellings_read: dict[Path, tuple[tuple[int, int], Mapping[str, str]]] = {}


def corpus_spellings() -> Mapping[str, str]:
    """The surnames the workspace's corpus spells whole (`[names]` of its transliteration.toml);
    none without the file. Read again when the file changes, as the places and the estates are."""
    path = _spellings_path()
    try:
        st = path.stat() if path is not None else None
    except FileNotFoundError:
        st = None
    if path is None or st is None:
        return MappingProxyType({})
    stamp = (st.st_mtime_ns, st.st_size)
    read = _spellings_read.get(path)
    if read is None or read[0] != stamp:
        read = (stamp, _read_spellings(path))
        _spellings_read[path] = read
    return read[1]


def _read_spellings(path: Path) -> Mapping[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise CorpusDataError(t("transliteration.not_toml", path=path, e=e)) from None
    unknown = sorted(set(data) - {"names"})
    if unknown:
        raise CorpusDataError(t("transliteration.unknown_key", path=path, unknown=unknown[0]))
    names = data.get("names", {})
    if not isinstance(names, dict):
        raise CorpusDataError(t("transliteration.names_not_table", path=path))
    for name, latin in names.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(latin, str):
            raise CorpusDataError(t("transliteration.name_not_string", path=path, name=name))
        if name in RU_V1.names:
            raise CorpusDataError(t("transliteration.profile_spells", path=path, name=name, profile=RU_V1.name))
    return MappingProxyType(dict(names))  # pyright: ignore[reportUnknownArgumentType]


workspace.on_change(_spellings_path.cache_clear)


#: A role of the transliteration: the res_names' (`address` — a Terraform address, frozen) or the names a person
#: reads (`display` — a Geni profile's Latin names).
type Role = Literal["address", "display"]


#: The profile a role of a workspace of schema 7 spells by where `[translit]` names none.
DEFAULT_PROFILE = RU_V2.name


def profile_of(role: Role) -> TranslitProfile:
    """The profile a role spells by in the current workspace: `ru-v1` for both in a workspace of schema 6 or older; in one
    of schema 7, the profile `[translit]` names for the role, else `ru-v2`. A name no profile has is a `WorkspaceError`."""
    ws = workspace.current()
    if ws.translit is None:
        return RU_V1
    name = getattr(ws.translit, role) or DEFAULT_PROFILE
    profile = PROFILES.get(name)
    if profile is None:
        raise workspace.WorkspaceError(t("transliteration.unknown_profile", config=ws.root / workspace.CONFIG,
                                         key=f"translit.{role}", profile=name, known=", ".join(PROFILES)))
    return profile


#: The workspace whose corpus was last seen without a `transliteration.toml`, and until when that holds (`spelling`).
_no_old_spellings: tuple[workspace.Workspace, float] | None = None


def _refuse_old_spellings(ws: workspace.Workspace, recheck: float) -> None:
    """Refuse a `transliteration.toml` still standing in the corpus of a workspace of schema 7. Looked at again at most every
    `recheck` seconds: `spelling` is asked once a word, and the look is a `stat`."""
    global _no_old_spellings
    seen = _no_old_spellings
    if seen is not None and seen[0] is ws and monotonic() < seen[1]:
        return
    old = _spellings_path()
    if old is not None and old.is_file():
        raise CorpusDataError(t("transliteration.moved_to_layer", path=old))
    _no_old_spellings = (ws, monotonic() + recheck)


def spelling(role: Role) -> Callable[[str], str]:
    """The role's spelling: a word the workspace spells whole, else its profile. The words spelled whole are, in a
    workspace of schema 6 or older, the corpus's `transliteration.toml` (`corpus_spellings`, `ru-v1`'s alone); in one of
    schema 7, the rules of the role's profile in the names layers (`verso.ru.naming.translit_layers`) — and a
    `transliteration.toml` still standing in its corpus is refused: its rules are the layers' now."""
    ws = workspace.current()
    profile = profile_of(role)
    if ws.translit is None:
        def spell_legacy(name: str) -> str:
            spelled = corpus_spellings().get(name)
            return spelled if spelled is not None else profile(name)
        return spell_legacy
    from verso.ru.naming import translit_layers
    _refuse_old_spellings(ws, translit_layers.RECHECK_SECONDS)
    by_key = translit_layers.rules(ws)
    tag = profile.name

    def spell(name: str) -> str:
        rule = by_key.get((tag, name))
        return rule.latin if rule is not None and rule.latin is not None else profile(name)
    return spell


def address() -> Callable[[str], str]:
    """The res_names' spelling (`spelling("address")`)."""
    return spelling("address")


def display() -> Callable[[str], str]:
    """The spelling of the names a person reads (`spelling("display")`)."""
    return spelling("display")


def display_name(name: str) -> str:
    """A name as a person reads it: the display role, asked anew each time (a rule edited is read on the next name)."""
    return display()(name)


def cyrillic_to_latin(name: str) -> str:
    """A name as the res_names spell it: the address role."""
    return address()(name)


def generate_res_name(name: str) -> str:
    return (
        cyrillic_to_latin(name)
        .replace(" ", "_")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .replace("'", "")
        .replace("?", "")
        .replace("\"", "")
        .replace(";", "")
        .replace(".", "")
        .lower()
    )
