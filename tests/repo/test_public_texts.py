"""What a stranger reads in this repository needs nothing from the corpus's repository: no plan's
phase label, no pointer to a guide of the data, and the code that ships names its own commands, never
a Makefile it does not ship."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".superpowers", ".pytest_cache", ".ruff_cache",
              "build", "dist", ".gradle", ".idea", "out", ".claude", ".verso-src", ".verso-app-src"}
_TEXT = {".py", ".md", ".toml", ".json", ".txt", ".tsv", ".cfg", ".yml", ".yaml", ".js", ".ts", ".kt", ".kts",
         ".html", ".css", ".sh", ".xml", ".properties", ".pyi", ".ini"}
_PHASE = re.compile(r"(?<![\w])Ф\d+[а-я]?")  # not a fund inside a scan's file name (ГАВО_Ф2Оп1…)
_POINTER = re.compile(r"CONSOLIDATION\.md|TERRAFORM\.md|regional-rules|docs/superpowers|SKILL\.md"
                      r"|\brules/[a-z-]+\.md|монорепо|monorepo", re.IGNORECASE)
# A Makefile target: a word with a hyphen (`make tf-plan`), or one of the one-word targets a corpus's
# Makefile has (`make bootstrap`) — not English («make the», «make it»).
_MAKE = re.compile(r"\bmake (?:[a-z][a-z0-9]*-[a-z0-9-]*|bootstrap|reconcile|generate|db|apply|rebatch|golden"
                   r"|premerge|review|timeline|facts|svyatcy|test|lint|ci|stamp|reference|standalone)\b")
#: A match that is no label or pointer, and why. Empty: an invented fixture is invented further.
ALLOWED: dict[str, str] = {}


def _files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if (path.is_file() and not set(rel.parts[:-1]) & _SKIP_DIRS
                and (path.suffix in _TEXT or path.name in ("Makefile", "LICENSE", "NOTICE"))
                and path != Path(__file__).resolve()):
            out.append(path)
    return out


def _found(pattern: re.Pattern[str], paths: list[Path]) -> list[str]:
    out: list[str] = []
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if pattern.search(line):
                out.append(f"{rel}:{n}: {line.strip()[:120]}")
    return out


def test_no_phase_labels():
    assert _found(_PHASE, _files()) == []


def test_no_pointer_into_the_data_repo():
    assert _found(_POINTER, _files()) == []


def test_shipped_code_names_no_make_target():
    shipped = [p for p in _files() if p.relative_to(ROOT).parts[:1] == ("packages",)
               and "src" in p.relative_to(ROOT).parts]
    assert _found(_MAKE, shipped) == []


_COMMAND = re.compile(r"`verso ([a-z][a-z0-9-]*)([^`]*)`")


def test_a_hinted_command_and_its_flags_exist():
    """A hint in the shipped code that names `verso <command> --flag …` is one a reader can type: the
    command is the library's and every flag is its own."""
    import subprocess
    import sys

    hinted: dict[str, set[str]] = {}
    for path in _files():
        if path.relative_to(ROOT).parts[:1] != ("packages",) or "src" not in path.relative_to(ROOT).parts:
            continue
        for m in _COMMAND.finditer(path.read_text(encoding="utf-8", errors="replace")):
            hinted.setdefault(m.group(1), set()).update(re.findall(r"--[a-z][a-z0-9-]*", m.group(2)))
    assert hinted
    workspace = ROOT / "tests" / "fixtures" / "workspace"
    env = {"COLUMNS": "200", "PATH": "", "VERSO_LANG": "en", "PYTHONPATH": ":".join(sys.path)}

    def help_of(*command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "verso.core.cli", "--workspace", str(workspace), *command, "--help"],
                              capture_output=True, text=True, env=env)

    listed = set(re.findall(r"^\s+([a-z][a-z0-9-]+)\s", help_of().stdout, re.MULTILINE))
    wrong: list[str] = []
    for command, flags in sorted(hinted.items()):
        if command not in listed:
            wrong.append(f"verso {command}: no such command")
        elif flags:
            said = help_of(command).stdout
            wrong += [f"verso {command} {flag}: no such flag" for flag in sorted(flags) if flag not in said]
    assert wrong == [], "\n".join(wrong)


_SECTION = re.compile(r"§\s?\d")


def test_shipped_code_names_no_section_of_a_guide_it_does_not_ship():
    # «§8» was a section of the corpus's consolidation guide; the pointer to the guide went in 0.1.13
    # and left its section numbers behind, pointing nowhere.
    shipped = [p for p in _files() if p.relative_to(ROOT).parts[:1] == ("packages",)
               and "src" in p.relative_to(ROOT).parts]
    assert _found(_SECTION, shipped) == []


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_readme_installs_from_a_git_tag():
    readme = _text("README.md")
    assert not any(line.startswith("pip install verso-core verso-ru") for line in readme.splitlines())
    assert "git+https://github.com/verso-genealogy/verso@" in readme
    assert "#subdirectory=packages/verso-core" in readme
    assert "#subdirectory=packages/verso-ru" in readme


def test_readme_names_the_shipped_names_base():
    readme = _text("README.md")
    assert "no names table" not in readme
    assert 'base = "ru"' in readme


def test_ru_plugin_is_a_record_tradition():
    texts = [_text("README.md"), _text("AGENTS.md"), _text("packages/verso-ru/pyproject.toml")]
    for text in texts:
        assert "the Russian Empire's books" not in text
        assert "records of the Russian Empire" not in text
    assert "written in Russian" in texts[0]


def test_contributing_follows_i18n():
    contributing = _text("CONTRIBUTING.md")
    assert "in Russian, the language of" not in contributing
    assert "en.toml" in contributing


def test_changelog_links_no_pr_number():
    assert re.search(r"\(#\d+\)", _text("CHANGELOG.md")) is None


#: A line a reader types, without its trailing comment (the comment is translated).
_COMMAND_LINE = re.compile(r"^((?:pip install|python examples/run\.py) .*?)(?:\s+#\s.*)?$", re.MULTILINE)


def test_russian_readmes_keep_the_english_ones_commands():
    """A README.ru.md is a translation: what a reader types — the install lines, the commands — is the
    English README's, so a command changed in one and not the other fails here."""
    for english in ("README.md", "examples/README.md"):
        en, ru = _text(english), _text(english.replace("README.md", "README.ru.md"))
        assert "README.ru.md" in en
        assert set(_COMMAND_LINE.findall(en)) <= set(_COMMAND_LINE.findall(ru)), english
        missing = {m.group(0) for m in _COMMAND.finditer(en)} - {m.group(0) for m in _COMMAND.finditer(ru)}
        assert not missing, sorted(missing)
