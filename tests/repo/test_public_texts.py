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


#: The texts with a Russian translation beside them (`X.ru.md`): every guide in docs/, and these. The
#: reference (docs/reference) is written from the code and stays English.
_TRANSLATED = ("README.md", "examples/README.md", "CONTRIBUTING.md", "SECURITY.md")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
#: A comment in a code block — a whole line or its tail: a translation translates it.
_CODE_COMMENT = re.compile(r"(?:^|\s+)#\s.*$")
#: A line of a code block a reader types.
_COMMAND_LINE = re.compile(r"^\s*((?:pip install|python) .*)$")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
#: A link's target: `](path)`, `](path "title")`, `](<path>)`, one level of parentheses inside the path.
_LINK = re.compile(r"\]\(\s*<?((?:[^()\s<>]|\([^()\s]*\))+)>?(?:\s+\"[^\"]*\")?\s*\)")
_LINK_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?", re.MULTILINE)
_ATX = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")


def _translated() -> list[Path]:
    return [ROOT / rel for rel in _TRANSLATED] + [p for p in sorted((ROOT / "docs").glob("*.md")) if not p.name.endswith(".ru.md")]


def _russian(english: Path) -> Path:
    return english.with_name(english.stem + ".ru.md")


def _split(text: str) -> tuple[list[str], list[list[str]]]:
    """A Markdown text's lines outside code blocks, and its code blocks (each a list of lines)."""
    prose: list[str] = []
    blocks: list[list[str]] = []
    fence: str | None = None
    for line in text.splitlines():
        m = _FENCE.match(line)
        if fence is None and m:
            fence = m.group(1)
            blocks.append([])
        elif fence is not None and m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                and not line.strip()[len(m.group(1)):].strip():
            fence = None
        elif fence is not None:
            blocks[-1].append(line)
        else:
            prose.append(line)
    return prose, blocks


def _headings(prose: list[str]) -> list[str]:
    """The headings' texts, in order: ATX (`## …`) and setext (a line over `===` / `---`)."""
    out: list[str] = []
    for i, line in enumerate(prose):
        if m := _ATX.match(line):
            out.append(m.group(2))
        elif (i + 1 < len(prose) and _SETEXT.match(prose[i + 1]) and line.strip()
              and not re.match(r"\s*([-*+|>]|\d+\.)\s", line) and not _ATX.match(line)):
            out.append(line.strip())
    return out


def _slug(heading: str) -> str:
    """GitHub's anchor of a heading: a link is its text, then lower case, punctuation dropped, spaces → hyphens."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _anchors(text: str) -> set[str]:
    """GitHub's anchors of a Markdown text's headings; a repeated one gets `-1`, `-2`, … as on GitHub."""
    seen: dict[str, int] = {}
    out: set[str] = set()
    for heading in _headings(_split(text)[0]):
        slug = _slug(heading)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    return out


def _shape(text: str) -> dict[str, object]:
    """What a translation keeps of its original: the headings' count and levels, the tables' rows, and the
    code blocks without their comments."""
    prose, blocks = _split(text)
    return {"headings": [len(m.group(1)) for line in prose if (m := _ATX.match(line))],
            "table rows": sum(1 for line in prose if line.lstrip().startswith("|")),
            "code blocks": [[_CODE_COMMENT.sub("", line).rstrip() for line in block] for block in blocks]}


def _typed(text: str) -> tuple[set[str], set[str]]:
    """What a reader types: the command lines of the code blocks (without a comment), the `verso …` of the prose."""
    prose, blocks = _split(text)
    lines = {_CODE_COMMENT.sub("", m.group(1)).rstrip() for block in blocks for line in block
             if (m := _COMMAND_LINE.match(line))}
    return lines, {m.group(0) for m in _COMMAND.finditer("\n".join(prose))}


def test_every_guide_has_its_russian_translation():
    english = _translated()
    assert len(english) > len(_TRANSLATED)
    missing = [p.relative_to(ROOT).as_posix() for p in english if not _russian(p).is_file()]
    assert missing == []
    unlinked = [p.relative_to(ROOT).as_posix() for p in english if f"]({_russian(p).name})" not in p.read_text(encoding="utf-8")]
    assert unlinked == []
    no_way_back = [_russian(p).relative_to(ROOT).as_posix() for p in english
                   if f"[English]({p.name})" not in _russian(p).read_text(encoding="utf-8")]
    assert no_way_back == []


def test_translations_keep_the_originals_shape():
    """A section, a table row or an example added to one language and not the other fails here."""
    wrong: list[str] = []
    for english in _translated():
        en, ru = _shape(english.read_text(encoding="utf-8")), _shape(_russian(english).read_text(encoding="utf-8"))
        wrong += [f"{english.relative_to(ROOT).as_posix()}: {key} differ" for key in en if en[key] != ru[key]]
    assert wrong == [], "\n".join(wrong)


def test_translations_keep_the_english_ones_commands():
    """A translation changes the words, not what a reader types — in neither direction."""
    wrong: list[str] = []
    for english in _translated():
        en, ru = _typed(english.read_text(encoding="utf-8")), _typed(_russian(english).read_text(encoding="utf-8"))
        rel = english.relative_to(ROOT).as_posix()
        for kind, a, b in (("line", en[0], ru[0]), ("command", en[1], ru[1])):
            wrong += [f"{rel}: {kind} only in English: {x}" for x in sorted(a - b)]
            wrong += [f"{rel}: {kind} only in Russian: {x}" for x in sorted(b - a)]
    assert wrong == [], "\n".join(wrong)


def _targets(text: str) -> list[str]:
    prose = _INLINE_CODE.sub("", "\n".join(_split(text)[0]))
    return _LINK.findall(prose) + _LINK_DEFINITION.findall(prose)


def test_translations_links_resolve():
    """A link of a translation reaches a file or a directory, and its anchor a heading of that file."""
    wrong: list[str] = []
    for english in _translated():
        russian = _russian(english)
        for target in _targets(russian.read_text(encoding="utf-8")):
            if re.match(r"[a-z][a-z0-9+.-]*:", target):
                continue
            file, _, anchor = target.partition("#")
            path = (russian.parent / file).resolve() if file else russian
            if not path.exists():
                wrong.append(f"{russian.relative_to(ROOT)}: {target} — no such file")
            elif anchor and (not path.is_file() or anchor not in _anchors(path.read_text(encoding="utf-8"))):
                wrong.append(f"{russian.relative_to(ROOT)}: {target} — no such heading")
    assert wrong == [], "\n".join(wrong)


def test_the_translation_checks_read_markdown_as_github_does():
    text = ("# A\n\n## Одна запись\n\n### Одна запись\n\nSetext\n---\n\n## See [DSL](dsl.md) `x`\n\n"
            "~~~\n# not a heading\n~~~\n")
    assert _anchors(text) == {"a", "одна-запись", "одна-запись-1", "setext", "see-dsl-x"}
    assert _targets('[a](x.md "t") [b](<y.md>) [c](z_(1).md) `[d](no.md)`\n\n[e]: w.md\n') == ["x.md", "y.md", "z_(1).md", "w.md"]
    assert _typed("```sh\n  pip install a   # the comment\n```\npython is prose\n") == ({"pip install a"}, set())
