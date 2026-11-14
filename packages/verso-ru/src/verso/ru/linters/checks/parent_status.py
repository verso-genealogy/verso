#!/usr/bin/env python3
"""AST-based linter (PSA001–PSA003) checking that a parent and their child share
one сословие across birth, marriage and death records.

Сословие is inherited within a household: the child of «крестьянин помещика
Кузьмы Филипповича Манилова» is «крестьянский сын помещика Кузьмы Филипповича
Манилова», never «ясачный крестьянский сын» — a private serf and a state peasant
are mutually exclusive fiscal categories. The estate rides on `person(status=)`,
whose constants (verso/ru/domain/statuses.py) are named `<ESTATE>_<ROLE>`:
`YASAK_PEASANT_MALE`, `MANILOV_KF_PEASANT_SON`, `PLJUSHKIN_AS_PEASANT_DAUGHTER`.

  [PSA001] Both sides state a status and the estates differ. One of the two is
           wrong — usually the child, left on the parish default.

  [PSA002] One side states it; the other omits `status=` and so inherits a
           DIFFERENT estate from `RecordDefaults` (record_defaults.py applies it
           after construction). The omitted side silently acquires the parish
           сословие regardless of what its household says. Children are the
           exception: `Birth.__init__` and `Death.__init__` derive a statusless
           child's/deceased child's status from the consulted parent via
           `statuses.child_status_for` (peasant estates + SOLDIER and
           RETIRED_SOLDIER), so those pairs are skipped — PSA002 fires only
           when no derivation applies (e.g. a мещанин or дворовый parent, out of derivation scope, or the
           REVERSE direction: a statusless parent of an explicit child).

  Plain PEASANT is treated as compatible with every qualified peasant estate
  (`estates_compatible`): bare «крестьянский сын» UNDER-specifies — the books
  routinely write it while the parish convention qualifies the adults
  («экономический крестьянин») — it does not contradict them. Two different
  QUALIFIED estates (ECON vs YASAK, or two landlords) still contradict.

  [PSA003] A birth `child=` whose status uses an adult role (`..._MALE`) instead
           of a child one (`..._SON`/`..._DAUGHTER`/`..._BOY`/`..._GIRL`).
           Births only: a deceased or a groom may legitimately be an adult, so
           role shape cannot be inferred from the relation there.

  [PSA004] Husband and wife only: one states an estate, the other omits
           `status=` and the book's default names NONE — a bare «крестьянка»
           beside «крестьянин вотчины г-на Ноздрева». Under-specification is
           harmless for a child, whose estate `Birth.__init__` derives from the
           parent; nothing derives a wife's, so on the default she simply loses
           it. Found 2026-10-01 on 117 Глуповы Горы births (1803–1842), every
           one a wife whose husband the book styles by his owner.

Compared pairs — birth: father→child, mother→child, father→mother; death:
relative→deceased for отец/мать and husband→wife for муж; marriage: each
`relative(..., Relationship.FATHER/MOTHER, ref)` against the party its
`relationship_ref` names. Groom↔bride is deliberately NOT compared: they come
from different households by definition. Godparents, witnesses and the
officiating clergy are out of scope for the same reason.

Estate mobility is real, so exempt estates skip pairs where either side is
military (conscription pulled a man out of his birth estate while his father
stayed a peasant), clergy (ranks differ between father and son and are not a
fiscal estate), or a status that names no сословие at all («девица», «вдова»).

That mobility is GENERATIONAL, and the clergy exemption goes no further: a
husband and wife are one household at one moment, and духовенство was a closed
estate whose wives belonged to it — «жена пономаря», «попадья», «дьячиха».
So the husband↔wife pairs (birth father~mother, death муж~умершая) compare
clergy, while parent~child pairs still skip it: `SPOUSE_EXEMPT_ESTATES` drops
`CLERGY_ESTATES` from `EXEMPT_ESTATES`. Military stays exempt on both axes
because our own constants say a солдатка keeps her peasant estate
(`YASAK_SOLDIER_WIFE` → YASAK_PEASANT), and a vacuous status contradicts
nobody.

The book's own words count as written: `defaults=DEFAULTS` bound at the top
of the file, and a status constant the file defines itself
(`GORELOVO_PEASANT = "…"`), read like a string literal — see
[verso.ru.linters.checks.file_bindings]. Until 2026-10-01 both were invisible, and
every Глуповы Горы file ran with no defaults and no statuses at all.

Free-text `status="…"` resolves through the text→constant map. A string no
constant spells — «дворовый человек помещицы …», «мещанка», «однодворец» — is
read by its words with `estate_of`, the classifier `estate-conflicts` uses, and
compared against the other side's words the same way (PSA001/PSA002 as for
constants). Until 2026-09-25 it was skipped, and so was every child the parish
default made ясачный beside it: 28 findings (Горюхино 22, Заманиловка 6). An
unrecognised constant NAME is still skipped.

Path-independent: scopes on call func names and kwargs, so it behaves the same
on disk or on a temp-file copy of an unsaved editor buffer.

Run:
    python3 -m verso.ru.linters.checks.parent_status FILE [FILE...]
"""

import ast
import sys
from collections.abc import Mapping
from pathlib import Path

from verso.ru.domain.estates import family_root
from verso.ru.domain.statuses import child_status_for, corpus_aliases, kept
from verso.ru.gender import Gender
from verso.ru.linters.checks.file_bindings import module_bindings, string_constants
from verso.ru.linters.checks.status_words import (
    DAT, GEN, LANDLORD_PREFIX, Default, counterpart, default_for, default_statuses, estate_words, file_bound, offer, role_word, split_role, tables, who, words_of)
from verso.core.i18n import Message
from verso.ru.linters.issue import issue as finding, line_text, says
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

# Roles a newborn may carry (PSA003).
CHILD_ROLES = frozenset({"SON", "DAUGHTER", "BOY", "GIRL"})

# A «попадья» / «дьячиха» is named by her husband's rank, not by one of her own, and
# «иерей» is «священник» in another word; the corpus adds its own owners' (the
# полковник Собакевич is the помещик, the Головлевы's people their peasants) —
# `estate_aliases()`, read from the workspace.
_OWN_ESTATE_ALIASES: dict[str, str] = {
    "POPADIA": "PRIEST",
    "DYACHIKHA": "DYACHOK",
    "HIEREUS": "PRIEST",
    # Two names for one estate, spelled alike: Нижняя Яичница's and Заманиловка's
    # books use GOSUDARSTVENNYJ_PEASANT_*, the wives and children are STATE_PEASANT_*.
    "GOSUDARSTVENNYJ_PEASANT": "STATE_PEASANT",
    # A временнообязанный and a крестьянин собственник are stages of a peasant's land
    # tenure after 1861, not an estate of their own: his wife on the book's
    # «законная жена крестьянина» is right, and must not read as PSA004.
    "TEMP_OBLIGED_PEASANT": "PEASANT",
    "PROPRIETOR_PEASANT": "PEASANT",
}


@kept
def estate_aliases() -> dict[str, str]:
    """The library's estate aliases and the corpus's own (`ESTATE_ALIASES` of its statuses: the
    полковник Собакевич, the Головлевы's земские and приказчики), kept for the workspace."""
    return {**_OWN_ESTATE_ALIASES, **corpus_aliases().estate}

def as_peasant(estate: str) -> str:
    """`X_DVOROVY` → `X_PEASANT`; any other estate unchanged."""
    suffix = "_DVOROVY"
    return estate[: -len(suffix)] + "_PEASANT" if estate.endswith(suffix) else estate


def estates_compatible(a: str, b: str) -> bool:
    """Whether two estates can describe one household without contradiction.

    Plain PEASANT is UNDER-specification, not a different estate: the books
    routinely write a child as bare «крестьянский сын» while the parish
    convention (and the RecordDefaults default) qualifies the adults —
    «экономический крестьянин» in Заманиловка. Less specific ≠ different, so
    PEASANT is compatible with every qualified peasant estate. Two DIFFERENT
    qualified estates (ECON vs YASAK, or two landlords) still contradict.

    A landlord's дворовый and his крестьянин are one сословие here: the books
    style the same household either way (a man is «дворовый» in one book and
    «крестьянин» in another, his wife and children «крестьянка»,
    «крестьянская дочь» beside him), so `X_DVOROVY` reads as `X_PEASANT`. The
    owner still has to agree — one landlord's дворовый beside another
    landlord's крестьянский сын is two landlords, as before. That is also how
    `estate_of` reads the words, so free text and constants now agree.
    """
    a, b = as_peasant(a), as_peasant(b)
    if a == b:
        return True

    def is_peasant(estate: str) -> bool:
        return estate == "PEASANT" or estate.endswith("_PEASANT")

    return (a == "PEASANT" and is_peasant(b)) or (b == "PEASANT" and is_peasant(a))


# Estates that legitimately differ from a parent's, or that state no сословие.
# NB: MERCHANT / MESHCHANIN / LANDLORD / ODNODVORETS / BUDNY_PEASANT are NOT
# here — they do name an estate and must be compared.

# Military. Exempt on BOTH axes: conscription pulled a man out of his father's
# estate, and it did not pull his WIFE out of it either — our own qualified
# constants say so, `YASAK_SOLDIER_WIFE` («солдатка» of the ясачные) resolving
# to YASAK_PEASANT rather than to SOLDIER. So a soldier beside a peasant wife
# is the model working, not a contradiction.
MILITARY_ESTATES = frozenset({"SOLDIER", "RETIRED_SOLDIER", "PRIVATE_SOLDIER", "UNTER_OFFICER"})

# Clergy. Exempt across GENERATIONS only: a rank is not a fiscal estate and
# father and son routinely hold different ones (or none — a peasant's son took
# orders). Within one marriage there is no such mobility: духовенство was a
# closed estate whose wives belonged to it, and the books name them by the
# husband's rank («жена пономаря», «попадья», «дьячиха»), never «крестьянка».
# POPADIA / DYACHIKHA / HIEREUS are absent by design — estate_aliases() folds
# them onto the rank they name.
CLERGY_ESTATES = frozenset({"PRIEST", "DEACON", "DYACHOK", "SEXTON"})

# «девица» / «девка» / «женка» / «вдова» say nothing about сословие, so they
# cannot contradict anyone — exempt on both axes.
VACUOUS_ESTATES = frozenset({"MAIDEN", "GIRL", "ZHONKA", "WIDOW"})

# Parent↔child pairs (birth, death, marriage) — the generational axis.
EXEMPT_ESTATES = MILITARY_ESTATES | CLERGY_ESTATES | VACUOUS_ESTATES

# Husband↔wife pairs — the marital axis, where clergy IS compared.
SPOUSE_EXEMPT_ESTATES = MILITARY_ESTATES | VACUOUS_ESTATES


@kept
def estates() -> dict[str, str]:
    """{constant_name: estate key}.

    A bare landlord key produced by a `*_LEGAL_WIFE` constant is promoted to
    `<KEY>_PEASANT` when that group exists: MANILOV_KF_LEGAL_WIFE («законная
    жена крестьянина помещика А.Т. Манилова») must land on MANILOV_KF_PEASANT,
    not on a group of its own that could never match her husband.
    """
    texts, aliases = tables().texts, estate_aliases()
    bases = {split_role(name)[0] for name in texts}
    found: dict[str, str] = {}
    for name in texts:
        base, _ = split_role(name)
        if base + "_PEASANT" in bases:
            base += "_PEASANT"
        found[name] = aliases.get(base, base)
    return found


@kept
def roles() -> dict[str, str]:
    return {name: split_role(name)[1] for name in tables().texts}


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert a 0-based AST col_offset (UTF-8 byte offset) to a char column.
    DSL lines contain Cyrillic (multi-byte), so the byte offset overshoots."""
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _kwargs(node: ast.Call) -> dict[str, ast.keyword]:
    return {kw.arg: kw for kw in node.keywords if kw.arg is not None}


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _name_id(node: ast.expr | None) -> str | None:
    """Identifier of a constant reference: `Name.id` or `Attribute.attr`
    (e.g. `statuses.MANILOV_OV_PEASANT_MALE`)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _person_kwarg(kwargs: dict[str, ast.keyword], role: str) -> ast.Call | None:
    kw = kwargs.get(role)
    if kw is None or not isinstance(kw.value, ast.Call):
        return None
    if _call_func_name(kw.value) != "person":
        return None
    return kw.value


def _status_node(person_node: ast.Call) -> ast.expr | None:
    """`status=` kwarg, else positional index 7 of person()."""
    pkw = _kwargs(person_node)
    if "status" in pkw:
        return pkw["status"].value
    if len(person_node.args) >= 8:
        return person_node.args[7]
    return None


def _status_const(person_node: ast.Call,
                  file_texts: Mapping[str, str]) -> tuple[str | None, str]:
    """(constant name, kind) for a person(). kind is one of:
    `const` / `text` — resolved to a constant; `free` — a string no constant
    spells, compared by its words (see [estate_words]); `unknown` — an
    unrecognised constant name, skip; `none` — no status at all, so
    RecordDefaults will fill it.

    A constant the FILE defines (`GORELOVO_PEASANT = "…"`) is read as the
    string it binds — `text` when `verso.ru.domain.statuses` spells it, else
    `free`."""
    node = _status_node(person_node)
    if node is None:
        return None, "none"
    ident = _name_id(node)
    if ident is not None and ident in estates() and not file_bound(node, file_texts):
        return ident, "const"
    text = words_of(node, file_texts)
    if text is not None:
        const = tables().by_text.get(text)
        return (const, "text") if const else (None, "free")
    return None, "unknown"


# --- free text ------------------------------------------------------------
#
# A status no constant spells — «дворовый человек помещицы Лукерьи Кузьминичны
# Маниловой», «мещанка», «солдатская жена из крестьян помещицы Анны Ивановны
# Пеночкиной» — used to be skipped, and so did the child the book's default made
# ясачный beside it. Such a pair is now read the way `estate-conflicts` reads a
# status: by `estate_of`, over the WORDS of both sides (a constant's text
# included), so the two checks cannot disagree about what an estate is. The
# words are coarser than the constants — ясачный and экономический are one
# `state` there — which costs nothing here: a pair that only the constants
# could tell apart already has two constants and never reaches this path.
#
# A солдатка is compared by what her status says of her ORIGIN. «солдатская
# жена из крестьян помещицы X» names X's estate, which she kept (the same
# reading as `YASAK_SOLDIER_WIFE` → YASAK_PEASANT), so her child left on the
# ясачный default is flagged; a bare «солдатка» names none and contradicts
# nobody. Military on the OTHER side stays exempt as before: `estate_of` gives
# a bare «солдат» no estate, and a military constant is skipped by name.


def _owner_key(owner: str) -> tuple[str, str | None, str | None]:
    """(family stem, given name, patronymic stem) of a landlord's name.

    The books spell one owner several ways — «Демьяна Назаровича» and
    «Демьяна Назарова» Манилова, «Ольги Власьевны» and «Фирстовны» — so
    the patronymic is compared by its first four letters and the surname by
    its gender-free stem. An owner written by surname alone («помещика
    Манилова») keeps only the family.
    """
    parts = owner.split()
    family = family_root(parts[-1]) if parts else ""
    if len(parts) >= 3:
        return family, parts[-3], parts[-2][:4]
    if len(parts) == 2:
        return family, parts[0], None
    return family, None, None


def _owners_compatible(a: str, b: str) -> bool:
    (fa, ga, pa), (fb, gb, pb) = _owner_key(a), _owner_key(b)
    if fa != fb:
        return False
    if ga is not None and gb is not None and ga != gb:
        return False
    return pa is None or pb is None or pa == pb


def free_estates_compatible(a: str, b: str) -> bool:
    """Whether two `estate_of` keys can describe one household.

    A bare «дворовый человек» names no owner, and so under-specifies any
    landlord's estate the way plain PEASANT under-specifies a qualified one.
    """
    if a == b:
        return True
    a_owner = a[len(LANDLORD_PREFIX):] if a.startswith(LANDLORD_PREFIX) else None
    b_owner = b[len(LANDLORD_PREFIX):] if b.startswith(LANDLORD_PREFIX) else None
    if a_owner is not None and b_owner is not None:
        return _owners_compatible(a_owner, b_owner)
    return ((a == "dvorovy" and b_owner is not None)
            or (b == "dvorovy" and a_owner is not None))


class _Party:
    """One side of a comparison: its person() node, the role name used to pick
    a RecordDefaults fallback, the gender that fallback keys on, and the word a
    finding calls them by («отец», «умершая»)."""

    def __init__(self, node: ast.Call, role: str, female: bool, label: str) -> None:
        self.node = node
        self.role = role
        self.female = female
        self.label = label


class ParentStatusChecker(shared_ast.Visitor):
    """Walks record-list calls tracking their RecordDefaults statuses, and
    compares each parent/child pair inside."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self.issues: list[dict[str, object]] = []
        self._defaults_stack: list[dict[str, Default]] = []
        self._lines = lines or []
        self._bindings: dict[str, ast.expr] = {}
        self._file_texts: dict[str, str] = {}

    # --- highlight spans --------------------------------------------------

    def _span(self, node: ast.expr) -> dict[str, int]:
        """Char-column span pinning `node`, so the IDE underlines the offending
        token instead of the whole record line. Empty for a multi-line node —
        the plugins take a span only within one line.

        Carries its own `line`: a span is only meaningful together with the line
        its columns were measured on, and the fallback in [_person_span] moves
        to a different line than the one the issue would otherwise report.
        """
        if node.lineno != node.end_lineno or node.end_col_offset is None:
            return {}
        return {
            "line": node.lineno,
            "col": _char_col(self._lines, node.lineno, node.col_offset),
            "end_col": _char_col(self._lines, node.lineno, node.end_col_offset),
        }

    def _person_span(self, person_node: ast.Call) -> dict[str, int]:
        """Span for a person with nothing to point at (PSA002 flags the ABSENCE
        of `status=`). Prefer the whole `person(...)` call; when it spans lines,
        fall back to its first argument — the given name identifies who."""
        span = self._span(person_node)
        if span:
            return span
        if person_node.args:
            return self._span(person_node.args[0])
        return {}

    # --- defaults ---------------------------------------------------------

    def _defaults(self) -> dict[str, Default]:
        return self._defaults_stack[-1] if self._defaults_stack else {}

    def _default_for(self, party: _Party) -> Default | None:
        """The status RecordDefaults would give this party, if any."""
        return default_for(self._defaults(), party.role, party.female)

    def _default_estate(self, party: _Party) -> tuple[str | None, str | None]:
        """(estate, constant name) RecordDefaults would give this party, when
        the default is a `verso.ru.domain.statuses` constant."""
        default = self._default_for(party)
        if default is None or default.const is None:
            return None, None
        return estates()[default.const], default.const

    def _status_const(self, person_node: ast.Call) -> tuple[str | None, str]:
        return _status_const(person_node, self._file_texts)

    def _status_text(self, person_node: ast.Call) -> str | None:
        return words_of(_status_node(person_node), self._file_texts)

    # --- traversal --------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        self._bindings = module_bindings(node)
        self._file_texts = string_constants(self._bindings)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fname = _call_func_name(node)
        pushed = False
        if fname in ("birth_records", "death_records", "marriage_records"):
            self._defaults_stack.append(
                default_statuses(node, self._bindings, self._file_texts))
            pushed = True

        if fname == "birth":
            self._visit_birth(node)
        elif fname == "death":
            self._visit_death(node)
        elif fname == "marriage":
            self._visit_marriage(node)

        self.generic_visit(node)
        if pushed:
            self._defaults_stack.pop()

    def _visit_birth(self, node: ast.Call) -> None:
        kwargs = _kwargs(node)
        father = _person_kwarg(kwargs, "father")
        mother = _person_kwarg(kwargs, "mother")
        child = _person_kwarg(kwargs, "child")
        child_female = _record_gender(node) == "FEMALE"

        if child is not None:
            # A statusless child INHERITS the consulted parent's estate
            # (Birth.__init__ → statuses.child_status_for), so there is
            # nothing for PSA002 to flag: the generator already does the
            # right thing. Skip the parent→child comparisons entirely —
            # PSA001 needs an explicit child status, which is absent here.
            _, child_kind = self._status_const(child)
            derived = (child_kind == "none"
                       and self._child_derives(father, mother, child_female))
            c = _Party(child, "child", child_female, "child")
            if father is not None and not derived:
                self._compare(_Party(father, "father", False, "father"), c)
            if mother is not None and not derived:
                self._compare(_Party(mother, "mother", True, "mother"), c)
            self._check_child_role(child, child_female)
        if father is not None and mother is not None:
            self._compare(_Party(father, "father", False, "husband"),
                          _Party(mother, "mother", True, "wife"), spouses=True)

    def _child_derives(self, father: ast.Call | None, mother: ast.Call | None,
                       child_female: bool) -> bool:
        """Mirror Birth.__init__'s consulted-parent rule: a father with ANY
        status is consulted exclusively (a clergy/merchant father must not
        fall through to the mother); the mother only when the father is
        absent or statusless. True when `child_status_for` would derive."""
        if father is not None and _status_node(father) is not None:
            consulted = father
        else:
            consulted = mother
        if consulted is None:
            return False
        const, kind = self._status_const(consulted)
        if kind not in ("const", "text") or const is None:
            return False
        gender = Gender.FEMALE if child_female else Gender.MALE
        return child_status_for(tables().texts[const], gender) is not None

    def _visit_death(self, node: ast.Call) -> None:
        kwargs = _kwargs(node)
        deceased = _person_kwarg(kwargs, "deceased")
        if deceased is None:
            return
        deceased_female = _record_gender(node) == "FEMALE"
        relatives = _death_relatives(node)
        # Mirror Death.__init__: a statusless deceased inherits the estate of
        # the first FATHER with a status (consulted exclusively), else the
        # first MOTHER — nothing to flag when the derivation applies.
        _, deceased_kind = self._status_const(deceased)
        derived = (deceased_kind == "none"
                   and self._deceased_derives(relatives, deceased_female))
        for person, relationship in relatives:
            if relationship in ("FATHER", "MOTHER"):
                if derived:
                    continue
                label = "father" if relationship == "FATHER" else "mother"
                self._compare(
                    _Party(person, "relative", relationship == "MOTHER", label),
                    _Party(deceased, "deceased", deceased_female,
                           "deceased_female" if deceased_female else "deceased_male"))
            elif relationship == "HUSBAND":
                self._compare(
                    _Party(person, "relative", False, "husband"),
                    _Party(deceased, "deceased", deceased_female, "deceased_female"),
                    spouses=True)

    def _deceased_derives(self, relatives: list[tuple[ast.Call, str | None]],
                          deceased_female: bool) -> bool:
        consulted = next(
            (p for p, rel in relatives
             if rel == "FATHER" and _status_node(p) is not None), None)
        if consulted is None:
            consulted = next(
                (p for p, rel in relatives
                 if rel == "MOTHER" and _status_node(p) is not None), None)
        if consulted is None:
            return False
        const, kind = self._status_const(consulted)
        if kind not in ("const", "text") or const is None:
            return False
        gender = Gender.FEMALE if deceased_female else Gender.MALE
        return child_status_for(tables().texts[const], gender) is not None

    def _visit_marriage(self, node: ast.Call) -> None:
        kwargs = _kwargs(node)
        for person, relationship, ref in _marriage_relatives(node):
            if relationship not in ("FATHER", "MOTHER"):
                continue
            if ref and "жених" in ref:  # i18n: content — the reference words the DSL writes
                party_node, role, female, label = (
                    _person_kwarg(kwargs, "groom"), "groom", False, "groom")
            elif ref and "невест" in ref:  # i18n: content — the reference words the DSL writes
                party_node, role, female, label = (
                    _person_kwarg(kwargs, "bride"), "bride", True, "bride")
            else:
                continue
            if party_node is None:
                continue
            parent_label = "father" if relationship == "FATHER" else "mother"
            self._compare(_Party(person, "relative", relationship == "MOTHER", parent_label),
                          _Party(party_node, role, female, label))

    # --- rules ------------------------------------------------------------

    def _compare(self, parent: _Party, child: _Party, spouses: bool = False) -> None:
        """`spouses` marks a husband↔wife pair, where the clergy exemption does
        not apply — see [CLERGY_ESTATES]."""
        p_const, p_kind = self._status_const(parent.node)
        c_const, c_kind = self._status_const(child.node)
        p_explicit = p_kind in ("const", "text")
        c_explicit = c_kind in ("const", "text")

        if p_explicit and c_explicit:
            self._psa001(parent, child, p_const, c_const, spouses)
            return
        if p_kind == "none" and c_kind == "none":
            return  # neither side says anything; the book's defaults speak for both
        free_default = any(
            kind == "none" and (d := self._default_for(party)) is not None and d.const is None
            for party, kind in ((parent, p_kind), (child, c_kind)))
        if "free" in (p_kind, c_kind) or free_default:
            self._compare_free(parent, child, spouses)
            return
        # PSA002 — exactly one side explicit, the other silent (an unrecognised
        # status is `unknown`, never compared against a default).
        if p_explicit and c_kind == "none":
            self._psa002(child, parent, p_const, spouses, silent_is_child=True)
        elif c_explicit and p_kind == "none":
            self._psa002(parent, child, c_const, spouses, silent_is_child=False)

    def _psa001(self, parent: _Party, child: _Party, p_const: str | None,
                c_const: str | None, spouses: bool = False) -> None:
        if p_const is None or c_const is None:
            return
        p_estate, c_estate = estates()[p_const], estates()[c_const]
        if estates_compatible(p_estate, c_estate):
            return
        exempt = SPOUSE_EXEMPT_ESTATES if spouses else EXEMPT_ESTATES
        if p_estate in exempt or c_estate in exempt:
            return
        self._contradiction(parent, child, tables().texts[p_const], tables().texts[c_const],
                            spouses)

    def _psa002(self, silent: _Party, stated: _Party, other_const: str | None,
                spouses: bool, *, silent_is_child: bool) -> None:
        if other_const is None:
            return
        other_estate = estates()[other_const]
        default_estate, default_const = self._default_estate(silent)
        if default_estate is None or default_const is None:
            return
        if estates_compatible(default_estate, other_estate):
            if (spouses and as_peasant(default_estate) == "PEASANT"
                    and as_peasant(other_estate) != "PEASANT"):
                self._silent("PSA004", silent, stated, tables().texts[default_const],
                             other_const, spouses, silent_is_child=silent_is_child)
            return
        exempt = SPOUSE_EXEMPT_ESTATES if spouses else EXEMPT_ESTATES
        if other_estate in exempt or default_estate in exempt:
            return
        self._silent("PSA002", silent, stated, tables().texts[default_const],
                     other_const, spouses, silent_is_child=silent_is_child)

    def _compare_free(self, parent: _Party, child: _Party, spouses: bool) -> None:
        """A pair with at least one free-text side, read by its words.

        PSA001 when both sides state a status, PSA002 when one is silent and
        the book's default speaks for it — the same two findings as for
        constants, over `estate_of` keys instead of constant prefixes.
        """
        exempt = SPOUSE_EXEMPT_ESTATES if spouses else EXEMPT_ESTATES
        # (estate, constant, words, silent) — estate None when the words name none
        read: list[tuple[str | None, str | None, str, bool]] = []
        for party in (parent, child):
            const, kind = self._status_const(party.node)
            if kind == "unknown":
                return
            silent = kind == "none"
            if silent:
                default = self._default_for(party)
                if default is None:
                    return
                const, text = default.const, default.text
            else:
                text = self._status_text(party.node)
            if const is not None and estates().get(const) in exempt:
                return
            estate = estate_words(text)
            if estate == "clergy" and not spouses:
                return
            read.append((estate, const, text or "", silent))
        (p_estate, p_const, p_words, p_silent), (c_estate, c_const, c_words, c_silent) = read
        if p_estate is None or c_estate is None:
            # A side naming no estate under-specifies the other. Harmless for a
            # child (derived), not for a spouse left on the default — PSA004.
            if spouses and p_silent != c_silent:
                silent_estate, stated_estate = ((p_estate, c_estate) if p_silent
                                                else (c_estate, p_estate))
                if silent_estate is None and stated_estate is not None:
                    if p_silent:
                        self._silent("PSA004", parent, child, p_words, c_const, spouses,
                                     silent_is_child=False, stated_words=c_words)
                    else:
                        self._silent("PSA004", child, parent, c_words, p_const, spouses,
                                     silent_is_child=True, stated_words=p_words)
            return
        if free_estates_compatible(p_estate, c_estate):
            return
        if p_silent:
            self._silent("PSA002", parent, child, p_words, c_const, spouses,
                         silent_is_child=False, stated_words=c_words)
        elif c_silent:
            self._silent("PSA002", child, parent, c_words, p_const, spouses,
                         silent_is_child=True, stated_words=p_words)
        else:
            self._contradiction(parent, child, p_words, c_words, spouses)

    # --- wording ----------------------------------------------------------
    #
    # A finding names the person as the record writes them and the statuses in
    # their words, and says what to do: the reader is as often on the review
    # page as in the editor, and a page shows the words, not the constant. The
    # constant appears once, in the fix, for whoever types it by hand.

    def _contradiction(self, parent: _Party, child: _Party, p_words: str,
                       c_words: str, spouses: bool) -> None:
        """PSA001 — both sides state a status, and the estates differ. Points at
        the child's own status, the token most often wrong."""
        status_node = _status_node(child.node)
        span = self._span(status_node) if status_node is not None else {}
        self.issues.append({
            "line": status_node.lineno if status_node is not None else child.node.lineno,
            **says("PSA001", "spouses" if spouses else "generations", child=who(child.label, child.node, capital=True),
                   child_words=c_words, parent=who(parent.label, parent.node), parent_words=p_words),
            **span,
        })

    def _silent(self, code: str, silent: _Party, stated: _Party, default_words: str,
                stated_const: str | None, spouses: bool, *, silent_is_child: bool,
                stated_words: str | None = None) -> None:
        """PSA002 / PSA004 — one side states no status, and the book's default
        gives it another estate (PSA002) or none at all (PSA004)."""
        if stated_words is None:
            stated_words = self._status_text(stated.node) or (
                tables().texts[stated_const] if stated_const else "")
        variant = ("female" if silent.female else "male") + ("_spouses" if spouses else "_generations")
        fix = _fix(silent, stated, stated_const, spouses, silent_is_child)
        self.issues.append({
            "line": silent.node.lineno,
            **says(code, variant, silent=who(silent.label, silent.node, GEN), default=default_words,
                   stated=who(stated.label, stated.node), stated_words=stated_words, fix=fix),
            **self._person_span(silent.node),
        })

    def _check_child_role(self, child: ast.Call, female: bool) -> None:
        const, kind = self._status_const(child)
        if kind not in ("const", "text") or const is None:
            return
        role = roles().get(const, "")
        if role in CHILD_ROLES:
            return
        estate = estates()[const]
        if estate in EXEMPT_ESTATES:
            return
        suggestion = counterpart(const, female=female, child=True)
        base = split_role(const)[0]
        newborn = "newborn_female" if female else "newborn_male"
        status_node = _status_node(child)
        span = self._span(status_node) if status_node is not None else {}
        self.issues.append({
            "line": status_node.lineno if status_node is not None else child.lineno,
            **(says("PSA003", "offer", newborn=who(newborn, child, DAT, capital=True), words=tables().texts[const],
                    offer=offer(suggestion)) if suggestion else
               says("PSA003", "forms", newborn=who(newborn, child, DAT, capital=True), words=tables().texts[const],
                    base=base)),
            **span,
        })


def _fix(silent: _Party, stated: _Party, stated_const: str | None, spouses: bool,
         silent_is_child: bool) -> Message:
    """What to write on the silent side: the stated estate in the silent
    person's own sex, when the catalog holds it. A child is not offered one —
    its status is derived from the parent, so the parent is what to fix."""
    dative = role_word(silent.label, DAT)
    suggestion = None
    if stated_const is not None and (spouses or not silent_is_child):
        suggestion = counterpart(
            stated_const, female=silent.female,
            wife=silent.female and (spouses or silent.role == "mother"))
    mother = silent.role == "mother"
    if suggestion:
        return (t("parent_status.fix_offer_mother", role=dative, offer=offer(suggestion)) if mother
                else t("parent_status.fix_offer", role=dative, offer=offer(suggestion)))
    stated_role = role_word(stated.label, GEN)
    return (t("parent_status.fix_like_mother", role=dative, stated=stated_role) if mother
            else t("parent_status.fix_like", role=dative, stated=stated_role))


def _record_gender(node: ast.Call) -> str | None:
    """Second positional arg of birth()/death() is Gender.MALE/FEMALE."""
    if len(node.args) < 2:
        return None
    g = node.args[1]
    if (isinstance(g, ast.Attribute)
            and isinstance(g.value, ast.Name)
            and g.value.id == "Gender"):
        return g.attr
    return None


def _relative_person(elt: ast.Call) -> ast.Call | None:
    """person() inside a `relative(person, Relationship.X, ref)` call."""
    person = _person_kwarg(_kwargs(elt), "person")
    if person is not None:
        return person
    if elt.args and isinstance(elt.args[0], ast.Call):
        cand = elt.args[0]
        if _call_func_name(cand) == "person":
            return cand
    return None


def _relative_entries(node: ast.Call) -> list[ast.Call]:
    """`relative(...)` / `Relative(...)` calls in a `relatives=[...]` kwarg."""
    rels = _kwargs(node).get("relatives")
    if rels is None or not isinstance(rels.value, ast.List):
        return []
    return [elt for elt in rels.value.elts
            if isinstance(elt, ast.Call)
            and _call_func_name(elt) in ("relative", "Relative")]


def _death_relatives(node: ast.Call) -> list[tuple[ast.Call, str | None]]:
    """(person, relationship) pairs from a death()'s `relatives=`."""
    out: list[tuple[ast.Call, str | None]] = []
    for elt in _relative_entries(node):
        person = _relative_person(elt)
        if person is None:
            continue
        ekw = _kwargs(elt)
        rel = (_name_id(ekw["relationship"].value) if "relationship" in ekw
               else (_name_id(elt.args[1]) if len(elt.args) >= 2 else None))
        out.append((person, rel))
    return out


def _marriage_relatives(node: ast.Call) -> list[tuple[ast.Call, str | None, str | None]]:
    """(person, relationship, relationship_ref) from a marriage()'s relatives."""
    out: list[tuple[ast.Call, str | None, str | None]] = []
    for elt in _relative_entries(node):
        person = _relative_person(elt)
        if person is None:
            continue
        ekw = _kwargs(elt)
        rel = (_name_id(ekw["relationship"].value) if "relationship" in ekw
               else (_name_id(elt.args[1]) if len(elt.args) >= 2 else None))
        ref = (_string_literal(ekw["relationship_ref"].value)
               if "relationship_ref" in ekw
               else (_string_literal(elt.args[2]) if len(elt.args) >= 3 else None))
        out.append((person, rel, ref))
    return out


def _collect(tree: ast.AST, lines: list[str] | None = None) -> list[dict[str, object]]:
    checker = ParentStatusChecker(lines)
    checker.visit(tree)
    return checker.issues


def check_file(path: Path) -> list[str]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError as e:
        return [line_text(path, finding("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}"
            for i in _collect(tree, src.splitlines())]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    out: list[dict[str, object]] = []
    for i in _collect(tree, src.splitlines()):
        # "error": hard since 2026-09-26 (0 corpus findings) — the IDE shows
        # it red, matching CI, which fails on any PSA finding.
        issue: dict[str, object] = {
            "level": "error", "line": i["line"], "message": i["message"]}
        if "col" in i:
            issue["col"] = i["col"]
            issue["end_col"] = i["end_col"]
        out.append(issue)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        all_errors.extend(check_file(Path(arg)))
    for e in all_errors:
        print(e)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
