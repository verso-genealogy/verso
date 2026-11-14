"""tools/layers.py — the library's layers (tools/layers.toml), held to the tree.

Every test but the first builds a toy tree in `tmp_path` with a toy table: no
village and no module of the real package is read there."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import layers

ROOT = Path(__file__).resolve().parent.parent.parent    # the library's root: lib/, or verso's

TOY = """\
schema = 2
[[tier]]
name = "low"
packages = ["verso.ru", "verso.ru.a"]
[[tier]]
name = "mid"
packages = ["verso.ru.b", "verso.ru.c"]
[[tier]]
name = "top"
packages = ["verso.ru.cli"]
[overrides]
"verso.ru.b.tool" = "top"
"""


def toy(tmp_path: Path, files: dict[str, str], allowlist: str | None = None, table: str = TOY) -> Path:
    """A tree with every package of the toy table and the module its [overrides] places,
    `files` on top, the table and (when given) the allowlist."""
    for package in ("verso/ru", "verso/ru/a", "verso/ru/b", "verso/ru/c", "verso/ru/cli"):
        (tmp_path / package).mkdir(parents=True, exist_ok=True)
        (tmp_path / package / "__init__.py").write_text("", encoding="utf-8")
    for rel, text in {"verso/ru/b/tool.py": "", **files}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / "tools" / "layers.toml").write_text(table, encoding="utf-8")
    if allowlist is not None:
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "layering_allowlist.txt").write_text(allowlist, encoding="utf-8")
    return tmp_path


def messages(root: Path) -> str:
    return "\n".join(layers.check(root))


# ---------------------------------------------------------------- the tree itself


def test_the_tree_keeps_its_layers():
    assert layers.check(ROOT) == []


def test_the_table_and_the_tree_agree():
    """The real tree: no module without a tier, no violation but LAY006's, and those the
    allowlist's lines, no more."""
    table = layers.read_table(ROOT / layers.TABLE)
    assert layers.table_problems(ROOT, table) == []
    found = layers.violations(ROOT, table)
    assert [v.message for v in found if v.code != "LAY006"] == []
    allowed = layers.read_allowlist((ROOT / layers.ALLOWLIST).read_text(encoding="utf-8"))
    assert sorted(v.key for v in found if v.code == "LAY006") == sorted(allowed)


# ---------------------------------------------------------------- the table


def test_a_module_under_no_package_is_refused(tmp_path: Path):
    """A side's root package (`verso.ru`) is its own `__init__` alone: a module put straight
    under it, or under a package no tier lists, names its tier itself."""
    root = toy(tmp_path, {"verso/ru/newpkg/x.py": "", "verso/ru/loose.py": ""})
    text = messages(root)
    assert "verso.ru.newpkg.x: нет слоя — впишите пакет в tools/layers.toml" in text
    assert "verso.ru.loose: нет слоя — впишите пакет в tools/layers.toml" in text


def test_a_module_belongs_to_the_longest_package_listed(tmp_path: Path):
    table = TOY.replace('packages = ["verso.ru.cli"]', 'packages = ["verso.ru.cli", "verso.ru.b.deep"]')
    root = toy(tmp_path, {"verso/ru/b/deep/__init__.py": "", "verso/ru/b/deep/x.py": "import verso.ru.c.z\n",
                          "verso/ru/b/y.py": "import verso.ru.c.z\n", "verso/ru/c/z.py": ""}, table=table)
    assert layers.read_table(root / layers.TABLE).tier_name("verso.ru.b.deep.x") == "top"
    assert layers.check(root) == [
        "verso.ru.b.y (mid) → verso.ru.c.z (mid): ребро вверх или вбок — см. tools/layers.toml"]


def test_a_tier_naming_a_missing_package_is_named(tmp_path: Path):
    root = toy(tmp_path, {}, table=TOY.replace('"verso.ru.b", "verso.ru.c"', '"verso.ru.b", "verso.ru.c", "verso.ru.gone"'))
    assert "tools/layers.toml: пакета verso.ru.gone нет" in messages(root)


def test_a_schema_1_table_is_refused(tmp_path: Path):
    """Until 0.1.0 the table spoke in the old names; the moves of 0.1.0 have none."""
    import pytest
    root = toy(tmp_path, {}, table=TOY.replace("schema = 2", "schema = 1"))
    with pytest.raises(layers.LayersError, match=r"^tools/layers.toml: schema 1 — старые имена; с 0.1.0 таблица в новых \(schema 2\)$"):
        layers.read_table(root / layers.TABLE)


# ---------------------------------------------------------------- LAY001


def test_an_import_of_the_cli_is_refused(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "from verso.ru.cli.y import z\n", "verso/ru/cli/y.py": "z = 1\n"})
    text = messages(root)
    assert "verso.ru.a.x: verso.ru.cli.y — CLI не импортируют; возьмите из verso.core.pipeline или перенесите в библиотеку" in text
    assert "LAY002" not in text and "→ verso.ru.cli.y" not in text        # one edge, one finding


def test_a_string_naming_the_cli_is_refused_but_a_docstring_is_not(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": '"""Run verso.ru.cli.y by hand."""\nCMD = "python -m verso.ru.cli.y"\n',
                          "verso/ru/cli/y.py": ""})
    assert layers.check(root) == [
        "verso.ru.a.x: verso.ru.cli.y — CLI не импортируют; возьмите из verso.core.pipeline или перенесите в библиотеку"]


def test_the_cli_may_import_the_cli(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/cli/x.py": "from verso.ru.cli import y\n", "verso/ru/cli/y.py": ""})
    assert layers.check(root) == []


def test_verso_may_not_import_the_cli_either(tmp_path: Path):
    root = toy(tmp_path, {"verso/app_dsl/__init__.py": "", "verso/app_dsl/s.py": "def f():\n    from verso.ru.cli.y import z\n",
                          "verso/ru/cli/y.py": "z = 1\n"})
    assert "verso.app_dsl.s: verso.ru.cli.y — CLI не импортируют" in messages(root)


# ---------------------------------------------------------------- LAY002


def test_an_edge_up_or_sideways_is_refused(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\n", "verso/ru/b/y.py": "import verso.ru.c.z\n",
                          "verso/ru/c/z.py": ""})
    text = messages(root)
    assert "verso.ru.a.x (low) → verso.ru.b.y (mid): ребро вверх или вбок — см. tools/layers.toml" in text
    assert "verso.ru.b.y (mid) → verso.ru.c.z (mid): ребро вверх или вбок" in text


def test_an_edge_down_and_inside_a_package_is_allowed(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/b/x.py": "from verso.ru.a import y\nfrom verso.ru.b.z import w\nfrom . import z\n",
                          "verso/ru/a/y.py": "", "verso/ru/b/z.py": "w = 1\n"})
    assert layers.check(root) == []


def test_a_function_level_import_counts_and_a_type_checking_one_does_not(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "def f():\n    import verso.ru.b.y\n",
                          "verso/ru/a/t.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import verso.ru.b.y\n",
                          "verso/ru/b/y.py": ""})
    assert layers.check(root) == ["verso.ru.a.x (low) → verso.ru.b.y (mid): ребро вверх или вбок — см. tools/layers.toml"]


def test_an_override_puts_a_module_in_another_tier(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/b/tool.py": "import verso.ru.c.z\n", "verso/ru/c/z.py": ""})
    assert layers.check(root) == []


# ---------------------------------------------------------------- LAY003


def test_a_top_level_cycle_is_refused_but_a_function_level_one_is_not(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.a.y\n", "verso/ru/a/y.py": "import verso.ru.a.x\n",
                          "verso/ru/a/p.py": "def f():\n    import verso.ru.a.q\n", "verso/ru/a/q.py": "import verso.ru.a.p\n"})
    assert layers.check(root) == ["цикл импортов верхнего уровня: verso.ru.a.x → verso.ru.a.y → verso.ru.a.x"]


# ---------------------------------------------------------------- LAY004 (0.1.0)


def test_the_table_refuses_moved(tmp_path: Path):
    """`[moved]` named what a CLI module re-exported until 0.1.0; the re-exports are gone."""
    import pytest
    root = toy(tmp_path, {}, table=TOY + '[moved."verso.ru.cli.facts"]\nconsolidated_facts = "verso.core.pipeline.facts"\n')
    with pytest.raises(layers.LayersError, match=r"\[moved\] снят до 0.1.0"):
        layers.read_table(root / layers.TABLE)


# ---------------------------------------------------------------- the allowlist


def test_an_allowlisted_violation_passes_and_a_stale_line_is_named(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\n", "verso/ru/b/y.py": ""},
               allowlist="# header\nLAY002 verso.ru.a.x -> verso.ru.b.y\nLAY002 verso.ru.a.gone -> verso.ru.b.y\n")
    assert layers.check(root) == [
        "tests/layering_allowlist.txt: «LAY002 verso.ru.a.gone -> verso.ru.b.y» уже не нарушение — "
        "вычеркните: make layering update=1"]


def test_update_seeds_a_missing_list(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\n", "verso/ru/b/y.py": ""})
    assert layers.update(root) == []
    assert "LAY002 verso.ru.a.x -> verso.ru.b.y\n" in (root / layers.ALLOWLIST).read_text(encoding="utf-8")
    assert layers.check(root) == []


def test_update_strikes_lines_and_never_adds_one(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\n", "verso/ru/a/w.py": "import verso.ru.c.z\n",
                          "verso/ru/b/y.py": "", "verso/ru/c/z.py": ""},
               allowlist="LAY002 verso.ru.a.x -> verso.ru.b.y\nLAY002 verso.ru.a.gone -> verso.ru.b.y\n")
    before = (root / layers.ALLOWLIST).read_text(encoding="utf-8")
    assert layers.update(root) == ["--update только вычёркивает: 1 новых нарушений — исправьте код"]
    assert (root / layers.ALLOWLIST).read_text(encoding="utf-8") == before
    (root / "verso" / "ru" / "a" / "w.py").write_text("", encoding="utf-8")
    assert layers.update(root) == []
    lines = [ln for ln in (root / layers.ALLOWLIST).read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    assert lines == ["LAY002 verso.ru.a.x -> verso.ru.b.y"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_base_refuses_a_line_the_base_lacks(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\nimport verso.ru.c.z\n", "verso/ru/b/y.py": "", "verso/ru/c/z.py": ""},
               allowlist="LAY002 verso.ru.a.x -> verso.ru.b.y\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    (root / layers.ALLOWLIST).write_text("LAY002 verso.ru.a.x -> verso.ru.b.y\nLAY002 verso.ru.a.x -> verso.ru.c.z\n", encoding="utf-8")
    assert layers.base_problems("HEAD", root) == [
        "«LAY002 verso.ru.a.x -> verso.ru.c.z» появилась после HEAD — список только убывает"]


def test_a_base_without_the_list_compares_nothing(tmp_path: Path):
    root = toy(tmp_path, {}, allowlist="")
    _git(root, "init", "-q")
    _git(root, "add", "tools")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    assert layers.allowlist_at("HEAD", root) is None
    assert layers.base_problems("HEAD", root) == []


def test_there_is_one_list_of_record_calls():
    """The calls that ARE a record: the ratchet fingerprints them, Verso draws one row each."""
    import ast

    from verso.ru.dsl import calls, describe
    from verso.ru.dsl import signatures
    assert calls.RECORD_FUNCS is describe.RECORD_FUNCS is signatures.RECORD_FUNCS
    assert frozenset(calls.CALLS.calls) == calls.RECORD_FUNCS     # the ratchet's dialect
    # Spelled once: no other module of the library binds the name at its top level (a linter's
    # own class attribute or `_RECORD_FUNCS` is another set).
    spelled = []
    for top in sorted(ROOT.glob("packages/*/src")):
        for path in sorted(top.rglob("*.py")):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
                if any(isinstance(t, ast.Name) and t.id == "RECORD_FUNCS" for t in targets):
                    spelled.append(path.relative_to(ROOT).as_posix())
    # By its source path: under `make standalone` the module is imported from an installed wheel.
    assert spelled == ["packages/verso-ru/src/verso/ru/dsl/calls.py"]


# ---------------------------------------------------------------- the final review's minors


def test_only_a_true_type_checking_branch_is_exempt(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": ("from typing import TYPE_CHECKING\n"
                                             "if not TYPE_CHECKING:\n"
                                             "    import verso.ru.b.y\n"),
                          "verso/ru/a/w.py": ("import typing\n"
                                             "if False:\n"
                                             "    pass\n"
                                             "elif typing.TYPE_CHECKING:\n"
                                             "    import verso.ru.b.y\n"),
                          "verso/ru/b/y.py": ""})
    assert layers.check(root) == ["verso.ru.a.x (low) → verso.ru.b.y (mid): ребро вверх или вбок — см. tools/layers.toml"]


def test_a_name_that_only_starts_like_the_cli_is_not_the_cli(tmp_path: Path):
    root = toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.cliff\n", "verso/ru/cliff.py": "",
                          "verso/ru/cliffs/__init__.py": "", "verso/ru/cliffs/y.py": "import verso.ru.cli.z\n",
                          "verso/ru/cli/z.py": ""},
               table=TOY.replace('packages = ["verso.ru", "verso.ru.a"]',
                                 'packages = ["verso.ru", "verso.ru.a", "verso.ru.cliff", "verso.ru.cliffs"]'))
    text = messages(root)
    assert "verso.ru.a.x: verso.ru.cliff — CLI не импортируют" not in text
    assert "verso.ru.cliffs.y: verso.ru.cli.z — CLI не импортируют" in text


def test_a_tier_without_its_name_or_packages_is_named(tmp_path: Path):
    import pytest
    root = toy(tmp_path, {}, table=TOY.replace('name = "mid"\n', ""))
    with pytest.raises(layers.LayersError, match="слой №2 без «name» или «packages»"):
        layers.read_table(root / layers.TABLE)


# ---------------------------------------------------------------- LAY005

CORPUS_TABLE = TOY + """[corpus]
package = "corpus"
"""


def test_the_library_importing_the_corpus_is_lay005(tmp_path: Path):
    root = toy(tmp_path, {"corpus/__init__.py": "", "corpus/statuses.py": "", "corpus/estates.py": "",
                          "verso/ru/a/statuses.py": "from corpus.statuses import *\n",
                          "verso/ru/b/x.py": "def f():\n    from corpus import estates\n",
                          "verso/app/y.py": "import corpus.statuses\n"},
               table=CORPUS_TABLE)
    assert sorted(layers.check(root)) == [
        "verso.app.y → corpus.statuses: библиотека не импортирует корпус — данные читаются через рабочую "
        "область (verso.core.corpus_data, verso.core.places)",
        "verso.ru.a.statuses → corpus.statuses: библиотека не импортирует корпус — данные читаются через рабочую "
        "область (verso.core.corpus_data, verso.core.places)",
        "verso.ru.b.x → corpus.estates: библиотека не импортирует корпус — данные читаются через рабочую область "
        "(verso.core.corpus_data, verso.core.places)"]


def test_the_corpus_may_import_the_library(tmp_path: Path):
    root = toy(tmp_path, {"corpus/__init__.py": "", "corpus/statuses.py": "from verso.ru.a import m\n", "verso/ru/a/m.py": ""},
               table=CORPUS_TABLE)
    assert layers.check(root) == []


def test_a_bridge_is_refused(tmp_path: Path):
    root = toy(tmp_path, {}, table=CORPUS_TABLE + 'bridge = { "verso.ru.a.statuses" = "corpus.statuses" }\n')
    with pytest.raises(layers.LayersError, match=r"\[corpus\] bridge снят до 0.1.0"):
        layers.read_table(root / layers.TABLE)


def test_the_cli_is_named_in_a_string():
    found = layers._CLI_STRING.findall("python -m verso.ru.cli.facts; verso.core.cli; verso.rux.cli; geni.cli.x")  # pyright: ignore[reportPrivateUsage]
    assert found == ["verso.ru.cli.facts", "verso.core.cli"]


# ---------------------------------------------------------------- the core and the plugin: LAY006

NEW_TABLE = """\
schema = 2
[[tier]]
name = "base"
packages = ["verso.core.base"]
[[tier]]
name = "core"
packages = ["verso.core", "verso.core.p"]
[[tier]]
name = "ru"
packages = ["verso.ru", "verso.ru.naming", "verso.ru.cli"]
"""


def renamed(tmp_path: Path, files: dict[str, str], allowlist: str | None = None, table: str = NEW_TABLE) -> Path:
    """A tree of the core and the plugin: verso/core and verso/ru, the toy table, the core's tiers
    under the plugin's."""
    base = {"verso/core/__init__.py": "", "verso/core/base/__init__.py": "",
            "verso/core/p/__init__.py": "", "verso/core/p/b.py": "",
            "verso/ru/__init__.py": "", "verso/ru/naming/__init__.py": "", "verso/ru/naming/a.py": "x = 1\n",
            "verso/ru/cli/__init__.py": ""}
    for rel, text in {**base, **files}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / "tools" / "layers.toml").write_text(table, encoding="utf-8")
    if allowlist is not None:
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "layering_allowlist.txt").write_text(allowlist, encoding="utf-8")
    return tmp_path


def test_a_core_module_importing_ru_is_lay006(tmp_path: Path):
    root = renamed(tmp_path, {"verso/core/p/b.py": "def f():\n    from verso.ru.naming.a import x\n"})
    assert layers.check(root) == ["verso.core.p.b → verso.ru.naming.a: ядро импортирует ru — возьмите это у плагина (verso.core.plugins)"]


def test_a_core_to_plugin_edge_is_lay006_alone(tmp_path: Path):
    """The core's tiers sit under the plugin's, so the edge also goes up: it is LAY006's, not LAY002's."""
    root = renamed(tmp_path, {"verso/core/p/b.py": "from verso.ru.naming.a import x\n"})
    assert layers.check(root) == ["verso.core.p.b → verso.ru.naming.a: ядро импортирует ru — возьмите это у плагина (verso.core.plugins)"]






def test_the_rules_read_a_module_by_its_new_name(tmp_path: Path):
    """The alias's table names geni.pipeline as verso.core.p; the rules no longer read it: the
    plugin's module importing the core's goes down."""
    root = renamed(tmp_path, {"verso/ru/naming/a.py": "from verso.core.p.b import y\n", "verso/core/p/b.py": "y = 1\n"})
    assert layers.check(root) == []


def test_a_new_module_under_a_sides_root_needs_a_tier(tmp_path: Path):
    """0.1.0 adds modules straight under a side's root (a plugin registry): the root names its
    own __init__ alone, so a new module names its tier itself."""
    root = renamed(tmp_path, {"verso/core/registry.py": "from verso.core.p.b import y\n"})
    assert layers.check(root) == ["verso.core.registry: нет слоя — впишите пакет в tools/layers.toml"]


def test_a_new_module_is_held_to_the_tier_the_overrides_give_it(tmp_path: Path):
    table = NEW_TABLE + '\n[overrides]\n"verso.core.registry" = "base"\n'
    root = renamed(tmp_path, {"verso/core/registry.py": "from verso.core.p.b import y\n"}, table=table)
    assert layers.check(root) == [
        "verso.core.registry (base) → verso.core.p.b (core): ребро вверх или вбок — см. tools/layers.toml"]


def test_an_override_of_no_module_is_refused(tmp_path: Path):
    table = NEW_TABLE + '\n[overrides]\n"verso.core.gone" = "core"\n'
    root = renamed(tmp_path, {}, table=table)
    assert layers.check(root) == ["tools/layers.toml: [overrides] — модуля verso.core.gone нет"]


def _committed(root: Path, layers_py: str) -> None:
    (root / "tools" / "layers.py").write_text(layers_py, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")


def test_the_first_seed_of_a_new_code_is_accepted_against_a_base_without_it(tmp_path: Path):
    root = renamed(tmp_path, {}, allowlist="")
    _committed(root, '"""Before 0.1.0: no core, no ru."""\n')
    (root / layers.ALLOWLIST).write_text("LAY006 verso.core.p.b -> verso.ru.naming.a\n", encoding="utf-8")
    assert layers.base_problems("HEAD", root) == []




def test_a_new_line_of_a_known_code_is_still_refused(tmp_path: Path):
    root = renamed(tmp_path, {}, allowlist="")
    _committed(root, 'CODES = ("LAY006",)\n')
    (root / layers.ALLOWLIST).write_text("LAY006 verso.core.p.b -> verso.ru.naming.a\n", encoding="utf-8")
    assert layers.base_problems("HEAD", root) == [
        "«LAY006 verso.core.p.b -> verso.ru.naming.a» появилась после HEAD — список только убывает"]




def test_a_string_of_core_code_naming_the_plugin_is_lay006(tmp_path: Path):
    """The core names no module of the plugin, by a string either (an import by name, a
    command run by its module); a docstring and a comment are documentation."""
    root = renamed(tmp_path, {"verso/core/p/b.py": ('"""Reads verso.ru.naming.a."""\n'
                                                   "# verso.ru.naming.a too\n"
                                                   'NAME = "verso.ru.naming.a"\n'
                                                   'CMD = f"python -m verso.ru.naming.a {1}"\n')})
    assert layers.check(root) == ["verso.core.p.b → verso.ru.naming.a: ядро называет ru строкой — "
                                  "возьмите это у плагина (verso.core.plugins)"]


def test_lay006_is_never_listed(tmp_path: Path):
    """The core imports the plugin nowhere, so a line of LAY006 is no exemption but an error."""
    root = renamed(tmp_path, {}, allowlist="LAY006 verso.core.p.b -> verso.ru.naming.a\n")
    assert layers.check(root) == [
        "tests/layering_allowlist.txt: «LAY006 verso.core.p.b -> verso.ru.naming.a» — LAY006 не списывается: "
        "ядро не импортирует плагин"]


def test_a_core_module_importing_the_plugin_fails_the_check(tmp_path: Path):
    root = renamed(tmp_path, {"verso/core/p/b.py": "from verso.ru.naming.a import x\n"},
                   allowlist="LAY006 verso.core.p.b -> verso.ru.naming.a\n")
    assert layers.check(root) == [
        "verso.core.p.b → verso.ru.naming.a: ядро импортирует ru — возьмите это у плагина (verso.core.plugins)",
        "tests/layering_allowlist.txt: «LAY006 verso.core.p.b -> verso.ru.naming.a» — LAY006 не списывается: "
        "ядро не импортирует плагин"]
    assert layers.update(root) == []           # the line is struck; the violation stays
    assert layers.read_allowlist((root / layers.ALLOWLIST).read_text(encoding="utf-8")) == []
    assert layers.check(root) == [
        "verso.core.p.b → verso.ru.naming.a: ядро импортирует ru — возьмите это у плагина (verso.core.plugins)"]


def test_the_record_calls_are_spelled_once_in_their_module():
    """RECORD_FUNCS is the dialect's calls, not a second spelling of them."""
    import ast
    from verso.ru.dsl import calls
    tree = ast.parse(Path(calls.__file__).read_text(encoding="utf-8"))
    spelled = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "listed_person"]
    assert spelled == ["listed_person"]
    assert calls.RECORD_FUNCS == frozenset(calls.CALLS.calls)




# ---------------------------------------------------------------- 0.1.0's layout


TOY_CORE = TOY.replace('packages = ["verso.ru", "verso.ru.a"]', 'packages = ["verso.core", "verso.ru", "verso.ru.a"]')


def split(root: Path) -> Path:
    """The toy tree in the library's layout: verso/core and verso/ru moved under packages/verso-*/src."""
    (root / "verso" / "core").mkdir(parents=True, exist_ok=True)
    (root / "verso" / "core" / "__init__.py").write_text("", encoding="utf-8")
    for side in ("core", "ru"):
        dst = root / "packages" / f"verso-{side}" / "src" / "verso" / side
        dst.parent.mkdir(parents=True)
        (root / "verso" / side).rename(dst)
    (root / "verso").rmdir()
    return root


def test_layers_reads_a_split_tree(tmp_path: Path):
    root = split(toy(tmp_path, {"verso/ru/a/x.py": "import verso.ru.b.y\n", "verso/ru/b/y.py": ""}, table=TOY_CORE))
    assert "verso.ru.a.x" in layers.modules(root)
    assert "verso.ru.a.x (low) → verso.ru.b.y (mid): ребро вверх или вбок — см. tools/layers.toml" in messages(root)
    assert "нет слоя" not in messages(root)



