"""What a `status=` says, and how a finding names the person it is about.

Shared by the two checks that compare statuses — `parent_status` (PSA, a status
against a relative's) and `residence_title` (RTV, a status against where the
person lives). Two halves:

* **Reading a status.** The words a status expression stands for (a constant of
  `verso.ru.domain.statuses`, a constant the file defines itself, a string literal),
  the status the book's `RecordDefaults` gives a person who states none, and the
  owner a status names. Moved out of `parent_status` unchanged on 2026-10-03,
  when RTV started asking the same questions of the Глуповы Горы books.
* **Wording a finding.** A person as the record writes them — «мужа (Захаръ
  Петровъ)» — and a constant of a stated estate in the other sex, offered as the
  fix. Until then PSA spoke in nominatives after «у» («у муж не указан status=»)
  and named RecordDefaults where a reader of the page wants the book.

Path-independent, like every DSL check: nothing here reads the file name.
"""

import ast
import re
from collections.abc import Mapping
from typing import NamedTuple

from verso.ru.domain import statuses
from verso.ru.domain.estates import estate_of
from verso.ru.linters.checks.file_bindings import record_defaults_call
from verso.core.i18n import Message
from verso.ru.messages import form, t

# --- the status catalog ---------------------------------------------------


class StatusTables(NamedTuple):
    """The workspace's status catalog as the checks read it, its names in alphabetical order:
    a text two constants spell is the later name's."""
    texts: Mapping[str, str]                # {constant: text}
    by_text: Mapping[str, str]              # {text: constant}
    genders: Mapping[str, str | None]       # {constant: "MALE"/"FEMALE"/None}


@statuses.kept
def tables() -> StatusTables:
    """The status catalog of the workspace (`statuses.catalog()`, its corpus's included), read
    at work time and kept for the workspace."""
    by_name: dict[str, str] = {}
    genders: dict[str, str | None] = {}
    for name, val in sorted(statuses.catalog().items()):
        by_name[name] = str(val)
        genders[name] = val.gender.name if val.gender is not None else None
    return StatusTables(by_name, {v: k for k, v in by_name.items()}, genders)


# Role suffixes of a constant name (`<ESTATE>_<ROLE>`), longest-first so
# DAUGHTER_MAIDEN, DAUGHTER_GIRL and LEGAL_WIFE win over the MAIDEN / GIRL / WIFE
# they end with.
ROLE_SUFFIXES: tuple[str, ...] = (
    "DAUGHTER_MAIDEN", "DAUGHTER_GIRL", "LEGAL_WIFE", "SOLDIER_WIFE", "WIFE_OF", "NEWCONVERT",
    "DAUGHTER", "WIDOWER", "MAIDEN", "FEMALE", "ZHONKA", "SPOUSE", "WIDOW",
    "MALE", "WIFE", "GIRL", "BOY", "SON",
)


def split_role(const_name: str) -> tuple[str, str]:
    """`KAZENNYJ_PEASANT_FEMALE` → (`KAZENNYJ_PEASANT`, `FEMALE`)."""
    for suffix in ROLE_SUFFIXES:
        if const_name.endswith("_" + suffix):
            return const_name[: -len(suffix) - 1], suffix
    return const_name, ""


# --- reading a status expression ------------------------------------------


def _name_id(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def file_bound(node: ast.expr | None, file_texts: Mapping[str, str]) -> bool:
    """A bare name the file binds itself — it shadows an imported constant of
    the same name, as it does when Python runs the file."""
    return isinstance(node, ast.Name) and node.id in file_texts


def words_of(node: ast.expr | None, file_texts: Mapping[str, str]) -> str | None:
    """The words a status expression stands for: a constant the file defines
    itself, one of `verso.ru.domain.statuses`, or a string literal."""
    if isinstance(node, ast.Name) and node.id in file_texts:
        return file_texts[node.id]
    ident = _name_id(node)
    if ident is not None:
        return tables().texts.get(ident)
    return _string_literal(node)


class Default(NamedTuple):
    """A status RecordDefaults would give: the `verso.ru.domain.statuses` constant
    it is, when it is one, and the words it stands for."""
    const: str | None
    text: str


def default_statuses(record_call: ast.Call, bindings: Mapping[str, ast.expr],
                     file_texts: Mapping[str, str]) -> dict[str, Default]:
    """`defaults=RecordDefaults(status_*=…)` on a record-list call — written in
    the call or bound by name at the top of the file, its values constants of
    `verso.ru.domain.statuses`, the file's own, or string literals."""
    defaults = record_defaults_call(record_call, bindings)
    if defaults is None:
        return {}
    out: dict[str, Default] = {}
    for key, kw in _kwargs(defaults).items():
        if not key.startswith("status_"):
            continue
        ident = _name_id(kw.value)
        if ident is not None and ident in tables().texts and not file_bound(kw.value, file_texts):
            out[key] = Default(ident, tables().texts[ident])
            continue
        text = words_of(kw.value, file_texts)
        if text is not None:
            out[key] = Default(tables().by_text.get(text), text)
    return out


# Roles whose RecordDefaults fallback differs from the plain by-gender one,
# mirroring RecordDefaults.apply_to_birth / _marriage (record_defaults.py).
ROLE_DEFAULT_KEYS: dict[str, tuple[str, ...]] = {
    "mother": ("status_mother", "status_female"),
    "bride": ("status_bride", "status_female"),
    "groom": ("status_groom", "status_male"),
}


def default_for(defaults: Mapping[str, Default], role: str, female: bool) -> Default | None:
    """The status RecordDefaults gives a person of this role and sex who
    states none, if the book sets one."""
    keys = ROLE_DEFAULT_KEYS.get(role, ("status_female",) if female else ("status_male",))
    for key in keys:
        default = defaults.get(key)
        if default is not None:
            return default
    return None


# --- the owner a status names ---------------------------------------------
#
# «крестьянин вотчины г-на Ноздрева», «земской вотчины малолетных детей гг.
# Головлевых», «крестьянин отчины гг. Головлевых» (the 1850s): the Глуповы Горы
# books name the owner after «вотчины» or «отчины», never after «помещика», so
# `estate_of` — which reads only the latter — finds no estate in them. The
# owner is read here, by the surname closing the phrase; the rest is honorific
# (г-на, гг., дворянина, малолетных детей, наследников) and differs from record
# to record for one owner.
#
# Deliberately NOT in `estate_of`: estate-conflicts shares it, and there the
# estate changing hands — Тентетниковъ → Ноздревъ in 1787, Ноздревъ → Головлевы in
# 1821/22 — reads as one person holding two: 13 findings on Глуповы Горы
# (measured 2026-10-01), 12 of them that handover, which the regional rules
# say is evidence of nothing. Inside one record the owner is one.
_VOTCHINA = re.compile(r"(?:в)?отчин[аыеу]\s+(?P<owner>.+?)\s*$")  # i18n: content — status words: vocabulary

LANDLORD_PREFIX = "landlord:"


def estate_words(text: str | None) -> str | None:
    """`estate_of`, plus the owner a «вотчины …» status names."""
    estate = estate_of(text)
    if estate is None and text and (m := _VOTCHINA.search(" ".join(text.split()))):
        return LANDLORD_PREFIX + m.group("owner").split()[-1]
    return estate


# --- wording a finding ----------------------------------------------------

NOM, GEN, DAT = 0, 1, 2

# A role as a finding writes it: the checks name it by its id, and its forms are the
# catalog's — `forms.role.<id>` of verso/ru/locales/<lang>.toml, a form for each case a message
# needs: who it is (nominative), whose status is missing (genitive, «у мужа»), to whom the fix
# applies (dative, «укажите мужу»), and the two that open a sentence. A language that keeps no
# cases (English) writes `nom` alone, which every case falls back to.
_CASES = ("nom", "gen", "dat")

NAME_PARAMS = (("name_orig", 0), ("patr_orig", 1), ("last_name_orig", 2))


def person_name(person_node: ast.Call | None) -> str:
    """The name a `person(…)` call writes — given name, patronymic, surname,
    as the scribe spelled them; empty when it writes none."""
    if person_node is None:
        return ""
    kwargs = _kwargs(person_node)
    parts: list[str] = []
    for kwarg, index in NAME_PARAMS:
        node = (kwargs[kwarg].value if kwarg in kwargs
                else person_node.args[index] if len(person_node.args) > index else None)
        text = _string_literal(node)
        if text:
            parts.append(text)
    return " ".join(parts)


def role_word(role: str, case: int = NOM, capital: bool = False) -> Message:
    """The role `role` (its id: `husband`, `household_member`) in `case` — the catalog's form."""
    return form("role", role, _CASES[case] + ("_capital" if capital else ""))


def who(role: str, person_node: ast.Call | None, case: int = NOM,
        capital: bool = False) -> Message:
    """«мужа (Захаръ Петровъ)» — the role in `case`, the name as written."""
    word = role_word(role, case, capital)
    name = person_name(person_node)
    return t("words.who", role=word, name=name) if name else word


def counterpart(const: str, *, female: bool, wife: bool = False,
                child: bool = False) -> str | None:
    """A constant of `const`'s estate for someone of the given sex and role, to
    offer as the fix — KAZENNYJ_PEASANT_FEMALE → KAZENNYJ_PEASANT_MALE for her
    husband. None when the catalog holds no such form; a fix is offered only
    when it can be written as a constant.

    A wife takes `<ESTATE>_WIFE` first — the Глуповы Горы books write her as
    her husband's («жена крестьянина вотчины г-на Ноздрева») — and a man the
    bare estate when there is no `_MALE` (NOZDREV_PEASANT is the man's form).
    """
    base, _ = split_role(const)
    stems = dict.fromkeys((base, base + "_PEASANT", base.removesuffix("_PEASANT")))
    if child:
        roles: tuple[str, ...] = ("DAUGHTER", "GIRL") if female else ("SON", "BOY")
    elif female:
        roles = ("WIFE", "LEGAL_WIFE", "FEMALE") if wife else ("FEMALE",)
    else:
        roles = ("MALE", "")
    sex = "FEMALE" if female else "MALE"
    for stem in stems:
        for role in roles:
            name = f"{stem}_{role}" if role else stem
            if tables().genders.get(name) == sex:
                return name
    return None


def offer(const: str) -> Message:
    """«казенный крестьянин» (KAZENNYJ_PEASANT_MALE) — a fix in words and in code."""
    return t("words.offer", words=tables().texts[const], constant=const)
