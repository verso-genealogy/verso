"""The Claude Code plugin `verso-reading` (plugins/verso-reading) and the marketplace `verso` that lists it.

What is checked here is the plugin's shape: the manifest and the marketplace agree, every skill and
agent names itself and says when to use it, and nothing in it points at a file it does not ship —
a corpus's rules, regional notes, archives and albums are the project's, named by the project's
AGENTS.md. Whether the plugin names anything OF a corpus (its villages, surnames, shelfmarks) is the
corpus's own check (its `public-check`), which reads its words off its data: a list of them kept
here would itself publish them.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from verso.core.scans.cli import subcommands

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
#: A word of one owner's setup, not of reading: where the frames come from is the project's (its AGENTS.md).
#: HEIC is the input of `verso scans jpeg` and may be named on the line that names it.
_SETUP = re.compile(r"verso-scans|\bPhotos\b|Photos\.sqlite|ZGENERICALBUM|osxphotos|photoscript|Google Drive|HEIC")
_PROJECT_AGENTS = re.compile(r"AGENTS\.md проекта|project's AGENTS\.md|AGENTS\.md of the project", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
#: The files a harness reads as a project's context on its own: the README, which says what another harness needs,
#: may name them; they point at no file of a corpus.
_HARNESS_FILES = re.compile(r"`(?:CLAUDE|GEMINI)\.md`")
README = PLUGIN / "README.md"


def _texts() -> list[Path]:
    return sorted(p for p in PLUGIN.rglob("*") if p.is_file() and p.suffix in {".md", ".py", ".json", ".toml"}
                  and "__pycache__" not in p.parts)


def _frontmatter(path: Path) -> dict[str, object]:
    """The YAML between the opening `---` lines, read by a YAML parser (PyYAML, a pin of requirements-dev.txt): what a
    harness reads, not what a line reader guesses."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path.relative_to(ROOT)}: no frontmatter"
    end = lines.index("---", 1)
    meta = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(meta, dict), f"{path.relative_to(ROOT)}: the frontmatter is no mapping"
    return meta


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


#: The Agent Skills standard (agentskills.io/specification): a skill's frontmatter keys, and its name.
_SKILL_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
#: Claude Code's subagent frontmatter, the keys a plugin agent may carry, and the tools this plugin's agents may name.
_AGENT_KEYS = {"name", "description", "tools", "disallowedTools", "model", "effort", "memory", "skills", "color",
               "maxTurns"}
_TOOLS = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill", "Agent", "WebFetch", "WebSearch", "NotebookEdit"}


def test_every_skill_and_agent_names_itself_and_says_when():
    skills = {p.parent.name: p for p in PLUGIN.glob(f"skills/*/{SKILL_FILE}")}
    agents = {p.stem: p for p in PLUGIN.glob("agents/*.md")}
    assert set(skills) == SKILLS
    assert set(agents) == AGENTS
    for name, path in {**skills, **agents}.items():
        meta = _frontmatter(path)
        assert meta.get("name") == name, path.relative_to(ROOT)
        assert isinstance(meta.get("description"), str) and len(meta["description"]) > 40, path.relative_to(ROOT)


def test_a_skill_keeps_to_the_standard():
    """What every harness of the standard reads: the name (≤ 64, lowercase words joined by single hyphens, its
    directory's), the description (≤ 1024), `compatibility` (≤ 500), and no key of one harness's own."""
    wrong: list[str] = []
    for path in sorted(PLUGIN.glob(f"skills/*/{SKILL_FILE}")):
        rel, meta = path.relative_to(ROOT).as_posix(), _frontmatter(path)
        name, description = str(meta.get("name", "")), str(meta.get("description", ""))
        if not (_SKILL_NAME.match(name) and len(name) <= 64 and name == path.parent.name):
            wrong.append(f"{rel}: name {name!r}")
        if not 0 < len(description) <= 1024:
            wrong.append(f"{rel}: description of {len(description)} characters")
        if not 0 < len(str(meta.get("compatibility", "-"))) <= 500:
            wrong.append(f"{rel}: compatibility of {len(str(meta['compatibility']))} characters")
        if extra := set(meta) - _SKILL_KEYS:
            wrong.append(f"{rel}: keys outside the standard {sorted(extra)}")
    assert wrong == [], "\n".join(wrong)


def test_an_agent_names_what_claude_code_resolves():
    """An agent's keys are Claude Code's subagent fields; its tools are tools there are (a removed one is dropped
    without a word); a preloaded skill is one the plugin ships."""
    wrong: list[str] = []
    for path in sorted(PLUGIN.glob("agents/*.md")):
        meta = _frontmatter(path)
        if extra := set(meta) - _AGENT_KEYS:
            wrong.append(f"{path.name}: keys {sorted(extra)}")
        tools = {t.strip() for t in str(meta.get("tools", "")).split(",") if t.strip()}
        if unknown := tools - _TOOLS:
            wrong.append(f"{path.name}: tools {sorted(unknown)}")
        preloaded = meta.get("skills") or []
        for skill in preloaded if isinstance(preloaded, list) else [preloaded]:
            if str(skill).split(":", 1)[-1] not in SKILLS:
                wrong.append(f"{path.name}: skill {skill!r}")
        if "Task tool" in str(meta.get("description", "")):
            wrong.append(f"{path.name}: the Task tool is the Agent tool")
    assert wrong == [], "\n".join(wrong)


def test_every_plugin_name_it_gives_is_shipped():
    """`verso-reading:<name>` is a skill or an agent of the plugin."""
    wrong = [f"{path.relative_to(ROOT).as_posix()}: verso-reading:{m.group(1)}"
             for path in _texts() for m in re.finditer(r"verso-reading:([a-z0-9-]+)", path.read_text(encoding="utf-8"))
             if m.group(1) not in SKILLS | AGENTS]
    assert wrong == [], "\n".join(wrong)


def test_nothing_points_outside_the_plugin():
    shipped = {p.name for p in PLUGIN.rglob("*") if p.is_file()}
    wrong: list[str] = []
    for path in _texts():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), start=1):
            if path == README:
                line = _HARNESS_FILES.sub("``", line)
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


#: A command whose subcommands each take flags of their own: a flag is looked up in its subcommand's help.
_PER_SUBCOMMAND = {"scans"}
#: A subcommand of `verso scans` named in inline code without `verso scans` before it, and a flag after it.
_BARE = re.compile(rf"^({'|'.join(sorted(subcommands()))})(\s+--.*)$")


def _commands_named() -> dict[tuple[str, ...], set[str]]:
    """`verso <command> …` as the plugin writes it: in inline code, or a line of a code block (with the lines a
    trailing backslash continues). `verso scans <sub> …` is keyed by its subcommand."""
    named: dict[tuple[str, ...], set[str]] = {}
    for path in PLUGIN.rglob("*.md"):
        fence = False
        carried = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if _FENCE.match(line):
                fence, carried = not fence, ""
                continue
            if fence:
                line = carried + " " + line.strip() if carried else line.strip()
                if line.endswith("\\"):
                    carried = line[:-1]
                    continue
                carried = ""
            spans = [line] if fence else re.findall(r"`([^`\n]*)`", line)
            for span in spans:
                if not fence and (bare := _BARE.match(span)):
                    # `crops --x0/--x1`, `zoom --row N OF`: a subcommand of `verso scans` named alone, with its flags.
                    named.setdefault(("scans", bare.group(1)), set()).update(
                        re.findall(r"--[a-z][a-z0-9-]*", bare.group(2)))
                    continue
                if not (m := re.match(r"verso ([a-z][a-z0-9-]*)(.*)", span)):
                    continue
                key, rest = (m.group(1),), m.group(2)
                if key[0] in _PER_SUBCOMMAND and (sub := re.match(r"\s+([a-z][a-z0-9-]*)(.*)", rest)):
                    key, rest = (key[0], sub.group(1)), sub.group(2)
                named.setdefault(key, set()).update(re.findall(r"--[a-z][a-z0-9-]*", rest))
    return named


def test_the_commands_it_names_are_the_librarys():
    named = _commands_named()
    assert named
    assert any(key[0] == "scans" and len(key) == 2 for key in named), "the skills read with `verso scans <sub>`"
    workspace = ROOT / "tests" / "fixtures" / "workspace"
    env = {"COLUMNS": "200", "PATH": "", "VERSO_LANG": "en", "PYTHONPATH": ":".join(sys.path)}

    def help_of(*command: str) -> str:
        return subprocess.run([sys.executable, "-m", "verso.core.cli", "--workspace", str(workspace), *command, "--help"],
                              capture_output=True, text=True, env=env).stdout

    def has(said: str, flag: str) -> bool:
        return re.search(re.escape(flag) + r"(?![\w-])", said) is not None

    listed = set(re.findall(r"^\s+([a-z][a-z0-9-]+)\s", help_of(), re.MULTILINE))
    wrong: list[str] = []
    for key, flags in sorted(named.items()):
        command = key[0]
        if command not in listed:
            wrong.append(f"verso {command}: no such command")
            continue
        said = help_of(command)
        if len(key) == 2:
            if key[1] not in set(re.findall(r"^\s+([a-z][a-z0-9-]+)\s", said, re.MULTILINE)):
                wrong.append(f"verso {' '.join(key)}: no such subcommand")
                continue
            said = help_of(*key)
        else:
            for group in re.findall(r"\{([a-z,-]+)\}", said):  # a command of subcommands: their flags too
                said += "".join(help_of(command, sub) for sub in group.split(","))
        wrong += [f"verso {' '.join(key)} {flag}: no such flag" for flag in sorted(flags) if not has(said, flag)]
    assert wrong == [], "\n".join(wrong)


def test_a_skill_names_no_plugin_root():
    """`${CLAUDE_PLUGIN_ROOT}` is set by Claude Code only; other agents (Codex, Gemini CLI, Copilot) read skill files too."""
    wrong = [skill.name for skill in sorted((PLUGIN / "skills").iterdir())
             if "CLAUDE_PLUGIN_ROOT" in (skill / SKILL_FILE).read_text(encoding="utf-8")]
    assert wrong == []


def test_no_scripts_in_the_plugin():
    """The scan tools are the library's command `verso scans`: the plugin ships text, not a copy of them."""
    shipped = [str(p.relative_to(PLUGIN)) for p in PLUGIN.rglob("*")
               if (p.is_file() and p.suffix == ".py") or (p.is_dir() and p.name == "scripts")]
    assert shipped == [], shipped
    said = [str(p.relative_to(PLUGIN)) for p in _texts() if "<this skill>" in p.read_text(encoding="utf-8")]
    assert said == [], said


def test_no_word_of_an_owners_setup():
    """The input of a skill is a directory of a дело's frames; a photo library, a cloud folder, an App's command are
    one owner's way of getting them there, and the project's AGENTS.md says which."""
    wrong: list[str] = []
    for path in _texts():
        rel = path.relative_to(ROOT).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for m in _SETUP.finditer(line):
                if m.group(0) == "HEIC" and "verso scans jpeg" in line:
                    continue
                wrong.append(f"{rel}:{n}: {m.group(0)!r} in {line.strip()[:100]}")
    assert wrong == [], "\n".join(wrong)


def test_skills_sh_finds_the_skills():
    """`npx skills add verso-genealogy/verso` (skills.sh) looks in `skills/`, `.claude/skills/` and the like, not in
    a plugin's folder: `skills.sh.json` at the root points it there."""
    paths = json.loads((ROOT / "skills.sh.json").read_text(encoding="utf-8"))["paths"]
    assert paths == ["./plugins/verso-reading/skills"]
    assert {p.parent.name for p in (ROOT / paths[0]).glob("*/" + SKILL_FILE)} == SKILLS


#: A requirement of the library as the plugin writes it: `verso-core[scans]>=0.1.41`, `'verso-ru>=0.1.41'`.
_FLOOR = re.compile(r"verso-(core|ru)(?:\[[a-z,]+\])?>=(\d+(?:\.\d+)+)")


def _stamped(package: str) -> str:
    """The version `packages/<package>/pyproject.toml` stamps, its `.devN` cut: the release this tree becomes."""
    text = (ROOT / "packages" / package / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert version, package
    return re.sub(r"\.dev\d+$", "", version.group(1))


def test_the_install_floor_is_the_release_this_tree_becomes():
    """A floor below it is satisfied by a release without what the skills name (`verso scans` came in 0.1.41, a
    release after 0.1.40 was cut): pip installs that one, or keeps it, and the command is missing."""
    floors = [(path.relative_to(ROOT).as_posix(), m.group(1), m.group(2))
              for path in _texts() for m in _FLOOR.finditer(path.read_text(encoding="utf-8"))]
    assert floors, "the skills say how to install the library"
    wrong = [f"{rel}: verso-{package}>={floor}, the tree stamps {_stamped('verso-' + package)}"
             for rel, package, floor in floors if floor != _stamped("verso-" + package)]
    assert wrong == [], "\n".join(wrong)
