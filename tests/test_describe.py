"""verso.ru.dsl.describe — the DSL described for the review page: its
record functions and their parameters, the constants a field takes, the sex a role or a
relation implies. What /api/catalog answers is `describe()`."""
from __future__ import annotations

from verso.ru.domain import Status, statuses
from verso.ru.dsl import calls, describe
from verso.ru.dsl.records import census
from verso.ru.gender import Gender


def test_describe_is_what_the_page_reads_as_its_catalog():
    found = describe.describe()
    assert list(found) == ["catalogs", "param_catalog", "signatures", "role_gender", "relationship_gender"]
    assert found["role_gender"]["CensusRole.WIFE"] == "ж"
    assert found["relationship_gender"]["Relationship.FATHER"] == "м"
    assert [p["name"] for p in found["signatures"]["member"]][:3] == ["number", "person", "role"]
    assert list(found["signatures"]) == list(describe.CATALOG_FUNCS)


def test_the_record_functions_are_one_list():
    assert describe.RECORD_FUNCS is calls.RECORD_FUNCS


def test_a_role_says_its_sex_by_its_public_name():
    assert census.ROLE_GENDER[census.CensusRole.WIFE] is Gender.FEMALE


def test_a_status_written_as_words_has_the_constants_sex():
    assert Status.gender_of(str(statuses.PEASANT_WIDOW)) is Gender.FEMALE
    assert Status.gender_of("никем не записанные слова") is None


def test_the_status_catalog_gives_each_constant_its_sex():
    assert ("PEASANT_WIFE", statuses.PEASANT_WIFE, "ж") in describe.status_catalog()


def _fresh() -> None:
    describe.catalogs.cache_clear()
    describe.constant_by_code.cache_clear()


def test_a_constant_names_the_module_the_dsl_imports_it_from(monkeypatch):
    """DSL v1: a constant the page adds is imported from the facade's catalog — the
    corpus's own from `corpus.statuses` —, whatever the module is named in the process
    (verso.ru.domain.statuses); a v0 file takes it in its own form (`v0_module`)."""
    from verso.ru.domain import causes_of_death, marital_status
    _fresh()
    try:
        for _ in range(2):
            cats = describe.catalogs()
            assert {c.module for c in cats["status"]} == {"verso.ru.dsl.statuses", "corpus.statuses"}
            assert {c.module for c in cats["status"] if c.code == "PEASANT_MALE"} == {"verso.ru.dsl.statuses"}
            assert {c.module for c in cats["cause"]} == {"verso.ru.dsl.causes_of_death"}
            assert {c.module for c in cats["marital"]} == {"verso.ru.dsl.marital_status"}
            for module, renamed in ((statuses, "a.renamed.statuses"), (causes_of_death, "a.renamed.causes"),
                                    (marital_status, "a.renamed.marital_status")):
                monkeypatch.setattr(module, "__name__", renamed)
            _fresh()
    finally:
        monkeypatch.undo()
        _fresh()


def test_every_catalog_names_its_module_in_one_table():
    assert describe.DSL_IMPORTS == {
        "status": "verso.ru.dsl.statuses", "cause": "verso.ru.dsl.causes_of_death",
        "marital": "verso.ru.dsl.marital_status", "gender": "verso.ru.dsl", "relationship": "verso.ru.dsl",
        "role": "verso.ru.dsl", "side": "verso.ru.dsl", "month": "verso.ru.dsl"}
    assert {c.module for c in describe.catalogs()["role"]} == {describe.DSL_IMPORTS["role"]}
