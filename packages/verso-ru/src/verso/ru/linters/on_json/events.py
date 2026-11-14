"""The rules on a death's, a marriage's, a card's and a name list's own fields (class `written`): the residences a
record states, the relatives a death names, the side a witness stood for, the hosts and documents of the external
cards, a name list's document and ages.

Each rule reads what a node wrote (`FileView.written`: the arguments of its call, by parameter) and answers as its
check answers the source, with the check's own tables and message builders. What the check reads off the SYNTAX
alone has no JSON counterpart:

* a value is read as the call evaluated it. The checks skip a name (`comment=NOTE`, `document_type=DOCUMENT`,
  `side=SIDE`) and a call whose value they cannot read; the walk sees the value. A name bound to a wrong value
  differs; none is in the corpus. The same holds of a persona bound to a name: WSD002-WSD006 see a witness only
  as a literal `person(...)` call, so a `W = person(...)` passed as `witness1=W` is invisible to them and read
  here; likewise the relatives, `groom=` and `bride=` that DRA001, DRL001 and MRA001 take from a bound name. `side=None` (a side that is not a `Side.X`) is the check's `"?"`: there it is a
  side written and no side declared, here the same.
* a keyword and a positional argument are one in `written`, and to the checks: MRA001 reads `groom`, `bride` and
  `relatives` in their places, DRA001, DRA002 and DRL001 `deceased` and `relatives` (`GROOM_AT`, `DECEASED_AT`…),
  as they read the keywords. (`source_url=`, `document_type=`, `casualty_reason=`, `award=` and the `age=` of
  `listed_person` are keyword-only in their factories.)
* an enum is its code: `document_type` reads as its member name (`wwi_document_type.award_lists` is
  `AWARD_LISTS`), a relationship as the label DRL001 gives (`father` is `FATHER`), a side as `GROOM`/`BRIDE`.
  A `relationship` that is none reads as the check's `#n`, the place of the relative in the list.
* a person is a persona, not a call. A `person(side=…)` bound once and used as a witness (`witness1=W`) is
  not a call the check sees as a witness: WSD001 flags it there and exempts it here, where the persona is a
  witness. A person bound but used nowhere is no persona and no finding.
* DRA001's household anchor is the deceased's residence, written as `""` too (an empty string is an anchor, as
  in the source), else the first relative's truthy one.
* DRL001 and DRA001 read the relatives of a death (a birth's and a marriage's are other records'); the label
  of a relative is its place among the death's relatives, as the check counts the entries it can read.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from verso.ru.linters.checks.external_sources import AWARD_MEMBER_NAMES, CRIMINAL_HOSTS, GWAR_HOSTS, PAMYAT_HOSTS
from verso.ru.linters.checks.witness_side import PER_SIDE_COLUMNS, SIDE_WORD, words_side
from verso.ru.linters.on_json.walk import FileView, Finding, Rule, as_text, finding, only, personas

__all__ = ["RULES"]

type Node = Mapping[str, Any]

_WITNESS_SLOTS = range(1, 7)
_EXTERNAL_VERBS = ("criminal_record", "wwi_record", "wwii_record")
_HOSTS = {"criminal_record": CRIMINAL_HOSTS, "wwi_record": GWAR_HOSTS, "wwii_record": PAMYAT_HOSTS}
_UNKNOWN = "?"      # witness_side: a `side=` that is no `Side.X` attribute or name


def _records(view: FileView, kind: str) -> Iterator[Node]:
    for _, record in view.records():
        if record["kind"] == kind:
            yield record


def _residence(view: FileView, persona: Node | None) -> str | None:
    """`deaths_residence._residence_value`: the residence a person wrote, if it is a string."""
    return as_text(view.written("person", persona).get("residence")) if persona is not None else None


# --- DRA001: a death whose household lives in two villages ------------------------------------------

def dra001(view: FileView) -> Iterator[Finding]:
    """Two written residences of one death that disagree (`deaths_residence._check_death`): a relative's against
    the deceased's, else against the first relative's own. DRA002 is the same walk's other half."""
    for record in _records(view, "death"):
        relatives = personas(record, "relative")
        if not relatives:
            continue
        deceased = next(iter(personas(record, "deceased")), None)
        anchor = _residence(view, deceased)
        if anchor is None:
            anchor = next((v for rel in relatives if (v := _residence(view, rel))), None)
        if anchor is None:
            continue
        for rel in relatives:
            value = _residence(view, rel)
            if value and value != anchor:
                yield finding("DRA001", "contradicts", record["id"], val=repr(value), anchor=repr(anchor))


# --- DRL001: a death that names more than one relative -----------------------------------------------

def _relationship_label(view: FileView, relatives: list[Node], index: int) -> str:
    """`deaths_relatives._relationship_label`: the relationship's member name, else `#<n>`."""
    relationship = as_text(view.written("relative", relatives[index]["link"]).get("relationship"))
    return relationship.upper() if relationship else f"#{index + 1}"


def drl001(view: FileView) -> Iterator[Finding]:
    """Every relative of a death after the first, which the translator drops (`deaths_relatives._check_death`)."""
    for record in _records(view, "death"):
        relatives = personas(record, "relative")
        if len(relatives) < 2:
            continue
        kept = _relationship_label(view, relatives, 0)
        for index in range(1, len(relatives)):
            yield finding("DRL001", "dropped", record["id"],
                          relative=_relationship_label(view, relatives, index), kept=kept)


# --- MRA001: a party and its parent in two villages --------------------------------------------------

def mra001(view: FileView) -> Iterator[Finding]:
    """A father or a mother of the groom or the bride whose written residence differs from the party's
    (`marriage_residence._check_marriage`)."""
    for record in _records(view, "marriage"):
        for rel in personas(record, "relative"):
            link = view.written("relative", rel["link"])
            relationship = (as_text(link.get("relationship")) or "").upper()
            if relationship not in ("FATHER", "MOTHER"):
                continue
            ref = as_text(link.get("relationship_ref"))
            if ref and "жених" in ref:  # i18n: content — the reference words the DSL writes
                party_label = "groom"
            elif ref and "невест" in ref:  # i18n: content — the reference words the DSL writes
                party_label = "bride"
            else:
                continue
            party = next(iter(personas(record, party_label)), None)
            if party is None:
                continue
            party_res, parent_res = _residence(view, party), _residence(view, rel)
            if not party_res or not parent_res or party_res == parent_res:
                continue
            yield finding("MRA001", f"{relationship.lower()}_{party_label}", record["id"],
                          parent=repr(parent_res), party=repr(party_res))


# --- WSD001-WSD006: the side a witness stood for -----------------------------------------------------

def _side(view: FileView, persona: Node) -> str | None:
    """`witness_side._side_of`: "GROOM"/"BRIDE", the check's "?" for a `side=` that names neither, else None."""
    written = view.written("person", persona)
    if "side" not in written:
        return None
    side = as_text(written["side"])
    return side.upper() if side else _UNKNOWN


def _witnesses(record: Node) -> list[tuple[int, Node]]:
    """`witness_side._marriage_witnesses`: (slot, persona) of a marriage's filled witness slots, by slot."""
    found = [(p["slot"], p) for p in personas(record, "witness") if p.get("slot") in _WITNESS_SLOTS]
    return sorted(found, key=lambda item: item[0])


def wsd001(view: FileView) -> Iterator[Finding]:
    """A `side=` on a person who is not a marriage's witness: a groom, a bride, a relative, anyone in another
    record (`witness_side._hard`)."""
    for _, record in view.records():
        for persona in record["persons"]:
            witness = record["kind"] == "marriage" and persona.get("role") == "witness" \
                and persona.get("slot") in _WITNESS_SLOTS
            if not witness and "side" in view.written("person", persona):
                yield finding("WSD001", "outside", record["id"])


def wsd002(view: FileView) -> Iterator[Finding]:
    """A witness's `side=` against the words of the witness's own `comment=` (`witness_side._hard`)."""
    for record in _records(view, "marriage"):
        for n, persona in _witnesses(record):
            side = _side(view, persona)
            if side not in SIDE_WORD:
                continue
            words = words_side(as_text(view.written("person", persona).get("comment")))
            if words in SIDE_WORD and words != side:
                yield finding("WSD002", f"says_{words.lower()}", record["id"], n=n, side=side)


def _advisory(view: FileView) -> Iterator[Finding]:
    """`witness_side._advisory`: the declarations of a marriage's witnesses against each other."""
    for record in _records(view, "marriage"):
        rid = record["id"]
        witnesses = _witnesses(record)
        if not witnesses:
            continue
        sides: dict[int, str | None] = {}
        for n, persona in witnesses:
            written = view.written("person", persona)
            side = _side(view, persona)
            sides[n] = side if side in SIDE_WORD else None
            words = words_side(as_text(written.get("comment")))
            if words not in SIDE_WORD or "comment" not in written:
                continue
            if side is None:
                yield finding("WSD003", f"undeclared_{words.lower()}", rid, n=n)
            elif side == words:
                yield finding("WSD003", f"repeated_{words.lower()}", rid, n=n)
        if words_side(as_text(record["written"].get("comment"))) is not None and any(s is None for s in sides.values()):
            yield finding("WSD003", "record_comment", rid)
        declared = {n: s for n, s in sides.items() if s is not None}
        if declared and len(declared) < len(sides):
            missing = ", ".join(f"witness{n}" for n, s in sides.items() if s is None)
            yield finding("WSD004", "half_declared", rid, missing=missing)
        grooms = [n for n, s in declared.items() if s == "GROOM"]
        brides = [n for n, s in declared.items() if s == "BRIDE"]
        if grooms and brides and max(grooms) > min(brides):
            yield finding("WSD005", "order", rid, groom=max(grooms), bride=min(brides))
        for side, slots in (("GROOM", grooms), ("BRIDE", brides)):
            if len(slots) > PER_SIDE_COLUMNS:
                yield finding("WSD006", f"too_many_{side.lower()}", rid, count=len(slots), columns=PER_SIDE_COLUMNS)


def wsd003(view: FileView) -> Iterator[Finding]:
    return only("WSD003", _advisory(view))


def wsd004(view: FileView) -> Iterator[Finding]:
    return only("WSD004", _advisory(view))


def wsd005(view: FileView) -> Iterator[Finding]:
    return only("WSD005", _advisory(view))


def wsd006(view: FileView) -> Iterator[Finding]:
    return only("WSD006", _advisory(view))


# --- ESC001-ESC004: the external cards ----------------------------------------------------------------

def _member(value: object) -> str | None:
    """`external_sources._enum_member_name`: the member name a `document_type` code ends in."""
    text = as_text(value)
    return text.rpartition(".")[2].upper() if text else None


def _cards(view: FileView) -> Iterator[tuple[Node, str, Node]]:
    """(record, verb, what the card's call wrote) of each criminal, WWI and WWII card."""
    for record in _records(view, "external_record"):
        verb = record["written"].get("verb")
        if verb in _EXTERNAL_VERBS:
            yield record, verb, view.written("external_record", record)


def _cards_found(view: FileView) -> Iterator[Finding]:
    """`external_sources.check_file_structured` over the cards a file holds."""
    for record, verb, written in _cards(view):
        rid = record["id"]
        if (url := as_text(written.get("source_url"))) is not None:
            hosts = _HOSTS[verb]
            if not any(h in url for h in hosts):
                expected = " or ".join(f"'{h}'" for h in hosts)
                yield finding("ESC001", "host", rid, expected=expected, func=verb, url=repr(url))
        if verb != "criminal_record":
            member = _member(written.get("document_type"))
            if "document_type" in written and "casualty_reason" in written:
                reason = as_text(written["casualty_reason"])
                if member in AWARD_MEMBER_NAMES and (reason is None or reason.strip()):
                    yield finding("ESC003", "award", rid, member=member)
            for name in ("award", "award_number"):      # «награда», «Номер награждения»: the catalog's
                if written.get(name) is not None and member not in AWARD_MEMBER_NAMES:
                    yield finding("ESC004", f"{name}_{'typed' if member is not None else 'untyped'}", rid,
                                  **({"member": member} if member is not None else {}))
        else:
            original = as_text(written.get("original_text"))
            if original is not None and not original.strip():
                yield finding("ESC002", "empty", rid)


def esc001(view: FileView) -> Iterator[Finding]:
    return only("ESC001", _cards_found(view))


def esc002(view: FileView) -> Iterator[Finding]:
    return only("ESC002", _cards_found(view))


def esc003(view: FileView) -> Iterator[Finding]:
    return only("ESC003", _cards_found(view))


def esc004(view: FileView) -> Iterator[Finding]:
    return only("ESC004", _cards_found(view))


# --- NLC001: a name list --------------------------------------------------------------------------------

def nlc001(view: FileView) -> Iterator[Finding]:
    """A name list with no `document_type`, or an entry whose age is an integer of nought or less
    (`name_lists._findings`): a text age such as "?" yields no birth event and is left alone."""
    for doc in view.documents():
        if doc.get("kind") != "name_list":
            continue
        written = doc["written"]
        document_type = written.get("document_type")
        if "document_type" in written and (document_type is None
                                           or (isinstance(document_type, str) and not document_type.strip())):
            yield finding("NLC001", "document_type", doc["id"])
    for _, record in view.records({"name_list"}):
        age = view.written("listed_person", record).get("age")
        if isinstance(age, int) and not isinstance(age, bool) and age <= 0:
            yield finding("NLC001", "age", record["id"], age=repr(age))


RULES: dict[str, Rule] = {
    "DRA001": dra001, "DRL001": drl001, "MRA001": mra001,
    "WSD001": wsd001, "WSD002": wsd002, "WSD003": wsd003, "WSD004": wsd004, "WSD005": wsd005, "WSD006": wsd006,
    "ESC001": esc001, "ESC002": esc002, "ESC003": esc003, "ESC004": esc004, "NLC001": nlc001,
}
