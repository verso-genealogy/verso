"""The rules that read the book and the corpus's estates (PSA, RTV, PAF001, CAI002, ZGS): what they share and the
differences from their checks that are accepted.

The parity of each rule with its check is the samples' oracle (`tests/test_linters_on_json_samples.py`); here are the
rules' own contracts: the workspace is the port (its estates, its names table), what a workspace without them
answers (a warning, never a raise), the alias constants the walk and the checks name apart, and every class of
difference between the source and the JSON that the module docstring declares, each pinned by a text on which both
readers are run.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import test_linters_on_json_samples as oracle
from thin_dictionary import FIXTURE, thin_workspace
from verso.core import workspace
from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.fields import vocabulary
from verso.core.records.ids import Ids
from verso.ru import corpus_data
from verso.ru.linters import on_json
from verso.ru.linters.checks import parent_status, patronymic_form, residence_title
from verso.ru.linters.checks.status_words import tables
from verso.ru.linters.on_json import estates, walk

CODES = ("PSA001", "PSA002", "PSA003", "PSA004", "RTV001", "RTV002", "PAF001", "CAI002",
         "ZGS001", "ZGS002", "ZGS003", "ZGS004", "ZGS005", "ZGS006")

HEAD = """
from verso.ru.dsl import (
    CensusRole, Gender, Month, RecordDefaults, Relationship, birth, birth_month, birth_records, census_records,
    death, death_records, household, marriage, marriage_records, member, person, relative)
from verso.ru.dsl.statuses import (
    GOSUDARSTVENNYJ_PEASANT_MALE, GOSUDARSTVENNYJ_PEASANT_FEMALE, PEASANT_FEMALE, STATE_PEASANT_FEMALE,
    STATE_PEASANT_MALE, YASAK_PEASANT_FEMALE, YASAK_PEASANT_MALE)
from corpus.statuses import MANILOV_KF_PEASANT_FEMALE, MANILOV_KF_PEASANT_MALE, NOZDREV_PEASANT
"""


def _data(text: str) -> dict[str, Any]:
    module = oracle.load_sample(HEAD + text)
    assert module is not None, "the text must load"
    doc = encode_namespace(record_namespace(module), village="Примерово", file="f.py", sha256="-", ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _both(code: str, text: str, root: Path | None = None) -> tuple[Counter[oracle.Key], Counter[oracle.Key]]:
    """(what dsllint says of the text, what the walk says of its JSON), for `code`, in the workspace `root`."""
    where = root if root is not None else workspace.current().root
    said = oracle.dsllint_in(where, "Примерово/file.py", HEAD + text)
    assert said is not None
    found = on_json.lint_records(copy.deepcopy(_data(text)), codes=[code], workspace=root)
    return (Counter({k: n for k, n in said.items() if k[0] == code}),
            Counter(oracle._key(f.code, f.variant, f.params, f.token) for f in found))


def _sample_data(name: str) -> dict[str, Any]:
    return next(s.data for s in oracle.samples()[0] if s.name.endswith(name))


# --- the constants that spell one status ---------------------------------------------------------------------

def test_status_collisions_agree_on_the_estate():
    """The constants that spell one text and sex (`STATE_PEASANT_MALE`, `GOSUDARSTVENNYJ_PEASANT_MALE`) are one status
    to the walk, which names the one that sorts last: the estate, the role, the landlord and the rank the checks read
    off them must agree, or the choice would change an answer."""
    groups = [names for names in walk._constants().values() if len([n for n in names if n in tables().texts]) > 1]
    assert groups, "the fixture holds status constants that collide"
    for names in groups:
        names = [n for n in names if n in tables().texts]
        assert len({parent_status.estates()[n] for n in names}) == 1, names
        assert len({parent_status.roles()[n] for n in names}) == 1, names
        landlords = corpus_data.estates().landlords
        assert len({residence_title.landlord_key(n) if residence_title.landlord_key(n) in landlords else None
                    for n in names}) == 1, names
        assert len({n.startswith(residence_title.YASAK_NAME_PREFIXES) for n in names}) == 1, names
        assert len({any(token in n for token in patronymic_form.HIGH_RANK_NAME_TOKENS) for n in names}) == 1, names
        assert len({any(token in n for token in patronymic_form.LOW_RANK_NAME_TOKENS) for n in names}) == 1, names


def test_an_alias_constant_is_named_by_value_in_a_fix():
    """Accepted: the constant PSA offers in its fix is the counterpart of the alias the walk names for the stated
    status, where dsllint offers the counterpart of the alias the source wrote (`GOSUDARSTVENNYJ_PEASANT_FEMALE` has no
    wife's form beside it, `STATE_PEASANT_WIFE` has). Everything else the two say is equal."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Примерово", "Церковь", 1850,
    birth(1, Gender.MALE, 3, 5, father=person("Иван", "Петров", status=GOSUDARSTVENNYJ_PEASANT_MALE),
          mother=person("Анна", "Петрова")),
    defaults=RecordDefaults(status_female=YASAK_PEASANT_FEMALE))
'''
    said, walked = _both("PSA002", text)
    assert sum(said.values()) == sum(walked.values()) == 1
    source, = said
    json_side, = walked
    assert "GOSUDARSTVENNYJ_PEASANT_FEMALE" in source[1] and "STATE_PEASANT_WIFE" in json_side[1]
    assert json.loads(source[1])["silent"] == json.loads(json_side[1])["silent"]


# --- the verbatim documents of PAF001 ------------------------------------------------------------------------------

def test_the_verbatim_documents_are_the_checks_verbs():
    """PAF001 exempts the records of the verbs `VERBATIM_SOURCE_VERBS` (cards, name lists); the walk exempts the
    documents these verbs make, named once in `estates._VERBATIM_DOCS`: the two lists name the same factories."""
    voc = vocabulary()
    by_code = {spec.code: {f.__name__ for f in spec.factories} for spec in voc.specs.values()}
    verbs = {name for doc in estates._VERBATIM_DOCS for name in by_code[doc]}
    verbs |= {name for code in ("listed_person", "external_record") for name in by_code[code]}
    assert verbs == patronymic_form.VERBATIM_SOURCE_VERBS


# --- the workspace is the port -----------------------------------------------------------------------------------

def _without_estates(root: Path, **kwargs: Any) -> Path:
    """A workspace of the tests' own corpus less its `estates.toml`."""
    thin_workspace(root, **kwargs)
    (root / "corpus").unlink()
    (root / "corpus").mkdir()
    for source in (FIXTURE / "corpus").iterdir():            # linked, not copied: `corpus.statuses` is one module
        if source.is_file() and source.name != "estates.toml":
            (root / "corpus" / source.name).symlink_to(source.resolve())
    return root


def test_the_estates_are_the_linting_workspaces(tmp_path: Path):
    """RTV001 reads the landlords of the workspace it is given: a corpus whose estates name no landlord gives a file
    none of the findings the tests' own corpus gives, and the findings that rest on a corpus there is none of are
    warnings (the analogue of the names table's H7)."""
    data = _sample_data("PSA_RTV_estates.py")
    here = on_json.lint_records(copy.deepcopy(data), codes=CODES)
    assert {f.code for f in here} >= {"PSA001", "PSA002", "PSA003", "RTV001", "RTV002", "PAF001", "CAI002"}
    assert {f.level for f in here if f.code.startswith("RTV")} == {"error"}
    root = _without_estates(tmp_path / "ws")
    there = on_json.lint_records(copy.deepcopy(data), codes=CODES, workspace=root)
    assert not any(f.code.startswith("RTV") for f in there)
    assert {f.level for f in there if f.code in ("PSA001", "PSA002", "PSA004")} == {"warn"}
    assert {f.level for f in there if f.code == "PSA003"} == {"error"}          # reads no estate: `needs = ["book"]`
    assert {f.code for f in there} >= {"PSA001", "PSA002", "PSA003"}


def test_a_workspace_with_estates_gives_the_stated_levels():
    """The levels follow hosted.toml where the workspace holds what the code reads (PSA, RTV: a hard check)."""
    data = _sample_data("PSA_RTV_estates.py")
    levels = {f.level for f in on_json.lint_records(copy.deepcopy(data), codes=("PSA001", "RTV001"))}
    assert levels == {"error"}


def test_a_workspace_with_no_names_table_answers_without_raising(tmp_path: Path):
    """RTV001 reads a first name's sex (a godparent's, a witness's): without a names table the sex is not known and
    the finding that rests on it is not made, and what is found is a warning, never a raise (H7)."""
    data = _sample_data("PSA_RTV_estates.py")
    root = thin_workspace(tmp_path / "ws", names=False)
    found = on_json.lint_records(copy.deepcopy(data), codes=CODES, workspace=root)
    assert found, "the constants and the words still speak"
    rtv = [f for f in found if f.code.startswith("RTV")]
    assert rtv and {f.level for f in rtv} == {"warn"}
    civil = on_json.lint_records(copy.deepcopy(_sample_data("ZGS_civil_books.py")), codes=CODES, workspace=root)
    by_code = {code: {f.level for f in civil if f.code == code} for code in ("ZGS001", "ZGS005")}
    assert by_code == {"ZGS001": {"error"}, "ZGS005": {"warn"}}          # a code that reads no name keeps its level


# --- the differences from the source that the module declares -----------------------------------------------------

def test_a_status_bound_to_a_name_is_classified_by_its_text():
    """RTV001 classifies the identifier a status is written with (a name the file binds is no landlord's); the JSON
    holds the text, so the walk classifies the words: it finds the landlord's peasant that dsllint, which reads a
    name, does not."""
    text = '''
OWN = "крестьянин помещика Кузьмы Филипповича Манилова"
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "Церковь", 1850,
    birth(1, Gender.MALE, 3, 5, father=person("Иван", "Петров", status=OWN)),
    defaults=RecordDefaults(residence="Горюхино"))
'''
    said, walked = _both("RTV001", text)
    assert not said and sum(walked.values()) == 1


def test_a_status_built_by_the_file_is_read_as_the_catalog_constant_of_its_value():
    """`Status(…)` the file builds equal to a catalog constant is a name the checks cannot resolve; the JSON holds
    `{text, gender}` and reads the constant."""
    text = '''
from verso.ru.dsl import Status
OWN = Status("крестьянин помещика Кузьмы Филипповича Манилова", Gender.MALE)
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "Церковь", 1850,
    birth(1, Gender.MALE, 3, 5, father=person("Иван", "Петров", status=OWN)),
    defaults=RecordDefaults(residence="Горюхино"))
'''
    said, walked = _both("RTV001", text)
    assert not said and sum(walked.values()) == 1


def test_a_person_given_by_position_is_seen_by_the_walk():
    """PSA reads the persons given as keywords; a birth whose parents are passed by position is invisible to it and
    seen by the walk (the JSON holds a persona wherever it stood)."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "Церковь", 1850,
    birth(1, Gender.MALE, 3, 5, Month.MARCH, Month.MARCH, None, person("Иван", "Петров", status=YASAK_PEASANT_MALE),
          person("Анна", "Петрова", status=MANILOV_KF_PEASANT_FEMALE)))
'''
    said, walked = _both("PSA001", text)
    assert not said and sum(walked.values()) == 1


def test_a_sex_written_by_keyword_is_the_records_sex():
    """The checks read the record's sex from its second positional argument; `gender=Gender.FEMALE` by keyword is no sex to
    them. The walk reads the sex the record wrote, so a newborn girl's PSA003 offers the daughter's form."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "Церковь", 1850,
    birth(1, child=person("Мария", status=STATE_PEASANT_FEMALE), gender=Gender.FEMALE))
'''
    said, walked = _both("PSA003", text)
    assert sum(said.values()) == sum(walked.values()) == 1
    assert "STATE_PEASANT_DAUGHTER" in next(iter(walked))[1]
    assert "STATE_PEASANT_SON" in next(iter(said))[1]


def test_zgs005_names_the_first_old_spelling_in_the_order_of_the_parameters():
    """ZGS005 takes the first of the name spellings the keywords wrote in the order the source wrote them; the walk takes
    them in the order of `person()`'s parameters."""
    text = '''
deaths = death_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "", 1925,
    death(1, Gender.MALE, 1, 2, deceased=person(last_name_orig="Лѣсовщиковъ", name_orig="Ѳома")),
    civil=True)
'''
    said, walked = _both("ZGS005", text)
    assert [k[3] for k in said] == ["Лѣсовщиковъ"] and [k[3] for k in walked] == ["Ѳома"]


def test_zgs004_does_not_count_a_derived_groom_default_twice():
    """A book's `status_groom` is `status_male` unless the author wrote another: the export writes the defaults whole,
    and the walk reads an equal pair as one status, as dsllint reads the one the author wrote. The case lost is the
    author who wrote the equal `status_groom` too: dsllint finds both, the walk one."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "", 1925,
    birth(1, Gender.MALE, 1, 2, child=person("Лука")),
    defaults=RecordDefaults(status_male="помещичий крестьянин"), civil=True)
'''
    said, walked = _both("ZGS004", text)
    assert sum(said.values()) == sum(walked.values()) == 1
    written = text.replace('status_male="помещичий крестьянин")', 'status_male="помещичий крестьянин", '
                           'status_groom="помещичий крестьянин")')
    said, walked = _both("ZGS004", written)
    assert sum(said.values()) == 2 and sum(walked.values()) == 1


def test_a_year_held_in_a_name_is_the_books_year_for_paf001():
    """PAF001 reads the year of a book from an integer written in the call; a year held in a name is none to it. The walk
    reads the book's year: a book of 1925 is exempt on the walk and not to dsllint."""
    text = '''
YEAR = 1925
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "Церковь", YEAR,
    birth(1, Gender.MALE, 1, 2, father=person("Иван", "Петрович")))
'''
    said, walked = _both("PAF001", text)
    assert sum(said.values()) == 1 and not walked


def test_a_previous_age_written_as_none_is_a_key():
    """CAI002 reads `previous_age=None` as written, so the comment's marker is not used then (the check and the walk
    agree)."""
    text = '''
census = census_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", 1858,
    household("1",
              member(1, person("Фома"), CensusRole.HEAD, None, 50, previous_age=None, comment="прошлая РС: 12"),
              member(2, person("Лука"), CensusRole.SON, 1, 50, comment="прошлая РС: 12")))
'''
    said, walked = _both("CAI002", text)
    assert said == walked and sum(said.values()) == 1


def test_an_old_estate_gets_its_token_from_the_name():
    """ZGS004's token is the name of the constant the status was written with, or the words of a literal."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "", 1925,
    birth(1, Gender.MALE, 1, 2, father=person("Иван", status=NOZDREV_PEASANT), child=person("Лука")),
    civil=True)
'''
    said, walked = _both("ZGS004", text)
    assert said == walked and next(iter(walked))[3] == "NOZDREV_PEASANT"


def test_every_code_of_the_module_is_registered():
    assert set(estates.RULES) == set(CODES)
    assert set(CODES) <= set(on_json.SUPPORTED)


def test_an_old_export_is_refused_by_zgs002():
    """ZGS002 reads the months and the year a `birth_month` section gave from the context an export keeps; one from before
    0.1.16 keeps them in `derived` and is asked for again, not read as if the section gave nothing."""
    from verso.core.records.encode import context_in_derived
    data = _sample_data("ZGS_civil_books.py")
    assert on_json.lint_records(copy.deepcopy(data), codes=["ZGS002"])
    old = copy.deepcopy(data)
    for doc in old["documents"]:
        for run in doc.get("pages", ()):
            run["records"] = [context_in_derived(r) for r in run["records"]]
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_records(old, codes=["ZGS002"])
    assert refused.value.message.key == "on_json.no_context"


def test_a_census_books_defaults_give_a_member_its_status_for_rtv002():
    """`ResidenceTitleChecker._book` reads the `RecordDefaults` statuses of a roll as of any book: a member with no status
    of its own, living in the state's деревня, takes the owners' default and is found (the roll's own is quiet)."""
    text = '''
census = census_records(
    "Госархив Примерской области", "21", "3", "1", "Глуповы Горы", 1858,
    household("1",
              member(1, person("Иван", "Петров", residence="Горелово"), CensusRole.HEAD, None, 30),
              member(2, person("Лука", "Иванов", residence="Горелово", status="крестьянин"), CensusRole.SON, 1, 5)),
    defaults=RecordDefaults(status_male=NOZDREV_PEASANT))
'''
    said, walked = _both("RTV002", text)
    assert said == walked and sum(said.values()) == 1
    assert next(iter(said))[2] == "owner_in_state_village_default"


def test_a_census_year_held_in_a_name_is_the_rolls_year_for_cai002():
    """CAI002 reads the year of a roll from a literal; a year held in a name is none to it and the walk reads the roll's year."""
    text = '''
YEAR = 1858
census = census_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", YEAR,
    household("1", member(1, person("Фома"), CensusRole.HEAD, None, 50, 30)))
'''
    said, walked = _both("CAI002", text)
    assert not said and sum(walked.values()) == 1


def test_zgs006_reads_an_explicit_null_as_an_empty_field():
    """A JSON `father_age: null` is as empty as a missing key, as the AST rule and the codemod read it."""
    text = '''
births = birth_records(
    "Госархив Примерской области", "21", "3", "1", "Горюхино", "", 1925,
    birth(1, Gender.MALE, 1, 2, child=person("Лука"), father_age=26, comment="отцу 26, матери 22"),
    civil=True)
'''
    data = _data(text)
    [record] = [r for doc in data["documents"] for run in doc["pages"] for r in run["records"] if r["kind"] == "birth"]
    assert [f.variant for f in on_json.lint_records(copy.deepcopy(data), codes=["ZGS006"])] == ["mother"]
    record["written"]["father_age"] = None
    assert sorted(f.variant for f in on_json.lint_records(copy.deepcopy(data), codes=["ZGS006"])) == ["father", "mother"]
