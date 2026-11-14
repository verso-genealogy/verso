"""VERSO_RECORDS: every reader of the DSL can read the exported JSON instead."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import village_fixture
from verso.ru.cli import generate_tf
from verso.core import ratchet
from verso.core.pipeline import records
from verso.core.pipeline.load import discover_records, load_module, village_modules
from verso.ru.cli.export_csv import export_file
from verso.core.pipeline.records import StaleRecords, export_village
from verso.core.records.graph import first_difference

BROKEN = 'from verso.ru.dsl import person\nx = person("Хщъ")\n'


@pytest.fixture
def village(tmp_path: Path) -> Path:
    return village_fixture.root(tmp_path) / "Маниловка"


@pytest.fixture
def rec(village: Path, tmp_path: Path) -> Path:
    export_village(village, tmp_path / "rec")
    return tmp_path / "rec"


def _tree(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def test_json_mode_discovers_the_same_record_sets_in_the_same_order(village: Path, rec: Path):
    dsl = list(discover_records(str(village)))
    with records.use(rec):
        js = list(discover_records(str(village)))
    assert [(p, n) for p, n, _ in dsl] == [(p, n) for p, n, _ in js]
    for (_, name, a), (_, _, b) in zip(dsl, js, strict=True):
        assert first_difference(a, b, name) is None


def test_json_mode_writes_the_same_terraform(village: Path, rec: Path, tmp_path: Path):
    assert generate_tf.main(["--village", str(village), "--output-dir", str(tmp_path / "a")]) == 0
    with records.use(rec):
        assert generate_tf.main(["--village", str(village), "--output-dir", str(tmp_path / "b")]) == 0
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")
    assert _tree(tmp_path / "a")


def test_export_file_writes_the_same_csv_from_json(tmp_path: Path):
    a = village_fixture.root(tmp_path / "a") / "Маниловка"
    b = village_fixture.root(tmp_path / "b") / "Маниловка"
    export_village(b, tmp_path / "rec")
    for path in sorted(a.glob("[0-9][0-9][0-9][0-9]/*.py")):
        export_file(path, tmp_path / "csv-a" / path.parent.name)
    with records.use(tmp_path / "rec"):
        for path in sorted(b.glob("[0-9][0-9][0-9][0-9]/*.py")):
            export_file(path, tmp_path / "csv-b" / path.parent.name)
    csv_a = {k: v for k, v in _tree(tmp_path / "csv-a").items() if k.endswith(".csv")}
    csv_b = {k: v for k, v in _tree(tmp_path / "csv-b").items() if k.endswith(".csv")}
    assert csv_a and csv_a == csv_b


def test_a_mirror_takes_the_village_from_the_caller(village: Path, rec: Path, tmp_path: Path):
    mirror = tmp_path / "mirror"
    shutil.copytree(village, mirror / "tmpname")
    with records.use(rec):
        sets = records.read_namespace(mirror / "tmpname" / "1900" / "manilovka_births_1900.py", village_dir=village)
    assert sets


def test_a_stale_export_stops_the_reader_even_inside_a_broad_except(village: Path, rec: Path):
    births = village / "1900" / "manilovka_births_1900.py"
    births.write_text(births.read_text(encoding="utf-8") + "\n# правка\n", encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match="устарела"):
        try:
            load_module(births)
        except Exception:
            pytest.fail("устаревшую выгрузку проглотил except Exception")


def test_a_new_dsl_file_makes_the_export_stale(village: Path, rec: Path):
    (village / "1900" / "manilovka_new_1900.py").write_text("x = 1\n", encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match="новый"):
        load_module(village / "1900" / "manilovka_births_1900.py")


def test_another_schema_version_is_refused(village: Path, rec: Path):
    index = rec / "Маниловка" / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["schema"] = "records-v9"
    index.write_text(json.dumps(data), encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match="records-v1"):
        load_module(village / "1900" / "manilovka_births_1900.py")


def test_no_export_is_refused(village: Path, tmp_path: Path):
    with records.use(tmp_path / "nothing"), pytest.raises(StaleRecords, match="нет выгрузки"):
        load_module(village / "1900" / "manilovka_births_1900.py")


def test_a_skipped_file_is_an_import_error_in_json_mode_too(village: Path, tmp_path: Path):
    (village / "1901").mkdir()
    (village / "1901" / "broken.py").write_text(BROKEN, encoding="utf-8")
    export_village(village, tmp_path / "rec")
    with records.use(tmp_path / "rec"), pytest.raises(ImportError, match="Unrecognized first name"):
        load_module(village / "1901" / "broken.py")


def test_a_skipped_files_reason_is_written_in_english(village: Path, tmp_path: Path):
    """The index is a derived artefact a corpus hashes: what it says of a skipped file follows no
    interface language."""
    from verso.core import i18n
    (village / "1901").mkdir()
    (village / "1901" / "broken.py").write_text(
        "from verso.core.messages import t\nfrom verso.core.workspace import WorkspaceError\n"
        "raise WorkspaceError(t('workspace.no_file', path='/x'))\n", encoding="utf-8")
    texts = []
    for lang in ("ru", "en"):
        with i18n.use(lang):
            export_village(village, tmp_path / lang)
        texts.append(json.loads((tmp_path / lang / "Маниловка" / "index.json").read_text(encoding="utf-8"))["skipped"])
    assert texts[0] == texts[1] and all(ord(c) < 0x400 for c in json.dumps(texts[0], ensure_ascii=False))


def test_the_environment_variable_switches_the_source(village: Path, rec: Path, monkeypatch: pytest.MonkeyPatch):
    assert records.root() is None
    monkeypatch.setenv(records.ENV, str(rec))
    assert records.root() == rec
    module = load_module(village / "1900" / "manilovka_births_1900.py")
    assert {k for k in vars(module) if not k.startswith("__")} == {"manilovka_births_1900"}
    assert module.__file__ == str(village / "1900" / "manilovka_births_1900.py")


def test_json_mode_hands_out_a_listed_record_already_on_geni(village: Path, tmp_path: Path):
    # What load_module's docstring says: the DSL marks `on_geni` in admit_listed, after
    # the load; the JSON holds the mark, so a caller of load_module alone sees it in
    # JSON mode only. Through village_modules the two agree.
    births = village / "1900" / "manilovka_births_1900.py"
    module = load_module(births)
    k, line = next((k, p) for k, (r, p) in enumerate(ratchet.pair(births.read_text(encoding="utf-8"), module))
                   if ratchet.unreviewed(r))
    (village / ratchet.LIST_FILE).write_text(
        ratchet.format_list([ratchet.Entry("1900/manilovka_births_1900.py", line.fingerprint, line.label)]),
        encoding="utf-8")
    export_village(village, tmp_path / "rec")

    def listed(module: object) -> list[bool]:
        return ["on_geni" in vars(r) for r in ratchet.runtime_records(vars(module))]

    walked = dict(village_modules(village))
    assert listed(load_module(births))[k] is False and listed(walked[births])[k] is True
    with records.use(tmp_path / "rec"):
        assert listed(load_module(births))[k] is True
        assert listed(dict(village_modules(village))[births]) == listed(walked[births])


@pytest.mark.parametrize("damage", ["missing", "corrupt", "sha256", "schema"])
def test_a_damaged_file_json_stops_the_reader(village: Path, rec: Path, damage: str):
    path = rec / "Маниловка" / "1900" / "manilovka_births_1900.json"
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_text(path.read_text(encoding="utf-8")[:200], encoding="utf-8")
    else:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc[damage] = "чужой"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match="перевыгрузите"):
        try:
            load_module(village / "1900" / "manilovka_births_1900.py")
        except Exception:
            pytest.fail("испорченный JSON проглотил except Exception")


def test_a_changed_ratchet_list_makes_the_export_stale(village: Path, rec: Path):
    (village / "unreviewed_on_geni.tsv").write_text("# новый список\n", encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match=r"unreviewed_on_geni\.tsv"):
        load_module(village / "1900" / "manilovka_births_1900.py")


def test_a_changed_names_layer_makes_the_export_stale(tmp_path: Path):
    """In Verso's workspace (`village_fixture.workspace`): its layer is the one the
    fixture's records are read with, and a layer of its own to change."""
    from verso.core import workspace

    root = village_fixture.root(tmp_path)
    village = root / "Маниловка"
    with workspace.use(village_fixture.workspace(tmp_path / "tables", root)):
        export_village(village, tmp_path / "rec")
        forms = tmp_path / "tables" / "names" / "forms.tsv"
        forms.write_text(forms.read_text(encoding="utf-8") + "M\tЗюзей\tЗюзея\t\t\t\t\tfixture\n", encoding="utf-8")
        with records.use(tmp_path / "rec"), pytest.raises(StaleRecords, match=r"forms\.tsv"):
            load_module(village / "1900" / "manilovka_births_1900.py")


def test_changed_library_code_makes_the_export_stale(village: Path, rec: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(records, "code_fingerprint", lambda: "другой код")
    with records.use(rec), pytest.raises(StaleRecords, match="код библиотеки"):
        load_module(village / "1900" / "manilovka_births_1900.py")


def test_the_landlords_statuses_are_code_the_export_rests_on(tmp_path: Path):
    """The 171 landlords' statuses left geni/ for corpus/statuses.py, which
    verso.ru.domain.statuses re-exports; a changed wording there must stale an export
    as a change in geni/ does."""
    statuses = tmp_path / "corpus" / "statuses.py"
    statuses.parent.mkdir()
    statuses.write_text('A = "крестьянин"\n', encoding="utf-8")
    records.code_fingerprint_of.cache_clear()
    try:
        before = records.code_fingerprint_of(("verso.core",), statuses)
        statuses.write_text('A = "крестьянка"\n', encoding="utf-8")
        records.code_fingerprint_of.cache_clear()
        assert records.code_fingerprint_of(("verso.core",), statuses) != before
        assert records.code_fingerprint_of(("verso.core",), None) != before
    finally:
        records.code_fingerprint_of.cache_clear()


def test_the_statuses_are_read_from_the_workspaces_corpus():
    """Through the workspace's corpus directory, not by importing the `corpus` package."""
    from verso.core import workspace
    corpus = workspace.current().corpus_dir
    assert corpus is not None
    assert records.code_fingerprint() == records.code_fingerprint_of(records.library(), corpus / "statuses.py")


def test_a_changed_statuses_toml_makes_the_export_stale(tmp_path: Path):
    """A corpus holding its statuses as data (`statuses.toml`): the file is an input of the export, as the names
    tables are — a changed wording stales it. A corpus holding `statuses.py` has no such input (its module is code)."""
    from verso.core import workspace
    from verso.ru.domain import statuses

    root = village_fixture.root(tmp_path)
    village = root / "Маниловка"
    ws = village_fixture.workspace(tmp_path / "tables", root)
    module = statuses.corpus_statuses()
    assert module is not None
    text = statuses.statuses_toml(module)
    old = workspace.current().corpus_dir
    assert old is not None
    assert "corpus/statuses.toml" not in records.inputs(village)
    corpus = tmp_path / "toy_toml_corpus"
    shutil.copytree(old, corpus, ignore=shutil.ignore_patterns("__pycache__", "statuses.py"))
    (corpus / "statuses.toml").write_text(text, encoding="utf-8")
    config = ws / "verso.toml"
    config.write_text(config.read_text(encoding="utf-8").replace(json.dumps(str(old), ensure_ascii=False),
                                                                 json.dumps(str(corpus), ensure_ascii=False)),
                      encoding="utf-8")
    with workspace.use(ws):
        assert workspace.current().corpus_dir == corpus
        export_village(village, tmp_path / "rec")
        index = json.loads((tmp_path / "rec" / "Маниловка" / "index.json").read_text(encoding="utf-8"))
        assert index["inputs"]["corpus/statuses.toml"]
        (corpus / "statuses.toml").write_text(text + '\n[ABC_NEW]\ntext = "новый чин"\n', encoding="utf-8")
        with records.use(tmp_path / "rec"), pytest.raises(StaleRecords, match=r"statuses\.toml"):
            load_module(village / "1900" / "manilovka_births_1900.py")


def test_a_mirror_reads_the_real_villages_inputs(village: Path, tmp_path: Path):
    # A copy holding the year files only (a corpus's comparison base before 0.1.0 runs its CSVs so) reads
    # the ratchet list and the names of the real village.
    (village / "unreviewed_on_geni.tsv").write_text("# пусто\n", encoding="utf-8")
    export_village(village, tmp_path / "rec")
    mirror = tmp_path / "mirror" / "tmpname"
    shutil.copytree(village / "1900", mirror / "1900")
    with records.use(tmp_path / "rec"):
        assert records.read_namespace(mirror / "1900" / "manilovka_births_1900.py", village_dir=village)


def test_a_mirror_copy_that_differs_is_stale(village: Path, rec: Path, tmp_path: Path):
    mirror = tmp_path / "mirror" / "tmpname"
    shutil.copytree(village / "1900", mirror / "1900")
    copy = mirror / "1900" / "manilovka_births_1900.py"
    copy.write_text(copy.read_text(encoding="utf-8") + "\n# правка\n", encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match="изменён"):
        records.read_namespace(copy, village_dir=village)


def test_the_fingerprint_reads_the_library_of_the_layout():
    """The packages are the core's and the enabled plugin's: in a workspace of ru, the
    library."""
    assert records.library() == ("verso.core", "verso.ru")


def test_v0_export_is_refused(village: Path, rec: Path):
    """Records v0 is read no more: an export written before v1 says how to write it again."""
    index = rec / "Маниловка" / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["schema"] = "records-v0"
    index.write_text(json.dumps(data), encoding="utf-8")
    with records.use(rec), pytest.raises(StaleRecords, match=r"records-v1(.|\n)*export-records"):
        load_module(village / "1900" / "manilovka_births_1900.py")
