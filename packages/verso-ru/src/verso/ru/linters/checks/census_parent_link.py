#!/usr/bin/env python3
"""AST-based linters (CPL001-CPL012) that WARN on census members whose
parent/spouse link is silently lost — or silently invented — in the generated
tree.

The translator's `_resolve_parent_ref` (census_resolvers.py) treats
`ref_member` as the parent ONLY for SON/DAUGHTER/STEPSON/STEPDAUGHTER. A
GRANDSON/GRANDDAUGHTER/NEPHEW/NIECE with `ref_member` pointing at a non-head,
non-hidden member gets NO parent link — yet `census.py` still derives the
grandchild's patronymic/surname from that ref, so the generated tree looks
plausible while the union is missing. This is exactly how one extracted roll
lost seven father links: members recorded in the source as «сынъ»/«дочь» of a
non-head member were encoded head-relatively as GRANDSON/NEPHEW.

CPL001 flags a member when ALL hold:
  - role is GRANDSON/GRANDDAUGHTER/NEPHEW/NIECE;
  - no `parent_member=` (the explicit upward link, translator precedence 1);
  - `ref_member` resolves to an in-household member that is not the HEAD and
    not `hidden=True` (a hidden ref IS treated as the parent — legacy path);
  - the sibling-inheritance path can't rescue it (NEPHEW/NIECE whose ref
    target itself carries `parent_member` inherits that parent);
  - the ref target plausibly IS the father: the member has no explicit
    patronymic (census.py derives it from the ref → ref is treated as the
    father; GRANDSON/GRANDDAUGHTER only — NEPHEW/NIECE get no derivation), or
    the explicit patronymic matches one derived from the ref target's first
    name, or the member's comment says «сын »/«дочь ».

An explicit patronymic that CONTRADICTS the ref target's name means the ref is
a relationship anchor («племянник Козмы» with the father absent) — that is
legitimate DSL and stays silent. Refs to the HEAD (grandfather/uncle anchor,
father absent) are likewise never flagged: there is no father to link.

Three resolutions for a finding: (a) the source says «сынъ»/«дочь» → the role
should be SON/DAUGHTER (a role carries the source's own word); (b) the role is
source-faithful (e.g. the 1897 посемейные списки write «внук» relative to the
head) and the ref target IS the father → add `parent_member=N`; (c) the match
is a coincidence and the ref is an anchor → keep as-is.

CPL002 is CPL001's complement: a lineage-role member whose ref points at the
HEAD (or nowhere) with no `parent_member` — the father is absent from the
household entirely, so the profile is emitted attached to NO union. When the
father is identifiable (patronymic, sibling group), the fix is a `hidden=True`
intermediary member plus `parent_member=` (the pattern of several families of
one roll); an unidentifiable father is a legitimate keep-as-is.

CPL003 flags a DAUGHTER_IN_LAW («сноха») whose marriage cannot be emitted:
her ref points at the HEAD, the household does not have exactly one deceased
SON (the generator's Rule A pairing), and no hidden member declares her as
spouse via `ref_member=<her number>`. The fix is a hidden husband:
`member(9, person("Иванъ"), None, ref_member=6, parent_member=1, hidden=True)`.

CPL004 is the inverse failure — not a LOST link but an INVENTED one. A woman
recorded as WIFE/DAUGHTER_IN_LAW married INTO the household, so she has no
parent in it; a `parent_member=` on her mints a bogus parent-union and shows up
on Geni as a `duplicate_parents` tree conflict. It fires only when the target is
her husband himself, an ancestor of his, or a sibling of his — i.e. exactly the
cases that would make her a blood relative of the man she married. Pointing at
her OWN father, who legitimately lives in the same household (he is the head and
her husband married in), is silent.

Crucially the check does NOT use patronymic agreement as evidence: in the cases
that prompted it the patronymic matched the wrong man's given name (a wife whose
patronymic fits her husband's brother, another whose patronymic fits her
husband's grandfather), and that coincidence is precisely what produced the
mis-links. Only the household's own kinship graph is consulted.

CPL005 audits hidden members themselves. A `hidden=True` member models someone
the source omits, and earns its place by CONNECTING a real person — being
referenced as a parent/spouse, or referencing an in-household spouse/parent. One
with no link in either direction is a fabricated leaf: it adds an unattested
person for no purpose. That is the shape of a member invented solely to father a
nephew, left dangling once the parent link was corrected. An outbound
`father_ref` alone does NOT rescue a member: it only makes them somebody's
unattested child.

"Connected" covers three shapes, all of them real corpus cases: something
references the member; the member references an in-household relative (via
`ref_member`, `parent_member` OR `secondary_ref_member`); or its ROLE resolves
head-relatively — a hidden DAUGHTER with no `ref_member` is the head's daughter,
a hidden WIFE is the head's wife. Only BROTHER/SISTER create no union, which is
why a fabricated BROTHER is left dangling.

Note the comment «Отсутствует в РС …; персона добавлена вручную по другим
материалам» is worthless as evidence either way — a fabricated member and a
well-attested one carry it verbatim. Only the link structure is consulted; corpus-wide attestation is a
cross-file question this check deliberately does not attempt (the linters must
stay path-independent so an IDE can lint an unsaved buffer via a temp file).

CPL007 flags a `role=None` member whose `ref_member` says nothing about what
the reference MEANS. With no role, `ref_member=N` is read as a spouse by one
pass of the generator and as a parent by another — `generator.py` documents the
convention outright («role had to be cleared so `ref_member` could encode the
spouse»), which makes the field an instruction about the encoding rather than a
claim about a person. The corpus holds thirteen: twelve where N is the
husband/wife and one where N is the father.

The fix is to name N on a typed axis as well — `spouse_member=N` or
`parent_member=N` — leaving `ref_member` exactly as it is, so no `.tf` byte
moves. Neither the generator nor the exporters read `spouse_member`; it exists
because `verso.ru.facts.extract.census` must state SpouseOf or ParentOf and may not
guess which, and because a convention that lives in a prose comment is one an
extractor cannot read.

`secondary_role=<role>` + `secondary_ref_member=N` settles the check too, and
the extractor reads it on the same footing. It is the right answer when the
reconstructed relationship should also reach Geni, and the wrong one when it
should not: that axis is a writing channel, and the translator mints a
`geni_union` from it. On the corpus's twelve it happens to mint one whose
res_name collides with the union the hidden-ancestor path already emits, so no
resource appears — but the tree still moves (two unions change position,
`consolidated_unions.tf` gains duplicate provenance lines) and the collision is
a coincidence of those twelve rather than a property of the field.

CPL008 is the other side of that choice. `secondary_role` + `secondary_ref_member`
are documented as an **additional** relationship, distinct from the primary role
the source records — so pointing the secondary reference at the same member as
`ref_member` is not an addition but a restatement, and it is the expensive way
to restate: the translator mints a `geni_union` from that axis, while the
annotation-only axes (`spouse_member` / `parent_member`) move no generated byte.
The restatement is also redundant by construction, because the `ref_member` path
already relates the same two people — and in some shapes it is nonsense (a SON
whose secondary HUSBAND reference names his own father). The corpus holds 36
members with a secondary reference and none of them equal to `ref_member`, so
the check gates at zero.

Hidden detection honours only the typed `hidden=True` kwarg: the legacy
string-`record_number` / comment sentinels are retired (hidden_flag HF001
errors on them), so this mirrors runtime `is_hidden()` exactly.

CPL009 is the structural floor the other eight stand on: a `ref_member`,
`parent_member` or `secondary_ref_member` naming a member number that does not
exist in the SAME household. All three are resolved against that household's
own `members_by_num` and nowhere else, so a number that misses resolves to
nothing: `_resolve_parent_ref` hands the generator a parent it then fails to
find, and the union is simply never emitted. Nothing raises, nothing logs — the
lost link looks exactly like a member who never claimed a parent, which is why
neither CPL001 nor CPL002 can see it (both read the resolved TARGET, and a
dangling number has none).

The shape that prompted it: a member carried `parent_member=16` while the
household held members 1–7. Member 16 lived in another household of the same
page — a DIFFERENT сказка, another owner's крестьяне — and was a `hidden=True`
reconstruction there. The link had been written when the whole лист was still
one flat `household()` call whose member numbers restarted per family, so 16 did
resolve; splitting the page into several households stranded it, and it sat as a
no-op. Numbering is per household BY CONSTRUCTION, so a split, a renumbering or
a copy-paste from the household next door produces this shape and nothing
downstream complains.

The right field for a parent who genuinely lives elsewhere is `father_ref=`,
which takes a CONSOLIDATED profile name and crosses households on purpose
(see PM002 in `parent_member.py`). When no such parent is attested, the link
is simply wrong and goes.

CPL010 is the floor under CPL009: a member number used TWICE in one household.
Every reference resolves through the household's number map, which keeps the
LAST member of each number (`CensusRecords` builds it as `{m.number: m}`, and so
does this module) — so a repeat silently replaces the earlier member: a
reference to the number reaches the later one, and every check that walks the
map, CPL001–CPL009 included, never sees the earlier at all. The facts layer
keys an appearance on the number too, so the two collapse into one persona
holding both names, both ages and both roles. The corpus case: a wife and her
5-year-old daughter of one двор were both № 18. The roll numbers дворы, not
people, so member numbers are the transcriber's own running count — read off the
scan, the daughter is 19 and the next member 20.

CPL011 is the one that catches a union the translator INVENTS between two people
who cannot be a couple. A hidden member who parents somebody gets a union of his
own, and the hidden-ancestor pass (`generator.py`) takes his `ref_member` as the
second PARTNER of it for every role but SON/DAUGHTER/STEPSON/STEPDAUGHTER — the
corpus convention of a hidden FATHER pointing at the MOTHER, or an absent brother
at his widow. Pointed anywhere else, the reference marries the children's father
to whoever it names. A roll did it twice on one page: a hidden BROTHER with
ref_member=1 made the head's brother the co-parent of a child, and another hidden
BROTHER with ref_member=1 married the head's brother and took three children with
him into that brother's first marriage once the roll was folded. The check fires
when the pair is of one sex, or when the role makes the hidden member the head's
sibling or parent and the reference is the head; a declared `spouse_member=N`
stands it down. Measured over 53 rolls: 26 hidden parents are partnered this way,
25 of them real marriages (12 declared, 9 FATHER→MOTHER, 4 a brother and his
widow), and the 26th was the same shape again — a hidden BROTHER with
`ref_member=1` against the head.

CPL012 reads the patronymic the other way round from CPL001 and CPL004: a
written patronymic the linked father's name cannot give — `parent_member`, else
a SON's or DAUGHTER's `ref_member` — is a contradiction inside the record, either
a wrong link or a misread name. Agreement is `father-claims`' own
(`verso.ru.naming.fathers.can_name`), so a spelling the names table folds or a
stem it does not know is silent; a parent who is not a man is skipped, and a
`patr_old` that agrees — the author's reading of a miswritten patronymic —
stands it down.

The check reads its inputs from the record content (NOT the file path), so it
behaves identically when an IDE plugin lints an unsaved buffer via a temp file.

Run:
    python3 -m verso.ru.linters.checks.census_parent_link FILE [FILE...]
"""

import ast
import sys
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import (
    canonicalize_name, derive_old_patronymic, derive_patronymic, get_gender_from_name, modernize_orthography)
from verso.ru.naming.fathers import can_name
from verso.core.i18n import Message
from verso.ru.linters.issue import issue, line_text, says
from verso.ru.messages import t
from verso.ru.linters.checks import shared_ast

_TARGETS = {"member", "CensusMember"}

# Lineage roles the translator does NOT link to a parent via ref_member.
# COUSIN/UNCLE/etc. are deliberately excluded pending corpus evidence — the
# surveyed bug classes are all grandchild/nephew shaped (false-negative-safe).
SUSPECT_ROLES = {"GRANDSON", "GRANDDAUGHTER", "NEPHEW", "NIECE"}
MALE_SUSPECT_ROLES = {"GRANDSON", "NEPHEW"}
# Sibling roles of `_resolve_parent_ref` precedence 4: ref target's own
# `parent_member` is inherited. Of the suspect roles only NEPHEW/NIECE qualify.
SIBLING_ROLES = {"BROTHER", "SISTER", "NIECE", "NEPHEW", "COUSIN"}
# Roles where census.py's `_CHILD_ROLES` auto-derives the patronymic from the
# ref target — a bare (no-patronymic) member of these roles treats the ref as
# the father by construction. NEPHEW/NIECE get no derivation.
DERIVES_PATR_FROM_REF = {"GRANDSON", "GRANDDAUGHTER"}
# Ref-target roles that imply a female target — a female ref can't be the
# patronymic father, so such refs are anchors by definition.
FEMALE_TARGET_ROLES = {
    "WIFE", "DAUGHTER", "MOTHER", "SISTER", "DAUGHTER_IN_LAW",
    "NIECE", "GRANDDAUGHTER", "STEPDAUGHTER",
}
# CPL004. Roles of a woman who married INTO the household — she has no parent
# here unless her own father happens to live in it too.
MARRIED_IN_ROLES = {"WIFE", "DAUGHTER_IN_LAW"}
# Roles for which the translator resolves `ref_member` as the parent, so they
# extend the household's ancestry chain (mirrors `_resolve_parent_ref`).
CHILD_REF_ROLES = {"SON", "DAUGHTER", "STEPSON", "STEPDAUGHTER"}
# Recorded relative to the HEAD, so these are the head's siblings even when no
# common parent is present in the household.
HEAD_SIBLING_ROLES = {"BROTHER", "SISTER"}
# CPL005. Roles the translator resolves into a union relative to the HEAD when
# no explicit ref_member is given — a DAUGHTER with no ref IS the head's
# daughter, a WIFE with no ref IS the head's wife. Such a member is connected
# even with no explicit link of its own. Sibling roles (BROTHER/SISTER) are
# absent on purpose: they create no union, which is what leaves a fabricated
# brother dangling.
HEAD_LINKED_ROLES = (CHILD_REF_ROLES
                      | {"WIFE", "HUSBAND", "FATHER", "MOTHER",
                         "DAUGHTER_IN_LAW", "SON_IN_LAW"})
# CPL011. A foster child has no biological parent union (mirrors
# `census_resolvers._resolve_parent_ref`).
FOSTER_ROLES = {"FOSTER_SON", "FOSTER_DAUGHTER"}
# CPL011. Roles whose word states the member's sex; anyone else's is read off
# the name.
MALE_ROLES = {"HUSBAND", "SON", "BROTHER", "UNCLE", "GRANDSON", "SON_IN_LAW",
               "BROTHER_IN_LAW", "STEPSON", "NEPHEW", "FATHER", "STEPBROTHER",
               "FOSTER_SON"}
FEMALE_ROLES = FEMALE_TARGET_ROLES | {"FOSTER_DAUGHTER"}
# CPL011. A hidden member in one of these roles is, by the role, the head's
# sibling or parent — never a partner of the head.
HEAD_BLOOD_ROLES = {"BROTHER", "SISTER", "FATHER", "MOTHER"}


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
    # A hidden member is often numbered -1, -2…, which parses as
    # `UnaryOp(USub, Constant)`: read only as a Constant, the member and every
    # reference to it were invisible to all eleven checks.
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _int_literal(node.operand)
        return -operand if operand is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _member_arg(node: ast.Call, index: int, kwarg: str) -> ast.expr | None:
    """A member() argument by kwarg name, else positional index.
    member(number, person, role, ref_member, age, previous_age, ...)."""
    mkw = _kwargs(node)
    if kwarg in mkw:
        return mkw[kwarg].value
    if len(node.args) > index:
        return node.args[index]
    return None


def _person_first_name(person_node: ast.expr | None) -> str:
    """The member's given name (person()'s first positional arg /
    first_name= kwarg), or "" when unavailable."""
    if not isinstance(person_node, ast.Call):
        return ""
    fn = _kwargs(person_node).get("first_name")
    if fn is not None:
        return _string_literal(fn.value) or ""
    if person_node.args:
        return _string_literal(person_node.args[0]) or ""
    return ""


def _person_patronymic(person_node: ast.expr | None) -> str | None:
    """The as-written patronymic of a `person()` call: `patr_orig` (kwarg or
    positional index 1), else the explicit `patr_old` (kwarg or index 4)."""
    if not isinstance(person_node, ast.Call):
        return None
    pkw = _kwargs(person_node)
    if "patr_orig" in pkw:
        return _string_literal(pkw["patr_orig"].value)
    if len(person_node.args) >= 2:
        lit = _string_literal(person_node.args[1])
        if lit is not None:
            return lit
    if "patr_old" in pkw:
        return _string_literal(pkw["patr_old"].value)
    if len(person_node.args) >= 5:
        return _string_literal(person_node.args[4])
    return None


def _role_name(node: ast.Call) -> str | None:
    # role is the 3rd positional arg in member()/CensusMember(), or a kwarg.
    role_expr: ast.expr | None = node.args[2] if len(node.args) >= 3 else None
    kw = _kwargs(node)
    if "role" in kw:
        role_expr = kw["role"].value
    if isinstance(role_expr, ast.Attribute):
        return role_expr.attr
    return None


def _member_number(node: ast.Call) -> int | None:
    return _int_literal(_member_arg(node, 0, "number"))


def _member_who(m: ast.Call) -> Message:
    return member_named(_member_number(m), _person_first_name(_member_arg(m, 1, "person")))


def member_named(num: int | None, name: str | None) -> Message:
    number = num if isinstance(num, int) else str(num)
    return t("census.member_named", number=number, name=name) if name else t("census.member", number=number)


def _is_hidden(m: ast.Call) -> bool:
    hidden = _kwargs(m).get("hidden")
    return (hidden is not None and isinstance(hidden.value, ast.Constant)
            and hidden.value.value is True)


def _comment(m: ast.Call) -> str:
    kw = _kwargs(m).get("comment")
    return (_string_literal(kw.value) if kw is not None else None) or ""


def _person_is_female(person_node: ast.expr | None) -> bool:
    """True when the person() call carries gender=Gender.FEMALE."""
    if not isinstance(person_node, ast.Call):
        return False
    g = _kwargs(person_node).get("gender")
    return g is not None and isinstance(g.value, ast.Attribute) \
        and g.value.attr == "FEMALE"


def patronymic_candidates(father_first: str, gender: Gender) -> set[str]:
    """All plausible patronymic spellings for a child of `gender` fathered by
    `father_first` (as-written): the short old form («Андреев») and the full
    modern form («Андреевич»), for both the modernized and the canonicalized
    father name. Modern orthography on every candidate; empty/"?" dropped."""
    father = modernize_orthography(father_first)
    first_names = {father, canonicalize_name(father, Gender.MALE) or father}
    candidates: set[str] = set()
    for fn in first_names:
        candidates.add(modernize_orthography(derive_patronymic(fn, gender)))
        candidates.add(modernize_orthography(derive_old_patronymic(fn, gender)))
    candidates.discard("")
    candidates.discard("?")
    return candidates


def _father_evidence(m: ast.Call, target: ast.Call, rm: int) -> Message | None:
    """Why the ref target looks like the member's father, or None (anchor /
    no evidence). A derivable-but-contradicting explicit patronymic vetoes
    everything — that is the legitimate relationship-anchor shape."""
    role = _role_name(m)
    patr = _person_patronymic(_member_arg(m, 1, "person"))
    father_first = _person_first_name(_member_arg(target, 1, "person"))

    if patr:
        if not father_first:
            return None
        gender = Gender.MALE if role in MALE_SUSPECT_ROLES else Gender.FEMALE
        try:
            candidates = patronymic_candidates(father_first, gender)
        except Exception:
            return None  # advisory check: no derivation → no evidence
        if not candidates:
            return None  # underivable name: neither evidence nor contradiction
        if modernize_orthography(patr).casefold() in {
                c.casefold() for c in candidates}:
            return t("CPL001.evidence_patronymic", patronymic=patr, father=father_first)
        return None  # contradiction: ref is a relationship anchor

    comment = _comment(m).casefold()
    if any(t in comment for t in ("сын ", "сынъ ", "дочь ")):  # i18n: content — the comment words the DSL writes
        return t("CPL001.evidence_comment")
    if role in DERIVES_PATR_FROM_REF:
        return t("CPL001.evidence_derived", member=rm)
    return None  # bare NEPHEW/NIECE: no derivation, no evidence


def _check_member(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    return (_check_cpl001(m, members, lines) + _check_cpl002(m, members, lines)
            + _check_cpl003(m, members, lines) + _check_cpl004(m, members, lines)
            + _check_cpl005(m, members, lines) + _check_cpl006(m, members, lines)
            + _check_cpl007(m, lines) + _check_cpl008(m, lines)
            + _check_cpl009(m, members, lines) + _check_cpl011(m, members, lines)
            + _check_cpl012(m, members, lines))


def _role_is_none(m: ast.Call) -> bool:
    """True when the member has no role: `role=None` written out, or the argument left out
    (`member(n, person(...), ref_member=...)`); the two build the same member."""
    role_expr: ast.expr | None = m.args[2] if len(m.args) >= 3 else None
    kw = _kwargs(m)
    if "role" in kw:
        role_expr = kw["role"].value
    return role_expr is None or (isinstance(role_expr, ast.Constant) and role_expr.value is None)


def _check_cpl008(m: ast.Call,
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A secondary reference naming the same member as `ref_member`.

    The secondary axis exists for a relationship the source's own role does NOT
    describe — «m12 is BROTHER of HEAD per the roll, AND HUSBAND of m2 per
    other materials». Aimed at the member `ref_member` already names it adds
    nothing: the `ref_member` path relates those two people already, so the
    `geni_union` the secondary pass mints for it is a duplicate, and in some
    shapes the claim is not even coherent (a SON whose secondary HUSBAND
    reference names the father his `ref_member` points at).

    Saying it on `spouse_member` / `parent_member` instead states the same
    thing and changes no generated byte, which is the difference the two axes
    are for.
    """
    ref = _int_literal(_member_arg(m, 3, "ref_member"))
    sec = _int_literal(_member_arg(m, 21, "secondary_ref_member"))
    if ref is None or sec is None or ref != sec:
        return []
    role = _secondary_role_name(m)
    axis = "spouse_member" if role in ("HUSBAND", "WIFE") else "parent_member"
    pin = _kwarg_range(m, "secondary_ref_member", lines)
    return [{"line": m.lineno, **pin, **says("CPL008", "same_ref", who=_member_who(m), sec=sec, ref=ref, axis=axis)}]


def _secondary_role_name(m: ast.Call) -> str | None:
    """The `secondary_role=` enum member's name, or None when absent."""
    expr = _member_arg(m, 20, "secondary_role")
    return expr.attr if isinstance(expr, ast.Attribute) else None


def _check_cpl007(m: ast.Call,
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A `role=None` member whose `ref_member` does not say what it encodes.

    A role tells the reader what the reference is measured against — a WIFE's
    ref is her husband, a SON's is his father. Clearing the role to reuse
    `ref_member` for a link the role would have contradicted leaves the
    meaning nowhere but in a prose comment, and the same number is then read
    as a spouse by one generator pass and as a parent by another.

    Naming the number a second time on a typed axis settles it. THREE axes do,
    and the choice between them is about what else you want to happen, not
    about the claim:

      * `spouse_member=N` and `parent_member=N` are read by
        `verso.ru.facts.extract.census` and by nothing in the translator, so
        declaring one cannot move a generated byte;
      * `secondary_role=<role>` + `secondary_ref_member=N` names the relation
        just as precisely — and the extractor reads it too — but it is a
        WRITING channel: `generator.py`'s secondary-relationship pass mints a
        `geni_union` from it. On the corpus's twelve spouse cases that union
        collides with the one the hidden-ancestor path already emits, so no
        resource appears, yet two unions change position and
        `consolidated_unions.tf` gains duplicate provenance lines — the tree
        moves and `stale-check` says so.

    So all three answer the check, and the message names the cheap ones first.
    """
    if not _role_is_none(m):
        return []
    ref = _int_literal(_member_arg(m, 3, "ref_member"))
    if ref is None:
        return []
    for idx, kw in ((24, "spouse_member"), (18, "parent_member")):
        if _int_literal(_member_arg(m, idx, kw)) == ref:
            return []
    # The secondary axis counts only when it carries a ROLE: the number alone
    # says nothing, and it is the role word that states the relation to N.
    if (_int_literal(_member_arg(m, 21, "secondary_ref_member")) == ref
            and _secondary_role_name(m) is not None):
        return []
    pin = _kwarg_range(m, "ref_member", lines)
    return [{"line": m.lineno, **pin, **says("CPL007", "role_none", who=_member_who(m), ref=ref)}]


def _resolved_parent(c: ast.Call, members: dict[int, ast.Call]) -> int | None:
    """The member the translator links `c` to as parent — a mirror of
    `census_resolvers._resolve_parent_ref`, precedence for precedence."""
    role = _role_name(c)
    if role in FOSTER_ROLES:
        return None
    pm = _int_literal(_member_arg(c, 18, "parent_member"))
    if pm is not None:
        return pm
    rm = _int_literal(_member_arg(c, 3, "ref_member"))
    if rm is None:
        return None
    if role in CHILD_REF_ROLES:
        return rm
    target = members.get(rm)
    if target is not None and _is_hidden(target):
        return rm
    if role in SIBLING_ROLES and target is not None:
        return _int_literal(_member_arg(target, 18, "parent_member"))
    return None


def _sex(m: ast.Call) -> Gender | None:
    """A member's sex as the role states it, else as the name gives it."""
    role = _role_name(m)
    if role in MALE_ROLES:
        return Gender.MALE
    if role in FEMALE_ROLES:
        return Gender.FEMALE
    if _person_is_female(_member_arg(m, 1, "person")):
        return Gender.FEMALE
    name = _person_first_name(_member_arg(m, 1, "person"))
    return get_gender_from_name(modernize_orthography(name)) if name else None


def _check_cpl011(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A hidden parent whose `ref_member` the translator turns into a spouse
    who cannot be one.

    The hidden-ancestor pass reads a hidden parent's `ref_member` as the second
    partner of his children's union for every role but the four child roles.
    That is the corpus convention — a hidden FATHER pointing at the MOTHER, an
    absent brother at his widow — and it is wrong wherever the reference names
    somebody else: two men, or the head paired with his own brother. A declared
    `spouse_member=N` says the pairing is meant and stands the check down.
    """
    if not _is_hidden(m):
        return []
    num = _member_number(m)
    role = _role_name(m)
    if num is None or role in CHILD_REF_ROLES:
        return []
    ref = _int_literal(_member_arg(m, 3, "ref_member"))
    target = members.get(ref) if ref is not None else None
    if target is None or _is_hidden(target):
        return []
    if _int_literal(_member_arg(m, 24, "spouse_member")) == ref:
        return []
    kids = sorted(n for n, c in members.items()
                  if n != num and _resolved_parent(c, members) == num)
    if not kids:
        return []
    m_sex, t_sex = _sex(m), _sex(target)
    if m_sex is not None and m_sex == t_sex:
        why = t("CPL011.one_sex")
    elif ref == _head_number(members) and role in HEAD_BLOOD_ROLES:
        why = t("CPL011.head_blood", role=role.lower())
    else:
        return []
    pin = _kwarg_range(m, "ref_member", lines)
    return [{"line": m.lineno, **pin, **says("CPL011", "hidden_partner", who=_member_who(m), numbers=format_numbers(kids), ref=ref, partner=_member_who(target), why=why)}]



def _may_name(patronymic: str, father: str, sex: Gender | None) -> bool:
    """`fathers.can_name`: whether the patronymic can name a man of that given name's. A patronymic the lexicon cannot
    canonicalize — one it lacks — is no contradiction: it says nothing of the father (the names linter says it lacks
    the patronymic), and asking raises. The linter never fails on it (as CPL012 of the records JSON, `on_json.names`)."""
    try:
        return can_name(patronymic, father, sex)
    except ValueError:
        return True

def _check_cpl012(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A written patronymic that cannot come from the father the household
    links the member to — `parent_member=`, else a SON's or DAUGHTER's
    `ref_member=`.

    Only a contradiction: names agree by the keys `father-claims` compares
    with (`verso.ru.naming.fathers`), so a spelling the names table folds
    («Егоровъ» of «Георгій») or a stem it does not know is silent. A parent
    who is not a man — a widow's children written «дѣти ея» — names no
    patronymic and is skipped, as is a number no member holds (CPL009's).
    """
    person = _member_arg(m, 1, "person")
    patronymic = _person_patronymic(person)
    if not patronymic or "?" in patronymic:
        return []
    # A `patr_old` beside the written form is the author's reading of the
    # patronymic («Климов» written, «Калинин» meant): either agreeing will do.
    old = (_string_literal(_kwargs(person)["patr_old"].value)
           if isinstance(person, ast.Call) and "patr_old" in _kwargs(person) else None)
    role = _role_name(m)
    if role in FOSTER_ROLES:
        return []
    kw, ref = "parent_member", _int_literal(_member_arg(m, 18, "parent_member"))
    if ref is None and role in {"SON", "DAUGHTER"}:
        kw, ref = "ref_member", _int_literal(_member_arg(m, 3, "ref_member"))
    target = members.get(ref) if ref is not None else None
    if target is None or _sex(target) is not Gender.MALE:
        return []
    father = _person_first_name(_member_arg(target, 1, "person"))
    if not father or "?" in father:
        return []
    if any(_may_name(modernize_orthography(p), modernize_orthography(father), _sex(m))
           for p in (patronymic, old) if p and "?" not in p):
        return []
    pin = _kwarg_range(m, kw, lines)
    return [{"line": m.lineno, **pin,
             **says("CPL012", "patronymic", token=patronymic, number=_member_number(m),
                    name=_person_first_name(person), patronymic=patronymic,
                    father=father, kw=kw, ref=ref)}]


def format_numbers(nums: list[int]) -> str:
    """Render member numbers compactly: [1,2,3,5] -> "1-3, 5". A hidden
    member's number below 1 stands alone — «-3--1» would read as nonsense."""
    if not nums:
        return "none"  # a test pins the word (test_check_census_parent_link)
    spans: list[str] = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1 and start > 0:
            prev = n
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    spans.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(spans)


def _check_cpl009(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A member reference naming a number absent from its own household.

    `ref_member`, `parent_member` and `secondary_ref_member` are all looked up
    in the household's own member map. A number that is not in it resolves to
    nothing and the union is silently dropped — see the module docstring.
    """
    present = sorted(members)
    issues: list[dict[str, object]] = []
    for idx, kw in ((3, "ref_member"), (18, "parent_member"),
                    (21, "secondary_ref_member")):
        ref = _int_literal(_member_arg(m, idx, kw))
        if ref is None or ref in members:
            continue
        pin = _kwarg_range(m, kw, lines)
        issues.append({"line": m.lineno, **pin, **says("CPL009", "no_such_member", who=_member_who(m), kw=kw, ref=ref, numbers=format_numbers(present))})
    return issues


def _check_cpl010(m: ast.Call, earlier: ast.Call,
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A member number already used by an earlier member of the same household.

    Pinned on the repeat's number argument; see the module docstring for what
    the repeat does downstream.
    """
    pin = _node_range(_member_arg(m, 0, "number"), lines)
    return [{"line": m.lineno, **pin, **says("CPL010", "number_taken", who=_member_who(m), earlier=_member_who(earlier))}]


def _check_cpl006(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A recorded member whose `ref_member` points at a HIDDEN member.

    `ref_member` is the relationship the SOURCE states — «дѣти ея», «жена
    его» — so it can only name somebody the source actually wrote down. A
    hidden member is our reconstruction; pointing a recorded person's
    `ref_member` at one silently rewrites what the document says, and the
    generated union then hangs off a person the roll never named.

    The reconstruction belongs on the other axis: keep `ref_member` on the
    visible relative the source names, and add `parent_member=<hidden>` to
    attach the real lineage. For two children written «дѣти ея» that is
    `ref_member` at their mother and `parent_member` at the reconstructed father.

    A hidden member pointing at anyone is fine, and so is a hidden member
    being named by `parent_member` / `secondary_ref_member` — those are the
    reconstruction's own wiring, not a claim about the source's wording.
    """
    if _is_hidden(m):
        return []
    ref = _int_literal(_member_arg(m, 3, "ref_member"))
    if ref is None:
        return []
    target = members.get(ref)
    if target is None or not _is_hidden(target):
        return []
    pin = _kwarg_range(m, "ref_member", lines)
    return [{"line": m.lineno, **pin, **says("CPL006", "ref_hidden", who=_member_who(m), ref=ref)}]


def _check_cpl005(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A hidden member that connects nobody — a fabricated leaf.

    Hidden members exist to model a person the source omits, and they earn
    their place by CONNECTING someone: being referenced as a parent/spouse, or
    pointing at an in-household spouse/parent themselves. One with no link in
    either direction adds an unattested person to the tree for no purpose.
    """
    if not _is_hidden(m):
        return []
    my_num = _member_number(m)
    if my_num is None:
        return []
    for num, other in members.items():
        if num == my_num:
            continue
        for idx, kw in ((3, "ref_member"), (18, "parent_member"),
                        (21, "secondary_ref_member")):
            if _int_literal(_member_arg(other, idx, kw)) == my_num:
                return []  # someone depends on them — a real connector
    # No inbound link. An outbound in-household ref (spouse/parent, including a
    # secondary_ref_member) still makes them load-bearing; an external
    # father_ref alone does not — that only makes them somebody's unattested
    # child.
    for idx, kw in ((3, "ref_member"), (18, "parent_member"),
                    (21, "secondary_ref_member")):
        if _int_literal(_member_arg(m, idx, kw)) in members:
            return []
    # A role that resolves head-relatively needs no explicit ref to be linked.
    if _role_name(m) in HEAD_LINKED_ROLES and _head_number(members) is not None:
        return []
    # Pin hidden=True — the unjustified thing is the hidden member itself.
    pin = _kwarg_range(m, "hidden", lines)
    return [{"line": m.lineno, **pin, **says("CPL005", "hidden_leaf", who=_member_who(m))}]


def _parent_of(m: ast.Call, head_num: int | None) -> int | None:
    """The member number the translator resolves as this member's parent."""
    pm = _int_literal(_member_arg(m, 18, "parent_member"))
    if pm is not None:
        return pm
    if _role_name(m) in CHILD_REF_ROLES:
        rm = _int_literal(_member_arg(m, 3, "ref_member"))
        return rm if rm is not None else head_num
    return None


def _ancestors_of(num: int | None, members: dict[int, ast.Call],
                  head_num: int | None) -> set[int]:
    out: set[int] = set()
    visited: set[int] = set()  # cycle guard, kept separate from the result
    cur = num
    while cur is not None and cur in members and cur not in visited:
        visited.add(cur)
        parent = _parent_of(members[cur], head_num)
        if parent is None:
            break
        out.add(parent)
        cur = parent
    return out


def _siblings_of(num: int | None, members: dict[int, ast.Call],
                 head_num: int | None) -> set[int]:
    if num is None or num not in members:
        return set()
    sibs: set[int] = set()
    own_parent = _parent_of(members[num], head_num)
    if own_parent is not None:
        sibs |= {n for n, x in members.items()
                 if n != num and _parent_of(x, head_num) == own_parent}
    # BROTHER/SISTER are recorded relative to the HEAD, so they are the head's
    # siblings (and each other's) even with no parent member in the household.
    head_sibs = {n for n, x in members.items()
                 if _role_name(x) in HEAD_SIBLING_ROLES}
    if head_num is not None:
        if num == head_num:
            sibs |= head_sibs
        elif num in head_sibs:
            sibs |= (head_sibs - {num}) | {head_num}
    return sibs


def _check_cpl004(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    """A married-in spouse whose `parent_member` points into her HUSBAND's
    lineage — she would be her own husband's sister, niece or aunt."""
    if _role_name(m) not in MARRIED_IN_ROLES or _is_hidden(m):
        return []
    pm = _int_literal(_member_arg(m, 18, "parent_member"))
    if pm is None or pm not in members:
        return []
    head_num = _head_number(members)
    rm = _int_literal(_member_arg(m, 3, "ref_member"))
    husband = rm if rm is not None else head_num
    if husband is None:
        return []
    ancestors = _ancestors_of(husband, members, head_num)
    siblings = _siblings_of(husband, members, head_num)
    if pm == husband:
        rel = t("CPL004.own_husband")
    elif pm in ancestors:
        rel = t("CPL004.husband_ancestor", husband=husband)
    elif pm in siblings:
        rel = t("CPL004.husband_sibling", husband=husband)
    else:
        return []  # points at her own kin — the legitimate shape
    # Pin parent_member — the fix is to drop exactly that kwarg.
    pin = _kwarg_range(m, "parent_member", lines)
    return [{"line": m.lineno, **pin, **says("CPL004", "invented_parent", who=_member_who(m), role=_role_name(m), pm=pm, rel=rel)}]


def _check_cpl001(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    role = _role_name(m)
    if role not in SUSPECT_ROLES:
        return []
    mkw = _kwargs(m)
    if "parent_member" in mkw:
        return []
    rm = _int_literal(_member_arg(m, 3, "ref_member"))
    if rm is None:
        return []
    target = members.get(rm)
    if target is None:
        return []  # dangling ref — relationship_ref's business
    if _role_name(target) == "HEAD" or _is_hidden(target):
        return []
    # Sibling-inheritance rescue (translator precedence 4): NEPHEW/NIECE whose
    # ref target itself descends from a known parent inherit that parent.
    target_pm = _kwargs(target).get("parent_member")
    if role in SIBLING_ROLES and target_pm is not None \
            and _int_literal(target_pm.value) is not None:
        return []
    # Adopted line: census.py skips derivation, and the listed ref is the
    # foster parent — lineage conclusions don't apply.
    if "приемн" in _comment(m).casefold() or "приемн" in _comment(target).casefold():  # i18n: content — the comment words the DSL writes
        return []
    # A female ref target can't be the patronymic father — anchor by definition.
    if _role_name(target) in FEMALE_TARGET_ROLES \
            or _person_is_female(_member_arg(target, 1, "person")):
        return []

    evidence = _father_evidence(m, target, rm)
    if evidence is None:
        return []

    target_txt = member_named(rm, _person_first_name(_member_arg(target, 1, "person")))
    # Pin the ROLE: only SON/DAUGHTER route ref_member to a parent, so the
    # role is what silently drops the link.
    pin = _node_range(_member_arg(m, 2, "role"), lines)
    return [{"line": m.lineno, **pin, **says("CPL001", "no_parent_link", who=_member_who(m), role=role, rm=rm, target_txt=target_txt, evidence=evidence)}]


def _head_number(members: dict[int, ast.Call]) -> int | None:
    for n, m in members.items():
        if _role_name(m) == "HEAD":
            return n
    return None


def _check_cpl002(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    role = _role_name(m)
    if role not in SUSPECT_ROLES or _is_hidden(m):
        return []
    mkw = _kwargs(m)
    if "parent_member" in mkw:
        return []
    rm = _int_literal(_member_arg(m, 3, "ref_member"))
    if rm is not None:
        target = members.get(rm)
        if target is None:
            return []  # dangling ref — CPL009's business
        if _is_hidden(target):
            return []  # legacy hidden upward link — resolved by the translator
        if _role_name(target) != "HEAD":
            return []  # visible non-head ref — CPL001 territory
    if "приемн" in _comment(m).casefold():  # i18n: content — the comment words the DSL writes
        return []
    patr = _person_patronymic(_member_arg(m, 1, "person"))
    hint = t("CPL002.hint", patronymic=patr) if patr else ""
    # Pin the ROLE — there is no parent_member kwarg here to point at.
    pin = _node_range(_member_arg(m, 2, "role"), lines)
    return [{"line": m.lineno, **pin, **says("CPL002", "no_father", who=_member_who(m), role=role, hint=hint)}]


def _char_col(lines: list[str], lineno: int, byte_col: int) -> int:
    """0-based AST col_offset (a UTF-8 BYTE offset) → char column.

    DSL lines are full of Cyrillic, so the byte offset overshoots. Mirrors
    census_redundancy._char_col.
    """
    idx = lineno - 1
    if 0 <= idx < len(lines):
        return len(lines[idx].encode("utf-8")[:byte_col].decode("utf-8", "ignore"))
    return byte_col


def _node_range(node: ast.AST | None,
                lines: list[str] | None) -> dict[str, object]:
    """`{line, col, end_col}` spanning a single-line AST node.

    Without a range the IntelliJ annotator has nothing to narrow to and
    highlights the WHOLE member() line (DslLintAnnotator.narrowRange). Returns
    {} when the source is unavailable or the node spans lines, and the caller
    then falls back to a line-only issue.
    """
    if lines is None or node is None:
        return {}
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    end_lineno = getattr(node, "end_lineno", None)
    end_col = getattr(node, "end_col_offset", None)
    if lineno is None or col is None or end_col is None or end_lineno != lineno:
        return {}
    return {"line": lineno,
            "col": _char_col(lines, lineno, col),
            "end_col": _char_col(lines, lineno, end_col)}


def _kwarg_range(m: ast.Call, name: str,
                 lines: list[str] | None) -> dict[str, object]:
    """`{line, col, end_col}` spanning a kwarg's ``name=value`` token."""
    if lines is None:
        return {}
    for kw in m.keywords:
        if kw.arg != name:
            continue
        end = kw.value
        if end.end_lineno != kw.lineno or end.end_col_offset is None:
            return {}
        return {"line": kw.lineno,
                "col": _char_col(lines, kw.lineno, kw.col_offset),
                "end_col": _char_col(lines, kw.lineno, end.end_col_offset)}
    return {}


def _check_cpl003(m: ast.Call, members: dict[int, ast.Call],
                  lines: list[str] | None = None) -> list[dict[str, object]]:
    if _role_name(m) != "DAUGHTER_IN_LAW" or _is_hidden(m):
        return []
    head_num = _head_number(members)
    if head_num is None:
        return []
    rm = _int_literal(_member_arg(m, 3, "ref_member"))
    if (rm if rm is not None else head_num) != head_num:
        return []  # ref → her husband directly; pass (a) pairs them
    # Rule A mirror: exactly one deceased SON of HEAD → the generator pairs
    # the сноха with him automatically.
    dead_sons = 0
    for x in members.values():
        if _role_name(x) != "SON":
            continue
        dr = _kwargs(x).get("departure_reason")
        if dr is None or _string_literal(dr.value) != "умер":  # i18n: content — the comment words the DSL writes
            continue
        x_ref = _int_literal(_member_arg(x, 3, "ref_member"))
        if x_ref is None or x_ref == head_num:
            dead_sons += 1
    if dead_sons == 1:
        return []
    # A hidden member declaring her as spouse (ref_member=<her number>).
    my_num = _member_number(m)
    for x in members.values():
        if _is_hidden(x) and my_num is not None \
                and _int_literal(_member_arg(x, 3, "ref_member")) == my_num:
            return []
    # A secondary marital annotation says the same thing, and the translator
    # emits the union from it: either SHE carries `secondary_role=WIFE` +
    # `secondary_ref_member=<him>` (the shape that keeps her primary role
    # «сноха», which is stated against the FATHER-in-law, not the husband),
    # or HE carries `secondary_role=HUSBAND` + `secondary_ref_member=<her>`.
    def _secondary(node: ast.Call) -> tuple[str | None, int | None]:
        kw = _kwargs(node)
        role_kw, ref_kw = kw.get("secondary_role"), kw.get("secondary_ref_member")
        role = (role_kw.value.attr
                if role_kw is not None and isinstance(role_kw.value, ast.Attribute)
                else None)
        ref = _int_literal(ref_kw.value) if ref_kw is not None else None
        return role, ref

    my_sec_role, my_sec_ref = _secondary(m)
    if my_sec_role == "WIFE" and my_sec_ref is not None and my_sec_ref in members:
        return []
    for x in members.values():
        x_sec_role, x_sec_ref = _secondary(x)
        if (x_sec_role == "HUSBAND" and my_num is not None
                and x_sec_ref == my_num):
            return []
    # Pin the ROLE argument: the finding is about the role, and a range keeps
    # the editor from lighting up the whole member() line.
    pin = _node_range(_member_arg(m, 2, "role"), lines)
    return [{"line": m.lineno, **pin, **says("CPL003", "no_husband", who=_member_who(m), dead_sons=dead_sons, my_num=my_num)}]


def _collect(tree: ast.AST,
             lines: list[str] | None = None) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for census in shared_ast.walk(tree):
        if not (isinstance(census, ast.Call)
                and _call_func_name(census) == "census_records"):
            continue
        for hh in shared_ast.walk(census):
            if not (isinstance(hh, ast.Call) and _call_func_name(hh) == "household"):
                continue
            members: dict[int, ast.Call] = {}
            for arg in hh.args:
                if isinstance(arg, ast.Call) and _call_func_name(arg) in _TARGETS:
                    num = _member_number(arg)
                    if num is not None:
                        if num in members:
                            issues.extend(_check_cpl010(arg, members[num], lines))
                        # The LAST member of a number wins — as it does in
                        # `CensusRecords`, whose map this mirrors.
                        members[num] = arg
            for member_node in members.values():
                issues.extend(_check_member(member_node, members, lines))
    issues.sort(key=lambda i: i["line"])  # type: ignore[index,return-value]
    return issues


def check_file(path: Path) -> list[str]:
    path = Path(path)
    try:
        tree = shared_ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [line_text(path, issue("SYN002", "detail", e.lineno or 1, level="error", detail=e.msg))]
    return [f"{path}:{i['line']}: {i['message']}" for i in _collect(tree)]


def check_file_structured(path: Path) -> list[dict[str, object]]:
    path = Path(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = shared_ast.parse(src)
    except SyntaxError:
        return []  # other linters report the syntax error as an error
    # `lines` lets CPL003 pin its role argument; spreading the issue keeps the
    # col/end_col it produces instead of rebuilding a line-only dict.
    return [{"level": "warn", **i} for i in _collect(tree, src.splitlines())]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    warnings: list[str] = []
    for arg in sys.argv[1:]:
        warnings.extend(check_file(Path(arg)))
    for w in warnings:
        print(w)
    # CPL001 is advisory — never fail the build on warnings.
    return 0


if __name__ == "__main__":
    sys.exit(main())
