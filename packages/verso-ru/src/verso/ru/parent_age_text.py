"""The parents' ages a civil birth's `comment=` still says in prose — the one reader both ZGS006 (the
linter that finds them) and `verso fix-parent-ages` (the codemod that moves them) ask.

A reading is moved to `father_age=` / `mother_age=` only when `age_bounds` can read it (the
owner's rule Р3): the number a fragment leads with, clean or with its doubt («42 (?)», «34 (или 31 ?)»,
«40(?)/43(?)»). What is cut («3…»), interleaved («2[?](?)»), corrected («34 испр. 31») or not a whole
number of 1–3 digits («1920?», «42 1/2») goes to no field, and its fragment stays. A doubt stays in the comment: the
field takes the first number, the fragment stays as written — its spacing and trailing period too.

The forms, measured on the corpus's civil books:

- `father_and_mother` — «отцу N, матери M»;
- `father`, `mother` — «отцу N», «матери M» alone;
- `pair` — «возраст N и M» (the father's first);
- `parents_1920` — «родители: Иван (35) и Феврония (35) Горюхины, занятие не указ.»: names of several words, with
  «(?)» marks, the parents joined by «и» or «,». The first two parentheticals that open with a figure or «возр» are the
  father's and the mother's age, each only where it directly follows a name token (a word, with «(?)» marks); the clause
  ends where a later label opens («, дети:»), and a clause with role words («вдова», «муж», «мать», «отец») or with
  any other number of such slots than two is not read: no age is given to a role by position alone. «(N)», «(N л.)»,
  «(N лет)» are cut out of the clause, the rest of it stays. A doubt
  («(23?)», «(37(?))») gives its figure and stays; «(2[?](?))», «(возр. не указ.)» give nothing. With no such
  parenthetical, «, возраст N и M» inside the clause is the pair.

A comment's fragments stand apart by «;» (a space after it or not). A fragment whose every part moved goes with its separator; one
part left (a doubt, a cut figure, a role whose field is already written) stays, as it was written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FATHER, MOTHER = "father", "mother"
ROLES = (FATHER, MOTHER)
FIELDS = {FATHER: "father_age", MOTHER: "mother_age"}

#: Forms, by the name the codemod counts them under.
FATHER_AND_MOTHER, FATHER_ALONE, MOTHER_ALONE, PAIR, PARENTS_1920 = (
    "father_and_mother", "father", "mother", "pair", "parents_1920")
FORMS = (FATHER_AND_MOTHER, FATHER_ALONE, MOTHER_ALONE, PAIR, PARENTS_1920)

SEPARATOR = "; "

_UNIT = r"(?:\s*(?:лет|года?|л\.?|г\.?))?"    # i18n: content — the age's unit words as the acts write them
_CLEAN = re.compile(rf"^(\d{{1,3}}){_UNIT}$")
_LEAD = re.compile(r"^(\d{1,3})(?!\d)(.*)$", re.DOTALL)     # at most three digits, and not the head of a longer number
#: What may follow a number and still be its doubt: a «?», a second figure, «или».
#: «испр.» (corrected) is no doubt: the first figure may be the one the scribe struck out, so no field takes it.
_DOUBT_TAIL = re.compile(r"^[\s()?/\d]*(?:или[\s()?/\d]*)*$")  # i18n: content — the scribe's word of a second reading
#: A «/» is a doubt only between two figures of two or three digits («40/43»), not a fraction («42 1/2», «1/2»).
_DOUBT_MARK = re.compile(r"\?|или|(?<!\d)/(?=\d{2,3}(?!\d))")   # i18n: content — the same word

_PARTS = re.compile(r"^(?P<l1>отцу)\s+(?P<f>.+?)(?:,\s*(?P<l2>матери)\s+(?P<m>.+))?$"    # i18n: content — «to the father … to the mother»
                    r"|^(?P<l3>матери)\s+(?P<m3>.+)$", re.IGNORECASE | re.DOTALL)         # i18n: content
_PAIR = re.compile(rf"^возраст\s+(\d{{1,3}})\s+и\s+(\d{{1,3}}){_UNIT}$", re.IGNORECASE)   # i18n: content — «age N and M»
_PAREN = re.compile(r"\((?:[^()]|\([^()]*\))*\)")
_SLOT = re.compile(r"^(?:\d|возр)", re.IGNORECASE)    # i18n: content — «age»
#: A slot stands right after a name token: a word, an initial («Ф.»), or letters the scribe restored in brackets («[Х.]»),
#: then «(?)» marks only.
_AFTER_NAME = re.compile(r"([^\W\d_][^\W\d_.-]*|[^\W\d_]\.|\[[^\]\d]*\])(?:\s*\(\?\))*\s*$")
_LABEL = re.compile(r"[^\W\d_]+:")          # a later label of the clause («дети:») ends the parents' words
_ROLE_WORDS = re.compile(r"\b(?:вдов\w*|муж\w*|жен[аыуе]|мать|матер\w*|отец|отц\w*"      # i18n: content — widow, husband, wife, mother, father,
                         r"|сын\w*|доч\w*|дет\w*|реб\w*|брат\w*|сестр\w*|крестн\w*|восприемн\w*|дед\w*|баб\w*)", re.IGNORECASE)  # i18n: content — and other kin
#: The parents' words end at a comma and a lowercase word («, занятие не указ.», «, крестный …»).
_CLAUSE_END = re.compile(r",\s*[а-яё]")   # i18n: content — lowercase Cyrillic
_AGE_CLEAN = re.compile(r"^(\d{1,3})(?:\s*(?:лет|л\.?|г\.?))?$")                   # i18n: content — the unit words
_AGE_DOUBT = re.compile(r"^(\d{1,3})\s*(?:\?|\(\?\))\s*(?:лет|л\.?|г\.?)?$")       # i18n: content — the unit words
_PAIR_IN_CLAUSE = re.compile(rf"\s*,\s*возраст\s+(\d{{1,3}})\s+и\s+(\d{{1,3}}){_UNIT}(?=\s*(?:,|$))", re.IGNORECASE)  # i18n: content — «age N and M»
_SEPARATOR = re.compile(r"(;\s*)")


@dataclass(frozen=True)
class Reading:
    """What a comment says of the parents' ages, for the roles asked: the figure each role takes, the
    comment that stays, the forms the figures came from (one per fragment that gave one)."""
    ages: dict[str, int] = field(default_factory=dict)
    comment: str | None = None
    forms: tuple[str, ...] = ()
    per_role: dict[str, str] = field(default_factory=dict)    # role → the form its figure came from


def _classify(text: str) -> tuple[int, bool] | None:
    """(the figure, whether it stands clean) of one role's words; None when no field takes it."""
    text = text.strip()
    if (clean := _CLEAN.match(text)) is not None:
        return int(clean.group(1)), True
    lead = _LEAD.match(text)
    if lead is None:
        return None
    tail = lead.group(2)
    if "/" in tail and len(lead.group(1)) < 2:     # «4/45» is no pair of ages
        return None
    if _DOUBT_TAIL.match(tail) and _DOUBT_MARK.search(tail):
        return int(lead.group(1)), False
    return None


def _follows_name(before: str) -> bool:
    """Whether `before` ends in a name token — a word that is no conjunction, with «(?)» marks only after it."""
    ending = _AFTER_NAME.search(before)
    return ending is not None and ending.group(1).lower() not in ("и", "а")    # i18n: content — «and», «but»


def _parents(text: str, wanted: frozenset[str]) -> tuple[dict[str, int], str | None, str] | None:
    """The 1920 form: «родители: Имя (N) и Имя (M) Фамилия, …» — see the module's docstring."""
    head, body = text[:len("родители:")], text[len("родители:"):]    # i18n: content — «parents:»
    label = _LABEL.search(body)
    ends = [m.start() for m in (label, _CLAUSE_END.search(body)) if m]
    clause = body[:min(ends)] if ends else body     # the parents' words end where «дети:» or «, занятие…» begins
    slots = [(p.start(), p.end(), p.group()[1:-1].strip()) for p in _PAREN.finditer(clause)
             if _SLOT.match(p.group()[1:-1].strip())]
    moved: dict[str, int] = {}
    if slots and (_ROLE_WORDS.search(clause) or any(not _follows_name(clause[:start]) for start, _, _ in slots)):
        return None                                      # by position alone no age is given to a role
    if len(slots) == 2:
        cut: list[tuple[int, int]] = []
        for role, (start, end, inner) in zip(ROLES, slots, strict=True):
            if role not in wanted:
                continue
            if (clean := _AGE_CLEAN.match(inner)) is not None:
                moved[role] = int(clean.group(1))
                cut.append((start, end))
            elif (doubt := _AGE_DOUBT.match(inner)) is not None:
                moved[role] = int(doubt.group(1))
        for start, end in reversed(cut):
            start -= len(body[:start]) - len(body[:start].rstrip())
            body = body[:start] + body[end:]
    elif not slots and wanted >= {FATHER, MOTHER} and (pair := _PAIR_IN_CLAUSE.search(body)) is not None:
        moved = {FATHER: int(pair.group(1)), MOTHER: int(pair.group(2))}
        body = body[:pair.start()] + body[pair.end():]
    return (moved, head + body, PARENTS_1920) if moved else None


def _fragment(text: str, wanted: frozenset[str]) -> tuple[dict[str, int], str | None, str] | None:
    """(the figures moved, what stays of the fragment — None when nothing, the form) or None."""
    if (pair := _PAIR.match(text.removesuffix("."))) is not None:
        if wanted >= {FATHER, MOTHER}:
            return {FATHER: int(pair.group(1)), MOTHER: int(pair.group(2))}, None, PAIR
        return None
    if text.lower().startswith("родители:"):    # i18n: content — «parents:»
        return _parents(text, wanted)
    whole = text.removesuffix(".")
    parts = _PARTS.match(whole)
    if parts is None:
        return None
    labelled = ([(FATHER, "l1", "f")] if parts["l1"] else []) \
        + ([(MOTHER, "l2", "m")] if parts["l2"] else []) \
        + ([(MOTHER, "l3", "m3")] if parts["l3"] else [])
    moved: dict[str, int] = {}
    kept: list[tuple[int, int]] = []      # the spans of the parts that stay, in the text as written
    for role, label, words in labelled:
        read = _classify(parts[words]) if role in wanted else None
        span = (parts.start(label), parts.end(words))
        if read is None:
            kept.append(span)
            continue
        moved[role] = read[0]
        if not read[1]:
            kept.append(span)
    if not moved:
        return None
    form = FATHER_AND_MOTHER if len(labelled) == 2 else FATHER_ALONE if labelled[0][0] == FATHER else MOTHER_ALONE
    if not kept:
        return moved, None, form
    # What stays is what was written: with every part left, the fragment whole; else the one part, with the period
    # that closed the fragment.
    stays = text if len(kept) == len(labelled) else text[kept[0][0]:kept[0][1]] + text[len(whole):]
    return moved, stays, form


def read_comment(comment: str | None, roles: tuple[str, ...] = ROLES) -> Reading | None:
    """The parents' ages `comment` says for `roles` and what stays of it; None when nothing moves.

    >>> found = read_comment("записан; отцу 26, матери 22; заявитель — отец")
    >>> found.ages, found.comment
    ({'father': 26, 'mother': 22}, 'записан; заявитель — отец')
    >>> read_comment("отцу 42 (?), матери 43").comment
    'отцу 42 (?)'
    >>> read_comment("матери 3…") is None
    True
    """
    if not comment:
        return None
    wanted = frozenset(roles)
    ages: dict[str, int] = {}
    per_role: dict[str, str] = {}
    forms: list[str] = []
    pieces = _SEPARATOR.split(comment)       # fragment, separator, fragment …
    fragments, separators = pieces[::2], pieces[1::2]
    stays: list[tuple[str, str]] = []        # (the separator before it, the fragment)
    for number, text in enumerate(fragments):
        before = separators[number - 1] if number else ""
        found = _fragment(text, wanted - ages.keys())
        if found is None:
            stays.append((before, text))
            continue
        moved, kept, form = found
        ages.update(moved)
        per_role.update(dict.fromkeys(moved, form))
        forms.append(form)
        if kept is not None:
            stays.append((before, kept))
    if not ages:
        return None
    rest = "".join((before if number else "") + text for number, (before, text) in enumerate(stays))
    return Reading(ages, rest or None, tuple(forms), per_role)
