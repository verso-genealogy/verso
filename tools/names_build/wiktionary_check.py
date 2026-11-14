"""Compare the forms of the names base with Russian Wiktionary — a check, never an input of the base.

    python tools/names_build/wiktionary_check.py --dump <kaikki.org Русский JSONL, plain or .gz> [--base DIR]

Wiktionary is CC BY-SA: nothing of it is written into the base, and its dump is never committed — download
the extract of the Russian language from kaikki.org (the Russian edition, «Русский») into a temporary
directory. Not run in CI.

For every name of the base the dump holds as a given name of the same sex (a category «Мужские имена…/ru» or
«Женские имена…/ru»), the base's genitive and — for a man's name — its two modern patronymics (the forms
entry's cell, else the rule's) are compared with the dump's: the singular genitive of its declension table and
the patronymics of its kinship block, stress marks taken off. A form is the same when it is among the dump's.
What differs is printed one per line (sex, name, column, the base's form, the dump's forms, a class), then
the counts. Each difference is either a defect of the base — fixed in `exceptions.tsv` — or the base's own
answer, with its reason in the report.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from verso.ru.gender import Gender
from verso.ru.naming import forms as rules
from verso.ru.naming.layer_files import BASE, FilesLayer
from verso.ru.naming.lexicon import Layer

_STRESS = str.maketrans("", "", "\u0301\u0300")
# The dump writes some stressed vowels as Latin letters with an accent (Лáуры): once the accent is off, the
# Latin letter is read as the Cyrillic one it stands for.
_LATIN = str.maketrans("aeocyxpAEOCYXP", "аеосухрАЕОСУХР")
_SEX = {"Мужские имена": Gender.MALE, "Женские имена": Gender.FEMALE}
_PATRONYMIC = {"отчество мужчины": "patronymic_m", "отчество женщины": "patronymic_f"}


def _plain(form: str) -> str:
    """The form without its stress marks — combining, or a Latin letter's own accent (й and ё are kept)."""
    bare = unicodedata.normalize("NFD", form).translate(_STRESS)
    return unicodedata.normalize("NFC", bare).translate(_LATIN).strip()


def _lines(path: Path) -> Iterator[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        yield from f


def _sex(entry: dict[str, Any]) -> Gender | None:
    for category in entry.get("categories", ()):
        name = category["name"] if isinstance(category, dict) else category
        for prefix, sex in _SEX.items():
            if name.startswith(prefix) and name.endswith("/ru"):
                return sex
    return None


def read_dump(lines: Iterable[str]) -> dict[tuple[Gender, str], dict[str, set[str]]]:
    """{(sex, name): {column: forms}} of the dump's Russian given names."""
    out: dict[tuple[Gender, str], dict[str, set[str]]] = {}
    for line in lines:
        if '"lang_code": "ru"' not in line and '"lang_code":"ru"' not in line:
            continue
        entry = json.loads(line)
        sex = _sex(entry)
        if entry.get("lang_code") != "ru" or sex is None:
            continue
        found = out.setdefault((sex, entry["word"]), {})
        for form in entry.get("forms", ()):
            tags = set(form.get("tags", ()))
            if {"singular", "genitive"} <= tags:
                found.setdefault("genitive", set()).add(_plain(form["form"]))
        for related in entry.get("related", ()):
            for tag in related.get("raw_tags", ()):
                if tag in _PATRONYMIC:
                    found.setdefault(_PATRONYMIC[tag], set()).add(_plain(related["word"]))
    return out


def ours(layer: Layer, sex: Gender, name: str) -> dict[str, str]:
    """The base's forms of a name: its forms entry's cell, else the rule's."""
    fe = layer.forms.get((sex, name))
    cells = {"genitive": (fe.genitive if fe else None) or rules.genitive(name, sex)}
    if sex is Gender.MALE:
        cells["patronymic_m"] = (fe.patronymic_m if fe else None) or rules.modern_patronymic(name, Gender.MALE)
        cells["patronymic_f"] = (fe.patronymic_f if fe else None) or rules.modern_patronymic(name, Gender.FEMALE)
    return cells


def classify(column: str, mine: str, theirs: set[str]) -> str:
    """A first guess at what a difference is — the report reads each one."""
    if any(t.replace("ё", "е") == mine.replace("ё", "е") for t in theirs):
        return "ё/е"
    if column.startswith("patronymic"):
        if any(t.replace("ьев", "иев") == mine or mine.replace("ьев", "иев") == t for t in theirs):
            return "-иевич/-ьевич"
        if any(t.endswith("инична") for t in theirs) or mine.endswith("инична"):
            return "-инична"
    return "other"


def compare(layer: Layer, dump: dict[tuple[Gender, str], dict[str, set[str]]]
            ) -> tuple[Counter[str], list[tuple[str, ...]]]:
    counts: Counter[str] = Counter()
    differences: list[tuple[str, ...]] = []
    for (sex, name), entry in sorted(layer.names.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        if sex is None or (sex, name) not in dump:
            continue
        counts["names in the dump"] += 1
        theirs_all = dump[(sex, name)]
        for column, mine in ours(layer, sex, name).items():
            theirs = theirs_all.get(column)
            if not theirs:
                continue
            counts[f"{column}: compared"] += 1
            if mine in theirs:
                counts[f"{column}: same"] += 1
                continue
            kind = classify(column, mine, theirs)
            counts[f"{column}: differs ({kind})"] += 1
            differences.append(("M" if sex is Gender.MALE else "F", name, column, mine, "|".join(sorted(theirs)), kind,
                                "base" if entry.bases == () else "variant", "editor" if (sex, name) in layer.forms
                                else "rule"))
    return counts, differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=None, help="a base directory (default: the package's)")
    args = parser.parse_args(argv)
    layer = FilesLayer(args.base or BASE, name="base", writable=False).load()
    counts, differences = compare(layer, read_dump(_lines(args.dump)))
    for row in differences:
        print("\t".join(row))
    for name, count in sorted(counts.items()):
        print(f"{count:6}  {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
