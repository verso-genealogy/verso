"""The rules every kind of record shares (class `written`): a name's letters, a relative's reference, an
age, a marital status, a status's orthography, how a relative attaches, an age retraction — and a divorce's
marriage written as text (DVC001).

Each rule reads what a node wrote (`FileView.written`: the arguments of its call, by parameter) and
answers as its check answers the source, with the check's own tables and message builders. What the
check reads off the SYNTAX alone has no JSON counterpart:

* a value is read as the call evaluated it. The check skips a name (`age=AGE`, `person=BOOK_PRIEST`,
  `relationship_ref=REF`) and a call whose value it cannot read, the walk sees the value. A name bound
  to a wrong value, or a person bound outside the record, therefore differs; neither is in the corpus.
* a positional age (`death(…, "5 лет")`) is read like a keyword one, by both readers: AGE001/AGE002 read an age
  in its place (`ages.AGE_POSITIONS`) as they read the keyword.
* a book's `defaults` is written whole: `RecordDefaults.__init__` derives `status_groom` from `status_male` when
  the author wrote none, and the JSON keeps no record of which keywords were written (the value has no
  `_written`). SOR001 skips a `status_groom` equal to `status_male`; the case lost is an author writing that
  very equal `status_groom` too (one finding fewer than dsllint).
* book-level defaults shared by several documents (`DEFAULTS` passed to two record sets) count once per use
  on JSON, as a person shared by two records does.
* SOR001's `bound_*` variants (a status written through a string the file binds, `name=`) are the
  source's: the JSON holds the text, so the walk answers the `literal_*` variant of the same text.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from verso.ru.ages import AGE_KWARGS, whole_years
from verso.ru.gender import Gender
from verso.ru.linters.checks import relationship_ref
from verso.ru.linters.checks.ages import is_valid_age_string, said_age001, said_unknown
from verso.ru.linters.checks.census_age import PREV_AGE_COMMENT_RE
from verso.ru.linters.checks.divorces import said as said_dvc001
from verso.ru.linters.checks.marital_status import KNOWN_MARITAL
from verso.ru.linters.checks.names import CYRILLIC_NAME_RE
from verso.ru.linters.checks.relative_attachment import GODPARENT_REF, WITNESS_REF, Subject
from verso.ru.linters.checks.retractions import NOT_RECORDED
from verso.ru.linters.checks.status_orthography import FIELDS, HONORIFIC, PRE_REFORM, catalog, modern_spelling
from verso.ru.linters.issue import says
from verso.ru.linters.on_json.walk import (
    FileView, Finding, Rule, as_text, finding, finding_of, gender_from_name, only, personas)
from verso.ru.naming import modernize_orthography

__all__ = ["RULES", "gender_of", "name_modern", "subject_of"]

type Node = Mapping[str, Any]

_NAME_FIELDS = ("name_orig", "patr_orig", "last_name_orig", "name_modern_orth", "last_name_modern_orth")
_REF_RECORDS = frozenset({"birth", "marriage", "death"})     # the records whose `relatives` the checks read
_AGE_RECORDS = frozenset({"death", "marriage", "external_record"})   # `ages.AGE_CALLS`, as the export names them
_MALE, _FEMALE = Gender.MALE.name, Gender.FEMALE.name


# --- NAM005: the letters of a name -----------------------------------------------------------------

def nam005(view: FileView) -> Iterator[Finding]:
    """A written name with a character no Russian name has (`names.NameChecker._check_person`): each of
    the five spellings a `person()` writes, but `?`."""
    for _, record in view.records():
        for persona in personas(record):
            written = view.written("person", persona)
            for field in _NAME_FIELDS:
                value = as_text(written.get(field))
                if value and value != "?" and not CYRILLIC_NAME_RE.match(value):
                    yield finding("NAM005", "latin", record["id"], token=value, field=field, value=value)


# --- REL001, REL002: a relative's reference ---------------------------------------------------------

def _references(view: FileView) -> Iterator[Finding]:
    """A `relationship_ref` of a birth's, a marriage's or a death's relative outside the allowlist
    (`relationship_ref.RelationshipRefChecker`): REL001 where a correction is known, REL002 else."""
    for _, record in view.records():
        if record["kind"] not in _REF_RECORDS:
            continue
        for persona in personas(record, "relative"):
            ref = as_text(view.written("relative", persona["link"]).get("relationship_ref"))
            if ref is not None and not relationship_ref.is_allowed(ref):
                yield finding_of(relationship_ref.said(ref)["message"], record["id"])


def rel001(view: FileView) -> Iterator[Finding]:
    return only("REL001", _references(view))


def rel002(view: FileView) -> Iterator[Finding]:
    return only("REL002", _references(view))


# --- AGE001, AGE002: an age's form ------------------------------------------------------------------

def _ages(view: FileView) -> Iterator[Finding]:
    """An age of a death, a marriage or a card that no `split_age` reads (AGE002: negative, a bool, junk
    text, a repeated unit), or that spells a whole number of years as a string (AGE001)
    (`ages.AgeChecker._check_age`)."""
    for _, record in view.records():
        kind = record["kind"]
        if kind not in _AGE_RECORDS:
            continue
        written = view.written(kind, record)
        for kwarg in AGE_KWARGS:
            value = written.get(kwarg)
            if value is None:
                continue
            if isinstance(value, bool):
                yield finding_of(said_unknown(kwarg, repr(value))["message"], record["id"])
            elif isinstance(value, (int, float)):
                if value < 0:
                    yield finding_of(said_unknown(kwarg, repr(value))["message"], record["id"])
            elif isinstance(value, str):
                if not is_valid_age_string(value):
                    yield finding_of(said_unknown(kwarg, value)["message"], record["id"])
                    continue
                digits = whole_years(value)
                if digits is not None:
                    yield finding_of(said_age001(kwarg, value, digits, kind)["message"], record["id"])


def age001(view: FileView) -> Iterator[Finding]:
    return only("AGE001", _ages(view))


def age002(view: FileView) -> Iterator[Finding]:
    return only("AGE002", _ages(view))


# --- MST001: a marital status ----------------------------------------------------------------------

def mst001(view: FileView) -> Iterator[Finding]:
    """A `marital_status` of a roll's member or of a WWI/WWII card with no constant in the catalog
    (`marital_status.MaritalStatusChecker`): a known text is `single_line_calls`' to propose a constant for."""
    if not KNOWN_MARITAL:
        return
    for _, record in view.records():
        sources: list[Node] = []
        if record["kind"] == "external_record":
            if record.get("written", {}).get("verb") != "criminal_record":      # a criminal card has no marital_status=
                sources.append(view.written("external_record", record))
        else:
            sources.extend(view.written("member", p["link"]) for p in personas(record, "member"))
        for written in sources:
            literal = as_text(written.get("marital_status"))
            if literal is not None and literal not in KNOWN_MARITAL:
                yield finding("MST001", "unknown", record["id"], token=literal, value=literal)


# --- SOR001: a status in the old orthography ---------------------------------------------------------

def _statuses(view: FileView) -> Iterator[tuple[str, str, str]]:
    """(record or book id, kwarg, text) of each classification text a node wrote: a person's `status`,
    a book's defaults, a member's `departure_reason`. A catalog constant is a `{text, gender}` object
    and modern by construction; only a string is read."""
    for doc in view.documents():
        defaults = doc.get("written", {}).get("defaults") or {}
        for kwarg, value in defaults.items():
            if kwarg == "status_groom" and value == defaults.get("status_male"):
                continue            # derived by RecordDefaults.__init__ from status_male, not written
            if kwarg in FIELDS and isinstance(value, str):
                yield doc["id"], kwarg, value
    for _, record in view.records():
        for persona in personas(record):
            if isinstance(status := view.written("person", persona).get("status"), str):
                yield record["id"], "status", status
            if persona.get("role") == "member":
                reason = as_text(view.written("member", persona["link"]).get("departure_reason"))
                if reason is not None:
                    yield record["id"], "departure_reason", reason


def sor001(view: FileView) -> Iterator[Finding]:
    """A classification field with a pre-reform letter or a capitalised honorific
    (`status_orthography._collect`): the text, its modern spelling and the catalog constant of it."""
    for where, kwarg, text in _statuses(view):
        if not (PRE_REFORM.search(text) or HONORIFIC.search(text)):
            continue
        modern = modern_spelling(text)
        constant = catalog().get(modern)
        params = {"kwarg": kwarg, "text": text, "modern": modern, **({"constant": constant} if constant else {})}
        yield finding("SOR001", "literal_constant" if constant else "literal_words", where, token=text, **params)


# --- RLA001: a relative that attaches to nobody -----------------------------------------------------

def name_modern(written: Node) -> str | None:
    """`relative_attachment._name_modern`: the modern first name written, else the old one modernized. A keyword
    holding none or nothing is no keyword (a positional call that reaches a later parameter writes the ones before it
    as none, and an old file as `""`)."""
    if modern := as_text(written.get("name_modern_orth")):
        return modern
    orig = as_text(written.get("name_orig"))
    return modernize_orthography(orig) if orig else None


def gender_of(view: FileView, persona: Node, fallback: str | None) -> str | None:
    """`relative_attachment._person_gender`: the gender the person writes, else its name's (none without a names
    table), else the slot's."""
    written = view.written("person", persona)
    gender = as_text(written.get("gender"))
    if gender:
        return gender.upper()
    name = name_modern(written)
    inferred = gender_from_name(name) if name else None
    return inferred.name if inferred is not None else fallback


def subject_of(view: FileView, verb: str, slots: Mapping[tuple[str, int | None], Node],
               ref: str | None) -> Subject | None:
    """`relative_attachment._subject_of` over the personas a record holds: which person the reference
    attaches the relative to, and whether the translator wires the two."""
    ref = ref or ""
    if verb == "marriage":
        if ref == "жених":  # i18n: content — the reference words the DSL writes
            return Subject("groom", _MALE, True)
        if ref == "невеста":  # i18n: content — the reference words the DSL writes
            return Subject("bride", _FEMALE, True)
        if witness := WITNESS_REF.match(ref):
            return Subject(f"witness{witness.group(1)}", None, True) if ("witness", int(witness.group(1))) in slots \
                else None
        return None
    if verb == "birth":
        if numbered := GODPARENT_REF.match(ref):
            slot = int(numbered.group(1))
            if ("godparent", slot) not in slots:
                return None
            return Subject(f"god_parent{slot}", {1: _MALE, 2: _FEMALE}.get(slot), True)
        if ref == "восприемница":  # i18n: content — the reference words the DSL writes
            sole = _sole_female_godparent(view, slots)
            return Subject(f"god_parent{sole}", _FEMALE, False) if sole else None
        if ref == "мать":  # i18n: content — the reference words the DSL writes
            return Subject("mother", _FEMALE, True) if ("mother", None) in slots else None
        return None
    if verb == "death" and not ref:
        return Subject("deceased", None, True)
    return None


def _sole_female_godparent(view: FileView, slots: Mapping[tuple[str, int | None], Node]) -> int | None:
    """The single female godparent slot of a birth, if there is exactly one."""
    female = [i for i in (1, 2, 3, 4)
              if ("godparent", i) in slots and gender_of(view, slots[("godparent", i)], {1: _MALE, 2: _FEMALE}.get(i)) == _FEMALE]
    return female[0] if len(female) == 1 else None


def rla001(view: FileView) -> Iterator[Finding]:
    """A relative of a birth, a marriage or a death whose reference names a slot the record lacks or one the
    translator does not wire (`relative_attachment._unattached_issue`); the kinship checks (RLA002, RLA003) are
    other rules."""
    for _, record in view.records():
        verb = record["kind"]
        if verb not in _REF_RECORDS:
            continue
        slots = {(p["role"], p.get("slot")): p for p in personas(record)}
        for persona in personas(record, "relative"):
            ref = as_text(view.written("relative", persona["link"]).get("relationship_ref"))
            subject = subject_of(view, verb, slots, ref)
            shown = ref or "<none>"
            if subject is None:
                yield finding_of(says("RLA001", "no_subject", ref=shown, verb=verb)["message"], record["id"])
            elif not subject.wired:
                sole = _sole_female_godparent(view, slots) if ref == "восприемница" else None  # i18n: content — the reference words the DSL writes
                yield finding_of((says("RLA001", "unwired_godmother", ref=shown, kwarg=subject.kwarg, godparent=sole)
                                  if sole else says("RLA001", "unwired", ref=shown, kwarg=subject.kwarg))["message"],
                                 record["id"])


# --- RET001–RET004: an age retraction that retracts nothing ---------------------------------

def _states(value: object) -> bool:
    """`retractions._states` of a written value: it states an age (or a date) unless it is none or a
    not-recorded mark."""
    if value is None:
        return False
    return not (isinstance(value, str) and value.strip() in NOT_RECORDED)


def _retractions(view: FileView) -> Iterator[Finding]:
    """`retractions._check_member` for each roll line and `_check_death` for each burial."""
    for _, record in view.records():
        if record["kind"] == "birth":
            written = view.written("birth", record)
            if "source_age_error" in written and not any(_states(written.get(k)) for k in ("father_age", "mother_age")):
                yield finding("RET004", "birth", record["id"])
            continue
        if record["kind"] == "death":
            written = view.written("death", record)
            if not _states(written.get("age")):
                for name in ("source_age_error", "namesake"):
                    if name in written:
                        yield finding("RET002", "burial_" + name, record["id"])
            continue
        for persona in personas(record, "member"):
            written = view.written("member", persona["link"])
            comment = as_text(written.get("comment"))
            has_prev = _states(written.get("previous_age")) or bool(comment and PREV_AGE_COMMENT_RE.search(comment))
            has_age = _states(written.get("age"))
            has_date = any(_states(written[k]) for k in ("birth_year", "birth_day", "birth_month") if k in written)
            whole, prev = "source_age_error" in written, "previous_age_error" in written
            if prev and not has_prev:
                yield finding("RET001", "no_previous", record["id"])
            if whole and not (has_age or has_prev or has_date):
                yield finding("RET002", "no_age", record["id"])
            if whole and prev:
                yield finding("RET003", "both", record["id"])


def ret001(view: FileView) -> Iterator[Finding]:
    return only("RET001", _retractions(view))


def ret002(view: FileView) -> Iterator[Finding]:
    return only("RET002", _retractions(view))


def ret003(view: FileView) -> Iterator[Finding]:
    return only("RET003", _retractions(view))


def ret004(view: FileView) -> Iterator[Finding]:
    return only("RET004", _retractions(view))


# --- DVC001: a divorce's marriage as text --------------------------------------------------------------

def dvc001(view: FileView) -> Iterator[Finding]:
    """A divorce whose `marriage_date` is text (`divorces._collect`): the same words, its replacement where the
    text reads as a date. A replay's record holds what the DSL wrote, a text kept as text."""
    for _, record in view.records():
        if record["kind"] != "divorce":
            continue
        value = view.written("divorce", record).get("marriage_date")
        if isinstance(value, str):
            yield finding_of(said_dvc001(value)["message"], record["id"])


RULES: dict[str, Rule] = {
    "NAM005": nam005, "REL001": rel001, "REL002": rel002, "AGE001": age001, "AGE002": age002,
    "MST001": mst001, "SOR001": sor001, "RLA001": rla001, "RET001": ret001, "RET002": ret002, "RET003": ret003, "RET004": ret004,
    "DVC001": dvc001,
}
