"""The core's catalogs against its code (`i18n.problems`), and every kind of problem the check
finds, on a toy package."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import verso.core
from verso.core import i18n


def test_catalogs_have_no_problems():
    assert i18n.problems("verso.core", Path(verso.core.__file__).parent) == []


def _toy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pkg = tmp_path / "probpkg"
    (pkg / "locales").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "messages.py").write_text("def t(key, /, **params): return (key, params)\n", encoding="utf-8")
    (pkg / "work.py").write_text(textwrap.dedent('''\
        from probpkg.messages import t
        KEY = "a.dynamic"
        t("a.fine", name=1)
        t(KEY)
        t("a.absent")
        t("a.params", wrong=1)
        t("a.plural", count=2)
        t("a.untranslated_but_done")
        t("a.missing_in_ru")
        t("a.ru_params", x=1)
        '''), encoding="utf-8")
    (pkg / "locales" / "en.toml").write_text(textwrap.dedent('''\
        schema = 1
        [a]
        fine = "fine {name}"
        params = "p {right}"
        nobody = "nobody calls me"
        untranslated_but_done = "done"
        missing_in_ru = "missing"
        ru_params = "x {x}"
        [a.plural]
        one = "{count} one"
        other = "{count} other"
        '''), encoding="utf-8")
    (pkg / "locales" / "ru.toml").write_text(textwrap.dedent('''\
        schema = 1
        untranslated = ["a.untranslated_but_done"]
        [a]
        fine = "хорошо {name}"
        params = "п {right}"
        nobody = "никто"
        untranslated_but_done = "сделано"
        ru_params = "икс {y}"
        [a.plural]
        one = "{count} один"
        other = "{count} других"
        '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return pkg


def test_problems_find_each_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pkg = _toy(tmp_path, monkeypatch)
    i18n.forget()
    found = i18n.problems("probpkg", pkg)
    def has(fragment: str) -> bool:
        return any(fragment in line for line in found)
    assert has("work.py:4: the key is no literal")
    assert has("work.py:5: «a.absent» — no such key in en")
    assert has("work.py:6: «a.params» — params {wrong}, the template's {right}")
    assert has("«a.nobody» — no call")
    assert has("ru: «a.missing_in_ru» — missing, and not untranslated")
    assert has("ru: «a.ru_params» — params {y}, English's {x}")
    assert has("ru: «a.untranslated_but_done» — untranslated, yet translated")
    assert has("ru: «a.plural» — plural forms one, other, the language's few, many, one, other")
    assert not has("a.fine")
    assert len(found) == 8, found
