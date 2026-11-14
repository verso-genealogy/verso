"""`verso names add | remove | check | explain` over the layers of a workspace of schema 6.

Every workspace here is written into tmp_path, its layer and its corpus invented (Зюзей, Зюзик …).
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli import names as cli
from verso.ru.gender import Gender
from verso.ru.naming import layer_files, layers, names_registry
from verso.ru.naming.layer_files import BASE, FILES, FilesLayer
from verso.ru.naming.lexicon import LexiconConflict, NameEntry
from verso.ru.naming.names_registry import current_lexicon, matching_base
from verso.ru.naming.validation import validate_first_name

M, F = Gender.MALE, Gender.FEMALE

# Invented: two records write Зюзей (one of them in the old orthography's spelling of Зюзик), a third a name no layer holds.
BIRTHS = '''
from verso.ru.dsl import Gender, birth, birth_records, marriage, person

births = birth_records(
    "ГА Глуповской области", "10", "4", "4047", "Маниловка", "Церковь", 1900,
    birth(1, Gender.MALE, 3, 5, child=person("Зюзей"), father=person("Зюзей", "Петровъ"),
          mother=person("Анна", "Ивановна")),
    birth(2, Gender.FEMALE, 4, 6, child=person("Анна"), father=person("Петръ"), mother=person("Зюзикъ")),
    birth(3, Gender.FEMALE, 7, 8, child=person("Анна"), father=person("Зюзей"), mother=person("Анна")))
'''


@pytest.fixture(autouse=True)
def forgotten() -> Iterator[None]:
    names_registry.reload()
    yield
    names_registry.reload()


def _workspace(root: Path, *, layer: bool = True, corpus: bool = False, schema: int = 6, read_only: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    names = ('[names]\nlayers = ["below", "names"]\nwritable = "names"\n' if read_only
             else '[names]\nlayers = ["names"]\nwritable = "names"\n') if layer else ""
    villages = 'villages = ["Маниловка"]\n' if corpus else "villages = []\n"
    (root / "verso.toml").write_text(f'schema = {schema}\n{villages}plugins = ["ru"]\n{names}[i18n]\nlocale = "ru"\n',
                                     encoding="utf-8")
    if layer:
        (root / "names").mkdir(exist_ok=True)
        if read_only:
            (root / "below").mkdir(exist_ok=True)
    if corpus:
        year = root / "Маниловка" / "1900"
        year.mkdir(parents=True)
        (year / "manilovka_births_1900.py").write_text(BIRTHS, encoding="utf-8")
    return root


def _digest(directory: Path | object) -> dict[str, str]:
    return {file: hashlib.sha256((directory / file).read_bytes()).hexdigest() for file in FILES.values()}  # type: ignore[operator]


def _run(root: Path, *argv: str) -> int:
    with workspace.use(root):
        return cli.main(list(argv))


def _rows(root: Path, file: str) -> list[str]:
    path = root / "names" / file
    return path.read_text(encoding="utf-8").splitlines()[1:] if path.is_file() else []


def test_add_goes_to_writable_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    before = _digest(BASE)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--genitive", "Зюзея-я", "--source", "Горюхино 1917") == 0
    assert _digest(BASE) == before                      # not a byte of the base
    assert _rows(root, "names.tsv") == ["M\tЗюзей\t\t\tГорюхино 1917\t"]
    assert _rows(root, "forms.tsv") == ["M\tЗюзей\tЗюзея-я\t\t\t\t\tГорюхино 1917"]
    with workspace.use(root):
        assert validate_first_name("Зюзей") is True
        assert current_lexicon().layers == ("base", "names")
        assert names_registry.genitive_from_name("Зюзей") == "Зюзея-я"
    assert "names/names.tsv" in capsys.readouterr().out


def test_add_takes_a_variant_with_its_base_and_no_form_cells(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--base", "Зюзей", "--patr-m", "-",
                "--old-patronymic-m", "Зюзиков") == 0
    assert _rows(root, "names.tsv") == ["M\tЗюзей\t\t\teditor\t", "M\tЗюзик\tЗюзей\t\teditor\t"]
    assert _rows(root, "forms.tsv") == ["M\tЗюзик\t\t-\t\tЗюзиков\t\teditor"]   # `-`: no such form; empty: the rule's
    with workspace.use(root):
        assert matching_base("Зюзик", M) == "Зюзей"


def test_add_forms_alone_for_a_name_the_layers_hold(tmp_path: Path) -> None:
    """A name the base holds: giving forms writes the forms row and leaves the name's own row to the base."""
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Иван", "--genitive", "Иванова") == 0
    assert _rows(root, "names.tsv") == []
    assert _rows(root, "forms.tsv") == ["M\tИван\tИванова\t\t\t\t\teditor"]
    with workspace.use(root):
        assert matching_base("Иван", M) == "Иоанн"                       # the base's name entry stands


def test_add_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "Ж", "--name", "Зюзея", "--dry-run") == 0
    assert _rows(root, "names.tsv") == [] and "--dry-run" in capsys.readouterr().out


def test_add_refuses_unknown_base(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--base", "Нетакогоимени") == 1
    err = capsys.readouterr().err
    assert "LEX003" in err and "Нетакогоимени" in err
    assert _rows(root, "names.tsv") == []              # nothing written


def test_add_refuses_a_key_no_lookup_can_ask_by(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Zyuzey") == 1
    assert "LEX001" in capsys.readouterr().err and _rows(root, "names.tsv") == []


def test_add_refuses_a_key_the_layer_holds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    before = (root / "names" / "names.tsv").read_bytes()
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--source", "другой") == 1
    assert "Зюзей" in capsys.readouterr().err and (root / "names" / "names.tsv").read_bytes() == before


def test_add_warns_redundant(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The base answers Иван → Иоанн already: the row is written, and the warning says the sum answers so."""
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Иван", "--base", "Иоанн") == 0
    err = capsys.readouterr().err
    assert "LEX005" in err and "Иван" in err
    assert _rows(root, "names.tsv") == ["M\tИван\tИоанн\t\teditor\t"]


def test_add_refuses_what_the_workspace_cannot_take(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--layer", str(tmp_path / "elsewhere")) == 1
    assert "elsewhere" in capsys.readouterr().err
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--origin", "Разг.") == 1
    assert "--origin" in capsys.readouterr().err
    bare = _workspace(tmp_path / "bare", layer=False)
    assert _run(bare, "add", "--gender", "М", "--name", "Зюзей") == 1
    assert "writable" in capsys.readouterr().err


def test_add_on_a_schema_5_workspace_goes_to_names_csv(legacy_workspace: Path,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    """The old tables: the row is placed in names.csv as it always was (`tests/test_names_cli_add.py` writes it), with a
    note it is the old path; --layer is refused, and remove and check are for layers."""
    copy = legacy_workspace
    assert _run(copy, "add", "--gender", "М", "--name", "Бузун", "--genitive", "Бузуна", "--dry-run") == 0
    captured = capsys.readouterr()
    assert "names.csv" in captured.out and ",Бузуна," in captured.out and "схема ≤ 5" in captured.err
    assert "Бузун" not in (copy / "names.csv").read_text(encoding="utf-8")
    assert _run(copy, "add", "--gender", "М", "--name", "Бузик", "--layer", str(copy)) == 1
    assert _run(copy, "remove", "--gender", "М", "--name", "Бузун") == 1
    assert _run(copy, "check") == 1


def test_remove_deletes_the_layers_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--genitive", "Зюзея-я") == 0
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей") == 0
    assert _rows(root, "names.tsv") == [] and _rows(root, "forms.tsv") == []
    out = capsys.readouterr().out
    assert "names.tsv, forms.tsv" in out
    with workspace.use(root):
        assert validate_first_name("Зюзей") is False


def test_remove_of_a_base_name_writes_a_removal_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A name only the base holds is taken out of the stack by a removal row (`-` in bases); the base keeps its bytes."""
    root = _workspace(tmp_path)
    before = _digest(BASE)
    assert "\tЛукас\t" in (BASE / "names.tsv").read_text(encoding="utf-8")
    assert _run(root, "remove", "--gender", "М", "--name", "Лукас") == 0
    assert _digest(BASE) == before
    assert _rows(root, "names.tsv") == ["M\tЛукас\t-\t\teditor\t"]
    assert "удал" in capsys.readouterr().out
    with workspace.use(root):
        assert validate_first_name("Лукас") is False
    # Removed once more, the row of the layer is deleted and the name is the base's again.
    assert _run(root, "remove", "--gender", "М", "--name", "Лукас") == 0
    assert _rows(root, "names.tsv") == []
    with workspace.use(root):
        assert validate_first_name("Лукас") is True


def test_remove_of_a_name_no_layer_holds_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей") == 1
    assert "Зюзей" in capsys.readouterr().err and _rows(root, "names.tsv") == []


def test_remove_warns_when_used(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Зюзей is written by two records of the corpus (the child and father of one, the father of another)…"""
    root = _workspace(tmp_path, corpus=True)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик") == 0
    capsys.readouterr()
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей") == 0     # a warning, never a refusal
    assert "2 записях" in capsys.readouterr().err
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзик") == 0     # written «Зюзикъ»: the old spelling counts
    assert "1 записи" in capsys.readouterr().err
    assert _rows(root, "names.tsv") == []


def test_remove_says_which_names_lose_their_base(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--base", "Зюзей") == 0
    capsys.readouterr()
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей") == 0
    err = capsys.readouterr().err
    assert "Зюзик" in err and "LEX003" in err


def test_remove_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    before = {p.name: p.read_bytes() for p in (root / "names").iterdir()}
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей", "--dry-run") == 0
    assert {p.name: p.read_bytes() for p in (root / "names").iterdir()} == before


def test_check_reads_the_writable_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей") == 0
    assert _run(root, "add", "--gender", "М", "--name", "Иван", "--base", "Иоанн") == 0     # LEX005: advice
    capsys.readouterr()
    assert _run(root, "check") == 0
    out = capsys.readouterr().out
    assert "LEX005" in out and "names/names.tsv" in out
    # A hand-written row with a base nothing holds is a hard finding.
    (root / "names" / "names.tsv").write_text(
        "sex\tname\tbases\tcanonical\tsource\tnote\nM\tЗюзик\tНету\t\teditor\t\n", encoding="utf-8")
    assert _run(root, "check") == 1
    assert "LEX003" in capsys.readouterr().out
    assert _run(root, "check", "--layer", str(root / "names")) == 1
    assert _run(root, "check", "--layer", str(tmp_path)) == 1                    # not a layer of the workspace


def test_check_all_reads_the_base_and_the_sum(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "check", "--all") == 0
    assert "base, names" in capsys.readouterr().out


def test_dangling_base_after_upgrade(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """A layer written over an old base leans on a name the new base lacks: it loads, `check` says LEX003 naming the layer
    and the name, and the lookup answers for the variant as for a name with no base."""
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--base", "Иоанн") == 0
    with workspace.use(root):
        assert matching_base("Зюзик", M) == "Иоанн"                   # over the base as it is today
    new_base = tmp_path / "newbase"
    new_base.mkdir()
    FilesLayer(new_base, name="base", writable=True).put(NameEntry(M, "Зюзий", source="editor"))
    monkeypatch.setitem(layers.BASES, "ru", lambda: FilesLayer(new_base, name="base", writable=False))
    names_registry.reload()
    capsys.readouterr()
    with workspace.use(root):
        assert current_lexicon().layers == ("base", "names")          # the load passes
        assert matching_base("Зюзик", M) == "Зюзик"                   # as a name with no base
        assert validate_first_name("Зюзик") is True
    assert _run(root, "check") == 1
    out = capsys.readouterr().out
    assert "LEX003" in out and "Зюзик" in out and "names/names.tsv" in out


def test_explain_says_which_layer_answered(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--genitive", "Зюзея-я") == 0
    capsys.readouterr()
    assert _run(root, "explain", "Зюзей", "--gender", "М") == 0
    out = capsys.readouterr().out
    assert 'genitive_given_name(Зюзей, M) = "Зюзея-я"' in out
    assert 'derive_patronymic(Зюзей, M) = "Зюзеевич"' in out
    assert 'derive_old_patronymic(Зюзей, F) = "Зюзеева"' in out
    assert "names: names.tsv М Зюзей" in out and "genitive = Зюзея-я [names]" in out     # the layer's own cell
    assert "patronymic_m = Зюзеевич [правило]" in out                                      # the rule's
    assert out.count("forms М Зюзей") == 5                  # once a function that reads a form, not under every one
    capsys.readouterr()
    assert _run(root, "explain", "Иван") == 0
    out = capsys.readouterr().out
    assert 'canonicalize_name(Иван, M) = "Иоанн"' in out and "base: names.tsv М Иван → Иоанн" in out
    assert _run(root, "explain", "Нетакогоимени") == 0
    assert "ни один слой не держит" in capsys.readouterr().out


def test_explain_reads_the_old_tables_of_a_schema_5_workspace(legacy_workspace: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(legacy_workspace, "explain", "Агап") == 0
    out = capsys.readouterr().out
    assert "legacy: names.tsv" in out


def test_add_and_remove_write_only_the_writable_layer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--layer` may name the writable layer alone: another layer of `[names] layers` is refused, naming the writable one,
    and its files stay as they were."""
    root = _workspace(tmp_path, read_only=True)
    FilesLayer(root / "below", name="below", writable=True).put(NameEntry(M, "Зюзей", source="editor"))
    before = {p.name: p.read_bytes() for p in (root / "below").iterdir()}
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--layer", str(root / "below")) == 1
    err = capsys.readouterr().err
    assert "names" in err and "below" in err
    assert _run(root, "remove", "--gender", "М", "--name", "Зюзей", "--layer", str(root / "below")) == 1
    assert {p.name: p.read_bytes() for p in (root / "below").iterdir()} == before
    assert _rows(root, "names.tsv") == []
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик", "--layer", str(root / "names")) == 0   # the writable one
    assert _run(root, "check", "--layer", str(root / "below")) == 0                                      # reading is free


def test_a_broken_layer_is_said_not_a_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """A layer file the lexicon cannot read (`LayerFileError`) and two derivations of one key (`LexiconConflict`) are an
    `error:` line and exit 1 in every command, with the file or the key named."""
    root = _workspace(tmp_path)
    (root / "names" / "names.tsv").write_text("sex\tname\n", encoding="utf-8")
    for argv in (("add", "--gender", "М", "--name", "Зюзей"), ("remove", "--gender", "М", "--name", "Зюзей"),
                 ("check",), ("explain", "Зюзей")):
        assert _run(root, *argv) == 1
        err = capsys.readouterr().err
        assert err.startswith("error:") and "names.tsv" in err and "Traceback" not in err
    ok = _workspace(tmp_path / "ok")

    def conflict(*_: object, **__: object) -> None:
        raise LexiconConflict(("old_m", "Зюзин"), ["Зюзей", "Зюзий"])

    monkeypatch.setattr(cli.edit, "findings_of", conflict)
    assert _run(ok, "add", "--gender", "М", "--name", "Зюзей") == 1
    err = capsys.readouterr().err
    assert err.startswith("error:") and "Зюзин" in err


def test_add_writes_both_files_or_neither(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A name with forms is two files: both are staged under temporary names before either is renamed, so a write that
    fails leaves the layer as it was."""
    root = _workspace(tmp_path)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзик") == 0
    before = {p.name: p.read_bytes() for p in (root / "names").iterdir()}
    real = layer_files.stage_table
    calls: list[str] = []

    def failing(directory: Path, table: str, rows: list[dict[str, str]]) -> Path:
        calls.append(table)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(directory, table, rows)  # type: ignore[arg-type]

    monkeypatch.setattr(layer_files, "stage_table", failing)
    with pytest.raises(OSError, match="disk full"):
        _run(root, "add", "--gender", "М", "--name", "Зюзей", "--genitive", "Зюзея-я")
    assert {p.name: p.read_bytes() for p in (root / "names").iterdir()} == before   # no half, no .tmp left
    monkeypatch.setattr(layer_files, "stage_table", real)
    assert _run(root, "add", "--gender", "М", "--name", "Зюзей", "--genitive", "Зюзея-я") == 0
    assert len(_rows(root, "names.tsv")) == 2 and len(_rows(root, "forms.tsv")) == 1


def test_a_legacy_workspace_ignored_name_derives_nothing(legacy_workspace: Path) -> None:
    """The old tables answer as they always did: a name of the ignore list has no genitive and no short patronymic from any
    rule (the layers that derive leave the ignore marker's names out the same way)."""
    from verso.ru.naming.names_registry import genitive_from_name, is_ignored_name
    from verso.ru.naming.patronymics import derive_old_patronymic
    ignored = [line.split(",")[1] for line in (legacy_workspace / "names_ignore.csv").read_text(
        encoding="utf-8").splitlines()[1:] if line]
    assert ignored
    with workspace.use(legacy_workspace):
        assert current_lexicon().layers == ("legacy",)
        for name in ignored:
            assert is_ignored_name(name)
            assert genitive_from_name(name) is None and derive_old_patronymic(name, M) == ""
            assert current_lexicon().forms_of(M, name) is None and current_lexicon().forms_of(F, name) is None
