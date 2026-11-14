"""The catalogs' mechanism (`verso.core.i18n`) on the toy's own catalogs (tests/core/locales):
the language of the moment, a message rendered when it is read, and an error never hidden by
the rendering of its message."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.codepaths import PROJECT, pythonpath
from verso.core import i18n, messages, workspace  # noqa: F401 — messages: the workspace speaks
from verso.core.i18n import CatalogError, LocalePack, Message

PKG = "tests.core"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("VERSO_LANG", raising=False)
    i18n.forget()
    yield
    i18n.forget()


def _ws(tmp_path: Path, text: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "verso.toml").write_text(text, encoding="utf-8")
    return tmp_path


def t(key: str, **params: object) -> Message:
    return Message(PKG, key, params)


def test_language_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with workspace.use(_ws(tmp_path, 'schema = 5\n[i18n]\nlocale = "ru"\n')):
        assert i18n.language() == "ru"                       # the workspace
        monkeypatch.setenv("VERSO_LANG", "en")
        assert i18n.language() == "en"                       # VERSO_LANG over it
        with i18n.use("ru"):
            assert i18n.language() == "ru"                   # use() over both
    monkeypatch.delenv("VERSO_LANG")
    with workspace.use(_ws(tmp_path / "en", "schema = 5\n")):
        assert i18n.language() == "en"


def test_lang_and_lc_are_ignored():
    """The system's locale says nothing: only VERSO_LANG and the workspace do."""
    done = subprocess.run(
        [sys.executable, "-c", "import os; os.chdir('/'); from verso.core import i18n, messages; print(i18n.language())"],
        cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath(), "LANG": "ru_RU.UTF-8", "LC_ALL": "ru_RU.UTF-8"})
    assert (done.returncode, done.stdout) == (0, "en\n"), done.stderr


def test_rendering_without_a_workspace_is_english():
    done = subprocess.run(
        [sys.executable, "-c", "import os; os.chdir('/')\nfrom verso.core import i18n, messages\n"
                               "print(i18n.render(i18n.Message('tests.core', 'hello.plain', {'name': 'A'})))"],
        cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
    assert (done.returncode, done.stdout) == (0, "Hello, A\n"), done.stderr


def test_a_message_renders_in_the_language_of_the_moment():
    message = t("hello.plain", name="Анна")
    with i18n.use("ru"):
        assert str(message) == "Здравствуй, Анна"
    with i18n.use("en"):
        assert str(message) == "Hello, Анна"
        assert str(SystemExit(message).code) == "Hello, Анна"      # a SystemExit prints str(code)


def test_language_follows_the_workspace(tmp_path: Path):
    ru = _ws(tmp_path / "ru", 'schema = 5\n[i18n]\nlocale = "ru"\n')
    en = _ws(tmp_path / "en", 'schema = 5\n[i18n]\nlocale = "en"\n')
    message = t("hello.plain", name="X")
    with workspace.use(ru):
        assert str(message) == "Здравствуй, X"
        with workspace.use(en):
            assert str(message) == "Hello, X"
        assert str(message) == "Здравствуй, X"


def test_a_message_is_hashable():
    """A message may key a cache or stand in a set: equal messages hash alike, whatever their params."""
    a, b = t("hello.plain", name="A"), t("hello.plain", name="A")
    assert a == b and hash(a) == hash(b) and len({a, b, t("hello.plain", name="B")}) == 2
    assert hash(t("hello.plain", name=["A", "B"])) == hash(t("hello.plain", name=["A", "B"]))


def test_braces_are_literal():
    with i18n.use("en"):
        assert str(t("hello.braces", n=3)) == "a {literal} brace and 3"
    with i18n.use("ru"):
        assert str(t("hello.braces", n=3)) == "скобка {буквально} и 3"


def test_untranslated_falls_back_to_english():
    with i18n.use("ru"):
        assert str(t("hello.untranslated")) == "left in English"
        assert str(t("hello.only_en")) == "only in English"
    assert i18n.untranslated(PKG, "ru") == frozenset({"hello.untranslated"})


def test_a_missing_key_renders_key_and_params():
    with i18n.use("ru"):
        assert str(t("nope.key", a=1)) == "nope.key {'a': 1}"
    assert str(Message(PKG, "hello.plain", {})) == "hello.plain {}"        # a parameter missing


def test_a_broken_catalog_never_hides_the_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    broken = tmp_path / "broken_pkg"
    (broken / "locales").mkdir(parents=True)
    (broken / "__init__.py").write_text("", encoding="utf-8")
    (broken / "locales" / "en.toml").write_text("schema = 1\n[a\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    with i18n.use("en"):
        assert str(Message("broken_pkg", "a.b", {"x": 1})) == "a.b {'x': 1}"
    with pytest.raises(CatalogError, match=r"en\.toml"):
        i18n.catalog("broken_pkg", "en")


def test_catalog_is_flat_and_keyed():
    catalog = i18n.catalog(PKG, "en")
    assert catalog["hello.plain"] == "Hello, {name}"
    assert catalog["hello.notes"] == {"one": "{count} note", "other": "{count} notes"}
    assert "schema" not in catalog and "untranslated" not in catalog


def test_plural_categories():
    assert [i18n.plural("ru", n) for n in (1, 3, 5, 21, 11, 22, 25, 111, 0)] == \
        ["one", "few", "many", "one", "many", "few", "many", "many", "many"]
    assert [i18n.plural("en", n) for n in (1, 2, 0)] == ["one", "other", "other"]
    with i18n.use("ru"):
        assert [str(t("hello.notes", count=n)) for n in (1, 3, 5)] == ["1 заметка", "3 заметки", "5 заметок"]
    with i18n.use("en"):
        assert [str(t("hello.notes", count=n)) for n in (1, 3)] == ["1 note", "3 notes"]


def _pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str) -> LocalePack:
    pkg = tmp_path / f"pack_{language}"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "toy.toml").write_text('schema = 1\n[hello]\nplain = "Salut, {name}"\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return LocalePack(name=language, language=language, catalogs={PKG: f"pack_{language}:toy.toml"},
                      plural=lambda n: "one" if n == 1 else "other")


def test_a_pack_adds_a_language_and_cannot_override_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with i18n.adding(_pack(tmp_path, monkeypatch, "xx")):
        assert "xx" in i18n.languages(PKG)
        with i18n.use("xx"):
            assert str(t("hello.plain", name="A")) == "Salut, A"
            assert str(t("hello.only_en")) == "only in English"
        assert i18n.plural("xx", 2) == "other"
    with i18n.adding(_pack(tmp_path / "2", monkeypatch, "ru")):
        assert i18n.catalog(PKG, "ru")["hello.plain"] != "Salut, {name}"   # the shipped catalog stands
        with pytest.raises(CatalogError, match="ru"):                       # and the pack is refused
            i18n.check()


def test_a_pack_not_installed_hides_no_message():
    """One typo in `[i18n] packs` blanks nothing: the shipped catalogs speak, and `check()` says why
    the pack is refused."""
    i18n.configure(configured=lambda: None, packs=lambda: ("nosuch",))
    try:
        with i18n.use("en"):
            assert str(t("hello.plain", name="A")) == "Hello, A"
        with i18n.use("ru"):
            assert str(t("hello.notes", count=3)) == "3 заметки"
        with pytest.raises(CatalogError, match="nosuch"):
            i18n.check()
    finally:
        i18n.configure(configured=lambda: None)


def test_a_shipped_language_never_asks_the_packs(monkeypatch: pytest.MonkeyPatch):
    asked: list[object] = []

    def entry_points(**kwargs: object) -> list[object]:
        asked.append(kwargs)
        return []

    monkeypatch.setattr(i18n.metadata, "entry_points", entry_points)
    i18n.configure(configured=lambda: None, packs=lambda: ("nosuch",))
    try:
        for lang in ("en", "ru", "en"):
            with i18n.use(lang):
                str(t("hello.plain", name="A"))
        assert asked == []
    finally:
        i18n.configure(configured=lambda: None)


def test_check_refuses_an_unknown_configured_language():
    i18n.configure(configured=lambda: "zz")
    try:
        with pytest.raises(CatalogError, match=r"zz.*en, ru"):
            i18n.check()
        assert str(t("hello.plain", name="A")) == "Hello, A"          # rendering never raises
    finally:
        i18n.configure(configured=lambda: None)


def test_unknown_language_lists_the_languages(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERSO_LANG", "xx")
    with pytest.raises(CatalogError, match=r"xx.*en, ru"):
        i18n.language()
    assert str(t("hello.plain", name="A")) == "Hello, A"         # rendering never raises


def test_languages_of_a_package():
    assert i18n.languages(PKG) == ("en", "ru")


def test_cli_lang_sets_the_commands_language():
    done = subprocess.run(
        [sys.executable, "-c", "import sys\nfrom tests.core.toy import TOY\nfrom verso.core import plugins, cli\n"
                               "import os\n"
                               "with plugins.adding(TOY, entry_points=False):\n"
                               "    code = cli.main(['--lang', 'en', 'toy-hello'])\n"
                               "print('VERSO_LANG=' + os.environ['VERSO_LANG'])\nsys.exit(code)"],
        cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
    assert done.returncode == 0, done.stderr
    assert "VERSO_LANG=en" in done.stdout


def test_cli_refuses_an_unknown_language():
    done = subprocess.run([sys.executable, "-m", "verso.core.cli", "--lang", "xx", "workspace", "root"],
                          cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
    assert done.returncode == 2
    assert "xx" in done.stderr and "en, ru" in done.stderr


def test_cli_lang_speaks_the_help_too():
    """`verso --lang L --help`: verso's own help, its usage and its errors speak L."""
    out = {}
    for lang in ("en", "ru"):
        done = subprocess.run([sys.executable, "-m", "verso.core.cli", "--lang", lang, "--help"],
                              cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
                              env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
        assert done.returncode == 0, done.stderr
        out[lang] = done.stdout
    assert "Run a module of the library as a program" in out["en"]
    assert "Запустить модуль библиотеки" in out["ru"]


def test_cli_refuses_an_unknown_verso_lang():
    done = subprocess.run([sys.executable, "-m", "verso.core.cli", "workspace", "root"],
                          cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath(), "VERSO_LANG": "zz"})
    assert done.returncode == 2
    assert "zz" in done.stderr and "en, ru" in done.stderr


def test_importing_i18n_reads_no_workspace():
    done = subprocess.run(
        [sys.executable, "-c", "import sys\nimport verso.core.i18n, verso.core.messages\n"
                               "print('verso.core.workspace' in sys.modules)"],
        cwd=PROJECT, capture_output=True, text=True, check=False, timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": pythonpath()})
    assert (done.returncode, done.stdout) == (0, "False\n"), done.stderr


def test_i18n_imports_nothing_of_verso():
    import ast
    tree = ast.parse(Path(i18n.__file__).read_text(encoding="utf-8"))
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [n for n in names if n.split(".")[0] == "verso"]


def test_a_form_falls_back_to_the_nominative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A word's forms (`forms.<kind>.<id>.<case>`): a language that keeps no case writes `nom`."""
    pkg = tmp_path / "formpkg"
    (pkg / "locales").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "locales" / "en.toml").write_text('schema = 1\n[forms.role.husband]\nnom = "husband"\n'
                                             'nom_capital = "Husband"\n', encoding="utf-8")
    (pkg / "locales" / "ru.toml").write_text('schema = 1\nuntranslated = []\n[forms.role.husband]\nnom = "муж"\n'
                                             'gen = "мужа"\nnom_capital = "Муж"\ngen_capital = "Мужа"\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    with i18n.use("en"):
        assert str(Message("formpkg", "forms.role.husband.gen", {})) == "husband"
        assert str(Message("formpkg", "forms.role.husband.gen_capital", {})) == "Husband"
    with i18n.use("ru"):
        assert str(Message("formpkg", "forms.role.husband.gen", {})) == "мужа"
    assert i18n.problems("formpkg", pkg) == []                   # a form is read by form(), never by t()


def test_a_catalog_is_read_once_by_many_threads(monkeypatch: pytest.MonkeyPatch):
    """A server answers in threads; the first read of a catalog is under a lock, so two threads
    asking at once read it once and see it whole."""
    import threading
    import time

    reads: list[tuple[str, str]] = []
    real = i18n._load  # pyright: ignore[reportPrivateUsage]

    def slow(package: str, lang: str):  # type: ignore[no-untyped-def]
        reads.append((package, lang))
        time.sleep(0.05)
        return real(package, lang)

    monkeypatch.setattr(i18n, "_load", slow)
    seen: list[int] = []
    threads = [threading.Thread(target=lambda: seen.append(len(i18n.catalog(PKG, "ru")))) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert reads == [(PKG, "ru")]
    assert len(set(seen)) == 1 and seen[0] > 0


def test_a_language_s_plural_categories_are_said():
    assert i18n.categories("ru") == {"one", "few", "many", "other"}
    assert i18n.categories("en") == {"one", "other"}



def test_a_pack_language_s_categories_look_the_pack_up_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`categories` asks the rule of 200 numbers: the packs are looked up once for them, not per number."""
    looked = 0
    enabled = i18n._enabled_packs

    def counting() -> Iterator[LocalePack]:
        nonlocal looked
        looked += 1
        return enabled()

    monkeypatch.setattr(i18n, "_enabled_packs", counting)
    with i18n.adding(_pack(tmp_path, monkeypatch, "xx")):
        assert i18n.categories("xx") == {"one", "other"}
    assert looked == 1

def test_use_speaks_per_thread():
    """Two threads each in a `use()` of their own — a server answering two pages at once — each speak
    their own language, whichever entered last."""
    import threading

    inside = threading.Barrier(2)
    spoken: dict[str, str] = {}

    def speak(lang: str) -> None:
        with i18n.use(lang):
            inside.wait()  # both are inside their use() now
            spoken[lang] = i18n.language()
            inside.wait()

    threads = [threading.Thread(target=speak, args=(lang,)) for lang in ("en", "ru")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert spoken == {"en": "en", "ru": "ru"}
