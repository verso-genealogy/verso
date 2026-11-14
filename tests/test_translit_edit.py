"""Writing the transliteration's rules (`verso.ru.linters.translit_layer`, `verso translit`): the writable layer, the
layers' linter LEX008–LEX010, the refusal of a rule that would rename a minted Terraform address, and `migrate`."""
from __future__ import annotations

from pathlib import Path

import pytest

from verso.core import workspace
from verso.ru.cli.translit import main
from verso.ru.linters import translit_layer as edit
from verso.ru.linters.checks.translit import lint_rules
from verso.ru.naming.translit_layers import TranslitRule

HEADER = "profile\tword\tlatin\tsource\tnote\n"
ROLES = '[translit]\naddress = "ru-v1"\ndisplay = "ru-v2"\n'


def _root(tmp_path: Path, *, roles: str = ROLES, low: str = "", tree: str | None = None,
          corpus_toml: str | None = None) -> Path:
    (tmp_path / "verso.toml").write_text(
        f'schema = 7\nvillages = ["Горюхино"]\nplugins = ["ru"]\n[corpus]\ndir = "corpus"\n'
        f'[names]\nbase = "ru"\nlayers = ["low", "top"]\nwritable = "top"\n{roles}', encoding="utf-8")
    (tmp_path / "corpus").mkdir()
    if corpus_toml is not None:
        (tmp_path / "corpus" / "transliteration.toml").write_text(corpus_toml, encoding="utf-8")
    for name in ("low", "top"):
        (tmp_path / name).mkdir()
    if low:
        (tmp_path / "low" / "translit.tsv").write_text(HEADER + low, encoding="utf-8")
    if tree is not None:
        (tmp_path / "Горюхино" / "terraform" / "geni").mkdir(parents=True)
        (tmp_path / "Горюхино" / "terraform" / "geni" / "mk_1850_birth.tf").write_text(tree, encoding="utf-8")
    return tmp_path


def _top(root: Path) -> str:
    return (root / "top" / "translit.tsv").read_text(encoding="utf-8")


def test_add_goes_to_writable_layer(tmp_path: Path):
    root = _root(tmp_path)
    with workspace.use(root):
        done = edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine")
    assert (done.profile, done.layer, done.profile_gives, done.redundant) == ("ru-v2", "top", "Plotvichkin", False)
    assert _top(root) == HEADER + "ru-v2\tПлотвичкин\tPlotvichkine\teditor\t\n"


def test_remove_lower_rule_writes_dash(tmp_path: Path):
    root = _root(tmp_path, low="ru-v2\tПлотвичкин\tPlotvichkine\teditor\t\n")
    with workspace.use(root):
        edit.remove_rule(workspace.current(), "Плотвичкин")
        assert edit.explain(workspace.current(), "Плотвичкин")[1].result == "Plotvichkin"
    assert _top(root) == HEADER + "ru-v2\tПлотвичкин\t-\teditor\t\n"


def test_remove_own_rule_drops_its_row(tmp_path: Path):
    root = _root(tmp_path)
    with workspace.use(root):
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine")
        edit.remove_rule(workspace.current(), "Плотвичкин")
    assert _top(root) == HEADER


def test_remove_of_no_rule_is_refused(tmp_path: Path):
    with workspace.use(_root(tmp_path)), pytest.raises(edit.RuleRefused) as caught:
        edit.remove_rule(workspace.current(), "Плотвичкин")
    assert caught.value.code == "no_rule"


TREE = 'resource "geni_profile" "_1850_01_02_ivan_plotvichkin_mk_births_3_child" {\n}\n'


def test_minted_refused(tmp_path: Path):
    root = _root(tmp_path, tree=TREE)
    with workspace.use(root):
        with pytest.raises(edit.RuleRefused) as caught:
            edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine", profile="ru-v1")
        assert caught.value.code == "minted"
        assert caught.value.params["count"] == 1
        assert caught.value.params["example"] == "_1850_01_02_ivan_plotvichkin_mk_births_3_child"
        assert "--profile ru-v2" in str(caught.value)
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine", profile="ru-v2")


def test_remove_minted_refused(tmp_path: Path):
    root = _root(tmp_path, tree=TREE.replace("plotvichkin", "plotvichkine"),
                 low="ru-v1\tПлотвичкин\tPlotvichkine\teditor\t\n")
    with workspace.use(root), pytest.raises(edit.RuleRefused) as caught:
        edit.remove_rule(workspace.current(), "Плотвичкин", profile="ru-v1")
    assert caught.value.code == "minted"


def test_a_redundant_rule_of_the_addresses_is_taken_away_over_a_minted_tree(tmp_path: Path):
    """A rule that gives what its profile gives renames nothing: taken away — or written — over a tree that spells it."""
    root = _root(tmp_path, tree=TREE, low="ru-v1\tПлотвичкин\tPlotvichkin\teditor\t\n")
    with workspace.use(root):
        edit.remove_rule(workspace.current(), "Плотвичкин", profile="ru-v1")
        assert edit.explain(workspace.current(), "Плотвичкин")[0].result == "Plotvichkin"
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkin", profile="ru-v1")


def test_minted_with_one_profile_for_both_roles_offers_no_display_profile(tmp_path: Path):
    root = _root(tmp_path, roles='[translit]\naddress = "ru-v1"\ndisplay = "ru-v1"\n', tree=TREE)
    with workspace.use(root), pytest.raises(edit.RuleRefused) as caught:
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine")
    assert caught.value.code == "minted" and caught.value.params["display"] == "ru-v1"
    assert "--profile" not in str(caught.value) and "[translit] display" in str(caught.value)


def test_minted_needs_a_tree(tmp_path: Path):
    with workspace.use(_root(tmp_path)):
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine", profile="ru-v1")


def test_a_rule_of_another_profile_minds_no_tree(tmp_path: Path):
    """When both roles are ru-v2, the address profile is ru-v2 and its rules are the ones refused."""
    root = _root(tmp_path, roles="", tree=TREE)
    with workspace.use(root), pytest.raises(edit.RuleRefused):
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkine")


@pytest.mark.parametrize(("rule", "code", "level"), [
    (TranslitRule("ru-v9", "Плотвичкин", "Plotvichkine"), "LEX008", "error"),
    (TranslitRule("ru-v2", "Plotvichkin", "Plotvichkine"), "LEX008", "error"),
    (TranslitRule("ru-v2", "Плотвичкин", ""), "LEX008", "error"),
    (TranslitRule("ru-v2", "Плотвичкин", "Plotvichkin"), "LEX009", "warn"),
    (TranslitRule("ru-v2", "Плотвичкин", "Plotvichkinа"), "LEX010", "error"),
    (TranslitRule("ru-v1", "Плотвичкин", "Plotvichkinа"), "LEX010", "warn"),
])
def test_lint_codes(rule: TranslitRule, code: str, level: str):
    found = lint_rules([(2, rule)])
    assert [(f.issue.code, f.issue.level) for f in found] == [(code, level)]


def test_lint_duplicate_and_redundant_removal():
    rule = TranslitRule("ru-v2", "Плотвичкин", "Plotvichkine")
    found = lint_rules([(2, rule), (3, rule), (4, TranslitRule("ru-v2", "Щеглов", None))])
    assert [f.issue.code for f in found] == ["LEX002", "LEX009"]


def test_a_hard_finding_refuses_the_write(tmp_path: Path):
    root = _root(tmp_path)
    with workspace.use(root), pytest.raises(edit.RuleRefused) as caught:
        edit.add_rule(workspace.current(), "Плотвичкин", "Plotvichkinа")
    assert caught.value.code == "LEX010"
    assert not (root / "top" / "translit.tsv").exists()


def test_migrate_writes_ru_v1_rows(tmp_path: Path):
    toml = '[names]\n"Щеглов" = "Shcheglof"\n"Плотвичкин" = "Plotvichkine"\n'
    root = _root(tmp_path, corpus_toml=toml)
    with workspace.use(root):
        path, written = edit.migrate(workspace.current())
        assert written == 2 and path.name == "transliteration.toml"
        assert edit.migrate(workspace.current())[1] == 0
    assert _top(root) == HEADER + "ru-v1\tПлотвичкин\tPlotvichkine\teditor\t\nru-v1\tЩеглов\tShcheglof\teditor\t\n"


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    root = _root(tmp_path, tree=TREE)
    with workspace.use(root):
        assert main(["add", "Плотвичкин", "Plotvichkine", "--dry-run"]) == 0
        assert not (root / "top" / "translit.tsv").exists()
        assert main(["add", "Плотвичкин", "Plotvichkine", "--profile", "ru-v1"]) == 1
        assert "--profile ru-v2" in capsys.readouterr().err
        assert main(["add", "Плотвичкин", "Plotvichkine"]) == 0
        assert main(["show", "Плотвичкин"]) == 0
        out = capsys.readouterr().out
        assert "address (ru-v1) → Plotvichkin" in out and "Plotvichkine" in out
        assert main(["check"]) == 0
        with pytest.raises(SystemExit) as caught:
            main(["add"])
        assert caught.value.code == 2
