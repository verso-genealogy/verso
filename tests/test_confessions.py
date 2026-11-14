"""Confession lists (исповедные росписи) as a census vocabulary.

An ИР is not its own record type: it is `census_records()` carrying
`CONFESSION_LIST`. So what has to be pinned is (a) everything that preset
renames, and (b) — the reason every default in `CensusRecords` is the string
the translator used to hardcode — that a plain revision tale still renders
byte-for-byte as it did. The committed census `.tf` tree is applied, and a
changed `geni_document.text` force-replaces the document on Geni.
"""
import re
from calendar import Month

from verso.ru.domain import RecordDefaults, page, person
from verso.ru.domain.statuses import ECON_PEASANT_FEMALE, ECON_PEASANT_MALE
from verso.ru.dsl.records.census import (
    CONFESSION_LIST, CensusRole, census_records, household, member)
from verso.ru.targets.geni.translator.generator import TerraformGenerator


def _records(**kw):
    kw.setdefault("record_month", Month.MARCH)
    for k, v in CONFESSION_LIST.items():
        kw.setdefault(k, v)
    return census_records(
        "ГАРО", "735", "265", "53", "Заманиловка", 1828,
        *page("34", household(
            "71",
            member(1, person("Харитонъ", "Пахомовъ"), CensusRole.HEAD, age=66),
            member(2, person("Анисья", "Сидорова"), CensusRole.WIFE, age=44),
            member(3, person("Игнатій"), CensusRole.SON, age=12),
        )),
        defaults=RecordDefaults(status_male=ECON_PEASANT_MALE,
                                status_female=ECON_PEASANT_FEMALE),
        **kw,
    )


def _emit(records=None):
    gen = TerraformGenerator()
    gen.add_census_records(records if records is not None else _records())
    return gen._outputs


def _tf(records=None):
    return "".join(_emit(records).values())


# --- the preset -------------------------------------------------------------

def test_confession_list_is_accepted_verbatim_by_census_records():
    # The whole point of the preset: it splats into census_records() with no
    # adapter, so the two ИР files in the corpus cannot drift apart.
    r = _records()
    for key, value in CONFESSION_LIST.items():
        assert getattr(r, key) == value, key


def test_shared_machinery_still_runs():
    # Patronymic derivation and surname inheritance come from CensusHousehold
    # and are not re-implemented for the ИР.
    r = _records()
    son = r.households[0].members[2]
    # «Харитонъ» canonicalizes to «Харитон» via names.csv — shared
    # machinery again, nothing ИР-specific.
    assert son.person.patr_modern == "Харитонович"


# --- what the ИР vocabulary renames -----------------------------------------

def test_emits_into_an_ir_prefixed_file():
    # An ИР and a ревизская сказка of the same year must not collide.
    assert set(_emit()) == {"ir_1828_1.tf"}


def test_document_is_keyed_and_titled_on_the_dvor():
    tf = _tf()
    assert ('resource "geni_document" '
            '"confession_of_the_household_number_71_1828"') in tf
    assert "Исповедная роспись Заманиловка 1828: двор 71" in tf
    assert "№ двора: 71" in tf
    assert "семья 71" not in tf


def test_member_profiles_are_keyed_on_ir_not_rs():
    tf = _tf()
    assert "_ir_" in tf
    assert "_rs_" not in tf


def test_one_age_column():
    tf = _tf()
    assert "№. Роль   Имя                    Возраст\n" in tf
    assert "Возраст в пред./текущей ревизии" not in tf
    # `-/66` would claim the scribe left a previous-revision cell empty, when
    # the ИР form has no such cell at all.
    assert "-/66" not in tf
    assert re.search(r"1\. глава: Харитон Пахомович: 66$", tf, re.M)


def test_reviewed_false_emits_nothing():
    assert not any(v.strip() for v in _emit(_records(reviewed=False)).values())


def test_record_type_keeps_find_person_working():
    # `find_person --type "исповедная роспись"` filters on this exact string.
    assert _records().record_type == "исповедная роспись"


# --- and what it must NOT change --------------------------------------------

def _census():
    return census_records(
        "ГАТО", "75", "8", "162", "Заманиловка", 1811,
        *page("198", household(
            "271",
            member(1, person("Нилъ", "Пахомовъ"), CensusRole.HEAD,
                   age=41, previous_age=25),
            member(2, person("Тихонъ"), CensusRole.SON, age=11),
        )),
        prev_revision_year=1795,
    )


def test_a_revision_tale_still_renders_as_before():
    gen = TerraformGenerator()
    gen.add_census_records(_census())
    outputs = gen._outputs
    assert set(outputs) == {"rs_1811_1.tf"}
    tf = "".join(outputs.values())
    assert 'resource "geni_document" "census_of_the_family_number_271_1811"' in tf
    assert "Ревизская сказка Заманиловка 1811: семья 271" in tf
    assert "№ семьи / № Двора: 271" in tf
    assert "Возраст в пред./текущей ревизии" in tf
    assert "25/41" in tf


def test_census_defaults_are_the_translator_s_old_hardcoded_strings():
    # Every one of these was a `getattr(records, …) or "<literal>"` fallback
    # in the generator. A drifted default here rewrites — and so
    # force-replaces on Geni — every applied census document in the corpus.
    r = _census()
    assert r.household_label == "семья"
    assert r.household_number_label == "№ семьи / № Двора"
    assert r.file_prefix == "rs"
    assert r.doc_res_prefix == "census_of_the_family_number"
    assert r.single_age_column is False
    assert r.record_type == "ревизия"


# --- the CSV exporter -------------------------------------------------------

def test_csv_leads_with_the_household_number(tmp_path, monkeypatch):
    import csv as _csv

    from verso.ru.exporters.csv import CensusRecordsCsvExporter

    monkeypatch.chdir(tmp_path)
    out = _records().export(CensusRecordsCsvExporter())
    with open(out, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    # One exporter, two vocabularies: the column header follows
    # `household_label`, so an ИР is cited by двор and a ревизия by семья.
    assert [r["Двор"] for r in rows] == ["71", "71", "71"]
    assert rows[0]["Возраст"] == "66"


def test_census_csv_uses_the_semya_header(tmp_path, monkeypatch):
    import csv as _csv

    from verso.ru.exporters.csv import CensusRecordsCsvExporter

    monkeypatch.chdir(tmp_path)
    out = _census().export(CensusRecordsCsvExporter())
    with open(out, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    assert [r["Семья"] for r in rows] == ["271", "271"]
