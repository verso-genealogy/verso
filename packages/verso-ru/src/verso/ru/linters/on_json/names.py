"""The rules that read the names table (class `context`, needs `names`): a name or a patronymic the table does not
hold (NAM001, NAM002), the sex they and the status give (NAM003, NAM004, GND001, NGA001, NGA002), the kinship
two names claim (RLA002, RLA003) and the roll's links read through them (CPL001, CPL011, CPL012).

The dictionary is the workspace (`lint_records(workspace=)`, owner decision Д2): a name is unknown to the table
of the workspace the file is linted in, which is not always the one that wrote it. A `Person` refuses a name its own
workspace lacks, so such a finding is seen on a file exported elsewhere. A workspace with no table at all answers as
far as it can (H7): every lookup of a name goes through `walk.without_names`, which reads a name no table can answer
as unknown (a name is taken as valid, a sex as not known, a patronymic as agreeing), so the finding that rests on it
is not made, and `lint_records` gives the findings that remain the level of a warning.

What the checks read off the SYNTAX alone has no JSON counterpart, and the walk reads what the calls wrote:

* a value is read as the call evaluated it. A name, patronymic or status held in a name (`NAME = "Лука"`) is skipped
  by the checks, which read string literals, and read by the walk; so is a `person()` bound outside any record.
* a keyword and a positional argument are one in `written`. NAM004 reads the `status` keyword alone, the CPL checks
  read a first name by position alone (`name_orig=` is no first name to them), and GND001 reads the `groom=`,
  `father=` … keywords of a record and the first argument of a `relative()`; the walk reads them all by parameter.
  A positional none (a call that reaches a later parameter writes the ones before it as none) is no value:
  `patr_orig=None` beside a `patr_old` is read as the `patr_old` alone, where CPL012 reads the keyword.
* NAM001 and NAM002 are the names the table of the linting workspace lacks. The `Person` constructor validates the
  same name and patronymic, so a file that loads in a workspace has none; they show on a file read in another one
  (`tests/test_linters_on_json_samples.py` judges them in a thin dictionary).
* NAM004 names the status as the source did: a catalog constant by its name (`walk.status_name`, the one that sorts
  last of those that spell one text, and the sex its NAME gives, `gender_from_status_name`), a literal by `repr`.
  The constants that spell one text and sex all answer alike (`test_status_collisions_agree`). A constant the file
  defines itself is no name the JSON holds: it is read as a literal of its text, with the sex it carries.
* the CPL checks read the `member()` calls that are direct arguments of a `household()`; the walk reads the members
  the JSON holds (see `census`).
* a keyword `name_modern_orth=""` is read as absent (`common.name_modern`: a positional `""` placeholder is no
  keyword), where RLA002 and RLA001 read the keyword (presence-based) and take no name from it.
* where the check crashes (CPL012 on a patronymic its table cannot canonicalize: `dsllint` reports the linter failed)
  the walk reads the patronymic as agreeing.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from verso.core.i18n import Message
from verso.ru.domain import Status
from verso.ru.gender import Gender
from verso.ru.linters.checks.census_parent_link import (
    CHILD_REF_ROLES, DERIVES_PATR_FROM_REF, FEMALE_ROLES, FEMALE_TARGET_ROLES, FOSTER_ROLES, HEAD_BLOOD_ROLES,
    MALE_ROLES, MALE_SUSPECT_ROLES, SIBLING_ROLES, SUSPECT_ROLES, format_numbers, member_named,
    patronymic_candidates)
from verso.ru.linters.checks.genders import RELATIONSHIP_GENDER
from verso.ru.linters.checks.name_gender_agreement import (
    FEMININE_PATRONYMIC, FEMININE_SURNAME, MASCULINE_PATRONYMIC, MASCULINE_SURNAME, disagrees)
from verso.ru.linters.checks.names import gender_from_status_name
from verso.ru.linters.checks.relative_attachment import patronymic_stem
from verso.ru.linters.on_json.census import Household, Member, by_number
from verso.ru.linters.on_json.common import gender_of, name_modern, subject_of
from verso.ru.linters.on_json.walk import (
    ADOPTED, FileView, Finding, Rule, as_text, finding, gender_from_name, only, personas, status_name_or_none, without_names)
from verso.ru.messages import t
from verso.ru.naming import (
    canonicalize_patronymic, derive_patronymic, feminize_surname, get_gender_from_old_patronymic,
    modernize_orthography, validate_first_name, validate_old_patronymic)
from verso.ru.naming.fathers import can_name

__all__ = ["RULES"]

type Node = Mapping[str, Any]

_REF_RECORDS = frozenset({"birth", "marriage", "death"})

# The lookups that rest on a table, with the answer of a workspace that has none.
_valid_first_name = without_names(validate_first_name, True)
_valid_patronymic = without_names(validate_old_patronymic, True)
_gender_from_patronymic = without_names(get_gender_from_old_patronymic, None)
_derived_patronymic = without_names(derive_patronymic, "")
_canonical_patronymic = without_names(canonicalize_patronymic, "")
_can_name = without_names(can_name, True)


def _may_name(patronymic: str, father: str, sex: Gender | None) -> bool:
    """`fathers.can_name`: whether the patronymic can name a man of that given name's. A patronymic the linting
    table cannot canonicalize (one it lacks) is no contradiction: the check would crash on it (dsllint says so as a
    linter failure), the walk reads it as agreeing, as it reads a workspace with no table."""
    try:
        return _can_name(patronymic, father, sex)
    except ValueError:
        return True


def _gender(code: object) -> Gender | None:
    """The `Gender` a written `male` / `female` is."""
    return Gender.__members__.get(code.upper()) if isinstance(code, str) else None


# --- NAM001-NAM004: a person's name, patronymic and status ---------------------------------------------------

def _status_reading(status: object) -> tuple[Gender | None, str]:
    """`names.NameChecker._get_status_gender` and the `status` the finding shows: a catalog constant is read by the
    sex of its NAME, a literal by the sex the catalog gives its words (`Status.gender_of`)."""
    if isinstance(status, str):
        return Status.gender_of(status), repr(status)
    if isinstance(status, Mapping) and (text := as_text(status.get("text"))) is not None:
        code = as_text(status.get("gender"))
        if (name := status_name_or_none(text, code)) is not None:
            return gender_from_status_name(name), name
        return _gender(code), repr(text)       # a constant the file defines itself: no name in the JSON
    return None, ""


def _names(view: FileView) -> Iterator[Finding]:
    """`names.NameChecker._check_person` for each person of each record: the first name and the patronymic against
    the table, the sex each gives against the other and against the status."""
    for _, record in view.records():
        for persona in personas(record):
            written = view.written("person", persona)
            rid = record["id"]
            name_orig, patr_orig = as_text(written.get("name_orig")), as_text(written.get("patr_orig"))
            name_modern_orth, patr_old = as_text(written.get("name_modern_orth")), as_text(written.get("patr_old"))
            if name_modern_orth is not None:
                name_to_check = shown = name_modern_orth
            elif name_orig is not None:
                name_to_check, shown = modernize_orthography(name_orig), name_orig
            else:
                name_to_check = shown = None
            if not _valid_first_name(name_to_check):
                yield finding("NAM001", "unknown", rid, token=str(name_to_check), name=str(name_to_check),
                              written=str(shown))
            patr_to_check = modernize_orthography(patr_orig) if patr_orig is not None else None
            if patr_old is None and not _valid_patronymic(patr_to_check, accept_full=True):
                yield finding("NAM002", "unknown", rid, token=str(patr_to_check), patronymic=str(patr_to_check),
                              written=str(patr_orig))
            name_gender = gender_from_name(name_to_check) if name_to_check else None
            patr_gender = _gender_from_patronymic(modernize_orthography(patr_orig)) if patr_orig else None
            if name_gender and patr_gender and name_gender != patr_gender:
                yield finding("NAM003", "mismatch", rid, token=str(name_to_check), name=str(name_to_check),
                              name_gender=name_gender.value, patronymic=str(patr_to_check),
                              patronymic_gender=patr_gender.value)
            person_gender = name_gender or patr_gender
            status_gender, status_arg = _status_reading(written.get("status"))
            if person_gender and status_gender and person_gender != status_gender:
                yield finding("NAM004", "mismatch", rid, token=str(name_to_check or patr_to_check),
                              name=str(name_to_check or patr_to_check), name_gender=person_gender.value,
                              status=status_arg, status_gender=status_gender.value)


def nam001(view: FileView) -> Iterator[Finding]:
    return only("NAM001", _names(view))


def nam002(view: FileView) -> Iterator[Finding]:
    return only("NAM002", _names(view))


def nam003(view: FileView) -> Iterator[Finding]:
    return only("NAM003", _names(view))


def nam004(view: FileView) -> Iterator[Finding]:
    return only("NAM004", _names(view))


# --- GND001: a person in a slot of the other sex ---------------------------------------------------------------

def _slot_gender(written: Node) -> Gender | None:
    """`genders._person_gender`: the sex written, else the sex of the name (the modern spelling first, then the old
    one); none for a doubtful name."""
    if (explicit := _gender(written.get("gender"))) is not None:
        return explicit
    name = as_text(written.get("name_modern_orth")) or as_text(written.get("name_orig"))
    if not name or "?" in name:
        return None
    return gender_from_name(modernize_orthography(name))


def _in_slot(view: FileView, rid: str, persona: Node, expected: Gender, role: str) -> Iterator[Finding]:
    """`genders.GenderChecker._check_role`."""
    actual = _slot_gender(view.written("person", persona))
    if actual is not None and actual != expected:
        yield finding("GND001", "mismatch", rid, expected=expected.name, role=role, actual=actual.name)


def gnd001(view: FileView) -> Iterator[Finding]:
    """A person whose sex (written, else from the name) contradicts the slot of a marriage, a birth or a death
    (`genders.GenderChecker.visit_Call`): groom and bride, child and deceased by the record's sex, father and
    mother, and a relative by the sex its relationship implies."""
    for _, record in view.records():
        kind, rid = record["kind"], record["id"]
        if kind == "marriage":
            for role, expected in (("groom", Gender.MALE), ("bride", Gender.FEMALE)):
                for persona in personas(record, role):
                    yield from _in_slot(view, rid, persona, expected, role)
            continue
        if kind not in ("birth", "death"):
            continue
        record_gender = _gender(view.written(kind, record).get("gender"))
        if record_gender is not None:
            for persona in personas(record, "child" if kind == "birth" else "deceased"):
                yield from _in_slot(view, rid, persona, record_gender, persona["role"])
        if kind == "birth":
            for role, expected in (("father", Gender.MALE), ("mother", Gender.FEMALE)):
                for persona in personas(record, role):
                    yield from _in_slot(view, rid, persona, expected, role)
        for persona in personas(record, "relative"):
            relationship = as_text(view.written("relative", persona["link"]).get("relationship"))
            if relationship and (expected := RELATIONSHIP_GENDER.get(relationship.upper())) is not None:
                yield from _in_slot(view, rid, persona, expected, "relative")


# --- NGA001, NGA002: a surname or patronymic in the other sex's form -----------------------------------------------

def _text_of(written: Node, *names: str) -> str | None:
    """`name_gender_agreement._text`: the first of `names` written as a non-empty string."""
    for name in names:
        if value := as_text(written.get(name)):
            return value
    return None


def _agreement_gender(written: Node) -> Gender | None:
    """`name_gender_agreement._gender`: the sex written, else the first name's (the old spelling first); none for a
    doubtful name."""
    if (explicit := _gender(written.get("gender"))) is not None:
        return explicit
    name = _text_of(written, "name_orig", "name_modern_orth")
    if not name or "?" in name:
        return None
    return gender_from_name(modernize_orthography(name))


def _agreement(view: FileView) -> Iterator[Finding]:
    """`name_gender_agreement.NameGenderAgreementChecker._check` for each person."""
    for _, record in view.records():
        for persona in personas(record):
            written = view.written("person", persona)
            gender = _agreement_gender(written)
            if gender is None:
                continue
            who = "man" if gender is Gender.MALE else "woman"
            name = _text_of(written, "name_orig", "name_modern_orth")
            patronymic = _text_of(written, "patr_orig", "patr_old")
            surname = _text_of(written, "last_name_orig", "last_name_modern_orth")
            full = " ".join(x for x in (name, patronymic, surname) if x)
            if surname and disagrees(gender, surname, FEMININE_SURNAME, MASCULINE_SURNAME):
                yield finding("NGA001", f"surname_{who}", record["id"], token=surname, full=full, surname=surname)
            if patronymic and disagrees(gender, patronymic, FEMININE_PATRONYMIC, MASCULINE_PATRONYMIC):
                yield finding("NGA002", f"patronymic_{who}", record["id"], token=patronymic, full=full,
                              patronymic=patronymic)


def nga001(view: FileView) -> Iterator[Finding]:
    return only("NGA001", _agreement(view))


def nga002(view: FileView) -> Iterator[Finding]:
    return only("NGA002", _agreement(view))


# --- RLA002, RLA003: a child whose name cannot come from the father relative's --------------------------------------

def _surname_modern(written: Node) -> str | None:
    """`relative_attachment._current_surname_modern`: the modern current surname written, else the old one modernized."""
    if modern := as_text(written.get("last_name_modern_orth")):
        return modern
    orig = as_text(written.get("last_name_orig"))
    return modernize_orthography(orig) if orig else None


def _slot_key(kwarg: str) -> tuple[str, int | None]:
    """The persona of a record that a `Subject`'s keyword names: `god_parent2` is the godparent of slot 2."""
    for prefix, role in (("witness", "witness"), ("god_parent", "godparent")):
        if kwarg.startswith(prefix) and kwarg[len(prefix):].isdigit():
            return role, int(kwarg[len(prefix):])
    return kwarg, None


def _patronymic_finding(rid: str, father: Node, subject: Node, subject_gender: str | None) -> Iterator[Finding]:
    """`relative_attachment._patronymic_issue`: the subject's stated patronymic against the one the father's name
    derives. The father's other kinships are never compared."""
    father_name, raw = name_modern(father), as_text(subject.get("patr_orig"))
    if not father_name or not raw or subject_gender not in (Gender.MALE.name, Gender.FEMALE.name):
        return
    try:
        written = _canonical_patronymic(modernize_orthography(raw))
    except ValueError:
        return
    if not written:                 # no names table: the comparison cannot be made (the surname's can)
        return
    derived = _derived_patronymic(father_name, Gender[subject_gender])
    if not derived or derived == "?":
        return
    if written == derived or patronymic_stem(written) == patronymic_stem(derived):
        return
    yield finding("RLA002", "patronymic", rid, raw=raw, written=written, father_name=father_name, derived=derived)


def _surname_finding(rid: str, father: Node, subject: Node, subject_gender: str | None) -> Iterator[Finding]:
    """`relative_attachment._surname_issue`: a father and child whose stated surnames cannot both be right."""
    father_surname, child_surname = _surname_modern(father), _surname_modern(subject)
    if not father_surname or not child_surname:
        return
    expected = feminize_surname(father_surname) if subject_gender == Gender.FEMALE.name else father_surname
    if expected != child_surname:
        yield finding("RLA003", "surname", rid, child_surname=repr(child_surname), father_surname=repr(father_surname),
                      expected=repr(expected))


def _kin(view: FileView) -> Iterator[Finding]:
    """`relative_attachment._collect` for the father relatives: the person each reference attaches a relative to,
    and whether the two can be father and child. A record that declares its kin names inconsistent
    (`source_kin_error`) stands both down."""
    for _, record in view.records():
        verb = record["kind"]
        if verb not in _REF_RECORDS:
            continue
        slots = {(p["role"], p.get("slot")): p for p in personas(record)}
        for relative in personas(record, "relative"):
            link = view.written("relative", relative["link"])
            subject = subject_of(view, verb, slots, as_text(link.get("relationship_ref")))
            if subject is None or (subject_persona := slots.get(_slot_key(subject.kwarg))) is None:
                continue
            subject_gender = gender_of(view, subject_persona, subject.gender_fallback)
            if as_text(view.written(verb, record).get("source_kin_error")):
                continue
            if (as_text(link.get("relationship")) or "").upper() == "FATHER":
                father, child = view.written("person", relative), view.written("person", subject_persona)
                yield from _patronymic_finding(record["id"], father, child, subject_gender)
                yield from _surname_finding(record["id"], father, child, subject_gender)


def rla002(view: FileView) -> Iterator[Finding]:
    return only("RLA002", _kin(view))


def rla003(view: FileView) -> Iterator[Finding]:
    return only("RLA003", _kin(view))


# --- CPL001, CPL011, CPL012: the roll's links, read through the names --------------------------------------------------

_SON_WORDS = ("сын ", "сынъ ", "дочь ")  # i18n: content — the comment words the DSL writes


def _patronymic(m: Member) -> str | None:
    """`census_parent_link._person_patronymic`: the patronymic as written, else the old form."""
    written = as_text(m.person.get("patr_orig"))
    return written if written is not None else as_text(m.person.get("patr_old"))


def _is_female(m: Member) -> bool:
    return m.person.get("gender") == "female"


def _sex(m: Member) -> Gender | None:
    """`census_parent_link._sex`: a member's sex as the role states it, else as the name gives it."""
    if m.role in MALE_ROLES:
        return Gender.MALE
    if m.role in FEMALE_ROLES:
        return Gender.FEMALE
    if _is_female(m):
        return Gender.FEMALE
    return gender_from_name(modernize_orthography(m.name)) if m.name else None


def _father_evidence(m: Member, target: Member, rm: int) -> Message | None:
    """`census_parent_link._father_evidence`: why the ref target looks like the member's father, or none. A
    derivable but contradicting patronymic vetoes everything: the ref is then a relationship anchor."""
    patronymic = _patronymic(m)
    if patronymic:
        if not target.name:
            return None
        gender = Gender.MALE if m.role in MALE_SUSPECT_ROLES else Gender.FEMALE
        try:
            candidates = patronymic_candidates(target.name, gender)
        except Exception:      # as the check: no derivation (and no names table) is no evidence
            return None
        if not candidates:
            return None
        if modernize_orthography(patronymic).casefold() in {c.casefold() for c in candidates}:
            return t("CPL001.evidence_patronymic", patronymic=patronymic, father=target.name)
        return None
    if any(word in m.comment.casefold() for word in _SON_WORDS):
        return t("CPL001.evidence_comment")
    if m.role in DERIVES_PATR_FROM_REF:
        return t("CPL001.evidence_derived", member=rm)
    return None


def _cpl001(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl001`: a grandchild, nephew or niece whose reference is a visible member other than
    the head, who plausibly is the father, and whom the translator does not link to him."""
    if m.role not in SUSPECT_ROLES or "parent_member" in m.link or (rm := m.ref("ref_member")) is None:
        return
    if (target := household.members.get(rm)) is None or target.role == "HEAD" or target.hidden:
        return
    if m.role in SIBLING_ROLES and target.ref("parent_member") is not None:
        return                       # the sibling-inheritance path gives the parent
    if ADOPTED in m.comment.casefold() or ADOPTED in target.comment.casefold():
        return
    if target.role in FEMALE_TARGET_ROLES or _is_female(target):
        return
    if (evidence := _father_evidence(m, target, rm)) is None:
        return
    yield finding("CPL001", "no_parent_link", rid, who=m.who, role=m.role, rm=rm, target_txt=member_named(rm, target.name),
                  evidence=evidence)


def _resolved_parent(c: Member, household: Household) -> int | None:
    """`census_parent_link._resolved_parent`: the member the translator links `c` to as parent."""
    if c.role in FOSTER_ROLES:
        return None
    if (pm := c.ref("parent_member")) is not None:
        return pm
    if (rm := c.ref("ref_member")) is None:
        return None
    if c.role in CHILD_REF_ROLES:
        return rm
    target = household.members.get(rm)
    if target is not None and target.hidden:
        return rm
    if c.role in SIBLING_ROLES and target is not None:
        return target.ref("parent_member")
    return None


def _cpl011(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl011`: a hidden parent whose reference the translator turns into a spouse who
    cannot be one — a partner of the same sex, or the head paired with his own brother."""
    if not m.hidden or m.number is None or m.role in CHILD_REF_ROLES:
        return
    ref = m.ref("ref_member")
    target = household.members.get(ref) if ref is not None else None
    if target is None or target.hidden or m.ref("spouse_member") == ref:
        return
    kids = sorted(n for n, c in household.members.items() if n != m.number and _resolved_parent(c, household) == m.number)
    if not kids:
        return
    m_sex, target_sex = _sex(m), _sex(target)
    if m_sex is not None and m_sex == target_sex:
        why = t("CPL011.one_sex")
    elif ref == household.head and m.role in HEAD_BLOOD_ROLES:
        why = t("CPL011.head_blood", role=(m.role or "").lower())
    else:
        return
    yield finding("CPL011", "hidden_partner", rid, who=m.who, numbers=format_numbers(kids), ref=ref,
                  partner=target.who, why=why)


def _cpl012(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl012`: a written patronymic the linked father's name cannot give."""
    patronymic = _patronymic(m)
    if not patronymic or "?" in patronymic or m.role in FOSTER_ROLES:
        return
    old = as_text(m.person.get("patr_old"))
    kw, ref = "parent_member", m.ref("parent_member")
    if ref is None and m.role in {"SON", "DAUGHTER"}:
        kw, ref = "ref_member", m.ref("ref_member")
    target = household.members.get(ref) if ref is not None else None
    if target is None or _sex(target) is not Gender.MALE:
        return
    father = target.name
    if not father or "?" in father:
        return
    if any(_may_name(modernize_orthography(p), modernize_orthography(father), _sex(m))
           for p in (patronymic, old) if p and "?" not in p):
        return
    yield finding("CPL012", "patronymic", rid, token=patronymic, number=m.number, name=m.name, patronymic=patronymic,
                  father=father, kw=kw, ref=ref)


RULES: dict[str, Rule] = {
    "NAM001": nam001, "NAM002": nam002, "NAM003": nam003, "NAM004": nam004, "GND001": gnd001,
    "NGA001": nga001, "NGA002": nga002, "RLA002": rla002, "RLA003": rla003,
    "CPL001": by_number(_cpl001), "CPL011": by_number(_cpl011), "CPL012": by_number(_cpl012),
}
