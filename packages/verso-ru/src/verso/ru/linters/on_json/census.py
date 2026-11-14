"""The rules on a household roll's own members (class `written`): the hidden flag, the parent link, the
parent_member axis, the ages a member states.

A household is a record of a census document, a member a persona of the role `member`; what the
member's `member()` call wrote is `link.written` (`FileView.written("member", link)`), what its
`person()` call wrote the persona's. Each rule answers as its check answers the source, with the
check's own tables and message builders; what the checks read off the SYNTAX alone has no JSON
counterpart:

* a household's members are the personas the JSON holds. The checks read the `member()` calls that
  are direct arguments of a `household()` call, and none that a name, a list or a helper produces;
  the walk sees them all. A member whose number is no integer takes no part in a household's checks
  (it is in no number map), as in the source; the checks that read a call alone (HID, PM001, CAI) read it.
* a value is read as the call evaluated it. A census year or an age held in a name reads as its value;
  `CAI001`'s `without_year` is the form of a year the check cannot read, and the JSON, which holds the
  year the book evaluated, answers `with_year` instead — except for a year of nought, which both read as none.
* a keyword and a positional argument are one in `written`. The checks that read a keyword alone
  (`birth_year`, `departure_reason`, `secondary_role`, a string `record_number`) read a positional one too
  here; none is written so in the corpus. PM001 and PM002 read `ref_member` and `parent_member` in their
  places too (`parent_member.REF_MEMBER_AT`), so `member(2, p, CensusRole.SON, 1, parent_member=1)` — the
  reference positional, the usual form — is the same finding to both readers.
* `CPL010` reads every member, the others the last member of a number (`CensusRecords`' number map).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

from verso.core.i18n import Message
from verso.ru.linters.checks import census_age
from verso.ru.linters.checks.census_parent_link import (
    CHILD_REF_ROLES, HEAD_LINKED_ROLES, HEAD_SIBLING_ROLES, MARRIED_IN_ROLES, SUSPECT_ROLES, format_numbers,
    member_named)
from verso.ru.linters.checks.parent_member import REF_IS_PARENT_ROLES, SPOUSE_ROLES
from verso.ru.linters.on_json.walk import (
    ADOPTED, FileView, Finding, Rule, as_int, as_text, finding)
from verso.ru.messages import t

__all__ = ["RULES", "Household", "Member", "age_years", "by_number"]

type Node = Mapping[str, Any]

_ABSENT = "Отсутствует в РС"  # i18n: content — the comment words the DSL writes for a member the roll omits
_DIED = "умер"  # i18n: content — the departure reason the DSL writes for a member who died
_REFERENCES = ("ref_member", "parent_member", "secondary_ref_member")     # the three references of CPL005/009


class Member:
    """A roll member as its `member()` call wrote it, and its person."""

    def __init__(self, view: FileView, persona: Node) -> None:
        self.link = view.written("member", persona["link"])
        self.person = view.written("person", persona)
        self.number = as_int(self.link.get("number"))
        self.name = as_text(self.person.get("name_orig")) or ""

    @property
    def role(self) -> str | None:
        """The `CensusRole` member's name, as the checks read the attribute."""
        return (as_text(self.link.get("role")) or "").upper() or None

    @property
    def secondary_role(self) -> str | None:
        return (as_text(self.link.get("secondary_role")) or "").upper() or None

    @property
    def hidden(self) -> bool:
        return self.link.get("hidden") is True

    @property
    def comment(self) -> str:
        return as_text(self.link.get("comment")) or ""

    @property
    def who(self) -> Message:
        return member_named(self.number, self.name)

    def ref(self, kwarg: str) -> int | None:
        return as_int(self.link.get(kwarg))


class Household:
    """A household's members: all of them in file order, and the number map the checks walk."""

    def __init__(self, view: FileView, record: Node) -> None:
        self.every = [Member(view, p) for p in record["persons"] if p.get("role") == "member"]
        self.members: dict[int, Member] = {}
        self.repeats: list[tuple[Member, Member]] = []            # (the repeat, the member it replaces)
        for m in self.every:
            if m.number is None:
                continue
            if (earlier := self.members.get(m.number)) is not None:
                self.repeats.append((m, earlier))
            self.members[m.number] = m                              # the last member of a number wins
        self.head = next((n for n, m in self.members.items() if m.role == "HEAD"), None)

    def parent_of(self, m: Member) -> int | None:
        """`census_parent_link._parent_of`: the member the translator takes as `m`'s parent."""
        if (pm := m.ref("parent_member")) is not None:
            return pm
        if m.role in CHILD_REF_ROLES:
            rm = m.ref("ref_member")
            return rm if rm is not None else self.head
        return None

    def ancestors_of(self, num: int | None) -> set[int]:
        found: set[int] = set()
        visited: set[int] = set()
        cur = num
        while cur is not None and cur in self.members and cur not in visited:
            visited.add(cur)
            parent = self.parent_of(self.members[cur])
            if parent is None:
                break
            found.add(parent)
            cur = parent
        return found

    def siblings_of(self, num: int | None) -> set[int]:
        if num is None or num not in self.members:
            return set()
        sibs: set[int] = set()
        if (own := self.parent_of(self.members[num])) is not None:
            sibs |= {n for n, x in self.members.items() if n != num and self.parent_of(x) == own}
        head_sibs = {n for n, x in self.members.items() if x.role in HEAD_SIBLING_ROLES}
        if self.head is not None:
            if num == self.head:
                sibs |= head_sibs
            elif num in head_sibs:
                sibs |= (head_sibs - {num}) | {self.head}
        return sibs


type Check = Callable[[Household, Member, str], Iterator[Finding]]
type CallCheck = Callable[[Member, int | None, str], Iterator[Finding]]


def by_number(check: Check) -> Rule:
    """A rule over the members of a household's number map, as `census_parent_link._collect` walks it."""
    def rule(view: FileView) -> Iterator[Finding]:
        for _, record in view.records({"census"}):
            household = Household(view, record)
            for m in household.members.values():
                yield from check(household, m, record["id"])
    return rule


def by_call(check: CallCheck) -> Rule:
    """A rule over every `member()` call of the file: the census year of its document and the call's own."""
    def rule(view: FileView) -> Iterator[Finding]:
        for doc, record in view.records({"census"}):
            year = as_int(doc["written"].get("year"))
            for m in Household(view, record).every:
                yield from check(m, year, record["id"])
    return rule


# --- CPL002: a grandchild, a nephew or a niece with no father in the household -------------------------

def _cpl002(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl002`."""
    if m.role not in SUSPECT_ROLES or m.hidden or "parent_member" in m.link:
        return
    if (ref := m.ref("ref_member")) is not None:
        target = household.members.get(ref)
        if target is None or target.hidden or target.role != "HEAD":
            return
    if ADOPTED in m.comment.casefold():
        return
    patr = m.person["patr_orig"] if "patr_orig" in m.person else m.person.get("patr_old")
    hint = t("CPL002.hint", patronymic=patr) if patr else ""
    yield finding("CPL002", "no_father", rid, who=m.who, role=m.role, hint=hint)


# --- HID001, HID002: the legacy hidden sentinels -----------------------------------------------------

def _hid001(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """`hidden_flag`: a record number written as a string."""
    if isinstance(m.link.get("record_number"), str):
        yield finding("HID001", "string_number", rid)


def _hid002(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """`hidden_flag`: the comment says the roll omits the member and `hidden=True` is not written."""
    if m.comment.strip().startswith(_ABSENT) and not m.hidden:
        yield finding("HID002", "absent_not_hidden", rid)


# --- PM001, PM002: parent_member ---------------------------------------------------------------------

def _pm001(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """`parent_member`: a child's parent_member that is its ref_member."""
    pm = m.ref("parent_member")
    if m.role in REF_IS_PARENT_ROLES and pm is not None and pm == m.ref("ref_member"):
        yield finding("PM001", "redundant", rid, member=pm)


def _resolved_parent(m: Member) -> int | None:
    """`parent_member._resolved_parent`: the explicit parent_member, else the ref_member of a child."""
    if (pm := m.ref("parent_member")) is not None:
        return pm
    return m.ref("ref_member") if m.role in REF_IS_PARENT_ROLES else None


def _pm002(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`parent_member`: a married-in spouse given the parent of the partner she refers to."""
    if m.role not in SPOUSE_ROLES:
        return
    pm, rm = m.ref("parent_member"), m.ref("ref_member")
    partner = household.members.get(rm) if rm is not None else None
    if pm is not None and partner is not None and _resolved_parent(partner) == pm:
        yield finding("PM002", "partners_parent", rid, member=pm, role=m.role, partner=rm)


# --- CAI001, CAI003, CAI004, CAI005: the ages a member states ----------------------------------------

def age_years(value: object) -> int | None:
    """`census_age._age_years`: the whole years of an age, or None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return census_age.age_years_str(value) if isinstance(value, str) else None


def _cai001(m: Member, year: int | None, rid: str) -> Iterator[Finding]:
    """A birth day or month with no birth year on a member of two or more (`census_age._check_member_cai001`)."""
    years = age_years(m.link.get("age"))
    if years is None:
        return
    link = m.link
    if not (any(k in link for k in census_age.BIRTH_DATE_KWARGS) and "birth_year" not in link
            and years >= census_age.MIN_ADULT_YEARS):
        return
    age = repr(link["age"]) if isinstance(link["age"], str) else f"{years}"
    if year:
        yield finding("CAI001", "with_year", rid, who=m.who, age=age, years=years, year=year, born=year - years)
    else:
        yield finding("CAI001", "without_year", rid, who=m.who, age=age, years=years)


def _cai003(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """`age=0` as the sentinel of an age not stated (`census_age._check_member_cai003`)."""
    age = m.link.get("age")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age == 0:
        yield finding("CAI003", "zero", rid, who=m.who)


def _departed(m: Member) -> str | None:
    """`census_age._departed_from_parish`: "died" or "married out" by the departure reason."""
    reason = as_text(m.link.get("departure_reason"))
    if reason is None:
        return None
    if census_age.DEATH_REASON_RE.search(reason):
        return "died"
    return "married out" if census_age.MARRIED_OUT_RE.search(reason) else None


def _cai004(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """A member who died or married out and still carries a current age (`census_age._check_member_cai004`)."""
    if (why := _departed(m)) is not None and m.link.get("age") is not None:
        yield finding("CAI004", "departed", rid, who=m.who, why=census_age.why_departed(why))


def _cai005(m: Member, _year: int | None, rid: str) -> Iterator[Finding]:
    """A birth year, with no day or month, on a member who died or married out (`census_age._check_member_cai005`)."""
    why = _departed(m)
    if why is None or any(k in m.link for k in census_age.BIRTH_DATE_KWARGS) or m.link.get("birth_year") is None:
        return
    yield finding("CAI005", "departed", rid, who=m.who, why=census_age.why_departed(why))


# --- CPL003: a daughter-in-law with no husband --------------------------------------------------------

def _cpl003(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl003`: a daughter-in-law of the head, when the generator pairs her with nobody."""
    head = household.head
    if m.role != "DAUGHTER_IN_LAW" or m.hidden or head is None:
        return
    rm = m.ref("ref_member")
    if (rm if rm is not None else head) != head:
        return                                      # refers to her husband: the generator pairs them
    others = household.members.values()
    dead_sons = sum(1 for x in others if x.role == "SON" and x.link.get("departure_reason") == _DIED
                    and x.ref("ref_member") in (None, head))
    if dead_sons == 1:
        return
    me = m.number
    if me is not None and any(x.hidden and x.ref("ref_member") == me for x in others):
        return
    if m.secondary_role == "WIFE" and (sec := m.ref("secondary_ref_member")) is not None and sec in household.members:
        return
    if me is not None and any(x.secondary_role == "HUSBAND" and x.ref("secondary_ref_member") == me for x in others):
        return
    yield finding("CPL003", "no_husband", rid, who=m.who, dead_sons=dead_sons, my_num=me)


# --- CPL004: a married-in wife with her husband's lineage as her parent ------------------------------

def _cpl004(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl004`: a wife whose parent_member is her husband, his ancestor or sibling."""
    if m.role not in MARRIED_IN_ROLES or m.hidden:
        return
    pm = m.ref("parent_member")
    if pm is None or pm not in household.members:
        return
    husband = m.ref("ref_member") if m.ref("ref_member") is not None else household.head
    if husband is None:
        return
    if pm == husband:
        rel = t("CPL004.own_husband")
    elif pm in household.ancestors_of(husband):
        rel = t("CPL004.husband_ancestor", husband=husband)
    elif pm in household.siblings_of(husband):
        rel = t("CPL004.husband_sibling", husband=husband)
    else:
        return                                      # her own kin: the legitimate shape
    yield finding("CPL004", "invented_parent", rid, who=m.who, role=m.role, pm=pm, rel=rel)


# --- CPL005, CPL006: hidden members --------------------------------------------------------------------

def _cpl005(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl005`: a hidden member nobody refers to and who refers to nobody."""
    me = m.number
    if not m.hidden or me is None:
        return
    for num, other in household.members.items():
        if num != me and any(other.ref(kw) == me for kw in _REFERENCES):
            return
    if any(m.ref(kw) in household.members for kw in _REFERENCES):
        return
    if m.role in HEAD_LINKED_ROLES and household.head is not None:
        return
    yield finding("CPL005", "hidden_leaf", rid, who=m.who)


def _cpl006(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl006`: a recorded member whose ref_member is a hidden one."""
    ref = m.ref("ref_member")
    if not m.hidden and ref is not None and (target := household.members.get(ref)) is not None and target.hidden:
        yield finding("CPL006", "ref_hidden", rid, who=m.who, ref=ref)


# --- CPL007, CPL008: what a reference means -----------------------------------------------------------

def _cpl007(_household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl007`: a `role=None` member whose ref_member is named on no typed axis."""
    ref = m.ref("ref_member")
    if "role" not in m.link or m.link["role"] is not None or ref is None:
        return
    if ref in (m.ref("spouse_member"), m.ref("parent_member")):
        return
    if m.ref("secondary_ref_member") == ref and m.secondary_role is not None:
        return
    yield finding("CPL007", "role_none", rid, who=m.who, ref=ref)


def _cpl008(_household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl008`: a secondary reference naming the member ref_member names."""
    ref, sec = m.ref("ref_member"), m.ref("secondary_ref_member")
    if ref is not None and ref == sec:
        axis = "spouse_member" if m.secondary_role in ("HUSBAND", "WIFE") else "parent_member"
        yield finding("CPL008", "same_ref", rid, who=m.who, sec=sec, ref=ref, axis=axis)


# --- CPL009, CPL010: the numbers of a household -------------------------------------------------------

def _cpl009(household: Household, m: Member, rid: str) -> Iterator[Finding]:
    """`census_parent_link._check_cpl009`: a reference to a number the household lacks."""
    present = format_numbers(sorted(household.members))
    for kw in _REFERENCES:
        ref = m.ref(kw)
        if ref is not None and ref not in household.members:
            yield finding("CPL009", "no_such_member", rid, who=m.who, kw=kw, ref=ref, numbers=present)


def cpl010(view: FileView) -> Iterator[Finding]:
    """A member number already used by an earlier member of the household (`census_parent_link._check_cpl010`):
    every repeat, against the member it replaces in the number map."""
    for _, record in view.records({"census"}):
        for repeat, earlier in Household(view, record).repeats:
            yield finding("CPL010", "number_taken", record["id"], who=repeat.who, earlier=earlier.who)


RULES: dict[str, Rule] = {
    "CPL002": by_number(_cpl002), "CPL003": by_number(_cpl003), "CPL004": by_number(_cpl004),
    "CPL005": by_number(_cpl005), "CPL006": by_number(_cpl006), "CPL007": by_number(_cpl007),
    "CPL008": by_number(_cpl008), "CPL009": by_number(_cpl009), "CPL010": cpl010,
    "PM002": by_number(_pm002),
    "HID001": by_call(_hid001), "HID002": by_call(_hid002), "PM001": by_call(_pm001),
    "CAI001": by_call(_cai001), "CAI003": by_call(_cai003), "CAI004": by_call(_cai004),
    "CAI005": by_call(_cai005),
}
