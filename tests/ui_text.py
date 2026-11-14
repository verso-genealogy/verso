"""The interface's Cyrillic text, a ratchet that only shrinks: every source line of the
project's code where a string constant holds Cyrillic, counted per file into `tests/ui_text.tsv`.

A new line of the interface's text goes through a catalog (`t("key", …)`), and the count of a file
falls as its messages move there. What is not the interface — generated content, the sources'
vocabulary — is declared in `tests/ui_content.toml`, a module (or a glob of them) and why, or marked
on its line with `# i18n: content` (in JS `// i18n: content`, in HTML `<!-- i18n: content -->`).
A page's markup (`.html`) counts the lines where its text or an attribute's value holds
Cyrillic: its words go into `data-i18n*` attributes, which hold keys. A docstring is not counted, nor a
comment. A declared module still counts its messages: a string raised, printed or warned there is
the interface all the same (`python_sinks`), so a mask hides no message.

    python -m tests.ui_text [--check]      # fail on a rise and on a line the list holds too high
    python -m tests.ui_text --update       # write the counts down; refused if one rose
    python -m tests.ui_text --base REV     # the ceiling is REV's tree counted by these same rules
    python -m tests.ui_text --seed         # write the first list

The project is the directory above this file's `tests/`: the library's (`lib/`) and the App's
(`app/`) each keep a copy, byte for byte (`make fixture-copies`), and their own list and content.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parent.parent
LIST = Path("tests") / "ui_text.tsv"
CONTENT = Path("tests") / "ui_content.toml"
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")   # the whole block: і ѣ ѳ ѵ too
_PY_MARK = "# i18n: content"
_JS_MARK = "// i18n: content"
_HEADER = """\
# The interface's Cyrillic text (tests/ui_text.py): per file, the lines of code where a string
# holds Cyrillic. Only shrinks — a new message goes through a catalog (t(…)); content and the
# sources' vocabulary are declared in tests/ui_content.toml or marked `# i18n: content`.
# file\tlines
"""


class ContentError(ValueError):
    """tests/ui_content.toml cannot be read: the message names the entry."""


@dataclass(frozen=True)
class Content:
    roots: tuple[str, ...]                       # the code counted, relative to the project
    modules: tuple[tuple[str, str], ...]         # (a path or a glob, why) — content, not counted
    skip: tuple[str, ...] = ()                   # globs never read (markup: 0.1.3)

    def declared(self, rel: str) -> bool:
        path = PurePosixPath(rel)
        return any(path.full_match(pattern) for pattern, _ in self.modules)

    def skipped(self, rel: str) -> bool:
        return any(PurePosixPath(rel).full_match(pattern) for pattern in self.skip)


def read_content(path: Path) -> Content:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    content = data.get("content", {})
    modules: list[tuple[str, str]] = []
    for entry in content.get("modules", []):
        where, why = entry.get("path"), entry.get("why")
        if not isinstance(where, str) or not where:
            raise ContentError(f"{path}: модуль содержания без path")
        if not isinstance(why, str) or not why.strip():
            raise ContentError(f"{path}: {where} — без причины (why)")
        modules.append((where, why))
    return Content(tuple(data.get("roots", ())), tuple(modules), tuple(content.get("skip", ())))


# ---------------------------------------------------------------- Python

def _docstrings(tree: ast.AST) -> set[tuple[int, int]]:
    """The (line, column) where each docstring of the module starts."""
    out: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                out.add((first.value.lineno, first.value.col_offset))
    return out


def python_lines(text: str) -> set[int]:
    """The lines of `text` where a string (not a docstring) holds Cyrillic, but those marked."""
    docs = _docstrings(ast.parse(text))
    lines = text.splitlines()
    marked = {n for n, line in enumerate(lines, start=1) if _PY_MARK in line}
    out: set[int] = set()
    kinds = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1), getattr(tokenize, "TSTRING_MIDDLE", -1)}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in kinds or token.start in docs:
            continue
        (first, _), (last, _) = token.start, token.end
        if last in marked:
            continue
        out.update(n for n in range(first, last + 1)
                   if n not in marked and _CYRILLIC.search(lines[n - 1]) and _CYRILLIC.search(token.string))
    return out


_SINK_CALLS = frozenset({"print", "warn", "write", "exit", "SystemExit"})


def _a_sink(call: ast.Call) -> bool:
    name = call.func.id if isinstance(call.func, ast.Name) else \
        call.func.attr if isinstance(call.func, ast.Attribute) else ""
    return name in _SINK_CALLS or name.endswith(("Error", "Exception", "Warning"))


def python_sinks(text: str) -> set[int]:
    """The lines of `text` where a string holding Cyrillic is said to a person: raised, or passed to
    an exception, `print`, `warn`, `write` or `exit` — but those marked."""
    lines = text.splitlines()
    marked = {n for n, line in enumerate(lines, start=1) if _PY_MARK in line}
    out: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        said: list[ast.AST] = []
        if isinstance(node, ast.Raise) and node.exc is not None:
            said.append(node.exc)
        elif isinstance(node, ast.Call) and _a_sink(node):
            said.extend([*node.args, *(k.value for k in node.keywords)])
        for part in said:
            for leaf in ast.walk(part):
                if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str) and _CYRILLIC.search(leaf.value):
                    out.update(n for n in range(leaf.lineno, (leaf.end_lineno or leaf.lineno) + 1)
                               if n not in marked and _CYRILLIC.search(lines[n - 1]))
    return out


# ---------------------------------------------------------------- JS (tools/verso_js_vocabulary.py's lexer)

class LexerLost(ValueError):
    """The lexer reached the end inside a string, a template, a comment or a `${…}`."""


def _quoted_end(text: str, i: int) -> int:
    quote, j = text[i], i + 1
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 3 if text.startswith("\r\n", j + 1) else 2
        elif c == quote:
            return j + 1
        elif c == "\n":
            raise LexerLost(f"строка {text.count(chr(10), 0, i) + 1}: кавычка не закрыта до конца строки")
        else:
            j += 1
    raise LexerLost(f"строка {text.count(chr(10), 0, i) + 1}: кавычка не закрыта до конца файла")


def _template_part(text: str, i: int) -> tuple[int, bool]:
    j = i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
        elif c == "`":
            return j + 1, False
        elif text.startswith("${", j):
            return j + 2, True
        else:
            j += 1
    raise LexerLost(f"строка {text.count(chr(10), 0, i) + 1}: шаблон `…` не закрыт до конца файла")


def _regex_end(text: str, i: int) -> int | None:
    j, in_class = i + 1, False
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n":
            return None
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return j + 1
        j += 1
    return None


_WORD = re.compile(r"\w+")
_NUMBER = re.compile(r"\d[\w.]*")
_BEFORE_REGEX = frozenset("(,=:[!&|?{};+-*%<>~^")
_STATEMENT_HEADS = frozenset({"if", "while", "for", "with"})
_REGEX_WORDS = frozenset({"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void",
                          "throw", "instanceof", "yield", "await"})
_VALUE = "value"


def js_spans(text: str) -> list[tuple[int, int]]:
    """The (start, end) offsets of every string, template text and regex body of `text`."""
    out: list[tuple[int, int]] = []
    i, n = 0, len(text)
    braces: list[int] = []
    heads: list[bool] = []
    last = ""
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise LexerLost(f"строка {text.count(chr(10), 0, i) + 1}: комментарий /* не закрыт")
            i = end + 2
        elif c in "'\"":
            end = _quoted_end(text, i)
            out.append((i, end))
            i, last = end, _VALUE
        elif c == "`" or (c == "}" and braces and braces[-1] == 0):
            if c == "}":
                braces.pop()
            end, opened = _template_part(text, i + 1)
            out.append((i, end))
            if opened:
                braces.append(0)
            i, last = end, ("{" if opened else _VALUE)
        elif c == "/" and (last == "" or last in _BEFORE_REGEX or last in _REGEX_WORDS) \
                and (end := _regex_end(text, i)) is not None:
            out.append((i, end))
            flags = _WORD.match(text, end)
            i, last = (flags.end() if flags else end), _VALUE
        elif "0" <= c <= "9":
            m = _NUMBER.match(text, i)
            assert m is not None
            i, last = m.end(), _VALUE
        elif (m := _WORD.match(text, i)) is not None:
            i, last = m.end(), m.group()
        else:
            if c == "{" and braces:
                braces[-1] += 1
            elif c == "}" and braces:
                braces[-1] -= 1
            if c in "+-" and text.startswith(c * 2, i):
                i, last = i + 2, _VALUE
            elif c == "(":
                heads.append(last in _STATEMENT_HEADS)
                i, last = i + 1, c
            elif c == ")" and heads and heads.pop():
                i, last = i + 1, ";"
            else:
                i, last = i + 1, c
    if braces:
        raise LexerLost("файл кончился внутри ${…} шаблона")
    return out


def js_lines(text: str) -> set[int]:
    """The lines of `text` where a string, a template's text or a regex holds Cyrillic, but
    those marked `// i18n: content`; never a comment."""
    lines = text.splitlines()
    marked = {n for n, line in enumerate(lines, start=1) if _JS_MARK in line}
    out: set[int] = set()
    for start, end in js_spans(text):
        piece = text[start:end]
        if not _CYRILLIC.search(piece):
            continue
        first = text.count("\n", 0, start) + 1
        for k, part in enumerate(piece.split("\n")):
            if _CYRILLIC.search(part) and first + k not in marked:
                out.add(first + k)
    return out


_HTML_MARK = "i18n: content"


def html_lines(text: str) -> set[int]:
    """The lines of a page's markup where its text or an attribute's value holds Cyrillic, but those
    marked `<!-- i18n: content -->`; never a comment, a script or a style."""
    from html.parser import HTMLParser

    lines = text.splitlines()
    marked = {n for n, line in enumerate(lines, start=1) if _HTML_MARK in line}
    out: set[int] = set()

    class _Reader(HTMLParser):
        skipping = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in ("script", "style"):
                self.skipping += 1
            first, _ = self.getpos()
            raw = self.get_starttag_text() or ""
            for k, part in enumerate(raw.split("\n")):
                if _CYRILLIC.search(part) and first + k not in marked:
                    out.add(first + k)
            del attrs

        handle_startendtag = handle_starttag

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style") and self.skipping:
                self.skipping -= 1

        def handle_data(self, data: str) -> None:
            if self.skipping or not _CYRILLIC.search(data):
                return
            first, _ = self.getpos()
            for k, part in enumerate(data.split("\n")):
                if _CYRILLIC.search(part) and first + k not in marked:
                    out.add(first + k)

    _Reader(convert_charrefs=True).feed(text)
    return out


# ---------------------------------------------------------------- the count

_SUFFIXES = {".py": python_lines, ".js": js_lines, ".mjs": js_lines, ".html": html_lines}


def count_text(rel: str, text: str) -> int:
    reader = _SUFFIXES.get(PurePosixPath(rel).suffix)
    return len(reader(text)) if reader is not None else 0


def _files(project: Path, content: Content) -> dict[str, str]:
    out: dict[str, str] = {}
    for root in content.roots:
        for path in sorted((project / root).rglob("*")):
            rel = path.relative_to(project).as_posix()
            if path.is_file() and path.suffix in _SUFFIXES and "__pycache__" not in rel \
                    and "node_modules" not in rel and not content.skipped(rel):
                out[rel] = path.read_text(encoding="utf-8")
    return out


def counts_of(files: Mapping[str, str], content: Content) -> dict[str, int]:
    """Each file's count; a declared module counts its messages alone (`python_sinks`)."""
    out = {rel: (len(python_sinks(text)) if rel.endswith(".py") else 0) if content.declared(rel)
           else count_text(rel, text) for rel, text in files.items()}
    return {rel: n for rel, n in sorted(out.items()) if n}


def counts(roots: Iterable[Path], content: Content) -> dict[str, int]:
    """Each file's count under `roots` (a project directory each), declared content left out."""
    out: dict[str, int] = {}
    for project in roots:
        out.update(counts_of(_files(project, content), content))
    return out


def _at(project: Path, rev: str, content: Content) -> dict[str, str]:
    """The project's counted files as they stand at `rev` (git, from the project's directory)."""
    prefix = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=project, capture_output=True, text=True,
                            check=True).stdout.strip()
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "--full-name", rev, "--", *content.roots], cwd=project,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    out: dict[str, str] = {}
    for full in listed:
        rel = full[len(prefix):] if full.startswith(prefix) else full
        if PurePosixPath(rel).suffix in _SUFFIXES and not content.skipped(rel):
            out[rel] = subprocess.run(["git", "show", f"{rev}:{full}"], cwd=project, capture_output=True,
                                      text=True, check=True).stdout
    return out


def read_list(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            file, n = line.split("\t")
            out[file] = int(n)
    return out


def write_list(path: Path, listed: Mapping[str, int]) -> None:
    path.write_text(_HEADER + "".join(f"{file}\t{n}\n" for file, n in sorted(listed.items())), encoding="utf-8")


def problems(found: Mapping[str, int], listed: Mapping[str, int]) -> tuple[list[str], list[str]]:
    """(rises, stale lines): a file counting more than its line says, one counting less."""
    rises, stale = [], []
    for file in sorted(found.keys() | listed.keys()):
        was, now = listed.get(file, 0), found.get(file, 0)
        if now > was:
            rises.append(f"{file}: строк с кириллицей было {was}, стало {now} — "
                         "через каталог (t(…)) или модуль содержания")
        elif now < was:
            stale.append(f"{file}: в списке {was}, а строк {now} — make ui-ratchet update=1")
    return rises, stale


def main(argv: list[str] | None = None, project: Path = PROJECT) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.ui_text", description=(__doc__ or "").split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    mode.add_argument("--seed", action="store_true")
    ap.add_argument("--base", metavar="REV")
    args = ap.parse_args(argv)
    content = read_content(project / CONTENT)
    found = counts_of(_files(project, content), content)
    listed = read_list(project / LIST)
    if args.seed:
        if listed:
            print(f"{LIST}: список уже есть — засевается один раз", file=sys.stderr)
            return 2
        write_list(project / LIST, found)
        print(f"{LIST}: файлов {len(found)}, строк {sum(found.values())}")
        return 0
    ceiling = listed
    if args.base:
        base = counts_of(_at(project, args.base, content), content)
        ceiling = {f: min(n, base.get(f, 0)) for f, n in listed.items()} | \
            {f: 0 for f in found if f not in listed}
    rises, stale = problems(found, ceiling)
    if args.update:
        if rises:
            print("\n".join(rises), file=sys.stderr)
            return 1
        write_list(project / LIST, found)
        print(f"{LIST}: файлов {len(found)}, строк {sum(found.values())}")
        return 0
    for line in (*rises, *(() if args.base else stale)):
        print(line, file=sys.stderr)
    if rises or (stale and not args.base):
        return 1
    print(f"{LIST}: в порядке — файлов {len(found)}, строк {sum(found.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
