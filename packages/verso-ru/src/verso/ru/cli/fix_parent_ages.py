"""fix-parent-ages: a civil birth's parents' ages, from the comment's prose into the fields.

    verso fix-parent-ages FILE [FILE...] [--check]

A birth of a book flagged `civil=True` whose `comment=` says «отцу 26, матери 22» (or one of the other forms
`verso.ru.parent_age_text` reads) gets `father_age=26, mother_age=22`, and the fragment leaves the comment. A
doubt stays in the comment (the field takes its first figure); a figure the field cannot take («3…») is left where
it is. The edit is the `comment=` keyword's source span, so the file's formatting is kept elsewhere.

A directory argument stands for its `*.py` files. A path that is no `.py` file, or a file that does not parse, is
reported as skipped, with its reason.

The guard, for each file: the Records JSON of the text before and after must differ in `father_age`, `mother_age`
and `comment` of births and in nothing else, and in each birth the digits that left the comment must be the digits
that entered the fields (a doubt's figure is in both); otherwise the file is left untouched and the command says why.
`--check` does everything but the write; it exits 1 when something would move, 2 when a file was refused.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.core.pipeline.load import build_text, record_types
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.linters.checks import civil_register, shared_ast
from verso.ru.messages import t
from verso.core.i18n import Message
from verso.ru.parent_age_text import (
    FATHER_ALONE, FATHER_AND_MOTHER, FIELDS, FORMS, MOTHER_ALONE, PAIR, PARENTS_1920, ROLES)

#: The keys of a birth's own `written` a move may change — and nothing else may differ.
MOVED_KEYS = ("father_age", "mother_age", "comment")


@dataclass
class Outcome:
    """What one file came to: the text it would have, the births and forms moved, why it was refused."""
    text: str
    changed: bool = False
    births: int = 0
    forms: Counter[str] = field(default_factory=Counter)
    refused: str | None = None
    skipped: str | None = None


def _literal(original: str, text: str) -> str:
    """`text` as a string literal, in the quote the original was written with when that is plain."""
    if original[:1] == "'" and original[-1:] == "'" and not original.startswith("'''") and not any(
            c in text for c in "'\\\n\r"):
        return f"'{text}'"
    return json.dumps(text, ensure_ascii=False)


def _offsets(source: bytes) -> list[int]:
    starts = [0]
    for line in source.split(b"\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    return starts


def plan(source: str) -> tuple[str, int, Counter[str]]:
    """(the text with the ages moved, the births it touched, the forms by count)."""
    tree = shared_ast.parse(source)
    raw = source.encode("utf-8")
    starts = _offsets(raw)
    edits: list[tuple[int, int, str]] = []
    forms: Counter[str] = Counter()
    births = 0

    def span(keyword: ast.keyword) -> tuple[int, int]:
        assert keyword.end_lineno is not None and keyword.end_col_offset is not None
        return (starts[keyword.lineno - 1] + keyword.col_offset,
                starts[keyword.end_lineno - 1] + keyword.end_col_offset)

    for birth in civil_register.civil_births(tree):
        move = civil_register.parent_age_moves(birth)
        if move is None:
            continue
        keyword, reading, nones = move
        for role, none in nones.items():        # `father_age=None` takes its figure where it stands
            if role in reading.ages:
                edits.append((*span(none), f"{FIELDS[role]}={reading.ages[role]}"))
        start, end = span(keyword)
        parts = [f"{FIELDS[role]}={reading.ages[role]}" for role in ROLES if role in reading.ages and role not in nones]
        if reading.comment:
            written = ast.get_source_segment(source, keyword.value) or ""
            parts.append(f"comment={_literal(written, reading.comment)}")
        if not parts:                           # the keyword goes, with the comma that joined it
            if raw[end:end + 2] == b", ":
                end += 2
            elif raw[start - 2:start] == b", ":
                start -= 2
        edits.append((start, end, ", ".join(parts)))
        births += 1
        forms.update(reading.forms)
    for start, end, text in sorted(edits, reverse=True):
        raw = raw[:start] + text.encode("utf-8") + raw[end:]
    return raw.decode("utf-8"), births, forms


def _encoded(path: Path, text: str) -> dict[str, Any]:
    namespace = build_text(path, text)
    sets = {name: value for name, value in namespace.items() if isinstance(value, record_types())}
    doc = encode_namespace(sets, village=path.parent.parent.name, file=path.name, sha256="0" * 64, ids=Ids())
    return json.loads(json.dumps(doc, ensure_ascii=False))


def _births(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for node in doc.get("documents", ()) for run in node.get("pages", ())
            for record in run["records"] if record.get("kind") == "birth"]


def _runs(text: object) -> Counter[str]:
    return Counter(re.findall(r"\d+", "" if text is None else str(text)))


def _digits_lost(was: dict[str, Any], now: dict[str, Any]) -> str | None:
    """The digits a birth's move did not account for, or None. What left the comment must be what entered the
    fields; a figure the field took and the comment kept (a doubt) is in both, so it is counted once on each side."""
    old, new = was.get("written", {}), now.get("written", {})
    taken = Counter[str]()
    for key in MOVED_KEYS[:2]:
        if old.get(key) is None:
            taken += _runs(new.get(key))
    before, after = _runs(old.get("comment")), _runs(new.get("comment"))
    removed, added = before - after, after - before
    kept_doubts = taken - removed
    if added or removed - taken or kept_doubts - after:
        return " ".join(sorted((added + (removed - taken) + (kept_doubts - after)).elements())) or "?"
    return None


def guard(path: Path, before: str, after: str) -> str | None:
    """Why `after` may not replace `before`, or None: the Records JSON of the two differ by
    `father_age`, `mother_age` and `comment` of births, and by nothing else."""
    try:
        old = _encoded(path, before)
    except Exception as exc:    # a text that does not build is a refusal, whatever it raised
        return str(t("cli.fix_parent_ages.guard_build", side=t("cli.fix_parent_ages.side_before"),
                     error=f"{type(exc).__name__}: {exc}"))
    try:
        new = _encoded(path, after)
    except Exception as exc:
        return str(t("cli.fix_parent_ages.guard_build", side=t("cli.fix_parent_ages.side_after"),
                     error=f"{type(exc).__name__}: {exc}"))
    for was, now in zip(_births(old), _births(new), strict=False):
        for key in MOVED_KEYS[:2]:
            if was.get("written", {}).get(key) is not None and was["written"][key] != now.get("written", {}).get(key):
                return str(t("cli.fix_parent_ages.guard_written", id=was["id"], key=key))
    for was, now in zip(_births(old), _births(new), strict=False):
        if (lost := _digits_lost(was, now)) is not None:
            return str(t("cli.fix_parent_ages.guard_digits", id=was["id"], digits=lost))
    for doc in (old, new):
        for record in _births(doc):
            for key in MOVED_KEYS:
                record.get("written", {}).pop(key, None)
    if old != new:
        what = next((was["id"] for was, now in zip(_births(old), _births(new), strict=False) if was != now), "?")
        return str(t("cli.fix_parent_ages.guard_differs", id=what))
    return None


def fix_file(path: Path, *, check: bool = False) -> Outcome:
    """Move the ages of one file; write it unless `check`, the guard refuses, or nothing moved."""
    with path.open(encoding="utf-8", newline="") as handle:      # line endings are the file's own
        source = handle.read()
    try:
        text, births, forms = plan(source)
    except SyntaxError as exc:
        return Outcome(source, skipped=str(t("cli.fix_parent_ages.unparsable", error=f"{type(exc).__name__}: {exc}")))
    if not births:
        return Outcome(source)
    refusal = guard(path, source, text)
    if refusal is not None:
        return Outcome(source, births=births, forms=forms, refused=refusal)
    if not check:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    return Outcome(text, changed=True, births=births, forms=forms)


def _form_words() -> dict[str, Message]:
    return {FATHER_AND_MOTHER: t("cli.fix_parent_ages.form.father_and_mother"),
            FATHER_ALONE: t("cli.fix_parent_ages.form.father"),
            MOTHER_ALONE: t("cli.fix_parent_ages.form.mother"),
            PAIR: t("cli.fix_parent_ages.form.pair"),
            PARENTS_1920: t("cli.fix_parent_ages.form.parents_1920")}


def _forms_said(forms: Counter[str]) -> str:
    words = _form_words()
    return ", ".join(f"{words[form]}: {forms[form]}" for form in FORMS if forms[form])


def expand(paths: list[Path]) -> tuple[list[Path], list[tuple[Path, str]]]:
    """(the `.py` files the arguments name, directories expanded; the arguments left out, with why)."""
    files: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(f for f in path.rglob("*.py") if not any(
                part.startswith(".") or part == ".venv" for part in f.relative_to(path).parts[:-1])))
        elif not path.is_file():
            skipped.append((path, str(t("cli.fix_parent_ages.not_found"))))
        elif path.suffix != ".py":
            skipped.append((path, str(t("cli.fix_parent_ages.not_py"))))
        else:
            files.append(path)
    return files, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="verso fix-parent-ages", description=str(t("cli.fix_parent_ages.description")))
    ap.add_argument("files", nargs="+", type=Path, help=str(t("cli.fix_parent_ages.help_files")))
    ap.add_argument("--check", action="store_true", help=str(t("cli.fix_parent_ages.help_check")))
    args = ap.parse_args(argv)
    total: Counter[str] = Counter()
    files = births = refused = 0
    paths, skipped = expand(args.files)
    for path, why in skipped:
        print(t("cli.fix_parent_ages.skipped", path=path, why=why), file=sys.stderr)
    for path in paths:
        outcome = fix_file(path, check=args.check)
        if outcome.skipped is not None:
            skipped.append((path, outcome.skipped))
            print(t("cli.fix_parent_ages.skipped", path=path, why=outcome.skipped), file=sys.stderr)
        elif outcome.refused is not None:
            refused += 1
            print(t("cli.fix_parent_ages.refused", path=path, why=outcome.refused), file=sys.stderr)
        elif outcome.changed:
            files += 1
            births += outcome.births
            total.update(outcome.forms)
            print(t("cli.fix_parent_ages.file", path=path, births=outcome.births, forms=_forms_said(outcome.forms)))
    print(t("cli.fix_parent_ages.total_check", files=files, births=births, refused=refused, skipped=len(skipped))
          if args.check else t("cli.fix_parent_ages.total", files=files, births=births, refused=refused,
                               skipped=len(skipped)))
    words = _form_words()
    for form in FORMS:
        if total[form]:
            print(f"  {words[form]}: {total[form]}")
    if refused or skipped:
        return 2
    return 1 if args.check and births else 0


if __name__ == "__main__":
    sys.exit(main())
