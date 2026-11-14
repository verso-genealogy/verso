"""tools/i18n_extract.py — the codemod that moves a message into a catalog, on a toy package
in a temporary directory: a message moves verbatim or not at all."""
from __future__ import annotations

import ast
import textwrap
import tomllib
from pathlib import Path

from tools import i18n_extract


def _tree(tmp_path: Path, source: str) -> tuple[Path, Path]:
    pkg = tmp_path / "toypkg"
    (pkg / "locales").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "locales" / "ru.toml").write_text("# toy\nschema = 1\nuntranslated = []\n", encoding="utf-8")
    module = pkg / "work.py"
    module.write_text(textwrap.dedent(source), encoding="utf-8")
    return module, pkg / "locales"


def _run(tmp_path: Path, source: str, *, helpers: tuple[str, ...] = ()) -> tuple[str, dict[str, object], i18n_extract.Spec]:
    module, locales = _tree(tmp_path, source)
    spec = i18n_extract.propose("toypkg", [module], helpers=helpers, root=tmp_path)
    i18n_extract.apply(spec, locales, "ru", root=tmp_path)
    catalog = tomllib.loads((locales / "ru.toml").read_text(encoding="utf-8"))
    return module.read_text(encoding="utf-8"), catalog, spec


def test_literal_moves_verbatim(tmp_path: Path):
    text, catalog, spec = _run(tmp_path, '''\
        def f():
            raise ValueError("нет файла {x}")
        ''')
    assert 'raise ValueError(str(t("work.1")))' in text
    assert "from toypkg.messages import t" in text
    assert catalog["work"] == {"1": "нет файла {{x}}"}
    assert [(s.line, s.key) for s in spec.sites] == [(2, "work.1")]


def test_conversion_and_braces_round_trip(tmp_path: Path):
    text, catalog, _ = _run(tmp_path, '''\
        def f(name, n):
            raise ValueError(f"«{name!r}» — {{x}} {n} шт.")
        ''')
    template = catalog["work"]["1"]                                    # type: ignore[index]
    assert template == "«{name}» — {{x}} {n} шт."
    call = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "t")
    params = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert params == {"name": "repr(name)", "n": "n"}
    for name, n in (("Анна", 3), ("a'b", 0)):
        assert template.format(name=repr(name), n=n) == f"«{name!r}» — {{x}} {n} шт."  # type: ignore[union-attr]


def test_refuses_a_format_spec_and_concatenation(tmp_path: Path):
    for source in ('def f(n):\n    raise ValueError(f"всего {n:>5}")\n',
                   'def f(n):\n    raise ValueError("всего " + str(n))\n',
                   'def f(n):\n    raise ValueError("всего %s" % n)\n',
                   'def f(n):\n    raise ValueError("всего {}".format(n))\n'):
        root = tmp_path / str(len(list(tmp_path.iterdir())))
        module, _ = _tree(root, source)
        spec = i18n_extract.propose("toypkg", [module], root=root)
        assert spec.sites == ()
        assert len(spec.manual) == 1 and spec.manual[0].startswith("toypkg/work.py:2: "), spec.manual
        assert spec.manual[0].endswith("перенести руками")


def test_implicit_concatenation_is_one_message(tmp_path: Path):
    text, catalog, _ = _run(tmp_path, '''\
        def f(path):
            print(f"{path}: первая часть, "
                  "вторая часть")
        ''')
    assert catalog["work"] == {"1": "{path}: первая часть, вторая часть"}
    assert 'print(t("work.1", path=path))' in text


def test_helper_argument_is_a_sink(tmp_path: Path):
    text, catalog, _ = _run(tmp_path, '''\
        def _wrong(path, key, expected):
            return ValueError(f"{path}: {key} — {expected}")


        def f(path):
            raise _wrong(path, "k", "ожидалась таблица")
        ''', helpers=("_wrong",))
    assert '_wrong(path, "k", t("work.1"))' in text
    assert catalog["work"] == {"1": "ожидалась таблица"}


def test_argparse_and_dict_messages_are_sinks(tmp_path: Path):
    text, catalog, _ = _run(tmp_path, '''\
        import argparse


        def f(ap: argparse.ArgumentParser, line: int):
            ap.add_argument("--x", help="справка")
            return {"line": line, "message": f"строка {line}"}
        ''')
    assert catalog["work"] == {"1": "справка", "2": "строка {line}"}
    assert 'help=str(t("work.1"))' in text and '"message": t("work.2", line=line)' in text


def test_apply_is_idempotent(tmp_path: Path):
    module, locales = _tree(tmp_path, 'def f():\n    print("привет")\n')
    spec = i18n_extract.propose("toypkg", [module], root=tmp_path)
    i18n_extract.apply(spec, locales, "ru", root=tmp_path)
    once = (module.read_text(encoding="utf-8"), (locales / "ru.toml").read_text(encoding="utf-8"))
    i18n_extract.apply(spec, locales, "ru", root=tmp_path)
    assert (module.read_text(encoding="utf-8"), (locales / "ru.toml").read_text(encoding="utf-8")) == once


def test_spec_round_trips_through_toml(tmp_path: Path):
    module, _ = _tree(tmp_path, 'def f(a, b):\n    print(f"{a} и {b.c}")\n')
    spec = i18n_extract.propose("toypkg", [module], root=tmp_path)
    again = i18n_extract.read_spec(i18n_extract.format_spec(spec))
    assert again == spec
    assert again.sites[0].params == {"a": "a", "c": "b.c"}


def test_a_renamed_key_and_param_are_kept(tmp_path: Path):
    module, locales = _tree(tmp_path, 'def f(a):\n    print(f"значение {a}")\n')
    spec = i18n_extract.propose("toypkg", [module], root=tmp_path)
    text = i18n_extract.format_spec(spec).replace('"work.1"', '"work.value"').replace("a = ", "value = ")
    i18n_extract.apply(i18n_extract.read_spec(text), locales, "ru", root=tmp_path)
    assert 'print(t("work.value", value=a))' in module.read_text(encoding="utf-8")
    assert tomllib.loads((locales / "ru.toml").read_text(encoding="utf-8"))["work"] == {"value": "значение {value}"}


def test_a_warning_is_a_sink(tmp_path: Path):
    text, catalog, _ = _run(tmp_path, '''\
        import warnings


        def f(old):
            warnings.warn(f"{old} устарела", FutureWarning, stacklevel=2)
        ''')
    assert catalog["work"] == {"1": "{old} устарела"}
    assert 'warnings.warn(str(t("work.1", old=old)), FutureWarning' in text


def test_a_builtin_exception_and_stderr_take_the_text(tmp_path: Path):
    """str(t(…)) where the text is read at once: argparse, warn(), stderr.write() take a str, and a
    KeyError reprs its argument; the core's own exceptions keep the Message, rendered when read."""
    text, _, _ = _run(tmp_path, '''\
        import sys


        class OwnError(Exception):
            pass


        def f(k):
            sys.stderr.write(f"нет {k}\\n")
            if k:
                raise KeyError(f"ключ {k}")
            raise OwnError(f"своя {k}")
        ''')
    assert 'sys.stderr.write(str(t("work.1", k=k)))' in text
    assert 'raise KeyError(str(t("work.2", k=k)))' in text
    assert 'raise OwnError(t("work.3", k=k))' in text
