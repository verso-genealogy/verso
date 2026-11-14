"""The rules that read the names table, and what is around them: the workspace is the dictionary (Д2), a workspace
without a table (H7) and the reverse table of status constants.

The parity of each rule with its check is the samples' oracle (`tests/test_linters_on_json_samples.py`); here are the
mechanisms the rules share.
"""
from __future__ import annotations

import ast
import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

import test_linters_on_json_samples as oracle
from thin_dictionary import thin_workspace
from verso.core import workspace
from verso.core.pipeline.load import record_namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.domain import marital_status, statuses
from verso.ru.linters import findings, hosted, on_json
from verso.ru.linters.checks import parent_status, patronymic_form
from verso.ru.linters.checks.names import gender_from_status_name
from verso.ru.linters.on_json.walk import names_table_present, status_constant, status_name
from verso.ru.naming import names_registry
from verso.ru.naming.lexicon import Lexicon

# Invented: two births whose mothers' patronymics and surnames the FATHER relative of the record cannot give.
RELATIVES = '''
from verso.ru.dsl import Gender, Relationship, birth, birth_records, person, relative

births = birth_records(
    "ГА Глуповской области", "10", "4", "4047", "Маниловка", "Церковь", 1851,
    birth(1, Gender.MALE, 3, 5, child=person("Иван"), mother=person("Анна", "Петровна", "Примерова"),
          relatives=[relative(person("Лука", "Лукинъ", "Опискинъ"), Relationship.FATHER, "мать")]),
    birth(2, Gender.MALE, 4, 6, child=person("Петр"), mother=person("Мария", "Ивановна", "Пробина"),
          relatives=[relative(person("Лука", "Лукинъ", "Опискинъ"), Relationship.FATHER, "мать")]))
'''

# Invented: a man in the father's slot by the sex he writes (the table is not asked), a woman's name in a man's slot,
# an unknown-sex name, a status of the other sex written as words.
SLOTS = '''
from verso.ru.dsl import Gender, birth, birth_records, person

births = birth_records(
    "ГА Глуповской области", "10", "4", "4047", "Маниловка", "Церковь", 1851,
    birth(1, Gender.MALE, 3, 5, child=person("Иван"), father=person("Петр", gender=Gender.MALE),
          mother=person("Анна", gender=Gender.FEMALE)),
    birth(2, Gender.MALE, 4, 6, child=person("Иван", status="экономическая крестьянка"),
          father=person("Петр", "Лукинъ", "Опискина")))
'''


def _data(text: str) -> dict[str, Any]:
    module = oracle.load_sample(text)
    assert module is not None
    doc = encode_namespace(record_namespace(module), village="Примерово", file="f.py", sha256="-", ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _found(data: dict[str, Any], code: str, root: Path | None = None) -> list[on_json.Finding]:
    return on_json.lint_records(copy.deepcopy(data), codes=[code], workspace=root)


def test_a_patronymic_the_table_lacks_is_no_contradiction(tmp_path: Path):
    """CPL012 asks `can_name`, which cannot canonicalize a patronymic its table lacks («Андреевъ» of a table without
    «Андрей»): both readers guard it — the walk (`_may_name`) and the check (`census_parent_link._may_name`) read it as
    agreeing, where the check used to crash (`dsllint` reported a failed linter). With either guard removed this
    raises `ValueError`."""
    text = _sample_text("CPL_names_links")
    data = _data(text)
    thin = thin_workspace(tmp_path / "thin", drop=frozenset({"Андрей"}))
    assert "Андреевъ" in {f.params["patronymic"] for f in _found(data, "CPL012")}      # a contradiction with the table
    assert "Андреевъ" not in {f.params["patronymic"] for f in _found(data, "CPL012", thin)}
    said = oracle.dsllint_in(thin, "on_json_samples/CPL_names_links.py", text)
    assert said is not None                                                              # dsllint: no linter crashed
    assert not [k for k in said if k[0] == "CPL012" and "Андреевъ" in str(k)]


def test_rla003_needs_no_table_for_a_surname(tmp_path: Path):
    """RLA002 derives a patronymic from the table, RLA003 compares surnames and needs none: without a table the first
    is not made and the second still is, for every record (a lookup that raised would end the shared walk at the first)."""
    text = RELATIVES
    data = _data(text)
    with_table = _found(data, "RLA003")
    assert len(with_table) == 2 and {f.level for f in with_table} == {"warn"}
    for root in (thin_workspace(tmp_path / "unset", names=False), _no_file(tmp_path / "nofile")):
        found = _found(data, "RLA003", root)
        assert [f.params for f in found] == [f.params for f in with_table] and {f.level for f in found} == {"warn"}
        assert _found(data, "RLA002", root) == []
    assert len(_found(data, "RLA002")) == 2


def test_a_keyword_name_modern_orth_that_says_nothing_is_no_keyword(tmp_path: Path):
    """Documented difference: RLA002 and RLA001 read `name_modern_orth=""` as a keyword that names nobody, the walk as no
    keyword (a positional `""` placeholder is the same in the export), so it falls to `name_orig`."""
    text = RELATIVES.replace('person("Лука", "Лукинъ", "Опискинъ")', 'person("Лука", "Лукинъ", "Опискинъ", name_modern_orth="")', 1)
    path = oracle_path(tmp_path, text)
    said = [f for f in findings.lint_text(text, path) if f.code == "RLA002"]
    assert len(said) == 1                                  # the other relative, whose name is written
    assert len(_found(_data(text), "RLA002")) == 2


def oracle_path(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "Примерово"
    root.mkdir()
    path = root / "file.py"
    path.write_text(text, encoding="utf-8")
    return path


def _sample_text(name: str) -> str:
    return (oracle.DATA / "on_json_samples" / f"{name}.py.sample").read_text(encoding="utf-8")


def _father_written_female(data: dict[str, Any]) -> dict[str, Any]:
    """The file, edited as a hosted Verso could receive it: the first birth's father writes the sex of a woman (a
    `Person` refuses it, so no DSL gives it)."""
    edited = copy.deepcopy(data)
    father = next(p for p in edited["documents"][0]["pages"][0]["records"][0]["persons"] if p["role"] == "father")
    father["written"]["gender"] = "female"
    return edited


def _no_file(root: Path) -> Path:
    """A workspace that names a table directory with no names.csv in it."""
    root.mkdir(parents=True)
    (root / "verso.toml").write_text('schema = 4\nvillages = []\nplugins = ["ru"]\n[names]\ndir = "."\n', encoding="utf-8")
    return root


# --- H7: a workspace without a names table ------------------------------------------------------------------------

def test_no_names_table_warns(tmp_path: Path):
    """In a workspace with no names table (none named, or a directory without `names.csv`) a code that reads names
    does not raise. It answers as far as it can without the table: the finding that rests on a sex written stays, at
    the level of a warning where the code is an error with a table; a finding that rests on a name only the table can
    read (an unknown name, the sex of a name, a patronymic's derivation) is not made, and the codes that replay the
    file, which builds its persons from the table, find nothing."""
    data = _father_written_female(_data(SLOTS))
    assert [f.level for f in _found(data, "GND001")] == ["error"]            # with a table: an error
    assert [f.variant for f in _found(data, "NGA001")] == ["surname_man"]    # a man's name read by the table
    for root in (thin_workspace(tmp_path / "unset", names=False), _no_file(tmp_path / "nofile")):
        with workspace.use(root):
            assert not names_table_present()
        gnd = _found(data, "GND001", root)
        assert [f.params["role"] for f in gnd] == ["father"] and {f.level for f in gnd} == {"warn"}
        assert _found(data, "NAM001", root) == []
        assert _found(data, "NGA001", root) == []
        assert _found(data, "BRD001", root) == []
    assert names_table_present()


def test_a_mistyped_names_base_is_refused_not_read_as_no_names(tmp_path: Path):
    """A `[names] base` no plugin ships is the workspace's error — the first lookup refuses it, naming the bases there
    are — and `lint_records` raises it, where a workspace with no names at all gets warnings."""
    data = _father_written_female(_data(SLOTS))
    root = tmp_path / "ws"
    root.mkdir()
    (root / "verso.toml").write_text('schema = 6\nvillages = []\nplugins = ["ru"]\n[names]\nbase = "xx"\n',
                                     encoding="utf-8")
    with pytest.raises(workspace.WorkspaceError, match="нет базы «xx»: одна из ru или false"):
        _found(data, "GND001", root)
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "verso.toml").write_text('schema = 6\nvillages = []\nplugins = ["ru"]\n[names]\nbase = false\n',
                                     encoding="utf-8")
    assert {f.level for f in _found(data, "GND001", bare)} == {"warn"}


def test_a_code_that_needs_names_is_a_warning_without_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The level of a finding of a code that needs the names table is `warn` in a workspace without one, the code's own
    severity with one (H5, H7)."""
    real = hosted.readiness()
    row = real["NGA001"]
    monkeypatch.setattr(hosted, "readiness", lambda: {**real, "NGA001": hosted.Readiness(
        row.cls, "refuse", row.needs, row.note, row.as_code)})
    data = _data(SLOTS)
    assert {f.level for f in _found(data, "NGA001")} == {"error"}
    # a man whose sex is written needs no table to be told his surname is a woman's
    father = data["documents"][0]["pages"][0]["records"][1]["persons"][1]
    assert father["role"] == "father"
    father["written"]["gender"] = "male"
    assert {f.level for f in _found(data, "NGA001", thin_workspace(tmp_path / "ws", names=False))} == {"warn"}


def test_no_names_table_never_raises(tmp_path: Path):
    """No supported code raises in a workspace without a names table, on any sample, and what a code that needs the
    table finds there is a warning."""
    unset, nofile = thin_workspace(tmp_path / "unset", names=False), _no_file(tmp_path / "nofile")
    table = hosted.readiness()
    for sample in oracle.samples()[0]:
        for code in on_json.SUPPORTED:
            for found in on_json.lint_records(copy.deepcopy(sample.data), codes=[code], workspace=unset):
                assert found.level == "warn" or "names" not in table[found.code].needs, (sample.name, code)
            if "names" in table[code].needs:
                on_json.lint_records(copy.deepcopy(sample.data), codes=[code], workspace=nofile)


def test_a_code_that_reads_the_names_table_says_so(monkeypatch: pytest.MonkeyPatch):
    """Every supported code that asks the names table of the workspace — to read a name, or to replay the file, which
    builds its persons from it — has `names` in its `needs` in `hosted.toml`: the one thing the level in a workspace
    without a table rests on (H7)."""
    loaded = oracle.samples()[0]               # building the samples reads the table: before the trace
    reads: Counter[str] = Counter()
    asking = [""]
    real = names_registry.current_lexicon

    def traced() -> Lexicon:
        reads[asking[0]] += 1
        return real()

    monkeypatch.setattr(names_registry, "current_lexicon", traced)
    for code in on_json.SUPPORTED:
        asking[0] = code
        for sample in loaded:
            on_json.lint_records(copy.deepcopy(sample.data), codes=[code])
    table = hosted.readiness()
    assert sorted(code for code, count in reads.items() if count and "names" not in table[code].needs) == []


# --- Д2: the workspace is the dictionary ---------------------------------------------------------------------------

def test_workspace_is_the_port(tmp_path: Path):
    """One file in two workspaces whose tables differ gives different findings, each as its table reads the names, and
    the workspace that was current is the current one afterwards."""
    data = _data(_sample_text("NAM_NGA_names"))
    wide = thin_workspace(tmp_path / "wide")
    thin = thin_workspace(tmp_path / "thin", drop=frozenset({"Иван", "Петр", "Анна", "Мария"}))
    flipped = thin_workspace(tmp_path / "flipped", flip=frozenset({"Иван", "Анна"}))
    before = workspace.current().root
    in_wide, in_thin = _found(data, "NAM001", wide), _found(data, "NAM001", thin)
    assert workspace.current().root == before
    assert in_wide == [] and {f.params["name"] for f in in_thin} == {"Иван", "Петр", "Анна", "Мария"}
    assert _found(data, "NAM001") == []                       # no workspace named: the tests' own, as the wide one
    assert _found(data, "NAM004", wide) != _found(data, "NAM004", flipped)
    assert workspace.current().root == before


# --- the reverse table of status constants -------------------------------------------------------------------------

def _groups() -> dict[tuple[str, str | None], list[str]]:
    found: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for name, value in sorted(statuses.catalog().items()):
        found[(str(value), None if value.gender is None else value.gender.name.lower())].append(name)
    return found


def test_status_constant_is_the_reverse_of_the_catalog():
    """`status_constant(text, gender)` names every constant of the catalog with those words and that sex, in
    alphabetical order; `status_name` the one `known_statuses` and `status_words.tables` give."""
    groups = _groups()
    assert len(groups) > 100
    for (text, gender), names in groups.items():
        assert status_constant(text, gender) == tuple(names)
        assert status_name(text, gender) == names[-1]
    assert status_constant("слова, которых нет", "male") == () and status_name("слова, которых нет", None) == "слова, которых нет"
    # the marital statuses are plain text, no sex
    assert status_constant(marital_status.MARRIED, None) == ("MARRIED",)
    assert status_constant(marital_status.MARRIED, "male") == ()


def test_status_collisions_agree():
    """Where several constants spell one status — the words and the sex — NAM004, PSA003 and PAF001 answer alike on
    each of them, so the JSON, which holds `{text, gender}` and no name, loses nothing by naming one (the
    alphabetically last, as `known_statuses` does): NAM004 by the sex the NAME gives, PSA003 by the role and the
    estate of the name (does the newborn carry an adult's role), PAF001 by the name's rank."""
    collisions = {key: names for key, names in _groups().items() if len(names) > 1}
    assert collisions, "the tests' catalog holds no status spelled twice: the test proves nothing"
    for key, names in collisions.items():
        assert status_constant(*key) == tuple(names)
        nam004 = {gender_from_status_name(n) for n in names}
        psa003 = {(parent_status.roles().get(n, "") in parent_status.CHILD_ROLES,
                   parent_status.estates().get(n) in parent_status.EXEMPT_ESTATES) for n in names}
        paf001 = {patronymic_form._is_high_rank(ast.Name(id=n)) for n in names}  # pyright: ignore[reportPrivateUsage]
        assert len(nam004) == len(psa003) == len(paf001) == 1, (key, names, nam004, psa003, paf001)


# --- a file the table cannot replay: the refusal carries what needs no replay ---------------------------------------

def test_a_file_the_table_cannot_replay_refuses_with_the_findings_that_need_no_replay(tmp_path: Path):
    """The names table lacks «Иван»: the file cannot be replayed, so the codes that read the replay are unanswered, and
    the call refuses — but the refusal carries NAM001, which names that very cause and needs no replay, leveled as
    usual, and the sorted codes it could not answer. Nothing of the findings is lost to the one failure."""
    data = _data(_sample_text("NAM_NGA_names"))
    thin = thin_workspace(tmp_path / "thin", drop=frozenset({"Иван"}))
    assert _found(data, "NAM001", thin)                        # alone, NAM001 answers: it reads no replay
    with pytest.raises(on_json.Unsupported) as refused:
        on_json.lint_records(copy.deepcopy(data), codes=on_json.SUPPORTED, workspace=thin)
    assert refused.value.message.key == "on_json.not_replayable"
    assert [f for f in refused.value.findings if f.code == "NAM001"] == _found(data, "NAM001", thin)
    assert {f.code for f in refused.value.findings} >= {"NAM001"}
    assert refused.value.unanswered == sorted(refused.value.unanswered) and refused.value.unanswered
    assert {f.code for f in refused.value.findings}.isdisjoint(refused.value.unanswered)
    # the births' codes that read the replay are unanswered (the file holds no other kind of record to ask of it) ...
    assert {"BRD001", "BRD003", "BRD005", "BRD006", "RVR001"} <= set(refused.value.unanswered)
    # ... and a code is unanswered exactly when it is refused asked alone: the report names the codes, whatever else is asked
    for code in on_json.SUPPORTED:
        try:
            alone = on_json.lint_records(copy.deepcopy(data), codes=[code], workspace=thin)
        except on_json.Unsupported as one:
            assert code in refused.value.unanswered and one.unanswered == [code] and one.findings == [], code
        else:
            assert code not in refused.value.unanswered, code
            assert [f for f in refused.value.findings if f.code == code] == alone, code
