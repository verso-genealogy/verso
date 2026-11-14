"""The interface's Cyrillic text ratchet (tests/ui_text.py): what it counts, what it refuses,
and this project's code within its list."""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

from tests import ui_text
from tests.ui_text import Content, ContentError

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_counts_skip_docstrings_and_marked_lines():
    text = textwrap.dedent('''\
        """Модуль: докстринг не считается."""
        A = "текст"
        B = "content"  # i18n: content
        C = f"строка {A}"
        D = "латиница"  # i18n: content
        # комментарий не считается


        def f():
            """И этот докстринг."""
            raise ValueError(f"нет {A}"
                             "второй строкой")


        E = ("""проза,
        ещё проза""")  # i18n: content
        ''')
    assert ui_text.python_lines(text) == {2, 4, 11, 12}


def test_pre_reform_letters_count():
    assert ui_text.count_text("m.py", 'x = "ѣ"\ny = "і"\nz = "Ѳ"\nw = "ѵ"\n') == 4


def test_a_content_module_still_counts_its_messages():
    """A module declared content is the sources' vocabulary; a message raised or printed from it is
    the interface all the same, and counted — a mask hides no message."""
    content = Content(("pkg",), (("pkg/vocab.py", "the sources' words: vocabulary"),))
    text = textwrap.dedent('''\
        WORDS = {"отец": "father", "мать": "mother"}
        def check(word):
            if word not in WORDS:
                raise ValueError(f"нет такого слова: {word}")
            print("слово", word)
            raise ValueError("так в подлиннике")  # i18n: content
        ''')
    assert ui_text.counts_of({"pkg/vocab.py": text}, content) == {"pkg/vocab.py": 2}
    assert ui_text.counts_of({"pkg/other.py": text}, content) == {"pkg/other.py": 3}


def test_js_comments_do_not_count():
    text = textwrap.dedent('''\
        // комментарий: он сказал "привет"
        const a = "текст";
        /* и блок
           комментариев */
        const b = `шаблон ${a} ещё`;
        const c = "words";
        const d = /рожд/.test(a);
        const e = "словарь"; // i18n: content
        ''')
    assert ui_text.js_lines(text) == {2, 5, 7}


def _project(tmp_path: Path, files: dict[str, str], modules: str = "") -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "ui_content.toml").write_text(f'roots = ["src"]\n[content]\nmodules = [{modules}]\n',
                                                        encoding="utf-8")
    return tmp_path


def test_html_counts_its_text_and_attributes_not_its_keys():
    page = ('<!doctype html>\n<html lang="ru">\n<body>\n'
            '  <button data-i18n="verso.app:page.save" title="Сохранить">Сохранить</button>\n'   # 4: text and title
            '  <p data-i18n="verso.app:page.loading"></p>\n'                                     # 5: a key alone
            '  <!-- Загрузка -->\n'                                                                # 6: a comment
            '  <span>л. 12</span> <!-- i18n: content -->\n'                                      # 7: marked
            '  <option\n    title="все">x</option>\n'                                             # 9: an attribute
            '  <script>const s = "текст";</script>\n'                                            # 10: a script
            '</body>\n</html>\n')
    assert ui_text.html_lines(page) == {4, 9}
    assert ui_text.count_text("static/index.html", page) == 2


def test_ratchet_refuses_a_rise_and_a_stale_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    project = _project(tmp_path, {"src/a.py": 'X = "один"\n'})
    assert ui_text.main(["--seed"], project) == 0
    assert ui_text.read_list(project / ui_text.LIST) == {"src/a.py": 1}
    (project / "src/a.py").write_text('X = "один"\nY = "два"\n', encoding="utf-8")
    assert ui_text.main(["--check"], project) == 1
    assert "src/a.py: строк с кириллицей было 1, стало 2" in capsys.readouterr().err
    assert ui_text.main(["--update"], project) == 1                  # a rise is never written down
    (project / "src/a.py").write_text('X = "one"\n', encoding="utf-8")
    assert ui_text.main(["--check"], project) == 1
    assert "make ui-ratchet update=1" in capsys.readouterr().err
    assert ui_text.main(["--update"], project) == 0
    assert ui_text.read_list(project / ui_text.LIST) == {}


def test_base_is_the_ceiling(tmp_path: Path):
    import subprocess
    project = _project(tmp_path, {"src/a.py": 'X = "один"\n'})
    ui_text.main(["--seed"], project)
    for argv in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
        subprocess.run(["git", *argv], cwd=project, check=True)
    (project / "src/a.py").write_text('X = "один"\nY = "два"\n', encoding="utf-8")
    ui_text.write_list(project / ui_text.LIST, {"src/a.py": 2})           # a line raised by hand
    assert ui_text.main(["--check"], project) == 0
    assert ui_text.main(["--base", "HEAD"], project) == 1


def test_a_content_module_needs_a_reason(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text('roots = ["src"]\n[content]\nmodules = [{ path = "src/x.py" }]\n', encoding="utf-8")
    with pytest.raises(ContentError, match=r"src/x\.py — без причины"):
        ui_text.read_content(path)
    project = _project(tmp_path / "p", {"src/gen.py": 'X = "проза"\n', "src/ui.py": 'X = "ошибка"\n'},
                       '{ path = "src/gen.py", why = "generated prose" }')
    content = ui_text.read_content(project / ui_text.CONTENT)
    assert ui_text.counts([project], content) == {"src/ui.py": 1}
    assert Content(("src",), (("src/**/gen*.py", "w"),)).declared("src/a/gen2.py")


def test_the_tree_is_within_the_ratchet():
    assert ui_text.main(["--check"]) == 0


def _matches_a_message_by_its_text(tree: ast.AST) -> list[int]:
    """The lines comparing a Cyrillic literal with an exception's text — `str(e)`, `e.args[0]`, or a
    method of either (`str(e).startswith(…)`)."""
    def cyrillic(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(_CYRILLIC.search(node.value))

    def messagey(node: ast.AST) -> bool:
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "str" and n.args:
                return True
            if isinstance(n, ast.Attribute) and n.attr == "args":
                return True
        return False

    out: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(cyrillic(s) for s in sides) and any(messagey(s) for s in sides):
                out.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("startswith", "endswith") and messagey(node.func.value)
              and any(cyrillic(a) for a in node.args)):
            out.append(node.lineno)
    return out


def test_no_message_is_matched_by_its_text():
    """A message goes through the catalog and reads in the interface's language, so code that
    catches an error tells it by its type or its key, never by its Russian words."""
    root = ui_text.PROJECT / "packages" / "verso-ru" / "src"
    found = [f"{path.relative_to(root)}:{line}"
             for path in sorted(root.rglob("*.py"))
             for line in _matches_a_message_by_its_text(ast.parse(path.read_text(encoding="utf-8")))]
    assert found == []


def test_matching_a_message_by_its_text_is_seen():
    code = textwrap.dedent('''\
        try:
            f()
        except ValueError as e:
            if "не модуль DSL" in str(e):
                pass
            if e.args[0] == "пусто":
                pass
            if str(e).startswith("нет"):
                pass
            if kind == "рождение":
                pass
        ''')
    assert _matches_a_message_by_its_text(ast.parse(code)) == [4, 6, 8]


def test_verso_ru_says_nothing_but_through_its_catalogs():
    """The ratchet is at zero — every message of verso-ru goes through a catalog; what Cyrillic is
    left in its code is the sources' own, declared in ui_content.toml or marked `i18n: content`."""
    assert ui_text.read_list(ui_text.LIST) == {}
