#!/usr/bin/env python3
"""AST-based linter: a person's status against the village they live in.

A peasant's звание encodes which estate they belonged to, and in the two
parishes below that fixes where they lived. Each parish has its own rule,
applied only to the books of that parish (the record set's `village`, so the
check stays path-independent):

  [RTV001] Горюхино and Собакевичево — one parish. The peasants of each noble
           landlord lived in exactly one village: some Маниловы held Горюхино
           peasants, others Собакевичево, so the mapping is keyed on the SPECIFIC
           landlord (the given-name+patronymic encoded in the status-constant
           initials, e.g. MANILOV_PS vs MANILOV_OV), not on the surname. The
           ясачные / казённые lived in Горюхино — but only in this parish's
           books: until 2026-10-03 that rule ran everywhere and refused a
           «казенная крестьянка» of Горелово in Глуповы Горы 1825. The
           landlord rule still runs everywhere; those owners occur nowhere else.

  [RTV002] Глуповы Горы — the село was its owners' (Тентетниковъ, Ноздревъ, the
           Головлевы), the деревня Горелово a state village (казённого,
           экономического ведомства, государственных имуществ). A status naming
           an owner in Горелово, or a state peasant in Глуповы Горы, is a
           contradiction. Hard: the corpus held none when it landed.

  A bare «крестьянин» — a peasant status naming no estate — is NOT flagged
  anywhere. RTV003 asked for the owner or the ведомство on every one of them in
  Глуповы Горы before 1861; it was retired on 2026-10-09, because the books
  themselves write plain «крестьянин» (1839 among them), and a transcription
  keeps what the source says.

RTV001 scope = resident roles: census family members, birth `father`/`mother`,
and death `deceased`. Godparents are exempt — they legitimately come from other
villages. Marriage roles (parties, witnesses, relatives) are checked ONLY when
the residence is INHERITED from the record default. A wedding gathers people
from several villages, so when the author states where someone lives that
statement comes from the source: an Плюшкина serf recorded in Усть-Неурожайка means
the landlord held serfs there (192/2, 171/1 and 323/1 splits in the corpus say
exactly that), not that the record is wrong. What remains catchable is the
silent case — nobody said where this person lives, so they take the parish
default while their own status names another village. That is how six people
of one Собакевич wedding party (the bride, her father and four witnesses)
were published as living in Горюхино. Skipping explicit residences is also what
keeps the ясачные quiet: their status maps to Горюхино, and the ~70 of them
recorded in Неелово, Ротозеево, Брехаловка and the like are all explicit —
correct data that a naive comparison would flag.
RTV001 reads only a written `status=`.

RTV002 scope = everyone whose residence and status the record settles —
godparents, witnesses and wedding parties included, a residence written or not:
the rule there has no exception, Горелово held no owner's serfs. The status is
the one the person ends with: written, else the book's `RecordDefaults` for the
role and sex — the default is exactly how a Горелово wife became a bare
«крестьянка». A child whose status the record derives from a parent is left to
the parent's finding. Soldiers are skipped: a «сторож казённого бора, рядовой
солдат» lived where his service put him.

If the status can't be classified, or the effective residence can't be resolved
from the AST, the person is skipped (conservative: never guess).

Run:
    python3 -m verso.ru.linters.checks.residence_title FILE [FILE...]
"""

import ast
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

from verso.ru import corpus_data
from verso.ru.corpus_data import Landlord, OwnersAndState, StatePeasants
from verso.ru.domain.estates import estate_of
from verso.ru.linters.checks.census_redundancy import _gender as _member_gender
from verso.ru.linters.checks.census_redundancy import _Member
from verso.ru.linters.checks.file_bindings import module_bindings, record_defaults_call, string_constants
from verso.ru.linters.checks.parent_status import _death_relatives, _marriage_relatives, _record_gender
from verso.ru.linters.checks.status_words import (
    GEN, LANDLORD_PREFIX, Default, default_for, default_statuses, estate_words, role_word, who, words_of)
from verso.ru.naming import get_gender_from_name, modernize_orthography
from verso.core.i18n import Message
from verso.ru.linters.issue import as_dict, issue, line_text, says
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

Issue = dict[str, object]

# Landlord identity → (village(s), full-name genitive token for freeform-string
# matching), keyed on the first two tokens of the status constant name
# (SURNAME_INITIALS): the corpus's `[landlords]` (corpus/estates.toml), read at
# check time through `verso.ru.corpus_data.estates()`.

# The state peasants (ясачные, казённые) of a parish lived in one village of it, in
# that parish's books only — the corpus's `[[state_peasants]]`. (Economic peasants are
# NOT village-specific, so ECON is deliberately excluded.)
YASAK_NAME_PREFIXES = ("YASAK_", "KAZENNYJ_")
YASAK_SUBSTRINGS = ("ясачн", "казённ", "казенн")  # i18n: content — status words: vocabulary
# A freeform landlord status must contain one of these markers + a known
# landlord's full-name token.
LANDLORD_MARKERS = ("помещик", "помещиц")  # i18n: content — status words: vocabulary
# дворовый человек = manor household serf, NOT a village peasant — skip.
SERF_MARKERS = ("дворов",)  # i18n: content — status words: vocabulary


# An owner named in words. `estate_words` reads «помещика» and «вотчины …»;
# «крестьянская дочь девка г-на Ноздрева» names him by the honorific alone.
OWNER_MARKERS = ("вотчин", "отчин", "помещи", "г-на", "гг.", "дворов")  # i18n: content — status words: vocabulary

_RECORD_CALLS = ("birth_records", "death_records", "marriage_records")

BY_RELATIONSHIP: dict[str, tuple[str, bool]] = {
    "FATHER": ("father", False), "MOTHER": ("mother", True),
    "HUSBAND": ("husband", False), "WIFE": ("wife", True),
    "SON": ("son", False), "DAUGHTER": ("daughter", True),
}




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


def _int_literal(node: ast.expr | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _name_id(node: ast.expr | None) -> str | None:
    """Identifier for a status constant: `Name.id`, or `Attribute.attr`
    (e.g. `statuses.MANILOV_OV_PEASANT_MALE`)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def landlord_key(const_id: str) -> str | None:
    """The landlord identity = first two tokens (SURNAME_INITIALS)."""
    parts = const_id.split("_")
    if len(parts) < 2:
        return None
    return f"{parts[0]}_{parts[1]}"




class Expected(NamedTuple):
    """Where a status says its bearer lived, and who it says lived there."""
    villages: tuple[str, ...]
    who: str


def landlord_expected(landlord: Landlord) -> Expected | None:
    return Expected(landlord.villages, f"крестьяне {landlord.token}") if landlord.villages else None  # i18n: content — status words: vocabulary


def _classify_status(status_node: ast.expr | None, *, state: StatePeasants | None) -> Expected | None:
    """Acceptable residence village(s) for a status, or None to skip. `state` — the
    book's parish keeps its state peasants in one village (`[[state_peasants]]`)."""
    landlords = corpus_data.estates().landlords
    ident = _name_id(status_node)
    if ident is not None:
        if "_DVOROVY" in ident:  # manor serf, not a village peasant
            return None
        key = landlord_key(ident)
        if key is not None and key in landlords:
            return landlord_expected(landlords[key])
        if state is not None and ident.startswith(YASAK_NAME_PREFIXES):
            return Expected((state.village,), state.who)
        return None

    text = _string_literal(status_node)
    if text is None:
        return None
    if any(m in text for m in SERF_MARKERS):
        return None
    if any(m in text for m in LANDLORD_MARKERS):
        for landlord in landlords.values():
            if landlord.token in text:
                return landlord_expected(landlord)
        return None  # помещик named, but not a landlord we map -> skip
    if state is not None and any(sub in text for sub in YASAK_SUBSTRINGS):
        return Expected((state.village,), state.who)
    return None


def normalize_village(name: str) -> str:
    name = name.strip()
    return corpus_data.estates().village_aliases.get(name, name)


def either(villages: tuple[str, ...]) -> str | Message:
    """«Собакевичево», «Собакевичево, Дырявино или Усть-Неурожайка»."""
    if len(villages) == 1:
        return villages[0]
    return t("words.either", some=", ".join(villages[:-1]), last=villages[-1])


def names_owner(words: str) -> bool:
    estate = estate_words(words)
    if estate is not None and (estate.startswith(LANDLORD_PREFIX) or estate == "dvorovy"):
        return True
    low = words.lower()
    return any(marker in low for marker in OWNER_MARKERS)


def _person_kwarg(kwargs: dict[str, ast.keyword], role: str) -> ast.Call | None:
    kw = kwargs.get(role)
    if kw is None or not isinstance(kw.value, ast.Call):
        return None
    if _call_func_name(kw.value) != "person":
        return None
    return kw.value


def _member_person(node: ast.Call) -> ast.Call | None:
    """`member(number, person, role, age, ...)` — person at positional index 1
    or the `person=` keyword."""
    pkw = _kwargs(node).get("person")
    if pkw is not None and isinstance(pkw.value, ast.Call):
        return pkw.value if _call_func_name(pkw.value) == "person" else None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Call):
        cand = node.args[1]
        return cand if _call_func_name(cand) == "person" else None
    return None


def _status_node(person_node: ast.Call) -> ast.expr | None:
    """`status=` kwarg, else positional index 7 of person()."""
    pkw = _kwargs(person_node)
    if "status" in pkw:
        return pkw["status"].value
    if len(person_node.args) >= 8:
        return person_node.args[7]
    return None


def _explicit_residence(person_node: ast.Call) -> str | None:
    """`residence=` kwarg literal, else positional index 6 of person()."""
    pkw = _kwargs(person_node)
    if "residence" in pkw:
        return _string_literal(pkw["residence"].value)
    if len(person_node.args) >= 7:
        return _string_literal(person_node.args[6])
    return None


def _explicit_gender(person_node: ast.Call) -> bool | None:
    """`gender=Gender.FEMALE` → True, `Gender.MALE` → False, else None."""
    kw = _kwargs(person_node).get("gender")
    name = _name_id(kw.value) if kw is not None else None
    return {"FEMALE": True, "MALE": False}.get(name or "")


def _name_gender(person_node: ast.Call) -> bool | None:
    """The sex the names table gives the first name, the way Person reads it."""
    kw = _kwargs(person_node).get("name_orig")
    name = _string_literal(kw.value if kw is not None
                           else person_node.args[0] if person_node.args else None)
    if not name:
        return None
    gender = get_gender_from_name(modernize_orthography(name))
    return None if gender is None else gender.name == "FEMALE"


def _record_defaults_residence(node: ast.Call,
                               bindings: Mapping[str, ast.expr]) -> str | None:
    """`defaults=RecordDefaults(residence="...")` on a record-list call, written
    in the call or bound by name at the top of the file."""
    defaults = record_defaults_call(node, bindings)
    if defaults is None:
        return None
    res = _kwargs(defaults).get("residence")
    return _string_literal(res.value) if res is not None else None


def _records_arg(node: ast.Call, index: int, kwarg: str) -> ast.expr | None:
    kw = _kwargs(node).get(kwarg)
    if kw is not None:
        return kw.value
    return node.args[index] if len(node.args) > index else None


class Lives(NamedTuple):
    """Where a person lives, and how a finding says we know."""
    village: str
    source: Message                  # how the finding says we know it


class _Book(NamedTuple):
    """A record set: its parish village and year, where a person the record
    places nowhere lives, and the statuses its RecordDefaults give."""
    village: str | None
    year: int | None
    lives: Lives | None
    statuses: Mapping[str, Default]


_NO_BOOK = _Book(None, None, None, {})


class _Slot(NamedTuple):
    """One person of a record, as both rules read them."""
    node: ast.Call
    label: str                   # the word a finding calls them by
    female: bool | None
    role: str                    # RecordDefaults' key for them: mother, groom, bride, or ""
    inherited: Lives | None     # the household's residence, before the book's
    rtv001: str | None           # None — not an RTV001 role; "all"; "inherited_only"
    derived: bool = False        # an unwritten status is derived from a parent
    hidden: bool = False         # a reconstructed roll member, not in the book


def _written(person_node: ast.Call | None, source: Message) -> Lives | None:
    value = _explicit_residence(person_node) if person_node is not None else None
    return Lives(value, source) if value else None


def _gendered(node: ast.Call, female: bool | None) -> bool | None:
    explicit = _explicit_gender(node)
    if explicit is not None:
        return explicit
    return female if female is not None else _name_gender(node)


class ResidenceTitleChecker(shared_ast.Visitor):
    """Walks record-list calls tracking each book's village, year, default
    residence and default statuses, and checks every person() against them."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self._books: list[_Book] = []
        self._bindings: dict[str, ast.expr] = {}
        self._file_texts: dict[str, str] = {}

    def visit_Module(self, node: ast.Module) -> None:
        self._bindings = module_bindings(node)
        self._file_texts = string_constants(self._bindings)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fname = _call_func_name(node)
        pushed = False
        if fname in _RECORD_CALLS or fname == "census_records":
            self._books.append(self._book(node, census=fname == "census_records"))
            pushed = True

        slots: dict[str, Callable[[ast.Call], list[_Slot]]] = {
            "birth": self._birth, "death": self._death, "marriage": self._marriage,
            "member": self._member, "CensusMember": self._member,
        }
        for slot in slots[fname](node) if fname in slots else []:
            self._check(slot)

        self.generic_visit(node)
        if pushed:
            self._books.pop()

    def _book(self, node: ast.Call, *, census: bool) -> _Book:
        village = _string_literal(_records_arg(node, 4, "village"))
        year = _int_literal(_records_arg(node, 5 if census else 6, "year"))
        if census:
            lives = Lives(village, t("residence.census_village")) if village else None
        else:
            default = _record_defaults_residence(node, self._bindings)
            lives = Lives(default, t("residence.book_default")) if default else None
        return _Book(village, year, lives,
                     default_statuses(node, self._bindings, self._file_texts))

    # --- who a record names -------------------------------------------------

    def _birth(self, node: ast.Call) -> list[_Slot]:
        kwargs = _kwargs(node)
        father = _person_kwarg(kwargs, "father")
        mother = _person_kwarg(kwargs, "mother")
        child = _person_kwarg(kwargs, "child")
        slots: list[_Slot] = []
        # A mother with no residence of her own lives where the father does
        # (births.py inherits father.residence before the record default); a
        # newborn where the father does, else the mother.
        father_lives = _written(father, t("residence.like", role=role_word("father", GEN)))
        if father is not None:
            slots.append(_Slot(father, "father", False, "", None, "all"))
        if mother is not None:
            slots.append(_Slot(mother, "mother", True, "mother", father_lives, "all"))
        if child is not None:
            gender = _record_gender(node)
            female = None if gender is None else gender == "FEMALE"
            slots.append(_Slot(child, "newborn_female" if female else "newborn_male",
                               _gendered(child, female), "",
                               father_lives or _written(mother, t("residence.like", role=role_word("mother", GEN))), None,
                               derived=True))
        for key, label, female in (("god_parent1", "godfather", False),
                                   ("god_parent2", "godmother", True),
                                   ("god_parent3", "", None), ("god_parent4", "", None)):
            godparent = _person_kwarg(kwargs, key)
            if godparent is None:
                continue
            sex = _gendered(godparent, female)
            slots.append(_Slot(godparent, label or ("godmother" if sex else "godfather"),
                               sex, "", None, None))
        slots.extend(self._relatives([(p, rel) for p, rel, _ in _marriage_relatives(node)],
                                     None, None))
        return slots

    def _death(self, node: ast.Call) -> list[_Slot]:
        kwargs = _kwargs(node)
        deceased = _person_kwarg(kwargs, "deceased")
        relatives = _death_relatives(node)
        gender = _record_gender(node)
        female = None if gender is None else gender == "FEMALE"
        # Death.__init__ derives one household residence from the first relative
        # that has one — else the deceased's own — BEFORE RecordDefaults
        # substitutes the parish village. Without mirroring that here, an
        # Собакевичево serf's infant looks like it lives in the parish and RTV001
        # reports a contradiction the generator does not actually produce.
        anchor = next((Lives(value, t("residence.like", role=relative_label(rel, GEN)))
                       for p, rel in relatives if (value := _explicit_residence(p))), None)
        deceased_label = "deceased_female" if female else "deceased_male"
        slots: list[_Slot] = []
        if deceased is not None:
            parent = any(rel in ("FATHER", "MOTHER") for _, rel in relatives)
            slots.append(_Slot(deceased, deceased_label, _gendered(deceased, female), "",
                               anchor, "all", derived=parent))
        household = anchor or _written(deceased, t("residence.like", role=role_word(deceased_label, GEN)))
        slots.extend(self._relatives(relatives, household, None))
        for key in ("witness1", "witness2"):
            witness = _person_kwarg(kwargs, key)
            if witness is not None:
                slots.append(_Slot(witness, "witness", _gendered(witness, None), "", None, None))
        return slots

    def _marriage(self, node: ast.Call) -> list[_Slot]:
        """Everyone a marriage names, on the inherited-residence rule only."""
        kwargs = _kwargs(node)
        slots: list[_Slot] = []
        for role, label, female in (("groom", "groom", False), ("bride", "bride", True)):
            party = _person_kwarg(kwargs, role)
            if party is not None:
                slots.append(_Slot(party, label, female, role, None, "inherited_only"))
        for index in range(1, 7):
            witness = _person_kwarg(kwargs, f"witness{index}")
            if witness is not None:
                slots.append(_Slot(witness, "surety", _gendered(witness, None), "",
                                   None, "inherited_only"))
        slots.extend(self._relatives([(p, rel) for p, rel, _ in _marriage_relatives(node)],
                                     None, "inherited_only"))
        return slots

    def _member(self, node: ast.Call) -> list[_Slot]:
        person = _member_person(node)
        if person is None:
            return []
        member = _Member(node)
        gender = _member_gender(member)
        female = None if gender is None else gender == "FEMALE"
        return [_Slot(person, "household_member", female, "", None, "all", hidden=member.hidden)]

    def _relatives(self, relatives: list[tuple[ast.Call, str | None]],
                   household: Lives | None, rtv001: str | None) -> list[_Slot]:
        out: list[_Slot] = []
        for person, relationship in relatives:
            label, female = BY_RELATIONSHIP.get(relationship or "", ("relative", None))
            out.append(_Slot(person, label, _gendered(person, female), "", household, rtv001))
        return out

    # --- the rules ----------------------------------------------------------

    def _book_now(self) -> _Book:
        return self._books[-1] if self._books else _NO_BOOK

    def _check(self, slot: _Slot) -> None:
        book = self._book_now()
        explicit = _explicit_residence(slot.node)
        lives = (Lives(explicit, t("residence.written")) if explicit is not None
                 else slot.inherited or book.lives)
        if slot.rtv001 is not None:
            self._rtv001(slot, lives, book, explicit is not None)
        rule = next((r for r in corpus_data.estates().owners_and_state if r.parish == book.village), None)
        if rule is not None and not slot.hidden:
            self._owners_and_state(slot, lives, book, rule)

    def _rtv001(self, slot: _Slot, lives: Lives | None, book: _Book,
                stated: bool) -> None:
        status_node = _status_node(slot.node)
        state = next((s for s in corpus_data.estates().state_peasants if book.village in s.books), None)
        expected = _classify_status(status_node, state=state)
        if expected is None:
            return
        if stated and slot.rtv001 == "inherited_only":
            return  # marriage role: the author stated it, the source knows better
        if lives is None:
            return  # indeterminate residence -> skip
        if normalize_village(lives.village) in expected.villages:
            return
        words = words_of(status_node, self._file_texts) or _name_id(status_node) or "?"
        self.issues.append({
            "line": slot.node.lineno,
            **says("RTV001", "elsewhere", who=who(slot.label, slot.node, capital=True), words=words,
                   estate=expected.who, villages=either(expected.villages), village=lives.village,
                   source=lives.source),
        })

    def _owners_and_state(self, slot: _Slot, lives: Lives | None, book: _Book, rule: OwnersAndState) -> None:
        """RTV002 — in the parish's books the state village was the state's, the село its owners'
        (Глуповы Горы and Горелово: the corpus's `[[owners_and_state]]`)."""
        if lives is None:
            return
        village = normalize_village(lives.village)
        in_village = {rule.owners.village: rule.owners.in_, rule.state.village: rule.state.in_}
        if village not in in_village:
            return
        status_node = _status_node(slot.node)
        if status_node is not None:
            words = words_of(status_node, self._file_texts)
            defaulted = False
        elif slot.derived:
            return  # the parent's own status is what to fix
        else:
            default = default_for(book.statuses, slot.role, slot.female is True)
            words, defaulted = (default.text, True) if default is not None else (None, False)
        if not words or "солдат" in words.lower():  # i18n: content — status words: vocabulary
            return
        owner, state = names_owner(words), estate_of(words) == "state"
        if (village == rule.state.village and owner) or (village == rule.owners.village and state):
            variant = ("owner_in_state_village" if village == rule.state.village else "state_in_owners_village") \
                + ("_default" if defaulted else "")
            self.issues.append({
                "line": slot.node.lineno,
                **says("RTV002", variant, who=who(slot.label, slot.node, capital=True), lives=in_village[village],
                       source=lives.source, words=words, state=rule.state.in_, owners=rule.owners.in_),
            })


def relative_label(relationship: str | None, case: int) -> Message:
    label, _ = BY_RELATIONSHIP.get(relationship or "", ("relative", None))
    return role_word(label, case)


def _collect(tree: ast.AST) -> list[Issue]:
    checker = ResidenceTitleChecker()
    checker.visit(tree)
    return checker.issues


def _parse(path: Path) -> ast.AST | SyntaxError:
    try:
        return shared_ast.parse(Path(path).read_text(encoding="utf-8"))
    except SyntaxError as e:
        return e


def check_file(path: Path) -> list[str]:
    tree = _parse(path)
    if isinstance(tree, SyntaxError):
        return [line_text(path, issue("SYN002", "detail", tree.lineno or 1, level="error", detail=tree.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree)]


def check_file_structured(path: Path) -> list[Issue]:
    tree = _parse(path)
    if isinstance(tree, SyntaxError):
        return [as_dict(issue("SYN001", "detail", tree.lineno or 1, level="error", detail=tree.msg))]
    return [{"level": "error", "line": i["line"], "message": i["message"]} for i in _collect(tree)]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    errors = [e for arg in sys.argv[1:] for e in check_file(Path(arg))]
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
