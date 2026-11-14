"""The DSL described: its functions, the parameters each takes, the constants a field
may be (what the App requires of the library, from `verso_app_dsl.signatures` before 0.1.0).

Read off the real functions with `inspect.signature`, never restated: a list of
`birth()`'s parameters copied here would be the eighth place the corpus spells
them, and the first to drift. `describe()` is what the review page reads as its
catalog (`/api/catalog`).
"""
from __future__ import annotations

import dataclasses
import inspect
from calendar import Month
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import Any

from verso.ru.domain import factories
from verso.ru.domain import causes_of_death, marital_status, statuses
from verso.ru.domain.record_defaults import RecordDefaults
from verso.ru.domain.cause_of_death import CauseOfDeath
from verso.ru.domain.side import Side
from verso.ru.dsl.calls import RECORD_FUNCS as RECORD_FUNCS  # re-exported: the review table's rows (the App reads it here)
from verso.ru.dsl.records import births, census, deaths, marriages, name_lists
from verso.ru.gender import Gender
from verso.ru.relationship import Relationship, gender_from_relationship, relative

# The records whose `reviewed=` the corpus writes right after the positionals.
VITAL_FUNCS = frozenset({"birth", "christening", "death", "marriage"})
# The file-level collections, each carrying the source's provenance.
CONTAINER_FUNCS = frozenset({"birth_records", "death_records", "marriage_records",
                             "census_records", "name_list_records"})

KIND = {"birth": "births", "christening": "births", "death": "deaths",
        "marriage": "marriages", "household": "census", "listed_person": "name_lists"}

FUNCS: dict[str, Callable[..., Any]] = {
    "birth": births.birth, "christening": births.christening,
    "birth_month": births.birth_month, "birth_month_year": births.birth_month_year,
    "birth_records": births.birth_records,
    "death": deaths.death, "death_month": deaths.death_month,
    "death_month_year": deaths.death_month_year, "death_records": deaths.death_records,
    "marriage": marriages.marriage, "marriage_month": marriages.marriage_month,
    "marriage_month_year": marriages.marriage_month_year,
    "marriage_records": marriages.marriage_records,
    "household": census.household, "member": census.member,
    "census_records": census.census_records,
    "listed_person": name_lists.listed_person, "name_list_records": name_lists.name_list_records,
    "person": factories.person, "page": factories.page, "book": factories.book,
    "relative": relative,
    # A book's defaults: what its records leave empty becomes these.
    "RecordDefaults": RecordDefaults,
}

KNOWN_FUNCS = frozenset(FUNCS)


@dataclass(frozen=True)
class Param:
    name: str
    order: int                # position in the signature, keyword-only included
    positional: bool          # may be passed positionally
    person: bool              # annotated `Person` — a slot the editor opens as a block
    has_default: bool


@dataclass(frozen=True)
class Signature:
    func: str
    params: tuple[Param, ...]
    varargs: str | None       # `*records`, `*members` …
    varargs_order: int | None

    def param(self, name: str) -> Param | None:
        for p in self.params:
            if p.name == name:
                return p
        return None

    def positional_param(self, index: int) -> Param | None:
        """The parameter the `index`-th positional argument binds to, or None
        when it falls into `*varargs`."""
        positional = [p for p in self.params if p.positional]
        return positional[index] if index < len(positional) else None


@cache
def signature(func: str) -> Signature | None:
    fn = FUNCS.get(func)
    if fn is None:
        return None
    params: list[Param] = []
    varargs: str | None = None
    varargs_order: int | None = None
    for order, (name, p) in enumerate(inspect.signature(fn).parameters.items()):
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            varargs, varargs_order = name, order
            continue
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        params.append(Param(
            name=name, order=order,
            positional=p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                  inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and varargs is None,
            person="Person" in str(p.annotation),
            has_default=p.default is not inspect.Parameter.empty,
        ))
    return Signature(func, tuple(params), varargs, varargs_order)


# ---------------------------------------------------------------- constants

@dataclass(frozen=True)
class Constant:
    code: str                 # what the DSL writes: «PEASANT_WIDOW», «Gender.MALE»
    text: str                 # what it means: «крестьянская вдова», «male»
    module: str               # where `import_name` is imported from
    import_name: str          # the name the file must have bound


# The module each catalog's constants are imported from, as DSL v1 writes it: the
# facade and its catalogs — never `module.__name__` (verso.ru.domain.…). A corpus's own
# statuses come from its `corpus.statuses`.
DSL_IMPORTS: dict[str, str] = {
    "status": "verso.ru.dsl.statuses",
    "cause": "verso.ru.dsl.causes_of_death",
    "marital": "verso.ru.dsl.marital_status",
    "gender": "verso.ru.dsl",
    "relationship": "verso.ru.dsl",
    "role": "verso.ru.dsl",
    "side": "verso.ru.dsl",
    "month": "verso.ru.dsl",
}

def _module_constants(module: Any, kind: type, dsl_module: str) -> list[Constant]:
    out = []
    for name, value in vars(module).items():
        if name.isupper() and isinstance(value, kind):
            out.append(Constant(name, str(value), dsl_module, name))
    return out


def _enum_constants(enum: type[Enum], module: str) -> list[Constant]:
    return [Constant(f"{enum.__name__}.{m.name}", str(m.value), module, enum.__name__)
            for m in enum]


@statuses.kept
def catalogs() -> dict[str, tuple[Constant, ...]]:
    """Every named constant a field may take, by catalog.

    The modules are the ones DSL v1 imports from (`from verso.ru.dsl import Gender`,
    `from verso.ru.dsl.statuses import …`, `from corpus.statuses import …`), so a
    constant the file has not imported yet is added to the import it already has. The
    statuses are the workspace's catalog
    (`statuses.catalog()`): the library's and its corpus's.
    """
    module = statuses.corpus_statuses()
    corpus = {name: module.__name__ for name in getattr(module, "__all__", ())} if module is not None else {}
    return {
        # The library's and the workspace's corpus's, in the catalog's order — the corpus's
        # from its own module, `corpus.statuses`.
        "status": tuple(Constant(name, str(value), corpus.get(name, DSL_IMPORTS["status"]), name)
                        for name, value in statuses.catalog().items()),
        "cause": tuple(_module_constants(causes_of_death, CauseOfDeath, DSL_IMPORTS["cause"])),
        "marital": tuple(_module_constants(marital_status, str, DSL_IMPORTS["marital"])),
        "gender": tuple(_enum_constants(Gender, DSL_IMPORTS["gender"])),
        "relationship": tuple(_enum_constants(Relationship, DSL_IMPORTS["relationship"])),
        "month": tuple(Constant(f"Month.{m.name}", str(m.value), DSL_IMPORTS["month"], "Month")
                       for m in Month),
        "role": tuple(_enum_constants(census.CensusRole, DSL_IMPORTS["role"])),
        "side": tuple(_enum_constants(Side, DSL_IMPORTS["side"])),
    }


# Which catalog a parameter's value is drawn from. By NAME, because the
# annotations do not say it (`cause_of_death: str | None`).
PARAM_CATALOG = {
    "status": "status", "cause_of_death": "cause", "marital_status": "marital",
    "gender": "gender", "relationship": "relationship", "role": "role",
    "secondary_role": "role",
    "b_month": "month", "k_month": "month", "d_month": "month", "w_month": "month",
    "birth_month": "month", "record_month": "month", "month": "month",
    "side": "side",
    # A book's defaults take a person's status, each for some of its people.
    "status_male": "status", "status_female": "status", "status_mother": "status",
    "status_groom": "status", "status_bride": "status",
}


@statuses.kept
def constant_by_code() -> dict[str, Constant]:
    return {c.code: c for group in catalogs().values() for c in group}


# The status catalog is the workspace's (its corpus's statuses), so both are kept per workspace, and
# forgotten with its statuses (`statuses.kept`).


# ---------------------------------------------------------------- the page's catalog

# The records whose parameters the page reads, in the order it is told them.
CATALOG_FUNCS = ("birth", "christening", "death", "marriage", "household", "member",
                 "listed_person", "person")


def describe() -> dict[str, Any]:
    """What the review page reads as its catalog: every catalog's constants, which
    catalog a parameter draws from, the parameters of the records it edits, and the
    sex a census role or a relation implies."""
    sigs = {}
    for f in CATALOG_FUNCS:
        s = signature(f)
        if s is not None:
            sigs[f] = [dataclasses.asdict(p) for p in s.params]
    return {"catalogs": {k: [{"code": c.code, "text": c.text} for c in v]
                         for k, v in catalogs().items()},
            "param_catalog": PARAM_CATALOG, "signatures": sigs,
            # A member's sex, for the name suggestions, follows the role it holds.
            "role_gender": {f"CensusRole.{role.name}": "м" if gender is Gender.MALE else "ж"  # i18n: content — the sex as the DSL and the page's values write it
                            for role, gender in census.ROLE_GENDER.items()},
            # …and a relative's, the relation: «отец» is a man.
            "relationship_gender": {f"Relationship.{r.name}": "м" if g is Gender.MALE else "ж"  # i18n: content — the sex as the DSL and the page's values write it
                                    for r in Relationship if (g := gender_from_relationship(r)) is not None}}


def status_catalog() -> list[tuple[str, str, str]]:
    """(code, words, sex) of the catalog's statuses; the sex is `Status.gender`."""
    out: list[tuple[str, str, str]] = []
    for c in catalogs()["status"]:
        gender = getattr(statuses.catalog().get(c.code), "gender", None)
        out.append((c.code, c.text, "м" if gender is Gender.MALE else "ж" if gender is Gender.FEMALE else ""))  # i18n: content — the sex as the DSL and the page's values write it
    return out
