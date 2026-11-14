"""Notes a proofread has made stale.

A Verso proofread changes READINGS — «Василій Сидоровъ ⚭ Наталья Петрова»
becomes «Василій Видоплясовъ ⚭ Пелагія Ежевикина» — and nothing else: the comments
above the record still argue from the old reading, and so do the notes of
other years and the corpus's own Markdown, wherever the overturned reading
was carried. One proofread of a village left such notes
in six DSL files of other years, three Markdown files and the consolidation
config, and they were found by hand.

Three steps, all read-only:

1. **What changed.** The DSL of the village is diffed between two revisions at
   the AST level: every `person(…)` is addressed by the record calls around it
   (`birth 5 MALE · mother`, `household 41 · member 10`), the two sides are
   aligned, and a person whose name, patronymic or surname lost a word is a
   CHANGE (old → new). Whitespace, case and «?» do not count; a word added
   does not either — there is nothing old to look for.
2. **Where the old form is still written.** Every adjacent pair of the old
   name's words the new name no longer has is looked for in the notes — `#`
   comments and prose kwargs of the village's DSL of every year, and the files
   the workspace's `[notes] globs` name (`note_files`) — Markdown, and the
   comments of a Python file. A PAIR, never one word: «Наталья» alone is in
   every year. Words match by stem, so «Натальей Петровой», «ВАСИЛІЯ СИДОРОВА»
   and «Василіевъ Сидоровыхъ» are found, and a pair may wrap across comment
   lines. A one-word name (a newborn, a roll member) is listed, not searched.

   A READING change («Наталья» → «Настасья») is looked for in any orthography
   (`names.match_key`). A SPELLING change — the same name by its base form,
   «Ѳомичъ» → «Фомичъ», «Алексій» → «Алексѣй» — is looked for letter by
   letter: folded, it would find the new spelling too.

   What is reported, measured against the two hand rewrites:
   - only where the note writes the WHOLE old name — «Иванъ Петровъ Сидоровъ»,
     not every «Иванъ Петровъ»;
   - a pair the DSL no longer writes anywhere: every such note;
   - a pair it still writes — a namesake («Василій Сидоровъ» is another man of
     a later year), or another record still spelled so — only a note TIED to the
     changed record: its number («№ м5») or leaf («л. 19об») cited beside the
     name in its year, its comment block, or its year as the year the note
     speaks of there (`_years_of`: the sentence, a headline, the Markdown
     section, the file). In a DSL file whose own records write the pair, only
     a number, a leaf or the block above the record ties it;
   - not a note that already says so (`--all` shows them): the new name of
     the same record beside it, or the old one written as overturned («не
     «…»», «вместо …», «… → …», «⛔ Первое чтение …», «снята», «вычитка»).

   Run on one such proofread with the notes as they stood, the report names 27
   of the note blocks the hand rewrite went on to change, and six it missed — among
   them a regional rule and an archive note, each quoting the old reading by
   name and year. What it does not see are conclusions drawn from the reading
   without naming it.
3. **Headers.** A DSL file whose header still notes `reviewed=False` while no
   record of it is held any more — one file turned up on 2026-10-13.

   Not a dsllint check on purpose: Verso refuses a save that gains a dsllint
   finding (`verso.app_dsl.validate`), so the «Вычитано» that releases a file's
   last held record would be refused over a header the page cannot edit.

A finding is a prompt to re-read a note, not a verdict. Report-only: the notes
are the user's research, and rewriting them is the user's call. `Tree` and
`build_report` read git and the files; everything above them is pure.

Run:
    python -m verso.ru.notes.stale_notes --village "Глуповы Горы"            # HEAD~1 → working tree
    python -m verso.ru.notes.stale_notes --village "Глуповы Горы" --rev HEAD~1..HEAD
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from verso.core import workspace
from verso.ru.naming.names_registry import matching_base
from verso.ru.naming.orthography import modernize_orthography
from verso.ru.naming.matching import match_key
from verso.ru.messages import t

# person()'s name fields, positional and keyword alike (`verso.ru.domain.factories.person`).
_POSITIONAL = {0: "name_orig", 1: "patr_orig", 2: "last_name_orig", 4: "patr_old"}
_NAME_FIELDS = frozenset(_POSITIONAL.values())
# The word sequences a note writes a person by: name, patronymic, surname — or the
# older patronymic a roll gives beside the name.
_SEQUENCES = (("name_orig", "patr_orig", "last_name_orig"), ("name_orig", "patr_old"))

# The calls that group records without identifying one: a record moved to another
# leaf or month is the same record.
_GROUP = re.compile(r"^(?:page|.+_month(?:_year)?|.+_records)$")
# The free-text kwargs of a record — notes as much as a comment is.
_PROSE = re.compile(r"^(?:comment|.+_note|.+_error|namesake)$")

READING = "чтение"  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
SPELLING = "написание"  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
# Who a pair names, not how: the given name by its base form (Іоаннъ = Иванъ,
# Наталія = Наталья), the rest by reading.
IDENTITY = "identity"

_WORD = re.compile(r"[^\W\d_]+")
# What may stand between the two words of a pair: spaces, line breaks, Markdown
# emphasis, quotes and brackets — not a comma, a ⚭ or a full stop.
_GAP = re.compile(r"[\s*_«»\"'`„“”()\[\]]*")
_ENDINGS = frozenset("аяыиеоуюйьъіѣ")  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
# A case ending a word may take past its stem: «Наталь|ей», «Сидоров|ыхъ».
_MAX_ENDING = 3
_MIN_STEM = 3

# A note that writes the old form as overturned has been dealt with.
_OVERTURNED_BEFORE = re.compile(r"(?:\bне|\bвместо|\bа\s+не|\bбыло|\bчиталось|\bпрочитано\s+как)\s*[«\"„*]*\s*$",  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
                                re.IGNORECASE)
_OVERTURNED_AFTER = re.compile(r"^[»\"“*\s]*(?:→|->|⟶|⇒\s*«)")
# A note that says the reading was withdrawn or redone: «⛔ Первое чтение дало …»,
# «снята вычиткой», «вычитка 13.10.2026 прочла там …». Not «ошибка чтения»: the
# notes weigh it as a hypothesis («перемена жены или ошибка чтения отчества») as
# often as they record it.
_RETRACTED = re.compile(r"сня(?:т|л)\w*|(?:перв|прежн)\w+\s+чтени\w*|вычитк\w*|⛔", re.IGNORECASE)  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
# How far from the old form the new name, or a retraction, still counts as the note's correction.
_NEAR = 300
_RETRACTED_NEAR = 80
# How far back and forth `_years_of` looks for the year a note speaks of. A note
# names the source first («МК 1872 г. даёт …», «в 1872 г. у него …»), a headline
# puts it last («… — ПАРА УЖЕ В СЕНТЯБРѢ 1871 г.»), and a year written after the
# name in the next sentence is another event's («(† 15 марта 1872)»). A sentence
# ends at «. » before a capital (not «1872 г. даёт»), a blank line, a table cell or
# a marker — not at a line break: the notes are hard-wrapped.
_YEAR_BEFORE = 100
_YEAR_AFTER = 60
_SENTENCE_END = re.compile(r"[.!?;][*»]*(?=\s+[«*(]*[А-ЯЁѢІѲA-Z])|\n\s*\n|\||[🔴⚠ⓘ✅⛔📍🆕⇒]")  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
_YEAR = re.compile(r"(?<!\d)(1[6-9]\d\d)(?!\d)")
_FILE_YEAR = re.compile(r"/(\d{4})/[^/]+\.py$")
# How close a record cited beside the old form — by number («(ч. 1 № м3)») or
# leaf («(л. 19об)») — ties it to that record, or unties it from ours.
_CITED_NEAR = 100
_CITED = re.compile(r"№\s*([мж]?)\s*(\d+)")  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
_SEX = {"MALE": "м", "FEMALE": "ж"}  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
# A comment block ending this few lines above a changed record's call is its own.
_ABOVE = 2

# A header's note about the hold: «# reviewed=False: прочитано один раз при 4.2×…».
_HELD_NOTE = re.compile(r"\breviewed\s*=\s*False\s*:")


# ---------------------------------------------------------------- folding ----

def spelling_key(word: str) -> str:
    """The word as written, less what a reading never turns on: case, ё, a final ъ."""
    return word.lower().replace("ё", "е").removesuffix("ъ")  # i18n: content — the notes' and the DSL's words it searches for, internal kinds


def reading_key(word: str) -> str:
    """The word whatever the orthography: «Ѳедорова» and «Федорова» are one reading."""
    return match_key(word).removesuffix("ъ")  # i18n: content — the notes' and the DSL's words it searches for, internal kinds


def given_key(word: str) -> str:
    """A given name by its base form (`names.csv` «Имя-основа»): «Іоаннъ» → «иван»."""
    return match_key(matching_base(modernize_orthography(word))) or reading_key(word)


def stem(key: str) -> str:
    """The folded word less its case ending, for matching an inflected note."""
    out = key
    while len(out) > _MIN_STEM and out[-1] in _ENDINGS and len(key) - len(out) < 2:
        out = out[:-1]
    return out


def _fits(word_key: str, stem_: str) -> bool:
    return word_key.startswith(stem_) and len(word_key) - len(stem_) <= _MAX_ENDING


# --------------------------------------------------------------- the DSL -----

@dataclass(frozen=True)
class Person:
    """One `person(…)` of a DSL file, addressed by the record calls around it."""

    key: str                                  # «birth 5 MALE · mother»
    shape: str                                # the key less its record numbers
    numbered: bool                            # the key names a record by its number
    line: int
    names: tuple[tuple[str, str], ...]        # (field, value), the fields written
    leaf: str = ""                            # the лист of the `page(…)` around it
    record_line: int = 0                      # where the record call around it begins

    def words(self, fields: Sequence[str]) -> list[tuple[str, bool]]:
        """(word, is the given name) of the fields, in order."""
        values = dict(self.names)
        return [(w, f == "name_orig" and k == 0) for f in fields for k, w in enumerate(_WORD.findall(values.get(f, "")))]

    @property
    def written(self) -> str:
        values = dict(self.names)
        main = " ".join(values[f] for f in _SEQUENCES[0] if values.get(f))
        return f"{main} ({values['patr_old']})" if values.get("patr_old") else main

    def pairs(self, mode: str) -> set[tuple[str, str]]:
        """Every adjacent pair of words, folded as READING, SPELLING or IDENTITY."""
        out: set[tuple[str, str]] = set()
        for fields in _SEQUENCES:
            keys = [_fold(mode, given)(w) for w, given in self.words(fields)]
            out.update(pairwise(keys))
        return out

    def spelled(self) -> tuple[str, ...]:
        return tuple(spelling_key(w) for f in sorted(_NAME_FIELDS) for w, _ in self.words([f]))


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, (int, str))) \
            and not isinstance(node.value, bool):
        return "" if node.value is None else str(node.value)
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _ident(node: ast.Call) -> tuple[str, ...]:
    """The record number (the first positional literal) and the sex, where written."""
    out: list[str] = []
    if node.args:
        first = _literal(node.args[0])
        if first:
            out.append(first)
    out += [a.attr for a in node.args
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "Gender"]
    return tuple(out)


def _names_itself(node: ast.expr) -> bool:
    """A record inside a record names itself (member 10), and so does a group of
    records; anything else — a person among persons — is told apart by its place."""
    return isinstance(node, ast.Call) and _call_name(node) != "person" \
        and (bool(_GROUP.match(_call_name(node))) or bool(_ident(node)))


def _person(node: ast.Call, path: list[str], shape: list[str], numbered: bool, leaf: str,
            record_line: int) -> Person | None:
    names: dict[str, str] = {}
    written = [(_POSITIONAL.get(i), a) for i, a in enumerate(node.args)]
    written += [(kw.arg, kw.value) for kw in node.keywords]
    for name, value in written:
        if name not in _NAME_FIELDS:
            continue
        text = _literal(value)
        if text is None:
            return None                       # a name the AST cannot read compares to nothing
        text = " ".join(text.replace("?", " ").split())
        if text:
            names[name] = text
    return Person(" · ".join(path), " · ".join(shape), numbered, node.lineno, tuple(sorted(names.items())), leaf,
                  record_line or node.lineno)


def people(source: str) -> list[Person]:
    """Every `person(…)` of a DSL source, in source order."""
    out: list[Person] = []

    def walk(node: ast.AST, path: list[str], shape: list[str], numbered: bool, leaf: str = "", at: int = 0) -> None:
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "person":
                found = _person(node, path, shape, numbered, leaf, at)
                if found is not None:
                    out.append(found)
                return
            if name == "page" and node.args:
                leaf = _literal(node.args[0]) or leaf
            for kw in node.keywords:
                if kw.arg == "page":
                    leaf = _literal(kw.value) or leaf
            if name and not _GROUP.match(name):
                at = at or node.lineno
                ident = _ident(node)
                path = [*path, " ".join((name, *ident))]
                shape = [*shape, name]
                numbered = numbered or bool(ident)
            for i, arg in enumerate(node.args):
                inner = arg.value if isinstance(arg, ast.Starred) else arg
                slot = [] if _names_itself(inner) or not name or _GROUP.match(name) else [f"@{i}"]
                walk(inner, path + slot, shape + slot, numbered, leaf, at)
            for kw in node.keywords:
                slot = [kw.arg] if kw.arg else []
                walk(kw.value, path + slot, shape + slot, numbered, leaf, at)
            return
        if isinstance(node, (ast.List, ast.Tuple)):
            for j, element in enumerate(node.elts):
                slot = [] if _names_itself(element) else [str(j + 1)]
                walk(element, path + slot, shape + ["[]"] * len(slot), numbered, leaf, at)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, path, shape, numbered, leaf, at)

    walk(ast.parse(source), [], [], False)
    return out


class OldPair(NamedTuple):
    """Two adjacent words of an old name the new name no longer writes."""

    first: str
    second: str
    kind: str                                 # READING, or SPELLING when only the spelling changed
    given: bool                               # the first word is the given name

    def folded(self, mode: str) -> tuple[str, str]:
        return _fold(mode, self.given)(self.first), _fold(mode)(self.second)


@dataclass(frozen=True)
class Change:
    """A person whose name a revision reads otherwise."""

    file: str                                 # village-relative, as the new side has it
    line: int                                 # of the new `person(…)`
    where: str                                # «birth 5 MALE · mother»
    old: str
    new: str
    pairs: tuple[OldPair, ...]                # what to look for in the notes; none for a one-word name
    sequences: tuple[tuple[str, ...], ...]    # the old name's words, as a note may write them in full
    leaf: str = ""                            # the record's лист, as a note may cite it
    record_line: int = 0                      # where the record call begins, in the new file

    @property
    def kind(self) -> str:
        return READING if any(p.kind == READING for p in self.pairs) else SPELLING

    @property
    def record(self) -> str:
        return f"{self.file} · {self.where.split(' · ')[0]}"

    @property
    def year(self) -> str | None:
        return self.file[:4] if self.file[:4].isdigit() else None

    @property
    def number(self) -> tuple[str, str] | None:
        """The record's number and sex as a note cites it: («5», «м») for «№ м5»."""
        ident = self.where.split(" · ")[0].split()[1:]
        if not ident or not ident[0].isdigit():
            return None
        return ident[0], next((_SEX[w] for w in ident[1:] if w in _SEX), "")


def _change(file: str, old: Person, new: Person) -> Change | None:
    if not Counter(old.spelled()) - Counter(new.spelled()):
        return None                           # unchanged, or a word added: nothing old to look for
    new_spelled, new_ident = new.pairs(SPELLING), new.pairs(IDENTITY)
    pairs: list[OldPair] = []
    for fields in _SEQUENCES:
        words = old.words(fields)
        for (a, given), (b, _) in pairwise(words):
            pair = OldPair(a, b, READING, given)
            if pair.folded(SPELLING) in new_spelled:
                continue
            if pair.folded(IDENTITY) in new_ident:
                pair = pair._replace(kind=SPELLING)
            if pair not in pairs:
                pairs.append(pair)
    sequences = tuple(tuple(w for w, _ in old.words(f)) for f in _SEQUENCES if len(old.words(f)) > 1)
    where = " · ".join(part for part in new.key.split(" · ") if not part.startswith("@"))
    return Change(file, new.line, where, old.written, new.written, tuple(pairs), sequences, new.leaf,
                  new.record_line)


def _pair_up(old: Sequence[Person], new: Sequence[Person], by: Callable[[Person], str]) -> list[tuple[int, int]]:
    waiting: dict[str, list[int]] = defaultdict(list)
    for j, p in enumerate(new):
        waiting[by(p)].append(j)
    out: list[tuple[int, int]] = []
    for i, p in enumerate(old):
        if waiting[by(p)]:
            out.append((i, waiting[by(p)].pop(0)))
    return out


def _by_key(p: Person) -> str:
    return p.key


def _by_shape(p: Person) -> str:
    return p.shape


def changes(old_source: str, new_source: str, file: str) -> list[Change]:
    """The persons whose names `new_source` reads otherwise than `old_source`.

    Aligned in three passes: the persons that did not change at all anchor the
    rest (difflib over key and spelling); between two anchors a person pairs
    with the one of its own key, else of its own shape — a renumbered record;
    what is left pairs across the file by a key carrying a record number — a
    record moved elsewhere and changed."""
    old, new = people(old_source), people(new_source)
    marks = SequenceMatcher(None, [(p.key, p.spelled()) for p in old],
                            [(p.key, p.spelled()) for p in new], autojunk=False)
    pairs: list[tuple[int, int]] = []
    loose_old: list[int] = []
    loose_new: list[int] = []
    for tag, i1, i2, j1, j2 in marks.get_opcodes():
        if tag == "equal":
            continue
        olds, news = list(range(i1, i2)), list(range(j1, j2))
        for by in (_by_key, _by_shape):
            matched = _pair_up([old[i] for i in olds], [new[j] for j in news], by)
            pairs += [(olds[a], news[b]) for a, b in matched]
            taken_old, taken_new = {olds[a] for a, _ in matched}, {news[b] for _, b in matched}
            olds = [i for i in olds if i not in taken_old]
            news = [j for j in news if j not in taken_new]
        loose_old += olds
        loose_new += news
    numbered_old = [i for i in loose_old if old[i].numbered]
    numbered_new = [j for j in loose_new if new[j].numbered]
    matched = _pair_up([old[i] for i in numbered_old], [new[j] for j in numbered_new], _by_key)
    pairs += [(numbered_old[a], numbered_new[b]) for a, b in matched]
    found = (_change(file, old[i], new[j]) for i, j in sorted(pairs, key=lambda ij: ij[1]))
    return [c for c in found if c is not None]


# --------------------------------------------------------------- the notes ---

@dataclass(frozen=True)
class Note:
    """A stretch of prose: a block of `#` comment lines, a prose kwarg, a Markdown file."""

    path: str                                 # repo-relative
    text: str
    lines: tuple[tuple[int, int], ...]        # (offset in text, line in the file)
    headings: tuple[tuple[int, str], ...] = ()   # Markdown: (offset, the year its heading names)

    def line_at(self, offset: int) -> int:
        line = self.lines[0][1]
        for start, number in self.lines:
            if start > offset:
                break
            line = number
        return line


def _block(path: str, rows: list[tuple[int, str]]) -> Note:
    text, lines, offset = [], [], 0
    for number, piece in rows:
        lines.append((offset, number))
        text.append(piece)
        offset += len(piece) + 1
    return Note(path, "\n".join(text), tuple(lines))


def comments(source: str) -> list[tuple[int, str]]:
    """(line, text) of every `#` comment, the «#» taken off."""
    try:
        return [(tok.start[0], tok.string.lstrip("#").strip())
                for tok in tokenize.generate_tokens(io.StringIO(source).readline)
                if tok.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return [(n, line.strip().lstrip("#").strip())
                for n, line in enumerate(source.splitlines(), 1) if line.lstrip().startswith("#")]


def python_notes(source: str, path: str) -> list[Note]:
    """The comment blocks (consecutive comment lines) and prose kwargs of a Python source."""
    out: list[Note] = []
    rows: list[tuple[int, str]] = []
    for number, text in comments(source):
        if rows and number != rows[-1][0] + 1:
            out.append(_block(path, rows))
            rows = []
        rows.append((number, text))
    if rows:
        out.append(_block(path, rows))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg and _PROSE.match(node.arg) \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out.append(Note(path, node.value.value, ((0, node.value.lineno),)))
    return out


def markdown_note(text: str, path: str) -> Note:
    note = _block(path, list(enumerate(text.split("\n"), 1)))
    headings: list[tuple[int, str]] = []
    for offset, _ in note.lines:
        line = text[offset:text.find("\n", offset) if "\n" in text[offset:] else len(text)]
        if line.startswith("#"):
            year = _YEAR.search(line)
            headings.append((offset, year.group(1) if year else ""))
    return Note(path, note.text, note.lines, tuple(headings))


@dataclass(frozen=True)
class Stale:
    """An old pair of words no new name writes, and the changes that dropped it."""

    pair: OldPair                             # as the old DSL wrote it (the first change's)
    first: str                                # the stems a note's words must fit
    second: str
    changes: tuple[Change, ...]
    corrected: tuple[str, ...]                # the new names of the records the changes are in
    was: tuple[str, ...] = ()                 # the old names of the same people

    @property
    def kind(self) -> str:
        return self.pair.kind

    @property
    def key(self) -> tuple[str, str, str]:
        return self.first, self.second, self.kind

    @property
    def text(self) -> str:
        return f"{self.pair.first} {self.pair.second}"

    @property
    def written_as(self) -> tuple[str, tuple[str, str]]:
        """How a person of the DSL still carrying this pair is recognised: a
        reading by who it names (a namesake), a spelling by its letters (another
        record still spelled so)."""
        mode = IDENTITY if self.kind == READING else SPELLING
        return mode, self.pair.folded(mode)


def stale_pairs(found: Sequence[Change]) -> list[Stale]:
    """The old pairs of all changes, one per pair however many changes dropped it."""
    grouped: dict[tuple[str, str, str], list[tuple[OldPair, Change]]] = defaultdict(list)
    for change in found:
        for pair in change.pairs:
            first, second = pair.folded(pair.kind)
            grouped[(stem(first), stem(second), pair.kind)].append((pair, change))
    by_record: dict[str, list[Change]] = defaultdict(list)
    for change in found:
        by_record[change.record].append(change)
    out: list[Stale] = []
    for (first, second, _), items in grouped.items():
        mine = tuple(dict.fromkeys(c for _, c in items))
        theirs = [r for c in mine for r in by_record[c.record]]
        corrected = tuple(dict.fromkeys(r.new for r in theirs))
        was = tuple(dict.fromkeys(r.old for r in theirs))
        out.append(Stale(items[0][0], first, second, mine, corrected, was))
    return out


@dataclass(frozen=True)
class Hit:
    stale: Stale
    path: str
    line: int
    excerpt: str
    settled: bool                             # the note writes the new form beside it, or the old as overturned
    tie: str                                  # RECORD | YEAR | "": how the note is tied to a changed record
    whole: bool                               # the note writes the whole old name, not only the pair of it
    block_end: int                            # the last line of the note's comment block (Markdown: the file's)


@dataclass(frozen=True)
class _Word:
    start: int
    end: int
    spelled: str
    read: str

    def key(self, kind: str) -> str:
        return self.read if kind == READING else self.spelled


def _words(text: str) -> list[_Word]:
    return [_Word(m.start(), m.end(), spelling_key(m.group()), reading_key(m.group()))
            for m in _WORD.finditer(text)]


def _fold(mode: str, given: bool = False) -> Callable[[str], str]:
    if mode == IDENTITY:
        return given_key if given else reading_key
    return reading_key if mode == READING else spelling_key


def _excerpt(text: str, start: int, end: int, width: int = 70) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    body = " ".join(text[left:right].split())
    return ("…" if left else "") + body + ("…" if right < len(text) else "")


def _pair_at(text: str, words: Sequence[_Word], i: int, first: str, second: str, kind: str) -> bool:
    a, b = words[i], words[i + 1]
    gap = text[a.end:b.start]
    return _fits(a.key(kind), first) and _fits(b.key(kind), second) \
        and _GAP.fullmatch(gap) is not None and gap.count("\n") < 2


def _new_pairs(stale: Stale) -> set[tuple[str, str]]:
    """The pairs the corrected names write and the old ones did not: a pair the proofread kept
    («Фома Фомичъ» of «Фома Фомичъ Опискинъ» → «… Ростаневъ») stands in the old form itself, and is
    no new reading beside it."""
    fold = _fold(stale.kind)

    def pairs(names: Iterable[str]) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for name in names:
            words = _WORD.findall(name)
            out.update((stem(fold(a)), stem(fold(b))) for a, b in pairwise(words))
        return out

    return pairs(stale.corrected) - pairs(stale.was)


def _settled(note: Note, words: Sequence[_Word], at: int, stale: Stale) -> bool:
    start, end = words[at].start, words[at + 1].end
    if _OVERTURNED_BEFORE.search(note.text[max(0, start - 25):start]) \
            or _OVERTURNED_AFTER.match(note.text[end:end + 6]) \
            or _RETRACTED.search(note.text[max(0, start - _RETRACTED_NEAR):end + _RETRACTED_NEAR]):
        return True
    near = [w for w in words if start - _NEAR <= w.start <= end + _NEAR]
    return any(_pair_at(note.text, near, i, a, b, stale.kind)
               for a, b in _new_pairs(stale) for i in range(len(near) - 1))


RECORD = "record"
YEAR = "year"


def _years_of(note: Note, start: int, end: int) -> set[str]:
    """The years the note speaks of at the old form: those cited before it in its
    sentence («МК 1879 и 1882 гг. дают …»), else after it in its sentence, else
    its Markdown section's, else the last before it at all (a body under its
    headline), else the year of the DSL file — within reach. Empty: unknown."""
    reach = max(0, start - _YEAR_BEFORE)
    sentence = max([reach, *(m.end() for m in _SENTENCE_END.finditer(note.text, reach, start))])
    stop = _SENTENCE_END.search(note.text, end, end + _YEAR_AFTER)
    in_file = _FILE_YEAR.search(note.path)
    for found in (_YEAR.findall(note.text, sentence, start),
                  _YEAR.findall(note.text, end, stop.start() if stop else end + _YEAR_AFTER),
                  [y for y in [_section_year(note, start)] if y],
                  _YEAR.findall(note.text, reach, start)[-1:],
                  [in_file.group(1)] if in_file else []):
        if found:
            return set(found)
    return set()


def _section_year(note: Note, offset: int) -> str | None:
    """The year of the Markdown section at `offset`: the first cell of its table
    row («| ✅ МК **1872** …»), else its heading («##### Что дал 1872 год»)."""
    line_start = note.text.rfind("\n", 0, offset) + 1
    if note.text.startswith("|", line_start):
        cell = note.text[line_start + 1:note.text.find("|", line_start + 1)]
        if year := _YEAR.search(cell):
            return year.group(1)
    years = [year for at, year in note.headings if at <= offset]
    return years[-1] if years and years[-1] else None


def _cites_leaf(text: str, leaf: str) -> bool:
    return any(re.search(rf"(?<![\dА-Яа-я]){re.escape(part)}(?![\dА-Яа-я])", text)  # i18n: content — the notes' and the DSL's words it searches for, internal kinds
               for part in leaf.split("-") if part)


def _tie(note: Note, start: int, end: int, stale: Stale) -> str:
    """How the note is tied to a changed record: RECORD — its number cited beside
    the old form in its year, or the comment block right above the record; YEAR
    — the old form spoken of in the record's year; "" — neither, or another
    record cited right by it."""
    window = note.text[max(0, start - _CITED_NEAR):end + _CITED_NEAR]
    cited = [(m.group(1), m.group(2)) for m in _CITED.finditer(window)]
    years = _years_of(note, start, end)
    best = ""
    for change in stale.changes:
        if note.path.endswith("/" + change.file) and change.record_line - _ABOVE <= note.lines[-1][1] < change.record_line:
            return RECORD
        if years and change.year and change.year not in years:
            continue
        own = change.number
        if change.leaf and _cites_leaf(window, change.leaf):
            return RECORD
        if cited and own:
            if any(n == own[0] and sex in ("", own[1]) for sex, n in cited):
                return RECORD
            continue
        if years:
            best = YEAR
    return best


def _whole(text: str, words: Sequence[_Word], i: int, stale: Stale) -> bool:
    """Whether the note writes the whole old name around the pair at `i` — true
    of a pair that was the whole name. «Иванъ Петровъ» of «Иванъ Петровъ Сидоровъ»
    is a namesake as often as not; the three words together are the reading."""
    for change in stale.changes:
        for sequence in change.sequences:
            old = [stem(_fold(stale.kind)(w)) for w in sequence]
            for at in range(len(old) - 1):
                if (old[at], old[at + 1]) != (stale.first, stale.second):
                    continue
                begin = i - at
                if len(old) == 2 or (begin >= 0 and begin + len(old) <= len(words) and all(
                        _pair_at(text, words, begin + k, old[k], old[k + 1], stale.kind) for k in range(len(old) - 1))):
                    return True
    return False


def find_hits(stales: Sequence[Stale], notes: Iterable[Note]) -> list[Hit]:
    """Every place a note writes an old pair."""
    wanted: dict[str, list[Stale]] = defaultdict(list)
    for stale in stales:
        wanted[stale.first[:_MIN_STEM]].append(stale)
    out: list[Hit] = []
    for note in notes:
        words = _words(note.text)
        for i in range(len(words) - 1):
            for prefix in {words[i].spelled[:_MIN_STEM], words[i].read[:_MIN_STEM]}:
                for stale in wanted.get(prefix, ()):
                    if _pair_at(note.text, words, i, stale.first, stale.second, stale.kind):
                        start, end = words[i].start, words[i + 1].end
                        out.append(Hit(stale, note.path, note.line_at(start), _excerpt(note.text, start, end),
                                       _settled(note, words, i, stale), _tie(note, start, end, stale),
                                       _whole(note.text, words, i, stale), note.lines[-1][1]))
    return out


def still_written(stales: Sequence[Stale], sources: Mapping[str, str]) -> dict[tuple[str, str, str], list[tuple[str, int]]]:
    """Where the DSL still writes each old pair — (file, line of the record call),
    one per person: someone else of that name, or another record still spelled
    so (`Stale.written_as`)."""
    wanted: dict[tuple[str, tuple[str, str]], list[tuple[str, str, str]]] = defaultdict(list)
    for stale in stales:
        wanted[stale.written_as].append(stale.key)
    found: dict[tuple[str, str, str], list[tuple[str, int]]] = defaultdict(list)
    for path, source in sources.items():
        try:
            persons = people(source)
        except SyntaxError:
            continue
        for p in persons:
            for mode in (IDENTITY, SPELLING):
                for pair in p.pairs(mode):
                    for key in wanted.get((mode, pair), ()):
                        found[key].append((path, p.record_line))
    return dict(found)


# --------------------------------------------------------------- headers -----

@dataclass(frozen=True)
class StaleHeader:
    path: str
    line: int
    text: str


def held(tree: ast.Module) -> bool:
    """Whether any call of the module still writes `reviewed=False`."""
    return any(isinstance(node, ast.keyword) and node.arg == "reviewed"
               and isinstance(node.value, ast.Constant) and node.value.value is False
               for node in ast.walk(tree))


def stale_header(source: str, path: str) -> StaleHeader | None:
    """The header's `reviewed=False` note of a file no record of which is held any more.

    The header is the comments above the first statement that is not an import
    or the docstring — where every DSL file states how it was read."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    body = [s for s in tree.body if not isinstance(s, (ast.Import, ast.ImportFrom))
            and not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    end = body[0].lineno if body else len(source.splitlines()) + 1
    for number, text in comments(source):
        if number < end and _HELD_NOTE.search(text):
            return None if held(tree) else StaleHeader(path, number, text)
    return None


# --------------------------------------------------------------- the report --

@dataclass(frozen=True)
class Report:
    village: str
    revs: str
    notes_at: str
    found: list[Change]
    stales: list[Stale]
    hits: list[Hit]
    written: dict[tuple[str, str, str], list[tuple[str, int]]]
    headers: list[StaleHeader]
    show_settled: bool = False

    def still(self, stale: Stale) -> int:
        return len(self.written.get(stale.key, ()))

    def counts(self, hit: Hit) -> bool:
        """Only where the note writes the whole old name (`_whole`). A pair the
        DSL no longer writes is then the old reading wherever a note has it. One
        it still writes names someone else too, so the note must be tied to the
        changed record — its number cited, or its file, or its year cited before
        the name; a DSL file whose own records write the pair is quoting them
        unless it cites the changed record; and the comment block right above a
        record that writes it is that record's."""
        if not hit.whole:
            return False
        where = self.written.get(hit.stale.key)
        if not where:
            return True
        if any(path == hit.path and line - _ABOVE <= hit.block_end < line for path, line in where):
            return False
        if any(path == hit.path for path, _ in where):
            return hit.tie == RECORD
        return bool(hit.tie)

    @property
    def shown(self) -> list[Hit]:
        return [h for h in self.hits if self.counts(h) and (self.show_settled or not h.settled)]

    @property
    def clean(self) -> bool:
        return not self.shown and not self.headers


def _change_text(c: Change) -> str:
    return f"{c.file}:{c.line}  {c.where}: «{c.old}» → «{c.new}»"


def _kind(kind: str) -> str:
    """A changed pair's kind (`READING`, `SPELLING`) as the report names it."""
    if kind == READING:
        return str(t("notes.stale_notes.kind.reading"))
    if kind == SPELLING:
        return str(t("notes.stale_notes.kind.spelling"))
    return kind


def format_report(report: Report) -> str:
    shown = report.shown
    settled = sum(1 for h in report.hits if h.settled and report.counts(h) and not report.show_settled)
    by_stale: dict[Stale, list[Hit]] = defaultdict(list)
    for hit in shown:
        by_stale[hit.stale].append(hit)
    lines = [str(t("notes.stale_notes.head", village=report.village, revs=report.revs, notes_at=report.notes_at,
                   names=len(report.found), pairs=len(report.stales), places=len(shown)))
             + (str(t("notes.stale_notes.settled", settled=settled)) if settled else "")
             + str(t("notes.stale_notes.headers", headers=len(report.headers)))]
    for stale in report.stales:
        hits = by_stale.get(stale)
        if not hits:
            continue
        lines.append(f"«{stale.text}»  [{_kind(stale.kind)}]")
        lines += [f"  {_change_text(c)}" for c in stale.changes]
        if report.still(stale):
            lines.append(str(t("notes.stale_notes.still", still=report.still(stale))))
        for hit in sorted(hits, key=lambda h: (h.path, h.line)):
            mark = str(t("notes.stale_notes.settled_mark")) if hit.settled else ""
            lines.append(f"    {hit.path}:{hit.line}{mark}")
            lines.append(f"        {hit.excerpt}")
        lines.append("")
    unsearched = [c for c in report.found if not c.pairs]
    if unsearched:
        lines.append(str(t("notes.stale_notes.unsearched")))
        lines += [f"  {_change_text(c)}" for c in unsearched]
        lines.append("")
    if report.headers:
        lines.append(str(t("notes.stale_notes.stale_headers")))
        lines += [f"  {h.path}:{h.line}  {h.text}" for h in report.headers]
        lines.append("")
    lines.append(str(t("notes.stale_notes.signal")))
    return "\n".join(lines)


def report_to_json(report: Report) -> str:
    def change(c: Change) -> dict[str, object]:
        return {"file": c.file, "line": c.line, "where": c.where, "old": c.old, "new": c.new, "kind": c.kind}
    shown = report.shown
    return json.dumps({
        "village": report.village, "revs": report.revs, "notes_at": report.notes_at,
        "changes": [change(c) for c in report.found],
        "pairs": [{"pair": s.text, "kind": s.kind, "still_written": report.still(s),
                   "changes": [change(c) for c in s.changes],
                   "notes": [{"path": h.path, "line": h.line, "settled": h.settled, "excerpt": h.excerpt}
                             for h in shown if h.stale is s]}
                  for s in report.stales],
        "headers": [{"path": h.path, "line": h.line, "text": h.text} for h in report.headers],
    }, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------- I/O -----

_KINDS = r"births|marriages|deaths|census|confessions|name_lists|external_sources|divorces"
_SLUG = re.compile(rf"^(?P<slug>[a-z_]+?)_(?:{_KINDS})_\d{{4}}\.py$")


class Tree:
    """The repository as one revision has it, or the working tree (`rev=None`)."""

    def __init__(self, root: Path, rev: str | None) -> None:
        self.root, self.rev = root, rev
        self._cache: dict[str, str | None] = {}

    def files(self, pattern: str) -> list[str]:
        """Repo-relative paths matching a glob pattern («Маниловка/[0-9][0-9][0-9][0-9]/*.py»)."""
        if self.rev is None:
            return sorted(p.relative_to(self.root).as_posix() for p in self.root.glob(pattern) if p.is_file())
        literal = PurePosixPath(*[part for part in pattern.split("/")[:-1] if not any(c in part for c in "*?[")])
        proc = subprocess.run(["git", "-C", str(self.root), "ls-tree", "-r", "-z", "--name-only", self.rev, "--",
                               literal.as_posix()], capture_output=True, check=False)
        found = proc.stdout.decode("utf-8").split("\0") if proc.returncode == 0 else []
        return sorted(p for p in found if p and PurePosixPath(p).full_match(pattern))

    def read(self, path: str) -> str | None:
        if self.rev is None:
            file = self.root / path
            return file.read_text(encoding="utf-8") if file.is_file() else None
        if path not in self._cache:
            self.fetch([path])
        return self._cache[path]

    def fetch(self, paths: Iterable[str]) -> None:
        """Read many files of a revision in one `git cat-file --batch`."""
        wanted = [p for p in dict.fromkeys(paths) if p not in self._cache]
        if self.rev is None or not wanted:
            return
        proc = subprocess.run(["git", "-C", str(self.root), "cat-file", "--batch"], check=False, capture_output=True,
                              input="".join(f"{self.rev}:{p}\n" for p in wanted).encode("utf-8"))
        out, at = proc.stdout, 0
        for path in wanted:
            end = out.index(b"\n", at)
            header = out[at:end].split()
            at = end + 1
            if len(header) != 3 or header[1] != b"blob":
                self._cache[path] = None
                continue
            size = int(header[2])
            self._cache[path] = out[at:at + size].decode("utf-8")
            at += size + 1

    def __str__(self) -> str:
        return self.rev or str(t("notes.stale_notes.working_tree"))


_DSL = "[0-9][0-9][0-9][0-9]/*.py"


def dsl_files(tree: Tree, village: str) -> list[str]:
    return tree.files(f"{village}/{_DSL}")


def changed_dsl(root: Path, village: str, old_rev: str, new_rev: str | None) -> list[str]:
    """The village's DSL files that differ between the two sides (`git diff`)."""
    revs = [old_rev] if new_rev is None else [old_rev, new_rev]
    proc = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "-z", *revs, "--", village],
                          capture_output=True, check=True)
    return sorted(p for p in proc.stdout.decode("utf-8").split("\0")
                  if p and PurePosixPath(p).full_match(f"{village}/{_DSL}"))


def note_files(tree: Tree, village: str, dsl: Sequence[str], globs: Sequence[str]) -> list[str]:
    """The files whose prose is searched: the village's DSL, then what the
    workspace's `[notes] globs` name, in their order — `{village}` the village's
    directory, `{slug}` the slug its DSL files carry (a glob naming the slug is
    skipped when they carry none)."""
    out = [*dsl]
    slugs = Counter(m.group("slug") for p in dsl if (m := _SLUG.match(PurePosixPath(p).name)))
    slug = slugs.most_common(1)[0][0].replace("_", "-") if slugs else None
    for glob in globs:
        if "{slug}" in glob and slug is None:
            continue
        out += tree.files(glob.replace("{village}", village).replace("{slug}", slug or ""))
    return out


def notes_of(tree: Tree, paths: Sequence[str]) -> Iterator[Note]:
    tree.fetch(paths)
    for path in paths:
        text = tree.read(path)
        if text is None:
            continue
        if path.endswith(".py"):
            yield from python_notes(text, path)
        else:
            yield markdown_note(text, path)


def parse_revs(spec: str) -> tuple[str, str | None]:
    """«A..B» → (A, B); «A..» or «A» → (A, None), the working tree."""
    old, _, new = spec.partition("..")
    return old, (new or None)


def build_report(root: Path, village: str, old_rev: str, new_rev: str | None, notes_rev: str | None,
                 show_settled: bool = False, globs: Sequence[str] | None = None) -> Report:
    """`globs`: the notes to search beyond the DSL — by default, as the
    workspace of the repository at `root` names them."""
    globs = workspace.load(root).notes if globs is None else globs
    old_tree, new_tree, notes_tree = Tree(root, old_rev), Tree(root, new_rev), Tree(root, notes_rev)
    found: list[Change] = []
    changed = changed_dsl(root, village, old_rev, new_rev)
    old_tree.fetch(changed)
    new_tree.fetch(changed)
    for path in changed:
        before, after = old_tree.read(path), new_tree.read(path)
        if before is None or after is None or before == after:
            continue
        try:
            found += changes(before, after, path.removeprefix(village + "/"))
        except SyntaxError as exc:
            print(f"WARNING: {path}: {exc}", file=sys.stderr)
    notes_dsl = dsl_files(notes_tree, village)
    notes_tree.fetch(notes_dsl)
    sources = {p: s for p in notes_dsl if (s := notes_tree.read(p)) is not None}
    notes = notes_of(notes_tree, note_files(notes_tree, village, notes_dsl, globs))
    return make_report(village, f"{old_rev}..{new_rev or ''}", str(notes_tree), found, notes, sources, show_settled)


def make_report(village: str, revs: str, notes_at: str, found: list[Change], notes: Iterable[Note],
                sources: Mapping[str, str], show_settled: bool = False) -> Report:
    """The report from the changes, the notes and the DSL sources (path → text)
    the notes side holds."""
    stales = stale_pairs(found)
    hits = find_hits(stales, notes)
    headers = [h for p, s in sources.items() if (h := stale_header(s, p))]
    return Report(village, revs, notes_at, found, stales, hits, still_written(stales, sources), headers, show_settled)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Notes (comments, Markdown) that still write a reading a proofread "
                                             "changed, and headers still noting reviewed=False.")
    ap.add_argument("--village", required=True, help="village dir")
    ap.add_argument("--rev", default="HEAD~1..",
                    help="A..B — the readings that changed from A to B; B empty = the working tree (default HEAD~1..)")
    ap.add_argument("--notes-at", default=None,
                    help="read the notes at this revision (default: the working tree, where they are fixed)")
    ap.add_argument("--all", action="store_true", help="also the notes that already write the new form beside the old")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if top.returncode != 0:
        print(t("notes.stale_notes.not_git"), file=sys.stderr)
        return 2
    root = Path(top.stdout.strip())
    # The notes are the ones this repository's workspace names, whatever the
    # process's own workspace is: the git paths below are the toplevel's.
    if not (root / workspace.CONFIG).is_file():
        print(t("notes.stale_notes.no_config", root=root, config=workspace.CONFIG), file=sys.stderr)
        return 2
    village = Path(args.village).resolve().relative_to(root.resolve()).as_posix()
    old_rev, new_rev = parse_revs(args.rev)
    report = build_report(root, village, old_rev, new_rev, args.notes_at, args.all)
    print(report_to_json(report) if args.json else format_report(report))
    return 0 if report.clean else 1


if __name__ == "__main__":
    sys.exit(main())
