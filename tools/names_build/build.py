"""Build the names base — `verso/ru/naming/data/base/` — from its free sources, a source on every row.

    python tools/names_build/build.py [--out DIR]

Deterministic: the same inputs give the same bytes. The inputs, in the order they are read:

  1. the святцы (`church_calendar/data/svyatcy_1906.tsv`, the 1906 Требник's alphabet): every name a
     canonical one of its sex, `trebnik1906:<line>`;
  2. the Wikidata snapshot (`wikidata-*.json`, CC0): every given name the святцы lack, `wikidata:Q…` — a
     variant of a святцы name where its «said to be the same as» (P460) links reach exactly one святцы name
     of its sex, else a canonical name of its own;
  3. the metric books' spellings (`corpus_spellings.tsv`): a variant or a spelling and its base, `mk`;
  4. the maintainer's exceptions (`exceptions.tsv`, `editor`): the forms the rules do not give, and the
     few links of the sources that are plainly wrong.

The variants and their bases make one graph a sex, the святцы names its anchors: a name's base is the
anchor nearest to it — by the books' own pairs first, then by every link — and never a variant, so a
chain of the sources (Праскова → Прасковья, Прасковья ~ Параскева) is collapsed to its anchor here. A pair
of two святцы names is no variant: the святцы keep both. A name no anchor reaches takes its books' base
when the base is a name of the base (a Wikidata one), and otherwise stays out — nothing is invented.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verso.ru.gender import Gender
from verso.ru.naming import forms as rules
from verso.ru.naming.layer_files import FILES, SEX, Row, row_of, write_table
from verso.ru.naming.lexicon import FormsEntry, Layer, Lexicon, NameEntry, PatronymicEntry

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RU = ROOT / "packages" / "verso-ru" / "src" / "verso" / "ru"
SVYATCY = RU / "church_calendar" / "data" / "svyatcy_1906.tsv"
WIKIDATA = HERE / "wikidata-2026-11-08.json"
CORPUS = HERE / "corpus_spellings.tsv"
EXCEPTIONS = HERE / "exceptions.tsv"
OUT = RU / "naming" / "data" / "base"

#: A given name: one word of the Russian alphabet, capitalised, or two joined by a hyphen.
_PART = r"[А-ЯЁ][а-яё]*"
NAME = re.compile(rf"{_PART}(?:-{_PART})?")
_ANY_CYRILLIC_WORD = re.compile(r"[Ѐ-ӿ]+(?:-[Ѐ-ӿ]+)?")
_CAPITALISED = re.compile(r"[Ѐ-Я][ѐ-ӿа-я]*(?:-[Ѐ-Я][ѐ-ӿа-я]*)?")

Key = tuple[str, str]  # (sex cell, name)


def is_name(label: str | None) -> bool:
    return bool(label) and NAME.fullmatch(label) is not None  # type: ignore[arg-type]


@dataclass
class Built:
    """What the build makes: the three tables (entry, note) by key, and its counts."""
    names: dict[Key, tuple[NameEntry, str]] = field(default_factory=dict)
    forms: dict[Key, FormsEntry] = field(default_factory=dict)
    patronymics: dict[Key, PatronymicEntry] = field(default_factory=dict)
    counts: Counter[str] = field(default_factory=Counter)
    #: The books' names left out, by reason: (sex, name, the books' base).
    left_out: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    #: The books' pairs turned round: (sex, the books' base, the святцы name it is now a variant of).
    turned: list[tuple[str, str, str]] = field(default_factory=list)

    def leave_out(self, reason: str, key: Key, base: str) -> None:
        self.counts[reason] += 1
        self.left_out.setdefault(reason, []).append((*key, base))

    def layer(self) -> Layer:
        sex = SEX
        return Layer("base", {(sex[k[0]], k[1]): e for k, (e, _) in self.names.items()},
                     {(sex[k[0]], k[1]): e for k, e in self.forms.items()},  # type: ignore[misc]
                     {(sex[k[0]], k[1]): e for k, e in self.patronymics.items()}, derives=True)


def _tsv(path: Path) -> Iterable[tuple[int, list[str]]]:
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        if line and not line.startswith("#"):
            yield number, line.split("\t")


# --- 1. the святцы --------------------------------------------------------------------------------

def svyatcy(path: Path, built: Built) -> set[Key]:
    anchors: set[Key] = set()
    for number, cells in _tsv(path):
        if cells[0] == "gender":
            continue
        key = (cells[0], cells[2])
        if not is_name(key[1]):
            built.counts["svyatcy: not a name"] += 1
            continue
        if key not in anchors:
            anchors.add(key)
            built.names[key] = (NameEntry(SEX[key[0]], key[1], source=f"trebnik1906:{number}"), "")
    return anchors


# --- 2. Wikidata ----------------------------------------------------------------------------------

def _qnum(qid: str) -> int:
    return int(qid[1:])


def _not_given_names(by_key: dict[Key, list[dict[str, Any]]], anchors: set[Key], dropped: dict[Key, str],
                     built: Built) -> None:
    """Take out of `by_key` the labels that are no given names: the maintainer's drops (`dropped`, with their
    reasons), a modern patronymic another name of the base gives (Иванович, Ильич), and a man's label that is
    the short patronymic — the surname — another man's name of the base gives (Костадинов). A woman's label
    that is a woman's short patronymic (Алина, Арина) stays: a woman's «-ина», «-ова» is far more often a
    name of her own; they are counted."""
    men = sorted({n for s, n in (*anchors, *by_key) if s == "M"})
    patronymic: dict[str, str] = {}
    surname: dict[str, str] = {}
    hers: dict[str, str] = {}
    for n in men:
        for child in (Gender.MALE, Gender.FEMALE):
            patronymic.setdefault(rules.modern_patronymic(n, child), n)
        surname.setdefault(rules.old_patronymic(n, Gender.MALE), n)
        hers.setdefault(rules.old_patronymic(n, Gender.FEMALE), n)
    for key in sorted(by_key):
        sex, label = key
        if key in anchors:
            continue
        if key in dropped:
            reason, why = "editor: not a given name (left out)", dropped[key]
        elif patronymic.get(label, label) != label:
            reason, why = "wikidata: a patronymic of a name of the base (left out)", patronymic[label]
        elif sex == "M" and surname.get(label, label) != label:
            reason, why = "wikidata: a man's surname form of a name of the base (left out)", surname[label]
        else:
            if sex == "F" and hers.get(label, label) != label:
                built.leave_out("wikidata: a woman's name that is also a woman's short patronymic (kept)", key,
                                hers[label])
            continue
        del by_key[key]
        built.leave_out(reason, key, why)


def _other_sex(by_key: dict[Key, list[dict[str, Any]]], attested: set[Key], built: Built) -> None:
    """Take out of `by_key` a label of one sex where the святцы or the books hold that name in the other sex
    alone: they decide a name's sex as they decide its direction (Борис is a man's name, Мария a woman's,
    whatever item of the other sex Wikidata keeps)."""
    other = {"M": "F", "F": "M"}
    for key in sorted(by_key):
        sex, label = key
        if key not in attested and (other[sex], label) in attested:
            items = by_key.pop(key)
            built.leave_out("wikidata: a name the святцы or the books hold in the other sex alone (left out)", key,
                            ",".join(sorted({i["qid"] for i in items}, key=_qnum)))


def wikidata(path: Path, anchors: set[Key], dropped: dict[Key, str], attested: set[Key],
             built: Built) -> tuple[dict[Key, str], dict[Key, str]]:
    """The Wikidata names the святцы lack ({key: lowest QID}), and the links that make one a variant of a
    святцы name ({key: the anchor's name}). `attested` — the names the святцы and the books hold, by sex."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    built.counts["wikidata: label not one Cyrillic word (left out by the snapshot)"] = len(doc["skipped_labels"])
    by_key: dict[Key, list[dict[str, Any]]] = {}
    label: dict[str, tuple[str | None, str | None]] = {q: (v["label"], v["sex"]) for q, v in doc["links"].items()}
    for item in doc["items"]:
        label[item["qid"]] = (item["label"], item["sex"])
        if not _ANY_CYRILLIC_WORD.fullmatch(item["label"]):
            built.counts["wikidata: label not one Cyrillic word"] += 1
        elif not _CAPITALISED.fullmatch(item["label"]):
            built.counts["wikidata: label not capitalised as a name"] += 1
        elif not is_name(item["label"]):
            for sex in item["sex"]:
                built.leave_out("wikidata: a letter outside the Russian alphabet (left out)", (sex, item["label"]),
                                item["qid"])
        else:
            for sex in item["sex"]:
                by_key.setdefault((sex, item["label"]), []).append(item)
    _not_given_names(by_key, anchors, dropped, built)
    _other_sex(by_key, attested, built)
    pointing: dict[str, set[str]] = {}
    for item in doc["items"]:
        for target in item["p460"]:
            pointing.setdefault(target, set()).add(item["qid"])
    names: dict[Key, str] = {}
    links: dict[Key, str] = {}
    for key in sorted(by_key):
        items = by_key[key]
        if key in anchors:
            built.counts["wikidata: in the святцы (the святцы's)"] += 1
            continue
        names[key] = min((i["qid"] for i in items), key=_qnum)
        reached: set[str] = set()
        for item in items:
            for other in (*item["p460"], *sorted(pointing.get(item["qid"], ()))):
                text, sex = label.get(other, (None, None))
                if not text:
                    built.counts["wikidata P460: target without a Russian label"] += 1
                elif not is_name(text):
                    built.counts["wikidata P460: target label not a name"] += 1
                elif sex and key[0] not in sex:
                    built.counts["wikidata P460: target of the other sex"] += 1
                elif (key[0], text) in anchors and text != key[1]:
                    reached.add(text)
        if len(reached) == 1:
            links[key] = next(iter(reached))
        elif reached:
            built.counts["wikidata: P460 reaches several святцы names (a name of its own)"] += 1
    return names, links


# --- 3. the books' spellings, 4. the maintainer's exceptions --------------------------------------

def corpus(path: Path, built: Built) -> list[tuple[Key, str, str]]:
    """The books' rows: ((sex, name), base, kind)."""
    rows = []
    for _, (sex, name, base, kind) in _tsv(path):
        if not (is_name(name) and is_name(base)):
            built.counts["mk: not a name"] += 1
            continue
        rows.append(((sex, name), base, kind))
    return rows


EXCEPTION_COLUMNS = ("table", "sex", "name", "base", "genitive", "patronymic_m", "patronymic_f",
                     "old_patronymic_m", "old_patronymic_f", "note")


def exceptions(path: Path) -> list[dict[str, str]]:
    out = []
    for number, cells in _tsv(path):
        if cells[0] == "table":
            continue
        if len(cells) != len(EXCEPTION_COLUMNS):
            raise SystemExit(f"{path.name}:{number}: {len(cells)} cells, not {len(EXCEPTION_COLUMNS)}")
        out.append({"line": str(number), **dict(zip(EXCEPTION_COLUMNS, cells, strict=True))})
    return out


# --- the graph ------------------------------------------------------------------------------------

def _nearest(start: Key, adjacent: dict[Key, set[Key]], anchors: set[Key]) -> set[Key]:
    """The anchors nearest to `start` (a path never runs through an anchor)."""
    seen, frontier = {start}, [start]
    while frontier:
        found: set[Key] = set()
        nxt: list[Key] = []
        for node in frontier:
            for other in sorted(adjacent.get(node, ())):
                if other in seen:
                    continue
                seen.add(other)
                if other in anchors:
                    found.add(other)
                else:
                    nxt.append(other)
        if found:
            return found
        frontier = nxt
    return set()


def _chain_end(start: Key, declared: dict[Key, str], known: set[Key]) -> Key | None:
    """The last name of the base dictionary on the books' chain from `start` (start itself left out)."""
    node, last, seen = start, None, {start}
    while node in declared:
        node = (node[0], declared[node])
        if node in seen:
            break
        seen.add(node)
        if node in known:
            last = node
    return last


def build(svyatcy_path: Path = SVYATCY, wikidata_path: Path = WIKIDATA, corpus_path: Path = CORPUS,
          exceptions_path: Path = EXCEPTIONS) -> Built:
    built = Built()
    anchors = svyatcy(svyatcy_path, built)
    editor = exceptions(exceptions_path)
    dropped = {(e["sex"], e["name"]): e["note"] for e in editor if e["table"] == "drop"}
    books = corpus(corpus_path, built)
    # The names the святцы and the books hold, by sex: a pair of the books names both its spelling and its base.
    attested = anchors | {k for key, base, kind in books if kind != "new" for k in (key, (key[0], base))}
    wd_names, wd_links = wikidata(wikidata_path, anchors, dropped, attested, built)
    fixed = {(e["sex"], e["name"]): e for e in editor if e["table"] == "names"}

    every: dict[Key, set[Key]] = {}
    by_books: dict[Key, set[Key]] = {}
    declared: dict[Key, str] = {}

    def link(a: Key, b: Key, *tables: dict[Key, set[Key]]) -> None:
        if a in fixed or b in fixed:
            return
        for table in tables:
            table.setdefault(a, set()).add(b)
            table.setdefault(b, set()).add(a)

    for key, base in sorted(wd_links.items()):
        link(key, (key[0], base), every)
    for key, base, kind in books:
        target = (key[0], base)
        if kind == "new":
            if key in anchors or key in wd_names:
                built.counts["mk new: a name of the base already"] += 1
            else:
                built.leave_out("mk new: no source has it (left out)", key, base)
            continue
        if key in anchors and target in anchors:
            built.leave_out("mk: two святцы names (the святцы keep both)", key, base)
            continue
        if key in anchors:
            built.counts["mk: a святцы name's base turned into its variant"] += 1
            built.turned.append((key[0], base, key[1]))
        declared[key] = base
        link(key, target, every, by_books)

    known = anchors | set(wd_names)
    written = {key for key, _, _ in books}
    resolved: dict[Key, tuple[str, str]] = {}  # variant → (base, source)
    canonical: set[Key] = set(wd_names)
    for node in sorted(set(every) | set(fixed)):
        if node in anchors:
            continue
        own = f"wikidata:{wd_names[node]}" if node in wd_names else ""
        if node in fixed:
            e = fixed[node]
            if node not in known and not (e["base"] and node in written):
                raise SystemExit(f"exceptions.tsv:{e['line']}: {e['name']} is in no source")
            if e["base"]:
                resolved[node] = (e["base"], "editor")
            built.counts["editor: " + ("a variant of the editor's base" if e["base"] else "no variant")] += 1
            continue
        near = _nearest(node, by_books, anchors) if node in by_books else set()
        if len(near) != 1:
            near = _nearest(node, every, anchors)
        if len(near) == 1:
            base = next(iter(near))[1]
        elif near:
            built.leave_out("ambiguous: two святцы names equally near (a name of its own)" if own
                            else "mk: two святцы names equally near (left out)", node,
                            "|".join(sorted(k[1] for k in near)))
            continue
        else:
            end = _chain_end(node, declared, known)
            if end is None:
                if not own and node in declared:
                    built.leave_out("mk: the base is in no source (left out)", node, declared[node])
                elif not own:
                    built.leave_out("mk: a base in no source (left out with its variants)", node, "")
                continue
            base = end[1]
        source = "mk" if node in by_books else own
        resolved[node] = (base, source)
        if node in declared and declared[node] != base:
            built.counts["mk: chain collapsed to its base"] += 1

    for key in sorted(canonical - set(resolved)):
        note = f"editor: {fixed[key]['note']}" if key in fixed else ""
        built.names[key] = (NameEntry(SEX[key[0]], key[1], source=f"wikidata:{wd_names[key]}"), note)
    for key, (base, source) in sorted(resolved.items()):
        note = f"wikidata:{wd_names[key]}" if key in wd_names and source == "mk" else ""
        if source == "editor":
            note = fixed[key]["note"]
        built.names[key] = (NameEntry(SEX[key[0]], key[1], (base,), source=source), note)

    _check_fixed_point(built)
    _forms(editor, built)
    _pins(editor, built)
    _count(built)
    Lexicon.of([built.layer()]).complete()  # a conflict here wants a pin in the exceptions, not a guess
    return built


def _check_fixed_point(built: Built) -> None:
    variants = {k for k, (e, _) in built.names.items() if e.bases}
    for key, (entry, _) in built.names.items():
        for base in entry.bases:
            if (key[0], base) in variants or (key[0], base) not in built.names:
                raise SystemExit(f"{key[1]}: its base {base} is not a canonical name of the base")


def _forms(editor: list[dict[str, str]], built: Built) -> None:
    """The maintainer's forms: a cell is kept only where the rule gives another form."""
    for e in editor:
        if e["table"] != "forms":
            continue
        key = (e["sex"], e["name"])
        if key not in built.names:
            raise SystemExit(f"exceptions.tsv:{e['line']}: {e['name']} is no name of the base")
        sex = SEX[e["sex"]]
        rule = {"genitive": rules.genitive(e["name"], sex),
                "patronymic_m": rules.modern_patronymic(e["name"], Gender.MALE),
                "patronymic_f": rules.modern_patronymic(e["name"], Gender.FEMALE),
                "old_patronymic_m": rules.old_patronymic(e["name"], Gender.MALE),
                "old_patronymic_f": rules.old_patronymic(e["name"], Gender.FEMALE)}
        cells = {column: e[column] or None for column in rule}
        same = [c for c, v in cells.items() if v is not None and v == rule[c]]
        if same:
            raise SystemExit(f"exceptions.tsv:{e['line']}: {e['name']} {', '.join(same)}: the rule gives that already")
        built.forms[key] = FormsEntry(sex, e["name"], *cells.values(), source="editor")  # type: ignore[arg-type]


def _pins(editor: list[dict[str, str]], built: Built) -> None:
    """The maintainer's pins: a short patronymic two names' rules give — `name` the form, `base` its father,
    `patronymic_m`/`patronymic_f` its modern form."""
    for e in editor:
        if e["table"] != "patronymics":
            continue
        key = (e["sex"], e["name"])
        if (e["sex"], e["base"]) not in built.names and ("M", e["base"]) not in built.names:
            raise SystemExit(f"exceptions.tsv:{e['line']}: {e['base']} is no name of the base")
        modern = e["patronymic_m"] if e["sex"] == "M" else e["patronymic_f"]
        built.patronymics[key] = PatronymicEntry(SEX[e["sex"]], e["name"], e["base"], modern or None, "editor")


def _count(built: Built) -> None:
    for (entry, _) in built.names.values():
        source = entry.source.split(":")[0]
        built.counts[f"names: {source} {'variant' if entry.bases else 'canonical'}"] += 1
    built.counts["forms: editor"] = len(built.forms)
    built.counts["patronymics"] = len(built.patronymics)


def write(built: Built, out: Path) -> None:
    tables: dict[str, list[Row]] = {"names": [], "forms": [], "patronymics": []}
    for key in sorted(built.names):
        entry, note = built.names[key]
        tables["names"].append(row_of(entry, note)[1])
    for key in sorted(built.forms):
        tables["forms"].append(row_of(built.forms[key])[1])
    for key in sorted(built.patronymics):
        tables["patronymics"].append(row_of(built.patronymics[key])[1])
    for table in FILES:
        write_table(out, table, tables[table])  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--verbose", action="store_true", help="list the books' names left out, by reason")
    args = parser.parse_args(argv)
    built = build()
    write(built, args.out)
    for name, count in sorted(built.counts.items()):
        print(f"{count:6}  {name}", file=sys.stderr)
    if args.verbose:
        for reason, rows in sorted(built.left_out.items()):
            print(f"{reason}: " + ", ".join(" ".join(r) for r in rows), file=sys.stderr)
        print("turned round: " + ", ".join(f"{s} {name} → {base}" for s, name, base in built.turned), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
