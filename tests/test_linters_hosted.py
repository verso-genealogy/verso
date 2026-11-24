"""The linters on records JSON (`verso.ru.linters.hosted`, `verso.ru.linters.on_json`, 0.1.11, L10 part 2).

Every code has a class of readiness — what it needs to run without the DSL's source — and the
pilot codes lint a file's records JSON as `dsllint` lints its source: the same codes and params,
a finding addressed by its record's id instead of a line.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import village_fixture
from verso.core import workspace
from verso.core.pipeline.load import load_module, record_namespace
from verso.core.records import FormatError
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.linters import findings, hosted, on_json
from verso.ru.linters.codes import LINTER_CODES

PILOT = ("CPL002", "ULC001")
CENSUS = "Маниловка/1858/manilovka_census_1858.py"
# A household of the roll that is held (`reviewed=False`, the roll's): a grandson whose reference
# is the head and who has no parent_member (CPL002), born in a place the corpus does not know.
GRANDSON = '''          household("3",
                    member(1, person("Лука", "Ѳоминъ", "Примеровъ"), CensusRole.HEAD, age=60),
                    member(2, person("Ѳома", "Лукинъ", residence="Неведомка"), CensusRole.GRANDSON,
                           ref_member=1, age=7)),
          household("2",'''


@pytest.fixture
def mini(tmp_path: Path):
    root = village_fixture.root(tmp_path)
    census = root / CENSUS
    census.write_text(census.read_text(encoding="utf-8").replace('          household("2",', GRANDSON, 1),
                      encoding="utf-8")
    village_fixture.workspace(tmp_path, root)
    with workspace.use(root):
        yield root


def _dsllint(path: Path, codes: tuple[str, ...]) -> Counter[tuple[str, str]]:
    found = findings.lint_text(path.read_text(encoding="utf-8"), path)
    return Counter((f.code, json.dumps(f.params, ensure_ascii=False, sort_keys=True))
                   for f in found if f.code in codes)


def _on_json(path: Path, codes: tuple[str, ...]) -> Counter[tuple[str, str]]:
    doc = encode_namespace(record_namespace(load_module(path)), village=path.parts[-3], file="f.py",
                           sha256="0" * 64, ids=Ids())
    data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
    return Counter((f.code, json.dumps(f.params, ensure_ascii=False, sort_keys=True))
                   for f in on_json.lint_records(data, codes=codes))


def test_every_code_has_a_class():
    table = hosted.readiness()
    assert set(table) == {code for codes in LINTER_CODES.values() for code in codes}
    assert {r.cls for r in table.values()} <= {"written", "derived", "context", "source"}
    assert all(r.needs for r in table.values() if r.cls == "context")
    assert {table[c].cls for c in PILOT} == {"written", "context"}


def test_every_code_has_a_scope():
    """`scope` says where a code is answered (`record`, `set`, `file`, `source`, `layer`): the class `source` is the
    scope `source`, ZGS003 is a finding about a book, ULC001 reads one fact of the whole file, the LEX codes a names
    layer's files, and every other code is a record's."""
    table = hosted.readiness()
    assert len(table) == 104
    assert {r.scope for r in table.values()} == {"record", "set", "file", "source", "layer"}
    assert {c for c, r in table.items() if r.scope == "layer"} == set(LINTER_CODES["lexicon"])
    assert {table[c].cls for c in LINTER_CODES["lexicon"]} == {"context"}
    assert {c for c, r in table.items() if r.scope == "source"} == {c for c, r in table.items() if r.cls == "source"}
    assert {c for c, r in table.items() if r.scope in ("set", "file")} == {"ZGS003", "ULC001"}
    assert table["ZGS003"].scope == "set" and table["ULC001"].scope == "file"
    # RVR001's `page_*` variants are the source's alone (the export has no trace of them): the code is a record's
    assert table["RVR001"].scope == "record"


@pytest.fixture(autouse=True)
def _read_again():
    """`hosted.toml` is read once per process: a test that patched the reader must not leave its table behind."""
    hosted._read_table.cache_clear()  # pyright: ignore[reportPrivateUsage]
    yield
    hosted._read_table.cache_clear()  # pyright: ignore[reportPrivateUsage]


def test_a_row_without_a_valid_scope_is_refused(monkeypatch: pytest.MonkeyPatch):
    import tomllib
    bad: dict[str, Any] = {"X001": {"class": "written", "severity": "warn", "scope": "page", "note": "n"}}

    def loads(_text: str) -> dict[str, Any]:
        return bad

    monkeypatch.setattr(tomllib, "loads", loads)
    hosted._read_table.cache_clear()     # pyright: ignore[reportPrivateUsage] — the file is read once, and read here again
    with pytest.raises(ValueError):
        hosted.readiness()


def test_a_held_record_is_linted_alike(mini: Path):
    found = on_json.lint_records(json.loads(json.dumps(encode_namespace(
        record_namespace(load_module(mini / CENSUS)), village="Маниловка", file="f.py", sha256="0" * 64,
        ids=Ids()), ensure_ascii=False)), codes=PILOT)
    cpl = [f for f in found if f.code == "CPL002"]
    assert len(cpl) == 1 and cpl[0].record.endswith("/household/3")
    assert _on_json(mini / CENSUS, ("CPL002",)) == _dsllint(mini / CENSUS, ("CPL002",))


def test_pilot_codes_agree_on_the_mini_corpus(mini: Path):
    files = sorted(mini.glob("*/*/*.py"))
    for code in PILOT:
        dsl = sum((_dsllint(p, (code,)) for p in files), Counter())
        js = sum((_on_json(p, (code,)) for p in files), Counter())
        assert dsl, f"{code}: the fixture must give a finding"
        assert js == dsl, code


def test_source_codes_are_refused():
    """A code about the form of the source text has no meaning without a file: refused by its own
    message, never skipped."""
    for code in ("SLC001", "SLC002", "CML001", "IMP001"):
        with pytest.raises(on_json.Unsupported) as refused:
            on_json.lint_records({"schema": "records-v1", "documents": []}, codes=[code])
        assert refused.value.message.key == "on_json.source_code", code


def test_an_unknown_code_is_unsupported():
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_records({"schema": "records-v1", "documents": []}, codes=["XXX999"])
    assert refused.value.message.key == "on_json.unsupported"


WRITTEN_ONLY = ("CPL002", "NAM001", "ULC001")        # codes that read no replay: the input is refused for them too


@pytest.mark.parametrize("bad", [{}, {"documents": None}, {"schema": "records-v1"}, {"schema": "records-v1", "documents": None},
                                 {"schema": "records-v1", "documents": {}}, {"schema": "records-v1", "documents": [None]},
                                 [], "records-v1", None, {"schema": "records-v0", "documents": []}, {"documents": []}])
def test_an_input_that_is_no_records_file_is_refused(bad: Any):
    """`lint_records` checks its input before any rule: a mapping of schema records-v1 with a list of documents,
    as `replay_file` asks — the same `FormatError`, for a written-only code too, never a `KeyError` or a `TypeError`."""
    for code in WRITTEN_ONLY:
        with pytest.raises(FormatError):
            on_json.lint_records(bad, codes=[code])


def test_a_vocabulary_newer_than_the_plugin_is_refused():
    """The header's vocabulary is checked as `replay_file` checks it (`check_vocabulary`): a newer one, or one that
    is not `{plugin, version}`, is a `FormatError` before any rule."""
    base: dict[str, Any] = {"schema": "records-v1", "documents": []}
    for vocabulary in ({"plugin": "ru", "version": 10**6}, "ru", {"plugin": "ru"}):
        with pytest.raises(FormatError):
            on_json.lint_records({**base, "vocabulary": vocabulary}, codes=["NAM001"])
    assert on_json.lint_records(base, codes=["NAM001"]) == []


def test_the_input_is_checked_in_the_workspace_of_the_call(tmp_path: Path):
    """A hosted caller has no ambient workspace and passes `workspace=`: the header's vocabulary is checked against the
    plugins enabled in THAT workspace (`check_vocabulary` asks `workspace.current()`), so a real export, which always
    carries the header, is answered. Run in a process with no workspace to find (cwd outside any, no VERSO_WORKSPACE)."""
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k != "VERSO_WORKSPACE"}
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    program = (
        "import sys; from pathlib import Path; from verso.ru.linters import on_json\n"
        "export = {'schema': 'records-v1', 'vocabulary': {'plugin': 'ru', 'version': 1}, 'documents': []}\n"
        "print(on_json.lint_records(export, codes=['NAM001'], workspace=Path(sys.argv[1])))\n")
    fixture = Path(__file__).resolve().parent / "fixtures" / "workspace"
    done = subprocess.run([sys.executable, "-c", program, str(fixture)], cwd=tmp_path, env=env,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-800:]
    assert done.stdout.strip() == "[]"


def test_no_codes_asks_nothing_of_the_input():
    assert on_json.lint_records({}, codes=[]) == []


def test_codes_given_as_a_string_are_refused():
    """A `str` is a collection of characters: «NAM001» would ask for six codes that do not exist. A caller's slip, said
    as one."""
    with pytest.raises(TypeError):
        on_json.lint_records({"schema": "records-v1", "documents": []}, codes="NAM001")


def test_level_follows_hosted_toml(mini: Path):
    """A finding's level is its code's severity in `hosted.toml`: refuse is an error, warn a warning."""
    table = hosted.readiness()
    assert table["CPL002"].severity == "warn" and table["ULC001"].severity == "warn"
    doc = encode_namespace(record_namespace(load_module(mini / CENSUS)), village="Маниловка", file="f.py",
                           sha256="0" * 64, ids=Ids())
    data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
    found = on_json.lint_records(data, codes=PILOT)
    assert found and {f.level for f in found} == {"warn"}


def test_level_error_for_a_refuse_code(monkeypatch: pytest.MonkeyPatch, mini: Path):
    real = hosted.readiness()
    row = real["CPL002"]
    monkeypatch.setattr(hosted, "readiness", lambda: {**real, "CPL002": hosted.Readiness(
        row.cls, "refuse", row.needs, row.note, row.as_code)})
    doc = encode_namespace(record_namespace(load_module(mini / CENSUS)), village="Маниловка", file="f.py",
                           sha256="0" * 64, ids=Ids())
    data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
    assert {f.level for f in on_json.lint_records(data, codes=["CPL002"])} == {"error"}


def test_registry_matches_hosted():
    """Every code of `hosted.toml` that is not the form of the source, and not folded into another by `as`, has a
    rule, and every rule is such a code: nothing is left pending. A names layer's codes read no record."""
    expected = {c for c, r in hosted.readiness().items()
                if r.cls != "source" and r.as_code is None and r.scope != "layer"}
    assert set(on_json.SUPPORTED) == expected


def test_positional_codes_fold():
    table = hosted.readiness()
    assert {c: table[c].as_code for c in ("BRD002", "BRD004", "CRD003", "CRD006")} == {
        "BRD002": "BRD001", "BRD004": "BRD003", "CRD003": "CRD002", "CRD006": "CRD005"}
    assert all(r.as_code in table for r in table.values() if r.as_code)


def test_redundant_is_what_the_notes_say():
    """`redundant` and the note hold one set: the codes whose note says «(redundant…», and the positional codes
    that fold into one of them (`as`). Each is `derived`; a caller reads `readiness()[code].redundant`."""
    table = hosted.readiness()
    said = {c for c, r in table.items() if "(redundant" in r.note}
    folded = {c for c, r in table.items() if r.as_code in said}
    assert {c for c, r in table.items() if r.redundant} == said | folded
    assert len(said | folded) == 19 and {"BRD002", "BRD004"} <= folded - said
    assert {table[c].cls for c in said | folded} == {"derived"}


def test_redundant_on_a_code_not_derived_is_refused(monkeypatch: pytest.MonkeyPatch):
    import tomllib
    real = tomllib.loads
    for row in ('[X]\nclass = "written"\nseverity = "warn"\nredundant = true\nnote = "x"\n',
                '[X]\nclass = "derived"\nseverity = "warn"\nredundant = "yes"\nnote = "x"\n'):
        def loads(_text: str, row: str = row) -> dict[str, Any]:
            return real(row)
        monkeypatch.setattr(hosted.tomllib, "loads", loads)
        hosted._read_table.cache_clear()  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(ValueError):
            hosted.readiness()


def test_only_the_form_of_the_text_is_source():
    """A redundant kwarg (a written value equal to the one it would inherit) is `written` and `derived`
    together — JSON keeps both — so only the codes about the text's own form need a file."""
    table = hosted.readiness()
    assert {c for c, r in table.items() if r.cls == "source"} == {"SLC001", "SLC002", "CML001", "IMP001"}
    assert {table[c].cls for c in ("VSR001", "CSR001", "CRD006", "BRD001", "RVR001", "DRA002")} == {"derived"}


def test_a_person_shared_by_two_records_is_found_once_per_record(mini: Path):
    """The walk addresses a finding by record: a `person()` object two records share is one call in the
    source (one dsllint finding) and two personas in the JSON (two findings) — the documented difference."""
    rel = "Маниловка/1900/manilovka_births_1900.py"
    path = mini / rel
    text = path.read_text(encoding="utf-8")
    text = text.replace("manilovka_births_1900 = birth_records(",
                        'GODFATHER = person("Семенъ", "Лукинъ", "Списковъ", residence="Неведомка")\n'
                        "manilovka_births_1900 = birth_records(", 1)
    text = text.replace('god_parent1=person("Никифоръ", "Андреевъ", "Образцовъ")', "god_parent1=GODFATHER", 1)
    text = text.replace('god_parent1=person("Николай", "Николаев", "Пробин")', "god_parent1=GODFATHER", 1)
    path.write_text(text, encoding="utf-8")
    assert _dsllint(path, ("ULC001",)) == Counter({("ULC001", '{"place": "Неведомка"}'): 1})
    assert _on_json(path, ("ULC001",)) == Counter({("ULC001", '{"place": "Неведомка"}'): 2})


def test_a_wrappers_values_are_no_written_of_the_call(mini: Path):
    """Since records v1.x a wrapper's value (the roll's record month, a лист's flag) stands in a record's
    `written`, named in `written.context`: the linters read the call's keys only, and lint a node
    alike with and without those values."""
    from verso.core.records.encode import context_in_derived
    doc = encode_namespace(record_namespace(load_module(mini / CENSUS)), village="Маниловка", file="f.py",
                           sha256="0" * 64, ids=Ids())
    data: dict[str, Any] = json.loads(json.dumps(doc, ensure_ascii=False))
    records = [r for d in data["documents"] for p in d.get("pages", ()) for r in p["records"]]
    marked = [r for r in records if "context" in r["written"]]
    assert marked, "the roll's households carry a wrapper's value"
    call = on_json.FileView(data).written(marked[0]["kind"], marked[0])
    assert "context" not in call and not set(marked[0]["written"]["context"]) & set(call)
    stripped = json.loads(json.dumps(data))
    for d in stripped["documents"]:
        for p in d.get("pages", ()):
            p["records"] = [context_in_derived(r) for r in p["records"]]

    def found(doc_: dict[str, Any]) -> list[tuple[str, str, str]]:
        return sorted((f.code, f.record, json.dumps(f.params, ensure_ascii=False, sort_keys=True))
                      for f in on_json.lint_records(doc_, codes=PILOT))

    assert found(data) == found(stripped) and found(data)


def test_fold_reads_a_positional_finding_as_the_keyword_one():
    """`as` and `forms` of `hosted.toml` are the one place the positional and the keyword form are one finding."""
    table = hosted.readiness()
    assert hosted.fold("BRD002", "residence_positional", {"val": "X"}, table) == ("BRD001", "residence", {"val": "X"})
    assert hosted.fold("BRD004", "surname_positional", {"role": "son"}, table) == ("BRD003", "surname", {"role": "son"})
    assert hosted.fold("CRD003", "surname", {"val": "X", "suffix": 1}, table) == (
        "CRD002", "surname_orig", {"orig_val": "X", "suffix": 1})
    assert hosted.fold("CRD006", "patronymic", {"val": "X"}, table) == ("CRD005", "patronymic_orig", {"val": "X"})
    assert hosted.fold("DRA002", "redundant_positional", {"val": "'Ротозеево'"}, table) == (
        "DRA002", "redundant", {"val": "Ротозеево"})
    assert hosted.fold("DRA002", "redundant", {"val": "Ротозеево"}, table) == ("DRA002", "redundant", {"val": "Ротозеево"})
    assert hosted.fold("CPL002", "no_father", {"a": 1}, table) == ("CPL002", "no_father", {"a": 1})
    assert hosted.fold("NOPE", "v", {}) == ("NOPE", "v", {})


def test_the_table_is_read_once_and_each_call_has_its_own(monkeypatch: pytest.MonkeyPatch):
    import tomllib
    real, reads = tomllib.loads, []

    def counting(text: str) -> dict[str, Any]:
        reads.append(1)
        return real(text)

    monkeypatch.setattr(hosted.tomllib, "loads", counting)
    first, second = hosted.readiness(), hosted.readiness()
    assert len(reads) == 1 and first == second and first is not second
    first.pop("NAM001")
    assert "NAM001" in hosted.readiness()


def test_stand_down_names_the_field_that_answers_a_code():
    """`stand_down`: the key of a record's `written` that stands a code down once the scan confirms the source —
    «так в подлиннике». A store that refuses a write for the code can offer the field instead of knowing the code."""
    from verso.core.records.fields import vocabulary

    table = hosted.readiness()
    assert {code: row.stand_down for code, row in table.items() if row.stand_down} == {
        "DBD001": "source_date_error", "DBD002": "source_date_error"}
    keys = {key for by_attr in vocabulary().json_keys.values() for key in by_attr.values()}
    assert all(row.stand_down in keys for row in table.values() if row.stand_down)
    assert table["DRA001"].stand_down is None
