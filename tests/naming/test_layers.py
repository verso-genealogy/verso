"""A workspace's names lexicon as `[names]` says: schema ≤ 5 the old tables alone, schema 6 the base and layers.

Every workspace of schema 6 here is written into tmp_path; its layers hold invented names (Зюзей, Зюзя).
"""
from __future__ import annotations

import os
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from verso.core import workspace
from verso.core.messages import t as core_t
from verso.ru.gender import Gender
from verso.ru.messages import t
from verso.ru.naming import names_registry
from verso.ru.naming.layer_files import BASE, FilesLayer
from verso.ru.naming import layers
from verso.ru.naming.layers import provided, sources
from verso.ru.naming.legacy import LegacyTables
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, NameEntry
from verso.ru.naming.names_registry import current_lexicon, matching_base
from verso.ru.naming.validation import validate_first_name

M, F = Gender.MALE, Gender.FEMALE


@pytest.fixture(autouse=True)
def forgotten() -> Iterator[None]:
    names_registry.reload()
    yield
    names_registry.reload()


def _workspace(root: Path, names: str = "", schema: int = 6) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "verso.toml").write_text(f'schema = {schema}\nplugins = ["ru"]\n{names}', encoding="utf-8")
    return root


def _layer(directory: Path, *entries: NameEntry | FormsEntry) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    layer = FilesLayer(directory, name=directory.name, writable=True)
    for entry in entries:
        layer.put(entry)
    return directory


def _base_names() -> str:
    return (BASE / "names.tsv").read_text(encoding="utf-8")


def test_schema5_reads_legacy_alone(legacy_workspace: Path) -> None:
    """A workspace of schema ≤ 5 is its old table and nothing under it: a name the base knows and the table does
    not stays unknown."""
    assert "\tЛукас\t" in _base_names()
    assert "Лукас" not in (legacy_workspace / "names.csv").read_text(encoding="utf-8")
    with workspace.use(legacy_workspace):
        assert workspace.current().names_layers is None
        assert [type(s) for s in sources(workspace.current())] == [LegacyTables]
        assert validate_first_name("Лукас") is False
        assert current_lexicon().layers == ("legacy",)


def test_schema6_default_is_base(tmp_path: Path) -> None:
    with workspace.use(_workspace(tmp_path)):
        assert current_lexicon().layers == ("base",)
        assert validate_first_name("Иоанн") is True
        assert matching_base("Иван", M) == "Иоанн"


def test_schema6_layers_order(tmp_path: Path) -> None:
    """Two layers with one key: the upper answers; a key the upper layer lacks the lower one answers."""
    low = _layer(tmp_path / "low", NameEntry(M, "Зюзей", source="editor"), NameEntry(M, "Зюзий", source="editor"),
                 NameEntry(M, "Зюзя", ("Зюзей",), source="editor"), NameEntry(F, "Зюзея", ("Зюзия",), source="editor"), NameEntry(F, "Зюзия", source="editor"))
    top = _layer(tmp_path / "top", NameEntry(M, "Зюзя", ("Зюзий",), source="editor"))
    with workspace.use(_workspace(tmp_path, f'[names]\nlayers = ["{low.name}", "{top.name}"]\n')):
        assert current_lexicon().layers == ("base", "low", "top")
        assert matching_base("Зюзя", M) == "Зюзий"
        assert matching_base("Зюзея", F) == "Зюзия"
        assert matching_base("Иван", M) == "Иоанн"  # the base under both


def test_schema6_without_a_base(tmp_path: Path) -> None:
    layer = _layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(_workspace(tmp_path, '[names]\nbase = false\nlayers = ["names"]\n')):
        assert current_lexicon().layers == ("names",)
        assert validate_first_name("Зюзей") is True
        assert validate_first_name("Иоанн") is False
    assert layer.is_dir()


def test_schema6_rejects_dir(tmp_path: Path) -> None:
    root = _workspace(tmp_path, '[names]\ndir = "."\n')
    with pytest.raises(workspace.WorkspaceError) as caught:
        workspace.load(root)
    assert str(caught.value) == str(core_t("workspace.names_dir_schema_6", path=root.resolve() / "verso.toml"))


def test_writable_marks_the_layer_named(tmp_path: Path) -> None:
    _layer(tmp_path / "low")
    _layer(tmp_path / "top")
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["low", "top"]\nwritable = "low"\n')) as ws:
        assert [(s.name, s.writable) for s in sources(ws)] == [("base", False), ("low", True), ("top", False)]
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["low", "top"]\n')) as ws:
        assert [(s.name, s.writable) for s in sources(ws)] == [("base", False), ("low", False), ("top", True)]


def test_a_writable_that_names_no_layer_is_refused(tmp_path: Path) -> None:
    _layer(tmp_path / "low")
    root = _workspace(tmp_path, '[names]\nlayers = ["low"]\nwritable = "elsewhere"\n')
    with pytest.raises(workspace.WorkspaceError, match=r"«names\.writable» — elsewhere нет среди «names\.layers»"):
        workspace.load(root)


def test_an_unknown_base_is_refused_at_the_first_lookup(tmp_path: Path) -> None:
    with workspace.use(_workspace(tmp_path, '[names]\nbase = "xx"\n')), \
            pytest.raises(workspace.WorkspaceError, match="нет базы «xx»: одна из ru или false"):
        validate_first_name("Иоанн")


def test_a_missing_layer_directory_is_refused(tmp_path: Path) -> None:
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["nowhere"]\n')), \
            pytest.raises(workspace.WorkspaceError, match="слой имён «nowhere»: нет каталога"):
        validate_first_name("Иоанн")


def test_a_layer_of_the_old_table_is_read_with_a_deprecation_warning(tmp_path: Path) -> None:
    old = tmp_path / "old"
    old.mkdir()
    (old / "names.csv").write_text(
        "Пол,Имя,Имя-основа,От,\"Склонения, связи\",Родительный падеж,Отчество старое М,Отчество старое Ж,"
        "Отчество М,Отчество Ж,Источник\nМ,Зюзей,,,,Зюзея,Зюзеев,Зюзеева,Зюзеевич,Зюзеевна,\n", encoding="utf-8")
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["old"]\n')):
        with pytest.warns(DeprecationWarning) as caught:
            assert validate_first_name("Зюзей") is True
        assert [w.category for w in caught] == [DeprecationWarning]
        assert str(caught[0].message) == str(t("names_layers.legacy_layer", layer="old", path=old / "names.csv"))
        assert current_lexicon().layers == ("base", "old")
        assert validate_first_name("Иоанн") is True  # the base under it


def test_a_layer_of_three_files_warns_nothing(tmp_path: Path) -> None:
    _layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["names"]\n')), warnings.catch_warnings():
        warnings.simplefilter("error")
        assert validate_first_name("Зюзей") is True


def test_the_loaded_sum_answers_the_reverse_lookups(tmp_path: Path) -> None:
    """A sum over deriving layers answers a reverse lookup on its first use, though the loader built none."""
    _layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["names"]\n')):
        lexicon = current_lexicon()
        assert lexicon.old_m["Зюзеев"].father == "Зюзей"  # the rule's short form of a layer's name
        assert names_registry.father_name_for_patronymic("Зюзеевич") == "Зюзей"


def test_with_layer_answers_the_reverse_lookups(tmp_path: Path) -> None:
    layer = FilesLayer(_layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor")), name="names",
                       writable=False).load()
    lexicon = Lexicon.of([]).with_layer(layer)
    assert lexicon.old_m["Зюзеев"].father == "Зюзей"


def test_a_changed_layer_file_is_read_again(tmp_path: Path) -> None:
    directory = _layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(_workspace(tmp_path, '[names]\nlayers = ["names"]\n')):
        assert validate_first_name("Зюзий") is False
        FilesLayer(directory, name="names", writable=True).put(NameEntry(M, "Зюзий", source="editor"))
        names_registry.reload()
        assert validate_first_name("Зюзий") is True


def test_answering_holds_a_lexicon_and_gives_the_workspace_back(tmp_path: Path) -> None:
    layer = FilesLayer(_layer(tmp_path / "names", NameEntry(M, "Зюзей", source="editor")), name="names",
                       writable=False).load()
    assert validate_first_name("Зюзей") is False
    with names_registry.answering(Lexicon.of([layer])):
        assert validate_first_name("Зюзей") is True
        with names_registry.asked() as keys:
            matching_base("Зюзей", M)
        assert ("name", "Зюзей") in keys
    assert validate_first_name("Зюзей") is False


def test_a_no_form_cell_is_not_filled_by_the_rules(tmp_path: Path) -> None:
    """`-` in a forms cell: the name has no such form — the rules do not fill it, no reverse index holds one, and a
    lookup reads the cell as the old table's empty one (`derive_old_patronymic` falls back on the short form of the
    modern patronymic, `derive_patronymic` on the rule)."""
    directory = tmp_path / "names"
    directory.mkdir()
    (directory / "names.tsv").write_text("sex\tname\tbases\tcanonical\tsource\tnote\nM\tЗюзей\t\t\tlegacy\t\n",
                                         encoding="utf-8")
    (directory / "forms.tsv").write_text("sex\tname\tgenitive\tpatronymic_m\tpatronymic_f\told_patronymic_m\t"
                                         "old_patronymic_f\tsource\nM\tЗюзей\t\t-\t\t-\t\tlegacy\n", encoding="utf-8")
    layer = FilesLayer(directory, name="names", writable=True)
    fe = layer.load().forms[(M, "Зюзей")]
    assert (fe.patronymic_m, fe.old_patronymic_m, fe.old_patronymic_f) == ("", "", None)
    with workspace.use(_workspace(tmp_path, '[names]\nbase = false\nlayers = ["names"]\n')):
        lexicon = current_lexicon()
        assert "Зюзеев" not in lexicon.old_m and "Зюзеевич" not in lexicon.modern_m
        assert "Зюзеева" in lexicon.old_f                                  # the cell not written: the rule's
        assert names_registry.father_name_for_patronymic("Зюзеев") is None
        from verso.ru.naming.patronymics import derive_old_patronymic, derive_patronymic
        assert derive_patronymic("Зюзей", M) == "Зюзеевич"                # the caller's own fallback, the rule
        assert derive_old_patronymic("Зюзей", M) == ""
    # Written back as it was read.
    layer.put(fe._replace(genitive="Зюзея"))
    assert "\tЗюзея\t-\t\t-\t" in (directory / "forms.tsv").read_text(encoding="utf-8")


def test_a_removal_takes_its_key_out_of_the_stack(tmp_path: Path) -> None:
    """`-` in a names row's bases: the (sex, name) does not exist in this stack — the lower layer's entry of that key
    goes, its forms with it, and nothing else of the name."""
    from verso.ru.naming.gender_inference import get_gender_from_name
    from verso.ru.naming.lexicon import Layer
    below = Layer("base", {(M, "Зюзь"): NameEntry(M, "Зюзь", source="mk"),
                           (F, "Зюзь"): NameEntry(F, "Зюзь", ("Зюзия",), source="mk"),
                           (F, "Зюзия"): NameEntry(F, "Зюзия", source="mk")},
                  {(F, "Зюзь"): FormsEntry(F, "Зюзь", "Зюзи", source="editor")}, {}, derives=True)
    directory = tmp_path / "names"
    directory.mkdir()
    (directory / "names.tsv").write_text("sex\tname\tbases\tcanonical\tsource\tnote\nF\tЗюзь\t-\t\tlegacy\t\n",
                                         encoding="utf-8")
    upper = FilesLayer(directory, name="names", writable=True).load()
    assert upper.names[(F, "Зюзь")].removes
    with names_registry.answering(Lexicon.of([below])):
        assert get_gender_from_name("Зюзь") is None and matching_base("Зюзь", F) == "Зюзия"
    lexicon = Lexicon.of([below, upper])
    with names_registry.answering(lexicon):
        assert get_gender_from_name("Зюзь") == M
        assert matching_base("Зюзь", F) == "Зюзь"           # as a name no layer holds in that sex
        assert matching_base("Зюзнь", F) == "Зюзнь"
        assert validate_first_name("Зюзия") is True          # nothing else of the stack moves
    assert (F, "Зюзь") not in lexicon.by_name["Зюзь"].sexed and lexicon.by_name["Зюзь"].forms is None


def test_an_unknown_base_is_refused_where_names_are_asked_for(tmp_path: Path) -> None:
    """`names_table_present` says «no lexicon» for no base and no layer, and refuses a base no plugin ships: a
    mistyped `[names] base` is the workspace's error, not a workspace without names."""
    from verso.ru.linters.on_json.walk import names_table_present
    with workspace.use(_workspace(tmp_path / "a", '[names]\nbase = "xx"\n')), \
            pytest.raises(workspace.WorkspaceError, match="нет базы «xx»: одна из ru или false"):
        names_table_present()
    with workspace.use(_workspace(tmp_path / "b")):
        assert names_table_present()
    with workspace.use(_workspace(tmp_path / "c", "[names]\nbase = false\n")):
        assert not names_table_present()


def test_an_ignored_name_derives_no_forms() -> None:
    """A name whose source is the ignore marker is known and not validated: a deriving layer gives it no genitive and no
    patronymics by rule (as the old ignore list did not), where a name of any other source gets them."""
    from verso.ru.naming.genitive import genitive_given_name
    from verso.ru.naming.lexicon import IGNORE_LIST, Layer
    from verso.ru.naming.names_registry import genitive_from_name, is_ignored_name, name_from_genitive
    from verso.ru.naming.patronymics import derive_old_patronymic, derive_patronymic
    layer = Layer("corpus", {(M, "Зюзей"): NameEntry(M, "Зюзей", source=IGNORE_LIST),
                             (F, "Зюзея"): NameEntry(F, "Зюзея", source=IGNORE_LIST),
                             (M, "Зюзик"): NameEntry(M, "Зюзик", source="editor")}, {}, {}, derives=True)
    lexicon = Lexicon.of([layer]).complete()
    assert lexicon.forms_of(M, "Зюзей") is None and lexicon.forms_of(F, "Зюзея") is None
    assert lexicon.forms_of(M, "Зюзик") is not None and lexicon.forms_of(M, "Зюзик").genitive == "Зюзика"  # type: ignore[union-attr]
    assert "Зюзея" not in lexicon.genitive and "Зюзика" in lexicon.genitive
    assert "Зюзеев" not in lexicon.old_m and "Зюзиков" in lexicon.old_m
    with names_registry.answering(lexicon):
        assert is_ignored_name("Зюзей") and genitive_from_name("Зюзей") is None
        assert genitive_from_name("Зюзик") == "Зюзика" and name_from_genitive("Зюзика") == "Зюзик"
        assert derive_old_patronymic("Зюзей", M) == "" and derive_patronymic("Зюзей", M) == "Зюзеевич"
        assert genitive_given_name("Зюзей", M) == "Зюзея"       # the caller's fallback is the rule, as for any unknown
        assert derive_old_patronymic("Зюзик", M) == "Зюзиков"
    # What a layer writes of an ignored name itself stands.
    own = Layer("corpus", {(M, "Зюзей"): NameEntry(M, "Зюзей", source=IGNORE_LIST)},
                {(M, "Зюзей"): FormsEntry(M, "Зюзей", "Зюзея")}, {}, derives=True)
    with names_registry.answering(Lexicon.of([own]).complete()):
        assert genitive_from_name("Зюзей") == "Зюзея"


def test_a_name_whose_base_no_layer_holds_answers_as_written(tmp_path: Path) -> None:
    """A layer written over an old base leans on a name the new base lacks: the load passes (the finding is the linter's,
    LEX003), and the lookups answer for the variant as for a name with no base."""
    from verso.ru.naming.names_registry import matching_base
    from verso.ru.naming.orthography import canonicalize_name
    base = tmp_path / "newbase"
    _layer(base, NameEntry(M, "Зюзий", source="editor"))
    user = _layer(tmp_path / "user", NameEntry(M, "Зюзик", ("Зюзей",), source="editor"),
                  NameEntry(M, "Зюзок", ("Зюзий",), source="editor"))
    layer_files = FilesLayer(base, name="base", writable=False)
    lexicon = Lexicon.of([layer_files.load(), FilesLayer(user, name="user", writable=True).load()]).complete()
    with names_registry.answering(lexicon):
        assert matching_base("Зюзик", M) == "Зюзик" and canonicalize_name("Зюзик", M) == "Зюзик"
        assert matching_base("Зюзок", M) == "Зюзий"          # a base the stack holds still folds


def test_a_workspace_entered_again_keeps_its_lexicon_and_a_changed_layer_does_not(tmp_path: Path) -> None:
    """A switch of workspace does not rebuild the sum of the base and the layers: the lexicon built from the same
    sources (their identity and their stamps) is the one answered; a layer's file changed makes another."""
    one = _workspace(tmp_path / "one", '[names]\nlayers = ["names"]\n')
    two = _workspace(tmp_path / "two", '[names]\nlayers = ["names"]\n')
    for root in (one, two):
        _layer(root / "names", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(one):
        first = current_lexicon()
    with workspace.use(two):
        assert current_lexicon() is not first                    # another directory, another lexicon
    with workspace.use(one):
        assert current_lexicon() is first                        # the same one, not built again
        (one / "names" / "forms.tsv").write_text(
            "sex\tname\tgenitive\tpatronymic_m\tpatronymic_f\told_patronymic_m\told_patronymic_f\tsource\n"
            "M\tЗюзей\tЗюзея-я\t\t\t\t\teditor\n", encoding="utf-8")
        names_registry.reload()
        assert current_lexicon() is not first


def _write_names(directory: Path, name: str) -> None:
    (directory / "names.tsv").write_text(f"sex\tname\tbases\tcanonical\tsource\tnote\nM\t{name}\t\t\teditor\t\n",
                                         encoding="utf-8")


def test_reload_rebuilds_whatever_the_stamps_say(tmp_path: Path) -> None:
    """A rewrite of the same size that leaves the file's mtime as it was (a coarse clock) shows in no stamp; `reload()` is
    the caller's word that the files changed, and the next lookup builds the lexicon again."""
    root = _workspace(tmp_path, '[names]\nlayers = ["names"]\n')
    layer = root / "names"
    layer.mkdir()
    _write_names(layer, "Зюзяк")
    with workspace.use(root):
        assert validate_first_name("Зюзяк") is True and validate_first_name("Зюзяч") is False
        before = (layer / "names.tsv").stat()
        _write_names(layer, "Зюзяч")
        os.utime(layer / "names.tsv", ns=(before.st_atime_ns, before.st_mtime_ns))
        assert (layer / "names.tsv").stat().st_size == before.st_size
        names_registry.reload()
        assert validate_first_name("Зюзяч") is True and validate_first_name("Зюзяк") is False


def test_a_layer_edited_leaves_one_lexicon_kept_for_its_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each edit makes a new stamp and so a new key; the lexicon of the older stamp can never be asked again and is dropped,
    so a process that edits a layer all day holds one lexicon of that workspace, not eight."""
    root = _workspace(tmp_path, '[names]\nlayers = ["names"]\n')
    layer = root / "names"
    layer.mkdir()
    _write_names(layer, "Зюзяк")
    monkeypatch.setattr(names_registry, "RECHECK_SECONDS", 0.0)
    with workspace.use(root):
        for name in ("Зюзяк", "Зюзяка", "Зюзякаа", "Зюзякааа"):
            _write_names(layer, name)
            assert validate_first_name(name) is True
        mine = [k for k in names_registry._built_lexicons if any(  # pyright: ignore[reportPrivateUsage]
            isinstance(i, tuple) and i[-1] == str(layer) for i in k[0])]
        assert len(mine) == 1


class _Rows:
    """A host's layer: its entries in memory, a stamp that moves with each write, an identity of its own."""

    writable = True

    def __init__(self, name: str, identity: object, *entries: NameEntry) -> None:
        self.name = name
        self.identity = identity
        self.entries = list(entries)
        self.stamp_n = 0
        self.loaded = 0

    def stamp(self) -> str:
        return str(self.stamp_n)

    def load(self) -> Layer:
        self.loaded += 1
        return Layer(self.name, {e.key: e for e in self.entries}, {}, {}, writable=True, derives=True)

    def put(self, entry: object) -> None:  # noqa: ARG002 — the port's signature
        raise TypeError("a test's layer is written by the test")

    def remove(self, table: object, key: object) -> None:  # noqa: ARG002 — the port's signature
        raise TypeError("a test's layer is written by the test")


def test_a_provided_layer_stands_in_the_place_of_its_directory(tmp_path: Path) -> None:
    """`[names] layers` names a directory that does not exist; the host's source is read in its place, in the stack's
    order, and gone when the block ends."""
    root = _workspace(tmp_path, '[names]\nlayers = ["names"]\n')
    host = _Rows("names", "one", NameEntry(M, "Зюзей", source="editor"))
    with workspace.use(root):
        with pytest.raises(workspace.WorkspaceError):
            sources(workspace.current())                        # no directory, no layer
        with provided((root / "names").resolve(), host):
            stack = sources(workspace.current())
            assert [s.name for s in stack] == ["base", "names"] and stack[1] is host
            assert validate_first_name("Зюзей") is True
        assert (root / "names").resolve() not in layers._PROVIDED  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(workspace.WorkspaceError):
            sources(workspace.current())


def test_a_provided_layer_with_an_identity_keeps_its_lexicon_between_workspaces(tmp_path: Path) -> None:
    """The base's ten thousand names are not summed again when a host switches between workspaces: a source that names
    its identity is kept by it and its stamp; a write moves the stamp, and the next lookup reads it again."""
    one = _workspace(tmp_path / "one", '[names]\nlayers = ["names"]\n')
    two = _workspace(tmp_path / "two", '[names]\nlayers = ["names"]\n')
    host_one = _Rows("names", "one", NameEntry(M, "Зюзей", source="editor"))
    host_two = _Rows("names", "two", NameEntry(M, "Зюзяк", source="editor"))
    with provided((one / "names").resolve(), host_one), provided((two / "names").resolve(), host_two):
        with workspace.use(one):
            first = current_lexicon()
        with workspace.use(two):
            assert current_lexicon() is not first
            assert validate_first_name("Зюзяк") is True and validate_first_name("Зюзей") is False
        with workspace.use(one):
            assert current_lexicon() is first and host_one.loaded == 1   # kept, not read again
            host_one.entries.append(NameEntry(M, "Зюзяка", source="editor"))
            host_one.stamp_n += 1
            names_registry.reload()
            assert validate_first_name("Зюзяка") is True


def test_provided_nests_and_is_gone_after_an_exception(tmp_path: Path) -> None:
    """The same directory provided twice (a nested entry of the workspace): the inner source stands inside and the outer is back
    after; an exception in the block leaves no source provided."""
    root = _workspace(tmp_path, '[names]\nlayers = ["names"]\n')
    directory = (root / "names").resolve()
    outer, inner = _Rows("names", "outer"), _Rows("names", "inner")
    with workspace.use(root), provided(directory, outer):
        with provided(directory, inner):
            assert sources(workspace.current())[1] is inner
        assert sources(workspace.current())[1] is outer
        with pytest.raises(RuntimeError), provided(directory, inner):
            raise RuntimeError
        assert sources(workspace.current())[1] is outer
    assert directory not in layers._PROVIDED  # pyright: ignore[reportPrivateUsage]


def test_a_source_without_an_identity_is_not_kept_and_a_typo_of_it_is_not_one() -> None:
    from verso.ru.naming.lexicon import IdentifiedSource
    assert isinstance(_Rows("names", "x"), IdentifiedSource)
    assert not isinstance(FilesLayer(Path("."), name="x", writable=False), IdentifiedSource)


def test_invalidate_drops_one_hosts_kept_lexicons_and_no_other(tmp_path: Path) -> None:
    """A host that wrote its layer says so by its identity: that layer's lexicon is built again, the lexicon of another host's layer
    and of a directory is not (`reload()` drops them all)."""
    one = _workspace(tmp_path / "one", '[names]\nlayers = ["names"]\n')
    two = _workspace(tmp_path / "two", '[names]\nlayers = ["names"]\n')
    three = _workspace(tmp_path / "three", '[names]\nlayers = ["names"]\n')
    _layer(three / "names", NameEntry(M, "Зюзей", source="editor"))
    host_one, host_two = _Rows("names", "one"), _Rows("names", "two")
    with provided((one / "names").resolve(), host_one), provided((two / "names").resolve(), host_two):
        kept = {}
        for name, root in (("one", one), ("two", two), ("three", three)):
            with workspace.use(root):
                kept[name] = current_lexicon()
        host_one.entries.append(NameEntry(M, "Зюзя", source="editor"))
        host_one.stamp_n += 1
        names_registry.invalidate("one")
        for name, root in (("one", one), ("two", two), ("three", three)):
            with workspace.use(root):
                again = current_lexicon()
            assert (again is kept[name]) == (name != "one"), name
        with workspace.use(one):
            assert validate_first_name("Зюзя") is True
