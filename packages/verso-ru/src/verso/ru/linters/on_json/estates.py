"""The rules that read the book and the corpus's estates (class `context`, needs `book`, `estates`): the estate a
parent and a child, or the spouses, state (PSA001-PSA004), a status against the village a person lives in (RTV001,
RTV002), a full patronymic of a low status (PAF001), a roll's two ages against the revision gap (CAI002) and the
books of the civil registry (ZGS001-ZGS006).

The book is a node of the document (`written` of a record set: its village, church, year, `civil`, `defaults`); the
estates are those of the workspace the file is linted in (`lint_records(workspace=)`, owner decision Д2): its
`estates.toml`, its landlords' statuses, its names table. A workspace without a corpus has no estate to read and the
findings that rest on one are warnings (`walk.estates_present`, the analogue of H7); every lookup of a name goes
through `walk.without_names`.

A status is read as the checks read the expression that wrote it: the JSON holds a catalog constant as `{text, gender}`
(the constant a name in the source), a literal as its text, a status a record did not write as no key at all
(`status=None` written is a key holding none, as the checks read `Constant(None)`). Of the constants that spell one
text and sex the walk names the one `walk.status_name` picks; the estate and role of the aliases agree
(`test_status_collisions_agree_on_the_estate`), what differs is the name a finding offers in its fix (`fix`, `offer`,
`base` of PSA) — dsllint names the alias the source wrote.

What the checks read off the SYNTAX alone has no JSON counterpart, and the walk reads the values:

* a status held in a name the file binds (`GORELOVO_PEASANT = "…"`) is the string to PSA and ZGS004 (as to the walk),
  but the identifier to RTV001 and PAF001, which classify the name; the JSON holds the text, so the walk classifies
  the text. A `Status(…)` the file builds itself is read as the catalog constant of its value, where the checks see
  an unknown name.
* a person given by position (`birth(1, Gender.MALE, …, person(…))`), a relative of a `relatives=` the checks cannot
  read (a tuple, a name) and a person bound outside the record are not seen by PSA and RTV, which read keywords and a
  literal list; the walk sees every persona the record holds (and a person bound once but used in two records is
  one finding per record). The record's sex is the one `gender` wrote, by keyword or position, where `_record_gender`
  reads the second positional argument alone.
* a book's `RecordDefaults` is written whole: `status_groom` is `status_male` unless the author wrote another. RTV and
  PSA read the groom through `status_groom`, then `status_male`, so the pair needs no telling apart; ZGS004 drops an
  equal `status_groom` (a finding fewer than dsllint for an author who wrote that equal status too).
* a value held in a name (`YEAR = 1858`, `VILLAGE = "…"`, `R = "…"`) is the value to the walk and nothing to the checks,
  which read literals: the book's year (PAF001, ZGS003, CAI002's census year: dsllint is silent on a roll of `YEAR`, the
  walk fires), its village and default residence (RTV001, RTV002), and the token of ZGS004 for a status held in a
  name (the identifier there, the words here). A year passed by keyword is the same: PAF001 reads a positional one
  only, ZGS003 both; the walk reads the book's `year`.
* ZGS005 takes the first of the three name spellings in the order of `person()`'s parameters; the check takes
  the positional ones first, then the keywords in the order the source wrote them.
* PAF001 reads `patr_orig`, else `patr_old`; the check stops at a keyword `patr_orig=None` and does not read
  `patr_old` then.
* CAI002: a `departure_year`, `departure_reason`, `previous_age` written as a keyword none (or reached by position)
  is a key of the call to both readers.
* ZGS002's section month is recovered from the context the export keeps (`b_month`, else `k_month` less the
  month the section advanced it by when the registration day is smaller than the birth day); a record that wrote its
  own birth and registration months needs no section.
"""
from __future__ import annotations

from calendar import Month
from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple, cast

from verso.core.i18n import Message
from verso.core.records.fields import split_context, vocabulary
from verso.ru import corpus_data
from verso.ru.census_revisions import PREVIOUS_AGE_REVISION_YEAR
from verso.ru.domain.estates import estate_of
from verso.ru.domain.statuses import child_status_for
from verso.ru.gender import Gender
from verso.ru.linters.checks import census_age, civil_register, parent_status, patronymic_form, residence_title
from verso.ru.linters.checks.status_words import (
    DAT, GEN, NAME_PARAMS, NOM, Default, counterpart, default_for, estate_words, offer, role_word, split_role, tables)
from verso.ru.linters.on_json.census import Household, Member, age_years
from verso.ru.linters.on_json.walk import (
    FileView, Finding, Rule, as_int, as_text, finding, gender_from_name, member_gender, only, personas, slot_of,
    status_name_or_none)
from verso.ru.messages import t
from verso.ru.naming import modernize_orthography
from verso.ru.parent_age_text import FIELDS, ROLES, read_comment

__all__ = ["RULES"]

type Node = Mapping[str, Any]

_GENDER_FEMALE = Gender.FEMALE.name


# --- a status, as the checks read the expression that wrote it ---------------------------------------------------

class _Reading(NamedTuple):
    """`parent_status._status_const` of a status the JSON holds: `kind` is `const` (a catalog constant), `text` (a
    string a constant spells), `free` (a string none does), `unknown` (a status the checks cannot read) or `none` (not
    written); `const` the constant, `words` the words it stands for."""
    kind: str
    const: str | None
    words: str | None

    @property
    def explicit(self) -> bool:
        return self.kind in ("const", "text")


_NONE = _Reading("none", None, None)
_UNKNOWN = _Reading("unknown", None, None)


def _catalog_name(value: Node) -> tuple[str | None, str | None]:
    """The catalog constant a `{text, gender}` status is, and its words: the name `walk.status_name_or_none` picks of
    those that spell it, if the catalog holds it (a marital status and a status the file builds are no catalog
    status to the checks: they read an unknown name)."""
    text = as_text(value.get("text"))
    if text is None:
        return None, None
    name = status_name_or_none(text, as_text(value.get("gender")))
    return (name, text) if name is not None and name in tables().texts else (None, text)


def _reading_of(written: Node) -> _Reading:
    """`parent_status._status_const` of what a `person()` wrote."""
    if "status" not in written:
        return _NONE
    status = written["status"]
    if isinstance(status, Mapping):
        name, text = _catalog_name(cast(Node, status))
        return _Reading("const", name, text) if name is not None else _UNKNOWN
    if isinstance(status, str):
        const = tables().by_text.get(status)
        return _Reading("text", const, status) if const else _Reading("free", None, status)
    return _UNKNOWN


def _defaults_of(defaults: object) -> dict[str, Default]:
    """`status_words.default_statuses` of a book's `defaults`: the statuses it gives, by its `status_*` keys."""
    out: dict[str, Default] = {}
    if not isinstance(defaults, Mapping):
        return out
    for key, value in cast(Node, defaults).items():
        if not key.startswith("status_"):
            continue
        if isinstance(value, Mapping):
            name, text = _catalog_name(cast(Node, value))
            if name is not None and text is not None:
                out[key] = Default(name, text)
        elif isinstance(value, str):
            out[key] = Default(tables().by_text.get(value), value)
    return out


def _named(label: str, written: Node, case: int = NOM, capital: bool = False) -> Message:
    """`status_words.who`: the role in `case` and the name as the record writes it."""
    word = role_word(label, case, capital)
    name = " ".join(text for kwarg, _ in NAME_PARAMS if (text := as_text(written.get(kwarg))))
    return t("words.who", role=word, name=name) if name else word


def _relationship(view: FileView, persona: Node) -> str | None:
    """The `Relationship` a relative's link wrote, as the checks name it (`FATHER`)."""
    name = as_text(view.written("relative", persona["link"]).get("relationship"))
    return name.upper() if name else None


def _record_female(written: Node) -> bool | None:
    """`_record_gender` of a birth or a death: `Gender.FEMALE` is true, `Gender.MALE` false, no sex none."""
    gender = as_text(written.get("gender"))
    return None if gender is None else gender.upper() == _GENDER_FEMALE


def _persona(record: Node, role: str) -> Node | None:
    return next(iter(personas(record, role)), None)


# --- PSA001-PSA004: a parent's estate against a child's, a husband's against a wife's --------------------------

class _Party(NamedTuple):
    """One side of a comparison: the person, the role that picks a `RecordDefaults` fallback, the sex it keys on and
    the word a finding calls them by."""
    written: Node
    reading: _Reading
    role: str
    female: bool
    label: str


def _party(view: FileView, persona: Node, role: str, female: bool, label: str) -> _Party:
    written = view.written("person", persona)
    return _Party(written, _reading_of(written), role, female, label)


class _Comparison:
    """`parent_status.ParentStatusChecker` over the personas of a record: the pairs it compares and what it says."""

    def __init__(self, rid: str, defaults: dict[str, Default]) -> None:
        self.rid = rid
        self.defaults = defaults
        self.found: list[Finding] = []

    def _default_estate(self, party: _Party) -> tuple[str | None, str | None]:
        default = default_for(self.defaults, party.role, party.female)
        if default is None or default.const is None:
            return None, None
        return parent_status.estates()[default.const], default.const

    def compare(self, parent: _Party, child: _Party, spouses: bool = False) -> None:
        p_explicit, c_explicit = parent.reading.explicit, child.reading.explicit
        if p_explicit and c_explicit:
            self._psa001(parent, child, parent.reading.const, child.reading.const, spouses)
            return
        p_kind, c_kind = parent.reading.kind, child.reading.kind
        if p_kind == "none" and c_kind == "none":
            return
        free_default = any(
            kind == "none" and (d := default_for(self.defaults, party.role, party.female)) is not None
            and d.const is None
            for party, kind in ((parent, p_kind), (child, c_kind)))
        if "free" in (p_kind, c_kind) or free_default:
            self._compare_free(parent, child, spouses)
            return
        if p_explicit and c_kind == "none":
            self._psa002(child, parent, parent.reading.const, spouses, silent_is_child=True)
        elif c_explicit and p_kind == "none":
            self._psa002(parent, child, child.reading.const, spouses, silent_is_child=False)

    def _psa001(self, parent: _Party, child: _Party, p_const: str | None, c_const: str | None,
                spouses: bool) -> None:
        if p_const is None or c_const is None:
            return
        p_estate, c_estate = parent_status.estates()[p_const], parent_status.estates()[c_const]
        if parent_status.estates_compatible(p_estate, c_estate):
            return
        exempt = parent_status.SPOUSE_EXEMPT_ESTATES if spouses else parent_status.EXEMPT_ESTATES
        if p_estate in exempt or c_estate in exempt:
            return
        self._contradiction(parent, child, tables().texts[p_const], tables().texts[c_const], spouses)

    def _psa002(self, silent: _Party, stated: _Party, other_const: str | None, spouses: bool, *,
                silent_is_child: bool) -> None:
        if other_const is None:
            return
        other_estate = parent_status.estates()[other_const]
        default_estate, default_const = self._default_estate(silent)
        if default_estate is None or default_const is None:
            return
        if parent_status.estates_compatible(default_estate, other_estate):
            if (spouses and parent_status.as_peasant(default_estate) == "PEASANT"
                    and parent_status.as_peasant(other_estate) != "PEASANT"):
                self._silent("PSA004", silent, stated, tables().texts[default_const], other_const, spouses,
                             silent_is_child=silent_is_child)
            return
        exempt = parent_status.SPOUSE_EXEMPT_ESTATES if spouses else parent_status.EXEMPT_ESTATES
        if other_estate in exempt or default_estate in exempt:
            return
        self._silent("PSA002", silent, stated, tables().texts[default_const], other_const, spouses,
                     silent_is_child=silent_is_child)

    def _compare_free(self, parent: _Party, child: _Party, spouses: bool) -> None:
        exempt = parent_status.SPOUSE_EXEMPT_ESTATES if spouses else parent_status.EXEMPT_ESTATES
        read: list[tuple[str | None, str | None, str, bool]] = []
        for party in (parent, child):
            const, kind = party.reading.const, party.reading.kind
            if kind == "unknown":
                return
            silent = kind == "none"
            if silent:
                default = default_for(self.defaults, party.role, party.female)
                if default is None:
                    return
                const, text = default.const, default.text
            else:
                text = party.reading.words
            if const is not None and parent_status.estates().get(const) in exempt:
                return
            estate = estate_words(text)
            if estate == "clergy" and not spouses:
                return
            read.append((estate, const, text or "", silent))
        (p_estate, p_const, p_words, p_silent), (c_estate, c_const, c_words, c_silent) = read
        if p_estate is None or c_estate is None:
            if spouses and p_silent != c_silent:
                silent_estate, stated_estate = (p_estate, c_estate) if p_silent else (c_estate, p_estate)
                if silent_estate is None and stated_estate is not None:
                    if p_silent:
                        self._silent("PSA004", parent, child, p_words, c_const, spouses, silent_is_child=False,
                                     stated_words=c_words)
                    else:
                        self._silent("PSA004", child, parent, c_words, p_const, spouses, silent_is_child=True,
                                     stated_words=p_words)
            return
        if parent_status.free_estates_compatible(p_estate, c_estate):
            return
        if p_silent:
            self._silent("PSA002", parent, child, p_words, c_const, spouses, silent_is_child=False,
                         stated_words=c_words)
        elif c_silent:
            self._silent("PSA002", child, parent, c_words, p_const, spouses, silent_is_child=True,
                         stated_words=p_words)
        else:
            self._contradiction(parent, child, p_words, c_words, spouses)

    def _contradiction(self, parent: _Party, child: _Party, p_words: str, c_words: str, spouses: bool) -> None:
        self.found.append(finding(
            "PSA001", "spouses" if spouses else "generations", self.rid,
            child=_named(child.label, child.written, capital=True), child_words=c_words,
            parent=_named(parent.label, parent.written), parent_words=p_words))

    def _silent(self, code: str, silent: _Party, stated: _Party, default_words: str, stated_const: str | None,
                spouses: bool, *, silent_is_child: bool, stated_words: str | None = None) -> None:
        if stated_words is None:
            stated_words = stated.reading.words or (tables().texts[stated_const] if stated_const else "")
        variant = ("female" if silent.female else "male") + ("_spouses" if spouses else "_generations")
        self.found.append(finding(
            code, variant, self.rid, silent=_named(silent.label, silent.written, GEN), default=default_words,
            stated=_named(stated.label, stated.written), stated_words=stated_words,
            fix=_fix(silent, stated, stated_const, spouses, silent_is_child)))

    def child_role(self, child: _Party, female: bool) -> None:
        """`ParentStatusChecker._check_child_role`: a newborn styled by an adult role."""
        const = child.reading.const
        if not child.reading.explicit or const is None:
            return
        if parent_status.roles().get(const, "") in parent_status.CHILD_ROLES:
            return
        if parent_status.estates()[const] in parent_status.EXEMPT_ESTATES:
            return
        suggestion = counterpart(const, female=female, child=True)
        newborn = "newborn_female" if female else "newborn_male"
        words = tables().texts[const]
        if suggestion:
            self.found.append(finding("PSA003", "offer", self.rid, newborn=_named(newborn, child.written, DAT, True),
                                      words=words, offer=offer(suggestion)))
        else:
            self.found.append(finding("PSA003", "forms", self.rid, newborn=_named(newborn, child.written, DAT, True),
                                      words=words, base=split_role(const)[0]))


def _fix(silent: _Party, stated: _Party, stated_const: str | None, spouses: bool, silent_is_child: bool) -> Message:
    """`parent_status._fix`: what to write on the silent side — the stated estate in the silent person's own sex,
    when the catalog holds it."""
    dative = role_word(silent.label, DAT)
    suggestion = None
    if stated_const is not None and (spouses or not silent_is_child):
        suggestion = counterpart(stated_const, female=silent.female,
                                 wife=silent.female and (spouses or silent.role == "mother"))
    mother = silent.role == "mother"
    if suggestion:
        return (t("parent_status.fix_offer_mother", role=dative, offer=offer(suggestion)) if mother
                else t("parent_status.fix_offer", role=dative, offer=offer(suggestion)))
    stated_role = role_word(stated.label, GEN)
    return (t("parent_status.fix_like_mother", role=dative, stated=stated_role) if mother
            else t("parent_status.fix_like", role=dative, stated=stated_role))


def _derives(consulted: _Party | None, female: bool) -> bool:
    """Whether `child_status_for` would derive a status from the consulted parent (`_child_derives`)."""
    if consulted is None or not consulted.reading.explicit or consulted.reading.const is None:
        return False
    gender = Gender.FEMALE if female else Gender.MALE
    return child_status_for(tables().texts[consulted.reading.const], gender) is not None


def _compare_birth(view: FileView, record: Node, comparison: _Comparison) -> None:
    father_node, mother_node, child_node = (_persona(record, role) for role in ("father", "mother", "child"))
    child_female = _record_female(view.written("birth", record)) is True
    father = _party(view, father_node, "father", False, "father") if father_node else None
    mother = _party(view, mother_node, "mother", True, "mother") if mother_node else None
    if child_node is not None:
        child = _party(view, child_node, "child", child_female, "child")
        consulted = father if father is not None and "status" in father.written else mother
        derived = child.reading.kind == "none" and _derives(consulted, child_female)
        if father is not None and not derived:
            comparison.compare(father, child)
        if mother is not None and not derived:
            comparison.compare(mother, child)
        comparison.child_role(child, child_female)
    if father_node is not None and mother_node is not None:
        comparison.compare(_party(view, father_node, "father", False, "husband"),
                           _party(view, mother_node, "mother", True, "wife"), spouses=True)


def _compare_death(view: FileView, record: Node, comparison: _Comparison) -> None:
    deceased_node = _persona(record, "deceased")
    if deceased_node is None:
        return
    female = _record_female(view.written("death", record)) is True
    relatives = [(p, _relationship(view, p)) for p in personas(record, "relative")]
    deceased = _party(view, deceased_node, "deceased", female, "deceased_female" if female else "deceased_male")
    consulted = next((p for p, rel in relatives if rel == "FATHER" and "status" in view.written("person", p)), None)
    if consulted is None:
        consulted = next((p for p, rel in relatives if rel == "MOTHER" and "status" in view.written("person", p)),
                         None)
    derived = deceased.reading.kind == "none" and _derives(
        _party(view, consulted, "relative", False, "relative") if consulted is not None else None, female)
    for person, relationship in relatives:
        if relationship in ("FATHER", "MOTHER"):
            if derived:
                continue
            comparison.compare(
                _party(view, person, "relative", relationship == "MOTHER",
                       "father" if relationship == "FATHER" else "mother"), deceased)
        elif relationship == "HUSBAND":                       # the check calls the wife «deceased_female» whatever the sex
            comparison.compare(_party(view, person, "relative", False, "husband"),
                               deceased._replace(label="deceased_female"), spouses=True)


def _compare_marriage(view: FileView, record: Node, comparison: _Comparison) -> None:
    for person, relationship in ((p, _relationship(view, p)) for p in personas(record, "relative")):
        if relationship not in ("FATHER", "MOTHER"):
            continue
        ref = as_text(view.written("relative", person["link"]).get("relationship_ref"))
        if ref and "жених" in ref:  # i18n: content — the reference words the DSL writes
            node, role, female = _persona(record, "groom"), "groom", False
        elif ref and "невест" in ref:  # i18n: content — the reference words the DSL writes
            node, role, female = _persona(record, "bride"), "bride", True
        else:
            continue
        if node is None:
            continue
        comparison.compare(
            _party(view, person, "relative", relationship == "MOTHER", "father" if relationship == "FATHER" else "mother"),
            _party(view, node, role, female, role))


_COMPARE = {"birth": _compare_birth, "death": _compare_death, "marriage": _compare_marriage}


def _psa(view: FileView) -> Iterator[Finding]:
    """`parent_status.ParentStatusChecker` for each birth, death and marriage of a book."""
    for doc, record in view.records({"births", "deaths", "marriages"}):
        compare = _COMPARE.get(record["kind"])
        if compare is None:
            continue
        comparison = _Comparison(record["id"], _defaults_of(doc.get("written", {}).get("defaults")))
        compare(view, record, comparison)
        yield from comparison.found


def psa001(view: FileView) -> Iterator[Finding]:
    return only("PSA001", _psa(view))


def psa002(view: FileView) -> Iterator[Finding]:
    return only("PSA002", _psa(view))


def psa003(view: FileView) -> Iterator[Finding]:
    return only("PSA003", _psa(view))


def psa004(view: FileView) -> Iterator[Finding]:
    return only("PSA004", _psa(view))


# --- RTV001, RTV002: a status against where its bearer lives ----------------------------------------------------

class _Slot(NamedTuple):
    """`residence_title._Slot`: one person of a record, as both rules read them."""
    written: Node
    label: str
    female: bool | None
    role: str
    inherited: residence_title.Lives | None
    rtv001: str | None
    derived: bool = False
    hidden: bool = False


class _Book(NamedTuple):
    village: str | None
    lives: residence_title.Lives | None
    statuses: dict[str, Default]


def _gendered(written: Node, female: bool | None) -> bool | None:
    """`residence_title._gendered`: the sex written, else the slot's, else the first name's."""
    explicit = as_text(written.get("gender"))
    if explicit is not None and explicit.upper() in (_GENDER_FEMALE, Gender.MALE.name):
        return explicit.upper() == _GENDER_FEMALE
    if female is not None:
        return female
    name = as_text(written.get("name_orig"))
    if not name:
        return None
    gender = gender_from_name(modernize_orthography(name))
    return None if gender is None else gender.name == _GENDER_FEMALE


def _lived(written: Node, source: Message) -> residence_title.Lives | None:
    value = as_text(written.get("residence"))
    return residence_title.Lives(value, source) if value else None


def _relatives(view: FileView, record: Node, household: residence_title.Lives | None,
               rtv001: str | None) -> Iterator[_Slot]:
    for persona in personas(record, "relative"):
        label, female = residence_title.BY_RELATIONSHIP.get(_relationship(view, persona) or "", ("relative", None))
        written = view.written("person", persona)
        yield _Slot(written, label, _gendered(written, female), "", household, rtv001)


def _birth_slots(view: FileView, record: Node) -> Iterator[_Slot]:
    father_node, mother_node, child_node = (_persona(record, role) for role in ("father", "mother", "child"))
    father = view.written("person", father_node) if father_node is not None else None
    mother = view.written("person", mother_node) if mother_node is not None else None
    child = view.written("person", child_node) if child_node is not None else None
    father_lives = _lived(father, t("residence.like", role=role_word("father", GEN))) if father is not None else None
    if father is not None:
        yield _Slot(father, "father", False, "", None, "all")
    if mother is not None:
        yield _Slot(mother, "mother", True, "mother", father_lives, "all")
    if child is not None:
        female = _record_female(view.written("birth", record))
        mother_lives = (_lived(mother, t("residence.like", role=role_word("mother", GEN)))
                        if mother is not None else None)
        yield _Slot(child, "newborn_female" if female else "newborn_male", _gendered(child, female), "",
                    father_lives or mother_lives, None, derived=True)
    for slot, label, female in ((1, "godfather", False), (2, "godmother", True), (3, "", None), (4, "", None)):
        godparent = next((p for p in personas(record, "godparent") if p.get("slot") == slot), None)
        if godparent is None:
            continue
        written = view.written("person", godparent)
        sex = _gendered(written, female)
        yield _Slot(written, label or ("godmother" if sex else "godfather"), sex, "", None, None)
    yield from _relatives(view, record, None, None)


def _death_slots(view: FileView, record: Node) -> Iterator[_Slot]:
    deceased_node = _persona(record, "deceased")
    female_record = _record_female(view.written("death", record))
    relatives = [(p, _relationship(view, p)) for p in personas(record, "relative")]
    anchor = next((residence_title.Lives(value, t("residence.like", role=residence_title.relative_label(rel, GEN)))
                   for p, rel in relatives if (value := as_text(view.written("person", p).get("residence")))), None)
    deceased_label = "deceased_female" if female_record else "deceased_male"
    deceased = view.written("person", deceased_node) if deceased_node is not None else None
    if deceased is not None:
        parent = any(rel in ("FATHER", "MOTHER") for _, rel in relatives)
        yield _Slot(deceased, deceased_label, _gendered(deceased, female_record), "", anchor, "all", derived=parent)
    household = anchor or (_lived(deceased, t("residence.like", role=role_word(deceased_label, GEN)))
                           if deceased is not None else None)
    yield from _relatives(view, record, household, None)
    for persona in personas(record, "witness"):
        written = view.written("person", persona)
        yield _Slot(written, "witness", _gendered(written, None), "", None, None)


def _marriage_slots(view: FileView, record: Node) -> Iterator[_Slot]:
    for role, label, female in (("groom", "groom", False), ("bride", "bride", True)):
        if (party := _persona(record, role)) is not None:
            yield _Slot(view.written("person", party), label, female, role, None, "inherited_only")
    for witness in personas(record, "witness"):
        written = view.written("person", witness)
        yield _Slot(written, "surety", _gendered(written, None), "", None, "inherited_only")
    yield from _relatives(view, record, None, "inherited_only")


def _member_slots(view: FileView, record: Node) -> Iterator[_Slot]:
    for persona in personas(record, "member"):
        member = Member(view, persona)
        sex = member_gender(member.person, member.role)
        yield _Slot(member.person, "household_member", None if sex is None else sex == _GENDER_FEMALE, "", None, "all",
                    hidden=member.hidden)


_SLOTS = {"birth": _birth_slots, "death": _death_slots, "marriage": _marriage_slots, "household": _member_slots}


def _classify(status: object, state: Any) -> residence_title.Expected | None:
    """`residence_title._classify_status` of a status the JSON holds: where it says its bearer lived, or none."""
    landlords = corpus_data.estates().landlords
    if isinstance(status, Mapping):
        ident, _ = _catalog_name(cast(Node, status))
        if ident is None:
            return None
        if "_DVOROVY" in ident:
            return None
        key = residence_title.landlord_key(ident)
        if key is not None and key in landlords:
            return residence_title.landlord_expected(landlords[key])
        if state is not None and ident.startswith(residence_title.YASAK_NAME_PREFIXES):
            return residence_title.Expected((state.village,), state.who)
        return None
    if not isinstance(status, str):
        return None
    if any(m in status for m in residence_title.SERF_MARKERS):
        return None
    if any(m in status for m in residence_title.LANDLORD_MARKERS):
        for landlord in landlords.values():
            if landlord.token in status:
                return residence_title.landlord_expected(landlord)
        return None
    if state is not None and any(sub in status for sub in residence_title.YASAK_SUBSTRINGS):
        return residence_title.Expected((state.village,), state.who)
    return None


def _words(status: object) -> str | None:
    """`status_words.words_of` of a status the JSON holds."""
    if isinstance(status, Mapping):
        name, text = _catalog_name(cast(Node, status))
        return text if name is not None else None
    return status if isinstance(status, str) else None


def _rtv(view: FileView) -> Iterator[Finding]:
    """`residence_title.ResidenceTitleChecker` for each person of a book."""
    estates = corpus_data.estates()
    for doc, record in view.records({"births", "deaths", "marriages", "census"}):
        kind = record["kind"]
        slots = _SLOTS.get(kind)
        if slots is None:
            continue
        written = doc.get("written", {})
        village = as_text(written.get("village"))
        if doc["kind"] == "census":
            lives = residence_title.Lives(village, t("residence.census_village")) if village else None
        else:
            default = as_text((written.get("defaults") or {}).get("residence"))
            lives = residence_title.Lives(default, t("residence.book_default")) if default else None
        statuses = _defaults_of(written.get("defaults"))       # a census book's too (`_book` reads them for each set)
        book = _Book(village, lives, statuses)
        state = next((s for s in estates.state_peasants if book.village in s.books), None)
        rule = next((r for r in estates.owners_and_state if r.parish == book.village), None)
        for slot in slots(view, record):
            explicit = as_text(slot.written.get("residence"))
            lived = (residence_title.Lives(explicit, t("residence.written")) if explicit is not None
                     else slot.inherited or book.lives)
            if slot.rtv001 is not None:
                yield from _rtv001(record["id"], slot, lived, state, explicit is not None)
            if rule is not None and not slot.hidden:
                yield from _rtv002(record["id"], slot, lived, book, rule)


def _rtv001(rid: str, slot: _Slot, lives: residence_title.Lives | None, state: Any,
            stated: bool) -> Iterator[Finding]:
    status = slot.written.get("status")
    expected = _classify(status, state)
    if expected is None or (stated and slot.rtv001 == "inherited_only") or lives is None:
        return
    if residence_title.normalize_village(lives.village) in expected.villages:
        return
    yield finding("RTV001", "elsewhere", rid, who=_named(slot.label, slot.written, capital=True),
                  words=_words(status) or "?", estate=expected.who, villages=residence_title.either(expected.villages),
                  village=lives.village, source=lives.source)


def _rtv002(rid: str, slot: _Slot, lives: residence_title.Lives | None, book: _Book,
            rule: Any) -> Iterator[Finding]:
    """The state village was the state's, the село its owners' (`residence_title._owners_and_state`)."""
    if lives is None:
        return
    village = residence_title.normalize_village(lives.village)
    in_village = {rule.owners.village: rule.owners.in_, rule.state.village: rule.state.in_}
    if village not in in_village:
        return
    if "status" in slot.written:
        words, defaulted = _words(slot.written["status"]), False
    elif slot.derived:
        return
    else:
        default = default_for(book.statuses, slot.role, slot.female is True)
        words, defaulted = (default.text, True) if default is not None else (None, False)
    if not words or "солдат" in words.lower():  # i18n: content — status words: vocabulary
        return
    owner, state = residence_title.names_owner(words), estate_of(words) == "state"
    if (village == rule.state.village and owner) or (village == rule.owners.village and state):
        variant = ("owner_in_state_village" if village == rule.state.village else "state_in_owners_village") \
            + ("_default" if defaulted else "")
        yield finding("RTV002", variant, rid, who=_named(slot.label, slot.written, capital=True),
                      lives=in_village[village], source=lives.source, words=words, state=rule.state.in_,
                      owners=rule.owners.in_)


def rtv001(view: FileView) -> Iterator[Finding]:
    return only("RTV001", _rtv(view))


def rtv002(view: FileView) -> Iterator[Finding]:
    return only("RTV002", _rtv(view))


# --- PAF001: a full patronymic of a person whose status is not a high one ---------------------------------------

# The documents the check exempts by the verb of the record: the name lists and the external cards. A test holds the
# verbs to the factories these documents are made by.
_VERBATIM_DOCS = frozenset({"name_list", "external_sources"})


def _high_rank(status: object) -> bool:
    """`patronymic_form._is_high_rank` of a status the JSON holds: a constant by its name, a literal by its words."""
    if isinstance(status, Mapping):
        ident = _catalog_name(cast(Node, status))[0] or ""     # a status the file builds: an unknown name, no token in it
        if any(token in ident for token in patronymic_form.LOW_RANK_NAME_TOKENS):
            return False
        return any(token in ident for token in patronymic_form.HIGH_RANK_NAME_TOKENS)
    if not isinstance(status, str):
        return False
    low = status.lower()
    if any(token in low for token in patronymic_form.LOW_RANK_TEXT):
        return False
    return any(token in low for token in patronymic_form.HIGH_RANK_TEXT)


def paf001(view: FileView) -> Iterator[Finding]:
    """A full patronymic («-ович») on a person whose status is not a high one (`patronymic_form`), but in the sources
    transcribed from a printed catalog and in books of 1918 on."""
    for doc, record in view.records():
        year = doc.get("written", {}).get("year")
        if doc.get("kind") in _VERBATIM_DOCS or (
                isinstance(year, int) and not isinstance(year, bool) and year >= patronymic_form.SOVIET_ERA_FROM):
            continue
        for persona in personas(record):
            written = view.written("person", persona)
            patronymic = as_text(written.get("patr_orig"))
            if patronymic is None:
                patronymic = as_text(written.get("patr_old"))
            if patronymic is None or not patronymic_form.is_full_form(patronymic):
                continue
            if _high_rank(written.get("status")):
                continue
            yield finding("PAF001", "full_form", record["id"], patr=patronymic)


# --- CAI002: the two ages of a roll member against the revision gap ----------------------------------------------

def _source_text(value: object) -> str | None:
    """`census_age._literal_source_str`: the text of a number or a string, the way the source wrote it."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    return str(value)


def _source_repr(value: object) -> str:
    return repr(value) if isinstance(value, str) else str(_source_text(value))


def cai002(view: FileView) -> Iterator[Finding]:
    """A member whose age less the previous age is not the revision gap, within a year (`census_age`)."""
    for doc, record in view.records({"census"}):
        year = doc["written"].get("year")
        if not isinstance(year, int) or isinstance(year, bool):
            continue
        previous_year = PREVIOUS_AGE_REVISION_YEAR.get(year)
        if previous_year is None:
            continue
        for m in Household(view, record).every:
            link = m.link
            if "departure_year" in link or "departure_reason" in link or m.hidden:
                continue
            age = link.get("age")
            if age is None:
                continue
            if "previous_age" in link:
                previous = link["previous_age"]
                age_text = _source_text(age)
                if age_text is not None and age_text == _source_text(previous):
                    continue
                previous_years, shown = age_years(previous), _source_repr(previous)
            else:
                comment = m.comment
                found = census_age.PREV_AGE_COMMENT_RE.search(comment) if comment else None
                if found is None:
                    continue
                payload = found.group(1).strip()
                previous_years, shown = census_age.age_years_str(payload), f"{payload!r} (from comment)"
            years = age_years(age)
            if years is None or previous_years is None:
                continue
            gap, diff = year - previous_year, years - previous_years
            if abs(diff - gap) <= census_age.CAI002_TOLERANCE:
                continue
            yield finding("CAI002", "gap", record["id"], who=m.who, age=_source_repr(age), previous=shown,
                          diff=diff, year=year, gap=gap, previous_year=previous_year)


# --- ZGS001-ZGS006: the books of the civil registry ---------------------------------------------------------

_BOOKS = frozenset({"births", "deaths", "marriages"})        # `civil_register._SETS`: the record sets it reads


def _civil(doc: Node) -> bool:
    return doc.get("written", {}).get("civil") is True


def _month(value: object) -> int | None:
    """A written month's number (`civil_register._month`): `march` is 3."""
    return Month[value.upper()].value if isinstance(value, str) and value.upper() in Month.__members__ else None


def zgs001(view: FileView) -> Iterator[Finding]:
    """What only a church writes in a civil book: a christening entry, a godparent, a surety, the clergy."""
    for doc, record in view.records(_BOOKS):
        if not _civil(doc):
            continue
        kind = record["kind"]
        if kind == "christening":
            yield finding("ZGS001", "christening", record["id"], token="christening")
        slots = civil_register.CHURCH_SLOTS.get(kind, ())
        for persona in personas(record):
            if persona["role"] != "relative" and (slot := slot_of(record, persona)) in slots:
                yield finding("ZGS001", "slot", record["id"], token=slot, slot=slot)


def _section_month(context: Mapping[str, Any], b_day: int | None, k_day: int | None) -> int | None:
    """The month the `birth_month` section a birth stands in gave: the birth's month if the section gave it, else
    the registration's, less the month the section advanced it by when the registration day is smaller than the
    birth day."""
    if (month := _month(context.get("b_month"))) is not None:
        return month
    registration = _month(context.get("k_month"))
    if registration is None:
        return None
    if b_day is not None and k_day is not None and k_day < b_day:
        return (registration - 2) % 12 + 1
    return registration


def zgs002(view: FileView) -> Iterator[Finding]:
    """A civil birth registered before it was born, on the months and years the record wrote and its section and book
    gave (`civil_register._registered_before_birth`)."""
    view.require_context()              # the section's months are read from the context an export keeps (0.1.16)
    cls = vocabulary().by_code["birth"]
    for doc, record in view.records({"births"}):
        if not _civil(doc) or record["kind"] != "birth":
            continue
        call = view.written("birth", record)
        _, context = split_context(cls, record.get("written", {}))
        b_day, k_day = as_int(call.get("b_day")), as_int(call.get("k_day"))
        block_month = _section_month(context, b_day, k_day)
        b_month = _month(call.get("b_month")) or block_month
        k_written, k_year = _month(call.get("k_month")), as_int(call.get("k_year"))
        year = as_int(call.get("year")) or as_int(context.get("year")) or as_int(doc["written"].get("year"))
        if k_written is None and k_year is None:
            continue
        k_month = k_written or block_month
        if b_month is None or k_month is None:
            continue
        birth = (year or 0, b_month, b_day or 1)
        registration = (k_year or year or 0, k_month, k_day or 31)
        if registration < birth:
            yield finding("ZGS002", "precedes", record["id"], registration=f"{k_day or '?'}.{k_month}",
                          birth=f"{b_day or '?'}.{b_month}")


def zgs003(view: FileView) -> Iterator[Finding]:
    """A book of 1918 on that names no church and is not civil (`civil_register._unflagged`)."""
    for doc in view.documents():
        written = doc.get("written", {})
        year = as_int(written.get("year"))
        if (doc.get("kind") in _BOOKS and not _civil(doc) and year is not None
                and year >= civil_register.CIVIL_LIKELY_FROM and written.get("church") == ""):
            yield finding("ZGS003", "unflagged", doc["id"], year=year)


def _estate_words(value: object) -> tuple[str | None, str | None]:
    """(the words a status stands for, the token the finding gives): a constant's name, a literal's text."""
    if isinstance(value, Mapping):
        name, text = _catalog_name(cast(Node, value))
        return (text, name) if name is not None else (None, None)
    return (value, value) if isinstance(value, str) else (None, None)


def zgs004(view: FileView) -> Iterator[Finding]:
    """A civil book styling someone by an estate of the old order: a default of the book, a person's status."""
    for doc in view.documents():
        if doc.get("kind") not in _BOOKS or not _civil(doc):
            continue
        defaults = doc.get("written", {}).get("defaults") or {}
        for key, value in defaults.items():
            if not key.startswith("status_") or (key == "status_groom" and value == defaults.get("status_male")):
                continue
            words, token = _estate_words(value)
            if words and civil_register.OLD_ESTATE.search(words):
                yield finding("ZGS004", "estate", doc["id"], token=token, status=words)
    for doc, record in view.records(_BOOKS):
        if not _civil(doc):
            continue
        for persona in personas(record):
            words, token = _estate_words(view.written("person", persona).get("status"))
            if words and civil_register.OLD_ESTATE.search(words):
                yield finding("ZGS004", "estate", record["id"], token=token, status=words)


def zgs005(view: FileView) -> Iterator[Finding]:
    """A name written with the letters the 1918 reform removed in a civil book: one finding a person."""
    for doc, record in view.records(_BOOKS):
        if not _civil(doc):
            continue
        for persona in personas(record):
            written = view.written("person", persona)
            for kwarg in civil_register.NAME_KWARGS:
                name = as_text(written.get(kwarg))
                if name and civil_register.OLD_LETTERS.search(name):
                    yield finding("ZGS005", "old_letters", record["id"], token=name, name=name)
                    break


def zgs006(view: FileView) -> Iterator[Finding]:
    """A civil birth's comment saying a parent's age whose field is empty (`civil_register._parent_ages_in_comment`)."""
    for doc, record in view.records({"births"}):
        if not _civil(doc) or record["kind"] != "birth":
            continue
        written = view.written("birth", record)
        comment = as_text(written.get("comment"))
        empty = tuple(role for role in ROLES if written.get(FIELDS[role]) is None)
        reading = read_comment(comment, empty) if comment else None
        for role in (reading.ages if reading else ()):
            yield finding("ZGS006", role, record["id"], token="comment")


RULES: dict[str, Rule] = {
    "PSA001": psa001, "PSA002": psa002, "PSA003": psa003, "PSA004": psa004, "RTV001": rtv001, "RTV002": rtv002,
    "PAF001": paf001, "CAI002": cai002, "ZGS001": zgs001, "ZGS002": zgs002, "ZGS003": zgs003, "ZGS004": zgs004,
    "ZGS005": zgs005, "ZGS006": zgs006,
}
