"""The Russian books' vocabulary of the records JSON (records v1 — its JSON names): every attribute of every
DSL class, in the order `vars()` shows it — the table the core's codec reads
(`verso.core.records.fields`), moved here verbatim before 0.1.0, with the two scalars the DSL's
strings may be (`status`, a `Status` keeping its gender, and `cause`, a `CauseOfDeath`).

One row per attribute: its name, its type and the value it holds when the call wrote
nothing and nothing derived it. A class or an attribute the table lacks is refused by the
encoder, so a new DSL field fails a test instead of going missing from the JSON — then
`python -m verso.core.records.schema --write`, and commit `records-v1.json` beside this file.
"""
from __future__ import annotations

from calendar import Month
from collections.abc import Callable
from typing import Any

from verso.ru.gender import Gender
from verso.core.records.fields import (
    ClassSpec, Field, ListOf, Numbering, Positional, Scalar, TypeSpec, Vocabulary, code, member_of, parse_fields)
from verso.ru.domain.cause_of_death import CauseOfDeath
from verso.ru.domain.event_date import EventDate
from verso.ru.domain.factories import person
from verso.ru.domain.person import Person
from verso.ru.domain.record_defaults import RecordDefaults
from verso.ru.domain.side import Side
from verso.ru.domain.status import Status
from verso.ru.dsl.records.births import Birth, BirthRecords, Christening, birth, birth_records, christening
from verso.ru.dsl.records.census import (
    CensusHousehold, CensusMember, CensusRecords, CensusRole, census_records, household, member)
from verso.ru.dsl.records.deaths import Death, DeathRecords, death, death_records
from verso.ru.dsl.records.divorces import Divorce, DivorceRecords, divorce, divorce_records
from verso.ru.dsl.records.external_sources import (
    ExternalSourceKind, ExternalSourceRecord, ExternalSourceRecords, SourceCitation, WwiDocumentType, WwiiDocumentType, criminal_record, external_source_records, wwi_record, wwii_record)
from verso.ru.dsl.records.marriages import Marriage, MarriageRecords, marriage, marriage_records
from verso.ru.dsl.records.name_lists import ListedPerson, NameListRecords, listed_person, name_list_records
from verso.ru.relationship import Relationship, Relative, relative


def _f(spec: str) -> tuple[Field, ...]:
    return parse_fields(spec, _TYPES)


_TYPES: dict[str, TypeSpec] = {
    "Gender": Gender, "Month": Month, "Side": Side, "Relationship": Relationship,
    "CensusRole": CensusRole, "Kind": ExternalSourceKind,
    "DocumentType": (WwiDocumentType, WwiiDocumentType),
    "EventDate": EventDate, "SourceCitation": SourceCitation, "RecordDefaults": RecordDefaults,
    "Relatives": ListOf(Relative), "Members": ListOf(CensusMember), "Households": ListOf(CensusHousehold),
    "Births": ListOf(Birth), "Marriages": ListOf(Marriage), "Deaths": ListOf(Death),
    "Divorces": ListOf(Divorce), "Entries": ListOf(ListedPerson), "Cards": ListOf(ExternalSourceRecord),
    "Strs": ListOf("str"),
}

_PERSON = _f("""name_orig:str name_modern:str='' patr_orig:str patr_old:str='' patr_modern:str=''
    last_name:str last_name_modern:str birth_last_name_modern:str last_name_in_book:bool=True
    residence:str status:status status_defaulted:bool=False gender:Gender comment:str
    occupation:str side:Side""")
_CLERGY = "priest:person deacon:person dyachok:person sexton:person"
_BIRTH = _f(f"""record_num:intstr reviewed:bool calendar_note:str source_date_error:str
    lag_note:str gender:Gender b_day:int b_month:Month k_day:int k_month:Month year:int k_year:int
    christening_age:int child:person father:person mother:person god_parent1:person
    god_parent2:person god_parent3:person god_parent4:person {_CLERGY} page:str inventory:str
    case:str book:str comment:str civil:bool=False relatives:Relatives=[]""")
_MARRIAGE = _f(f"""record_num:intstr reviewed:bool calendar_note:str source_kin_error:str
    age_note:str w_day:int w_month:Month groom:person bride:person groom_marriage_num:int
    bride_marriage_num:int groom_age:age bride_age:age witness1:person witness2:person
    witness3:person witness4:person witness5:person witness6:person page:str archive:str
    fund:str inventory:str case:str village:str church:str book:str comment:str {_CLERGY}
    relatives:Relatives=[] year:int bride_takes_groom_surname:bool=True civil:bool=False""")
_DEATH = _f(f"""record_num:intstr reviewed:bool source_date_error:str source_age_error:str
    namesake:str lag_note:str gender:Gender year:int d_day:int d_month:Month b_day:int b_month:Month
    deceased:person relatives:Relatives=[] witness1:person witness2:person {_CLERGY}
    cause_of_death:cause age:age page:str archive:str fund:str inventory:str case:str
    church:str book:str comment:str civil:bool=False""")
_DIVORCE = _f("""record_num:intstr reviewed:bool=True d_day:int d_month:Month husband:person wife:person
    husband_age:age wife_age:age marriage_date:str children:str initiator:str page:str case:str
    comment:str year:int""")
_MEMBER = _f("""number:int person:person role:CensusRole age:age ref_member:int
    marital_status:str occupation:str origin:str comment:str destination:str arrival_year:int
    departure_year:int arrival_reason:str departure_reason:str previous_age:age
    record_number:intstr birth_day:int birth_month:Month birth_year:int parent_member:int
    spouse_member:int source_age_error:str previous_age_error:str father_ref:str
    secondary_role:CensusRole secondary_ref_member:int hidden:bool=False""")
_HOUSEHOLD = _f("""page:str case:str comment:str reviewed:bool record_day:int record_month:Month
    family_id:intstr members:Members=[]""")
_BOOK = "archive:str fund:str inventory:str case:str village:str church:str year:int"
_CENSUS = _f("""archive:str fund:str inventory:str case:str village:str year:int document_type:str
    document_type_genitive:str district:str volost:str prev_revision_year:int record_day:int
    record_month:Month archive_suffix:str suffix_in_res_names:bool=False reviewed:bool=True
    household_label:str household_number_label:str file_prefix:str doc_res_prefix:str
    single_age_column:bool=False female_previous_age:bool record_type:str
    households:Households=[]""")
_NAME_LIST = _f("""archive:str fund:str inventory:str case:str village:str year:int
    document_type:str document_type_genitive:str district:str volost:str record_day:int
    record_month:Month scan_file:str source_url:str labels:Strs reviewed:bool=True
    household_order:bool=False entries:Entries=[]""")
_LISTED = _f("number:int person:person age:age comment:str reviewed:bool=True page:str index:int")
_CARD = _f("""person:person kind:Kind citation:SourceCitation record_number:intstr index:int age:age
    birth_year:int birth_date:EventDate date:EventDate page:str rank:str military_unit:str
    casualty_reason:str document_type:DocumentType award:str award_number:intstr
    marital_status:str place_of_casualty:str casualty_date:EventDate draft_board:str
    draft_date:EventDate feat_date:EventDate labels:Strs comment:str reviewed:bool=True""")
_CITATION = _f("""catalog:str source_url:str original_text:str bibliography:str archive:str fund:str
    inventory:str case:str archive_location:str scan_files:Strs=[] scan_file:str
    scan_content_type:str""")
_EVENT_DATE = _f("""year:int month:Month day:int year_end:int month_end:Month day_end:int
    circa:bool=False circa_end:bool=False date_range:str""")
_RECORD_DEFAULTS = _f("""residence:str status_male:status status_female:status status_bride:status
    status_groom:status status_mother:status cause_of_death:cause""")

SPECS: dict[type, ClassSpec] = {s.cls: s for s in (
    ClassSpec(Person, "person", _PERSON, (person,)),
    ClassSpec(Relative, "relative", _f("person:person relationship:Relationship relationship_ref:str"),
              (relative,)),
    ClassSpec(Birth, "birth", _BIRTH, (birth,)),
    ClassSpec(Christening, "christening", _BIRTH, (christening,)),
    ClassSpec(Marriage, "marriage", _MARRIAGE, (marriage,)),
    ClassSpec(Death, "death", _DEATH, (death,)),
    ClassSpec(Divorce, "divorce", _DIVORCE, (divorce,)),
    ClassSpec(CensusMember, "member", _MEMBER, (member,)),
    ClassSpec(CensusHousehold, "household", _HOUSEHOLD, (household,)),
    ClassSpec(ListedPerson, "listed_person", _LISTED, (listed_person,)),
    ClassSpec(ExternalSourceRecord, "external_record", _CARD,
              (criminal_record, wwi_record, wwii_record)),
    ClassSpec(BirthRecords, "births", _f(f"{_BOOK} records:Births reviewed:bool=True civil:bool=False"),
              (birth_records,), "records"),
    ClassSpec(MarriageRecords, "marriages", _f(f"{_BOOK} records:Marriages reviewed:bool=True civil:bool=False"),
              (marriage_records,), "records"),
    ClassSpec(DeathRecords, "deaths", _f(f"{_BOOK} records:Deaths reviewed:bool=True civil:bool=False"),
              (death_records,), "records"),
    ClassSpec(DivorceRecords, "divorces", _f(f"{_BOOK} records:Divorces reviewed:bool=True"), (divorce_records,), "records"),
    ClassSpec(CensusRecords, "census", _CENSUS, (census_records,), "households"),
    ClassSpec(NameListRecords, "name_list", _NAME_LIST, (name_list_records,), "entries"),
    ClassSpec(ExternalSourceRecords, "external_sources", _f("village:str records:Cards"),
              (external_source_records,), "records"),
    ClassSpec(SourceCitation, "source_citation", _CITATION),
    ClassSpec(EventDate, "event_date", _EVENT_DATE),
    ClassSpec(RecordDefaults, "record_defaults", _RECORD_DEFAULTS),
)}

#: The classes written whole as a value of a field, never as a node of their own.
VALUE_CLASSES: tuple[type, ...] = (SourceCitation, EventDate, RecordDefaults)

#: A factory parameter whose attribute is spelled otherwise.
PARAM_TO_ATTR: dict[type, dict[str, str]] = {
    Person: {"last_name_orig": "last_name", "name_modern_orth": "name_modern",
             "last_name_modern_orth": "last_name_modern",
             "birth_last_name_modern_orth": "birth_last_name_modern"},
    Christening: {"age": "christening_age"},
}

_CITATION_PARAMS = {name: "strs" if name == "scan_file" else "str" for name in (
    "source_url", "original_text", "bibliography", "archive", "fund", "inventory", "case",
    "archive_location", "scan_file", "scan_content_type")}

#: A factory parameter that sets no attribute of its own.
WRITTEN_ONLY: dict[tuple[type, str], TypeSpec] = {
    **{(cls, "defaults"): RecordDefaults for cls in (
        BirthRecords, MarriageRecords, DeathRecords, DivorceRecords, CensusRecords)},
    **{(ExternalSourceRecord, name): kind for name, kind in _CITATION_PARAMS.items()},
}

#: The list fields whose items each hold a person, and the role a person there takes.
ITEM_ROLES = {"relatives": "relative", "members": "member"}


def _status(text: str, gender: Gender | None) -> Status:
    """A `Status` as its constant built it, without the constructor's write to
    `Status._gender_registry`: that is the DSL file's own doing when it runs, and data
    read back must not give a gender to every later plain-string status of its words."""
    status = str.__new__(Status, text)
    status.gender = gender
    return status


def _decode_status(node: Any) -> Status:
    gender = node.get("gender")
    return _status(node["text"], None if gender is None else member_of(Gender, gender))  # type: ignore[arg-type]


STATUS = Scalar(
    "status", Status,
    encode=lambda value: {"text": str(value), "gender": None if value.gender is None else code(value.gender)},
    decode=_decode_status,
    same=lambda a, b: str(a) == str(b) and a.gender == getattr(b, "gender", None),
    schema=({"text": {"type": "string"}, "gender": {"enum": ["male", "female", None]}}, ["text", "gender"]))
CAUSE = Scalar(
    "cause", CauseOfDeath,
    encode=lambda value: {"text": str(value), "type": "cause"},
    decode=lambda node: CauseOfDeath(node["text"]),
    same=lambda a, b: a == b,
    schema=({"text": {"type": "string"}, "type": {"const": "cause"}}, ["text", "type"]))

_RECORD_DATE = {"record_day": "record.day", "record_month": "record.month"}
_BIRTH_KEYS = {"record_num": "number", "b_day": "birth.day", "b_month": "birth.month",
               "k_day": "baptism.day", "k_month": "baptism.month", "k_year": "baptism.year",
               "christening_age": "baptism.age"}

#: Records v1: the JSON key of a field named otherwise than its attribute. An event's day,
#: month and year are one object (`birth.day`), a name's forms are one (`given.original`), and no
#: abbreviation is left (`record_num` → `number`). What is not named keeps its name; a person's
#: slot has no key — it is a persona, named by its role.
JSON_NAMES: dict[type, dict[str, str]] = {
    Person: {"name_orig": "given.original", "name_modern": "given.modern",
             "patr_orig": "patronymic.original", "patr_old": "patronymic.old",
             "patr_modern": "patronymic.modern", "last_name": "surname.original",
             "last_name_modern": "surname.modern", "last_name_in_book": "surname.in_book",
             "birth_last_name_modern": "maiden_surname.modern"},
    Birth: _BIRTH_KEYS,
    Christening: _BIRTH_KEYS,
    Marriage: {"record_num": "number", "w_day": "marriage.day", "w_month": "marriage.month",
               "groom_marriage_num": "groom_marriage_number", "bride_marriage_num": "bride_marriage_number"},
    Death: {"record_num": "number", "d_day": "death.day", "d_month": "death.month",
            "b_day": "burial.day", "b_month": "burial.month"},
    Divorce: {"record_num": "number", "d_day": "divorce.day", "d_month": "divorce.month"},
    CensusMember: {"birth_day": "birth.day", "birth_month": "birth.month", "birth_year": "birth.year",
                   "arrival_year": "arrival.year", "arrival_reason": "arrival.reason", "origin": "arrival.place",
                   "departure_year": "departure.year", "departure_reason": "departure.reason",
                   "destination": "departure.place"},
    CensusHousehold: _RECORD_DATE,
    CensusRecords: _RECORD_DATE,
    NameListRecords: _RECORD_DATE,
}

#: What the wrappers set and no call writes: the month and year of a section
#: (`birth_month_year()` and its kin), the provenance, the day and the flag of a `page()`, the
#: name of a `book()`. Records v1.x writes each into `written` under its key when the call did not
#: write it, named in `written.context`; replay sets them on the record its factory built.
_WRAPPED = frozenset({"b_month", "k_month", "k_year", "d_month", "w_month", "year", "page", "case", "archive",
                      "fund", "inventory", "church", "record_day", "record_month", "reviewed", "book"})
CONTEXT: dict[type, frozenset[str]] = {
    cls: frozenset(f.name for f in spec.fields if f.name in _WRAPPED)
    for cls, spec in SPECS.items()
    if spec.records_attr is None and cls not in VALUE_CLASSES and cls not in (Person, Relative, CensusMember)}

#: Of those, what a wrapper keeps beside a call's own value of it (`verso.core.written.shadow`, records v1.x
#: `written.wrapper`): the leaf of a `page()`, the months and year of a `*_month(…)` / `*_month_year(…)` section.
_SHADOWED = frozenset({"page", "year", "b_month", "k_month", "d_month", "w_month"})
SHADOWED: dict[type, frozenset[str]] = {cls: names & _SHADOWED for cls, names in CONTEXT.items() if names & _SHADOWED}

#: The verbs of a class whose factories `written` cannot tell apart: a card is a criminal, a WWI
#: or a WWII one, and the three take the same keys. `written.verb` names the one that built it.
VERBS: dict[type, dict[str, Callable[..., object]]] = {
    ExternalSourceRecord: {"criminal_record": criminal_record, "wwi_record": wwi_record,
                           "wwii_record": wwii_record}}

# What a record holds that is its place in the set: a list's and a card's 1-based `index`, a roll's
# running № п/п over its members (a hidden member takes none — `census_records`' autonumbering).
POSITIONAL: dict[type, Positional] = {
    ListedPerson: Positional(index="index"),
    ExternalSourceRecord: Positional(index="index"),
    CensusHousehold: Positional(numbering=Numbering(items="members", attr="record_number", skipped="hidden")),
}

VOCABULARY = Vocabulary(specs=SPECS, value_classes=VALUE_CLASSES, param_to_attr=PARAM_TO_ATTR,
                        written_only=WRITTEN_ONLY, item_roles=ITEM_ROLES, person=Person,
                        scalars={"status": STATUS, "cause": CAUSE}, schema_package="verso.ru.records",
                        json_names=JSON_NAMES, context=CONTEXT, verbs=VERBS, shadowed=SHADOWED, positional=POSITIONAL)
