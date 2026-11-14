"""The accepted differences between a `written` check and its walk on records JSON (`census`, `common`, `events`), each
pinned by a text on which both readers are run: what `dsllint` says of the source, and what `lint_records` says of its
JSON. The parity of every rule with its check is the samples' oracle (`tests/test_linters_on_json_samples.py`); these
are the cases the module docstrings declare as differing, because the source reads a call's syntax and the JSON holds
only what the call evaluated to. None is in a real corpus. The positional forms of PM001/PM002, AGE001/AGE002,
MRA001 and DRA001 differed too until the checks read an argument in its place; their tests pin the agreement.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any

import test_linters_on_json_samples as oracle
from verso.core import workspace
from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.linters import on_json

HEAD = """
from verso.ru.dsl import (
    CensusRole, Gender, Month, Relationship, Side, census_records, death, death_records, household, marriage,
    marriage_records, member, person, relative)
"""
DEATHS = 'deaths = death_records("ГА Глуповской области", "10", "4", "4060", "Маниловка", "Церковь", 1860,'
MARRIAGES = 'marriages = marriage_records("ГА Глуповской области", "10", "4", "4061", "Маниловка", "Церковь", 1860,'
CENSUS = 'census = census_records("ГА Глуповской области", "10", "4", "4062", "Маниловка", 1858,'


def _both(code: str, text: str) -> tuple[Counter[oracle.Key], Counter[oracle.Key]]:
    """(what dsllint says of the text, what the walk says of its JSON), for `code`."""
    module = oracle.load_sample(HEAD + text)
    assert module is not None, "the text must load"
    doc = encode_namespace(record_namespace(module), village="Примерово", file="f.py", sha256="-", ids=Ids())
    data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
    said = oracle.dsllint_in(workspace.current().root, "Примерово/file.py", HEAD + text)
    assert said is not None
    found = on_json.lint_records(copy.deepcopy(data), codes=[code])
    return (Counter({k: n for k, n in said.items() if k[0] == code}),
            Counter(oracle._key(f.code, f.variant, f.params, f.token) for f in found))  # pyright: ignore[reportPrivateUsage]


def _variants(counted: Counter[oracle.Key]) -> list[str]:
    return sorted(key[2] for key in counted.elements())


def test_pm001_and_pm002_read_a_positional_reference_as_the_walk_does():
    """`member(2, p, CensusRole.SON, 1, parent_member=1)`, the reference positional (the usual form), and the same
    call with `ref_member=1` are one call to both readers: the JSON cannot tell the two forms apart, and the check
    reads the reference in its place as it reads the keyword."""
    text = f'''
{CENSUS}
    household("1",
              member(1, person("Лука", "Ѳомичъ", "Опискинъ"), CensusRole.HEAD, age=60),
              member(2, person("Иван", "Лукинъ"), CensusRole.SON, 1, parent_member=1, age=30),
              member(3, person("Анна"), CensusRole.WIFE, 2, parent_member=1, age=28)))
'''
    keyword = text.replace("CensusRole.SON, 1,", "CensusRole.SON, ref_member=1,") \
                  .replace("CensusRole.WIFE, 2,", "CensusRole.WIFE, ref_member=2,")
    for code, variant in (("PM001", "redundant"), ("PM002", "partners_parent")):
        for form in (text, keyword):
            said, walked = _both(code, form)
            assert said == walked and _variants(said) == [variant], code


def test_age001_and_age002_read_a_positional_age_as_the_walk_does():
    """`death(…, person("Лука"), "70")`, the age positional, is the same age as `age="70"` to both readers."""
    text = f'''
{DEATHS}
    death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, person("Лука"), "70"),
    death(2, Gender.FEMALE, 5, 6, Month.MAY, Month.MAY, person("Марія"), "много лет"))
'''
    keyword = text.replace('person("Лука"), "70"', 'person("Лука"), age="70"') \
                  .replace('person("Марія"), "много лет"', 'person("Марія"), age="много лет"')
    for code in ("AGE001", "AGE002"):
        for form in (text, keyword):
            said, walked = _both(code, form)
            assert said == walked and sum(said.values()) == 1, code


def test_age001_and_age002_read_a_marriage_s_positional_ages_as_the_walk_does():
    """`marriage(…, groom, bride, None, None, "20", "много лет")`: a groom's and a bride's age in their places."""
    text = f'''
{MARRIAGES}
    marriage(1, 7, Month.FEBRUARY, person("Лука"), person("Дарья"), None, None, "20", "много лет"))
'''
    keyword = text.replace('None, None, "20", "много лет"', 'groom_age="20", bride_age="много лет"')
    for code in ("AGE001", "AGE002"):
        for form in (text, keyword):
            said, walked = _both(code, form)
            assert said == walked and sum(said.values()) == 1, code


def test_mra001_and_dra001_read_a_positional_party_as_the_walk_does():
    """MRA001's groom and bride and DRA001's deceased, written positionally, are the record's parties to both
    readers, whose parent's village is compared with theirs; so are a death's relatives in their place."""
    marriage_text = f'''
{MARRIAGES}
    marriage(1, 7, Month.FEBRUARY, person("Лука", residence="Маниловка"), person("Дарья", residence="Маниловка"),
             relatives=[relative(person("Петръ", residence="Заманиловка"), Relationship.FATHER, "жених")]))
'''
    death_text = f'''
{DEATHS}
    death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, person("Лука", residence="Маниловка"), 70,
          relatives=[relative(person("Петръ", residence="Заманиловка"), Relationship.FATHER)]))
'''
    forms = {
        "MRA001": (marriage_text,
                   marriage_text.replace('Month.FEBRUARY, person("Лука"', 'Month.FEBRUARY, groom=person("Лука"')
                                .replace('person("Дарья"', 'bride=person("Дарья"')),
        "DRA001": (death_text,
                   death_text.replace("), 70,\n          relatives=", "), 70,\n          "),
                   death_text.replace("Month.MAY, person(", "Month.MAY, deceased=person(")
                             .replace("), 70,", "), age=70,")),
    }
    for code, texts in forms.items():
        for form in texts:
            said, walked = _both(code, form)
            assert said == walked and sum(said.values()) == 1, (code, form)
    said, _ = _both("MRA001", marriage_text)
    assert _variants(said) == ["father_groom"]


def test_wsd001_exempts_a_side_on_a_person_bound_and_used_as_a_witness():
    """A `person(side=…)` bound once and passed as `witness1=W` is not a witness call to the check, so WSD001 flags
    the side as outside a witness there. The JSON holds the persona in the witness slot and exempts it."""
    text = f'''
W = person("Василій", side=Side.GROOM)
{MARRIAGES}
    marriage(1, 7, Month.FEBRUARY, groom=person("Лука"), bride=person("Дарья"), witness1=W))
'''
    said, walked = _both("WSD001", text)
    assert _variants(said) == ["outside"] and sum(walked.values()) == 0
    direct = text.replace('W = person("Василій", side=Side.GROOM)\n', "") \
                 .replace("witness1=W", 'witness1=person("Василій", side=Side.GROOM)')
    said, walked = _both("WSD001", direct)
    assert sum(said.values()) == sum(walked.values()) == 0


def test_a_value_held_in_a_name_is_read_evaluated():
    """`age=AGE` is an identifier to AGE002, which skips it; the JSON holds the value the name evaluated to and reads
    it, so a name bound to a wrong age is a finding there and none in the source."""
    text = f'''
AGE = "много лет"
{DEATHS}
    death(1, Gender.MALE, 3, 4, Month.MAY, Month.MAY, deceased=person("Лука"), age=AGE))
'''
    said, walked = _both("AGE002", text)
    assert sum(said.values()) == 0 and sum(walked.values()) == 1
    literal = text.replace("age=AGE", 'age="много лет"')
    said, walked = _both("AGE002", literal)
    assert said == walked and said
