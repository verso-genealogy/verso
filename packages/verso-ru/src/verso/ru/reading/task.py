"""The task of reading one record: the prompt, the answer's schema, the card and the task line.

The prompt of a group is the common rules and the group's, the same for every model. The answer
is JSON under a closed schema; the record's field names are the DSL's, and a person is a slot
family and the fields a scorer compares. A change of a prompt or a schema changes what a model
answers: it is made on purpose, with a new measurement, and `tests/ru/reading` holds their hash.

A household member's `of` («чей») is read by `of_targets`, by one rule: when no member has a written `number`,
`of` is the 1-based place of the member in `persons`; otherwise it is a member's `number`. An `of` that names
the head of the household, oneself or no member at all is no link (`None`) — never a guess; a household where only
some members are numbered is read by numbers, so an `of` naming an unnumbered member names nobody. A «?» on the
`of` («2?») is taken off and reported as `doubtful`.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

_CLERGY = ("priest", "deacon", "dyachok", "sexton")
FAMILIES: Mapping[str, tuple[str, ...]] = {
    "births": ("child", "father", "mother", "godparent", "relative", *_CLERGY),
    "marriages": ("groom", "bride", "witness", "relative", *_CLERGY),
    "deaths": ("deceased", "relative", "witness", *_CLERGY),
    "census": ("member",),
}
RECORD_FIELDS: Mapping[str, tuple[str, ...]] = {
    "births": ("record_num", "gender", "b_day", "b_month", "k_day", "k_month", "age"),
    "marriages": ("record_num", "w_day", "w_month", "groom_age", "bride_age", "groom_marriage_num",
                  "bride_marriage_num"),
    "deaths": ("record_num", "gender", "d_day", "d_month", "b_day", "b_month", "age", "cause_of_death"),
    "census": ("family_id",),
}
CARD_KEYS = ("village", "parish", "year", "kind", "folio", "part")
_CARD_LABELS = {"village": "Село", "parish": "Приход", "year": "Год", "kind": "Вид записи", "folio": "Лист",
                "part": "Часть книги"}
_PERSON_FIELDS = ("number", "name", "patronymic", "surname", "status", "residence", "role", "of", "age",
                  "previous_age", "departure_year", "departure_reason")
#: The fields only a household member has: a metric book names no one's «whose» and no departure.
_CENSUS_ONLY = ("previous_age", "role", "of", "departure_year", "departure_reason")
#: The kind of a household's list, the word the context card's `kind` carries.
CARD_KINDS: Mapping[str, str] = {"revision": "ревизская сказка", "confession": "исповедная роспись"}
#: What a relative is to the person they hang off, as records v1 codes it (`written_relative.relationship`;
#: a test keeps the two equal).
RELATIONSHIPS = ("father", "mother", "husband", "wife", "son", "daughter", "father_in_law", "mother_in_law",
                 "son_in_law", "daughter_in_law", "foster_father", "foster_mother", "step_mother", "step_father")
#: The party a relative hangs off, by group, as the ui-hints' `relationship_ref` choices name them (a test
#: keeps the two equal). Null is the record's main person. A death has one party, so no choice.
RELATIONSHIP_OF: Mapping[str, tuple[str, ...]] = {
    "births": ("mother", "godparent"),
    "marriages": ("groom", "bride", "witness"),
}
#: Of those, the parties that are numbered, with how many a record can name: «witness 2» is a choice of
#: `relationship_of`. A test ties the roles to the ui-hints' choices whose word has `{n}` and the counts to
#: records-v1's `god_parentN` and `witnessN`.
NUMBERED_PARTIES: Mapping[str, int] = {"godparent": 4, "witness": 6}
TASK_LINE = "Прочитай запись на снимке и верни её поля в JSON по схеме."

#: The census roles as the records JSON codes them, with the source's word for each: the DSL's
#: `CensusRole` (a test keeps the two equal; this module imports nothing of verso).
CENSUS_ROLES: Mapping[str, str] = {
    "head": "хозяин", "wife": "жена", "husband": "муж", "son": "сын", "daughter": "дочь", "brother": "брат",
    "uncle": "дядя", "grandson": "внук", "granddaughter": "внучка", "daughter_in_law": "невестка",
    "son_in_law": "зять", "brother_in_law": "шурин", "stepson": "пасынок", "nephew": "племянник",
    "niece": "племянница", "cousin": "двоюродный брат", "mother": "мать", "father": "отец", "sister": "сестра",
    "stepdaughter": "падчерица", "lodger": "прохожий", "stepbrother": "сводный брат",
    "foster_son": "приёмный сын", "foster_daughter": "приёмная дочь",
}


def prompt_text(name: str) -> str:
    """One prompt file of the package, by its name: `common.md`, `births.md`, `marking.md`…"""
    return resources.files("verso.ru.reading").joinpath("prompts", name).read_text(encoding="utf-8")


def system_prompt(group: str, *, priors: Sequence[str] = ()) -> str:
    """The common rules, the group's, and — for an ablation only — the parish's surnames."""
    parts = [prompt_text("common.md"), prompt_text(f"{group}.md")]
    if group == "census":
        parts.append("\n".join(f"- `{code}` — {word}" for code, word in CENSUS_ROLES.items()))
    if priors:
        parts.append("Фамилии, встречающиеся в приходе: " + ", ".join(priors) + ".")
    return "\n\n".join(p.strip() for p in parts) + "\n"


def card(fields: Mapping[str, Any]) -> str:
    """The context card: where the record is, never anything a scorer grades."""
    return "\n".join(f"{_CARD_LABELS[k]}: {fields[k]}" for k in CARD_KEYS if fields.get(k))


def _nullable(**schema: Any) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def closed(properties: dict[str, Any]) -> dict[str, Any]:
    """An object schema that names every property, requires all and admits no other."""
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def relationship_of_choices(group: str) -> list[str]:
    """The parties a relative hangs off, a numbered one with its number: `godparent 2`, `witness 1`."""
    return [c for role in RELATIONSHIP_OF[group]
            for c in ([f"{role} {n}" for n in range(1, NUMBERED_PARTIES[role] + 1)]
                      if role in NUMBERED_PARTIES else [role])]


def output_schema(group: str) -> dict[str, Any]:
    record: dict[str, Any] = {f: {"type": ["string", "null"]} for f in RECORD_FIELDS[group]}
    if "gender" in record:
        record["gender"] = _nullable(type="string", enum=["male", "female"])
    # a metric book states no previous revision's age, role, «whose» or departure, and the API takes 16 nullable
    # fields at most
    fields = _PERSON_FIELDS if group == "census" else tuple(f for f in _PERSON_FIELDS if f not in _CENSUS_ONLY)
    person: dict[str, Any] = {"slot": {"type": "string", "enum": list(FAMILIES[group])},
                              **{f: {"type": ["string", "null"]} for f in fields}}
    if group == "census":
        person["role"] = _nullable(type="string", enum=list(CENSUS_ROLES))
    else:
        # a relative's relationship to the person they hang off, and, with `relationship_of`, which party that is
        person["relationship"] = _nullable(type="string", enum=list(RELATIONSHIPS))
        if group in RELATIONSHIP_OF:
            person["relationship_of"] = _nullable(type="string", enum=relationship_of_choices(group))
    # a name read two or three ways (П15): the likelier in its field with «?», the others by the field's path, as `doubtful` says it
    alternative = closed({"path": {"type": "string"}, "readings": {"type": "array", "items": {"type": "string"}}})
    return closed({"record": closed(record), "persons": {"type": "array", "items": closed(person)},
                   "doubtful": {"type": "array", "items": {"type": "string"}},
                   "alternatives": {"type": "array", "items": alternative}})


@dataclass(frozen=True)
class OfTarget:
    """Whose a member is, as `of_targets` resolves it: `target` is the 0-based index into `persons` of the
    member this one is written under (`None`: none, the head, oneself or nobody named), `doubtful` is true when
    the `of` was written with a «?», and `under_head` is true when the `of` named the head: the default, empty and
    right, told apart from oneself and nobody, which are reading errors."""
    target: int | None
    doubtful: bool = False
    under_head: bool = False


def _text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def of_targets(persons: Sequence[Mapping[str, Any]]) -> list[OfTarget]:
    """For each member of an answer's `persons`, whose it is (see the module's rule): by place when no member
    has a written `number`, by number otherwise; the head, oneself and a name no member carries give `None`, the head
    told apart from the other two by `under_head`."""
    numbers = [(_text(p.get("number")) or "").replace("?", "").strip().rstrip(".") or None for p in persons]
    by_place = not any(numbers)
    index: dict[str, int] = {}
    for i, number in enumerate(numbers):
        key = str(i + 1) if by_place else number
        if key is not None:
            index.setdefault(key, i)
    result: list[OfTarget] = []
    for i, person in enumerate(persons):
        said = _text(person.get("of"))
        doubtful = said is not None and "?" in said
        key = said.replace("?", "").strip().rstrip(".") if said is not None else ""
        target = index.get(key) if key else None
        under_head = target is not None and target != i and persons[target].get("role") == "head"
        if target == i or under_head:
            target = None
        result.append(OfTarget(target, doubtful, under_head))
    return result
