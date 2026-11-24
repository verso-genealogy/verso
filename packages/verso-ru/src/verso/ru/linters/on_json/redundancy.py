"""The rules on what a record inherits (class `derived`): the days a death's month block and year give it
(DBD001, DBD002), the arguments written equal to what a book's `RecordDefaults` would give (SLC003, SLC004,
SLC005, VSR001, CSR001), a record's `reviewed=` equal to its record set's (RVR001), and the arguments written
equal to what the family gives a person: a birth's residence and surname (BRD001-BRD006), a death's relative's
residence (DRA002), a roll member's surname, maiden name and patronymic (CRD001-CRD006).

A `derived` code reads two things the source shows together and the JSON keeps apart: what the call WROTE
(`FileView.written`) and what the record INHERITED. The inherited value is read from the object `replay_file`
builds from `written` alone (`FileView.replayed`): a death's month and year come from the section and the
book, as the DSL derives them; a book's `RecordDefaults` is the value `written.defaults` of its document
holds, whole. An export without `written.context` (before 0.1.16) is refused (`FileView.require_context`), as
every rule here asks.

**RVR001 answers what the export represents, and only that.** The check compares a `reviewed=` of a record, or of
a `page()`, with what would be inherited from the `page()` and the record set. Its variants:

* `inner_records_default` / `inner_records_set` — a record's own flag equal to the record set's (written by the set
  or its default `True`) with no flag on the page around it. Recoverable only for a record that stands in no
  `page()`: its flag is a key of its `written`, the set's value is the replayed set's `reviewed` ("set" when the
  document wrote it).
* `page_labelled_*`, `page_bare_*` — a `page()`'s flag equal to the set's: NOT recoverable. `page()` fills only a
  record whose flag is unset, so a page's flag that equals the set's, `True` or `False`, leaves nothing in the
  export; probed: with and without it the JSON is byte for byte the same.
* `inner_page_labelled` / `inner_page_bare` — a record's own flag equal to the page's: NOT recoverable. A record
  that wrote its own keeps nothing of the page's, and one that did not carries the value the page OR the set gave.

The export cannot show where a `page()` call begins and ends: the encoder merges consecutive records of one `page`
into one run, so a leaf spanning two `death_month` sections, or two `page()` calls of one label, is one run with
two flags in it, and `page(None, …)` is a run that looks page-less. A false RVR001 invites removing a flag, which
changes a record's review state, and a missed one is safe, so the walk ABSTAINS on every labelled run and answers a
run with no page only when at least one UNFLAGGED record of it shows the set's value, and none shows another: a
`page(None, reviewed=…)` over unflagged records would show its flag, so it cannot lie over them. An unflagged record
shows the flag its export holds — a wrapper's in `written`, else its kind's default (a divorce's, a name list's
entry's `True` is written nowhere) — never its replayed object's: a set's `False` would fill that object and hide a
`page(None, reviewed=True)` over it. A run whose records
all wrote their own flags tells nothing and is not answered. What stays is a `page(None, …)` whose records all
wrote flags, beside page-less records that wrote none (one run, one set's value shown): it is a call outside the
DSL's contract (the leaf number is a `str`; `""` is a leaf and labels its run), absent from the corpus, and the
walk reads its records as the set's. A finding of the walk is then an
`inner_records_*` of the check; what it does not say is a missed finding (a flag equal to the set's inside a page
that wrote none, or in a run of explicit flags alone). `tests/test_linters_on_json_samples.py` declares `page_*`,
`inner_page_*` and the `inner_records_*` found inside a `page()` call or in a page-less run of explicit flags absent on
JSON (`SOURCE_ONLY`), and `hosted.toml` says so in the note. What the check reads off the syntax and the walk reads
as values: a `reviewed=FLAG` held in a name makes the check skip the whole set (the walk reads the value), and a
record bound outside the set call is invisible to the check (the walk sees it in the set).

What the checks read off the SYNTAX alone has no JSON counterpart, and the walk answers on the values:

* a constant is its value. The checks compare the text of an expression, `status=PEASANT` with the name the
  book's `status_male=` writes. The JSON holds a status constant as `{text, gender}` and a cause of death as
  `{text, type}` (a literal is its text, and never equals a constant), so two names of one value are one value
  (the checks say two). The finding names the constant as the checks do, by the catalog's name of the text
  (`walk.status_name` for a status, `KNOWN_CAUSES` for a cause). The rule when several constants spell one text: the
  name that sorts LAST alphabetically (both tables are built over sorted names and the later one overwrites; SLC002
  names the same one), so `STATE_PEASANT_MALE` over `GOSUDARSTVENNYJ_PEASANT_MALE`. A constant the file defines itself
  is shown by its text.
* a name is its value. A `person` bound to a name and passed as `father=F` is no call to the checks, which skip
  it, and the walk reads it; so does the priest a `book()` hands every record, which is one finding per record here
  and none there. A residence, status or cause held in a module-level name is compared by SLC003-SLC005 as the
  identifier (`R = "Ротозеево"` in the defaults and in `person(residence=R)`: `value: "R"`) and by VSR001 as the
  expression; the walk compares and shows the value (`value: "Ротозеево"`).
* a keyword and a positional argument are one in `written`. The checks read a person's name by position (SLC005's
  gender of a witness) and its residence and status by keyword; the walk reads them by parameter, so a
  `person(name_orig="…")` is read by name here and ignored there, and a positional residence is read here. A
  `relative(person=…)` given by keyword is a relative here too; the checks look at the first argument.
* a book's `RecordDefaults` has no `_written`: `status_groom` is derived from `status_male` when the author
  wrote none, and the JSON cannot say which. VSR001 reads an equal pair as `status_groom` unwritten (the field it
  names is then `status_male`); an author who wrote the equal `status_groom` too is told `status_male`.
* the gender of a name comes from the names table. A workspace without one reads it as unknown
  (`walk.gender_from_name`): SLC005's check does the same, VSR001's would raise. Every code that reads a name says so
  in `hosted.toml` (`needs`), and `lint_records` answers a workspace without a table for all of them alike (H7: what
  they find without the table, at the level of a warning; the codes that replay the file, which builds its persons
  from the table, find nothing).
* a status the checks cannot resolve to words (a name no catalog holds, a call) keeps the newborn's parent
  (`newborn_status.UNKNOWN`); the JSON always has the words, so it answers where the source stays silent.
* DBD001 and DBD002 take the section of a `death_month()` from the objects, so a wrapper whose records are not
  its direct arguments (`death_month(M, *page(…))`) gives the walk a month the checks do not see.

**The family rules (BRD, DRA002, CRD, CSR001)** compare what a person's own call WROTE with what its family gives it,
and differ from the checks where the checks read the syntax:

* the form of an argument is not in the export (Д3). A keyword and a positional argument leave the same `written`
  (a positional call writes its skipped parameters as Nones; whether a keyword call skipped them by position is
  not a thing it can show), so BRD002, BRD004, CRD003 and CRD006 are the findings of BRD001, BRD003, CRD002 and
  CRD005 on JSON, in those codes' variants and params, and DRA002's `redundant_positional` (whose `val` the check
  quotes) is its `redundant`. `hosted.toml` says so (`as`, `forms`) and `hosted.fold` applies it: for `lint_records`
  (a positional code asks its keyword code's findings), the samples oracle and the corpus test.
* a family's surname is read off the objects, the person's own arguments off `written`. The father's modern
  surname (BRD) is what the DSL gave him, from the replay; a mother's, a child's or a relative's residence is what
  the call wrote, because the object holds the book's residence and the father's, and a child at the book's village
  says nothing of its family. `Birth.__init__` derives a daughter's surname from her mother's when the mother wrote
  one, else from the father's: the mother's written surname is what the walk compares, not the one the object
  inherited. A roll member's source (CRD) is read as the generator had it when it reached the member: its own written
  surname, or the one it derived (a son's from his father's, so a grandson's chains through him) only when it is
  listed BEFORE the member (`CensusHousehold.__init__` makes one pass in member order) and does not itself rest on the
  member (a grandson naming the son who names him: the son's surname is what the grandson derived from, and
  load-bearing). Otherwise the walk abstains, and so does the check, which reads the source alike
  (`census_redundancy._family_surname`): a member whose source is listed later and derives, a member naming itself, a
  circular pair. A daughter who writes a current surname of her own is given no maiden name, so the maiden name she
  writes is no repetition (CRD004) on either side.
* a keyword holding none is no keyword. A positional call writes `last_name_modern_orth=None` for a parameter it
  skipped, and the check reads that as absent (it reads the keyword alone); `last_name_modern_orth=None` written
  by keyword is a keyword to the check (a person with a surname it cannot read: no BRD rule runs for a father, BRD006
  stays quiet for a mother) and absent here, where the surname is the one `last_name_orig` gives. The walk answers
  in the cases where the check would say something false (a daughter's surname that equals the father's feminized,
  where her mother wrote another) or nothing. Likewise a modern surname given by POSITION (index 5): the checks read
  index 2 and 6 only, so the walk sees a surname the check does not (BRD006 and BRD003 differ both ways).
* `birth(1, gender=Gender.MALE, …)` by keyword: `_record_gender` reads the second positional argument, so the check
  says nothing of a child's surname; the walk reads the gender and finds a son's.
* the household's members are the personas the JSON holds (a `member()` built by a helper or a list is one here and
  none there), a person bound to a name is read, and a repeated member number takes the last member, as the checks'
  number map does.
* `person()` gender given by POSITION (index 8): the check's `_gender` reads the keyword alone (CSR001, CRD), the walk
  reads the gender written. Where the positional gender is the only thing that says the sex, the walk answers and the
  check is silent (the safe direction for a finding; a CSR001 may name a member the check left as sexless).
* DRA002 reads the relatives of a death as the JSON holds them; the check reads an `ast.List` of `relative()` calls
  alone, so relatives passed as a tuple or through a bound list are seen here and not there.
* the gender of a roll member comes from the names table as the check reads it (`gender_from_name`): a workspace
  without one reads it as unknown, as for SLC005.
* CSR001 compares the status as a value, as VSR001 does: two names of one status are one (the oracle's
  `CONSTANT_PARAMS`), a literal is not the constant of its text.
"""
from __future__ import annotations

from calendar import Month
from collections.abc import Collection, Iterator, Mapping
from typing import Any, cast

from verso.core.i18n import Message
from verso.core.records.fields import vocabulary
from verso.ru.domain.statuses import child_status_for
from verso.ru.gender import Gender
from verso.ru.linters.checks import deaths_burial_date as burial
from verso.ru.linters.checks.census_redundancy import (
    CHILDREN, DAUGHTERS, REQUIRE_REF, ROLE_GENDER_BY_NAME, SONS, SURNAME_ROLES, patronymic_tier)
from verso.ru.linters.checks.reviewed_redundancy import INNER_CALLS
from verso.ru.linters.checks.single_line_calls import (
    GENDER_AMBIGUOUS_ROLES, KNOWN_CAUSES, effective_default_status)
from verso.ru.linters.checks.status_redundancy import RELATIVE_SLOT, SLOTS, Slot
from verso.ru.linters.issue import Text
from verso.ru.linters.on_json.walk import (
    ADOPTED, FileView, Finding, Rule, as_int, as_text, finding, finding_of, gender_from_name, member_gender, member_name, only,
    personas, slot_of, status_name)
from verso.ru.messages import t
from verso.ru.naming import (
    derive_old_patronymic, derive_patronymic, feminize_surname, modernize_orthography)
from verso.ru.relationship import Relationship, gender_from_relationship

__all__ = ["RULES"]

type Node = Mapping[str, Any]

_VERB = {"births": "birth", "marriages": "marriage", "deaths": "death"}      # a record set's kind, its record's


# --- DBD001, DBD002: the two dates of a death ---------------------------------------------------------

def _side(written: Node, day: object, month: Month | None, key: str) -> burial.Side:
    """One of the death's two dates as the DSL resolved it: its day (none for 0, the corpus's empty
    column), the month the section gave, and whether the call wrote the month itself (`d_month=None` is not)."""
    return burial.Side(as_int(day) or None, month.value if month is not None else None, written.get(key) is not None)


def _dates(view: FileView) -> Iterator[Finding]:
    """`deaths_burial_date._check_death` for each burial: an impossible day, else a burial before the death,
    on the effective months and year the objects hold, and the book's `civil` flag."""
    for doc, record in view.records({"deaths"}):
        written = view.written("death", record)
        if written.get("source_date_error"):             # the book contradicts itself: declared, nothing to fix
            continue
        built = view.object_of(record)
        year = as_int(built.year) or as_int(view.set_of(doc).year)
        death = _side(written, built.d_day, built.d_month, "d_month")
        buried = _side(written, built.b_day, built.b_month, "b_month")
        messages = burial.impossible_days(death, buried, year)
        if not messages:
            order = burial.burial_before_death(death, buried, year, built.civil is True)
            messages = [order] if order else []
        for message in messages:
            yield finding_of(cast(Text, message["message"]), record["id"])


def dbd001(view: FileView) -> Iterator[Finding]:
    return only("DBD001", _dates(view))


def dbd002(view: FileView) -> Iterator[Finding]:
    return only("DBD002", _dates(view))


# --- the book's defaults and a person's slot ----------------------------------------------------------

def _books(view: FileView) -> Iterator[tuple[Node, str, Node, Node]]:
    """(document, verb, defaults, record) of each birth, marriage and death of a book that sets defaults. A
    christening is no birth to these checks; a book with no `RecordDefaults` (or an empty one) has nothing to
    repeat. An export without `written.context` is refused."""
    view.require_context()
    for doc, record in view.records(_VERB):
        verb = _VERB[doc["kind"]]
        defaults = doc.get("written", {}).get("defaults")
        if record["kind"] == verb and defaults:
            yield doc, verb, defaults, record


def _shown(value: object) -> str:
    """What the finding calls a value, as the check does: a constant's name, a literal's text. The JSON holds a
    status as `{text, gender}` and a cause of death as `{text, type}` when the source wrote a constant, and the
    text itself when it wrote a literal."""
    if isinstance(value, Mapping):
        text = str(value.get("text", ""))
        if value.get("type") == "cause":
            return KNOWN_CAUSES.get(text, text)
        gender = value.get("gender")
        return status_name(text, gender if isinstance(gender, str) else None)
    return str(value)


def _redundant(view: FileView, statuses: bool = True) -> Iterator[Finding]:
    """`single_line_calls.Checker._check_redundant_defaults` for each record of a book with defaults. The status a
    person's slot would get may need a name's sex (`statuses`); SLC003 and SLC004, which read none, do not ask."""
    for _, verb, defaults, record in _books(view):
        rid = record["id"]
        wrote = view.written(verb, record)
        cause = wrote.get("cause_of_death")
        if cause is not None and "cause_of_death" in defaults and cause == defaults["cause_of_death"]:
            yield finding("SLC003", "default", rid, value=_shown(cause))
        slots: list[tuple[Node, Mapping[str, Any], str, Any]] = []
        for persona in personas(record):
            if persona["role"] == "relative":           # only a residence is compared for a relative
                written = view.written("person", persona)
                yield from _residence(rid, written, defaults)
                continue
            written = view.written("person", persona)
            slot = slot_of(record, persona)
            slots.append((persona, written, slot, _effective_status(written, slot, defaults) if statuses else None))
        repeated = {p["id"] for p, w, _, effective in slots
                    if effective is not None and w.get("status") is not None and w["status"] == effective}
        kept = _kept_parent(view, record, repeated)
        for persona, written, slot, effective in slots:
            yield from _residence(rid, written, defaults)
            keep = persona["id"] == kept or (slot == "deceased" and _derives_status(view, record))
            status = written.get("status")
            if status is not None and effective is not None and not keep and status == effective:
                yield finding("SLC005", "default", rid, value=_shown(status))


def _residence(rid: str, written: Mapping[str, Any], defaults: Node) -> Iterator[Finding]:
    residence = written.get("residence")
    if residence is not None and "residence" in defaults and residence == defaults["residence"]:
        yield finding("SLC004", "default", rid, value=_shown(residence))


def _effective_status(written: Mapping[str, Any], slot: str, defaults: Node) -> Any:
    """The status a person of this slot would get from the book (`_effective_default_status`), for a slot that
    may be either sex the one of the person's first name (`_role_default_status`)."""
    effective = effective_default_status(slot, cast(dict[str, str], dict(defaults)))
    if slot in GENDER_AMBIGUOUS_ROLES and (name := as_text(written.get("name_orig"))):
        gender = gender_from_name(modernize_orthography(name))
        if gender is not None:
            return defaults.get("status_female") if gender == Gender.FEMALE else defaults.get("status_male")
    return effective


def slc003(view: FileView) -> Iterator[Finding]:
    return only("SLC003", _redundant(view, statuses=False))


def slc004(view: FileView) -> Iterator[Finding]:
    return only("SLC004", _redundant(view, statuses=False))


def slc005(view: FileView) -> Iterator[Finding]:
    return only("SLC005", _redundant(view))


# --- the newborn's status: which parent's written status it rests on ---------------------------------------

class _Unknown:
    """A status that gives no words, or a record with no gender: it may derive anything."""


_UNKNOWN = _Unknown()


def _status_words(written: Mapping[str, Any]) -> str | None:
    status = written.get("status")
    if isinstance(status, Mapping):
        status = status.get("text")
    return status if isinstance(status, str) else None


def _chain(view: FileView, record: Node) -> tuple[Node | None, list[Node]]:
    """`newborn_status._chain`: the newborn (or the deceased) and the parents it may derive from, in the order
    its record's `__init__` consults them."""
    if record["kind"] == "birth":
        parents = [first for role in ("father", "mother") if (first := next(iter(personas(record, role)), None))]
        return next(iter(personas(record, "child")), None), parents
    if record["kind"] == "death":
        relatives = personas(record, "relative")

        def kin(name: str) -> list[Node]:
            return [r for r in relatives if str(view.written("relative", r["link"]).get("relationship")).upper() == name]
        return next(iter(personas(record, "deceased")), None), kin("FATHER") + kin("MOTHER")
    return None, []


def _derived(view: FileView, record: Node, source: Node | None) -> str | _Unknown | None:
    """`newborn_status._derived`: what `child_status_for` gives the newborn from `source`'s written status."""
    if source is None:
        return None
    words = _status_words(view.written("person", source))
    spelled = view.written(record["kind"], record).get("gender")
    gender = Gender.__members__.get(spelled.upper()) if isinstance(spelled, str) else None
    if words is None or gender is None:
        return _UNKNOWN
    derived = child_status_for(words, gender)
    return str(derived) if derived is not None else None


def _has_status(view: FileView, persona: Node) -> bool:
    return "status" in view.written("person", persona)


def _kept_parent(view: FileView, record: Node, redundant: Collection[str]) -> str | None:
    """`newborn_status.load_bearing_parent`: the id of the parent whose written status must stay although it
    repeats the book's default, because the newborn's own derives from it."""
    child, parents = _chain(view, record)
    if child is None or _has_status(view, child):
        return None
    written = [p for p in parents if _has_status(view, p)]
    if not written or written[0]["id"] not in redundant:
        return None
    remaining = (p for p in written if p["id"] not in redundant)
    before = _derived(view, record, written[0])
    after = _derived(view, record, next(remaining, None))
    if isinstance(before, _Unknown) or isinstance(after, _Unknown) or before != after:
        return written[0]["id"]
    return None


def _derives_status(view: FileView, record: Node) -> bool:
    """`newborn_status.derives_status`: whether the newborn (or the deceased) would take a status derived from a
    parent's were its own not written."""
    _, parents = _chain(view, record)
    source = next((p for p in parents if _has_status(view, p)), None)
    return _derived(view, record, source) is not None


# --- VSR001: a status written equal to the book's default for its slot ---------------------------------------

def _person_gender(written: Mapping[str, Any]) -> str | None:
    """`status_redundancy._person_gender`: the gender written, else the name's, before any default applies."""
    explicit = written.get("gender")
    if isinstance(explicit, str) and explicit:
        return explicit.upper()
    name = as_text(written.get("name_modern_orth")) or as_text(written.get("name_orig"))
    inferred = gender_from_name(name) if name else None
    return inferred.name if inferred is not None else None


def _relative_gender(view: FileView, relative: Node) -> str | None:
    """`status_redundancy._relative_gender`: the gender the relationship implies."""
    name = as_text(view.written("relative", relative["link"]).get("relationship"))
    try:
        implied = gender_from_relationship(Relationship[name.upper()]) if name else None
    except KeyError:
        return None
    return implied.name if implied is not None else None


def _effective_default(slot: Slot, gender: str | None, defaults: Node) -> tuple[Any, str]:
    """`status_redundancy._effective_default`: the status this person would inherit with no `status=`, and the
    `RecordDefaults` field that gives it. `status_groom` equal to `status_male` is the one `RecordDefaults`
    derives, not one written."""
    dedicated = defaults.get(slot.dedicated_default) if slot.dedicated_default else None
    if slot.dedicated_default == "status_groom" and dedicated == defaults.get("status_male"):
        dedicated = None
    if dedicated is not None and slot.dedicated_default is not None:
        return dedicated, slot.dedicated_default
    female = defaults.get("status_female")
    if gender == Gender.FEMALE.name and female is not None:
        return female, "status_female"
    return defaults.get("status_male"), "status_male"


def _expression(value: object) -> str:
    """The text the check puts in `status=`: the source of the expression that wrote the status — a constant's
    name, or a literal as Python writes it."""
    if isinstance(value, Mapping):
        return _shown(value)
    return repr(value)


def vsr001(view: FileView) -> Iterator[Finding]:
    """A person's `status=` that repeats what the book's `RecordDefaults` would give its slot
    (`status_redundancy._collect`), but for the parent a newborn's status rests on."""
    for _, verb, defaults, record in _books(view):
        by_slot = {slot_of(record, p): p for p in personas(record) if p["role"] != "relative"}
        slots: list[tuple[Node, Slot, str | None]] = []
        for slot in SLOTS.get(verb, ()):
            if (persona := by_slot.get(slot.kwarg)) is not None:
                slots.append((persona, slot, slot.gender_fallback))
        slots.extend((rel, RELATIVE_SLOT, _relative_gender(view, rel)) for rel in personas(record, "relative"))
        repeated: list[tuple[Node, Slot, Any, str]] = []
        for persona, slot, fallback in slots:
            written = view.written("person", persona)
            explicit = written.get("status")
            if explicit is None:
                continue
            effective, field = _effective_default(slot, _person_gender(written) or fallback, defaults)
            if effective is not None and explicit == effective:
                repeated.append((persona, slot, explicit, field))
        kept = _kept_parent(view, record, {p["id"] for p, *_ in repeated})
        for persona, slot, explicit, field in repeated:
            if persona["id"] != kept:
                yield finding("VSR001", "redundant", record["id"], status=_expression(explicit), slot=slot.kwarg,
                              verb=verb, field=field)


# --- RVR001: a record's reviewed= that restates the record set's -----------------------------------------------

_SET_CALL = {"births": "birth_records", "marriages": "marriage_records", "deaths": "death_records",
             "census": "census_records", "name_list": "name_list_records",
             "divorces": "divorce_records"}     # the set's kind, the call that wrote it


def review_level(node: Mapping[str, Any], built: Any) -> Any:
    """The `reviewed` a record node that wrote no flag of its own shows, `built` the record replayed from it: a
    wrapper's in `written` (`written.context`), else its kind's default when the kind has one — a divorce's, a name
    list's entry's `True` is written nowhere, so the replayed record, filled by its set, may not hold it — else the
    replayed record's. RVR001 reads a run's levels so, and a store gives `lint_record` its `run_levels` so."""
    if "reviewed" in node["written"]:
        return node["written"]["reviewed"]
    voc = vocabulary()
    default = voc.specs[voc.by_code[node["kind"]]].field("reviewed").default
    return default if isinstance(default, bool) else built.reviewed


def rvr001(view: FileView) -> Iterator[Finding]:
    """A record's own `reviewed=` equal to the record set's (`reviewed_redundancy._inner_issue`, `inner_records_*`)
    in a run with no page that holds an unflagged record, every unflagged record carrying the set's value. A
    labelled run is not answered: the export cannot show the boundaries of the `page()` calls it was merged from
    (see above)."""
    view.require_context()
    for doc in view.documents():
        call = _SET_CALL.get(doc.get("kind", ""))
        if call is None:
            continue
        stated = "reviewed" in doc.get("written", {})
        level = view.set_of(doc).reviewed
        for run in doc.get("pages", ()):
            if run["page"] is not None:
                continue
            wrote = [(r, view.written(r["kind"], r)) for r in run["records"]]
            shown = {review_level(r, view.object_of(r)) for r, written in wrote if "reviewed" not in written}
            shown |= view.run_mates(run)
            if shown != {level}:        # nothing shown (all flagged), or a flag from elsewhere: `page(None, reviewed=…)`
                continue
            for record, written in wrote:
                flag = written.get("reviewed")
                if record["kind"] in INNER_CALLS and isinstance(flag, bool) and flag == level:
                    yield finding("RVR001", "inner_records_" + ("set" if stated else "default"), record["id"],
                                  value=str(flag), func=record["kind"], effective=str(level), records=call)

# --- BRD001-BRD006: what a birth's persons repeat of the family --------------------------------------------

def _eff_modern(written: Mapping[str, Any]) -> str | None:
    """`birth_redundancy._effective_modern`: the modern surname a person writes, the modern kwarg else the
    modernized old one. A kwarg holding none is no kwarg (a positional call writes its skipped parameters as none)."""
    modern = as_text(written.get("last_name_modern_orth"))
    if modern is not None:
        return modern
    orig = as_text(written.get("last_name_orig"))
    return modernize_orthography(orig) if orig is not None else None


def _surname_findings(rid: str, written: Mapping[str, Any], derived: str, role: str) -> Iterator[Finding]:
    """`birth_redundancy._redundancy_issues`: the three coupled findings on a person who writes
    `last_name_in_book=False` beside the surname the record derives (BRD003 the old one, BRD005 the modern one
    alone, BRD006 none at all). The positional form of BRD003 is BRD004, which the export cannot tell."""
    if not derived or written.get("last_name_in_book") is not False:
        return
    orig = as_text(written.get("last_name_orig"))
    modern = as_text(written.get("last_name_modern_orth"))
    eff = _eff_modern(written)
    if orig is not None and eff == derived:
        yield finding("BRD003", "surname", rid, orig_val=orig, role=role)
    elif orig is None and modern is not None and eff == derived:
        yield finding("BRD005", "modern_surname", rid, eff=eff, role=role)
    elif orig is None and modern is None:
        yield finding("BRD006", "in_book", rid, role=role)


def _residence_findings(rid: str, written: Mapping[str, Any], derived: str | None, reason: Message) -> Iterator[Finding]:
    """`birth_redundancy._residence_issues`: a residence written equal to the family's (BRD001; BRD002 by position)."""
    residence = as_text(written.get("residence"))
    if derived and residence is not None and residence == derived:
        yield finding("BRD001", "residence", rid, val=residence, reason=reason)


def _births(view: FileView) -> Iterator[Finding]:
    """`birth_redundancy._collect` for each birth. The family's surname is the father's as the DSL gave it (the
    replayed object); what a person WROTE is read from `written`, never from the object, which holds the book's
    residence and the surname `Birth.__init__` inherited: a mother's residence the object calls hers is the father's
    or the book's, and `_residence_value` compares what the mother's own call said."""
    view.require_context()
    for _, record in view.records({"births"}):
        if record["kind"] != "birth":
            continue
        rid = record["id"]
        built = view.object_of(record)
        slots = {role: next(iter(personas(record, role)), None) for role in ("father", "mother", "child")}
        wrote = {role: view.written("person", p) if p is not None else None for role, p in slots.items()}
        father, mother, child = wrote["father"], wrote["mother"], wrote["child"]
        family = built.father.last_name_modern if father is not None else None
        if family:
            if mother is not None:
                yield from _surname_findings(rid, mother, feminize_surname(family), "mother")
            if child is not None:
                gender = as_text(view.written("birth", record).get("gender"))
                if gender == "male":
                    yield from _surname_findings(rid, child, family, "son")
                elif gender == "female":
                    derived = (_eff_modern(mother) if mother is not None else None) or feminize_surname(family)
                    yield from _surname_findings(rid, child, derived, "daughter")
        father_res = as_text(father.get("residence")) if father is not None else None
        mother_res = as_text(mother.get("residence")) if mother is not None else None
        if mother is not None and father_res:
            yield from _residence_findings(rid, mother, father_res, t("birth.mother_at_father"))
        if child is not None:
            yield from _residence_findings(rid, child, father_res or mother_res, t("birth.child_at_family"))


def brd001(view: FileView) -> Iterator[Finding]:
    return only("BRD001", _births(view))


def brd003(view: FileView) -> Iterator[Finding]:
    return only("BRD003", _births(view))


def brd005(view: FileView) -> Iterator[Finding]:
    return only("BRD005", _births(view))


def brd006(view: FileView) -> Iterator[Finding]:
    return only("BRD006", _births(view))


# --- DRA002: a relative's residence repeating the deceased's -------------------------------------------------

def dra002(view: FileView) -> Iterator[Finding]:
    """A relative's written residence equal to the deceased's (`deaths_residence._check_death`, DRA002), the
    deceased's own being written (an empty one is an anchor, and no relative repeats it). A relative-only residence is
    the anchor the deceased inherits; one that differs is DRA001's, and silences the record: `Death.__init__` gives a
    relative without a residence the FIRST relative's that states one, so a repeated residence removed there could
    take another relative's village. Read from `written`: `Death.__init__` and the book fill the residences in, and
    the object cannot say which the call wrote."""
    for _, record in view.records({"deaths"}):
        if record["kind"] != "death":
            continue
        deceased = next(iter(personas(record, "deceased")), None)
        anchor = as_text(view.written("person", deceased).get("residence")) if deceased is not None else None
        if anchor is None:
            continue
        values = [as_text(view.written("person", rel).get("residence")) for rel in personas(record, "relative")]
        if any(value and value != anchor for value in values):
            continue
        for value in values:
            if value and value == anchor:
                yield finding("DRA002", "redundant", record["id"], val=value)


# --- CRD001-CRD006, CSR001: what a roll member repeats of its household -----------------------------------------

_FEMALE, _MALE = Gender.FEMALE.name, Gender.MALE.name


class _Line:
    """A roll member as `census_redundancy._Member` has it: its `member()` call and `person()` as they were
    written, the role's name, and the member the replay built (the surname and name the DSL gave it)."""

    def __init__(self, view: FileView, persona: Node, built: Any, index: int = 0) -> None:
        link = view.written("member", persona["link"])
        self.id = persona["id"]
        self.index = index
        self.person = view.written("person", persona)
        self.built = built
        self.number = as_int(link.get("number"))
        self.role = (as_text(link.get("role")) or "").upper() or None
        self.ref = as_int(link.get("ref_member"))
        self.comment = as_text(link.get("comment"))
        self.hidden = link.get("hidden") is True

    @property
    def own_surname(self) -> bool:
        """Whether the call wrote a current surname (`CensusHousehold.__init__`: `p.last_name or p.last_name_modern`),
        which the generator leaves as it is and every member naming this one reads at once."""
        return bool(as_text(self.person.get("last_name_orig")) or as_text(self.person.get("last_name_modern_orth")))

    @property
    def adopted(self) -> bool:
        return bool(self.comment and ADOPTED in self.comment.lower())

    @property
    def name(self) -> str | None:
        """`census_redundancy._name_modern`: the modern first name written, else the old one modernized."""
        return member_name(self.person)

    @property
    def gender(self) -> str | None:
        """`census_redundancy._gender`: the gender written, else the role's, else the first name's."""
        return member_gender(self.person, self.role)


def _lines(view: FileView, record: Node) -> list[_Line]:
    return [_Line(view, p, m, i)
            for i, (p, m) in enumerate(zip(personas(record, "member"), view.object_of(record).members, strict=True))]


def _source(m: _Line, head: _Line | None, by_number: Mapping[int | None, _Line]) -> _Line | None:
    """`census_redundancy._resolve_source`: the member the reference names, else the head, but for a role that
    must name one."""
    if m.ref is not None:
        return by_number.get(m.ref)
    return None if m.role in REQUIRE_REF else head


def _family_surname(m: _Line, source: _Line, head: _Line | None, by_number: Mapping[int | None, _Line]) -> str | None:
    """The surname `source` had when `CensusHousehold.__init__` reached `m`, which is what `m` would be given were its
    own not written. The generator makes ONE pass in member order: a source that wrote a surname has it at once; one
    that derived its own has it only if listed BEFORE `m`; and if its derivation rests on `m` (it names `m`, or a
    member that does), `m`'s surname is what it derived from, so the value is circular and `m`'s is load-bearing.
    The replayed object holds the final value; the order and the chain say whether `m` could have had it."""
    if source is m or (not source.own_surname and source.index > m.index):
        return None
    node: _Line | None = source
    seen: set[int] = set()
    while node is not None and not node.own_surname:
        if node.index in seen:
            return None
        seen.add(node.index)
        node = _source(node, head, by_number)
        if node is m:
            return None
    return source.built.person.last_name_modern or None


def _surnames(rid: str, m: _Line, derived: str) -> Iterator[Finding]:
    """`census_redundancy._surname_issues`: an explicit current surname equal to the household's (CRD001 the modern
    one, CRD002 the old one; CRD003 is the old one by position)."""
    suffix = t("census.surname_matches_head", role=(m.role or "").lower())
    if as_text(m.person.get("last_name_modern_orth")) == derived:
        yield finding("CRD001", "modern_surname", rid, derived=derived, suffix=suffix)
        return
    orig = as_text(m.person.get("last_name_orig"))
    if orig is not None and modernize_orthography(orig) == derived:
        yield finding("CRD002", "surname_orig", rid, orig_val=orig, suffix=suffix)


def _patronymics(rid: str, m: _Line, source: _Line) -> Iterator[Finding]:
    """`census_redundancy._patronymic_issue`: an explicit child patronymic equal to the one the father's first name
    gives (CRD005; CRD006 by position). The advisory tail marks the one that drops the pre-reform spelling."""
    parent = source.name
    if not parent or m.role not in ROLE_GENDER_BY_NAME:
        return
    child_gender = ROLE_GENDER_BY_NAME[m.role]
    # `derive_patronymic` reads the names table without `without_names`, on purpose: this is reached only after
    # `view.object_of` has replayed the file, which raises `NoReplay` first in a workspace without a table. Do not
    # move the lookup ahead of the replay.
    gen_modern = derive_patronymic(parent, child_gender)
    gen_orig = derive_old_patronymic(parent, child_gender) or gen_modern
    if not gen_orig or gen_orig == "?" or not gen_modern or gen_modern == "?":
        return
    explicit = as_text(m.person.get("patr_orig"))
    tier = patronymic_tier(explicit, gen_orig, gen_modern) if explicit is not None else None
    if explicit is not None and tier is not None:
        yield finding("CRD005", "patronymic_orig", rid, val=explicit, role=(m.role or "").lower(),
                      adv=t("census.patronymic_advisory") if tier == "modernize" else "")


def _roll(view: FileView) -> Iterator[Finding]:
    """`census_redundancy._collect` for each household: the surname, the daughter's maiden name and the patronymic a
    member writes beside what its head, husband or father gives it. The family's surname is the source member's
    as the generator had it when it reached the member (`_family_surname`: the replayed object, in member order);
    the source's gender and first name are the check's, from what the source wrote."""
    for _, record in view.records({"census"}):
        if record["kind"] != "household":
            continue
        lines = _lines(view, record)
        by_number = {m.number: m for m in lines}
        head = next((m for m in lines if m.role == "HEAD"), None)
        for m in lines:
            if m.hidden or m.adopted:
                continue
            source = _source(m, head, by_number) if m.role in SURNAME_ROLES or m.role in CHILDREN else None
            if source is None:
                continue
            if m.role in SURNAME_ROLES and source.gender != _FEMALE and (family := _family_surname(m, source, head, by_number)):
                derived = family if m.role in SONS else feminize_surname(family)
                yield from _surnames(record["id"], m, derived)
                # A daughter who writes a current surname is given no maiden name: hers is load-bearing.
                if (m.role in DAUGHTERS and not m.own_surname
                        and as_text(m.person.get("birth_last_name_modern_orth")) == derived):
                    yield finding("CRD004", "modern_birth_surname", record["id"], derived=derived)
            if m.role in CHILDREN and source.gender == _MALE:
                yield from _patronymics(record["id"], m, source)


def crd001(view: FileView) -> Iterator[Finding]:
    return only("CRD001", _roll(view))


def crd002(view: FileView) -> Iterator[Finding]:
    return only("CRD002", _roll(view))


def crd004(view: FileView) -> Iterator[Finding]:
    return only("CRD004", _roll(view))


def crd005(view: FileView) -> Iterator[Finding]:
    return only("CRD005", _roll(view))


def csr001(view: FileView) -> Iterator[Finding]:
    """A member's `status=` equal to what the roll's `RecordDefaults` would give it
    (`census_status_redundancy._collect`): the female default for a woman where the book has one, else the male
    default; a member whose sex nothing says, and a hidden one, are left (the status may be what tells the sex)."""
    view.require_context()
    for doc, record in view.records({"census"}):
        defaults = doc.get("written", {}).get("defaults") or {}
        male, female = defaults.get("status_male"), defaults.get("status_female")
        if male is None and female is None:
            continue
        for persona in personas(record, "member"):
            link = view.written("member", persona["link"])
            explicit = view.written("person", persona).get("status")
            if link.get("hidden") is True or explicit is None:
                continue
            line = _Line(view, persona, None)
            gender = line.gender
            if gender is None:
                continue
            effective, field = (female, "status_female") if gender == _FEMALE and female is not None else (male, "status_male")
            if effective is not None and explicit == effective:
                yield finding("CSR001", "redundant", record["id"], status=_expression(explicit),
                              role=line.role.lower() if line.role else "member", field=field)


RULES: dict[str, Rule] = {
    "BRD001": brd001, "BRD003": brd003, "BRD005": brd005, "BRD006": brd006, "CRD001": crd001, "CRD002": crd002,
    "CRD004": crd004, "CRD005": crd005, "CSR001": csr001, "DBD001": dbd001, "DBD002": dbd002, "DRA002": dra002,
    "RVR001": rvr001, "SLC003": slc003, "SLC004": slc004, "SLC005": slc005, "VSR001": vsr001,
}
