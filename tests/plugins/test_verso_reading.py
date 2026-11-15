"""The Claude Code plugin `verso-reading` (plugins/verso-reading) and the marketplace `verso` that lists it.

What is checked here is the plugin's shape: the manifest and the marketplace agree, every skill and
agent names itself and says when to use it, and nothing in it points at a file it does not ship —
a corpus's rules, regional notes, archives and albums are the project's, named by the project's
AGENTS.md. Whether the plugin names anything OF a corpus (its villages, surnames, shelfmarks) is the
corpus's own check (its `public-check`), which reads its words off its data: a list of them kept
here would itself publish them.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN = ROOT / "plugins" / "verso-reading"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
SKILL_FILE = "SKILL" + ".md"  # spelled apart: the repository's text check reads a bare one as a pointer into a corpus

SKILLS = {"metric-books", "census", "transcription", "agri-census-1917", "names"}
AGENTS = {"scan-reader", "dsl-writer"}

#: A pointer at a file outside the plugin: a corpus's rules and notes, its tools, a home directory, a
#: guide of the library's tree, an `@`-include (which a plugin agent cannot resolve).
_OUTSIDE = re.compile(
    r"regional[-]rules|(?<![\w-])rules/|ARCHIVES\.md|CLAUDE\.md|\.claude/|/Users/|~/|(?<![\w-])tools/|\btools\.[a-z_]"
    r"|(?<![\w-])corpus/|(?<![\w-])docs/|(?<![\w-])tests/|\.venv/|\bverso:[\w./-]|dsllint\.py|^@\S",
    re.MULTILINE)
#: A target of a corpus's Makefile (`make tf-plan`, `make generate_csv`, `make x=1`): the plugin names the
#: library's commands instead.
_MAKE = re.compile(r"\bmake (?:[a-z][a-z0-9]*[-_][a-z0-9_-]*|[a-z]+=|bootstrap|generate|db|lint|test|ci)\b")
_MD = re.compile(r"[\w.-]+\.md\b")
_PY = re.compile(r"[\w-]+\.py\b")
_ROOTED = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")
_SKILL_PATH = re.compile(r"<this skill>/([\w./-]+)")
_PROJECT_AGENTS = re.compile(r"AGENTS\.md проекта|project's AGENTS\.md|AGENTS\.md of the project", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def _texts() -> list[Path]:
    return sorted(p for p in PLUGIN.rglob("*") if p.is_file() and p.suffix in {".md", ".py", ".json", ".toml"}
                  and "__pycache__" not in p.parts)


def _frontmatter(path: Path) -> dict[str, str]:
    """The `key: value` pairs between the opening `---` lines; a `key: >` block folds its indented lines."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path.relative_to(ROOT)}: no frontmatter"
    end = lines.index("---", 1)
    out: dict[str, str] = {}
    key: str | None = None
    for line in lines[1:end]:
        if key is not None and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
            continue
        name, sep, value = line.partition(":")
        assert sep, f"{path.relative_to(ROOT)}: {line!r} is no `key: value`"
        value = value.strip()
        key = name.strip() if value in {">", "|", ">-", "|-"} else None
        out[name.strip()] = "" if key else value.strip('"').strip("'")
    return out


def test_the_marketplace_lists_the_plugin_under_its_own_name():
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert market["name"] == "verso"
    assert market["owner"]["name"]
    [entry] = market["plugins"]
    assert entry["name"] == manifest["name"] == "verso-reading"
    assert entry["source"] == "./plugins/verso-reading"
    assert (MARKETPLACE.parent.parent / entry["source"]).resolve() == PLUGIN.resolve()
    assert manifest["description"]
    # No `version`, in the manifest or the entry: Claude Code then versions the plugin by the commit it was
    # installed from, so a corpus that moves its pin to a new tag gets the new plugin. A version written here
    # would keep every user on the copy they first cached until someone remembered to raise it.
    assert "version" not in manifest and "version" not in entry
    assert set(manifest) <= {"name", "version", "description", "author", "homepage", "repository", "license", "keywords"}


def test_every_skill_and_agent_names_itself_and_says_when():
    skills = {p.parent.name: p for p in PLUGIN.glob(f"skills/*/{SKILL_FILE}")}
    agents = {p.stem: p for p in PLUGIN.glob("agents/*.md")}
    assert set(skills) == SKILLS
    assert set(agents) == AGENTS
    for name, path in {**skills, **agents}.items():
        meta = _frontmatter(path)
        assert meta.get("name") == name, path.relative_to(ROOT)
        assert len(meta.get("description", "")) > 40, path.relative_to(ROOT)


def test_an_agent_preloads_the_plugins_own_skills():
    for path in PLUGIN.glob("agents/*.md"):
        preloaded = _frontmatter(path).get("skills", "")
        for skill in filter(None, (s.strip() for s in preloaded.split(","))):
            assert skill.startswith("verso-reading:") and skill.split(":", 1)[1] in SKILLS, (path.name, skill)


def test_nothing_points_outside_the_plugin():
    shipped = {p.name for p in PLUGIN.rglob("*") if p.is_file()}
    wrong: list[str] = []
    for path in _texts():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), start=1):
            for pattern in (_OUTSIDE, _MAKE):
                if m := pattern.search(line):
                    wrong.append(f"{rel}:{n}: {m.group(0)!r} in {line.strip()[:100]}")
            for m in _MD.finditer(line):
                name = m.group(0)
                if name == "AGENTS.md" and _PROJECT_AGENTS.search(line):
                    continue
                if name not in {"MEMORY.md"} and name not in shipped:
                    wrong.append(f"{rel}:{n}: {name}")
            wrong += [f"{rel}:{n}: {m.group(0)}" for m in _PY.finditer(line) if m.group(0) not in shipped]
        for m in _ROOTED.finditer(text):
            if not (PLUGIN / m.group(1)).exists():
                wrong.append(f"{rel}: ${{CLAUDE_PLUGIN_ROOT}}/{m.group(1)} does not exist")
    assert wrong == [], "\n".join(wrong)


def _commands_named() -> dict[str, set[str]]:
    """`verso <command> …` as the plugin writes it: in inline code, or a line of a code block."""
    named: dict[str, set[str]] = {}
    for path in PLUGIN.rglob("*.md"):
        fence = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if _FENCE.match(line):
                fence = not fence
                continue
            spans = [line.strip()] if fence else re.findall(r"`([^`\n]*)`", line)
            for span in spans:
                if m := re.match(r"verso ([a-z][a-z0-9-]*)(.*)", span):
                    named.setdefault(m.group(1), set()).update(re.findall(r"--[a-z][a-z0-9-]*", m.group(2)))
    return named


def test_the_commands_it_names_are_the_librarys():
    named = _commands_named()
    assert named
    workspace = ROOT / "tests" / "fixtures" / "workspace"
    env = {"COLUMNS": "200", "PATH": "", "VERSO_LANG": "en", "PYTHONPATH": ":".join(sys.path)}

    def help_of(*command: str) -> str:
        return subprocess.run([sys.executable, "-m", "verso.core.cli", "--workspace", str(workspace), *command, "--help"],
                              capture_output=True, text=True, env=env).stdout

    listed = set(re.findall(r"^\s+([a-z][a-z0-9-]+)\s", help_of(), re.MULTILINE))
    wrong: list[str] = []
    for command, flags in sorted(named.items()):
        if command not in listed:
            wrong.append(f"verso {command}: no such command")
            continue
        said = help_of(command)
        for group in re.findall(r"\{([a-z,-]+)\}", said):  # a command of subcommands: their flags too
            said += "".join(help_of(command, sub) for sub in group.split(","))
        wrong += [f"verso {command} {flag}: no such flag" for flag in sorted(flags) if flag not in said]
    assert wrong == [], "\n".join(wrong)


def test_a_skill_names_its_scripts_from_its_own_folder():
    """A skill says `<this skill>/scripts/x.py`, not `${CLAUDE_PLUGIN_ROOT}/…`: other agents (Codex, Gemini CLI, Copilot)
    read skill files too, and only Claude Code sets that variable. Every such path exists."""
    wrong = []
    for skill in sorted((PLUGIN / "skills").iterdir()):
        text = (skill / SKILL_FILE).read_text(encoding="utf-8")
        if "CLAUDE_PLUGIN_ROOT" in text:
            wrong.append(f"{skill.name}: ${{CLAUDE_PLUGIN_ROOT}} in a skill")
        wrong += [f"{skill.name}: <this skill>/{m.group(1)} does not exist"
                  for m in _SKILL_PATH.finditer(text) if not (skill / m.group(1)).resolve().exists()]
    assert wrong == [], "\n".join(wrong)


def test_skills_sh_finds_the_skills():
    """`npx skills add verso-genealogy/verso` (skills.sh) looks in `skills/`, `.claude/skills/` and the like, not in
    a plugin's folder: `skills.sh.json` at the root points it there."""
    paths = json.loads((ROOT / "skills.sh.json").read_text(encoding="utf-8"))["paths"]
    assert paths == ["./plugins/verso-reading/skills"]
    assert {p.parent.name for p in (ROOT / paths[0]).glob("*/" + SKILL_FILE)} == SKILLS


def test_a_skills_scripts_live_in_its_scripts_folder():
    """One layout for every skill: its skill file at its root, its scripts in `scripts/`."""
    loose = [str(p.relative_to(PLUGIN)) for p in PLUGIN.rglob("*.py")
             if p.parent.name != "scripts" or p.parent.parent.parent != PLUGIN / "skills"]
    assert loose == [], loose


def test_the_scripts_need_only_python_and_pillow():
    scripts = sorted(PLUGIN.rglob("*.py"))
    assert scripts
    for path in scripts:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"{path.name}: a relative import"
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            assert roots <= set(sys.stdlib_module_names) | {"PIL", "__future__"}, (path.name, roots)
